from fastapi import APIRouter

from app.api.platform.auth import router as auth_router
from app.api.platform.tenants import router as tenants_router

router = APIRouter(prefix="/api/platform")
router.include_router(auth_router, tags=["platform-auth"])
router.include_router(tenants_router, tags=["platform-tenants"])