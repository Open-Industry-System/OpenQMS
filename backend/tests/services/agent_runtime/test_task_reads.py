"""Real tenant activity windows, object proofs and current-source user admission."""
import asyncio
import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.util import await_only

from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.models.agent_plugin import AgentPluginInstallation, AgentPluginGrant
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage, AgentTaskGrant
from app.models.agent_readonly_control import AgentTaskUpdate
from app.models.agent_runtime_event import AgentProjectionReceipt, AgentRunEvent
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.services.agent_runtime import task_service
from tests.services.agent_runtime.test_readonly_delivery import context_delivery, context
from tests.services.agent_runtime.test_readonly_outputs import write, result_body, event_body
from tests.services.agent_runtime.test_runtime_messages import delivery, append, claim, ack
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned


def service():
    try:
        from app.services.agent_runtime import task_reads
    except ImportError:
        pytest.fail("current-source activity read service missing")
    return task_reads


async def scope_for(db, owned):
    return RequestScope(FactoryScope([], None), None, ProductLineScope('NONE', []), await db.get(User, owned.user_id))


async def activity(owned, **kwargs):
    async with owned.factory(binding=owned.binding) as db:
        return await service().get_activity(db, await scope_for(db, owned), owned.task_id, **kwargs)


async def directory(owned):
    async with owned.factory(binding=owned.binding) as db:
        task = await db.get(AgentTask, owned.task_id)
        return await service().list_installations(db, await scope_for(db, owned), task.target_capa_id)


async def messages(owned, first, last):
    async with owned.factory(binding=owned.binding) as db:
        for seq in range(first, last+1):
            mid = uuid4()
            db.add(AgentTaskMessage(message_id=mid, task_id=owned.task_id, author_id=owned.user_id,
                sequence=seq, content=f'restricted-{seq}', state='queued', sensitivity='restricted', idempotency_key=f'input-{seq}'))
            db.add(AgentTaskUpdate(task_id=owned.task_id, sequence=seq, kind='message', object_id=mid))
        await db.commit()


def test_activity_query_strict_bounded_window_contract():
    import app.schemas.agent_control as mod
    assert hasattr(mod, 'ActivityQuery'), 'strict activity query missing'
    assert mod.ActivityQuery(before_sequence=51, window_end_sequence=100, page_size=50)
    assert mod.ActivityQuery(before_sequence=9223372036854775808, window_end_sequence=9223372036854775807)
    for fields in ({'before_sequence': 1}, {'before_sequence': 102, 'window_end_sequence':100},
                   {'window_end_sequence': -1}, {'window_end_sequence': 9223372036854775808},
                   {'before_sequence': 0, 'window_end_sequence':0}, {'page_size':0}, {'page_size':51},
                   {'page_size':True}, {'page_size':1.0}, {'page_size':'1'}, {'window_end_sequence':False}, {'spoof':1}):
        with pytest.raises(ValidationError):
            mod.ActivityQuery(**fields)
    for raw in ('true', '-1', '+1', '1.0', '１２', '9'*100):
        with pytest.raises(ValidationError):
            mod.ActivityHTTPQuery(window_end_sequence=raw)
    assert mod.ActivityHTTPQuery(before_sequence='51', window_end_sequence='100', page_size='50').before_sequence == 51


@pytest.mark.asyncio
async def test_fixed_window_two_connections_and_next_cycle_adjacent_pages(committed_runtime):
    owned = committed_runtime
    await messages(owned,1,100)
    latest = await activity(owned)
    assert [i['sequence'] for i in latest['items']] == list(range(51,101))
    assert latest['window_end_sequence'] == 100 and latest['next_before_sequence'] == 51
    await messages(owned,101,110)
    old = await activity(owned,before_sequence=51,window_end_sequence=100)
    assert [i['sequence'] for i in old['items']] == list(range(1,51))
    assert old['next_before_sequence'] is None and old['window_end_sequence'] == 100
    fresh = await activity(owned)
    adjacent = await activity(owned,before_sequence=fresh['next_before_sequence'],window_end_sequence=fresh['window_end_sequence'])
    assert [i['sequence'] for i in fresh['items']] == list(range(61,111))
    assert [i['sequence'] for i in adjacent['items']] == list(range(11,61))
    assert set(fresh) == {'task_id','task_status','run_id','run_status','lease_epoch','items','window_end_sequence','next_before_sequence'}
    assert 'total' not in json.dumps(fresh)


@pytest.mark.asyncio
async def test_latest_window_is_highest_selected_not_later_max(committed_runtime):
    owned = committed_runtime
    await messages(owned,1,100)
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set(); await release.wait()
    def intercept(conn,cursor,statement,parameters,ctx,many):
        if 'FROM agent_task_updates' in statement and 'ORDER BY' in statement:
            await_only(pause())
    event.listen(owned.engine.sync_engine,'after_cursor_execute',intercept)
    future = asyncio.create_task(activity(owned))
    try:
        await asyncio.wait_for(reached.wait(),10)
        await messages(owned,101,110)
        release.set()
        result = await asyncio.wait_for(future,10)
        assert result['window_end_sequence'] == 100
        assert [i['sequence'] for i in result['items']] == list(range(51,101))
    finally:
        release.set(); await asyncio.gather(future,return_exceptions=True)
        event.remove(owned.engine.sync_engine,'after_cursor_execute',intercept)


@pytest.mark.asyncio
@pytest.mark.parametrize('corruption',['foreignmessage','unknownobject','author','claimedproof','unknownkind','foreignrun','foreigncontrol'])
async def test_corrupt_pointer_denies_entire_page(committed_runtime,corruption):
    owned = committed_runtime
    await messages(owned,1,2)
    async with owned.factory(binding=owned.binding) as db:
        pointer = await db.scalar(select(AgentTaskUpdate).where(AgentTaskUpdate.sequence==2))
        message = await db.get(AgentTaskMessage,pointer.object_id)
        if corruption == 'unknownobject': pointer.object_id=uuid4()
        elif corruption == 'author':
            # Actual seeded second user; a real author mismatch must fail closed.
            other = User(email='other@example.test',username='other',password_hash='unused',legacy_role='viewer',role_id=owned.role_id)
            db.add(other); await db.flush(); message.author_id=other.user_id
        elif corruption == 'claimedproof': message.state='claimed'
        elif corruption == 'unknownkind':
            await db.execute(text('ALTER TABLE agent_task_updates DROP CONSTRAINT ck_agent_update_kind'))
            pointer.kind='invented'
        else:
            task=await db.get(AgentTask,owned.task_id)
            other=AgentTask(initiator_id=owned.user_id,executor_user_id=owned.user_id,preferred_installation_id=owned.plugin_id,
                target_capa_id=task.target_capa_id,factory_id=task.factory_id,request_key=uuid4().hex,status='ready')
            db.add(other); await db.flush()
            if corruption=='foreignmessage': message.task_id=other.task_id
            elif corruption=='foreignrun':
                run=AgentRun(task_id=other.task_id,installation_id=owned.plugin_id,plugin_version='1.0.0',status='completed')
                db.add(run); await db.flush(); pointer.kind='finish'; pointer.object_id=run.run_id
            else:
                from app.models.agent_readonly_control import AgentTaskControl
                row=AgentTaskControl(task_id=other.task_id,key='foreign',action='cancel')
                db.add(row); await db.flush(); pointer.kind='control'; pointer.object_id=row.control_id
        await db.commit()
    with pytest.raises(PermissionError): await activity(owned)


@pytest.mark.asyncio
async def test_actual_sources_results_checkpoint_events_and_ack_receive_only(context_delivery):
    from tests.services.agent_runtime.test_readonly_checkpoints import save
    owned=context_delivery
    await append(owned,'original restricted input')
    batch=await claim(owned); await ack(owned,batch.batch_id,1)
    receipt=(await context(owned))['receipt_id']
    await write(owned,result_body([receipt]))
    await write(owned,event_body([receipt]),True)
    await write(owned,event_body([],key='unsourced',kind='progress'),True)
    await save(owned,[receipt])
    result=await activity(owned)
    kinds=[i['kind'] for i in result['items']]
    assert {'message','ack','event','result','checkpoint'} <= set(kinds)
    ackitem=next(i for i in result['items'] if i['kind']=='ack')
    assert ackitem['data']['state']=='received' and 'executed' not in json.dumps(ackitem)
    unsourced=next(i for i in result['items'] if i['kind']=='event' and not i['data']['sources'])
    assert unsourced['data']['presentation_code']=='plugin_running'
    assert 'RESTRICTED PROGRESS' not in json.dumps(unsourced)
    assert not {'stage','message','completed','total','payload'} & set(unsourced['data'])
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentRun).values(status='completed'))
        await db.execute(update(AgentPluginInstallation).values(enabled=False))
        await db.commit()
    assert (await activity(owned))['items']
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentProjectionReceipt).values(projection_digest='bad'))
        await db.commit()
    with pytest.raises(PermissionError): await activity(owned)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['role','target','source','line'])
async def test_final_read_guard_after_last_materialized_object_real_commit(context_delivery,change):
    from app.models.capa import CAPAEightD
    owned=context_delivery
    await write(owned,result_body([(await context(owned))['receipt_id']]))
    reached,release=asyncio.Event(),asyncio.Event()
    paused=False
    async def pause(): reached.set(); await release.wait()
    def intercept(conn,cursor,statement,parameters,ctx,many):
        nonlocal paused
        # Wait after actual content was selected; first pass can authorize it,
        # but the whole window must reject the subsequently committed withdrawal.
        if not paused and 'FROM agent_results' in statement:
            paused=True; await_only(pause())
    event.listen(owned.engine.sync_engine,'after_cursor_execute',intercept)
    future=asyncio.create_task(activity(owned))
    try:
        await asyncio.wait_for(reached.wait(),10)
        async with owned.factory(binding=owned.binding) as writer:
            if change=='role': await writer.execute(update(RolePermission).where(RolePermission.role_id==owned.role_id,RolePermission.module=='capa').values(permission_level=0))
            elif change=='source': await writer.execute(update(AgentProjectionReceipt).values(projection_digest='bad'))
            elif change=='line':
                from app.models.product_line import ProductLine
                line=ProductLine(code='NO-ACCESS',name='withdrawn line',factory_id=owned.factory_id)
                writer.add(line); await writer.flush()
                await writer.execute(update(RoleDefinition).where(RoleDefinition.id==owned.role_id).values(bypass_row_level_security=False))
                await writer.execute(update(CAPAEightD).values(product_line_code=line.code))
                await writer.execute(delete(UserProductLine).where(UserProductLine.user_id==owned.user_id))
            else:
                target=await writer.scalar(select(CAPAEightD))
                other=CAPAEightD(document_no='8D-MOVED',title='Moved',factory_id=target.factory_id,product_line_code=target.product_line_code)
                writer.add(other); await writer.flush()
                await writer.execute(update(AgentTask).where(AgentTask.task_id==owned.task_id).values(target_capa_id=other.report_id))
            await writer.commit()
        release.set()
        with pytest.raises((PermissionError,LookupError)): await asyncio.wait_for(future,10)
    finally:
        release.set(); await asyncio.gather(future,return_exceptions=True)
        event.remove(owned.engine.sync_engine,'after_cursor_execute',intercept)


@pytest.mark.asyncio
async def test_directory_canonical_current_target_and_safe_read_only(ready_owned):
    owned=ready_owned
    async with owned.factory(binding=owned.binding) as db:
        plugin=await db.get(AgentPluginInstallation,owned.plugin_id)
        plugin.manifest={**plugin.manifest,'optional_capabilities':['unknown.optional.v1']}
        await db.commit()
    result=await directory(owned)
    assert result=={'items':[{'installation_id':str(owned.plugin_id),'plugin_key':'owned','plugin_version':'1.0.0'}]}
    assert 'secret' not in json.dumps(result) and 'manifest' not in json.dumps(result)
    async with owned.factory(binding=owned.binding) as db:
        assert await db.scalar(select(func.count()).select_from(AgentTask))==1
        assert await db.scalar(select(func.count()).select_from(AgentTaskGrant))==1
        await db.execute(update(AgentPluginGrant).values(enabled=False)); await db.commit()
    assert await directory(owned)=={'items':[]}


@pytest.mark.asyncio
async def test_directory_default_deny_empty_even_enabled_actual_grant(committed_runtime):
    owned=committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        plugin=await db.get(AgentPluginInstallation,owned.plugin_id)
        task=await db.get(AgentTask,owned.task_id)
        plugin.manifest={'protocol_versions':['1'],'required_capabilities':[task_service.TARGET_SUMMARY]}
        db.add(AgentPluginGrant(grant_id=uuid4(),installation_id=owned.plugin_id,capability_id=task_service.TARGET_SUMMARY,
            factory_ids=[str(task.factory_id)],enabled=True,granted_by=owned.user_id))
        await db.commit()
    assert await directory(owned)=={'items':[]}


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['disabled','required','malformed','factory','line','version'])
async def test_directory_rechecks_actual_installation_grants_and_pinned_manifest(ready_owned,change):
    owned=ready_owned
    assert (await directory(owned))['items']
    async with owned.factory(binding=owned.binding) as db:
        plugin=await db.get(AgentPluginInstallation,owned.plugin_id)
        grant=await db.scalar(select(AgentPluginGrant))
        if change=='disabled': plugin.enabled=False
        elif change=='required': plugin.manifest={**plugin.manifest,'required_capabilities':[task_service.TARGET_SUMMARY,'unknown.v1']}
        elif change=='malformed': plugin.manifest={'protocol_versions':['unsupported']}
        elif change=='factory': grant.factory_ids=[str(uuid4())]
        elif change=='line': grant.product_line_codes=['other']
        else:
            plugin.plugin_version='2.0.0'
            plugin.manifest={'protocol_versions':['1'],'required_capabilities':['unknown.version.v1']}
        await db.commit()
    assert await directory(owned)=={'items':[]}


@pytest.mark.asyncio
async def test_control_activity_uses_actual_origin_and_resulting_run(context_delivery):
    from tests.services.agent_runtime.test_readonly_checkpoints import save, restart
    from tests.services.agent_runtime.test_task_controls import control
    owned=context_delivery
    await append(owned,'input'); batch=await claim(owned); await ack(owned,batch.batch_id,1)
    checkpoint=await save(owned,[(await context(owned))['receipt_id']])
    await control(owned,'pause',key='pause',epoch=1)
    page=await activity(owned)
    paused=next(i for i in page['items'] if i['kind']=='control')
    assert paused['data']['run_id']==str(owned.run_id)
    assert paused['data']['resulting_run_id']==str(owned.run_id)
    await restart(owned,UUID(checkpoint['checkpoint_id']))
    page=await activity(owned)
    assert page['run_id']!=str(owned.run_id) and page['lease_epoch']==0
    assert [i['data']['action'] for i in page['items'] if i['kind']=='control']==['pause','restart']


@pytest.mark.asyncio
async def test_receipts_reloaded_after_last_window_object_materialization(context_delivery):
    owned=context_delivery
    await write(owned,result_body([(await context(owned))['receipt_id']]))
    await write(owned,event_body([],key='last',kind='progress'),True)
    reached,release=asyncio.Event(),asyncio.Event()
    calls=0
    async def pause(): reached.set(); await release.wait()
    def intercept(conn,cursor,statement,parameters,ctx,many):
        nonlocal calls
        if 'FROM agent_run_events' in statement:
            calls+=1
            if calls==2: await_only(pause())
    event.listen(owned.engine.sync_engine,'after_cursor_execute',intercept)
    future=asyncio.create_task(activity(owned))
    try:
        await asyncio.wait_for(reached.wait(),10)
        async with owned.factory(binding=owned.binding) as writer:
            await writer.execute(update(AgentProjectionReceipt).values(projection_digest='corrupt'))
            await writer.commit()
        release.set()
        with pytest.raises(PermissionError): await asyncio.wait_for(future,10)
    finally:
        release.set(); await asyncio.gather(future,return_exceptions=True)
        event.remove(owned.engine.sync_engine,'after_cursor_execute',intercept)


@pytest.mark.asyncio
async def test_selected_factory_independence_and_current_scope_withdrawal(ready_owned):
    from app.models.factory import Factory,UserFactory
    owned=ready_owned
    await messages(owned,1,1)
    async with owned.factory(binding=owned.binding) as db:
        task=await db.get(AgentTask,owned.task_id)
        selected=Factory(id=uuid4(),name='Other selected factory',code='selected-'+uuid4().hex[:8])
        db.add(selected); await db.flush()
        await db.execute(delete(RolePermission).where(RolePermission.role_id==owned.role_id,RolePermission.module=='group'))
        await db.execute(update(RoleDefinition).where(RoleDefinition.id==owned.role_id).values(bypass_row_level_security=False))
        await db.execute(update(User).where(User.user_id==owned.user_id).values(factory_id=selected.id))
        await db.execute(delete(UserFactory).where(UserFactory.user_id==owned.user_id))
        db.add_all([UserFactory(user_id=owned.user_id,factory_id=selected.id),UserFactory(user_id=owned.user_id,factory_id=task.factory_id)])
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id==owned.user_id))
        db.add(UserProductLine(user_id=owned.user_id,product_line_code='DC-DC-100'))
        await db.commit()
        scope=RequestScope(FactoryScope([selected.id,task.factory_id],selected.id),selected.id,
            ProductLineScope('NONE',[]),await db.get(User,owned.user_id))
        assert (await service().list_installations(db,scope,task.target_capa_id))['items']
        assert (await service().get_activity(db,scope,owned.task_id))['items']
        await db.execute(delete(UserFactory).where(UserFactory.user_id==owned.user_id,UserFactory.factory_id==task.factory_id))
        await db.commit()
        with pytest.raises(LookupError): await service().get_activity(db,scope,owned.task_id)
        with pytest.raises(LookupError): await service().list_installations(db,scope,task.target_capa_id)


@pytest.mark.asyncio
async def test_history_retained_generation_disabled_plugin_and_no_read_writes(context_delivery,monkeypatch):
    from app.services.agent_runtime import runtime_access
    from app.services.agent.permissions import catalog
    from app.services.agent.permissions.types import ApprovalFloor
    from types import MappingProxyType
    from tests.services.agent_runtime.test_readonly_checkpoints import save
    owned=context_delivery
    await append(owned,'sensitive preserved history'); batch=await claim(owned); await ack(owned,batch.batch_id,1)
    receipt=(await context(owned))['receipt_id']
    await save(owned,[receipt]); await write(owned,result_body([receipt]))
    await write(owned,event_body([receipt]),True)
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentRun).values(status='completed',lease_expires_at=None))
        await db.execute(update(AgentPluginInstallation).values(enabled=False))
        await db.execute(delete(AgentTaskGrant))
        await db.commit()
    async with owned.engine.begin() as conn:
        await conn.execute(text('UPDATE public.tenants SET generation=generation+1 WHERE id=:id'),{'id':owned.binding.tenant_id})
    owned.binding=replace(owned.binding,generation=owned.binding.generation+1)
    monkeypatch.setattr(runtime_access,'TRUSTED_DELIVERY_DEPLOYMENTS',frozenset())
    monkeypatch.setattr(catalog,'CAPA_CAPABILITIES',MappingProxyType({k:replace(v,approval_floor=ApprovalFloor.DENY) for k,v in catalog.CAPA_CAPABILITIES.items()}))
    writes=[]
    def intercept(conn,cursor,statement,params,ctx,many):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')): writes.append(statement)
    event.listen(owned.engine.sync_engine,'before_cursor_execute',intercept)
    try:
        result=await activity(owned)
        assert {'message','ack','event','result','checkpoint'} <= {i['kind'] for i in result['items']}
    finally:
        event.remove(owned.engine.sync_engine,'before_cursor_execute',intercept)
    assert not writes
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id==owned.role_id,RolePermission.module=='capa').values(permission_level=0)); await db.commit()
    with pytest.raises(PermissionError): await activity(owned,window_end_sequence=result['window_end_sequence'])


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['factory','line'])
async def test_current_factory_line_withdrawal_after_last_object_denies_whole_page(context_delivery,change):
    from app.models.factory import UserFactory
    from app.models.capa import CAPAEightD
    from app.models.product_line import ProductLine
    owned=context_delivery
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(delete(RolePermission).where(RolePermission.role_id==owned.role_id,RolePermission.module=='group'))
        await db.execute(update(RoleDefinition).where(RoleDefinition.id==owned.role_id).values(bypass_row_level_security=False))
        await db.execute(delete(UserFactory).where(UserFactory.user_id==owned.user_id))
        db.add(UserFactory(user_id=owned.user_id,factory_id=owned.factory_id))
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id==owned.user_id))
        db.add(UserProductLine(user_id=owned.user_id,product_line_code='DC-DC-100'))
        db.add(ProductLine(code='ACTIVITY-WITHDRAWN',name='Other line',factory_id=owned.factory_id))
        await db.commit()
    await write(owned,result_body([(await context(owned))['receipt_id']]))
    await write(owned,event_body([],key='last',kind='progress'),True)
    reached,release=asyncio.Event(),asyncio.Event(); calls=0
    async def pause(): reached.set(); await release.wait()
    def intercept(conn,cursor,statement,parameters,ctx,many):
        nonlocal calls
        if 'FROM agent_run_events' in statement:
            calls+=1
            if calls==2: await_only(pause())
    event.listen(owned.engine.sync_engine,'after_cursor_execute',intercept)
    future=asyncio.create_task(activity(owned))
    try:
        await asyncio.wait_for(reached.wait(),10)
        async with owned.factory(binding=owned.binding) as writer:
            if change=='factory':
                # Remove both membership and the legitimate home-factory fallback.
                await writer.execute(delete(UserFactory).where(UserFactory.user_id==owned.user_id,UserFactory.factory_id==owned.factory_id))
                await writer.execute(update(User).where(User.user_id==owned.user_id).values(factory_id=None))
            else: await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id==owned.report_id).values(product_line_code='ACTIVITY-WITHDRAWN'))
            await writer.commit()
        release.set()
        with pytest.raises((PermissionError,LookupError)): await asyncio.wait_for(future,10)
    finally:
        release.set(); await asyncio.gather(future,return_exceptions=True)
        event.remove(owned.engine.sync_engine,'after_cursor_execute',intercept)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['disabled','grant','role'])
async def test_directory_committed_revocation_during_grants_read(ready_owned,change):
    owned=ready_owned
    reached,release=asyncio.Event(),asyncio.Event(); paused=False
    async def pause(): reached.set(); await release.wait()
    def intercept(conn,cursor,statement,parameters,ctx,many):
        nonlocal paused
        if not paused and 'FROM agent_plugin_grants' in statement:
            paused=True; await_only(pause())
    event.listen(owned.engine.sync_engine,'after_cursor_execute',intercept)
    future=asyncio.create_task(directory(owned))
    try:
        await asyncio.wait_for(reached.wait(),10)
        async with owned.factory(binding=owned.binding) as writer:
            if change=='disabled': await writer.execute(update(AgentPluginInstallation).values(enabled=False))
            elif change=='grant': await writer.execute(update(AgentPluginGrant).values(enabled=False))
            else: await writer.execute(update(RolePermission).where(RolePermission.role_id==owned.role_id,RolePermission.module=='capa').values(permission_level=0))
            await writer.commit()
        release.set()
        if change=='role':
            with pytest.raises(PermissionError): await asyncio.wait_for(future,10)
        else: assert await asyncio.wait_for(future,10)=={'items':[]}
    finally:
        release.set(); await asyncio.gather(future,return_exceptions=True)
        event.remove(owned.engine.sync_engine,'after_cursor_execute',intercept)


@pytest.mark.asyncio
@pytest.mark.parametrize("change",["target_line","disabled","grant","version"])
async def test_directory_second_materialization_target_line_move_recomputes_actual_grants(ready_owned,change):
    from app.models.capa import CAPAEightD
    from app.models.product_line import ProductLine
    owned=ready_owned
    async with owned.factory(binding=owned.binding) as db:
        target=await db.scalar(select(CAPAEightD))
        db.add(ProductLine(code='DIRECTORY-MOVED',name='User-visible new target line',factory_id=target.factory_id))
        await db.commit()
    reached,release=asyncio.Event(),asyncio.Event(); calls=0
    async def pause(): reached.set(); await release.wait()
    def intercept(conn,cursor,statement,params,ctx,many):
        nonlocal calls
        if 'FROM agent_plugin_grants' in statement:
            calls+=1
            if calls==2: await_only(pause())
    event.listen(owned.engine.sync_engine,'after_cursor_execute',intercept)
    future=asyncio.create_task(directory(owned))
    try:
        await asyncio.wait_for(reached.wait(),10)
        async with owned.factory(binding=owned.binding) as writer:
            # User remains authorized through actual ALL product-line scope.
            # Only the actual canonical plugin grant is now out of target scope.
            if change=='target_line': await writer.execute(update(CAPAEightD).values(product_line_code='DIRECTORY-MOVED'))
            elif change=='disabled': await writer.execute(update(AgentPluginInstallation).values(enabled=False))
            elif change=='grant': await writer.execute(update(AgentPluginGrant).values(enabled=False))
            else: await writer.execute(update(AgentPluginInstallation).values(plugin_version='2.0.0',manifest={'protocol_versions':['1'],'required_capabilities':['unknown.version.v1']}))
            await writer.commit()
        release.set()
        assert await asyncio.wait_for(future,10)=={'items':[]}
    finally:
        release.set(); await asyncio.gather(future,return_exceptions=True)
        event.remove(owned.engine.sync_engine,'after_cursor_execute',intercept)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['checkpoint_link','checkpoint_coordinate','checkpoint_digest','restart_origin'])
async def test_final_checkpoint_metadata_and_restart_origin_match_returned_actual_sources(context_delivery,change):
    from app.models.agent_readonly_control import AgentReadonlyCheckpoint,AgentCheckpointReceipt
    from tests.services.agent_runtime.test_readonly_checkpoints import save,restart
    from tests.services.agent_runtime.test_task_controls import control
    owned=context_delivery
    await append(owned,'input'); batch=await claim(owned); await ack(owned,batch.batch_id,1)
    first=(await context(owned))['receipt_id']; second=(await context(owned))['receipt_id']
    checkpoint=await save(owned,[first])
    if change=='restart_origin':
        await control(owned,'pause',key='pause',epoch=1)
        restarted=await restart(owned,UUID(checkpoint['checkpoint_id']))
        async with owned.factory(binding=owned.binding) as db:
            marker=AgentRunEvent(task_id=owned.task_id,run_id=restarted.run_id,event_type='progress',payload={},idempotency_key='last')
            db.add(marker); await db.flush()
            sequence=await db.scalar(select(func.max(AgentTaskUpdate.sequence)).where(AgentTaskUpdate.task_id==owned.task_id))
            db.add(AgentTaskUpdate(task_id=owned.task_id,sequence=sequence+1,kind='event',object_id=marker.event_id)); await db.commit()
    else: await write(owned,event_body([],key='last',kind='progress'),True)
    reached,release=asyncio.Event(),asyncio.Event(); calls=0
    async def pause(): reached.set(); await release.wait()
    def intercept(conn,cursor,statement,params,ctx,many):
        nonlocal calls
        if 'FROM agent_run_events' in statement:
            calls+=1
            if calls==2: await_only(pause())
    event.listen(owned.engine.sync_engine,'after_cursor_execute',intercept)
    # For restart isolate the actual control + last progress; no CP item can
    # accidentally cover the separately required origin consistency check.
    future=asyncio.create_task(activity(owned,page_size=2 if change=='restart_origin' else 50))
    try:
        await asyncio.wait_for(reached.wait(),10)
        async with owned.factory(binding=owned.binding) as writer:
            cp=await writer.get(AgentReadonlyCheckpoint,UUID(checkpoint['checkpoint_id']))
            if change=='checkpoint_link':
                await writer.execute(delete(AgentCheckpointReceipt).where(AgentCheckpointReceipt.checkpoint_id==cp.checkpoint_id))
                writer.add(AgentCheckpointReceipt(checkpoint_id=cp.checkpoint_id,receipt_id=UUID(second)))
            elif change=='checkpoint_coordinate': cp.accepted_message_seq=0
            elif change=='checkpoint_digest': await writer.execute(update(AgentProjectionReceipt).where(AgentProjectionReceipt.receipt_id==UUID(first)).values(projection_digest='b'*64))
            else:
                other=AgentRun(task_id=owned.task_id,installation_id=owned.plugin_id,plugin_version='1.0.0',status='completed',lease_epoch=cp.lease_epoch)
                writer.add(other); await writer.flush()
                receipt=AgentProjectionReceipt(task_id=owned.task_id,run_id=other.run_id,lease_epoch=cp.lease_epoch,
                    tenant_generation=cp.tenant_generation,source_capa_id=owned.report_id,projection_id=task_service.TARGET_SUMMARY,
                    projection_digest='b'*64,data_class='internal')
                writer.add(receipt); await writer.flush()
                cp.run_id=other.run_id
                await writer.execute(delete(AgentCheckpointReceipt).where(AgentCheckpointReceipt.checkpoint_id==cp.checkpoint_id))
                writer.add(AgentCheckpointReceipt(checkpoint_id=cp.checkpoint_id,receipt_id=receipt.receipt_id))
            await writer.commit()
        release.set()
        with pytest.raises(PermissionError): await asyncio.wait_for(future,10)
    finally:
        release.set(); await asyncio.gather(future,return_exceptions=True)
        event.remove(owned.engine.sync_engine,'after_cursor_execute',intercept)
