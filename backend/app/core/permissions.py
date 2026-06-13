"""Permission checking utilities."""
import uuid
from enum import IntEnum, StrEnum

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TENANT_AUDIENCE, TENANT_ISSUER, verify_token
from app.database import get_db
from app.models.role import RolePermission
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


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
    SUPPLY_CHAIN_RISK_MAP = "supply_chain_risk_map"
    GROUP = "group"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        if request and hasattr(request.state, "tenant") and request.state.tenant:
            # Tenant route: cryptographically verify tenant issuer/audience
            payload = verify_token(token, issuer=TENANT_ISSUER, audience=TENANT_AUDIENCE)
        else:
            # Single-tenant mode: token has no issuer/audience claims
            payload = verify_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject refresh tokens — they must not be used as access tokens
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    # --- Tenant JWT validation ---
    # If request has a resolved tenant, enforce tenant JWT requirements:
    # - Platform tokens (is_platform_admin) are forbidden on tenant routes
    # - Only tokens issued by the tenant issuer are accepted
    # - tenant_id must be present and must match the resolved tenant
    if request and hasattr(request.state, "tenant") and request.state.tenant:
        if payload.get("is_platform_admin"):
            raise HTTPException(status_code=403, detail="Platform token cannot access tenant routes")
        if payload.get("iss") != TENANT_ISSUER or payload.get("aud") != TENANT_AUDIENCE:
            raise HTTPException(status_code=403, detail="Invalid tenant token")
        jwt_tenant_id = payload.get("tenant_id")
        if not jwt_tenant_id:
            raise HTTPException(status_code=403, detail="Missing tenant_id")
        if jwt_tenant_id != str(request.state.tenant.id):
            raise HTTPException(status_code=403, detail="Token tenant mismatch")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.user_id == user_uuid))
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


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role_definition.role_key != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
