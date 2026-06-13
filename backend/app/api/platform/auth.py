from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app.core.security import (
    verify_password,
    create_platform_admin_token,
)
from app.database import get_platform_db
from app.models.platform_admin import PlatformAdminUser
from app.schemas.platform import PlatformLoginRequest, PlatformLoginResponse

router = APIRouter()


@router.post("/auth/login", response_model=PlatformLoginResponse)
async def platform_login(request: PlatformLoginRequest, db=Depends(get_platform_db)):
    """Platform admin login — authenticates against platform_admin_users in public schema."""
    result = await db.execute(
        select(PlatformAdminUser).where(PlatformAdminUser.email == request.email)
    )
    admin = result.scalar_one_or_none()
    if not admin or not verify_password(request.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not admin.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")
    token = create_platform_admin_token(str(admin.id), admin.role)
    return PlatformLoginResponse(access_token=token, token_type="bearer")