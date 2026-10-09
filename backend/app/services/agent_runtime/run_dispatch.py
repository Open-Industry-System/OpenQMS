"""Claim installation-pinned runs with current-key retries and bounded leases.

A new-key reclaim replaces the prior key; this is a current-lease idempotency
fence, not a permanent history of every installation request key.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.tenant_transaction import TenantBinding
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.schemas.agent_runtime import RunClaim, RunClaimOut
from app.services.agent_runtime import plugin_registry, run_auth, runtime_access, task_service, task_updates


async def claim_run(db: AsyncSession, binding: TenantBinding | None, installation_id: UUID,
                    secret: str, request_key: str) -> RunClaimOut:
    request = RunClaim(installation_id=installation_id, secret=secret, request_key=request_key)
    # Actual tenant namespace admission first; caller-provided info on a plain
    # session never establishes identity. Claims do not choose a business schema.
    await task_service._require_namespace(db)
    if binding != db.info.get("tenant_binding"):
        raise PermissionError(run_auth.INVALID_TOKEN)
    # All mutating runtime paths lock INSTALL→TASK→RUN. Install lock also
    # serializes selection/idempotency across several pending tasks.
    with db.no_autoflush:
        plugin = await db.scalar(select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == request.installation_id)
            .with_for_update().execution_options(populate_existing=True))
    plugin = await plugin_registry.verify_plugin_secret(db, request.installation_id, request.secret)
    if not plugin.enabled:
        raise PermissionError(run_auth.INVALID_TOKEN)
    await task_service._require_namespace(db)  # recheck after an installation-lock wait
    now = datetime.now(UTC)
    with db.no_autoflush:
        run = await db.scalar(select(AgentRun).where(
            AgentRun.installation_id == plugin.installation_id, AgentRun.claim_key == request.request_key)
            .execution_options(populate_existing=True))
        if run is None:
            run = await db.scalar(select(AgentRun).join(AgentTask, AgentTask.task_id == AgentRun.task_id)
                .where(AgentRun.installation_id == plugin.installation_id,
                    AgentTask.preferred_installation_id == plugin.installation_id, AgentTask.status == "ready",
                    or_(AgentRun.status == "pending", and_(AgentRun.status == "active", AgentRun.lease_expires_at <= now)))
                .order_by(AgentRun.created_at, AgentRun.run_id).limit(1)
                .execution_options(populate_existing=True))
        if run is None:
            raise LookupError("No claimable run")
        task = await db.scalar(select(AgentTask).where(AgentTask.task_id == run.task_id)
            .with_for_update().execution_options(populate_existing=True))
        run = await db.scalar(select(AgentRun).where(AgentRun.run_id == run.run_id)
            .with_for_update().execution_options(populate_existing=True))
    now = datetime.now(UTC)
    if (task is None or run is None or run.task_id != task.task_id or task.status != "ready"
            or task.preferred_installation_id != plugin.installation_id
            or run.installation_id != plugin.installation_id or run.plugin_version != plugin.plugin_version):
        raise PermissionError(run_auth.INVALID_TOKEN)
    retry = run.status == "active" and run.lease_expires_at is not None and run.lease_expires_at > now
    if retry and run.claim_key != request.request_key:
        raise LookupError("No claimable run")
    if not retry and (run.status not in {"pending", "active"}
            or (run.status == "active" and run.lease_expires_at is None)):
        raise LookupError("No claimable run")
    authority = await runtime_access.authorize_task(db, task, plugin)
    if not retry:
        run.claim_key = request.request_key
        run.lease_epoch += 1
        run.status = "active"
        run.lease_expires_at = datetime.now(UTC) + timedelta(minutes=settings.AGENT_RUN_TOKEN_TTL_MINUTES)
        if authority.trial is not None:
            run.lease_expires_at = min(run.lease_expires_at, authority.trial.expires_at)
        db.add(AuditLog(table_name="agent_runs", record_id=run.run_id, action="CLAIM_AGENT_RUN",
            operated_by=task.executor_user_id, factory_id=task.factory_id,
            changed_fields={"task_id": str(task.task_id), "installation_id": str(plugin.installation_id),
                "lease_epoch": run.lease_epoch}))
        await db.flush()
        await task_updates.append_update(db, task_id=task.task_id, kind="claim", object_id=run.run_id)
    if authority.trial is not None:
        final = await runtime_access.authorize_task(db, task, plugin)
        if final.trial != authority.trial or authority.trial.expires_at <= datetime.now(UTC):
            raise PermissionError(run_auth.INVALID_TOKEN)
        run.lease_expires_at = min(run.lease_expires_at, authority.trial.expires_at)
    tenant_id = "single" if binding is None else str(binding.tenant_id)
    generation = 0 if binding is None else binding.generation
    token = run_auth.issue_run_token(run, plugin, tenant_id, generation, trial=authority.trial)
    result = RunClaimOut(run_id=run.run_id, task_id=task.task_id, token=token,
        lease_epoch=run.lease_epoch, lease_expires_at=run.lease_expires_at,
        accepted_message_seq=run.accepted_message_seq, has_resume_checkpoint=run.resume_checkpoint_id is not None)
    await db.commit()
    return result
