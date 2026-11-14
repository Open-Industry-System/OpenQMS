"""Real managed artifact and deterministic HTTP model, never real credentials."""
from pathlib import Path
import pytest
from tests.services.agent_runtime.test_r5_model_binding import r5_case, _managed_claim as claim_without_workflow
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial


async def _managed_claim(c):
    result=await claim_without_workflow(c)
    from app.services.agent_runtime import runtime_access, model_workflow
    async with c.session() as db:
        await c.session_info(db)
        identity=await runtime_access.verify_runtime_identity(db,c.token,c.binding)
        model_workflow.begin_round(identity)
    return result


def test_actual_r5_artifact_is_present():
    assert (Path(__file__).parents[2] / 'examples/d5_proposal_agent.py').is_file(), 'T7 managed model artifact missing'


@pytest.mark.asyncio
async def test_workflow_rejects_unissued_tools(r5_case):
    c = r5_case
    await _managed_claim(c)
    response = await c.client.post('/api/agent/runtime/model/tools', json={'call_id':'unissued'}, headers={'Authorization':'Bearer '+c.token})
    assert response.status_code == 403, response.text


async def actual_agent(c):
    from dataclasses import replace
    import sys
    from app.services.agent_runtime.r5_executor import ExecutorApproval
    artifact = Path(__file__).parents[2] / 'examples/d5_proposal_agent.py'
    c.pilot = replace(c.pilot, approval=ExecutorApproval.approve(artifact, sys.executable))
    c.app.state.r5_controlled_pilot = c.pilot
    model = await c.admin.post('/api/agent/models', json=dict(c.model_body, version='actual-agent'))
    assert model.status_code == 201, model.text
    c.create_body.update(model_deployment_id=model.json()['deployment_id'], initial_text='deliver_d4_root_cause_candidate_v1')


def scripted_model(c, turns):
    import json
    from http.server import BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.bodies.append(body)
            message = turns[min(len(self.server.bodies)-1, len(turns)-1)]
            response = json.dumps({'id':'synthetic','object':'chat.completion','created':1,'model':'synthetic',
                'choices':[{'index':0,'finish_reason':'stop','message':dict(role='assistant', **message)}]}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(response))); self.end_headers(); self.wfile.write(response)
    c.witness.a.RequestHandlerClass = Handler


def call(name, args=None, identifier='call'):
    import json
    return {'content':None, 'tool_calls':[{'id':identifier,'type':'function','function':{'name':name,'arguments':json.dumps(args or {})}}]}


@pytest.mark.asyncio
async def test_real_sandbox_model_reads_requests_checkpoint_accepts_and_saves(r5_case):
    import asyncio
    from uuid import UUID
    from sqlalchemy import select
    from app.models.capa_d5_proposal import CapaD5Proposal, CapaD5ProposalSource
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    c = r5_case
    await actual_agent(c)
    scripted_model(c, [call('read_d4'),call('request_supplement', {'question':'Confirm no extra source context.'}, 'supplement'),
        call('save_proposal',{'text':'synthetic model corrective action'},'save'), {'content':'done'}])
    created = await c.client.post('/api/agent/tasks', json=c.create_body)
    assert created.status_code == 201, created.text
    task = created.json()['task_id']
    launch = asyncio.create_task(c.client.post(f'/api/agent/tasks/{task}/launch', timeout=130))
    try:
        for _ in range(500):
            status = await c.client.get(f'/api/agent/tasks/{task}/workflow')
            if status.status_code == 200 and status.json().get('question'):
                break
            if launch.done():
                assert False, (await launch).text
            await asyncio.sleep(.02)
        assert status.json()['question']=='Confirm no extra source context.'
        assert status.json()['checkpoint_id']
        duplicate=await c.client.post(f'/api/agent/tasks/{task}/launch', timeout=5)
        assert duplicate.status_code==403,duplicate.text
        message = await c.client.post(f'/api/agent/tasks/{task}/messages',json={'content':'{"intent":"continue_d5","additional_context":"none"}','idempotency_key':'supplement'})
        assert message.status_code == 202, message.text
        response = await launch
        assert response.status_code == 200, response.text
        assert response.json()['status']=='executed'
        async with c.session() as db:
            proposals = list(await db.scalars(select(CapaD5Proposal).where(CapaD5Proposal.task_id==UUID(task))))
            assert len(proposals)==1 and proposals[0].original_text=='synthetic model corrective action'
            sources=list(await db.scalars(select(CapaD5ProposalSource).where(CapaD5ProposalSource.proposal_id==proposals[0].proposal_id)))
            assert len(sources)==1 and sources[0].node_id=='cause-A'
            assert len(list(await db.scalars(select(AgentD5BasisReceipt))))>=1
        assert len(c.witness.a.bodies)==4 and c.witness.b.bodies==[]
        second=c.witness.a.bodies[1]['messages']
        assert any(m['role']=='tool' and 'synthetic candidate' in m['content'] for m in second)
        third=c.witness.a.bodies[2]['messages']
        for index, message in enumerate(third):
            if message.get('tool_calls'):
                assert third[index+1]['role']=='tool', 'OpenAI tool result must immediately follow assistant calls'
        assert any(m['role']=='user' and 'continue_d5' in m['content'] for m in third)
    finally:
        if not launch.done():
            launch.cancel()
            await asyncio.gather(launch, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('tools', [[],[call('query_source')['tool_calls'][0]],
    [call('query_source',identifier='q1')['tool_calls'][0],call('read_d4',identifier='q2')['tool_calls'][0]]])
async def test_actual_artifact_allows_zero_one_or_multiple_queries(r5_case, tools):
    c=r5_case
    await actual_agent(c)
    scripted_model(c,[{'content':'done','tool_calls':tools},{'content':'done'}])
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    response=await c.client.post('/api/agent/tasks/'+created.json()['task_id']+'/launch',timeout=130)
    assert response.status_code==200,response.text
    assert len(c.witness.a.bodies)==(2 if tools else 1) and c.witness.b.bodies==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('turn', [call('delete_report'), call('query_source',{'url':'http://forbidden'}),
    call('save_proposal',{'text':'字'*6000}), {'content':None,'tool_calls':[call('query_source',identifier=str(i))['tool_calls'][0] for i in range(9)]}])
async def test_malformed_unapproved_and_over_budget_model_tools_stop(r5_case,turn):
    c=r5_case
    await _managed_claim(c)
    scripted_model(c,[turn])
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow'},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==403,response.text
    again=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow'},headers={'Authorization':'Bearer '+c.token})
    assert again.status_code==403,response.text
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]


async def workflow_call(c, turn=0):
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow','turn':turn},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==200,response.text
    return response.json()


async def execute(c, identifier):
    return await c.client.post('/api/agent/runtime/model/tools',json={'call_id':identifier},headers={'Authorization':'Bearer '+c.token})


@pytest.mark.asyncio
async def test_expired_round_cannot_restart_budget_with_turn_zero(r5_case):
    from app.services.agent_runtime import model_workflow
    c=r5_case
    await _managed_claim(c)
    scripted_model(c,[call('read_d4')])
    await workflow_call(c)
    state=model_workflow._rounds[(c.binding.tenant_id,c.run_id,c.epoch)]
    state.deadline=0
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow'},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==403,response.text
    assert len(c.witness.a.bodies)==1


@pytest.mark.asyncio
async def test_tool_id_retries_use_original_write_and_no_arbitrary_context_can_save(r5_case):
    from sqlalchemy import select,func
    from app.models.capa_d5_proposal import CapaD5Proposal
    c=r5_case
    c.create_body['initial_text']='deliver_d4_root_cause_candidate_v1'
    await _managed_claim(c)
    scripted_model(c,[call('read_d4'),call('save_proposal',{'text':'immutable synthetic text'},'save')])
    first=await workflow_call(c)
    assert (await execute(c,first['tool_calls'][0]['id'])).status_code==200
    second=await workflow_call(c,1)
    identifier=second['tool_calls'][0]['id']
    saved=await execute(c,identifier)
    assert saved.status_code==200,saved.text
    assert (await execute(c,identifier)).json()==saved.json()
    assert (await c.client.post('/api/agent/runtime/model/tools',json={'call_id':identifier,'text':'changed'},headers={'Authorization':'Bearer '+c.token})).status_code==422
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal))==1
    assert len(c.witness.a.bodies)==2


@pytest.mark.asyncio
async def test_lost_server_launch_state_cannot_be_recreated_by_old_run_token(r5_case):
    c=r5_case
    await claim_without_workflow(c)
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow'},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==403,response.text
    assert c.witness.a.bodies==[]


@pytest.mark.asyncio
async def test_missing_valid_basis_can_chat_but_cannot_save(r5_case):
    from sqlalchemy import update
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    c=r5_case
    c.create_body['initial_text']='deliver_d4_root_cause_candidate_v1'
    await _managed_claim(c)
    await accept_initial(c)
    async with c.session() as db:
        await db.execute(update(CapaD4RootCauseSourceProof).values(status='superseded'))
        await db.commit()
    scripted_model(c,[call('read_d4'), call('save_proposal',{'text':'must not save'},'save')])
    first=await workflow_call(c)
    result=await execute(c,first['tool_calls'][0]['id'])
    assert result.status_code==200 and result.json()['status']=='missing_basis',result.text
    second=await workflow_call(c,1)
    result=await execute(c,second['tool_calls'][0]['id'])
    assert result.status_code==403,result.text
    assert len(c.witness.a.bodies)==2 and c.witness.b.bodies==[]


@pytest.mark.asyncio
async def test_cancel_prevents_next_issued_tool_and_new_model_call(r5_case):
    c=r5_case
    await _managed_claim(c)
    scripted_model(c,[call('read_d4')])
    first=await workflow_call(c)
    cancelled=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json={'action':'cancel','run_id':str(c.run_id),'expected_epoch':c.epoch,'idempotency_key':'stop'})
    assert cancelled.status_code==200,cancelled.text
    assert (await execute(c,first['tool_calls'][0]['id'])).status_code in {401,403}
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow','turn':1},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code in {401,403}
    assert len(c.witness.a.bodies)==1


@pytest.mark.asyncio
async def test_undefined_additional_task_context_is_delivered_but_save_denied(r5_case):
    c=r5_case
    await _managed_claim(c)
    # Actual unrestricted employee chat is permitted to the approved model,
    # while T4 keeps it out of shared report material.
    batch=await c.client.post('/api/agent/runtime/messages/claim',json={},headers={'Authorization':'Bearer '+c.token})
    ack=await c.client.post('/api/agent/runtime/messages/ack',json={'batch_id':batch.json()['batch_id'],'through_sequence':1},headers={'Authorization':'Bearer '+c.token})
    assert ack.status_code==200,ack.text
    scripted_model(c,[call('read_d4'),call('save_proposal',{'text':'must not share'},'save')])
    first=await workflow_call(c)
    assert any(m.get('content')=='synthetic D5 request' for m in c.witness.a.bodies[0]['messages'])
    assert (await execute(c,first['tool_calls'][0]['id'])).status_code==200
    second=await workflow_call(c,1)
    result=await execute(c,second['tool_calls'][0]['id'])
    assert result.status_code==403,result.text


@pytest.mark.asyncio
async def test_concurrent_same_turn_is_one_model_round_and_same_ids(r5_case):
    import asyncio
    c=r5_case
    await _managed_claim(c)
    scripted_model(c,[call('read_d4')])
    first,second=await asyncio.wait_for(asyncio.gather(workflow_call(c),workflow_call(c)),timeout=5)
    assert first==second
    assert len(c.witness.a.bodies)==1


@pytest.mark.asyncio
async def test_original_delivered_tool_snapshot_cannot_silently_change_before_model(r5_case):
    from sqlalchemy import update
    from app.models.fmea import FMEADocument
    c=r5_case
    await _managed_claim(c)
    scripted_model(c,[call('read_d4')])
    first=await workflow_call(c)
    assert (await execute(c,first['tool_calls'][0]['id'])).status_code==200
    async with c.session() as db:
        await db.execute(update(FMEADocument).where(FMEADocument.fmea_id==c.fmea_id).values(graph_data={
            'nodes':[{'id':'cause-A','type':'FailureCause','description':'changed after actual read'}],'edges':[]}))
        await db.commit()
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow','turn':1},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code in {401,403},response.text
    assert len(c.witness.a.bodies)==1


@pytest.mark.asyncio
async def test_unknown_write_can_only_replay_original_issued_id(r5_case,monkeypatch):
    from app.services.agent_runtime import d5_commands
    from sqlalchemy import select,func
    from app.models.capa_d5_proposal import CapaD5Proposal
    c=r5_case
    c.create_body['initial_text']='deliver_d4_root_cause_candidate_v1'
    await _managed_claim(c)
    scripted_model(c,[call('read_d4'), {'content':None,'tool_calls':[
        call('save_proposal',{'text':'first original'},'first')['tool_calls'][0],
        call('save_proposal',{'text':'second independent'},'second')['tool_calls'][0]]}])
    first=await workflow_call(c)
    assert (await execute(c,first['tool_calls'][0]['id'])).status_code==200
    second=await workflow_call(c,1)
    original=d5_commands.save_proposal
    keys=[]
    async def committed_unknown(db,identity,body):
        keys.append(body.command_key)
        result=await original(db,identity,body)
        if len(keys)==1:
            raise ConnectionResetError('synthetic lost response after committed write')
        return result
    monkeypatch.setattr(d5_commands,'save_proposal',committed_unknown)
    identifier=second['tool_calls'][0]['id']
    unknown=await execute(c,identifier)
    assert unknown.status_code==409,unknown.text
    blocked=await execute(c,second['tool_calls'][1]['id'])
    assert blocked.status_code==403,blocked.text
    replay=await execute(c,identifier)
    assert replay.status_code==200,replay.text
    assert keys==['r5:'+identifier]*2
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal))==1


@pytest.mark.asyncio
async def test_question_status_rechecks_actual_reader_source_permissions(r5_case):
    from sqlalchemy import update
    from app.models.agent_plugin import AgentPluginGrant
    c=r5_case
    await _managed_claim(c)
    await accept_initial(c)
    scripted_model(c,[call('request_supplement',{'question':'restricted synthetic source question'})])
    first=await workflow_call(c)
    assert (await execute(c,first['tool_calls'][0]['id'])).json()['status']=='waiting'
    status=await c.client.get(f'/api/agent/tasks/{c.task_id}/workflow')
    assert status.status_code==200 and status.json()['question']=='restricted synthetic source question',status.text
    async with c.session() as db:
        await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id==c.r5_id,
            AgentPluginGrant.capability_id=='capa.d4.root_cause_candidate.masked.v1').values(enabled=False))
        await db.commit()
    denied=await c.client.get(f'/api/agent/tasks/{c.task_id}/workflow')
    assert denied.status_code==403 and 'restricted synthetic' not in denied.text,denied.text
    assert (await execute(c,first['tool_calls'][0]['id'])).status_code in {401,403}
    model_denied=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow','turn':1},headers={'Authorization':'Bearer '+c.token})
    assert model_denied.status_code in {401,403},model_denied.text
    assert len(c.witness.a.bodies)==1


async def accept_initial(c):
    headers={'Authorization':'Bearer '+c.token}
    batch=await c.client.post('/api/agent/runtime/messages/claim',json={},headers=headers)
    assert batch.status_code==200,batch.text
    ack=await c.client.post('/api/agent/runtime/messages/ack',json={'batch_id':batch.json()['batch_id'],'through_sequence':batch.json()['messages'][-1]['sequence']},headers=headers)
    assert ack.status_code==200,ack.text


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['malformed','timeout','cancel','source_revoke'])
async def test_actual_child_failure_releases_only_own_active_lease(r5_case,monkeypatch,failure):
    import asyncio
    from sqlalchemy import select
    from app.models.agent_task import AgentRun
    from app.services.agent_runtime import r5_executor
    c=r5_case
    await actual_agent(c)
    scripted_model(c,[call('forbidden_write') if failure=='malformed' else call('request_supplement',{'question':'synthetic wait'})])
    if failure=='timeout':
        actual=r5_executor.run_controlled
        def short_child(*args,**kwargs):
            return actual(*args,**dict(kwargs,timeout=1))
        monkeypatch.setattr(r5_executor,'run_controlled',short_child)
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    task=created.json()['task_id']
    launch=asyncio.create_task(c.client.post(f'/api/agent/tasks/{task}/launch',timeout=10))
    if failure in {'cancel','source_revoke'}:
        for _ in range(300):
            status=await c.client.get(f'/api/agent/tasks/{task}/workflow')
            if status.status_code==200 and status.json().get('question'):
                break
            await asyncio.sleep(.01)
        assert status.json()['question']=='synthetic wait'
        async with c.session() as db:
            run=await db.scalar(select(AgentRun).where(AgentRun.task_id==created.json()['task_id']))
            run_id,epoch=run.run_id,run.lease_epoch
        if failure=='cancel':
            cancelled=await c.client.post(f'/api/agent/tasks/{task}/control',json={'action':'cancel','run_id':str(run_id),'expected_epoch':epoch,'idempotency_key':'cancel-child'})
            assert cancelled.status_code==200,cancelled.text
        else:
            from sqlalchemy import update
            from app.models.agent_plugin import AgentPluginGrant
            async with c.session() as db:
                await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id==c.r5_id,AgentPluginGrant.capability_id=='capa.d4.root_cause_candidate.masked.v1').values(enabled=False))
                await db.commit()
    response=await launch
    assert response.status_code==403,response.text
    expected='cancelled' if failure=='cancel' else 'failed'
    detail=await c.client.get(f'/api/agent/tasks/{task}')
    assert detail.json()['status']==expected,detail.text
    async with c.session() as db:
        run=await db.scalar(select(AgentRun).where(AgentRun.task_id==created.json()['task_id']))
        assert run.status==('stopped' if failure=='cancel' else 'failed')
        assert run.lease_expires_at is None and run.claim_key is None
    status=await c.client.get(f'/api/agent/tasks/{task}/workflow')
    assert status.status_code==200 and status.json()['status']==expected,status.text
    assert not r5_executor._launches
    assert c.witness.b.bodies==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('read_first',[False,True])
async def test_supplement_in_multi_tool_turn_defers_reply_until_all_results(r5_case,read_first):
    import asyncio
    c=r5_case
    await actual_agent(c)
    calls=[call('request_supplement',{'question':'synthetic multi tool question'},'ask')['tool_calls'][0],call('read_d4',identifier='read')['tool_calls'][0]]
    if read_first:
        calls.reverse()
    scripted_model(c,[{'content':None,'tool_calls':calls},call('save_proposal',{'text':'synthetic batch proposal'},'save'),{'content':'done'}])
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    task=created.json()['task_id']
    launch=asyncio.create_task(c.client.post(f'/api/agent/tasks/{task}/launch',timeout=15))
    for _ in range(300):
        status=await c.client.get(f'/api/agent/tasks/{task}/workflow')
        if status.status_code==200 and status.json().get('question'):
            break
        await asyncio.sleep(.01)
    assert status.json()['question']=='synthetic multi tool question'
    if read_first:
        from sqlalchemy import select,func
        from app.models.agent_d5_basis import AgentD5BasisReceipt
        assert status.json()['checkpoint_id'] is None
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentD5BasisReceipt))==0, 'checkpoint must not mint undelivered basis'
    posted=await c.client.post(f'/api/agent/tasks/{task}/messages',json={'content':'{"intent":"continue_d5","additional_context":"none"}','idempotency_key':'multi'})
    assert posted.status_code==202,posted.text
    response=await launch
    assert response.status_code==200,response.text
    messages=c.witness.a.bodies[1]['messages']
    index=next(i for i,m in enumerate(messages) if m.get('tool_calls'))
    assert [m['role'] for m in messages[index:index+4]]==['assistant','tool','tool','user']
    assert sum(m['role']=='user' and 'continue_d5' in m['content'] for m in messages)==1
    from sqlalchemy import select,func
    from app.models.capa_d5_proposal import CapaD5Proposal
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal))==1
