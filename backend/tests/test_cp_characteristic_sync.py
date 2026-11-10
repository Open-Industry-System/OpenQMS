"""Per-characteristic approved-snapshot synchronization through real APIs."""
import uuid
import pytest
from tests.test_cp_characteristic_import import documents, graph, IDS, preview, apply, rows
from app.services.version_service import create_fmea_version

pytestmark = pytest.mark.asyncio

async def seed(client, documents):
    p = (await preview(client, documents)).json()
    r = await apply(client, documents, p)
    assert r.status_code == 200, r.text

async def target(db, documents, user, changed=None):
    cp, fmea, _ = documents
    fmea.graph_data = changed or graph()
    return await create_fmea_version(db, fmea, 'approve', 'Target', user.user_id)

async def sync_preview(client, cp, version=None):
    return await client.get(f'/api/control-plans/{cp.cp_id}/sync-preview', params=(
        {'source_fmea_version_id': str(version.version_id)} if version else {}))

async def sync_apply(client, cp, p, keys=None, **changes):
    body = {k: p[k] for k in ('source_fmea_version_id', 'expected_lock_version', 'preview_digest')}
    body['selected_candidate_keys'] = keys if keys is not None else [i['candidate_key'] for i in p['items'] if i['applicable']]
    body.update(changes)
    return await client.post(f'/api/control-plans/{cp.cp_id}/sync-from-fmea', json=body)

async def test_five_real_rows_clears_rename_delete_step_and_stable_add(db, admin_client, documents, admin_user):
    cp, fmea, _ = documents
    original_graph = graph()
    original_graph['nodes'][2]['characteristics'][1]['classification'] = 'SC'
    fmea.graph_data = original_graph
    baseline = await create_fmea_version(db, fmea, 'approve', 'Classified baseline', admin_user.user_id)
    documents = (cp, fmea, baseline)
    await seed(admin_client, documents)
    cp, _, baseline = documents
    before = await rows(db, cp.cp_id)
    ids = [str(r.item_id) for r in before]
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    g['nodes'][2]['characteristics'][0]['name'] = '改名'
    g['nodes'][2]['characteristics'][0]['specification'] = None
    g['nodes'][2]['characteristics'][1]['classification'] = None
    g['nodes'][3]['characteristics'].pop()
    g['nodes'][3]['characteristics'].append({'id': str(uuid.uuid4()), 'kind': 'process', 'name': '新增'})
    v = await target(db, documents, admin_user, g)
    r = await sync_preview(admin_client, cp, v)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p['source_fmea_version_id'] == str(v.version_id)
    assert {i['item_id'] for i in p['items'] if i['item_id']} == set(ids)
    assert len(p['items']) == 6
    add = next(i for i in p['items'] if i['action'] == 'add')
    assert add['item_id'] is None
    p2 = (await sync_preview(admin_client, cp, v)).json()
    assert p2['preview_digest'] == p['preview_digest']
    assert next(i for i in p2['items'] if i['action'] == 'add')['candidate_key'] == add['candidate_key']
    first = next(i for i in p['items'] if i['item_id'] == ids[0])
    assert first['merged_value']['specification_tolerance'] is None
    assert first['merged_value']['step_no'] == 'OP20'
    applied = await sync_apply(admin_client, cp, p)
    assert applied.status_code == 200, applied.text
    after = await rows(db, cp.cp_id)
    assert len(after) == 5
    assert after[0].item_id == before[0].item_id
    assert after[0].product_characteristic == '改名'
    assert after[0].specification_tolerance is None
    assert after[1].special_class is None
    assert all(r.step_no == 'OP20' for r in after)
    assert all(r.source_characteristic_ref['accepted_source_version_id'] == str(v.version_id) for r in after)
    assert (await sync_preview(admin_client, cp, v)).json()['items'] == []
    assert cp.sync_pending is False and cp.source_fmea_version_id == v.version_id

async def test_partial_baselines_multiple_controls_and_manual_preservation(db, admin_client, documents, admin_user):
    from app.models.control_plan import ControlPlanItem
    await seed(admin_client, documents)
    cp, _, original = documents
    initial = await rows(db, cp.cp_id)
    row = initial[0]
    row.control_method, row.evaluation_method = 'manual control', 'manual evaluation'
    row.sample_size, row.sample_frequency, row.reaction_plan = '5', 'hourly', 'stop'
    duplicate = ControlPlanItem(cp_id=cp.cp_id, factory_id=cp.factory_id, sort_order=10,
        source_fmea_node_id=row.source_fmea_node_id, source_characteristic_ref=dict(row.source_characteristic_ref),
        **{f: getattr(row, f) for f in ('step_no', 'process_name', 'equipment', 'product_characteristic',
                                      'process_characteristic', 'special_class', 'specification_tolerance')})
    db.add(duplicate)
    await db.flush()
    g = graph()
    g['nodes'][2]['characteristics'][0]['name'] = 'V2'
    v2 = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v2)).json()
    assert len(p['items']) == 2 and {i['item_id'] for i in p['items']} == {str(row.item_id), str(duplicate.item_id)}
    r = await sync_apply(admin_client, cp, p, [p['items'][0]['candidate_key']])
    assert r.status_code == 200, r.text
    assert cp.sync_pending and cp.source_fmea_version_id == original.version_id
    await db.refresh(row)
    assert row.source_characteristic_ref['accepted_source_version_id'] == str(v2.version_id)
    assert duplicate.source_characteristic_ref['accepted_source_version_id'] == str(original.version_id)
    assert (row.control_method, row.evaluation_method, row.sample_size, row.sample_frequency, row.reaction_plan) == (
        'manual control', 'manual evaluation', '5', 'hourly', 'stop')
    g['nodes'][2]['characteristics'][0]['specification'] = 'V3 specification'
    v3 = await target(db, documents, admin_user, g)
    p3 = (await sync_preview(admin_client, cp, v3)).json()
    assert len(p3['items']) == 2
    assert all(i['applicable'] and not i['conflicts'] for i in p3['items'])
    assert {i['base_value']['product_characteristic'] for i in p3['items']} == {'V2', '孔距'}
    assert (await sync_apply(admin_client, cp, p3)).status_code == 200
    assert cp.source_fmea_version_id == v3.version_id and not cp.sync_pending

async def test_three_way_conflict_missing_baseline_and_legacy_never_rebound(db, admin_client, documents, admin_user):
    from app.models.control_plan import ControlPlanItem
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    initial[0].product_characteristic = 'local'
    ref = dict(initial[1].source_characteristic_ref)
    ref['accepted_source_version_id'] = None
    initial[1].source_characteristic_ref = ref
    legacy = ControlPlanItem(cp_id=cp.cp_id, factory_id=cp.factory_id, source_fmea_node_id='missing-step',
                             product_characteristic='legacy', sort_order=9)
    db.add(legacy)
    await db.flush()
    g = graph()
    g['nodes'][2]['characteristics'][0]['name'] = 'remote'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert {c['code'] for i in p['items'] for c in i['conflicts']} == {'three_way_conflict', 'baseline_unavailable'}
    assert any(i['code'] == 'manual_or_legacy_source' and i['item_id'] == str(legacy.item_id) for i in p['issues'])
    assert not any(i['item_id'] == str(legacy.item_id) for i in p['items'])
    assert (await sync_apply(admin_client, cp, p, [p['items'][0]['candidate_key']])).status_code == 409
    assert initial[0].product_characteristic == 'local'

async def test_old_uuid_selection_and_stale_digest_rejected(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    g = graph()
    g['nodes'][0]['process_number'] = 'OP99'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    old = await admin_client.post(f'/api/control-plans/{cp.cp_id}/sync-from-fmea', json={'selected_item_ids': [p['items'][0]['item_id']]})
    assert old.status_code == 409
    initial = await rows(db, cp.cp_id)
    initial[0].sample_size = 'changed without lock bump'
    await db.flush()
    assert (await sync_apply(admin_client, cp, p)).status_code == 409
    fresh = (await sync_preview(admin_client, cp, v)).json()
    assert (await sync_apply(admin_client, cp, fresh)).status_code == 200
    assert (await sync_apply(admin_client, cp, fresh)).status_code == 409

async def test_stale_check_uses_exact_approved_source_not_current_graph(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    assert (await admin_client.get(f'/api/control-plans/{cp.cp_id}/stale-check')).json()['stale_items'] == []
    g = graph()
    g['nodes'][2]['characteristics'][0]['specification'] = ''
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    s = await admin_client.get(f'/api/control-plans/{cp.cp_id}/stale-check', params={'source_fmea_version_id': str(v.version_id)})
    assert s.status_code == 200, s.text
    assert [{k: i[k] for k in ('item_id', 'action', 'diff_fields', 'merged_value')} for i in s.json()['stale_items']] == [
        {k: i[k] for k in ('item_id', 'action', 'diff_fields', 'merged_value')} for i in p['items']]
    assert p['items'][0]['merged_value']['specification_tolerance'] == ''

async def test_api_failure_after_staged_snapshot_leaves_no_partial_sync(db, admin_client, documents, admin_user, monkeypatch):
    from sqlalchemy import select
    from app.models.control_plan_version import ControlPlanVersion
    from app.models.audit import AuditLog
    from app.services import version_service
    await seed(admin_client, documents)
    cp, _, original = documents
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    before_versions = list((await db.scalars(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))).all())
    stage = version_service.stage_cp_version
    async def fail(*args, **kwargs):
        await stage(*args, **kwargs)
        raise RuntimeError('api injected failure after snapshot')
    monkeypatch.setattr(version_service, 'stage_cp_version', fail)
    with pytest.raises(RuntimeError, match='api injected'):
        await sync_apply(admin_client, cp, p)
    await db.refresh(cp)
    assert cp.lock_version == 1 and cp.source_fmea_version_id == original.version_id
    assert all(r.step_no == 'OP10' for r in await rows(db, cp.cp_id))
    assert len((await db.scalars(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))).all()) == len(before_versions)
    assert not (await db.scalars(select(AuditLog).where(AuditLog.record_id == cp.cp_id, AuditLog.action == 'SYNC_FMEA'))).all()

async def test_local_only_source_override_is_visible_without_auto_overwrite(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, original = documents
    initial = await rows(db, cp.cp_id)
    initial[0].specification_tolerance = 'Local permitted specification'
    await db.flush()
    p = (await sync_preview(admin_client, cp, original)).json()
    assert not p['items']
    assert any(i['code'] == 'local_source_override' for i in p['issues'])
    s = (await admin_client.get(f'/api/control-plans/{cp.cp_id}/stale-check')).json()['stale_items']
    assert s[0]['item_id'] == str(initial[0].item_id) and s[0]['diff_fields'] == ['specification_tolerance']
    assert (await sync_apply(admin_client, cp, p, [])).status_code == 200
    assert initial[0].specification_tolerance == 'Local permitted specification'

async def test_unchanged_fields_with_inconsistent_work_element_baseline_cannot_acknowledge(
    db, admin_client, documents, admin_user,
):
    from copy import deepcopy
    from sqlalchemy import select
    from app.models.control_plan_version import ControlPlanVersion
    await seed(admin_client, documents)
    cp, _, original = documents
    initial = await rows(db, cp.cp_id)
    process_rows = initial[2:]
    for row in process_rows:
        row.source_characteristic_ref = {**row.source_characteristic_ref, 'work_element_id': 'w2'}
    cp.sync_pending = True
    await db.flush()
    original_refs = {str(r.item_id): deepcopy(r.source_characteristic_ref) for r in process_rows}
    lock = cp.lock_version
    versions = list((await db.scalars(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))).all())
    g = graph()
    # Replace the sole Machine identity, not its name or any projected value.
    g['nodes'][1]['id'] = 'w2'
    for edge in g['edges']:
        for endpoint in ('source', 'target'):
            if edge[endpoint] == 'w1':
                edge[endpoint] = 'w2'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert (await sync_apply(admin_client, cp, p, [])).status_code == 409
    assert {i['item_id'] for i in p['items']} == set(original_refs)
    assert all(i['base_value'] == i['fmea_new_value'] for i in p['items'])
    assert all(not i['applicable'] and any(c['code'] == 'baseline_unavailable' for c in i['conflicts'])
               for i in p['items'])
    assert (await sync_apply(admin_client, cp, p, [i['candidate_key'] for i in p['items']])).status_code == 409
    await db.refresh(cp)
    assert cp.sync_pending and cp.source_fmea_version_id == original.version_id and cp.lock_version == lock
    again = (await sync_preview(admin_client, cp, v)).json()
    assert again['preview_digest'] == p['preview_digest']
    for row in process_rows:
        await db.refresh(row)
        assert row.source_characteristic_ref == original_refs[str(row.item_id)]
    assert len((await db.scalars(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))).all()) == len(versions)


async def test_unit_only_source_update_is_shared_by_import_sync_and_stale_check(db, admin_client, documents, admin_user):
    cp, fmea, original = documents
    await seed(admin_client, documents)
    initial = await rows(db, cp.cp_id)
    item_id = initial[0].item_id
    original_value = initial[0].specification_tolerance
    g = graph()
    g['nodes'][2]['characteristics'][0]['unit'] = 'mm'
    v2 = await target(db, documents, admin_user, g)
    preview = (await sync_preview(admin_client, cp, v2)).json()
    assert len(preview['items']) == 1
    candidate = preview['items'][0]
    assert candidate['item_id'] == str(item_id)
    assert candidate['base_value']['specification_tolerance'] == original_value
    assert candidate['merged_value']['specification_tolerance'] == '10±0.1 mm'
    assert candidate['applicable'] and not candidate['conflicts']
    stale = await admin_client.get(f'/api/control-plans/{cp.cp_id}/stale-check', params={'source_fmea_version_id': str(v2.version_id)})
    assert stale.status_code == 200, stale.text
    assert any(i['item_id'] == str(item_id) for i in stale.json()['stale_items'])
    applied = await sync_apply(admin_client, cp, preview)
    assert applied.status_code == 200, applied.text
    readback = (await admin_client.get(f'/api/control-plans/{cp.cp_id}')).json()
    item = next(i for i in readback['items'] if i['item_id'] == str(item_id))
    assert item['specification_tolerance'] == '10±0.1 mm'
    assert item['source_characteristic_ref']['accepted_source_version_id'] == str(v2.version_id)
    assert (await sync_preview(admin_client, cp, v2)).json()['items'] == []
    # Explicit clearing stays empty despite a retained unit: no unit-only criterion.
    g['nodes'][2]['characteristics'][0]['specification'] = None
    v3 = await target(db, documents, admin_user, g)
    clear = (await sync_preview(admin_client, cp, v3)).json()
    assert clear['items'][0]['merged_value']['specification_tolerance'] is None
    assert (await sync_apply(admin_client, cp, clear)).status_code == 200
