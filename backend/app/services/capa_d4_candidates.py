"""Empty-root candidate inputs and commands. Candidate creation is never verification."""
import hmac
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import select, func, text
from sqlalchemy.orm import load_only

from app.core.permissions import PermissionLevel
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.capa_r6 import (AgentD4InputReceipt, AgentD4InputReceiptSource, AgentD4CommandInput,
    AgentD4CandidateCommand, CapaD4Candidate, CapaD4CandidateSource, CapaR6SourceOrigin, CapaR6ReportSnapshot)
from app.models.agent_task import AgentTaskMessage
from app.models.audit import AuditLog
from app.services.agent_runtime import runtime_access, model_egress
from app.services.agent_runtime.d4_text_delivery import _digest, _lock_authority_inputs
from app.services.capa_current_access import current_capa_actor_access, current_capa_target_metadata
from app.services.capa_d4_material import snapshot_report_input, capture_fmea_origin
from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version, _NODES
from app.services.capa_review_guard import assert_reviewed_material_mutable

UNAVAILABLE = 'D4 candidate unavailable'
START_MESSAGE = 'analyze_d4_candidate_v1'
FMEA_CAPABILITY = 'capa.d4.fmea_input.masked.v1'
REQUIRED = ('capa.d2.snapshot.v1', 'capa.d3.snapshot.v1', 'capa.d4.candidate.propose.v1', FMEA_CAPABILITY)


@dataclass(frozen=True)
class D4InputSnapshot:
    values: dict = field(repr=False)
    context: dict = field(repr=False)
    signature: str


def require_admission(identity):
    if identity.trial is None or identity.trial.profile != model_egress.D4_PROFILE:
        raise PermissionError(UNAVAILABLE)
    for capability in REQUIRED:
        runtime_access.require_capability(identity, capability)
    runtime_access.require_delivery(identity, 'restricted', 'masked', controlled_egress=True)


async def _metadata(db, identity):
    factories, lines = await current_capa_actor_access(db, identity.task.executor_user_id, PermissionLevel.EDIT)
    target = await current_capa_target_metadata(db, identity.task.target_capa_id, factories, lines)
    assert_reviewed_material_mutable(target, {'d4_candidates'})
    if target.status != 'D4_ROOT_CAUSE':
        raise PermissionError(UNAVAILABLE)
    return target


def _version(source):
    return dict(kind=source.kind, projection_id=source.projection_id, version=source.version,
        source_version_counter=source.source_version_counter, snapshot_id=None if source.snapshot_id is None else str(source.snapshot_id),
        fmea_id=None if source.fmea_id is None else str(source.fmea_id), node_id=source.node_id,
        factory_id=str(source.factory_id), product_line_code=source.product_line_code)


def _signature(values):
    return _digest('openqms.r6.d4-input.v1', values)


async def bounded_messages(db, identity, command=None):
    rows = list(await db.scalars(select(AgentTaskMessage).where(AgentTaskMessage.task_id == identity.task.task_id)
        .order_by(AgentTaskMessage.sequence).execution_options(populate_existing=True)))
    if ([row.sequence for row in rows] != list(range(1,len(rows)+1))
            or any(row.author_id!=identity.task.executor_user_id or row.sensitivity!='restricted'
                or row.state not in {'queued','claimed','accepted'} for row in rows)):
        raise PermissionError(UNAVAILABLE)
    from app.services.agent_runtime import runtime_messages
    await runtime_messages.require_accepted_prefix(db,identity.task.task_id,identity.run.accepted_message_seq)
    correction = None
    for row in rows:
        if row.content == START_MESSAGE:
            continue
        try:
            intent = json.loads(row.content, object_pairs_hook=_unique_pairs)
            if not isinstance(intent,dict): raise ValueError()
            if set(intent)=={'intent','additional_context'} and intent=={'intent':'continue_d4','additional_context':'none'}:
                predecessor=None
            elif set(intent)=={'intent','predecessor_id'} and intent['intent']=='replace_d4':
                predecessor=UUID(intent['predecessor_id'])
            else:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise PermissionError(UNAVAILABLE) from None
        if command is not None and row.state!='accepted':
            raise PermissionError(UNAVAILABLE)
        if predecessor is None or row.sequence!=identity.run.accepted_message_seq:
            continue
        if row.state!='accepted' or row.delivery_epoch!=identity.run.lease_epoch:
            continue
        first=await db.scalar(select(func.min(AgentTaskMessage.sequence)).where(
            AgentTaskMessage.task_id==identity.task.task_id,AgentTaskMessage.delivery_batch_id==row.delivery_batch_id))
        if first is None or row.delivery_batch_id!=runtime_messages._batch_id(identity,first):
            continue
        correction=(row,predecessor)
    if command is not None and command.operation == 'replace':
        if correction is None or (command.correction_message_id, command.predecessor_id) != (correction[0].message_id, correction[1]):
            raise PermissionError(UNAVAILABLE)
    return correction


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


async def authorize_sources(db, actor_id, report_id, sources, *, fresh=False):
    factories, lines = await current_capa_actor_access(db, actor_id, PermissionLevel.VIEW)
    target = await current_capa_target_metadata(db, report_id, factories, lines)
    scope = SimpleNamespace(user=SimpleNamespace(user_id=actor_id))
    for source in sources:
        if source.report_id != report_id or (source.factory_id, source.product_line_code) != (target.factory_id, target.product_line_code):
            raise PermissionError(UNAVAILABLE)
        if source.kind == 'fmea_projection':
            visible = await visible_fmea_source(db, scope, source.fmea_id)
            if (visible.factory_id, visible.product_line_code) != (source.factory_id, source.product_line_code):
                raise PermissionError(UNAVAILABLE)
            if fresh:
                version = await failure_cause_version(db, visible, source.node_id)
                counter = await db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id == source.fmea_id))
                if version != source.version or type(source.source_version_counter) is not int or source.source_version_counter != counter:
                    raise PermissionError(UNAVAILABLE)
        elif source.kind == 'report_snapshot':
            if source.object_id != report_id:
                raise PermissionError(UNAVAILABLE)
            if fresh:
                kind = {'capa.d2.snapshot.v1': 'd2', 'capa.d3.snapshot.v1': 'd3'}.get(source.projection_id)
                latest = await db.scalar(select(CapaR6ReportSnapshot).where(CapaR6ReportSnapshot.report_id == report_id,
                    CapaR6ReportSnapshot.kind == kind).order_by(CapaR6ReportSnapshot.version.desc()).limit(1))
                if latest is None or latest.snapshot_id != source.snapshot_id or str(latest.version) != source.version:
                    raise PermissionError(UNAVAILABLE)
                field = 'd2_description' if kind == 'd2' else 'd3_interim'
                body = await db.scalar(select(getattr(CAPAEightD, field)).where(CAPAEightD.report_id == report_id))
                if latest.body != (body or ''):
                    raise PermissionError(UNAVAILABLE)
        else:
            raise PermissionError(UNAVAILABLE)


async def build_context(db, identity):
    from app.services.capa_entry_switch import require_generation_enabled
    require_generation_enabled()
    from app.services.capa_entry_switch import admit
    await admit(db, "current")
    current = await runtime_access.lock_runtime_identity(db, identity)
    require_admission(current)
    await _metadata(db, current)
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == current.task.target_capa_id).with_for_update())
    authority = await runtime_access.authorize_task(db, current.task, current.installation)
    source = authority.current_source
    if source is None:
        raise PermissionError(UNAVAILABLE)
    await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id == source.fmea_id).with_for_update(nowait=True))
    await _lock_authority_inputs(db, current)
    current = await runtime_access.refresh_runtime_identity(db, current)
    require_admission(current)
    await _metadata(db, current)
    await bounded_messages(db, current)
    authority = await runtime_access.authorize_task(db, current.task, current.installation)
    if authority.current_source != source:
        raise PermissionError(UNAVAILABLE)
    recipient = await model_egress.task_deployment(db, current.task, lock=True)
    if model_egress.deployment_profile(recipient) != model_egress.D4_PROFILE:
        raise PermissionError(UNAVAILABLE)
    sources, context = [], {}
    for kind, field_name in (('d2', 'd2_description'), ('d3', 'd3_interim')):
        body = await db.scalar(select(getattr(CAPAEightD, field_name)).where(CAPAEightD.report_id == current.task.target_capa_id))
        if len((body or '').encode()) > 16384:
            raise PermissionError(UNAVAILABLE)
        latest = await db.scalar(select(CapaR6ReportSnapshot).where(CapaR6ReportSnapshot.report_id == current.task.target_capa_id,
            CapaR6ReportSnapshot.kind == kind).order_by(CapaR6ReportSnapshot.version.desc()).limit(1))
        if latest is None:
            latest = await snapshot_report_input(db, SimpleNamespace(report_id=current.task.target_capa_id, **{field_name: body}), kind)
            await db.flush()
        if latest.body != (body or ''):
            raise PermissionError(UNAVAILABLE)
        origin = await db.scalar(select(CapaR6SourceOrigin).where(CapaR6SourceOrigin.snapshot_id == latest.snapshot_id))
        if origin is None:
            origin = CapaR6SourceOrigin(report_id=current.task.target_capa_id, kind='report_snapshot', module='capa',
                object_id=current.task.target_capa_id, projection_id=f'capa.{kind}.snapshot.v1', version=str(latest.version),
                factory_id=current.task.factory_id, product_line_code=current.target_product_line_code, snapshot_id=latest.snapshot_id)
            db.add(origin)
            await db.flush()
        sources.append(origin)
        context[kind] = latest.body
    origin = await capture_fmea_origin(db, current.task.executor_user_id, current.task.target_capa_id, source.fmea_id, source.cause_node_id)
    sources.append(origin)
    # Only the single approved node is selected, under its parent lock.
    node = await db.scalar(text(_NODES + 'SELECT n FROM nodes WHERE octet_length(n::text)<=65536 AND (SELECT count(*) FROM nodes)=1'),
        {'fmea_id': source.fmea_id, 'node_id': source.cause_node_id})
    if not isinstance(node, dict) or node.get('type') != 'FailureCause':
        raise PermissionError(UNAVAILABLE)
    context['fmea'] = node
    values = dict(receipt_id=str(uuid4()), report_id=str(current.task.target_capa_id), task_id=str(current.task.task_id),
        run_id=str(current.run.run_id), lease_epoch=current.run.lease_epoch, tenant_generation=current.binding.generation,
        tenant_id=str(current.binding.tenant_id), executor_id=str(current.task.executor_user_id),
        installation_id=str(current.installation.installation_id), deployment_id=str(recipient.deployment_id),
        deployment_config_hmac=recipient.config_hmac, source_count=len(sources),
        input_versions={str(s.source_id): _version(s) for s in sources})
    return D4InputSnapshot(values, context, _signature(values))


async def validate_snapshot(db, identity, snapshot):
    require_admission(identity)
    values = snapshot.values
    if not hmac.compare_digest(_signature(values), snapshot.signature):
        raise PermissionError(UNAVAILABLE)
    expected = dict(report_id=str(identity.task.target_capa_id), task_id=str(identity.task.task_id), run_id=str(identity.run.run_id),
        executor_id=str(identity.task.executor_user_id), installation_id=str(identity.installation.installation_id),
        lease_epoch=identity.run.lease_epoch, tenant_generation=identity.binding.generation, tenant_id=str(identity.binding.tenant_id))
    if any(values.get(key) != value for key, value in expected.items()):
        raise PermissionError(UNAVAILABLE)
    await _metadata(db, identity)
    await bounded_messages(db, identity)
    sources = list(await db.scalars(select(CapaR6SourceOrigin).where(CapaR6SourceOrigin.source_id.in_([UUID(k) for k in values['input_versions']]))))
    if len(sources) != values['source_count'] or {str(s.source_id): _version(s) for s in sources} != values['input_versions']:
        raise PermissionError(UNAVAILABLE)
    authority = await runtime_access.authorize_task(db, identity.task, identity.installation)
    source = authority.current_source
    external = [s for s in sources if s.kind == 'fmea_projection']
    if source is None or len(external) != 1 or (external[0].fmea_id, external[0].node_id) != (source.fmea_id, source.cause_node_id):
        raise PermissionError(UNAVAILABLE)
    await authorize_sources(db, identity.task.executor_user_id, identity.task.target_capa_id, sources, fresh=True)
    if not isinstance(snapshot.context,dict) or set(snapshot.context)!={'d2','d3','fmea'}:
        raise PermissionError(UNAVAILABLE)
    for origin in sources:
        if origin.kind=='report_snapshot':
            captured=await db.get(CapaR6ReportSnapshot,origin.snapshot_id,populate_existing=True)
            key={'capa.d2.snapshot.v1':'d2','capa.d3.snapshot.v1':'d3'}.get(origin.projection_id)
            if captured is None or snapshot.context.get(key)!=captured.body:
                raise PermissionError(UNAVAILABLE)
        elif not hmac.compare_digest(_digest('openqms.fmea.failure-cause-node.v1',snapshot.context['fmea']),origin.version):
            raise PermissionError(UNAVAILABLE)
    recipient = await model_egress.task_deployment(db, identity.task, lock=True)
    if (str(recipient.deployment_id), recipient.config_hmac) != (values['deployment_id'], values['deployment_config_hmac']):
        raise PermissionError(UNAVAILABLE)
    return sources


async def record_delivery(db, identity, snapshot):
    sources = await validate_snapshot(db, identity, snapshot)
    values = dict(snapshot.values)
    values.pop('tenant_id')
    for key in ('receipt_id', 'report_id', 'task_id', 'run_id', 'executor_id', 'installation_id', 'deployment_id'):
        values[key] = UUID(values[key])
    receipt = await db.get(AgentD4InputReceipt, values['receipt_id'])
    if receipt is None:
        db.add(AgentD4InputReceipt(**values, receipt_hmac=snapshot.signature))
        await db.flush()
        db.add_all([AgentD4InputReceiptSource(receipt_id=values['receipt_id'], report_id=values['report_id'], source_id=s.source_id) for s in sources])
        await db.flush()


async def receipt_sources(db, receipt, *, actor_id, task, fresh=False):
    from app.models.agent_task import AgentRun
    from app.models.agent_model_deployment import AgentModelDeployment, AgentTaskModelBinding
    run = await db.get(AgentRun, receipt.run_id, populate_existing=True)
    pin = await db.get(AgentTaskModelBinding, task.task_id, populate_existing=True)
    recipient = None if pin is None else await db.get(AgentModelDeployment, pin.deployment_id, populate_existing=True)
    binding = db.info['tenant_binding']
    values = {key: str(getattr(receipt, key)) for key in ('receipt_id','report_id','task_id','run_id','executor_id','installation_id','deployment_id')}
    values.update(lease_epoch=receipt.lease_epoch, tenant_generation=receipt.tenant_generation, tenant_id=str(binding.tenant_id),
        deployment_config_hmac=receipt.deployment_config_hmac, source_count=receipt.source_count, input_versions=receipt.input_versions)
    if (run is None or run.task_id != task.task_id or run.installation_id != receipt.installation_id
            or receipt.lease_epoch > run.lease_epoch or receipt.task_id != task.task_id or receipt.report_id != task.target_capa_id
            or receipt.executor_id != task.executor_user_id or receipt.installation_id != task.preferred_installation_id
            or (fresh and receipt.tenant_generation != binding.generation) or recipient is None or pin.config_hmac != recipient.config_hmac
            or receipt.deployment_id != recipient.deployment_id or receipt.deployment_config_hmac != recipient.config_hmac
            or model_egress.deployment_profile(recipient) != model_egress.D4_PROFILE
            or not hmac.compare_digest(model_egress._digest(db, recipient), recipient.config_hmac)
            or not hmac.compare_digest(_signature(values), receipt.receipt_hmac)):
        raise PermissionError(UNAVAILABLE)
    sources = list(await db.scalars(select(CapaR6SourceOrigin).join(AgentD4InputReceiptSource,
        AgentD4InputReceiptSource.source_id == CapaR6SourceOrigin.source_id).where(AgentD4InputReceiptSource.receipt_id == receipt.receipt_id,
        AgentD4InputReceiptSource.report_id == receipt.report_id)))
    if len(sources) != receipt.source_count or {str(s.source_id): _version(s) for s in sources} != receipt.input_versions:
        raise PermissionError(UNAVAILABLE)
    await authorize_sources(db, actor_id, task.target_capa_id, sources, fresh=fresh)
    return sources


async def authorize_task_history(db, actor_id, task):
    receipts = list(await db.scalars(select(AgentD4InputReceipt).where(AgentD4InputReceipt.task_id == task.task_id)))
    for receipt in receipts:
        await receipt_sources(db, receipt, actor_id=actor_id, task=task)


def reference(candidate, command):
    return dict(candidate_id=candidate.candidate_id, command_id=command.command_id, report_id=candidate.report_id,
        task_id=candidate.task_id, run_id=candidate.run_id, state=candidate.state, version=candidate.version)


async def save_candidate(db, identity, body):
    from app.services.capa_entry_switch import admit
    await admit(db, "current")
    current = await runtime_access.lock_runtime_identity(db, identity)
    require_admission(current)
    await _metadata(db, current)
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == current.task.target_capa_id).with_for_update())
    existing = await db.scalar(select(AgentD4CandidateCommand).where(AgentD4CandidateCommand.task_id == current.task.task_id,
        AgentD4CandidateCommand.command_key == body.command_key))
    receipt_query = select(AgentD4InputReceipt).where(AgentD4InputReceipt.task_id == current.task.task_id)
    if existing is None:
        from app.services.capa_entry_switch import require_generation_enabled
        require_generation_enabled()
        receipt_query = receipt_query.where(AgentD4InputReceipt.run_id == current.run.run_id,
            AgentD4InputReceipt.lease_epoch == current.run.lease_epoch)
    else:
        receipt_query = receipt_query.join(AgentD4CommandInput, AgentD4CommandInput.receipt_id == AgentD4InputReceipt.receipt_id).where(
            AgentD4CommandInput.command_id == existing.command_id)
    receipts = list(await db.scalars(receipt_query.order_by(AgentD4InputReceipt.receipt_id)))
    if not receipts:
        raise PermissionError(UNAVAILABLE)
    sources = {}
    for receipt in receipts:
        for source in await receipt_sources(db, receipt, actor_id=current.task.executor_user_id, task=current.task, fresh=True):
            sources[source.source_id] = source
    for fmea_id in sorted({s.fmea_id for s in sources.values() if s.fmea_id is not None}, key=str):
        await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id == fmea_id).with_for_update(nowait=True))
    await _lock_authority_inputs(db, current)
    current = await runtime_access.refresh_runtime_identity(db, current)
    require_admission(current)
    await _metadata(db, current)
    for receipt in receipts:
        await receipt_sources(db, receipt, actor_id=current.task.executor_user_id, task=current.task, fresh=True)
    request_hmac = _digest('openqms.r6.d4-command.v1', dict(tenant_id=str(current.binding.tenant_id),
        task_id=str(current.task.task_id), request=body.model_dump(mode='json'), receipt_ids=[str(r.receipt_id) for r in receipts]))
    if existing is not None:
        if not hmac.compare_digest(existing.request_hmac, request_hmac):
            raise ValueError('D4 command conflict')
        candidate = await db.scalar(select(CapaD4Candidate).options(load_only(
            CapaD4Candidate.candidate_id,CapaD4Candidate.report_id,CapaD4Candidate.task_id,CapaD4Candidate.run_id,
            CapaD4Candidate.command_id,CapaD4Candidate.state,CapaD4Candidate.version,CapaD4Candidate.source_count,
            CapaD4Candidate.input_versions,CapaD4Candidate.created_by)).where(CapaD4Candidate.command_id == existing.command_id))
        if candidate is None or candidate.report_id != current.task.target_capa_id:
            raise PermissionError(UNAVAILABLE)
        linked = set(await db.scalars(select(CapaD4CandidateSource.source_id).where(CapaD4CandidateSource.candidate_id == candidate.candidate_id)))
        if (linked != set(sources) or candidate.source_count!=len(sources)
                or candidate.input_versions!={str(k):_version(v) for k,v in sources.items()}
                or candidate.task_id!=existing.task_id or candidate.run_id!=existing.run_id
                or candidate.created_by!=current.task.executor_user_id):
            raise PermissionError(UNAVAILABLE)
        result = reference(candidate, existing)
        await db.commit()
        return result
    await bounded_messages(db, current, body)
    predecessor = None
    if body.operation == 'replace':
        predecessor = await db.scalar(select(CapaD4Candidate).options(load_only(
            CapaD4Candidate.candidate_id,CapaD4Candidate.report_id,CapaD4Candidate.task_id,CapaD4Candidate.run_id,
            CapaD4Candidate.command_id,CapaD4Candidate.state,CapaD4Candidate.version,CapaD4Candidate.source_count,
            CapaD4Candidate.input_versions,CapaD4Candidate.created_by)).where(CapaD4Candidate.candidate_id == body.predecessor_id,
            CapaD4Candidate.task_id == current.task.task_id, CapaD4Candidate.report_id == current.task.target_capa_id)
            .with_for_update().execution_options(populate_existing=True))
        if predecessor is None or predecessor.state != 'pending':
            raise ValueError('D4 predecessor unavailable')
        # The candidate lock is another potential wait. No protected body is
        # selected, and all current authority follows it before state changes.
        current=await runtime_access.refresh_runtime_identity(db,current)
        require_admission(current)
        await _metadata(db,current)
        await bounded_messages(db,current,body)
        for receipt in receipts:
            await receipt_sources(db,receipt,actor_id=current.task.executor_user_id,task=current.task,fresh=True)
        prior_sources = list(await db.scalars(select(CapaR6SourceOrigin).join(CapaD4CandidateSource,
            CapaD4CandidateSource.source_id == CapaR6SourceOrigin.source_id).where(CapaD4CandidateSource.candidate_id == predecessor.candidate_id)))
        await authorize_sources(db, current.task.executor_user_id, current.task.target_capa_id, prior_sources)
        predecessor.state = 'superseded'
        predecessor.version += 1
    maximum = await db.scalar(select(func.max(AgentD4CandidateCommand.sequence)).where(AgentD4CandidateCommand.task_id == current.task.task_id)) or 0
    command = AgentD4CandidateCommand(command_id=uuid4(), report_id=current.task.target_capa_id, task_id=current.task.task_id,
        run_id=current.run.run_id, command_key=body.command_key, operation=body.operation, sequence=maximum+1, request_hmac=request_hmac)
    db.add(command)
    await db.flush()
    candidate = CapaD4Candidate(candidate_id=uuid4(), report_id=current.task.target_capa_id, task_id=current.task.task_id,
        run_id=current.run.run_id, command_id=command.command_id, original_text=body.text, supporting=body.supporting,
        opposing=body.opposing, missing_information=body.missing_information, input_versions={str(k): _version(v) for k,v in sources.items()},
        state='pending', version=1, source_count=len(sources), predecessor_id=body.predecessor_id,
        correction_message_id=body.correction_message_id, created_by=current.task.executor_user_id)
    db.add(candidate)
    await db.flush()
    db.add_all([CapaD4CandidateSource(candidate_id=candidate.candidate_id, report_id=candidate.report_id, source_id=source_id) for source_id in sources])
    db.add_all([AgentD4CommandInput(command_id=command.command_id, receipt_id=r.receipt_id, report_id=command.report_id,
        task_id=command.task_id, run_id=command.run_id) for r in receipts])
    db.add(AuditLog(table_name='capa_d4_candidates', record_id=candidate.candidate_id, action='SAVE_D4_CANDIDATE',
        operated_by=current.task.executor_user_id, factory_id=current.task.factory_id,
        changed_fields=dict(task_id=str(command.task_id), command_id=str(command.command_id), operation=body.operation, state='pending')))
    await db.flush()
    result = reference(candidate, command)
    await db.commit()
    return result


async def current_inputs(db, identity, *, snapshot=None, lock=False):
    from app.services.capa_entry_switch import admit
    await admit(db, "current")
    current = await (runtime_access.lock_runtime_identity(db, identity) if lock else runtime_access.refresh_runtime_identity(db, identity))
    require_admission(current)
    await _metadata(db, current)
    receipts = list(await db.scalars(select(AgentD4InputReceipt).where(AgentD4InputReceipt.run_id == current.run.run_id)))
    for receipt in receipts:
        await receipt_sources(db, receipt, actor_id=current.task.executor_user_id, task=current.task, fresh=True)
    if lock:
        await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == current.task.target_capa_id).with_for_update())
        ids = set()
        if snapshot is not None:
            ids.update(UUID(v['fmea_id']) for v in snapshot.values['input_versions'].values() if v['fmea_id'])
        for receipt in receipts:
            ids.update(UUID(v['fmea_id']) for v in receipt.input_versions.values() if v['fmea_id'])
        for source_id in sorted(ids, key=str):
            await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id == source_id).with_for_update(nowait=True))
        await _lock_authority_inputs(db, current)
        current = await runtime_access.refresh_runtime_identity(db, current)
        require_admission(current)
        for receipt in receipts:
            await receipt_sources(db, receipt, actor_id=current.task.executor_user_id, task=current.task, fresh=True)
    if snapshot is not None:
        await validate_snapshot(db, current, snapshot)
    await bounded_messages(db, current)
    await model_egress.task_deployment(db, current.task, lock=lock)
    return current


async def is_d4_task(db, task):
    """Immutable classification never requires an enabled deployment or DNS."""
    from app.models.agent_model_deployment import AgentTaskModelBinding, AgentModelDeployment
    pin=await db.get(AgentTaskModelBinding,task.task_id,populate_existing=True)
    if pin is None: return False
    row=await db.get(AgentModelDeployment,pin.deployment_id,populate_existing=True)
    if row is None or pin.config_hmac!=row.config_hmac or not hmac.compare_digest(model_egress._digest(db,row),row.config_hmac):
        raise PermissionError(UNAVAILABLE)
    return model_egress.deployment_profile(row)==model_egress.D4_PROFILE
