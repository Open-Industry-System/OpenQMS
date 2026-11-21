"""Source-pinned, authority-free two-unit supervision edge probe."""
import os
import re
import signal
import time
import hashlib
import json
import sys
import types

class EdgeFailure(Exception):pass

CASES=('watchdog_exit_zero','stop_post_timeout','attach_disconnect')

def require(value,code):
    if not value:raise EdgeFailure(code)

def hook_source(case):
    require(case in CASES,'edge_case_invalid')
    header='''# TEST ONLY: fixed source-pinned supervision fault, no config fields.
import os as _eo, sys as _es, time as _et, json as _ej, signal as _eg
from pathlib import Path as _EP
_edge_root=_EP(__file__).absolute().parents[2]
def _edge_marker(phase,**counts):
    value=dict(phase=phase,at_ns=_et.monotonic_ns(),**counts)
    name='edge-stop-'+str(_eo.getpid())+'.json' if phase=='stop_sleep' else 'edge-marker.json'
    target=_edge_root/name
    temporary=target.with_suffix('.tmp')
    fd=_eo.open(temporary,_eo.O_WRONLY|_eo.O_CREAT|_eo.O_EXCL|_eo.O_NOFOLLOW,0o600)
    try:
        raw=_ej.dumps(value,sort_keys=True).encode('ascii')
        if _eo.write(fd,raw)!=len(raw):raise RuntimeError('edge_marker_write')
        _eo.fsync(fd)
    finally:_eo.close(fd)
    _eo.replace(temporary,target)
'''
    if case=='watchdog_exit_zero':
        return header+'''if len(_es.argv)==4 and _es.argv[1]=='watchdog':
    def _edge_exit(sig,frame):
        _edge_marker('exit_zero')
        _eo._exit(0)
    _eg.signal(_eg.SIGUSR1,_edge_exit)
'''
    if case=='stop_post_timeout':
        return header+'''if len(_es.argv)==4 and _es.argv[1]=='stop':
    _edge_marker('stop_sleep',pid=_eo.getpid(),invocation_id=_eo.environ.get('INVOCATION_ID',''))
    _et.sleep(30)
'''
    return header+'''if len(_es.argv)==4 and _es.argv[1]=='controller':
    _es.path.insert(0,str(_edge_root))
    from agent_d4_isolation import linux_engine as _ee
    _edge_write=_ee.AttachedIO.write
    _edge_closed=False
    def _edge_disconnect(self,data,deadline_ns):
        global _edge_closed
        if _edge_closed:raise OSError('edge_attach_closed')
        count=_edge_write(self,data[:1],deadline_ns)
        if count!=1:raise OSError('edge_partial_write_invalid')
        _edge_marker('partial_ready',bytes_written=count,calls=1)
        until=min(deadline_ns,_et.monotonic_ns()+5_000_000_000)
        while not (_edge_root/'edge-release').exists():
            if _et.monotonic_ns()>=until:raise OSError('edge_observer_not_ready')
            _et.sleep(.01)
        started=_et.monotonic_ns()
        self.close()
        _edge_closed=True
        _edge_marker('disconnected',bytes_written=count,calls=1,close_calls=1,disconnect_started_ns=started)
        return count
    _ee.AttachedIO.write=_edge_disconnect
'''

def verify_zero_exit(view,invocation):
    require(view.get('InvocationID')==invocation and view.get('ExecMainCode')=='1'
            and view.get('ExecMainStatus')=='0','watchdog_zero_exit_not_proved')

def handler_projection(view):
    """Closed diagnostic facts, excluding command/path/arbitrary manager text."""
    raw=view.get('ExecStopPost','')
    def field(pattern):
        matches=re.findall(r'(?:^|;\s*)'+pattern+r'(?=\s*(?:;|\}|$))',raw)
        return matches[0] if len(matches)==1 else None
    pid=field(r'pid=([0-9]{1,10})')
    code=field(r'code=([a-z]+)')
    status=field(r'status=([0-9]{1,3})(?:/([A-Z]+))?')
    invocation=view.get('InvocationID')
    suffix=status[1] if status else None
    return dict(invocation_id=invocation if type(invocation) is str and re.fullmatch('[a-f0-9]{32}',invocation) else None,
                active_state=view.get('ActiveState') if view.get('ActiveState') in ('active','activating','deactivating','inactive','failed') else 'unknown',
                sub_state=view.get('SubState') if view.get('SubState') in ('running','stop-post','stop-sigterm','stop-sigkill','failed','dead','exited') else 'unknown',
                pid=int(pid) if pid and int(pid)>1 else None,
                code=code if code in ('exited','killed','dumped') else 'unknown',
                status=int(status[0]) if status and int(status[0])<=255 else None,
                signal=(suffix if suffix in ('TERM','KILL') else 'unknown') if suffix else None)


def verify_timeout(view,rows,started,observed,*,pid=None):
    require(5_500_000_000<=observed-started<=9_000_000_000,'handler_timeout_budget_invalid')
    fact=handler_projection(view)
    if pid is not None:
        require(type(pid) is int and pid>1 and fact['pid']==pid,
                'handler_process_changed')
    require(fact['code']=='killed' and (fact['status'],fact['signal']) in ((15,None),(15,'TERM'),(9,None),(9,'KILL')),
            'handler_not_manager_killed')
    require(any(row.get('_PID')=='1' and re.search(r"(?:State 'stop-post'|stop-post).*timed out",row.get('MESSAGE',''))
                for row in rows),'manager_timeout_not_observed')


def signal_usr1(F,unit):
    require(unit in F.UNITS,'unit_not_registered')
    first=F.manager_view(unit);pid=int(first['MainPID']);invocation=first['InvocationID']
    require(first['ActiveState']=='active' and pid>1 and re.fullmatch('[a-f0-9]{32}',invocation)
            and first.get('ControlGroup')=='/system.slice/'+unit,'unit_not_live')
    start=F.process_starttime(pid,unit);fd=os.pidfd_open(pid,0)
    try:
        second=F.manager_view(unit)
        require(second['ActiveState']=='active' and second['MainPID']==str(pid)
                and second['InvocationID']==invocation and second.get('ControlGroup')==first['ControlGroup']
                and F.process_starttime(pid,unit)==start,'unit_instance_changed')
        sent=time.monotonic_ns();signal.pidfd_send_signal(fd,signal.SIGUSR1,None,0)
        return dict(unit=unit,invocation_id=invocation,main_pid=pid,main_starttime=start,
                    signal='SIGUSR1',sent_ns=sent)
    finally:os.close(fd)


def wait_partial(H,collector,receipt,*,binding_ready):
    require(callable(binding_ready),'observer_custody_required')
    binding=None;until=time.monotonic_ns()+15_000_000_000
    while time.monotonic_ns()<until:
        state=H.safe_read(H.ROOT/'state'/(H.NONCE+'.json'))
        if state and state.get('receiver_id') and state.get('snapshot') and binding is None:
            cid=state['receiver_id'];H.assert_owned(cid,receipt['image_id'],'receiver')
            binding=collector.bind(H.NONCE,cid,time.monotonic_ns()+500_000_000)
            binding_ready(binding)
            require(binding.snapshot()==state['snapshot'],'observer_identity_mismatch')
            receipt['receiver_id']=cid;H.record_receipt(receipt)
        phase=H.safe_read(H.ROOT/'edge-marker.json')
        if binding is not None and phase is not None:
            require(phase.get('phase')=='partial_ready' and phase.get('bytes_written')==1
                    and phase.get('calls')==1 and state['first_stdin_ns'] is not None,'partial_witness_invalid')
            return binding,phase
        time.sleep(.01)
    raise EdgeFailure('partial_boundary_deadline')


def helpers():
    F=types.ModuleType('_owned_edge_fault_helpers')
    F.__dict__.update(PACKAGE_B64=PACKAGE_B64,PACKAGE_SHA256=PACKAGE_SHA256,
                      WIRING_PROBE_SOURCE=WIRING_PROBE_SOURCE,WIRE_FIXTURE_SOURCE=WIRE_FIXTURE_SOURCE)
    exec(compile(FAULT_PROBE_SOURCE,'<owned-edge-fault-helpers>','exec'),F.__dict__)
    H=F.helpers();F.H=H;F.UNITS=H.UNITS
    return F,H


def manager_view(H,unit):
    require(unit in H.UNITS,'unit_not_registered')
    properties='LoadState,ActiveState,SubState,InvocationID,MainPID,ControlGroup,Result,ExecMainCode,ExecMainStatus,ExecStopPost,TimeoutStopUSec'
    raw=H.run(['/usr/bin/systemctl','show',unit,'--property='+properties],timeout=.5,check=False).stdout
    require(len(raw)<=8192,'manager_facts_limit')
    value={}
    for line in raw.decode('ascii').splitlines():
        key,sep,item=line.partition('=');require(sep and key not in value,'manager_facts_invalid');value[key]=item
    require({'LoadState','ActiveState','SubState','InvocationID','MainPID','ControlGroup'}<=set(value),'manager_facts_missing')
    return value


def wait_timeout(F,H,proof,receipt):
    until=proof['sent_ns']+9_000_000_000
    unit=proof['unit'];observed=None
    while time.monotonic_ns()<until:
        view=F.manager_view(unit)
        receipt['handler_observation']=handler_projection(view)
        receipt['handler_observed_ns']=time.monotonic_ns()
        if view['ActiveState']=='failed':
            observed=time.monotonic_ns();break
        time.sleep(.02)
    require(observed is not None,'handler_timeout_not_finished')
    markers=[H.safe_read(path) for path in H.ROOT.glob('edge-stop-*.json')]
    require(0<len(markers)<=2,'handler_marker_count_invalid')
    rows=[row for row in markers if type(row) is dict and row.get('invocation_id')==proof['invocation_id']]
    require(len(rows)==1 and rows[0].get('phase')=='stop_sleep','handler_instance_not_observed')
    started=rows[0]['at_ns'];require(started>=proof['sent_ns'],'handler_started_before_fault')
    receipt.update(handler_started_ns=started,handler_marker_pid=rows[0].get('pid'),
                   handler_marker_invocation_id=rows[0].get('invocation_id'))
    # Only PID1 messages for this exact owned unit, at most 16 small manager
    # records. Never request application output or transport/request content.
    raw=H.run(['/usr/bin/journalctl','--quiet','--no-pager','--output=json','-n','16',
               '_PID=1','UNIT='+unit],timeout=1).stdout
    require(len(raw)<=32768,'manager_journal_limit')
    logs=[json.loads(line) for line in raw.splitlines()]
    # Keep fixed event/time/instance coordinates even when the assertion below
    # rejects manager status. Do not print raw journal messages or Exec argv.
    diagnostic=[]
    for row in logs:
        if row.get('_PID')!='1':continue
        message=row.get('MESSAGE','')
        event='handler_timeout' if re.search(r"(?:State 'stop-post'|stop-post).*timed out",message) else (
            'handler_exit' if row.get('COMMAND')=='ExecStopPost' else None)
        if event is None:continue
        stamp=row.get('__MONOTONIC_TIMESTAMP','')
        invocation=next((row[key] for key in ('INVOCATION_ID','OBJECT_SYSTEMD_INVOCATION_ID','OBJECT_INVOCATION_ID')
                         if type(row.get(key)) is str and re.fullmatch('[a-f0-9]{32}',row[key])),None)
        diagnostic.append(dict(event=event,monotonic_ns=int(stamp)*1000 if type(stamp) is str and re.fullmatch('[0-9]{1,20}',stamp) else None,
                               invocation_id=invocation,
                               code=row.get('EXIT_CODE') if row.get('EXIT_CODE') in ('killed','exited','dumped') else None,
                               status=int(row['EXIT_STATUS']) if type(row.get('EXIT_STATUS')) is str and re.fullmatch('[0-9]{1,3}',row['EXIT_STATUS']) else None))
    receipt['handler_manager_events']=diagnostic
    H.record_receipt(receipt)
    require(type(rows[0].get('pid')) is int and rows[0]['pid']>1,'handler_marker_pid_invalid')
    require(view.get('InvocationID')==proof['invocation_id'],'handler_manager_invocation_changed')
    verify_timeout(view,logs,started,observed,pid=rows[0].get('pid'))
    return dict(handler_timeout_verified=True,handler_started_ns=started,
                handler_timeout_observed_ns=observed,handler_duration_ns=observed-started,
                handler_manager_killed=True)


def main(image):
    require(os.geteuid()==0 and EDGE_CASE in CASES,'root_or_case_invalid')
    require(type(image) is str and image and not image.startswith('-'),'image_invalid')
    F,H=helpers()
    receipt=dict(case=EDGE_CASE,nonce=H.NONCE,root=str(H.ROOT),units=list(H.UNITS),
                 bundle_sha256=PACKAGE_SHA256,probe_sha256=EDGE_PROBE_SHA256,
                 fault_probe_sha256=hashlib.sha256(FAULT_PROBE_SOURCE.encode()).hexdigest(),
                 receiver_id=None,api_create_pending=False,verified=False,resources_cleaned=False,
                 registration_retained=True,failure_code=None)
    binding=collector=None;zero_exit=None
    try:
        H.unpack_package()
        edge=hook_source(EDGE_CASE)
        source=edge if EDGE_CASE=='attach_disconnect' else F.hook_source('claim_watchdog_kill')+edge
        F.hook_source=lambda case:source
        F.install_hook('claim_watchdog_kill',receipt);H.record_receipt(receipt)
        image_id,api_id,manifest=F.setup_api(image,receipt)
        sys.path.insert(0,str(H.ROOT))
        from agent_d4_isolation.linux_engine import EngineClient
        from agent_d4_isolation.linux_identity import KernelCollector
        from agent_d4_isolation.runtime_supervisor import launch_session,state_call
        from agent_d4_isolation.runtime_state import StateStore
        engine=EngineClient();collector=KernelCollector(engine,image_id,api_id)
        (H.ROOT/'state').mkdir(mode=0o700);(H.ROOT/'state/journal').mkdir(mode=0o700)
        store=StateStore(H.ROOT)
        # Retain the manager's actual exit status while its StopPost still runs.
        def view(unit):
            nonlocal zero_exit
            if EDGE_CASE=='watchdog_exit_zero' and unit==H.UNITS[0]:
                watcher=manager_view(H,H.UNITS[1])
                if watcher.get('ExecMainCode')=='1' and watcher.get('ExecMainStatus')=='0':zero_exit=watcher
            value=manager_view(H,unit)
            if EDGE_CASE=='watchdog_exit_zero' and unit==H.UNITS[1] and value.get('ExecMainCode')=='1' and value.get('ExecMainStatus')=='0':zero_exit=value
            return value
        F.manager_view=view
        launch_session(H.ROOT,H.NONCE)
        def take_binding(value):
            nonlocal binding
            require(binding is None,'observer_already_retained');binding=value
        if EDGE_CASE=='attach_disconnect':
            binding,phase=wait_partial(H,collector,receipt,binding_ready=take_binding)
        else:
            binding,phase=F.wait_fault_phase('claim_watchdog_kill',collector,api_id,receipt,binding_ready=take_binding)
        state=state_call(lambda:store.read(H.NONCE),time.monotonic_ns()+200_000_000)
        require(not state['invalidated'],'session_invalid_before_fault')
        if EDGE_CASE=='attach_disconnect':
            fd=os.open(H.ROOT/'edge-release',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
            until=time.monotonic_ns()+1_000_000_000
            while time.monotonic_ns()<until:
                phase=H.safe_read(H.ROOT/'edge-marker.json')
                if phase and phase.get('phase')=='disconnected':break
                time.sleep(.005)
            require(phase and phase.get('phase')=='disconnected' and phase['bytes_written']==1
                    and phase['calls']==1 and phase['close_calls']==1,'attach_not_disconnected')
            proof=dict(unit=H.UNITS[0],invocation_id=state['controller_invocation_id'],
                       sent_ns=phase['disconnect_started_ns'],fault='attach_disconnect')
        else:
            proof=signal_usr1(F,H.UNITS[1]) if EDGE_CASE=='watchdog_exit_zero' else F.signal_unit(H.UNITS[1],signal.SIGKILL)
        receipt['fault_proof']=proof;H.record_receipt(receipt)
        detection_proof=dict(proof,unit=H.UNITS[0],invocation_id=state['controller_invocation_id'])
        detection=F.wait_detected(detection_proof)
        done=F.wait_reclaimed(binding,detection['earliest_detection_ns'])
        receipt.update(detection_witness=detection,reclaim_observed_ns=done,
                       detection_ns=detection['observed_ns']-proof['sent_ns'],
                       reclaim_ns=done-detection['earliest_detection_ns'],
                       receiver_stopped=True,observer_cgroup_empty=True,
                       written_bytes=phase['bytes_written'],write_calls=phase['calls'])
        require(H.assert_owned(api_id,image_id,'api')['State']['Running'],'api_stopped')
        receipt['api_survived']=True
        current=H.safe_read(H.ROOT/'edge-marker.json') if EDGE_CASE=='attach_disconnect' else F.marker()
        require(current==phase,'stdin_replayed_after_fault');receipt['no_replay']=True
        H.summarize_runtime(receipt)
        require(receipt['state_summary']['invalidated'],'session_not_invalidated')
        receipt['infrastructure_result']='isolation_terminated' if receipt['journal_summary']['closed_by']=='reclaim_verified' else 'isolation_unknown'
        # Preserve this boundary even when the deliberately slow manager handler
        # later fails or a later cleanup legitimately obtains more evidence.
        H.record_receipt(receipt)
        if EDGE_CASE=='watchdog_exit_zero':
            view(H.UNITS[1]);require(zero_exit is not None,'watchdog_exit_status_lost')
            verify_zero_exit(zero_exit,proof['invocation_id'])
            receipt.update(watchdog_exit_code=0,watchdog_exit_verified=True)
        elif EDGE_CASE=='stop_post_timeout':receipt.update(wait_timeout(F,H,proof,receipt))
        receipt['verified']=True
    except Exception as error:
        receipt['failure_code']=str(error) if type(error) in (EdgeFailure,F.FaultFailure,H.ProbeFailure) else 'runtime_edge_unknown'
    finally:
        if H.ROOT.exists():
            H.summarize_runtime(receipt,'post_observation_');F.cleanup(receipt,binding,collector)
            if H.ROOT.exists():H.record_receipt(receipt)
        print(json.dumps(receipt,sort_keys=True),flush=True)
    require(receipt['verified'] and receipt['resources_cleaned'],'edge_not_verified')
    print('runtime_supervision_edge_verified:'+EDGE_CASE,flush=True)


if __name__=='__main__':
    try:
        require(len(sys.argv)==2,'image_required');main(sys.argv[1])
    except Exception:
        print('runtime_supervision_edge_failed',flush=True)
        raise SystemExit(1)
