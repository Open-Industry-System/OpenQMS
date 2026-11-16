"""Versioned outcome contract keeps v1 history and fences corrected v2 material."""
import hashlib
import hmac
import json
import pytest
from app.config import settings
from app.services.capa_outcome_review import outcome_revision


def test_v1_signature_bytes_remain_unchanged():
    material = {'contract':'capa.outcome-review.v1','d5_measures':[]}
    encoded = json.dumps(material,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    assert outcome_revision(material) == hmac.new(settings.SECRET_KEY.encode(),
        b'openqms.capa.outcome-review.v1\0'+encoded,hashlib.sha256).hexdigest()


def test_corrected_material_needs_explicit_v2_contract():
    corrected = {'measure_id':'12345678-1234-1234-1234-123456789011','correction_revision_id':'12345678-1234-1234-1234-123456789012','correction_revision_no':1}
    with pytest.raises(ValueError):
        outcome_revision({'contract':'capa.outcome-review.v1','d5_measures':[corrected]})
    material = {'contract':'capa.outcome-review.v2','d5_measures':[corrected]}
    encoded = json.dumps(material,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    assert outcome_revision(material) == hmac.new(settings.SECRET_KEY.encode(),
        b'openqms.capa.outcome-review.v2\0'+encoded,hashlib.sha256).hexdigest()

@pytest.mark.parametrize('row', [
    {'correction_revision_id':None,'correction_revision_no':1},
    {'correction_revision_id':'bad','correction_revision_no':1},
    {'correction_revision_id':'12345678-1234-1234-1234-123456789012','correction_revision_no':0},
])
def test_v2_rejects_invalid_correction_identity(row):
    with pytest.raises(ValueError):
        outcome_revision({'contract':'capa.outcome-review.v2','d5_measures':[row]})

from tests.capa.test_r6_d5_corrections import correction_case, staff_case, d5_case, committed_runtime
from tests.capa.test_capa_outcome_decision import decision_provider


async def stored_review_fixture(c):
    """An explicitly seeded pre-existing D8 round, never normal D7 re-entry.

    Complete D7/local manual gate flow depends on Task6B and remains a later
    acceptance gate. This fixture exercises actual normal employee review APIs.
    """
    from tests.capa.test_d5_outcome_fence import outcome_ready
    from sqlalchemy import update
    from app.models.role import RolePermission
    await outcome_ready(c)
    await c.db.execute(update(RolePermission).where(RolePermission.role_id==c.scope.role_id,
        RolePermission.module=='capa').values(permission_level=4))
    await c.db.commit()
    return f'/api/capa/{c.report.report_id}'


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_normal_reject_then_correct_invalidates_old_expectation(correction_case):
    from app.models.capa import CAPAEightD
    from app.schemas.capa import AdvanceRequest
    from app.services.capa_outcome_review import collect_outcome_material, require_outcome_expectation
    from app.services.capa_current_access import current_capa_access
    from app.services.capa_review_guard import OutcomeReviewConflict
    c = correction_case
    root = await stored_review_fixture(c)
    old = await c.client.get(root+'/outcome-review')
    assert old.status_code == 200, old.text
    seen = old.json()
    assert seen['contract'] == 'capa.outcome-review.v1'
    rejection = await c.client.post(root+'/advance',json=dict(target_state='D7_PREVENTION',reject_reason='fix measure',
        expected_outcome_revision=seen['revision'],expected_review_round_id=seen['review_round_id']))
    assert rejection.status_code == 200, rejection.text
    current = (await c.client.get(c.url)).json()
    corrected = await c.client.post(c.url+'/corrections',json=dict(operation_key='post-rejection',
        expected_measure_version=current['current_version'],expected_material_version=current['material_version'],
        final_text='review corrected text',reason='review correction'))
    assert corrected.status_code == 200, corrected.text
    # The normal legacy D7/gate path stays protected. Do not seed a fresh passed
    # analysis or bypass a gate to pretend that normal re-entry is complete.
    async with c.factory(binding=c.binding) as db:
        capa = await db.get(CAPAEightD,c.report.report_id)
        assert capa.status == 'D7_PREVENTION'
        db.info['outcome_read_access'] = await current_capa_access(db,c.scope)
        material = await collect_outcome_material(db,capa)
        assert material['contract'] == 'capa.outcome-review.v2'
        measure = material['d5_measures'][0]
        assert measure['final_text'] == 'review corrected text'
        assert measure['correction_revision_no'] == 1 and measure['correction_revision_id']
        assert len(measure['sources']) == 1
        with pytest.raises(OutcomeReviewConflict):
            await require_outcome_expectation(db,c.scope,capa,AdvanceRequest(target_state='D8_CLOSURE',
                expected_outcome_revision=seen['revision'],expected_review_round_id=seen['review_round_id']))


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('corrected',[False,True])
async def test_stored_round_approval_preserves_its_contract_and_signature(correction_case, decision_provider, corrected):
    c = correction_case
    if corrected:
        current = (await c.client.get(c.url)).json()
        response = await c.client.post(c.url+'/corrections',json=dict(operation_key='before-stored-round',
            expected_measure_version=current['current_version'],expected_material_version=current['material_version'],
            final_text='v2 reviewed text',reason='v2 reason'))
        assert response.status_code == 200, response.text
    root = await stored_review_fixture(c)
    pending = await c.client.get(root+'/outcome-review')
    assert pending.status_code == 200, pending.text
    seen = pending.json()
    assert seen['contract'] == ('capa.outcome-review.v2' if corrected else 'capa.outcome-review.v1')
    approval = await c.client.post(root+'/advance',json=dict(target_state='D8_CLOSURE',
        expected_outcome_revision=seen['revision'],expected_review_round_id=seen['review_round_id']))
    assert approval.status_code == 200, approval.text
    closed = await c.client.get(root+'/outcome-review')
    assert closed.status_code == 200, closed.text
    assert closed.json()['binding_status'] == 'verified'
    assert closed.json()['revision'] == seen['revision']
    assert closed.json()['contract'] == seen['contract']
    frozen = await c.client.post(c.url+'/corrections',json=dict(operation_key='frozen',
        expected_measure_version='stale',expected_material_version='stale',final_text='no',reason='no'))
    assert frozen.status_code == 409
    archived = await c.client.post(root+'/advance',json={})
    assert archived.status_code == 200, archived.text
    final = await c.client.get(root+'/outcome-review')
    assert final.status_code == 200, final.text
    assert final.json()['binding_status'] == 'verified' and final.json()['revision'] == seen['revision']

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_d7_material_counter_covers_insert_change_and_hash_refresh_only(db,default_factory,admin_user):
    import copy
    from tests.capa.test_capa_d7_action_service import _make_capa, _make_fmea, _link_capa_fmea
    from app.services.capa_d7_action_service import record_d7_action
    from app.schemas.capa_verification import D7NodeActionCreate
    from app.services.capa_d4_material import material_version
    capa = await _make_capa(db,default_factory.id,admin_user.user_id)
    fmea = await _make_fmea(db,default_factory.id,admin_user.user_id)
    await _link_capa_fmea(db,capa,fmea)
    request = D7NodeActionCreate(action='confirmed',fmea_id=fmea.fmea_id,
        failure_mode_node_id='fm-1',failure_cause_node_id='c-1',match_source='linked')
    before = await material_version(db,capa.report_id)
    await record_d7_action(db,capa,request,admin_user)
    inserted = await material_version(db,capa.report_id)
    assert inserted != before
    await record_d7_action(db,capa,request,admin_user)
    assert await material_version(db,capa.report_id) == inserted
    graph = copy.deepcopy(fmea.graph_data)
    graph['nodes'][0]['name'] = 'updated mode'
    fmea.graph_data = graph
    await db.flush()
    await record_d7_action(db,capa,request,admin_user)
    refreshed = await material_version(db,capa.report_id)
    assert refreshed != inserted
    await record_d7_action(db,capa,request.model_copy(update={'action':'skipped','reason':'checked'}),admin_user)
    assert await material_version(db,capa.report_id) != refreshed


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_doc_gate_failed_analysis_is_material(db,capa_d8_gate,docg_no_creds):
    from app.services.capa_doc_gate_service import generate_impact_analysis
    from app.services.capa_d4_material import material_version
    capa,user = capa_d8_gate
    before = await material_version(db,capa.report_id)
    with pytest.raises(ValueError,match='BLOCKED'):
        await generate_impact_analysis(db,capa,user.user_id)
    assert await material_version(db,capa.report_id) != before


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_doc_gate_decision_is_material(db,capa_with_empty_done_analysis):
    from app.services.capa_doc_gate_service import confirm_no_affected
    from app.services.capa_d4_material import material_version
    capa,user = capa_with_empty_done_analysis
    before = await material_version(db,capa.report_id)
    assert (await confirm_no_affected(db,capa,user.user_id))['decision']=='passed'
    assert await material_version(db,capa.report_id) != before
