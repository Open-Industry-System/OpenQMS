"""Long-term plugin credential management. Mutations never commit the caller's transaction."""
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module, PermissionLevel
from app.core.security import hash_password, verify_password
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.audit import AuditLog
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from app.schemas.agent_plugin import PluginGrantCreate, PluginRegister
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import ApprovalFloor
from app.services.agent_runtime.task_service import _require_namespace


async def _require_current_admin(db: AsyncSession, actor: User) -> None:
    await _require_namespace(db)
    # Scalar columns avoid cached User/role relationships and stale identity-map state.
    with db.no_autoflush:
        admitted = await db.scalar(
            select(User.user_id).join(RoleDefinition, User.role_id == RoleDefinition.id)
            .join(RolePermission, RolePermission.role_id == RoleDefinition.id)
            .where(User.user_id == actor.user_id, User.is_active.is_(True),
                RoleDefinition.role_key == "admin", RoleDefinition.is_active.is_(True),
                RolePermission.module == Module.PERMISSION_MGMT.value,
                RolePermission.permission_level >= PermissionLevel.ADMIN)
        )
    if admitted is None:
        raise PermissionError("Plugin administration requires current admin permission")


def _audit(db: AsyncSession, actor: User, plugin: AgentPluginInstallation, action: str) -> None:
    fields = {"installation_id": str(plugin.installation_id),
        "plugin_version": plugin.plugin_version, "credential_epoch": plugin.credential_epoch}
    if action == "SET_PLUGIN_ENABLED":
        fields["enabled"] = plugin.enabled
    db.add(AuditLog(table_name="agent_plugin_installations", record_id=plugin.installation_id,
        action=action, operated_by=actor.user_id, changed_fields=fields))


async def register_plugin(db: AsyncSession, actor: User, key: str, version: str,
                          manifest: dict) -> tuple[AgentPluginInstallation, str]:
    await _require_current_admin(db, actor)
    registration = PluginRegister(plugin_key=key, plugin_version=version, manifest=manifest)
    # begin_nested() flushes pending caller state before creating its savepoint.
    # Keep unrelated write failures outside plugin conflict translation.
    await db.flush()
    secret = secrets.token_urlsafe(32)
    plugin = AgentPluginInstallation(installation_id=uuid4(), plugin_key=registration.plugin_key,
        plugin_version=registration.plugin_version, manifest=registration.manifest.model_dump(),
        secret_hash=hash_password(secret), enabled=False, credential_epoch=0,
        created_by=actor.user_id)
    # The database unique constraint arbitrates concurrent registrations. A savepoint
    # preserves the caller's transaction and keeps driver errors (including hashes) private.
    try:
        async with db.begin_nested():
            db.add(plugin)
            _audit(db, actor, plugin, "REGISTER_PLUGIN")
            await db.flush()
    except IntegrityError as exc:
        driver_error = exc.orig.__cause__
        if (getattr(exc.orig, "sqlstate", None) == "23505"
                and getattr(driver_error, "constraint_name", None)
                == "uq_agent_plugin_installation_key_version"):
            raise ValueError("Plugin key/version already registered") from None
        raise
    return plugin, secret


async def verify_plugin_secret(db: AsyncSession, installation_id: UUID,
                               secret: str) -> AgentPluginInstallation:
    with db.no_autoflush:
        plugin = await db.scalar(select(AgentPluginInstallation)
            .where(AgentPluginInstallation.installation_id == installation_id)
            .execution_options(populate_existing=True))
    valid = False
    if plugin is not None and isinstance(secret, str):
        try:
            if len(secret.encode("utf-8")) <= 72:
                valid = verify_password(secret, plugin.secret_hash)
        except (ValueError, TypeError, UnicodeError):
            pass
    if not valid:
        raise PermissionError("Invalid plugin credential")
    # Activation is checked by runtime admission, separately from credential possession.
    return plugin


async def rotate_plugin_secret(db: AsyncSession, actor: User,
                               installation_id: UUID) -> tuple[AgentPluginInstallation, str]:
    await _require_current_admin(db, actor)
    with db.no_autoflush:
        plugin = await db.scalar(select(AgentPluginInstallation)
            .where(AgentPluginInstallation.installation_id == installation_id)
            .with_for_update().execution_options(populate_existing=True))
    if plugin is None:
        raise LookupError("Plugin installation not found")
    await _require_current_admin(db, actor)
    secret = secrets.token_urlsafe(32)
    plugin.secret_hash = hash_password(secret)
    plugin.credential_epoch += 1
    _audit(db, actor, plugin, "ROTATE_PLUGIN_SECRET")
    await db.flush()
    return plugin, secret


async def revoke_local_trial(db: AsyncSession, actor: User, installation_id: UUID,
                             expected_epoch: int):
    from app.schemas.agent_plugin import LocalTrialRevoke, LocalTrialRevokeOut
    request = LocalTrialRevoke(expected_credential_epoch=expected_epoch)
    await _require_current_admin(db, actor)
    plugin = await _plugin(db, installation_id, lock=True)
    await _require_current_admin(db, actor)
    old_epoch = plugin.credential_epoch
    if old_epoch > request.expected_credential_epoch and not plugin.enabled:
        return LocalTrialRevokeOut(installation_id=plugin.installation_id,
            credential_epoch=old_epoch, enabled=False, outcome="already_fenced")
    if old_epoch != request.expected_credential_epoch:
        raise ValueError("Credential version conflicts")
    plugin.enabled = False
    plugin.secret_hash = hash_password(secrets.token_urlsafe(32))
    plugin.credential_epoch = old_epoch + 1
    db.add(AuditLog(table_name="agent_plugin_installations", record_id=plugin.installation_id,
        action="REVOKE_LOCAL_TRIAL", operated_by=actor.user_id, changed_fields={
            "installation_id": str(plugin.installation_id), "old_credential_epoch": old_epoch,
            "credential_epoch": plugin.credential_epoch, "enabled": False}))
    await db.flush()
    return LocalTrialRevokeOut(installation_id=plugin.installation_id,
        credential_epoch=plugin.credential_epoch, enabled=False, outcome="revoked")


async def _plugin(db: AsyncSession, installation_id: UUID, *, lock: bool = False) -> AgentPluginInstallation:
    query = select(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == installation_id)
    if lock:
        query = query.with_for_update()
    with db.no_autoflush:
        plugin = await db.scalar(query.execution_options(populate_existing=True))
    if plugin is None:
        raise LookupError("Plugin installation not found")
    return plugin


def _pagination(page: int, page_size: int) -> None:
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("Invalid pagination")


async def list_plugins(db: AsyncSession, actor: User, page: int, page_size: int) -> dict:
    await _require_current_admin(db, actor)
    _pagination(page, page_size)
    with db.no_autoflush:
        total = await db.scalar(select(func.count()).select_from(AgentPluginInstallation))
        items = list((await db.scalars(select(AgentPluginInstallation)
            .order_by(AgentPluginInstallation.created_at.desc(), AgentPluginInstallation.installation_id)
            .offset((page - 1) * page_size).limit(page_size)
            .execution_options(populate_existing=True))).all())
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_plugin(db: AsyncSession, actor: User, installation_id: UUID) -> AgentPluginInstallation:
    await _require_current_admin(db, actor)
    return await _plugin(db, installation_id)


async def set_plugin_enabled(db: AsyncSession, actor: User, installation_id: UUID,
                             enabled: bool) -> AgentPluginInstallation:
    await _require_current_admin(db, actor)
    plugin = await _plugin(db, installation_id, lock=True)
    await _require_current_admin(db, actor)  # Admission may have changed while waiting for the lock.
    if type(enabled) is not bool:
        raise ValueError("enabled must be boolean")
    plugin.enabled = enabled
    _audit(db, actor, plugin, "SET_PLUGIN_ENABLED")
    await db.flush()
    return plugin


async def _require_grant_enableable(db, plugin, grant) -> None:
    baseline = get_capability(grant.capability_id)
    if baseline is not None and baseline.kind == "context" and baseline.approval_floor == ApprovalFloor.DIRECT:
        return
    from app.models.capa import CAPAEightD
    from app.services.agent_runtime.trial_policy import EMPTY_POLICY, TrialPolicy, select_admission
    policy = db.info.get("agent_local_trial_policy", EMPTY_POLICY)
    if (grant.capability_id != "capa.d4.summary.masked.v1" or not isinstance(policy, TrialPolicy)
            or not grant.object_ids or not grant.product_line_codes or not grant.factory_ids
            or grant.expires_at is None or grant.expires_at.tzinfo is None
            or grant.expires_at <= datetime.now(UTC)):
        raise ValueError("Capability cannot be enabled")
    ids = {UUID(str(value)) for value in grant.object_ids}
    with db.no_autoflush:
        targets = list((await db.scalars(select(CAPAEightD).where(CAPAEightD.report_id.in_(ids))
            .execution_options(populate_existing=True))).all())
    if (len(targets) != len(ids) or {str(target.factory_id) for target in targets}
            != {str(value) for value in grant.factory_ids}
            or {target.product_line_code for target in targets} != set(grant.product_line_codes)):
        raise ValueError("Capability cannot be enabled")
    for target in targets:
        admitted = [select_admission(policy, binding=db.info.get("tenant_binding"), installation=plugin,
            executor_user_id=row.executor_user_id, report_id=target.report_id,
            factory_id=target.factory_id, product_line_code=target.product_line_code, now=datetime.now(UTC))
            for row in policy.entries]
        deadlines = [item.expires_at for item in admitted if item is not None]
        if not deadlines or grant.expires_at > min(deadlines):
            raise ValueError("Capability cannot be enabled")


def _grant_audit(db: AsyncSession, actor: User, grant: AgentPluginGrant, action: str) -> None:
    db.add(AuditLog(table_name="agent_plugin_grants", record_id=grant.grant_id,
        action=action, operated_by=actor.user_id, changed_fields={
            "installation_id": str(grant.installation_id), "grant_id": str(grant.grant_id),
            "capability_id": grant.capability_id, "factory_ids": grant.factory_ids,
            "product_line_codes": grant.product_line_codes, "object_ids": grant.object_ids,
            "enabled": grant.enabled}))


async def list_plugin_grants(db: AsyncSession, actor: User, installation_id: UUID,
                             page: int, page_size: int) -> dict:
    await _require_current_admin(db, actor)
    _pagination(page, page_size)
    await _plugin(db, installation_id)
    query = select(AgentPluginGrant).where(AgentPluginGrant.installation_id == installation_id)
    with db.no_autoflush:
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        items = list((await db.scalars(query.order_by(AgentPluginGrant.grant_id)
            .offset((page - 1) * page_size).limit(page_size)
            .execution_options(populate_existing=True))).all())
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def create_plugin_grant(db: AsyncSession, actor: User, installation_id: UUID,
                              request: PluginGrantCreate) -> AgentPluginGrant:
    await _require_current_admin(db, actor)
    plugin = await _plugin(db, installation_id, lock=True)
    await _require_current_admin(db, actor)
    if request.enabled:
        await _require_grant_enableable(db, plugin, request)
    grant = AgentPluginGrant(grant_id=uuid4(), installation_id=installation_id,
        capability_id=request.capability_id, factory_ids=[str(value) for value in request.factory_ids],
        product_line_codes=request.product_line_codes,
        object_ids=None if request.object_ids is None else [str(value) for value in request.object_ids],
        expires_at=request.expires_at, enabled=request.enabled, granted_by=actor.user_id)
    db.add(grant)
    _grant_audit(db, actor, grant, "CREATE_PLUGIN_GRANT")
    await db.flush()
    return grant


async def set_plugin_grant_enabled(db: AsyncSession, actor: User, installation_id: UUID,
                                   grant_id: UUID, enabled: bool) -> AgentPluginGrant:
    await _require_current_admin(db, actor)
    # Fixed order: installation before grant. Runtime admission will share it.
    plugin = await _plugin(db, installation_id, lock=True)
    with db.no_autoflush:
        grant = await db.scalar(select(AgentPluginGrant).where(
            AgentPluginGrant.installation_id == installation_id, AgentPluginGrant.grant_id == grant_id)
            .with_for_update().execution_options(populate_existing=True))
    if grant is None:
        raise LookupError("Plugin grant not found")
    await _require_current_admin(db, actor)
    if type(enabled) is not bool:
        raise ValueError("enabled must be boolean")
    if enabled:
        await _require_grant_enableable(db, plugin, grant)
    grant.enabled = enabled
    _grant_audit(db, actor, grant, "SET_PLUGIN_GRANT_ENABLED")
    await db.flush()
    return grant
