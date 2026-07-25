"""用户管理服务：更新、停用、删除。

Service 负责校验与变更，抛 LookupError(不存在)/ValueError(校验/护栏)，不 commit；
API 层转换 HTTPException 并在单事务内 commit。
"""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.factory_scope import get_user_factory_ids
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.factory import Factory, UserFactory
from app.models.role import RoleDefinition
from app.models.user import User
from app.schemas.auth import validate_password_complexity

# 显式 null 视为非法的字段（不可"清空"）
_NON_NULLABLE_FIELDS = ("role_key", "password", "is_active", "factory_ids")


async def _count_active_admins(db: AsyncSession) -> int:
    result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
    return sum(1 for u in result.scalars().all() if u.role_definition.role_key == "admin")


async def update_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    updates: dict,
    acting_user_id: uuid.UUID,
) -> User:
    """校验并应用用户字段变更（含 factory 集合 + 默认工厂），不 commit。"""
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise LookupError(f"用户 '{user_id}' 不存在")

    # 1. 显式 null 拒绝（不可清空字段）
    for key in _NON_NULLABLE_FIELDS:
        if key in updates and updates[key] is None:
            raise ValueError(f"字段 '{key}' 不能为空")

    # 2. role_key 校验（暂存，guards 之后再写）
    new_role_key = None
    if "role_key" in updates:
        new_role_key = updates["role_key"]
        rd = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == new_role_key))
        if rd.scalar_one_or_none() is None:
            raise ValueError(f"无效角色 '{new_role_key}'")

    # 3. password 校验（暂存；复杂度不合法在此抛错，先于任何变更）
    new_password = None
    if "password" in updates:
        new_password = updates["password"]
        validate_password_complexity(new_password)

    # 4. factory_ids 校验（暂存）
    new_factory_ids: list[uuid.UUID] | None = None
    if "factory_ids" in updates:
        new_factory_ids = list(updates["factory_ids"])
        if len(new_factory_ids) != len(set(new_factory_ids)):
            raise ValueError("factory_ids 中存在重复工厂")
        for fid in new_factory_ids:
            fr = await db.execute(select(Factory).where(Factory.id == fid))
            f = fr.scalar_one_or_none()
            if f is None or not f.is_active:
                raise ValueError(f"无效或已停用的工厂 '{fid}'")

    # 5. 计算有效工厂集合
    if new_factory_ids is not None:
        effective = set(new_factory_ids)
    else:
        effective = set(await get_user_factory_ids(user, db))

    # 6. default_factory_id 校验
    explicit_default = "default_factory_id" in updates
    if explicit_default:
        val = updates["default_factory_id"]
        if val is not None and val not in effective:
            raise ValueError("默认工厂必须在可访问工厂集合内")

    # 7. 护栏（基于当前状态）
    current_is_admin = user.role_definition.role_key == "admin" and user.is_active
    will_deactivate = "is_active" in updates and updates["is_active"] is False
    will_demote_admin = current_is_admin and new_role_key is not None and new_role_key != "admin"
    if will_deactivate and user.user_id == acting_user_id:
        raise ValueError("不能停用自己的账号")
    if (will_deactivate or will_demote_admin) and current_is_admin:
        if await _count_active_admins(db) <= 1:
            raise ValueError("不能停用或降级最后一个管理员")

    changes: dict = {}

    # 8. 应用标量变更
    if "display_name" in updates:
        val = updates["display_name"]
        if isinstance(val, str):
            val = val.strip() or None
        if val != user.display_name:
            changes["display_name"] = val
            user.display_name = val
    if "email" in updates:
        val = updates["email"]
        if isinstance(val, str):
            val = val.strip() or None
        if val != user.email:
            changes["email"] = val
            user.email = val
    if "is_active" in updates and updates["is_active"] is not None:
        if updates["is_active"] != user.is_active:
            changes["is_active"] = updates["is_active"]
            user.is_active = updates["is_active"]
    if new_role_key is not None:
        role_def = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == new_role_key))).scalar_one()
        changes["role_key"] = new_role_key
        user.role_id = role_def.id
        user.legacy_role = new_role_key
    if new_password is not None:
        user.password_hash = hash_password(new_password)
        user.refresh_token = None
        user.refresh_token_expires = None
        changes["password"] = "[reset]"

    # 9. 默认工厂 + 工厂集合
    if explicit_default:
        val = updates["default_factory_id"]
        if val != user.factory_id:
            changes["default_factory_id"] = str(val) if val else None
            user.factory_id = val
    elif new_factory_ids is not None:
        if not new_factory_ids:
            if user.factory_id is not None:
                changes["default_factory_id"] = None
                user.factory_id = None
        elif user.factory_id not in new_factory_ids:
            changes["default_factory_id"] = str(new_factory_ids[0])
            user.factory_id = new_factory_ids[0]

    if new_factory_ids is not None:
        await db.execute(delete(UserFactory).where(UserFactory.user_id == user.user_id))
        for fid in new_factory_ids:
            db.add(UserFactory(user_id=user.user_id, factory_id=fid))
        changes["factory_ids"] = [str(f) for f in new_factory_ids]

    # 10. 审计日志
    db.add(AuditLog(
        table_name="users",
        record_id=user.user_id,
        action="UPDATE",
        changed_fields=changes,
        operated_by=acting_user_id,
    ))
    return user


async def delete_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> None:
    """校验并删除用户（不 commit；API 层 commit 并捕获 IntegrityError→409）。"""
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise LookupError(f"用户 '{user_id}' 不存在")

    if user.user_id == acting_user_id:
        raise ValueError("不能删除自己的账号")

    if user.role_definition.role_key == "admin" and user.is_active:
        if await _count_active_admins(db) <= 1:
            raise ValueError("不能删除最后一个管理员")

    db.add(AuditLog(
        table_name="users",
        record_id=user.user_id,
        action="DELETE",
        changed_fields={"username": user.username, "role_key": user.role_definition.role_key},
        operated_by=acting_user_id,
    ))
    await db.delete(user)
