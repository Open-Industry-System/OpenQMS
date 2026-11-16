"""Employee confirmation is a distinct authorized business decision."""
from uuid import UUID
import pytest
from sqlalchemy import select, func, update
from tests.services.agent_runtime.test_r6_d4_candidates import d4_case, r5_case, d4_text_local_trial, owned_local_trial, _managed_claim
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
from app.models.capa_r6 import CapaR6StaffReceipt, CapaR6RootRevisionSource

@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_normal_candidate_confirmation_does_not_verify(d4_case):
    c = d4_case
    from app.api.capa_r6 import router
    c.app.include_router(router)
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer '+c.token}
    generated = await c.client.post('/api/agent/runtime/model/infer', json={'operation':'propose_d4'}, headers=headers)
    assert generated.status_code == 200, generated.text
    saved = await c.client.post('/api/agent/runtime/capa/d4/candidates', json=dict(command_key='confirm-source', text='定位销磨损导致孔径超差'), headers=headers)
    assert saved.status_code == 200, saved.text
    candidate_id = saved.json()['candidate_id']
    detail = await c.admin.get(f'/api/capa/{c.report_id}/d4-candidates')
    assert detail.status_code == 200, detail.text
    candidate = detail.json()['items'][0]
    body = dict(operation_key='employee-confirm', expected_material_version=candidate['material_version'], expected_candidate_version=candidate['version'], final_text='定位销磨损导致孔径超差')
    response = await c.admin.post(f'/api/capa/{c.report_id}/d4-candidates/{candidate_id}/confirm', json=body)
    assert response.status_code == 200, response.text
    assert not {'receipt_id','input_versions','receipt_hmac'} & response.json().keys()
    replay = await c.admin.post(f'/api/capa/{c.report_id}/d4-candidates/{candidate_id}/confirm', json=body)
    assert replay.status_code == 200 and replay.json() == response.json(), replay.text
    changed=await c.admin.post(f'/api/capa/{c.report_id}/d4-candidates/{candidate_id}/confirm',json=dict(body,final_text='changed'))
    assert changed.status_code==409,changed.text
    async with c.session() as db:
        from app.models.audit import AuditLog
        audit=await db.scalar(select(AuditLog).where(AuditLog.record_id==UUID(candidate_id),AuditLog.action=='CONFIRM_D4_CANDIDATE'))
        assert audit.changed_fields['version']==2
        assert (await db.get(CAPAEightD,c.report_id)).d4_root_cause == body['final_text']
        assert await db.scalar(select(func.count()).select_from(CapaR6RootRevisionSource).where(CapaR6RootRevisionSource.report_id==c.report_id)) == 3
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt).where(CapaR6StaffReceipt.report_id==c.report_id)) == 1
        assert await db.scalar(select(func.count()).select_from(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id==c.report_id)) == 0
        assert await db.scalar(select(func.count()).select_from(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.report_id==c.report_id)) == 0

import pytest_asyncio

@pytest_asyncio.fixture
async def staff_candidate(r6_case):
    """Committed pending metadata for ordinary authority/conflict boundaries.

    Native main-chain tests above supply the actual delivered input receipts.
    This fixture never pretends to supply delivery or proof evidence.
    """
    from uuid import uuid4
    from app.models.capa_r6 import CapaD4Candidate, AgentD4CandidateCommand, CapaD4CandidateSource
    from app.services.capa_d4_material import capture_fmea_origin
    from app.services.capa_d4_candidates import _version
    c=r6_case
    async with c.session() as db:
        report=await db.get(CAPAEightD,c.report_id)
        report.status='D4_ROOT_CAUSE'
        source=await capture_fmea_origin(db,c.actor().user_id,c.report_id,c.source_a.fmea_id,'cause')
        command=AgentD4CandidateCommand(command_id=uuid4(),task_id=c.task_id,run_id=c.run_id,
            report_id=c.report_id,command_key='ordinary-boundary',request_hmac='0'*64,sequence=1,operation='save')
        db.add(command)
        await db.flush()
        candidate=CapaD4Candidate(
            candidate_id=uuid4(),report_id=c.report_id,task_id=c.task_id,run_id=c.run_id,command_id=command.command_id,
            original_text='RESTRICTED-CANDIDATE',supporting=['support'],opposing=['against'],missing_information=['missing'],
            input_versions={str(source.source_id):_version(source)},state='pending',version=1,source_count=1,created_by=c.actor().user_id)
        db.add(candidate)
        await db.flush()
        db.add(CapaD4CandidateSource(candidate_id=candidate.candidate_id,report_id=c.report_id,source_id=source.source_id))
        await db.commit()
        c.candidate_id=candidate.candidate_id
    response=await c.actor().client.get(f'/api/capa/{c.report_id}/d4-candidates')
    assert response.status_code==200,response.text
    c.confirm_body=dict(operation_key='boundary',expected_material_version=response.json()['items'][0]['material_version'],
        expected_candidate_version=response.json()['items'][0]['version'],final_text='final')
    return c

@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['append','replace'])
@pytest.mark.parametrize('denial',['view','edit_revoked','source_revoked','candidate_version','material_version','withdrawn','superseded','adopted','terminal'])
async def test_confirmation_failure_is_atomic(staff_candidate,mode,denial):
    from app.models.capa_r6 import CapaD4Candidate
    from sqlalchemy import update
    c=staff_candidate
    actor='edit'
    body=dict(c.confirm_body,mode=mode)
    if denial=='view': actor='view'
    elif denial=='edit_revoked': await c.actor().revoke('edit')
    elif denial=='source_revoked': await c.actor().revoke('fmea')
    elif denial=='candidate_version': body['expected_candidate_version']='stale'
    elif denial=='material_version': body['expected_material_version']='stale'
    else:
        async with c.session() as db:
            if denial=='terminal': await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report_id).values(status='ARCHIVED'))
            else: await db.execute(update(CapaD4Candidate).where(CapaD4Candidate.candidate_id==c.candidate_id).values(state=denial,version=2))
            await db.commit()
    before=await c.snapshot()
    response=await c.confirm(c.candidate_id,body,actor=actor)
    assert response.status_code==(403 if denial in {'view','edit_revoked','source_revoked'} else 409),response.text
    assert await c.snapshot()==before

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_confirmation_validation_never_echoes_restricted_body(r6_case):
    from uuid import uuid4
    c=r6_case
    response=await c.confirm(uuid4(),dict(operation_key='invalid',expected_material_version='v',
        expected_candidate_version='v',final_text='PRIVATE-VALIDATION-SENTINEL',extra_private='PRIVATE-VALIDATION-SENTINEL'))
    assert response.status_code==422
    assert 'PRIVATE-VALIDATION-SENTINEL' not in response.text
    assert response.headers.get('cache-control')=='no-store'

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_employee_single_withdraw_is_atomic_and_reason_bound(staff_candidate):
    c=staff_candidate
    url=f'/api/capa/{c.report_id}/d4-candidates/{c.candidate_id}/withdraw'
    body=dict(operation_key='single-withdraw',reason='RESTRICTED-REASON')
    response=await c.actor().client.post(url,json=body)
    assert response.status_code==200,response.text
    from app.models.audit import AuditLog
    async with c.session() as db:
        audit=await db.scalar(select(AuditLog).where(AuditLog.record_id==c.candidate_id,AuditLog.action=='WITHDRAW_D4_CANDIDATE'))
        assert audit.changed_fields['version']==2
    replay=await c.actor().client.post(url,json=body)
    assert replay.json()==response.json() and replay.status_code==200
    before=await c.snapshot()
    changed=await c.actor().client.post(url,json=dict(body,reason='changed'))
    assert changed.status_code==409
    assert await c.snapshot()==before
    denied=await c.confirm(c.candidate_id,c.confirm_body)
    assert denied.status_code==409
    assert await c.snapshot()==before

async def _generate_and_confirm(c,key,text):
    await _managed_claim(c)
    headers={'Authorization':'Bearer '+c.token}
    batch=await c.client.post('/api/agent/runtime/messages/claim',json={'limit':20},headers=headers)
    assert batch.status_code==200,batch.text
    ack=await c.client.post('/api/agent/runtime/messages/ack',json=dict(batch_id=batch.json()['batch_id'],through_sequence=1),headers=headers)
    assert ack.status_code==200,ack.text
    generated=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'propose_d4'},headers=headers)
    assert generated.status_code==200,generated.text
    saved=await c.client.post('/api/agent/runtime/capa/d4/candidates',json=dict(command_key=key,text=text,
        supporting=['原文依据'],opposing=[],missing_information=['员工独立验证']),headers=headers)
    assert saved.status_code==200,saved.text
    candidate_id=saved.json()['candidate_id']
    finished=await c.client.post('/api/agent/runtime/finish',json={'status':'completed'},headers=headers)
    assert finished.status_code==200,finished.text
    disabled=await c.admin.patch(f'/api/admin/agent-plugins/{c.r5_id}',json={'enabled':False})
    assert disabled.status_code==200,disabled.text
    listing=await c.client.get(f'/api/capa/{c.report_id}/d4-candidates')
    assert listing.status_code==200,listing.text
    row=next(r for r in listing.json()['items'] if r['candidate_id']==candidate_id)
    body=dict(operation_key=key,expected_material_version=row['material_version'],expected_candidate_version=row['version'],final_text=text)
    if getattr(c,'before_confirm',None) is not None:
        callback=c.before_confirm
        c.before_confirm=None
        if await callback(c,candidate_id,body) is False: return candidate_id
    response=await c.client.post(f'/api/capa/{c.report_id}/d4-candidates/{candidate_id}/confirm',json=body)
    assert response.status_code==200,response.text
    return candidate_id

async def _profile(c,profile,version,scope):
    from dataclasses import replace
    from uuid import uuid4
    d4=profile=='model_d4_candidate_v1'
    required=(['capa.d2.snapshot.v1','capa.d3.snapshot.v1','capa.d4.candidate.propose.v1','capa.d4.fmea_input.masked.v1'] if d4 else
        ['capa.d4.root_cause_candidate.masked.v1','capa.d5.proposal.save.v1','capa.d2.snapshot.v1','capa.d3.snapshot.v1'])
    registered=await c.admin.post('/api/admin/agent-plugins',json=dict(plugin_key='openqms.controlled-d5-model',plugin_version=version,
        manifest=dict(protocol_versions=['1'],required_capabilities=required,optional_capabilities=[])))
    assert registered.status_code==201,registered.text
    c.r5_id=UUID(registered.json()['plugin']['installation_id'])
    c.pilot=replace(c.pilot,installation_id=c.r5_id,plugin_version=version,profile=profile)
    c.app.state.r5_controlled_pilot=c.pilot
    for capability in required:
        body=dict(capability_id=capability,factory_ids=[str(c.factory_id)],object_ids=[str(c.report_id)],product_line_codes=[c.line],
            enabled=True,expires_at=c.pilot.expires_at.isoformat())
        if capability in {'capa.d4.fmea_input.masked.v1','capa.d4.root_cause_candidate.masked.v1'}: body['derived_source_scope']=scope
        granted=await c.admin.post(f'/api/admin/agent-plugins/{c.r5_id}/grants',json=body)
        assert granted.status_code==201,granted.text
    enabled=await c.admin.patch(f'/api/admin/agent-plugins/{c.r5_id}',json={'enabled':True})
    assert enabled.status_code==200,enabled.text
    model=await c.admin.post('/api/agent/models',json=dict(c.model_body,name='C5 '+uuid4().hex))
    assert model.status_code==201,model.text
    c.model_id=UUID(model.json()['deployment_id'])
    c.create_body=dict(c.create_body,request_key=uuid4().hex,installation_id=str(c.r5_id),model_deployment_id=str(c.model_id),
        initial_text='analyze_d4_candidate_v1' if d4 else 'synthetic D5 request',derived_source_scope=scope)

async def _verify(c,text):
    result=await c.client.post(f'/api/capa/{c.report_id}/root-cause-verifications',json=dict(
        root_cause_text=text,method='measurement',result='现场测量符合根因',conclusion='passed',
        source_ref=dict(fmea_id=str(c.fmea_id),cause_node_id='cause-A'),source_declaration=dict(declares_complete_coverage=True)))
    assert result.status_code==200 and result.json()['source_proof_issued'],result.text
    return result

@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_supported_report_inputs_and_single_external_source_deliver(d4_case):
    import json
    from app.api.capa_r6 import router
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    from app.models.capa_r6 import CapaR6RootDeliveryBinding
    from app.models.audit import AuditLog
    c=d4_case
    c.app.include_router(router)
    await _generate_and_confirm(c,'C3-POS','定位销磨损导致孔径超差')
    await _verify(c,'定位销磨损导致孔径超差')
    advanced=await c.client.post(f'/api/capa/{c.report_id}/advance',json={})
    assert advanced.status_code==200,advanced.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id==c.report_id))==1
        actions=set(await db.scalars(select(AuditLog.action).where((AuditLog.record_id==c.report_id)|(AuditLog.table_name=='capa_d4_candidates'))))
        assert {'CONFIRM_D4_CANDIDATE','D4_VERIFICATION_PASSED','D4_SOURCE_PROOF_ISSUED'}<=actions
    await _profile(c,'model_d5_proposal_r6_v1','1.0.5',c.source_scope)
    await _managed_claim(c)
    c.witness.a.bodies.clear()
    response=await c.client.post('/api/agent/runtime/model/infer',json={},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==200,response.text
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]
    assert json.loads(c.witness.a.bodies[0]['messages'][1]['content'])['d4_root_cause']=='定位销磨损导致孔径超差'
    async with c.session() as db:
        receipt=await db.scalar(select(AgentD5BasisReceipt).where(AgentD5BasisReceipt.run_id==c.run_id))
        sidecar=await db.get(CapaR6RootDeliveryBinding,receipt.receipt_id)
        assert sidecar is not None and len(sidecar.input_bindings)==2

@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_extra_external_origin_never_leaves_server(d4_case):
    from uuid import uuid4
    from app.api.capa_r6 import router
    from app.models.fmea import FMEADocument
    from app.models.capa_r6 import CapaR6SourceOrigin,CapaR6RootRevisionSource
    from app.services.agent_runtime import runtime_access,model_egress
    from app.services.capa_r6_delivery import require_root_delivery
    from types import SimpleNamespace
    c=d4_case
    c.app.include_router(router)
    await _generate_and_confirm(c,'C3-NEG-A','定位销磨损导致孔径超差')
    a_scope=c.source_scope
    async with c.session() as db:
        doc=FMEADocument(document_no='C5-B-'+uuid4().hex[:12],title='Approved B',factory_id=c.factory_id,product_line_code=c.line,
            graph_data={'nodes':[{'id':'cause-B','type':'FailureCause','name':'夹具松动导致孔径超差'}],'edges':[]},lock_version=0)
        db.add(doc)
        await db.flush()
        b_id=doc.fmea_id
        await db.commit()
    b_scope=dict(target_report_id=str(c.report_id),fmea_id=str(b_id),cause_node_id='cause-B')
    await _profile(c,'model_d4_candidate_v1','1.0.6',b_scope)
    await _generate_and_confirm(c,'C3-NEG-B','夹具松动导致孔径超差')
    text='定位销磨损导致孔径超差\n夹具松动导致孔径超差'
    await _verify(c,text)
    advanced=await c.client.post(f'/api/capa/{c.report_id}/advance',json={})
    assert advanced.status_code==200,advanced.text
    async with c.session() as db:
        sources=list(await db.scalars(select(CapaR6SourceOrigin).join(CapaR6RootRevisionSource,
            CapaR6RootRevisionSource.source_id==CapaR6SourceOrigin.source_id).where(
            CapaR6RootRevisionSource.report_id==c.report_id).distinct()))
        assert len(sources)==4 and {s.fmea_id for s in sources if s.kind=='fmea_projection'}=={c.fmea_id,b_id}
    await _profile(c,'model_d5_proposal_r6_v1','1.0.5',a_scope)
    await _managed_claim(c)
    c.witness.a.bodies.clear()
    async with c.session() as db:
        await c.session_info(db)
        identity=await runtime_access.verify_runtime_identity(db,c.token,c.binding)
        proof=await db.scalar(select(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.report_id==c.report_id,
            CapaD4RootCauseSourceProof.status=='active'))
        with pytest.raises(PermissionError):
            await require_root_delivery(db,identity,SimpleNamespace(report_id=c.report_id),proof)
        with pytest.raises(PermissionError):
            await model_egress.send_context(db,identity,snapshot=None,messages=[{'role':'user','content':'D5'}],tools=[])
    response=await c.client.post('/api/agent/runtime/model/infer',json={},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==403,response.text
    assert c.witness.a.bodies==c.witness.b.bodies==[]
    version=(await c.client.get(f'/api/capa/{c.report_id}')).json()['material_version']
    manual=await c.client.put(f'/api/capa/{c.report_id}',json={'d5_correction':'人工D5继续','expected_material_version':version})
    assert manual.status_code==200,manual.text

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_material_token_binds_current_inherited_source_epoch_without_body_reads(staff_candidate):
    from app.models.capa_r6 import CapaD4CandidateSource
    from app.models.fmea import FMEADocument
    from app.services.capa_d4_material import material_version
    from app.services.capa_d4_provenance import record_root_revision
    from sqlalchemy import event
    c=staff_candidate
    async with c.session() as db:
        source_id=await db.scalar(select(CapaD4CandidateSource.source_id).where(CapaD4CandidateSource.candidate_id==c.candidate_id))
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report_id).values(d4_root_cause='old root'))
        await record_root_revision(db,report_id=c.report_id,actor_id=c.actor().user_id,write_path='r6:test-old-history',added_source_ids=[source_id])
        await db.commit()
        old=await material_version(db,c.report_id)
        doc=await db.get(FMEADocument,c.source_a.fmea_id)
        graph=doc.graph_data
        doc.graph_data={'nodes':[],'edges':[]}
        await db.commit()
        doc.graph_data=graph
        await db.commit()
        statements=[]
        def capture(conn,cursor,statement,parameters,context,executemany): statements.append(statement.lower())
        event.listen(c.runtime.engine.sync_engine,'before_cursor_execute',capture)
        try: current=await material_version(db,c.report_id)
        finally: event.remove(c.runtime.engine.sync_engine,'before_cursor_execute',capture)
        assert current!=old
        assert not any('graph_data' in s or 'd4_root_cause,' in s or 'select capa_r6_root_revision_bodies.body' in s for s in statements)

@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['append','replace'])
async def test_inherited_source_aba_rejects_old_form_and_refresh_can_confirm(d4_case,mode):
    from uuid import uuid4
    from app.api.capa_r6 import router
    from app.models.fmea import FMEADocument
    from app.models.capa_r6 import CapaR6SourceOrigin,CapaR6RootRevisionSource
    from app.services.capa_d4_material import require_root_freshness
    c=d4_case
    c.app.include_router(router)
    await _generate_and_confirm(c,'history-A','定位销磨损导致孔径超差')
    async with c.session() as db:
        b=FMEADocument(document_no='C5-B-'+uuid4().hex[:12],title='B',factory_id=c.factory_id,product_line_code=c.line,
            graph_data={'nodes':[{'id':'cause-B','type':'FailureCause','name':'夹具松动导致孔径超差'}],'edges':[]},lock_version=0)
        db.add(b)
        await db.flush()
        b_id=b.fmea_id
        await db.commit()
    await _profile(c,'model_d4_candidate_v1','1.0.6',dict(target_report_id=str(c.report_id),fmea_id=str(b_id),cause_node_id='cause-B'))
    async def change_inherited(c,candidate_id,body):
        from app.models.capa_r6 import CapaR6MaterialVersion
        async with c.session() as db:
            counter=await db.scalar(select(CapaR6MaterialVersion.counter).where(CapaR6MaterialVersion.report_id==c.report_id))
            a=await db.get(FMEADocument,c.fmea_id)
            original=a.graph_data
            a.graph_data={'nodes':[],'edges':[]}
            await db.commit()
            a.graph_data=original
            await db.commit()
            assert counter==await db.scalar(select(CapaR6MaterialVersion.counter).where(CapaR6MaterialVersion.report_id==c.report_id))
        old=await c.client.post(f'/api/capa/{c.report_id}/d4-candidates/{candidate_id}/confirm',json=body)
        assert old.status_code==409,old.text
        rows=(await c.client.get(f'/api/capa/{c.report_id}/d4-candidates')).json()['items']
        fresh=next(r for r in rows if r['candidate_id']==candidate_id)
        assert fresh['material_version']!=body['expected_material_version']
        body.update(expected_material_version=fresh['material_version'],mode=mode)
    c.before_confirm=change_inherited
    await _generate_and_confirm(c,'history-B','夹具松动导致孔径超差')
    async with c.session() as db:
        assert (await db.get(CAPAEightD,c.report_id)).d4_root_cause==('夹具松动导致孔径超差' if mode=='replace' else '定位销磨损导致孔径超差\n夹具松动导致孔径超差')
        assert await db.scalar(select(func.count()).select_from(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id==c.report_id))==0
        assert await db.scalar(select(func.count()).select_from(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.report_id==c.report_id))==0
        sources=set(await db.scalars(select(CapaR6RootRevisionSource.source_id).where(CapaR6RootRevisionSource.report_id==c.report_id)))
        assert len(sources)==4
        with pytest.raises(PermissionError): await require_root_freshness(db,c.user_id,c.report_id)

@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('input_kind',['fmea_aba','d2_aba'])
async def test_stale_candidate_inputs_stay_rejected_after_refresh(d4_case,input_kind):
    from app.api.capa_r6 import router
    from app.models.fmea import FMEADocument
    from app.models.capa_r6 import CapaD4Candidate
    c=d4_case
    c.app.include_router(router)
    async def change_candidate(c,candidate_id,body):
        if input_kind=='fmea_aba':
            async with c.session() as db:
                doc=await db.get(FMEADocument,c.fmea_id)
                original=doc.graph_data
                doc.graph_data={'nodes':[],'edges':[]}
                await db.commit()
                doc.graph_data=original
                await db.commit()
        else:
            for value in ['changed','孔径测量超出上限']:
                response=await c.client.put(f'/api/capa/{c.report_id}',json={'d2_description':value})
                assert response.status_code==200,response.text
        rows=(await c.client.get(f'/api/capa/{c.report_id}/d4-candidates')).json()['items']
        fresh=next(r for r in rows if r['candidate_id']==candidate_id)
        body['expected_material_version']=fresh['material_version']
        denied=await c.client.post(f'/api/capa/{c.report_id}/d4-candidates/{candidate_id}/confirm',json=body)
        assert denied.status_code==409,denied.text
        return False
    c.before_confirm=change_candidate
    candidate_id=await _generate_and_confirm(c,'stale-candidate','定位销磨损导致孔径超差')
    async with c.session() as db:
        assert (await db.get(CAPAEightD,c.report_id)).d4_root_cause is None
        assert (await db.get(CapaD4Candidate,UUID(candidate_id))).state=='pending'
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt).where(CapaR6StaffReceipt.report_id==c.report_id))==0

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_confirmation_rechecks_source_after_real_parent_lock_wait(staff_candidate,monkeypatch):
    import asyncio
    from sqlalchemy import update
    from app.models.role import RolePermission
    from app.services import capa_d4_confirmation as service
    from types import SimpleNamespace
    from app.schemas.capa_r6 import D4Confirm
    c=staff_candidate
    reached=asyncio.Event()
    async with c.session() as blocker:
        await blocker.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==c.report_id).with_for_update())
        async def contender():
            async with c.session() as db:
                scalar=db.scalar
                async def observed(statement,*args,**kwargs):
                    if 'FOR UPDATE' in str(statement) and 'capa_eightd' in str(statement): reached.set()
                    return await scalar(statement,*args,**kwargs)
                db.scalar=observed
                try:
                    return await service.confirm(db,SimpleNamespace(user=SimpleNamespace(user_id=c.actor().user_id)),
                        c.report_id,c.candidate_id,D4Confirm(**c.confirm_body))
                except Exception as error:
                    await db.rollback()
                    return error
        pending=asyncio.create_task(contender())
        await asyncio.wait_for(reached.wait(),5)
        assert not pending.done()
        await blocker.execute(update(RolePermission).where(RolePermission.role_id==c.actor().role_id,
            RolePermission.module=='fmea').values(permission_level=0))
        await blocker.commit()
        result=await asyncio.wait_for(pending,10)
        assert isinstance(result,PermissionError),repr(result)
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt))==0
        assert (await db.get(CAPAEightD,c.report_id)).d4_root_cause is None

@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_confirmation_withdraw_race_has_one_decision(d4_case):
    import asyncio
    from app.api.capa_r6 import router
    from app.models.capa_r6 import CapaD4Candidate
    c=d4_case
    c.app.include_router(router)
    async def race(c,candidate_id,body):
        base=f'/api/capa/{c.report_id}/d4-candidates/{candidate_id}'
        responses=await asyncio.gather(c.client.post(base+'/confirm',json=body),c.client.post(base+'/withdraw',json={
            'operation_key':'racing-withdraw','reason':'controlled withdrawal'}))
        assert sorted(r.status_code for r in responses)==[200,409],[r.text for r in responses]
        return False
    c.before_confirm=race
    candidate_id=await _generate_and_confirm(c,'racing-confirm','定位销磨损导致孔径超差')
    async with c.session() as db:
        row=await db.get(CapaD4Candidate,UUID(candidate_id))
        assert row.state in {'adopted','withdrawn'}
        assert await db.scalar(select(func.count()).select_from(CapaR6StaffReceipt).where(CapaR6StaffReceipt.report_id==c.report_id))==1
        assert await db.scalar(select(func.count()).select_from(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id==c.report_id))==0

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_candidate_page_filters_unreadable_sources_before_pagination(staff_candidate):
    from uuid import uuid4
    from app.models.fmea import FMEADocument
    from app.models.capa_r6 import CapaD4Candidate,AgentD4CandidateCommand,CapaD4CandidateSource
    from app.services.capa_d4_material import capture_fmea_origin
    from app.services.capa_d4_candidates import _version
    c=staff_candidate
    async with c.session() as db:
        doc=FMEADocument(document_no='CAND-B-'+uuid4().hex,title='later hidden',factory_id=c.factory_id,product_line_code=c.line,
            graph_data={'nodes':[{'id':'cause','type':'FailureCause'}],'edges':[]})
        db.add(doc)
        await db.flush()
        origin=await capture_fmea_origin(db,c.actor().user_id,c.report_id,doc.fmea_id,'cause')
        command=AgentD4CandidateCommand(command_id=uuid4(),report_id=c.report_id,task_id=c.task_id,run_id=c.run_id,
            command_key='hidden-B',request_hmac='b'*64,sequence=2,operation='save')
        db.add(command)
        await db.flush()
        candidate=CapaD4Candidate(candidate_id=uuid4(),report_id=c.report_id,task_id=c.task_id,run_id=c.run_id,command_id=command.command_id,
            original_text='HIDDEN-OTHER-CANDIDATE',supporting=[],opposing=[],missing_information=[],
            input_versions={str(origin.source_id):_version(origin)},state='pending',version=1,source_count=1,created_by=c.actor().user_id)
        db.add(candidate)
        await db.flush()
        db.add(CapaD4CandidateSource(candidate_id=candidate.candidate_id,report_id=c.report_id,source_id=origin.source_id))
        await db.commit()
        doc.factory_id=c.outside_factory_id
        doc.product_line_code=c.outside_source.product_line_code
        await db.commit()
    for page,expected in [(1,[str(c.candidate_id)]),(2,[])]:
        response=await c.actor().client.get(f'/api/capa/{c.report_id}/d4-candidates?page={page}&page_size=1')
        assert response.status_code==200,response.text
        assert [item['candidate_id'] for item in response.json()['items']]==expected
        assert 'HIDDEN-OTHER-CANDIDATE' not in response.text

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_candidate_page_final_authority_check_suppresses_loaded_body(staff_candidate,monkeypatch):
    from app.services import capa_d4_confirmation as service
    c=staff_candidate
    original=service.candidate_metadata
    calls=0
    async def revoke_after_body(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==4: await c.actor().revoke('fmea')
        return await original(*args,**kwargs)
    monkeypatch.setattr(service,'candidate_metadata',revoke_after_body)
    response=await c.actor().client.get(f'/api/capa/{c.report_id}/d4-candidates')
    assert response.status_code==403,response.text
    assert 'RESTRICTED-CANDIDATE' not in response.text

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_readonly_confirmation_context_binds_both_versions_and_keeps_view_readable(staff_candidate):
    c=staff_candidate
    root=f'/api/capa/{c.report_id}'
    response=await c.actor('view').client.get(root+f'/d4-candidates/{c.candidate_id}/confirmation-context')
    assert response.status_code==200,response.text
    context=response.json()
    assert context['candidate_id']==str(c.candidate_id)
    assert context['candidate_version']==c.confirm_body['expected_candidate_version']
    assert context['material_version']==c.confirm_body['expected_material_version']
    assert context['can_confirm'] is False
    await c.actor('view').revoke('fmea')
    denied=await c.actor('view').client.get(root+f'/d4-candidates/{c.candidate_id}/confirmation-context')
    assert denied.status_code==403
    assert 'current_root_text' not in denied.json()
