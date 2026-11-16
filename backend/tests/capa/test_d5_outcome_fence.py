"""D5 material belongs to the existing outcome revision and source fences."""
import pytest
from app.services.capa_outcome_review import collect_outcome_material, outcome_revision
from app.services.capa_current_access import current_capa_access
from tests.capa.test_d5_measure_visibility import d5_case
from tests.services.agent_runtime.conftest import committed_runtime
from tests.capa.test_capa_outcome_decision import decision_provider

pytestmark = pytest.mark.requires_db


async def _pending_source_valid_proposal(c):
    """R5 initial fixture: pending sibling with the established current basis."""
    from uuid import uuid4
    from sqlalchemy import select, update
    from app.models.agent_d5_command import AgentD5Command
    from app.models.capa_d5_proposal import CapaD5Proposal, CapaD5ProposalSource
    from app.models.role import RolePermission
    original = await c.db.get(CapaD5Proposal, c.proposals[0])
    sources = list((await c.db.scalars(select(CapaD5ProposalSource).where(
        CapaD5ProposalSource.proposal_id == original.proposal_id))).all())
    proposal_id, command_id = uuid4(), uuid4()
    c.db.add(AgentD5Command(command_id=command_id, task_id=c.task_id, run_id=c.run_id,
        proposal_id=proposal_id, command_key='outcome-membership', operation='save',
        request_hmac='b'*64, sequence=3))
    await c.db.flush()
    c.db.add(CapaD5Proposal(proposal_id=proposal_id, report_id=c.report.report_id,
        task_id=c.task_id, original_text='additional pending fixture', state='pending',
        revision_id=original.revision_id, proof_id=original.proof_id,
        command_id=command_id, created_by=c.user_id))
    await c.db.flush()
    for source in sources:
        c.db.add(CapaD5ProposalSource(proposal_id=proposal_id, projection_id=source.projection_id,
            factory_id=source.factory_id, product_line_code=source.product_line_code,
            fmea_id=source.fmea_id, node_id=source.node_id, node_hmac=source.node_hmac))
    await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.actors[2].role_id,
        RolePermission.module == 'capa').values(permission_level=3))
    await c.db.commit()
    return proposal_id

@pytest.mark.asyncio
async def test_outcome_refuses_partial_source_authority_before_d5_body(d5_case):
    c = d5_case
    c.db.info['outcome_read_access'] = await current_capa_access(c.db, c.actors[1])
    with pytest.raises(PermissionError):
        await collect_outcome_material(c.db, c.report)

@pytest.mark.asyncio
async def test_d5_snapshot_is_stable_and_versioned(d5_case):
    from app.services.capa_d5_measures import full_d5_material
    from app.services.capa_outcome_review import outcome_revision
    from app.models.capa_d5_proposal import CapaD5Measure, CapaD5ProposalSource
    from app.models.audit import AuditLog
    from app.services.capa_d5_proposals import staff_action
    from sqlalchemy import update, select
    c = d5_case
    pending = await _pending_source_valid_proposal(c)
    before = await full_d5_material(c.db, c.report, scope=c.actors[2])
    assert before == await full_d5_material(c.db, c.report, scope=c.actors[2])
    # The actual material mutation is a legal D5 adoption, including its audit;
    # original adoption text remains immutable. Text corrections are Task 6.
    await staff_action(c.db, c.actors[2], c.report.report_id, pending,
        operation='adopt', operation_key='outcome-membership', value='NEW SENTINEL')
    assert await c.db.scalar(select(AuditLog.log_id).where(
        AuditLog.record_id == pending, AuditLog.action == 'D5_PROPOSAL_ADOPT')) is not None
    assert await c.db.scalar(select(CapaD5Measure.final_text).where(
        CapaD5Measure.measure_id == c.measures[0])) == 'secret final 1'
    after = await full_d5_material(c.db, c.report, scope=c.actors[2])
    assert outcome_revision({'d5_measures': before}) != outcome_revision({'d5_measures': after})
    await c.db.execute(update(CapaD5ProposalSource).where(CapaD5ProposalSource.proposal_id == c.proposals[1], CapaD5ProposalSource.fmea_id == c.docs[1].fmea_id).values(node_hmac='a'*64))
    await c.db.commit()
    changed = await full_d5_material(c.db, c.report, scope=c.actors[2])
    assert outcome_revision({'d5_measures': changed}) != outcome_revision({'d5_measures': after})


async def outcome_ready(c):
    from datetime import datetime, UTC
    from app.services.version_service import create_fmea_version
    from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
    for doc in c.docs:
        await create_fmea_version(c.db, doc, 'update', 'fixture', c.user_id)
    c.report.status = 'D8_APPROVAL_PENDING'
    c.report.d5_correction = None
    c.report.d6_verification = 'verified'
    analysis = CapaDocgAnalysis(capa_id=c.report.report_id, factory_id=c.report.factory_id,
        status='done', is_current=True, affected_docs=[], generated_by=c.user_id,
        llm_available=True, model='fixture', analysis_input_hash='f'*64, completed_at=datetime.now(UTC))
    c.db.add(analysis)
    await c.db.flush()
    from datetime import datetime, UTC
    c.db.add(CapaDocgDecision(analysis_id=analysis.analysis_id, factory_id=c.report.factory_id,
        revision=1, decision='passed', no_affected_confirmed=True, version_snapshot=[],
        decided_by=c.user_id, decided_at=datetime.now(UTC)))
    from app.services.capa_d5_measures import full_d5_material
    from app.services.capa_doc_gate_service import _compute_input_hash, _build_allowlist
    c.report._d5_material = await full_d5_material(c.db, c.report, scope=c.actors[2])
    analysis.analysis_input_hash = _compute_input_hash(c.report, await _build_allowlist(c.db, c.report))
    await c.db.commit()
    return analysis


async def prepare_d5_manual_round(c):
    """Real local service re-entry from a controlled historical model round."""
    from types import SimpleNamespace
    from app.models.capa import CAPAEightD
    from tests.capa.test_capa_outcome_decision import prepare_restricted_manual_round
    report_id = c.report.report_id
    async def report(db):
        return await db.get(CAPAEightD, report_id, populate_existing=True)
    async def scope(db):
        return c.actors[2]
    case = SimpleNamespace(report_id=report_id, actor_id=c.actors[2].user.user_id,
        session_factory=lambda: c.factory(binding=c.binding), report=report, scope=scope)
    await c.db.rollback()
    await prepare_restricted_manual_round(case)
    c.report = await report(c.db)


@pytest.mark.asyncio
async def test_actual_outcome_reader_binds_all_measures_and_sources(d5_case):
    from app.services.capa_outcome_review import read_outcome_review
    c = d5_case
    await outcome_ready(c)
    result = await read_outcome_review(c.db, c.actors[2], c.report.report_id)
    assert result.core.d5_correction is None
    assert {row.final_text for row in result.d5_measures} == {'secret final 1', 'secret final 2'}
    assert len(next(row for row in result.d5_measures if row.final_text == 'secret final 2').sources) == 2
    assert {v.object_id for v in result.documents} == {d.fmea_id for d in c.docs}
    with pytest.raises(PermissionError):
        await read_outcome_review(c.db, c.actors[1], c.report.report_id)


@pytest.mark.asyncio
async def test_source_reference_guard_includes_secondary_d5_source(d5_case):
    from app.services.capa_review_source_guard import _source_capa_ids, lock_source_capa_references
    from app.services.capa_review_guard import ReviewedContentLocked
    c = d5_case
    assert c.report.report_id in await _source_capa_ids(c.db, 'fmea', c.docs[1].fmea_id)
    c.report.status = 'D8_CLOSURE'
    await c.db.commit()
    with pytest.raises(ReviewedContentLocked):
        await lock_source_capa_references(c.db, 'fmea', c.docs[1].fmea_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['ordinary-text', 'secondary-acl'])
async def test_waiting_decision_rechecks_complete_d5_material(d5_case, change):
    import asyncio
    from types import SimpleNamespace
    from sqlalchemy import select, update, text
    from app.models.role import RolePermission, UserProductLine
    from app.services.capa_review_guard import lock_capa_parent, OutcomeReviewConflict
    from app.services.capa_service import advance_capa, update_capa
    from app.services.capa_outcome_review import read_outcome_review
    from app.schemas.capa import AdvanceRequest
    c = d5_case
    await outcome_ready(c)
    await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.actors[2].role_id,
        RolePermission.module == 'capa').values(permission_level=4))
    await c.db.commit()
    seen = await read_outcome_review(c.db, c.actors[2], c.report.report_id)
    report_id, line_b = c.report.report_id, c.line_b.code
    await c.db.rollback()
    async with c.factory(binding=c.binding) as writer, c.factory(binding=c.binding) as decider:
        await lock_capa_parent(writer, report_id)
        cached = await decider.get(type(c.report), report_id)
        waiter_pid = await decider.scalar(text('SELECT pg_backend_pid()'))
        task = asyncio.create_task(advance_capa(decider, cached, c.actors[2].user.user_id,
            AdvanceRequest(target_state='D7_PREVENTION', reject_reason='return',
                expected_outcome_revision=seen.revision, expected_review_round_id=seen.review_round_id)))
        try:
            for _ in range(200):
                blockers = await writer.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))'), {'pid': waiter_pid})
                if blockers:
                    break
                await asyncio.sleep(.01)
            else:
                pytest.fail('decision did not wait on the actual CAPA parent lock')
            if change == 'ordinary-text':
                # Keep the exact stale complete-material expectation while
                # using a currently legal ordinary material write. Restricted
                # measure TEXT correction freshness is exercised in Task 6.
                await update_capa(writer, await writer.get(type(c.report), report_id),
                    {'d5_correction': 'ordinary material changed while waiting'}, c.actors[2].user.user_id)
            else:
                from sqlalchemy import delete
                await writer.execute(delete(UserProductLine).where(UserProductLine.user_id == c.actors[2].user.user_id,
                    UserProductLine.product_line_code == line_b))
            await writer.commit()
            with pytest.raises((OutcomeReviewConflict, PermissionError)):
                await asyncio.wait_for(task, 5)
            await decider.rollback()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await writer.rollback()


@pytest.mark.asyncio
async def test_original_d5_adoption_refuses_in_place_text_updates(d5_case):
    from sqlalchemy import update, select
    from sqlalchemy.exc import DBAPIError
    from app.models.capa_d5_proposal import CapaD5Measure
    c = d5_case
    with pytest.raises(DBAPIError):
        async with c.db.begin_nested():
            await c.db.execute(update(CapaD5Measure).where(
                CapaD5Measure.measure_id == c.measures[0]).values(final_text='forbidden rewrite'))
    async with c.factory(binding=c.binding) as check:
        assert await check.scalar(select(CapaD5Measure.final_text).where(
            CapaD5Measure.measure_id == c.measures[0])) == 'secret final 1'


@pytest.mark.parametrize('state', ['D8_CLOSURE', 'ARCHIVED'])
def test_new_d5_material_names_use_same_terminal_guard(state):
    from types import SimpleNamespace
    from app.services.capa_review_guard import assert_reviewed_material_mutable, ReviewedContentLocked
    with pytest.raises(ReviewedContentLocked):
        assert_reviewed_material_mutable(SimpleNamespace(status=state), {'d5_measures'})


@pytest.mark.asyncio
async def test_restricted_only_full_material_can_be_approved_and_archived(d5_case, decision_provider):
    from sqlalchemy import update
    from app.models.role import RolePermission
    from app.services.capa_outcome_review import read_outcome_review
    from app.services.capa_service import advance_capa
    from app.schemas.capa import AdvanceRequest
    c = d5_case
    await outcome_ready(c)
    await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.actors[2].role_id,
        RolePermission.module == 'capa').values(permission_level=4))
    await c.db.commit()
    await prepare_d5_manual_round(c)
    seen = await read_outcome_review(c.db, c.actors[2], c.report.report_id)
    result = await advance_capa(c.db, c.report, c.actors[2].user.user_id,
        AdvanceRequest(target_state='D8_CLOSURE', expected_outcome_revision=seen.revision,
            expected_review_round_id=seen.review_round_id))
    assert result.status == 'D8_CLOSURE' and result.d5_correction is None
    closed = await read_outcome_review(c.db, c.actors[2], result.report_id)
    assert closed.binding_status == 'verified' and 'secret final 2' in {row.final_text for row in closed.d5_measures}
    result = await advance_capa(c.db, result, c.actors[2].user.user_id)
    assert result.status == 'ARCHIVED'
    assert (await read_outcome_review(c.db, c.actors[2], result.report_id)).binding_status == 'verified'


@pytest.mark.asyncio
async def test_human_gate_rechecks_secondary_acl_after_analysis_lock_wait(d5_case):
    import asyncio
    from sqlalchemy import update, select, text, delete
    from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
    from app.models.role import RolePermission, UserProductLine
    from app.services.capa_doc_gate_service import confirm_no_affected
    c = d5_case
    analysis = await outcome_ready(c)
    c.report.status = 'D8_GATE_PENDING'
    await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.actors[2].role_id,
        RolePermission.module == 'capa').values(permission_level=4))
    await c.db.commit()
    report_id, analysis_id, extra_line = c.report.report_id, analysis.analysis_id, c.line_b.code
    async with c.factory(binding=c.binding) as writer, c.factory(binding=c.binding) as gate:
        await writer.execute(select(CapaDocgAnalysis.analysis_id).where(
            CapaDocgAnalysis.analysis_id == analysis_id).with_for_update())
        cached = await gate.get(type(c.report), report_id)
        waiter_pid = await gate.scalar(text('SELECT pg_backend_pid()'))
        task = asyncio.create_task(confirm_no_affected(gate, cached, c.actors[2].user.user_id))
        try:
            for _ in range(200):
                if await writer.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))'), {'pid': waiter_pid}):
                    break
                await asyncio.sleep(.01)
            else:
                pytest.fail('human gate did not wait on the actual analysis row')
            await writer.execute(delete(UserProductLine).where(UserProductLine.user_id == c.actors[2].user.user_id,
                UserProductLine.product_line_code == extra_line))
            await writer.commit()
            with pytest.raises(PermissionError):
                await asyncio.wait_for(task, 5)
            await gate.rollback()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await writer.rollback()
    async with c.factory(binding=c.binding) as check:
        assert await check.scalar(select(CapaDocgDecision.revision).where(
            CapaDocgDecision.analysis_id == analysis_id).order_by(CapaDocgDecision.revision.desc()).limit(1)) == 1
