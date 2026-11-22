"""Managed IQC run leases, live business fences and accounted read projections."""

import asyncio
import hmac
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.core.tenant_transaction import TenantBinding
from app.models.agent_iqc_investigation import IqcInvestigationBinding, IqcInvestigationReceipt
from app.models.agent_model_deployment import AgentModelDeployment
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.models.iqc_inspection import IqcInspection
from app.services.agent_runtime import r5_executor, run_auth, task_updates
from app.services.agent_runtime.control_authority_fence import _no_wait, lock_employee_acl
from app.services.agent_runtime.iqc_investigation_pilot import (
    ALL_CAPABILITIES, ASSOCIATIONS, CONTEXT, HISTORY, ITEMS, MATERIAL, REINSPECTIONS,
    REQUIRED_CAPABILITIES, SUPPLIER, IQC_PROFILE, IqcRuntimeUnavailable,
    current_pilot, fresh_iqc_scope, granted_capabilities, require_iqc_deployment,
    resolve_iqc_activation, list_iqc_deployments,
)
from app.services.iqc_investigation_facts import read_inspection_facts, read_item_page

RUNTIME_PREFIX = "/api/agent/runtime/iqc-investigation"
MAX_READS = 32
MAX_BYTES = 480 * 1024  # Leave room for receipt IDs and the model input envelope.
MAX_MODEL_TURNS = 17
_launches = set()


def wire(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False, allow_nan=False))


def canonical(value):
    return json.dumps(wire(value), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def version_of(value):
    return sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class IqcRuntime:
    task: AgentTask
    run: AgentRun
    binding: dict
    binding_digest: str
    epoch: int
    pilot: object
    scope: object
    facts: object
    capabilities: frozenset[str]


def lifecycle(task, run, epoch, *, replay=False):
    if (task.status == "ready" and run.status == "active" and run.lease_epoch == epoch
            and run.lease_expires_at is not None and run.lease_expires_at > datetime.now(UTC)):
        return
    if (replay and task.status == "completed" and run.status == "completed"
            and run.lease_epoch == epoch + 1 and run.lease_expires_at is None and run.claim_key is None):
        return
    raise IqcRuntimeUnavailable()


async def _bound_business(db, task, binding, pilot):
    scope = await fresh_iqc_scope(db, task.executor_user_id)
    facts = await read_inspection_facts(db, scope, UUID(binding["inspection_id"]),
        allow_unassigned_line=binding["allow_unassigned_line"])
    if (facts.version != binding["facts_version"]
            or facts.payload["identity_generation"] != binding["identity_generation"]
            or facts.payload["factory_id"] != binding["factory_id"]
            or facts.payload["product_line_code"] != binding["product_line_code"]
            or not facts.eligible):
        raise IqcRuntimeUnavailable()
    for member in sorted(facts.members, key=lambda entry: str(entry.inspection_id)):
        if (await _no_wait(db, select(IqcInspection.inspection_id).where(
            IqcInspection.inspection_id == member.inspection_id,
            IqcInspection.identity_generation == member.identity_generation,
            IqcInspection.inspection_revision == member.inspection_revision,
        ), read=True)).scalar_one_or_none() is None:
            raise IqcRuntimeUnavailable()
    await lock_employee_acl(db, (task.executor_user_id,), read=True)
    scope = await fresh_iqc_scope(db, task.executor_user_id)
    facts = await read_inspection_facts(db, scope, UUID(binding["inspection_id"]),
        allow_unassigned_line=binding["allow_unassigned_line"])
    if facts.version != binding["facts_version"]:
        raise IqcRuntimeUnavailable()
    installation, row, current = await resolve_iqc_activation(db, scope, facts, UUID(binding["deployment_id"]))
    if (current != pilot or installation.installation_id != task.preferred_installation_id
            or str(installation.installation_id) != binding["installation_id"]
            or installation.credential_epoch != binding["installation_epoch"]
            or installation.plugin_version != binding["plugin_version"]
            or row.config_hmac != binding["deployment_hmac"]):
        raise IqcRuntimeUnavailable()
    available = await granted_capabilities(db, installation, pilot, facts)
    pinned = binding.get("capabilities")
    if (not isinstance(pinned, list) or any(not isinstance(item, str) for item in pinned)
            or not set(pinned) <= ALL_CAPABILITIES or not REQUIRED_CAPABILITIES <= set(pinned)):
        raise IqcRuntimeUnavailable()
    granted = frozenset(pinned) & available
    if not REQUIRED_CAPABILITIES <= granted:
        raise IqcRuntimeUnavailable()
    return scope, facts, granted


async def lock_runtime(db, token, tenant, *, terminal_replay=False, publishing=False):
    from app.services.agent_runtime.iqc_investigation_tasks import load_iqc_binding, try_lock_iqc_associations
    from app.services.agent_runtime.iqc_investigation_results import recheck_iqc_receipts

    pilot = current_pilot(db)
    claims = run_auth._claims(token)
    await run_auth._require_tenant(db, claims, tenant)
    while publishing and not await try_lock_iqc_associations(db):
        # A queued exclusive lock could block other writers that the current
        # writer needs before it can finish its transaction.
        await db.rollback()
        await asyncio.sleep(0.05)
        claims = run_auth._claims(token)
        await run_auth._require_tenant(db, claims, tenant)
    # The signed run chooses the task. Request JSON never chooses an identity.
    task_id = await db.scalar(select(AgentRun.task_id).where(
        AgentRun.run_id == claims["run_id"], AgentRun.installation_id == claims["installation_id"]))
    if task_id is None:
        raise IqcRuntimeUnavailable()
    installation = (await _no_wait(db, select(AgentPluginInstallation).where(
        AgentPluginInstallation.installation_id == claims["installation_id"]))).scalar_one_or_none()
    if installation is None:
        raise IqcRuntimeUnavailable()
    pilot.verify(tenant, installation)
    task, stored = await load_iqc_binding(db, task_id)
    await _no_wait(db, select(AgentTask.task_id).where(AgentTask.task_id == task_id))
    run = (await _no_wait(db, select(AgentRun).where(
        AgentRun.run_id == claims["run_id"], AgentRun.task_id == task_id,
        AgentRun.installation_id == installation.installation_id,
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    binding = stored.binding
    if (run is None or not run.plugin_version == installation.plugin_version == claims["plugin_version"]
            or claims["credential_epoch"] != installation.credential_epoch
            or not hmac.compare_digest(claims.get("trial_binding_sha256", ""), pilot.fingerprint())
            or claims.get("model_deployment_id") != binding["deployment_id"]
            or claims.get("model_config_hmac") != binding["deployment_hmac"]):
        raise IqcRuntimeUnavailable()
    epoch = claims["lease_epoch"]
    lifecycle(task, run, epoch, replay=terminal_replay)
    await _no_wait(db, select(AgentPluginGrant.grant_id).where(
        AgentPluginGrant.installation_id == installation.installation_id).order_by(AgentPluginGrant.grant_id), read=True)
    await _no_wait(db, select(AgentModelDeployment.deployment_id).where(
        AgentModelDeployment.deployment_id == UUID(binding["deployment_id"])), read=True)
    scope, facts, capabilities = await _bound_business(db, task, binding, pilot)
    receipts = await recheck_iqc_receipts(db, scope, task_id, run.run_id, epoch, facts)
    if any(receipt.payload["projection"] not in capabilities for receipt in receipts):
        raise IqcRuntimeUnavailable()
    run_auth._claims(token)
    pilot.verify(tenant, installation)
    lifecycle(task, run, epoch, replay=terminal_replay)
    return IqcRuntime(task, run, binding, stored.binding_digest, epoch, pilot, scope, facts, capabilities)


def bindings(current):
    return dict(task_id=str(current.task.task_id), run_id=str(current.run.run_id), lease_epoch=current.epoch)


def _cursor(current, projection, payload):
    import base64

    data = canonical({"task": str(current.task.task_id), "run": str(current.run.run_id),
        "epoch": current.epoch, "facts": current.facts.version, "projection": projection, "query": payload})
    encoded = base64.urlsafe_b64encode(data).decode("ascii")
    mac = hmac.new(settings.SECRET_KEY.encode(), b"iqc.cursor.v1:" + data, sha256).hexdigest()
    return encoded + "." + mac


def read_cursor(current, projection, value):
    import base64

    if not isinstance(value, str) or len(value) > 4096:
        raise IqcRuntimeUnavailable()
    try:
        raw, mac = value.split(".", 1)
        data = json.loads(base64.urlsafe_b64decode(raw).decode("utf-8"))
        query = data["query"]
        if not hmac.compare_digest(_cursor(current, projection, query), value):
            raise ValueError
        return query
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise IqcRuntimeUnavailable() from None


async def _release(db, current, projection, data, params, *, version=None, continuation=None):
    if projection not in current.capabilities:
        raise IqcRuntimeUnavailable()
    payload = wire(dict(projection=projection, version=version or version_of(data), data=data,
                        params=params, continuation=continuation))
    rows = (await db.scalars(select(IqcInvestigationReceipt).where(
        IqcInvestigationReceipt.task_id == current.task.task_id,
        IqcInvestigationReceipt.run_id == current.run.run_id,
        IqcInvestigationReceipt.lease_epoch == current.epoch,
        IqcInvestigationReceipt.kind == "source",
    ).limit(MAX_READS + 1))).all()
    if len(rows) > MAX_READS:
        raise IqcRuntimeUnavailable()
    previous = next((row for row in rows if row.payload == payload), None)
    receipt_id = previous.receipt_id if previous else uuid4()
    if previous is None:
        if len(rows) >= MAX_READS or sum(len(canonical(row.payload)) for row in rows) + len(canonical(payload)) > MAX_BYTES:
            return await _unavailable(db, current, projection, reason="budget_exhausted")
        db.add(IqcInvestigationReceipt(receipt_id=receipt_id, task_id=current.task.task_id,
            run_id=current.run.run_id, lease_epoch=current.epoch, kind="source", payload=payload))
    response = {**bindings(current), "available": True, "receipt_id": str(receipt_id),
                **payload}
    # Commit the possible release under the live authority and business locks.
    await db.commit()
    return response


async def _unavailable(db, current, projection, *, reason="unavailable"):
    db.add(AuditLog(table_name="agent_runs", record_id=current.run.run_id, action="IQC_QUERY_UNAVAILABLE",
        operated_by=current.task.executor_user_id, factory_id=current.task.factory_id,
        correlation_id=current.run.run_id,
        changed_fields={"projection": projection, "lease_epoch": current.epoch, "reason": reason}))
    response = {**bindings(current), "available": False, "projection": projection, "reason": reason}
    await db.commit()
    return response


async def context_projection(db, current, *, reinspection=False):
    projection = REINSPECTIONS if reinspection else CONTEXT
    params = dict(members=[asdict(member) for member in current.facts.members])
    return await _release(db, current, projection, current.facts.payload, params, version=current.facts.version)


async def item_projection(db, current, *, inspection_id=None, item_id=None, cursor=None):
    inspection_id = inspection_id or UUID(current.binding["inspection_id"])
    params = dict(inspection_id=str(inspection_id), item_id=None if item_id is None else str(item_id), offset=0, limit=40)
    if cursor is not None:
        continuation = read_cursor(current, ITEMS, cursor)
        if any(continuation.get(key) != params[key] for key in ("inspection_id", "item_id", "limit")):
            raise IqcRuntimeUnavailable()
        params = continuation
    if type(params.get("offset")) is not int or params["offset"] < 0:
        raise IqcRuntimeUnavailable()
    if item_id is not None:
        rows = (await db.scalars(select(IqcInvestigationReceipt).where(
            IqcInvestigationReceipt.run_id == current.run.run_id,
            IqcInvestigationReceipt.lease_epoch == current.epoch, IqcInvestigationReceipt.kind == "source",
        ).limit(MAX_READS + 1))).all()
        if not any(row.payload.get("projection") == ITEMS
                   and row.payload.get("params", {}).get("inspection_id") == str(inspection_id)
                   and row.payload.get("params", {}).get("item_id") is None
                   and any(item.get("item_id") == str(item_id) for item in row.payload.get("data", {}).get("rows", []))
                   for row in rows):
            raise IqcRuntimeUnavailable()
    page = await read_item_page(db, current.facts, inspection_id, item_id=item_id,
        offset=params["offset"], limit=params["limit"])
    continuation = None if page.next_offset is None else _cursor(current, ITEMS, {**params, "offset": page.next_offset})
    return await _release(db, current, ITEMS, asdict(page), params, continuation=continuation)


async def optional_projection(db, current, projection, *, cursor=None):
    if projection not in current.capabilities:
        return await _unavailable(db, current, projection)
    from app.services import iqc_investigation_optional as optional
    from app.services.iqc_investigation_associations import AssociationChanged, read_linked_investigations

    identifier = UUID(current.binding["inspection_id"])
    params = {}
    if projection == ASSOCIATIONS:
        lines = current.binding["association_product_lines"]
        if current.scope.pl_scope.mode != "ALL" and (
            lines is None or not set(lines) <= set(current.scope.pl_scope.codes or ())
        ):
            return await _unavailable(db, current, projection)
        params = dict(product_lines=lines)
    elif projection == HISTORY:
        task_date = date.fromisoformat(current.binding["task_date"])
        continuation = None if cursor is None else read_cursor(current, HISTORY, cursor)
        bound = None if continuation is None else optional.HistoryCursor(
            date.fromisoformat(continuation["inspection_date"]), UUID(continuation["inspection_id"]))
        params = dict(task_date=task_date.isoformat(), cursor=continuation, limit=20)
    try:
        async with db.begin_nested():
            if projection == ASSOCIATIONS:
                value = await read_linked_investigations(db, current.scope, current.facts.family_ids,
                    factory_id=UUID(current.binding["factory_id"]),
                    allowed_product_lines=frozenset(lines) if lines is not None else None)
            elif projection == HISTORY:
                value = await optional.read_inspection_history(db, current.scope, identifier,
                    task_date=task_date, cursor=bound, limit=20)
            elif projection == MATERIAL:
                value = await optional.read_current_material(db, current.scope, identifier)
            elif projection == SUPPLIER:
                value = await optional.read_current_supplier(db, current.scope, identifier)
            else:
                raise IqcRuntimeUnavailable()
    except (AssociationChanged, PermissionError, LookupError, HTTPException, SQLAlchemyError):
        return await _unavailable(db, current, projection)
    if value is None:
        return await _unavailable(db, current, projection)
    next_cursor = (None if projection != HISTORY or value.next_cursor is None
                   else _cursor(current, HISTORY, wire(asdict(value.next_cursor))))
    version = value.version if projection == ASSOCIATIONS else (
        value.source.version if projection in {MATERIAL, SUPPLIER} else None
    )
    return await _release(db, current, projection, asdict(value), params,
        version=version, continuation=next_cursor)


def make_launch_payload(*, task_id, run_id, deployment_id, epoch, expiry, token, tenant_slug, platform_origin):
    return dict(protocol="r7.iqc.launch.v1", profile=IQC_PROFILE, api_origin=platform_origin,
        token=token, tenant_slug=tenant_slug, task_id=str(task_id), run_id=str(run_id),
        deployment_id=str(deployment_id), lease_epoch=epoch, lease_expires_at=expiry.isoformat())


async def launch_iqc_task(db, scope, task_id, *, platform_origin, tenant_slug):
    from app.services.agent_runtime.iqc_investigation_tasks import load_iqc_binding

    pilot = current_pilot(db)
    if platform_origin not in (f"http://127.0.0.1:{pilot.platform_port}", f"http://127.0.0.1:{pilot.platform_port}/"):
        raise IqcRuntimeUnavailable()
    tenant = db.info.get("tenant_binding")
    if not isinstance(tenant, TenantBinding) or tenant.mode != "business":
        raise IqcRuntimeUnavailable()
    exclusion = (tenant.tenant_id, task_id)
    if exclusion in _launches:
        raise IqcRuntimeUnavailable()
    _launches.add(exclusion)
    run_id = None
    actor_id = scope.user.user_id
    try:
        task, stored = await load_iqc_binding(db, task_id)
        binding = stored.binding
        installation = (await _no_wait(db, select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == task.preferred_installation_id))).scalar_one_or_none()
        await _no_wait(db, select(AgentTask.task_id).where(AgentTask.task_id == task_id))
        if (task.initiator_id, task.executor_user_id) != (actor_id, actor_id) or task.status != "blocked_capability":
            raise IqcRuntimeUnavailable()
        pilot.verify(tenant, installation)
        await _bound_business(db, task, binding, pilot)
        slug = await db.scalar(text("SELECT slug FROM public.tenants WHERE id=:id AND status='active' AND generation=:generation"),
            {"id": tenant.tenant_id, "generation": tenant.generation})
        if not slug or slug != tenant_slug:
            raise IqcRuntimeUnavailable()
        pilot.verify(tenant, installation)
        expiry = min(datetime.now(UTC) + timedelta(minutes=settings.AGENT_RUN_TOKEN_TTL_MINUTES), pilot.expires_at)
        run_id = uuid4()
        run = AgentRun(run_id=run_id, task_id=task_id, installation_id=installation.installation_id,
            plugin_version=installation.plugin_version, status="active", lease_epoch=1,
            claim_key=uuid4().hex, lease_expires_at=expiry, accepted_message_seq=0)
        db.add(run)
        task.status = "ready"
        await db.flush()
        db.add(AuditLog(table_name="agent_runs", record_id=run_id, action="CLAIM_IQC_INVESTIGATION_RUN",
            operated_by=actor_id, factory_id=task.factory_id,
            changed_fields={"task_id": str(task_id), "lease_epoch": 1}))
        await task_updates.append_update(db, task_id=task_id, kind="claim", object_id=run_id)
        token = run_auth.issue_run_token(run, installation, str(tenant.tenant_id), tenant.generation,
            trial=SimpleNamespace(installation_id=installation.installation_id, expires_at=pilot.expires_at,
                                  binding_sha256=pilot.fingerprint()),
            model_binding=SimpleNamespace(deployment_id=UUID(binding["deployment_id"]), config_hmac=binding["deployment_hmac"]))
        request = canonical(make_launch_payload(task_id=task_id, run_id=run_id,
            deployment_id=binding["deployment_id"], epoch=1, expiry=expiry, token=token,
            tenant_slug=slug, platform_origin=platform_origin.rstrip("/")))
        await db.commit()
        await asyncio.to_thread(r5_executor.run_controlled, pilot.approval,
            platform_port=pilot.platform_port, request=request)
        if await db.scalar(select(AgentTask.status).where(AgentTask.task_id == task_id)) != "completed":
            raise IqcRuntimeUnavailable()
        return dict(task_id=task_id, status="executed")
    except (Exception, asyncio.CancelledError) as error:
        if run_id is not None:
            await r5_executor.fail_claimed_run(db, task_id=task_id, run_id=run_id, lease_epoch=1, actor_id=actor_id)
        if isinstance(error, asyncio.CancelledError):
            raise
        raise IqcRuntimeUnavailable() from None
    finally:
        _launches.discard(exclusion)


async def drain_installation(db, installation, actor_id):
    tasks = (await db.scalars(select(AgentTask).join(IqcInvestigationBinding,
        IqcInvestigationBinding.task_id == AgentTask.task_id).where(
        AgentTask.preferred_installation_id == installation.installation_id,
        AgentTask.status.in_(("blocked_capability", "ready", "paused")),
    ).order_by(AgentTask.task_id).with_for_update(of=AgentTask))).all()
    for task in tasks:
        run = await db.scalar(select(AgentRun).where(AgentRun.task_id == task.task_id,
            AgentRun.status.in_(("pending", "active", "paused"))).with_for_update())
        task.status = "cancelled"
        if run is not None:
            run.status = "stopped"
            run.lease_epoch += 1
            run.lease_expires_at = None
            run.claim_key = None
        db.add(AuditLog(table_name="agent_tasks", record_id=task.task_id, action="DRAIN_AGENT_IQC_INVESTIGATION",
            operated_by=actor_id, factory_id=task.factory_id, changed_fields={"status": "cancelled"}))
        await task_updates.append_update(db, task_id=task.task_id, kind="finish",
            object_id=run.run_id if run is not None else task.task_id)
