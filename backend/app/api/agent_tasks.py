"""Default-off, target-bound task creation and instruction queue APIs."""
from uuid import UUID
import logging
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import RequestScope, get_request_scope
from app.database import get_db
from app.schemas.agent_control import (TaskControl, TaskControlOut, ActivityHTTPQuery, ActivityPage,
    InstallationDirectoryQuery, InstallationDirectory, AvailabilityQuery, RuntimeAvailability)
from app.schemas.agent_runtime import RuntimeResultOut, ReadonlyCheckpointView
from app.schemas.agent_d4_recovery import D4RecoveryCreate, D4RecoveryView
from app.schemas.agent_task import TaskCreate, TaskList, TaskMessageAccepted, TaskMessageCreate, TaskOut
from app.services.agent_runtime import message_queue, task_service, readonly_delivery, task_controls, checkpoint_service, task_reads, d4_recovery


class _RecoveryAccessLogFilter(logging.Filter):
    """Do not log unvalidated identifiers or query strings on recovery routes."""
    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path = unquote(urlsplit(args[2]).path)
            if path.startswith('/api/agent/tasks/') and '/d4-recovery-checkpoints' in path:
                record.args = (*args[:2], '/api/agent/tasks/{task_id}/d4-recovery-checkpoints', *args[3:])
        return True


_access_logger = logging.getLogger('uvicorn.access')
if not any(isinstance(item, _RecoveryAccessLogFilter) for item in _access_logger.filters):
    _access_logger.addFilter(_RecoveryAccessLogFilter())


def require_task_runtime() -> None:
    if not settings.AGENT_TASK_RUNTIME_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


def runtime_error(exc: Exception) -> HTTPException:
    """Translate business errors without echoing database/driver details."""
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail="Access denied")
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail="Not Found")
    return HTTPException(status_code=409, detail="Operation conflicts with current state")


router = APIRouter(prefix="/api/agent/tasks", tags=["agent-tasks"],
    dependencies=[Depends(require_task_runtime)])


def _recovery_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail='Invalid request') from None


@router.post('/{task_id}/d4-recovery-checkpoints', response_model=D4RecoveryView)
async def create_d4_recovery_checkpoint(task_id: str, request: Request,
        scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    identifier = _recovery_uuid(task_id)
    try:
        body = D4RecoveryCreate.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail='Invalid request') from None
    try:
        return await d4_recovery.create_checkpoint(db, scope, identifier, body.run_id, body.expected_epoch)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get('/{task_id}/d4-recovery-checkpoints/{checkpoint_id}', response_model=D4RecoveryView)
async def get_d4_recovery_checkpoint(task_id: str, checkpoint_id: str,
        scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    identifier, checkpoint = _recovery_uuid(task_id), _recovery_uuid(checkpoint_id)
    try:
        return await d4_recovery.get_checkpoint(db, scope, identifier, checkpoint)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, scope: RequestScope = Depends(get_request_scope),
                      db: AsyncSession = Depends(get_db)):
    try:
        return await task_service.create_task(db, scope, body.report_id, body.installation_id,
            body.request_key, body.initial_text, derived_source_scope=body.derived_source_scope)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("", response_model=TaskList)
async def list_tasks(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        return await task_service.list_for_initiator(db, scope, page, page_size)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/availability", response_model=RuntimeAvailability)
async def availability(query: AvailabilityQuery = Query(), scope: RequestScope = Depends(get_request_scope)):
    return {"enabled": True}


@router.get("/installations", response_model=InstallationDirectory)
async def installations(query: InstallationDirectoryQuery = Query(),
                         scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        return await task_reads.list_installations(db, scope, query.report_id)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/{task_id}/activity", response_model=ActivityPage)
async def activity(task_id: UUID, query: ActivityHTTPQuery = Query(),
                   scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        return await task_reads.get_activity(db, scope, task_id, **query.model_dump())
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID, scope: RequestScope = Depends(get_request_scope),
                   db: AsyncSession = Depends(get_db)):
    try:
        return await task_service.get_task_for_view(db, scope, task_id)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/{task_id}/messages", response_model=TaskMessageAccepted, status_code=202)
async def append_message(task_id: UUID, body: TaskMessageCreate,
                         scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        task = await task_service.get_task_for_view(db, scope, task_id)
        return await message_queue.append_task_message(db, task, scope, body.content, body.idempotency_key)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/{task_id}/results/{result_id}", response_model=RuntimeResultOut)
async def get_result(task_id: UUID, result_id: UUID,
                     scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        return await readonly_delivery.get_result_for_view(db, scope, task_id, result_id)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/{task_id}/control", response_model=TaskControlOut)
async def control_task(task_id: UUID, body: TaskControl,
                       scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        return await task_controls.control_task(db, scope, task_id, body)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/{task_id}/checkpoints/{checkpoint_id}", response_model=ReadonlyCheckpointView)
async def get_checkpoint(task_id: UUID, checkpoint_id: UUID,
                         scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    try:
        task = await task_service.get_task_for_view(db, scope, task_id)
        if await d4_recovery.is_text_task(db, task):
            raise LookupError('Checkpoint not found')
        return await checkpoint_service.get_checkpoint_for_view(db, scope, task_id, checkpoint_id)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None
