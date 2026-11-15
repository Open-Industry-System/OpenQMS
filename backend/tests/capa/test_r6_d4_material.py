"""R6 complete root inheritance and legacy compatibility."""
import pytest
from sqlalchemy import select
from app.models.capa_r6 import CapaR6RootRevisionBody
from tests.capa.test_d4_root_revisions import make_report

pytestmark = pytest.mark.requires_db

@pytest.mark.asyncio
async def test_manual_revisions_keep_immutable_body_and_material(db, default_factory, admin_user):
    from app.services.capa_d4_material import read_root, material_version
    from app.services.capa_service import update_capa
    report = await make_report(db, default_factory, admin_user)
    old = await material_version(db, report.report_id)
    for body in ('A', 'B', ''):
        await update_capa(db, report, {'d4_root_cause': body}, admin_user.user_id)
        assert await read_root(db, admin_user.user_id, report.report_id) == body
    rows = list((await db.scalars(select(CapaR6RootRevisionBody).where(
        CapaR6RootRevisionBody.report_id == report.report_id))).all())
    assert {r.body for r in rows} == {'A', 'B', ''}
    assert all(r.binding_state == 'legacy_unattested' for r in rows)
    assert old != await material_version(db, report.report_id)

@pytest.mark.asyncio
async def test_complete_union_survives_manual_clear_and_live_revocation(r6_case):
    from types import SimpleNamespace
    from uuid import uuid4
    from app.models.capa_r6 import CapaR6SourceOrigin
    from app.services.capa_d4_material import read_root, authorize_root
    from app.services.capa_d4_provenance import record_root_revision
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    from app.services.capa_service import update_capa
    case = r6_case
    actor = case.actor('edit')
    source_ids = []
    async with case.session() as db:
        report = await case.report()
        from app.models.capa import CAPAEightD
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D4_ROOT_CAUSE'
        from app.models.capa import CapaRootCauseVerification
        from app.models.audit import AuditLog
        db.add(CapaRootCauseVerification(capa_id=case.report_id, factory_id=case.factory_id,
            root_cause_text='A+B protected verification', method='observation', result='observed',
            conclusion='pending', is_verified=False, verified_by=actor.user_id))
        db.add(AuditLog(table_name='capa_eightd', record_id=case.report_id, action='LEGACY_ROOT',
            changed_fields={'d4_root_cause': 'historical protected body'},
            old_values={'d4_root_cause': 'before restricted'}, new_values={'d4_root_cause': 'after restricted'},
            operated_by=actor.user_id, factory_id=case.factory_id))
        await db.commit()
        for doc, text in ((case.source_a, 'A'), (case.source_b, 'A+B')):
            await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == case.report_id).with_for_update())
            visible = await visible_fmea_source(db, SimpleNamespace(user=actor), doc.fmea_id)
            version = await failure_cause_version(db, visible, 'cause')
            source = CapaR6SourceOrigin(source_id=uuid4(), report_id=case.report_id,
                kind='fmea_projection', module='fmea', object_id=doc.fmea_id,
                projection_id='fmea.failure_cause.reference.v1', version=version,
                factory_id=doc.factory_id, product_line_code=doc.product_line_code,
                fmea_id=doc.fmea_id, node_id='cause')
            db.add(source)
            await db.flush()
            source_ids.append(source.source_id)
            report.d4_root_cause = text
            await record_root_revision(db, report_id=case.report_id, actor_id=actor.user_id,
                write_path='r6:test', added_source_ids=[source.source_id])
            await db.commit()
        await update_capa(db, report, {'d4_root_cause': ''}, actor.user_id)
        assert await read_root(db, actor.user_id, case.report_id) == ''
        _, sources = await authorize_root(db, actor.user_id, case.report_id)
        assert {s.source_id for s in sources} == set(source_ids)
    detail = await actor.client.get(f'/api/capa/{case.report_id}')
    assert detail.status_code == 200, detail.text
    assert detail.json()['d4_root_cause'] == ''
    assert detail.json()['material_version']
    assert (await actor.client.get('/api/capa')).status_code == 200
    verification_response = await actor.client.get(f'/api/capa/{case.report_id}/root-cause-verifications')
    assert verification_response.status_code == 200
    assert verification_response.json()[0]['root_cause_text'] == 'A+B protected verification'
    from app.services.log_service import list_audit_logs
    async with case.session() as db:
        rows, _ = await list_audit_logs(db, {'action': 'LEGACY_ROOT'}, 1, 20, actor_id=actor.user_id)
        assert rows[0]['old_values']['d4_root_cause'] == 'before restricted'
    # History authority is independent of current node freshness.
    from app.models.fmea import FMEADocument
    from app.services.capa_d4_material import require_root_freshness
    async with case.session() as db:
        doc = await db.get(FMEADocument, case.source_a.fmea_id)
        doc.graph_data = {'nodes': [{'id': 'cause', 'type': 'FailureCause', 'name': 'changed'}], 'edges': []}
        await db.commit()
        assert await read_root(db, actor.user_id, case.report_id) == ''
        with pytest.raises(PermissionError, match='D4_MATERIAL_STALE'):
            await require_root_freshness(db, actor.user_id, case.report_id)
    # This actor has every route's module permission: rejection must be root authority.
    from app.models.role import RolePermission
    async with case.session() as db:
        db.add(RolePermission(role_id=actor.role_id, module='supplier_risk', permission_level=3))
        await db.commit()
    await actor.revoke('source_b')
    from sqlalchemy import event
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    engine = case.runtime.engine.sync_engine
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        assert (await actor.client.get(f'/api/capa/{case.report_id}/related-fmea')).status_code == 403
        assert (await actor.client.post(f'/api/capa/{case.report_id}/lessons-learned', json={})).status_code == 403
        assert (await actor.client.post(f'/api/capa/{case.report_id}/confirm-repeat',
                    json={'repeat_confirmed': True})).status_code == 403
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert not any('from capa_eightd' in query and 'd4_root_cause' in query for query in statements)
    assert (await actor.client.get(f'/api/capa/{case.report_id}')).status_code == 403
    assert (await actor.client.get('/api/capa')).status_code == 403
    assert (await actor.client.get(f'/api/capa/{case.report_id}/root-cause-verifications')).status_code == 403
    async with case.session() as db:
        from app.services.capa_d4_text_preview import get_version, create_preview
        from app.schemas.capa_d4_text_preview import D4PreviewRequest
        preview_queries = []
        connection = await db.connection()
        def capture_preview(conn, cursor, statement, parameters, context, executemany):
            preview_queries.append(statement.lower())
        event.listen(connection.sync_connection, 'before_cursor_execute', capture_preview)
        try:
            with pytest.raises(PermissionError):
                await get_version(db, SimpleNamespace(user=actor), case.report_id)
            with pytest.raises(PermissionError):
                await create_preview(db, SimpleNamespace(user=actor), case.report_id, D4PreviewRequest())
        finally:
            event.remove(connection.sync_connection, 'before_cursor_execute', capture_preview)
        assert not any('capa_eightd.d4_root_cause' in query or
                       'capa_root_cause_verification.root_cause_text' in query for query in preview_queries)
        with pytest.raises(PermissionError):
            await list_audit_logs(db, {'action': 'LEGACY_ROOT'}, 1, 20, actor_id=actor.user_id)
        with pytest.raises(PermissionError):
            await read_root(db, actor.user_id, case.report_id)
        report = await db.get(CAPAEightD, case.report_id)
        with pytest.raises(PermissionError):
            await update_capa(db, report, {'d4_root_cause': 'launder'}, actor.user_id)

@pytest.mark.asyncio
async def test_view_actor_cannot_write(r6_case):
    from app.services.capa_service import update_capa
    case = r6_case
    async with case.session() as db:
        from app.models.capa import CAPAEightD
        report = await db.get(CAPAEightD, case.report_id)
        with pytest.raises(PermissionError):
            await update_capa(db, report, {'d4_root_cause': 'denied'}, case.actor('view').user_id)

@pytest.mark.asyncio
@pytest.mark.parametrize('prior_binding', [False, True])
async def test_missing_first_binding_and_unmarked_successor_fail_before_body(
        db, default_factory, admin_user, prior_binding):
    from sqlalchemy import event
    from uuid import uuid4
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision
    from app.services.capa_d4_material import read_root
    from app.services.capa_d4_provenance import record_root_revision
    report = await make_report(db, default_factory, admin_user, 'secret')
    if prior_binding:
        await record_root_revision(db, report_id=report.report_id, actor_id=admin_user.user_id,
                                   write_path='fixture')
    db.add(CapaD4RootCauseRevision(revision_id=uuid4(), report_id=report.report_id,
        revision_no=2 if prior_binding else 1, field_hmac='0' * 64, actor_id=admin_user.user_id,
        write_path='old.writer' if prior_binding else 'r6:missing'))
    await db.flush()
    statements = []
    connection = await db.connection()
    def spy(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(connection.sync_connection, 'before_cursor_execute', spy)
    try:
        with pytest.raises(PermissionError):
            await read_root(db, admin_user.user_id, report.report_id)
    finally:
        event.remove(connection.sync_connection, 'before_cursor_execute', spy)
    assert not any('select capa_eightd.d4_root_cause' in statement for statement in statements)

@pytest.mark.asyncio
async def test_true_unmarked_legacy_root_remains_readable(db, default_factory, admin_user):
    from uuid import uuid4
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision
    from app.services.capa_d4_material import read_root
    report = await make_report(db, default_factory, admin_user, 'legacy')
    db.add(CapaD4RootCauseRevision(revision_id=uuid4(), report_id=report.report_id,
        revision_no=1, field_hmac='0' * 64, actor_id=admin_user.user_id, write_path='historic'))
    await db.flush()
    assert await read_root(db, admin_user.user_id, report.report_id) == 'legacy'

@pytest.mark.asyncio
async def test_input_snapshots_detect_aba_and_expected_material_conflict(db, default_factory, admin_user):
    from app.services.capa_service import update_capa
    from app.services.capa_d4_material import material_version
    from app.models.capa_r6 import CapaR6ReportSnapshot
    report = await make_report(db, default_factory, admin_user)
    token = await material_version(db, report.report_id)
    for text in ('A', 'B', 'A'):
        await update_capa(db, report, {'d2_description': text}, admin_user.user_id)
    snapshots = list((await db.scalars(select(CapaR6ReportSnapshot).where(
        CapaR6ReportSnapshot.report_id == report.report_id).order_by(CapaR6ReportSnapshot.version))).all())
    assert [(s.version, s.body) for s in snapshots] == [(1, 'A'), (2, 'B'), (3, 'A')]
    with pytest.raises(ValueError, match='CAPA_MATERIAL_CHANGED'):
        await update_capa(db, report, {'d4_root_cause': 'stale', 'expected_material_version': token}, admin_user.user_id)

@pytest.mark.asyncio
async def test_other_manual_material_and_legacy_d5_adopt_bump_counter(db, default_factory, admin_user):
    from app.services.capa_service import update_capa
    from app.services.capa_verification_service import adopt_recommendation
    from app.services.capa_d4_material import material_version
    from app.schemas.capa_verification import AdoptRequest
    report = await make_report(db, default_factory, admin_user)
    report.status = 'D5_CORRECTION'
    await db.flush()
    before = await material_version(db, report.report_id)
    await update_capa(db, report, {'d5_correction': 'manual measure'}, admin_user.user_id)
    manual = await material_version(db, report.report_id)
    assert manual != before
    await adopt_recommendation(db, report, AdoptRequest(d_step='d5', adopted_text='legacy measure', source='rule'), admin_user)
    assert await material_version(db, report.report_id) != manual

@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['digest', 'source_count'])
async def test_corrupt_binding_fails_before_root_body(db, default_factory, admin_user, damage):
    from sqlalchemy import event
    from uuid import uuid4
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision
    from app.services.capa_d4_material import read_root, origin_digest
    report = await make_report(db, default_factory, admin_user, 'protected')
    revision = CapaD4RootCauseRevision(revision_id=uuid4(), report_id=report.report_id,
        revision_no=1, field_hmac='0'*64, actor_id=admin_user.user_id, write_path='r6:damaged')
    db.add(revision)
    await db.flush()
    db.add(CapaR6RootRevisionBody(revision_id=revision.revision_id, report_id=report.report_id,
        binding_state='controlled' if damage == 'source_count' else 'legacy_unattested',
        source_count=1 if damage == 'source_count' else 0, body='protected',
        origin_digest=origin_digest([]) if damage == 'source_count' else '0'*64))
    await db.flush()
    statements = []
    connection = await db.connection()
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(connection.sync_connection, 'before_cursor_execute', capture)
    try:
        with pytest.raises(PermissionError):
            await read_root(db, admin_user.user_id, report.report_id)
    finally:
        event.remove(connection.sync_connection, 'before_cursor_execute', capture)
    assert not any('select capa_eightd.d4_root_cause' in query for query in statements)

@pytest.mark.asyncio
async def test_same_report_uuid_isolated_in_real_second_tenant(r6_case):
    from uuid import uuid4
    from sqlalchemy import text
    from app.core.tenant_transaction import TenantBinding
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    from app.models.capa import CAPAEightD
    from app.models.product_line import ProductLine
    from app.models.user import User
    from app.services.capa_service import update_capa
    from app.services.capa_d4_material import read_root, material_version
    case = r6_case
    other = await tenant_migrator.provision_new(TenantCreateRequest(name='R6 isolation',
        slug='r6-isolation-' + uuid4().hex[:12], admin_email='isolation@example.test',
        admin_password='R6IsolationSyntheticPassword123!'))
    binding = TenantBinding(other.id, other.schema_name, other.generation, 'business')
    try:
        async with case.session() as db:
            report = await db.get(CAPAEightD, case.report_id)
            report.status = 'D4_ROOT_CAUSE'
            await db.commit()
            await update_capa(db, report, {'d4_root_cause': 'first tenant'}, case.actor('edit').user_id)
            first = await material_version(db, case.report_id)
        async with case.factory(binding=binding) as db:
            user = await db.scalar(select(User).where(User.email == 'isolation@example.test'))
            line = await db.scalar(select(ProductLine))
            report = CAPAEightD(report_id=case.report_id, document_no='R6-SECOND', title='second',
                factory_id=line.factory_id, product_line_code=line.code, created_by=user.user_id,
                status='D4_ROOT_CAUSE')
            db.add(report)
            await db.commit()
            await update_capa(db, report, {'d4_root_cause': 'second tenant'}, user.user_id)
            assert await material_version(db, case.report_id) != first
            assert await read_root(db, user.user_id, case.report_id) == 'second tenant'
            with pytest.raises(PermissionError):
                await read_root(db, case.actor('edit').user_id, case.report_id)
        async with case.session() as db:
            assert await read_root(db, case.actor('edit').user_id, case.report_id) == 'first tenant'
    finally:
        # Exactly this test's newly provisioned namespace, following owned-runtime cleanup.
        async with case.runtime.engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{other.schema_name}" CASCADE'))
            await connection.execute(text('DELETE FROM public.tenant_migrations WHERE tenant_id=:id'), {'id': other.id})
            await connection.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': other.id})

@pytest.mark.asyncio
async def test_advance_rechecks_source_revocation_after_real_parent_wait(r6_case):
    import asyncio
    from types import SimpleNamespace
    from uuid import uuid4
    from sqlalchemy import text
    from app.models.capa import CAPAEightD
    from app.models.capa_r6 import CapaR6SourceOrigin
    from app.services.capa_d4_provenance import record_root_revision
    from app.services.capa_d4_material import material_version
    from app.services.capa_service import advance_capa
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    case = r6_case
    actor = case.actor('edit')
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status, report.d4_root_cause = 'D2_DESCRIPTION', 'restricted root'
        doc = case.source_b
        visible = await visible_fmea_source(db, SimpleNamespace(user=actor), doc.fmea_id)
        version = await failure_cause_version(db, visible, 'cause')
        origin = CapaR6SourceOrigin(source_id=uuid4(), report_id=case.report_id,
            kind='fmea_projection', module='fmea', object_id=doc.fmea_id,
            projection_id='fmea.failure_cause.reference.v1', version=version,
            factory_id=doc.factory_id, product_line_code=doc.product_line_code,
            fmea_id=doc.fmea_id, node_id='cause')
        db.add(origin)
        await db.flush()
        await record_root_revision(db, report_id=case.report_id, actor_id=actor.user_id,
                                   write_path='test', added_source_ids=[origin.source_id])
        await db.commit()
    before = await case.snapshot()
    async with case.session() as blocker, case.session() as writer:
        report = await writer.get(CAPAEightD, case.report_id)
        waiter_pid = await writer.scalar(text('SELECT pg_backend_pid()'))
        blocker_pid = await blocker.scalar(text('SELECT pg_backend_pid()'))
        await blocker.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == case.report_id).with_for_update())
        task = asyncio.create_task(advance_capa(writer, report, actor.user_id))
        async def observed_wait():
            async with case.session() as monitor:
                while blocker_pid not in await monitor.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid': waiter_pid}):
                    await asyncio.sleep(.01)
        try:
            await asyncio.wait_for(observed_wait(), timeout=10)
            await actor.revoke('source_b')
        finally:
            await blocker.rollback()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(task, timeout=10)
        await writer.rollback()
    after = await case.snapshot()
    assert before == after

@pytest.mark.asyncio
async def test_link_and_stage_transition_invalidate_general_material(r6_case):
    from app.models.capa import CAPAEightD
    from app.services.capa_d4_material import material_version
    from app.services.capa_service import link_fmea, advance_capa
    case = r6_case
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D2_DESCRIPTION'
        await db.commit()
        before = await material_version(db, case.report_id)
        await link_fmea(db, report, case.source_a.fmea_id, case.actor('edit').user_id, 'cause')
        linked = await material_version(db, case.report_id)
        assert linked != before
        await advance_capa(db, report, case.actor('edit').user_id)
        assert report.status == 'D3_INTERIM'
        assert await material_version(db, case.report_id) != linked

@pytest.mark.asyncio
async def test_list_payload_uses_frozen_authorized_ids_during_insert(r6_case, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4
    from sqlalchemy import event
    from app.models.capa import CAPAEightD
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision
    from app.services import capa_d4_material
    from app.services.capa_service import list_capas
    case = r6_case
    actor = case.actor('edit')
    original = capa_d4_material.authorize_root
    inserted = uuid4()
    done = False
    async def after_admission(db, actor_id, report_id, *args):
        nonlocal done
        result = await original(db, actor_id, report_id, *args)
        if not done:
            done = True
            async with case.session() as writer:
                writer.add(CAPAEightD(report_id=inserted, document_no='R6-INSERT', title='unavailable newcomer',
                    factory_id=case.factory_id, product_line_code=case.line, created_by=actor.user_id,
                    status='D4_ROOT_CAUSE', d4_root_cause='restricted newcomer',
                    created_at=datetime.now(UTC) + timedelta(days=1)))
                await writer.flush()
                writer.add(CapaD4RootCauseRevision(revision_id=uuid4(), report_id=inserted,
                    revision_no=1, field_hmac='0'*64, actor_id=actor.user_id, write_path='r6:unavailable'))
                await writer.commit()
        return result
    monkeypatch.setattr(capa_d4_material, 'authorize_root', after_admission)
    async with case.session() as db:
        statements = []
        connection = await db.connection()
        def capture(conn, cursor, statement, parameters, context, executemany):
            if 'capa_eightd.d4_root_cause' in statement.lower():
                statements.append((statement, str(parameters)))
        event.listen(connection.sync_connection, 'before_cursor_execute', capture)
        try:
            items, total = await list_capas(db, page_size=1, factory_id=case.factory_id, actor_id=actor.user_id)
        finally:
            event.remove(connection.sync_connection, 'before_cursor_execute', capture)
        assert [item.report_id for item in items] == [case.report_id]
        assert statements and all(str(inserted) not in params for _, params in statements)
        assert total == 2

@pytest.mark.asyncio
async def test_audit_authorizes_only_frozen_page(db, default_factory, admin_user):
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4
    from sqlalchemy import event
    from app.models.audit import AuditLog
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision
    from app.services.log_service import list_audit_logs
    report = await make_report(db, default_factory, admin_user, 'restricted')
    db.add(CapaD4RootCauseRevision(revision_id=uuid4(), report_id=report.report_id,
        revision_no=1, field_hmac='0'*64, actor_id=admin_user.user_id, write_path='r6:missing'))
    action = 'PAGE-' + uuid4().hex[:12]
    now = datetime.now(UTC)
    db.add_all([
        AuditLog(table_name='users', record_id=admin_user.user_id, action=action,
            changed_fields={'allowed': True}, operated_by=admin_user.user_id,
            factory_id=default_factory.id, operated_at=now),
        AuditLog(table_name='capa_eightd', record_id=report.report_id, action=action,
            old_values={'d4_root_cause': 'protected'}, operated_by=admin_user.user_id,
            factory_id=default_factory.id, operated_at=now - timedelta(days=1))])
    await db.flush()
    rows, count = await list_audit_logs(db, {'action': action}, 1, 1, actor_id=admin_user.user_id)
    assert count == 2 and rows[0]['changed_fields'] == {'allowed': True}
    statements = []
    connection = await db.connection()
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(connection.sync_connection, 'before_cursor_execute', capture)
    try:
        with pytest.raises(PermissionError):
            await list_audit_logs(db, {'action': action}, 2, 1, actor_id=admin_user.user_id)
    finally:
        event.remove(connection.sync_connection, 'before_cursor_execute', capture)
    assert not any('audit_logs.old_values' in query for query in statements)
