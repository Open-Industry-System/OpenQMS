"""Service-layer tests for product_type_code filtering in semantic search + QA."""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select as _select

from app.core.permissions import Module
from app.models.factory import Factory
from app.models.product_line import ProductLine
from app.models.product_type import ProductType
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from app.services.search_service import SearchService


async def _admin_user_with_permissions(db, factory: Factory) -> User:
    """Create an admin user with all search-relevant module permissions."""
    result = await db.execute(
        _select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        role = RoleDefinition(
            role_key="admin",
            name_zh="管理员",
            name_en="Admin",
            is_system=True,
            is_active=True,
        )
        db.add(role)
        await db.flush()
        await db.refresh(role)

    # Seed permissions for every entity type used by SearchService (idempotent)
    existing_result = await db.execute(
        _select(RolePermission.module).where(RolePermission.role_id == role.id)
    )
    existing_modules = {row[0] for row in existing_result.fetchall()}
    for module in [
        Module.FMEA,
        Module.CAPA,
        Module.AUDIT,
        Module.CUSTOMER_QUALITY,
        Module.SCAR,
    ]:
        if module.value not in existing_modules:
            db.add(RolePermission(role_id=role.id, module=module.value, permission_level=5))
    await db.flush()

    user = User(
        user_id=uuid.uuid4(),
        username=f"search_admin_{uuid.uuid4().hex[:8]}",
        display_name="Search Admin",
        password_hash="hashed",
        role_id=role.id,
        legacy_role="admin",
        is_active=True,
        factory_id=factory.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_semantic_search_filters_by_product_type(db, default_factory):
    """product_type_code=POWER should keep only product lines whose product_type_code is POWER."""
    # Seed product types
    for code, name in [("POWER", "动力类"), ("MOTOR", "电机类")]:
        db.add(ProductType(code=code, name=name, is_active=True))
    await db.flush()

    # Seed product lines with distinct product_type_code assignments
    pl_codes = [
        ("PT-DC-100", "POWER"),
        ("PT-AC-200", "POWER"),
        ("PT-MOTOR-100", "MOTOR"),
    ]
    for code, ptype in pl_codes:
        db.add(ProductLine(
            code=code,
            name=code,
            factory_id=default_factory.id,
            product_type_code=ptype,
        ))
    await db.flush()

    user = await _admin_user_with_permissions(db, default_factory)

    service = SearchService(db=db, llm_provider=None, embedding_provider=None)
    real_execute = service.db.execute

    # Fake search result rows: two POWER rows and one MOTOR row
    power_rows = [
        ("1", "fmea_node", uuid.uuid4(), None, "field", "POWER row 1", "PT-DC-100", {}, 0.9),
        ("2", "fmea_node", uuid.uuid4(), None, "field", "POWER row 2", "PT-AC-200", {}, 0.8),
    ]
    motor_rows = [
        ("3", "fmea_node", uuid.uuid4(), None, "field", "MOTOR row", "PT-MOTOR-100", {}, 0.85),
    ]
    all_rows = power_rows + motor_rows

    class FakeScalarRow:
        def __init__(self, value):
            self._value = value

        def __getitem__(self, idx):
            if idx == 0:
                return self._value
            raise IndexError(idx)

    class FakeRow:
        def __init__(self, row):
            self._mapping = {
                "id": row[0],
                "entity_type": row[1],
                "entity_id": row[2],
                "node_id": row[3],
                "entity_field": row[4],
                "chunk_text": row[5],
                "product_line_code": row[6],
                "metadata": row[7],
                "score": row[8],
            }

    class FakeResult:
        def __init__(self, rows, scalar=False):
            self._rows = rows
            self._scalar = scalar

        def fetchall(self):
            if self._scalar:
                return [FakeScalarRow(r[0]) for r in self._rows]
            return [FakeRow(r) for r in self._rows]

    async def _fake_execute(stmt, params=None):
        text_str = str(stmt.compile(compile_kwargs={"literal_binds": True})) if hasattr(stmt, "compile") else str(stmt)

        # The new type-resolution query in semantic_search
        if "product_lines" in text_str and "product_type_code" in text_str:
            target_type = params.get("product_type_code") if params else None
            if target_type is None:
                # SQLAlchemy may bind the value positionally; infer from statement text
                target_type = "POWER"
            matched = [(code,) for code, ptype in pl_codes if ptype == target_type]
            return FakeResult(matched, scalar=True)

        # Vector/fulltext raw queries against document_embeddings
        if "document_embeddings" in text_str:
            allowed = set(params.get("product_type_codes", [])) if params else set()
            if allowed:
                filtered = [r for r in all_rows if r[6] in allowed]
                return FakeResult(filtered)
            return FakeResult(all_rows)

        # Everything else (permissions, user product lines, etc.) uses the real DB
        return await real_execute(stmt, params)

    service.db.execute = AsyncMock(side_effect=_fake_execute)

    response = await service.semantic_search(
        query="test",
        user=user,
        product_type_code="POWER",
        entity_types=["fmea_node"],
        limit=10,
    )

    returned_codes = {r.product_line_code for r in response.results}
    assert returned_codes == {"PT-DC-100", "PT-AC-200"}
    assert "PT-MOTOR-100" not in returned_codes


@pytest.mark.asyncio
async def test_semantic_search_mismatched_pl_and_type_returns_empty(db, default_factory):
    """When both product_line_code and product_type_code are supplied but the PL
    does not belong to that type, return empty instead of silently honoring the
    (stale) product_line_code and ignoring the type filter."""
    for code, name in [("POWER", "动力类"), ("MOTOR", "电机类")]:
        db.add(ProductType(code=code, name=name, is_active=True))
    await db.flush()
    pl_codes = [("PT-DC-100", "POWER"), ("PT-AC-200", "POWER"), ("PT-MOTOR-100", "MOTOR")]
    for code, ptype in pl_codes:
        db.add(ProductLine(code=code, name=code, factory_id=default_factory.id, product_type_code=ptype))
    await db.flush()

    user = await _admin_user_with_permissions(db, default_factory)
    service = SearchService(db=db, llm_provider=None, embedding_provider=None)
    real_execute = service.db.execute

    class FakeScalarRow:
        def __init__(self, value):
            self._value = value
        def __getitem__(self, idx):
            if idx == 0:
                return self._value
            raise IndexError(idx)

    class FakeResult:
        def __init__(self, rows, scalar=False):
            self._rows = rows
            self._scalar = scalar
        def fetchall(self):
            if self._scalar:
                return [FakeScalarRow(r[0]) for r in self._rows]
            return []

    async def _fake_execute(stmt, params=None):
        text_str = str(stmt.compile(compile_kwargs={"literal_binds": True})) if hasattr(stmt, "compile") else str(stmt)
        if "product_lines" in text_str and "product_type_code" in text_str:
            # Resolve POWER -> its PL codes; PT-MOTOR-100 is not among them.
            matched = [(c,) for c, p in pl_codes if p == "POWER"]
            return FakeResult(matched, scalar=True)
        return await real_execute(stmt, params)

    service.db.execute = AsyncMock(side_effect=_fake_execute)

    response = await service.semantic_search(
        query="test",
        user=user,
        product_line_code="PT-MOTOR-100",   # belongs to MOTOR, not POWER
        product_type_code="POWER",
        entity_types=["fmea_node"],
        limit=10,
    )
    assert response.results == []
    assert response.total == 0
