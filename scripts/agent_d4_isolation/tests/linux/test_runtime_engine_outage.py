"""Session-management Engine outage through the real two-unit supervision chain."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import pytest
HERE=Path(__file__).resolve().parent

def probe():
    spec=importlib.util.spec_from_file_location('_outage_local',HERE/'runtime_engine_outage_probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_local_request_boundary_delegates_then_fails_without_daemon_access():
    p=probe();calls=[]
    def original(*args,**kwargs):calls.append((args,kwargs));return b'OK'
    class EngineError(Exception):pass
    assert p.request_boundary(original,False,EngineError,'GET','/_ping',123,body=None)==b'OK'
    assert calls==[(('GET','/_ping',123),{'body':None})]
    with pytest.raises(EngineError,match='engine_unavailable'):
        p.request_boundary(original,True,EngineError,'GET','/_ping',123)
    assert len(calls)==1


def test_local_kill_observer_records_only_after_real_original_capability():
    p=probe();events=[]
    def kill():events.append('actual_kill')
    p.observe_kernel_kill(kill,33,77,lambda row:events.append(row))
    assert events[0]=='actual_kill' and events[1]=={'role':'watchdog','cgroup_dev':33,'cgroup_inode':77,'kill_returned':True}
    def failed():raise OSError('fixed')
    with pytest.raises(OSError):p.observe_kernel_kill(failed,33,77,lambda row:events.append(row))
    assert len(events)==2


def test_local_outage_result_requires_unknown_permanent_gate_and_no_replay():
    p=probe();state={'invalidated':True,'create_converged':True,'first_stdin_ns':5}
    journal={'state':'stopping','closed_by':None};marker={'bytes_written':100,'calls':1}
    p.verify_boundary(state,journal,marker,marker,5)
    for changes in ({'invalidated':False},{'first_stdin_ns':6}):
        with pytest.raises(p.OutageFailure):p.verify_boundary({**state,**changes},journal,marker,marker,5)
    with pytest.raises(p.OutageFailure):p.verify_boundary(state,{'state':'closed','closed_by':'reclaim_verified'},marker,marker,5)
    with pytest.raises(p.OutageFailure):p.verify_boundary(state,journal,marker,{**marker,'calls':2},5)


def test_local_watchdog_kill_must_match_original_observer_cgroup():
    p=probe();snapshot={'cgroup_dev':33,'cgroup_inode':77}
    p.verify_watchdog_kill([{'role':'watchdog','cgroup_dev':33,'cgroup_inode':77,'kill_returned':True}],snapshot)
    for rows in ([],[{'role':'controller','cgroup_dev':33,'cgroup_inode':77,'kill_returned':True}],
                 [{'role':'watchdog','cgroup_dev':33,'cgroup_inode':78,'kill_returned':True}]):
        with pytest.raises(p.OutageFailure):p.verify_watchdog_kill(rows,snapshot)


def test_local_hook_is_scoped_and_composes_with_original_entry():
    import ast
    p=probe();source=p.hook_source('a'*64)
    assert 'engine-outage.flag' in source and '_own' in source and "_role=='watchdog'" in source
    assert 'docker.service' not in source and 'SIGKILL' not in source
    ast.parse(source+(HERE.parents[1]/'deploy/runtime_entry.py').read_text())
    with pytest.raises(p.OutageFailure):p.hook_source('bad')


def test_real_session_engine_outage_keeps_original_kernel_capability(remote):
    image=os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE');assert image,'explicit pinned receiver image required'
    spec=importlib.util.spec_from_file_location('_outage_bundle',HERE/'test_runtime_wiring.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bundle,digest=module._package_bundle();source=(HERE/'runtime_engine_outage_probe.py').read_text()
    values=dict(PACKAGE_B64=bundle,PACKAGE_SHA256=digest,OUTAGE_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        WIRING_PROBE_SOURCE=(HERE/'runtime_wiring_probe.py').read_text(),FAULT_PROBE_SOURCE=(HERE/'runtime_faults_probe.py').read_text(),
        INTERRUPTION_PROBE_SOURCE=(HERE/'runtime_interruptions_probe.py').read_text(),
        WIRE_FIXTURE_SOURCE=(HERE.parents[3]/'backend/tests/e2e/d4_text_wire_fixture.py').read_text())
    script=''.join(key+'='+repr(value)+'\n' for key,value in values.items())+source
    output=remote('sudo -n /usr/bin/python3 -I -S -B - '+shlex.quote(image)+" <<'D4_ENGINE_OUTAGE'\n"+script+'\nD4_ENGINE_OUTAGE\n',timeout=150,check=False)
    print(output);rows=[json.loads(line) for line in output.splitlines() if line.startswith('{')];assert len(rows)==1,output
    row=rows[0]
    assert row['verified'] and row['resources_cleaned'] and row['failure_code'] is None,row
    assert row['scope']=='injected_session_management_io_not_shared_daemon_stop',row
    assert row['detect_ns']<=2_000_000_000 and row['reclaim_ns']<=5_000_000_000,row
    assert row['watchdog_original_kernel_kill'] and row['observer_cgroup_empty'] and row['receiver_stopped'],row
    assert row['bystander_unchanged'] and row['api_survived'] and row['controller_stopped'] and row['no_replay'],row
    assert row['infrastructure_result']=='isolation_unknown' and row['journal_summary']['state']!='closed',row
    assert row['registration_retained'] and row['bad_initial_record_retained'] and row['outage_sha256']==values['OUTAGE_SHA256'],row
    assert 'runtime_engine_outage_verified' in output.splitlines(),output


def test_local_generated_request_wrapper_preserves_arguments_and_records_once(tmp_path):
    import ast
    p=probe();tree=ast.parse(p.hook_source('a'*64));events=[]
    function=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='_outage_request')
    class EngineError(Exception):pass
    def original(*args,**kwargs):events.append((args,kwargs));return b'real'
    namespace=dict(_root=tmp_path,_role='controller',_outage_hit=False,_original_request=original,
        _EError=EngineError,_et=p.time,request_boundary=p.request_boundary,
        _outage_record=lambda name,row:events.append((name,row)))
    exec(compile(ast.Module(body=[function],type_ignores=[]),'actual_outage_hook','exec'),namespace)
    owner=object();kwargs=dict(body=b'fixed',statuses=(204,),upgrade=False)
    assert namespace['_outage_request'](owner,'POST','/fixed',123,**kwargs)==b'real'
    assert events==[((owner,'POST','/fixed',123),kwargs)]
    (tmp_path/'engine-outage.flag').write_text('{}')
    for _ in range(2):
        with pytest.raises(EngineError,match='engine_unavailable'):namespace['_outage_request'](owner,'GET','/fixed',124)
    assert len(events)==2 and events[1][0]=='engine-outage-hits.jsonl'
    assert events[1][1]['role']=='controller' and events[1][1]['event']=='engine_unavailable'


def test_local_generated_watchdog_kill_uses_actual_held_fd(tmp_path):
    import ast
    p=probe();tree=ast.parse(p.hook_source('a'*64));events=[]
    function=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='_watchdog_kill')
    namespace=dict(_eo=os,_original_kill=lambda owner:events.append(('actual_kill',owner.fd)),
        observe_kernel_kill=p.observe_kernel_kill,_outage_record=lambda name,row:events.append((name,row)))
    exec(compile(ast.Module(body=[function],type_ignores=[]),'actual_outage_hook','exec'),namespace)
    with (tmp_path/'reference').open('w') as fd:
        owner=type('OriginalReference',(),{'fd':fd.fileno()})();fact=os.fstat(owner.fd)
        namespace['_watchdog_kill'](owner)
        assert events[0]==('actual_kill',owner.fd)
        assert events[1]==('watchdog-kernel-kill.jsonl',{'role':'watchdog','cgroup_dev':fact.st_dev,'cgroup_inode':fact.st_ino,'kill_returned':True})


def test_local_generated_event_writer_produces_private_json_lines(tmp_path):
    import ast
    p=probe();tree=ast.parse(p.hook_source('a'*64))
    function=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='_outage_record')
    namespace=dict(_root=tmp_path,_eo=os,_ej=json)
    exec(compile(ast.Module(body=[function],type_ignores=[]),'actual_outage_hook','exec'),namespace)
    row={'role':'watchdog','cgroup_dev':33,'cgroup_inode':77,'kill_returned':True}
    for _ in range(2):namespace['_outage_record']('watchdog-kernel-kill.jsonl',row)
    path=tmp_path/'watchdog-kernel-kill.jsonl'
    assert [json.loads(line) for line in path.read_text().splitlines()]==[row,row]
    assert path.stat().st_mode&0o777==0o600
    with pytest.raises(ValueError):namespace['_outage_record']('unowned.jsonl',row)


def test_local_generated_prefix_rejects_other_nonce_before_engine_import(monkeypatch,tmp_path):
    import sys
    p=probe();monkeypatch.setattr(os,'geteuid',lambda:0)
    monkeypatch.setattr(sys,'argv',['entry','watchdog','--nonce','b'*64])
    with pytest.raises(ValueError,match='outage_scope_invalid'):
        exec(compile(p.hook_source('a'*64),'actual_prefix','exec'),{'__file__':str(tmp_path/'pkg/deploy/runtime_entry.py')})
