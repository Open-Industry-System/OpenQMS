"""Empty-root D4 uses an explicit deployment and independent input receipts."""
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, Grant


def test_only_explicit_d4_profile_can_propose_target_bound_candidates():
    capability = 'capa.d4.candidate.propose.v1'
    for profile in ('baseline', 'model_d5_proposal_v1', 'model_d5_proposal_r6_v1'):
        spec = get_capability(capability, profile=profile)
        assert spec is None or spec.approval_floor == ApprovalFloor.DENY
    spec = get_capability(capability, profile='model_d4_candidate_v1')
    assert spec is not None, 'empty-root candidate command has no approved profile'
    assert spec.target_required and spec.approval_floor == ApprovalFloor.DIRECT
    report, factory = UUID(int=1), UUID(int=2)
    grant = Grant(capability, frozenset({factory}), frozenset({report}), frozenset({'L'}))
    attempt = AccessAttempt(spec, {Module.CAPA: PermissionLevel.EDIT}, frozenset({factory}),
        frozenset({'L'}), grant, grant, factory, report, 'L', datetime.now(UTC),
        catalog_profile='model_d4_candidate_v1')
    assert authorize(attempt).allowed
    from dataclasses import replace
    assert not authorize(replace(attempt, task_grant=replace(grant, object_ids=None))).allowed


@pytest.mark.parametrize('capability', ['capa.d2.snapshot.v1', 'capa.d3.snapshot.v1'])
def test_empty_root_profile_has_independent_report_fact_reads(capability):
    spec = get_capability(capability, profile='model_d4_candidate_v1')
    assert spec is not None and spec.approval_floor == ApprovalFloor.DIRECT

import pytest_asyncio
from tests.services.agent_runtime.test_r5_model_binding import r5_case, _managed_claim
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial  # noqa: F401


@pytest_asyncio.fixture
async def d4_case(r5_case,request):
    from dataclasses import replace
    from uuid import uuid4
    from app.models.capa import CAPAEightD, CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    from sqlalchemy import delete
    c = r5_case
    async with c.session() as db:
        from app.models.fmea import FMEADocument
        doc=await db.get(FMEADocument,c.fmea_id)
        doc.graph_data={'nodes':[{'id':'cause-A','type':'FailureCause','name':'定位销磨损导致孔径超差'}], 'edges':[]}
        report = CAPAEightD(document_no='R6-EMPTY-'+uuid4().hex[:12], title='D4 empty root',
            status='D4_ROOT_CAUSE', d2_description='孔径测量超出上限', d3_interim='隔离该批并复测',
            factory_id=c.factory_id, product_line_code=c.line, created_by=c.user_id, fmea_ref_id=c.fmea_id)
        db.add(report)
        await db.flush()
        c.report_id=report.report_id
        c.source_scope=dict(c.source_scope,target_report_id=str(c.report_id))
        if getattr(request,'param',None)=='B':
            c.linked_A=c.fmea_id
            extra=FMEADocument(document_no='R6-B-'+uuid4().hex[:12],title='外部FMEA B',factory_id=c.factory_id,
                product_line_code=c.line,lock_version=0,graph_data={'nodes':[{'id':'cause-B','type':'FailureCause','name':'夹具松动导致孔径超差'}],'edges':[]})
            db.add(extra)
            await db.flush()
            c.fmea_id=extra.fmea_id
            c.source_scope=dict(c.source_scope,fmea_id=str(c.fmea_id),cause_node_id='cause-B')
        c.create_body=dict(c.create_body,report_id=str(c.report_id),derived_source_scope=c.source_scope)
        await db.commit()
    required = ['capa.d2.snapshot.v1', 'capa.d3.snapshot.v1',
                'capa.d4.candidate.propose.v1', 'capa.d4.fmea_input.masked.v1']
    registered = await c.admin.post('/api/admin/agent-plugins', json=dict(
        plugin_key='openqms.controlled-d5-model', plugin_version='1.0.4',
        manifest=dict(protocol_versions=['1'], required_capabilities=required, optional_capabilities=[])))
    assert registered.status_code == 201, registered.text
    c.r5_id = UUID(registered.json()['plugin']['installation_id'])
    c.pilot = replace(c.pilot, installation_id=c.r5_id, plugin_version='1.0.4', profile='model_d4_candidate_v1')
    c.app.state.r5_controlled_pilot = c.pilot
    for cap in required:
        body = dict(capability_id=cap, factory_ids=[str(c.factory_id)], object_ids=[str(c.report_id)],
            product_line_codes=[c.line], expires_at=c.pilot.expires_at.isoformat(), enabled=True)
        if cap == required[-1]:
            body['derived_source_scope'] = c.source_scope
        granted = await c.admin.post(f'/api/admin/agent-plugins/{c.r5_id}/grants', json=body)
        assert granted.status_code == 201, granted.text
    enabled = await c.admin.patch(f'/api/admin/agent-plugins/{c.r5_id}', json={'enabled': True})
    assert enabled.status_code == 200, enabled.text
    model = await c.admin.post('/api/agent/models', json=dict(c.model_body, name='D4 '+uuid4().hex))
    assert model.status_code == 201, model.text
    c.model_id = UUID(model.json()['deployment_id'])
    c.create_body = dict(c.create_body, installation_id=str(c.r5_id), model_deployment_id=str(c.model_id),
                        initial_text='analyze_d4_candidate_v1')
    return c


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_empty_root_without_proof_reads_delivers_and_saves_complete_sources(d4_case):
    from sqlalchemy import select, func
    from app.models.capa import CAPAEightD, CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof,CapaD4RootCauseRevision
    from app.models.capa_r6 import CapaD4Candidate, CapaD4CandidateSource, AgentD4CandidateCommand
    c = d4_case
    await _managed_claim(c)
    headers = {'Authorization': 'Bearer '+c.token}
    response = await c.client.post('/api/agent/runtime/model/infer', json={'operation': 'propose_d4'}, headers=headers)
    assert response.status_code == 200, response.text
    saved = await c.client.post('/api/agent/runtime/capa/d4/candidates', json=dict(
        command_key='empty-root', text='待验证：定位销磨损', supporting=['FMEA明确记录磨损可能导致孔径超差'],
        opposing=[], missing_information=['现场验证']), headers=headers)
    assert saved.status_code == 200, saved.text
    replay = await c.client.post('/api/agent/runtime/capa/d4/candidates', json=dict(
        command_key='empty-root', text='待验证：定位销磨损', supporting=['FMEA明确记录磨损可能导致孔径超差'],
        opposing=[], missing_information=['现场验证']), headers=headers)
    assert replay.status_code == 200 and replay.json() == saved.json(), replay.text
    async with c.session() as db:
        candidate = await db.scalar(select(CapaD4Candidate))
        assert candidate.state == 'pending'
        assert await db.scalar(select(func.count()).select_from(CapaD4CandidateSource)) == 3
        assert await db.scalar(select(func.count()).select_from(AgentD4CandidateCommand)) == 1
        assert (await db.get(CAPAEightD, c.report_id)).d4_root_cause is None
        assert await db.scalar(select(func.count()).select_from(CapaD4RootCauseRevision).where(CapaD4RootCauseRevision.report_id==c.report_id))==0
        assert await db.scalar(select(func.count()).select_from(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id==c.report_id)) == 0
        assert await db.scalar(select(func.count()).select_from(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.report_id==c.report_id)) == 0
    assert len(c.witness.a.bodies) == 1 and c.witness.b.bodies == []


def test_empty_root_inputs_have_independent_durable_delivery_and_command_links():
    from app.database import TenantBase
    tables = TenantBase.metadata.tables
    expected = {'agent_d4_input_receipts', 'agent_d4_input_receipt_sources', 'agent_d4_command_inputs'}
    assert expected <= set(tables), 'D4 must not fabricate a Root/P to persist actual input delivery'
    receipt = tables['agent_d4_input_receipts']
    assert not {'proof_id', 'revision_id'} & set(receipt.c.keys())
    assert {'report_id', 'task_id', 'run_id', 'lease_epoch', 'tenant_generation',
            'executor_id', 'installation_id', 'deployment_id', 'deployment_config_hmac',
            'source_count', 'input_versions', 'receipt_hmac'} <= set(receipt.c.keys())


def test_empty_root_fmea_input_is_separate_from_formal_root_text():
    name = 'capa.d4.fmea_input.masked.v1'
    for profile in ('baseline', 'model_d5_proposal_v1', 'model_d5_proposal_r6_v1', 'local_d4_root_cause_text_v1'):
        spec = get_capability(name, profile=profile)
        assert spec is None or spec.approval_floor == ApprovalFloor.DENY
    spec = get_capability(name, profile='model_d4_candidate_v1')
    assert spec is not None and spec.approval_floor == ApprovalFloor.DIRECT
    assert get_capability('capa.d4.root_cause_candidate.masked.v1', profile='model_d4_candidate_v1') is None
    from app.services.agent.permissions.derived_sources import DerivedSourceScope
    from dataclasses import replace
    report, factory = UUID(int=1), UUID(int=2)
    source = DerivedSourceScope(report, name, Module.FMEA, 'fmea.failure_cause.reference.v1', UUID(int=3), 'A')
    grant = Grant(name, frozenset({factory}), frozenset({report}), frozenset({'L'}))
    attempt = AccessAttempt(spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}),
        frozenset({'L'}), grant, grant, factory, report, 'L', datetime.now(UTC),
        catalog_profile='model_d4_candidate_v1', current_source=source,
        plugin_source_scope=source, task_source_scope=source)
    assert authorize(attempt).allowed
    assert not authorize(replace(attempt, task_source_scope=None)).allowed
    assert not authorize(replace(attempt, plugin_source_scope=replace(source, cause_node_id='B'))).allowed
    assert not authorize(replace(attempt, plugin_grant=replace(grant, object_ids=None))).allowed


def test_d4_command_schema_is_bounded_and_has_no_caller_provenance():
    import importlib.util
    assert importlib.util.find_spec('app.schemas.agent_d4_candidate') is not None, 'D4 command schema missing'
    from app.schemas.agent_d4_candidate import D4CandidateCommand
    from pydantic import ValidationError
    assert D4CandidateCommand(command_key='safe', text='Hypothesis').operation == 'save'
    for data in ({'report_id': UUID(int=1)}, {'source_ids': [UUID(int=2)]},
                 {'text': ' '}, {'supporting': ['x'*2001]}, {'operation': 'replace'},
                 {'operation': 'save', 'predecessor_id': UUID(int=1)}):
        with pytest.raises(ValidationError):
            D4CandidateCommand(**(dict(command_key='safe', text='Hypothesis') | data))


async def deliver(c):
    await _managed_claim(c)
    response = await c.client.post('/api/agent/runtime/model/infer', json={'operation':'propose_d4'}, headers={'Authorization':'Bearer '+c.token})
    assert response.status_code == 200, response.text


async def save(c, key='first', **changes):
    return await c.client.post('/api/agent/runtime/capa/d4/candidates', json=dict(
        command_key=key, text='待验证：定位销磨损', **changes), headers={'Authorization':'Bearer '+c.token})


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_candidate_requires_actual_delivery_and_rejects_wrong_target_and_old_text(d4_case):
    c=d4_case
    await _managed_claim(c)
    assert (await save(c)).status_code == 403
    rejected=await save(c, report_id=str(UUID(int=99)))
    assert rejected.status_code == 422
    old=await c.client.get('/api/agent/runtime/capa/d4/root-cause-text', headers={'Authorization':'Bearer '+c.token})
    assert old.status_code in {403,404}
    assert c.witness.a.bodies == c.witness.b.bodies == []


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['source_acl','lease','d2_aba','fmea_aba','deployment','free_chat'])
async def test_delivered_candidate_inputs_fence_later_mutations(d4_case,change):
    from sqlalchemy import update,select,func
    from app.models.agent_task import AgentRun,AgentTaskMessage
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_model_deployment import AgentModelDeployment
    from app.models.capa import CAPAEightD
    from app.models.capa_r6 import AgentD4CandidateCommand
    from app.models.fmea import FMEADocument
    from app.services.capa_d4_material import snapshot_report_input
    from datetime import timedelta
    c=d4_case
    await deliver(c)
    async with c.session() as db:
        if change=='source_acl':
            await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id==c.r5_id,
                AgentPluginGrant.capability_id=='capa.d4.fmea_input.masked.v1').values(enabled=False))
        elif change=='lease':
            await db.execute(update(AgentRun).where(AgentRun.run_id==c.run_id).values(lease_expires_at=datetime.now(UTC)-timedelta(seconds=1)))
        elif change=='d2_aba':
            report=await db.get(CAPAEightD,c.report_id)
            original=report.d2_description
            for body in ('changed',original):
                report.d2_description=body
                await snapshot_report_input(db,report,'d2')
        elif change=='fmea_aba':
            doc=await db.get(FMEADocument,c.fmea_id)
            original=doc.graph_data
            doc.graph_data=dict(original, changed=True)
            await db.flush()
            doc.graph_data=original
        elif change=='deployment':
            await db.execute(update(AgentModelDeployment).where(AgentModelDeployment.deployment_id==c.model_id).values(enabled=False))
        else:
            db.add(AgentTaskMessage(task_id=c.task_id,sequence=2,author_id=c.user_id,idempotency_key='external',
                state='queued',content='Unclassified external process secrets'))
        await db.commit()
    assert (await save(c)).status_code in {401,403,409}
    retry=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'propose_d4'},headers={'Authorization':'Bearer '+c.token})
    assert retry.status_code in {401,403,409}
    assert len(c.witness.a.bodies)==1
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD4CandidateCommand))==0


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_same_key_freezes_original_receipts_after_later_delivery(d4_case):
    from sqlalchemy import select,func
    from app.models.capa_r6 import AgentD4CommandInput,AgentD4InputReceipt
    c=d4_case
    await deliver(c)
    first=await save(c)
    assert first.status_code==200,first.text
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'propose_d4'},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==200,response.text
    replay=await save(c)
    assert replay.status_code==200 and replay.json()==first.json(),replay.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD4InputReceipt))==2
        assert await db.scalar(select(func.count()).select_from(AgentD4CommandInput))==1


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_active_checkpoint_captures_candidate_command_watermark(d4_case):
    from sqlalchemy import select
    from app.models.capa_r6 import AgentD4CandidateCheckpointPosition
    c=d4_case
    await deliver(c)
    assert (await save(c)).status_code==200
    cp=await c.client.post('/api/agent/runtime/capa/d4/checkpoints',json={},headers={'Authorization':'Bearer '+c.token})
    assert cp.status_code==200,cp.text
    assert cp.json()['command_watermark']==1
    async with c.session() as db:
        position=await db.get(AgentD4CandidateCheckpointPosition,UUID(cp.json()['checkpoint_id']))
        assert position is not None and position.watermark==1


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_pause_restart_preserves_candidates_and_recaptures_inputs(d4_case):
    from sqlalchemy import select,func
    from app.models.capa_r6 import CapaD4Candidate,AgentD4InputReceipt
    c=d4_case
    await deliver(c)
    batch=await c.client.post('/api/agent/runtime/messages/claim',json={'limit':20},headers={'Authorization':'Bearer '+c.token})
    assert batch.status_code==200,batch.text
    ack=await c.client.post('/api/agent/runtime/messages/ack',json=dict(batch_id=batch.json()['batch_id'],through_sequence=1),headers={'Authorization':'Bearer '+c.token})
    assert ack.status_code==200,ack.text
    first=await save(c)
    assert first.status_code==200,first.text
    cp=await c.client.post('/api/agent/runtime/capa/d4/checkpoints',json={},headers={'Authorization':'Bearer '+c.token})
    assert cp.status_code==200,cp.text
    oldtoken,oldrun=c.token,c.run_id
    pause=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(
        action='pause',run_id=str(c.run_id),expected_epoch=c.epoch,idempotency_key='pause'))
    assert pause.status_code==200,pause.text
    restart=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(
        action='restart',run_id=str(c.run_id),expected_epoch=pause.json()['lease_epoch'],
        checkpoint_id=cp.json()['checkpoint_id'],idempotency_key='restart'))
    assert restart.status_code==200,restart.text
    await _managed_claim(c)
    assert c.run_id!=oldrun
    denied=await c.client.post('/api/agent/runtime/capa/d4/candidates',json=dict(command_key='stale',text='stale'),headers={'Authorization':'Bearer '+oldtoken})
    assert denied.status_code in {401,403}
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'propose_d4'},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==200,response.text
    new_cp=await c.client.post('/api/agent/runtime/capa/d4/checkpoints',json={},headers={'Authorization':'Bearer '+c.token})
    assert new_cp.status_code==200 and new_cp.json()['checkpoint_id']!=cp.json()['checkpoint_id'],new_cp.text
    assert new_cp.json()['run_id']==str(c.run_id) and new_cp.json()['command_watermark']==1
    pause_again=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='pause',run_id=str(c.run_id),expected_epoch=c.epoch,idempotency_key='pause-new'))
    assert pause_again.status_code==200,pause_again.text
    wrong_run_cp=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='restart',run_id=str(c.run_id),
        expected_epoch=pause_again.json()['lease_epoch'],checkpoint_id=cp.json()['checkpoint_id'],idempotency_key='wrong-cp-run'))
    assert wrong_run_cp.status_code in {403,409},wrong_run_cp.text
    async with c.session() as db:
        assert (await db.get(CapaD4Candidate,UUID(first.json()['candidate_id']))).state=='pending'
        assert await db.scalar(select(func.count()).select_from(AgentD4InputReceipt))==2


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_receipt_history_remains_offline_but_requires_all_current_source_permissions(d4_case,monkeypatch):
    from sqlalchemy import update
    from app.models.role import RolePermission
    from app.models.agent_model_deployment import AgentModelDeployment
    from app.services.agent_runtime import model_egress
    c=d4_case
    await deliver(c)
    async with c.session() as db:
        await db.execute(update(AgentModelDeployment).where(AgentModelDeployment.deployment_id==c.model_id).values(enabled=False))
        await db.commit()
    monkeypatch.setattr(model_egress,'_addresses',lambda _: (_ for _ in ()).throw(AssertionError('offline history must not resolve DNS')))
    view=await c.client.get(f'/api/agent/tasks/{c.task_id}')
    assert view.status_code==200,view.text
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    hidden=await c.client.get(f'/api/agent/tasks/{c.task_id}')
    assert hidden.status_code in {403,404},hidden.text


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('sdk',[False,True])
@pytest.mark.parametrize('protocol',['chat_completions','responses'])
async def test_real_managed_process_reads_opaque_ack_then_saves_candidate(d4_case,sdk,protocol):
    import asyncio,json
    from pathlib import Path
    from dataclasses import replace
    import sys
    from sqlalchemy import select,func
    from app.models.capa_r6 import CapaD4Candidate,AgentD4InputReceipt
    from app.services.agent_runtime.r5_executor import ExecutorApproval
    from tests.e2e.test_r5_model_agent import scripted_model,call
    c=d4_case
    artifact=Path(__file__).parents[3]/('examples/d4_candidate_agent.py' if sdk else 'examples/d5_proposal_agent.py')
    assert artifact.is_file(), 'Approved single-artifact D4 SDK bundle missing'
    c.pilot=replace(c.pilot,approval=ExecutorApproval.approve(artifact,sys.executable))
    c.app.state.r5_controlled_pilot=c.pilot
    c.model_body=dict(c.model_body,api_protocol=protocol)
    model=await c.admin.post('/api/agent/models',json=dict(c.model_body,name='D4 actual',version='actual'))
    assert model.status_code==201,model.text
    c.create_body['model_deployment_id']=model.json()['deployment_id']
    turns=[call('read_inputs'),call('save_candidate',dict(text='待验证定位销磨损',supporting=['D2与FMEA吻合'],opposing=[],missing_information=['现场验证']),'save'),{'content':'done'}]
    if protocol=='responses': scripted_responses(c,turns)
    else: scripted_model(c,turns)
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201 and created.json()['status']=='ready',created.text
    response=await c.client.post(f"/api/agent/tasks/{created.json()['task_id']}/launch",timeout=130)
    assert response.status_code==200,response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD4Candidate))==1
        assert await db.scalar(select(func.count()).select_from(AgentD4InputReceipt))==1
    assert len(c.witness.a.bodies)==3 and c.witness.b.bodies==[]
    frames=c.witness.a.bodies
    # The child echoes only the acknowledgement; protected inputs are inserted
    # by the platform into model messages and never emitted as a tool result.
    if protocol=='responses':
        assert any(m.get('type')=='function_call_output' and json.loads(m['output'])=={'status':'prepared'} for m in frames[1]['input'])
        assert c.witness.a.frames[0][0] in frames[1]['input']
    else:
        assert any(m.get('role')=='tool' and json.loads(m['content'])=={'status':'prepared'} for m in frames[1]['messages'])
    assert '孔径测量超出上限' in json.dumps(frames[1],ensure_ascii=False)


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_checkpoint_withdraws_only_later_pending_items_and_retains_reason(d4_case):
    from sqlalchemy import select,update
    from app.models.capa_r6 import CapaD4Candidate
    from app.database import TenantBase
    c=d4_case
    await deliver(c)
    before=await save(c,'before')
    assert before.status_code==200,before.text
    cp=await c.client.post('/api/agent/runtime/capa/d4/checkpoints',json={},headers={'Authorization':'Bearer '+c.token})
    assert cp.status_code==200,cp.text
    later=await save(c,'later',operation='alternative')
    adopted=await save(c,'adopted',operation='alternative')
    assert later.status_code==adopted.status_code==200
    async with c.session() as db:
        await db.execute(update(CapaD4Candidate).where(CapaD4Candidate.candidate_id==UUID(adopted.json()['candidate_id'])).values(state='adopted',version=2))
        await db.commit()
    response=await c.client.post(f"/api/agent/tasks/{c.task_id}/d4-checkpoints/{cp.json()['checkpoint_id']}/candidates/withdraw",json=dict(
        candidate_ids=[str(UUID(int=999)),before.json()['candidate_id'],later.json()['candidate_id'],adopted.json()['candidate_id']],
        operation_key='withdraw-batch',reason='员工要求重新分析'))
    assert response.status_code==200,response.text
    outcomes={item['candidate_id']:item['outcome'] for item in response.json()['items']}
    assert outcomes[str(UUID(int=999))]=='unavailable'
    assert outcomes[later.json()['candidate_id']]=='withdrawn'
    assert outcomes[adopted.json()['candidate_id']]=='adopted'
    assert outcomes[before.json()['candidate_id']]=='unavailable'
    conflict=await c.client.post(f"/api/agent/tasks/{c.task_id}/d4-checkpoints/{cp.json()['checkpoint_id']}/candidates/withdraw",json=dict(
        candidate_ids=[later.json()['candidate_id']],operation_key='withdraw-batch',reason='different reason'))
    assert conflict.status_code==200 and conflict.json()['items'][0]['outcome']=='conflict',conflict.text
    table=TenantBase.metadata.tables['capa_d4_candidate_withdrawals']
    async with c.session() as db:
        assert await db.scalar(select(table.c.reason))=='员工要求重新分析'
        assert (await db.get(CapaD4Candidate,UUID(before.json()['candidate_id']))).state=='pending'
    from app.services.agent_runtime import d4_candidate_checkpoints
    from app.models.capa_r6 import CapaR6StaffReceipt
    from types import SimpleNamespace
    assert hasattr(d4_candidate_checkpoints,'read_withdrawal'), 'Restricted reasons need a complete-source employee reader'
    async with c.session() as db:
        receipt_id=await db.scalar(select(CapaR6StaffReceipt.receipt_id).where(CapaR6StaffReceipt.candidate_id==UUID(later.json()['candidate_id'])))
        detail=await d4_candidate_checkpoints.read_withdrawal(db,SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)),receipt_id)
        assert detail['reason']=='员工要求重新分析' and detail['actor_id']==c.user_id


    from app.models.role import RolePermission
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    async with c.session() as db:
        with pytest.raises(PermissionError):
            await d4_candidate_checkpoints.read_withdrawal(db,SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)),receipt_id)


def test_managed_launch_extends_only_the_new_d4_profile():
    from app.services.agent_runtime import r5_executor
    assert hasattr(r5_executor,'managed_launch_payload'), 'D4 managed claim metadata has no typed public envelope'
    from types import SimpleNamespace
    metadata=SimpleNamespace(run_id=UUID(int=1),task_id=UUID(int=2),lease_epoch=3,
        lease_expires_at=datetime.now(UTC),accepted_message_seq=4,has_resume_checkpoint=False,token='opaque')
    row=SimpleNamespace(deployment_id=UUID(int=5),executor_pins={'profile':'model_d4_candidate_v1'})
    payload=r5_executor.managed_launch_payload(row,metadata,platform_origin='http://127.0.0.1:1',tenant_slug='tenant')
    assert payload['protocol']=='r6.d4.launch.v1' and payload['run_id']==str(metadata.run_id)
    row.executor_pins={}
    old=r5_executor.managed_launch_payload(row,metadata,platform_origin='http://127.0.0.1:1',tenant_slug='tenant')
    assert old==dict(api_origin='http://127.0.0.1:1',token='opaque',task_id=str(metadata.task_id),deployment_id=str(row.deployment_id),tenant_slug='tenant')


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_prepared_context_cannot_drift_from_its_source_versions(d4_case):
    from dataclasses import replace
    from app.services import capa_d4_candidates as candidates
    from app.services.agent_runtime import runtime_access
    c=d4_case
    await _managed_claim(c)
    async with c.session() as db:
        await c.session_info(db)
        identity=await runtime_access.verify_runtime_identity(db,c.token,c.binding)
        snapshot=await candidates.build_context(db,identity)
        changed=replace(snapshot,context=dict(snapshot.context,d2='unclassified external fact'))
        with pytest.raises(PermissionError):
            await candidates.validate_snapshot(db,identity,changed)
        await db.rollback()


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_workflow_response_after_round_expiry_is_not_disclosed(d4_case,monkeypatch):
    import time
    from app.services.agent_runtime import runtime_access,model_workflow
    from app.services.agent import provider_adapter
    c=d4_case
    await _managed_claim(c)
    async with c.session() as db:
        await c.session_info(db)
        identity=await runtime_access.verify_runtime_identity(db,c.token,c.binding)
        model_workflow.begin_round(identity)
        key=model_workflow._key(identity)
    original=provider_adapter.chat_with_tools
    async def expired(*args,**kwargs):
        result=await original(*args,**kwargs)
        model_workflow._rounds[key].deadline=time.monotonic()-1
        return result
    monkeypatch.setattr(provider_adapter,'chat_with_tools',expired)
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'workflow','turn':0},headers={'Authorization':'Bearer '+c.token})
    assert response.status_code==403,response.text


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_task_list_filters_delivered_inputs_after_source_revocation(d4_case):
    from sqlalchemy import update
    from app.models.role import RolePermission
    c=d4_case
    await deliver(c)
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    response=await c.client.get('/api/agent/tasks')
    assert response.status_code==200,response.text
    assert response.json()['items']==[] and response.json()['total']==0


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('d4_case',['B'],indirect=True)
async def test_explicit_independent_B_is_delivered_and_retained_with_report_inputs(d4_case):
    from sqlalchemy import select
    from app.models.capa_r6 import CapaD4CandidateSource,CapaR6SourceOrigin
    from app.models.capa import CAPAEightD
    c=d4_case
    await deliver(c)
    result=await save(c,'B')
    assert result.status_code==200,result.text
    async with c.session() as db:
        sources=list(await db.scalars(select(CapaR6SourceOrigin).join(CapaD4CandidateSource,
            CapaD4CandidateSource.source_id==CapaR6SourceOrigin.source_id)))
        assert len(sources)==3
        assert {s.projection_id for s in sources}=={'capa.d2.snapshot.v1','capa.d3.snapshot.v1','fmea.failure_cause.reference.v1'}
        external=[s for s in sources if s.kind=='fmea_projection']
        assert len(external)==1 and external[0].fmea_id==c.fmea_id and external[0].node_id=='cause-B'
        assert (await db.get(CAPAEightD,c.report_id)).fmea_ref_id==c.linked_A!=c.fmea_id


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_explicit_accepted_correction_replaces_atomically_for_a_real_multi_message_batch(d4_case):
    import json
    from app.models.capa_r6 import CapaD4Candidate
    c=d4_case
    await deliver(c)
    first=await save(c)
    assert first.status_code==200,first.text
    message=await c.client.post(f'/api/agent/tasks/{c.task_id}/messages',json=dict(
        idempotency_key='correction',content=json.dumps(dict(intent='replace_d4',predecessor_id=first.json()['candidate_id']))))
    assert message.status_code==202,message.text
    batch=await c.client.post('/api/agent/runtime/messages/claim',json={'limit':20},headers={'Authorization':'Bearer '+c.token})
    assert batch.status_code==200 and len(batch.json()['messages'])==2,batch.text
    ack=await c.client.post('/api/agent/runtime/messages/ack',json=dict(batch_id=batch.json()['batch_id'],through_sequence=2),headers={'Authorization':'Bearer '+c.token})
    assert ack.status_code==200,ack.text
    from sqlalchemy import event
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().lower().startswith('select'):
            statements.append(statement.lower())
    event.listen(c.engine.sync_engine,'before_cursor_execute',capture)
    try:
        replacement=await save(c,'replace',operation='replace',predecessor_id=first.json()['candidate_id'],
            correction_message_id=message.json()['message_id'])
    finally:
        event.remove(c.engine.sync_engine,'before_cursor_execute',capture)
    assert not any(any(column in statement for column in ('capa_d4_candidates.original_text','capa_d4_candidates.supporting','capa_d4_candidates.opposing')) for statement in statements)

    assert replacement.status_code==200,replacement.text
    async with c.session() as db:
        assert (await db.get(CapaD4Candidate,UUID(first.json()['candidate_id']))).state=='superseded'
        assert (await db.get(CapaD4Candidate,UUID(replacement.json()['candidate_id']))).state=='pending'


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('field',['task','run','epoch','deployment','incomplete'])
async def test_managed_launch_pin_mismatch_fails_before_model_or_candidate(d4_case,field,monkeypatch):
    c=d4_case
    await _managed_claim(c)
    headers={'Authorization':'Bearer '+c.token,'X-OpenQMS-Task':str(c.task_id),'X-OpenQMS-Run':str(c.run_id),
        'X-OpenQMS-Lease':str(c.epoch),'X-OpenQMS-Deployment':str(c.model_id)}
    key={'task':'X-OpenQMS-Task','run':'X-OpenQMS-Run','epoch':'X-OpenQMS-Lease','deployment':'X-OpenQMS-Deployment','incomplete':'X-OpenQMS-Run'}[field]
    if field=='incomplete': headers.pop(key)
    else: headers[key]='99' if field=='epoch' else str(UUID(int=99))
    from app.services.agent_runtime import runtime_access
    checks=[]
    original=runtime_access.authorize_task
    async def source_check(*args,**kwargs):
        checks.append(True)
        return await original(*args,**kwargs)
    monkeypatch.setattr(runtime_access,'authorize_task',source_check)
    response=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'propose_d4'},headers=headers)
    assert response.status_code in {401,403},response.text
    assert c.witness.a.bodies==c.witness.b.bodies==[]
    assert checks==[], "bad managed pins must be rejected before source authority reads node bodies"


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_checkpoint_history_exposes_only_authorized_positions_and_item_metadata(d4_case):
    c=d4_case
    await deliver(c)
    first=await save(c,'first')
    cp=await c.client.post('/api/agent/runtime/capa/d4/checkpoints',json={},headers={'Authorization':'Bearer '+c.token})
    assert cp.status_code==200,cp.text
    later=await save(c,'later',operation='alternative')
    assert later.status_code==200,later.text
    history=await c.client.get(f'/api/agent/tasks/{c.task_id}/d4-checkpoints')
    assert history.status_code==200,history.text
    assert history.json()['items'][0]['checkpoint_id']==cp.json()['checkpoint_id']
    assert history.json()['items'][0]['command_watermark']==1
    items=await c.client.get(f"/api/agent/tasks/{c.task_id}/d4-checkpoints/{cp.json()['checkpoint_id']}/candidates")
    assert items.status_code==200,items.text
    assert items.json()['items']==[dict(candidate_id=later.json()['candidate_id'],state='pending',sequence=2)]
    assert '待验证' not in history.text+items.text


def scripted_responses(c,turns):
    import json
    from http.server import BaseHTTPRequestHandler
    c.witness.a.frames=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.bodies.append(body)
            index=len(self.server.bodies)-1
            message=turns[min(index,len(turns)-1)]
            items=[dict(type='reasoning',id=f'rs_{index}',summary=[],encrypted_content=f'D4_PRIVATE_REASONING_{index}')]
            if message.get('content') is not None:
                items.append(dict(type='message',id=f'msg_{index}',role='assistant',status='completed',phase='final_answer',
                    content=[dict(type='output_text',text=message['content'],annotations=[])]))
            for call in message.get('tool_calls',[]):
                items.append(dict(type='function_call',id=f'fc_{index}',call_id=call['id'],name=call['function']['name'],
                    arguments=call['function']['arguments'],status='completed'))
            self.server.frames.append(items)
            response=json.dumps(dict(id=f'resp_{index}',object='response',created_at=1,status='completed',model='synthetic',
                output=items,parallel_tool_calls=True,tools=body['tools'],tool_choice='auto',error=None,incomplete_details=None)).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(response)))
            self.end_headers()
            self.wfile.write(response)
    c.witness.a.RequestHandlerClass=Handler


def strict_scripted_chat(c,turns):
    import json
    from http.server import BaseHTTPRequestHandler
    c.witness.a.invalid_protocol=False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.bodies.append(body)
            pending=set()
            for item in body['messages']:
                if item.get('role')=='tool':
                    if item.get('tool_call_id') not in pending:
                        self.server.invalid_protocol=True
                    pending.discard(item.get('tool_call_id'))
                elif pending:
                    self.server.invalid_protocol=True
                if item.get('role')=='assistant':
                    pending.update(call['id'] for call in item.get('tool_calls',[]))
            if pending or self.server.invalid_protocol:
                response=b'{"error":{"message":"Invalid tool protocol"}}'
                self.send_response(400)
            else:
                message=turns[min(len(self.server.bodies)-1,len(turns)-1)]
                response=json.dumps(dict(id='synthetic',object='chat.completion',created=1,model='synthetic',
                    choices=[dict(index=0,finish_reason='stop',message=dict(role='assistant',**message))])).encode()
                self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(response)))
            self.end_headers()
            self.wfile.write(response)
    c.witness.a.RequestHandlerClass=Handler


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_real_sdk_supplement_preserves_tool_protocol_and_original_checkpoint(d4_case,monkeypatch):
    import asyncio,json,sys
    from pathlib import Path
    from dataclasses import replace
    from app.services.agent_runtime.r5_executor import ExecutorApproval
    from tests.e2e.test_r5_model_agent import call
    from sqlalchemy import select
    from app.models.capa_r6 import AgentD4CandidateCheckpointPosition,CapaD4Candidate
    c=d4_case
    from app.services.agent_runtime import d4_candidate_checkpoints
    original_checkpoint=d4_candidate_checkpoints.save_checkpoint
    checkpoint_attempts=[]
    async def checkpoint(*args,**kwargs):
        try:
            value=await original_checkpoint(*args,**kwargs)
        except Exception as error:
            checkpoint_attempts.append(type(error).__name__)
            raise
        checkpoint_attempts.append('saved')
        return value
    monkeypatch.setattr(d4_candidate_checkpoints,'save_checkpoint',checkpoint)
    artifact=Path(__file__).parents[3]/'examples/d4_candidate_agent.py'
    c.pilot=replace(c.pilot,approval=ExecutorApproval.approve(artifact,sys.executable))
    c.app.state.r5_controlled_pilot=c.pilot
    model=await c.admin.post('/api/agent/models',json=dict(c.model_body,name='D4 supplement SDK',version='actual'))
    assert model.status_code==201,model.text
    c.create_body['model_deployment_id']=model.json()['deployment_id']
    strict_scripted_chat(c,[call('read_inputs'),call('request_supplement',{'question':'是否继续使用当前已授权事实？'},'question'),
        call('save_candidate',{'text':'待验证定位销磨损'},'save'),{'content':'done'}])
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201,created.text
    task=created.json()['task_id']
    launch=asyncio.create_task(c.client.post(f'/api/agent/tasks/{task}/launch',timeout=130))
    try:
        for _ in range(500):
            status=await c.client.get(f'/api/agent/tasks/{task}/workflow')
            if status.status_code==200 and status.json().get('question'): break
            if launch.done(): break
            await asyncio.sleep(.02)
        assert status.status_code==200 and status.json().get('checkpoint_id'),status.text
        checkpoint=UUID(status.json()['checkpoint_id'])
        message=await c.client.post(f'/api/agent/tasks/{task}/messages',json=dict(idempotency_key='continue',
            content=json.dumps({'intent':'continue_d4','additional_context':'none'})))
        assert message.status_code==202,message.text
        response=await launch
        invalid_protocol=bool(c.witness.a.invalid_protocol)
        assert not invalid_protocol, 'accepted user message preceded its pending tool result'
        assert checkpoint_attempts==['saved','saved']
        assert response.status_code==200,response.text
        async with c.session() as db:
            position=await db.get(AgentD4CandidateCheckpointPosition,checkpoint)
            assert position.watermark==0
            assert (await db.scalar(select(CapaD4Candidate))).state=='pending'
    finally:
        if not launch.done():
            launch.cancel()
            await asyncio.gather(launch,return_exceptions=True)


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_source_acl_revoked_during_real_report_lock_wait_rejects_before_fact_reads(d4_case):
    import asyncio
    from sqlalchemy import select,update,text,event,func
    from app.models.capa import CAPAEightD
    from app.models.role import RolePermission
    from app.models.capa_r6 import CapaD4Candidate,AgentD4InputReceipt
    c=d4_case
    await _managed_claim(c)
    after_revoke=[]
    revoked=False
    def capture(conn,cursor,statement,parameters,context,executemany):
        if revoked and statement.lstrip().lower().startswith('select'):
            after_revoke.append(statement.lower())
    event.listen(c.engine.sync_engine,'before_cursor_execute',capture)
    pending=None
    try:
        async with c.session() as blocker:
            await blocker.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==c.report_id).with_for_update())
            pid=await blocker.scalar(text('SELECT pg_backend_pid()'))
            pending=asyncio.create_task(c.client.post('/api/agent/runtime/model/infer',json={'operation':'propose_d4'},headers={'Authorization':'Bearer '+c.token}))
            waited=False
            for _ in range(200):
                async with c.session() as observer:
                    waited=bool(await observer.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND :pid=ANY(pg_blocking_pids(pid)))"),{'pid':pid}))
                if waited: break
                await asyncio.sleep(.02)
            assert waited,'actual PostgreSQL report lock wait was not reached'
            await blocker.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
            revoked=True
            await blocker.commit()
        result=await pending
        assert result.status_code in {401,403},result.text
        assert c.witness.a.bodies==c.witness.b.bodies==[]
        assert not any('capa_eightd.d2_description' in sql or 'capa_eightd.d3_interim' in sql or 'jsonb_array_elements' in sql for sql in after_revoke)
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(CapaD4Candidate))==0
            assert await db.scalar(select(func.count()).select_from(AgentD4InputReceipt))==0
    finally:
        event.remove(c.engine.sync_engine,'before_cursor_execute',capture)
        if pending is not None and not pending.done():
            await asyncio.gather(pending,return_exceptions=True)


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_actual_http_delivery_then_source_revocation_returns_no_derived_body(d4_case,monkeypatch):
    from sqlalchemy import select,update,func
    from app.models.role import RolePermission
    from app.models.capa_r6 import AgentD4InputReceipt,CapaD4Candidate
    from app.services.agent import provider_adapter
    c=d4_case
    await _managed_claim(c)
    original=provider_adapter.build_deployment_client
    def build(*args,**kwargs):
        pc=original(*args,**kwargs)
        close=pc.client.close
        async def revoke_after_close():
            await close()
            async with c.session() as db:
                await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
                await db.commit()
        monkeypatch.setattr(pc.client,'close',revoke_after_close)
        return pc
    monkeypatch.setattr(provider_adapter,'build_deployment_client',build)
    result=await c.client.post('/api/agent/runtime/model/infer',json={'operation':'propose_d4'},headers={'Authorization':'Bearer '+c.token})
    assert result.status_code==403 and 'synthetic D5' not in result.text,result.text
    assert len(c.witness.a.bodies)==1 and c.witness.b.bodies==[]
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentD4InputReceipt))==1
        assert await db.scalar(select(func.count()).select_from(CapaD4Candidate))==0


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_source_revocation_still_allows_metadata_pause_cancel_but_not_resume(d4_case):
    from sqlalchemy import update,event
    from app.models.role import RolePermission
    c=d4_case
    await deliver(c)
    nonowner=await c.admin.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='pause',run_id=str(c.run_id),expected_epoch=c.epoch,idempotency_key='not-owner'))
    assert nonowner.status_code in {403,404},nonowner.text
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==c.role_id,RolePermission.module=='fmea').values(permission_level=0))
        await db.commit()
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().lower().startswith('select'):
            statements.append(statement.lower())
    event.listen(c.engine.sync_engine,'before_cursor_execute',capture)
    try:
        pause=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='pause',run_id=str(c.run_id),expected_epoch=c.epoch,idempotency_key='pause-no-source'))
        assert pause.status_code==200,pause.text
        epoch=pause.json()['lease_epoch']
        cp=await c.client.post(f'/api/agent/tasks/{c.task_id}/d4-recovery-checkpoints',json=dict(run_id=str(c.run_id),expected_epoch=epoch))
        assert cp.status_code==200,cp.text
        resume=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='resume',run_id=str(c.run_id),expected_epoch=epoch,idempotency_key='resume-no-source'))
        assert resume.status_code==403,resume.text
        cancel=await c.client.post(f'/api/agent/tasks/{c.task_id}/control',json=dict(action='cancel',run_id=str(c.run_id),expected_epoch=epoch,idempotency_key='cancel-no-source'))
        assert cancel.status_code==200,cancel.text
    finally:
        event.remove(c.engine.sync_engine,'before_cursor_execute',capture)
    assert not any('jsonb_array_elements' in sql or 'capa_d4_candidates.original_text' in sql or 'capa_d4_candidate_withdrawals.reason' in sql for sql in statements)


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_real_embedded_sdk_candidate_endpoint_contract_retries_and_checkpoints(d4_case,tmp_path):
    from pathlib import Path
    from dataclasses import replace
    import sys
    from sqlalchemy import select,func
    from app.models.capa_r6 import CapaD4Candidate,AgentD4CandidateCommand,CapaD4CandidateSource
    from app.models.capa import CAPAEightD
    from app.services.agent_runtime.r5_executor import ExecutorApproval
    from tests.e2e.test_r5_model_agent import call
    c=d4_case
    root=Path(__file__).parents[3]
    bundle=(root/'examples/d4_candidate_agent.py').read_text()
    main=(root/'examples/d4_candidate_agent_main.py').read_text()
    assert bundle.endswith(main)
    probe='''import json,sys
from openqms_agent_sdk import ManagedLaunch,RunClient

def main():
    assert sys.flags.isolated and sys.flags.no_site
    assert not any(name.split('.')[0] in {'app','httpx','sqlalchemy','pydantic'} for name in sys.modules)
    with RunClient.from_launch(ManagedLaunch.from_dict(json.load(sys.stdin))) as run:
        batch=run.claim_messages()
        run.ack_messages(batch_id=batch.batch_id,through_sequence=batch.messages[-1].sequence)
        turn=run.model_turn(turn=0)
        assert len(turn.tool_calls)==1
        result=run.model_tool(call_id=turn.tool_calls[0].id)
        assert result.status=='prepared'
        assert not run.model_turn(turn=1).tool_calls
        first=run.save_d4_candidate(command_key='sdk-contract',text='待验证定位销磨损',supporting=('FMEA明确记录磨损',),missing_information=('现场验证',))
        retry=run.save_d4_candidate(command_key='sdk-contract',text='待验证定位销磨损',supporting=('FMEA明确记录磨损',),missing_information=('现场验证',))
        assert first==retry and first.state=='pending'
        checkpoint=run.save_d4_checkpoint()
        assert checkpoint.command_watermark==1
        run.finish(status='completed')
if __name__=='__main__':
    try: main()
    except Exception: sys.exit(1)
'''
    artifact=tmp_path/'sdk-candidate-contract.py'
    artifact.write_text(bundle[:-len(main)]+probe)
    c.pilot=replace(c.pilot,approval=ExecutorApproval.approve(artifact,sys.executable))
    c.app.state.r5_controlled_pilot=c.pilot
    model=await c.admin.post('/api/agent/models',json=dict(c.model_body,name='SDK command contract',version='contract'))
    assert model.status_code==201,model.text
    c.create_body['model_deployment_id']=model.json()['deployment_id']
    strict_scripted_chat(c,[call('read_inputs'),{'content':'authorized inputs delivered'}])
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201,created.text
    result=await c.client.post(f"/api/agent/tasks/{created.json()['task_id']}/launch",timeout=130)
    assert result.status_code==200,result.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD4Candidate))==1
        assert await db.scalar(select(func.count()).select_from(AgentD4CandidateCommand))==1
        assert await db.scalar(select(func.count()).select_from(CapaD4CandidateSource))==3
        assert (await db.get(CAPAEightD,c.report_id)).d4_root_cause is None
    assert len(c.witness.a.bodies)==2 and c.witness.b.bodies==[]


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('field',['protocol','profile','missing','metadata_expired','token','expired_token','task_id','run_id','lease_epoch','deployment_id'])
async def test_real_sdk_rejects_bad_managed_envelope_without_model_or_candidate(d4_case,monkeypatch,field):
    from pathlib import Path
    from dataclasses import replace
    from types import SimpleNamespace
    from datetime import timedelta
    import sys
    from sqlalchemy import select,func
    from app.models.capa_r6 import CapaD4Candidate,AgentD4InputReceipt
    from app.services.agent_runtime import r5_executor,run_auth
    from app.services.agent_runtime.trial_policy import TrialAdmission
    c=d4_case
    artifact=Path(__file__).parents[3]/'examples/d4_candidate_agent.py'
    c.pilot=replace(c.pilot,approval=r5_executor.ExecutorApproval.approve(artifact,sys.executable))
    c.app.state.r5_controlled_pilot=c.pilot
    model=await c.admin.post('/api/agent/models',json=dict(c.model_body,name='D4 bad envelope',version='bad-wire'))
    assert model.status_code==201,model.text
    c.create_body['model_deployment_id']=model.json()['deployment_id']
    original=r5_executor.managed_launch_payload
    def changed(row,claim,**kwargs):
        data=original(row,claim,**kwargs)
        if field=='missing': data.pop('run_id')
        elif field=='metadata_expired': data['lease_expires_at']='2000-01-01T00:00:00+00:00'
        elif field=='protocol': data['protocol']='unknown'
        elif field=='profile': data['profile']='model_d5_proposal_v1'
        elif field=='token': data['token']='invalid-opaque-token'
        elif field=='expired_token':
            expired=SimpleNamespace(run_id=claim.run_id,lease_epoch=claim.lease_epoch,plugin_version=c.pilot.plugin_version,
                lease_expires_at=datetime.now(UTC)-timedelta(minutes=1))
            installation=SimpleNamespace(installation_id=c.r5_id,credential_epoch=c.pilot.credential_epoch)
            trial=TrialAdmission(c.pilot.profile,c.pilot.fingerprint(),c.pilot.expires_at,c.r5_id)
            data['token']=run_auth.issue_run_token(expired,installation,str(c.binding.tenant_id),c.binding.generation,trial=trial,model_binding=row)
        elif field=='lease_epoch': data[field]+=1
        else: data[field]=str(UUID(int=999))
        return data
    monkeypatch.setattr(r5_executor,'managed_launch_payload',changed)
    created=await c.client.post('/api/agent/tasks',json=c.create_body)
    assert created.status_code==201,created.text
    result=await c.client.post(f"/api/agent/tasks/{created.json()['task_id']}/launch",timeout=130)
    assert result.status_code==403,result.text
    assert c.witness.a.bodies==c.witness.b.bodies==[]
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaD4Candidate))==0
        assert await db.scalar(select(func.count()).select_from(AgentD4InputReceipt))==0


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_control_metadata_cannot_rebind_to_another_tenant(d4_case):
    from dataclasses import replace
    from uuid import uuid4
    from types import SimpleNamespace
    from sqlalchemy import text,event
    from app.services.agent_runtime.task_service import get_task_for_control
    c=d4_case
    await deliver(c)
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        statements.append(statement.lower())
    async with c.session() as db:
        await db.execute(text('SELECT 1'))
        db.info['tenant_binding']=replace(c.binding,tenant_id=uuid4())
        event.listen(c.engine.sync_engine,'before_cursor_execute',capture)
        try:
            with pytest.raises(PermissionError):
                await get_task_for_control(db,SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)),c.task_id)
        finally:
            db.info['tenant_binding']=c.binding
            event.remove(c.engine.sync_engine,'before_cursor_execute',capture)
    assert not any('agent_tasks' in sql or 'jsonb_array_elements' in sql for sql in statements)


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_checkpoint_original_position_cannot_be_rebased_backwards(d4_case):
    from sqlalchemy import update
    from app.models.agent_task import AgentRun
    from app.models.agent_d4_recovery import D4RecoveryCheckpoint
    from app.models.capa_r6 import AgentD4CandidateCheckpointPosition
    c=d4_case
    await deliver(c)
    batch=await c.client.post('/api/agent/runtime/messages/claim',json={'limit':20},headers={'Authorization':'Bearer '+c.token})
    assert batch.status_code==200,batch.text
    ack=await c.client.post('/api/agent/runtime/messages/ack',json=dict(batch_id=batch.json()['batch_id'],through_sequence=1),headers={'Authorization':'Bearer '+c.token})
    assert ack.status_code==200,ack.text
    cp=await c.client.post('/api/agent/runtime/capa/d4/checkpoints',json={},headers={'Authorization':'Bearer '+c.token})
    assert cp.status_code==200,cp.text
    async with c.session() as db:
        await db.execute(update(AgentRun).where(AgentRun.run_id==c.run_id).values(accepted_message_seq=0))
        await db.commit()
    rejected=await c.client.post('/api/agent/runtime/capa/d4/checkpoints',json={},headers={'Authorization':'Bearer '+c.token})
    assert rejected.status_code in {403,409},rejected.text
    async with c.session() as db:
        original=await db.get(D4RecoveryCheckpoint,UUID(cp.json()['checkpoint_id']))
        position=await db.get(AgentD4CandidateCheckpointPosition,original.checkpoint_id)
        assert original.accepted_message_seq==1 and position.watermark==0


@pytest.mark.ci_r5_native
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_real_old_generation_delivery_history_is_readable_without_reenabling_its_token(d4_case,monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from sqlalchemy import text
    from app.services.agent_runtime import task_service,runtime_access,model_egress
    c=d4_case
    await deliver(c)
    next_binding=replace(c.binding,generation=c.binding.generation+1)
    async with c.engine.begin() as connection:
        await connection.execute(text('UPDATE public.tenants SET generation=:generation WHERE id=:id'),
            {'generation':next_binding.generation,'id':c.binding.tenant_id})
    monkeypatch.setattr(model_egress,'_addresses',lambda _: (_ for _ in ()).throw(AssertionError('historical metadata must not resolve DNS')))
    async with c.factory(binding=next_binding) as db:
        task=await task_service.get_task_for_view(db,SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)),c.task_id)
        assert task.task_id==c.task_id
        from sqlalchemy import select
        from app.models.capa_r6 import AgentD4InputReceipt
        from app.services.capa_d4_candidates import receipt_sources
        receipt=await db.scalar(select(AgentD4InputReceipt).where(AgentD4InputReceipt.task_id==c.task_id))
        assert receipt.tenant_generation==c.binding.generation
        with pytest.raises(PermissionError):
            await receipt_sources(db,receipt,actor_id=c.user_id,task=task,fresh=True)
        with pytest.raises(PermissionError):
            await runtime_access.verify_runtime_identity(db,c.token,next_binding)
