"""Actual managed R5 artifact over deterministic Responses HTTP, never live keys."""
import asyncio
import json
from http.server import BaseHTTPRequestHandler
from uuid import UUID

import pytest
from sqlalchemy import select, func, update

from app.models.agent_d5_basis import AgentD5BasisReceipt
from app.models.audit import AuditLog
from app.models.capa_d5_proposal import CapaD5Proposal
from app.models.role import RolePermission
from tests.services.agent_runtime.test_r5_model_binding import r5_case
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial
from tests.e2e.test_r5_model_agent import actual_agent, call, _managed_claim, workflow_call, execute

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.asyncio]
PRIVATE = "RESPONSES_PRIVATE_REASONING_SENTINEL"


async def responses_agent(c, turns, statuses=None):
    c.model_body.update(api_protocol='responses', model='gpt-6.1-terra')
    await actual_agent(c)
    c.witness.a.frames = []
    c.witness.a.paths = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            if self.path != '/v1/responses':
                self.send_response(404); self.end_headers(); return
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.paths.append(self.path)
            self.server.bodies.append(body)
            index = min(len(self.server.bodies)-1, len(turns)-1)
            message = turns[index]
            items = [{'type':'reasoning', 'id':f'rs_{index}', 'summary':[], 'encrypted_content':PRIVATE+str(index)}]
            if message.get('content') is not None:
                items.append({'type':'message','id':f'msg_{index}','role':'assistant','status':'completed',
                    'phase':'commentary' if message.get('tool_calls') else 'final_answer',
                    'content':[{'type':'output_text','text':message['content'],'annotations':[]}]})
            for tool in message.get('tool_calls', []):
                items.append({'type':'function_call','id':f'fc_{index}_{tool["id"]}','call_id':tool['id'],
                    'name':tool['function']['name'],'arguments':tool['function']['arguments'],'status':'completed'})
            self.server.frames.append(items)
            response = json.dumps({'id':f'resp_{index}','object':'response','created_at':1,
                'status':statuses[index] if statuses else 'completed','model':'gpt-6.1-terra',
                'output':items,'parallel_tool_calls':True,'tools':body['tools'],'tool_choice':'auto',
                'error':None,'incomplete_details':None}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(response))); self.end_headers(); self.wfile.write(response)
    c.witness.a.RequestHandlerClass = Handler


async def test_actual_responses_managed_read_supplement_save_and_private_replay(r5_case):
    c = r5_case
    await responses_agent(c, [dict(call('read_d4'), content='Read the authorized D4 first.'), call('request_supplement', {'question':'Confirm no extra context.'}, 'question'),
        call('save_proposal', {'text':'Responses synthetic corrective measure'}, 'save'), {'content':'done'}])
    created = await c.client.post('/api/agent/tasks', json=c.create_body)
    assert created.status_code == 201, created.text
    task = created.json()['task_id']
    running = asyncio.create_task(c.client.post(f'/api/agent/tasks/{task}/launch', timeout=130))
    try:
        for _ in range(1000):
            status = await c.client.get(f'/api/agent/tasks/{task}/workflow')
            assert PRIVATE not in status.text
            if status.status_code == 200 and status.json().get('question'): break
            if running.done(): pytest.fail((await running).text)
            await asyncio.sleep(.02)
        else: pytest.fail('Responses did not reach employee checkpoint')
        assert status.json()['checkpoint_id']
        continued = await c.client.post(f'/api/agent/tasks/{task}/messages', json={
            'content':'{"intent":"continue_d5","additional_context":"none"}', 'idempotency_key':'responses-continue'})
        assert continued.status_code == 202, continued.text
        result = await running
        assert result.status_code == 200, result.text
        async with c.session() as db:
            rows = list(await db.scalars(select(CapaD5Proposal).where(CapaD5Proposal.task_id==UUID(task))))
            assert len(rows)==1 and rows[0].original_text=='Responses synthetic corrective measure'
            assert await db.scalar(select(func.count()).select_from(AgentD5BasisReceipt).where(AgentD5BasisReceipt.task_id==UUID(task))) >= 1
            audit = list(await db.scalars(select(AuditLog.changed_fields)))
            assert PRIVATE not in json.dumps(audit, default=str)
        assert len(c.witness.a.bodies)==4 and c.witness.b.bodies==[]
        for index, body in enumerate(c.witness.a.bodies):
            assert body['store'] is False and 'previous_response_id' not in body
            assert body['model']=='gpt-6.1-terra'
            assert all(tool['type']=='function' and tool['strict'] is False and 'function' not in tool for tool in body['tools'])
            prior = [item for item in body['input'] if item.get('type')=='reasoning']
            assert prior == [c.witness.a.frames[i][0] for i in range(index)]
        final = c.witness.a.bodies[-1]['input']
        assert any(item.get('phase')=='commentary' and item.get('id')=='msg_0' for item in c.witness.a.bodies[1]['input'])
        assert any(item.get('phase')=='final_answer' for item in c.witness.a.frames[-1])
        assert any(item.get('type')=='function_call_output' and item['call_id']=='save' for item in final)
    finally:
        if not running.done(): running.cancel(); await asyncio.gather(running, return_exceptions=True)


async def test_responses_tool_replay_preserves_one_report_suggestion(r5_case):
    c = r5_case
    await responses_agent(c, [call('read_d4'), call('save_proposal', {'text':'one Responses suggestion'}, 'save')])
    await _managed_claim(c)
    first = await workflow_call(c)
    assert (await execute(c, first['tool_calls'][0]['id'])).status_code == 200
    second = await workflow_call(c, 1)
    identifier = second['tool_calls'][0]['id']
    saved = await execute(c, identifier)
    assert saved.status_code == 200, saved.text
    assert (await execute(c, identifier)).json() == saved.json()
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal)) == 1
    assert len(c.witness.a.bodies)==2 and c.witness.b.bodies==[]
    assert PRIVATE not in json.dumps(second)


async def test_responses_source_revocation_stops_next_egress(r5_case):
    c = r5_case
    await responses_agent(c, [call('read_d4'), {'content':'must not be reached'}])
    await _managed_claim(c)
    first = await workflow_call(c)
    assert (await execute(c, first['tool_calls'][0]['id'])).status_code == 200
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id, RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    response = await c.client.post('/api/agent/runtime/model/infer', json={'operation':'workflow','turn':1},
        headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==401, response.text
    assert response.json()=={'detail':'Invalid run credential'}
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]


async def test_incomplete_responses_has_no_usable_basis_or_saved_proposal(r5_case):
    c = r5_case
    await responses_agent(c, [call('read_d4'), call('save_proposal', {'text':'must not save'}, 'save')],
                          statuses=['completed','incomplete'])
    await _managed_claim(c)
    first = await workflow_call(c)
    assert (await execute(c, first['tool_calls'][0]['id'])).status_code == 200
    response = await c.client.post('/api/agent/runtime/model/infer', json={'operation':'workflow','turn':1},
        headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==403, response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD5BasisReceipt))==0
        assert await db.scalar(select(func.count()).select_from(CapaD5Proposal))==0
    assert len(c.witness.a.bodies)==2 and c.witness.b.bodies==[]


async def test_responses_propose_d5_http_never_returns_opaque_provider_items(r5_case):
    from tests.services.agent_runtime.test_r5_model_binding import _managed_claim as claim_without_workflow
    c = r5_case
    await responses_agent(c, [{'content':'Synthetic inference text only'}])
    await claim_without_workflow(c)
    response = await c.client.post('/api/agent/runtime/model/infer', json={}, headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==200, response.text
    assert response.json()['content']=='Synthetic inference text only'
    assert 'response_items' not in response.json() and PRIVATE not in response.text
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]


@pytest.mark.parametrize('case', ['valid', 'proof_revoked', 'grant_revoked', 'free_chat'])
async def test_root_only_sidebar_intent_derives_only_current_approved_source(r5_case, case):
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    from app.models.agent_task import AgentTaskGrant
    c = r5_case
    await actual_agent(c)
    body = dict(c.create_body)
    body.pop('derived_source_scope')
    if case == 'free_chat': body['initial_text'] = 'ordinary chat without declared source'
    if case in {'proof_revoked', 'grant_revoked'}:
        async with c.session() as db:
            if case == 'proof_revoked':
                await db.execute(update(CapaD4RootCauseSourceProof).values(status='superseded'))
            else:
                await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id == c.r5_id,
                    AgentPluginGrant.capability_id == 'capa.d4.root_cause_candidate.masked.v1').values(enabled=False))
            await db.commit()
    response = await c.client.post('/api/agent/tasks', json=body)
    assert response.status_code == 201, response.text
    expected = 'ready' if case == 'valid' else 'blocked_capability'
    assert response.json()['status'] == expected
    repeated = await c.client.post('/api/agent/tasks', json=body)
    assert repeated.status_code == 201 and repeated.json()['task_id'] == response.json()['task_id']
    async with c.session() as db:
        count = await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(
            AgentTaskGrant.task_id == UUID(response.json()['task_id']),
            AgentTaskGrant.capability_id == 'capa.d4.root_cause_candidate.masked.v1'))
        assert count == (1 if case == 'valid' else 0)
    assert c.witness.a.bodies == c.witness.b.bodies == []


async def test_actual_responses_root_only_sidebar_request_reads_then_saves(r5_case):
    c = r5_case
    await responses_agent(c, [call('read_d4'), call('save_proposal', {'text':'Root-only actual Responses measure'}, 'save'), {'content':'done'}])
    body = dict(c.create_body)
    body.pop('derived_source_scope')
    created = await c.client.post('/api/agent/tasks', json=body)
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task = created.json()['task_id']
    launch = await c.client.post(f'/api/agent/tasks/{task}/launch', timeout=130)
    assert launch.status_code == 200, launch.text
    async with c.session() as db:
        rows = list(await db.scalars(select(CapaD5Proposal).where(CapaD5Proposal.task_id == UUID(task))))
        assert len(rows) == 1 and rows[0].original_text == 'Root-only actual Responses measure'
    assert len(c.witness.a.bodies) == 3 and c.witness.b.bodies == []
