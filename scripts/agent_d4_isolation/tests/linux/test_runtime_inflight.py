"""A real controller dies after real create acceptance; list hiding is explicit."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import pytest
HERE=Path(__file__).resolve().parent

def probe():
    spec=importlib.util.spec_from_file_location('_inflight_local',HERE/'runtime_inflight_probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_local_create_marker_is_after_real_return_and_never_returns_to_controller():
    p=probe();events=[]
    def original(*args):events.append('real_create');return 'b'*64
    def publish(value):events.append(value)
    def pause():events.append('paused');raise InterruptedError('fixed')
    with pytest.raises(InterruptedError):p.accepted_boundary(original,'a'*64,'image','api',10,publish,pause)
    assert events[0]=='real_create' and events[-1]=='paused'
    assert events[1]['id']=='b'*64 and events[1]['nonce']=='a'*64 and events[1]['accepted_ns']>0
    assert set(events[1])=={'id','nonce','accepted_ns'}


def test_local_visibility_calls_real_observer_and_only_hides_own_nonce():
    p=probe();calls=[];rows=[]
    def real(nonce,deadline):calls.append(nonce);return ('b'*64,)
    assert p.visibility_boundary(real,'a'*64,'a'*64,10,True,'maintain',rows.append)==()
    assert p.visibility_boundary(real,'a'*64,'a'*64,10,False,'stop',rows.append)==('b'*64,)
    assert calls==['a'*64]*2 and [row['actual_count'] for row in rows]==[1,1]
    assert [row['returned_count'] for row in rows]==[0,1]
    with pytest.raises(ValueError):p.visibility_boundary(real,'c'*64,'a'*64,10,True,'stop',rows.append)
    assert len(calls)==2


def test_local_unknown_gate_cannot_be_closed_or_secret_started():
    p=probe();journal={'state':'unresolved'};state={'invalidated':True,'create_converged':False,'first_stdin_ns':None,'deadline_ns':123}
    p.verify_unknown(journal,state,123)
    for changes in ({'invalidated':False},{'create_converged':True},{'first_stdin_ns':1},{'deadline_ns':124}):
        with pytest.raises(p.InflightFailure):p.verify_unknown(journal,{**state,**changes},123)
    with pytest.raises(p.InflightFailure):p.verify_unknown({'state':'closed'},state,123)


def test_local_candidate_registered_before_persistence_and_inspection():
    p=probe();items=[]
    def failed():raise OSError('fixed')
    with pytest.raises(OSError):p.register_candidate(items,'b'*64,'a'*64,failed)
    assert items==[{'id':'b'*64,'nonce':'a'*64}]


def test_local_created_cleanup_verifies_full_recipe_before_remove():
    p=probe();events=[];item={'id':'b'*64,'nonce':'a'*64}
    class Engine:
        def inspect(self,*args):return {'Id':item['id'],'Image':'image','Config':{'Labels':{p.LABEL:item['nonce']}},'State':{'Running':False,'Pid':0,'Status':'created','StartedAt':'0001-01-01T00:00:00Z'}}
        def remove(self,*args):events.append('remove')
    class Collector:
        def verify_created(self,*args):events.append('recipe');return False
    with pytest.raises(p.InflightFailure):p.cleanup_created(item,Engine(),Collector(),'image',lambda cid:events.append('absent'))
    assert events==['recipe']


def test_local_hook_scopes_create_to_controller_and_own_nonce():
    p=probe();source=p.hook_source('a'*64)
    assert "_role=='controller'" in source and '_nonce==_own' in source
    assert 'accepted-marker.json' in source and 'visibility-hidden' in source
    assert 'begin_delivery' not in source and 'create_converged' not in source
    with pytest.raises(p.InflightFailure):p.hook_source('invalid')


def test_real_controller_crash_with_inflight_accepted_create(remote):
    image=os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE');assert image,'explicit pinned receiver image required'
    spec=importlib.util.spec_from_file_location('_inflight_bundle',HERE/'test_runtime_wiring.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bundle,digest=module._package_bundle();source=(HERE/'runtime_inflight_probe.py').read_text()
    values=dict(PACKAGE_B64=bundle,PACKAGE_SHA256=digest,INFLIGHT_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        WIRING_PROBE_SOURCE=(HERE/'runtime_wiring_probe.py').read_text(),FAULT_PROBE_SOURCE=(HERE/'runtime_faults_probe.py').read_text(),
        WIRE_FIXTURE_SOURCE=(HERE.parents[3]/'backend/tests/e2e/d4_text_wire_fixture.py').read_text())
    script=''.join(key+'='+repr(value)+'\n' for key,value in values.items())+source
    output=remote('sudo -n /usr/bin/python3 -I -S -B - '+shlex.quote(image)+" <<'D4_INFLIGHT'\n"+script+'\nD4_INFLIGHT\n',timeout=150,check=False)
    print(output);rows=[json.loads(line) for line in output.splitlines() if line.startswith('{')];assert len(rows)==1,output
    row=rows[0]
    assert row['verified'] and row['failure_code'] is None and row['resources_cleaned'],row
    assert row['hidden_empty_rounds']>=3 and row['controller_killed_after_acceptance'],row
    assert row['late_created_removed'] and row['bystander_unchanged'],row
    assert row['first_stdin_ns'] is None and row['secret_bytes_written']==0 and row['api_survived'],row
    assert row['registration_retained'] and row['bad_initial_record_retained'],row
    assert row['journal_summary']['state']!='closed' and row['create_converged'] is False,row
    assert row['inflight_sha256']==values['INFLIGHT_SHA256'],row
    assert 'runtime_inflight_verified' in output.splitlines(),output


def test_local_bound_journal_still_needs_invalidated_registration_gate():
    p=probe();p.verify_combined_gate(False,True,True)
    with pytest.raises(p.InflightFailure):p.verify_combined_gate(False,True,False)
    with pytest.raises(p.InflightFailure):p.verify_combined_gate(True,False,True)


def test_local_accepted_marker_is_private_complete_and_no_clobber(tmp_path):
    p=probe();value={'id':'b'*64,'nonce':'a'*64,'accepted_ns':1}
    p.publish_marker(tmp_path,value)
    path=tmp_path/'accepted-marker.json'
    assert json.loads(path.read_text())==value and path.stat().st_mode&0o777==0o600
    with pytest.raises(FileExistsError):p.publish_marker(tmp_path,{**value,'accepted_ns':2})
    assert json.loads(path.read_text())==value


def test_local_generated_controller_wrapper_calls_real_create_before_pause():
    import ast
    p=probe();tree=ast.parse(p.hook_source('a'*64));events=[]
    function=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='_inflight_create')
    def real(*args):events.append(args);return 'b'*64
    def pause():raise InterruptedError('fixed')
    namespace=dict(_role='controller',_own='a'*64,_original_create=real,accepted_boundary=p.accepted_boundary,
                   _publish_accepted=lambda value:events.append(value),_pause_accepted=pause)
    exec(compile(ast.Module(body=[function],type_ignores=[]),'actual_generated_hook','exec'),namespace)
    owner=object()
    with pytest.raises(InterruptedError):namespace['_inflight_create'](owner,'a'*64,'image','api',123)
    assert events[0]==(owner,'a'*64,'image','api',123) and events[1]['id']=='b'*64
    namespace['_role']='watchdog'
    try:namespace['_inflight_create'](owner,'a'*64,'image','api',123)
    except ValueError:pass
    except InterruptedError:pytest.fail('watchdog role reached real create')
    else:pytest.fail('watchdog role returned from controller-only create')
    assert len(events)==2


def test_local_generated_visibility_is_actual_json_lines(tmp_path):
    import ast
    p=probe();tree=ast.parse(p.hook_source('a'*64))
    function=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='_record_visibility')
    namespace=dict(_io=os,_ij=json,_root=tmp_path)
    exec(compile(ast.Module(body=[function],type_ignores=[]),'actual_generated_hook','exec'),namespace)
    row={'role':'maintain','actual_count':1,'returned_count':0}
    namespace['_record_visibility'](row);namespace['_record_visibility'](row)
    assert [json.loads(line) for line in (tmp_path/'visibility.jsonl').read_text().splitlines()]==[row,row]
    compile(p.hook_source('a'*64)+(HERE.parents[1]/'deploy/runtime_entry.py').read_text(),'composed_entry','exec')
