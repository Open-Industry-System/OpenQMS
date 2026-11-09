"""RR/RO boundaries, independent authority gate, and bounded complete reads."""
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.services.capa_review_guard import OutcomeReviewConflict, OutcomeReviewLimit
from tests.capa.test_capa_outcome_review import read
from tests.capa.test_capa_outcome_sources import bind_sources

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize('location', ['core', 'result', 'evidence', 'source_ref', 'gate', 'supplement'])
async def test_real_8mib_preflight_does_not_load_oversized_body(review_case, location):
    from app.models.capa_doc_gate import CapaDocgDecision
    from app.services.capa_outcome_review import MAX_OUTCOME_REVIEW_BYTES
    assert MAX_OUTCOME_REVIEW_BYTES == 8 * 1024 * 1024
    oversized = '界' * (MAX_OUTCOME_REVIEW_BYTES // 3 + 1)
    async with review_case.session_factory() as db:
        if location in {'core', 'supplement'}:
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(
                **{'d4_root_cause' if location == 'core' else 'd8_closure': oversized}))
        elif location == 'gate':
            await db.execute(update(CapaDocgDecision).where(CapaDocgDecision.analysis_id ==
                review_case.owned_ids['analysis_id']).values(version_snapshot=[{'untrusted': oversized}]))
        else:
            value = oversized if location == 'result' else [{'name': oversized}] if location == 'evidence' else {'bad': oversized}
            field = 'evidence_attachments' if location == 'evidence' else location
            await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
                review_case.verification_id).values(**{field: value}))
        await db.commit()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    engine = review_case.session_factory.kw['bind']
    event.listen(engine.sync_engine, 'before_cursor_execute', record)
    try:
        with pytest.raises(OutcomeReviewLimit):
            await read(review_case)
    finally:
        event.remove(engine.sync_engine, 'before_cursor_execute', record)
    body_column = {'core': 'capa_eightd.d4_root_cause', 'supplement': 'capa_eightd.d8_closure',
        'result': 'capa_root_cause_verification.result', 'evidence': 'capa_root_cause_verification.evidence_attachments',
        'source_ref': 'capa_root_cause_verification.source_ref', 'gate': 'capa_docg_decision.version_snapshot'}[location]
    assert not any(body_column in statement.split('FROM')[0] and 'octet_length' not in statement
                   for statement in statements if statement.lstrip().startswith('SELECT'))


@pytest.mark.asyncio
@pytest.mark.parametrize('large_field', ['snapshot', 'change_summary'])
async def test_immutable_source_body_is_preflighted_before_existing_validator_load(review_case, review_sources, large_field):
    from app.models.fmea import FMEADocument
    from app.services.version_service import create_fmea_version
    from app.services.capa_outcome_review import MAX_OUTCOME_REVIEW_BYTES
    large = 'x' * (MAX_OUTCOME_REVIEW_BYTES + 1)
    async with review_case.session_factory() as db:
        fmea = await db.get(FMEADocument, review_sources.fmea_id)
        if large_field == 'snapshot':
            fmea.graph_data = {'nodes': [], 'edges': [], 'metadata': large}
            await db.commit()
        await create_fmea_version(db, fmea, 'edit', large if large_field == 'change_summary' else 'large snapshot', review_case.actor_id)
        (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
        await db.commit()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    engine = review_case.session_factory.kw['bind']
    event.listen(engine.sync_engine, 'before_cursor_execute', record)
    try:
        with pytest.raises(OutcomeReviewLimit):
            await read(review_case)
    finally:
        event.remove(engine.sync_engine, 'before_cursor_execute', record)
    assert not any('fmea_versions.snapshot' in sql.split('FROM')[0] and 'octet_length' not in sql
        for sql in statements if sql.lstrip().startswith('SELECT'))


@pytest.mark.asyncio
async def test_json_encoding_expansion_is_limited_before_row_append(review_case):
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
            review_case.verification_id).values(result='\n' * (4 * 1024 * 1024)))
        await db.commit()
    with pytest.raises(OutcomeReviewLimit):
        await read(review_case)


@pytest.mark.asyncio
async def test_final_response_has_independent_budget(review_case, monkeypatch):
    from app.services import capa_outcome_review as service
    result = await read(review_case)
    async with review_case.session_factory() as db:
        material = await service.collect_outcome_material(db, await review_case.report(db))
    limit = max(len(service._encoded(result.model_dump(mode='json'))), len(service._encoded(material))) + 500
    monkeypatch.setattr(service, 'MAX_OUTCOME_REVIEW_BYTES', limit)
    async with review_case.session_factory() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(
            d8_closure='x' * (limit - len(service._encoded(result.model_dump(mode='json'))) + 10)))
        await db.commit()
    with pytest.raises(OutcomeReviewLimit):
        await read(review_case)


@pytest.mark.asyncio
async def test_snapshot_uses_request_engine_repeatable_read_and_readonly(review_case, monkeypatch):
    import app.database as database
    from app.services import capa_outcome_review as service
    original = service.collect_outcome_material
    observed = []
    async def inspect(db, capa):
        mode = await db.scalar(text('SHOW transaction_read_only'))
        isolation = await db.scalar(text('SHOW transaction_isolation'))
        observed.append((mode, isolation))
        if mode == 'on':
            assert isolation == 'repeatable read'
            with pytest.raises(DBAPIError, match='read-only'):
                async with db.begin_nested():
                    await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).values(title='not allowed'))
        return await original(db, capa)
    monkeypatch.setattr(service, 'collect_outcome_material', inspect)
    # A wrong global engine must never be consulted.
    monkeypatch.setattr(database, 'engine', None)
    await read(review_case)
    assert ('on', 'repeatable read') in observed
    assert ('off', 'read committed') in observed


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['identity', 'role', 'capa', 'scope', 'source', 'material', 'round', 'line', 'status'])
async def test_real_commit_after_snapshot_is_rejected_by_independent_final_gate(review_case, review_sources, monkeypatch, change):
    from app.models.audit import AuditLog
    from app.models.fmea import FMEADocument
    from app.services import capa_outcome_review as service
    await bind_sources(review_case, review_sources)
    original = service._read_snapshot
    snapshot_done, continue_read = asyncio.Event(), asyncio.Event()
    async def paused(*args, **kwargs):
        result = await original(*args, **kwargs)
        snapshot_done.set()
        await continue_read.wait()
        return result
    monkeypatch.setattr(service, '_read_snapshot', paused)
    task = asyncio.create_task(read(review_case))
    await asyncio.wait_for(snapshot_done.wait(), 5)
    async with review_case.session_factory() as db:
        if change == 'identity':
            await db.execute(update(User).where(User.user_id == review_case.actor_id).values(is_active=False))
        elif change == 'role':
            await db.execute(update(RoleDefinition).where(RoleDefinition.id == review_case.owned_ids['role_id']).values(is_active=False))
        elif change in {'capa', 'source'}:
            await db.execute(update(RolePermission).where(RolePermission.role_id == review_case.owned_ids['role_id'],
                RolePermission.module == ('capa' if change == 'capa' else 'planning')).values(permission_level=0))
        elif change == 'scope':
            await db.execute(delete(UserProductLine).where(UserProductLine.user_id == review_case.actor_id))
        elif change == 'line':
            await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == review_sources.fmea_id).values(product_line_code='outcome-moved-line'))
        elif change == 'material':
            await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
                review_case.verification_id).values(result='externally committed after snapshot'))
        elif change == 'status':
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(status='D8_GATE_PENDING'))
        else:
            db.add(AuditLog(table_name='capa_eightd', record_id=review_case.report_id, factory_id=review_case.factory_id,
                action='TRANSITION', changed_fields={'old_status': 'D8_GATE_PENDING', 'new_status': 'D8_APPROVAL_PENDING'},
                operated_by=review_case.actor_id))
        await db.commit()
    continue_read.set()
    with pytest.raises((PermissionError, LookupError, OutcomeReviewConflict)):
        await asyncio.wait_for(task, 5)


@pytest.mark.asyncio
async def test_committed_parent_and_child_change_during_rr_does_not_mix_versions(review_case, monkeypatch):
    from app.services import capa_outcome_review as service
    original = service._rows
    at_children, resume = asyncio.Event(), asyncio.Event()
    async def paused(db, *args, **kwargs):
        if await db.scalar(text('SHOW transaction_read_only')) == 'on' and not at_children.is_set():
            at_children.set()
            await resume.wait()
        return await original(db, *args, **kwargs)
    monkeypatch.setattr(service, '_rows', paused)
    async with review_case.session_factory() as request_db:
        request_scope = await review_case.scope(request_db)
        task = asyncio.create_task(service._read_snapshot(request_db, request_scope, review_case.report_id, None))
        await asyncio.wait_for(at_children.wait(), 5)
        try:
            async with review_case.session_factory() as writer:
                await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(d4_root_cause='new root'))
                await writer.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
                    review_case.verification_id).values(result='new child'))
                await writer.commit()
        finally:
            resume.set()
        material, dto, _ = await asyncio.wait_for(task, 5)
    assert material['core']['d4_root_cause'] == dto.core.d4_root_cause == '扭矩不足'
    assert dto.verifications[0].result == '复测合格'
    current = await read(review_case)
    assert current.core.d4_root_cause == 'new root'
    assert current.verifications[0].result == 'new child'
    assert current.revision != dto.revision


@pytest.mark.asyncio
async def test_child_batches_are_100_with_uuid_keyset_and_no_ui_cap(review_case):
    from app.models.capa import CapaD7NodeAction
    async with review_case.session_factory() as db:
        db.add_all([CapaD7NodeAction(capa_id=review_case.report_id, factory_id=review_case.factory_id,
            action='skipped', failure_mode_node_id=f'rule:{i}', match_source='rule', reason='not applicable',
            acted_by=review_case.actor_id) for i in range(205)])
        await db.commit()
    batches = []
    def record(conn, cursor, statement, parameters, context, executemany):
        if 'FROM capa_d7_node_action' in statement and 'ORDER BY' in statement:
            batches.append((statement, parameters))
    engine = review_case.session_factory.kw['bind']
    event.listen(engine.sync_engine, 'before_cursor_execute', record)
    try:
        result = await read(review_case)
    finally:
        event.remove(engine.sync_engine, 'before_cursor_execute', record)
    assert len(result.d7_actions) == 205
    assert len(batches) >= 6  # RR + independent final read, three populated batches each
    assert all('LIMIT' in sql and 100 in params for sql, params in batches)
    assert any('action_id >' in sql for sql, _ in batches)


@pytest.mark.asyncio
@pytest.mark.parametrize('move', ['source_factory', 'source_product_line', 'target_factory', 'target_product_line'])
async def test_actual_owned_factory_and_line_migration_cannot_return_old_body(review_case, review_sources, monkeypatch, move):
    from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
    from app.models.factory import Factory
    from app.models.product_line import ProductLine
    from app.models.fmea import FMEADocument
    from app.services import capa_outcome_review as service
    factory_id, line_code = uuid4(), 'ORM'+uuid4().hex[:12]
    async with review_case.session_factory() as db:
        db.add(Factory(id=factory_id, code='OR-MOVE-'+uuid4().hex[:8], name='Owned migration target'))
        await db.flush()
        db.add(ProductLine(code=line_code, name='Owned other scope', factory_id=factory_id,
            product_type_code=review_case.owned_ids['product_type_code']))
        await db.commit()
    await bind_sources(review_case, review_sources)
    original = service._read_snapshot
    snapshot_done, proceed = asyncio.Event(), asyncio.Event()
    async def paused(*args, **kwargs):
        value = await original(*args, **kwargs)
        snapshot_done.set()
        await proceed.wait()
        return value
    monkeypatch.setattr(service, '_read_snapshot', paused)
    task = asyncio.create_task(read(review_case))
    try:
        await asyncio.wait_for(snapshot_done.wait(), 5)
        async with review_case.session_factory() as db:
            if move.startswith('source'):
                values = {'product_line_code': line_code}
                if move == 'source_factory': values['factory_id'] = factory_id
                await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == review_sources.fmea_id).values(**values))
            else:
                # The external transaction retires its old gate before moving
                # the parent, preserving the real composite FK constraints.
                await db.execute(delete(CapaDocgDecision).where(CapaDocgDecision.analysis_id == review_case.owned_ids['analysis_id']))
                await db.execute(delete(CapaDocgAnalysis).where(CapaDocgAnalysis.analysis_id == review_case.owned_ids['analysis_id']))
                values = {'product_line_code': line_code}
                if move == 'target_factory': values['factory_id'] = factory_id
                await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(**values))
            await db.commit()
        proceed.set()
        with pytest.raises((PermissionError, LookupError, OutcomeReviewConflict)):
            await asyncio.wait_for(task, 5)
    finally:
        proceed.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with review_case.session_factory() as db:
            await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == review_sources.fmea_id).values(
                factory_id=review_case.factory_id, product_line_code=review_case.product_line_code))
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(
                factory_id=review_case.factory_id, product_line_code=review_case.product_line_code))
            await db.execute(delete(ProductLine).where(ProductLine.code == line_code))
            await db.execute(delete(Factory).where(Factory.id == factory_id))
            await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['identity', 'source_permission', 'source_scope'])
async def test_last_authority_gate_is_after_final_dto_assembly(review_case, review_sources, monkeypatch, change):
    from app.models.fmea import FMEADocument
    from app.services import capa_outcome_review as service
    await bind_sources(review_case, review_sources)
    original = service._dto
    async def changed(db, *args, **kwargs):
        result = await original(db, *args, **kwargs)
        if await db.scalar(text('SHOW transaction_read_only')) == 'off':
            async with review_case.session_factory() as writer:
                if change == 'identity':
                    await writer.execute(update(User).where(User.user_id == review_case.actor_id).values(is_active=False))
                elif change == 'source_permission':
                    await writer.execute(update(RolePermission).where(RolePermission.role_id == review_case.owned_ids['role_id'],
                        RolePermission.module == 'planning').values(permission_level=0))
                else:
                    await writer.execute(update(FMEADocument).where(FMEADocument.fmea_id == review_sources.fmea_id).values(
                        product_line_code='outcome-moved-line'))
                await writer.commit()
        return result
    monkeypatch.setattr(service, '_dto', changed)
    with pytest.raises((PermissionError, OutcomeReviewConflict)):
        await read(review_case)


@pytest.mark.asyncio
async def test_read_committed_collector_does_not_change_isolation_or_write(review_case):
    from app.services.capa_outcome_review import collect_outcome_material
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        await db.execute(select(CAPAEightD.report_id).where(CAPAEightD.report_id == review_case.report_id).with_for_update())
        material = await collect_outcome_material(db, await review_case.report(db))
        assert material['core']['d4_root_cause'] == '扭矩不足'
        assert await db.scalar(text('SHOW transaction_isolation')) == 'read committed'
        assert await db.scalar(text('SHOW transaction_read_only')) == 'off'
    assert before == await review_case.snapshot()
