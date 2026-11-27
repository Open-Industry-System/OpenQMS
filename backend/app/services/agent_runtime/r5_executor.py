"""Darwin-only controlled pilot. Unsupported hosts and stale pins fail closed.

Approval is platform-owned; never construct it from a plugin HTTP assertion.
The interpreter uses only stdlib; the artifact gets input on stdin, no platform
credential files/environment. Exact loopback platform port is the sole network
exception. This entry is deliberately separate from the R4b fixed launcher.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class ExecutorApproval:
    artifact: Path
    artifact_sha256: str
    interpreter: Path
    interpreter_sha256: str
    launcher_sha256: str

    @classmethod
    def approve(cls, artifact, interpreter):
        """Called only by platform admin enrollment, not by runtime payloads."""
        artifact, interpreter = Path(artifact).resolve(strict=True), Path(interpreter).resolve(strict=True)
        return cls(artifact, _sha(artifact), interpreter, _sha(interpreter), _sha(__file__))

    def verify(self):
        if (platform.system() != 'Darwin' or not Path('/usr/bin/sandbox-exec').is_file()
                or self.artifact.is_symlink() or self.interpreter.is_symlink()
                or _sha(self.artifact) != self.artifact_sha256
                or _sha(self.interpreter) != self.interpreter_sha256
                or _sha(__file__) != self.launcher_sha256):
            raise PermissionError('Controlled executor unavailable')


def _literal(path):
    return json.dumps(str(path))


def sandbox_policy(approval, platform_port):
    if type(platform_port) is not int or not 1 <= platform_port <= 65535:
        raise PermissionError('Controlled executor unavailable')
    # Only Python stdlib/runtime files and THIS artifact. No home/workspace,
    # inherited socket, credential file, subprocess execution or write access.
    roots = {Path(sys.base_prefix).resolve(), Path('/System'), Path('/usr/lib'), Path('/private/var/db/dyld')}
    reads = ' '.join('(subpath '+_literal(p)+')' for p in sorted(roots))
    return ('(version 1)(deny default)(allow process-exec (literal '+_literal(approval.interpreter)+'))'
        '(allow file-read-metadata)(allow file-read* (literal "/") '+reads+' (literal '+_literal(approval.artifact)+')'
        ' (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))'
        '(allow sysctl-read)'
        '(allow network-outbound (remote ip "localhost:'+str(platform_port)+'"))')


def run_controlled(approval, *, platform_port, request, timeout=120):
    approval.verify()
    if type(request) is not bytes or len(request) > 1024 * 1024 or not 0 < timeout <= 120:
        raise PermissionError('Controlled executor unavailable')
    policy = sandbox_policy(approval, platform_port)
    # Copy only verified bytes to an owned immutable-by-child location. Launch
    # and artifact pins are rechecked after copy; no caller cwd or environment.
    with tempfile.TemporaryDirectory(prefix='openqms-r5-executor-') as directory:
        path = Path(directory).resolve() / 'plugin.py'
        path.write_bytes(approval.artifact.read_bytes())
        path.chmod(0o400)
        if _sha(path) != approval.artifact_sha256:
            raise PermissionError('Controlled executor unavailable')
        approval.verify()
        copied = ExecutorApproval(path, approval.artifact_sha256, approval.interpreter,
            approval.interpreter_sha256, approval.launcher_sha256)
        return subprocess.run(['/usr/bin/sandbox-exec', '-p', sandbox_policy(copied, platform_port),
            str(approval.interpreter), '-I', '-S', str(path)], input=request,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=directory,
            env={'LANG': 'C', 'LC_ALL': 'C'}, close_fds=True, timeout=timeout, check=False)


@dataclass(frozen=True)
class ControlledPilot:
    approval: ExecutorApproval
    tenant_id: object
    tenant_generation: int
    installation_id: object
    credential_epoch: int
    plugin_version: str
    platform_port: int
    expires_at: object
    profile: str = 'model_d5_proposal_v1'

    def fingerprint(self):
        from dataclasses import asdict
        data=asdict(self)
        if self.profile == 'model_d5_proposal_v1':
            data.pop('profile')
        data['approval']={key:str(value) for key,value in data['approval'].items()}
        return hashlib.sha256(json.dumps(data,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()

    def verify(self, binding, installation):
        from datetime import UTC, datetime
        from app.core.tenant_transaction import TenantBinding
        if self.profile not in {'model_d5_proposal_v1', 'model_d5_proposal_r6_v1', 'model_d4_candidate_v1'}:
            raise PermissionError('Controlled executor unavailable')
        self.approval.verify()
        if (not isinstance(binding, TenantBinding) or binding.mode != 'business'
                or binding.tenant_id != self.tenant_id or binding.generation != self.tenant_generation
                or installation.installation_id != self.installation_id
                or installation.credential_epoch != self.credential_epoch
                or installation.plugin_version != self.plugin_version
                or self.expires_at <= datetime.now(UTC)):
            raise PermissionError('Controlled executor unavailable')
        return self


# This capability is local to the platform process; no HTTP/body/header value
# can impersonate it. Only managed_run below puts it in a private DB session.
_MANAGED_CLAIM = object()


def require_managed_claim(db):
    if db.info.get('_r5_managed_claim') is not _MANAGED_CLAIM:
        raise PermissionError('Controlled executor required')


async def _managed_run(db, scope, task_id, *, platform_origin):
    """Employee-triggered platform launch. The run token is never returned.

    T7 supplies the approved artifact loop. No remote claim credential can
    release restricted R5 context to an unconstrained plugin process.
    """
    import asyncio
    from urllib.parse import urlsplit
    from uuid import uuid4
    from app.services.agent_runtime import task_service, model_egress, run_dispatch
    task = await task_service.get_task_for_view(db, scope, task_id)
    row = await model_egress.task_deployment(db, task)
    actor_id = task.executor_user_id
    pilot = db.info.get('r5_controlled_pilot')
    if not isinstance(pilot, ControlledPilot):
        raise PermissionError('Controlled executor unavailable')
    origin = urlsplit(platform_origin)
    if origin.scheme != 'http' or origin.hostname != '127.0.0.1' or origin.port != pilot.platform_port or origin.path not in {'','/'}:
        raise PermissionError('Controlled executor unavailable')
    from sqlalchemy import text
    tenant_slug = await db.scalar(text('SELECT slug FROM public.tenants WHERE id=:id'), {'id':db.info['tenant_binding'].tenant_id})
    if not tenant_slug:
        raise PermissionError('Controlled executor unavailable')
    # claim_run locks and rechecks the actual pending task; dedicated target
    # filtering prevents accidentally dispatching another ready task.
    db.info['_r5_managed_claim'] = _MANAGED_CLAIM
    db.info['_r5_managed_task'] = task_id
    try:
        result = await run_dispatch.claim_run(db, db.info.get('tenant_binding'),
            task.preferred_installation_id, 'managed-claim-placeholder', uuid4().hex)
    finally:
        db.info.pop('_r5_managed_claim', None)
        db.info.pop('_r5_managed_task', None)
    from app.services.agent_runtime import runtime_access, model_workflow
    key = (db.info['tenant_binding'].tenant_id, result.run_id, result.lease_epoch)
    try:
        current = await runtime_access.verify_runtime_identity(db,result.token,db.info['tenant_binding'])
        model_workflow.begin_round(current)
        request = json.dumps(managed_launch_payload(row,result,platform_origin=platform_origin,tenant_slug=tenant_slug)).encode()
        await db.rollback()
        # Thread wait does not block runtime/message HTTP. subprocess.run kills
        # and waits for its own child on timeout before this cleanup executes.
        process = await asyncio.to_thread(run_controlled, pilot.approval,
            platform_port=pilot.platform_port, request=request)
        if process.returncode != 0:
            raise PermissionError('Controlled executor failed')
    except Exception:
        model_workflow._expire(key)
        await fail_claimed_run(db,task_id=task_id,run_id=result.run_id,
            lease_epoch=result.lease_epoch,actor_id=actor_id)
        raise PermissionError('Controlled executor failed') from None
    return dict(task_id=task_id, status='executed')


def load_controlled_pilot(path, *, enabled, runtime_enabled, tenant_mode):
    """Read a private platform file. Missing/malformed/unsupported stays closed.

    The file contains only deployment/executable pins, never model credentials.
    No plugin manifest, header or employee request can install this policy.
    """
    if not enabled or not runtime_enabled or tenant_mode != 'dev' or platform.system() != 'Darwin' or not path:
        return None
    try:
        from datetime import UTC, datetime
        from uuid import UUID
        from app.services.agent_runtime.local_d4_text_policy import _read_policy
        from app.services.agent_runtime.trial_policy import _unique_keys
        data=json.loads(_read_policy(path),object_pairs_hook=_unique_keys)
        expected={'schema_version','artifact','artifact_sha256','interpreter','interpreter_sha256','launcher_sha256',
            'tenant_id','tenant_generation','installation_id','credential_epoch','plugin_version','platform_port','expires_at'}
        if (type(data.get('schema_version')) is not int
                or not (data['schema_version'] == 1 and set(data) == expected
                    or data['schema_version'] == 2 and set(data) == expected | {'profile'}
                    and data['profile'] in {'model_d5_proposal_r6_v1', 'model_d4_candidate_v1'})):
            return None
        for name in ('tenant_generation','credential_epoch','platform_port'):
            if type(data[name]) is not int or data[name]<0: return None
        if not 1<=data['platform_port']<=65535 or not isinstance(data['plugin_version'],str) or not 1<=len(data['plugin_version'])<=40:
            return None
        expiry=datetime.fromisoformat(data['expires_at'])
        if expiry.tzinfo is None or expiry<=datetime.now(UTC):return None
        approval=ExecutorApproval(Path(data['artifact']).resolve(strict=True),data['artifact_sha256'],
            Path(data['interpreter']).resolve(strict=True),data['interpreter_sha256'],data['launcher_sha256'])
        approval.verify()
        return ControlledPilot(approval,UUID(data['tenant_id']),data['tenant_generation'],UUID(data['installation_id']),
            data['credential_epoch'],data['plugin_version'],data['platform_port'],expiry,
            profile=data.get('profile', 'model_d5_proposal_v1'))
    except (OSError,ValueError,TypeError,KeyError,PermissionError):
        return None


def resolve_credential(reference):
    """Platform-only environment namespace; never copy this env to a plugin."""
    import re
    if not isinstance(reference,str) or re.fullmatch(r'r5-env:R5_MODEL_CREDENTIAL_[A-Z0-9_]{1,64}',reference) is None:
        raise PermissionError('Model credential unavailable')
    value=os.environ.get(reference.removeprefix('r5-env:'))
    if not value: raise PermissionError('Model credential unavailable')
    return value


# Process-local launch exclusion complements DB claim fencing. A duplicate HTTP
# retry never starts a second worker holding the same run credential.
_launches = set()


async def managed_run(db, scope, task_id, *, platform_origin):
    key = (db.info.get('tenant_binding').tenant_id, task_id)
    if key in _launches:
        raise ValueError('Model launch already active')
    _launches.add(key)
    try:
        return await _managed_run(db, scope, task_id, platform_origin=platform_origin)
    finally:
        _launches.discard(key)


async def fail_claimed_run(db, *, task_id, run_id, lease_epoch, actor_id):
    """Trusted runner cleanup, never an HTTP/runtime capability.

    Stopping our already-finished child needs no business read grant. CAS on the
    claimed run/epoch preserves a concurrent pause/cancel/restart/new worker.
    """
    from sqlalchemy import select
    from app.models.agent_task import AgentTask, AgentRun
    from app.models.audit import AuditLog
    from app.services.agent_runtime import task_service, task_updates
    await db.rollback()
    await task_service._require_namespace(db)
    task = await db.scalar(select(AgentTask).where(AgentTask.task_id==task_id)
        .with_for_update().execution_options(populate_existing=True))
    run = await db.scalar(select(AgentRun).where(AgentRun.run_id==run_id,AgentRun.task_id==task_id)
        .with_for_update().execution_options(populate_existing=True))
    if (task is None or run is None or task.status!='ready' or run.status!='active'
            or run.lease_epoch!=lease_epoch or task.executor_user_id!=actor_id):
        await db.rollback()
        return
    task.status='failed'
    run.status='failed'
    run.lease_epoch+=1
    run.lease_expires_at=None
    run.claim_key=None
    db.add(AuditLog(table_name='agent_runs',record_id=run_id,action='FINISH_AGENT_RUN',
        operated_by=actor_id,factory_id=task.factory_id,changed_fields=dict(
            task_id=str(task_id),run_id=str(run_id),status='failed',lease_epoch=run.lease_epoch,
            failure_code='managed_child_failed')))
    await task_updates.append_update(db,task_id=task_id,kind='finish',object_id=run_id)
    await db.commit()


def managed_launch_payload(row,claim,*,platform_origin,tenant_slug):
    from app.services.agent_runtime import model_egress
    payload=dict(api_origin=platform_origin,token=claim.token,task_id=str(claim.task_id),
        deployment_id=str(row.deployment_id),tenant_slug=tenant_slug)
    if model_egress.deployment_profile(row)==model_egress.D4_PROFILE:
        payload.update(protocol='r6.d4.launch.v1',profile=model_egress.D4_PROFILE,run_id=str(claim.run_id),
            lease_epoch=claim.lease_epoch,lease_expires_at=claim.lease_expires_at.isoformat(),
            accepted_message_seq=claim.accepted_message_seq,has_resume_checkpoint=claim.has_resume_checkpoint)
    return payload
