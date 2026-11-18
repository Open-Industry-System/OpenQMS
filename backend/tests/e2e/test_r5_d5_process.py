"""R5 cross-entry acceptance using signed managed runs, TCP and owned PostgreSQL.

All model recipients are deterministic loopback witnesses; no real model trial.
"""
import asyncio
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func, update, text

from app.models.agent_d5_command import AgentD5Command
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_d5_proposal import CapaD5Proposal, CapaD5Measure
from app.models.role import RolePermission
from tests.services.agent_runtime.test_r5_model_binding import r5_case
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial
from tests.e2e.test_r5_model_agent import actual_agent, scripted_model, call

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.asyncio]


async def launch_proposals(c, texts):
    await actual_agent(c)
    scripted_model(c, [call('read_d4'), *[call('save_proposal', {'text': text}, f'save-{i}') for i,text in enumerate(texts)], {'content':'done'}])
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201,created.text
    task=created.json()['task_id']
    result=await c.client.post(f'/api/agent/tasks/{task}/launch',timeout=130)
    assert result.status_code==200,result.text
    listing=await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert listing.status_code==200,listing.text
    items=listing.json()['items']
    assert {item['original_text'] for item in items}==set(texts)
    assert c.witness.b.bodies==[]
    return task,items


async def test_actual_model_explicit_correction_and_parallel_alternative(r5_case):
    c=r5_case
    await actual_agent(c)
    scripted_model(c,[call('read_d4'),call('save_proposal',{'text':'original'},'first'),
        call('request_supplement',{'question':'Select the original proposal to correct.'},'question'),
        call('save_proposal',{'text':'corrected','operation':'replace'},'replace'),
        call('save_proposal',{'text':'parallel','operation':'alternative'},'alternative'),{'content':'done'}])
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201,created.text
    task=created.json()['task_id']
    running=asyncio.create_task(c.client.post(f'/api/agent/tasks/{task}/launch',timeout=130))
    try:
        for _ in range(1000):
            status=await c.client.get(f'/api/agent/tasks/{task}/workflow')
            if status.status_code==200 and status.json().get('question'):break
            if running.done():pytest.fail((await running).text)
            await asyncio.sleep(.02)
        else:pytest.fail('managed model did not ask for correction')
        listing=await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
        original=listing.json()['items'][0]['proposal_id']
        checkpoint=status.json()['checkpoint_id']
        message=await c.client.post(f'/api/agent/tasks/{task}/messages',json={'content':json.dumps({'intent':'replace_d5','predecessor_id':original}),'idempotency_key':'explicit-correction'})
        assert message.status_code==202,message.text
        result=await running
        assert result.status_code==200,result.text
        async with c.session() as db:
            rows=list(await db.scalars(select(CapaD5Proposal).where(CapaD5Proposal.task_id==UUID(task))))
            assert {row.original_text:row.state for row in rows}=={'original':'superseded','corrected':'pending','parallel':'pending'}
            corrected=next(row for row in rows if row.original_text=='corrected')
            parallel=next(row for row in rows if row.original_text=='parallel')
            assert str(corrected.predecessor_id)==original and corrected.correction_message_id
            assert parallel.predecessor_id is None and parallel.correction_message_id is None
            assert await db.scalar(select(func.count()).select_from(AgentD5Command))==3
            corrected_id,parallel_id=corrected.proposal_id,parallel.proposal_id
        advanced=await c.client.post(f'/api/capa/{c.report_id}/advance',json={})
        assert advanced.status_code==200,advanced.text
        adopted=await c.client.post(f'/api/capa/{c.report_id}/d5-proposals/{corrected_id}/adopt',json={'operation_key':'keep-corrected','final_text':'employee confirmed correction'})
        assert adopted.status_code==200,adopted.text
        path=f'/api/agent/tasks/{task}/d5-checkpoints/{checkpoint}/proposals/withdraw'
        batch={'operation_key':'partial','reason':'withdraw selected alternative','proposal_ids':[original,str(corrected_id),str(parallel_id)]}
        response=await c.client.post(path,json=batch)
        assert response.status_code==200,response.text
        assert [item['outcome'] for item in response.json()]==['unavailable','adopted','withdrawn']
        assert (await c.client.post(path,json=batch)).json()==response.json()
        assert len(c.witness.a.bodies)==6 and c.witness.b.bodies==[]
        schema=next(tool['function']['parameters'] for tool in c.witness.a.bodies[0]['tools'] if tool['function']['name']=='save_proposal')
        assert schema['properties']['operation']['enum']==['save','alternative','replace']
        assert not {'predecessor_id','correction_message_id','report_id'} & set(schema['properties'])
    finally:
        if not running.done():running.cancel();await asyncio.gather(running,return_exceptions=True)


async def test_actual_launch_formal_material_race_export_and_current_revocation(r5_case, monkeypatch):
    c=r5_case
    task,items=await launch_proposals(c,['R5-T9-ORIGINAL-SENTINEL','R5-T9-RACE-SENTINEL'])
    advanced=await c.client.post(f'/api/capa/{c.report_id}/advance',json={})
    assert advanced.status_code==200,advanced.text
    base=f'/api/capa/{c.report_id}/d5-proposals'
    adopted=await c.client.post(f"{base}/{items[0]['proposal_id']}/adopt",json={'operation_key':'adopt','final_text':'R5-T9-FORMAL-SENTINEL'})
    assert adopted.status_code==200,adopted.text
    assert adopted.json()==(await c.client.post(f"{base}/{items[0]['proposal_id']}/adopt",json={'operation_key':'adopt','final_text':'R5-T9-FORMAL-SENTINEL'})).json()
    # A legacy model draft cannot consume item-protected formal material.
    from unittest.mock import AsyncMock
    from app.services.agent import provider_adapter
    from app.models.audit import AuditLog
    build = AsyncMock(side_effect=AssertionError('formal material reached provider setup'))
    complete = AsyncMock(side_effect=AssertionError('formal material reached model'))
    existing_model_calls = len(c.witness.a.bodies)
    assert existing_model_calls > 0  # Keep the preceding authorized delivery history.
    with monkeypatch.context() as patcher:
        patcher.setattr(provider_adapter, 'build_client', build)
        patcher.setattr(provider_adapter, 'complete_json', complete)
        draft = await c.client.post(f'/api/capa/{c.report_id}/draft/d5', json={
            'format': 'structured', 'request_id': str(uuid4())})
        assert draft.status_code == 403, draft.text
        assert draft.json() == {'detail': 'D4_DRAFT_MATERIAL_UNAVAILABLE'}
        assert 'R5-T9-FORMAL-SENTINEL' not in draft.text
        assert not {'content', 'structured_data', 'summary'} & set(draft.json())
        assert len(c.witness.a.bodies) == existing_model_calls and c.witness.b.bodies == []
        build.assert_not_awaited()
        complete.assert_not_awaited()
    async with c.session() as db:
        audit = await db.scalar(select(AuditLog).where(
            AuditLog.record_id == c.report_id, AuditLog.action == 'AI_DRAFT'))
        assert audit.changed_fields['status_code'] == 403
        assert audit.changed_fields['success'] is False
        assert audit.changed_fields['error'] == 'D4_DRAFT_MATERIAL_UNAVAILABLE'
    race=await asyncio.gather(c.client.post(f"{base}/{items[1]['proposal_id']}/adopt",json={'operation_key':'race-adopt','final_text':'race final'}),c.client.post(f"{base}/{items[1]['proposal_id']}/withdraw",json={'operation_key':'race-withdraw','reason':'race reason'}))
    assert sorted(response.status_code for response in race)==[200,409],[response.text for response in race]
    advanced=await c.client.post(f'/api/capa/{c.report_id}/advance',json={})
    assert advanced.status_code==200,advanced.text
    detail=await c.client.get(f'/api/capa/{c.report_id}')
    assert 'R5-T9-FORMAL-SENTINEL' not in detail.text and not detail.json().get('d5_correction')
    async with c.session() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report_id).values(status='D8_CLOSURE'))
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id==c.report_id).values(evidence_attachments=[]))
        await db.commit()
    exported=await c.client.post(f'/api/capa/{c.report_id}/ppt-export')
    assert exported.status_code==200,exported.text
    import io,zipfile
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        slides=''.join(archive.read(name).decode() for name in archive.namelist() if name.startswith('ppt/slides/slide') and name.endswith('.xml'))
    assert 'R5-T9-FORMAL-SENTINEL' in slides
    assert 'R5-T9-ORIGINAL-SENTINEL' not in slides and 'R5-T9-RACE-SENTINEL' not in slides
    locked=await c.client.post(f"{base}/{items[0]['proposal_id']}/withdraw",json={'operation_key':'terminal','reason':'cannot change final'})
    assert locked.status_code==409,locked.text
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    for endpoint in ('d5-proposals','d5-measures'):
        response=await c.client.get(f'/api/capa/{c.report_id}/{endpoint}')
        assert response.status_code==200,response.text
        assert response.json()['total']==0 and 'SENTINEL' not in response.text
    exported=await c.client.post(f'/api/capa/{c.report_id}/ppt-export')
    assert exported.status_code==403 and 'SENTINEL' not in exported.text,exported.text
    assert c.witness.b.bodies==[]


@pytest.mark.parametrize('bad', ['no-intent','model-target','newer-accepted-intent'])
async def test_issued_replacement_cannot_invent_or_retarget_employee_selection(r5_case,bad):
    from tests.e2e.test_r5_model_agent import _managed_claim, workflow_call, execute, accept_initial
    c=r5_case
    c.create_body['initial_text']='deliver_d4_root_cause_candidate_v1'
    await _managed_claim(c)
    await accept_initial(c)
    scripted_model(c,[call('read_d4'),call('save_proposal',{'text':'original'},'original')])
    issued=await workflow_call(c)
    assert (await execute(c,issued['tool_calls'][0]['id'])).status_code==200
    issued=await workflow_call(c,1)
    original=(await execute(c,issued['tool_calls'][0]['id'])).json()['proposal_id']
    if bad!='no-intent':
        sent=await c.client.post(f'/api/agent/tasks/{c.task_id}/messages',json={'content':json.dumps({'intent':'replace_d5','predecessor_id':original}),'idempotency_key':'correct'})
        assert sent.status_code==202,sent.text
        batch=await c.client.post('/api/agent/runtime/messages/claim',json={},headers={'Authorization':'Bearer '+c.token})
        ack=await c.client.post('/api/agent/runtime/messages/ack',json={'batch_id':batch.json()['batch_id'],'through_sequence':2},headers={'Authorization':'Bearer '+c.token})
        assert ack.status_code==200,ack.text
    args={'text':'replacement','operation':'replace'}
    if bad=='model-target':args['predecessor_id']=original
    scripted_model(c,[call('save_proposal',args,'replace')])
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow','turn':2},headers={'Authorization':'Bearer '+c.token})
    if bad=='newer-accepted-intent':
        assert response.status_code==200,response.text
        sent=await c.client.post(f'/api/agent/tasks/{c.task_id}/messages',json={'content':json.dumps({'intent':'replace_d5','predecessor_id':str(uuid4())}),'idempotency_key':'new-selection'})
        assert sent.status_code==202,sent.text
        batch=await c.client.post('/api/agent/runtime/messages/claim',json={},headers={'Authorization':'Bearer '+c.token})
        ack=await c.client.post('/api/agent/runtime/messages/ack',json={'batch_id':batch.json()['batch_id'],'through_sequence':3},headers={'Authorization':'Bearer '+c.token})
        assert ack.status_code==200,ack.text
        response=await execute(c,response.json()['tool_calls'][0]['id'])
    assert response.status_code==403,response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal))==1
        assert (await db.get(CapaD5Proposal,UUID(original))).state=='pending'


async def test_http_cross_report_and_unknown_committed_write_replay(r5_case,monkeypatch):
    from tests.e2e.test_r5_model_agent import _managed_claim
    from app.services.agent_runtime import d5_commands
    c=r5_case
    c.create_body['initial_text']='deliver_d4_root_cause_candidate_v1'
    await _managed_claim(c)
    headers={'Authorization':'Bearer '+c.token}
    delivered=await c.client.post('/api/agent/runtime/model/infer',json={},headers=headers)
    assert delivered.status_code==200,delivered.text
    body={'command_key':'unknown-write','text':'R5-T9-UNKNOWN'}
    foreign=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=dict(body,report_id=str(uuid4())),headers=headers)
    assert foreign.status_code==422,foreign.text
    real=d5_commands.save_proposal
    async def committed_then_lost(*args,**kwargs):
        await real(*args,**kwargs)
        raise RuntimeError('synthetic response loss after commit')
    monkeypatch.setattr(d5_commands,'save_proposal',committed_then_lost)
    unknown=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=body,headers=headers)
    assert unknown.status_code==500,unknown.text
    monkeypatch.setattr(d5_commands,'save_proposal',real)
    replay=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=body,headers=headers)
    assert replay.status_code==200,replay.text
    assert replay.json()==(await c.client.post('/api/agent/runtime/capa/d5/proposals',json=body,headers=headers)).json()
    assert (await c.client.post('/api/agent/runtime/capa/d5/proposals',json=dict(body,text='changed'),headers=headers)).status_code==409
    async with c.session() as db:
        rows=list(await db.scalars(select(CapaD5Proposal)))
        assert len(rows)==1 and rows[0].report_id==c.report_id
        assert await db.scalar(select(func.count()).select_from(AgentD5Command))==1


async def test_actual_launch_root_ABA_and_proof_changes_never_restore_adoption(r5_case):
    c=r5_case
    _,items=await launch_proposals(c,['R5-T9-OLD-BASIS'])
    for text in ('synthetic B','synthetic candidate'):
        result=await c.admin.put(f'/api/capa/{c.report_id}',json={'d4_root_cause':text})
        assert result.status_code==200,result.text
    advanced=await c.client.post(f'/api/capa/{c.report_id}/advance',json={})
    assert advanced.status_code==200,advanced.text
    path=f"/api/capa/{c.report_id}/d5-proposals/{items[0]['proposal_id']}/adopt"
    rejected=await c.client.post(path,json={'operation_key':'stale','final_text':'must not adopt'})
    assert rejected.status_code==409,rejected.text
    listing=await c.client.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert listing.json()['items'][0]['can_adopt'] is False
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Measure))==0


async def test_actual_formal_measure_full_review_snapshot_and_final_authority(r5_case):
    from app.models.fmea import FMEADocument
    from app.services.version_service import create_fmea_version
    c=r5_case
    _,items=await launch_proposals(c,['R5-T9-REVIEW-ORIGINAL'])
    assert (await c.client.post(f'/api/capa/{c.report_id}/advance',json={})).status_code==200
    adopted=await c.client.post(f"/api/capa/{c.report_id}/d5-proposals/{items[0]['proposal_id']}/adopt",json={'operation_key':'review-adopt','final_text':'R5-T9-REVIEW-FORMAL'})
    assert adopted.status_code==200,adopted.text
    async with c.session() as db:
        doc=await db.get(FMEADocument,c.fmea_id)
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='capa').values(permission_level=4))
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report_id).values(status='D8_APPROVAL_PENDING',d6_verification='synthetic verified'))
        await db.commit()
    from types import SimpleNamespace
    from tests.capa.test_d5_outcome_fence import outcome_ready
    async with c.session() as db:
        actor=SimpleNamespace(user=SimpleNamespace(user_id=c.user_id))
        setup=SimpleNamespace(db=db,docs=[await db.get(FMEADocument,c.fmea_id)],
            report=await db.get(CAPAEightD,c.report_id),user_id=c.user_id,actors=[None,None,actor])
        await outcome_ready(setup)
    path=f'/api/capa/{c.report_id}'
    seen=await c.client.get(path+'/outcome-review')
    assert seen.status_code==200,seen.text
    assert any(item['final_text']=='R5-T9-REVIEW-FORMAL' for item in seen.json()['d5_measures'])
    expected={'target_state':'D8_CLOSURE','expected_outcome_revision':seen.json()['revision'],'expected_review_round_id':seen.json()['review_round_id']}
    async with c.session() as db:
        from sqlalchemy.exc import IntegrityError
        measure_id = await db.scalar(select(CapaD5Measure.measure_id).where(
            CapaD5Measure.proposal_id == UUID(items[0]['proposal_id'])))
        assert measure_id is not None
        with pytest.raises(IntegrityError, match='R6 original D5 adoption is immutable'):
            async with db.begin_nested():
                await db.execute(update(CapaD5Measure).where(CapaD5Measure.measure_id == measure_id)
                    .values(final_text='synthetic changed final').execution_options(synchronize_session=False))
        assert await db.scalar(select(CapaD5Measure.final_text).where(
            CapaD5Measure.measure_id == measure_id)) == 'R5-T9-REVIEW-FORMAL'
        # Exceptional imported-history tamper fixture, not a Task6 correction.
        # Bypass only this owned row; real HTTP guards run after normal triggers resume.
        await db.execute(text('SET LOCAL session_replication_role = replica'))
        changed = await db.execute(update(CapaD5Measure).where(CapaD5Measure.measure_id == measure_id)
            .values(final_text='synthetic changed final').execution_options(synchronize_session=False))
        assert changed.rowcount == 1
        await db.execute(text('SET LOCAL session_replication_role = origin'))
        await db.commit()
    stale=await c.client.post(path+'/advance',json=expected)
    assert stale.status_code==409 and stale.json()['detail']=='CAPA_OUTCOME_REVIEW_CHANGED',stale.text
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    denied=await c.client.get(path+'/outcome-review')
    assert denied.status_code==403 and 'REVIEW-FORMAL' not in denied.text,denied.text
    denied=await c.client.post(path+'/advance',json=expected)
    assert denied.status_code==403,denied.text
    async with c.session() as db:
        assert (await db.get(CAPAEightD,c.report_id)).status=='D8_APPROVAL_PENDING'
