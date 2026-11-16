"""Bounded D4 rounds retain context only inside the platform."""
import asyncio
import json
import time
from uuid import UUID, uuid4

from app.models.audit import AuditLog
from app.services.agent import provider_adapter
from app.services.agent_runtime import model_egress, runtime_access, model_workflow
from app.services import capa_d4_candidates as candidates

UNAVAILABLE = candidates.UNAVAILABLE


def _active(state):
    if state.stopped or state.deadline<=time.monotonic():
        state.stopped=True
        raise PermissionError(UNAVAILABLE)


async def send_context(db, identity, *, snapshot, messages, tools):
    current = await candidates.current_inputs(db, identity, snapshot=snapshot, lock=True)
    row = await model_egress.task_deployment(db, current.task, lock=True)
    resolver = db.info.get('r5_credential_resolver')
    if not callable(resolver):
        raise PermissionError(UNAVAILABLE)
    secret = resolver(row.credential_ref)
    if not isinstance(secret, str) or not secret:
        raise PermissionError(UNAVAILABLE)
    options = dict(transport=model_egress.PinnedTransport(row))
    if model_egress._api_protocol(row) == 'responses':
        options['api_protocol'] = 'responses'
    client = provider_adapter.build_deployment_client(row.provider, row.model, row.base_url, secret, **options)
    attempt_id = uuid4()
    ids = dict(task_id=str(current.task.task_id), run_id=str(current.run.run_id), deployment_id=str(row.deployment_id))
    actor, factory, deployment_id = current.task.executor_user_id, current.task.factory_id, row.deployment_id
    try:
        db.add(AuditLog(log_id=attempt_id, table_name='agent_model_deployments', record_id=deployment_id,
            action='MODEL_EGRESS_ATTEMPT', operated_by=actor, factory_id=factory, changed_fields=ids))
        await db.commit()
        current = await candidates.current_inputs(db, current, snapshot=snapshot, lock=True)
        from app.services.egress_guard import suppress_sdk_payload_logs
        with suppress_sdk_payload_logs():
            turn = await provider_adapter.chat_with_tools(client, messages, tools)
        if snapshot is not None:
            await candidates.record_delivery(db, current, snapshot)
        db.add(AuditLog(table_name='agent_model_deployments', record_id=deployment_id,
            action='MODEL_EGRESS_COMPLETED', operated_by=actor, factory_id=factory,
            correlation_id=attempt_id, changed_fields=ids))
        await db.commit()
        result = dict(content=turn.content, tool_calls=turn.tool_calls, deployment_id=deployment_id, version=row.version)
        if getattr(turn, 'response_items', None) is not None:
            result['response_items'] = turn.response_items
    except Exception:
        await db.rollback()
        raise PermissionError(UNAVAILABLE) from None
    finally:
        await client.client.close()
    await candidates.current_inputs(db, current, snapshot=snapshot,lock=True)
    return result


async def infer(db, identity):
    snapshot = await candidates.build_context(db, identity)
    result = await send_context(db, identity, snapshot=snapshot, messages=[
        {'role': 'system', 'content': 'Analyze a D4 root cause hypothesis using only authorized D2/D3 and FMEA facts. Employee confirmation and independent verification are required.'},
        {'role': 'user', 'content': json.dumps(snapshot.context, ensure_ascii=False)}], tools=[])
    result.pop('response_items', None)
    return result


def specs():
    from types import SimpleNamespace
    definitions = [
        ('read_inputs', 'Prepare the currently authorized D2/D3 and FMEA context; content remains inside the platform.', {'type':'object','properties':{},'additionalProperties':False}),
        ('request_supplement', 'Ask for a source-neutral employee instruction.', {'type':'object','properties':{'question':{'type':'string','minLength':1,'maxLength':2000}},'required':['question'],'additionalProperties':False}),
        ('save_candidate', 'Save a hypothesis for employee review, without formal adoption or verification.', {'type':'object','properties':{
            'text': {'type':'string','minLength':1,'maxLength':16384}, 'operation':{'type':'string','enum':['save','alternative','replace']},
            **{k:{'type':'array','items':{'type':'string','maxLength':2000},'maxItems':20} for k in ('supporting','opposing','missing_information')}},
            'required':['text'],'additionalProperties':False})]
    return provider_adapter.tools_schema_for(SimpleNamespace(provider='openai'),
        [SimpleNamespace(name=n, description=d, param_schema=p) for n,d,p in definitions])


def validate_calls(calls, remaining):
    from app.schemas.agent_d4_candidate import D4CandidateCommand
    if not isinstance(calls, list) or len(calls) > remaining:
        raise ValueError(UNAVAILABLE)
    ids = set()
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get('id'),str) or not call['id'] or call['id'] in ids:
            raise ValueError(UNAVAILABLE)
        ids.add(call['id'])
        args = call.get('arguments')
        if not isinstance(args,dict):
            raise ValueError(UNAVAILABLE)
        if call.get('name') == 'read_inputs':
            if args: raise ValueError(UNAVAILABLE)
        elif call.get('name') == 'request_supplement':
            if set(args) != {'question'} or not isinstance(args['question'],str) or not 1 <= len(args['question'].encode()) <= 2000:
                raise ValueError(UNAVAILABLE)
        elif call.get('name') == 'save_candidate':
            if not set(args) <= {'text','operation','supporting','opposing','missing_information'}:
                raise ValueError(UNAVAILABLE)
            values = dict(args)
            if values.get('operation') == 'replace':
                values.update(predecessor_id=UUID(int=1), correction_message_id=UUID(int=1))
            D4CandidateCommand(command_key='validation', **values)
        else:
            raise ValueError(UNAVAILABLE)


async def next_turn(db, identity, turn):
    current = await candidates.current_inputs(db, identity)
    state = model_workflow._round(current)
    async with state.lock:
        _active(state)
        current = await candidates.current_inputs(db, current, snapshot=state.snapshot, lock=True)
        _active(state)
        if turn in state.turns:
            return state.turns[turn]
        if turn != len(state.turns) or any('result' not in call for call in state.calls.values()):
            raise ValueError(UNAVAILABLE)
        await model_workflow._messages(db, current, state)
        messages = [{'role':'system','content':'Use only authorized D2/D3 and FMEA facts. Prepare inputs before saving D4 hypotheses. Never claim verified root cause.'}] + list(state.messages)
        if state.snapshot is not None:
            messages.insert(1, {'role':'user','content':json.dumps(state.snapshot.context, ensure_ascii=False)})
        try:
            response = await asyncio.wait_for(send_context(db,current,snapshot=state.snapshot,messages=messages,tools=specs()),
                timeout=max(.01,state.deadline-__import__('time').monotonic()))
            _active(state)
            validate_calls(response['tool_calls'], model_workflow.LIMIT-len(state.calls))
        except Exception:
            state.stopped=True
            raise PermissionError(UNAVAILABLE) from None
        if state.snapshot is not None:
            state.delivered_signature=state.snapshot.signature
        issued, stored = [], []
        correction = await candidates.bounded_messages(db,current)
        for call in response['tool_calls']:
            binding = None
            if call['name']=='save_candidate' and call['arguments'].get('operation')=='replace':
                if correction is None: raise PermissionError(UNAVAILABLE)
                binding=dict(predecessor_id=correction[1],correction_message_id=correction[0].message_id,accepted_sequence=current.run.accepted_message_seq)
            identifier=uuid4().hex
            state.calls[identifier]=dict(name=call['name'],arguments=call['arguments'],model_id=call['id'],correction=binding)
            issued.append(dict(id=identifier,name=call['name']))
            stored.append(dict(id=call['id'],type='function',function=dict(name=call['name'],arguments=json.dumps(call['arguments'],ensure_ascii=False))))
        assistant=dict(role='assistant',content=response['content'] or None)
        if response.get('response_items') is not None: assistant['_responses_output']=response['response_items']
        if stored: assistant['tool_calls']=stored
        state.messages.append(assistant)
        result=dict(content=response['content'],tool_calls=issued)
        state.turns[turn]=result
        return result


async def execute_tool(db, identity, request):
    from app.schemas.agent_d4_candidate import D4CandidateCommand
    current=await candidates.current_inputs(db,identity)
    state=model_workflow._round(current)
    async with state.lock:
        _active(state)
        current=await candidates.current_inputs(db,current,snapshot=state.snapshot,lock=True)
        _active(state)
        if state.uncertain_id is not None and state.uncertain_id != request.call_id:
            raise PermissionError(UNAVAILABLE)
        call=state.calls.get(request.call_id)
        if call is None: raise PermissionError(UNAVAILABLE)
        if 'result' in call:
            _active(state)
            return call['result']
        args=call['arguments']
        following=[]
        if call['name']=='read_inputs':
            snapshot=await candidates.build_context(db,current)
            if state.snapshot is not None and snapshot.values['input_versions'] != state.snapshot.values['input_versions']:
                raise PermissionError(UNAVAILABLE)
            state.snapshot=snapshot
            # No context body or source coordinates enter the independent child.
            result={'status':'prepared'}
        elif call['name']=='save_candidate':
            if state.snapshot is None or state.delivered_signature != state.snapshot.signature:
                raise PermissionError(UNAVAILABLE)
            correction=call['correction'] or {}
            if correction and current.run.accepted_message_seq != correction['accepted_sequence']:
                raise PermissionError(UNAVAILABLE)
            state.uncertain_id=request.call_id
            saved=await candidates.save_candidate(db,current,D4CandidateCommand(command_key='r6:'+request.call_id,
                **args,**{k:v for k,v in correction.items() if k!='accepted_sequence'}))
            result={'status':'saved','candidate_id':str(saved['candidate_id'])}
        elif call['name']=='request_supplement':
            from app.services.agent_runtime import runtime_messages
            from app.services.agent_runtime.d4_candidate_checkpoints import save_checkpoint
            if 'watermark' not in call:
                cp=await save_checkpoint(db,current)
                state.checkpoint_id=str(cp['checkpoint_id'])
                call['watermark']=current.run.accepted_message_seq
                state.question=args['question']
            batch=await runtime_messages.claim_messages(db,current,20)
            _active(state)
            if not batch.messages: return {'status':'waiting'}
            await runtime_messages.ack_messages(db,current,batch.batch_id,batch.messages[-1].sequence)
            current=await candidates.current_inputs(db,current,snapshot=state.snapshot)
            previous=len(state.messages)
            await model_workflow._messages(db,current,state)
            following=state.messages[previous:]
            del state.messages[previous:]
            if state.accepted<=call['watermark']: return {'status':'waiting'}
            state.question=None
            result={'status':'accepted','accepted_sequence':state.accepted}
        _active(state)
        state.uncertain_id=None
        call['result']=result
        state.messages.append(dict(role='tool',tool_call_id=call['model_id'],content=json.dumps(result)))
        state.deferred_users.extend(following)
        if all('result' in pending for pending in state.calls.values()):
            state.messages.extend(state.deferred_users)
            state.deferred_users.clear()
        await db.commit()
        return result
