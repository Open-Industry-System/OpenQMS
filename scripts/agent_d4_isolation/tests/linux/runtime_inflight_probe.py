"""Real two-unit controller crash; explicit test-only list visibility overlay.

The unchanged receiver is truly created but never started. Acceptance is only
an external witness, never create-convergence authority. No platform secrets.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import sys
import time
import types
LABEL='org.openqms.d4.nonce'

class InflightFailure(Exception):pass

def require(ok,code):
    if not ok:raise InflightFailure(code)

BOUNDARY_SOURCE='''
def _boundary_require(ok):
    if not ok:raise ValueError('inflight_scope_invalid')

def accepted_boundary(original,nonce,image,api,deadline,publish,pause):
    cid=original(nonce,image,api,deadline)
    _boundary_require(type(cid)is str and re.fullmatch('[a-f0-9]{64}',cid))
    publish({'id':cid,'nonce':nonce,'accepted_ns':time.monotonic_ns()})
    pause()
    raise ValueError('accepted_create_must_not_return')

def publish_marker(root,value):
    temporary=root/'.accepted-marker.tmp'
    target=root/'accepted-marker.json'
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        raw=json.dumps(value,sort_keys=True).encode()
        _boundary_require(os.write(fd,raw)==len(raw))
        os.fsync(fd)
    finally:os.close(fd)
    try:
        os.link(temporary,target,follow_symlinks=False)
        directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:temporary.unlink()

def visibility_boundary(original,nonce,own,deadline,hidden,role,record):
    _boundary_require(nonce==own and role in ('launch','controller','watchdog','stop','maintain'))
    actual=original(nonce,deadline)
    returned=() if hidden else actual
    record({'role':role,'actual_count':len(actual),'returned_count':len(returned)})
    return returned
'''
exec(compile(BOUNDARY_SOURCE,'<fixed-inflight-boundaries>','exec'))


def hook_source(nonce):
    require(type(nonce)is str and re.fullmatch('[a-f0-9]{64}',nonce),'hook_nonce_invalid')
    return '''# TEST ONLY: this private deployment; never installed in production.
import os, json
import os as _io, sys as _is, json as _ij, time, re
from pathlib import Path as _IP
'''+BOUNDARY_SOURCE+'''
if len(_is.argv)==4 and _is.argv[1] in ('launch','controller','watchdog','stop','maintain'):
    if _io.geteuid()!=0:raise ValueError('inflight_root_required')
    _root=_IP(__file__).absolute().parents[2]
    _own='''+repr(nonce)+'''
    _role=_is.argv[1]
    if _is.argv[2]!='--nonce' or _is.argv[3]!=_own:raise ValueError('inflight_scope_invalid')
    _is.path.insert(0,str(_root))
    from agent_d4_isolation.linux_engine import EngineClient as _IE
    def _record_visibility(value):
        fd=_io.open(_root/'visibility.jsonl',_io.O_WRONLY|_io.O_CREAT|_io.O_APPEND|_io.O_NOFOLLOW,0o600)
        try:
            raw=(_ij.dumps(value,sort_keys=True)+'\\n').encode()
            if _io.write(fd,raw)!=len(raw):raise ValueError('inflight_record_failed')
            _io.fsync(fd)
        finally:_io.close(fd)
    _original_list=_IE.list_by_nonce
    def _inflight_list(self,_nonce,deadline_ns):
        return visibility_boundary(lambda nonce,deadline:_original_list(self,nonce,deadline),
            _nonce,_own,deadline_ns,(_root/'visibility-hidden').exists(),_role,_record_visibility)
    _IE.list_by_nonce=_inflight_list
    if _role=='controller':
        _original_create=_IE.create
        def _publish_accepted(value):
            publish_marker(_root,value)
        def _pause_accepted():
            while True:time.sleep(1)
        def _inflight_create(self,_nonce,image_id,api_container_id,deadline_ns):
            if not (_role=='controller' and _nonce==_own):raise ValueError('inflight_scope_invalid')
            return accepted_boundary(lambda nonce,image,api,deadline:_original_create(self,nonce,image,api,deadline),
                _nonce,image_id,api_container_id,deadline_ns,_publish_accepted,_pause_accepted)
        _IE.create=_inflight_create
'''


def register_candidate(items,cid,nonce,persist):
    require(type(cid)is str and re.fullmatch('[a-f0-9]{64}',cid) and type(nonce)is str and re.fullmatch('[a-f0-9]{64}',nonce),'candidate_invalid')
    if not any(item['id']==cid for item in items):items.append({'id':cid,'nonce':nonce})
    persist()


def verify_unknown(journal,state,deadline):
    require(journal['state']!='closed','bad_intent_closed')
    require(state['invalidated']is True and state['create_converged']is False,'bad_convergence_or_gate')
    require(state['first_stdin_ns']is None,'secret_started')
    require(state['deadline_ns']==deadline,'original_deadline_extended')


def verify_combined_gate(admission_allowed,journal_allowed,invalidated):
    require(admission_allowed is False and not(journal_allowed and not invalidated),'unknown_gate_open')

def created_fact(raw):
    state=raw['State']
    require(state['Running']is False and state['Pid']==0 and state['Status']=='created' and
        re.fullmatch(r'0001-01-01T00:00:00(?:\.0+)?Z',state['StartedAt']),'target_was_started')
    return {'id':raw['Id'],'pid':state['Pid'],'running':state['Running'],'status':state['Status'],'started_at':state['StartedAt']}


def cleanup_created(item,engine,collector,image_id,absent):
    raw=engine.inspect(item['id'],time.monotonic_ns()+1_000_000_000)
    require(raw['Id']==item['id'] and raw['Image']==image_id and raw['Config']['Labels']=={LABEL:item['nonce']},'cleanup_identity_mismatch')
    created_fact(raw)
    require(collector.verify_created(item['nonce'],item['id'],time.monotonic_ns()+1_000_000_000),'cleanup_recipe_unverified')
    engine.remove(item['id'],time.monotonic_ns()+1_000_000_000);absent(item['id'])


def helpers():
    fault=types.ModuleType('_inflight_fault_helpers')
    fault.__dict__.update(PACKAGE_B64=PACKAGE_B64,PACKAGE_SHA256=PACKAGE_SHA256,
        WIRING_PROBE_SOURCE=WIRING_PROBE_SOURCE,WIRE_FIXTURE_SOURCE=WIRE_FIXTURE_SOURCE)
    exec(compile(FAULT_PROBE_SOURCE,'<inflight-fault-helpers>','exec'),fault.__dict__)
    H=fault.helpers();fault.H,fault.UNITS=H,H.UNITS
    return H,fault


def main(image_tag):
    require(os.geteuid()==0 and type(image_tag)is str and image_tag and not image_tag.startswith('-'),'root_or_image_invalid')
    H,F=helpers()
    receipt=dict(verified=False,failure_code=None,resources_cleaned=False,registration_retained=True,
        bad_initial_record_retained=False,nonce=H.NONCE,root=str(H.ROOT),units=list(H.UNITS),
        bundle_sha256=PACKAGE_SHA256,inflight_sha256=INFLIGHT_SHA256,
        timing_model='real_controller_accepted_create_crash_with_test_only_list_visibility',
        secret_bytes_written=0,api_create_pending=False,create_pending=False,registry=[],hidden_empty_rounds=0,observer_rounds=[],stage='package')
    engine=collector=None;image_id=api_id=None;items=[];target=None
    def persist():receipt['registry']=list(items);H.record_receipt(receipt)
    entry=H.ROOT/'agent_d4_isolation/deploy/runtime_entry.py'
    def command(role):
        result=H.run(['/usr/bin/python3','-I','-S','-B',str(entry),role,'--nonce',H.NONCE],timeout=12,check=False)
        require(result.returncode in (0,1) and result.stdout.decode('ascii').strip()=='isolation_unknown','fixed_manager_command_failed')
        return 'isolation_unknown'
    def raw(cid):return engine.inspect(cid,time.monotonic_ns()+1_000_000_000)
    def session_state():
        from agent_d4_isolation.runtime_supervisor import state_call
        return state_call(lambda:store.read(H.NONCE),time.monotonic_ns()+500_000_000)
    def blocked(original_deadline):
        from agent_d4_isolation.journal import SessionBlocked
        journal=H.safe_read(H.ROOT/'state/journal'/(H.NONCE+'.json'))
        state=session_state();verify_unknown(journal,state,original_deadline)
        journal_allowed=journal_api.delivery_gate(H.NONCE).allowed
        verify_combined_gate(journal_api.admission().may_open_session,journal_allowed,state['invalidated'])
        receipt['combined_gate_evidence']={'journal_allowed':journal_allowed,'registration_invalidated':state['invalidated']}
        try:journal_api.record_intent(secrets.token_hex(32))
        except SessionBlocked:pass
        else:raise InflightFailure('new_intent_allowed')
        require(H.docker('logs',api_id).stdout.decode('ascii').splitlines()==['ready'],'secret_or_business_request_seen')
        return journal,state
    def visibility():
        path=H.ROOT/'visibility.jsonl'
        if not path.exists():return []
        data=None
        if data is None:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            try:
                info=os.fstat(fd);require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600 and info.st_size<=65536,'visibility_file_invalid')
                data=os.read(fd,65537);require(len(data)<=65536,'visibility_limit')
            finally:os.close(fd)
            data=[json.loads(line) for line in data.splitlines()]
        require(all(set(row)=={'role','actual_count','returned_count'} and row['role'] in ('launch','controller','watchdog','stop','maintain') and type(row['actual_count'])is int and type(row['returned_count'])is int and row['actual_count']>=row['returned_count']>=0 for row in data),'visibility_evidence_invalid')
        return data
    try:
        H.unpack_package();persist()
        receipt['stage']='api'
        image_id,api_id,manifest=F.setup_api(image_tag,receipt)
        hook=hook_source(H.NONCE).encode();original=entry.read_bytes()
        receipt.update(entry_original_sha256=hashlib.sha256(original).hexdigest(),hook_sha256=hashlib.sha256(hook).hexdigest())
        temporary=entry.with_suffix('.inflight-new');H.private_json(H.ROOT/'visibility-hidden',{'hidden':True})
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
        try:
            data=memoryview(hook+original)
            while data:
                count=os.write(fd,data);require(count>0,'entry_overlay_write');data=data[count:]
            os.fsync(fd)
        finally:os.close(fd)
        os.replace(temporary,entry);receipt['entry_test_sha256']=hashlib.sha256(entry.read_bytes()).hexdigest();persist()
        sys.path.insert(0,str(H.ROOT))
        from agent_d4_isolation.linux_engine import EngineClient,EngineError
        from agent_d4_isolation.linux_identity import KernelCollector
        from agent_d4_isolation.runtime_state import StateStore
        from agent_d4_isolation.journal import IntentJournal
        engine=EngineClient();collector=KernelCollector(engine,image_id,api_id)
        bystander_nonce=secrets.token_hex(32);receipt['bystander_create_pending']=True;persist()
        bystander=engine.create(bystander_nonce,image_id,api_id,time.monotonic_ns()+3_000_000_000)
        register_candidate(items,bystander,bystander_nonce,persist);receipt['bystander_create_pending']=False;persist()
        before=created_fact(raw(bystander));api_before=H.inspect(api_id)['State']['StartedAt']
        receipt['stage']='real_launch';receipt['create_pending']=True;persist();command('launch')
        store=StateStore(H.ROOT);journal_api=IntentJournal(store.journal_path)
        receipt['stage']='accepted_marker'
        until=time.monotonic_ns()+5_000_000_000
        while time.monotonic_ns()<until:
            marker=H.safe_read(H.ROOT/'accepted-marker.json')
            if marker:break
            time.sleep(.01)
        else:raise InflightFailure('accepted_marker_deadline')
        require(set(marker)=={'id','nonce','accepted_ns'} and marker['nonce']==H.NONCE and type(marker['accepted_ns'])is int and marker['accepted_ns']>0,'accepted_marker_invalid')
        target=marker['id'];register_candidate(items,target,H.NONCE,persist);receipt['create_pending']=False;persist()
        require(collector.verify_created(H.NONCE,target,time.monotonic_ns()+1_000_000_000),'accepted_recipe_unverified')
        receipt['accepted_object']=created_fact(raw(target));receipt['accepted_ns']=marker['accepted_ns']
        require(set(engine.list_by_nonce(H.NONCE,time.monotonic_ns()+1_000_000_000))=={target},'unhooked_observer_not_real_object')
        initial_state=session_state()
        require(initial_state['first_stdin_ns']is None and initial_state['create_converged']is False,'early_stdin_or_convergence')
        require(journal_api.load(H.NONCE).state=='create_inflight','create_not_inflight_at_crash')
        receipt['stage']='controller_kill'
        watchdog=F.manager_view(H.UNITS[1])
        require(watchdog['ActiveState']=='active' and watchdog['SubState']=='running' and re.fullmatch('[a-f0-9]{32}',watchdog['InvocationID']),'watchdog_not_ready_at_acceptance')
        receipt['watchdog_at_acceptance']={key:watchdog[key] for key in ('ActiveState','SubState','InvocationID')}
        proof=F.signal_unit(H.UNITS[0],signal.SIGKILL)
        require(proof['sent_ns']>=marker['accepted_ns'],'controller_killed_before_acceptance')
        receipt.update(signal_proof=proof,controller_killed_after_acceptance=True);persist()
        F.wait_detected(proof)
        until=time.monotonic_ns()+3_000_000_000
        while time.monotonic_ns()<until:
            state=session_state()
            if state['invalidated']:break
            time.sleep(.01)
        else:raise InflightFailure('crash_did_not_invalidate')
        original_deadline=state['deadline_ns'];receipt['original_reclaim_deadline_ns']=original_deadline
        receipt['stage']='hidden_observations'
        for _ in range(4):
            journal,state=blocked(original_deadline)
            require(set(engine.list_by_nonce(H.NONCE,time.monotonic_ns()+1_000_000_000))=={target},'hidden_object_disappeared')
            require(created_fact(raw(target))==receipt['accepted_object'],'hidden_object_was_modified')
            receipt['observer_rounds'].append(dict(observed_ns=time.monotonic_ns(),actual_count=1,journal_state=journal['state'],invalidated=state['invalidated'],first_stdin_ns=state['first_stdin_ns'],deadline_ns=state['deadline_ns']))
            rows=visibility();empty=[row for row in rows if row['returned_count']==0 and row['actual_count']==1]
            if len(empty)>=3:break
            command('maintain')
        else:raise InflightFailure('three_empty_rounds_missing')
        receipt.update(hidden_empty_rounds=len(empty),hidden_visibility=list(rows))
        H.private_json(H.ROOT/'bad-registration-initial.json',journal)
        H.private_json(H.ROOT/'bad-session-initial.json',state)
        receipt['bad_initial_record_retained']=True;persist()
        receipt['stage']='visible_maintenance'
        (H.ROOT/'visibility-hidden').unlink()
        receipt['infrastructure_result']=command('maintain')
        try:raw(target)
        except EngineError as error:require(str(error)=='engine_not_found','late_absence_unknown')
        else:raise InflightFailure('late_created_not_removed')
        receipt['late_created_removed']=True
        blocked(original_deadline)
        require(created_fact(raw(bystander))==before,'bystander_affected')
        require(H.inspect(api_id)['State']['Running']is True and H.inspect(api_id)['State']['StartedAt']==api_before,'api_affected')
        require(any(row['actual_count']==row['returned_count']==1 and row['role']=='maintain' for row in visibility()),'visible_maintenance_not_observed')
        H.summarize_runtime(receipt)
        receipt['stage']='verified'
        receipt.update(verified=True,bystander_unchanged=True,api_survived=True,first_stdin_ns=state['first_stdin_ns'],create_converged=session_state()['create_converged'])
    except Exception as error:
        receipt['failure_code']=str(error) if type(error)is InflightFailure else 'inflight_probe_failed'
    finally:
        errors=[]
        def attempt(code,call):
            try:return call()
            except Exception:errors.append(code);return None
        attempt('unit_stop_unknown',lambda:H.run(['/usr/bin/systemctl','stop',*H.UNITS],timeout=15,check=False))
        attempt('unit_reset_unknown',lambda:H.run(['/usr/bin/systemctl','reset-failed',*H.UNITS],check=False))
        # Independent enumeration is never hidden. Discover own returned IDs even
        # if the marker/persistence failed, then verify every candidate afresh.
        if engine is not None:
            def discover():
                for cid in engine.list_by_nonce(H.NONCE,time.monotonic_ns()+1_000_000_000):register_candidate(items,cid,H.NONCE,persist)
            attempt('final_discovery_unknown',discover)
        for item in reversed(items):
            def remove(item=item):
                if item['id']==target and receipt.get('late_created_removed'):
                    H.absent(item['id']);return
                cleanup_created(item,engine,collector,image_id,H.absent)
            attempt('exact_created_cleanup_unknown',remove)
        api_id=api_id or receipt.get('api_id');image_id=image_id or receipt.get('image_id')
        if api_id:
            def api_cleanup():
                H.assert_owned(api_id,image_id,'api');H.docker('rm','-f',api_id);H.absent(api_id)
            attempt('exact_api_cleanup_unknown',api_cleanup)
        def verify_absent():
            require(not receipt.get('api_create_pending') and not receipt.get('bystander_create_pending') and not receipt.get('create_pending'),'create_outcome_unknown')
            for nonce in {H.NONCE}|{item['nonce'] for item in items}:
                require(not engine.list_by_nonce(nonce,time.monotonic_ns()+1_000_000_000),'owned_object_remains')
            require(not H.exact_matches(H.SMOKE_LABEL),'api_remains')
            until=time.monotonic_ns()+3_000_000_000
            while True:
                if all(F.manager_view(unit)['LoadState']=='not-found' for unit in H.UNITS):break
                require(time.monotonic_ns()<until,'unit_remains');time.sleep(.025)
        attempt('fresh_absence_unknown',verify_absent)
        attempt('final_summary_unknown',lambda:H.summarize_runtime(receipt,'post_cleanup_'))
        def retained():
            require(H.ROOT.exists(),'root_registration_missing')
            if receipt['bad_initial_record_retained']:
                require((H.ROOT/'bad-registration-initial.json').is_file() and (H.ROOT/'bad-session-initial.json').is_file(),'initial_bad_record_missing')
                require(receipt.get('post_cleanup_journal_summary',{}).get('state')!='closed','cleanup_closed_unknown_journal')
        attempt('root_retention_unknown',retained)
        receipt.update(cleanup_errors=errors,resources_cleaned=not errors,registration_retained=True)
        if errors:receipt['failure_code']=receipt['failure_code'] or 'inflight_cleanup_failed'
        attempt('receipt_write_unknown',persist)
        if errors:receipt.update(resources_cleaned=False,failure_code=receipt['failure_code'] or 'inflight_cleanup_failed')
        print(json.dumps(receipt,sort_keys=True),flush=True)
    require(receipt['verified'] and receipt['resources_cleaned'] and receipt['failure_code']is None,'inflight_not_verified')
    print('runtime_inflight_verified',flush=True)

if __name__=='__main__':
    try:require(len(sys.argv)==2,'image_required');main(sys.argv[1])
    except Exception as error:
        print('runtime_inflight_failed:'+(str(error) if type(error)is InflightFailure else 'probe_failed'),flush=True)
        raise SystemExit(1)
