"""Permission checking utilities."""
import uuid
from enum import IntEnum, StrEnum
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.models.role import RolePermission

bearer_scheme = HTTPBearer()


class PermissionLevel(IntEnum):
    NONE = 0
    VIEW = 1
    CREATE = 2
    EDIT = 3
    APPROVE = 4
    ADMIN = 5


class Module(StrEnum):
    FMEA = "fmea"
    CAPA = "capa"
    DASHBOARD = "dashboard"
    AUDIT = "audit"
    CUSTOMER_QUALITY = "customer_quality"
    CUSTOMER_AUDIT = "customer_audit"
    SUPPLIER = "supplier"
    IQC = "iqc"
    PPAP = "ppap"
    SPC = "spc"
    MSA = "msa"
    PLANNING = "planning"
    MANAGEMENT_REVIEW = "management_review"
    USER_MGMT = "user_mgmt"
    PERMISSION_MGMT = "permission_mgmt"
    SPECIAL_CHARACTERISTIC = "special_characteristic"
    QUALITY_GOAL = "quality_goal"
    SCAR = "scar"
    KNOWLEDGE_GRAPH = "knowledge_graph"  # 新增
    MES = "mes"
    PLM = "plm"
    ERP = "erp"
    SUPPLIER_RISK = "supplier_risk"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.user_id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_user_permission(
    user: User,
    module: Module,
    db: AsyncSession,
) -> PermissionLevel:
    result = await db.execute(
        select(RolePermission.permission_level)
        .where(RolePermission.role_id == user.role_id)
        .where(RolePermission.module == module.value)
    )
    level = result.scalar_one_or_none()
    return PermissionLevel(level) if level is not None else PermissionLevel.NONE


def require_permission(module: Module, min_level: PermissionLevel):
    async def _check(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        level = await get_user_permission(user, module, db)
        if level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要 {module.value} 模块的 {min_level.name} 权限",
            )
        return user
    return _check


# Backward-compatible wrappers
async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role_definition.role_key != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_engineer_or_admin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Deprecated: redirects to permission check."""
    level = await get_user_permission(user, Module.FMEA, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="编辑权限不足")
    return user
