"""Platform-owned R5 recipient resolution; plugins cannot choose body or URL."""
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import ipaddress
import json
import socket
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.models.agent_model_deployment import AgentModelDeployment, AgentTaskModelBinding
from app.models.audit import AuditLog
from app.services.agent_runtime.r5_executor import ExecutorApproval

R5_PROFILE = 'model_d5_proposal_v1'
R5_PLUGIN_KEY = 'openqms.controlled-d5-model'
UNAVAILABLE = 'Model deployment unavailable'
CONFIG_FIELDS = ('deployment_id', 'name', 'version', 'tenant_generation', 'kind', 'provider',
    'model', 'base_url', 'allowed_addresses', 'credential_ref', 'executor_pins', 'created_by')


class DeploymentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    kind: str
    provider: Literal['openai']
    model: str = Field(min_length=1, max_length=100)
    base_url: str = Field(repr=False)
    allowed_addresses: list[str] = Field(min_length=1, max_length=10, repr=False)
    credential_ref: str = Field(min_length=1, max_length=100, repr=False)


class InferenceRequest(BaseModel):
    # T7 may add bounded tool IDs. Caller body/messages/source coordinates never
    # cross this API. The current source is derived from the task grant.
    model_config = ConfigDict(extra='forbid', frozen=True)
    operation: str = 'propose_d5'


def _namespace(db):
    from app.core.tenant_transaction import TenantBinding
    binding = db.info.get('tenant_binding')
    if not isinstance(binding, TenantBinding) or binding.mode != 'business':
        raise PermissionError(UNAVAILABLE)
    return binding


def _digest(db, row):
    from app.config import settings
    data = {key: str(getattr(row, key)) if key.endswith('_id') or key == 'created_by' else getattr(row, key) for key in CONFIG_FIELDS}
    data['tenant_id'] = str(_namespace(db).tenant_id)
    raw = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hmac.new(settings.SECRET_KEY.encode(), b'openqms.r5.model-deployment.v1\n'+raw, hashlib.sha256).hexdigest()


def _addresses(base_url):
    u = urlsplit(base_url)
    if (u.scheme not in {'http','https'} or not u.hostname or u.username or u.password
            or u.query or u.fragment or any(ord(c) <= 32 or ord(c) == 127 for c in base_url)):
        raise ValueError(UNAVAILABLE)
    addresses = sorted({str(ipaddress.ip_address(row[4][0])) for row in socket.getaddrinfo(
        u.hostname, u.port or (443 if u.scheme == 'https' else 80), type=socket.SOCK_STREAM)})
    if u.scheme != 'https' and not all(ipaddress.ip_address(ip).is_loopback for ip in addresses):
        raise ValueError(UNAVAILABLE)
    return addresses


def _approval(db):
    pilot = db.info.get('r5_controlled_pilot')
    from app.services.agent_runtime.r5_executor import ControlledPilot
    approval = pilot.approval if isinstance(pilot, ControlledPilot) else None
    if not isinstance(approval, ExecutorApproval):
        raise PermissionError(UNAVAILABLE)
    approval.verify()
    return approval


def _pins(db, approval):
    return dict(policy_sha256=db.info['r5_controlled_pilot'].fingerprint(), artifact_sha256=approval.artifact_sha256, interpreter_sha256=approval.interpreter_sha256,
        launcher_sha256=approval.launcher_sha256)


async def register_deployment(db, actor, request):
    from app.services.agent_runtime.plugin_registry import _require_current_admin
    await _require_current_admin(db, actor)
    request = DeploymentCreate.model_validate(request)
    if request.kind not in {'local','cloud'} or request.provider != 'openai':
        raise ValueError(UNAVAILABLE)
    addresses = _addresses(request.base_url)
    if addresses != sorted(set(request.allowed_addresses)):
        raise ValueError(UNAVAILABLE)
    approval = _approval(db)
    row = AgentModelDeployment(deployment_id=uuid4(), **request.model_dump(),
        tenant_generation=_namespace(db).generation, executor_pins=_pins(db, approval), created_by=actor.user_id,
        enabled=True)
    row.config_hmac = _digest(db, row)
    await _require_current_admin(db, actor)
    from sqlalchemy.exc import IntegrityError
    await db.flush()
    try:
        async with db.begin_nested():
            db.add(row)
            db.add(AuditLog(table_name='agent_model_deployments', record_id=row.deployment_id,
                action='APPROVE_MODEL_DEPLOYMENT', operated_by=actor.user_id,
                changed_fields={'deployment_id':str(row.deployment_id),'version':row.version}))
            await db.flush()
    except IntegrityError as exc:
        driver_error = exc.orig.__cause__
        if (getattr(exc.orig, 'sqlstate', None) == '23505'
                and getattr(driver_error, 'constraint_name', None) == 'uq_model_deployment_version'):
            raise ValueError('Model deployment version conflicts') from None
        raise
    return row


async def deployment(db, deployment_id, *, lock=False):
    from app.services.agent_runtime.task_service import _require_namespace
    await _require_namespace(db)
    q = select(AgentModelDeployment).where(AgentModelDeployment.deployment_id == deployment_id)
    if lock: q = q.with_for_update()
    with db.no_autoflush:
        row = await db.scalar(q.execution_options(populate_existing=True))
    if row is None or not row.enabled or row.tenant_generation != _namespace(db).generation:
        raise PermissionError(UNAVAILABLE)
    if not hmac.compare_digest(row.config_hmac, _digest(db, row)) or row.executor_pins != _pins(db, _approval(db)):
        raise PermissionError(UNAVAILABLE)
    try:
        addresses = _addresses(row.base_url)
    except (OSError,ValueError):
        raise PermissionError(UNAVAILABLE) from None
    if addresses != sorted(row.allowed_addresses):
        raise PermissionError(UNAVAILABLE)
    return row


async def revoke_deployment(db, actor, deployment_id):
    from app.services.agent_runtime.plugin_registry import _require_current_admin
    await _require_current_admin(db, actor)
    row = await db.scalar(select(AgentModelDeployment).where(
        AgentModelDeployment.deployment_id == deployment_id).with_for_update().execution_options(populate_existing=True))
    await _require_current_admin(db, actor)
    if row is None: raise LookupError(UNAVAILABLE)
    row.enabled = False
    db.add(AuditLog(table_name='agent_model_deployments', record_id=row.deployment_id,
        action='REVOKE_MODEL_DEPLOYMENT', operated_by=actor.user_id,
        changed_fields={'deployment_id':str(row.deployment_id),'version':row.version}))
    await db.flush()


async def selectable_deployments(db, scope):
    from app.services.agent_runtime.task_service import _current_access
    await _current_access(db, scope)
    ids = list(await db.scalars(select(AgentModelDeployment.deployment_id).where(AgentModelDeployment.enabled.is_(True))))
    out = []
    for key in ids:
        try: row = await deployment(db, key)
        except (PermissionError, ValueError, OSError): continue
        out.append(dict(deployment_id=row.deployment_id, name=row.name, version=row.version, kind=row.kind))
    return out


async def task_deployment(db, task, *, lock=False):
    with db.no_autoflush:
        binding = await db.scalar(select(AgentTaskModelBinding).where(
            AgentTaskModelBinding.task_id == task.task_id).execution_options(populate_existing=True))
    if binding is None: raise PermissionError(UNAVAILABLE)
    row = await deployment(db, binding.deployment_id, lock=lock)
    if binding.config_hmac != row.config_hmac: raise PermissionError(UNAVAILABLE)
    return row


async def is_r5_task(db, task):
    # Classification only. Missing binding on the dedicated plugin remains R5
    # (corrupt), never a fallback to the old fixed-message profile.
    from app.models.agent_plugin import AgentPluginInstallation
    with db.no_autoflush:
        pinned = await db.scalar(select(AgentTaskModelBinding.task_id).where(AgentTaskModelBinding.task_id == task.task_id))
        key = await db.scalar(select(AgentPluginInstallation.plugin_key).where(
            AgentPluginInstallation.installation_id == task.preferred_installation_id))
    return pinned is not None or key == R5_PLUGIN_KEY


class PinnedTransport(httpx.AsyncBaseTransport):
    """No DNS at connect time, redirects, proxies, retries or alternate host."""
    def __init__(self, row):
        self.origin = httpx.URL(row.base_url)
        self.endpoint = self.origin.path.rstrip('/') + ('/chat/completions' if row.provider == 'openai' else '/messages')
        self.address = sorted(row.allowed_addresses)[0]
        self.transport = httpx.AsyncHTTPTransport(verify=True, retries=0, trust_env=False)

    async def handle_async_request(self, request):
        if (request.method != 'POST' or request.url.scheme != self.origin.scheme
                or request.url.host != self.origin.host or request.url.port != self.origin.port
                or request.url.path != self.endpoint or request.url.query):
            raise PermissionError(UNAVAILABLE)
        request.headers['Host'] = self.origin.netloc.decode()
        request.extensions['sni_hostname'] = self.origin.host
        pinned = request.url.copy_with(host=self.address)
        request.url = pinned
        response = await self.transport.handle_async_request(request)
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise PermissionError(UNAVAILABLE)
        return response

    async def aclose(self):
        await self.transport.aclose()


async def infer(db, identity, request):
    from app.services.agent_runtime import runtime_access, d5_commands
    from app.services import capa_d5_proposals
    from app.services.agent import provider_adapter
    request = InferenceRequest.model_validate(request)
    if request.operation != 'propose_d5': raise ValueError(UNAVAILABLE)
    current = await runtime_access.lock_runtime_identity(db, identity)
    d5_commands.require_r5_admission(current)
    row = await task_deployment(db, current.task, lock=True)
    # The only context coordinate comes from CURRENT canonical task authority.
    authority = await runtime_access.authorize_task(db, current.task, current.installation)
    source = authority.current_source
    if source is None: raise PermissionError(UNAVAILABLE)
    snapshot = await capa_d5_proposals.build_d5_context(db, current, source_queries=[
        dict(projection_id=source.source_projection_id, fmea_id=str(source.fmea_id), node_id=source.cause_node_id)])
    resolver = db.info.get('r5_credential_resolver')
    if not callable(resolver): raise PermissionError(UNAVAILABLE)
    secret = resolver(row.credential_ref)
    if not isinstance(secret, str) or not secret: raise PermissionError(UNAVAILABLE)
    client = provider_adapter.build_deployment_client(row.provider, row.model, row.base_url, secret,
        transport=PinnedTransport(row))
    try:
        # The durable control attempt is separate from usable delivered basis.
        # A crash/unknown response can leave an attempt, never a source grant.
        await capa_d5_proposals.validate_d5_context_for_release(db, current, snapshot=snapshot)
        attempt_id = uuid4()
        deployment_id, version = row.deployment_id, row.version
        actor_id, factory_id, run_id, task_id = current.task.executor_user_id, current.task.factory_id, current.run.run_id, current.task.task_id
        db.add(AuditLog(log_id=attempt_id, table_name='agent_model_deployments', record_id=deployment_id,
            action='MODEL_EGRESS_ATTEMPT', operated_by=actor_id, factory_id=factory_id, correlation_id=run_id,
            changed_fields=dict(task_id=str(task_id), run_id=str(run_id), deployment_id=str(deployment_id),
                version=version, snapshot_hmac=snapshot.signature)))
        await db.commit()
        # Commit released locks: reacquire and recheck the same snapshot and
        # selected recipient immediately before actual transport sends anything.
        current, _, _ = await capa_d5_proposals.validate_d5_context_for_release(db, current, snapshot=snapshot)
        await task_deployment(db, current.task, lock=True)
        turn = await provider_adapter.chat_with_tools(client, [
            {'role':'system','content':'Propose a D5 corrective measure using only the supplied evidence.'},
            {'role':'user','content':json.dumps(snapshot.context, ensure_ascii=False)}], [])
        await capa_d5_proposals.record_delivered_basis(db, current, snapshot=snapshot)
        db.add(AuditLog(table_name='agent_model_deployments', record_id=deployment_id,
            action='MODEL_EGRESS_COMPLETED', operated_by=actor_id, factory_id=factory_id, correlation_id=attempt_id,
            changed_fields=dict(task_id=str(task_id), run_id=str(run_id), deployment_id=str(deployment_id), version=version)))
        await db.commit()
        return dict(content=turn.content, tool_calls=turn.tool_calls, deployment_id=deployment_id, version=version)
    except Exception:
        await db.rollback()
        raise PermissionError(UNAVAILABLE) from None
    finally:
        await client.client.close()


async def project_binding(db, task):
    """Historical receiver identity remains visible after revocation/versioning."""
    with db.no_autoflush:
        pin = await db.get(AgentTaskModelBinding, task.task_id, populate_existing=True)
        row = None if pin is None else await db.get(AgentModelDeployment, pin.deployment_id, populate_existing=True)
    if pin is not None and (row is None or pin.config_hmac != row.config_hmac or not hmac.compare_digest(row.config_hmac, _digest(db,row))):
        raise PermissionError(UNAVAILABLE)
    task.model_deployment = None if row is None else dict(deployment_id=row.deployment_id,name=row.name,version=row.version)
    return task
