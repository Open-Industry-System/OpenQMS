"""Independent-session permission, review and reverse-link publication races."""
import asyncio
import uuid
import pytest
from sqlalchemy import select, text
from app.core.tenant_utils import current_tenant_schema
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.capa import CAPAEightD
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.models.special_characteristic import SpecialCharacteristic
from app.services import version_service as sync, control_plan_service as imports, capa_doc_gate_service as gate
from app.services import special_characteristic_service as scs
from app.services.permission_service import update_role_permissions
from tests.test_cp_characteristic_import_transactions import tenant_scope, isolated_tenants
from tests.test_cp_characteristic_import import rows
from tests.test_cp_characteristic_sync_transactions import sync_tenants, prepared, request, running, publish, _assert_waiting

pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize('first', ['sync', 'permission'])
async def test_actual_permission_delete_insert_interlocks_with_sync(sync_tenants, monkeypatch, first):
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, vid, p = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    held, release = asyncio.Event(), asyncio.Event()
    tasks = []
    original = sync.stage_cp_version
    if first == 'sync':
        async def paused(*args, **kwargs):
            result = await original(*args, **kwargs)
            held.set()
            await release.wait()
            return result
        monkeypatch.setattr(sync, 'stage_cp_version', paused)
    async def do_sync():
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            try:
                await sync.apply_sync_preview(db, ids[4], request(p), ids[3], scope=scope)
                return 'applied'
            except imports.CharacteristicImportError as exc:
                assert exc.status_code == 403
                return 'denied'
    async def revoke():
        async with sessions() as db:
            await db.execute(text(f'SET search_path TO "{schema}", public'))
            execute = db.execute
            async def paused_delete(stmt, *args, **kwargs):
                result = await execute(stmt, *args, **kwargs)
                if str(stmt).startswith('DELETE FROM role_permissions') and first == 'permission':
                    held.set()
                    await release.wait()
                return result
            monkeypatch.setattr(db, 'execute', paused_delete)
            await update_role_permissions(db, 'importer', [
                {'module': 'planning', 'level': 2}, {'module': 'fmea', 'level': 0}])
            await db.commit()
            return 'revoked'
    try:
        tasks.append(asyncio.create_task(do_sync() if first == 'sync' else revoke()))
        await asyncio.wait_for(held.wait(), 5)
        tasks.append(asyncio.create_task(revoke() if first == 'sync' else do_sync()))
        await _assert_waiting(tasks[1])
        release.set()
        result = await asyncio.wait_for(asyncio.gather(*tasks), 10)
        assert result == (['applied', 'revoked'] if first == 'sync' else ['revoked', 'denied'])
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            with pytest.raises(imports.CharacteristicImportError) as exc:
                await sync.build_sync_preview(db, ids[4], vid, scope=scope)
            assert exc.value.status_code == 403
            actual = await rows(db, ids[4])
            assert all(i.step_no == ('OP20' if first == 'sync' else 'OP10') for i in actual)
    finally:
        release.set()
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        current_tenant_schema.reset(token)

@pytest.mark.parametrize('first', ['sync', 'link'])
async def test_readonly_characteristic_consumer_and_source_delete_both_orders(sync_tenants, monkeypatch, first):
    # Task 9 canonical trace is derived, not a legacy step-wide SC link write.
    # Keep the real CP-parent serialization proof in both transaction orders.
    from tests.test_cp_characteristic_import import IDS
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, vid, p = await prepared(sessions, schema, deletion=True)
    token = current_tenant_schema.set(schema)
    held, release = asyncio.Event(), asyncio.Event()
    tasks = []
    async with sessions() as db:
        await tenant_scope(db, schema, ids[3])
        source = SpecialCharacteristic(sc_id=uuid.uuid4(), sc_code="LINK-RACE", sc_name="Linked", sc_type="CC",
            source_fmea_id=ids[5], source_node_id="wf1", source_characteristic_id=uuid.UUID(IDS[4]),
            source_type="PFMEA", factory_id=ids[0], product_line_code="LINE")
        db.add(source)
        await db.commit()
    original = sync.stage_cp_version
    if first == "sync":
        async def paused(*args, **kwargs):
            result = await original(*args, **kwargs)
            held.set()
            await release.wait()
            return result
        monkeypatch.setattr(sync, "stage_cp_version", paused)
    async def do_sync():
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            await sync.apply_sync_preview(db, ids[4], request(p), ids[3], scope=scope)
            return "applied"
    async def consume():
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            execute = db.execute
            async def paused_parent(stmt, *args, **kwargs):
                result = await execute(stmt, *args, **kwargs)
                if first == "link" and "FROM control_plans" in str(stmt) and "FOR UPDATE" in str(stmt):
                    held.set()
                    await release.wait()
                return result
            monkeypatch.setattr(db, "execute", paused_parent)
            await scs.sync_to_cp(db, ids[4], ids[3], scope=scope)
            return "read_only"
    try:
        tasks.append(asyncio.create_task(do_sync() if first == "sync" else consume()))
        await asyncio.wait_for(held.wait(), 5)
        tasks.append(asyncio.create_task(consume() if first == "sync" else do_sync()))
        await _assert_waiting(tasks[1])
        release.set()
        result = await asyncio.wait_for(asyncio.gather(*tasks), 10)
        assert result == (["applied", "read_only"] if first == "sync" else ["read_only", "applied"])
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            sc = await db.scalar(select(SpecialCharacteristic))
            assert sc.cp_item_id is None
            chain = await scs.get_traceability_chain(db, sc.sc_id, scope=scope)
            assert chain["control_plan_items"] == []
    finally:
        release.set()
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        current_tenant_schema.reset(token)

@pytest.mark.parametrize('writer', ['audit', 'defer'])
async def test_actual_review_replacement_holds_cp_parent_and_expires_sync_preview(sync_tenants, monkeypatch, writer):
    from datetime import date
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, vid, _ = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    held, release = asyncio.Event(), asyncio.Event()
    tasks = []
    try:
        cid, p1, p2 = await running(sessions, schema, ids, monkeypatch)
        async with sessions() as db:
            assert (await publish(db, schema, ids, cid, p1, p2))['status'] == 'done'
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            p = await sync.build_sync_preview(db, ids[4], vid, scope=scope)
            keys = [i['candidate_key'] for i in p['items'] if i['applicable']]
            assert len(keys) == 4
        original = gate.lock_analysis_inputs
        async def paused(*args, **kwargs):
            await original(*args, **kwargs)
            held.set()
            await release.wait()
        monkeypatch.setattr(gate, 'lock_analysis_inputs', paused)
        async def review():
            async with sessions() as db:
                await tenant_scope(db, schema, ids[3])
                capa = await db.get(CAPAEightD, cid)
                if writer == 'audit':
                    return await gate.run_audit(db, capa, ids[3])
                return await gate.record_defer(db, capa, 'Review', ids[3], date.today(), ids[3])
        async def apply():
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                with pytest.raises(imports.CharacteristicImportError) as exc:
                    await sync.apply_sync_preview(db, ids[4], request(p, keys), ids[3], scope=scope)
                assert exc.value.status_code == 409
        tasks.append(asyncio.create_task(review()))
        await asyncio.wait_for(held.wait(), 5)
        tasks.append(asyncio.create_task(apply()))
        await _assert_waiting(tasks[1])
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 10)
    finally:
        release.set()
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        current_tenant_schema.reset(token)

async def test_committed_capa_close_rechecked_without_root_lock(sync_tenants, monkeypatch):
    sessions, schemas = sync_tenants
    schema = schemas[0]
    ids, vid, _ = await prepared(sessions, schema)
    token = current_tenant_schema.set(schema)
    try:
        cid, p1, p2 = await running(sessions, schema, ids, monkeypatch)
        async with sessions() as db:
            assert (await publish(db, schema, ids, cid, p1, p2))['status'] == 'done'
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            p = await sync.build_sync_preview(db, ids[4], vid, scope=scope)
        async with sessions() as closer:
            await tenant_scope(closer, schema, ids[3])
            await closer.execute(text("UPDATE capa_eightd SET status='D8_CLOSURE' WHERE report_id=:id"), {'id': cid})
            await closer.commit()
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            with pytest.raises(imports.CharacteristicImportError):
                await sync.apply_sync_preview(db, ids[4], request(p), ids[3], scope=scope)
            fresh = await sync.build_sync_preview(db, ids[4], vid, scope=scope)
            assert all(i['applicable'] for i in fresh['items'])
            await sync.apply_sync_preview(db, ids[4], request(fresh), ids[3], scope=scope)
    finally:
        current_tenant_schema.reset(token)
