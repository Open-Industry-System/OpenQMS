"""Synthetic witnesses for R5's platform-owned model and controlled executor."""
import importlib.util


def test_r5_controlled_executor_is_a_separate_fail_closed_entry():
    assert importlib.util.find_spec('app.services.agent_runtime.r5_executor') is not None, 'R5 has no enforceable controlled executor'


def test_executor_allows_platform_only_and_cannot_read_unapproved_file(tmp_path):
    import hashlib
    import json
    import socket
    import sys
    from app.services.agent_runtime.r5_executor import ExecutorApproval, run_controlled
    a, b = socket.socket(), socket.socket()
    try:
        a.bind(('127.0.0.1', 0)); a.listen()
        b.bind(('127.0.0.1', 0)); b.listen()
        secret = tmp_path / 'platform-secret'
        secret.write_text('synthetic-secret')
        artifact = tmp_path / 'plugin.py'
        artifact.write_text('import socket,json\nout=[]\nfor p in '+repr([a.getsockname()[1], b.getsockname()[1]])+':\n s=socket.socket(); s.settimeout(1)\n try: s.connect(("127.0.0.1",p)); out.append("allowed")\n except OSError: out.append("denied")\n s.close()\ntry: open('+repr(str(secret))+').read(); out.append("read")\nexcept OSError: out.append("denied")\nprint(json.dumps(out))\n')
        approval = ExecutorApproval.approve(artifact, sys.executable)
        result = run_controlled(approval, platform_port=a.getsockname()[1], request=b'{}', timeout=5)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == ['allowed', 'denied', 'denied']
        b.settimeout(.1)
        try:
            b.accept()
            assert False, 'forbidden receiver B accepted a connection'
        except TimeoutError:
            pass
    finally:
        a.close(); b.close()


def test_model_deployment_and_task_binding_have_dedicated_persistence():
    from app.database import TenantBase
    assert {'agent_model_deployments', 'agent_task_model_bindings'} <= set(TenantBase.metadata.tables), 'R5 selected recipient is not persisted'


def test_model_egress_does_not_accept_a_plugin_url_or_business_body():
    import inspect
    from app.services.agent_runtime import model_egress
    assert list(inspect.signature(model_egress.infer).parameters) == ['db', 'identity', 'request'], 'only platform-built contexts may enter model egress'
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        model_egress.InferenceRequest(provider_url='http://127.0.0.1:1', messages=[{'role':'user','content':'raw business'}])


def test_unmanaged_claim_cannot_mint_a_controlled_run_credential():
    from app.services.agent_runtime import r5_executor
    assert hasattr(r5_executor, 'require_managed_claim'), 'remote credential holder can claim an R5 run outside the sandbox'


async def _model_http_witness(redirect=False,tls=None):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from types import SimpleNamespace
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            self.server.hosts.append(self.headers.get('Host'))
            self.server.bodies.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            if self.server.redirect:
                self.send_response(307); self.send_header('Location', self.server.redirect); self.end_headers(); return
            body = json.dumps({'id':'synthetic','object':'chat.completion','created':1,'model':'synthetic',
                'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'synthetic D5'}}]}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    servers=[]; threads=[]
    for _ in range(2):
        s=ThreadingHTTPServer(('127.0.0.1',0),Handler); s.bodies=[]; s.hosts=[]; s.redirect=None
        if tls is not None:s.socket=tls.wrap_socket(s.socket,server_side=True)
        t=threading.Thread(target=s.serve_forever,daemon=True); t.start(); servers.append(s); threads.append(t)
    a,b=servers
    if redirect: a.redirect='http://127.0.0.1:'+str(b.server_port)+'/v1/chat/completions'
    return SimpleNamespace(a=a,b=b,threads=threads)


import pytest

pytestmark = pytest.mark.ci_r5_native


@pytest.mark.asyncio
@pytest.mark.parametrize('redirect',[False,True])
async def test_actual_http_approved_A_is_only_recipient(redirect):
    from types import SimpleNamespace
    from app.services.agent import provider_adapter
    from app.services.agent_runtime.model_egress import PinnedTransport, UNAVAILABLE
    c=await _model_http_witness(redirect)
    row=SimpleNamespace(base_url='http://127.0.0.1:'+str(c.a.server_port)+'/v1',provider='openai',allowed_addresses=['127.0.0.1'])
    pc=provider_adapter.build_deployment_client('openai','synthetic',row.base_url,'synthetic-no-real-credential',transport=PinnedTransport(row))
    try:
        if redirect:
            # SDK 2 wraps transport denials; SDK 3 preserves PermissionError.
            connection_error = __import__('openai').APIConnectionError
            with pytest.raises((connection_error, PermissionError)) as rejected:
                await provider_adapter.chat_with_tools(pc,[{'role':'user','content':'synthetic-A-sentinel'}],[])
            denial = rejected.value.__cause__ if isinstance(rejected.value, connection_error) else rejected.value
            assert isinstance(denial, PermissionError)
            assert str(denial) == UNAVAILABLE
        else:
            result=await provider_adapter.chat_with_tools(pc,[{'role':'user','content':'synthetic-A-sentinel'}],[])
            assert result.content=='synthetic D5'
        assert len(c.a.bodies)==1
        assert c.a.bodies[0]['messages'][0]['content']=='synthetic-A-sentinel'
        assert c.b.bodies==[]
    finally:
        await pc.client.close()
        for s,t in zip([c.a,c.b],c.threads): s.shutdown(); s.server_close(); t.join()


import pytest_asyncio
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial


@pytest_asyncio.fixture
async def r5_case(d4_text_local_trial, tmp_path):
    import sys
    from datetime import UTC, datetime, timedelta
    from uuid import UUID
    from sqlalchemy import update
    from app.models.role import RolePermission
    from app.services.agent_runtime.r5_executor import ControlledPilot, ExecutorApproval
    c=d4_text_local_trial
    from app.api.admin.agent_models import router as models_router
    c.app.include_router(models_router)
    c.witness=await _model_http_witness()
    required=['capa.d4.root_cause_candidate.masked.v1','capa.d5.proposal.save.v1']
    optional=['capa.d5.proposal.replace.v1']
    registered=await c.admin.post('/api/admin/agent-plugins',json=dict(plugin_key='openqms.controlled-d5-model',plugin_version='1.0.0',manifest=dict(protocol_versions=['1'],required_capabilities=required,optional_capabilities=optional)))
    assert registered.status_code==201,registered.text
    c.r5_id=UUID(registered.json()['plugin']['installation_id']); c.r5_secret=registered.json()['secret']
    artifact=tmp_path/'controlled_plugin.py'; artifact.write_text('print("synthetic controlled plugin")\n')
    c.pilot=ControlledPilot(ExecutorApproval.approve(artifact,sys.executable), c.binding.tenant_id,c.binding.generation,
        c.r5_id,0,'1.0.0',c.client.base_url.port,datetime.now(UTC)+timedelta(minutes=10))
    c.app.state.r5_controlled_pilot=c.pilot
    c.app.state.r5_credential_resolver=lambda ref: 'synthetic-no-real-credential' if ref=='synthetic-test-key' else None
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='capa').values(permission_level=3))
        await db.commit()
    for cap in required+optional:
        body=dict(capability_id=cap,factory_ids=[str(c.factory_id)],object_ids=[str(c.report_id)],product_line_codes=[c.line],expires_at=c.pilot.expires_at.isoformat(),enabled=True)
        if cap==required[0]: body['derived_source_scope']=c.source_scope
        result=await c.admin.post(f'/api/admin/agent-plugins/{c.r5_id}/grants',json=body)
        assert result.status_code==201,result.text
    result=await c.admin.patch(f'/api/admin/agent-plugins/{c.r5_id}',json={'enabled':True}); assert result.status_code==200,result.text
    c.model_body=dict(name='synthetic A',version='1',kind='local',provider='openai',model='synthetic',base_url=f'http://127.0.0.1:{c.witness.a.server_port}/v1',allowed_addresses=['127.0.0.1'],credential_ref='synthetic-test-key')
    model=await c.admin.post('/api/agent/models',json=c.model_body)
    assert model.status_code==201,model.text
    c.model_id=UUID(model.json()['deployment_id'])
    c.create_body=dict(report_id=str(c.report_id),installation_id=str(c.r5_id),request_key='r5-task',initial_text='synthetic D5 request',derived_source_scope=c.source_scope,model_deployment_id=str(c.model_id))
    async def session_info(db):
        db.info['r5_controlled_pilot']=c.pilot; db.info['r5_credential_resolver']=c.app.state.r5_credential_resolver
    c.session_info=session_info
    try: yield c
    finally:
        c.app.state.r5_controlled_pilot=None; c.app.state.r5_credential_resolver=None
        for s,t in zip([c.witness.a,c.witness.b],c.witness.threads): s.shutdown(); s.server_close(); t.join()


@pytest.mark.asyncio
async def test_actual_task_binding_and_remote_claim_denial(r5_case):
    c=r5_case
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201 and created.json()['status']=='ready',created.text
    assert created.json().get('model_deployment') == dict(deployment_id=str(c.model_id), name='synthetic A', version='1')
    claim=await c.client.post('/api/agent/runtime/claim',json=dict(installation_id=str(c.r5_id),secret=c.r5_secret,request_key='remote'))
    assert claim.status_code==403,claim.text
    changed=await c.admin.post('/api/agent/models',json=dict(c.model_body,name='synthetic B',base_url=f'http://127.0.0.1:{c.witness.b.server_port}/v1'))
    assert changed.status_code==201,changed.text
    conflict=await c.client.post('/api/agent/tasks',json=dict(c.create_body,model_deployment_id=changed.json()['deployment_id']))
    assert conflict.status_code==409,conflict.text
    assert c.witness.a.bodies==c.witness.b.bodies==[]


async def _managed_claim(c):
    from app.services.agent_runtime import r5_executor, run_dispatch
    from uuid import UUID
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201 and created.json()['status']=='ready',created.text
    c.task_id=UUID(created.json()['task_id'])
    async with c.session() as db:
        await c.session_info(db)
        db.info['_r5_managed_claim']=r5_executor._MANAGED_CLAIM
        db.info['_r5_managed_task']=c.task_id
        claimed=await run_dispatch.claim_run(db,c.binding,c.r5_id,'managed-claim-placeholder','managed-test')
        c.token=claimed.token; c.run_id=claimed.run_id; c.epoch=claimed.lease_epoch
    return claimed


@pytest.mark.asyncio
async def test_actual_model_gateway_sends_only_server_built_context_to_A(r5_case):
    c=r5_case
    await _managed_claim(c)
    result=await c.client.post('/api/agent/runtime/model/infer',json={},headers={'Authorization':'Bearer '+c.token})
    assert result.status_code==200,result.text
    assert result.json()['deployment_id']==str(c.model_id)
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]
    import json
    context=json.loads(c.witness.a.bodies[0]['messages'][1]['content'])
    assert context['d4_root_cause']=='synthetic candidate'
    assert context['tools'][0]['data']['id']=='cause-A'
    rejected=await c.client.post('/api/agent/runtime/model/infer',json={'provider_url':f'http://127.0.0.1:{c.witness.b.server_port}'},headers={'Authorization':'Bearer '+c.token})
    assert rejected.status_code==422
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['deployment_revoke','source_revoke','config_generation','artifact_change','address_change'])
async def test_final_gateway_rechecks_mutable_admission_before_any_HTTP(r5_case,change):
    c=r5_case
    await _managed_claim(c)
    from sqlalchemy import update
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.tenant import Tenant
    if change=='deployment_revoke':
        response=await c.admin.post(f'/api/agent/models/{c.model_id}/revoke')
        assert response.status_code==200,response.text
    elif change=='source_revoke':
        async with c.session() as db:
            await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id==c.r5_id,AgentPluginGrant.capability_id=='capa.d4.root_cause_candidate.masked.v1').values(enabled=False)); await db.commit()
    elif change=='config_generation':
        from dataclasses import replace
        c.app.state.r5_controlled_pilot=replace(c.pilot,tenant_generation=c.binding.generation+1)
    elif change=='artifact_change':
        c.pilot.approval.artifact.write_text('print("changed")\n')
    elif change=='address_change':
        from dataclasses import replace
        # Approved DNS/address set remains immutable in DB. Changing a numeric
        # recipient is rejected by its immutable-deployment trigger below.
        from app.models.agent_model_deployment import AgentModelDeployment
        from sqlalchemy.exc import DBAPIError
        async with c.session() as db:
            with pytest.raises(DBAPIError):
                await db.execute(update(AgentModelDeployment).where(AgentModelDeployment.deployment_id==c.model_id).values(base_url=f'http://127.0.0.1:{c.witness.b.server_port}/v1'))
            await db.rollback()
        response=await c.admin.post(f'/api/agent/models/{c.model_id}/revoke'); assert response.status_code==200
    response=await c.client.post('/api/agent/runtime/model/infer',json={},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code in {401,403},response.text
    assert c.witness.a.bodies==c.witness.b.bodies==[]


@pytest.mark.asyncio
async def test_active_R5_checkpoint_survives_pause_and_restart_without_recapture(r5_case):
    from uuid import UUID
    from sqlalchemy import select
    from app.models.agent_d5_command import AgentD5CheckpointPosition
    from app.models.agent_d4_recovery import D4RecoveryCheckpoint
    from app.models.agent_model_deployment import AgentTaskModelBinding
    c=r5_case
    await _managed_claim(c)
    result=await c.client.post('/api/agent/runtime/model/infer',json={},headers={'Authorization':'Bearer '+c.token})
    assert result.status_code==200,result.text
    first=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=dict(command_key='before',text='synthetic before checkpoint'),headers={'Authorization':'Bearer '+c.token})
    assert first.status_code==200,first.text
    cp=await c.client.post('/api/agent/runtime/capa/d5/checkpoints',json={},headers={'Authorization':'Bearer '+c.token})
    assert cp.status_code==200,cp.text
    identifier=UUID(cp.json()['checkpoint_id']); watermark=cp.json()['command_watermark']
    later=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=dict(command_key='after',text='synthetic after checkpoint'),headers={'Authorization':'Bearer '+c.token})
    assert later.status_code==200,later.text
    assert watermark==1
    message=await c.client.post(f'/api/agent/tasks/{c.task_id}/messages',json=dict(content='synthetic additional task instruction',idempotency_key='after-checkpoint-message'))
    assert message.status_code==202,message.text
    claimed=await c.client.post('/api/agent/runtime/messages/claim',json={'limit':10},headers={'Authorization':'Bearer '+c.token})
    assert claimed.status_code==200,claimed.text
    ack=await c.client.post('/api/agent/runtime/messages/ack',json=dict(batch_id=claimed.json()['batch_id'],through_sequence=2),headers={'Authorization':'Bearer '+c.token})
    assert ack.status_code==200,ack.text
    paused=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='pause',run_id=str(c.run_id),expected_epoch=c.epoch,idempotency_key='pause'))
    assert paused.status_code==200,paused.text
    pausedcp=await c.client.post(f'/api/agent/tasks/{c.task_id}/d4-recovery-checkpoints',json=dict(run_id=str(c.run_id),expected_epoch=paused.json()['lease_epoch']))
    assert pausedcp.status_code==200 and pausedcp.json()['checkpoint_id']==str(identifier),pausedcp.text
    restarted=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='restart',run_id=str(c.run_id),expected_epoch=paused.json()['lease_epoch'],checkpoint_id=str(identifier),idempotency_key='restart'))
    assert restarted.status_code==200,restarted.text
    async with c.session() as db:
        assert (await db.get(AgentD5CheckpointPosition,identifier)).watermark==watermark
        assert (await db.get(D4RecoveryCheckpoint,identifier)).lease_epoch==c.epoch
        assert (await db.get(AgentTaskModelBinding,c.task_id)).deployment_id==c.model_id
    again=await _managed_claim(c)
    assert again.accepted_message_seq==2
    result=await c.client.post('/api/agent/runtime/model/infer',json={},headers={'Authorization':'Bearer '+c.token})
    assert result.status_code==200 and result.json()['deployment_id']==str(c.model_id),result.text


@pytest.mark.asyncio
@pytest.mark.parametrize('trusted',[True,False])
async def test_cloud_TLS_pins_IP_preserves_hostname_SNI_and_validates_certificate(tmp_path,monkeypatch,trusted):
    import ssl,subprocess,json
    from types import SimpleNamespace
    from app.services.agent_runtime import model_egress
    from app.services.agent import provider_adapter
    cert=tmp_path/'cert.pem'; key=tmp_path/'key.pem'
    subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
        '-keyout',str(key),'-out',str(cert),'-subj','/CN=synthetic.example.test',
        '-addext','subjectAltName=DNS:synthetic.example.test'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key)
    seen=[];tls.set_servername_callback(lambda sock,name,ctx:seen.append(name))
    c=await _model_http_witness(tls=tls)
    if trusted:
        # Trust only the synthetic CA in this test. Production transport still
        # uses verify=True and gets no caller-controlled verification option.
        real_transport=model_egress.httpx.AsyncHTTPTransport
        context=ssl.create_default_context(cafile=str(cert))
        monkeypatch.setattr(model_egress.httpx,'AsyncHTTPTransport',lambda **kwargs:real_transport(**dict(kwargs,verify=context)))
    row=SimpleNamespace(base_url=f'https://synthetic.example.test:{c.a.server_port}/v1',provider='openai',allowed_addresses=['127.0.0.1'])
    pc=provider_adapter.build_deployment_client('openai','synthetic',row.base_url,'synthetic-no-real-credential',transport=model_egress.PinnedTransport(row))
    try:
        if trusted:
            turn=await provider_adapter.chat_with_tools(pc,[{'role':'user','content':'synthetic-TLS-sentinel'}],[])
            assert turn.content=='synthetic D5' and len(c.a.bodies)==1
            assert c.a.hosts==[f'synthetic.example.test:{c.a.server_port}']
        else:
            with pytest.raises(__import__('openai').APIConnectionError):
                await provider_adapter.chat_with_tools(pc,[{'role':'user','content':'synthetic-TLS-sentinel'}],[])
            assert c.a.bodies==[]
        assert seen==['synthetic.example.test']
        assert c.b.bodies==[]
    finally:
        await pc.client.close()
        for s,t in zip([c.a,c.b],c.threads):s.shutdown();s.server_close();t.join()


def test_R5_policy_can_be_loaded_only_by_server_enrollment():
    from app.services.agent_runtime import r5_executor
    assert hasattr(r5_executor,'load_controlled_pilot'), 'no server-owned controlled pilot enrollment'


@pytest.mark.asyncio
async def test_staff_model_administration_and_historical_task_projection(r5_case):
    c=r5_case
    denied=await c.client.post('/api/agent/models',json=dict(c.model_body,version='unauthorized'))
    assert denied.status_code==403,denied.text
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201,created.text
    key=created.json()['task_id']
    revoked=await c.admin.post(f'/api/agent/models/{c.model_id}/revoke');assert revoked.status_code==200
    models=await c.client.get('/api/agent/models');assert models.status_code==200 and models.json()['items']==[]
    detail=await c.client.get(f'/api/agent/tasks/{key}');assert detail.status_code==200,detail.text
    assert detail.json()['model_deployment']==created.json()['model_deployment']
    listed=await c.client.get('/api/agent/tasks');assert listed.status_code==200,listed.text
    assert listed.json()['items'][0]['model_deployment']==created.json()['model_deployment']
    duplicate=await c.admin.post('/api/agent/models',json=c.model_body)
    assert duplicate.status_code==409,duplicate.text


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke',['deployment','source'])
async def test_revocation_still_allows_pause_cancel_but_denies_resume(r5_case,revoke):
    c=r5_case
    await _managed_claim(c)
    if revoke=='deployment':
        result=await c.admin.post(f'/api/agent/models/{c.model_id}/revoke');assert result.status_code==200
    else:
        from app.models.agent_plugin import AgentPluginGrant
        from sqlalchemy import update
        async with c.session() as db:
            await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id==c.r5_id).values(enabled=False));await db.commit()
    paused=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='pause',run_id=str(c.run_id),expected_epoch=c.epoch,idempotency_key='stop'))
    assert paused.status_code==200,paused.text
    resume=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='resume',run_id=str(c.run_id),expected_epoch=paused.json()['lease_epoch'],idempotency_key='resume'))
    assert resume.status_code==403,resume.text
    cancelled=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='cancel',run_id=str(c.run_id),expected_epoch=paused.json()['lease_epoch'],idempotency_key='cancel'))
    assert cancelled.status_code==200,cancelled.text


@pytest.mark.asyncio
async def test_failed_model_send_leaves_durable_control_attempt_without_usable_basis(r5_case):
    from sqlalchemy import select,func
    from app.models.audit import AuditLog
    from app.models.agent_d5_basis import AgentD5BasisReceipt
    c=r5_case
    await _managed_claim(c)
    c.witness.a.redirect=f'http://127.0.0.1:{c.witness.b.server_port}/v1/chat/completions'
    result=await c.client.post('/api/agent/runtime/model/infer',json={},headers={'Authorization':'Bearer '+c.token})
    assert result.status_code==403,result.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='MODEL_EGRESS_ATTEMPT'))==1
        assert await db.scalar(select(func.count()).select_from(AgentD5BasisReceipt))==0
    save=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=dict(command_key='no-model',text='must not save'),headers={'Authorization':'Bearer '+c.token})
    assert save.status_code==403,save.text
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]


@pytest.mark.asyncio
async def test_actual_managed_child_cannot_reach_B_but_calls_platform_model_A(r5_case):
    from dataclasses import replace
    from types import SimpleNamespace
    import sys
    from uuid import UUID
    from app.models.user import User
    from app.services.agent_runtime import r5_executor
    c=r5_case
    c.pilot.approval.artifact.write_text('import sys,json,socket,http.client\np=json.load(sys.stdin)\ns=socket.socket();s.settimeout(1)\ntry:\n s.connect(("127.0.0.1",'+str(c.witness.b.server_port)+'));raise RuntimeError("direct B allowed")\nexcept OSError:pass\ns.close()\nu=http.client.HTTPConnection("127.0.0.1",'+str(c.pilot.platform_port)+',timeout=10)\nu.request("POST","/api/agent/runtime/model/infer",body="{}",headers={"Content-Type":"application/json","Authorization":"Bearer "+p["token"],"X-Tenant-ID":p["tenant_slug"]})\nr=u.getresponse();assert r.status==200,r.status\nassert json.loads(r.read())["content"]=="synthetic D5"\nu.close()\n')
    c.pilot=replace(c.pilot,approval=r5_executor.ExecutorApproval.approve(c.pilot.approval.artifact,sys.executable))
    c.app.state.r5_controlled_pilot=c.pilot
    model=await c.admin.post('/api/agent/models',json=dict(c.model_body,version='managed-child'))
    assert model.status_code==201,model.text
    c.create_body['model_deployment_id']=model.json()['deployment_id']
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201,created.text
    async with c.session() as db:
        await c.session_info(db)
        actor=await db.get(User,c.user_id)
        result=await r5_executor.managed_run(db,SimpleNamespace(user=actor),UUID(created.json()['task_id']),platform_origin=str(c.client.base_url).rstrip('/'))
        assert result['status']=='executed'
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]

@pytest.mark.asyncio
async def test_R5_checkpoint_history_is_paged_typed_current_and_keeps_original_positions(r5_case):
    from sqlalchemy import select
    from app.models.agent_d5_command import AgentD5CheckpointPosition
    from app.models.role import RolePermission
    c=r5_case
    await _managed_claim(c)
    headers={'Authorization':'Bearer '+c.token}
    inferred=await c.client.post('/api/agent/runtime/model/infer',json={},headers=headers)
    assert inferred.status_code==200,inferred.text
    first=await c.client.post('/api/agent/runtime/capa/d5/checkpoints',json={},headers=headers)
    assert first.status_code==200,first.text
    checkpoint_id=first.json()['checkpoint_id']
    history=await c.client.get(f'/api/agent/tasks/{c.task_id}/d5-checkpoints',params={'page':1,'page_size':1})
    assert history.status_code==200,history.text
    assert history.headers['cache-control']=='no-store'
    assert history.json()['items']==[{'checkpoint_id':checkpoint_id,'run_id':str(c.run_id),'created_at':history.json()['items'][0]['created_at']}]
    assert set(history.json())=={'items','total','page','page_size'}
    assert history.json()['total']==1
    assert (await c.client.get(f'/api/agent/tasks/{__import__("uuid").uuid4()}/d5-checkpoints')).status_code==404
    from app.models.agent_d4_recovery import D4RecoveryCheckpoint
    async with c.session() as db:
        await db.execute(__import__('sqlalchemy').update(D4RecoveryCheckpoint).where(D4RecoveryCheckpoint.checkpoint_id==__import__('uuid').UUID(checkpoint_id)).values(tenant_generation=c.binding.generation+1))
        await db.commit()
    assert (await c.client.get(f'/api/agent/tasks/{c.task_id}/d5-checkpoints')).json()['items']==[]
    async with c.session() as db:
        await db.execute(__import__('sqlalchemy').update(D4RecoveryCheckpoint).where(D4RecoveryCheckpoint.checkpoint_id==__import__('uuid').UUID(checkpoint_id)).values(tenant_generation=c.binding.generation))
        await db.commit()
    assert 'watermark' not in history.text and 'text' not in history.text
    assert (await c.client.get(f'/api/agent/tasks/{c.task_id}/d5-checkpoints',params={'page':2,'page_size':1})).json()['items']==[]
    claimed=await c.client.post('/api/agent/runtime/messages/claim',json={'limit':10},headers=headers)
    ack=await c.client.post('/api/agent/runtime/messages/ack',json={'batch_id':claimed.json()['batch_id'],'through_sequence':1},headers=headers)
    assert ack.status_code==200,ack.text
    finished=await c.client.post('/api/agent/runtime/finish',json={'status':'completed'},headers=headers)
    assert finished.status_code==200,finished.text
    assert (await c.client.get(f'/api/agent/tasks/{c.task_id}/d5-checkpoints')).json()['items'][0]['checkpoint_id']==checkpoint_id
    async with c.session() as db:
        await db.execute(__import__('sqlalchemy').update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='capa').values(permission_level=0))
        await db.commit()
    assert (await c.client.get(f'/api/agent/tasks/{c.task_id}/d5-checkpoints')).status_code in (403,404)
    async with c.session() as db:
        position=await db.scalar(select(AgentD5CheckpointPosition).where(AgentD5CheckpointPosition.checkpoint_id==__import__('uuid').UUID(checkpoint_id)))
        assert position.watermark==first.json()['command_watermark']
