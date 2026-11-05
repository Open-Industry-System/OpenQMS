"""Task 3 review I1-I4: committed source, receipt and post-assembly gates."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import delete, text, update

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.services.capa_review_guard import OutcomeReviewConflict
from app.services.version_service import create_fmea_version
from tests.capa.test_capa_outcome_review import read
from tests.capa.test_capa_outcome_sources import approved_receipt, bind_sources

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize('node_id', [None, '', 0, False, [], {}])
async def test_i1_exact_verification_source_requires_nonempty_string_cause(review_case, review_sources, node_id):
    await bind_sources(review_case, review_sources, explicit=True)
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
            review_case.verification_id).values(source_ref={'fmea_id': str(review_sources.fmea_id), 'cause_node_id': node_id}))
        await db.commit()
    before = await review_case.snapshot()
    with pytest.raises(PermissionError, match='CAPA_OUTCOME_REVIEW_ACCESS_DENIED'):
        await read(review_case)
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['control_plan_alias', 'missing_fmea', 'missing_planning',
    'duplicate', 'extra_envelope', 'missing_decision', 'wrong_decision', 'extra_source_field', 'wrong_contract'])
async def test_i3_valid_hmac_is_not_enough_for_noncontract_or_incomplete_receipt(review_case, review_sources, damage):
    await bind_sources(review_case, review_sources, explicit=True)
    pending, original = await approved_receipt(review_case)
    assert (await read(review_case)).binding_status == 'verified'
    receipt = deepcopy(original)
    if damage == 'control_plan_alias':
        next(v for v in receipt['source_versions'] if v['module'] == 'planning')['module'] = 'control_plan'
    elif damage in {'missing_fmea', 'missing_planning'}:
        module = 'fmea' if damage == 'missing_fmea' else 'planning'
        receipt['source_versions'] = [v for v in receipt['source_versions'] if v['module'] != module]
    elif damage == 'duplicate':
        receipt['source_versions'].append(deepcopy(receipt['source_versions'][0]))
    elif damage == 'extra_envelope':
        receipt['unapproved_key'] = True
    elif damage == 'missing_decision':
        receipt.pop('doc_decision_id')
    elif damage == 'wrong_decision':
        receipt['doc_decision_id'] = str(uuid4())
    elif damage == 'extra_source_field':
        receipt['source_versions'][0]['unapproved_key'] = True
    else:
        receipt['contract'] = 'other.contract'
    # Only representation/identity metadata changes; leave the genuine signed
    # material revision intact. Do not generate a new HMAC for the damaged data.
    assert receipt['revision'] == original['revision'] == pending.revision
    async with review_case.session_factory() as db:
        await db.execute(update(AuditLog).where(AuditLog.record_id == review_case.report_id,
            AuditLog.action == 'D8_APPROVED').values(changed_fields={'outcome_review': receipt}))
        await db.commit()
    before = await review_case.snapshot()
    if damage in {'control_plan_alias', 'extra_source_field'}:
        with pytest.raises(PermissionError, match='CAPA_OUTCOME_REVIEW_ACCESS_DENIED'):
            await read(review_case)
    else:
        result = await read(review_case)
        assert result.binding_status == 'unverifiable'
        assert result.revision == original['revision']
        assert result.status == 'D8_CLOSURE'
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
async def test_i4_legacy_round_stable_on_maintenance_but_material_sources_and_resubmit_invalidate(review_case, review_sources):
    async with review_case.session_factory() as db:
        (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
        await db.execute(delete(AuditLog).where(AuditLog.record_id == review_case.report_id,
            AuditLog.action == 'TRANSITION'))
        await db.commit()
    before = await review_case.snapshot()
    initial = await read(review_case)
    expected = uuid5(NAMESPACE_URL, f'capa.outcome-review.legacy:public:{review_case.report_id}')
    assert initial.review_round_id == expected
    assert before == await review_case.snapshot()
    async with review_case.session_factory() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(
            title='ordinary title maintenance', updated_at=datetime(2030, 1, 1, tzinfo=UTC)))
        await db.commit()
    maintained = await read(review_case)
    assert maintained.review_round_id == initial.review_round_id
    assert maintained.revision == initial.revision
    async with review_case.session_factory() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(d5_correction='actual correction change'))
        await db.commit()
    core = await read(review_case)
    assert core.review_round_id == expected
    assert core.revision != maintained.revision
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
            review_case.verification_id).values(result='actual new verification result'))
        await db.commit()
    child = await read(review_case)
    assert child.review_round_id == expected
    assert child.revision != core.revision
    async with review_case.session_factory() as db:
        fmea = await db.get(FMEADocument, review_sources.fmea_id)
        graph = deepcopy(fmea.graph_data)
        graph['nodes'][0]['properties']['name'] = 'actual controlled cause content change'
        fmea.graph_data = graph
        await db.commit()
        await create_fmea_version(db, fmea, 'edit', 'actual controlled source evolution', review_case.actor_id)
    source = await read(review_case)
    assert source.review_round_id == expected
    assert source.revision != child.revision
    new_round = uuid4()
    async with review_case.session_factory() as db:
        db.add(AuditLog(log_id=new_round, table_name='capa_eightd', record_id=review_case.report_id,
            factory_id=review_case.factory_id, action='TRANSITION', operated_by=review_case.actor_id,
            changed_fields={'old_status': 'D8_GATE_PENDING', 'new_status': 'D8_APPROVAL_PENDING'}))
        await db.commit()
    resubmitted = await read(review_case)
    assert resubmitted.review_round_id == new_round
    assert resubmitted.revision != source.revision


@pytest.mark.asyncio
@pytest.mark.parametrize('writer_kind', ['verification', 'supplement', 'fmea_version', 'cp_version'])
async def test_i2_read_fence_serializes_actual_parent_and_source_writer_protocols(review_case, review_sources, monkeypatch, writer_kind):
    from sqlalchemy import event
    from app.core.permissions import PermissionLevel
    from app.models.control_plan import ControlPlan
    from app.services import capa_outcome_review as service
    from app.services.capa_review_guard import lock_current_material_write
    from app.services.version_service import create_cp_version
    from tests.capa.outcome_review_support import wait_for_pg_blocker

    # Gate-bound CP plus a pending explicit FMEA exercises both source locks,
    # including their control_plan-before-fmea writer order.
    await bind_sources(review_case, review_sources, modules=('planning',), explicit=True)
    if writer_kind == 'supplement':
        await approved_receipt(review_case)
    initial = await read(review_case)
    original = service._lock_read_fence
    locked, resume, writer_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids, lock_sql = {}, []
    async def paused(db, *args, **kwargs):
        value = await original(db, *args, **kwargs)
        pids['reader'] = await db.scalar(text('SELECT pg_backend_pid()'))
        locked.set()
        await resume.wait()
        return value
    monkeypatch.setattr(service, '_lock_read_fence', paused)
    def record(conn, cursor, statement, parameters, context, executemany):
        if 'FOR SHARE' in statement:
            lock_sql.append(statement)
    engine = review_case.session_factory.kw['bind']
    event.listen(engine.sync_engine, 'before_cursor_execute', record)

    async def write():
        async with review_case.session_factory() as db:
            pids['writer'] = await db.scalar(text('SELECT pg_backend_pid()'))
            writer_started.set()
            if writer_kind in {'verification', 'supplement'}:
                fields = {'d8_closure'} if writer_kind == 'supplement' else None
                await lock_current_material_write(db, await review_case.report(db), review_case.actor_id,
                    PermissionLevel.EDIT, fields)
                if writer_kind == 'verification':
                    await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
                        review_case.verification_id).values(result='writer committed after read fence'))
                else:
                    await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(
                        d8_closure='writer supplement after read fence'))
                await db.commit()
            elif writer_kind == 'fmea_version':
                fmea = await db.get(FMEADocument, review_sources.fmea_id)
                await create_fmea_version(db, fmea, 'edit', 'writer after shared source fence', review_case.actor_id)
            else:
                cp = await db.get(ControlPlan, review_sources.cp_id)
                await create_cp_version(db, cp, 'edit', 'writer after shared source fence', review_case.actor_id)

    reader, writer = asyncio.create_task(read(review_case)), None
    try:
        await asyncio.wait_for(locked.wait(), 5)
        writer = asyncio.create_task(write())
        await asyncio.wait_for(writer_started.wait(), 5)
        await wait_for_pg_blocker(review_case, pids['writer'], pids['reader'])
        resume.set()
        result = await asyncio.wait_for(reader, 5)
        await asyncio.wait_for(writer, 5)
        assert result.model_dump(mode='json') == initial.model_dump(mode='json')
        assert len(lock_sql) == 3
        assert 'FROM capa_eightd' in lock_sql[0]
        assert 'FROM control_plans' in lock_sql[1]
        assert 'FROM fmea_documents' in lock_sql[2]
    finally:
        resume.set()
        for task in [reader, writer]:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        event.remove(engine.sync_engine, 'before_cursor_execute', record)
    current = await read(review_case)
    if writer_kind == 'verification':
        assert current.verifications[0].result == 'writer committed after read fence'
        assert current.revision != initial.revision
    elif writer_kind == 'supplement':
        assert current.supplement.text == 'writer supplement after read fence'
        assert current.revision == initial.revision
    elif writer_kind == 'fmea_version':
        assert current.revision != initial.revision
    else:
        assert current.revision == initial.revision  # old gate CP version remains bound



@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['verification', 'supplement', 'supplement_audit', 'decision_metadata', 'source_version'])
async def test_i2_commit_after_request_dto_before_last_gate_cannot_return_old_response(review_case, review_sources, monkeypatch, change):
    from app.services import capa_outcome_review as service
    if change == 'source_version':
        async with review_case.session_factory() as db:
            (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
            await db.commit()
    elif change != 'verification':
        await approved_receipt(review_case)
    initial = await read(review_case)
    original = service._dto
    assembled, resume = asyncio.Event(), asyncio.Event()
    async def paused(db, *args, **kwargs):
        value = await original(db, *args, **kwargs)
        if await db.scalar(text('SHOW transaction_read_only')) == 'off' and not assembled.is_set():
            assembled.set()
            await resume.wait()
        return value
    monkeypatch.setattr(service, '_dto', paused)
    task = asyncio.create_task(read(review_case))
    try:
        await asyncio.wait_for(assembled.wait(), 5)
        async with review_case.session_factory() as writer:
            if change == 'verification':
                await writer.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
                    review_case.verification_id).values(result='committed after request DTO assembly'))
            elif change == 'supplement':
                await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(
                    d8_closure='new unreviewed supplement after DTO assembly'))
            elif change == 'source_version':
                fmea = await writer.get(FMEADocument, review_sources.fmea_id)
                await create_fmea_version(writer, fmea, 'edit', 'source committed after request DTO assembly', review_case.actor_id)
            elif change == 'supplement_audit':
                writer.add(AuditLog(table_name='capa_eightd', record_id=review_case.report_id,
                    factory_id=review_case.factory_id, action='UPDATE', changed_fields={'d8_closure': None},
                    operated_by=review_case.actor_id, operated_at=datetime.now(UTC)+timedelta(seconds=1)))
            else:
                await writer.execute(update(AuditLog).where(AuditLog.record_id == review_case.report_id,
                    AuditLog.action == 'D8_APPROVED').values(operated_at=datetime.now(UTC)+timedelta(seconds=1)))
            await writer.commit()
        externally_committed = await review_case.snapshot()
        resume.set()
        with pytest.raises(OutcomeReviewConflict):
            await asyncio.wait_for(task, 5)
        assert externally_committed == await review_case.snapshot()
        current = await read(review_case)
        if change == 'verification':
            assert current.revision != initial.revision
            assert current.verifications[0].result == 'committed after request DTO assembly'
        elif change == 'source_version':
            assert current.revision != initial.revision
            assert current.documents[0].version_id != initial.documents[0].version_id
        else:
            assert current.revision == initial.revision
            assert current.model_dump(mode='json') != initial.model_dump(mode='json')
    finally:
        resume.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
