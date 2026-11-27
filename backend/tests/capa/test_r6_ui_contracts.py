"""Employee UI reads remain VIEW, selected source authority and exact version domains."""
import pytest
from sqlalchemy import update
from app.models.capa import CAPAEightD
from tests.capa.test_r6_local_closure import local_case, local_form, correction_case, staff_case, d5_case, committed_runtime
pytestmark=pytest.mark.requires_db

async def test_selected_form_exposes_server_correction_qualification(correction_case):
    c=correction_case
    response=await c.client.get(c.url)
    assert response.status_code==200,response.text
    assert response.json()['can_correct'] is True
    assert response.json()['current_version'] and response.json()['material_version']

async def test_local_form_has_action_specific_current_qualification(local_case):
    c=local_case
    form=await local_form(c)
    assert form['can_save_prevention'] is True
    assert form['can_save_manual_analysis'] is False
    assert form['can_review_propagation'] is True
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report.report_id).values(status='D7_COMPLETED'))
        await db.commit()
    form=await local_form(c)
    assert form['can_save_prevention'] is False
    assert form['can_review_propagation'] is True

async def test_manual_catalog_is_controlled_and_bound_to_local_form(local_case):
    c=local_case
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report.report_id).values(status='D8_GATE_PENDING'))
        await db.commit()
    form=await local_form(c)
    response=await c.client.get(c.root+'/manual-doc-catalog')
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    catalog=response.json()
    assert catalog['material_version']==form['material_version']
    assert catalog['items']
    assert all('existing_targets' in item and 'add_anchors' in item for item in catalog['items'])

async def test_verification_read_projects_validated_inherited_origins(local_case):
    c=local_case
    response=await c.client.get(c.root+'/root-cause-verifications')
    assert response.status_code==200,response.text
    assert all(isinstance(row['known_source_origins'],list) for row in response.json())
    assert response.json()

async def test_manual_catalog_baseline_ties_match_writer_selector(local_case):
    from uuid import UUID
    from app.models.fmea_version import FMEAVersion
    from app.services.capa_r6_local_closure import candidates_metadata,controlled_manual_candidates
    from app.services.capa_doc_gate_service import _get_baseline_version
    c=local_case
    async with c.factory(binding=c.binding) as db:
        capa=await db.get(CAPAEightD,c.report.report_id)
        doc=c.docs[0]
        for identifier,major in [('00000000-0000-4000-8000-000000000010',20),('00000000-0000-4000-8000-000000000020',10)]:
            db.add(FMEAVersion(version_id=UUID(identifier),fmea_id=doc.fmea_id,factory_id=doc.factory_id,
                major_no=major,minor_no=0,created_at=capa.created_at,sha256_hash=str(major)[0]*64,
                snapshot={'nodes':[{'id':'tie-cause','type':'FailureCause','name':'fixture'}],'edges':[]}))
        await db.flush()
        metadata=await candidates_metadata(db,capa,c.scope.user.user_id)
        selected=next(item for item in metadata if item['object_id']==str(doc.fmea_id))
        baseline=await _get_baseline_version(db,doc.fmea_id,capa.created_at,'fmea')
        assert selected['baseline_version_id']==str(baseline.version_id)=='00000000-0000-4000-8000-000000000010'
        catalog=await controlled_manual_candidates(db,capa,metadata,c.scope.user.user_id)
        assert next(item for item in catalog if item['doc_id']==str(doc.fmea_id))['baseline_version_id']==selected['baseline_version_id']

async def test_manual_catalog_reauthorizes_candidate_set_before_document_bodies(local_case,monkeypatch):
    from sqlalchemy import event
    from app.models.role import RolePermission
    from app.services import capa_r6_local_closure as local
    c=local_case
    async with c.factory(binding=c.binding) as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report.report_id).values(status='D8_GATE_PENDING'))
        await db.commit()
    original=local.controlled_manual_candidates
    async def revoke(db,capa,candidates,actor_id):
        async with c.factory(binding=c.binding) as other:
            await other.execute(update(RolePermission).where(RolePermission.role_id==c.scope.role_id,RolePermission.module=='fmea').values(permission_level=0))
            await other.commit()
        return await original(db,capa,candidates,actor_id)
    monkeypatch.setattr(local,'controlled_manual_candidates',revoke)
    bodies=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT') and 'fmea_documents.graph_data' in statement:bodies.append(statement)
    event.listen(c.engine.sync_engine,'before_cursor_execute',capture)
    try:
        response=await c.client.get(c.root+'/manual-doc-catalog')
        assert response.status_code==403,response.text
        assert bodies==[]
    finally:event.remove(c.engine.sync_engine,'before_cursor_execute',capture)

@pytest.mark.parametrize('kind,field,target_kind,node_type',[
    ('fmea','name','fmea_node','FailureCause'),
    ('control_plan','control_method','cp_item','FailureMode'),
])
async def test_ui_add_payload_matches_actual_strict_manual_grammar(kind,field,target_kind,node_type):
    from types import SimpleNamespace
    from uuid import uuid4
    from app.services.capa_doc_gate_service import _cand_from_cp,_cand_from_fmea
    from app.services.capa_r6_local_closure import strict_affected
    identifier=uuid4()
    baseline=SimpleNamespace(version_id=uuid4(),major_no=1,minor_no=0,sha256_hash='a'*64,
        snapshot={'nodes':[{'id':'parent','type':'ProcessStep','name':'existing'}],'edges':[]},
        items_snapshot={'items':[{'item_id':'existing','source_fmea_node_id':'parent'}]})
    parent=SimpleNamespace(fmea_id=identifier,cp_id=identifier,title='actual typed catalog')
    candidate=(_cand_from_fmea if kind=='fmea' else _cand_from_cp)(parent,baseline)
    point={'expected_action':'add','target_kind':target_kind,'field':field,
        'add_anchor':{'parent_node_id':'parent','node_type':node_type,'business_key':'new-business'}}
    body=[{'doc_type':kind,'doc_id':str(identifier),'update_suggestion':'employee add', 'key_points':[point]}]
    assert strict_affected(body,[candidate])[0]['key_points']==[point]
    missing={**point};missing.pop('field')
    with pytest.raises(ValueError):strict_affected([{**body[0],'key_points':[missing]}],[candidate])
