"""Admin permission management API."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module, PermissionLevel, require_permission
from app.database import get_db
from app.models.user import User
from app.schemas.permission import AssignProductLineRequest, PermissionUpdateRequest
from app.services import permission_service

router = APIRouter(prefix="/api/admin", tags=["admin-permissions"])


@router.get("/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    roles = await permission_service.list_roles(db)
    result = []
    for role in roles:
        perms = await permission_service.get_role_permissions(db, role.id)
        result.append({
            "id": str(role.id),
            "role_key": role.role_key,
            "name_zh": role.name_zh,
            "name_en": role.name_en,
            "is_system": role.is_system,
            "is_editable": role.is_editable,
            "permissions": perms,
        })
    return result


@router.put("/roles/{role_key}/permissions")
async def update_permissions(
    role_key: str,
    req: PermissionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    try:
        await permission_service.update_role_permissions(
            db, role_key, [p.model_dump() for p in req.permissions]
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(400, str(e))
    return {"message": "权限已更新"}


@router.get("/modules")
async def list_modules(
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    return [{"key": m.value, "name": m.name} for m in Module]


@router.get("/users/{user_id}/product-lines")
async def get_user_product_lines(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    upls = await permission_service.get_user_product_lines(db, user_id)
    return [{"product_line_code": upl.product_line_code} for upl in upls]


@router.post("/users/{user_id}/product-lines")
async def assign_product_line(
    user_id: uuid.UUID,
    req: AssignProductLineRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    try:
        await permission_service.assign_product_line(db, user_id, req.product_line_code)
        await db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"message": "产品线已分配"}


@router.delete("/users/{user_id}/product-lines/{product_line_code}")
async def remove_product_line(
    user_id: uuid.UUID,
    product_line_code: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    await permission_service.remove_product_line(db, user_id, product_line_code)
    await db.commit()
    return {"message": "产品线已移除"}
