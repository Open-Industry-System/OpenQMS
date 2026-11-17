"""Opt-in, authority-free faults through the actual two-unit receiver runtime.

The fixture has no platform grants, employee identity, database, or provider.
Local tests below exercise only probe authority checks; they are not Linux gates.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex

import pytest

HERE=Path(__file__).resolve().parent
PACKAGE=HERE.parents[1]
REPOSITORY=HERE.parents[3]
CASES=('ready_watchdog_kill','before_stdin_watchdog_kill','partial_stdin_watchdog_kill',
       'claim_watchdog_kill','claim_watchdog_stop','claim_controller_kill')


def _bundle():
    spec=importlib.util.spec_from_file_location('_runtime_faults_bundle',HERE/'test_runtime_wiring.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module._package_bundle()


@pytest.mark.parametrize('case',CASES)
def test_real_runtime_single_fault_without_platform_authority(remote,case):
    image=os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE')
    assert image,'explicit pinned receiver image required'
    bundle,digest=_bundle()
    wiring=(HERE/'runtime_wiring_probe.py').read_text()
    source=(HERE/'runtime_faults_probe.py').read_text()
    fixture=(REPOSITORY/'backend/tests/e2e/d4_text_wire_fixture.py').read_text()
    constants=dict(PACKAGE_B64=bundle,PACKAGE_SHA256=digest,WIRE_FIXTURE_SOURCE=fixture,
                   WIRING_PROBE_SOURCE=wiring,FAULT_CASE=case,
                   FAULT_PROBE_SHA256=hashlib.sha256(source.encode()).hexdigest())
    probe=''.join(key+' = '+repr(value)+'\n' for key,value in constants.items())+source
    output=remote('sudo -n /usr/bin/python3 -I -S -B - '+shlex.quote(image)+
                  " <<'D4_RUNTIME_FAULT'\n"+probe+'\nD4_RUNTIME_FAULT\n',timeout=180,check=False)
    print(output)
    receipts=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert len(receipts)==1,output
    receipt=receipts[0]
    assert receipt['case']==case and receipt['fault_verified'] is True,receipt
    assert receipt['resources_cleaned'] is True,receipt
    assert receipt['failure_code'] is None,receipt
    assert receipt['api_survived_fault'] is True,receipt
    witness=receipt['detection_witness'];sent=receipt['signal_proof']['sent_ns']
    assert set(witness)=={'observed_ns','earliest_detection_ns'},receipt
    assert sent<=witness['earliest_detection_ns']<=witness['observed_ns'],receipt
    assert receipt['detection_ns']==witness['observed_ns']-sent<=2_000_000_000,receipt
    assert receipt['reclaim_ns']==receipt['reclaim_observed_ns']-witness['earliest_detection_ns']<=5_000_000_000,receipt
    if case=='ready_watchdog_kill':
        assert receipt['journal_summary']['closed_by']=='create_absent',receipt
        assert receipt['receiver_id'] is None and receipt['written_bytes']==0,receipt
    else:
        assert receipt['receiver_stopped'] is True and receipt['observer_cgroup_empty'] is True,receipt
    if case=='before_stdin_watchdog_kill':
        assert receipt['state_summary']['first_stdin_ns'] is None and receipt['written_bytes']==0,receipt
    elif case=='partial_stdin_watchdog_kill':
        assert receipt['state_summary']['first_stdin_ns'] is not None and receipt['written_bytes']==1,receipt
    if receipt['journal_summary']['state']!='closed':
        assert receipt['registration_retained'] is True,receipt
        assert receipt['infrastructure_result']=='isolation_unknown',receipt
    assert 'runtime_fault_verified:'+case in output.splitlines(),output


def _local_probe():
    spec=importlib.util.spec_from_file_location('_runtime_faults_local',HERE/'runtime_faults_probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_local_fault_hook_is_fixed_and_records_only_counts():
    probe=_local_probe()
    source=probe.hook_source('partial_stdin_watchdog_kill')
    assert 'data[:1]' in source and 'bytes_written' in source
    assert 'read_private_config' not in source
    assert 'installation-secret' not in source and 'subprocess' not in source
    with pytest.raises(probe.FaultFailure):probe.hook_source('arbitrary-command')


def test_local_unit_signal_rejects_changed_invocation_before_sending(monkeypatch):
    probe=_local_probe();unit='openqms-d4-watchdog-'+'a'*64+'.service'
    monkeypatch.setattr(probe,'UNITS',(unit,))
    views=iter((dict(ActiveState='active',InvocationID='b'*32,MainPID='123',ControlGroup='/system.slice/'+unit),
                dict(ActiveState='active',InvocationID='c'*32,MainPID='123',ControlGroup='/system.slice/'+unit)))
    monkeypatch.setattr(probe,'manager_view',lambda name:next(views))
    monkeypatch.setattr(probe,'process_starttime',lambda pid,unit:10,raising=False)
    monkeypatch.setattr(probe.os,'pidfd_open',lambda pid,flags=0:44,raising=False)
    closed=[];sent=[]
    monkeypatch.setattr(probe.os,'close',closed.append)
    monkeypatch.setattr(probe.signal,'pidfd_send_signal',lambda *args:sent.append(args),raising=False)
    with pytest.raises(probe.FaultFailure):probe.signal_unit(unit,probe.signal.SIGKILL)
    assert sent==[] and closed==[44]


def test_local_unknown_registration_is_never_deleted():
    probe=_local_probe()
    assert not probe.may_remove_registration({'state':'stopping','closed_by':None})
    assert not probe.may_remove_registration({'state':'unresolved','closed_by':None})
    assert not probe.may_remove_registration({'state':'stopping','closed_by':'reclaim_verified'})
    assert probe.may_remove_registration({'state':'closed','closed_by':'reclaim_verified'})

def test_local_cleanup_attempts_owned_api_even_when_unit_stop_fails(monkeypatch,tmp_path):
    from types import SimpleNamespace
    probe=_local_probe();removed=[]
    def failed(*args,**kwargs):raise OSError('must-not-leak')
    fake=SimpleNamespace(ROOT=tmp_path,NONCE='a'*64,RECEIVER_LABEL='receiver',SMOKE_LABEL='api',
                         run=failed,safe_read=lambda path:{'state':'stopping','closed_by':None},
                         exact_matches=lambda label:(),assert_owned=lambda *args:{'State':{'Running':True}},
                         docker=lambda *args:removed.append(args),absent=lambda identity:None)
    monkeypatch.setattr(probe,'H',fake)
    monkeypatch.setattr(probe,'UNITS',('registered-controller','registered-watchdog'))
    monkeypatch.setattr(probe,'manager_view',lambda unit:{'ActiveState':'inactive','LoadState':'not-found'})
    receipt={'api_id':'e'*64,'image_id':'sha256:'+'f'*64,'api_create_pending':False,
             'journal_summary':{'state':'stopping','closed_by':None}}
    assert not probe.cleanup(receipt,None,None)
    assert ('rm','-f','e'*64) in removed
    assert receipt['registration_retained'] and tmp_path.exists()
    assert receipt['cleanup_errors']
    assert 'must-not-leak' not in json.dumps(receipt)


def test_local_pidfd_target_rejects_kernel_pid_reuse_with_same_manager_facts(monkeypatch):
    probe=_local_probe();unit='openqms-d4-controller-'+'a'*64+'.service'
    monkeypatch.setattr(probe,'UNITS',(unit,))
    view=dict(ActiveState='active',InvocationID='b'*32,MainPID='123',ControlGroup='/system.slice/'+unit)
    monkeypatch.setattr(probe,'manager_view',lambda name:dict(view))
    times=iter((10,11))
    monkeypatch.setattr(probe,'process_starttime',lambda pid,unit:next(times),raising=False)
    monkeypatch.setattr(probe.os,'pidfd_open',lambda pid,flags=0:44,raising=False)
    closed=[];sent=[]
    monkeypatch.setattr(probe.os,'close',closed.append)
    monkeypatch.setattr(probe.signal,'pidfd_send_signal',lambda *args:sent.append(args),raising=False)
    with pytest.raises(probe.FaultFailure):probe.signal_unit(unit,probe.signal.SIGKILL)
    assert sent==[] and closed==[44]

@pytest.mark.parametrize('phase,early_write',[('before_stdin_watchdog_kill',False),('partial_stdin_watchdog_kill',False),('before_stdin_watchdog_kill',True)])
def test_local_hooks_pause_at_zero_or_one_actual_byte_without_storing_payload(tmp_path,monkeypatch,phase,early_write):
    import sys
    import time
    import types
    probe=_local_probe();calls=[];reads=[]
    package=types.ModuleType('agent_d4_isolation')
    engine=types.ModuleType('agent_d4_isolation.linux_engine')
    contracts=types.ModuleType('agent_d4_isolation.contracts')
    class IO:
        def write(self,data,deadline_ns):calls.append(bytes(data));return len(data)
    engine.AttachedIO=IO
    contracts.read_private_config=lambda path:reads.append(path)
    package.linux_engine=engine;package.contracts=contracts
    monkeypatch.setitem(sys.modules,'agent_d4_isolation',package)
    monkeypatch.setitem(sys.modules,'agent_d4_isolation.linux_engine',engine)
    monkeypatch.setitem(sys.modules,'agent_d4_isolation.contracts',contracts)
    entry=tmp_path/'agent_d4_isolation/deploy/runtime_entry.py'
    monkeypatch.setattr(sys,'argv',[str(entry),'controller','--nonce','a'*64])
    monkeypatch.setattr(sys,'path',list(sys.path))
    class StopRequested(Exception):pass
    def stopped(seconds):raise StopRequested()
    monkeypatch.setattr(time,'sleep',stopped)
    namespace={'__file__':str(entry)}
    exec(compile(probe.hook_source(phase),'<owned-fault-hook>','exec'),namespace)
    if early_write:engine.AttachedIO().write(b'x',10**18)
    with pytest.raises(StopRequested):
        if phase.startswith('before_'):contracts.read_private_config(tmp_path/'private/config.json')
        else:engine.AttachedIO().write(b'payload-must-not-be-persisted',10**18)
    witness=json.loads((tmp_path/'fault-marker.json').read_text())
    assert witness['bytes_written']==(1 if early_write or phase.startswith('partial_') else 0)
    assert calls==([b'x'] if early_write else ([] if phase.startswith('before_') else [b'p'])) and reads==[]
    assert 'payload' not in (tmp_path/'fault-marker.json').read_text()


def test_local_delayed_wire_and_all_fixed_hooks_compile_without_receiver_edits(monkeypatch):
    probe=_local_probe()
    monkeypatch.setattr(probe,'PACKAGE_B64','',raising=False)
    monkeypatch.setattr(probe,'PACKAGE_SHA256','0'*64,raising=False)
    monkeypatch.setattr(probe,'WIRE_FIXTURE_SOURCE',(REPOSITORY/'backend/tests/e2e/d4_text_wire_fixture.py').read_text(),raising=False)
    monkeypatch.setattr(probe,'WIRING_PROBE_SOURCE',(HERE/'runtime_wiring_probe.py').read_text(),raising=False)
    original=probe.helpers()
    monkeypatch.setattr(probe,'H',original)
    wire=probe.api_source()
    assert 'if index==0:time.sleep(8)' in wire and 'except OSError: break' in wire
    compile(wire,'<owned-delayed-wire>','exec')
    entry=(PACKAGE/'deploy/runtime_entry.py').read_text()
    for case in CASES:compile(probe.hook_source(case)+entry,'<owned-test-entry>','exec')

def test_local_detection_timeout_never_accepts_an_active_unit(monkeypatch):
    probe=_local_probe()
    class Clock:
        value=0
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock()
    monkeypatch.setattr(probe.time,'monotonic_ns',clock)
    monkeypatch.setattr(probe.time,'sleep',clock.sleep)
    monkeypatch.setattr(probe,'manager_view',lambda unit:{'ActiveState':'active'})
    with pytest.raises(probe.FaultFailure):probe.wait_detected({'sent_ns':0,'unit':'registered-unit'})
    assert clock.value<=2_000_000_000


@pytest.mark.parametrize('running,tasks',[(False,1),(True,0),(False,None)])
def test_local_reclaim_needs_both_current_engine_and_original_empty_cgroup(monkeypatch,running,tasks):
    from types import SimpleNamespace
    probe=_local_probe()
    class Clock:
        value=0
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock()
    monkeypatch.setattr(probe.time,'monotonic_ns',clock)
    monkeypatch.setattr(probe.time,'sleep',clock.sleep)
    binding=SimpleNamespace(container_running=lambda deadline:running,tasks_remaining=lambda:tasks)
    with pytest.raises(probe.FaultFailure):probe.wait_reclaimed(binding,0)
    assert clock.value<=5_015_000_000

def test_local_delayed_manager_observation_cannot_extend_real_reclaim_budget(monkeypatch):
    from types import SimpleNamespace
    probe=_local_probe()
    class Clock:
        value=0
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock()
    monkeypatch.setattr(probe.time,'monotonic_ns',clock)
    monkeypatch.setattr(probe.time,'sleep',clock.sleep)
    def delayed_query(unit):
        # Manager detected at t=0; its status RPC returns only at t=1s.
        clock.value=1_000_000_000
        return {'ActiveState':'deactivating'}
    monkeypatch.setattr(probe,'manager_view',delayed_query)
    observed=probe.wait_detected({'sent_ns':0,'unit':'registered-unit'})
    lower=observed['earliest_detection_ns'] if isinstance(observed,dict) else observed
    binding=SimpleNamespace(container_running=lambda deadline:clock.value<5_800_000_000,
                            tasks_remaining=lambda:0 if clock.value>=5_800_000_000 else 1)
    with pytest.raises(probe.FaultFailure):probe.wait_reclaimed(binding,lower)
    assert observed=={'observed_ns':1_000_000_000,'earliest_detection_ns':0}


def test_local_fault_boundary_stopping_survives_later_closed_cleanup(tmp_path,monkeypatch,capsys):
    import shutil
    import stat
    from types import SimpleNamespace
    probe=_local_probe();deleted=[]
    stopping={'state':'stopping','closed_by':None,'container_id':None}
    closed={'state':'closed','closed_by':'create_absent','container_id':None}
    def record(receipt):
        receipt.setdefault('journal_summary',dict(stopping))
        receipt.setdefault('state_summary',{'invalidated':True})
        receipt.setdefault('infrastructure_result','isolation_unknown')
    def summarize(receipt,prefix=''):
        receipt[prefix+'journal_summary']=dict(closed)
        receipt[prefix+'state_summary']={'invalidated':True}
    fake=SimpleNamespace(ROOT=tmp_path,NONCE='a'*64,UNITS=(),
                         unpack_package=lambda:None,record_receipt=record,
                         summarize_runtime=summarize,run=lambda *a,**kw:None,
                         safe_read=lambda path:dict(closed),exact_matches=lambda label:(),
                         RECEIVER_LABEL='receiver',SMOKE_LABEL='api')
    monkeypatch.setattr(probe,'helpers',lambda:fake)
    monkeypatch.setattr(probe,'install_hook',lambda *args:None)
    def fail_api(*args):raise probe.FaultFailure('planned_fault_boundary')
    monkeypatch.setattr(probe,'setup_api',fail_api)
    for name,value in {'FAULT_CASE':'before_stdin_watchdog_kill','PACKAGE_SHA256':'0'*64,
                       'FAULT_PROBE_SHA256':'1'*64,'WIRING_PROBE_SOURCE':''}.items():
        monkeypatch.setattr(probe,name,value,raising=False)
    monkeypatch.setattr(probe.os,'geteuid',lambda:0)
    original_lstat=Path.lstat
    monkeypatch.setattr(Path,'lstat',lambda path:SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
                        if path==tmp_path else original_lstat(path))
    monkeypatch.setattr(shutil,'rmtree',lambda path:deleted.append(path))
    with pytest.raises(probe.FaultFailure):probe.main('pinned-fixture')
    receipt=json.loads(capsys.readouterr().out.splitlines()[0])
    assert receipt['journal_summary']==stopping
    assert receipt['infrastructure_result']=='isolation_unknown'
    assert receipt['post_observation_journal_summary']==closed
    assert receipt['registration_retained'] and not deleted

@pytest.mark.parametrize('wrong_instance',[False,True])
def test_local_detection_lower_bound_uses_credentialed_active_query_start(monkeypatch,wrong_instance):
    probe=_local_probe()
    class Clock:
        value=200_000_000
        def __call__(self):return self.value
        def sleep(self,seconds):self.value+=int(seconds*1e9)
    clock=Clock();queries=[]
    monkeypatch.setattr(probe.time,'monotonic_ns',clock)
    monkeypatch.setattr(probe.time,'sleep',clock.sleep)
    def query(unit):
        queries.append(clock.value)
        if len(queries)==1:
            clock.value=500_000_000
            return {'ActiveState':'active','InvocationID':('c' if wrong_instance else 'b')*32}
        clock.value=1_000_000_000
        return {'ActiveState':'deactivating','InvocationID':'b'*32}
    monkeypatch.setattr(probe,'manager_view',query)
    proof={'sent_ns':0,'unit':'registered-unit','invocation_id':'b'*32}
    if wrong_instance:
        with pytest.raises(probe.FaultFailure):probe.wait_detected(proof)
    else:
        assert probe.wait_detected(proof)=={'observed_ns':1_000_000_000,'earliest_detection_ns':200_000_000}

def test_local_signal_receipt_freezes_current_manager_watchdog_timestamp(monkeypatch):
    probe=_local_probe();unit='openqms-d4-watchdog-'+'a'*64+'.service'
    monkeypatch.setattr(probe,'UNITS',(unit,))
    facts=dict(ActiveState='active',InvocationID='b'*32,MainPID='123',ControlGroup='/system.slice/'+unit,
               WatchdogTimestampMonotonic='2',WatchdogUSec='1s')
    monkeypatch.setattr(probe,'manager_view',lambda name:dict(facts))
    monkeypatch.setattr(probe,'process_starttime',lambda pid,unit:10)
    monkeypatch.setattr(probe.os,'pidfd_open',lambda pid,flags=0:44,raising=False)
    monkeypatch.setattr(probe.os,'close',lambda fd:None)
    monkeypatch.setattr(probe.signal,'pidfd_send_signal',lambda *args:None,raising=False)
    monkeypatch.setattr(probe.time,'monotonic_ns',lambda:3000)
    proof=probe.signal_unit(unit,probe.signal.SIGSTOP)
    assert proof['watchdog_timestamp_ns_before_signal']==2000
    assert proof['watchdog_usec_property']=='1s' and proof['sent_ns']==3000

@pytest.mark.parametrize('publish_after',[1,2])
def test_local_claim_refreshes_marker_after_seen_log_publication(monkeypatch,tmp_path,publish_after):
    from types import SimpleNamespace
    probe=_local_probe();published=[False];owned=[];queries=[0]
    state={'receiver_id':'c'*64,'snapshot':{'original':'identity'}}
    class Binding:
        closed=False
        def snapshot(self):return dict(state['snapshot'])
        def close(self):self.closed=True
    binding=Binding()
    class Collector:
        def bind(self,*args):return binding
    witness={'phase':'claim_write','bytes_written':100,'calls':1}
    def logs(*args,**kwargs):
        queries[0]+=1
        published[0]=queries[0]>=publish_after
        return SimpleNamespace(stdout=b'ready\nseen_0\n')
    fake=SimpleNamespace(ROOT=tmp_path,NONCE='a'*64,safe_read=lambda path:state,
                         assert_owned=lambda *args:None,record_receipt=lambda value:None,docker=logs)
    monkeypatch.setattr(probe,'H',fake);monkeypatch.setattr(probe,'UNITS',('controller','watchdog'))
    monkeypatch.setattr(probe,'marker',lambda:dict(witness) if published[0] else None)
    monkeypatch.setattr(probe,'manager_view',lambda unit:{'ActiveState':'active'})
    result,phase=probe.wait_fault_phase('claim_watchdog_kill',Collector(),'api',{'image_id':'image'},binding_ready=owned.append)
    assert result is binding and phase==witness and owned==[binding] and not binding.closed


@pytest.mark.parametrize('fail_at',['logs','identity'])
def test_local_phase_failure_does_not_discard_original_observer_fd(monkeypatch,tmp_path,fail_at):
    from types import SimpleNamespace
    probe=_local_probe();owned=[]
    state={'receiver_id':'c'*64,'snapshot':{'original':'identity'}}
    class Binding:
        closed=False
        def snapshot(self):return dict(state['snapshot']) if fail_at=='logs' else {'changed':'identity'}
        def close(self):self.closed=True
    binding=Binding()
    class Collector:
        def bind(self,*args):return binding
    def failed_logs(*args,**kwargs):raise OSError('fixed-diagnostic-only')
    fake=SimpleNamespace(ROOT=tmp_path,NONCE='a'*64,safe_read=lambda path:state,
                         assert_owned=lambda *args:None,record_receipt=lambda value:None,docker=failed_logs)
    monkeypatch.setattr(probe,'H',fake);monkeypatch.setattr(probe,'marker',lambda:None)
    with pytest.raises(OSError if fail_at=='logs' else probe.FaultFailure):probe.wait_fault_phase('claim_watchdog_kill',Collector(),'api',{'image_id':'image'},binding_ready=owned.append)
    assert owned==[binding] and not binding.closed
