"""Permission management service."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User


async def list_roles(db: AsyncSession) -> list[RoleDefinition]:
    result = await db.execute(
        select(RoleDefinition).order_by(RoleDefinition.sort_order)
    )
    return result.scalars().all()


async def get_role_by_key(db: AsyncSession, role_key: str) -> RoleDefinition | None:
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == role_key)
    )
    return result.scalar_one_or_none()


async def get_role_permissions(
    db: AsyncSession, role_id: uuid.UUID
) -> dict[str, int]:
    result = await db.execute(
        select(RolePermission.module, RolePermission.permission_level)
        .where(RolePermission.role_id == role_id)
    )
    return {module: level for module, level in result.all()}


async def update_role_permissions(
    db: AsyncSession,
    role_key: str,
    permissions: list[dict],
) -> None:
    from app.core.permissions import Module

    role = await get_role_by_key(db, role_key)
    if not role:
        raise ValueError(f"角色 '{role_key}' 不存在")
    if not role.is_editable:
        raise ValueError(f"角色 '{role_key}' 权限不可修改")

    valid_modules = set(m.value for m in Module)
    for p in permissions:
        if p["module"] not in valid_modules:
            raise ValueError(f"无效模块 '{p['module']}'")

    await db.execute(
        delete(RolePermission).where(RolePermission.role_id == role.id)
    )
    for p in permissions:
        db.add(RolePermission(
            role_id=role.id,
            module=p["module"],
            permission_level=p["level"],
        ))


async def assign_product_line(
    db: AsyncSession, user_id: uuid.UUID, product_line_code: str
) -> UserProductLine:
    from app.models.product_line import ProductLine

    user_result = await db.execute(select(User).where(User.user_id == user_id))
    if not user_result.scalar_one_or_none():
        raise ValueError(f"用户 '{user_id}' 不存在")

    pl_result = await db.execute(
        select(ProductLine).where(ProductLine.code == product_line_code)
    )
    if not pl_result.scalar_one_or_none():
        raise ValueError(f"产品线 '{product_line_code}' 不存在")

    existing = await db.execute(
        select(UserProductLine)
        .where(UserProductLine.user_id == user_id)
        .where(UserProductLine.product_line_code == product_line_code)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"用户已分配产品线 '{product_line_code}'")

    upl = UserProductLine(user_id=user_id, product_line_code=product_line_code)
    db.add(upl)
    return upl


async def remove_product_line(
    db: AsyncSession, user_id: uuid.UUID, product_line_code: str
) -> None:
    await db.execute(
        delete(UserProductLine)
        .where(UserProductLine.user_id == user_id)
        .where(UserProductLine.product_line_code == product_line_code)
    )


async def get_user_product_lines(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserProductLine]:
    result = await db.execute(
        select(UserProductLine).where(UserProductLine.user_id == user_id)
    )
    return result.scalars().all()
