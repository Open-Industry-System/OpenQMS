"""T8 real Chromium/HTTP two-role UI; deterministic loopback recipient only."""
import asyncio
import json
import os
from pathlib import Path
import socket
from uuid import uuid4

from fastapi import HTTPException, Request
import httpx
import pytest
from sqlalchemy import select, update

from app.core.security import hash_password
from app.models.agent_task import AgentTaskMessage
from app.models.agent_model_deployment import AgentTaskModelBinding
from app.models.capa import CAPAEightD
from app.models.capa_d5_proposal import CapaD5Measure
from app.models.factory import UserFactory
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from tests.ci.browser_runtime import browser_environment, resolve_browser
from tests.services.agent_runtime.test_r5_model_binding import r5_case, d4_text_local_trial, owned_local_trial, _managed_claim
from tests.e2e.agent_local_trial_harness import PASSWORD

pytestmark = [pytest.mark.requires_db, pytest.mark.ci_browser]

@pytest.mark.asyncio
async def test_real_two_role_R5_sidebar_and_report_collaboration(r5_case,tmp_path):
    c=r5_case
    from app.api import product_line, fmea, knowledge
    for router in (product_line.router,fmea.router,knowledge.router): c.app.include_router(router)
    await _managed_claim(c)
    token={'Authorization':'Bearer '+c.token}
    inferred=await c.client.post('/api/agent/runtime/model/infer',json={},headers=token)
    assert inferred.status_code==200,inferred.text
    checkpoint=await c.client.post('/api/agent/runtime/capa/d5/checkpoints',json={},headers=token)
    assert checkpoint.status_code==200,checkpoint.text
    saved=await c.client.post('/api/agent/runtime/capa/d5/proposals',json={'command_key':'t8-browser','text':'T8 Agent 原文'},headers=token)
    assert saved.status_code==200,saved.text
    proposal=saved.json()['proposal_id']
    model_b=await c.admin.post('/api/agent/models',json=dict(c.model_body,name='synthetic B',base_url=f'http://127.0.0.1:{c.witness.b.server_port}/v1'))
    assert model_b.status_code==201,model_b.text
    async with c.session() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==c.report_id).values(status='D5_CORRECTION'))
        role=await db.scalar(select(RoleDefinition).where(RoleDefinition.role_key=='field_qe'))
        colleague=User(username='t8-colleague',display_name='T8 colleague',password_hash=hash_password(PASSWORD),role_id=role.id,legacy_role='field_qe',factory_id=c.factory_id,is_active=True)
        db.add(colleague);await db.flush()
        db.add_all([UserFactory(user_id=colleague.user_id,factory_id=c.factory_id),UserProductLine(user_id=colleague.user_id,product_line_code=c.line)])
        await db.execute(update(RolePermission).where(RolePermission.role_id==role.id,RolePermission.module=='capa').values(permission_level=3))
        await db.execute(update(RolePermission).where(RolePermission.role_id==role.id,RolePermission.module=='fmea').values(permission_level=1))
        await db.commit()
        colleague_id=colleague.user_id
    nonce=uuid4().hex
    @c.app.post('/__t8_ui/complete')
    async def complete(request:Request):
        if request.headers.get('X-Acceptance-Nonce')!=nonce:raise HTTPException(404)
        claimed=await c.client.post('/api/agent/runtime/messages/claim',json={'limit':10},headers=token)
        assert claimed.status_code==200,claimed.text
        ack=await c.client.post('/api/agent/runtime/messages/ack',json={'batch_id':claimed.json()['batch_id'],'through_sequence':max(m['sequence'] for m in claimed.json()['messages'])},headers=token)
        assert ack.status_code==200,ack.text
        result=await c.client.post('/api/agent/runtime/finish',json={'status':'completed'},headers=token)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=result.status_code,content=result.json())
    @c.app.post('/__t8_ui/revoke-source')
    async def revoke_source(request:Request):
        if request.headers.get('X-Acceptance-Nonce')!=nonce:raise HTTPException(404)
        async with c.session() as db:
            await db.execute(update(RolePermission).where(RolePermission.role_id==role.id,RolePermission.module=='fmea').values(permission_level=0))
            await db.commit()
        return {'revoked':True}
    frontend=Path(__file__).resolve().parents[3]/'frontend'
    chromium=resolve_browser(frontend,os.environ)
    probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
    backend=str(c.client.base_url).rstrip('/')
    log=(tmp_path/'vite.log').open('wb');vite=browser=None
    try:
        vite=await asyncio.create_subprocess_exec('node',str(frontend/'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(port),'--strictPort',cwd=frontend,env=browser_environment(os.environ,{'BACKEND_URL':backend}),stdout=log,stderr=log)
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(300):
                if vite.returncode is not None:pytest.fail('Owned Vite exited')
                try:
                    if (await client.get(f'http://127.0.0.1:{port}',timeout=1)).status_code==200:break
                except httpx.HTTPError:pass
                await asyncio.sleep(.05)
            else:pytest.fail('Owned Vite did not start')
        env=browser_environment(os.environ,{'BACKEND_URL':backend,'AGENT_BACKEND_URL':backend,'AGENT_BROWSER_URL':f'http://127.0.0.1:{port}','AGENT_BROWSER_TENANT':c.slug,'AGENT_BROWSER_REPORT':str(c.report_id),'AGENT_BROWSER_TASK':str(c.task_id),'AGENT_HARNESS_NONCE':nonce,'AGENT_BROWSER_LOGIN':json.dumps({'username':'trial-executor','password':PASSWORD,'installation':str(c.r5_id),'model_b':model_b.json()['deployment_id'],'proposal':proposal,'checkpoint':checkpoint.json()['checkpoint_id']}),'OUTCOME_APPROVER_LOGIN':json.dumps({'username':'t8-colleague','password':PASSWORD,'user_id':str(colleague_id)}),'AGENT_BROWSER_ARTIFACTS':str(tmp_path/'playwright'),'OPENQMS_AGENT_BROWSER_EXECUTABLE':str(chromium)})
        browser=await asyncio.create_subprocess_exec('node',str(frontend/'node_modules/@playwright/test/cli.js'),'test','--config','playwright.agent.config.ts','r5-collaboration.spec.ts',cwd=frontend,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await asyncio.wait_for(browser.communicate(),180)
        (tmp_path/'browser.log').write_bytes(stdout+stderr)
        assert browser.returncode==0,(stdout+stderr).decode()
        assert b'1 passed' in stdout and b'skipped' not in stdout
        async with c.session() as db:
            messages=list(await db.scalars(select(AgentTaskMessage).where(AgentTaskMessage.task_id==c.task_id)))
            assert any(m.content=='T8 Enter stays A' for m in messages)
            bindings=list(await db.scalars(select(AgentTaskModelBinding)))
            assert any(str(b.deployment_id)==model_b.json()['deployment_id'] and b.task_id!=c.task_id for b in bindings)
            measure=await db.scalar(select(CapaD5Measure).where(CapaD5Measure.proposal_id==proposal))
            assert measure.final_text=='T8 同事确认最终措施' and measure.adopted_by==colleague_id
        assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]
        print('CHROMIUM_REAL: two roles, bound A / new B / Enter A / colleague adoption after finish; real HTTP; loopback only')
    finally:
        if browser and browser.returncode is None:browser.kill();await browser.wait()
        if vite and vite.returncode is None:
            vite.terminate()
            try:await asyncio.wait_for(vite.wait(),10)
            except asyncio.TimeoutError:vite.kill();await vite.wait()
        log.close()
        (tmp_path/'owned-processes.json').write_text(json.dumps({'vite_pid':vite.pid if vite else None,'vite_exit':vite.returncode if vite else None,'browser_pid':browser.pid if browser else None,'browser_exit':browser.returncode if browser else None}))
