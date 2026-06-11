"""Multi-factory scope resolution and data filtering.

Three-layer scope model:
- FactoryScope: which factories the user can access
- ProductLineScope: which product lines the user can access
- PermissionScope: what operations the user can perform (handled by existing permissions.py)

Key design: bypass_row_level_security ONLY bypasses product-line filtering, NOT factory scope.
Only Module.GROUP ADMIN grants cross-factory visibility.
"""
import uuid
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.role import UserProductLine
from app.models.factory import UserFactory


@dataclass
class FactoryScope:
    """Resolved factory scope, immutable, for the entire request lifetime."""
    accessible_factory_ids: list[UUID] | None  # None = all factories (GROUP ADMIN only)
    default_factory_id: UUID | None            # default factory for creating records


@dataclass
class ProductLineScope:
    """Resolved product line scope."""
    mode: str               # "ALL" | "EXPLICIT" | "NONE"
    codes: list[str] | None # product line codes for EXPLICIT mode


def resolve_factory_scope(
    user: User,
    user_factory_ids: list[UUID],
    has_group_admin: bool,
) -> FactoryScope:
    # 1. GROUP ADMIN → all factories visible
    if has_group_admin:
        return FactoryScope(accessible_factory_ids=None, default_factory_id=user.factory_id)

    # 2. Has user_factories records → limited to those factories
    if user_factory_ids:
        return FactoryScope(
            accessible_factory_ids=user_factory_ids,
            default_factory_id=user.factory_id or user_factory_ids[0],
        )

    # 3. Factory user (no user_factories but has factory_id) → fallback to own factory
    if user.factory_id:
        return FactoryScope(
            accessible_factory_ids=[user.factory_id],
            default_factory_id=user.factory_id,
        )

    # 4. No factory association → no data access
    return FactoryScope(accessible_factory_ids=[], default_factory_id=None)


def resolve_product_line_scope(
    user: User,
    user_product_line_codes: list[str],
    factory_scope: FactoryScope,
) -> ProductLineScope:
    # 1. bypass_row_level_security → product line not filtered (but factory still is!)
    if user.role_definition.bypass_row_level_security:
        return ProductLineScope(mode="ALL", codes=None)

    # 2. No product line assignment → no data access
    if not user_product_line_codes:
        return ProductLineScope(mode="NONE", codes=None)

    # 3. Has explicit product line assignments
    return ProductLineScope(mode="EXPLICIT", codes=user_product_line_codes)


def resolve_effective_factory_id(
    scope: FactoryScope,
    requested_factory_id: UUID | None,
) -> UUID | None:
    """Resolve the effective factory ID for this request.
    Returns None meaning 'do not filter by factory' (GROUP ADMIN without specific factory).
    """
    if scope.accessible_factory_ids is None:
        return requested_factory_id  # GROUP ADMIN: allow any or no filter

    if requested_factory_id is None:
        if len(scope.accessible_factory_ids) == 1:
            return scope.accessible_factory_ids[0]  # Single-factory user locked
        return None  # Multi-factory user without selection → see all accessible

    if requested_factory_id not in scope.accessible_factory_ids:
        raise HTTPException(status_code=403, detail=f"无权访问工厂 '{requested_factory_id}'")
    return requested_factory_id


def apply_scope_filter(
    query,
    model: type,
    module: str,
    factory_scope: FactoryScope,
    effective_factory_id: UUID | None,
    pl_scope: ProductLineScope,
    user: User,
    db: AsyncSession,
):
    """Apply factory + product line scope filtering to a query.

    Replaces the old apply_product_line_filter. Two-layer filtering:
    1. Factory filter: model.factory_id == effective_factory_id (or IN accessible_factory_ids)
    2. Product line filter: based on ProductLineScope mode
    """
    # Layer 1: Factory filtering
    if hasattr(model, "factory_id"):
        if effective_factory_id is not None:
            query = query.where(model.factory_id == effective_factory_id)
        elif factory_scope.accessible_factory_ids is not None:
            if factory_scope.accessible_factory_ids:
                query = query.where(model.factory_id.in_(factory_scope.accessible_factory_ids))
            else:
                query = query.where(False)  # No accessible factories
        # else: GROUP ADMIN without specific factory → no factory filter

    # Layer 2: Product line filtering
    if pl_scope.mode == "NONE":
        # No product line access at all — but only filter if model has product_line field
        pl_field = _get_product_line_field(model, module)
        if pl_field:
            query = query.where(False)
    elif pl_scope.mode == "EXPLICIT" and pl_scope.codes:
        pl_field = _get_product_line_field(model, module)
        if pl_field:
            query = query.where(pl_field.in_(pl_scope.codes))
    # ALL mode: no product line filter

    return query


# Module → product line field name mapping
_PRODUCT_LINE_FIELD_MAP: dict[str, str] = {
    "fmea": "product_line_code",
    "capa": "product_line_code",
    "audit": "product_line_code",
    "customer_quality": "product_line_code",
    "customer_audit": "product_line_code",
    "iqc": "product_line_code",
    "ppap": "product_line_code",
    "spc": "product_line",
    "msa": "product_line_code",
    "planning": "product_line_code",
    "management_review": "product_line_code",
    "special_characteristic": "product_line_code",
    "quality_goal": "product_line_code",
    "scar": "product_line_code",
    "mes": "product_line_code",
    "plm": "product_line_code",
    "erp": "product_line_code",
    "supplier_risk": "product_line_code",
    "control_plan": "product_line_code",
    "cp_validation": "product_line_code",
    "knowledge_graph": "product_line_code",
}


def _get_product_line_field(model: type, module: str):
    """Get the product line field attribute for the model, or None."""
    field_name = _PRODUCT_LINE_FIELD_MAP.get(module)
    if field_name and hasattr(model, field_name):
        return getattr(model, field_name)
    return None


async def get_user_factory_ids(user: User, db: AsyncSession) -> list[UUID]:
    """Fetch the list of factory IDs the user has access to via user_factories."""
    result = await db.execute(
        select(UserFactory.factory_id).where(UserFactory.user_id == user.user_id)
    )
    return [row[0] for row in result.all()]


async def get_user_product_line_codes(user: User, db: AsyncSession) -> list[str]:
    """Fetch the list of product line codes the user has access to."""
    result = await db.execute(
        select(UserProductLine.product_line_code).where(UserProductLine.user_id == user.user_id)
    )
    return [row[0] for row in result.all()]


async def populate_factory_id(
    record,
    model: type,
    db: AsyncSession,
    scope: "RequestScope" = None,
    default_factory_id: UUID | None = None,
):
    """Populate factory_id on a record based on its derivation category.

    Derivation rules (from spec §3.5):
    - product_line_derived: factory_id from ProductLine[record.product_line_code].factory_id
    - parent_derived: factory_id from parent record
    - supplier_derived: factory_id from Supplier[record.supplier_id].factory_id
    - connection_derived: factory_id from Connection[record.connection_id].factory_id
    - explicit_scope: factory_id from scope.default_factory_id
    """
    if not hasattr(record, "factory_id") or record.factory_id is not None:
        return  # Already set or model doesn't have factory_id

    # Product-line-derived: if record has product_line_code, look up factory_id
    if hasattr(record, "product_line_code") and record.product_line_code:
        from app.models.product_line import ProductLine
        result = await db.execute(
            select(ProductLine.factory_id).where(ProductLine.code == record.product_line_code)
        )
        factory_id = result.scalar_one_or_none()
        if factory_id:
            record.factory_id = factory_id
            return

    # SPC uses 'product_line' instead of 'product_line_code'
    if hasattr(record, "product_line") and record.product_line:
        from app.models.product_line import ProductLine
        result = await db.execute(
            select(ProductLine.factory_id).where(ProductLine.code == record.product_line)
        )
        factory_id = result.scalar_one_or_none()
        if factory_id:
            record.factory_id = factory_id
            return

    # Parent-derived: check common parent FKs
    parent_derived = _get_parent_factory_id(record, db)
    if parent_derived is not None:
        # This is an awaitable
        fid = await parent_derived
        if fid:
            record.factory_id = fid
            return

    # Explicit scope: use default_factory_id from scope
    factory_id = default_factory_id
    if scope and hasattr(scope, "effective_factory_id") and factory_id is None:
        factory_id = scope.effective_factory_id
    if scope and hasattr(scope, "factory_scope") and factory_id is None:
        factory_id = scope.factory_scope.default_factory_id

    if factory_id:
        record.factory_id = factory_id


async def _get_parent_factory_id(record, db: AsyncSession) -> UUID | None:
    """Try to derive factory_id from parent record via common FK patterns."""
    # FMEA version → FMEADocument
    if hasattr(record, "fmea_id") and record.fmea_id:
        from app.models.fmea import FMEADocument
        result = await db.execute(
            select(FMEADocument.factory_id).where(FMEADocument.id == record.fmea_id)
        )
        return result.scalar_one_or_none()

    # Control plan version → ControlPlan
    if hasattr(record, "cp_id") and record.cp_id:
        from app.models.control_plan import ControlPlan
        result = await db.execute(
            select(ControlPlan.factory_id).where(ControlPlan.id == record.cp_id)
        )
        return result.scalar_one_or_none()

    # Supplier sub-tables → Supplier
    if hasattr(record, "supplier_id") and record.supplier_id:
        from app.models.supplier import Supplier
        result = await db.execute(
            select(Supplier.factory_id).where(Supplier.supplier_id == record.supplier_id)
        )
        return result.scalar_one_or_none()

    # Audit sub-tables → AuditProgram
    if hasattr(record, "program_id") and record.program_id:
        from app.models.audit_program import AuditProgram
        result = await db.execute(
            select(AuditProgram.factory_id).where(AuditProgram.program_id == record.program_id)
        )
        return result.scalar_one_or_none()

    # MES/PLM/ERP connection sub-tables
    if hasattr(record, "connection_id") and record.connection_id:
        conn_factory_id = await _get_connection_factory_id(record, db)
        if conn_factory_id:
            return conn_factory_id

    return None


async def _get_connection_factory_id(record, db: AsyncSession) -> UUID | None:
    """Derive factory_id from a connection record (MES/PLM/ERP)."""
    table_name = record.__tablename__ if hasattr(record, "__tablename__") else ""

    if table_name.startswith("mes_") or "mes_" in table_name:
        from app.models.mes import MESConnection
        result = await db.execute(
            select(MESConnection.factory_id).where(MESConnection.id == record.connection_id)
        )
        return result.scalar_one_or_none()

    if table_name.startswith("plm_") or "plm_" in table_name:
        from app.models.plm import PLMConnection
        result = await db.execute(
            select(PLMConnection.factory_id).where(PLMConnection.id == record.connection_id)
        )
        return result.scalar_one_or_none()

    if table_name.startswith("erp_") or "erp_" in table_name:
        from app.models.erp import ERPConnection
        result = await db.execute(
            select(ERPConnection.factory_id).where(ERPConnection.id == record.connection_id)
        )
        return result.scalar_one_or_none()

    return None


async def validate_factory_invariant(
    record,
    db: AsyncSession,
):
    """Validate that factory_id is consistent with the record's derivation path.

    Raises ValueError if inconsistent.
    """
    if not hasattr(record, "factory_id") or record.factory_id is None:
        return  # Nothing to validate

    # Product-line-derived: factory_id must match product_lines.factory_id
    if hasattr(record, "product_line_code") and record.product_line_code:
        from app.models.product_line import ProductLine
        result = await db.execute(
            select(ProductLine.factory_id).where(ProductLine.code == record.product_line_code)
        )
        expected = result.scalar_one_or_none()
        if expected and record.factory_id != expected:
            raise ValueError(
                f"factory_id 不一致：产品线 '{record.product_line_code}' 属于工厂 {expected}，"
                f"但记录的 factory_id 为 {record.factory_id}"
            )

    # SPC uses 'product_line' instead of 'product_line_code'
    if hasattr(record, "product_line") and record.product_line:
        from app.models.product_line import ProductLine
        result = await db.execute(
            select(ProductLine.factory_id).where(ProductLine.code == record.product_line)
        )
        expected = result.scalar_one_or_none()
        if expected and record.factory_id != expected:
            raise ValueError(
                f"factory_id 不一致：产品线 '{record.product_line}' 属于工厂 {expected}，"
                f"但记录的 factory_id 为 {record.factory_id}"
            )