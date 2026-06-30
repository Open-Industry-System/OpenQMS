"""Agent pending-action endpoints — list + approve/reject/modify."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_db, get_request_scope
from app.core.factory_scope import check_factory_access
from app.models.agent import AgentAction
from app.models.role import RoleDefinition
from app.schemas.agent import ActionOut, DecisionIn
from app.services.agent import approval

router = APIRouter(prefix="/actions", tags=["agent-actions"])


async def _check_approver_auth(action: AgentAction, scope: RequestScope, db: AsyncSession) -> None:
    """Approver must be admin, OR hold APPROVE on the tool's module.

    Demo tools with required_permission module=None are admin-only.
    """
    from app.core.permissions import Module, PermissionLevel, get_user_permission
    from app.services.agent.registry import TOOL_REGISTRY

    role_key = (
        await db.execute(
            select(RoleDefinition.role_key).where(RoleDefinition.id == scope.user.role_id)
        )
    ).scalar_one_or_none()
    if role_key == "admin":
        return
    spec = TOOL_REGISTRY.get(action.tool_name)
    req = (spec.required_permission if spec else None) or {}
    module = req.get("module")
    if module is None:
        raise HTTPException(status_code=403, detail="需要管理员权限审批此动作")
    if (await get_user_permission(scope.user, Module(module), db)) < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要该模块的审批权限")


@router.get("", response_model=list[ActionOut])
async def list_actions(
    factory_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    check_factory_access(factory_id, scope)
    actions = await approval.list_pending(db, factory_id)
    return [ActionOut.model_validate(a) for a in actions]


@router.post("/{action_id}/approve", response_model=ActionOut)
async def approve_action(
    action_id: uuid.UUID,
    req: DecisionIn,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    action = await approval.get(db, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="动作不存在")
    check_factory_access(action.factory_id, scope)
    await _check_approver_auth(action, scope, db)
    try:
        action = await approval.approve(db, action_id, scope.user, req.reason or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ActionOut.model_validate(action)


@router.post("/{action_id}/reject", response_model=ActionOut)
async def reject_action(
    action_id: uuid.UUID,
    req: DecisionIn,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    action = await approval.get(db, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="动作不存在")
    check_factory_access(action.factory_id, scope)
    await _check_approver_auth(action, scope, db)
    try:
        action = await approval.reject(db, action_id, scope.user, req.reason or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ActionOut.model_validate(action)


@router.post("/{action_id}/modify", response_model=ActionOut)
async def modify_action(
    action_id: uuid.UUID,
    req: DecisionIn,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    if req.new_payload is None:
        raise HTTPException(status_code=400, detail="modify requires new_payload")
    action = await approval.get(db, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="动作不存在")
    check_factory_access(action.factory_id, scope)
    await _check_approver_auth(action, scope, db)
    try:
        action = await approval.modify(
            db, action_id, scope.user, req.new_payload, req.reason or ""
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ActionOut.model_validate(action)
