"""Opt-in, existing full app and DB; no substitute ASGI app or secret input."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import pytest

HERE = Path(__file__).resolve().parent


def probe():
    spec = importlib.util.spec_from_file_location('_full_app_logging', HERE / 'full_app_logging_probe.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def recipe():
    root='/run/oqms-d4-i9-'+'a'*12
    mounts=[('code/scripts/agent_d4_isolation_fixture.py','/app/scripts/agent_d4_isolation_fixture.py',False),
        ('code/scripts/agent_d4_isolated_api.py','/app/scripts/agent_d4_isolated_api.py',False),
        ('code/app/core/agent_isolation_logging.py','/app/app/core/agent_isolation_logging.py',False),
        ('api-private/api.env','/app/.env',False),('api-private','/private',True),('pgsocket','/pgsocket',False)]
    return dict(Entrypoint=['python'],Cmd=['-I','-B','/app/scripts/agent_d4_isolation_fixture.py','serve'],User='2002:2002',
        NetworkMode='bridge',PortBindings=None,PublishAllPorts=False,
        Mounts=[dict(Type='bind',Source=root+'/'+source,Destination=destination,RW=rw,Propagation='rprivate') for source,destination,rw in mounts])


def manifest():
    return dict(schema_version=1, nonce='a'*12, api_id='b'*64, api_image='sha256:'+'c'*64,
                pg_id='d'*64, pg_image='sha256:'+'e'*64,api_recipe=recipe())


def test_local_manifest_is_closed_and_exact():
    p = probe(); p.validate_manifest(manifest())
    for changes in ({'api_id':'short'}, {'nonce':'a;id'}, {'api_image':'latest'}, {'extra':1}, {'schema_version':True}):
        with pytest.raises(p.LoggingFailure): p.validate_manifest({**manifest(), **changes})


def test_local_schema_projection_rejects_arbitrary_identifiers():
    p=probe();slug='i9-0123456789abcdef'
    spec=importlib.util.spec_from_file_location('_canonical_tenant_utils',HERE.parents[3]/'backend/app/core/tenant_utils.py')
    canonical=importlib.util.module_from_spec(spec);spec.loader.exec_module(canonical)
    schema=canonical.slug_to_schema_name(slug)
    assert schema=='tenant_i9_0123456789abcdef'
    assert p.validate_tenant({'schema_name':schema,'tenant_slug':slug})
    for invalid_schema in ('public','tenant_a;DROP','tenant_abc.xyz','tenant_z123',
                           'tenant_i9_0123456789abcdee','tenant_i9_0123456789abcdef"',schema+'_'*64):
        with pytest.raises(p.LoggingFailure):p.validate_tenant({'schema_name':invalid_schema,'tenant_slug':slug})
    for invalid_slug in ('i9-0123456789abcde','i9-0123456789abcdefg',slug+'"',slug+';DROP'):
        with pytest.raises(p.LoggingFailure):p.validate_tenant({'schema_name':schema,'tenant_slug':invalid_slug})


def test_local_log_scan_requires_fixed_events_and_no_sentinel():
    p = probe(); safe = b'unknown_event level=WARNING logger=app route=-\n'
    assert p.inspect_stream(safe, ['sentinel'])['events'] == 1
    with pytest.raises(p.LoggingFailure,match='sentinel_in_log'):p.inspect_stream(safe,['WARNING'])
    for value in (b'', safe+b'sentinel\n', safe+b'Traceback (most recent call last):\n', b'arbitrary request target\n'):
        with pytest.raises(p.LoggingFailure): p.inspect_stream(value, ['sentinel'], require_event=True)
    assert p.inspect_stream(b'', ['sentinel'], require_event=False)['events'] == 0


def test_local_database_positive_control_is_not_empty_or_raw_exception():
    p = probe(); row = dict(logger_name='app.auth',level='WARNING',message='unknown_event -',module='auth',traceback=None)
    assert p.inspect_database([row], ['sentinel'])['warning_rows'] == 1
    with pytest.raises(p.LoggingFailure,match='sentinel_in_db_log'):p.inspect_database([row],['unknown_event'])
    for rows in ([], [{**row,'message':'sentinel'}], [{**row,'traceback':'raw error'}]):
        with pytest.raises(p.LoggingFailure): p.inspect_database(rows, ['sentinel'])


def test_local_request_vectors_are_real_and_nul_is_json_decoded():
    p = probe(); vectors=p.request_vectors('SENTINEL','i9-0123456789abcdef')
    assert set(vectors)=={'health','path','query','header','body','validation','nul_exception','malformed'}
    assert b'SENTINEL' in vectors['path'] and b'SENTINEL' in vectors['query']
    assert b'X-Sentinel: SENTINEL' in vectors['header']
    assert b'User-Agent: SENTINEL' in vectors['body']
    for name in ('body','nul_exception'):
        raw=vectors[name].split(b'\r\n\r\n',1)[1]; decoded=json.loads(raw)
        assert 'SENTINEL' in str(decoded)
    assert '\x00' in json.loads(vectors['nul_exception'].split(b'\r\n\r\n',1)[1])['username']


def test_local_statuses_do_not_fabricate_exception_coverage():
    p = probe(); results=dict(health=200,path=404,query=404,header=404,body=401,validation=422,nul_exception=422,malformed=400)
    assert p.classify_results(results)['unhandled_exception']=='NOT_RUN'
    results['nul_exception']=500
    assert p.classify_results(results)['unhandled_exception']=='OBSERVED_500'
    results['path']=400
    with pytest.raises(p.LoggingFailure): p.classify_results(results)


def test_local_collector_rejects_unrelated_container_and_uses_no_raw_environment():
    p = probe(); m=manifest()
    raw={'Id':m['api_id'],'Image':m['api_image'],'Config':{'Labels':{p.LABEL:m['nonce']},'User':'2002:2002','Entrypoint':recipe()['Entrypoint'],'Cmd':recipe()['Cmd']},'Mounts':recipe()['Mounts'],'State':{'Running':True},'HostConfig':{'LogConfig':{'Type':'json-file'},'NetworkMode':'bridge','PortBindings':None,'PublishAllPorts':False}}
    assert p.verify_container(raw,m,'api')=='json-file'
    raw['Config']['Labels'][p.LABEL]='f'*12
    with pytest.raises(p.LoggingFailure):p.verify_container(raw,m,'api')


def test_existing_full_application_log_chain(remote):
    path=os.environ.get('OPENQMS_D4_LOGGING_MANIFEST')
    assert path, 'explicit root-private full-app manifest required'
    source=(HERE/'full_app_logging_probe.py').read_text()
    fixture=(HERE.parents[3]/'backend/scripts/agent_d4_isolation_fixture.py').read_bytes()
    policy=(HERE.parents[3]/'backend/app/core/agent_isolation_logging.py').read_bytes()
    entry=(HERE.parents[3]/'backend/scripts/agent_d4_isolated_api.py').read_bytes()
    source='FIXTURE_SHA256='+repr(hashlib.sha256(fixture).hexdigest())+'\nPOLICY_SHA256='+repr(hashlib.sha256(policy).hexdigest())+'\nENTRY_SHA256='+repr(hashlib.sha256(entry).hexdigest())+'\n'+source
    output=remote('sudo -n /usr/bin/python3 -I -S -B - '+shlex.quote(path)+" <<'D4_FULL_LOG'\n"+source+'\nD4_FULL_LOG\n',timeout=90,check=False)
    print(output)
    rows=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert len(rows)==1, output
    row=rows[0]
    assert row['failure_code'] is None and row['verified'] is True, row
    assert row['full_app_witness_verified'] and row['database']['warning_rows']>0, row
    assert row['unhandled_exception']=='OBSERVED_500' and row['exception_collector']=='OBSERVED_SAFE_ERROR', row
    assert 'full_app_logging_verified' in output.splitlines(), output


def test_local_bounded_command_handles_output_and_deadline():
    import sys
    p=probe()
    assert p.run([sys.executable,'-I','-S','-c','print("safe")'])[0]==b'safe\n'
    for program,timeout in (("import os;os.write(1,b'x'*300000)",2),("import time;time.sleep(2)",.03)):
        with pytest.raises(p.LoggingFailure):p.run([sys.executable,'-I','-S','-c',program],timeout=timeout)

def test_local_manifest_reader_requires_original_root_private_directory():
    p=probe()
    with pytest.raises(p.LoggingFailure):p.read_manifest('/tmp/untrusted.json')


def test_local_500_needs_real_exception_collector_event_not_just_access():
    p=probe();safe=b'unknown_event level=INFO logger=uvicorn.access route=-\n'*8
    with pytest.raises(p.LoggingFailure):p.verify_channels(safe,b'',500)
    evidence=p.verify_channels(safe,b'unhandled level=ERROR logger=uvicorn route=-\n',500)
    assert evidence['exception_collector']=='OBSERVED_SAFE_ERROR'
    assert p.verify_channels(safe,b'',422)['exception_collector']=='NOT_RUN'


def test_local_parser_and_auth_warnings_cannot_be_silent():
    p=probe();safe=b'unknown_event level=INFO logger=uvicorn.access route=-\n'*8
    for extra in (b'',b'unknown_event level=WARNING logger=uvicorn route=-\n',b'unknown_event level=WARNING logger=app route=-\n'):
        with pytest.raises(p.LoggingFailure):p.verify_parser_and_warning(safe+extra)
    p.verify_parser_and_warning(safe+b'unknown_event level=WARNING logger=uvicorn route=-\nunknown_event level=WARNING logger=app route=-\n')


def test_local_inspect_observer_requests_only_safe_projection(monkeypatch):
    p=probe();calls=[]
    def run(argv,**kwargs):
        calls.append(argv);return b'{"Id":"safe"}',b''
    monkeypatch.setattr(p,'run',run)
    assert p.inspect_current(manifest(),'api')=={'Id':'safe'}
    assert calls[0][:3]==['/usr/bin/docker','inspect','--format']
    assert '.Config.Env' not in calls[0][3] and '.Config.Cmd' in calls[0][3]
    assert '.Config.Labels' in calls[0][3] and calls[0][-1]==manifest()['api_id']


def test_local_sender_uses_fixed_loopback_and_real_http_status(monkeypatch):
    import contextlib
    import io
    import socket
    p=probe();destinations=[]
    class Channel:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def settimeout(self,value):assert value==2
        def sendall(self,raw):self.raw=raw
        def recv(self,size):
            assert size==1
            if not hasattr(self,'reply'):self.reply=iter(b'HTTP/1.1 404 Not Found\r\n')
            return bytes([next(self.reply)])
    def connect(destination,timeout):
        destinations.append(destination);assert timeout==2;return Channel()
    monkeypatch.setattr(socket,'create_connection',connect)
    def api_program(manifest,program,timeout):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):exec(compile(program,'actual_sender','exec'),{})
        return json.loads(output.getvalue())
    monkeypatch.setattr(p,'api_program',api_program)
    assert p.send_requests(manifest(),{'path':b'GET /missing HTTP/1.1\r\n\r\n'})=={'path':404}
    assert destinations==[('127.0.0.1',18777)]


def test_local_not_run_exception_cannot_close_full_logging_gate():
    p=probe()
    with pytest.raises(p.LoggingFailure,match='mandatory_exception_not_run'):
        p.require_complete_exception({'unhandled_exception':'NOT_RUN'})
    p.require_complete_exception({'unhandled_exception':'OBSERVED_500'})


def test_local_stopped_api_lifecycle_restores_even_start_rpc_fails(monkeypatch):
    p=probe();m=manifest();events=[]
    raw={'State':{'Running':False}}
    monkeypatch.setattr(p,'verify_container',lambda *args,**kwargs:'json-file')
    current=False
    def inspect(*args):return {'State':{'Running':current}}
    monkeypatch.setattr(p,'inspect_current',inspect)
    def run(argv,**kwargs):
        nonlocal current
        events.append(argv[1]);current=argv[1]=='start'
        if argv[1]=='start':raise p.LoggingFailure('command_deadline')
        return b'',b''
    monkeypatch.setattr(p,'run',run)
    receipt={};lease=p.APILifecycle(m,raw,receipt)
    with pytest.raises(p.LoggingFailure):lease.ensure_running()
    lease.restore()
    assert events==['start','stop'] and receipt['api_restored_stopped'] is True


def test_local_running_api_is_never_restarted_or_stopped(monkeypatch):
    p=probe();events=[];receipt={}
    def forbidden(*args,**kwargs):raise AssertionError('running_api_restarted_or_stopped')
    monkeypatch.setattr(p,'run',forbidden)
    lease=p.APILifecycle(manifest(),{'State':{'Running':True}},receipt)
    lease.ensure_running();lease.restore()
    assert events==[] and receipt['api_original_running'] is True and receipt['api_restored_stopped'] is False


def test_local_api_recipe_refuses_command_mount_or_port_widening():
    p=probe()
    for field,value in (('Cmd',['bootstrap']),('PublishAllPorts',True),('PortBindings',{'18777/tcp':[{'HostPort':'18777'}]}),('Mounts',[])):
        m=manifest();m['api_recipe']={**m['api_recipe'],field:value}
        with pytest.raises(p.LoggingFailure):p.validate_manifest(m)


def test_local_restore_refuses_replaced_owner_before_stop(monkeypatch):
    p=probe();calls=[]
    lease=p.APILifecycle(manifest(),{'State':{'Running':False}},{})
    lease.restore_needed=True
    monkeypatch.setattr(p,'inspect_current',lambda *args:{'State':{'Running':True}})
    def reject(*args,**kwargs):raise p.LoggingFailure('container_owner_mismatch')
    monkeypatch.setattr(p,'verify_container',reject)
    monkeypatch.setattr(p,'run',lambda *args,**kwargs:calls.append(args))
    with pytest.raises(p.LoggingFailure,match='container_owner_mismatch'):lease.restore()
    assert calls==[]


def test_local_actual_policy_coarse_uvicorn_parser_and_exception_classes():
    import logging
    p=probe()
    location=HERE.parents[3]/'backend/app/core/agent_isolation_logging.py'
    spec=importlib.util.spec_from_file_location('_policy_without_install',location)
    policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
    def formatted(logger,level,exception=None):
        exc=(RuntimeError,RuntimeError('SYNTHETIC_MARKER'),None) if exception else None
        record=logging.LogRecord(logger,level,'fixed.py',1,'SYNTHETIC_MARKER',(),exc)
        policy.PolicyFilter().filter(record)
        return policy.SafeFormatter().format(record).encode()+b'\n'
    parser=formatted('uvicorn.error',logging.WARNING)
    app_warning=formatted('app.auth',logging.WARNING)
    error=formatted('uvicorn.error',logging.ERROR,True)
    assert parser==b'unknown_event level=WARNING logger=uvicorn route=-\n'
    assert error==b'unhandled level=ERROR logger=uvicorn route=-\n'
    p.verify_parser_and_warning(parser+app_warning)
    assert p.verify_channels(b'',error,500)['exception_collector']=='OBSERVED_SAFE_ERROR'
    with pytest.raises(p.LoggingFailure):p.verify_channels(b'',formatted('uvicorn.error',logging.ERROR),500)


def test_local_start_rpc_and_readiness_share_one_original_deadline(monkeypatch):
    from types import SimpleNamespace
    p=probe();clock=[0.0]
    monkeypatch.setattr(p,'time',SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda seconds:None))
    def run(argv,**kwargs):clock[0]+=9.5;return b'',b''
    monkeypatch.setattr(p,'run',run)
    monkeypatch.setattr(p,'inspect_current',lambda *args:{'State':{'Running':True}})
    monkeypatch.setattr(p,'verify_container',lambda *args,**kwargs:'json-file')
    def ready(*args,**kwargs):clock[0]+=.6;return True
    monkeypatch.setattr(p,'api_program',ready)
    lease=p.APILifecycle(manifest(),{'State':{'Running':False}},{})
    with pytest.raises(p.LoggingFailure,match='api_readiness_deadline'):lease.ensure_running()
    assert clock[0]==10.1


def test_local_api_only_cold_start_between_five_and_ten_seconds_is_allowed(monkeypatch):
    from types import SimpleNamespace
    p=probe();clock=[0.0]
    monkeypatch.setattr(p,'time',SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda seconds:clock.__setitem__(0,clock[0]+seconds)))
    def start(argv,**kwargs):clock[0]+=2;return b'',b''
    monkeypatch.setattr(p,'run',start)
    monkeypatch.setattr(p,'inspect_current',lambda *args:{'State':{'Running':True}})
    monkeypatch.setattr(p,'verify_container',lambda *args,**kwargs:'json-file')
    def ready(*args,**kwargs):
        clock[0]+=.2
        if clock[0]<7:raise p.LoggingFailure('command_failed')
        return True
    monkeypatch.setattr(p,'api_program',ready)
    lease=p.APILifecycle(manifest(),{'State':{'Running':False}},{})
    try:lease.ensure_running()
    except p.LoggingFailure as error:pytest.fail('API startup inside ten seconds rejected: '+str(error))
    assert 5<clock[0]<10
