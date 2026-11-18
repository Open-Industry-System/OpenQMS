"""Source explanations require the complete item's authority before body reads."""
import pytest
from tests.capa.test_r6_d4_confirm import staff_candidate
pytestmark=pytest.mark.requires_db

@pytest.mark.asyncio
async def test_candidate_source_details_are_complete_and_reauthenticated(staff_candidate):
    c=staff_candidate
    url=f'/api/capa/{c.report_id}/sources/d4-candidate/{c.candidate_id}'
    response=await c.actor().client.get(url)
    assert response.status_code==200,response.text
    body=response.json()
    assert body['original_text']=='RESTRICTED-CANDIDATE'
    assert body['supporting']==['support'] and body['opposing']==['against']
    assert body['proof']['state']=='not_issued_by_confirmation'
    assert len(body['sources'])==1
    assert body['sources'][0]['current_state']=='current'
    assert response.headers['cache-control']=='no-store'
    link=body['sources'][0]['evidence_url']
    assert (await c.actor().client.get(link)).status_code==200
    await c.actor().revoke('fmea')
    for path in [url,link]:
        denied=await c.actor().client.get(path)
        assert denied.status_code in {403,404}
        assert 'RESTRICTED-CANDIDATE' not in denied.text and 'source' not in denied.json().get('sources',{})

@pytest.mark.asyncio
async def test_changed_node_is_honestly_stale(staff_candidate):
    from app.models.fmea import FMEADocument
    c=staff_candidate
    async with c.session() as db:
        doc=await db.get(FMEADocument,c.source_a.fmea_id)
        doc.graph_data={'nodes':[],'edges':[]}
        await db.commit()
    response=await c.actor().client.get(f'/api/capa/{c.report_id}/sources/d4-candidate/{c.candidate_id}')
    assert response.status_code==200,response.text
    source=response.json()['sources'][0]
    assert source['current_state'] in {'stale','unavailable'}
    assert source.get('evidence') is None

@pytest.mark.asyncio
async def test_original_verification_source_is_guarded_when_current_root_is_empty(r6_case):
    from app.models.capa import CapaRootCauseVerification
    c=r6_case
    async with c.session() as db:
        row=CapaRootCauseVerification(capa_id=c.report_id,factory_id=c.factory_id,root_cause_text='HISTORIC-VERIFICATION',
            method='observation',result='old evidence',conclusion='pending',is_verified=False,
            source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'})
        db.add(row)
        await db.commit()
        vid=row.verification_id
    await c.actor().revoke('fmea')
    before=await c.snapshot()
    for method,path,body in [('GET',f'/api/capa/{c.report_id}/root-cause-verifications',None),
            ('PATCH',f'/api/capa/{c.report_id}/root-cause-verifications/{vid}',{'conclusion':'passed','method':'observation'})]:
        response=await c.actor().client.request(method,path,json=body)
        assert response.status_code in {403,404},response.text
        assert 'HISTORIC-VERIFICATION' not in response.text
    assert await c.snapshot()==before

@pytest.mark.asyncio
async def test_verification_audit_retains_reference_without_source_body(r6_case):
    import json
    from sqlalchemy import select
    from app.models.audit import AuditLog
    c=r6_case
    response=await c.actor().client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=dict(
        root_cause_text='PRIVATE-VERIFY-BODY',method='measurement',result='PRIVATE-VERIFY-RESULT',conclusion='passed',
        source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'}))
    assert response.status_code==200,response.text
    async with c.session() as db:
        rows=list(await db.scalars(select(AuditLog).where(AuditLog.record_id==c.report_id)))
        assert rows
        assert all('PRIVATE-VERIFY-' not in json.dumps(row.changed_fields) for row in rows)

@pytest.mark.asyncio
async def test_historical_verification_audit_is_sql_projected_without_mutating_storage(r6_case):
    import json
    from app.models.audit import AuditLog
    from app.models.capa import CapaRootCauseVerification
    from app.services.log_service import list_audit_logs
    c=r6_case
    async with c.session() as db:
        verification=CapaRootCauseVerification(capa_id=c.report_id,factory_id=c.factory_id,root_cause_text='PRIVATE-OLD-ROOT',conclusion='pending',is_verified=False)
        db.add(verification)
        await db.flush()
        vid=verification.verification_id
        row=AuditLog(table_name='capa_eightd',record_id=c.report_id,action='D4_VERIFICATION_UPDATED',
            changed_fields={'verification_id':str(vid),'method':'PRIVATE-OLD-METHOD','source_ref':{'untrusted':'PRIVATE-OLD-SOURCE'}},
            old_values={'evidence':'PRIVATE-OLD-EVIDENCE'},new_values={'root_cause_text':'PRIVATE-OLD-ROOT'},
            operated_by=c.actor('second_edit').user_id,factory_id=c.factory_id)
        db.add(row)
        await db.commit()
        row_id=row.log_id
    await c.actor().revoke('fmea')
    async with c.session() as db:
        items,_=await list_audit_logs(db,{'action':'D4_VERIFICATION_UPDATED'},1,20,actor_id=c.actor().user_id)
        assert len(items)==1
        assert 'PRIVATE-OLD-' not in json.dumps(items)
        assert items[0]['changed_fields']['verification_id']==str(vid)
        stored=await db.get(AuditLog,row_id)
        assert stored.old_values=={'evidence':'PRIVATE-OLD-EVIDENCE'}

from tests.capa.test_d5_measure_visibility import d5_case

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['d5-proposal','d5-measure'])
async def test_d5_details_use_selected_items_full_sources_not_current_root(d5_case,kind):
    from app.services.capa_sources_view import source_details,evidence
    from app.models.role import UserProductLine
    from sqlalchemy import delete
    from app.models.capa_r6 import CapaD5MeasureRevision
    from uuid import uuid4
    c=d5_case
    item_id=c.proposals[1] if kind=='d5-proposal' else c.measures[1]
    result=await source_details(c.db,c.actors[2],c.report.report_id,kind,item_id)
    assert len(result['sources'])==2
    assert {s['fmea_id'] for s in result['sources']}=={d.fmea_id for d in c.docs}
    # Current root has no controlled source set; source B remains necessary.
    for scope in c.actors[:2]:
        with pytest.raises((PermissionError,LookupError)):
            await source_details(c.db,scope,c.report.report_id,kind,item_id)
    if kind=='d5-measure':
        c.db.add(CapaD5MeasureRevision(revision_id=uuid4(),report_id=c.report.report_id,measure_id=item_id,
            revision_no=1,predecessor_id=None,final_text='CURRENT-CORRECTION',reason='CONTROLLED-CORRECTION-REASON',actor_id=c.actors[2].user.user_id))
        await c.db.commit()
        result=await source_details(c.db,c.actors[2],c.report.report_id,kind,item_id)
        assert result['final_text']=='CURRENT-CORRECTION'
        assert result['adopted_text']=='secret final 2'
    source_id=result['sources'][1]['source_id']
    await c.db.execute(delete(UserProductLine).where(UserProductLine.user_id==c.actors[2].user.user_id,
        UserProductLine.product_line_code==c.line_b.code))
    await c.db.commit()
    with pytest.raises((PermissionError,LookupError)):
        await evidence(c.db,c.actors[2],c.report.report_id,kind,item_id,source_id)

@pytest.mark.asyncio
async def test_source_changed_during_detail_is_not_returned_as_current(staff_candidate,monkeypatch):
    from app.services import capa_sources_view as service
    from app.models.fmea import FMEADocument
    c=staff_candidate
    original=service.item_metadata
    calls=0
    async def change_on_final(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==2:
            async with c.session() as db:
                doc=await db.get(FMEADocument,c.source_a.fmea_id)
                doc.graph_data={'nodes':[],'edges':[]}
                await db.commit()
        return await original(*args,**kwargs)
    monkeypatch.setattr(service,'item_metadata',change_on_final)
    response=await c.actor().client.get(f'/api/capa/{c.report_id}/sources/d4-candidate/{c.candidate_id}')
    assert response.status_code==200,response.text
    assert response.json()['sources'][0]['current_state'] in {'stale','unavailable'}
    assert response.json()['sources'][0]['evidence'] is None

@pytest.mark.asyncio
async def test_legacy_audit_payload_shapes_and_cross_report_refs_never_expand_details(r6_case):
    import json
    from uuid import uuid4
    from app.models.audit import AuditLog
    from app.models.capa import CAPAEightD,CapaRootCauseVerification
    from app.services.log_service import list_audit_logs
    c=r6_case
    async with c.session() as db:
        other=CAPAEightD(document_no='OTHER-'+uuid4().hex,title='other',factory_id=c.factory_id,product_line_code=c.line,created_by=c.actor().user_id)
        db.add(other)
        await db.flush()
        verification=CapaRootCauseVerification(capa_id=other.report_id,factory_id=c.factory_id,root_cause_text='PRIVATE-AUDIT-FOREIGN',conclusion='pending',is_verified=False)
        db.add(verification)
        await db.flush()
        foreign_id=verification.verification_id
        shapes=['PRIVATE-AUDIT-SCALAR',['PRIVATE-AUDIT-ARRAY'],None,{},
            {'verification_id':['PRIVATE-AUDIT-ID']},{'verification_id':'PRIVATE-AUDIT-MALFORMED'},
            {'verification_id':str(uuid4())},{'verification_id':str(foreign_id)}]
        for shape in shapes:
            db.add(AuditLog(table_name='capa_eightd',record_id=c.report_id,action='D4_VERIFICATION_UPDATED',
                changed_fields=shape,old_values={'evidence':'PRIVATE-AUDIT-OLD'},new_values={'result':'PRIVATE-AUDIT-NEW'},
                operated_by=c.actor().user_id,factory_id=c.factory_id))
        await db.commit()
    await c.actor().revoke('fmea')
    seen=[]
    async with c.session() as db:
        for page in range(1,len(shapes)+1):
            rows,total=await list_audit_logs(db,{'action':'D4_VERIFICATION_UPDATED'},page,1,actor_id=c.actor().user_id)
            assert total==len(shapes) and len(rows)==1
            row=rows[0]
            assert 'PRIVATE-AUDIT-' not in json.dumps(row)
            assert row['changed_fields'].get('verification_id') is None
            assert row['old_values'] is row['new_values'] is None
            assert row['changed_fields']['details_status']=='historical_audit_body_unattested'
            seen.append(row['log_id'])
        assert len(set(seen))==len(shapes)

@pytest.mark.asyncio
async def test_verification_final_read_reauthorizes_original_source(r6_case,monkeypatch):
    from app.models.capa import CapaRootCauseVerification
    from app.services import capa_verification_service as service
    c=r6_case
    async with c.session() as db:
        db.add(CapaRootCauseVerification(capa_id=c.report_id,factory_id=c.factory_id,root_cause_text='PRIVATE-VERIFY-FINAL',
            conclusion='pending',is_verified=False,source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'}))
        await db.commit()
    original=service._require_original_verification_sources
    calls=0
    async def revoke_on_final(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==2: await c.actor().revoke('fmea')
        return await original(*args,**kwargs)
    monkeypatch.setattr(service,'_require_original_verification_sources',revoke_on_final)
    response=await c.actor().client.get(f'/api/capa/{c.report_id}/root-cause-verifications')
    assert response.status_code==403,response.text
    assert 'PRIVATE-VERIFY-FINAL' not in response.text

@pytest.mark.asyncio
async def test_verification_source_change_cannot_drop_old_source_authority(r6_case):
    from app.models.capa import CapaRootCauseVerification,CAPAEightD
    from app.models.fmea import FMEADocument
    from uuid import uuid4
    c=r6_case
    async with c.session() as db:
        verification=CapaRootCauseVerification(capa_id=c.report_id,factory_id=c.factory_id,root_cause_text='PRIVATE-OLD-A',
            conclusion='pending',is_verified=False,source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'})
        db.add(verification)
        replacement=FMEADocument(document_no='NEW-'+uuid4().hex,title='readable B',factory_id=c.factory_id,
            product_line_code=c.line,graph_data={'nodes':[{'id':'cause','type':'FailureCause'}],'edges':[]})
        db.add(replacement)
        await db.flush()
        report=await db.get(CAPAEightD,c.report_id)
        report.fmea_ref_id=replacement.fmea_id
        source=await db.get(FMEADocument,c.source_a.fmea_id)
        source.factory_id=c.outside_factory_id
        source.product_line_code=c.outside_source.product_line_code
        await db.commit()
        vid,b_id=verification.verification_id,replacement.fmea_id
    before=await c.snapshot()
    response=await c.actor().client.patch(f'/api/capa/{c.report_id}/root-cause-verifications/{vid}',json={
        'conclusion':'passed','method':'measurement','source_ref':{'fmea_id':str(b_id),'cause_node_id':'cause'}})
    assert response.status_code==403,response.text
    assert await c.snapshot()==before

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['clear','replace'])
async def test_clearing_verification_ref_cannot_erase_original_source_restriction(r6_case,change):
    c=r6_case
    created=await c.actor().client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=dict(
        root_cause_text='PRIVATE-ORIGINAL-A',method='observation',conclusion='pending',
        source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'}))
    assert created.status_code==200,created.text
    vid=created.json()['verification_id']
    new_ref=None
    if change=='replace':
        from uuid import uuid4
        from app.models.fmea import FMEADocument
        from app.models.capa import CAPAEightD
        async with c.session() as db:
            doc=FMEADocument(document_no='REF-B-'+uuid4().hex,title='readable B',factory_id=c.factory_id,product_line_code=c.line,
                graph_data={'nodes':[{'id':'cause','type':'FailureCause'}],'edges':[]})
            db.add(doc)
            await db.flush()
            report=await db.get(CAPAEightD,c.report_id)
            report.fmea_ref_id=doc.fmea_id
            new_ref={'fmea_id':str(doc.fmea_id),'cause_node_id':'cause'}
            await db.commit()
    cleared=await c.actor().client.patch(f'/api/capa/{c.report_id}/root-cause-verifications/{vid}',json={'source_ref':new_ref})
    assert cleared.status_code==200,cleared.text
    assert 'r6_source_origins' not in cleared.json()
    assert cleared.json()['root_cause_text']=='PRIVATE-ORIGINAL-A'
    if change=='replace':
        async with c.session() as db:
            source=await db.get(FMEADocument,c.source_a.fmea_id)
            source.factory_id=c.outside_factory_id
            source.product_line_code=c.outside_source.product_line_code
            await db.commit()
    else:
        await c.actor().revoke('fmea')
    denied=await c.actor().client.get(f'/api/capa/{c.report_id}/root-cause-verifications')
    assert denied.status_code==403,denied.text
    assert 'PRIVATE-ORIGINAL-A' not in denied.text

@pytest.mark.asyncio
async def test_retained_verification_sources_guard_all_body_consumers_and_review_references(r6_case,monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy import event
    from app.models.capa import CAPAEightD
    from app.services.capa_ppt_service import generate_content
    from app.services.capa_outcome_review import collect_outcome_material
    from app.services.capa_d4_text_preview import get_version
    from app.services.knowledge_sink_service import _assemble_deterministic_fields
    from app.services.capa_lateral_diffusion_service import build_source_snapshot
    from app.services.capa_review_source_guard import _source_capa_ids
    from app.services.capa_current_access import current_capa_access
    c=r6_case
    created=await c.actor().client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=dict(
        root_cause_text='PRIVATE-CONSUMER-VERIFY',method='observation',conclusion='passed',
        source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'}))
    assert created.status_code==200,created.text
    vid=created.json()['verification_id']
    version=(await c.actor().client.get(f'/api/capa/{c.report_id}')).json()['material_version']
    edited=await c.actor().client.put(f'/api/capa/{c.report_id}',json={'d4_root_cause':'PRIVATE-CONSUMER-VERIFY','expected_material_version':version})
    assert edited.status_code==200,edited.text
    cleared=await c.actor().client.patch(f'/api/capa/{c.report_id}/root-cause-verifications/{vid}',json={'source_ref':None})
    assert cleared.status_code==200,cleared.text
    scope=SimpleNamespace(user=SimpleNamespace(user_id=c.actor().user_id))
    async with c.session() as db:
        assert c.report_id in await _source_capa_ids(db,'fmea',c.source_a.fmea_id)
        content=await generate_content(db,c.report_id,scope=scope)
        assert content.root_cause_verifications[0]['root_cause_text']=='PRIVATE-CONSUMER-VERIFY'
        # The legacy preview cannot encode the retained A after source_ref clears.
        with pytest.raises(PermissionError): await get_version(db,scope,c.report_id)
    await c.actor().revoke('fmea')
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many): statements.append(statement.lower())
    event.listen(c.runtime.engine.sync_engine,'before_cursor_execute',capture)
    try:
        for consumer in ['ppt','outcome','preview']:
            async with c.session() as db:
                report=await db.get(CAPAEightD,c.report_id)
                with pytest.raises(PermissionError):
                    if consumer=='ppt': await generate_content(db,c.report_id,scope=scope)
                    elif consumer=='outcome':
                        db.info['outcome_read_access']=await current_capa_access(db,scope)
                        await collect_outcome_material(db,report)
                    elif consumer=='preview': await get_version(db,scope,c.report_id)
        # These collectors consume only safe verification metadata/references,
        # so current root/metadata behavior remains supported without FMEA A.
        async with c.session() as db:
            report=await db.get(CAPAEightD,c.report_id)
            await _assemble_deterministic_fields(db,report)
            await build_source_snapshot(db,report)
        assert not any('capa_root_cause_verification.root_cause_text' in query.split('from',1)[0] or 'capa_root_cause_verification.result' in query.split('from',1)[0]
            or 'capa_root_cause_verification.evidence_attachments' in query.split('from',1)[0] for query in statements)
    finally: event.remove(c.runtime.engine.sync_engine,'before_cursor_execute',capture)

@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['create','update'])
async def test_commit_then_source_revoke_blocks_refresh_before_verification_body_select(r6_case,monkeypatch,operation):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import event
    from app.services import capa_verification_service as service
    c=r6_case
    payload=dict(root_cause_text='PRIVATE-COMMIT-VERIFY',method='observation',conclusion='pending',
        source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'})
    vid=None
    if operation=='update':
        created=await c.actor().client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=payload)
        assert created.status_code==200,created.text
        vid=created.json()['verification_id']
    original_guard=service._require_original_verification_sources
    async def tag_session(db,*args,**kwargs):
        db.info['_task5_revoke_after_commit']=True
        return await original_guard(db,*args,**kwargs)
    monkeypatch.setattr(service,'_require_original_verification_sources',tag_session)
    original_commit=AsyncSession.commit
    revoked=False
    async def revoke_after_commit(db):
        nonlocal revoked
        await original_commit(db)
        if db.info.pop('_task5_revoke_after_commit',False) and not revoked:
            await c.actor().revoke('fmea')
            revoked=True
    monkeypatch.setattr(AsyncSession,'commit',revoke_after_commit)
    body_reads=[]
    def capture(conn,cursor,statement,parameters,context,many):
        query=statement.lower()
        if revoked and query.lstrip().startswith('select') and 'from capa_root_cause_verification' in query:
            fields=query.split('from',1)[0]
            if any(name in fields for name in ['.root_cause_text','.result','.evidence_attachments']): body_reads.append(query)
    event.listen(c.runtime.engine.sync_engine,'before_cursor_execute',capture)
    try:
        response=(await c.actor().client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=payload) if operation=='create' else
            await c.actor().client.patch(f'/api/capa/{c.report_id}/root-cause-verifications/{vid}',json={'conclusion':'passed'}))
        assert response.status_code==403,response.text
        assert revoked and body_reads==[]
    finally: event.remove(c.runtime.engine.sync_engine,'before_cursor_execute',capture)

@pytest.mark.asyncio
async def test_proof_status_is_distinct_from_current_node_and_bound_to_selected_item(d5_case):
    from app.services.capa_sources_view import source_details
    c=d5_case
    result=await source_details(c.db,c.actors[2],c.report.report_id,'d5-proposal',c.proposals[0])
    assert all(s['current_state']=='current' for s in result['sources'])
    assert result['proof']['state']=='active' and result['proof']['bound_to_item']
    assert result['proof']['revision_id']==c.revision.revision_id
    c.proof.status='superseded'
    await c.db.commit()
    result=await source_details(c.db,c.actors[2],c.report.report_id,'d5-proposal',c.proposals[0])
    assert all(s['current_state']=='current' for s in result['sources'])
    assert result['proof']['state']=='superseded' and result['proof']['bound_to_item']
    assert result['proof']['basis_current'] is False

@pytest.mark.asyncio
@pytest.mark.parametrize('guess,revoked,expected',[('PRIVATE-STAGE-A',True,403),('different guess',True,403),('PRIVATE-STAGE-A',False,200)])
async def test_unreadable_verification_cannot_be_used_as_stage_transition_oracle(r6_case,guess,revoked,expected):
    from app.models.capa import CAPAEightD
    from sqlalchemy import select,event
    c=r6_case
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id)
        report.status='D4_ROOT_CAUSE'
        await db.commit()
    created=await c.actor().client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=dict(
        root_cause_text='PRIVATE-STAGE-A',method='observation',conclusion='passed',
        source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'}))
    assert created.status_code==200,created.text
    vid=created.json()['verification_id']
    cleared=await c.actor().client.patch(f'/api/capa/{c.report_id}/root-cause-verifications/{vid}',json={'source_ref':None})
    assert cleared.status_code==200,cleared.text
    if revoked: await c.actor().revoke('fmea')
    assert (await c.actor().client.get(f'/api/capa/{c.report_id}/root-cause-verifications')).status_code==(403 if revoked else 200)
    version=(await c.actor().client.get(f'/api/capa/{c.report_id}')).json()['material_version']
    edited=await c.actor().client.put(f'/api/capa/{c.report_id}',json={'d4_root_cause':guess,'expected_material_version':version})
    assert edited.status_code==200,edited.text
    before=await c.snapshot()
    comparisons=[]
    def capture(conn,cursor,statement,parameters,context,many):
        query=statement.lower()
        if 'from capa_root_cause_verification' in query and 'root_cause_text =' in query: comparisons.append(query)
    event.listen(c.runtime.engine.sync_engine,'before_cursor_execute',capture)
    try:
        response=await c.actor().client.post(f'/api/capa/{c.report_id}/advance',json={})
        assert response.status_code==expected,response.text
        if revoked: assert comparisons==[]
    finally: event.remove(c.runtime.engine.sync_engine,'before_cursor_execute',capture)
    if revoked: assert await c.snapshot()==before
    else: assert (await c.report()).status=='D5_CORRECTION'

@pytest.mark.asyncio
async def test_manual_verification_without_known_sources_does_not_require_fmea_for_stage_use(r6_case):
    from app.models.capa import CAPAEightD
    c=r6_case
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id)
        report.status='D4_ROOT_CAUSE'
        await db.commit()
    await c.actor().revoke('fmea')
    created=await c.actor().client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=dict(
        root_cause_text='ordinary manual root',method='observation',conclusion='passed'))
    assert created.status_code==200,created.text
    version=(await c.actor().client.get(f'/api/capa/{c.report_id}')).json()['material_version']
    edited=await c.actor().client.put(f'/api/capa/{c.report_id}',json={'d4_root_cause':'ordinary manual root','expected_material_version':version})
    assert edited.status_code==200,edited.text
    advanced=await c.actor().client.post(f'/api/capa/{c.report_id}/advance',json={})
    assert advanced.status_code==200,advanced.text
    assert (await c.report()).status=='D5_CORRECTION'

async def _complete_protected_ppt(c,kind='verification'):
    from app.models.capa import CAPAEightD
    if kind=='verification':
        created=await c.actor().client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=dict(
            root_cause_text='PRIVATE-PPT-V-A',method='observation',result='PRIVATE-PPT-RESULT-A',conclusion='passed',
            source_ref={'fmea_id':str(c.source_a.fmea_id),'cause_node_id':'cause'}))
        assert created.status_code==200,created.text
        cleared=await c.actor().client.patch(f'/api/capa/{c.report_id}/root-cause-verifications/{created.json()["verification_id"]}',json={'source_ref':None})
        assert cleared.status_code==200,cleared.text
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id)
        report.d1_team=[{'name':'Synthetic owner','role':'owner'}]
        for field in ['d2_description','d3_interim','d4_root_cause','d5_correction','d6_verification','d7_prevention','d8_closure']:
            setattr(report,field,'complete '+field)
        report.fmea_node_id='cause'
        if kind=='root':
            from app.services.capa_d4_material import capture_fmea_origin
            from app.services.capa_d4_provenance import record_root_revision
            origin=await capture_fmea_origin(db,c.actor().user_id,c.report_id,c.source_a.fmea_id,'cause')
            await record_root_revision(db,report_id=c.report_id,actor_id=c.actor().user_id,write_path='r6:test-ppt-root',added_source_ids=[origin.source_id])
        report.status='D8_CLOSURE'
        await db.commit()

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['verification','root'])
async def test_complete_protected_ppt_never_reaches_unapproved_review_model(r6_case,monkeypatch,kind):
    from types import SimpleNamespace
    from app.services import capa_ppt_service,capa_ppt_review_service,agent_review_skill_service
    from app.services.agent import provider_adapter
    from app.models.capa import CAPAEightD
    c=r6_case
    await _complete_protected_ppt(c,kind)
    calls=[]
    async def complete(pc,prompt,schema):
        calls.append(prompt)
        return {'passed':True,'issues':[],'suggestions':[]}
    async def skill(*args,**kwargs): return SimpleNamespace(content='Synthetic reviewer')
    monkeypatch.setattr(provider_adapter,'complete_json',complete)
    monkeypatch.setattr(agent_review_skill_service,'get_by_name',skill)
    scope=SimpleNamespace(user=SimpleNamespace(user_id=c.actor().user_id))
    async with c.session() as db:
        content=await capa_ppt_service.generate_content(db,c.report_id,scope=scope)
        assert capa_ppt_service._validate_ppt_content(content,await db.get(CAPAEightD,c.report_id))==[]
        denied=False
        try: await capa_ppt_review_service.review_and_correct(db,c.report_id,object(),c.binding.schema_name,scope=scope)
        except PermissionError: denied=True
        assert denied and calls==[]
        local,review=await capa_ppt_review_service.review_and_correct(db,c.report_id,None,c.binding.schema_name,scope=scope)
        assert review.status=='skipped' and len(local.pages)==11

@pytest.mark.asyncio
async def test_cached_ppt_review_report_guard_precedes_json_select(r6_case):
    from app.models.capa import CapaPptExport
    from sqlalchemy import event
    c=r6_case
    await _complete_protected_ppt(c)
    async with c.session() as db:
        row=CapaPptExport(capa_id=c.report_id,factory_id=c.factory_id,generated_by=c.actor().user_id,
            version='historical-review',review_status='needs_review',review_report={'issues':['PRIVATE-PPT-V-A'],'suggestions':[]})
        db.add(row)
        await db.commit()
        export_id=row.export_id
    await c.actor().revoke('fmea')
    reads=[]
    def capture(conn,cursor,statement,parameters,context,many):
        if 'select' in statement.lower() and 'capa_ppt_export.review_report' in statement.lower(): reads.append(statement)
    event.listen(c.runtime.engine.sync_engine,'before_cursor_execute',capture)
    try:
        response=await c.actor().client.get(f'/api/capa/{c.report_id}/ppt-exports/{export_id}')
        assert response.status_code==403,response.text
        assert reads==[] and 'PRIVATE-PPT-V-A' not in response.text
        assert response.headers.get('cache-control')=='no-store'
    finally: event.remove(c.runtime.engine.sync_engine,'before_cursor_execute',capture)

@pytest.mark.asyncio
@pytest.mark.parametrize('revoke',[False,True])
async def test_local_ppt_export_rechecks_verification_sources_after_commit(r6_case,monkeypatch,revoke):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.capa import CapaPptExport
    from app.services.agent import provider_adapter
    from app.services.capa_d4_material import material_version
    c=r6_case
    await _complete_protected_ppt(c)
    async def no_model(*args,**kwargs): raise provider_adapter.ProviderNotConfiguredError('synthetic no model')
    monkeypatch.setattr(provider_adapter,'build_client',no_model)
    original=AsyncSession.commit
    fired=False
    async def commit_then_revoke(db):
        nonlocal fired
        exporting=any(isinstance(row,CapaPptExport) for row in db.new)
        await original(db)
        if exporting and revoke and not fired:
            fired=True
            await c.actor().revoke('fmea')
    monkeypatch.setattr(AsyncSession,'commit',commit_then_revoke)
    async with c.session() as db: before=await material_version(db,c.report_id)
    response=await c.actor().client.post(f'/api/capa/{c.report_id}/ppt-export')
    if revoke:
        assert fired and response.status_code==403,response.text[:200]
        assert not response.content.startswith(b'PK')
    else:
        assert response.status_code==200,response.text[:200]
        assert response.content.startswith(b'PK')
    async with c.session() as db: assert before==await material_version(db,c.report_id)

@pytest.mark.asyncio
async def test_cached_ppt_uses_measure_sources_independent_from_current_root(d5_case):
    from app.models.capa import CapaPptExport
    from app.services.capa_ppt_service import get_export
    from sqlalchemy import event
    c=d5_case
    row=CapaPptExport(capa_id=c.report.report_id,factory_id=c.report.factory_id,generated_by=c.user_id,
        version='historical-D5-review',review_status='needs_review',review_report={'issues':['PRIVATE-MEASURE-B'],'suggestions':[]})
    c.db.add(row)
    await c.db.commit()
    assert (await get_export(c.db,row.export_id,c.report.report_id,scope=c.actors[2])).review_report['issues']==['PRIVATE-MEASURE-B']
    reads=[]
    def capture(conn,cursor,statement,parameters,context,many):
        if 'select' in statement.lower() and 'capa_ppt_export.review_report' in statement.lower(): reads.append(statement)
    event.listen(c.engine.sync_engine,'before_cursor_execute',capture)
    try:
        with pytest.raises(PermissionError): await get_export(c.db,row.export_id,c.report.report_id,scope=c.actors[1])
        assert reads==[]
    finally: event.remove(c.engine.sync_engine,'before_cursor_execute',capture)
