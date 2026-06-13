import logging
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module
from app.core.security import hash_password
from app.core.tenant_utils import set_search_path_sql, slug_to_schema_name
from app.database import async_session
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest

logger = logging.getLogger(__name__)


# Module values used for the initial permission matrix seeded into every tenant.
_PERMISSION_MODULES = [m.value for m in Module]

# role_key -> {module: level}
# Admin gets level 5 on every module. Other roles get the explicit overrides below;
# any module not listed defaults to 0.
_PERMISSION_OVERRIDES = {
    "manager": {
        "fmea": 4, "capa": 4, "dashboard": 4, "audit": 4,
        "customer_quality": 4, "customer_audit": 4, "supplier": 4,
        "iqc": 4, "ppap": 4, "spc": 4, "msa": 4, "planning": 4,
        "management_review": 4, "user_mgmt": 1, "permission_mgmt": 0,
        "special_characteristic": 4, "quality_goal": 4, "scar": 4,
        "group": 4,
    },
    "viewer": {
        "fmea": 1, "capa": 1, "dashboard": 1, "audit": 1,
        "customer_quality": 1, "customer_audit": 1, "supplier": 1,
        "iqc": 1, "ppap": 1, "spc": 1, "msa": 1, "planning": 1,
        "management_review": 1, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 1, "quality_goal": 1, "scar": 1,
    },
    "customer_qe": {
        "fmea": 1, "capa": 2, "dashboard": 1, "audit": 1,
        "customer_quality": 3, "customer_audit": 3, "supplier": 1,
        "iqc": 0, "ppap": 0, "spc": 1, "msa": 0, "planning": 0,
        "management_review": 0, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 0, "quality_goal": 0, "scar": 1,
    },
    "supplier_qe": {
        "fmea": 1, "capa": 2, "dashboard": 1, "audit": 1,
        "customer_quality": 0, "customer_audit": 0, "supplier": 3,
        "iqc": 3, "ppap": 3, "spc": 1, "msa": 0, "planning": 1,
        "management_review": 0, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 0, "quality_goal": 0, "scar": 3,
    },
    "field_qe": {
        "fmea": 3, "capa": 3, "dashboard": 1, "audit": 1,
        "customer_quality": 1, "customer_audit": 1, "supplier": 1,
        "iqc": 1, "ppap": 0, "spc": 3, "msa": 3, "planning": 1,
        "management_review": 1, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 0, "quality_goal": 0, "scar": 1,
    },
    "planning_qe": {
        "fmea": 3, "capa": 1, "dashboard": 1, "audit": 1,
        "customer_quality": 1, "customer_audit": 1, "supplier": 1,
        "iqc": 1, "ppap": 3, "spc": 1, "msa": 0, "planning": 3,
        "management_review": 1, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 3, "quality_goal": 0, "scar": 1,
    },
}

_PERMISSION_MATRIX = {"admin": {m: 5 for m in _PERMISSION_MODULES}}
for role_key, overrides in _PERMISSION_OVERRIDES.items():
    _PERMISSION_MATRIX[role_key] = {m: overrides.get(m, 0) for m in _PERMISSION_MODULES}

_ROLES = [
    # (role_key, name_zh, name_en, is_system, is_editable, bypass_row_level_security, sort_order)
    ("admin", "系统管理员", "System Admin", True, False, True, 1),
    ("manager", "质量经理", "Quality Manager", True, True, False, 2),
    ("viewer", "只读用户", "Viewer", True, False, False, 3),
    ("customer_qe", "客户质量工程师", "Customer QE", True, True, False, 4),
    ("supplier_qe", "供应商质量工程师", "Supplier QE", True, True, False, 5),
    ("field_qe", "现场质量工程师", "Field QE", True, True, False, 6),
    ("planning_qe", "前期策划质量工程师", "Planning QE", True, True, False, 7),
]


def _run_alembic_upgrade(schema_name: str) -> bool:
    """Run alembic upgrade tenant@head for a specific tenant schema."""
    cmd = [
        sys.executable, "-m", "alembic",
        "-x", f"schema={schema_name}",
        "upgrade", "tenant@head",
    ]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Alembic failed for %s:\n%s", schema_name, result.stderr)
        return False
    logger.info("Successfully migrated %s", schema_name)
    return True


@asynccontextmanager
async def _tenant_schema_session(schema_name: str):
    """Open a session whose search_path is set to the given tenant schema."""
    async with async_session() as session:
        await session.execute(text(set_search_path_sql(schema_name)))
        try:
            yield session
        finally:
            await session.rollback()
            await session.execute(text('RESET search_path'))
            await session.close()


async def _seed_roles_and_permissions(tenant_db: AsyncSession):
    """Create the standard role definitions and permission matrix."""
    from app.models.role import RoleDefinition, RolePermission

    role_map = {}
    for role_key, name_zh, name_en, is_system, is_editable, bypass, sort in _ROLES:
        role = RoleDefinition(
            role_key=role_key,
            name_zh=name_zh,
            name_en=name_en,
            is_system=is_system,
            is_editable=is_editable,
            bypass_row_level_security=bypass,
            sort_order=sort,
        )
        tenant_db.add(role)
        await tenant_db.flush()
        role_map[role_key] = role.id

    for role_key, module_levels in _PERMISSION_MATRIX.items():
        role_id = role_map[role_key]
        for module, level in module_levels.items():
            tenant_db.add(RolePermission(role_id=role_id, module=module, permission_level=level))

    await tenant_db.commit()


async def _seed_default_factory_and_product_line(tenant_db: AsyncSession):
    """Create a default factory and product line for the tenant."""
    from app.models.factory import Factory
    from app.models.product_line import ProductLine

    default_factory = Factory(
        id=uuid.uuid4(),
        code="DEFAULT",
        name="默认工厂",
        location="默认地址",
        is_active=True,
    )
    tenant_db.add(default_factory)
    await tenant_db.flush()

    product_line = ProductLine(
        code="DC-DC-100",
        name="DC-DC 转换器",
        is_active=True,
        factory_id=default_factory.id,
    )
    tenant_db.add(product_line)
    await tenant_db.commit()

    return default_factory, product_line


async def _seed_first_admin(
    tenant_db: AsyncSession,
    request: TenantCreateRequest,
    factory_id: uuid.UUID,
    product_line_code: str,
):
    """Create the first tenant admin user."""
    from app.models.factory import UserFactory
    from app.models.role import RoleDefinition, UserProductLine
    from app.models.user import User

    admin_role = (
        await tenant_db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
    ).scalar_one()

    admin = User(
        user_id=uuid.uuid4(),
        username=request.admin_email,
        email=request.admin_email,
        display_name=request.admin_display_name or request.admin_email,
        password_hash=hash_password(request.admin_password),
        role_id=admin_role.id,
        legacy_role="admin",
        factory_id=factory_id,
        is_active=True,
    )
    tenant_db.add(admin)
    await tenant_db.flush()

    tenant_db.add(UserFactory(user_id=admin.user_id, factory_id=factory_id))
    tenant_db.add(UserProductLine(user_id=admin.user_id, product_line_code=product_line_code))
    await tenant_db.commit()

    return admin


class TenantService:
    @staticmethod
    async def provision(db: AsyncSession, request: TenantCreateRequest) -> Tenant:
        """Provision a new tenant: create schema, run migrations, seed data."""
        schema_name = slug_to_schema_name(request.slug)
        subdomain = request.subdomain or request.slug

        # Pre-check uniqueness to avoid IntegrityError 500s during races
        existing = (
            await db.execute(
                select(Tenant).where(
                    or_(
                        Tenant.slug == request.slug,
                        Tenant.schema_name == schema_name,
                        Tenant.subdomain == subdomain,
                    )
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise ValueError("Tenant slug, schema, or subdomain already exists")

        tenant = Tenant(
            name=request.name,
            slug=request.slug,
            schema_name=schema_name,
            subdomain=subdomain,
            plan=request.plan or "free",
            status="provisioning",
            provisioning_step="create_schema",
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

        try:
            # Step 1: Create schema
            await db.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            await db.commit()
            tenant.provisioning_step = "run_migrations"

            # Step 2: Run tenant migrations to create business tables
            migrations_ok = _run_alembic_upgrade(schema_name)
            if not migrations_ok:
                raise RuntimeError(f"Alembic migration failed for schema {schema_name}")
            tenant.provisioning_step = "seed_data"

            # Step 3: Seed initial tenant data
            async with _tenant_schema_session(schema_name) as tenant_db:
                await _seed_roles_and_permissions(tenant_db)
                factory, product_line = await _seed_default_factory_and_product_line(tenant_db)
                await _seed_first_admin(tenant_db, request, factory.id, product_line.code)

            tenant.status = "active"
            tenant.provisioning_step = None
            await db.commit()
        except Exception as e:
            tenant.status = "failed"
            tenant.provisioning_error = str(e)
            await db.commit()
            logger.error("Tenant provisioning failed for %s: %s", request.slug, e)
            raise

        return tenant
