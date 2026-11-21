"""Injected per-deployment management I/O loss, with the actual two-unit chain.

No shared daemon is stopped. The independent observer keeps an unmodified
EngineClient and original kernel references. Only fixed test entry wrappers are
installed in this fresh root-private deployment; receiver recipe is unchanged.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

class OutageFailure(Exception):pass

def require(ok,code):
    if not ok:raise OutageFailure(code)

BOUNDARY_SOURCE='''
def request_boundary(original,failed,error_type,*args,**kwargs):
    if failed:raise error_type('engine_unavailable')
    return original(*args,**kwargs)

def observe_kernel_kill(original,device,inode,record):
    result=original()
    record({'role':'watchdog','cgroup_dev':device,'cgroup_inode':inode,'kill_returned':True})
    return result
'''
exec(compile(BOUNDARY_SOURCE,'<outage-fixed-boundaries>','exec'))


def hook_source(nonce):
    require(type(nonce)is str and re.fullmatch('[a-f0-9]{64}',nonce),'hook_nonce_invalid')
    return '''# TEST ONLY: one root-private management deployment, never production.
import os as _eo,sys as _es,json as _ej,time as _et
from pathlib import Path as _EP
'''+BOUNDARY_SOURCE+'''
if len(_es.argv)==4 and _es.argv[1] in ('launch','controller','watchdog','stop','maintain'):
    if _eo.geteuid()!=0:raise ValueError('outage_root_required')
    _root=_EP(__file__).absolute().parents[2]
    _own='''+repr(nonce)+'''
    _role=_es.argv[1]
    if _es.argv[2]!='--nonce' or _es.argv[3]!=_own:raise ValueError('outage_scope_invalid')
    _es.path.insert(0,str(_root))
    from agent_d4_isolation.linux_engine import EngineClient as _EE,EngineError as _EError
    def _outage_record(name,row):
        if name not in ('engine-outage-hits.jsonl','watchdog-kernel-kill.jsonl'):raise ValueError('outage_record_scope')
        fd=_eo.open(_root/name,_eo.O_WRONLY|_eo.O_CREAT|_eo.O_APPEND|_eo.O_NOFOLLOW,0o600)
        try:
            raw=(_ej.dumps(row,sort_keys=True)+'\\n').encode()
            if _eo.write(fd,raw)!=len(raw):raise ValueError('outage_record_failed')
            _eo.fsync(fd)
        finally:_eo.close(fd)
    _original_request=_EE._request
    _outage_hit=False
    def _outage_request(self,method,path,deadline_ns,**kwargs):
        global _outage_hit
        failed=(_root/'engine-outage.flag').exists()
        if failed and not _outage_hit:
            _outage_record('engine-outage-hits.jsonl',{'role':_role,'event':'engine_unavailable','observed_ns':_et.monotonic_ns()})
            _outage_hit=True
        return request_boundary(lambda *args,**kw:_original_request(self,*args,**kw),failed,_EError,
                                method,path,deadline_ns,**kwargs)
    _EE._request=_outage_request
    if _role=='watchdog':
        from agent_d4_isolation.linux_identity import _Cgroup as _EC
        _original_kill=_EC.kill
        def _watchdog_kill(self):
            fact=_eo.fstat(self.fd)
            return observe_kernel_kill(lambda:_original_kill(self),fact.st_dev,fact.st_ino,
                lambda row:_outage_record('watchdog-kernel-kill.jsonl',row))
        _EC.kill=_watchdog_kill
'''


def verify_boundary(state,journal,before_marker,after_marker,first_stdin):
    require(state['invalidated']is True and state['first_stdin_ns']==first_stdin,'gate_reopened_or_stdin_changed')
    require(journal['state']!='closed' and journal['closed_by']is None,'outage_fabricated_convergence')
    require(before_marker==after_marker,'stdin_replayed')


def verify_watchdog_kill(rows,snapshot):
    require(any(row=={'role':'watchdog','cgroup_dev':snapshot['cgroup_dev'],
        'cgroup_inode':snapshot['cgroup_inode'],'kill_returned':True} for row in rows),'watchdog_original_kill_missing')


def helpers():
    interruptions=types.ModuleType('_outage_interruption_helpers')
    interruptions.__dict__.update(PACKAGE_B64=PACKAGE_B64,PACKAGE_SHA256=PACKAGE_SHA256,
        WIRING_PROBE_SOURCE=WIRING_PROBE_SOURCE,FAULT_PROBE_SOURCE=FAULT_PROBE_SOURCE,WIRE_FIXTURE_SOURCE=WIRE_FIXTURE_SOURCE)
    exec(compile(INTERRUPTION_PROBE_SOURCE,'<outage-interruption-helpers>','exec'),interruptions.__dict__)
    F,H=interruptions.helpers()
    return interruptions,F,H


def read_rows(root,name):
    require(name in ('engine-outage-hits.jsonl','watchdog-kernel-kill.jsonl'),'record_name_invalid')
    path=root/name
    if not path.exists():return []
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd);require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and info.st_size<=8192,'record_file_invalid')
        raw=os.read(fd,8193);require(len(raw)<=8192,'record_limit')
    finally:os.close(fd)
    return [json.loads(line) for line in raw.splitlines()]


def main(image):
    require(os.geteuid()==0 and type(image)is str and image and not image.startswith('-'),'root_or_image_invalid')
    I,F,H=helpers()
    receipt=dict(verified=False,failure_code=None,resources_cleaned=False,registration_retained=True,
        bad_initial_record_retained=False,receiver_id=None,api_create_pending=False,
        nonce=H.NONCE,root=str(H.ROOT),units=list(H.UNITS),bundle_sha256=PACKAGE_SHA256,outage_sha256=OUTAGE_SHA256,
        scope='injected_session_management_io_not_shared_daemon_stop',stage='package',
        wiring_sha256=hashlib.sha256(WIRING_PROBE_SOURCE.encode()).hexdigest(),
        fault_helper_sha256=hashlib.sha256(FAULT_PROBE_SOURCE.encode()).hexdigest(),
        interruption_helper_sha256=hashlib.sha256(INTERRUPTION_PROBE_SOURCE.encode()).hexdigest())
    engine=collector=binding=None;bystander=None;bystander_nonce=None;image_id=api_id=None
    candidates=[]
    def persist():receipt['bystander_candidates']=list(candidates);H.record_receipt(receipt)
    def phase_marker():return F.marker()
    def created(cid):
        raw=engine.inspect(cid,time.monotonic_ns()+1_000_000_000)
        require(raw['Id']==cid and raw['Image']==image_id and raw['Config']['Labels']=={'org.openqms.d4.nonce':bystander_nonce},'bystander_identity_mismatch')
        state=raw['State'];require(state['Running']is False and state['Pid']==0 and state['Status']=='created' and state['StartedAt'].startswith('0001-01-01T00:00:00'),'bystander_started')
        return {'id':cid,'running':state['Running'],'pid':state['Pid'],'started_at':state['StartedAt']}
    try:
        H.unpack_package();F.install_hook('claim_watchdog_kill',receipt);persist()
        entry=H.ROOT/'agent_d4_isolation/deploy/runtime_entry.py';original=entry.read_bytes();hook=hook_source(H.NONCE).encode()
        temporary=entry.with_suffix('.outage-new');fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
        try:
            data=memoryview(hook+original)
            while data:
                count=os.write(fd,data);require(count>0,'entry_overlay_write');data=data[count:]
            os.fsync(fd)
        finally:os.close(fd)
        os.replace(temporary,entry);receipt.update(outage_hook_sha256=hashlib.sha256(hook).hexdigest(),entry_test_sha256=hashlib.sha256(entry.read_bytes()).hexdigest());persist()
        receipt['stage']='api';image_id,api_id,manifest=F.setup_api(image,receipt)
        sys.path.insert(0,str(H.ROOT))
        from agent_d4_isolation.linux_engine import EngineClient
        from agent_d4_isolation.linux_identity import KernelCollector
        from agent_d4_isolation.runtime_state import StateStore
        from agent_d4_isolation.runtime_supervisor import launch_session,state_call
        from agent_d4_isolation.journal import IntentJournal,SessionBlocked
        engine=EngineClient();collector=KernelCollector(engine,image_id,api_id)
        bystander_nonce=secrets_token();receipt.update(bystander_nonce=bystander_nonce,bystander_create_pending=True);persist()
        bystander=engine.create(bystander_nonce,image_id,api_id,time.monotonic_ns()+3_000_000_000)
        candidates.append(bystander);receipt['bystander_create_pending']=False;persist()
        bystander_before=created(bystander);api_before=H.inspect(api_id)['State']['StartedAt']
        (H.ROOT/'state').mkdir(mode=0o700);(H.ROOT/'state/journal').mkdir(mode=0o700)
        store=StateStore(H.ROOT);receipt['stage']='real_launch';launch_session(H.ROOT,H.NONCE)
        def take_observer(value):
            nonlocal binding
            require(binding is None,'observer_custody_conflict');binding=value
        binding,marker=F.wait_fault_phase('claim_watchdog_kill',collector,api_id,receipt,binding_ready=take_observer)
        def read_state():return state_call(lambda:store.read(H.NONCE),time.monotonic_ns()+200_000_000)
        original_state=read_state()
        require(not original_state['invalidated'] and original_state['watchdog_bound_verified'] and original_state['first_stdin_ns']is not None,'real_bound_claim_missing')
        require(binding.snapshot()==original_state['snapshot'] and binding.tasks_remaining()>0,'observer_original_reference_missing')
        require(H.docker('logs',api_id).stdout.decode('ascii').splitlines()==['ready','seen_0'],'claim_wire_missing')
        receipt.update(stage='outage',write_marker_before=marker,original_snapshot=binding.snapshot());persist()
        H.private_json(H.ROOT/'.engine-outage.tmp',{'failed':True})
        started=time.monotonic_ns()
        require(started+2_000_000_000<original_state['deadline_ns'],'natural_deadline_too_close')
        os.replace(H.ROOT/'.engine-outage.tmp',H.ROOT/'engine-outage.flag')
        directory=os.open(H.ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
        receipt['injected_ns']=started
        witness=I.wait_invalidated(read_state,original_state,not_before_ns=started,observe_deadline_ns=started+2_000_000_000)
        receipt.update(witness,detect_ns=witness['invalidated_observed_ns']-started)
        H.summarize_runtime(receipt,'invalidation_');persist()
        done=F.wait_reclaimed(binding,witness['invalidated_started_ns'])
        receipt.update(reclaimed_ns=done,reclaim_ns=done-witness['invalidated_started_ns'])
        until=witness['invalidated_started_ns']+5_000_000_000
        while time.monotonic_ns()<until:
            unit=F.manager_view(H.UNITS[0])
            if unit['ActiveState'] in ('inactive','failed'):break
            time.sleep(.01)
        else:raise OutageFailure('controller_not_stopped')
        verify_watchdog_kill(read_rows(H.ROOT,'watchdog-kernel-kill.jsonl'),binding.snapshot())
        hits=read_rows(H.ROOT,'engine-outage-hits.jsonl')
        require(all(set(row)=={'role','event','observed_ns'} and row['role']in('launch','controller','watchdog','stop','maintain') and row['event']=='engine_unavailable' and type(row['observed_ns'])is int and row['observed_ns']>=started for row in hits),'outage_hit_shape')
        require({'watchdog','controller'}<={row['role'] for row in hits},'both_manager_outages_not_observed')
        receipt['management_outage_hits']=hits;receipt['watchdog_kernel_kill_events']=read_rows(H.ROOT,'watchdog-kernel-kill.jsonl')
        state=read_state();journal=IntentJournal(store.journal_path);record=H.safe_read(H.ROOT/'state/journal'/(H.NONCE+'.json'))
        verify_boundary(state,record,marker,phase_marker(),original_state['first_stdin_ns'])
        require(not journal.admission().may_open_session and not(journal.delivery_gate(H.NONCE).allowed and not state['invalidated']),'new_delivery_allowed')
        try:journal.record_intent(secrets_token())
        except SessionBlocked:pass
        else:raise OutageFailure('new_intent_allowed')
        H.private_json(H.ROOT/'bad-registration-initial.json',record);H.private_json(H.ROOT/'bad-session-initial.json',state)
        receipt['bad_initial_record_retained']=True
        require(created(bystander)==bystander_before,'bystander_affected')
        api=H.assert_owned(api_id,image_id,'api')
        require(api['State']['Running'] and api['State']['StartedAt']==api_before,'api_affected')
        require(H.docker('logs',api_id).stdout.decode('ascii').splitlines()==['ready','seen_0'],'request_replayed_after_outage')
        require(type(engine.info(time.monotonic_ns()+1_000_000_000))is dict,'observer_engine_unavailable')
        H.summarize_runtime(receipt)
        receipt.update(verified=True,stage='verified',infrastructure_result='isolation_unknown',watchdog_original_kernel_kill=True,
            observer_cgroup_empty=True,receiver_stopped=True,bystander_unchanged=True,api_survived=True,controller_stopped=True,no_replay=True,observer_engine_available=True)
    except Exception as error:
        receipt['failure_code']=str(error) if type(error)in(OutageFailure,F.FaultFailure,H.ProbeFailure,I.InterruptionFailure) else 'engine_outage_probe_failed'
    finally:
        errors=[]
        def attempt(code,call):
            try:return call()
            except Exception:errors.append(code);return None
        if engine is not None and bystander_nonce is not None:
            def discover():
                for cid in engine.list_by_nonce(bystander_nonce,time.monotonic_ns()+1_000_000_000):
                    if cid not in candidates:candidates.append(cid);persist()
            attempt('bystander_discovery_unknown',discover)
        for cid in reversed(candidates):
            def remove(cid=cid):
                created(cid);require(collector.verify_created(bystander_nonce,cid,time.monotonic_ns()+1_000_000_000),'bystander_recipe_unverified')
                engine.remove(cid,time.monotonic_ns()+1_000_000_000);H.absent(cid)
            attempt('bystander_cleanup_unknown',remove)
        if receipt.get('bystander_create_pending'):errors.append('bystander_create_unknown')
        if H.ROOT.exists():
            H.summarize_runtime(receipt,'post_observation_')
            attempt('runtime_cleanup_unknown',lambda:F.cleanup(receipt,binding,collector))
            errors.extend(receipt.get('cleanup_errors',[]))
            def final_retention():
                require(H.ROOT.exists(),'unknown_root_erased')
                H.summarize_runtime(receipt,'post_cleanup_')
                if receipt.get('bad_initial_record_retained'):
                    require((H.ROOT/'bad-registration-initial.json').is_file() and receipt['post_cleanup_journal_summary']['state']!='closed','bad_registration_erased')
                    verify_boundary(read_state(),H.safe_read(H.ROOT/'state/journal'/(H.NONCE+'.json')),marker,phase_marker(),original_state['first_stdin_ns'])
                if engine is not None and bystander_nonce is not None:require(not engine.list_by_nonce(bystander_nonce,time.monotonic_ns()+1_000_000_000),'bystander_remains')
            attempt('unknown_retention_unverified',final_retention)
        receipt.update(resources_cleaned=not errors,cleanup_errors=errors,registration_retained=True)
        if errors:receipt['failure_code']=receipt['failure_code'] or 'engine_outage_cleanup_failed'
        attempt('receipt_write_unknown',persist)
        if errors:receipt.update(resources_cleaned=False,failure_code=receipt['failure_code'] or 'engine_outage_cleanup_failed')
        print(json.dumps(receipt,sort_keys=True),flush=True)
    require(receipt['verified'] and receipt['resources_cleaned'] and receipt['failure_code']is None,'outage_not_verified')
    print('runtime_engine_outage_verified',flush=True)


def secrets_token():
    import secrets
    return secrets.token_hex(32)

if __name__=='__main__':
    try:require(len(sys.argv)==2,'image_required');main(sys.argv[1])
    except Exception as error:
        print('runtime_engine_outage_failed:'+(str(error)if type(error)is OutageFailure else 'probe_failed'),flush=True)
        raise SystemExit(1)
