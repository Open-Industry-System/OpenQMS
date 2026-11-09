"""Task 9 automatic consumers: real PostgreSQL and actual API writer boundaries."""
from copy import deepcopy
from datetime import date, timedelta
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.main import app
from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.services.version_service import create_fmea_version
from app.models.gauge import Gauge
from app.models.product_line import ProductLine
from app.models.special_characteristic import SpecialCharacteristic
from app.models.spc import InspectionCharacteristic
from app.services import special_characteristic_service as svc
from tests.test_cp_characteristic_import import graph, IDS, documents, preview, apply, rows as cp_rows
from tests.test_cp_characteristic_import_transactions import isolated_tenants, seed_tenant, tenant_scope
from tests.test_cp_characteristic_sync_transactions import sync_tenants

pytestmark = pytest.mark.asyncio


def characteristic_graph():
    g = graph()
    for n in g['nodes']:
        n.setdefault('name', n['id'])
    g['nodes'][2].update(classification='CC', severity=10)
    g['nodes'][2]['characteristics'][0]['classification'] = 'CC'
    g['nodes'][2]['characteristics'][1].update(classification='SC', specification='无裂纹')
    g['nodes'][3]['characteristics'][0].update(classification='SC', specification='8 ± 1 MPa')
    return g


@pytest_asyncio.fixture
async def source(db, admin_user, default_factory):
    doc = FMEADocument(fmea_id=uuid.uuid4(), document_no='T9-'+uuid.uuid4().hex[:10],
        title='Characteristic source', factory_id=default_factory.id,
        product_line_code='DC-DC-100', fmea_type='PFMEA', status='draft',
        graph_data=characteristic_graph(), created_by=admin_user.user_id)
    db.add(doc)
    await db.flush()
    return doc


async def extract(db, source, user):
    return await svc.sync_from_fmea(db, source.fmea_id, user.user_id)


async def sc_rows(db, source):
    return list((await db.scalars(select(SpecialCharacteristic).where(
        SpecialCharacteristic.source_fmea_id == source.fmea_id))).all())


async def test_extract_distinct_characteristics_types_specs_rename_and_no_auto_parent(db, source, admin_user):
    other = SpecialCharacteristic(sc_id=uuid.uuid4(), sc_code='OTHER-'+uuid.uuid4().hex[:10],
        sc_name='孔距', sc_type='CC', source_node_id='sf1', source_type='DFMEA',
        factory_id=source.factory_id, product_line_code=source.product_line_code)
    db.add(other); await db.flush()
    await extract(db, source, admin_user)
    rows = await sc_rows(db, source)
    by_id = {str(s.source_characteristic_id): s for s in rows}
    assert set(by_id) == set(IDS[:3])
    assert [(by_id[i].sc_type, by_id[i].sc_category, by_id[i].spec_requirement) for i in IDS[:3]] == [
        ('CC', 'product', '10±0.1'), ('SC', 'product', '无裂纹'), ('SC', 'process', '8 ± 1 MPa')]
    assert all(s.parent_sc_id is None and s.factory_id == source.factory_id for s in rows)
    created_ids = set((await db.scalars(select(AuditLog.record_id).where(
        AuditLog.table_name == 'special_characteristics', AuditLog.action == 'CREATE',
        AuditLog.record_id.in_([s.sc_id for s in rows])))).all())
    assert created_ids == {s.sc_id for s in rows}
    assert by_id[IDS[0]].source_node_id == by_id[IDS[1]].source_node_id == 'sf1'
    old_id = by_id[IDS[0]].sc_id
    g = deepcopy(source.graph_data); g['nodes'][2]['characteristics'][0]['name'] = 'Renamed'
    source.graph_data = g; await db.flush()
    await extract(db, source, admin_user)
    renamed = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    assert renamed.sc_id == old_id and renamed.sc_name == 'Renamed'


async def test_canonical_empty_and_unclassified_are_authoritative_over_severity_and_function_class(db, source, admin_user):
    g = characteristic_graph()
    g['nodes'][2]['characteristics'] = []
    g['nodes'][3]['characteristics'][0]['classification'] = None
    g['nodes'][3]['characteristics'][0]['related_product_characteristic_ids'] = []
    g['nodes'][3].update(classification='SC', severity=10)
    g['nodes'].append(dict(id='fm', name='High severity', type='FailureMode', severity=10))
    g['edges'].append(dict(source='sf1', target='fm', type='HAS_FAILURE_MODE'))
    source.graph_data = g; await db.flush()
    assert await extract(db, source, admin_user) == []
    assert await sc_rows(db, source) == []


@pytest.mark.parametrize('state', ['submitted', 'approved'])
@pytest.mark.parametrize('change', ['rename', 'cancel', 'remove', 'rebind'])
async def test_automatic_extraction_preserves_reviewed_safety_material_and_warns(
    db, source, admin_user, admin_client, state, change,
):
    await extract(db, source, admin_user)
    sc = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    response = await admin_client.post(f'/api/special-characteristics/{sc.sc_id}/safety-submit', json={
        'safety_regulation_ref': 'SR-1', 'safety_verification_method': 'Measured'})
    assert response.status_code == 200, response.text
    if state == 'approved':
        response = await admin_client.post(f'/api/special-characteristics/{sc.sc_id}/safety-approve', json={})
        assert response.status_code == 200, response.text
    before = (sc.sc_id, sc.sc_name, sc.sc_type, sc.sc_category, sc.spec_requirement,
              sc.source_node_id, sc.source_characteristic_id, sc.safety_approval_status,
              sc.safety_approved_by, sc.safety_approved_at, sc.safety_regulation_ref)
    g = deepcopy(source.graph_data)
    c = g['nodes'][2]['characteristics'][0]
    if change == 'rename':
        c.update(name='Different', specification='New', classification='SC')
    elif change == 'cancel':
        c['classification'] = None
    elif change == 'remove':
        g['nodes'][2]['characteristics'].pop(0)
        g['nodes'][3]['characteristics'][0]['related_product_characteristic_ids'] = []
    else:
        g['nodes'].append(dict(id='sf2', name='New owner', type='ProcessStepFunction', characteristics=[c]))
        g['nodes'][2]['characteristics'].pop(0)
        g['edges'].append(dict(source='s1', target='sf2', type='HAS_FUNCTION'))
    source.graph_data = g; await db.flush()
    response = await admin_client.post(f'/api/special-characteristics/sync-from-fmea/{source.fmea_id}')
    assert response.status_code == 200, response.text
    await db.refresh(sc)
    assert (sc.sc_id, sc.sc_name, sc.sc_type, sc.sc_category, sc.spec_requirement,
            sc.source_node_id, sc.source_characteristic_id, sc.safety_approval_status,
            sc.safety_approved_by, sc.safety_approved_at, sc.safety_regulation_ref) == before
    assert any(w['sc_id'] == str(sc.sc_id) for w in response.json()['warnings'])


async def setup_cp(db, source, ref, **changes):
    if ref is not None and 'accepted_source_version_id' not in ref:
        version = await db.scalar(select(FMEAVersion).where(
            FMEAVersion.fmea_id == source.fmea_id, FMEAVersion.change_type == 'approve')
            .order_by(FMEAVersion.major_no.desc()))
        if version is None:
            version = await create_fmea_version(db, source, 'approve', 'Trace fixture baseline', source.created_by)
        ref = {**ref, 'accepted_source_version_id': str(version.version_id)}
    cp = ControlPlan(cp_id=uuid.uuid4(), document_no='T9-CP-'+uuid.uuid4().hex[:10], title='CP',
        factory_id=source.factory_id, product_line_code=source.product_line_code,
        fmea_ref_id=source.fmea_id, status='draft')
    db.add(cp); await db.flush()
    row = ControlPlanItem(item_id=uuid.uuid4(), cp_id=cp.cp_id, factory_id=cp.factory_id,
        step_no='OP10', process_name='装配', source_fmea_node_id='s1',
        source_characteristic_ref=ref, special_class='MANUAL', **changes)
    db.add(row); await db.flush()
    return cp, row


def ref(source, cid=IDS[0], **changes):
    value = dict(mapping_version=1, fmea_id=str(source.fmea_id), step_id='s1',
        function_id='sf1', work_element_id=None, characteristic_id=cid)
    value.update(changes)
    return value


async def test_exact_all_row_trace_no_sync_bypass_and_actual_execution_evidence(
    db, source, admin_user, admin_client,
):
    await extract(db, source, admin_user)
    sc = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    cp, row = await setup_cp(db, source, ref(source), product_characteristic='Manual diameter')
    second = ControlPlanItem(item_id=uuid.uuid4(), cp_id=cp.cp_id, factory_id=cp.factory_id,
        step_no='OP10', process_name='装配', source_fmea_node_id='s1',
        source_characteristic_ref=deepcopy(row.source_characteristic_ref), special_class='CC')
    db.add(second)
    # Same class/name alone, wrong function, step, document, or work-element must not match.
    bad_refs = [None, ref(source, function_id='wrong'), ref(source, step_id='wrong'),
                ref(source, fmea_id=str(uuid.uuid4())), ref(source, work_element_id='w1')]
    for bad in bad_refs:
        await setup_cp(db, source, bad)
    ic = InspectionCharacteristic(ic_id=uuid.uuid4(), ic_code='T9-'+uuid.uuid4().hex[:8],
        factory_id=source.factory_id, product_line=source.product_line_code, process_name='装配',
        characteristic_name='Not a name match', spec_upper=1, spec_lower=0, target_value=0,
        chart_type='xbar_r', created_by_id=admin_user.user_id)
    gauge = Gauge(gauge_id=uuid.uuid4(), gauge_no='T9-'+uuid.uuid4().hex[:8], name='Calibrated',
        factory_id=source.factory_id, product_line_code=source.product_line_code,
        status='active', next_calibration_date=date.today()+timedelta(days=30), created_by=admin_user.user_id)
    db.add_all([ic, gauge]); await db.flush()
    row.spc_chart_id = ic.ic_id; row.gauge_id = gauge.gauge_id; await db.flush()
    before = (row.item_id, row.spc_chart_id, row.gauge_id, row.special_class,
              row.product_characteristic, deepcopy(row.source_characteristic_ref), cp.lock_version)
    result = await admin_client.post(f'/api/special-characteristics/sync-to-cp/{cp.cp_id}')
    assert result.status_code == 200, result.text
    assert result.json()['updated_count'] == 0
    assert result.json()['requires_version_sync_count'] == 1
    chain = (await admin_client.get(f'/api/special-characteristics/traceability/{sc.sc_id}')).json()
    assert {i['item_id'] for i in chain['control_plan_items']} == {str(row.item_id), str(second.item_id)}
    assert chain['sc_category'] == 'product' and chain['source_characteristic_id'] == IDS[0]
    assert chain['msa_study_id'] is None and chain['msa_status'] == 'PENDING'
    assert len(chain['spc_characteristics']) == 1
    assert chain['spc_characteristics'][0]['ic_id'] == str(ic.ic_id)
    assert chain['spc_characteristics'][0]['spec_target'] == 0
    assert next(i for i in chain['control_plan_items'] if i['item_id'] == str(row.item_id))['gauge_id'] == str(gauge.gauge_id)
    assert sc.cp_item_id is None
    assert (row.item_id, row.spc_chart_id, row.gauge_id, row.special_class,
            row.product_characteristic, row.source_characteristic_ref, cp.lock_version) == before
    status = await admin_client.get(f'/api/special-characteristics/cp-sync-status/{cp.cp_id}')
    assert status.status_code == 200
    row_status = next(i for i in status.json()['items'] if i['item_id'] == str(row.item_id))
    assert row_status['expected_special_class'] == 'CC'
    assert row_status['requires_version_sync'] is True


@pytest.mark.parametrize('mode', ['factory', 'product_line', 'none'])
async def test_consumer_apis_forward_real_request_scope_and_deny_foreign_targets(
    db, source, admin_user, admin_client, mode,
):
    await extract(db, source, admin_user)
    sc = (await sc_rows(db, source))[0]
    cp, row = await setup_cp(db, source, ref(source))
    scope = RequestScope(user=admin_user,
        factory_scope=FactoryScope(accessible_factory_ids=[] if mode == 'factory' else [source.factory_id],
            default_factory_id=source.factory_id), effective_factory_id=None,
        pl_scope=ProductLineScope(mode='NONE' if mode == 'none' else 'EXPLICIT',
            codes=['FOREIGN'] if mode == 'product_line' else [source.product_line_code]))
    app.dependency_overrides[get_request_scope] = lambda: scope
    for method, url in [('get', f'traceability/{sc.sc_id}'), ('get', f'cp-sync-status/{cp.cp_id}'),
                        ('post', f'sync-to-cp/{cp.cp_id}'), ('post', f'sync-from-fmea/{source.fmea_id}')]:
        response = await getattr(admin_client, method)('/api/special-characteristics/'+url)
        assert response.status_code == 404, (url, response.text)
    assert sc.cp_item_id is None and row.special_class == 'MANUAL'


async def test_two_factory_same_name_actual_writer_rejects_foreign_product_and_preserves_state(
    db, source, admin_user, admin_client,
):
    factory = Factory(id=uuid.uuid4(), code='T9-'+uuid.uuid4().hex[:8], name='Second')
    db.add(factory); await db.flush()
    pl = ProductLine(code='T9-'+uuid.uuid4().hex[:8], name='Second', factory_id=factory.id)
    db.add(pl); await db.flush()
    doc2 = FMEADocument(fmea_id=uuid.uuid4(), document_no='T9-'+uuid.uuid4().hex[:8],
        title='Second', fmea_type='PFMEA', status='draft', factory_id=factory.id,
        product_line_code=pl.code, graph_data={'nodes': [], 'edges': []}, created_by=admin_user.user_id)
    source.graph_data = {'nodes': [], 'edges': []}
    db.add(doc2); await db.flush()
    g1, g2 = characteristic_graph(), characteristic_graph()
    product2 = str(uuid.uuid4()); g2['nodes'][2]['characteristics'][0]['id'] = product2
    g2['nodes'][3]['characteristics'][0]['related_product_characteristic_ids'] = [product2]
    scope = RequestScope(user=admin_user, factory_scope=FactoryScope(
        accessible_factory_ids=[source.factory_id, factory.id], default_factory_id=source.factory_id),
        effective_factory_id=None, pl_scope=ProductLineScope(mode='EXPLICIT', codes=[source.product_line_code, pl.code]))
    app.dependency_overrides[get_request_scope] = lambda: scope
    for doc, g in [(source, g1), (doc2, g2)]:
        response = await admin_client.put(f'/api/fmea/{doc.fmea_id}', json={'graph_data': g, 'lock_version': 0})
        assert response.status_code == 200, response.text
        assert response.json()['lock_version'] == 1
    await db.refresh(doc2)
    saved = deepcopy(doc2.graph_data); lock = doc2.lock_version
    audits = await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.record_id == doc2.fmea_id))
    assert audits >= 1
    bad = deepcopy(g2)
    bad['nodes'][3]['characteristics'][0]['related_product_characteristic_ids'] = [IDS[0]]
    response = await admin_client.put(f'/api/fmea/{doc2.fmea_id}', json={'graph_data': bad, 'lock_version': lock})
    assert response.status_code == 400, response.text
    assert 'related product characteristic does not exist in this FMEA' in response.text
    await db.refresh(doc2)
    assert doc2.graph_data == saved and doc2.lock_version == lock
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.record_id == doc2.fmea_id)) == audits


async def test_same_uuid_other_document_factory_and_wrong_product_line_are_not_trace_coverage(
    db, source, admin_user, admin_client,
):
    await extract(db, source, admin_user)
    original = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    factory = Factory(id=uuid.uuid4(), code='T9-X-'+uuid.uuid4().hex[:8], name='Foreign')
    db.add(factory); await db.flush()
    pl = ProductLine(code='T9-X-'+uuid.uuid4().hex[:8], name='Foreign', factory_id=factory.id)
    db.add(pl); await db.flush()
    foreign = FMEADocument(fmea_id=uuid.uuid4(), document_no='T9-X-'+uuid.uuid4().hex[:8],
        title='Foreign same name', fmea_type='PFMEA', status='draft', factory_id=factory.id,
        product_line_code=pl.code, graph_data=characteristic_graph(), created_by=admin_user.user_id)
    db.add(foreign); await db.flush()
    await extract(db, foreign, admin_user)
    other = next(s for s in await sc_rows(db, foreign) if str(s.source_characteristic_id) == IDS[0])
    assert other.sc_id != original.sc_id and other.parent_sc_id is None
    await setup_cp(db, foreign, ref(foreign))
    # Even a forged ref to the local document is not coverage outside its scope.
    await setup_cp(db, foreign, ref(source))
    cp, _ = await setup_cp(db, source, ref(source))
    cp.product_line_code = pl.code; await db.flush()
    chain = await svc.get_traceability_chain(db, original.sc_id)
    assert chain['control_plan_items'] == []


async def test_legacy_suggestion_and_existing_source_survive_canonical_adoption_without_merging(
    db, source, admin_user,
):
    g = characteristic_graph()
    g['nodes'][2].pop('characteristics')
    g['nodes'][3]['characteristics'][0]['related_product_characteristic_ids'] = []
    source.graph_data = g; await db.flush()
    await extract(db, source, admin_user)
    legacy = next(s for s in await sc_rows(db, source) if s.source_node_id == 'sf1')
    assert legacy.source_characteristic_id is None and legacy.is_safety_suggested
    original_id = legacy.sc_id
    source.graph_data = characteristic_graph(); await db.flush()
    result = await extract(db, source, admin_user)
    assert await db.scalar(select(SpecialCharacteristic.sc_id).where(SpecialCharacteristic.sc_id == original_id)) == original_id
    rows = await sc_rows(db, source)
    assert len([s for s in rows if s.source_characteristic_id]) == 3
    assert any(s.sc_id == original_id and s.review_required for s in result)


@pytest.mark.parametrize('state', ['submitted', 'approved'])
async def test_automatic_cp_consumer_never_rebinds_protected_sc_even_with_multiple_controls(
    db, source, admin_user, admin_client, state,
):
    await extract(db, source, admin_user)
    sc = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    r = await admin_client.post(f'/api/special-characteristics/{sc.sc_id}/safety-submit', json={
        'safety_regulation_ref': 'SR-1', 'safety_verification_method': 'Measured'})
    assert r.status_code == 200
    if state == 'approved':
        assert (await admin_client.post(f'/api/special-characteristics/{sc.sc_id}/safety-approve', json={})).status_code == 200
    cp, first = await setup_cp(db, source, ref(source))
    second = ControlPlanItem(item_id=uuid.uuid4(), cp_id=cp.cp_id, factory_id=cp.factory_id,
        step_no='OP10', source_fmea_node_id='s1', source_characteristic_ref=deepcopy(first.source_characteristic_ref), special_class='SC')
    db.add(second); await db.flush()
    r = await admin_client.post(f'/api/special-characteristics/sync-to-cp/{cp.cp_id}')
    assert r.status_code == 200 and r.json()['updated_count'] == 0
    await db.refresh(sc)
    assert sc.cp_item_id is None and sc.safety_approval_status == state
    assert first.special_class == 'MANUAL' and second.special_class == 'SC'
    assert len((await svc.get_traceability_chain(db, sc.sc_id))['control_plan_items']) == 2


async def test_existing_legacy_link_lock_and_scope_check_remain_real(db, source, admin_user, admin_client):
    source.graph_data = {'nodes': [{'id': 's1', 'name': 'Legacy', 'type': 'ProcessStep', 'classification': 'CC'}], 'edges': []}
    await db.flush()
    await extract(db, source, admin_user)
    sc = (await sc_rows(db, source))[0]
    cp, row = await setup_cp(db, source, None)
    result = await admin_client.post(f'/api/special-characteristics/sync-to-cp/{cp.cp_id}')
    assert result.status_code == 200 and result.json()['updated_count'] == 1
    assert sc.cp_item_id == row.item_id and row.special_class == 'CC'
    # A scope-denied call cannot establish another association.
    scope = RequestScope(user=admin_user, effective_factory_id=None,
        factory_scope=FactoryScope(accessible_factory_ids=[], default_factory_id=None),
        pl_scope=ProductLineScope(mode='ALL', codes=None))
    app.dependency_overrides[get_request_scope] = lambda: scope
    assert (await admin_client.post(f'/api/special-characteristics/sync-to-cp/{cp.cp_id}')).status_code == 404
    assert sc.cp_item_id == row.item_id


async def test_readonly_trace_does_not_match_spc_by_name_and_no_permission_cannot_link(
    db, source, admin_user, admin_client, viewer_user,
):
    await extract(db, source, admin_user)
    sc = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    ic = InspectionCharacteristic(ic_code='T9-NAME-'+uuid.uuid4().hex[:8],
        factory_id=source.factory_id, product_line=source.product_line_code,
        process_name='装配', characteristic_name=sc.sc_name, spec_upper=1, spec_lower=0,
        chart_type='Xbar-R', created_by_id=admin_user.user_id)
    db.add(ic); await db.flush()
    cp, row = await setup_cp(db, source, ref(source))
    assert (await svc.get_traceability_chain(db, sc.sc_id))['spc_characteristics'] == []
    scope = RequestScope(user=viewer_user, effective_factory_id=source.factory_id,
        factory_scope=FactoryScope(accessible_factory_ids=[source.factory_id], default_factory_id=source.factory_id),
        pl_scope=ProductLineScope(mode='ALL', codes=None))
    app.dependency_overrides[get_request_scope] = lambda: scope
    response = await admin_client.post(f'/api/special-characteristics/sync-to-cp/{cp.cp_id}')
    assert response.status_code == 403, response.text
    assert sc.cp_item_id is None and row.special_class == 'MANUAL'


@pytest.mark.parametrize('cp_status,safety_status', [('approved', None), ('draft', 'submitted'), ('draft', 'approved')])
async def test_legacy_automatic_cp_path_reports_protection_without_mutation(
    db, source, admin_user, admin_client, cp_status, safety_status,
):
    source.graph_data = {'nodes': [{'id': 's1', 'type': 'ProcessStep', 'name': 'Old', 'classification': 'CC'}], 'edges': []}
    await db.flush()
    await extract(db, source, admin_user)
    sc = (await sc_rows(db, source))[0]
    if safety_status:
        sc.is_safety_related = True; sc.safety_approval_status = safety_status
    cp, row = await setup_cp(db, source, None)
    cp.status = cp_status; await db.flush()
    response = await admin_client.post(f'/api/special-characteristics/sync-to-cp/{cp.cp_id}')
    assert response.status_code == 200, response.text
    assert response.json()['updated_count'] == 0
    assert response.json()['requires_version_sync_count'] == 1
    assert row.special_class == 'MANUAL' and sc.cp_item_id is None


@pytest.mark.parametrize('evidence', ['missing_id', 'dangling_id', 'study_only', 'measured'])
async def test_msa_trace_requires_actual_scoped_study_and_result_not_cached_pass(
    db, source, admin_user, evidence,
):
    from app.models.bias import BiasStudy, BiasResult
    await extract(db, source, admin_user)
    sc = (await sc_rows(db, source))[0]
    sc.msa_status = 'PASS'
    if evidence != 'missing_id':
        sc.msa_study_id = uuid.uuid4()
    if evidence in ('study_only', 'measured'):
        study = BiasStudy(study_id=sc.msa_study_id, study_no='T9-MSA-'+uuid.uuid4().hex[:8],
            title='Evidence', characteristic_name=sc.sc_name, reference_value=10,
            factory_id=sc.factory_id, product_line_code=sc.product_line_code, created_by=admin_user.user_id)
        db.add(study); await db.flush()
        if evidence == 'measured':
            db.add(BiasResult(study_id=study.study_id, factory_id=sc.factory_id,
                mean=10, bias=0, std_dev=0.1, t_statistic=0, p_value=1, conclusion='acceptable'))
    await db.flush()
    chain = await svc.get_traceability_chain(db, sc.sc_id)
    assert chain['msa_status'] == ('acceptable' if evidence == 'measured' else 'PENDING')
    assert chain['msa_study_id'] == (str(sc.msa_study_id) if evidence in ('study_only', 'measured') else None)
    assert sc.msa_status == 'PASS'  # read-only adapter does not rewrite stored history


async def test_protected_source_change_is_reviewable_even_when_cp_class_already_matches_new_source(
    db, source, admin_user, admin_client,
):
    await extract(db, source, admin_user)
    sc = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    sc.is_safety_related = True; sc.safety_approval_status = 'approved'
    cp, row = await setup_cp(db, source, ref(source))
    g = deepcopy(source.graph_data)
    g['nodes'][2]['characteristics'][0].update(name='Changed source', classification='SC')
    source.graph_data = g; row.special_class = 'SC'; await db.flush()
    response = await admin_client.post(f'/api/special-characteristics/sync-to-cp/{cp.cp_id}')
    assert response.status_code == 200
    assert response.json()['requires_version_sync_count'] == 1
    chain = await svc.get_traceability_chain(db, sc.sc_id)
    assert chain['review_required'] is True
    assert chain['control_plan_items'][0]['requires_version_sync'] is True
    assert sc.sc_name == '孔距' and sc.sc_type == 'CC' and sc.cp_item_id is None


async def test_dfmea_canonical_product_sc_has_independent_document_identity(db, source, admin_user):
    source.fmea_type = 'DFMEA'
    source.graph_data = {'nodes': [
        {'id': 'sys', 'name': 'Design', 'type': 'System'},
        {'id': 'fn', 'name': 'Function', 'type': 'ProcessStepFunction', 'characteristics': [
            {'id': IDS[0], 'kind': 'product', 'name': 'Speed', 'classification': 'SC', 'reference': 'DWG-19 rev C'}]}],
        'edges': [{'source': 'sys', 'target': 'fn', 'type': 'HAS_FUNCTION'}]}
    await db.flush()
    result = await extract(db, source, admin_user)
    assert len(result) == 1
    assert (result[0].sc_type, result[0].sc_category, result[0].spec_requirement) == ('SC', 'product', 'DWG-19 rev C')
    assert result[0].source_node_id == 'fn' and result[0].parent_sc_id is None


async def test_actual_approved_import_baseline_and_manual_override_survive_sc_consumer(
    db, admin_user, admin_client, documents,
):
    cp, fmea, approved = documents
    p = await preview(admin_client, documents)
    assert p.status_code == 200, p.text
    r = await apply(admin_client, documents, p.json())
    assert r.status_code == 200, r.text
    rows = await cp_rows(db, cp.cp_id)
    row_ids = [r.item_id for r in rows]
    accepted = deepcopy([r.source_characteristic_ref for r in rows])
    assert all(r['accepted_source_version_id'] == str(approved.version_id) for r in accepted)
    rows[0].special_class = 'MANUAL'
    fmea.graph_data = characteristic_graph(); await db.flush()
    await extract(db, fmea, admin_user)
    lock = cp.lock_version
    response = await admin_client.post(f'/api/special-characteristics/sync-to-cp/{cp.cp_id}')
    assert response.status_code == 200, response.text
    assert response.json()['updated_count'] == 0
    assert response.json()['requires_version_sync_count'] == 3
    assert rows[0].special_class == 'MANUAL'
    assert all(r.special_class is None for r in rows[1:])
    assert [r.item_id for r in rows] == row_ids
    assert [r.source_characteristic_ref for r in rows] == accepted
    assert cp.source_fmea_version_id == approved.version_id and cp.lock_version == lock


async def test_actual_request_transaction_rolls_back_mid_extraction_failure(sync_tenants, monkeypatch):
    """Real API + production get_db lifecycle, observed from a fresh connection."""
    from fastapi import Depends
    from sqlalchemy import text
    from app.core.tenant_utils import current_tenant_schema, strict_tenant_search_path_sql
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import get_db
    from app.models.role import RolePermission
    from app.models.fmea_version import FMEAVersion

    sessions, schemas = sync_tenants
    schema = schemas[0]
    token = current_tenant_schema.set(schema)
    ids, _ = await seed_tenant(sessions, schema)
    async with sessions() as db:
        await tenant_scope(db, schema, ids[3])
        fmea = await db.get(FMEADocument, ids[5])
        fmea.graph_data = characteristic_graph()
        db.add(RolePermission(role_id=ids[2], module='special_characteristic', permission_level=2))
        await db.commit()

    async def request_scope(db: AsyncSession = Depends(get_db)):
        scope = await tenant_scope(db, schema, ids[3])
        await db.execute(text(strict_tenant_search_path_sql(schema)))
        return scope

    original_audit = svc._create_audit
    staged_counts = []

    async def fail_second_create(db, action, record_id, user_id, detail):
        if action == 'CREATE':
            staged_counts.append(await db.scalar(select(func.count()).select_from(SpecialCharacteristic)))
            if len(staged_counts) == 2:
                raise ValueError('injected_mid_extraction_failure')
        return await original_audit(db, action, record_id, user_id, detail)

    monkeypatch.setattr(svc, '_create_audit', fail_second_create)
    prior = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides[get_request_scope] = request_scope
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post(f'/api/special-characteristics/sync-from-fmea/{ids[5]}',
                                         headers={'X-Tenant-ID': schema.replace('_', '-')})
        assert response.status_code == 404, response.text
        assert 'injected_mid_extraction_failure' in response.text
        assert staged_counts == [1, 2]  # failure occurred after real rows were flushed
        async with sessions() as db:
            await tenant_scope(db, schema, ids[3])
            assert await db.scalar(select(func.count()).select_from(SpecialCharacteristic)) == 0
            assert await db.scalar(select(func.count()).select_from(AuditLog)) == 0
            assert await db.scalar(select(func.count()).select_from(ControlPlanItem)) == 0
            assert await db.scalar(select(func.count()).select_from(FMEAVersion)) == 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(prior)
        current_tenant_schema.reset(token)


async def reviewed_import_controls(db, source, user, client, state='submitted'):
    """Actual approved import, reviewed SC and two real same-source controls."""
    source.status = 'approved'
    approved = await create_fmea_version(db, source, 'approve', 'Trace baseline', user.user_id)
    cp = ControlPlan(cp_id=uuid.uuid4(), document_no='T9-HIST-'+uuid.uuid4().hex[:8],
        title='Retained controls', factory_id=source.factory_id, product_line_code=source.product_line_code,
        status='draft', created_by=user.user_id)
    db.add(cp); await db.flush()
    docs = (cp, source, approved)
    p = await preview(client, docs)
    assert p.status_code == 200, p.text
    result = await apply(client, docs, p.json())
    assert result.status_code == 200, result.text
    first = (await cp_rows(db, cp.cp_id))[0]
    second = ControlPlanItem(item_id=uuid.uuid4(), cp_id=cp.cp_id, factory_id=cp.factory_id,
        step_no=first.step_no, process_name=first.process_name, source_fmea_node_id=first.source_fmea_node_id,
        source_characteristic_ref=deepcopy(first.source_characteristic_ref),
        product_characteristic=first.product_characteristic, special_class=first.special_class, sort_order=20)
    db.add(second)
    await extract(db, source, user)
    sc = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    r = await client.post(f'/api/special-characteristics/{sc.sc_id}/safety-submit', json={
        'safety_regulation_ref': 'SR-1', 'safety_verification_method': 'Measured'})
    assert r.status_code == 200, r.text
    if state == 'approved':
        r = await client.post(f'/api/special-characteristics/{sc.sc_id}/safety-approve', json={})
        assert r.status_code == 200, r.text
    for row in (first, second):
        ic = InspectionCharacteristic(ic_id=uuid.uuid4(), ic_code='HIST-'+uuid.uuid4().hex[:8],
            factory_id=source.factory_id, product_line=source.product_line_code,
            process_name='装配', characteristic_name='Actual linked SPC', spec_upper=1, spec_lower=0,
            target_value=0, chart_type='Xbar-R', created_by_id=user.user_id)
        gauge = Gauge(gauge_id=uuid.uuid4(), gauge_no='HIST-'+uuid.uuid4().hex[:8], name='Actual linked gauge',
            factory_id=source.factory_id, product_line_code=source.product_line_code, created_by=user.user_id)
        db.add_all([ic, gauge]); await db.flush()
        row.spc_chart_id = ic.ic_id; row.gauge_id = gauge.gauge_id
    cp.status = 'approved'  # Read trace must not invoke a draft/write-only import context.
    source.status = 'rework'
    await db.flush()
    return cp, approved, sc, [first, second]


@pytest.mark.parametrize('state', ['submitted', 'approved'])
@pytest.mark.parametrize('divergence', ['empty', 'removed', 'moved'])
async def test_accepted_coverage_survives_working_graph_divergence_with_real_execution_links(
    db, source, admin_user, admin_client, state, divergence,
):
    cp, approved, sc, controls = await reviewed_import_controls(db, source, admin_user, admin_client, state)
    before = [(r.item_id, deepcopy(r.source_characteristic_ref), r.special_class, r.spc_chart_id, r.gauge_id) for r in controls]
    g = deepcopy(source.graph_data)
    if divergence == 'empty':
        g = {'nodes': [], 'edges': []}
    else:
        g['nodes'][3]['characteristics'][0]['related_product_characteristic_ids'] = []
        if divergence == 'removed':
            g['nodes'][2]['characteristics'].pop(0)
        else:
            g['nodes'].append({'id': 's2', 'type': 'ProcessStep', 'name': 'New owner', 'process_number': 'OP20'})
            next(e for e in g['edges'] if e['target'] == 'sf1')['source'] = 's2'
    source.graph_data = g; await db.flush()
    r = await admin_client.post(f'/api/special-characteristics/sync-from-fmea/{source.fmea_id}')
    assert r.status_code == 200, r.text
    audit_count = await db.scalar(select(func.count()).select_from(AuditLog))
    response = await admin_client.get(f'/api/special-characteristics/traceability/{sc.sc_id}')
    assert response.status_code == 200, response.text
    chain = response.json()
    assert {r['item_id'] for r in chain['control_plan_items']} == {str(r.item_id) for r in controls}
    assert {r['gauge_id'] for r in chain['control_plan_items']} == {str(r.gauge_id) for r in controls}
    assert {r['ic_id'] for r in chain['spc_characteristics']} == {str(r.spc_chart_id) for r in controls}
    assert chain['review_required'] is True
    assert all(r['requires_version_sync'] and r['guidance'] for r in chain['control_plan_items'])
    assert [(r.item_id, r.source_characteristic_ref, r.special_class, r.spc_chart_id, r.gauge_id) for r in controls] == before
    assert sc.safety_approval_status == state and sc.cp_item_id is None and sc.sc_name == '孔距'
    assert cp.source_fmea_version_id == approved.version_id and cp.status == 'approved'
    assert source.graph_data == g
    assert await db.scalar(select(func.count()).select_from(AuditLog)) == audit_count
    # Actual absence, not working-graph absence, removes derived coverage/evidence.
    await db.delete(controls[1]); await db.flush()
    chain = await svc.get_traceability_chain(db, sc.sc_id)
    assert [r['item_id'] for r in chain['control_plan_items']] == [str(controls[0].item_id)]
    assert [r['ic_id'] for r in chain['spc_characteristics']] == [str(controls[0].spc_chart_id)]


@pytest.mark.parametrize('bad', ['missing_version', 'dangling_version', 'malformed_version', 'foreign_document',
    'version_factory', 'unapproved', 'minor_version', 'invalid_snapshot', 'hash', 'function', 'step', 'work_element', 'mapping'])
async def test_untrusted_accepted_refs_cannot_fall_back_to_matching_current_graph(
    db, source, admin_user, admin_client, bad,
):
    cp, approved, sc, controls = await reviewed_import_controls(db, source, admin_user, admin_client)
    row, valid_row = controls
    raw = deepcopy(row.source_characteristic_ref)
    if bad == 'missing_version':
        raw.pop('accepted_source_version_id')
    elif bad == 'dangling_version':
        raw['accepted_source_version_id'] = str(uuid.uuid4())
    elif bad == 'malformed_version':
        raw['accepted_source_version_id'] = 'not-a-uuid'
    elif bad == 'foreign_document':
        foreign = FMEADocument(fmea_id=uuid.uuid4(), document_no='FOREIGN-'+uuid.uuid4().hex[:8],
            title='Not this source', factory_id=source.factory_id, product_line_code=source.product_line_code,
            fmea_type='PFMEA', graph_data=characteristic_graph(), status='approved')
        db.add(foreign); await db.flush()
        version = await create_fmea_version(db, foreign, 'approve', 'Foreign', admin_user.user_id)
        raw['accepted_source_version_id'] = str(version.version_id)
    elif bad in ('version_factory', 'minor_version', 'invalid_snapshot'):
        factory_id = source.factory_id
        if bad == 'version_factory':
            factory = Factory(id=uuid.uuid4(), code='VERSION-'+uuid.uuid4().hex[:8], name='Foreign')
            db.add(factory); await db.flush(); factory_id = factory.id
        snapshot = deepcopy(source.graph_data)
        if bad == 'invalid_snapshot':
            snapshot['edges'] = [e for e in snapshot['edges'] if e.get('target') != 'sf1']
        version = FMEAVersion(version_id=uuid.uuid4(), fmea_id=source.fmea_id, factory_id=factory_id,
            major_no=7, minor_no=1 if bad == 'minor_version' else 0, change_type='approve',
            snapshot=snapshot, sha256_hash='trigger recomputes', created_by=admin_user.user_id)
        db.add(version); await db.flush()
        raw['accepted_source_version_id'] = str(version.version_id)
    elif bad == 'unapproved':
        version = await create_fmea_version(db, source, 'manual', 'Unapproved', admin_user.user_id)
        raw['accepted_source_version_id'] = str(version.version_id)
    elif bad == 'function':
        raw['function_id'] = 'wrong-function'
    elif bad == 'step':
        raw['step_id'] = 'wrong-step'
    elif bad == 'work_element':
        raw['work_element_id'] = 'w1'
    elif bad == 'mapping':
        raw['mapping_version'] = 99
    row.source_characteristic_ref = raw; await db.flush()
    old_hash = approved.sha256_hash
    # Fault only the loaded hash input, never update/disable an immutable table.
    with db.no_autoflush:
        if bad == 'hash':
            approved.sha256_hash = 'untrustworthy-hash'
        try:
            chain = await svc.get_traceability_chain(db, sc.sc_id)
            expected = set() if bad == 'hash' else {str(valid_row.item_id)}
            assert {r['item_id'] for r in chain['control_plan_items']} == expected
            assert {r['ic_id'] for r in chain['spc_characteristics']} == (
                set() if bad == 'hash' else {str(valid_row.spc_chart_id)})
        finally:
            approved.sha256_hash = old_hash


async def test_each_control_uses_its_own_accepted_snapshot_not_document_version_or_other_row_cache(
    db, source, admin_user, admin_client,
):
    cp, first_version, sc, controls = await reviewed_import_controls(db, source, admin_user, admin_client, 'approved')
    moved = deepcopy(source.graph_data)
    moved['nodes'][2]['id'] = 'sf-new'
    next(e for e in moved['edges'] if e['target'] == 'sf1')['target'] = 'sf-new'
    source.graph_data = moved
    second_version = await create_fmea_version(db, source, 'approve', 'New function owner', admin_user.user_id)
    controls[1].source_characteristic_ref = {**controls[1].source_characteristic_ref,
        'function_id': 'sf-new', 'accepted_source_version_id': str(second_version.version_id)}
    source.graph_data = {'nodes': [], 'edges': []}; await db.flush()
    chain = await svc.get_traceability_chain(db, sc.sc_id)
    assert {r['item_id'] for r in chain['control_plan_items']} == {str(r.item_id) for r in controls}
    assert len(chain['spc_characteristics']) == 2 and chain['review_required'] is True
    assert cp.source_fmea_version_id == first_version.version_id
    assert sc.source_node_id == 'sf1' and sc.safety_approval_status == 'approved' and sc.cp_item_id is None
    # A valid version ID for a different accepted owner must not borrow the
    # other cached version's mapping, even for the same characteristic UUID.
    controls[1].source_characteristic_ref = {**controls[1].source_characteristic_ref,
        'accepted_source_version_id': str(first_version.version_id)}
    await db.flush()
    chain = await svc.get_traceability_chain(db, sc.sc_id)
    assert [r['item_id'] for r in chain['control_plan_items']] == [str(controls[0].item_id)]



async def test_canonical_sc_criteria_keeps_separate_unit_and_reviewed_material(db, source, admin_user):
    g = deepcopy(source.graph_data)
    g['nodes'][2]['characteristics'][0].update(specification='10±0.1', unit='mm')
    source.graph_data = g
    await db.flush()
    await extract(db, source, admin_user)
    sc = next(sc for sc in await sc_rows(db, source) if str(sc.source_characteristic_id) == IDS[0])
    assert sc.spec_requirement == '10±0.1 mm'
    # Automatic extraction cannot alter protected reviewed safety material.
    sc.is_safety_related, sc.safety_approval_status = True, 'submitted'
    await db.flush()
    g = deepcopy(source.graph_data)
    g['nodes'][2]['characteristics'][0]['unit'] = 'cm'
    source.graph_data = g
    await db.flush()
    output = await extract(db, source, admin_user)
    assert sc.spec_requirement == '10±0.1 mm' and sc.safety_approval_status == 'submitted'
    assert next(item for item in output if item.sc_id == sc.sc_id).review_required


@pytest.mark.parametrize("state", ["submitted", "approved"])
async def test_protected_unit_source_review_uses_canonical_criteria(db, source, admin_user, admin_client, state):
    g = deepcopy(source.graph_data)
    g["nodes"][2]["characteristics"][0].update(specification="10", unit="mm")
    source.graph_data = g
    await db.flush()
    await extract(db, source, admin_user)
    sc = next(s for s in await sc_rows(db, source) if str(s.source_characteristic_id) == IDS[0])
    response = await admin_client.post(f"/api/special-characteristics/{sc.sc_id}/safety-submit", json={
        "safety_regulation_ref": "SIMULATED", "safety_verification_method": "Measured"})
    assert response.status_code == 200
    if state == "approved":
        response = await admin_client.post(f"/api/special-characteristics/{sc.sc_id}/safety-approve", json={})
        assert response.status_code == 200
    await db.refresh(sc)
    record = svc._characteristic_records(source)[IDS[0]]
    assert sc.spec_requirement == "10 mm"
    assert not svc._source_review_required(sc, record)
    g = deepcopy(source.graph_data)
    g["nodes"][2]["characteristics"][0]["unit"] = "cm"
    source.graph_data = g
    assert svc._source_review_required(sc, svc._characteristic_records(source)[IDS[0]])
    assert sc.spec_requirement == "10 mm" and sc.safety_approval_status == state
