"""Root-only, synthetic-wire faults against the unchanged receiver and two units.

The only hooks are source-pinned in this private test deployment. No hook option
is added to the production entry, image, create recipe, UID, or receiver bytes.
Unknown registrations survive exact resource cleanup; they are never erased to
manufacture convergence. This module performs no work merely by being imported.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time
import types

CASES=('ready_watchdog_kill','before_stdin_watchdog_kill','partial_stdin_watchdog_kill',
       'claim_watchdog_kill','claim_watchdog_stop','claim_controller_kill')
UNITS=()
H=None


class FaultFailure(Exception):
    """Fixed diagnostic codes only; never management output or request data."""


def require(value,code):
    if not value:raise FaultFailure(code)


def helpers():
    module=types.ModuleType('_owned_runtime_wiring_helpers')
    module.__dict__.update(PACKAGE_B64=PACKAGE_B64,PACKAGE_SHA256=PACKAGE_SHA256,
                           WIRE_FIXTURE_SOURCE=WIRE_FIXTURE_SOURCE)
    # The reference probe has an explicit __main__ guard. Import under a fixed
    # non-main name, retaining helpers without executing its smoke main().
    exec(compile(WIRING_PROBE_SOURCE,'<owned-wiring-helpers>','exec'),module.__dict__)
    return module


def hook_source(case):
    require(case in CASES,'fault_case_invalid')
    if case=='ready_watchdog_kill':return ''
    header="""# TEST-ONLY fixed fault hook; no configuration values are recorded.
import os as _fo, sys as _fs, json as _fj, time as _ft
from pathlib import Path as _FP
_fault_root=_FP(__file__).absolute().parents[2]
_fs.path.insert(0,str(_fault_root))
if len(_fs.argv)==4 and _fs.argv[1]=='controller':
    _fault_bytes=0
    _fault_calls=0
    def _fault_marker(phase):
        target=_fault_root/'fault-marker.json'
        temporary=_fault_root/'.fault-marker.tmp'
        fd=_fo.open(temporary,_fo.O_WRONLY|_fo.O_CREAT|_fo.O_EXCL|_fo.O_NOFOLLOW,0o600)
        try:
            raw=_fj.dumps({'phase':phase,'bytes_written':_fault_bytes,'calls':_fault_calls},sort_keys=True).encode('ascii')
            if _fo.write(fd,raw)!=len(raw):raise RuntimeError('fault_marker_invalid')
            _fo.fsync(fd)
        finally:_fo.close(fd)
        _fo.replace(temporary,target)
"""
    if case=='before_stdin_watchdog_kill':
        return header+"""    from agent_d4_isolation import contracts as _fc
    from agent_d4_isolation import linux_engine as _fe
    _fault_write=_fe.AttachedIO.write
    def _fault_observe_write(self,data,deadline_ns):
        global _fault_bytes,_fault_calls
        count=_fault_write(self,data,deadline_ns)
        _fault_bytes+=count
        _fault_calls+=1
        return count
    _fe.AttachedIO.write=_fault_observe_write
    _fault_read=_fc.read_private_config
    def _fault_pause_before_config(path):
        _fault_marker('before_stdin')
        _ft.sleep(30)
        return _fault_read(path)
    _fc.read_private_config=_fault_pause_before_config
"""
    partial=case=='partial_stdin_watchdog_kill'
    return header+"""    from agent_d4_isolation import linux_engine as _fe
    _fault_write=_fe.AttachedIO.write
    def _fault_count_write(self,data,deadline_ns):
        global _fault_bytes,_fault_calls
        count=_fault_write(self,"""+('data[:1]' if partial else 'data')+""",deadline_ns)
        _fault_bytes+=count
        _fault_calls+=1
        _fault_marker('"""+('partial_stdin' if partial else 'claim_write')+"""')
"""+('        _ft.sleep(30)\n' if partial else '')+"""        return count
    _fe.AttachedIO.write=_fault_count_write
"""


def manager_view(unit):
    require(unit in UNITS,'unit_not_registered')
    raw=H.run(['/usr/bin/systemctl','show',unit,
               '--property=LoadState,ActiveState,SubState,InvocationID,MainPID,ControlGroup,Result,WatchdogTimestampMonotonic,WatchdogUSec'],
              timeout=1,check=False).stdout.decode('ascii')
    result={}
    for line in raw.splitlines():
        key,sep,value=line.partition('=')
        require(sep and key not in result,'unit_facts_invalid');result[key]=value
    require({'LoadState','ActiveState','SubState','InvocationID','MainPID','ControlGroup'}<=set(result),'unit_facts_missing')
    return result


def process_starttime(pid,unit):
    """Pin manager MainPID to this exact unit's kernel cgroup before pidfd use."""
    require(type(pid) is int and pid>1 and unit in UNITS,'process_identity_invalid')
    base=Path('/proc')/str(pid)
    with open(base/'cgroup','r',encoding='ascii') as handle:groups=handle.read(8192)
    require(groups.splitlines()==['0::/system.slice/'+unit],'process_unit_mismatch')
    with open(base/'stat','r',encoding='ascii') as handle:raw=handle.read(8192)
    start=int(raw.rsplit(')',1)[1].split()[19])
    require(start>0,'process_starttime_invalid')
    return start


def signal_unit(unit,signum):
    require(unit in UNITS and signum in (signal.SIGKILL,signal.SIGSTOP),'signal_target_invalid')
    first=manager_view(unit)
    invocation=first['InvocationID'];pid=int(first['MainPID'])
    require(first['ActiveState']=='active' and re.fullmatch('[a-f0-9]{32}',invocation) and pid>1,
            'unit_not_live')
    require(first.get('ControlGroup')=='/system.slice/'+unit,'unit_cgroup_mismatch')
    starttime=process_starttime(pid,unit)
    fd=os.pidfd_open(pid,0)
    try:
        second=manager_view(unit)
        require(second['ActiveState']=='active' and second['InvocationID']==invocation
                and second['MainPID']==str(pid) and second.get('ControlGroup')==first['ControlGroup']
                and process_starttime(pid,unit)==starttime,'unit_instance_changed')
        sent_ns=time.monotonic_ns()
        signal.pidfd_send_signal(fd,signum,None,0)
        return dict(unit=unit,invocation_id=invocation,main_pid=pid,main_starttime=starttime,
                    signal=signal.Signals(signum).name,sent_ns=sent_ns,
                    watchdog_timestamp_ns_before_signal=manager_watchdog_stamp(second),
                    watchdog_usec_property=second.get('WatchdogUSec') if second.get('WatchdogUSec') in ('1s','2s','1000000','2000000') else None)
    finally:os.close(fd)


def manager_watchdog_stamp(view):
    value=view.get('WatchdogTimestampMonotonic','')
    return int(value)*1000 if type(value) is str and re.fullmatch('[0-9]{1,20}',value) else None


def may_remove_registration(journal):
    return (type(journal) is dict and journal.get('state')=='closed'
            and journal.get('closed_by') in ('create_absent','reclaim_verified'))


def wait_detected(proof):
    """Bound observation above, and manager detection conservatively below.

    A property RPC can return long after the manager actually changed state.
    Its return time is an upper bound, never a safe start for a reclaim budget.
    """
    deadline=proof['sent_ns']+2_000_000_000
    earliest=proof['sent_ns']
    while time.monotonic_ns()<deadline:
        query_started=time.monotonic_ns()
        view=manager_view(proof['unit'])
        proof['last_observed_ns']=time.monotonic_ns()
        proof['last_active_state']=view['ActiveState'] if view['ActiveState'] in ('active','activating','deactivating','inactive','failed') else 'unknown'
        proof['last_sub_state']=view.get('SubState') if view.get('SubState') in ('running','stop-watchdog','stop-sigterm','stop-sigkill','stop-post','dead','failed') else 'unknown'
        proof['last_watchdog_timestamp_ns']=manager_watchdog_stamp(view)
        if view['ActiveState'] not in ('active','activating'):
            observed=time.monotonic_ns()
            require(observed<=deadline,'fault_detection_over_two_seconds')
            return dict(observed_ns=observed,earliest_detection_ns=earliest)
        if 'invocation_id' in proof:
            require(view.get('InvocationID')==proof['invocation_id'],'detection_instance_changed')
        # The active snapshot occurred no earlier than this query's start.
        # Its end could already be after the real transition, so is unsafe.
        earliest=max(proof['sent_ns'],query_started)
        time.sleep(.01)
    raise FaultFailure('fault_detection_over_two_seconds')


def marker():
    value=H.safe_read(H.ROOT/'fault-marker.json')
    if value is None:return None
    require(type(value) is dict and set(value)=={'phase','bytes_written','calls'},'marker_invalid')
    require(value['phase'] in ('before_stdin','partial_stdin','claim_write'),'marker_invalid')
    require(type(value['bytes_written']) is int and value['bytes_written']>=0
            and type(value['calls']) is int and value['calls']>=0,'marker_invalid')
    return value


def install_hook(case,receipt):
    entry=H.ROOT/'agent_d4_isolation/deploy/runtime_entry.py'
    original=entry.read_bytes();hook=hook_source(case).encode('ascii')
    receipt['entry_original_sha256']=hashlib.sha256(original).hexdigest()
    receipt['hook_sha256']=hashlib.sha256(hook).hexdigest()
    # Trusted source-only overlay in the one freshly unpacked root-private
    # deployment. The unmodified receiver image remains content-pinned.
    temporary=entry.with_suffix('.fault-new')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    try:
        view=memoryview(hook+original)
        while view:
            count=os.write(fd,view);require(count>0,'hook_write_failed');view=view[count:]
        os.fsync(fd)
    finally:os.close(fd)
    os.replace(temporary,entry)
    receipt['entry_test_sha256']=hashlib.sha256(entry.read_bytes()).hexdigest()


def api_source():
    source=H.owned_wire_source().replace('if index==0:time.sleep(3)','if index==0:time.sleep(8)')
    needle='  connection.sendall(reply(responses()[index]))'
    require(needle in source,'wire_fixture_shape_changed')
    # A deliberately interrupted client cannot take down the trusted API fixture.
    return source.replace(needle,'  try: connection.sendall(reply(responses()[index]))\n  except OSError: break')


def setup_api(image_tag,receipt):
    image=json.loads(H.docker('image','inspect',image_tag).stdout)
    require(type(image) is list and len(image)==1,'image_invalid')
    image_id=image[0]['Id'];require(re.fullmatch('sha256:[a-f0-9]{64}',image_id),'image_invalid')
    receipt['image_id']=image_id;receipt['api_create_pending']=True;H.record_receipt(receipt)
    created=H.docker('create','--pull=never','--name','oqms-d4-fault-api-'+H.NONCE,
                     '--label',H.SMOKE_LABEL+'='+H.NONCE,'--label',H.ROLE_LABEL+'=api',
                     '--network','bridge','--user','2002:2002','--cap-drop','ALL',
                     '--security-opt','no-new-privileges','--read-only','--memory','128m',
                     '--memory-swap','128m','--pids-limit','16','--cpus','1','--ulimit','core=0:0',
                     '--log-driver','json-file','--log-opt','max-size=16k','--log-opt','max-file=1',
                     '--entrypoint','python',image_id,'-I','-S','-B','-u','-c',api_source())
    api_id=created.stdout.decode('ascii').strip()
    require(re.fullmatch('[a-f0-9]{64}',api_id),'api_create_unknown')
    H.assert_owned(api_id,image_id,'api')
    receipt.update(api_id=api_id,api_create_pending=False);H.record_receipt(receipt)
    H.docker('start',api_id)
    deadline=time.monotonic_ns()+5_000_000_000
    while time.monotonic_ns()<deadline:
        if H.docker('logs',api_id,timeout=1).stdout.decode('ascii').splitlines()==['ready']:break
        time.sleep(.025)
    else:raise FaultFailure('api_not_ready')
    namespace={};exec(compile(WIRE_FIXTURE_SOURCE,'<owned-fault-wire>','exec'),namespace)
    config=namespace['config']('http://127.0.0.1:18777');config['request_key']=H.NONCE
    H.private_json(H.ROOT/'private/config.json',config)
    manifest={'schema_version':1,'api_container_id':api_id,
              'permit':dict(image_digest=image_id,worker_sha256=H.WORKER_SHA256,
                            receiver_uid=2001,api_uid=2002,api_port=18777)}
    H.private_json(H.ROOT/'deployment.json',manifest)
    return image_id,api_id,manifest


def wait_fault_phase(case,collector,api_id,receipt,*,binding_ready):
    """Publish each original capability to the caller's finally before more I/O.

    The callback takes custody immediately after bind succeeds, including when
    identity comparison, marker sampling or later management queries fail.
    """
    require(callable(binding_ready),'observer_custody_required')
    binding=None;deadline=time.monotonic_ns()+20_000_000_000
    while time.monotonic_ns()<deadline:
        state=H.safe_read(H.ROOT/'state'/(H.NONCE+'.json'))
        if state and state.get('receiver_id') and state.get('snapshot') and binding is None:
            cid=state['receiver_id'];H.assert_owned(cid,receipt['image_id'],'receiver')
            binding=collector.bind(H.NONCE,cid,time.monotonic_ns()+1_000_000_000)
            binding_ready(binding)
            require(binding.snapshot()==state['snapshot'],'observer_identity_mismatch')
            receipt['receiver_id']=cid;H.record_receipt(receipt)
        phase=marker()
        if binding is not None:
            if case=='before_stdin_watchdog_kill' and phase and phase['phase']=='before_stdin':
                require(state['first_stdin_ns'] is None and phase['bytes_written']==0,'unexpected_first_stdin')
                return binding,phase
            if case=='partial_stdin_watchdog_kill' and phase and phase['phase']=='partial_stdin':
                require(state['first_stdin_ns'] is not None and phase['bytes_written']==1 and phase['calls']==1,
                        'partial_stdin_not_exactly_one')
                return binding,phase
            if case.startswith('claim_'):
                codes=H.docker('logs',api_id,timeout=1).stdout.decode('ascii').splitlines()
                if codes==['ready','seen_0']:
                    # The server can consume stdin before the controller's
                    # write wrapper publishes its count. Sample after the log
                    # witness, and retry a still-unpublished marker normally.
                    phase=marker()
                    if phase is not None:
                        require(phase['phase']=='claim_write' and phase['bytes_written']>0,'write_witness_missing')
                        return binding,phase
        require(manager_view(UNITS[0])['ActiveState'] not in ('inactive','failed'),'controller_ended_before_fault')
        time.sleep(.015)
    raise FaultFailure('fault_phase_deadline')


def wait_reclaimed(binding,earliest_detection_ns):
    deadline=earliest_detection_ns+5_000_000_000
    while time.monotonic_ns()<deadline:
        if (binding.container_running(min(deadline,time.monotonic_ns()+100_000_000)) is False
                and binding.tasks_remaining()==0):
            done=time.monotonic_ns();require(done<=deadline,'reclaim_over_five_seconds');return done
        time.sleep(.015)
    raise FaultFailure('reclaim_over_five_seconds')


def cleanup(receipt,binding,collector):
    """Attempt every exact resource; any unknown proof retains the registration."""
    errors=[]
    def attempt(code,call):
        try:return call()
        except Exception:errors.append(code);return None
    attempt('unit_stop_unknown',lambda:H.run(['/usr/bin/systemctl','stop',*UNITS],timeout=15,check=False))
    for unit in UNITS:
        def stopped(unit=unit):
            require(manager_view(unit)['ActiveState'] not in ('active','activating','deactivating'),'cleanup_unit_active')
        attempt('unit_state_unknown',stopped)
    attempt('unit_reset_unknown',lambda:H.run(['/usr/bin/systemctl','reset-failed',*UNITS],check=False))
    journal=attempt('journal_read_unknown',lambda:H.safe_read(H.ROOT/'state/journal'/(H.NONCE+'.json')))
    if hasattr(H,'summarize_runtime'):attempt('summary_unknown',lambda:H.summarize_runtime(receipt,'post_stop_'))
    cid=receipt.get('receiver_id') or (journal or {}).get('container_id')
    matches=attempt('receiver_enumeration_unknown',lambda:H.exact_matches(H.RECEIVER_LABEL))
    ambiguous=matches is not None and len(matches)>1
    if ambiguous:errors.append('receiver_ambiguous')
    if cid is None and matches and not ambiguous:cid=matches[0]
    if cid is not None and not ambiguous:
        try:
            raw=H.assert_owned(cid,receipt['image_id'],'receiver')
            if binding is None and raw['State']['Running']:
                binding=collector.bind(H.NONCE,cid,time.monotonic_ns()+1_000_000_000)
            never_started=False
            if binding is None and raw['State'].get('Status')=='created':
                never_started=collector.verify_created(H.NONCE,cid,time.monotonic_ns()+500_000_000)
            if binding is not None and binding.container_running(time.monotonic_ns()+500_000_000) is not False:
                binding.signal('SIGKILL',time.monotonic_ns()+500_000_000)
                binding.terminate(time.monotonic_ns()+2_000_000_000)
            H.docker('rm','-f',cid);H.absent(cid)
            receipt['receiver_id']=cid
            require(never_started or (binding is not None and binding.tasks_remaining()==0),'cleanup_cgroup_unknown')
        except Exception:errors.append('receiver_cleanup_unknown')
    api_id=receipt.get('api_id')
    if api_id:
        def api_cleanup():
            H.assert_owned(api_id,receipt['image_id'],'api')
            H.docker('rm','-f',api_id);H.absent(api_id)
        attempt('api_cleanup_unknown',api_cleanup)
    def no_resources():
        require(not H.exact_matches(H.RECEIVER_LABEL) and not H.exact_matches(H.SMOKE_LABEL),
                'cleanup_nonce_resources_remain')
        require(not receipt.get('api_create_pending'),'cleanup_api_create_unknown')
    attempt('resource_absence_unknown',no_resources)
    def units_collected():
        until=time.monotonic_ns()+3_000_000_000
        while True:
            views=[manager_view(unit) for unit in UNITS]
            if all(view['LoadState']=='not-found' and view['ActiveState']=='inactive' for view in views):return
            require(time.monotonic_ns()<until,'cleanup_unit_remaining');time.sleep(.025)
    attempt('unit_gc_unknown',units_collected)
    # Never erase a registration observed unknown at the fault boundary, even if
    # a later legitimate StopPost manages to close it during resource teardown.
    # Both snapshots remain inspectable in the retained private receipt/root.
    initial=receipt.get('journal_summary')
    closed=may_remove_registration(initial) and may_remove_registration(journal)
    receipt['registration_retained']=not closed or bool(errors)
    if not receipt['registration_retained']:
        def remove_closed_root():
            import shutil
            info=H.ROOT.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,
                    'cleanup_root_invalid')
            shutil.rmtree(H.ROOT)
        attempt('closed_root_cleanup_unknown',remove_closed_root)
        if errors:receipt['registration_retained']=True
    if binding is not None:attempt('observer_close_unknown',binding.close)
    receipt['cleanup_errors']=errors
    receipt['resources_cleaned']=not errors
    return not errors


def main(image_tag):
    global H,UNITS
    require(os.geteuid()==0 and FAULT_CASE in CASES,'root_or_case_invalid')
    require(type(image_tag) is str and image_tag and not image_tag.startswith('-'),'image_invalid')
    H=helpers();UNITS=H.UNITS
    receipt=dict(case=FAULT_CASE,nonce=H.NONCE,root=str(H.ROOT),units=list(UNITS),
                 bundle_sha256=PACKAGE_SHA256,fault_probe_sha256=FAULT_PROBE_SHA256,
                 wiring_probe_sha256=hashlib.sha256(WIRING_PROBE_SOURCE.encode()).hexdigest(),
                 receiver_id=None,api_create_pending=False,fault_verified=False,resources_cleaned=False,
                 registration_retained=True,failure_code=None)
    binding=collector=None
    try:
        H.unpack_package();install_hook(FAULT_CASE,receipt);H.record_receipt(receipt)
        image_id,api_id,manifest=setup_api(image_tag,receipt)
        sys.path.insert(0,str(H.ROOT))
        from agent_d4_isolation.linux_engine import EngineClient
        from agent_d4_isolation.linux_identity import KernelCollector
        from agent_d4_isolation.runtime_state import StateStore
        from agent_d4_isolation.runtime_supervisor import SystemdUnits,launch_session
        from agent_d4_isolation.runtime_network import prepare_api
        engine=EngineClient();collector=KernelCollector(engine,image_id,api_id)
        (H.ROOT/'state').mkdir(mode=0o700);(H.ROOT/'state/journal').mkdir(mode=0o700)
        store=StateStore(H.ROOT)
        proof=None
        if FAULT_CASE=='ready_watchdog_kill':
            class FaultUnits(SystemdUnits):
                def start(self,unit,deadline_ns):
                    nonlocal proof
                    super().start(unit,deadline_ns)
                    require(unit==UNITS[1],'controller_unexpectedly_started')
                    proof=signal_unit(unit,signal.SIGKILL)
                    receipt['signal_proof']=proof;H.record_receipt(receipt)
                    detection=wait_detected(proof);receipt['detection_witness']=detection
                    until=detection['earliest_detection_ns']+5_000_000_000
                    while time.monotonic_ns()<until:
                        if manager_view(unit)['ActiveState'] in ('inactive','failed'):return
                        time.sleep(.015)
                    raise FaultFailure('readiness_stop_deadline')
            deadline=time.monotonic_ns()+10_000_000_000
            daemon=collector.pin_daemon(deadline);api=None
            try:
                api=prepare_api(engine,manifest,deadline,install=True)
                launch_session(H.ROOT,H.NONCE,units=FaultUnits(H.ROOT),preparation_leases=(daemon,api))
            finally:
                if api is not None:api.close()
                daemon.close()
            require(proof is not None,'readiness_fault_not_sent')
            detection=receipt['detection_witness'];done=time.monotonic_ns()
            require(not H.exact_matches(H.RECEIVER_LABEL),'receiver_created_after_watchdog_death')
            receipt.update(written_bytes=0,write_calls=0,receiver_stopped=True,observer_cgroup_empty=True)
        else:
            launch_session(H.ROOT,H.NONCE)
            def take_observer(value):
                nonlocal binding
                require(binding is None or binding is value,'observer_custody_conflict')
                binding=value
            binding,phase=wait_fault_phase(FAULT_CASE,collector,api_id,receipt,binding_ready=take_observer)
            # A fresh heartbeat aged 0.2s leaves observation slack while still
            # proving a manager-enforced <=2s SIGSTOP detection after the fault.
            if FAULT_CASE=='claim_watchdog_stop':
                until=time.monotonic_ns()+1_000_000_000
                while time.monotonic_ns()<until:
                    stamp=int(manager_view(UNITS[1]).get('WatchdogTimestampMonotonic','0'))*1000
                    if 200_000_000<=time.monotonic_ns()-stamp<=450_000_000:break
                    time.sleep(.01)
                else:raise FaultFailure('fresh_watchdog_lease_unobserved')
            target=UNITS[0] if FAULT_CASE=='claim_controller_kill' else UNITS[1]
            signum=signal.SIGSTOP if FAULT_CASE=='claim_watchdog_stop' else signal.SIGKILL
            proof=signal_unit(target,signum)
            receipt['signal_proof']=proof;H.record_receipt(receipt)
            detection=wait_detected(proof)
            done=wait_reclaimed(binding,detection['earliest_detection_ns'])
            require(marker()==phase,'stdin_replayed_after_fault')
            receipt.update(written_bytes=phase['bytes_written'],write_calls=phase['calls'],
                           receiver_stopped=True,observer_cgroup_empty=True)
        receipt['signal_proof']=proof
        receipt['detection_witness']=detection
        receipt['reclaim_observed_ns']=done
        receipt['detection_ns']=detection['observed_ns']-proof['sent_ns']
        receipt['reclaim_ns']=done-detection['earliest_detection_ns']
        require(receipt['detection_ns']<=2_000_000_000 and receipt['reclaim_ns']<=5_000_000_000,'fault_budget_exceeded')
        require(H.assert_owned(api_id,image_id,'api')['State']['Running'] is True,'api_stopped_with_receiver')
        receipt['api_survived_fault']=True
        if FAULT_CASE.startswith('claim_'):
            require(H.docker('logs',api_id,timeout=1).stdout.decode('ascii').splitlines()==['ready','seen_0'],
                    'receiver_progressed_after_claim_fault')
        # Wait for handlers to publish their own evidence; the observer never
        # upgrades the journal or manufactures an infrastructure conclusion.
        until=proof['sent_ns']+8_000_000_000
        while time.monotonic_ns()<until:
            if manager_view(UNITS[0])['ActiveState'] in ('inactive','failed'):break
            time.sleep(.02)
        H.summarize_runtime(receipt)
        journal=receipt['journal_summary'];state=receipt['state_summary']
        require(state['invalidated'] and journal['state'] in ('closed','stopping','unresolved','create_inflight'),
                'fault_registration_invalid')
        if FAULT_CASE=='ready_watchdog_kill':
            require(journal['closed_by']=='create_absent' and state['first_stdin_ns'] is None,'never_create_not_closed')
        if FAULT_CASE=='before_stdin_watchdog_kill':require(state['first_stdin_ns'] is None,'secret_started_before_marker')
        if FAULT_CASE=='partial_stdin_watchdog_kill':require(state['first_stdin_ns'] is not None,'first_stdin_not_registered')
        receipt['infrastructure_result']='isolation_terminated' if journal['closed_by']=='reclaim_verified' else 'isolation_unknown'
        receipt['fault_verified']=True
    except Exception as error:
        receipt['failure_code']=str(error) if type(error) is FaultFailure else 'runtime_fault_probe_unknown'
    finally:
        if H is not None and H.ROOT.exists():
            H.summarize_runtime(receipt,'post_observation_')
            cleanup(receipt,binding,collector)
            if H.ROOT.exists():
                try:H.record_receipt(receipt)
                except Exception:receipt['receipt_write_failed']=True
        print(json.dumps(receipt,sort_keys=True),flush=True)
    require(receipt['fault_verified'] and receipt['resources_cleaned'] and receipt['failure_code'] is None,
            'runtime_fault_not_verified')
    print('runtime_fault_verified:'+FAULT_CASE,flush=True)


if __name__=='__main__':
    try:
        require(len(sys.argv)==2,'image_required');main(sys.argv[1])
    except Exception as error:
        print('runtime_fault_failed:'+(str(error) if type(error) is FaultFailure else 'runtime_fault_probe_unknown'),flush=True)
        raise SystemExit(1)
