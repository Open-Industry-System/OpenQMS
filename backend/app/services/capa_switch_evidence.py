"""Purpose-separated switch documents and independent deployment authority.

Documents contain expectations. Authority is loaded only from the deployment's
configured signed registry, never from a document path or CLI isolation flag.
The registry signer and formal authorization signer are independently supplied
by the operator environment; this module ships neither key nor approval.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class TenantTarget(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tenant_id: UUID | None
    schema_name: str = Field(alias="schema",min_length=1, max_length=64, pattern=r'^[a-z0-9_]+$')
    generation: int = Field(ge=0)


class Target(BaseModel):
    model_config = ConfigDict(extra='forbid')
    environment: str = Field(pattern=r'^(isolated_exercise|formal)$')
    deployment_role: str = Field(pattern=r'^(synthetic_exercise|production)$')
    environment_id: str = Field(min_length=1, max_length=128)
    owner: str = Field(min_length=16, max_length=128)
    database: str = Field(min_length=1, max_length=128)
    system_identifier: str = Field(pattern=r'^\d+$', max_length=32)
    tenant: TenantTarget
    public_head: str = Field(min_length=1, max_length=128)
    tenant_head: str = Field(min_length=1, max_length=128)
    candidate_build: str = Field(pattern=r'^[0-9a-f]{40,64}$')
    compatible_build: str = Field(pattern=r'^[0-9a-f]{40,64}$')
    source_manifest: str = Field(pattern=r'^[0-9a-f]{64}$')
    config_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    database_role: str = Field(min_length=1, max_length=128)


class ReleaseBinding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    exercise_input_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    data_ref: str = Field(min_length=1,max_length=200)
    run_refs: list[str] = Field(min_length=2,max_length=64)
    plugin_version: str = Field(min_length=1,max_length=64)
    candidate_source_sha: str = Field(pattern=r'^[0-9a-f]{40}$')
    compatible_source_sha: str = Field(pattern=r'^[0-9a-f]{40}$')
    full_sources_receipt: str = Field(pattern=r'^[0-9a-f]{64}$')
    correction_history_receipt: str = Field(pattern=r'^[0-9a-f]{64}$')
    drain_receipt: str = Field(pattern=r'^[0-9a-f]{64}$')
    scenario_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    approved_by: UUID


class ResumeBinding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_ref: UUID
    previous_document_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    draining_epoch: int = Field(ge=1)


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1, le=1)
    kind: str = Field(pattern=r'^(exercise_input|release_manifest)$')
    purpose: str = Field(pattern=r'^(r6-rehearsal.v1|r6-release.v1)$')
    exercise_id: UUID | None = None
    expires_at: datetime
    target: Target
    initial_epoch: int = Field(ge=0)
    c9_receipt: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    c10_receipt: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    resume_of: ResumeBinding | None = None
    release_binding: ReleaseBinding | None = None
    authorization: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


def validate_document(document, actual):
    if document.get('kind') == 'exercise_input' and actual.get('environment') != 'isolated_exercise':
        raise ValueError('exercise input is forbidden for formal or unknown environment')
    if len(json.dumps(document).encode()) > 65536:
        raise ValueError('switch document exceeds limit')
    try:
        parsed = Document.model_validate(document).model_dump(mode='json',by_alias=True)
    except Exception:
        raise ValueError('invalid switch document') from None
    expiry=datetime.fromisoformat(parsed['expires_at'].replace('Z','+00:00'))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError('switch document expired or missing timezone')
    expected_purpose='r6-rehearsal.v1' if parsed['kind']=='exercise_input' else 'r6-release.v1'
    if parsed['purpose']!=expected_purpose or (parsed['kind']=='exercise_input') != (parsed['exercise_id'] is not None):
        raise ValueError('switch document purpose or exercise identity mismatch')
    if parsed['target'] != actual:
        raise ValueError('switch target differs from independent authority')
    if parsed['kind'] == 'exercise_input':
        if parsed['c9_receipt'] or parsed['c10_receipt'] or parsed['authorization'] or parsed['release_binding']:
            raise ValueError('exercise input cannot claim release authorization')
    else:
        if actual['environment']!='formal' or parsed['release_binding'] is None:
            raise ValueError('release manifest requires formal target and complete evidence binding')
        if str(parsed['release_binding']['approved_by'])!=os.environ.get('R6_SWITCH_RELEASE_APPROVER'):
            raise ValueError('release manifest approver is not independently configured')
        key = os.environ.get('R6_SWITCH_RELEASE_AUTHORIZATION_KEY')
        signature = parsed.pop('authorization')
        if not key or not signature or not parsed['c9_receipt'] or not parsed['c10_receipt']:
            raise ValueError('release manifest requires independent authorization and C9/C10')
        if not hmac.compare_digest(signature, hmac.new(key.encode(), digest(parsed).encode(), hashlib.sha256).hexdigest()):
            raise ValueError('release authorization does not bind manifest')
        parsed['authorization'] = signature
    return {'version': 1, 'purpose': parsed['purpose'], 'document_kind': parsed['kind'], 'exercise_id':parsed['exercise_id'], 'expires_at':parsed['expires_at'], 'target': parsed['target'],
        'initial_epoch': parsed['initial_epoch'], 'document_digest': digest(parsed),
        'resume_of':parsed['resume_of'],'c9_receipt':parsed['c9_receipt'],'c10_receipt':parsed['c10_receipt'],'release_binding':parsed['release_binding']}


def _read_registry():
    path, key = os.environ.get('R6_SWITCH_AUTHORITY_FILE'), os.environ.get('R6_SWITCH_AUTHORITY_KEY')
    if not path or not key:
        raise ValueError('independent switch authority is not configured')
    raw = Path(path).read_bytes()
    if len(raw) > 262144:
        raise ValueError('authority registry exceeds limit')
    envelope = json.loads(raw)
    if set(envelope) != {'record', 'signature'} or not hmac.compare_digest(envelope['signature'],
            hmac.new(key.encode(), digest(envelope['record']).encode(), hashlib.sha256).hexdigest()):
        raise ValueError('untrusted switch authority registry')
    return envelope['record']


def runtime_manifest(root):
    """Complete fixed runtime roots, including schema/SDK and frontend source.

    The caller cannot choose a convenient subset or substitute a single file.
    """
    roots=('backend/app','backend/scripts','backend/alembic/versions','backend/alembic_tenant','frontend/src','sdk')
    result={}
    for relative_root in roots:
        directory=root/relative_root
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.suffix in {'.py','.ts','.tsx','.json','.toml'} and not {'__pycache__','node_modules','.venv'} & set(path.parts):
                result[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _artifact(reference):
    if not isinstance(reference,dict) or set(reference)!={'path','sha256'}:
        raise ValueError('content-addressed artifact required')
    raw=Path(reference['path']).read_bytes()
    if len(raw)>2097152 or hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('registered artifact changed')
    return json.loads(raw)


def _builds(record,target,root):
    builds=record.get('build_artifacts')
    if not isinstance(builds,dict) or set(builds)!={target['candidate_build'],target['compatible_build']}:
        raise ValueError('candidate and compatible build artifacts required')
    actual_manifest=runtime_manifest(root)
    if target['source_manifest']!=digest(actual_manifest) or any(not re.fullmatch('[0-9a-f]{64}',v) for v in actual_manifest.values()):
        raise ValueError('complete frozen runtime source manifest mismatch')
    for build_id,reference in builds.items():
        artifact=_artifact(reference)
        if set(artifact)!={'source_manifest','source_root','executable','executable_digest','config_digest','roles','schema_heads','source_revision'} or digest(artifact)!=build_id:
            raise ValueError('build identity does not match frozen executable artifact')
        if not isinstance(artifact['source_revision'],str) or not re.fullmatch('[0-9a-f]{40}',artifact['source_revision']):
            raise ValueError('exact build source revision required')
        source_root=Path(artifact['source_root']).resolve()
        if artifact['source_manifest']!=runtime_manifest(source_root):
            raise ValueError('registered build source changed')
        if artifact['executable_digest']!=hashlib.sha256(Path(artifact['executable']).read_bytes()).hexdigest():
            raise ValueError('registered executable changed')
        if artifact['config_digest']!=target['config_digest'] or set(artifact['roles'])!={'server','worker'}:
            raise ValueError('registered build deployment configuration mismatch')
        if artifact['schema_heads']!=[target['public_head'],target['tenant_head']]:
            raise ValueError('registered build schema mismatch')
    candidate=_artifact(builds[target['candidate_build']])
    if Path(candidate['source_root']).resolve()!=root or candidate['source_manifest']!=actual_manifest:
        raise ValueError('operator does not execute the registered candidate artifact')
    if Path(candidate['executable']).resolve()!=Path(sys.executable).resolve():
        raise ValueError('operator executable differs from registered build')
    return builds


async def authority(db):
    """Validate independently registered ownership against live DB/build facts."""
    record = _read_registry()
    target = Target.model_validate(record['target']).model_dump(mode='json',by_alias=True)
    binding = db.info.get('tenant_binding')
    namespace = {'tenant_id': None if binding is None else str(binding.tenant_id),
        'schema': 'public' if binding is None else binding.schema_name,
        'generation': 0 if binding is None else binding.generation}
    if target['tenant'] != namespace:
        raise ValueError('authority tenant generation mismatch')
    actual = (await db.execute(text("SELECT current_database(),current_user,(pg_control_system()).system_identifier::text"))).one()
    if tuple(actual) != (target['database'], target['database_role'], target['system_identifier']):
        raise ValueError('authority database or role mismatch')
    public_head = await db.scalar(text('SELECT version_num FROM public.alembic_version'))
    tenant_head = await db.scalar(text('SELECT version_num FROM tenant_schema_version' if binding else 'SELECT version_num FROM alembic_version'))
    if (public_head, tenant_head) != (target['public_head'], target['tenant_head']):
        raise ValueError('authority schema heads mismatch')
    root = Path(__file__).resolve().parents[3]
    _builds(record,target,root)
    if target['environment'] == 'isolated_exercise':
        # Registered fixture ownership comes from independently configured
        # resource registry, matched against the actual running Docker owner.
        resource = json.loads(Path(record['resource_record']).read_text())
        if resource.get('owner_nonce') != target['owner'] or resource.get('test_database') != target['database']:
            raise ValueError('exercise owner resource mismatch')
        inspected = json.loads(subprocess.check_output(['docker', 'inspect', resource['container_id']], text=True))[0]
        labels = inspected.get('Config', {}).get('Labels') or {}
        if not inspected['State']['Running'] or target['owner'] not in labels.values():
            raise ValueError('exercise resource is not owner-bound and running')
        ports = inspected['NetworkSettings']['Ports'].get('5432/tcp') or []
        if not any(int(port['HostPort']) == resource['port'] and port['HostIp'] in {'127.0.0.1','::1'} for port in ports):
            raise ValueError('exercise database port is not isolated')
    expected_role='synthetic_exercise' if target['environment']=='isolated_exercise' else 'production'
    if target['deployment_role']!=expected_role:
        raise ValueError('deployment role does not match switch purpose')
    # Config identity is an actual file digest, not a request boolean.
    config = Path(record['config_file'])
    if hashlib.sha256(config.read_bytes()).hexdigest() != target['config_digest']:
        raise ValueError('authority configuration changed')
    config_facts=json.loads(config.read_bytes())
    if (config_facts.get('deployment_role')!=expected_role or config_facts.get('owner')!=target['owner']
        or config_facts.get('environment_id')!=target['environment_id'] or config_facts.get('tenant')!=namespace):
        raise ValueError('actual application deployment role or ownership mismatch')
    if target['environment']=='isolated_exercise':
        lease=_artifact(record.get('exclusive_lease'))
        if lease!={'owner':target['owner'],'environment_id':target['environment_id'],'tenant':namespace,'deployment_role':expected_role}:
            raise ValueError('exclusive exercise deployment lease mismatch')
    return target


async def verify_inventory(db, evidence):
    actual = await authority(db)
    if evidence['target'] != actual:
        raise ValueError('authority changed during drain')
    record = _read_registry()
    if evidence['document_kind']=='release_manifest':
        release=evidence['release_binding']
        expected={'c9':evidence['c9_receipt'],'c10':evidence['c10_receipt'],
            'exercise_input':release['exercise_input_hash'],'full_sources':release['full_sources_receipt'],
            'correction_history':release['correction_history_receipt'],'drain':release['drain_receipt']}
        registered=record.get('release_receipts')
        if not isinstance(registered,dict) or set(registered)!=set(expected):
            raise ValueError('independent release receipt registry required')
        for name,sha in expected.items():
            if registered[name]['sha256']!=sha:
                raise ValueError('release receipt identity mismatch')
            _artifact(registered[name])
        for build_key,revision_key in [('candidate_build','candidate_source_sha'),('compatible_build','compatible_source_sha')]:
            if _artifact(record['build_artifacts'][actual[build_key]])['source_revision']!=release[revision_key]:
                raise ValueError('release source revision differs from executable artifact')
    inventory = record.get('instances')
    if not isinstance(inventory, list) or not inventory or len(inventory) > 128:
        raise ValueError('complete registered runtime inventory required')
    for instance in inventory:
        launch=_artifact(instance)
        signature=launch.pop('signature',None)
        key=os.environ.get('R6_SWITCH_LAUNCH_ATTESTATION_KEY')
        if not key or not isinstance(signature,str) or not hmac.compare_digest(signature,hmac.new(key.encode(),digest(launch).encode(),hashlib.sha256).hexdigest()):
            raise ValueError('independent launch attestation required')
        if set(launch)!={'pid','start','command_digest','build','role','deployment_role','owner','executable','executable_digest','config_digest'}:
            raise ValueError('invalid registered launch receipt')
        if (launch['role'] not in {'server','worker'} or launch['build'] not in {actual['candidate_build'],actual['compatible_build']}
            or launch['deployment_role']!=actual['deployment_role'] or launch['owner']!=actual['owner'] or launch['config_digest']!=actual['config_digest']):
            raise ValueError('old or foreign runtime remains reachable')
        build=_artifact(record['build_artifacts'][launch['build']])
        if launch['executable']!=build['executable'] or launch['executable_digest']!=build['executable_digest']:
            raise ValueError('launch executable does not match registered build')
        observed=subprocess.check_output(['ps','-p',str(launch['pid']),'-o','lstart=','-o','command='],text=True).strip()
        if not observed.startswith(launch['start']) or hashlib.sha256(observed.encode()).hexdigest()!=launch['command_digest']:
            raise ValueError('runtime inventory process identity changed')
        if hashlib.sha256(Path(launch['executable']).read_bytes()).hexdigest()!=launch['executable_digest']:
            raise ValueError('live launch executable changed')
    # The independent registry signer attests completeness and stopped legacy
    # instances. Their stop receipts are immutable content-addressed artifacts.
    stopped = record.get('stopped_legacy_receipts')
    if not isinstance(stopped,list) or len(stopped)>128:
        raise ValueError('legacy instance stop evidence required')
    for receipt in stopped:
        raw=Path(receipt['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=receipt['sha256']:
            raise ValueError('legacy stop receipt changed')
        fact=json.loads(raw)
        if fact.get('owner')!=actual['owner'] or fact.get('pid') in {_artifact(v)['pid'] for v in inventory}:
            raise ValueError('legacy stop receipt scope invalid')
        try:
            os.kill(fact['pid'],0)
        except ProcessLookupError:
            continue
        raise ValueError('legacy process still reachable')


def require_operator(actor_id):
    allowed=_read_registry().get('operators')
    if not isinstance(allowed,list) or str(actor_id) not in allowed:
        raise ValueError('actor is not an independently registered switch operator')


def require_document_authorization(evidence):
    allowed=_read_registry().get('authorized_documents')
    if not isinstance(allowed,list) or len(allowed)>64 or evidence['document_digest'] not in allowed:
        raise ValueError('document is not independently authorized for this operation')


def require_live_evidence(evidence):
    """Recheck at every authority-use boundary, including after a drain wait."""
    try:
        value=evidence['expires_at']
        expiry=datetime.fromisoformat(value.replace('Z','+00:00'))
        if expiry.tzinfo is None or expiry<=datetime.now(timezone.utc):raise ValueError()
    except (KeyError,TypeError,AttributeError,ValueError):
        raise ValueError('switch authority expired; renew the durable operation') from None
