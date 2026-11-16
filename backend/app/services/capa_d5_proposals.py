"""CAPA-owned D5 writes and full, server-owned delivered-basis evidence.

Receipts are internal only. The context delivery owner must call
record_delivered_basis in its final authorized release transaction and must
supply every tool source it actually releases. No runtime request accepts a
receipt, source, report, executor or proof selected by the plugin.
"""
import hmac
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, or_

from app.models.agent_d5_basis import AgentD5BasisReceipt, AgentD5CommandBasis
from app.models.agent_d5_command import AgentD5Command
from app.models.agent_task import AgentTaskMessage
from app.models.capa import CAPAEightD
from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
from app.models.capa_d5_proposal import CapaD5Proposal, CapaD5ProposalSource
from app.models.audit import AuditLog
from app.services.agent_runtime.d4_text_delivery import _digest, _bounded_field
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from app.services.capa_d5_measures import _basis_current, _visible_metadata
from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version, FAILURE_CAUSE_REFERENCE

UNAVAILABLE = 'D5 command unavailable'
class D5StaffKeyConflict(ValueError):
    pass


SOURCE_KEYS = {'projection_id', 'factory_id', 'product_line_code', 'fmea_id', 'node_id', 'node_hmac'}


async def _current_basis(db, identity):
    """Current report/revision/proof relationships, never independent FK trust."""
    target = (await db.execute(select(CAPAEightD.report_id, CAPAEightD.factory_id,
        CAPAEightD.product_line_code, CAPAEightD.fmea_ref_id).where(
        CAPAEightD.report_id == identity.task.target_capa_id))).one_or_none()
    if (target is None or target.factory_id != identity.task.factory_id
            or target.product_line_code != identity.target_product_line_code):
        raise PermissionError(UNAVAILABLE)
    proofs = list(await db.scalars(select(CapaD4RootCauseSourceProof).where(
        CapaD4RootCauseSourceProof.report_id == target.report_id,
        CapaD4RootCauseSourceProof.status == 'active',
        CapaD4RootCauseSourceProof.invalidated_at.is_(None),
        CapaD4RootCauseSourceProof.tenant_generation == identity.binding.generation)
        .execution_options(populate_existing=True)))
    if len(proofs) != 1:
        raise PermissionError(UNAVAILABLE)
    proof = proofs[0]
    revision = await db.get(CapaD4RootCauseRevision, proof.revision_id, populate_existing=True)
    if (revision is None or revision.report_id != target.report_id
            or revision.field_hmac != proof.field_hmac or proof.factory_id != target.factory_id
            or proof.product_line_code != target.product_line_code):
        raise PermissionError(UNAVAILABLE)
    latest = await db.scalar(select(CapaD4RootCauseRevision.revision_id).where(
        CapaD4RootCauseRevision.report_id == target.report_id).order_by(
        CapaD4RootCauseRevision.revision_no.desc()).limit(1))
    if (latest != proof.revision_id or target.fmea_ref_id != proof.fmea_id
            or proof.source_projection_id != FAILURE_CAUSE_REFERENCE.source_projection_id):
        raise PermissionError(UNAVAILABLE)
    primary = await visible_fmea_source(db, identity.scope, proof.fmea_id)
    if primary.factory_id != proof.factory_id or primary.product_line_code != proof.product_line_code:
        raise PermissionError(UNAVAILABLE)
    await require_source_authority(db, identity, primary, dict(projection_id=proof.source_projection_id,
        fmea_id=str(proof.fmea_id), node_id=proof.cause_node_id))
    from app.services.capa_r6_delivery import require_root_delivery
    await require_root_delivery(db, identity, target, proof)
    return target, proof


async def _source(db, identity, coordinate):
    if (not isinstance(coordinate, dict) or set(coordinate) != {'projection_id', 'fmea_id', 'node_id'}
            or coordinate['projection_id'] != FAILURE_CAUSE_REFERENCE.source_projection_id
            or not isinstance(coordinate['node_id'], str) or not 1 <= len(coordinate['node_id']) <= 128):
        raise PermissionError(UNAVAILABLE)
    try:
        doc = await visible_fmea_source(db, identity.scope, UUID(str(coordinate['fmea_id'])))
        await require_source_authority(db, identity, doc, coordinate)
        version = await failure_cause_version(db, doc, coordinate['node_id'])
    except (ValueError, TypeError):
        raise PermissionError(UNAVAILABLE) from None
    return dict(projection_id=coordinate['projection_id'], factory_id=str(doc.factory_id),
        product_line_code=doc.product_line_code, fmea_id=str(doc.fmea_id), node_id=coordinate['node_id'], node_hmac=version)



async def require_source_authority(db, identity, doc, coordinate):
    """Canonical identity ∩ installation ∩ task, for EVERY delivered coordinate."""
    from datetime import UTC, datetime
    from app.core.permissions import Module
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_task import AgentTaskGrant
    from app.models.agent_d4_recovery import D4TaskParentGrant
    from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
    from app.services.agent.permissions.access import authorize
    from app.services.agent.permissions.catalog import get_capability
    from app.services.agent.permissions.types import AccessAttempt
    from app.services.agent.permissions.derived_sources import DerivedSourceScope
    from app.services.agent_runtime import runtime_access, task_service
    from app.services.agent_runtime.derived_source_grants import scope_from_row
    from app.services.agent_runtime.deployment_profiles import TEXT_CAPABILITY
    profile = None if identity.trial is None else identity.trial.profile
    spec = get_capability(TEXT_CAPABILITY, profile=profile)
    if spec is None:
        raise PermissionError(UNAVAILABLE)
    levels, factories, lines = await task_service._current_access(db, identity.scope)
    source = DerivedSourceScope(identity.task.target_capa_id, TEXT_CAPABILITY, Module.FMEA,
        coordinate['projection_id'], doc.fmea_id, coordinate['node_id'])
    plugins = (await db.execute(select(AgentPluginGrant, AgentPluginDerivedSourceScope)
        .join(AgentPluginDerivedSourceScope, AgentPluginDerivedSourceScope.plugin_grant_id == AgentPluginGrant.grant_id)
        .where(AgentPluginGrant.installation_id == identity.installation.installation_id,
            AgentPluginGrant.enabled.is_(True), AgentPluginGrant.capability_id == TEXT_CAPABILITY)
        .execution_options(populate_existing=True))).all()
    tasks = (await db.execute(select(AgentTaskGrant, AgentTaskDerivedSourceScope, D4TaskParentGrant.plugin_grant_id)
        .join(AgentTaskDerivedSourceScope, AgentTaskDerivedSourceScope.task_grant_id == AgentTaskGrant.grant_id)
        .join(D4TaskParentGrant, D4TaskParentGrant.task_grant_id == AgentTaskGrant.grant_id)
        .where(AgentTaskGrant.task_id == identity.task.task_id, AgentTaskGrant.capability_id == TEXT_CAPABILITY,
            AgentTaskGrant.access_kind == 'read').execution_options(populate_existing=True))).all()
    for plugin, p_scope in plugins:
        for task, t_scope, parent in tasks:
            if parent != plugin.grant_id:
                continue
            attempt = AccessAttempt(spec, levels,
                None if factories.accessible_factory_ids is None else frozenset(factories.accessible_factory_ids),
                None if lines.mode == 'ALL' else frozenset(lines.codes or []),
                runtime_access._grant(plugin), runtime_access._grant(task), identity.task.factory_id,
                identity.task.target_capa_id, identity.target_product_line_code, datetime.now(UTC),
                catalog_profile=profile, identity_bypass_row_level_security=lines.mode == 'ALL',
                current_source=source, plugin_source_scope=scope_from_row(p_scope), task_source_scope=scope_from_row(t_scope))
            if authorize(attempt).allowed:
                return
    raise PermissionError(UNAVAILABLE)

def _receipt_payload(receipt, tenant_id):
    return {'tenant_id': str(tenant_id)} | {key: str(getattr(receipt, key)) for key in (
        'receipt_id', 'task_id', 'run_id', 'report_id', 'revision_id', 'proof_id', 'lease_epoch', 'tenant_generation')} | {
            'sources': receipt.sources}



@dataclass(frozen=True, slots=True)
class D5ContextSnapshot:
    # JSON strings keep the sealed object deeply immutable. Bodies never enter
    # the receipt, command ledger or security audit.
    payload_json: str = field(repr=False)
    signature: str

    @property
    def context(self):
        return json.loads(self.payload_json)['context']


async def build_d5_context(db, identity, *, source_queries):
    """Execute authorized context reads and seal EXACT bodies/source versions.

    An internal tool dispatcher may request additional supported coordinates;
    it cannot submit its own body, version, proof or receipt source declaration.
    The returned context is the only body that the future R5 egress may send.
    """
    from app.services.agent_runtime import d5_commands, runtime_access
    from app.services.fmea_agent_sources import _NODES
    current = await runtime_access.refresh_runtime_identity(db, identity)
    d5_commands.require_r5_admission(current)
    target, proof = await _current_basis(db, current)
    if not isinstance(source_queries, list) or not source_queries:
        raise PermissionError(UNAVAILABLE)
    from app.services.agent_runtime.model_egress import R6_PROFILE
    r6 = current.trial is not None and current.trial.profile == R6_PROFILE
    sources, tools, context_epochs = [], [], []
    for query in source_queries:
        source = await _source(db, current, query)
        params = {'fmea_id': UUID(source['fmea_id']), 'node_id': source['node_id']}
        if r6:
            # One MVCC statement captures the body and its source-parent epoch.
            pair = (await db.execute(text(_NODES + '''SELECT n,
                (SELECT lock_version FROM fmea_documents WHERE fmea_id=:fmea_id) AS source_epoch
                FROM nodes WHERE octet_length(n::text) <= 65536 AND (SELECT count(*) FROM nodes) = 1'''), params)).one_or_none()
            node, epoch = pair if pair is not None else (None, None)
            if type(epoch) is not int or epoch < 0:
                raise PermissionError(UNAVAILABLE)
            context_epochs.append(dict(source, source_version_counter=epoch))
        else:
            node = (await db.execute(text(_NODES + 'SELECT n FROM nodes WHERE octet_length(n::text) <= 65536 AND (SELECT count(*) FROM nodes) = 1'), params)).scalar_one_or_none()
        if not isinstance(node, dict):
            raise PermissionError(UNAVAILABLE)
        # Recheck against precisely the body just read, not a later node.
        node_hmac = _digest_node(node)
        if node_hmac != source['node_hmac']:
            raise PermissionError(UNAVAILABLE)
        sources.append(source)
        tools.append(dict(source=source, data=node))
    primary = dict(projection_id=proof.source_projection_id, factory_id=str(proof.factory_id),
        product_line_code=proof.product_line_code, fmea_id=str(proof.fmea_id),
        node_id=proof.cause_node_id, node_hmac=proof.node_hmac)
    if primary not in sources or not await _basis_current(db, current.scope, target,
            SimpleNamespace(proof_id=proof.proof_id, revision_id=proof.revision_id),
            [SimpleNamespace(**(source | {'fmea_id': UUID(source['fmea_id'])})) for source in sources]):
        raise PermissionError(UNAVAILABLE)
    payload = dict(tenant_id=str(current.binding.tenant_id), task_id=str(current.task.task_id), run_id=str(current.run.run_id),
        report_id=str(target.report_id), revision_id=str(proof.revision_id), proof_id=str(proof.proof_id),
        lease_epoch=current.run.lease_epoch, tenant_generation=current.binding.generation,
        sources=sorted({tuple(sorted(source.items())): source for source in sources}.values(),
            key=lambda source: (source['projection_id'], source['fmea_id'], source['node_id'])),
        context=dict(d4_root_cause=await _bounded_field(db, target.report_id), tools=tools))
    from app.services.capa_r6_delivery import require_root_delivery, complete_root_input_binding, validate_context_source_epochs
    if r6:
        context_epochs = sorted({tuple(sorted(entry.items())): entry for entry in context_epochs}.values(),
            key=lambda entry: (entry['projection_id'], entry['fmea_id'], entry['node_id']))
        await validate_context_source_epochs(db, payload['sources'], context_epochs, scope=current.scope)
        payload['context_source_epochs'] = context_epochs
    root_binding = complete_root_input_binding(await require_root_delivery(db, current, target, proof), context_epochs)
    if root_binding is not None:
        payload['root_input_binding'] = root_binding
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return D5ContextSnapshot(raw, _digest('openqms.d5.context-snapshot.v1', payload))


def _digest_node(node):
    import hashlib
    from app.config import settings
    raw = json.dumps(node, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hmac.new(settings.SECRET_KEY.encode(), b'openqms.fmea.failure-cause-node.v1\n' + raw,
        hashlib.sha256).hexdigest()


async def validate_d5_context_for_release(db, identity, *, snapshot):
    """Lock and revalidate the EXACT signed snapshot; this creates no receipt.

    The model egress uses it immediately before outbound under current source,
    installation, task, run and ACL fences. A control attempt is not basis.
    """
    from app.services.agent_runtime import d5_commands, runtime_access
    from app.services.agent_runtime.d4_text_delivery import _lock_authority_inputs
    from app.models.fmea import FMEADocument
    if not isinstance(snapshot, D5ContextSnapshot):
        raise PermissionError(UNAVAILABLE)
    payload = json.loads(snapshot.payload_json)
    if not hmac.compare_digest(snapshot.signature, _digest('openqms.d5.context-snapshot.v1', payload)):
        raise PermissionError(UNAVAILABLE)
    current = await runtime_access.lock_runtime_identity(db, identity)
    d5_commands.require_r5_admission(current)
    await db.scalar(select(CAPAEightD.report_id).where(
        CAPAEightD.report_id == current.task.target_capa_id).with_for_update())
    for fmea_id in sorted({UUID(source['fmea_id']) for source in payload['sources']}, key=str):
        await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id == fmea_id)
            .with_for_update(nowait=True))
    await _lock_authority_inputs(db, current)
    current = await runtime_access.refresh_runtime_identity(db, current)
    d5_commands.require_r5_admission(current)
    target, proof = await _current_basis(db, current)
    from app.services.capa_r6_delivery import require_root_delivery, complete_root_input_binding, validate_context_source_epochs
    from app.services.agent_runtime.model_egress import R6_PROFILE
    epochs = payload.get('context_source_epochs')
    if current.trial is not None and current.trial.profile == R6_PROFILE:
        await validate_context_source_epochs(db, payload['sources'], epochs, scope=current.scope)
    elif epochs is not None:
        raise PermissionError(UNAVAILABLE)
    expected_root = complete_root_input_binding(await require_root_delivery(db, current, target, proof), epochs)
    if payload.get('root_input_binding') != expected_root:
        raise PermissionError(UNAVAILABLE)
    expected = dict(tenant_id=str(current.binding.tenant_id), task_id=str(current.task.task_id), run_id=str(current.run.run_id),
        report_id=str(target.report_id), revision_id=str(proof.revision_id), proof_id=str(proof.proof_id),
        lease_epoch=current.run.lease_epoch, tenant_generation=current.binding.generation)
    if any(payload[key] != value for key, value in expected.items()):
        raise PermissionError(UNAVAILABLE)
    sources = payload['sources']
    for source in sources:
        if await _source(db, current, {key: source[key] for key in ('projection_id', 'fmea_id', 'node_id')}) != source:
            raise PermissionError(UNAVAILABLE)
    if payload['context']['d4_root_cause'] != await _bounded_field(db, target.report_id) or not await _basis_current(
            db, current.scope, target, SimpleNamespace(proof_id=proof.proof_id, revision_id=proof.revision_id),
            [SimpleNamespace(**(source | {'fmea_id': UUID(source['fmea_id'])})) for source in sources]):
        raise PermissionError(UNAVAILABLE)
    return current, expected, sources


async def record_delivered_basis(db, identity, *, snapshot):
    """Record usable source basis only after a successful exact-context round.

    The platform gateway holds release fences while calling the model, then
    records this receipt and commits before returning the model output. Unknown
    or failed sends create no usable basis. This is not a provider ACK claim.
    """
    current, expected, sources = await validate_d5_context_for_release(db, identity, snapshot=snapshot)
    receipt = AgentD5BasisReceipt(receipt_id=uuid4(), **{key: UUID(value) if key.endswith('_id') else value
        for key, value in expected.items() if key != 'tenant_id'}, sources=sources)
    receipt.basis_hmac = _digest('openqms.d5.delivered-basis.v1', _receipt_payload(receipt, current.binding.tenant_id))
    db.add(receipt)
    await db.flush()
    from app.services.capa_r6_delivery import add_root_delivery_binding
    await add_root_delivery_binding(db, current, receipt, json.loads(snapshot.payload_json).get('root_input_binding'))
    return receipt.receipt_id


async def delivered_sources(db, identity):
    """Union ALL delivered tool sources; a plugin cannot select a subset."""
    target, proof = await _current_basis(db, identity)
    receipts = list(await db.scalars(select(AgentD5BasisReceipt).where(
        AgentD5BasisReceipt.run_id == identity.run.run_id).order_by(AgentD5BasisReceipt.receipt_id)
        .execution_options(populate_existing=True)))
    if not receipts:
        raise PermissionError(UNAVAILABLE)
    union = {}
    for receipt in receipts:
        from app.services.capa_r6_delivery import validate_root_delivery_binding
        await validate_root_delivery_binding(db, receipt, identity.binding.tenant_id,
            scope=identity.scope, identity=identity, target=target, proof=proof)
        if (receipt.task_id != identity.task.task_id or receipt.report_id != target.report_id
                or receipt.revision_id != proof.revision_id or receipt.proof_id != proof.proof_id
                or receipt.lease_epoch != identity.run.lease_epoch
                or receipt.tenant_generation != identity.binding.generation
                or not isinstance(receipt.sources, list) or not receipt.sources
                or not hmac.compare_digest(receipt.basis_hmac,
                    _digest('openqms.d5.delivered-basis.v1', _receipt_payload(receipt, identity.binding.tenant_id)))):
            raise PermissionError(UNAVAILABLE)
        for source in receipt.sources:
            if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
                raise PermissionError(UNAVAILABLE)
            coordinate = {key: source[key] for key in ('projection_id', 'fmea_id', 'node_id')}
            current = await _source(db, identity, coordinate)
            if current != source:
                raise PermissionError(UNAVAILABLE)
            union[tuple(sorted(source.items()))] = source
    sources = list(union.values())
    primary = dict(projection_id=proof.source_projection_id, factory_id=str(proof.factory_id),
        product_line_code=proof.product_line_code, fmea_id=str(proof.fmea_id),
        node_id=proof.cause_node_id, node_hmac=proof.node_hmac)
    if primary not in sources or not await _basis_current(db, identity.scope, target,
            SimpleNamespace(proof_id=proof.proof_id, revision_id=proof.revision_id),
            [SimpleNamespace(**(s | {'fmea_id': UUID(s['fmea_id'])})) for s in sources]):
        raise PermissionError(UNAVAILABLE)
    return proof, sources


async def require_bounded_messages(db, identity, body):
    """Only fixed start and explicit, source-free structured correction intent.

    Arbitrary user text may be delivered to a permitted model later, but has no
    known complete business-source scope here and therefore closes shared save.
    """
    import json
    rows = list(await db.scalars(select(AgentTaskMessage).where(
        AgentTaskMessage.task_id == identity.task.task_id,
        or_(AgentTaskMessage.sequence <= identity.run.accepted_message_seq, AgentTaskMessage.state != 'queued'))
        .order_by(AgentTaskMessage.sequence).execution_options(populate_existing=True)))
    correction = None
    for message in rows:
        if message.content == START_MESSAGE and message.sequence == 1:
            continue
        try:
            def unique_object(pairs):
                value = dict(pairs)
                if len(value) != len(pairs):
                    raise ValueError('Duplicate intent key')
                return value
            content = json.loads(message.content, object_pairs_hook=unique_object)
        except (ValueError, TypeError):
            raise PermissionError(UNAVAILABLE) from None
        if (content == {'intent':'continue_d5','additional_context':'none'}
                and message.state == 'accepted' and message.author_id == identity.task.executor_user_id):
            continue
        if (not isinstance(content, dict) or set(content) != {'intent', 'predecessor_id'}
                or content['intent'] != 'replace_d5' or message.state != 'accepted'
                or message.author_id != identity.task.executor_user_id):
            raise PermissionError(UNAVAILABLE)
        try:
            UUID(content['predecessor_id'])
        except (ValueError, TypeError, AttributeError):
            raise PermissionError(UNAVAILABLE) from None
        if message.message_id == body.correction_message_id:
            correction = (message, content)
    if body.operation == 'replace':
        if (correction is None or correction[1]['predecessor_id'] != str(body.predecessor_id)
                or correction[0].sequence != identity.run.accepted_message_seq
                or correction[0].delivery_epoch != identity.run.lease_epoch):
            raise PermissionError(UNAVAILABLE)
        from app.services.agent_runtime.runtime_messages import _batch_id
        first = await db.scalar(select(func.min(AgentTaskMessage.sequence)).where(
            AgentTaskMessage.task_id == identity.task.task_id,
            AgentTaskMessage.delivery_batch_id == correction[0].delivery_batch_id))
        if first is None or correction[0].delivery_batch_id != _batch_id(identity, first):
            raise PermissionError(UNAVAILABLE)


async def replay_reference(db, identity, command):
    _, rows, source_sets = await _visible_metadata(db, identity.scope, identity.task.target_capa_id)
    matching = [row for row in rows if row.proposal_id == command.proposal_id and row.task_id == identity.task.task_id]
    if len(matching) != 1:
        raise PermissionError(UNAVAILABLE)
    stored = await db.get(AgentD5Command, command.command_id, populate_existing=True)
    if (stored is None or stored.proposal_id != command.proposal_id
            or stored.task_id != identity.task.task_id):
        raise PermissionError(UNAVAILABLE)
    receipts = list(await db.scalars(select(AgentD5BasisReceipt).join(AgentD5CommandBasis,
        AgentD5CommandBasis.receipt_id == AgentD5BasisReceipt.receipt_id).where(
        AgentD5CommandBasis.command_id == stored.command_id).execution_options(populate_existing=True)))
    if not receipts:
        raise PermissionError(UNAVAILABLE)
    row = matching[0]
    pinned_sources = set()
    for receipt in receipts:
        from app.services.capa_r6_delivery import validate_root_delivery_binding
        target, proof = await _current_basis(db, identity)
        await validate_root_delivery_binding(db, receipt, identity.binding.tenant_id, scope=identity.scope,
            identity=identity, target=target, proof=proof)
        if (receipt.task_id != identity.task.task_id or receipt.run_id != stored.run_id
                or receipt.report_id != identity.task.target_capa_id
                or receipt.revision_id != row.revision_id or receipt.proof_id != row.proof_id
                or receipt.tenant_generation != identity.binding.generation
                or not hmac.compare_digest(receipt.basis_hmac, _digest('openqms.d5.delivered-basis.v1',
                    _receipt_payload(receipt, identity.binding.tenant_id)))):
            raise PermissionError(UNAVAILABLE)
        for source in receipt.sources:
            if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
                raise PermissionError(UNAVAILABLE)
            pinned_sources.add(tuple(sorted(source.items())))
    actual_sources = {tuple(sorted(dict(projection_id=source.projection_id,
        factory_id=str(source.factory_id), product_line_code=source.product_line_code,
        fmea_id=str(source.fmea_id), node_id=source.node_id, node_hmac=source.node_hmac).items()))
        for source in source_sets[command.proposal_id]}
    if pinned_sources != actual_sources:
        raise PermissionError(UNAVAILABLE)
    for source in source_sets[command.proposal_id]:
        doc = await visible_fmea_source(db, identity.scope, source.fmea_id)
        await require_source_authority(db, identity, doc, dict(
            projection_id=source.projection_id, fmea_id=str(source.fmea_id), node_id=source.node_id))
    # _visible_metadata validates command/proposal/task/run/revision/proof joins.
    return dict(proposal_id=command.proposal_id, state=matching[0].state, command_id=command.command_id)


async def insert_proposal(db, identity, body, request_hmac, proof, sources, receipt_ids):
    predecessor = None
    if body.operation == 'replace':
        predecessor = await db.scalar(select(CapaD5Proposal).where(
            CapaD5Proposal.proposal_id == body.predecessor_id).with_for_update()
            .execution_options(populate_existing=True))
        if (predecessor is None or predecessor.task_id != identity.task.task_id
                or predecessor.report_id != identity.task.target_capa_id or predecessor.state != 'pending'):
            raise ValueError('D5 command conflict')
        # Replacements also need all original source permissions, independently
        # of sources in the newly delivered context.
        await replay_reference(db, identity, SimpleNamespace(proposal_id=predecessor.proposal_id,
            command_id=predecessor.command_id))
    sequence = (await db.scalar(select(func.max(AgentD5Command.sequence)).where(
        AgentD5Command.task_id == identity.task.task_id)) or 0) + 1
    command_id, proposal_id = uuid4(), uuid4()
    command = AgentD5Command(command_id=command_id, task_id=identity.task.task_id,
        run_id=identity.run.run_id, operation=body.operation, command_key=body.command_key,
        request_hmac=request_hmac, sequence=sequence, proposal_id=proposal_id)
    db.add(command)
    await db.flush()
    proposal = CapaD5Proposal(proposal_id=proposal_id, report_id=identity.task.target_capa_id,
        task_id=identity.task.task_id, original_text=body.text, revision_id=proof.revision_id,
        proof_id=proof.proof_id, state='pending', command_id=command_id,
        predecessor_id=body.predecessor_id, correction_message_id=body.correction_message_id,
        created_by=identity.task.executor_user_id)
    db.add(proposal)
    await db.flush()
    for source in sources:
        db.add(CapaD5ProposalSource(proposal_id=proposal_id, **(source | {
            'factory_id': UUID(source['factory_id']), 'fmea_id': UUID(source['fmea_id'])})))
    for receipt_id in receipt_ids:
        db.add(AgentD5CommandBasis(command_id=command_id, receipt_id=receipt_id))
    if predecessor is not None:
        predecessor.state = 'superseded'
    db.add(AuditLog(table_name='capa_d5_proposals', record_id=proposal_id,
        action='D5_PROPOSAL_' + body.operation.upper(), operated_by=identity.task.executor_user_id,
        factory_id=identity.task.factory_id, correlation_id=identity.run.run_id,
        changed_fields=dict(task_id=str(identity.task.task_id), run_id=str(identity.run.run_id),
            command_id=str(command_id), proposal_id=str(proposal_id), sequence=sequence,
            operation=body.operation)))
    return dict(proposal_id=proposal_id, state='pending', command_id=command_id)


async def _staff_metadata(db, scope, report_id, proposal_id):
    """Employee permission only; task/run grants never authorize staff actions."""
    from app.core.permissions import Module, PermissionLevel
    from app.services.capa_current_access import current_capa_access
    access = await current_capa_access(db, scope)
    if access[0].get(Module.CAPA, PermissionLevel.NONE) < PermissionLevel.EDIT:
        raise PermissionError(UNAVAILABLE)
    target, rows, sources = await _visible_metadata(db, scope, report_id, access)
    row = next((row for row in rows if row.proposal_id == proposal_id), None)
    if row is None:
        raise LookupError('D5 item unavailable')
    return target, row, sources[proposal_id]


async def staff_action(db, scope, report_id, proposal_id, *, operation, operation_key, value, checkpoint_boundary=None):
    """Atomically adopt/withdraw one currently readable proposal.

    Report → proposal → source parents → employee authority is the write fence.
    The only body read for adoption freshness follows complete source admission.
    Caller owns rollback on rejected requests; successful effects commit together.
    """
    from app.schemas.capa_d5_staff import D5Adopt, D5Withdraw
    from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Withdrawal, CapaD5StaffReceipt
    from app.models.fmea import FMEADocument
    from app.services.agent_runtime.control_authority_fence import lock_employee_acl
    from app.services.capa_review_guard import assert_reviewed_material_mutable
    from app.state_machines.eightd_state import EightDState
    if operation not in {'adopt', 'withdraw'}:
        raise ValueError('D5 operation conflict')
    request = (D5Adopt(operation_key=operation_key, final_text=value) if operation == 'adopt'
        else D5Withdraw(operation_key=operation_key, reason=value))
    await _staff_metadata(db, scope, report_id, proposal_id)
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == report_id).with_for_update())
    await db.scalar(select(CapaD5Proposal.proposal_id).where(
        CapaD5Proposal.proposal_id == proposal_id, CapaD5Proposal.report_id == report_id).with_for_update())
    target, row, sources = await _staff_metadata(db, scope, report_id, proposal_id)
    for source_id in sorted({source.fmea_id for source in sources}, key=str):
        await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id == source_id)
            .with_for_update(nowait=True))
    await lock_employee_acl(db, (scope.user.user_id,))
    target, row, sources = await _staff_metadata(db, scope, report_id, proposal_id)
    assert_reviewed_material_mutable(target, {'d5_proposals', 'd5_measures'})
    if checkpoint_boundary is not None:
        from app.services.agent_runtime.task_controls import require_d5_checkpoint_member
        await require_d5_checkpoint_member(db, scope, *checkpoint_boundary, report_id, proposal_id)
    binding = db.info.get('tenant_binding')
    fingerprint = _digest('openqms.d5.staff.v1', dict(
        tenant_id=None if binding is None else str(binding.tenant_id), actor_id=str(scope.user.user_id),
        report_id=str(report_id), proposal_id=str(proposal_id), operation=operation,
        request=request.model_dump(mode='json')))
    receipt = await db.scalar(select(CapaD5StaffReceipt).where(
        CapaD5StaffReceipt.actor_id == scope.user.user_id,
        CapaD5StaffReceipt.operation_key == operation_key).execution_options(populate_existing=True))
    if receipt is not None:
        if not hmac.compare_digest(receipt.request_hmac, fingerprint):
            raise D5StaffKeyConflict('D5 operation conflict')
        result = dict(proposal_id=proposal_id, state=row.state)
        if operation == 'adopt': result['measure_id'] = receipt.measure_id
        await db.commit()
        return result
    if row.state != 'pending':
        raise ValueError('D5 operation conflict')
    if operation == 'adopt' and (target.status != EightDState.D5_CORRECTION
            or not await _basis_current(db, scope, target, row, sources)):
        raise ValueError('D5 adoption basis or stage conflict')
    # The final refresh occurs after every potentially waiting lock and basis read.
    target, row, _ = await _staff_metadata(db, scope, report_id, proposal_id)
    assert_reviewed_material_mutable(target, {'d5_proposals', 'd5_measures'})
    if row.state != 'pending': raise ValueError('D5 operation conflict')
    reference = uuid4()
    if operation == 'adopt':
        db.add(CapaD5Measure(measure_id=reference, proposal_id=proposal_id,
            final_text=value, adopted_by=scope.user.user_id))
    else:
        db.add(CapaD5Withdrawal(withdrawal_id=reference, proposal_id=proposal_id,
            reason=value, actor_id=scope.user.user_id))
    await db.flush()
    from sqlalchemy import update
    await db.execute(update(CapaD5Proposal).where(CapaD5Proposal.proposal_id == proposal_id)
        .values(state='adopted' if operation == 'adopt' else 'withdrawn'))
    db.add(CapaD5StaffReceipt(actor_id=scope.user.user_id, operation_key=operation_key,
        operation=operation, request_hmac=fingerprint, proposal_id=proposal_id,
        measure_id=reference if operation == 'adopt' else None,
        withdrawal_id=reference if operation == 'withdraw' else None))
    db.add(AuditLog(table_name='capa_d5_proposals', record_id=proposal_id,
        action='D5_PROPOSAL_' + operation.upper(), operated_by=scope.user.user_id,
        factory_id=target.factory_id, changed_fields=dict(proposal_id=str(proposal_id),
            operation=operation, reference_id=str(reference))))
    from app.services.capa_d4_material import bump_material
    await bump_material(db, report_id)
    await db.commit()
    result = dict(proposal_id=proposal_id, state='adopted' if operation == 'adopt' else 'withdrawn')
    if operation == 'adopt': result['measure_id'] = reference
    return result
