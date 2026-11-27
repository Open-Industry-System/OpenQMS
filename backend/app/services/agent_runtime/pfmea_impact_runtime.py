"""Dedicated R7 managed lease and current business-scope authentication.

Legacy claim and runtime authorization never accept R7 tasks. Only the host
launch path issues a credential to the sandboxed, pinned worker.
"""

import asyncio
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, text

from app.config import settings
from app.core.tenant_transaction import TenantBinding
from app.models.agent_pfmea_impact import AgentPfmeaImpactBinding
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.schemas.pfmea_impact import CapaImpactMaterial, ImpactSourceRef
from app.services.agent_runtime import pfmea_impact_tasks, r5_executor, run_auth, task_updates
from app.services.agent_runtime.pfmea_impact_pilot import ImpactPilot
from app.services.capa_impact_material import read_material
from app.services.fmea_impact_projection import (
    FMEA_SNAPSHOT_PROJECTION,
    ApprovedImpactSnapshot,
    read_approved_snapshot,
    read_approved_target,
)


class ImpactRuntimeUnavailable(PermissionError):
    def __init__(self):
        super().__init__("PFMEA impact runtime unavailable")


@dataclass(frozen=True)
class ImpactRuntime:
    task: AgentTask
    run: AgentRun
    binding: pfmea_impact_tasks.ImpactTaskBinding
    binding_digest: str
    epoch: int
    pilot: ImpactPilot
    material: CapaImpactMaterial
    snapshot: ApprovedImpactSnapshot


def validate_origin(value: str, port: int) -> str:
    origin = f"http://127.0.0.1:{port}"
    if type(port) is not int or not 1 <= port <= 65535 or value not in (origin, origin + "/"):
        raise ImpactRuntimeUnavailable()
    return origin


def validate_run_lifecycle(task, run, epoch: int, *, terminal_replay: bool) -> bool:
    if (
        task.status == "ready" and run.status == "active" and run.lease_epoch == epoch
        and run.lease_expires_at is not None and run.lease_expires_at > datetime.now(UTC)
    ):
        return False
    if (
        terminal_replay and task.status == "completed" and run.status == "completed"
        and run.lease_epoch == epoch + 1 and run.lease_expires_at is None and run.claim_key is None
    ):
        return True
    raise ImpactRuntimeUnavailable()


def make_launch_payload(*, task_id, run_id, deployment_id, epoch, expiry, token, tenant_slug, platform_origin):
    return {
        "protocol": "r7.pfmea.launch.v1", "profile": pfmea_impact_tasks.R7_PROFILE,
        "api_origin": platform_origin, "token": token, "tenant_slug": tenant_slug,
        "task_id": str(task_id), "run_id": str(run_id), "deployment_id": str(deployment_id),
        "lease_epoch": epoch, "lease_expires_at": expiry.isoformat(), "accepted_message_seq": 0,
        "has_resume_checkpoint": False,
    }


def target_source(binding, node_id: str | None = None) -> ImpactSourceRef:
    target = binding.target
    return ImpactSourceRef(
        source_id=target.approved_version_id if node_id is None else uuid5(target.approved_version_id, f"node:{node_id}"),
        module="fmea", object_id=target.fmea_id, projection_id=FMEA_SNAPSHOT_PROJECTION,
        version=target.snapshot_hash, factory_id=binding.capa.factory_id,
        product_line_code=binding.capa.product_line_code, snapshot_id=target.approved_version_id,
        node_id=node_id,
    )


def _pilot(db) -> ImpactPilot:
    value = db.info.get("r7_impact_pilot")
    if (
        not settings.AGENT_TASK_RUNTIME_ENABLED or not settings.AGENT_R7_PFMEA_IMPACT_ENABLED
        or settings.TENANT_MODE != "dev" or not isinstance(value, ImpactPilot)
    ):
        raise ImpactRuntimeUnavailable()
    return value


def _request(task, binding):
    return pfmea_impact_tasks.ImpactTaskRequest(
        report_id=binding.capa.report_id, fmea_id=binding.target.fmea_id,
        approved_version_id=binding.target.approved_version_id,
        installation_id=binding.activation.installation_id, model_deployment_id=binding.activation.deployment_id,
        request_key=task.request_key, previous_result_id=binding.previous_result_id,
    )


async def _resolve_bound_business(db, task, binding):
    scope = SimpleNamespace(user=SimpleNamespace(user_id=task.executor_user_id))
    request = _request(task, binding)
    if await pfmea_impact_tasks._controlled_activation(db, scope, request) != binding.activation:
        raise ImpactRuntimeUnavailable()
    # Confirm the saved coordinates still describe the complete live authority
    # before locking any cross-module source rows, then resolve again under all locks.
    await read_material(db, scope, request.report_id, expected=binding.capa)
    await pfmea_impact_tasks._lock_activation(db, request, binding.activation)
    await pfmea_impact_tasks._lock_business_sources(db, request, scope, binding.capa)
    material = await read_material(db, scope, request.report_id, expected=binding.capa)
    target = await read_approved_target(
        db, scope, request.fmea_id, factory_id=binding.capa.factory_id,
        product_line_code=binding.capa.product_line_code, expected_version_id=request.approved_version_id, lock=True,
    )
    if (target.scope_generation, target.sha256_hash, target.major_no) != (
        binding.target.scope_generation, binding.target.snapshot_hash, binding.target.major_no,
    ):
        raise ImpactRuntimeUnavailable()
    snapshot = await read_approved_snapshot(
        db, scope, request.fmea_id, factory_id=binding.capa.factory_id,
        product_line_code=binding.capa.product_line_code, expected_version_id=request.approved_version_id,
    )
    if snapshot.sha256_hash != binding.target.snapshot_hash:
        raise ImpactRuntimeUnavailable()
    if await pfmea_impact_tasks._controlled_activation(db, scope, request) != binding.activation:
        raise ImpactRuntimeUnavailable()
    return material, snapshot


async def _lock_entities(db, installation_id, task_id, run_id=None):
    with db.no_autoflush:
        installation = await db.scalar(select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == installation_id,
        ).with_for_update().execution_options(populate_existing=True))
        task = await db.scalar(select(AgentTask).where(
            AgentTask.task_id == task_id, AgentTask.preferred_installation_id == installation_id,
        ).with_for_update().execution_options(populate_existing=True))
        if installation is None or task is None:
            raise ImpactRuntimeUnavailable()
        run = None
        if run_id is not None:
            run = await db.scalar(select(AgentRun).where(
                AgentRun.run_id == run_id, AgentRun.task_id == task_id,
                AgentRun.installation_id == installation_id,
            ).with_for_update().execution_options(populate_existing=True))
            if run is None:
                raise ImpactRuntimeUnavailable()
    return installation, task, run


async def lock_runtime(db, token: str, tenant: TenantBinding, *, terminal_replay=False) -> ImpactRuntime:
    """Resolve signed coordinates and hold live authority through a caller-owned release."""
    pilot = _pilot(db)
    claims = run_auth._claims(token)
    await run_auth._require_tenant(db, claims, tenant)
    task_id = await db.scalar(select(AgentRun.task_id).where(
        AgentRun.run_id == claims["run_id"], AgentRun.installation_id == claims["installation_id"],
    ))
    if task_id is None:
        raise ImpactRuntimeUnavailable()
    installation, task, run = await _lock_entities(db, claims["installation_id"], task_id, claims["run_id"])
    pilot.verify(tenant, installation)
    binding = await pfmea_impact_tasks.load_binding(db, task_id)
    epoch = claims["lease_epoch"]
    if (
        not run.plugin_version == installation.plugin_version == claims["plugin_version"]
        or claims["credential_epoch"] != installation.credential_epoch
        or not hmac.compare_digest(claims.get("trial_binding_sha256", ""), pilot.fingerprint())
        or claims.get("model_deployment_id") != str(binding.activation.deployment_id)
        or claims.get("model_config_hmac") != binding.activation.deployment_config_hmac
    ):
        raise ImpactRuntimeUnavailable()
    validate_run_lifecycle(task, run, epoch, terminal_replay=terminal_replay)
    material, snapshot = await _resolve_bound_business(db, task, binding)
    # An authorization await may have spent the remaining lease lifetime.
    run_auth._claims(token)
    pilot.verify(tenant, installation)
    validate_run_lifecycle(task, run, epoch, terminal_replay=terminal_replay)
    digest = await db.scalar(select(AgentPfmeaImpactBinding.binding_digest).where(
        AgentPfmeaImpactBinding.task_id == task_id,
    ))
    if digest is None:
        raise ImpactRuntimeUnavailable()
    return ImpactRuntime(task, run, binding, digest, epoch, pilot, material, snapshot)


async def launch_impact_task(db, scope, task_id: UUID, *, platform_origin: str, tenant_slug: str):
    """Launch only an owned, pinned assessment. Never return the worker credential."""
    pilot = _pilot(db)
    origin = validate_origin(platform_origin, pilot.platform_port)
    tenant = db.info.get("tenant_binding")
    if not isinstance(tenant, TenantBinding) or tenant.mode != "business":
        raise ImpactRuntimeUnavailable()
    binding = await pfmea_impact_tasks.load_binding(db, task_id)
    installation, task, _ = await _lock_entities(db, binding.activation.installation_id, task_id)
    actor_id = task.executor_user_id
    if (task.initiator_id, actor_id) != (scope.user.user_id, scope.user.user_id):
        raise ImpactRuntimeUnavailable()
    if task.status != "blocked_capability":
        raise ImpactRuntimeUnavailable()
    pilot.verify(tenant, installation)
    await _resolve_bound_business(db, task, binding)
    actual_slug = await db.scalar(text("SELECT slug FROM public.tenants WHERE id=:tenant_id"),
                                  {"tenant_id": tenant.tenant_id})
    if not actual_slug or actual_slug != tenant_slug:
        raise ImpactRuntimeUnavailable()
    pilot.verify(tenant, installation)
    expiry = min(datetime.now(UTC) + timedelta(minutes=settings.AGENT_RUN_TOKEN_TTL_MINUTES), pilot.expires_at)
    run_id = uuid4()
    run = AgentRun(run_id=run_id, task_id=task_id, installation_id=installation.installation_id,
        plugin_version=installation.plugin_version, status="active", lease_epoch=1, claim_key=uuid4().hex,
        lease_expires_at=expiry, accepted_message_seq=0)
    db.add(run)
    task.status = "ready"
    await db.flush()
    db.add(AuditLog(table_name="agent_runs", record_id=run_id, action="CLAIM_PFMEA_IMPACT_RUN",
        operated_by=actor_id, factory_id=task.factory_id, changed_fields={"task_id": str(task_id), "lease_epoch": 1}))
    await task_updates.append_update(db, task_id=task_id, kind="claim", object_id=run_id)
    token = run_auth.issue_run_token(
        run, installation, str(tenant.tenant_id), tenant.generation,
        trial=SimpleNamespace(installation_id=installation.installation_id, expires_at=pilot.expires_at,
                              binding_sha256=pilot.fingerprint()),
        model_binding=SimpleNamespace(deployment_id=binding.activation.deployment_id,
                                      config_hmac=binding.activation.deployment_config_hmac),
    )
    request = json.dumps(make_launch_payload(
        task_id=task_id, run_id=run_id, deployment_id=binding.activation.deployment_id,
        epoch=1, expiry=expiry, token=token, tenant_slug=actual_slug, platform_origin=origin,
    )).encode()
    await db.commit()
    try:
        await asyncio.to_thread(
            r5_executor.run_controlled, pilot.approval, platform_port=pilot.platform_port, request=request,
        )
        # The HTTP acknowledgment can be lost after the terminal commit. The
        # committed task is authoritative even when the worker exits nonzero.
        status = await db.scalar(select(AgentTask.status).where(AgentTask.task_id == task_id))
        if status != "completed":
            raise ImpactRuntimeUnavailable()
    except (Exception, asyncio.CancelledError) as exc:
        await r5_executor.fail_claimed_run(db, task_id=task_id, run_id=run_id, lease_epoch=1, actor_id=actor_id)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise ImpactRuntimeUnavailable() from None
    return {"task_id": task_id, "status": "executed"}


async def drain_installation(db, installation: AgentPluginInstallation, actor_id: UUID) -> None:
    """Revoke outstanding R7 work under the registry's installation lock."""
    active = ("pending", "active", "paused")
    tasks = (await db.scalars(
        select(AgentTask).join(AgentPfmeaImpactBinding, AgentPfmeaImpactBinding.task_id == AgentTask.task_id)
        .where(AgentTask.preferred_installation_id == installation.installation_id,
               AgentTask.status.in_(("blocked_capability", "ready", "paused")))
        .order_by(AgentTask.task_id).with_for_update(of=AgentTask).execution_options(populate_existing=True)
    )).all()
    for task in tasks:
        run = await db.scalar(select(AgentRun).where(
            AgentRun.task_id == task.task_id, AgentRun.installation_id == installation.installation_id,
            AgentRun.status.in_(active),
        ).with_for_update().execution_options(populate_existing=True))
        task.status = "cancelled"
        if run is not None:
            run.status = "stopped"
            run.lease_epoch += 1
            run.lease_expires_at = None
            run.claim_key = None
        db.add(AuditLog(
            table_name="agent_tasks", record_id=task.task_id, action="DRAIN_AGENT_PFMEA_IMPACT",
            operated_by=actor_id, factory_id=task.factory_id,
            changed_fields={"status": "cancelled", "installation_id": str(installation.installation_id)},
        ))
        await task_updates.append_update(db, task_id=task.task_id, kind="finish",
                                         object_id=run.run_id if run is not None else task.task_id)
