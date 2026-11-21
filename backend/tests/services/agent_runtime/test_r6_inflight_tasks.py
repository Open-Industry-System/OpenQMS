"""Cutover never upgrades an immutable R5 run/profile or duplicates commands."""
from types import SimpleNamespace
from uuid import UUID
import pytest
from sqlalchemy import select,func
from tests.services.agent_runtime.test_r5_model_binding import r5_case,_managed_claim
from tests.e2e.d4_text_local_harness import d4_text_local_trial,owned_local_trial  # noqa:F401
from app.models.agent_task import AgentTask,AgentRun
from app.models.agent_d5_command import AgentD5Command
from app.models.agent_d5_basis import AgentD5BasisReceipt
from app.models.agent_model_deployment import AgentTaskModelBinding

pytestmark=[pytest.mark.requires_db,pytest.mark.ci_r5_native,pytest.mark.asyncio]


async def test_compatible_r5_run_keeps_profile_command_and_run_identity(r5_case,tmp_path):
    from tests.capa.r6_switch_support import owned_cli,cli
    c=r5_case
    await _managed_claim(c)
    headers={'Authorization':'Bearer '+c.token}
    inferred=await c.client.post('/api/agent/runtime/model/infer',json={},headers=headers)
    assert inferred.status_code==200,inferred.text  # local scripted witness, zero real model calls
    body={'command_key':'r5-before-switch','text':'immutable R5 proposal'}
    first=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=body,headers=headers)
    assert first.status_code==200,first.text
    async with c.session() as db:
        binding=await db.get(AgentTaskModelBinding,c.task_id)
        old_binding={column.name:getattr(binding,column.name) for column in binding.__table__.columns}
        run=await db.get(AgentRun,c.run_id)
        epoch=run.lease_epoch
        receipt_ids=list(await db.scalars(select(AgentD5BasisReceipt.receipt_id).where(AgentD5BasisReceipt.run_id==c.run_id)))
    fixture_case=SimpleNamespace(binding=c.binding,session=c.session,actor=lambda:SimpleNamespace(user_id=c.user_id))
    fixture=await owned_cli(fixture_case,tmp_path)
    code,closed=await cli(fixture,'close');assert code==0,closed
    blocked=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=body,headers=headers)
    assert blocked.status_code==503,blocked.text
    code,switched=await cli(fixture,'finish');assert code==0,switched
    replay=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=body,headers=headers)
    assert replay.status_code==200 and replay.json()==first.json(),replay.text
    async with c.session() as db:
        binding=await db.get(AgentTaskModelBinding,c.task_id)
        assert old_binding=={column.name:getattr(binding,column.name) for column in binding.__table__.columns}
        assert (await db.get(AgentRun,c.run_id)).lease_epoch==epoch
        assert receipt_ids==list(await db.scalars(select(AgentD5BasisReceipt.receipt_id).where(AgentD5BasisReceipt.run_id==c.run_id)))
        assert await db.scalar(select(func.count()).select_from(AgentD5Command).where(AgentD5Command.task_id==c.task_id))==1
    # A new command still revalidates the old exact source/proof contract. It
    # is permitted only while that original run remains actually compatible.
    continuation=await c.client.post('/api/agent/runtime/capa/d5/proposals',json=dict(body,command_key='r5-same-run-after'),headers=headers)
    assert continuation.status_code==200,continuation.text
    async with c.session() as db:
        assert set(await db.scalars(select(AgentRun.run_id).where(AgentRun.task_id==c.task_id)))=={c.run_id}


async def test_generation_disabled_keeps_pending_withdrawal_and_manual_work(r5_case,monkeypatch,tmp_path):
    from app.config import settings
    c=r5_case
    await _managed_claim(c)
    headers={'Authorization':'Bearer '+c.token}
    initial=await c.client.post('/api/agent/runtime/model/infer',json={},headers=headers)
    assert initial.status_code==200,initial.text
    saved=await c.client.post('/api/agent/runtime/capa/d5/proposals',json={'command_key':'before-disable','text':'pending survives generation disable'},headers=headers)
    assert saved.status_code==200,saved.text
    from tests.capa.r6_switch_support import owned_cli,cli
    fixture=await owned_cli(SimpleNamespace(binding=c.binding,session=c.session,actor=lambda:SimpleNamespace(user_id=c.user_id)),tmp_path)
    assert (await cli(fixture,'close'))[0]==0
    assert (await cli(fixture,'finish'))[0]==0
    monkeypatch.setattr(settings,'R6_GENERATION_ENABLED',False,raising=False)
    denied=await c.client.post('/api/agent/runtime/model/infer',json={},headers=headers)
    assert denied.status_code==503,denied.text
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]
    withdrawn=await c.admin.post(f"/api/capa/{c.report_id}/d5-proposals/{saved.json()['proposal_id']}/withdraw",
        json={'operation_key':'disabled-withdraw','reason':'employee remains authorized'})
    assert withdrawn.status_code==200,withdrawn.text
    detail=await c.admin.get(f'/api/capa/{c.report_id}')
    assert detail.status_code==200 and detail.json()['entry_phase']=='switched',detail.text
    manual=await c.admin.put(f'/api/capa/{c.report_id}',json={'d5_correction':'safe manual fallback',
        'expected_material_version':detail.json()['material_version'],'expected_entry_epoch':detail.json()['entry_epoch']})
    assert manual.status_code==200,manual.text


async def test_incompatible_installation_invalidates_old_runtime_without_migrating_history(r5_case,tmp_path):
    from tests.capa.r6_switch_support import owned_cli,cli
    c=r5_case
    await _managed_claim(c)
    headers={'Authorization':'Bearer '+c.token}
    assert (await c.client.post('/api/agent/runtime/model/infer',json={},headers=headers)).status_code==200
    first=await c.client.post('/api/agent/runtime/capa/d5/proposals',json={'command_key':'original','text':'history remains original'},headers=headers)
    assert first.status_code==200,first.text
    fixture=await owned_cli(SimpleNamespace(binding=c.binding,session=c.session,actor=lambda:SimpleNamespace(user_id=c.user_id)),tmp_path)
    assert (await cli(fixture,'close'))[0]==0
    assert (await cli(fixture,'finish'))[0]==0
    disabled=await c.admin.patch(f'/api/admin/agent-plugins/{c.r5_id}',json={'enabled':False})
    assert disabled.status_code==200,disabled.text
    before=len(c.witness.a.bodies)
    for path,body in [('/api/agent/runtime/model/infer',{}),('/api/agent/runtime/capa/d5/proposals',{'command_key':'new-forbidden','text':'never migrated'})]:
        response=await c.client.post(path,json=body,headers=headers)
        assert response.status_code==401 and response.json()=={'detail':'Invalid run credential'},response.text
    assert len(c.witness.a.bodies)==before
    history=await c.admin.get(f'/api/capa/{c.report_id}/d5-proposals')
    assert history.status_code==200 and any(item['proposal_id']==first.json()['proposal_id'] for item in history.json()['items']),history.text
    async with c.session() as db:
        assert set(await db.scalars(select(AgentRun.run_id).where(AgentRun.task_id==c.task_id)))=={c.run_id}
        assert await db.scalar(select(func.count()).select_from(AgentD5Command).where(AgentD5Command.task_id==c.task_id))==1


from tests.services.agent_runtime.test_r6_d4_candidates import d4_case  # noqa:F401,E402


async def test_switched_normal_current_d4_confirmation_and_employee_verification_proof(d4_case,tmp_path):
    from app.api.capa_r6 import router
    from tests.capa.r6_switch_support import owned_cli,cli
    from tests.capa.test_r6_d4_confirm import _generate_and_confirm,_verify
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    c=d4_case;c.app.include_router(router)
    fixture=await owned_cli(SimpleNamespace(binding=c.binding,session=c.session,actor=lambda:SimpleNamespace(user_id=c.user_id)),tmp_path)
    assert (await cli(fixture,'close'))[0]==0
    assert (await cli(fixture,'finish'))[0]==0
    await _generate_and_confirm(c,'switched-current-d4','现场确认的当前根因')
    verified=await _verify(c,'现场确认的当前根因')
    changed=await c.client.patch(f"/api/capa/{c.report_id}/root-cause-verifications/{verified.json()['verification_id']}",
        json={'method':'measurement','result':'补充现场记录','conclusion':'passed'})
    assert changed.status_code==200,changed.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id==c.report_id))==1
        assert await db.scalar(select(func.count()).select_from(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.report_id==c.report_id))==1


async def test_writer_controls_drain_before_business_locks_then_continue_switched(r5_case,tmp_path):
    from fastapi import HTTPException
    from sqlalchemy import event
    from tests.capa.r6_switch_support import owned_cli,cli
    from tests.services.agent_runtime.test_task_controls import scope,request
    from app.services.agent_runtime.task_controls import control_task
    c=r5_case
    await _managed_claim(c)
    async with c.session() as db:
        original=await db.get(AgentTaskModelBinding,c.task_id)
        pinned={column.name:getattr(original,column.name) for column in original.__table__.columns}
        stopped=await control_task(db,await scope(db,c),c.task_id,
            request(action='pause',run_id=c.run_id,expected_epoch=1,idempotency_key='writer-pause'))
        assert stopped.lease_epoch==2
    fixture=await owned_cli(SimpleNamespace(binding=c.binding,session=c.session,actor=lambda:SimpleNamespace(user_id=c.user_id)),tmp_path)
    assert (await cli(fixture,'close'))[0]==0
    async with c.session() as db:
        statements=[]
        def observe(_conn,_cursor,statement,_parameters,_context,_many):
            statements.append(statement.upper())
        engine=db.bind.sync_engine
        event.listen(engine,'before_cursor_execute',observe)
        try:
            with pytest.raises(HTTPException) as denied:
                await control_task(db,await scope(db,c),c.task_id,
                    request(action='resume',run_id=c.run_id,expected_epoch=2,idempotency_key='writer-resume'))
            assert denied.value.status_code==503
            assert not any('FOR UPDATE' in sql for sql in statements)
            assert any('AGENT_TASK_MODEL_BINDINGS' in sql or 'AGENT_TASK_GRANTS' in sql for sql in statements)
        finally:
            event.remove(engine,'before_cursor_execute',observe)
            await db.rollback()
    assert (await cli(fixture,'finish'))[0]==0
    async with c.session() as db:
        # Match the actual HTTP dependency: independently approved local pilot
        # is server session context, never a client-provided bypass.
        await c.session_info(db)
        resumed=await control_task(db,await scope(db,c),c.task_id,
            request(action='resume',run_id=c.run_id,expected_epoch=2,idempotency_key='writer-resume'))
        assert resumed.lease_epoch==3
        current=await db.get(AgentTaskModelBinding,c.task_id)
        assert pinned=={column.name:getattr(current,column.name) for column in current.__table__.columns}
