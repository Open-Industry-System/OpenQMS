"""Complete, current-authorized CAPA outcomes from a tenant-bound readonly snapshot.

The collector is also usable inside the parent's locked write transaction. It
never changes isolation, acquires write locks, creates versions, or emits audit.
"""
from datetime import UTC, date, datetime
import hashlib
import hmac
import json
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Text, cast, func, select, text
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.config import settings
from app.core.permissions import Module
from app.core.tenant_transaction import TenantBinding, TenantUnavailable
from app.database import TenantSession
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaD7NodeAction, CapaRootCauseVerification
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.models.control_plan import ControlPlan
from app.models.control_plan_version import ControlPlanVersion
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.models.user import User
from app.schemas.capa_outcome_review import CapaOutcomeReview
from app.services.capa_current_access import (
    current_capa_access, current_capa_target_metadata, require_business_namespace,
    require_capa_source_access,
)
from app.services.capa_review_guard import OutcomeReviewConflict, OutcomeReviewLimit, REVIEWED_STATES
from app.services.version_service import verify_cp_version, verify_fmea_version

CONTRACT = 'capa.outcome-review.v1'
MAX_OUTCOME_REVIEW_BYTES = 8 * 1024 * 1024
BATCH_SIZE = 100
_ALLOWED_STATES = REVIEWED_STATES | {'D8_APPROVAL_PENDING'}
_CORE = ('d4_root_cause', 'd5_correction', 'd6_verification', 'd7_prevention',
         'd4_retry_count', 'fmea_ref_id', 'fmea_node_id', 'supplier_id', 'severity')
_VERIFICATIONS = ('verification_id', 'capa_id', 'factory_id', 'root_cause_text', 'method', 'result',
                  'is_verified', 'conclusion', 'evidence_attachments', 'source_ref',
                  'verified_by', 'verified_at', 'created_at', 'updated_at')
_ACTIONS = ('action_id', 'capa_id', 'factory_id', 'action', 'fmea_id', 'failure_mode_node_id',
            'failure_cause_node_id', 'match_source', 'prevention_control_node_id',
            'prevention_control_name_before', 'prevention_control_name_after', 'reason',
            'acted_by', 'acted_at', 'recommendation_hash', 'status')
_GATE = ('decision_id', 'analysis_id', 'audit_run_id', 'revision', 'factory_id', 'decision',
         'no_affected_confirmed', 'version_snapshot', 'defer_reason', 'defer_owner',
         'defer_deadline', 'waiver_reason', 'waiver_items', 'decided_by', 'decided_at')


class OutcomeMaterial(dict):
    """Server-owned internal value; never put free text in diagnostics."""
    def __repr__(self):
        return 'OutcomeMaterial(<controlled material>)'


def _normal(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _normal(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normal(item) for item in value]
    return value


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def _check_size(value):
    if len(_encoded(value)) > MAX_OUTCOME_REVIEW_BYTES:
        raise OutcomeReviewLimit()


def outcome_revision(material: dict) -> str:
    return hmac.new(settings.SECRET_KEY.encode(),
        b'openqms.capa.outcome-review.v1\0' + _encoded(material), hashlib.sha256).hexdigest()


def _tenant_identity(db):
    binding = db.info.get('tenant_binding')
    if settings.TENANT_MODE == 'single' and binding is None:
        return 'public'
    if not isinstance(binding, TenantBinding) or binding.mode != 'business':
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    return str(binding.tenant_id)


def _columns(model, names):
    return [getattr(model, name) for name in names]


def _byte_length(columns):
    return sum((func.coalesce(func.octet_length(cast(col, Text)), 0) for col in columns), 0)


async def _preflight(db, columns, predicate):
    """Only lengths cross the DB boundary before any unbounded body/JSON."""
    size = await db.scalar(select(func.coalesce(func.sum(_byte_length(columns)), 0)).where(predicate))
    if size > MAX_OUTCOME_REVIEW_BYTES:
        raise OutcomeReviewLimit()
    return size


async def _rows(db, model, names, predicate, identifier, *, budget):
    await _preflight(db, _columns(model, names), predicate)
    result, last, encoded_size = [], None, 2
    while True:
        query = select(*_columns(model, names)).where(predicate).order_by(identifier).limit(BATCH_SIZE)
        if last is not None:
            query = query.where(identifier > last)
        batch = (await db.execute(query)).mappings().all()
        if not batch:
            return result
        for row in batch:
            item = _normal(dict(row))
            if 'evidence_attachments' in item:
                evidence = item['evidence_attachments']
                if type(evidence) is not list or any(type(entry) is not dict for entry in evidence):
                    raise OutcomeReviewConflict()
                item['evidence_attachments'] = sorted(evidence, key=lambda entry: (
                    str(entry.get('attachment_id', entry.get('id', ''))), _encoded(entry)))
            encoded_size += len(_encoded(item)) + (1 if result else 0)
            if encoded_size > budget:
                raise OutcomeReviewLimit()
            result.append(item)
        last = batch[-1][identifier.key]


async def _audit(db, capa, actions, extra=None):
    predicate = (AuditLog.table_name == 'capa_eightd', AuditLog.record_id == capa.report_id,
                 AuditLog.factory_id == capa.factory_id, AuditLog.action.in_(actions))
    query = select(AuditLog.log_id).where(*predicate)
    if extra is not None:
        query = query.where(extra)
    identifier = await db.scalar(query.order_by(AuditLog.operated_at.desc(), AuditLog.log_id.desc()).limit(1))
    if identifier is None:
        return None
    await _preflight(db, [AuditLog.changed_fields], AuditLog.log_id == identifier)
    return (await db.execute(select(AuditLog.log_id, AuditLog.action, AuditLog.changed_fields,
        AuditLog.operated_by, AuditLog.operated_at).where(AuditLog.log_id == identifier))).one()


async def _decision_audit(db, capa):
    return await _audit(db, capa, ['D8_APPROVED', 'D8_REJECTED'])


def _receipt(audit):
    if audit is None or type(audit.changed_fields) is not dict:
        return None
    return audit.changed_fields.get('outcome_review')


def _receipt_round(receipt):
    if type(receipt) is not dict or receipt.get('contract') != CONTRACT:
        return None
    try:
        return UUID(receipt['round_id'])
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


async def resolve_review_round(db, capa) -> UUID | None:
    if capa.status in REVIEWED_STATES:
        return _receipt_round(_receipt(await _decision_audit(db, capa)))
    if capa.status != 'D8_APPROVAL_PENDING':
        return None
    # Production TRANSITION uses old_status/new_status. Task 1's committed
    # compatibility fixture also records the earlier from/to envelope.
    transition = await _audit(db, capa, ['TRANSITION'],
        (AuditLog.changed_fields['new_status'].astext == 'D8_APPROVAL_PENDING') |
        (AuditLog.changed_fields['to'].astext == 'D8_APPROVAL_PENDING'))
    if transition is not None:
        return transition.log_id
    return uuid5(NAMESPACE_URL, 'capa.outcome-review.legacy:' + _tenant_identity(db) + ':'
                 + str(capa.report_id) + ':' + capa.updated_at.isoformat())


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED') from None


def _source_key(module, object_id):
    if type(module) is not str:
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    if module == 'control_plan':
        module = 'planning'
    if module not in {'fmea', 'planning'}:
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    return module, str(_uuid(object_id))


def _version_ref(value, *, gate=False):
    keys = {'doc_type', 'doc_id', 'version_after_id', 'sha256'} if gate else {
        'module', 'object_id', 'version_id', 'sha256'}
    if type(value) is not dict or set(value) != keys:
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    module, object_id = _source_key(value['doc_type' if gate else 'module'], value['doc_id' if gate else 'object_id'])
    version_id = value['version_after_id' if gate else 'version_id']
    if version_id is None:
        raise OutcomeReviewConflict()
    _uuid(version_id)
    if type(value['sha256']) is not str or re.fullmatch('[0-9a-f]{64}', value['sha256']) is None:
        raise OutcomeReviewConflict()
    return {'module': module, 'object_id': object_id, 'version_id': version_id, 'sha256': value['sha256']}


async def _controlled_version(db, capa, key, ref):
    module, object_id = key
    model = FMEAVersion if module == 'fmea' else ControlPlanVersion
    identity = model.fmea_id if module == 'fmea' else model.cp_id
    query = select(model.version_id, model.factory_id, model.sha256_hash).where(identity == _uuid(object_id))
    if ref is not None:
        query = query.where(model.version_id == _uuid(ref['version_id']))
    else:
        query = query.order_by(model.major_no.desc(), model.minor_no.desc(), model.created_at.desc(), model.version_id.desc()).limit(1)
    version = (await db.execute(query)).one_or_none()
    if version is None or version.factory_id != capa.factory_id or (ref and version.sha256_hash != ref['sha256']):
        raise OutcomeReviewConflict()
    # Reuse the existing PG/legacy-compact integrity validator, but only after
    # metadata preflight. Never load current graph_data or CP items.
    body = [model.snapshot] if module == 'fmea' else [model.header_snapshot, model.items_snapshot]
    await _preflight(db, body + [model.change_summary], model.version_id == version.version_id)
    validator = verify_fmea_version if module == 'fmea' else verify_cp_version
    if not await validator(db, version.version_id):
        raise OutcomeReviewConflict()
    return {'module': module, 'object_id': object_id, 'version_id': str(version.version_id), 'sha256': version.sha256_hash}


async def _node(db, ref, node_id, node_type=None):
    if type(node_id) is not str or not 1 <= len(node_id) <= 128:
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    path = '$.nodes[*] ? (@.id == $id' + (' && @.type == $type' if node_type else '') + ')'
    present = await db.scalar(select(func.jsonb_path_exists(FMEAVersion.snapshot,
        cast(path, JSONPATH), func.jsonb_build_object('id', node_id, 'type', node_type)))
        .where(FMEAVersion.version_id == _uuid(ref['version_id']),
               func.jsonb_typeof(FMEAVersion.snapshot['nodes']) == 'array'))
    if not present:
        raise OutcomeReviewConflict()


async def _source_access(db, capa, key, access):
    module, identifier = key
    model = FMEADocument if module == 'fmea' else ControlPlan
    identity = model.fmea_id if module == 'fmea' else model.cp_id
    source = (await db.execute(select(model.factory_id, model.product_line_code)
        .where(identity == _uuid(identifier)))).one_or_none()
    if access is not None:
        require_capa_source_access(*access, Module.FMEA if module == 'fmea' else Module.PLANNING, source, capa)
    elif source is None or (source.factory_id, source.product_line_code) != (capa.factory_id, capa.product_line_code):
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')


async def _source_versions(db, capa, core, verifications, actions, gate, affected, receipt):
    required, nodes, bound = set(), [], {}
    def add_bound(ref):
        key = (ref['module'], ref['object_id'])
        if key in bound and bound[key] != ref:
            raise OutcomeReviewConflict()
        required.add(key)
        bound[key] = ref
    snapshot = gate['version_snapshot'] if gate else []
    if type(snapshot) is not list or type(affected) is not list:
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    for value in snapshot:
        add_bound(_version_ref(value, gate=True))
    for doc in affected:
        if type(doc) is not dict or 'doc_type' not in doc or 'doc_id' not in doc:
            raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
        key = _source_key(doc['doc_type'], doc['doc_id'])
        required.add(key)
        if key not in bound:
            raise OutcomeReviewConflict()
    if capa.status in REVIEWED_STATES and receipt is not None:
        if type(receipt) is not dict or type(receipt.get('source_versions')) is not list:
            raise OutcomeReviewConflict()
        for value in receipt['source_versions']:
            add_bound(_version_ref(value))
    def reference(identifier, node_id=None, node_type=None):
        key = ('fmea', identifier)
        required.add(key)
        if node_id is not None:
            nodes.append((key, node_id, node_type))
    if core['fmea_ref_id'] is not None:
        reference(core['fmea_ref_id'], core['fmea_node_id'])
    elif core['fmea_node_id'] is not None:
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    for row in verifications:
        value = row['source_ref']
        if value is not None:
            if (type(value) is not dict or set(value) != {'fmea_id', 'cause_node_id'}
                    or value['fmea_id'] != core['fmea_ref_id']):
                raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
            _uuid(value['fmea_id'])
            reference(value['fmea_id'], value['cause_node_id'], 'FailureCause')
    for row in actions:
        if row['fmea_id'] is not None:
            reference(row['fmea_id'], row['failure_mode_node_id'], 'FailureMode')
            if row['failure_cause_node_id']:
                reference(row['fmea_id'], row['failure_cause_node_id'], 'FailureCause')
            if row['prevention_control_node_id']:
                reference(row['fmea_id'], row['prevention_control_node_id'], 'PreventionControl')
    result = {}
    for key in sorted(required):
        # A version receipt never grants current source-module authority.
        await _source_access(db, capa, key, db.info.get('outcome_read_access'))
        if capa.status in REVIEWED_STATES and key not in bound:
            # A GET cannot reconstruct the version that an old approval saw.
            raise OutcomeReviewConflict()
        result[key] = await _controlled_version(db, capa, key, bound.get(key))
    for key, node_id, node_type in nodes:
        await _node(db, result[key], node_id, node_type)
    for row in actions:
        if row['fmea_id'] is not None and row['failure_cause_node_id']:
            present = await db.scalar(select(func.jsonb_path_exists(FMEAVersion.snapshot,
                cast('$.edges[*] ? (@.source == $cause && @.target == $mode && @.type == "CAUSE_OF")', JSONPATH),
                func.jsonb_build_object('cause', row['failure_cause_node_id'], 'mode', row['failure_mode_node_id'])))
                .where(FMEAVersion.version_id == _uuid(result[('fmea', row['fmea_id'])]['version_id']),
                       func.jsonb_typeof(FMEAVersion.snapshot['edges']) == 'array'))
            if not present:
                raise OutcomeReviewConflict()
    return list(result.values())


async def collect_outcome_material(db, capa) -> dict:
    await require_business_namespace(db)
    fields = _columns(CAPAEightD, _CORE)
    await _preflight(db, fields, CAPAEightD.report_id == capa.report_id)
    core = _normal(dict((await db.execute(select(*fields).where(
        CAPAEightD.report_id == capa.report_id))).mappings().one()))
    material = OutcomeMaterial(contract=CONTRACT, tenant_identity=_tenant_identity(db),
        report_id=str(capa.report_id), factory_id=str(capa.factory_id), product_line_code=capa.product_line_code,
        round_id=_normal(await resolve_review_round(db, capa)), core=core, verifications=[],
        d7_actions=[], doc_gate=None, source_versions=[])
    _check_size(material)
    remaining = MAX_OUTCOME_REVIEW_BYTES - len(_encoded(material))
    verifications = await _rows(db, CapaRootCauseVerification, _VERIFICATIONS,
        CapaRootCauseVerification.capa_id == capa.report_id, CapaRootCauseVerification.verification_id,
        budget=remaining + 2)
    remaining -= len(_encoded(verifications)) - 2
    material['verifications'] = verifications
    actions = await _rows(db, CapaD7NodeAction, _ACTIONS,
        CapaD7NodeAction.capa_id == capa.report_id, CapaD7NodeAction.action_id, budget=remaining + 2)
    remaining -= len(_encoded(actions)) - 2
    material['d7_actions'] = actions
    if any(row['factory_id'] != str(capa.factory_id) for row in verifications + actions):
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    analysis_id = await db.scalar(select(CapaDocgAnalysis.analysis_id).where(
        CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.factory_id == capa.factory_id,
        CapaDocgAnalysis.is_current.is_(True), CapaDocgAnalysis.status == 'done'))
    gate, affected = None, []
    if analysis_id is not None:
        await _preflight(db, [CapaDocgAnalysis.affected_docs], CapaDocgAnalysis.analysis_id == analysis_id)
        affected = await db.scalar(select(CapaDocgAnalysis.affected_docs).where(CapaDocgAnalysis.analysis_id == analysis_id))
        decision_id = await db.scalar(select(CapaDocgDecision.decision_id).where(
            CapaDocgDecision.analysis_id == analysis_id).order_by(CapaDocgDecision.revision.desc()).limit(1))
        if decision_id is not None:
            await _preflight(db, _columns(CapaDocgDecision, _GATE), CapaDocgDecision.decision_id == decision_id)
            gate = _normal(dict((await db.execute(select(*_columns(CapaDocgDecision, _GATE)).where(
                CapaDocgDecision.decision_id == decision_id))).mappings().one()))
    if gate is not None:
        if type(gate['version_snapshot']) is not list:
            raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
        gate['version_snapshot'] = sorted(gate['version_snapshot'], key=_encoded)
        if gate['waiver_items'] is not None:
            gate['waiver_items'] = sorted(gate['waiver_items'], key=_encoded)
    if capa.status == 'D8_APPROVAL_PENDING' and gate is None:
        raise OutcomeReviewConflict()
    remaining -= len(_encoded(gate)) - 4  # replace the null gate placeholder
    if remaining < 0:
        raise OutcomeReviewLimit()
    material['doc_gate'] = gate
    receipt = _receipt(await _decision_audit(db, capa)) if capa.status in REVIEWED_STATES else None
    sources = await _source_versions(db, capa, core, verifications, actions, gate, affected, receipt)
    if len(_encoded(sources)) - 2 > remaining:
        raise OutcomeReviewLimit()
    material['source_versions'] = sources
    _check_size(material)
    return material


async def _admission(db, scope, report_id):
    access = await current_capa_access(db, scope)
    target = await current_capa_target_metadata(db, report_id, access[1], access[2])
    if target.status not in _ALLOWED_STATES:
        raise LookupError('CAPA_OUTCOME_REVIEW_UNAVAILABLE')
    role_id = await db.scalar(select(User.role_id).where(User.user_id == scope.user.user_id))
    signature = (role_id, dict(access[0]), access[1], access[2], target.factory_id, target.product_line_code)
    return target, access, signature


async def _dto(db, capa, material):
    audit = await _decision_audit(db, capa)
    receipt = _receipt(audit)
    revision = outcome_revision(material)
    if capa.status == 'D8_APPROVAL_PENDING':
        binding_status = 'pending'
    elif receipt is None:
        binding_status = 'legacy_unversioned'
    else:
        valid = (type(receipt) is dict and receipt.get('contract') == CONTRACT
                 and _receipt_round(receipt) is not None
                 and type(receipt.get('revision')) is str
                 and re.fullmatch('[0-9a-f]{64}', receipt['revision']) is not None
                 and hmac.compare_digest(receipt['revision'], revision)
                 and audit.action == 'D8_APPROVED')
        binding_status = 'verified' if valid else 'unverifiable'
        # Do not silently re-sign the historical receipt under a new key.
        if type(receipt) is dict and type(receipt.get('revision')) is str and re.fullmatch('[0-9a-f]{64}', receipt['revision']):
            revision = receipt['revision']
    decision = None
    if audit is not None and (capa.status in REVIEWED_STATES or _receipt_round(receipt) == (
            UUID(material['round_id']) if material['round_id'] else None)):
        decision = dict(action='approved' if audit.action == 'D8_APPROVED' else 'rejected',
            actor_id=audit.operated_by, operated_at=audit.operated_at, audit_id=audit.log_id)
    supplement_audit = await _audit(db, capa, ['UPDATE'], AuditLog.changed_fields.has_key('d8_closure'))
    output = CapaOutcomeReview(report_id=capa.report_id, status=capa.status,
        review_round_id=material['round_id'], revision=revision, binding_status=binding_status,
        core={key: material['core'][key] for key in _CORE[:4]},
        verifications=[{key: value for key, value in row.items() if key not in {'factory_id', 'updated_at'}}
                       for row in material['verifications']],
        d7_actions=[{key: value for key, value in row.items() if key not in {'factory_id', 'recommendation_hash'}}
                    for row in material['d7_actions']],
        documents=material['source_versions'], decision=decision,
        supplement=dict(text=None, updated_by=supplement_audit.operated_by if supplement_audit else None,
                        updated_at=supplement_audit.operated_at if supplement_audit else None))
    _check_size(output.model_dump(mode='json'))
    remaining = MAX_OUTCOME_REVIEW_BYTES - len(_encoded(output.model_dump(mode='json')))
    size = await _preflight(db, [CAPAEightD.d8_closure], CAPAEightD.report_id == capa.report_id)
    if size - 4 > remaining:
        raise OutcomeReviewLimit()
    supplement = await db.scalar(select(CAPAEightD.d8_closure).where(CAPAEightD.report_id == capa.report_id))
    if len(_encoded(supplement)) - 4 > remaining:
        raise OutcomeReviewLimit()
    output.supplement.text = supplement
    return output


async def _read_snapshot(db, scope, report_id, binding):
    bind = db.bind
    engine = bind.engine if isinstance(bind, AsyncConnection) else bind
    if engine is None:
        raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED')
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            kwargs = {} if binding is None else {'sync_session_class': TenantSession, 'binding': binding}
            async with AsyncSession(bind=connection, expire_on_commit=False, **kwargs) as snapshot:
                target, access, signature = await _admission(snapshot, scope, report_id)
                snapshot.info['outcome_read_access'] = access
                material = await collect_outcome_material(snapshot, target)
                return material, await _dto(snapshot, target, material), signature


async def read_outcome_review(db, scope, report_id) -> CapaOutcomeReview:
    """A pure GET: build once in RR/RO, independently recheck on request DB."""
    with db.no_autoflush:
        target, access, signature = await _admission(db, scope, report_id)
        binding = db.info.get('tenant_binding')
        try:
            material, output, snapshot_signature = await _read_snapshot(db, scope, report_id, binding)
        except TenantUnavailable:
            raise PermissionError('CAPA_OUTCOME_REVIEW_ACCESS_DENIED') from None
        current, current_access, final_signature = await _admission(db, scope, report_id)
        if (db.info.get('tenant_binding') != binding or signature != snapshot_signature
                or signature != final_signature or target.status != current.status or current.status != output.status):
            raise OutcomeReviewConflict()
        previous = db.info.get('outcome_read_access')
        db.info['outcome_read_access'] = current_access
        try:
            final = await collect_outcome_material(db, current)
            final_output = await _dto(db, current, final)
        finally:
            if previous is None:
                db.info.pop('outcome_read_access', None)
            else:
                db.info['outcome_read_access'] = previous
        if (not hmac.compare_digest(outcome_revision(material), outcome_revision(final))
                or output.model_dump(mode='json') != final_output.model_dump(mode='json')):
            raise OutcomeReviewConflict()
        # DTO construction performs reads too. Authority must still be live
        # after that work, not just before assembling the final material.
        last_target, last_access, last_signature = await _admission(db, scope, report_id)
        if (db.info.get('tenant_binding') != binding or last_signature != signature
                or last_target.status != output.status
                or _normal(await resolve_review_round(db, last_target)) != material['round_id']):
            raise OutcomeReviewConflict()
        for source in final['source_versions']:
            await _source_access(db, last_target, (source['module'], source['object_id']), last_access)
        return output
