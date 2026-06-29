"""Admin-only commit-whitelist endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.permissions import require_admin
from app.models.user import User
from app.schemas.agent import WhitelistIn, WhitelistOut
from app.services.agent import whitelist as whitelist_service

router = APIRouter(prefix="/whitelist", tags=["agent-whitelist"])


@router.post("", response_model=WhitelistOut, status_code=201)
async def create_whitelist(
    req: WhitelistIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    row = await whitelist_service.create(db, admin, **req.model_dump())
    return WhitelistOut.model_validate(row)


@router.get("", response_model=list[WhitelistOut])
async def list_whitelist(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rows = await whitelist_service.list_all(db)
    return [WhitelistOut.model_validate(r) for r in rows]


@router.get("/{whitelist_id}", response_model=WhitelistOut)
async def get_whitelist(
    whitelist_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = await whitelist_service.get(db, whitelist_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Whitelist rule not found")
    return WhitelistOut.model_validate(row)


@router.put("/{whitelist_id}", response_model=WhitelistOut)
async def update_whitelist(
    whitelist_id: uuid.UUID,
    req: WhitelistIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = await whitelist_service.get(db, whitelist_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Whitelist rule not found")
    row = await whitelist_service.update(db, row, **req.model_dump())
    return WhitelistOut.model_validate(row)


@router.delete("/{whitelist_id}", status_code=204)
async def delete_whitelist(
    whitelist_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = await whitelist_service.get(db, whitelist_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Whitelist rule not found")
    await whitelist_service.delete(db, row)
    return None
