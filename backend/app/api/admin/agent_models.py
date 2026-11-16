"""Tenant-scoped approved R5 model versions; no credentials or URLs in outputs."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.agent_tasks import require_task_runtime, runtime_error
from app.core.deps import RequestScope, get_request_scope
from app.database import get_db
from app.services.agent_runtime import model_egress

router = APIRouter(prefix='/api/agent/models', tags=['agent-models'], dependencies=[Depends(require_task_runtime)])


@router.get('')
async def selectable(scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        return {'items':await model_egress.selectable_deployments(db, scope)}
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post('', status_code=201)
async def approve(body: model_egress.DeploymentCreate, scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        row = await model_egress.register_deployment(db, scope.user, body)
        result = dict(deployment_id=row.deployment_id, name=row.name, version=row.version, kind=row.kind)
        await db.commit()
        return result
    except (PermissionError, LookupError, ValueError, OSError) as exc:
        await db.rollback()
        raise runtime_error(exc) from None


@router.post('/{deployment_id}/revoke')
async def revoke(deployment_id: UUID, scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        await model_egress.revoke_deployment(db, scope.user, deployment_id)
        await db.commit()
        return {'deployment_id':deployment_id, 'enabled':False}
    except (PermissionError, LookupError, ValueError) as exc:
        await db.rollback()
        raise runtime_error(exc) from None
