"""Retirement checks follow authentication and report authorization."""
from uuid import uuid4
import pytest
from app.models.capa_r6 import CapaR6EntrySwitch
from tests.capa.r6_support import r6_case  # noqa: F401

@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('path,method,body',[
    ('d4-fmea-recommendations','get',None),('d5-fmea-recommendations','get',None),
    ('draft/d4','post',{'request_id':str(uuid4()),'format':'paragraph'}),
    ('draft/d5','post',{'request_id':str(uuid4()),'format':'paragraph'}),
    ('adopt-recommendation','post',{'d_step':'d4','adopted_text':'old','source':'llm'}),
])
async def test_old_routes_retired_after_identity_and_report_checks(r6_case,path,method,body):
    c=r6_case
    async with c.session() as db:
        db.add(CapaR6EntrySwitch(switch_id=uuid4(),epoch=1,state='switched',
            actor_id=c.actor().user_id,evidence={'fixture':'already switched'}))
        await db.commit()
    send=getattr(c.actor().client,method)
    response=await send(f'/api/capa/{c.report_id}/{path}',**({} if body is None else {'json':body}))
    assert response.status_code==410,response.text
    missing=await send(f'/api/capa/{uuid4()}/{path}',**({} if body is None else {'json':body}))
    assert missing.status_code in {403,404},missing.text

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_unbound_legacy_candidate_requires_regeneration(r6_case):
    c=r6_case
    before=await c.report()
    response=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',
        json={'d_step':'d4','adopted_text':'unknown old history','source':'llm'})
    assert response.status_code==409,response.text
    assert (await c.report()).d4_root_cause==before.d4_root_cause

@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('writer_outcome',['commit','rollback'])
async def test_real_cli_close_timeout_and_resume_preserves_writer(r6_case,tmp_path,writer_outcome):
    from sqlalchemy import select,text
    from app.models.audit import AuditLog
    from app.models.capa import CAPAEightD
    from app.services.capa_entry_switch import admit,status
    from tests.capa.r6_switch_support import owned_cli,cli,held_manual_writer
    c=r6_case
    fixture=await owned_cli(c,tmp_path)
    async with held_manual_writer(c,outcome=writer_outcome) as writer:
        code,closed=await cli(fixture,'close')
        assert code==0,closed
        assert closed=={'state':'draining','epoch':1,'operation_ref':fixture['operation']}
        code,pending=await cli(fixture,'finish','--timeout-ms','100')
        assert code==2,pending
        async with c.session() as observer:
            assert (await status(observer)).state=='draining'
        before=await c.report()
        denied=await c.actor().client.put(f'/api/capa/{c.report_id}',json={'d4_root_cause':'new denied writer'})
        assert denied.status_code==503,denied.text
        assert (await c.report()).d4_root_cause==before.d4_root_cause
    code,switched=await cli(fixture,'finish')
    assert code==0,switched
    assert switched=={'state':'switched','epoch':2,'operation_ref':fixture['operation']}
    code,replay=await cli(fixture,'finish')
    assert code==0 and replay==switched,replay
    async with c.session() as db:
        final=await status(db)
        assert final.evidence['settled']['count']>=1
        assert await db.scalar(select(__import__('sqlalchemy').func.count()).select_from(AuditLog).where(AuditLog.action=='R6_FINISH_SWITCH'))==1
        assert (await db.get(CAPAEightD,c.report_id)).d4_root_cause==('admitted before durable close' if writer_outcome=='commit' else before.d4_root_cause)

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_operator_killed_while_pg_reports_blocking_remains_draining(r6_case,tmp_path):
    import asyncio
    from sqlalchemy import text,update
    from app.models.capa import CAPAEightD
    from app.services.capa_entry_switch import admit,status
    from tests.capa.r6_switch_support import owned_cli,cli,ROOT,held_manual_writer
    c=r6_case
    fixture=await owned_cli(c,tmp_path)
    async with held_manual_writer(c,value='writer survives killed operator') as writer:
        writer_pid=await writer.scalar(text('SELECT pg_backend_pid()'))
        code,closed=await cli(fixture,'close')
        assert code==0,closed
        process=await asyncio.create_subprocess_exec(*fixture['base'],'finish',*fixture['args'],'--timeout-ms','60000',
            env=fixture['env'],cwd=ROOT/'backend',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            blocked=False
            for _ in range(100):
                async with c.session() as observer:
                    blocked=await observer.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE :writer=ANY(pg_blocking_pids(pid)) AND wait_event_type='Lock' AND wait_event='advisory')"),{'writer':writer_pid})
                if blocked:break
                await asyncio.sleep(.05)
            assert blocked,'actual PostgreSQL exclusive drain did not block on the admitted writer'
            process.kill()
            await process.communicate()
            assert process.returncode<0
            async with c.session() as observer:
                assert (await status(observer)).state=='draining'
                assert await observer.scalar(text('SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pid=:pid)'),{'pid':writer_pid})
            denied=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json={'d_step':'d4','source':'llm','adopted_text':'new denied'})
            assert denied.status_code==503,denied.text
            # Context releases the original real business commit; never cancel writer.
        finally:
            if process.returncode is None:
                process.kill();await process.communicate()
    code,finished=await cli(fixture,'finish')
    assert code==0 and finished['state']=='switched',finished
    assert (await c.report()).d4_root_cause=='writer survives killed operator'


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('change',['expired','purpose','owner','build','config_role','registry_signature','launch_artifact'])
async def test_actual_cli_rejects_wrong_evidence_before_close(r6_case,tmp_path,change):
    import json
    from datetime import datetime,timedelta,timezone
    from app.services.capa_entry_switch import status
    from tests.capa.r6_switch_support import owned_cli,cli
    c=r6_case
    fixture=await owned_cli(c,tmp_path)
    document=json.loads(fixture['document'].read_text())
    if change=='expired':document['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    elif change=='purpose':document['purpose']='r6-release.v1'
    elif change=='owner':document['target']['owner']='another-owner-12345'
    elif change=='build':document['target']['candidate_build']='0'*64
    elif change=='config_role':
        from pathlib import Path
        config=__import__('pathlib').Path(fixture['record']['config_file'])
        facts=json.loads(config.read_text());facts['deployment_role']='production';config.write_text(json.dumps(facts))
    elif change=='registry_signature':
        value=json.loads(fixture['registry'].read_text());value['signature']='0'*64;fixture['registry'].write_text(json.dumps(value))
    else:
        from pathlib import Path
        launch=Path(fixture['record']['instances'][0]['path']);launch.write_text('{}')
    fixture['document'].write_text(json.dumps(document))
    code,result=await cli(fixture,'close')
    assert code==1,result
    async with c.session() as db:
        actual=await status(db)
        assert actual.state=='legacy' and actual.epoch==0


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_old_before_adopt_put_committed_then_post_after_real_switch(r6_case,tmp_path):
    from sqlalchemy import select,func
    from app.models.audit import AuditLog
    from app.models.capa import CapaAIAdoption
    from tests.capa.r6_switch_support import owned_cli,cli
    c=r6_case
    saved=await c.actor().client.put(f'/api/capa/{c.report_id}',json={'d4_root_cause':'saved beforeAdopt input'})
    assert saved.status_code==200,saved.text
    fixture=await owned_cli(c,tmp_path)
    assert (await cli(fixture,'close'))[0]==0
    assert (await cli(fixture,'finish'))[0]==0
    rejected=await c.actor().client.post(f'/api/capa/{c.report_id}/adopt-recommendation',json={'d_step':'d4','adopted_text':'old preview','source':'llm'})
    assert rejected.status_code==410,rejected.text
    assert (await c.report()).d4_root_cause=='saved beforeAdopt input'
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(CapaAIAdoption))==0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='UPDATE',AuditLog.record_id==c.report_id))==1

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_expired_document_requires_authorized_renewal_then_same_operation_resume(r6_case,tmp_path):
    import asyncio,json
    from datetime import datetime,timedelta,timezone
    from app.services.capa_entry_switch import status
    from tests.capa.r6_switch_support import owned_cli,cli
    c=r6_case
    fixture=await owned_cli(c,tmp_path)
    document=json.loads(fixture['document'].read_text())
    expires=datetime.now(timezone.utc)+timedelta(seconds=5)
    document['expires_at']=expires.isoformat()
    fixture['document'].write_text(json.dumps(document))
    fixture.get('authorize_document',lambda value:None)(document)
    code,closed=await cli(fixture,'close');assert code==0,closed
    await asyncio.sleep(max(0,(expires-datetime.now(timezone.utc)).total_seconds())+.05)
    code,expired=await cli(fixture,'finish');assert code==1,expired
    async with c.session() as db:before=await status(db)
    assert before.state=='draining'
    renewed=dict(document,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(),
        resume_of={'operation_ref':fixture['operation'],'previous_document_digest':before.evidence['document_digest'],'draining_epoch':before.epoch})
    fixture['document'].write_text(json.dumps(renewed))
    code,unregistered=await cli(fixture,'renew')
    assert code==1,unregistered
    fixture.get('authorize_document',lambda value:None)(renewed)
    code,result=await cli(fixture,'renew')
    assert code==0 and result['state']=='draining' and result['epoch']==2,result
    code,replay=await cli(fixture,'renew');assert code==0 and replay==result,replay
    code,finished=await cli(fixture,'finish')
    assert code==0 and finished['state']=='switched' and finished['epoch']==3,finished
    assert finished['operation_ref']==closed['operation_ref']


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_more_than_1000_real_admissions_do_not_prevent_switch(r6_case,tmp_path):
    from app.services.capa_entry_switch import admit,status
    from tests.capa.r6_switch_support import owned_cli,cli
    c=r6_case
    # Real independently committed transactions, not 1001 synthetic rows with
    # a made-up xid or a stubbed settle result.
    async with c.session() as writer:
        for _ in range(1001):
            await admit(writer,'current')
            await writer.commit()
    fixture=await owned_cli(c,tmp_path)
    assert (await cli(fixture,'close'))[0]==0
    code,result=await cli(fixture,'finish','--timeout-ms','60000')
    assert code==0,result
    async with c.session() as db:
        final=await status(db)
        assert final.evidence['settled']['count']==1001


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_authority_expiring_while_blocked_cannot_finish(r6_case,tmp_path):
    import asyncio,json
    from datetime import datetime,timedelta,timezone
    from sqlalchemy import text
    from app.services.capa_entry_switch import status
    from tests.capa.r6_switch_support import owned_cli,cli,held_manual_writer,ROOT
    c=r6_case;fixture=await owned_cli(c,tmp_path)
    document=json.loads(fixture['document'].read_text())
    expires=datetime.now(timezone.utc)+timedelta(seconds=5)
    document['expires_at']=expires.isoformat();fixture['document'].write_text(json.dumps(document));fixture['authorize_document'](document)
    process=None
    try:
        async with held_manual_writer(c) as writer:
            writer_pid=await writer.scalar(text('SELECT pg_backend_pid()'))
            code,closed=await cli(fixture,'close');assert code==0,closed
            process=await asyncio.create_subprocess_exec(*fixture['base'],'finish',*fixture['args'],'--timeout-ms','60000',
                env=fixture['env'],cwd=ROOT/'backend',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            blocked=False
            for _ in range(100):
                async with c.session() as db:
                    blocked=await db.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)))'),{'pid':writer_pid})
                if blocked:break
                await asyncio.sleep(.03)
            assert blocked,'operator must actually wait on admitted business transaction'
            await asyncio.sleep(max(0,(expires-datetime.now(timezone.utc)).total_seconds())+.05)
        out,err=await process.communicate()
        assert process.returncode==1,(out or err).decode()
        async with c.session() as db:
            before=await status(db)
            assert before.state=='draining' and before.epoch==1
        renewed=dict(document,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(),
            resume_of={'operation_ref':fixture['operation'],'previous_document_digest':before.evidence['document_digest'],'draining_epoch':1})
        fixture['document'].write_text(json.dumps(renewed));fixture['authorize_document'](renewed)
        assert (await cli(fixture,'renew'))[0]==0
        code,finished=await cli(fixture,'finish');assert code==0 and finished['epoch']==3,finished
    finally:
        if process is not None and process.returncode is None:
            process.kill();await process.communicate()


async def _blocked_operator(case,writer_pid):
    import asyncio
    from sqlalchemy import text
    for _ in range(150):
        async with case.session() as db:
            blocked=await db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid)) AND wait_event='advisory')"),{'pid':writer_pid})
        if blocked:return
        await asyncio.sleep(.05)
    raise AssertionError('operator did not really block on admitted transaction')


def _renewal_fixture(fixture,path,document):
    import json
    path.write_text(json.dumps(document));fixture['authorize_document'](document)
    return dict(fixture,document=path,args=[*fixture['args'][:-1],str(path)])


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_two_competing_renewals_only_one_wins(r6_case,tmp_path):
    import asyncio,json
    from datetime import datetime,timedelta,timezone
    from sqlalchemy import select,func
    from app.models.audit import AuditLog
    from app.services.capa_entry_switch import status
    from tests.capa.r6_switch_support import owned_cli,cli
    c=r6_case;fixture=await owned_cli(c,tmp_path)
    assert (await cli(fixture,'close'))[0]==0
    async with c.session() as db:before=await status(db)
    original=json.loads(fixture['document'].read_text())
    choices=[]
    for index,minutes in enumerate((20,30)):
        document=dict(original,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat(),
            resume_of={'operation_ref':fixture['operation'],'previous_document_digest':before.evidence['document_digest'],'draining_epoch':1})
        choices.append(_renewal_fixture(fixture,tmp_path/f'renew-{index}.json',document))
    outcomes=await asyncio.gather(*(cli(choice,'renew') for choice in choices))
    assert sorted(code for code,_ in outcomes)==[0,1],outcomes
    winner=choices[next(index for index,(code,_) in enumerate(outcomes) if code==0)]
    async with c.session() as db:
        assert (await status(db)).epoch==2
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='R6_REAUTHORIZE_DRAIN'))==1
    assert (await cli(winner,'renew'))[0]==0
    code,finished=await cli(winner,'finish')
    assert code==0 and finished['epoch']==3,finished


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_old_finish_waiter_rejects_renewed_authority(r6_case,tmp_path):
    import asyncio,json
    from datetime import datetime,timedelta,timezone
    from sqlalchemy import text,select,func
    from app.models.audit import AuditLog
    from app.services.capa_entry_switch import status
    from tests.capa.r6_switch_support import owned_cli,cli,held_manual_writer,ROOT
    c=r6_case;fixture=await owned_cli(c,tmp_path);process=None
    try:
        async with held_manual_writer(c) as writer:
            writer_pid=await writer.scalar(text('SELECT pg_backend_pid()'))
            assert (await cli(fixture,'close'))[0]==0
            process=await asyncio.create_subprocess_exec(*fixture['base'],'finish',*fixture['args'],'--timeout-ms','60000',
                env=fixture['env'],cwd=ROOT/'backend',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            await _blocked_operator(c,writer_pid)
            async with c.session() as db:before=await status(db)
            original=json.loads(fixture['document'].read_text())
            renewed=_renewal_fixture(fixture,tmp_path/'renewed.json',dict(original,
                expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),
                resume_of={'operation_ref':fixture['operation'],'previous_document_digest':before.evidence['document_digest'],'draining_epoch':1}))
            code,result=await cli(renewed,'renew');assert code==0,result
        out,err=await process.communicate()
        assert process.returncode==1,(out or err).decode()
        async with c.session() as db:
            actual=await status(db);assert actual.state=='draining' and actual.epoch==2
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='R6_FINISH_SWITCH'))==0
        code,finished=await cli(renewed,'finish');assert code==0 and finished['epoch']==3,finished
    finally:
        if process is not None and process.returncode is None:process.kill();await process.communicate()


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_generation_change_while_operator_waits_refuses_old_authority(r6_case,tmp_path):
    import asyncio
    from sqlalchemy import text,select,func
    from app.core.tenant_transaction import TenantBinding,TenantUnavailable
    from app.models.audit import AuditLog
    from app.services.capa_entry_switch import status
    from tests.capa.r6_switch_support import owned_cli,cli,held_manual_writer,ROOT
    c=r6_case;fixture=await owned_cli(c,tmp_path);process=None;changed=False
    try:
        try:
            async with held_manual_writer(c) as writer:
                writer_pid=await writer.scalar(text('SELECT pg_backend_pid()'))
                assert (await cli(fixture,'close'))[0]==0
                process=await asyncio.create_subprocess_exec(*fixture['base'],'finish',*fixture['args'],'--timeout-ms','60000',
                    env=fixture['env'],cwd=ROOT/'backend',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                await _blocked_operator(c,writer_pid)
                # Fault injection in this fixture-owned registry only; normal
                # maintenance owns its separate tenant barrier. Never a phase UPDATE.
                async with c.runtime.engine.begin() as registry:
                    await registry.execute(text('UPDATE public.tenants SET generation=generation+1 WHERE id=:id'),{'id':c.binding.tenant_id})
                changed=True
        except (TenantUnavailable,PermissionError):
            assert changed  # The original commit can succeed but response auth expires.
        out,err=await process.communicate()
        assert process.returncode==1,(out or err).decode()
        new=TenantBinding(c.binding.tenant_id,c.binding.schema_name,c.binding.generation+1,'business')
        async with c.factory(binding=new) as db:
            actual=await status(db);assert actual.state=='draining' and actual.epoch==1
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='R6_FINISH_SWITCH'))==0
        code,refused=await cli(fixture,'finish');assert code==1,refused
    finally:
        if process is not None and process.returncode is None:process.kill();await process.communicate()


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_admission_witness_does_not_borrow_saturated_business_pool(r6_case):
    import asyncio
    from sqlalchemy import select,func,text
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker,AsyncSession
    from app.database import TenantSession
    from app.models.audit import AuditLog
    from app.services.capa_entry_switch import admit,_witness_engine
    from app.core.tenant_transaction import TenantBinding,TenantUnavailable
    c=r6_case
    engine=create_async_engine(c.runtime.engine.url,pool_size=2,max_overflow=0,pool_timeout=.2,hide_parameters=True)
    factory=async_sessionmaker(engine,class_=AsyncSession,sync_session_class=TenantSession,expire_on_commit=False)
    try:
        async with factory(binding=c.binding) as a,factory(binding=c.binding) as b:
            # Both real primary connections are checked out before either
            # request asks for its independently durable admission witness.
            await a.scalar(text('SELECT 1'));await b.scalar(text('SELECT 1'))
            await asyncio.wait_for(asyncio.gather(admit(a),admit(b)),timeout=3)
            async with c.session() as observer:
                assert await observer.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='R6_ENTRY_ADMITTED'))==2
                assert await observer.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='R6_ENTRY_COMMITTED'))==0
            await a.commit();await b.rollback()
        async with c.session() as observer:
            assert await observer.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='R6_ENTRY_COMMITTED'))==1
        witness=_witness_engine(engine)
        assert witness.pool.size()==1 and witness.pool.overflow()==0
        # The reserved connection must not retain another transaction's tenant
        # search_path or bypass normal registry generation validation.
        invalid=TenantBinding(c.binding.tenant_id,c.binding.schema_name,c.binding.generation+1,'business')
        async with AsyncSession(bind=witness,sync_session_class=TenantSession,binding=invalid) as wrong:
            with pytest.raises(TenantUnavailable):await wrong.scalar(select(func.count()).select_from(AuditLog))
        async with AsyncSession(bind=witness,sync_session_class=TenantSession,binding=c.binding) as right:
            assert await right.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='R6_ENTRY_ADMITTED'))==2
    finally:
        await engine.dispose()
    assert witness.pool.checkedin()==0
