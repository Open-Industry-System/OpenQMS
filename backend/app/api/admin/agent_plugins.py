"""Tenant admin configuration only; no plugin execution or delivery endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_tasks import require_task_runtime, runtime_error
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.agent_plugin import (
    PluginEnabledUpdate, PluginGrantCreate, PluginGrantList, PluginGrantOut,
    PluginList, PluginOut, PluginRegister, PluginSecretOut, LocalTrialRevoke, LocalTrialRevokeOut,
)
from app.services.agent_runtime import plugin_registry

router = APIRouter(prefix="/api/admin/agent-plugins", tags=["admin-agent-plugins"],
    dependencies=[Depends(require_task_runtime)])


@router.post("", response_model=PluginSecretOut, status_code=201)
async def register(body: PluginRegister, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        plugin, secret = await plugin_registry.register_plugin(db, user, body.plugin_key,
            body.plugin_version, body.manifest.model_dump())
        await db.commit()
        return PluginSecretOut(plugin=PluginOut.model_validate(plugin), secret=secret)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("", response_model=PluginList)
async def list_plugins(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                       user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await plugin_registry.list_plugins(db, user, page, page_size)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/{installation_id}", response_model=PluginOut)
async def detail(installation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await plugin_registry.get_plugin(db, user, installation_id)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.patch("/{installation_id}", response_model=PluginOut)
async def update_enabled(installation_id: UUID, body: PluginEnabledUpdate,
                         user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        plugin = await plugin_registry.set_plugin_enabled(db, user, installation_id, body.enabled)
        await db.commit()
        return plugin
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/{installation_id}/rotate-secret", response_model=PluginSecretOut)
async def rotate(installation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        plugin, secret = await plugin_registry.rotate_plugin_secret(db, user, installation_id)
        await db.commit()
        return PluginSecretOut(plugin=PluginOut.model_validate(plugin), secret=secret)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/{installation_id}/revoke-local-trial", response_model=LocalTrialRevokeOut)
async def revoke_local_trial(installation_id: UUID, body: LocalTrialRevoke,
                             user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        result = await plugin_registry.revoke_local_trial(db, user, installation_id, body.expected_credential_epoch)
        await db.commit()
        return result
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/{installation_id}/grants", response_model=PluginGrantList)
async def list_grants(installation_id: UUID, page: int = Query(1, ge=1),
                      page_size: int = Query(20, ge=1, le=100),
                      user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await plugin_registry.list_plugin_grants(db, user, installation_id, page, page_size)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/{installation_id}/grants", response_model=PluginGrantOut, status_code=201)
async def create_grant(installation_id: UUID, body: PluginGrantCreate,
                       user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        grant = await plugin_registry.create_plugin_grant(db, user, installation_id, body)
        await db.commit()
        return grant
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.patch("/{installation_id}/grants/{grant_id}", response_model=PluginGrantOut)
async def update_grant_enabled(installation_id: UUID, grant_id: UUID, body: PluginEnabledUpdate,
                               user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        grant = await plugin_registry.set_plugin_grant_enabled(db, user, installation_id, grant_id, body.enabled)
        await db.commit()
        return grant
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None
