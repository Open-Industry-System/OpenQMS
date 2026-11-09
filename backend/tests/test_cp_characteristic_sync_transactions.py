"""Real commits and independent sessions for Task 6; only disposable qms_test schemas."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import re
import uuid
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from sqlalchemy import event, select, text

from tests.test_cp_characteristic_import_transactions import (
    isolated_tenants, seed_tenant, tenant_scope, import_request,
)
from tests.test_cp_characteristic_import import graph, rows
from app.core.tenant_utils import current_tenant_schema, current_tenant_binding
from app.core.permissions import PermissionLevel
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.models.fmea_version import FMEAVersion
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision
from app.models.special_characteristic import SpecialCharacteristic
from app.models.role import RolePermission
from app.schemas.version import SyncFromFMEARequest
from app.services import control_plan_service as imports, version_service as sync, capa_doc_gate_service as gate
from app.services.agent import provider_adapter

pytestmark = pytest.mark.asyncio
EXTRAS = ('capa_eightd', 'capa_docg_analysis', 'capa_docg_audit', 'capa_docg_decision', 'special_characteristics')
BASE = ('factories', 'product_lines', 'role_definitions', 'users', 'role_permissions',
        'user_factories', 'user_product_lines', 'fmea_documents', 'fmea_versions',
        'control_plans', 'control_plan_items', 'control_plan_versions', 'audit_logs')

@pytest_asyncio.fixture
async def sync_tenants(isolated_tenants, monkeypatch):
    sessions, schemas = isolated_tenants
    async with sessions() as db:
        for schema in schemas:
            for table in EXTRAS:
                await db.execute(text(f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL)'))
            for table in EXTRAS:
                definitions = (await db.execute(text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid=to_regclass(:table) AND contype='f'"), {'table': 'public.'+table})).all()
                for name, definition in definitions:
                    definition = re.sub(r'REFERENCES (?:public\.)?([a-z_]+)',
                        lambda m: f'REFERENCES "{schema if m[1] in BASE+EXTRAS else "public"}"."{m[1]}"', definition)
                    await db.execute(text(f'ALTER TABLE "{schema}"."{table}" ADD CONSTRAINT "{name}" {definition}'))
        # Install the reviewed tenant-local guards (strict paths exclude public).
        from alembic_tenant.snapshot.business_20260927 import DDL
        for schema in schemas:
            await db.execute(text(f'SET LOCAL search_path TO "{schema}", pg_catalog'))
            for statement in DDL:
                if statement.startswith(('CREATE FUNCTION verify_version_hash(', 'CREATE FUNCTION prevent_version_tampering(')):
                    await db.execute(text(statement))
            for statement in DDL:
                if statement.startswith('CREATE TRIGGER trg_') and '_version_' in statement:
                    name = statement.split()[2]
                    table = statement.split(' ON ')[1].split()[0]
                    await db.execute(text(f'DROP TRIGGER {name} ON {table}'))
                    await db.execute(text(statement))
        await db.commit()
    # Exercise main's real tenant-session admission, not search_path-only authority.
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    from app.database import TenantSession
    from sqlalchemy.ext.asyncio import AsyncSession
    bindings = {schema: TenantBinding(uuid.uuid4(), schema, 1, 'business') for schema in schemas}
    async with sessions() as db:
        for binding in bindings.values():
            await db.execute(text("INSERT INTO public.tenants (id,name,slug,subdomain,schema_name,status,generation) "
                                  "VALUES (:id,:schema,:slug,:slug,:schema,'active',1)"),
                             {'id': binding.tenant_id, 'schema': binding.schema_name, 'slug': binding.schema_name.replace('_', '-')})
        await db.commit()
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    # Normal request/background entry points use the same real NullPool test
    # engine; pooled connections cannot survive pytest's per-test event loops.
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app import database
    from app.core import tenant_context
    monkeypatch.setattr(database, 'tenant_async_session', async_sessionmaker(
        sessions.kw['bind'], class_=AsyncSession, sync_session_class=TenantSession,
        expire_on_commit=False))
    monkeypatch.setattr(tenant_context, 'async_session', async_sessionmaker(
        sessions.kw['bind'], class_=AsyncSession, expire_on_commit=False))

    @asynccontextmanager
    async def bound_sessions(*, expire_on_commit=True):
        binding = bindings[current_tenant_schema.get()]
        token = current_tenant_binding.set(binding)
        try:
            async with AsyncSession(bind=sessions.kw['bind'], sync_session_class=TenantSession,
                                    binding=binding, expire_on_commit=expire_on_commit) as db:
                yield db
        finally:
            current_tenant_binding.reset(token)

    # DDL setup is owner maintenance, not an unbound business session.
    bound_sessions.admin_sessions = sessions

    try:
        yield bound_sessions, schemas
    finally:
        async with sessions() as db:
            for binding in bindings.values():
                await db.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': binding.tenant_id})
            await db.commit()

async def prepared(sessions, schema, *, ids=None, deletion=False):
    token = current_tenant_schema.set(schema)
    try:
        ids, body = await seed_tenant(sessions, schema, identical_ids=ids)
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            db.add(RolePermission(role_id=ids[2], module='capa', permission_level=PermissionLevel.EDIT))
            await db.flush()
            req = await import_request(db, ids, body, scope)
            await imports.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
            await db.execute(text(f'SET search_path TO "{schema}", public'))
            g = graph()
            if deletion:
                g['nodes'][3]['characteristics'].pop()
            else:
                g['nodes'][0]['process_number'] = 'OP20'
            v = FMEAVersion(version_id=uuid.uuid4(), fmea_id=ids[5], factory_id=ids[0],
                major_no=2, minor_no=0, change_type='approve', snapshot=g,
                sha256_hash=await sync.compute_pg_jsonb_hash(db, g), created_by=ids[3])
            db.add(v)
            vid = v.version_id
            await db.commit()
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            p = await sync.build_sync_preview(db, ids[4], vid, scope=scope)
        return ids, vid, p
    finally:
        current_tenant_schema.reset(token)


def request(p, keys=None):
    return SyncFromFMEARequest(source_fmea_version_id=p['source_fmea_version_id'],
        expected_lock_version=p['expected_lock_version'], preview_digest=p['preview_digest'],
        selected_candidate_keys=keys if keys is not None else [i['candidate_key'] for i in p['items'] if i['applicable']])

async def running(sessions, schema, ids, monkeypatch):
    async with sessions() as db:
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        capa = CAPAEightD(report_id=uuid.uuid4(), document_no='CAPA-PUBLISH', title='Private',
            factory_id=ids[0], product_line_code='LINE', status='D8_GATE_PENDING')
        db.add(capa)
        await db.commit()
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        capa = await db.scalar(select(CAPAEightD))
        cid = capa.report_id
        monkeypatch.setattr(provider_adapter, 'build_client', AsyncMock(return_value=type('Client', (), {'model': 'test'})()))
        target = (await rows(db, ids[4]))[0]
        monkeypatch.setattr(provider_adapter, 'complete_json', AsyncMock(return_value={'affected_docs': [{
            'doc_type': 'control_plan', 'doc_id': str(ids[4]), 'key_points': [{
                'target_kind': 'cp_item', 'expected_action': 'modify', 'target_key': str(target.item_id),
                'field': 'control_method'}], 'update_suggestion': 'Review'}]}))
        p1 = await gate._phase1_create_running(db, capa, ids[3])
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        capa = await db.get(CAPAEightD, cid)
        p2 = await gate._phase2_llm(db, capa, p1)
        return cid, p1, p2

async def publish(db, schema, ids, cid, p1, p2):
    await db.execute(text(f'SET search_path TO "{schema}", public'))
    capa = await db.get(CAPAEightD, cid)
    return await gate._phase3_cas(db, capa, p1, p2, ids[3])

async def test_real_commit_no_postcommit_read_and_replay_race(sync_tenants):
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, vid, p = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    try:
        async def apply():
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                count = []
                event.listen(db.sync_session, 'after_commit', lambda s: count.append(1) if not s.in_nested_transaction() else None)
                try:
                    response = await sync.apply_sync_preview(db, ids[4], request(p), ids[3], scope=scope)
                    assert len(count) == 1 and not db.in_transaction()
                    assert response.change_type == 'fmea_sync'
                    return 'applied'
                except imports.CharacteristicImportError as exc:
                    assert exc.status_code == 409
                    return 'stale'
        assert sorted(await asyncio.wait_for(asyncio.gather(apply(), apply()), 10)) == ['applied', 'stale']
        async with sessions() as db:
            await tenant_scope(db, schema, ids[3])
            cp = await db.get(ControlPlan, ids[4])
            assert not cp.sync_pending and cp.source_fmea_version_id == vid and cp.lock_version == 2
            assert all(i.step_no == 'OP20' for i in await rows(db, ids[4]))
            versions = list((await db.scalars(select(ControlPlanVersion).order_by(ControlPlanVersion.minor_no))).all())
            assert len(versions) == 2
            for version in versions:
                assert await sync.verify_cp_version(db, version.version_id)
            assert all(r['source_characteristic_ref']['accepted_source_version_id'] == str(vid)
                       for r in versions[-1].items_snapshot)
            assert all(r['source_characteristic_ref']['accepted_source_version_id'] == str(ids[6])
                       for r in versions[0].items_snapshot)
    finally:
        current_tenant_schema.reset(token)

@pytest.mark.parametrize('first', ['sync', 'capa'])
async def test_actual_publication_interlock_both_orders(sync_tenants, monkeypatch, first):
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, vid, p = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    try:
        cid, p1, p2 = await running(sessions, schema, ids, monkeypatch)
        locked, release = asyncio.Event(), asyncio.Event()
        original = sync.stage_cp_version if first == 'sync' else gate.cp_input_state
        if first == 'sync':
            async def paused(*args, **kwargs):
                result = await original(*args, **kwargs)
                locked.set()
                await release.wait()
                return result
            monkeypatch.setattr(sync, 'stage_cp_version', paused)
        else:
            async def paused(*args, **kwargs):
                result = await original(*args, **kwargs)
                if kwargs.get('lock'):
                    locked.set()
                    await release.wait()
                return result
            monkeypatch.setattr(gate, 'cp_input_state', paused)
        async def do_sync():
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                try:
                    await sync.apply_sync_preview(db, ids[4], request(p), ids[3], scope=scope)
                    return 'applied'
                except imports.CharacteristicImportError:
                    return 'stale'
        async def do_publish():
            async with sessions() as db:
                return await publish(db, schema, ids, cid, p1, p2)
        first_task = asyncio.create_task(do_sync() if first == 'sync' else do_publish())
        await asyncio.wait_for(locked.wait(), 5)
        second_task = asyncio.create_task(do_publish() if first == 'sync' else do_sync())
        # Event loop progress, not a serial commit->flush imitation. First holds real parent locks.
        await asyncio.wait_for(asyncio.shield(asyncio.create_task(_assert_waiting(second_task))), 5)
        release.set()
        a, b = await asyncio.wait_for(asyncio.gather(first_task, second_task), 10)
        if first == 'sync':
            assert a == 'applied' and b == {'status': 'failed', 'error': 'input_changed'}
        else:
            assert a['status'] == 'done' and b == 'stale'
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            fresh = await sync.build_sync_preview(db, ids[4], vid, scope=scope)
            if first == 'capa':
                assert any(not i['applicable'] for i in fresh['items'])
            else:
                assert not fresh['items']
    finally:
        current_tenant_schema.reset(token)

async def _assert_waiting(task):
    # Yield through several loop turns; completion here would violate the held-lock protocol.
    for _ in range(100):
        await asyncio.sleep(0.001)
    assert not task.done()

async def test_failure_after_snapshot_flush_rolls_back_all_material(sync_tenants, monkeypatch):
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, vid, p = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    original = sync.stage_cp_version
    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError('injected after version flush')
    monkeypatch.setattr(sync, 'stage_cp_version', fail)
    try:
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            with pytest.raises(RuntimeError, match='injected'):
                await sync.apply_sync_preview(db, ids[4], request(p), ids[3], scope=scope)
            await db.commit()  # prove even caller commit cannot leak nested failed writes
        async with sessions() as db:
            await tenant_scope(db, schema, ids[3])
            assert all(i.step_no == 'OP10' for i in await rows(db, ids[4]))
            cp = await db.get(ControlPlan, ids[4])
            assert cp.lock_version == 1 and cp.source_fmea_version_id == ids[6]
            assert len((await db.scalars(select(ControlPlanVersion))).all()) == 1
            assert not (await db.execute(text("SELECT 1 FROM audit_logs WHERE action='SYNC_FMEA'"))).all()
    finally:
        current_tenant_schema.reset(token)

async def test_tenant_digest_and_missing_protection_table_never_fall_back(sync_tenants):
    sessions, schemas = sync_tenants
    ids, vid, p = await prepared(sessions, schemas[0])
    ids2, vid2, p2 = await prepared(sessions, schemas[1], ids=ids)
    token = current_tenant_schema.set(schemas[1])
    try:
        async with sessions() as db:
            scope = await tenant_scope(db, schemas[1], ids[3])
            req = request(p2)
            req.preview_digest = p['preview_digest']
            with pytest.raises(imports.CharacteristicImportError):
                await sync.apply_sync_preview(db, ids[4], req, ids[3], scope=scope)
        async with sessions() as db:
            await db.execute(text(f'ALTER TABLE "{schemas[1]}".capa_docg_audit RENAME TO hidden_audit'))
            await db.commit()
        async with sessions() as db:
            scope = await tenant_scope(db, schemas[1], ids[3])
            with pytest.raises(imports.CharacteristicImportError) as exc:
                await sync.build_sync_preview(db, ids[4], vid2, scope=scope)
            assert exc.value.status_code == 404
    finally:
        current_tenant_schema.reset(token)

async def test_actual_multiphase_orchestration_refreshes_tenant_inputs_and_orders_multiple_cps(sync_tenants, monkeypatch):
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, vid, p = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    try:
        async with sessions() as db:
            await tenant_scope(db, schema, ids[3])
            other_id = uuid.uuid4()
            db.add(ControlPlan(cp_id=other_id, document_no='CP-SECOND', title='Other',
                factory_id=ids[0], product_line_code='LINE', status='draft'))
            capa = CAPAEightD(document_no='CAPA-MULTI', title='Review', factory_id=ids[0],
                             product_line_code='LINE', status='D8_GATE_PENDING')
            db.add(capa)
            await db.flush()
            cid = capa.report_id
            await db.commit()
            monkeypatch.setattr(provider_adapter, 'build_client', AsyncMock(return_value=type('Client', (), {'model': 'test'})()))
            monkeypatch.setattr(provider_adapter, 'complete_json', AsyncMock(return_value={'affected_docs': []}))
            execute = db.execute
            acquired = []
            async def tracked(stmt, *args, **kwargs):
                result = await execute(stmt, *args, **kwargs)
                if 'FROM control_plans' in str(stmt) and 'FOR UPDATE' in str(stmt):
                    acquired.append(str(stmt.compile().params['cp_id_1']))
                return result
            monkeypatch.setattr(db, 'execute', tracked)
            input_state = gate.cp_input_state
            async def strict_input_state(session, *args, **kwargs):
                path = await session.scalar(text("SHOW search_path"))
                assert 'public' not in path, 'phase handoff must retain strict tenant namespace'
                return await input_state(session, *args, **kwargs)
            monkeypatch.setattr(gate, 'cp_input_state', strict_input_state)
            result = await gate.generate_impact_analysis(db, capa, ids[3])
            assert result['status'] == 'done'
            assert not db.in_transaction()
            assert acquired == sorted([str(ids[4]), str(other_id)])
        async with sessions() as verify:
            await tenant_scope(verify, schema, ids[3])
            a = await verify.scalar(select(CapaDocgAnalysis).where(CapaDocgAnalysis.capa_id == cid))
            assert a.status == 'done' and a.is_current
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.parametrize('change', ['permission', 'reviewed'])
async def test_characteristic_publication_rechecks_current_authority_and_reviewed_material(sync_tenants, monkeypatch, change):
    from app.services.capa_review_guard import ReviewedContentLocked
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, _, _ = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    try:
        cid, p1, p2 = await running(sessions, schema, ids, monkeypatch)
        async with sessions() as db:
            if change == 'permission':
                await db.execute(text("UPDATE role_permissions SET permission_level=1 WHERE role_id=:role AND module='capa'"), {'role': ids[2]})
            else:
                await db.execute(text("UPDATE capa_eightd SET status='D8_CLOSURE' WHERE report_id=:cid"), {'cid': cid})
            await db.commit()
        async with sessions() as db:
            with pytest.raises(PermissionError if change == 'permission' else ReviewedContentLocked):
                await publish(db, schema, ids, cid, p1, p2)
            await db.rollback()
        async with sessions() as db:
            analysis = await db.get(CapaDocgAnalysis, uuid.UUID(p1['analysis_id']))
            assert analysis.status == 'running' and not analysis.is_current
            assert not (await db.scalars(select(AuditLog).where(
                AuditLog.action == 'DOC_IMPACT_ANALYZED', AuditLog.record_id == cid))).all()
    finally:
        current_tenant_schema.reset(token)


async def test_audit_locks_complete_cp_input_set_before_subset_source_locks(sync_tenants, monkeypatch):
    from sqlalchemy.exc import DBAPIError
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, _, _ = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    try:
        other_id = uuid.uuid4()
        async with sessions() as db:
            db.add(ControlPlan(cp_id=other_id, document_no='CP-OTHER-LOCK', title='Other',
                               factory_id=ids[0], product_line_code='LINE', status='draft'))
            await db.commit()
        cid, p1, p2 = await running(sessions, schema, ids, monkeypatch)
        async with sessions() as db:
            assert (await publish(db, schema, ids, cid, p1, p2))['status'] == 'done'
        original = sync.lock_version_parents_in_order
        checked = []

        async def verify_input_locks(db, identities):
            # Before locking a referenced subset, every scope CP must already be
            # locked. Otherwise another CAPA publisher can hold the lower UUID
            # and wait on the higher UUID while this audit does the reverse.
            for cp_id in sorted([ids[4], other_id], key=str):
                async with sessions() as observer:
                    with pytest.raises(DBAPIError) as error:
                        await observer.execute(select(ControlPlan.cp_id).where(
                            ControlPlan.cp_id == cp_id).with_for_update(nowait=True))
                    assert error.value.orig.sqlstate == '55P03'
                    await observer.rollback()
                checked.append(cp_id)
            await original(db, identities)

        monkeypatch.setattr(sync, 'lock_version_parents_in_order', verify_input_locks)
        async with sessions() as db:
            capa = await db.get(CAPAEightD, cid)
            result = await gate.run_audit(db, capa, ids[3])
            assert result['decision'] == 'blocked'
        assert set(checked) == {ids[4], other_id}
    finally:
        current_tenant_schema.reset(token)
