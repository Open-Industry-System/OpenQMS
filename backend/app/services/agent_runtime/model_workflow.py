"""Bounded process-local R5 conversations; no caller-supplied messages or results.

Lost process state fails closed. New run/epoch starts a fresh round, preserving
only durable accepted employee messages and CAPA command receipts. Raw questions
and model tool arguments never enter control logs, checkpoints or security audit.
"""
import asyncio
from dataclasses import dataclass, field
import json
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.models.agent_task import AgentTaskMessage
from app.services.agent_runtime import runtime_access, runtime_messages, d5_commands, model_egress
from app.services import capa_d5_proposals

LIMIT = 8
SECONDS = 120
UNAVAILABLE = 'Model workflow unavailable'


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    call_id: str = Field(min_length=1, max_length=100)


@dataclass
class Round:
    deadline: float = field(default_factory=lambda: time.monotonic()+SECONDS)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    messages: list = field(default_factory=list, repr=False)
    calls: dict = field(default_factory=dict, repr=False)
    turns: dict = field(default_factory=dict, repr=False)
    snapshot: object = field(default=None, repr=False)
    delivered_signature: str | None = None
    deferred_users: list = field(default_factory=list, repr=False)
    accepted: int = 0
    question: str | None = field(default=None, repr=False)
    checkpoint_id: str | None = None
    stopped: bool = False
    token: str = field(default="", repr=False)
    uncertain_id: str | None = None


_rounds = {}
_expired = set()


def _expire(key):
    state = _rounds.pop(key, None)
    if state is not None:
        state.stopped = True
        state.messages.clear()
        state.deferred_users.clear()
        state.calls.clear()
        state.turns.clear()
        state.snapshot = None
        state.delivered_signature = None
        state.token = ''
        state.question = None
    _expired.add(key)


def _key(identity):
    return (identity.binding.tenant_id, identity.run.run_id, identity.run.lease_epoch)


def _round(identity):
    now = time.monotonic()
    for key, value in list(_rounds.items()):
        if value.deadline <= now:
            _expire(key)
    key = _key(identity)
    if key in _expired:
        raise PermissionError(UNAVAILABLE)
    if key not in _rounds:
        raise PermissionError(UNAVAILABLE)
    state = _rounds[key]
    if state.stopped or state.deadline <= now:
        raise PermissionError(UNAVAILABLE)
    return state


def begin_round(identity):
    """Platform-only launch registration, before the verified child receives stdin.

    The HTTP inference caller cannot create state. Lost state requires a new
    managed run/epoch, so process restart cannot reset an old round's budget.
    """
    key = _key(identity)
    if key in _rounds or key in _expired:
        raise PermissionError(UNAVAILABLE)
    _rounds[key] = Round(token=identity._token)
    asyncio.get_running_loop().call_later(SECONDS, _expire, key)


async def _current(db, identity, *, lock=True):
    current = await (runtime_access.lock_runtime_identity(db, identity) if lock else runtime_access.refresh_runtime_identity(db, identity))
    if current.trial is not None and current.trial.profile == model_egress.D4_PROFILE:
        from app.services.capa_d4_candidates import current_inputs
        return await current_inputs(db,current,lock=lock)
    d5_commands.require_r5_admission(current)
    await model_egress.task_deployment(db, current.task, lock=lock)
    from app.services.capa_r6_delivery import require_current_root_use
    await require_current_root_use(db, current)
    return current


async def _messages(db, current, state):
    runtime_access.require_delivery(current, 'restricted', 'raw', controlled_egress=True, delivery_kind='message')
    await runtime_messages.require_accepted_prefix(db, current.task.task_id, current.run.accepted_message_seq)
    rows = list(await db.scalars(select(AgentTaskMessage).where(AgentTaskMessage.task_id==current.task.task_id,
        AgentTaskMessage.state=='accepted', AgentTaskMessage.sequence>state.accepted,
        AgentTaskMessage.sequence<=current.run.accepted_message_seq).order_by(AgentTaskMessage.sequence)))
    for row in rows:
        content = row.content
        if content == 'deliver_d4_root_cause_candidate_v1':
            # Keep the accepted original marker and explain the employee's
            # fixed sidebar action. The model still chooses its own steps.
            content += ('\nEmployee request: Using only the current authorized D4 root cause '
                'and its source evidence, generate actionable D5 corrective-measure proposals '
                'and save suitable proposals to this report using save_proposal for employee review. '
                'Plan the steps yourself and ask for clarification when needed. '
                'Saved proposals require separate employee adoption.')
        state.messages.append({'role':'user','content':content})
    state.accepted = current.run.accepted_message_seq


def _specs():
    empty = {'type':'object','properties':{},'additionalProperties':False}
    definitions = [
        ('read_d4','Read the current authorized D4 root cause and primary source.', empty),
        ('query_source','Query the authorized primary failure cause. No arbitrary source coordinates.',empty),
        ('request_supplement','Ask the employee a question and wait at a checkpoint.',
            {'type':'object','properties':{'question':{'type':'string','minLength':1,'maxLength':2000}},'required':['question'],'additionalProperties':False}),
        ('save_proposal','Save a D5 proposal only with current delivered evidence and bounded employee intent.',
            {'type':'object','properties':{'text':{'type':'string','minLength':1,'maxLength':16384},'operation':{'type':'string','enum':['save','alternative','replace']}},'required':['text'],'additionalProperties':False})]
    from app.services.agent.provider_adapter import tools_schema_for
    return tools_schema_for(SimpleNamespace(provider='openai'), [SimpleNamespace(name=n,description=d,param_schema=p) for n,d,p in definitions])


def _validate_calls(calls, remaining):
    if not isinstance(calls, list) or len(calls)>remaining:
        raise ValueError(UNAVAILABLE)
    ids = set()
    for call in calls:
        name, args = call.get('name'), call.get('arguments')
        if not isinstance(call.get('id'),str) or not call['id'] or call['id'] in ids or not isinstance(args,dict):
            raise ValueError(UNAVAILABLE)
        ids.add(call['id'])
        if name in {'read_d4','query_source'}:
            valid = not args
        elif name == 'request_supplement':
            valid = set(args)=={'question'} and isinstance(args['question'],str) and 1<=len(args['question'].encode())<=2000
        elif name == 'save_proposal':
            valid = {'text'} <= set(args) <= {'text','operation'} and args.get('operation','save') in ('save','alternative','replace') and isinstance(args['text'],str) and bool(args['text'].strip()) and len(args['text'].encode())<=16384
        else:
            valid = False
        if not valid:
            raise ValueError(UNAVAILABLE)


async def next_turn(db, identity, turn):
    current = await _current(db, identity, lock=False)
    state = _round(current)
    async with state.lock:
        if state.stopped or time.monotonic() >= state.deadline:
            raise PermissionError(UNAVAILABLE)
        current = await _current(db, current)
        if state.snapshot is not None:
            await capa_d5_proposals.validate_d5_context_for_release(db,current,snapshot=state.snapshot)
        if turn in state.turns:
            return state.turns[turn]
        if turn != len(state.turns) or any('result' not in call for call in state.calls.values()):
            raise ValueError(UNAVAILABLE)
        await _messages(db, current, state)
        if not state.messages:
            state.messages.append({'role':'user','content':'Discuss the current D5 task.'})
        messages = [{'role':'system','content':'Use only authorized task context. Read evidence before saving D5. Ask for clarification when needed. Arbitrary additional context prevents shared saving.'}]+state.messages
        try:
            response = await asyncio.wait_for(model_egress.send_context(db, current,
                snapshot=state.snapshot, messages=messages, tools=_specs()), timeout=max(.01,state.deadline-time.monotonic()))
            if state.deadline<=time.monotonic() or state.stopped:
                raise PermissionError(UNAVAILABLE)
            _validate_calls(response['tool_calls'], LIMIT-len(state.calls))
        except Exception:
            state.stopped = True
            raise PermissionError(UNAVAILABLE) from None
        if state.snapshot is not None:
            # send_context committed the receipt for THIS exact signed body.
            state.delivered_signature = state.snapshot.signature
        model_calls = response['tool_calls']
        stored = []
        issued = []
        for call in model_calls:
            # Resolve the employee's explicit target at issuance, never when a
            # delayed tool executes. The model cannot supply either identifier.
            correction = None
            if call['name']=='save_proposal' and call['arguments'].get('operation')=='replace':
                current=await _current(db,current)
                if current.run.accepted_message_seq != state.accepted:
                    raise PermissionError(UNAVAILABLE)
                message=await db.scalar(select(AgentTaskMessage).where(
                    AgentTaskMessage.task_id==current.task.task_id,
                    AgentTaskMessage.sequence==state.accepted,
                    AgentTaskMessage.state=='accepted'))
                try:
                    intent=json.loads(message.content)
                    if set(intent)!={'intent','predecessor_id'} or intent['intent']!='replace_d5':
                        raise ValueError(UNAVAILABLE)
                    predecessor=UUID(intent['predecessor_id'])
                except (AttributeError, TypeError, ValueError, KeyError):
                    raise PermissionError(UNAVAILABLE) from None
                from app.schemas.agent_d5_command import D5Command
                command=D5Command(command_key='issuance',text=call['arguments']['text'],operation='replace',
                    predecessor_id=predecessor,correction_message_id=message.message_id)
                await capa_d5_proposals.require_bounded_messages(db,current,command)
                correction={'predecessor_id':predecessor,'correction_message_id':message.message_id,
                    'accepted_sequence':state.accepted}
            identifier = uuid4().hex
            state.calls[identifier] = dict(name=call['name'], arguments=call['arguments'], model_id=call['id'], correction=correction)
            issued.append({'id':identifier, 'name':call['name']})
            stored.append({'id':call['id'],'type':'function','function':{'name':call['name'],'arguments':json.dumps(call['arguments'],ensure_ascii=False)}})
        assistant = {'role':'assistant','content':response['content'] or None}
        if response.get('response_items') is not None:
            assistant['_responses_output'] = response['response_items']
        if stored:
            assistant['tool_calls'] = stored
        state.messages.append(assistant)
        result = {'content':response['content'], 'tool_calls':issued}
        state.turns[turn] = result
        return result


async def execute_tool(db, identity, request):
    if identity.trial is not None and identity.trial.profile == model_egress.D4_PROFILE:
        from app.services.agent_runtime import d4_candidate_workflow
        return await d4_candidate_workflow.execute_tool(db, identity, request)
    current = await _current(db, identity, lock=False)
    state = _round(current)
    async with state.lock:
        if state.stopped or time.monotonic() >= state.deadline:
            raise PermissionError(UNAVAILABLE)
        current = await _current(db, current)
        if state.snapshot is not None:
            await capa_d5_proposals.validate_d5_context_for_release(db,current,snapshot=state.snapshot)
        if state.uncertain_id is not None and request.call_id != state.uncertain_id:
            raise PermissionError(UNAVAILABLE)
        call = state.calls.get(request.call_id)
        if call is None:
            raise PermissionError(UNAVAILABLE)
        if 'result' in call:
            return call['result']
        if time.monotonic()>=state.deadline:
            state.stopped=True
            raise PermissionError(UNAVAILABLE)
        name, args = call['name'], call['arguments']
        following = []
        if name in {'read_d4','query_source'}:
            authority=await runtime_access.authorize_task(db,current.task,current.installation)
            source=authority.current_source
            if source is None or not authority.basis_available:
                result={'status':'missing_basis'}
            else:
                try:
                    snapshot=await capa_d5_proposals.build_d5_context(db,current,source_queries=[dict(
                        projection_id=source.source_projection_id,fmea_id=str(source.fmea_id),node_id=source.cause_node_id)])
                    await capa_d5_proposals.validate_d5_context_for_release(db,current,snapshot=snapshot)
                except PermissionError:
                    # Chat is allowed without basis, but never mint a save grant.
                    await db.rollback()
                    result={'status':'missing_basis'}
                else:
                    if state.snapshot is not None and state.snapshot.signature != snapshot.signature:
                        state.stopped=True
                        raise PermissionError(UNAVAILABLE)
                    state.snapshot=snapshot
                    result={'status':'read','context':snapshot.context}
        elif name=='request_supplement':
            from app.services.agent_runtime import checkpoint_service
            if 'watermark' not in call:
                if state.snapshot is not None and state.delivered_signature == state.snapshot.signature:
                    cp=await checkpoint_service.save_d5_checkpoint(db,current)
                    state.checkpoint_id=str(cp['checkpoint_id']) if isinstance(cp,dict) else str(cp.checkpoint_id)
                call['watermark']=current.run.accepted_message_seq
                state.question=args['question']
            batch=await runtime_messages.claim_messages(db,current,20)
            if not batch.messages:
                return {'status':'waiting'}
            await runtime_messages.ack_messages(db,current,batch.batch_id,batch.messages[-1].sequence)
            current=await _current(db,current)
            previous=len(state.messages)
            await _messages(db,current,state)
            following=state.messages[previous:]
            del state.messages[previous:]
            if state.accepted<=call['watermark']:
                return {'status':'waiting'}
            state.question=None
            result={'status':'accepted','accepted_sequence':state.accepted}
        elif name=='save_proposal':
            from app.schemas.agent_d5_command import D5Command
            # The same opaque issued ID always maps to this original write key.
            state.uncertain_id=request.call_id
            correction=call['correction']
            if correction is not None and current.run.accepted_message_seq != correction['accepted_sequence']:
                raise PermissionError(UNAVAILABLE)
            binding={key:value for key,value in (correction or {}).items() if key!='accepted_sequence'}
            saved=await d5_commands.save_proposal(db,current,D5Command(command_key='r5:'+request.call_id,
                text=args['text'],operation=args.get('operation','save'),**binding))
            result={'status':'saved','proposal_id':str(saved.proposal_id) if hasattr(saved,'proposal_id') else str(saved['proposal_id'])}
        state.uncertain_id=None
        call['result']=result
        state.messages.append({'role':'tool','tool_call_id':call['model_id'],'content':json.dumps(result,ensure_ascii=False)})
        state.deferred_users.extend(following)
        if all('result' in pending for pending in state.calls.values()):
            state.messages.extend(state.deferred_users)
            state.deferred_users.clear()
        await db.commit()
        return result


async def status(db, scope, task_id):
    from app.services.agent_runtime import task_service
    task=await task_service.get_task_for_view(db,scope,task_id)
    # Task view and model binding each recheck current source/employee authority.
    await model_egress.task_deployment(db,task)
    from app.models.agent_task import AgentRun
    run=await db.scalar(select(AgentRun).where(AgentRun.task_id==task_id,AgentRun.status=='active'))
    if run is None:
        return {'status':task.status,'question':None,'checkpoint_id':None}
    state=_rounds.get((db.info['tenant_binding'].tenant_id,run.run_id,run.lease_epoch))
    if state is None or state.deadline<=time.monotonic():
        return {'status':'unavailable','question':None,'checkpoint_id':None}
    current=await runtime_access.verify_runtime_identity(db,state.token,db.info['tenant_binding'])
    current=await _current(db,current)
    if state.snapshot is not None:
        if current.trial is not None and current.trial.profile == model_egress.D4_PROFILE:
            from app.services.capa_d4_candidates import validate_snapshot
            await validate_snapshot(db,current,state.snapshot)
        else:
            await capa_d5_proposals.validate_d5_context_for_release(db,current,snapshot=state.snapshot)
    return {'status':'waiting' if state.question else 'running','question':state.question,'checkpoint_id':state.checkpoint_id}
