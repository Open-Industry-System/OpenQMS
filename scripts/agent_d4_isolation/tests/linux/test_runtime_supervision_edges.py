"""Opt-in real two-unit edge failures; local tests validate test-only hooks."""
import importlib.util
import hashlib
import json
import os
import shlex
from pathlib import Path
import signal
import sys
import time
import types
import pytest

HERE=Path(__file__).resolve().parent
CASES=('watchdog_exit_zero','stop_post_timeout','attach_disconnect')


@pytest.mark.parametrize('case',CASES)
def test_real_two_unit_supervision_edges(remote,case):
    spec=importlib.util.spec_from_file_location('_edges_bundle',HERE/'test_runtime_wiring.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bundle,digest=module._package_bundle();probe=(HERE/'runtime_supervision_edges_probe.py').read_text()
    values=dict(PACKAGE_B64=bundle,PACKAGE_SHA256=digest,EDGE_CASE=case,
                EDGE_PROBE_SHA256=hashlib.sha256(probe.encode()).hexdigest(),
                FAULT_PROBE_SOURCE=(HERE/'runtime_faults_probe.py').read_text(),
                WIRING_PROBE_SOURCE=(HERE/'runtime_wiring_probe.py').read_text(),
                WIRE_FIXTURE_SOURCE=(HERE.parents[3]/'backend/tests/e2e/d4_text_wire_fixture.py').read_text())
    source=''.join(key+'='+repr(value)+'\n' for key,value in values.items())+probe
    image=os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE');assert image
    output=remote('sudo -n /usr/bin/python3 -I -S -B - '+shlex.quote(image)+
                  " <<'SUPERVISION_EDGE'\n"+source+'\nSUPERVISION_EDGE\n',timeout=180,check=False)
    print(output)
    rows=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert len(rows)==1,output
    row=rows[0]
    assert row['case']==case and row['verified'] and row['resources_cleaned'],row
    assert row['receiver_stopped'] and row['observer_cgroup_empty'] and row['api_survived'] and row['no_replay'],row
    assert row['detection_ns']==row['detection_witness']['observed_ns']-row['fault_proof']['sent_ns']<=2_000_000_000,row
    assert row['reclaim_ns']==row['reclaim_observed_ns']-row['detection_witness']['earliest_detection_ns']<=5_000_000_000,row
    if case=='watchdog_exit_zero':assert row['watchdog_exit_code']==0 and row['watchdog_exit_verified'],row
    elif case=='stop_post_timeout':assert row['handler_timeout_verified'] and row['handler_manager_killed'],row
    else:assert row['written_bytes']==1 and row['write_calls']==1,row
    if row['journal_summary']['state']!='closed':assert row['registration_retained'],row
    assert 'runtime_supervision_edge_verified:'+case in output.splitlines(),output


def _probe():
    spec=importlib.util.spec_from_file_location('_supervision_edges',HERE/'runtime_supervision_edges_probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_local_normal_exit_hook_uses_usr1_and_exit_zero(tmp_path,monkeypatch):
    probe=_probe();handlers={};exits=[]
    entry=tmp_path/'agent_d4_isolation/deploy/runtime_entry.py'
    monkeypatch.setattr(sys,'argv',[str(entry),'watchdog','--nonce','a'*64])
    monkeypatch.setattr(signal,'signal',lambda sig,fn:handlers.setdefault(sig,fn))
    monkeypatch.setattr(probe.os,'_exit',exits.append)
    exec(compile(probe.hook_source('watchdog_exit_zero'),'<edge-hook>','exec'),{'__file__':str(entry)})
    assert set(handlers)=={signal.SIGUSR1}
    handlers[signal.SIGUSR1](signal.SIGUSR1,None)
    assert exits==[0]
    assert json.loads((tmp_path/'edge-marker.json').read_text())['phase']=='exit_zero'


def test_local_attach_disconnect_writes_one_real_byte_and_closes_once(tmp_path,monkeypatch):
    probe=_probe();writes=[];closed=[]
    package=types.ModuleType('agent_d4_isolation');engine=types.ModuleType('agent_d4_isolation.linux_engine')
    class IO:
        def write(self,data,deadline_ns):writes.append(bytes(data));return len(data)
        def close(self):closed.append(self)
    engine.AttachedIO=IO;package.linux_engine=engine
    monkeypatch.setitem(sys.modules,'agent_d4_isolation',package)
    monkeypatch.setitem(sys.modules,'agent_d4_isolation.linux_engine',engine)
    monkeypatch.setattr(sys,'path',list(sys.path))
    entry=tmp_path/'agent_d4_isolation/deploy/runtime_entry.py'
    monkeypatch.setattr(sys,'argv',[str(entry),'controller','--nonce','a'*64])
    (tmp_path/'edge-release').touch(mode=0o600)
    exec(compile(probe.hook_source('attach_disconnect'),'<edge-hook>','exec'),{'__file__':str(entry)})
    stream=engine.AttachedIO()
    assert stream.write(b'nonsecret-fixture-config',10**18)==1
    with pytest.raises(OSError):stream.write(b'remainder',10**18)
    assert writes==[b'n'] and closed==[stream]
    witness=json.loads((tmp_path/'edge-marker.json').read_text())
    assert witness['phase']=='disconnected' and witness['bytes_written']==1 and witness['calls']==1
    assert 'nonsecret' not in (tmp_path/'edge-marker.json').read_text()


def test_local_stop_timeout_hook_does_not_run_stop_body(tmp_path,monkeypatch):
    probe=_probe();sleeps=[]
    entry=tmp_path/'agent_d4_isolation/deploy/runtime_entry.py'
    monkeypatch.setattr(sys,'argv',[str(entry),'stop','--nonce','a'*64])
    class Interrupted(Exception):pass
    def sleep(seconds):sleeps.append(seconds);raise Interrupted()
    monkeypatch.setattr(time,'sleep',sleep)
    with pytest.raises(Interrupted):
        exec(compile(probe.hook_source('stop_post_timeout'),'<edge-hook>','exec'),{'__file__':str(entry)})
    assert sleeps==[30]
    assert json.loads(next(tmp_path.glob('edge-stop-*.json')).read_text())['phase']=='stop_sleep'


@pytest.mark.parametrize('status,code',[('0','2'),('15','1')])
def test_local_exit_zero_requires_actual_manager_exit_code(status,code):
    probe=_probe()
    with pytest.raises(probe.EdgeFailure):
        probe.verify_zero_exit({'InvocationID':'b'*32,'ExecMainCode':code,'ExecMainStatus':status},'b'*32)
    probe.verify_zero_exit({'InvocationID':'b'*32,'ExecMainCode':'1','ExecMainStatus':'0'},'b'*32)


def test_local_timeout_proof_rejects_elapsed_time_without_manager_timeout():
    probe=_probe()
    with pytest.raises(probe.EdgeFailure):
        probe.verify_timeout({'ExecStopPost':'code=killed ; status=15'},[],0,6_100_000_000)
    probe.verify_timeout({'ExecStopPost':'code=killed ; status=15'},
                         [{'MESSAGE':"State 'stop-post' timed out. Killing.",'_PID':'1'}],0,6_100_000_000)


def test_local_timeout_requires_same_handler_pid():
    probe=_probe()
    rows=[{'MESSAGE':"State 'stop-post' timed out. Killing.",'_PID':'1'}]
    with pytest.raises(probe.EdgeFailure):
        probe.verify_timeout({'ExecStopPost':'pid=43 ; code=killed ; status=15'},rows,0,6_100_000_000,pid=42)
    probe.verify_timeout({'ExecStopPost':'pid=42 ; code=killed ; status=15'},rows,0,6_100_000_000,pid=42)


@pytest.mark.parametrize('status',['15/TERM','9/KILL'])
def test_local_timeout_accepts_systemd_255_signal_display(status):
    probe=_probe()
    view={'ExecStopPost':'{ path=/fixed/entry ; argv[]=fixed stop ; pid=42 ; code=killed ; status='+status+' }'}
    rows=[{'MESSAGE':"State 'stop-post' timed out. Terminating.",'_PID':'1'}]
    probe.verify_timeout(view,rows,0,6_100_000_000,pid=42)


@pytest.mark.parametrize('status',['15/KILL','9/TERM','15/SECRET','150/TERM'])
def test_local_timeout_rejects_inconsistent_signal_suffix(status):
    probe=_probe()
    with pytest.raises(probe.EdgeFailure):
        probe.verify_timeout({'ExecStopPost':'pid=42 ; code=killed ; status='+status},
                             [{'MESSAGE':"State 'stop-post' timed out. Terminating.",'_PID':'1'}],0,6_100_000_000,pid=42)


def test_local_manager_projection_never_copies_command_or_unknown_text():
    probe=_probe()
    view={'InvocationID':'b'*32,'ActiveState':'failed','SubState':'failed',
          'ExecStopPost':'{ path=/secret/private/config ; argv[]=raw-token-SECRET ; pid=42 ; code=killed ; status=15/TERM }'}
    assert probe.handler_projection(view)==dict(invocation_id='b'*32,active_state='failed',sub_state='failed',
                                                pid=42,code='killed',status=15,signal='TERM')
    view['ExecStopPost']='pid=42 ; code=RAW-SECRET ; status=SECRET'
    assert 'SECRET' not in json.dumps(probe.handler_projection(view))


def test_local_timeout_failure_preserves_safe_manager_and_pid1_evidence(tmp_path,monkeypatch):
    probe=_probe();invocation='b'*32;unit='owned-watchdog';saved=[]
    marker=tmp_path/'edge-stop-42.json'
    marker.write_text(json.dumps(dict(invocation_id=invocation,phase='stop_sleep',at_ns=1,pid=42)))
    view=dict(InvocationID=invocation,ActiveState='failed',SubState='failed',
              ExecStopPost='pid=42 ; code=exited ; status=0 ; argv[]=SECRET')
    rows=[dict(_PID='1',INVOCATION_ID=invocation,__MONOTONIC_TIMESTAMP='6000000',
               MESSAGE="State 'stop-post' timed out. Terminating.")]
    H=types.SimpleNamespace(ROOT=tmp_path,safe_read=lambda path:json.loads(path.read_text()),
                            run=lambda *args,**kwargs:types.SimpleNamespace(stdout=json.dumps(rows[0]).encode()+b'\n'),
                            record_receipt=lambda value:saved.append(json.loads(json.dumps(value))))
    F=types.SimpleNamespace(manager_view=lambda unit:view)
    monkeypatch.setattr(probe.time,'monotonic_ns',lambda:6_100_000_000)
    receipt={}
    with pytest.raises(probe.EdgeFailure,match='handler_not_manager_killed'):
        probe.wait_timeout(F,H,dict(unit=unit,sent_ns=0,invocation_id=invocation),receipt)
    assert receipt['handler_observation']['pid']==42
    assert receipt['handler_observation']['code']=='exited'
    assert receipt['handler_manager_events'][0]['monotonic_ns']==6_000_000_000
    assert saved and 'SECRET' not in json.dumps(saved)


def test_local_test_hooks_compile_with_unchanged_entry_and_reject_other_cases():
    probe=_probe();entry=(HERE.parents[1]/'deploy/runtime_entry.py').read_text()
    for case in CASES:compile(probe.hook_source(case)+entry,'<edge-with-production-entry>','exec')
    with pytest.raises(probe.EdgeFailure):probe.hook_source('arbitrary-command')


def test_local_partial_wait_hands_off_fd_before_marker_read_failure():
    probe=_probe();owned=[];closed=[]
    state={'receiver_id':'a'*64,'snapshot':{'safe':1}}
    class Binding:
        def snapshot(self):return {'safe':1}
        def close(self):closed.append(True)
    binding=Binding()
    def read(path):
        if path.name=='edge-marker.json':raise OSError('marker unavailable')
        return state
    H=types.SimpleNamespace(ROOT=Path('/unused'),NONCE='b'*64,safe_read=read,
                            assert_owned=lambda *args:None,record_receipt=lambda receipt:None)
    collector=types.SimpleNamespace(bind=lambda *args:binding)
    with pytest.raises(OSError):
        probe.wait_partial(H,collector,{'image_id':'image'},binding_ready=owned.append)
    assert owned==[binding] and closed==[]


def test_local_exact_usr1_signal_rejects_replaced_manager_invocation(monkeypatch):
    probe=_probe();sent=[]
    unit='registered-watchdog'
    views=iter([dict(ActiveState='active',InvocationID=key*32,MainPID='123',ControlGroup='/system.slice/'+unit)
                for key in ('b','c')])
    F=types.SimpleNamespace(UNITS=(unit,),manager_view=lambda unit:next(views),
                            process_starttime=lambda *args:10,manager_watchdog_stamp=lambda view:0)
    monkeypatch.setattr(probe.os,'pidfd_open',lambda *args:44,raising=False)
    monkeypatch.setattr(probe.os,'close',lambda fd:None)
    monkeypatch.setattr(signal,'pidfd_send_signal',lambda *args:sent.append(args),raising=False)
    with pytest.raises(probe.EdgeFailure):probe.signal_usr1(F,unit)
    assert sent==[]
