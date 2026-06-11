import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_refresh_token
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse, TokenResponse, RefreshTokenRequest, RefreshTokenResponse
from app.services.permission_service import get_role_permissions
from app.core.product_line_filter import get_user_product_line_codes

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def build_user_response(user: User, db: AsyncSession) -> UserResponse:
    permissions = await get_role_permissions(db, user.role_id)
    if user.role_definition.bypass_row_level_security:
        result = await db.execute(select(ProductLine.code, ProductLine.name).where(ProductLine.is_active == True))
        product_lines = [{"product_line_code": code, "name": name} for code, name in result.all()]
    else:
        codes = await get_user_product_line_codes(user, db)
        product_lines = [{"product_line_code": code} for code in codes]

    # Factory scope
    from app.core.factory_scope import get_user_factory_ids, resolve_factory_scope
    from app.core.permissions import Module, get_user_permission, PermissionLevel
    from app.models.factory import Factory

    user_factory_ids = await get_user_factory_ids(user, db)
    group_level = await get_user_permission(user, Module.GROUP, db)
    factory_scope = resolve_factory_scope(user, user_factory_ids, group_level >= PermissionLevel.ADMIN)

    # Fetch accessible factories
    if factory_scope.accessible_factory_ids is None:
        fresult = await db.execute(
            select(Factory).where(Factory.is_active == True).order_by(Factory.code)
        )
    else:
        fresult = await db.execute(
            select(Factory).where(Factory.id.in_(factory_scope.accessible_factory_ids), Factory.is_active == True).order_by(Factory.code)
        )
    factory_records = fresult.scalars().all()

    factory_scope_dict = {
        "accessible_factory_ids": [str(fid) for fid in factory_scope.accessible_factory_ids] if factory_scope.accessible_factory_ids is not None else None,
        "default_factory_id": str(factory_scope.default_factory_id) if factory_scope.default_factory_id else None,
    }
    factories_list = [
        {"id": str(f.id), "code": f.code, "name": f.name, "location": f.location, "is_active": f.is_active}
        for f in factory_records
    ]

    return UserResponse(
        user_id=user.user_id, username=user.username,
        display_name=user.display_name, email=user.email,
        role_key=user.role_definition.role_key, legacy_role=user.legacy_role,
        permissions=permissions, product_lines=product_lines,
        bypass_row_level_security=user.role_definition.bypass_row_level_security,
        is_active=user.is_active, auditor_info=user.auditor_info,
        factory_scope=factory_scope_dict, factories=factories_list,
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(user.user_id))
    refresh_token, refresh_expires = create_refresh_token(str(user.user_id))
    user.refresh_token = refresh_token
    user.refresh_token_expires = refresh_expires
    await db.commit()
    user_resp = await build_user_response(user, db)
    return TokenResponse(access_token=token, refresh_token=refresh_token, user=user_resp)


@router.post("/register", response_model=UserResponse)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username exists")
    role_def = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == req.role_key))
    role_def = role_def.scalar_one_or_none()
    if role_def is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role_key")
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name or req.username,
        email=req.email,
        role_id=role_def.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await build_user_response(user, db)


@router.get("/users", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db), _user: User = Depends(require_admin)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [await build_user_response(u, db) for u in users]


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await build_user_response(user, db)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(req: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    user_id = decode_refresh_token(req.refresh_token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.refresh_token != req.refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if user.refresh_token_expires and user.refresh_token_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
    new_access = create_access_token(str(user.user_id))
    new_refresh, new_expires = create_refresh_token(str(user.user_id))
    user.refresh_token = new_refresh
    user.refresh_token_expires = new_expires
    await db.commit()
    return RefreshTokenResponse(access_token=new_access, refresh_token=new_refresh)
