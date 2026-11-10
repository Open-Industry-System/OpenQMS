"""Conservative current-material protection, exercised at sync API boundary."""
from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import select
from tests.test_cp_characteristic_import import documents, graph, rows
from tests.test_cp_characteristic_sync import seed, target, sync_preview, sync_apply
from app.models.capa import CAPAEightD
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision
from app.models.control_plan_version import ControlPlanVersion
from app.models.special_characteristic import SpecialCharacteristic
from app.services import capa_doc_gate_service as gate

pytestmark = pytest.mark.asyncio

async def material(db, cp, user, item_id=None, status='D8_GATE_PENDING', docs=None):
    capa = CAPAEightD(report_id=uuid.uuid4(), document_no='CP-PROTECT-'+uuid.uuid4().hex[:10],
        title='Do not disclose this CAPA', factory_id=cp.factory_id,
        product_line_code=cp.product_line_code, status=status)
    db.add(capa)
    await db.flush()
    affected = docs if docs is not None else [{'doc_type': 'control_plan', 'doc_id': str(cp.cp_id),
        'doc_name': 'CP', 'baseline_version_id': None, 'baseline_version': None,
        'key_points': [{'target_kind': 'cp_item', 'expected_action': 'delete',
                        'target_key': str(item_id), 'field': 'product_characteristic'}],
        'update_suggestion': 'Review'}]
    a = CapaDocgAnalysis(capa_id=capa.report_id, factory_id=cp.factory_id, is_current=True,
        status='done', affected_docs=affected, analysis_input_hash=gate._compute_input_hash(
            capa, await gate._build_allowlist(db, capa)), llm_available=True,
        completed_at=datetime.now(timezone.utc), generated_by=user.user_id)
    db.add(a)
    await db.flush()
    return capa, a

@pytest.mark.parametrize('status', ['D1_TEAM', 'D7_COMPLETED', 'D8_GATE_PENDING', 'D8_APPROVAL_PENDING'])
async def test_active_target_blocks_modify_delete_no_waiver_escape(db, admin_client, documents, admin_user, status):
    await seed(admin_client, documents)
    cp, _, original = documents
    initial = await rows(db, cp.cp_id)
    capa, a = await material(db, cp, admin_user, initial[0].item_id, status)
    g = graph()
    g['nodes'][2]['characteristics'][0]['name'] = 'remote'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    i = next(i for i in p['items'] if i['item_id'] == str(initial[0].item_id))
    assert not i['applicable'] and any(x['code'] == 'protected_capa_material' for x in i['issues'])
    assert 'Do not disclose' not in str(p) and capa.document_no not in str(p)
    assert (await sync_apply(admin_client, cp, p, [i['candidate_key']])).status_code == 409
    assert initial[0].product_characteristic == '孔距'
    assert initial[0].source_characteristic_ref['accepted_source_version_id'] == str(original.version_id)

@pytest.mark.parametrize('status', ['D8_CLOSURE', 'ARCHIVED'])
async def test_closed_or_unrelated_history_not_permanent_protection(db, admin_client, documents, admin_user, status):
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    await material(db, cp, admin_user, initial[0].item_id, status)
    g = graph()
    g['nodes'][2]['characteristics'][0]['name'] = 'remote'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert p['items'][0]['applicable']
    assert (await sync_apply(admin_client, cp, p)).status_code == 200

async def test_analysis_replacement_and_protection_change_expires_preview(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    g = graph()
    g['nodes'][2]['characteristics'][0]['name'] = 'remote'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    capa, a = await material(db, cp, admin_user, initial[0].item_id)
    assert (await sync_apply(admin_client, cp, p)).status_code == 409
    a.is_current = False
    await db.flush()
    p2 = (await sync_preview(admin_client, cp, v)).json()
    assert p2['items'][0]['applicable']
    assert (await sync_apply(admin_client, cp, p2)).status_code == 200

async def test_protected_noop_does_not_rebase_or_create_candidate(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, original = documents
    initial = await rows(db, cp.cp_id)
    await material(db, cp, admin_user, initial[0].item_id)
    v = await target(db, documents, admin_user)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert not p['items']
    assert (await sync_apply(admin_client, cp, p, [])).status_code == 200
    assert not cp.sync_pending and cp.source_fmea_version_id == v.version_id
    assert initial[0].source_characteristic_ref['accepted_source_version_id'] == str(original.version_id)
    lock = cp.lock_version
    repeat = (await sync_preview(admin_client, cp, v)).json()
    assert (await sync_apply(admin_client, cp, repeat, [])).status_code == 200
    assert cp.lock_version == lock

@pytest.mark.parametrize('broken', ['target', 'version_owner', 'hash', 'coverage'])
async def test_known_malformed_material_fails_closed(db, admin_client, documents, admin_user, broken):
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    capa, a = await material(db, cp, admin_user, initial[0].item_id)
    latest = await db.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))
    if broken == 'target':
        docs = list(a.affected_docs)
        docs[0] = {**docs[0], 'key_points': [{'target_kind': 'cp_item', 'expected_action': 'modify', 'target_key': 'garbage'}]}
        a.affected_docs = docs
    else:
        meta = {'version_id': str(latest.version_id), 'sha256': latest.sha256_hash}
        if broken == 'version_owner':
            meta['version_id'] = str(uuid.uuid4())
        if broken == 'hash':
            meta['sha256'] = 'wrong'
        audit = CapaDocgAudit(analysis_id=a.analysis_id, audit_run_id=uuid.uuid4(), factory_id=cp.factory_id,
            doc_type='control_plan', doc_id=cp.cp_id, doc_name='CP', status='passed',
            version_before=meta, version_after=meta, coverage={} if broken == 'coverage' else [],
            covered_count=0, total_count=0, audited_by=admin_user.user_id)
        db.add(audit)
    await db.flush()
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert all(not i['applicable'] for i in p['items'])
    assert all(any(x['code'] == 'protection_state_unresolved' for x in i['issues']) for i in p['items'])

async def test_version_snapshot_binds_all_existing_rows_not_only_named_target(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    capa, a = await material(db, cp, admin_user, initial[0].item_id)
    latest = await db.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))
    db.add(CapaDocgDecision(analysis_id=a.analysis_id, factory_id=cp.factory_id, revision=0, decision='blocked',
        version_snapshot=[{'doc_type': 'control_plan', 'doc_id': str(cp.cp_id),
                           'version_after_id': str(latest.version_id), 'sha256': latest.sha256_hash}],
        decided_by=admin_user.user_id))
    await db.flush()
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert len(p['items']) == 5 and all(not i['applicable'] for i in p['items'])

async def test_reverse_special_characteristic_reference_blocks_source_deletion(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    sc = SpecialCharacteristic(sc_id=uuid.uuid4(), sc_code='PROTECT-'+uuid.uuid4().hex[:8], sc_name='Linked',
        sc_type='CC', source_node_id='s1', source_type='PFMEA', factory_id=cp.factory_id, product_line_code=cp.product_line_code, cp_item_id=initial[4].item_id)
    db.add(sc)
    await db.flush()
    g = graph()
    g['nodes'][3]['characteristics'].pop()
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    i = next(i for i in p['items'] if i['action'] == 'delete')
    assert any(x['code'] == 'linked_execution_reference' for x in i['issues'])
    assert (await sync_apply(admin_client, cp, p, [i['candidate_key']])).status_code == 409
    assert sc.cp_item_id == initial[4].item_id and await db.get(type(initial[4]), initial[4].item_id)

async def test_phase3_rejects_cp_inputs_changed_during_external_calculation(db, admin_client, documents, admin_user, monkeypatch):
    from app.services.agent import provider_adapter
    from unittest.mock import AsyncMock
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    capa, a = await material(db, cp, admin_user, initial[0].item_id)
    monkeypatch.setattr(provider_adapter, 'build_client', AsyncMock(return_value=type('Client', (), {'model': 'test'})()))
    monkeypatch.setattr(provider_adapter, 'complete_json', AsyncMock(return_value={'affected_docs': []}))
    p1 = await gate._phase1_create_running(db, capa, admin_user.user_id)
    p2 = await gate._phase2_llm(db, capa, p1)
    initial[0].sample_size = 'changed during external calculation'
    await db.flush()
    result = await gate._phase3_cas(db, capa, p1, p2, admin_user.user_id)
    assert result['status'] == 'failed' and result['error'] == 'input_changed'

@pytest.mark.parametrize('kind', ['gauge', 'spc'])
async def test_execution_links_block_delete_preserve_entities_and_allow_field_sync(db, admin_client, documents, admin_user, kind):
    from app.models.gauge import Gauge
    from app.models.spc import InspectionCharacteristic
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    row = initial[4]
    if kind == 'gauge':
        entity = Gauge(gauge_no='SYNC-'+uuid.uuid4().hex[:8], name='Retain gauge',
                       factory_id=cp.factory_id, created_by=admin_user.user_id)
        db.add(entity)
        await db.flush()
        row.gauge_id = entity.gauge_id
        entity_id = entity.gauge_id
    else:
        entity = InspectionCharacteristic(ic_code='SYNC-'+uuid.uuid4().hex[:8],
            process_name='Process', characteristic_name='Retain SPC', spec_upper=10, spec_lower=0,
            chart_type='Xbar-R', factory_id=cp.factory_id, created_by_id=admin_user.user_id)
        db.add(entity)
        await db.flush()
        row.spc_chart_id = entity.ic_id
        entity_id = entity.ic_id
    await db.flush()
    g = graph()
    g['nodes'][3]['characteristics'].pop()
    deleted_source = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, deleted_source)).json()
    assert p['items'][0]['action'] == 'delete' and not p['items'][0]['applicable']
    assert (await sync_apply(admin_client, cp, p, [p['items'][0]['candidate_key']])).status_code == 409
    assert await db.get(type(entity), entity_id) is not None
    g = graph()
    g['nodes'][3]['characteristics'][2]['name'] = 'Changed linked parameter'
    modified_source = await target(db, documents, admin_user, g)
    p2 = (await sync_preview(admin_client, cp, modified_source)).json()
    assert p2['items'][0]['applicable']
    assert any(i['code'] == 'review_execution_applicability' for i in p2['items'][0]['issues'])
    assert (await sync_apply(admin_client, cp, p2)).status_code == 200
    await db.refresh(row)
    assert (row.gauge_id if kind == 'gauge' else row.spc_chart_id) == entity_id
    assert await db.get(type(entity), entity_id) is not None

async def test_unprotected_subset_applies_without_rebasing_protected_row(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, original = documents
    initial = await rows(db, cp.cp_id)
    capa, a = await material(db, cp, admin_user, initial[0].item_id)
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    keys = [i['candidate_key'] for i in p['items'] if i['applicable']]
    assert len(keys) == 4
    assert (await sync_apply(admin_client, cp, p, keys)).status_code == 200
    await db.refresh(initial[0])
    assert initial[0].step_no == 'OP10'
    assert initial[0].source_characteristic_ref['accepted_source_version_id'] == str(original.version_id)
    assert cp.sync_pending and cp.source_fmea_version_id == original.version_id
    again = (await sync_preview(admin_client, cp, v)).json()
    assert len(again['items']) == 1 and not again['items'][0]['applicable']

async def test_unknown_state_fails_closed_and_unrelated_document_target_does_not_protect(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    capa, a = await material(db, cp, admin_user, initial[0].item_id, docs=[{
        'doc_type': 'control_plan', 'doc_id': str(uuid.uuid4()), 'key_points': [{
            'target_kind': 'cp_item', 'expected_action': 'delete', 'target_key': str(initial[0].item_id)}]}])
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert all(i['applicable'] for i in p['items'])
    capa.status = 'UNKNOWN'
    await db.flush()
    p2 = (await sync_preview(admin_client, cp, v)).json()
    assert all(any(x['code'] == 'protection_state_unresolved' for x in i['issues']) for i in p2['items'])

async def test_latest_decision_replaces_old_bound_versions_not_analysis_targets(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    capa, a = await material(db, cp, admin_user, initial[0].item_id)
    version = await db.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))
    db.add(CapaDocgDecision(analysis_id=a.analysis_id, factory_id=cp.factory_id, revision=0,
        decision='blocked', version_snapshot=[{'doc_type': 'control_plan', 'doc_id': str(cp.cp_id),
        'version_after_id': str(version.version_id), 'sha256': version.sha256_hash}], decided_by=admin_user.user_id))
    await db.flush()
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert all(not i['applicable'] for i in p['items'])
    from datetime import date
    db.add(CapaDocgDecision(analysis_id=a.analysis_id, factory_id=cp.factory_id, revision=1,
        decision='deferred', defer_reason='Review', defer_owner=admin_user.user_id, defer_deadline=date.today(),
        version_snapshot=[], decided_by=admin_user.user_id))
    await db.flush()
    p2 = (await sync_preview(admin_client, cp, v)).json()
    assert sum(i['applicable'] for i in p2['items']) == 4

async def test_null_decision_version_binding_is_not_protection_for_document_add(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    capa, a = await material(db, cp, admin_user, docs=[{'doc_type': 'control_plan', 'doc_id': str(cp.cp_id),
        'key_points': [{'target_kind': 'document', 'expected_action': 'add'}]}])
    db.add(CapaDocgDecision(analysis_id=a.analysis_id, factory_id=cp.factory_id, revision=0,
        decision='blocked', version_snapshot=[{'doc_type': 'control_plan', 'doc_id': str(cp.cp_id),
        'version_after_id': None, 'sha256': None}], decided_by=admin_user.user_id))
    await db.flush()
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    assert all(i['applicable'] for i in (await sync_preview(admin_client, cp, v)).json()['items'])

async def test_current_complete_audit_coverage_and_versions_protect_real_rows(db, admin_client, documents, admin_user):
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    capa, a = await material(db, cp, admin_user, initial[0].item_id)
    version = await db.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))
    meta = {'version_id': str(version.version_id), 'sha256': version.sha256_hash}
    audit = CapaDocgAudit(analysis_id=a.analysis_id, audit_run_id=uuid.uuid4(), factory_id=cp.factory_id,
        doc_type='control_plan', doc_id=cp.cp_id, doc_name='CP', status='pending_update', version_before=meta,
        version_after=None, coverage=[{'key_point': a.affected_docs[0]['key_points'][0], 'covered': False}],
        total_count=1, covered_count=0, audited_by=admin_user.user_id)
    db.add(audit)
    await db.flush()
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    assert len(p['items']) == 5 and all(not i['applicable'] for i in p['items'])
    assert all(any(c['code'] == 'protected_capa_material' for c in i['issues']) for i in p['items'])
    from datetime import timedelta
    newer = CapaDocgAudit(analysis_id=a.analysis_id, audit_run_id=uuid.uuid4(), factory_id=cp.factory_id,
        doc_type='control_plan', doc_id=cp.cp_id, doc_name='CP', status='pending_update',
        version_before=None, version_after=None, audited_at=audit.audited_at + timedelta(seconds=1),
        coverage=[{'key_point': a.affected_docs[0]['key_points'][0], 'covered': False}],
        total_count=1, covered_count=0, audited_by=admin_user.user_id)
    db.add(newer)
    await db.flush()
    fresh = (await sync_preview(admin_client, cp, v)).json()
    assert sum(i['applicable'] for i in fresh['items']) == 4

async def test_actual_existing_gate_waiver_does_not_authorize_syncing_bound_rows(db, admin_client, documents, admin_user):
    from app.services.version_service import create_cp_version
    await seed(admin_client, documents)
    cp, _, _ = documents
    initial = await rows(db, cp.cp_id)
    baseline = await db.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))
    missing_id = initial[0].item_id
    docs = [{'doc_type': 'control_plan', 'doc_id': str(cp.cp_id), 'doc_name': 'CP',
        'baseline_version_id': str(baseline.version_id), 'baseline_version': {
            'major': baseline.major_no, 'minor': baseline.minor_no, 'sha256': baseline.sha256_hash},
        'key_points': [{'target_kind': 'cp_item', 'expected_action': 'modify',
                        'target_key': str(missing_id), 'field': 'control_method'}], 'update_suggestion': 'Review'}]
    capa, a = await material(db, cp, admin_user, docs=docs)
    # This fixture wraps commit as flush: assign distinct insertion times so a
    # later snapshot cannot become a phantom CAPA-time baseline via txn NOW().
    from datetime import timedelta
    from sqlalchemy import event
    capa.created_at = datetime.now(timezone.utc)
    await db.flush()
    a.analysis_input_hash = gate._compute_input_hash(capa, await gate._build_allowlist(db, capa))
    await db.flush()
    def later_snapshot(mapper, connection, version):
        version.created_at = capa.created_at + timedelta(seconds=1)
    # Historical deletion on the unchanged manual path, not an automatic-sync authorization.
    await db.delete(initial[0])
    await db.flush()
    event.listen(ControlPlanVersion, 'before_insert', later_snapshot)
    try:
        await create_cp_version(db, cp, 'manual', 'Historical identity break', admin_user.user_id)
    finally:
        event.remove(ControlPlanVersion, 'before_insert', later_snapshot)
    audited = await gate.run_audit(db, capa, admin_user.user_id)
    assert audited['decision'] == 'blocked'
    waiver = await gate.record_gate_waiver(db, capa, 'Historical missing target', [{
        'doc_type': 'control_plan', 'doc_id': str(cp.cp_id), 'target_key': str(missing_id),
        'field': 'control_method'}], admin_user.user_id)
    assert waiver['decision'] == 'passed'
    g = graph()
    g['nodes'][0]['process_number'] = 'OP20'
    v = await target(db, documents, admin_user, g)
    p = (await sync_preview(admin_client, cp, v)).json()
    existing = [i for i in p['items'] if i['item_id']]
    assert len(existing) == 4 and all(not i['applicable'] for i in existing)
    assert (await sync_apply(admin_client, cp, p, [existing[0]['candidate_key']])).status_code == 409

@pytest.mark.parametrize('operation', ['modify', 'delete'])
@pytest.mark.parametrize('bad_shape', [
    'missing_action', 'unknown_action', 'missing_kind', 'wrong_kind',
    'missing_field', 'unknown_field', 'ambiguous_anchor', 'item_add_with_target',
    'item_add_missing_anchor', 'document_modify', 'document_add_with_target',
])
async def test_malformed_known_cp_shapes_block_changes_but_allow_independent_add(
    db, admin_client, documents, admin_user, operation, bad_shape,
):
    await seed(admin_client, documents)
    cp, _, original = documents
    initial = await rows(db, cp.cp_id)
    row = initial[4]
    kp = {'target_kind': 'cp_item', 'expected_action': 'modify',
          'target_key': str(row.item_id), 'field': 'process_characteristic'}
    if bad_shape == 'missing_action':
        kp.pop('expected_action')
    elif bad_shape == 'unknown_action':
        kp['expected_action'] = 'replace'
    elif bad_shape == 'missing_kind':
        kp.pop('target_kind')
    elif bad_shape == 'wrong_kind':
        kp['target_kind'] = 'fmea_node'
    elif bad_shape == 'missing_field':
        kp.pop('field')
    elif bad_shape == 'unknown_field':
        kp['field'] = 'not_a_cp_field'
    elif bad_shape == 'ambiguous_anchor':
        kp['add_anchor'] = {'parent_node_id': 's1', 'node_type': 'FailureMode', 'business_key': 'extra'}
    elif bad_shape == 'item_add_with_target':
        kp['expected_action'] = 'add'
        kp['add_anchor'] = {'parent_node_id': 's1', 'node_type': 'FailureMode', 'business_key': 'extra'}
    elif bad_shape == 'item_add_missing_anchor':
        kp = {'target_kind': 'cp_item', 'expected_action': 'add', 'field': 'process_characteristic'}
    elif bad_shape == 'document_modify':
        kp['target_kind'] = 'document'
    elif bad_shape == 'document_add_with_target':
        kp.update(target_kind='document', expected_action='add')
    await material(db, cp, admin_user, docs=[{
        'doc_type': 'control_plan', 'doc_id': str(cp.cp_id), 'key_points': [kp],
        'baseline_version_id': None, 'baseline_version': None,
    }])
    g = graph()
    if operation == 'modify':
        g['nodes'][3]['characteristics'][2]['name'] = 'Changed process source'
    else:
        g['nodes'][3]['characteristics'].pop()
    g['nodes'][3]['characteristics'].append({'id': str(uuid.uuid4()), 'kind': 'process', 'name': 'Independent add'})
    v = await target(db, documents, admin_user, g)
    cp.sync_pending = True
    await db.flush()
    p = (await sync_preview(admin_client, cp, v)).json()
    affected = next(i for i in p['items'] if i['item_id'] == str(row.item_id))
    added = next(i for i in p['items'] if i['action'] == 'add')
    assert any(i['code'] == 'protection_state_unresolved' for i in affected['issues'])
    assert not affected['applicable'] and added['applicable']
    assert (await sync_apply(admin_client, cp, p, [affected['candidate_key']])).status_code == 409
    assert (await sync_apply(admin_client, cp, p, [affected['candidate_key'], added['candidate_key']])).status_code == 409
    assert len(await rows(db, cp.cp_id)) == 5
    assert (await sync_apply(admin_client, cp, p, [added['candidate_key']])).status_code == 200
    await db.refresh(row)
    assert row.process_characteristic == '时间'
    assert row.source_characteristic_ref['accepted_source_version_id'] == str(original.version_id)
    assert cp.sync_pending and cp.source_fmea_version_id == original.version_id
    assert len(await rows(db, cp.cp_id)) == 6
