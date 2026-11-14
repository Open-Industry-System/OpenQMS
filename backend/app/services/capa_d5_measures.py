"""Project D5 history by current report and complete original source authority.

Read paths select association/source metadata first. Hidden entries do not take
part in counts, pages or body queries. This service grants no write capability.
"""
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB

from app.models.agent_d5_command import AgentD5Command
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal, CapaD5ProposalSource
from app.schemas.capa_d5_measure import D5MeasureItem, D5MeasureList, D5ProposalItem, D5ProposalList
from app.services.agent.permissions.derived_sources import SourceUnavailable
from app.services.capa_current_access import current_capa_access, current_capa_target_metadata
from app.services import fmea_agent_sources


async def _target(db, scope, report_id, access=None):
    _, factories, lines = access if access is not None else await current_capa_access(db, scope)
    return await current_capa_target_metadata(db, report_id, factories, lines)


async def _visible_metadata(db, scope, report_id, access=None):
    target = await _target(db, scope, report_id, access)
    p, command = CapaD5Proposal, AgentD5Command
    proof, revision = CapaD4RootCauseSourceProof, CapaD4RootCauseRevision
    # Independent foreign keys establish existence only. Every association must
    # match this report, task and command before any proposal text is selected.
    query = (select(p.proposal_id, p.state, p.created_at, p.revision_id, p.proof_id,
                    p.task_id, p.predecessor_id, p.correction_message_id,
                    proof.factory_id, proof.product_line_code, proof.source_projection_id,
                    proof.fmea_id, proof.cause_node_id, proof.node_hmac)
        .join(command, (command.command_id == p.command_id) & (command.proposal_id == p.proposal_id)
              & (command.task_id == p.task_id))
        .join(AgentTask, (AgentTask.task_id == p.task_id) & (AgentTask.target_capa_id == p.report_id)
              & (AgentTask.factory_id == target.factory_id))
        .join(AgentRun, (AgentRun.run_id == command.run_id) & (AgentRun.task_id == p.task_id))
        .join(revision, (revision.revision_id == p.revision_id) & (revision.report_id == p.report_id))
        .join(proof, (proof.proof_id == p.proof_id) & (proof.report_id == p.report_id)
              & (proof.revision_id == p.revision_id) & (proof.field_hmac == revision.field_hmac))
        .join(CapaRootCauseVerification, (CapaRootCauseVerification.verification_id == proof.verification_id)
              & (CapaRootCauseVerification.capa_id == p.report_id))
        .where(p.report_id == report_id)
        .order_by(p.created_at, p.proposal_id))
    with db.no_autoflush:
        rows = (await db.execute(query)).all()
        sources = (await db.execute(select(CapaD5ProposalSource).where(
            CapaD5ProposalSource.proposal_id.in_([r.proposal_id for r in rows])).execution_options(populate_existing=True))).scalars().all() if rows else []
    grouped = defaultdict(list)
    for source in sources:
        grouped[source.proposal_id].append(source)
    visible, source_sets = [], {}
    source_cache = {}
    for row in rows:
        all_sources = grouped[row.proposal_id]
        primary = (row.source_projection_id, row.factory_id, row.product_line_code,
                   row.fmea_id, row.cause_node_id, row.node_hmac)
        if (not all_sources or row.factory_id != target.factory_id
                or row.product_line_code != target.product_line_code
                or primary not in {(s.projection_id, s.factory_id, s.product_line_code,
                                    s.fmea_id, s.node_id, s.node_hmac) for s in all_sources}):
            continue
        if row.predecessor_id is not None:
            with db.no_autoflush:
                predecessor = await db.scalar(select(p.proposal_id).where(
                    p.proposal_id == row.predecessor_id, p.report_id == report_id,
                    p.task_id == row.task_id))
                message = await db.scalar(select(AgentTaskMessage.message_id).where(
                    AgentTaskMessage.message_id == row.correction_message_id,
                    AgentTaskMessage.task_id == row.task_id))
            if predecessor is None or message is None:
                continue
        allowed = True
        for source in all_sources:
            if source.projection_id != fmea_agent_sources.FAILURE_CAUSE_REFERENCE.source_projection_id:
                allowed = False
                break
            if source.fmea_id not in source_cache:
                try:
                    if access is None:
                        source_cache[source.fmea_id] = await fmea_agent_sources.visible_fmea_source(db, scope, source.fmea_id)
                    else:
                        from app.models.fmea import FMEADocument
                        from app.core.permissions import Module, PermissionLevel
                        levels, factories, lines = access
                        current = (await db.execute(select(FMEADocument.factory_id,
                            FMEADocument.product_line_code).where(FMEADocument.fmea_id == source.fmea_id))).one_or_none()
                        source_cache[source.fmea_id] = current if (
                            levels.get(Module.FMEA, PermissionLevel.NONE) >= PermissionLevel.VIEW
                            and current is not None
                            and (factories.accessible_factory_ids is None or current.factory_id in factories.accessible_factory_ids)
                            and (lines.mode == 'ALL' or current.product_line_code in (lines.codes or []))) else None
                except SourceUnavailable:
                    source_cache[source.fmea_id] = None
            current = source_cache[source.fmea_id]
            if (current is None or current.factory_id != source.factory_id
                    or current.product_line_code != source.product_line_code):
                allowed = False
                break
        if allowed:
            visible.append(row)
            source_sets[row.proposal_id] = all_sources
    return target, visible, source_sets


async def _basis_current(db, scope, target, row, sources):
    """Freshness is separate from historical read authority, never a write grant."""
    from app.config import settings
    from app.services.capa_d4_provenance import current_field_namespace, field_hmac, verification_version

    binding = db.info.get('tenant_binding')
    if binding is None:
        return False
    with db.no_autoflush:
        proof = await db.scalar(select(CapaD4RootCauseSourceProof).where(
            CapaD4RootCauseSourceProof.proof_id == row.proof_id).execution_options(populate_existing=True))
        # Match D4's semantic evidence contract, without its runtime-only
        # development/profile admission gates. Historical read authority above
        # deliberately does not depend on these current-evidence conditions.
        active = (await db.scalars(select(CapaD4RootCauseSourceProof.proof_id).where(
            CapaD4RootCauseSourceProof.report_id == target.report_id,
            CapaD4RootCauseSourceProof.status == 'active',
            CapaD4RootCauseSourceProof.invalidated_at.is_(None),
            CapaD4RootCauseSourceProof.tenant_generation == binding.generation))).all()
        latest = await db.scalar(select(CapaD4RootCauseRevision.revision_id).where(
            CapaD4RootCauseRevision.report_id == target.report_id).order_by(
            CapaD4RootCauseRevision.revision_no.desc()).limit(1))
        root, linked_fmea_id = (await db.execute(select(CAPAEightD.d4_root_cause,
            CAPAEightD.fmea_ref_id).where(CAPAEightD.report_id == target.report_id))).one()
        expected_source = {'fmea_id': str(proof.fmea_id), 'cause_node_id': proof.cause_node_id}
        verification = (await db.execute(select(CapaRootCauseVerification.conclusion,
            CapaRootCauseVerification.updated_at,
            (CapaRootCauseVerification.root_cause_text == (root or '').strip()).label('text_matches'),
            (CapaRootCauseVerification.source_ref == func.cast(expected_source, JSONB)).label('source_matches'))
            .where(CapaRootCauseVerification.verification_id == proof.verification_id,
                CapaRootCauseVerification.capa_id == target.report_id,
                CapaRootCauseVerification.factory_id == target.factory_id))).one_or_none()
    if (list(active) != [row.proof_id] or latest != row.revision_id
            or linked_fmea_id is None or linked_fmea_id != proof.fmea_id
            or proof.source_projection_id != fmea_agent_sources.FAILURE_CAUSE_REFERENCE.source_projection_id
            or proof.declaration_kind != 'employee_declared_complete_v1'
            or not isinstance(root, str) or not root.strip()
            or verification is None or verification.conclusion != 'passed'
            or verification.text_matches is not True or verification.source_matches is not True
            or proof.verification_version != verification_version(proof.verification_id,
                verification.conclusion, verification.updated_at)
            or proof.field_hmac != field_hmac(settings.SECRET_KEY.encode(),
                await current_field_namespace(db), target.report_id, root)):
        return False
    for source in sources:
        try:
            current = await fmea_agent_sources.visible_fmea_source(db, scope, source.fmea_id)
            if await fmea_agent_sources.failure_cause_version(db, current, source.node_id) != source.node_hmac:
                return False
        except SourceUnavailable:
            return False
    return True


def _page(rows, page, page_size):
    if page < 1 or not 1 <= page_size <= 200:
        raise ValueError('Invalid pagination')
    return rows[(page - 1) * page_size:page * page_size]


async def _read(db, scope, report_id, *, kind, page=1, page_size=20, item_id=None):
    target, rows, sources = await _visible_metadata(db, scope, report_id)
    initial_signature = _signature(rows, sources)
    if kind == 'measures':
        with db.no_autoflush:
            measures = (await db.execute(select(CapaD5Measure.measure_id, CapaD5Measure.proposal_id).where(
                CapaD5Measure.proposal_id.in_([r.proposal_id for r in rows if r.state == 'adopted'])))).all() if rows else []
        by_proposal = {m.proposal_id: m.measure_id for m in measures}
        rows = [r for r in rows if r.proposal_id in by_proposal]
        keys = {r.proposal_id: by_proposal[r.proposal_id] for r in rows}
    else:
        keys = {r.proposal_id: r.proposal_id for r in rows}
    total = len(rows)
    selected = [r for r in rows if keys[r.proposal_id] == item_id] if item_id is not None else _page(rows, page, page_size)
    if item_id is not None and not selected:
        raise LookupError('D5 item unavailable')
    items = []
    for row in selected:
        with db.no_autoflush:
            if kind == 'measures':
                body = (await db.execute(select(CapaD5Measure.measure_id, CapaD5Measure.proposal_id,
                    CapaD5Measure.final_text, CapaD5Measure.adopted_by, CapaD5Measure.adopted_at).where(
                    CapaD5Measure.measure_id == keys[row.proposal_id]))).one()
                items.append(D5MeasureItem(**body._mapping))
            else:
                original_text = await db.scalar(select(CapaD5Proposal.original_text).where(
                    CapaD5Proposal.proposal_id == row.proposal_id))
                items.append(D5ProposalItem(proposal_id=row.proposal_id, original_text=original_text,
                    state=row.state, created_at=row.created_at,
                    basis_current=await _basis_current(db, scope, target, row, sources[row.proposal_id])))
    legacy = None
    if kind == 'measures' and item_id is None:
        with db.no_autoflush:
            legacy = await db.scalar(select(CAPAEightD.d5_correction).where(CAPAEightD.report_id == report_id))
    # A page or detail is not a retained authority token. Recheck after loading
    # bodies as well; any changed membership requires a fresh projection.
    latest_target, latest_rows, latest_sources = await _visible_metadata(db, scope, report_id)
    if (latest_target.factory_id != target.factory_id
            or latest_target.product_line_code != target.product_line_code
            or _signature(latest_rows, latest_sources) != initial_signature):
        raise PermissionError('D5 view changed; refresh required')
    if item_id is not None:
        return items[0]
    if kind == 'measures':
        return D5MeasureList(legacy_text=legacy, items=items, total=total, page=page, page_size=page_size)
    return D5ProposalList(items=items, total=total, page=page, page_size=page_size)


def _signature(rows, sources):
    return [(tuple(row), sorted((str(s.source_id), s.projection_id, str(s.factory_id),
        s.product_line_code, str(s.fmea_id), s.node_id, s.node_hmac)
        for s in sources[row.proposal_id])) for row in rows]


async def read_d5_proposals(db, scope, report_id, *, page=1, page_size=20):
    return await _read(db, scope, report_id, kind='proposals', page=page, page_size=page_size)


async def read_d5_measures(db, scope, report_id, *, page=1, page_size=20):
    return await _read(db, scope, report_id, kind='measures', page=page, page_size=page_size)


async def read_d5_proposal(db, scope, report_id, proposal_id):
    return await _read(db, scope, report_id, kind='proposals', item_id=proposal_id)


async def read_d5_measure(db, scope, report_id, measure_id):
    return await _read(db, scope, report_id, kind='measures', item_id=measure_id)


async def _formal_ids(db, report_id):
    # Compare against the raw persisted set. An invalid association is a reason
    # to refuse complete material, never permission to silently omit a measure.
    with db.no_autoflush:
        return (await db.execute(select(CapaD5Measure.measure_id, CapaD5Measure.proposal_id)
            .join(CapaD5Proposal, CapaD5Proposal.proposal_id == CapaD5Measure.proposal_id)
            .where(CapaD5Proposal.report_id == report_id).order_by(CapaD5Measure.measure_id))).all()


async def require_legacy_d5_only(db, report_id):
    """Flows without item ACL/recipient support cannot claim complete material."""
    if await _formal_ids(db, report_id):
        raise PermissionError('D5_FULL_MATERIAL_UNAVAILABLE')


async def full_d5_material(db, capa, *, scope=None, access=None):
    """Controlled, complete internal snapshot; never an employee list response.

    The caller provides live authority and holds the CAPA parent for decisions.
    Source scope may include other product lines, unlike legacy D4 references.
    """
    formal = await _formal_ids(db, capa.report_id)
    if not formal:
        return []
    if scope is not None:
        access = await current_capa_access(db, scope)
    if access is None:
        raise PermissionError('D5_FULL_MATERIAL_UNAVAILABLE')
    _, rows, sources = await _visible_metadata(db, scope, capa.report_id, access)
    by_id = {row.proposal_id: row for row in rows if row.state == 'adopted'}
    if any(item.proposal_id not in by_id for item in formal):
        raise PermissionError('D5_FULL_MATERIAL_UNAVAILABLE')
    signature = _signature(rows, sources)
    import hashlib
    import hmac
    from app.config import settings
    material = []
    for item in formal:
        row = by_id[item.proposal_id]
        body = (await db.execute(select(CapaD5Measure.final_text, CapaD5Measure.adopted_by,
            CapaD5Measure.adopted_at).where(CapaD5Measure.measure_id == item.measure_id))).one()
        material.append(dict(measure_id=str(item.measure_id), proposal_id=str(item.proposal_id),
            final_text=body.final_text, adopted_by=str(body.adopted_by), adopted_at=body.adopted_at.isoformat(),
            text_version=hmac.new(settings.SECRET_KEY.encode(), b'openqms.d5.measure.v1\0'
                + item.measure_id.bytes + body.final_text.encode(), hashlib.sha256).hexdigest(),
            revision_id=str(row.revision_id), proof_id=str(row.proof_id),
            sources=sorted([dict(source_id=str(s.source_id), projection_id=s.projection_id,
                factory_id=str(s.factory_id), product_line_code=s.product_line_code,
                fmea_id=str(s.fmea_id), node_id=s.node_id, node_hmac=s.node_hmac)
                for s in sources[item.proposal_id]], key=lambda s: s['source_id'])))
    if scope is not None:
        access = await current_capa_access(db, scope)
    _, latest, latest_sources = await _visible_metadata(db, scope, capa.report_id, access)
    if signature != _signature(latest, latest_sources) or formal != await _formal_ids(db, capa.report_id):
        raise PermissionError('D5_FULL_MATERIAL_UNAVAILABLE')
    return material


async def has_formal_d5(db, capa):
    """Business completeness is independent of an employee's filtered view."""
    if (capa.d5_correction or '').strip():
        return True
    from types import SimpleNamespace
    from app.core.permissions import Module, PermissionLevel
    # Qualification is server-owned and does not use an employee's projected
    # item count. Association/source integrity still applies to actual measures.
    business_access = ({Module.FMEA: PermissionLevel.VIEW},
        SimpleNamespace(accessible_factory_ids=None), SimpleNamespace(mode='ALL'))
    _, rows, _ = await _visible_metadata(db, None, capa.report_id, business_access)
    valid = {row.proposal_id for row in rows if row.state == 'adopted'}
    return any(item.proposal_id in valid for item in await _formal_ids(db, capa.report_id))


def complete_d5_text(legacy, material):
    if not material:
        return legacy
    return '\n'.join([value for value in [legacy, *(row['final_text'] for row in material)] if value])
