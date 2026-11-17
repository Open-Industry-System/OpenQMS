"""Root observer for an EXISTING dedicated full app; no app replacement/hook.

Only synthetic markers are sent. No auth.json/private.env/response bodies are
read. A normal failed-login audit is legitimate business persistence, excluded
explicitly from the nonbusiness log scan. No resource creation or deletion.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import stat
import subprocess
import sys
import time

LABEL='org.openqms.d4.i9.nonce'
LIMIT=256*1024
MANIFEST_KEYS={'schema_version','nonce','api_id','api_image','pg_id','pg_image','api_recipe'}
SAFE_LINE=re.compile(r'(request|unknown_route|parse_failure|unhandled|background|startup|shutdown|unknown_event) level=(DEBUG|INFO|WARNING|ERROR|CRITICAL) logger=(uvicorn|uvicorn.error|uvicorn.access|app|asgi|other) route=(-|claim|heartbeat|deliver|ack|finish|status)')

class LoggingFailure(Exception):pass

def require(ok,code):
    if not ok:raise LoggingFailure(code)

def expected_recipe(nonce):
    root='/run/oqms-d4-i9-'+nonce
    mounts=(('code/scripts/agent_d4_isolation_fixture.py','/app/scripts/agent_d4_isolation_fixture.py',False),
        ('code/scripts/agent_d4_isolated_api.py','/app/scripts/agent_d4_isolated_api.py',False),
        ('code/app/core/agent_isolation_logging.py','/app/app/core/agent_isolation_logging.py',False),
        ('api-private/api.env','/app/.env',False),('api-private','/private',True),('pgsocket','/pgsocket',False))
    return dict(Entrypoint=['python'],Cmd=['-I','-B','/app/scripts/agent_d4_isolation_fixture.py','serve'],User='2002:2002',
        NetworkMode='bridge',PortBindings=None,PublishAllPorts=False,
        Mounts=sorted([dict(Type='bind',Source=root+'/'+source,Destination=destination,RW=rw,Propagation='rprivate') for source,destination,rw in mounts],key=lambda x:x['Destination']))

def normal_recipe(recipe):
    require(type(recipe)is dict and set(recipe)=={'Entrypoint','Cmd','User','NetworkMode','PortBindings','PublishAllPorts','Mounts'},'api_recipe_keys_invalid')
    require(recipe['PortBindings'] is None or recipe['PortBindings']=={},'api_published_ports')
    require(type(recipe['PublishAllPorts'])is bool and type(recipe['Mounts'])is list,'api_recipe_types_invalid')
    for mount in recipe['Mounts']:
        require(type(mount)is dict and set(mount)=={'Type','Source','Destination','RW','Propagation'} and type(mount['RW'])is bool and type(mount['Destination'])is str,'api_mount_shape_invalid')
    return {**recipe,'PortBindings':None,'Mounts':sorted(recipe['Mounts'],key=lambda x:x['Destination'])}

def validate_manifest(value):
    require(type(value)is dict and set(value)==MANIFEST_KEYS,'manifest_keys_invalid')
    require(type(value['schema_version'])is int and value['schema_version']==1,'manifest_version_invalid')
    require(type(value['nonce'])is str and re.fullmatch('[a-f0-9]{12}',value['nonce']),'manifest_nonce_invalid')
    for role in ('api','pg'):
        require(type(value[role+'_id'])is str and re.fullmatch('[a-f0-9]{64}',value[role+'_id']),'manifest_id_invalid')
        require(type(value[role+'_image'])is str and re.fullmatch('sha256:[a-f0-9]{64}',value[role+'_image']),'manifest_image_invalid')
    require(value['api_id']!=value['pg_id'],'manifest_same_container')
    require(normal_recipe(value['api_recipe'])==expected_recipe(value['nonce']),'api_recipe_not_fixed')
    return value

def validate_tenant(value):
    require(type(value)is dict and set(value)=={'schema_name','tenant_slug'},'tenant_projection_invalid')
    require(type(value['tenant_slug'])is str and re.fullmatch('i9-[a-f0-9]{16}',value['tenant_slug']),'tenant_slug_invalid')
    # Fixture uses token_hex(8); canonical slug_to_schema_name replaces hyphens
    # with underscores. Exact correspondence is narrower than a generic SQL ID.
    require(type(value['schema_name'])is str and len(value['schema_name'])<=63 and
        re.fullmatch('tenant_[a-z0-9_]+',value['schema_name']) and
        value['schema_name']=='tenant_'+value['tenant_slug'].replace('-','_'),'tenant_schema_invalid')
    return value

def read_manifest(path):
    require(type(path)is str and re.fullmatch('/run/oqms-d4-i9-[a-f0-9]{12}/logging-manifest.json',path),'manifest_path_invalid')
    root,name=path.rsplit('/',1)
    directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(directory)
        require(info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,'manifest_directory_invalid')
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            before=os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid==0 and stat.S_IMODE(before.st_mode)==0o600 and before.st_nlink==1 and before.st_size<=4096,'manifest_file_invalid')
            raw=os.read(fd,4097);after=os.fstat(fd)
            require(len(raw)<=4096 and all(getattr(before,key)==getattr(after,key) for key in ('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')),'manifest_changed')
            value=validate_manifest(json.loads(raw))
            require(root=='/run/oqms-d4-i9-'+value['nonce'],'manifest_root_nonce_mismatch')
            return value
        finally:os.close(fd)
    finally:os.close(directory)

def inspect_stream(raw,markers,*,require_event=True):
    require(type(raw)is bytes and len(raw)<=LIMIT,'log_stream_limit')
    require(not any(marker.encode() in raw for marker in markers),'sentinel_in_log')
    text=raw.decode('utf-8',errors='strict')
    lines=text.splitlines()
    require(all(SAFE_LINE.fullmatch(line) for line in lines),'unsafe_log_shape')
    require(not require_event or bool(lines),'silent_log_chain')
    return {'bytes':len(raw),'events':len(lines),'sha256':hashlib.sha256(raw).hexdigest()}

def verify_parser_and_warning(raw):
    lines=raw.splitlines()
    require(b'unknown_event level=WARNING logger=uvicorn route=-' in lines,'parser_warning_missing')
    require(b'unknown_event level=WARNING logger=app route=-' in lines,'application_warning_missing')

def verify_channels(stdout,stderr,nul_status):
    # A 500 status alone could come from a handled response. Require the actual
    # uvicorn exception collector's sanitised ERROR record as well.
    observed=b'unhandled level=ERROR logger=uvicorn route=-' in (stdout+b'\n'+stderr).splitlines()
    require(nul_status!=500 or observed,'exception_collector_not_observed')
    return {'exception_collector':'OBSERVED_SAFE_ERROR' if nul_status==500 else 'NOT_RUN'}

def inspect_database(rows,markers):
    require(type(rows)is list and 0<len(rows)<=256,'db_log_positive_control_missing')
    warnings=0
    for row in rows:
        require(type(row)is dict and set(row)=={'logger_name','level','message','module','traceback'},'db_log_shape')
        raw=json.dumps(row,sort_keys=True).encode()
        require(not any(marker.encode()in raw for marker in markers),'sentinel_in_db_log')
        require(row['traceback'] is None,'raw_db_traceback')
        require(row['message'] in {event+' -' for event in ('request','unknown_route','parse_failure','unhandled','background','startup','shutdown','unknown_event')},'unsafe_db_message')
        require(row['level'] in ('WARNING','ERROR','CRITICAL') and type(row['logger_name'])is str and re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.]{0,99}',row['logger_name']),'unsafe_db_metadata')
        require(row['module'] is None or (type(row['module'])is str and re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,199}',row['module'])),'unsafe_db_module')
        warnings+=row['logger_name']=='app.auth' and row['level']=='WARNING' and row['message']=='unknown_event -'
    require(warnings>0,'db_login_warning_missing')
    return {'rows':len(rows),'warning_rows':warnings,'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}

def request_vectors(marker,tenant):
    require(re.fullmatch('[A-Za-z0-9_-]{1,128}',marker),'marker_invalid')
    require(re.fullmatch('i9-[a-f0-9]{16}',tenant),'tenant_slug_invalid')
    def request(method,path,body=b'',extra=()):
        headers=[method+' '+path+' HTTP/1.1','Host: 127.0.0.1','X-Tenant-ID: '+tenant,
                 'Connection: close']+list(extra)
        if not any(value.startswith('User-Agent: ') for value in extra):headers.append('User-Agent: d4-log-probe')
        if method=='POST':headers+=['Content-Type: application/json','Content-Length: '+str(len(body))]
        return ('\r\n'.join(headers)+'\r\n\r\n').encode()+body
    login=json.dumps({'username':'d4-log-no-user-'+secrets.token_hex(12),'password':marker}).encode()
    nul=json.dumps({'username':'\x00'+marker,'password':marker}).encode()
    return dict(health=request('GET','/api/health'),path=request('GET','/d4-log-'+marker),
        query=request('GET','/d4-log-missing?secret='+marker),
        header=request('GET','/d4-log-missing',extra=('X-Sentinel: '+marker,)),
        body=request('POST','/api/auth/login',login,extra=('X-Sentinel: '+marker,'User-Agent: '+marker)),
        validation=request('POST','/api/auth/login',b'{"password":"'+marker.encode()+b'",'),
        nul_exception=request('POST','/api/auth/login',nul),
        malformed=b'GET /d4-log-missing HTTP/1.1\r\nHost: 127.0.0.1\r\n'+marker.encode()+b'\x00: invalid\r\n\r\n')

def classify_results(results):
    expected={'health':200,'path':404,'query':404,'header':404,'body':401,'validation':422,'malformed':400}
    require(set(results)==set(expected)|{'nul_exception'},'request_evidence_missing')
    require(all(type(results[key])is int and results[key]==code for key,code in expected.items()),'request_status_unexpected')
    require(type(results['nul_exception'])is int and results['nul_exception'] in (422,500),'nul_carrier_status_unexpected')
    return {'unhandled_exception':'OBSERVED_500' if results['nul_exception']==500 else 'NOT_RUN',
            'validation_exception':'OBSERVED_422','business_login_audit_expected':1}

def require_complete_exception(receipt):
    require(receipt.get('unhandled_exception')=='OBSERVED_500','mandatory_exception_not_run')

def verify_container(raw,manifest,role,*,require_running=True):
    require(type(raw)is dict and raw.get('Id')==manifest[role+'_id'] and raw.get('Image')==manifest[role+'_image'],'container_identity_mismatch')
    require(raw.get('Config',{}).get('Labels',{}).get(LABEL)==manifest['nonce'],'container_owner_mismatch')
    require(type(raw.get('State',{}).get('Running'))is bool,'container_state_unknown')
    require(not require_running or raw['State']['Running']is True,'container_not_running')
    if role=='api':
        config=raw['Config'];host=raw.get('HostConfig',{})
        actual={key:config.get(key) for key in ('Entrypoint','Cmd','User')}
        actual.update({key:host.get(key) for key in ('NetworkMode','PortBindings','PublishAllPorts')})
        actual['Mounts']=raw.get('Mounts')
        require(normal_recipe(actual)==normal_recipe(manifest['api_recipe'])==expected_recipe(manifest['nonce']),'api_recipe_mismatch')
    driver=raw.get('HostConfig',{}).get('LogConfig',{}).get('Type')
    require(driver in ('json-file','local','journald'),'observable_log_driver_required')
    return driver

def run(argv,*,input_bytes=None,timeout=5):
    # Bound reads while the child runs; capture_output followed by a length check
    # could allocate the entire unexpected output first.
    process=subprocess.Popen(argv,stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin'})
    selector=selectors.DefaultSelector(); buffers={}
    deadline=time.monotonic()+timeout
    try:
        for stream in (process.stdout,process.stderr):
            os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ);buffers[stream]=bytearray()
        if input_bytes is not None:
            require(len(input_bytes)<=32768,'command_input_limit')
            # Every command input is a small fixed program/SQL, below pipe capacity.
            os.set_blocking(process.stdin.fileno(),False)
            require(os.write(process.stdin.fileno(),input_bytes)==len(input_bytes),'command_input_incomplete')
            process.stdin.close()
        while selector.get_map():
            require(time.monotonic()<deadline,'command_deadline')
            for key,_ in selector.select(min(.05,max(0,deadline-time.monotonic()))):
                part=os.read(key.fileobj.fileno(),8192)
                if not part:selector.unregister(key.fileobj);continue
                buffers[key.fileobj].extend(part)
                require(len(buffers[key.fileobj])<=LIMIT,'command_output_limit')
        require(process.wait(timeout=max(.001,deadline-time.monotonic()))==0,'command_failed')
        return bytes(buffers[process.stdout]),bytes(buffers[process.stderr])
    finally:
        selector.close()
        if process.poll()is None:process.kill();process.wait(timeout=1)
        for stream in (process.stdin,process.stdout,process.stderr):
            if stream is not None:stream.close()

# Docker's template emits a safe projection; this process never receives Env,
# command arguments, mounts, or a raw inspect document.
INSPECT_TEMPLATE='{"Id":{{json .Id}},"Image":{{json .Image}},"Config":{"User":{{json .Config.User}},"Entrypoint":{{json .Config.Entrypoint}},"Cmd":{{json .Config.Cmd}},"Labels":{"'+LABEL+'":{{json (index .Config.Labels "'+LABEL+'")}}}},"State":{"Running":{{json .State.Running}}},"Mounts":[{{range $i,$m := .Mounts}}{{if $i}},{{end}}{"Type":{{json $m.Type}},"Source":{{json $m.Source}},"Destination":{{json $m.Destination}},"RW":{{json $m.RW}},"Propagation":{{json $m.Propagation}}}{{end}}],"HostConfig":{"NetworkMode":{{json .HostConfig.NetworkMode}},"PortBindings":{{json .HostConfig.PortBindings}},"PublishAllPorts":{{json .HostConfig.PublishAllPorts}},"LogConfig":{"Type":{{json .HostConfig.LogConfig.Type}}}}}'

def inspect_current(manifest,role,timeout=5):
    out,err=run(['/usr/bin/docker','inspect','--format',INSPECT_TEMPLATE,manifest[role+'_id']],timeout=timeout)
    require(not err,'inspect_observer_stderr')
    return json.loads(out)

def api_program(manifest,program,timeout=5):
    stdout,stderr=run(['/usr/bin/docker','exec','-i','--user','2002:2002',manifest['api_id'],
                       'python','-I','-S','-B','-'],input_bytes=program.encode(),timeout=timeout)
    require(not stderr,'observer_stderr_unexpected')
    return json.loads(stdout)

class APILifecycle:
    def __init__(self,manifest,initial,receipt):
        self.manifest,self.receipt=manifest,receipt
        self.original_running=initial['State']['Running']
        self.restore_needed=False
        receipt.update(api_original_running=self.original_running,api_started_by_probe=False,api_restored_stopped=False)

    def ensure_running(self):
        if self.original_running:return
        # Mark before the RPC: a timeout can lose an accepted start response.
        until=time.monotonic()+10
        self.restore_needed=True
        run(['/usr/bin/docker','start',self.manifest['api_id']],timeout=min(3,max(.001,until-time.monotonic())))
        self.receipt['api_started_by_probe']=True
        require(time.monotonic()<until,'api_readiness_deadline')
        while time.monotonic()<until:
            raw=inspect_current(self.manifest,'api',min(.5,max(.001,until-time.monotonic())));verify_container(raw,self.manifest,'api',require_running=False)
            if raw['State']['Running']:
                try:
                    result=api_program(self.manifest,"import socket\nwith socket.create_connection(('127.0.0.1',18777),timeout=.2):pass\nprint('true')",timeout=min(.5,max(.001,until-time.monotonic())))
                    if result is True:
                        require(time.monotonic()<until,'api_readiness_deadline')
                        return
                except LoggingFailure:pass
            time.sleep(min(.05,max(0,until-time.monotonic())))
        raise LoggingFailure('api_readiness_deadline')

    def restore(self):
        if not self.restore_needed:return
        raw=inspect_current(self.manifest,'api');verify_container(raw,self.manifest,'api',require_running=False)
        if raw['State']['Running']:
            run(['/usr/bin/docker','stop','--time','2',self.manifest['api_id']],timeout=5)
        raw=inspect_current(self.manifest,'api');verify_container(raw,self.manifest,'api',require_running=False)
        require(raw['State']['Running']is False,'api_restore_not_stopped')
        self.receipt['api_restored_stopped']=True

PROJECTION=r'''
import hashlib,json,os,stat
from pathlib import Path
result={}
for name in ('state','witness'):
    fd=os.open('/private/d4/'+name+'.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and info.st_uid==2002 and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and info.st_size<=262144
        raw=os.read(fd,262145);assert len(raw)<=262144
        value=json.loads(raw)
        result[name]=({key:value[key] for key in ('schema_name','tenant_slug')} if name=='state' else
                      {key:value[key] for key in ('kind','generation')})
    finally:os.close(fd)
for name,path in (('fixture','/app/scripts/agent_d4_isolation_fixture.py'),('policy','/app/app/core/agent_isolation_logging.py'),('entry','/app/scripts/agent_d4_isolated_api.py')):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        raw=os.read(fd,262145);assert len(raw)<=262144
        result[name+'_sha256']=hashlib.sha256(raw).hexdigest()
    finally:os.close(fd)
print(json.dumps(result,sort_keys=True))
'''

def send_requests(manifest,vectors):
    encoded={key:base64.b64encode(value).decode() for key,value in vectors.items()}
    program="""import base64,json,socket\nvectors="""+repr(encoded)+"""\nresult={}
for name,encoded in vectors.items():
    with socket.create_connection(('127.0.0.1',18777),timeout=2) as channel:
        channel.settimeout(2);channel.sendall(base64.b64decode(encoded));raw=bytearray()
        while b'\\r\\n' not in raw:
            part=channel.recv(1)
            if not part:break
            raw.extend(part)
            assert len(raw)<=4096
        line=bytes(raw).split(b'\\r\\n',1)[0].split(b' ')
        assert len(line)>=2 and line[0] in (b'HTTP/1.1',b'HTTP/1.0')
        result[name]=int(line[1])
print(json.dumps(result,sort_keys=True))
"""
    return api_program(manifest,program,timeout=22)

def psql(manifest,sql):
    out,err=run(['/usr/bin/docker','exec','-i','--user','postgres',manifest['pg_id'],
        'psql','-X','-q','-t','-A','-v','ON_ERROR_STOP=1','-U','isolation','-d','isolation_synthetic'],
        input_bytes=('BEGIN READ ONLY; SET LOCAL statement_timeout=1000; '+sql+'; COMMIT;\n').encode(),timeout=3)
    require(not err,'db_observer_stderr')
    return out.strip()

def main(path):
    receipt={'verified':False,'failure_code':None,'unhandled_exception':'NOT_RUN','full_app_witness_verified':False}
    lifecycle=None
    try:
        require(os.geteuid()==0,'root_required')
        manifest=read_manifest(path)
        drivers={}
        for role in ('api','pg'):
            raw=inspect_current(manifest,role)
            drivers[role]=verify_container(raw,manifest,role,require_running=role!='api')
            if role=='api':lifecycle=APILifecycle(manifest,raw,receipt)
        lifecycle.ensure_running()
        projection=api_program(manifest,PROJECTION)
        tenant=validate_tenant(projection['state'])
        require(projection['witness']['kind']=='full_app_request_sql_witness.v1','full_app_witness_missing')
        require(projection['fixture_sha256']==FIXTURE_SHA256 and projection['policy_sha256']==POLICY_SHA256 and projection['entry_sha256']==ENTRY_SHA256,'fixture_source_mismatch')
        receipt.update(full_app_witness_verified=True,fixture_sha256=projection['fixture_sha256'],
            witness_generation_sha256=hashlib.sha256(projection['witness']['generation'].encode()).hexdigest())
        marker='D4LOG_'+secrets.token_hex(24)
        started=datetime.now(timezone.utc).isoformat(timespec='microseconds')
        db_start=psql(manifest,'SELECT clock_timestamp()').decode('ascii')
        require(re.fullmatch(r'[0-9-]{10} [0-9:.]+\+00',db_start),'db_clock_invalid')
        results=send_requests(manifest,request_vectors(marker,tenant['tenant_slug']))
        receipt.update(classify_results(results));receipt['request_statuses']=results
        schema=tenant['schema_name']
        sql='SELECT coalesce(json_agg(t),\'[]\'::json) FROM (SELECT logger_name,level,message,module,traceback FROM "'+schema+'".system_logs WHERE occurred_at >= \''+db_start+'\'::timestamptz ORDER BY occurred_at LIMIT 257) t'
        until=time.monotonic()+2
        while True:
            rows=json.loads(psql(manifest,sql))
            if any(row.get('logger_name')=='app.auth' for row in rows) or time.monotonic()>=until:break
            time.sleep(.05)
        receipt['database']=inspect_database(rows,[marker])
        stdout,stderr=run(['/usr/bin/docker','logs','--since',started,manifest['api_id']])
        verify_parser_and_warning(stdout+b'\n'+stderr)
        receipt.update(verify_channels(stdout,stderr,results['nul_exception']))
        receipt['docker_stdout']=inspect_stream(stdout,[marker],require_event=False)
        receipt['docker_stderr']=inspect_stream(stderr,[marker],require_event=False)
        require(receipt['docker_stdout']['events']+receipt['docker_stderr']['events']>=len(results),'silent_access_chain')
        receipt['journald']={'status':'NOT_CONFIGURED','driver':drivers['api']}
        if drivers['api']=='journald':
            out,_=run(['/usr/bin/journalctl','--no-pager','--since',started,'-o','json','CONTAINER_ID_FULL='+manifest['api_id']],timeout=3)
            entries=[json.loads(line) for line in out.splitlines()]
            require(bool(entries) and all(entry.get('CONTAINER_ID_FULL')==manifest['api_id'] for entry in entries),'journal_scope_missing')
            raw=('\n'.join(entry['MESSAGE'] for entry in entries)+'\n').encode()
            receipt['journald']={'status':'OBSERVED',**inspect_stream(raw,[marker])}
        after=api_program(manifest,PROJECTION)
        require(after==projection,'api_generation_or_fixture_changed')
        verify_container(inspect_current(manifest,'api'),manifest,'api')
        receipt['nonbusiness_scan_verified']=True
        require_complete_exception(receipt)
        receipt.update(verified=True,api_survived=True,resources_created=0,
            marker_sha256=hashlib.sha256(marker.encode()).hexdigest(),
            unhandled_database_context='NOT_RUN_no_trusted_tenant_binding_at_uvicorn_collector',
            business_audit_scope='normal_failed_login_audit_is_expected_not_a_nonbusiness_log')
    except Exception as error:
        receipt['failure_code']=str(error) if type(error)is LoggingFailure else 'full_app_logging_probe_failed'
    finally:
        if lifecycle is not None:
            try:lifecycle.restore()
            except Exception:
                receipt['restore_failure_code']='api_restore_unknown';receipt['verified']=False
                receipt['failure_code']=receipt['failure_code'] or 'api_restore_unknown'
    print(json.dumps(receipt,sort_keys=True),flush=True)
    require(receipt['verified'] and receipt['failure_code']is None,'logging_gate_failed')
    print('full_app_logging_verified',flush=True)

if __name__=='__main__':
    try:
        require(len(sys.argv)==2,'manifest_path_required');main(sys.argv[1])
    except Exception as error:
        print('full_app_logging_failed:'+(str(error) if type(error)is LoggingFailure else 'probe_failed'),flush=True)
        raise SystemExit(1)
