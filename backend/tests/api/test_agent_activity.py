"""Activity and static directory via real user JWT and tenant middleware."""
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient
from app.config import settings
from app.core.security import create_access_token
from app.main import app
from tests.services.agent_runtime.conftest import committed_runtime
from tests.services.agent_runtime.test_runtime_access import ready_owned,direct_caps
from tests.services.agent_runtime.test_task_reads import messages
from tests.services.agent_runtime.test_readonly_delivery import context_delivery
from tests.services.agent_runtime.test_runtime_messages import delivery


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['single','dev','production'])
async def test_new_user_gets_off_before_tenant_auth_query_body_all_methods(monkeypatch,mode):
    monkeypatch.setattr(settings,'TENANT_MODE',mode)
    monkeypatch.setattr(settings,'AGENT_TASK_RUNTIME_ENABLED',False)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        for path in ('availability','installations?report_id=bad','bad/activity?page_size=bad'):
            for method in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'):
                response=await client.request(method,'/api/agent/tasks/'+path,content='bad',headers={'X-Tenant-ID':'unknown','Authorization':'Bearer bad'})
                assert response.status_code==404,response.text


@pytest.mark.asyncio
async def test_real_user_static_routes_activity_strict_queries_and_domain(ready_owned,monkeypatch):
    import app.database as database
    from app.models.agent_task import AgentTask
    owned=ready_owned
    monkeypatch.setattr(settings,'AGENT_TASK_RUNTIME_ENABLED',True)
    monkeypatch.setattr(database,'tenant_async_session',owned.factory)
    headers={'Authorization':'Bearer '+create_access_token({'sub':str(owned.user_id),'tenant_id':str(owned.binding.tenant_id)})}
    async with owned.factory(binding=owned.binding) as db:
        report=(await db.get(AgentTask,owned.task_id)).target_capa_id
    await messages(owned,1,2)
    assert not app.dependency_overrides
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.get('/api/agent/tasks/availability',headers=headers)
        assert response.status_code==200,response.text
        assert response.json()=={'enabled':True}
        response=await client.get('/api/agent/tasks/installations',params={'report_id':str(report)},headers=headers)
        assert response.status_code==200,response.text
        assert set(response.json()['items'][0])=={'installation_id','plugin_key','plugin_version'}
        path='/api/agent/tasks/'+str(owned.task_id)+'/activity'
        response=await client.get(path,params={'page_size':'1'},headers=headers)
        assert response.status_code==200,response.text
        assert response.json()['window_end_sequence']==2
        for params in ({'before_sequence':'1'},{'before_sequence':'4','window_end_sequence':'2'}, {'window_end_sequence':'-1'},
                       {'page_size':'true'}, {'page_size':'+1'},{'page_size':'1.0'},{'page_size':'51'},
                       {'window_end_sequence':str(2**63)}, {'before_sequence':str(2**63+1),'window_end_sequence':str(2**63-1)}, {'spoof':'x'}):
            response=await client.get(path,params=params,headers=headers)
            assert response.status_code==422,response.text
        response=await client.get(path,params={'before_sequence':str(2**63),'window_end_sequence':str(2**63-1)},headers=headers)
        assert response.status_code==200,response.text
        assert response.json()['window_end_sequence']==2**63-1
        assert (await client.get('/api/agent/tasks/installations',params={'report_id':str(report),'spoof':'x'},headers=headers)).status_code==422
        assert (await client.get('/api/agent/tasks/availability',params={'spoof':'x'},headers=headers)).status_code==422
        assert (await client.get('/api/agent/tasks/'+str(uuid4())+'/activity',headers=headers)).status_code==404


@pytest.mark.asyncio
async def test_activity_http_whole_page_denial_and_unsourced_progress_no_leaks(context_delivery,monkeypatch):
    import app.database as database
    from sqlalchemy import select,update
    from app.models.agent_runtime_event import AgentRunEvent,AgentProjectionReceipt
    from tests.services.agent_runtime.test_readonly_outputs import write,result_body,event_body
    from tests.services.agent_runtime.test_readonly_delivery import context
    owned=context_delivery
    monkeypatch.setattr(settings,'AGENT_TASK_RUNTIME_ENABLED',True)
    monkeypatch.setattr(database,'tenant_async_session',owned.factory)
    headers={'Authorization':'Bearer '+create_access_token({'sub':str(owned.user_id),'tenant_id':str(owned.binding.tenant_id)})}
    await write(owned,result_body([(await context(owned))['receipt_id']]))
    await write(owned,event_body([],key='unsafe',kind='progress'),True)
    async with owned.factory(binding=owned.binding) as db:
        row=await db.scalar(select(AgentRunEvent))
        row.payload={'stage':'LEAK-STAGE','message':'LEAK-TEXT','completed':99,'total':100,'source_capa_id':'FORGED'}
        await db.commit()
    path='/api/agent/tasks/'+str(owned.task_id)+'/activity'
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        for route in ('/api/agent/tasks/availability',path):
            assert (await client.get(route,headers={'Authorization':'Bearer '+owned.token})).status_code==400
        response=await client.get(path,headers=headers)
        assert response.status_code==200,response.text
        assert 'LEAK' not in response.text and 'FORGED' not in response.text
        assert 'plugin_running' in response.text and 'RESTRICTED EXPLANATION' in response.text
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(update(AgentProjectionReceipt).values(projection_id='forged.v1')); await db.commit()
        response=await client.get(path,headers=headers)
        assert response.status_code==403 and response.json()=={'detail':'Access denied'}
        assert all(field not in response.text for field in ('window_end_sequence','next_before_sequence','receipt_id','RESTRICTED','event_id','total'))


@pytest.mark.asyncio
async def test_cancelled_activity_keeps_claimed_delivery_and_historical_batch_proof(delivery, monkeypatch):
    import app.database as database
    from sqlalchemy import update
    from app.models.agent_plugin import AgentPluginInstallation
    from tests.services.agent_runtime.test_runtime_messages import append, claim, ack, snapshot

    owned = delivery
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(database, 'tenant_async_session', owned.factory)
    headers = {'Authorization': 'Bearer '+create_access_token({
        'sub': str(owned.user_id), 'tenant_id': str(owned.binding.tenant_id)})}
    await append(owned, 'accepted input')
    await append(owned, 'claimed input')
    batch = await claim(owned)
    await ack(owned, batch.batch_id, 1)
    await append(owned, 'queued input')
    before = await snapshot(owned)
    # Historical user access does not require a currently enabled plugin.
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == owned.plugin_id).values(enabled=False))
        await db.commit()
    path = '/api/agent/tasks/'+str(owned.task_id)
    assert not app.dependency_overrides
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post(path+'/control', headers=headers, json={
            'action': 'cancel', 'run_id': str(owned.run_id), 'expected_epoch': 1,
            'idempotency_key': 'cancel-historical-inputs'})
        assert response.status_code == 200, response.text
        response = await client.get(path+'/activity', headers=headers)
        assert response.status_code == 200, response.text
        page = response.json()
        assert (page['task_status'], page['run_status'], page['lease_epoch']) == ('cancelled', 'stopped', 2)
        inputs = [item['data'] for item in page['items'] if item['kind'] == 'message']
        assert [(row['sequence'], row['state'], row['content']) for row in inputs] == [
            (1, 'received', 'accepted input'), (2, 'claimed', 'claimed input'),
            (3, 'queued', 'queued input')]
        # The actual historical batch remains readable at its original epoch,
        # even though its owning Run is stopped and has advanced to epoch 2.
        acknowledgements = [item['data'] for item in page['items'] if item['kind'] == 'ack']
        assert acknowledgements == [{'batch_id': str(batch.batch_id), 'state': 'received'}]
        assert (await client.post('/api/agent/runtime/messages/claim', json={},
            headers={'Authorization': 'Bearer '+owned.token})).status_code == 401
    assert await snapshot(owned) == before
