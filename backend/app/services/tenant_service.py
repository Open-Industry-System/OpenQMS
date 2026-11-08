import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest


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

    await tenant_db.flush()


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
    await tenant_db.flush()

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
    await tenant_db.flush()

    return admin


class TenantService:
    @staticmethod
    async def provision(db: AsyncSession, request: TenantCreateRequest) -> Tenant:
        """Register once and provision through the owner-bound coordinator.

        db is the platform-admin session supplied by the API. The coordinator
        owns its own short-lived platform transactions and exclusive owner.
        """
        from app.services.tenant_migrator import provision_new

        return await provision_new(request)
