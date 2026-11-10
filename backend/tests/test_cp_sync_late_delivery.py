"""Actual worker/import/sync transactions, independent connections, guarded schemas.

Immutable approved snapshots are declared fixture preconditions from the existing
transaction fixtures. Normal browser approval paths are tested separately.
"""
import asyncio
import re
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.tenant_utils import current_tenant_schema
from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan
from app.models.cp_sync_outbox import CPSyncOutbox
from app.schemas.control_plan import ControlPlanCreate, ControlPlanUpdate, ControlPlanItemCreate
from app.services import control_plan_service as cp_service, version_service as versions
from app.services.cp_sync_worker import process_cp_sync_outbox_batch
from app.services.product_line_service import lock_candidate_scopes
from tests.test_cp_characteristic_import_transactions import isolated_tenants, seed_tenant, tenant_scope, import_request
from tests.test_cp_characteristic_sync_transactions import sync_tenants, prepared, request
from tests.test_cp_characteristic_import import rows

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def runtime(sync_tenants):
    sessions, schemas = sync_tenants
    added = ('cp_sync_outbox', 'cp_validation_runs', 'cp_validation_findings', 'cp_validation_occurrences')
    async with sessions.admin_sessions() as db:
        for schema in schemas:
            for table in added:
                await db.execute(text(f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL)'))
            for table in added:
                constraints = (await db.execute(text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid=to_regclass(:table) AND contype='f'"), {'table': 'public.' + table})).all()
                for name, definition in constraints:
                    definition = re.sub(r'REFERENCES (?:public\.)?([a-z_]+)',
                        lambda match: f'REFERENCES "{schema}"."{match[1]}"', definition)
                    await db.execute(text(f'ALTER TABLE "{schema}"."{table}" ADD CONSTRAINT "{name}" {definition}'))
                triggers = (await db.execute(text(
                    "SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid=to_regclass(:table) AND NOT tgisinternal"),
                    {'table': 'public.' + table})).scalars().all()
                for definition in triggers:
                    await db.execute(text(definition.replace(f' ON public.{table} ', f' ON "{schema}"."{table}" ')))
        await db.commit()
    token = current_tenant_schema.set(schemas[0])
    try:
        yield sessions, schemas[0]
    finally:
        current_tenant_schema.reset(token)


async def create_after_approval(sessions, schema, ids, document_no):
    # Re-check captured tenant generation on every post-commit checkout.
    async with sessions(expire_on_commit=False) as db:
        cp = await cp_service.create_control_plan(db, ControlPlanCreate(
            title='Created after approval', document_no=document_no, fmea_ref_id=ids[5], product_line_code='LINE'),
            ids[3], factory_id=ids[0])
        return cp.cp_id


async def enqueue(sessions, schema, ids, version_id):
    async with sessions() as db:
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        row = CPSyncOutbox(id=uuid.uuid4(), fmea_id=ids[5], fmea_version_id=version_id,
                          payload={'user_id': str(ids[3])})
        db.add(row)
        oid = row.id
        await db.commit()
        return oid


async def deliver(sessions, schema):
    async with sessions() as db:
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        return await process_cp_sync_outbox_batch(db)


async def apply(sessions, schema, ids, preview, keys=None):
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        return await versions.apply_sync_preview(db, ids[4], request(preview, keys), ids[3], scope=scope)


async def state(sessions, schema, ids, event_id):
    async with sessions() as db:
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        cp = await db.get(ControlPlan, ids[4])
        row = await db.get(CPSyncOutbox, event_id)
        audits = list((await db.scalars(select(AuditLog).where(
            AuditLog.record_id == ids[4], AuditLog.action == 'UPDATE',
            AuditLog.changed_fields.op('?')('trigger_fmea_version_id')))).all())
        return cp.sync_pending, cp.source_fmea_version_id, row.status, audits


@pytest.mark.parametrize('event_source', ['same', 'older'])
async def test_late_event_after_real_sync_cannot_restore_pending(runtime, event_source):
    sessions, schema = runtime
    ids, v2, preview = await prepared(sessions, schema)
    await apply(sessions, schema, ids, preview)
    event_id = await enqueue(sessions, schema, ids, v2 if event_source == 'same' else ids[6])
    assert await deliver(sessions, schema) == 1
    pending, accepted, status, audits = await state(sessions, schema, ids, event_id)
    assert pending is False
    assert accepted == v2 and status == 'completed' and audits == []
    assert await deliver(sessions, schema) == 0


async def test_cp_created_and_imported_after_approval_is_not_reopened_by_late_worker(runtime):
    sessions, schema = runtime
    ids, body = await seed_tenant(sessions, schema)
    new_id = await create_after_approval(sessions, schema, ids, 'CP-LATE')
    ids = list(ids); ids[4] = new_id
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        req = await import_request(db, ids, body, scope)
        await cp_service.import_from_fmea(db, new_id, req, ids[3], scope=scope)
    event_id = await enqueue(sessions, schema, ids, ids[6])
    await deliver(sessions, schema)
    pending, accepted, status, audits = await state(sessions, schema, ids, event_id)
    assert pending is False and accepted == ids[6] and status == 'completed' and audits == []


async def test_genuinely_newer_worker_first_marks_once_then_real_sync_clears(runtime):
    sessions, schema = runtime
    ids, v2, preview = await prepared(sessions, schema)
    event_id = await enqueue(sessions, schema, ids, v2)
    assert await deliver(sessions, schema) == 1
    pending, accepted, status, audits = await state(sessions, schema, ids, event_id)
    assert pending and accepted == ids[6] and status == 'completed' and len(audits) == 1
    assert set(audits[0].changed_fields) == {'sync_pending', 'trigger_fmea_version_id'}
    assert await deliver(sessions, schema) == 0
    await apply(sessions, schema, ids, preview)
    assert (await state(sessions, schema, ids, event_id))[:3] == (False, v2, 'completed')


@pytest.mark.parametrize('selection', ['partial_import', 'no_import', 'partial_sync'])
async def test_partial_or_unknown_baselines_remain_conservative(runtime, selection):
    sessions, schema = runtime
    if selection == 'partial_sync':
        ids, target, preview = await prepared(sessions, schema)
        await apply(sessions, schema, ids, preview, [preview['items'][0]['candidate_key']])
    else:
        ids, body = await seed_tenant(sessions, schema)
        target = ids[6]
        if selection == 'no_import':
            new_id = await create_after_approval(sessions, schema, ids, 'CP-UNKNOWN')
            ids = list(ids); ids[4] = new_id
        if selection == 'partial_import':
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                req = await import_request(db, ids, body, scope)
                req.selected_candidate_keys = req.selected_candidate_keys[:1]
                await cp_service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
    event_id = await enqueue(sessions, schema, ids, target)
    await deliver(sessions, schema)
    pending, accepted, status, audits = await state(sessions, schema, ids, event_id)
    assert pending and status == 'completed'
    # Partial import now persists pending atomically, so the worker must not renotify.
    assert len(audits) == (1 if selection == 'no_import' else 0)


async def test_worker_waits_on_parent_protocol_and_rereads_after_real_sync(runtime):
    sessions, schema = runtime
    ids, v2, preview = await prepared(sessions, schema)
    event_id = await enqueue(sessions, schema, ids, v2)
    worker_ready = asyncio.Queue()

    async def worker():
        # Match the real worker's expire_on_commit=False while retaining the
        # loaded instance; refresh must occur before its actual commit.
        async with sessions(expire_on_commit=False) as db:
            await db.execute(text(f'SET search_path TO "{schema}", public'))
            # Deliberately stale ORM object must never overwrite a later clear.
            stale = await db.get(ControlPlan, ids[4])
            assert stale.source_fmea_version_id == ids[6]
            await worker_ready.put(await db.scalar(text('SELECT pg_backend_pid()')))
            count = await process_cp_sync_outbox_batch(db)
            assert stale.source_fmea_version_id == v2
            return count

    task = None
    try:
        async with sessions() as writer:
            scope = await tenant_scope(writer, schema, ids[3])
            await lock_candidate_scopes(writer, [(ids[0], 'LINE')])
            await versions.lock_version_parents_in_order(writer, [('control_plan', ids[4])])
            task = asyncio.create_task(worker())
            pid = await asyncio.wait_for(worker_ready.get(), 5)
            async def actually_blocked():
                async with sessions() as observer:
                    while not task.done():
                        if await observer.scalar(text('SELECT cardinality(pg_blocking_pids(:pid)) > 0'), {'pid': pid}):
                            return True
                        await asyncio.sleep(0.01)
                return False
            assert await asyncio.wait_for(actually_blocked(), 5), 'worker did not serialize with the actual writer mutex'
            await versions.apply_sync_preview(writer, ids[4], request(preview), ids[3], scope=scope)
        assert await asyncio.wait_for(task, 5) == 1
        pending, accepted, status, audits = await state(sessions, schema, ids, event_id)
        assert pending is False and accepted == v2 and status == 'completed' and audits == []
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def imported_baseline(sessions, schema):
    ids, body = await seed_tenant(sessions, schema)
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        req = await import_request(db, ids, body, scope)
        await cp_service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
    return ids


async def permitted_override(sessions, schema, ids):
    from tests.test_cp_characteristic_import import IDS
    async with sessions(expire_on_commit=False) as db:
        cp = await cp_service.get_control_plan(db, ids[4])
        items = [ControlPlanItemCreate(**{name: getattr(item, name) for name in ControlPlanItemCreate.model_fields}) for item in cp.items]
        selected = next(item for item in cp.items if item.source_characteristic_ref['characteristic_id'] == IDS[0])
        next(item for item in items if item.item_id == selected.item_id).specification_tolerance = 'SIMULATED permitted local criterion'
        item_id = selected.item_id
        before_tasks = set(asyncio.all_tasks())
        await cp_service.update_control_plan(db, cp, ControlPlanUpdate(items=items, lock_version=cp.lock_version), ids[3])
        validation = [task for task in asyncio.all_tasks() - before_tasks
                      if '_run_validation_background' in task.get_coro().__qualname__]
        await asyncio.gather(*validation)
        assert await db.scalar(text('SELECT status FROM cp_validation_runs WHERE cp_id=:id ORDER BY started_at DESC LIMIT 1'), {'id': ids[4]}) == 'completed'
        return item_id


async def fixture_approved_target(sessions, schema, ids, *, conflicting=False):
    # A new immutable approved snapshot is fixture input, not a forged CP marker.
    # CP edits, source preview, explicit acceptance and worker delivery below are
    # all the real application services and real commits.
    from tests.test_cp_characteristic_import import graph
    from app.models.fmea import FMEADocument
    async with sessions(expire_on_commit=False) as db:
        source = await db.get(FMEADocument, ids[5])
        changed = graph()
        if conflicting:
            changed['nodes'][2]['characteristics'][0]['specification'] = 'Changed source criterion'
        else:
            changed['nodes'][2]['characteristics'][1]['name'] = 'V2 different characteristic'
        source.graph_data = changed
        version = await versions.create_fmea_version(db, source, 'approve', 'R2 immutable fixture target', ids[3])
        return version.version_id


@pytest.mark.parametrize('event_source', ['same', 'older_after_other_source_change'])
async def test_acknowledged_unchanged_source_override_is_not_reopened(runtime, event_source):
    sessions, schema = runtime
    ids = await imported_baseline(sessions, schema)
    item_id = await permitted_override(sessions, schema, ids)
    target_id = ids[6]
    if event_source != 'same':
        target_id = await fixture_approved_target(sessions, schema, ids)
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            preview = await versions.build_sync_preview(db, ids[4], target_id, scope=scope)
            assert len(preview['items']) == 1 and preview['items'][0]['applicable']
            assert any(issue['code'] == 'local_source_override' and not issue['blocking'] for issue in preview['issues'])
            await versions.apply_sync_preview(db, ids[4], request(preview), ids[3], scope=scope)
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        preview = await versions.build_sync_preview(db, ids[4], target_id, scope=scope)
        assert preview['items'] == []
        assert any(issue['code'] == 'local_source_override' and not issue['blocking'] for issue in preview['issues'])
        # Real explicit no-op acknowledgment, never a directly stamped marker.
        await versions.apply_sync_preview(db, ids[4], request(preview, []), ids[3], scope=scope)
    event_id = await enqueue(sessions, schema, ids, ids[6])
    assert await deliver(sessions, schema) == 1
    pending, accepted, status, audits = await state(sessions, schema, ids, event_id)
    assert pending is False and accepted == target_id and status == 'completed' and audits == []
    async with sessions() as db:
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        from app.models.control_plan import ControlPlanItem
        row = await db.get(ControlPlanItem, item_id)
        assert row.specification_tolerance == 'SIMULATED permitted local criterion'
        assert row.source_characteristic_ref['accepted_source_version_id'] == str(ids[6])


async def test_changed_source_conflict_after_local_override_still_needs_update(runtime):
    sessions, schema = runtime
    ids = await imported_baseline(sessions, schema)
    await permitted_override(sessions, schema, ids)
    v2 = await fixture_approved_target(sessions, schema, ids, conflicting=True)
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        preview = await versions.build_sync_preview(db, ids[4], v2, scope=scope)
        assert any(not item['applicable'] and any(c['code'] == 'three_way_conflict' for c in item['conflicts']) for item in preview['items'])
        with pytest.raises(cp_service.CharacteristicImportError):
            await versions.apply_sync_preview(db, ids[4], request(preview, []), ids[3], scope=scope)
    event_id = await enqueue(sessions, schema, ids, v2)
    await deliver(sessions, schema)
    pending, accepted, status, audits = await state(sessions, schema, ids, event_id)
    assert pending is True and accepted == ids[6] and status == 'completed' and len(audits) == 1


async def test_worker_consumed_before_new_cp_partial_import_reload_and_completion(runtime):
    sessions, schema = runtime
    ids, body = await seed_tenant(sessions, schema)
    event_id = await enqueue(sessions, schema, ids, ids[6])
    assert await deliver(sessions, schema) == 1
    new_id = await create_after_approval(sessions, schema, ids, "CP-PARTIAL-WORKER-FIRST")
    ids = list(ids); ids[4] = new_id
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        req = await import_request(db, ids, body, scope)
        req.selected_candidate_keys = req.selected_candidate_keys[:1]
        await cp_service.import_from_fmea(db, new_id, req, ids[3], scope=scope)
    assert (await state(sessions, schema, ids, event_id))[0] is True
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        remaining = await versions.build_sync_preview(db, new_id, ids[6], scope=scope)
        assert len(remaining["items"]) == 4
        stored = await rows(db, new_id)
        assert len(stored) == 1
        assert stored[0].source_characteristic_ref["accepted_source_version_id"] == str(ids[6])
    await apply(sessions, schema, ids, remaining)
    assert (await state(sessions, schema, ids, event_id))[:3] == (False, ids[6], "completed")
    async with sessions() as db:
        await tenant_scope(db, schema, ids[3])
        assert len(await rows(db, new_id)) == 5


async def test_historical_full_import_keeps_newer_delivered_approval_pending(runtime):
    sessions, schema = runtime
    ids, v2, _ = await prepared(sessions, schema)
    new_id = await create_after_approval(sessions, schema, ids, "CP-HISTORICAL-IMPORT")
    ids = list(ids); ids[4] = new_id
    event_id = await enqueue(sessions, schema, ids, v2)
    assert await deliver(sessions, schema) == 1
    assert (await state(sessions, schema, ids, event_id))[0] is True
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        body = {"fmea_id": str(ids[5]), "source_fmea_version_id": str(ids[6]), "expected_lock_version": 0, "step_ids": ["s1"]}
        req = await import_request(db, ids, body, scope)
        await cp_service.import_from_fmea(db, new_id, req, ids[3], scope=scope)
    assert (await state(sessions, schema, ids, event_id))[:3] == (True, ids[6], "completed")
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        stored = await rows(db, new_id)
        assert len(stored) == 5
        assert all(r.source_characteristic_ref["accepted_source_version_id"] == str(ids[6]) for r in stored)
        assert all(r.step_no == "OP10" for r in stored)
        current = await versions.build_sync_preview(db, new_id, v2, scope=scope)
    await apply(sessions, schema, ids, current)
    assert (await state(sessions, schema, ids, event_id))[:3] == (False, v2, "completed")


@pytest.mark.parametrize("delivered_first", [True, False])
async def test_historical_noop_sync_preserves_newer_approval_obligation(runtime, delivered_first):
    sessions, schema = runtime
    ids, v2, current = await prepared(sessions, schema)
    event_id = await enqueue(sessions, schema, ids, v2)
    if delivered_first:
        assert await deliver(sessions, schema) == 1
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        old = await versions.build_sync_preview(db, ids[4], ids[6], scope=scope)
        assert old["items"] == []
    await apply(sessions, schema, ids, old, [])
    pending, baseline, _, _ = await state(sessions, schema, ids, event_id)
    assert pending is True and baseline == ids[6]
    async with sessions() as db:
        scope = await tenant_scope(db, schema, ids[3])
        assert all(r.source_characteristic_ref["accepted_source_version_id"] == str(ids[6]) for r in await rows(db, ids[4]))
        current = await versions.build_sync_preview(db, ids[4], v2, scope=scope)
    await apply(sessions, schema, ids, current)
    assert (await state(sessions, schema, ids, event_id))[:2] == (False, v2)
    if not delivered_first:
        assert await deliver(sessions, schema) == 1
        assert (await state(sessions, schema, ids, event_id))[:3] == (False, v2, "completed")
