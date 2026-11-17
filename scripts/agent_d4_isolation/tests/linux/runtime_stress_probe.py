"""Trusted no-authority stress in the actual receiver cgroup and two-unit chain.

The Docker exec adversary has uid 2001 and inherits the receiver's seccomp,
mount, PID and cgroup boundaries. It is an extra trusted-injected test process,
not a modified receiver or a production arbitrary-command interface.
"""
import json
import os
import sys
import time
import types
import selectors
import hashlib
import re


def require(value, code):
    if not value:
        raise RuntimeError(code)


def program(case):
    if case in ('combined', 'flood'):
        return 'MODE='+repr(case)+'\n'+r'''
import os,time
# First prove both init streams are writable with a small forged result. The
# host observes the controller still alive before ordering the flood.
out=os.open('/proc/1/fd/1',os.O_WRONLY);err=os.open('/proc/1/fd/2',os.O_WRONLY)
fake=b'{"status":"completed","received_fields":999,"run_id":"00000000-0000-0000-0000-000000000001"}\n'
assert os.write(out,fake)==len(fake)
assert os.write(err,b'forged-stderr\n')==14
print('streams_verified',flush=True)
while not os.path.exists('/tmp/stress-go'):time.sleep(.01)
# Each individual stream contributes less than 4096 before combined overflow.
if MODE=='combined':
 assert os.write(out,b'x'*2048)==2048
 assert os.write(err,b'y'*2048)==2048
 time.sleep(30)
else:
 while True:os.write(out,b'z'*4096)
'''
    if case == 'limits':
        return r'''
import errno,json,os,resource
from pathlib import Path
assert resource.getrlimit(resource.RLIMIT_NOFILE)==(64,64)
fds=[]
try:
 while True:fds.append(os.open('/dev/null',os.O_RDONLY))
except OSError as e:assert e.errno==errno.EMFILE
finally:
 for fd in fds:os.close(fd)
assert 40<=len(fds)<=61
paths=[]
try:
 for i in range(256):
  p='/tmp/inode-'+str(i)
  with open(p,'wb'):pass
  paths.append(p)
except OSError as e:assert e.errno==errno.ENOSPC
else:raise AssertionError('inode_limit_not_enforced')
assert 100<=len(paths)<=127
for p in paths:os.unlink(p)
written=0
try:
 with open('/tmp/bytes','wb',buffering=0) as f:
  while written<16*1024*1024:written+=f.write(b'x'*65536)
except OSError as e:assert e.errno==errno.ENOSPC
else:raise AssertionError('byte_limit_not_enforced')
assert 7*1024*1024<=written<=8*1024*1024
os.unlink('/tmp/bytes')
assert Path('/sys/fs/cgroup/pids.max').read_text().strip()=='16'
assert Path('/sys/fs/cgroup/memory.max').read_text().strip()=='134217728'
q,p=map(int,Path('/sys/fs/cgroup/cpu.max').read_text().split());assert q==p
try:os.fork()
except OSError as e:assert e.errno==errno.EPERM
else:raise AssertionError('fork_was_allowed')
try:os.setsid()
except OSError as e:assert e.errno==errno.EPERM
else:raise AssertionError('setsid_was_allowed')
print(json.dumps(dict(nofile_emfile=True,opened=len(fds),tmpfs_inodes_enospc=True,inodes=len(paths),tmpfs_bytes_enospc=True,bytes=written,fork_seccomp_denied=True,setsid_denied=True)),flush=True)
'''
    if case == 'memory':
        return r'''
import os,time
print('memory_pressure_started',flush=True)
chunks=[]
while True:
 chunks.append(bytearray(4*1024*1024))
 time.sleep(.002)
'''
    raise ValueError('case_invalid')


def capture(child, deadline_ns, *, first_line=False, limit=4096):
    """Read both child pipes in capped chunks before storing any bytes."""
    output=[bytearray(),bytearray()]
    with selectors.DefaultSelector() as poll:
        for index,stream in enumerate((child.stdout,child.stderr)):
            os.set_blocking(stream.fileno(),False)
            poll.register(stream,selectors.EVENT_READ,index)
        while poll.get_map():
            remaining=(deadline_ns-time.monotonic_ns())/1e9
            require(remaining>0,'exec_capture_deadline')
            for key,_ in poll.select(min(.1,remaining)):
                raw=os.read(key.fileobj.fileno(),512)
                if not raw:
                    poll.unregister(key.fileobj);continue
                require(sum(map(len,output))+len(raw)<=limit,'exec_output_limit')
                output[key.data].extend(raw)
                if first_line and b'\n' in output[0]:
                    require(output[0]==b'streams_verified\n' and not output[1],'exec_marker_invalid')
                    return tuple(map(bytes,output))
        child.wait(timeout=max(.001,(deadline_ns-time.monotonic_ns())/1e9))
    return tuple(map(bytes,output))


DIAGNOSTIC_HOOK=r'''
# TEST ONLY fixed infrastructure trace; no config, payload, IDs or exceptions.
import sys as _ds,os as _do,time as _dt,json as _dj
from pathlib import Path as _DP
_dr=_DP(__file__).absolute().parents[2];_ds.path.insert(0,str(_dr))
from agent_d4_isolation import linux_identity as _di,linux_engine as _de,runtime_supervisor as _du
def _trace(event,result=None):
 try:
  fd=_do.open(_dr/'stress-trace.jsonl',_do.O_WRONLY|_do.O_APPEND|_do.O_CREAT|_do.O_NOFOLLOW,0o600)
  try:
   if _do.fstat(fd).st_size<65536:
    row={'event':event,'time':_dt.monotonic_ns(),'role':_ds.argv[1],'result':result}
    _do.write(fd,(_dj.dumps(row,separators=(',',':'))+'\n').encode())
  finally:_do.close(fd)
 except Exception:pass
def _wrap(cls,name):
 old=getattr(cls,name)
 def wrapped(self,*args,**kwargs):
  _trace(name+'_start')
  try:
   result=old(self,*args,**kwargs)
   _trace(name+'_end',result if type(result) in (int,bool) or result is None else 'object')
   return result
  except BaseException:
   _trace(name+'_error');raise
 setattr(cls,name,wrapped)
for _name in ('signal','container_running','tasks_remaining','terminate'):_wrap(_di.LiveBinding,_name)
_wrap(_di._Cgroup,'kill');_wrap(_de.EngineClient,'signal')
_wrap(_de.EngineClient,'inspect');_wrap(_de.AttachedIO,'close')
from contextlib import contextmanager as _cm
_old_stop_lock=_du._stop_lock
@_cm
def _traced_lock(store,*args,**kwargs):
 _trace('stop_lock_start')
 try:
  with _old_stop_lock(store,*args,**kwargs):
   _trace('stop_lock_acquired');yield
 except BaseException:
  _trace('stop_lock_error');raise
_du._stop_lock=_traced_lock
'''


def main(image):
    global F
    require(os.geteuid() == 0 and STRESS_CASE in ('combined', 'flood', 'limits', 'memory'), 'case_invalid')
    F=types.ModuleType('_owned_stress_fault_helpers')
    F.__dict__.update(PACKAGE_B64=PACKAGE_B64,PACKAGE_SHA256=PACKAGE_SHA256,
                      WIRE_FIXTURE_SOURCE=WIRE_FIXTURE_SOURCE,WIRING_PROBE_SOURCE=WIRING_PROBE_SOURCE)
    exec(compile(FAULT_PROBE_SOURCE,'<fault-helpers>','exec'),F.__dict__)
    H=F.helpers();F.H=H;F.UNITS=H.UNITS
    receipt=dict(case=STRESS_CASE,nonce=H.NONCE,root=str(H.ROOT),units=list(H.UNITS),
                 bundle_sha256=PACKAGE_SHA256,receiver_id=None,api_create_pending=False,
                 verified=False,resources_cleaned=False,registration_retained=True,failure_code=None)
    receipt.update(stress_probe_sha256=STRESS_PROBE_SHA256,
                   program_sha256=hashlib.sha256(program(STRESS_CASE).encode()).hexdigest(),
                   fault_probe_sha256=hashlib.sha256(FAULT_PROBE_SOURCE.encode()).hexdigest())
    binding=collector=child=None
    memory_events=None
    try:
        H.unpack_package();F.install_hook('claim_watchdog_kill',receipt);H.record_receipt(receipt)
        if globals().get('STRESS_DIAGNOSTIC',False):
            entry=H.ROOT/'agent_d4_isolation/deploy/runtime_entry.py'
            raw=DIAGNOSTIC_HOOK.encode()+entry.read_bytes()
            entry.write_bytes(raw)
            receipt['diagnostic_hook_sha256']=hashlib.sha256(DIAGNOSTIC_HOOK.encode()).hexdigest()
            receipt['entry_test_sha256']=hashlib.sha256(raw).hexdigest()
        image_id,api_id,manifest=F.setup_api(image,receipt)
        sys.path.insert(0,str(H.ROOT))
        from agent_d4_isolation.linux_engine import EngineClient
        from agent_d4_isolation.linux_identity import KernelCollector
        from agent_d4_isolation.runtime_supervisor import launch_session,stop_session
        engine=EngineClient();collector=KernelCollector(engine,image_id,api_id)
        (H.ROOT/'state').mkdir(mode=0o700);(H.ROOT/'state/journal').mkdir(mode=0o700)
        launch_session(H.ROOT,H.NONCE)
        def retain_observer(value):
            nonlocal binding
            require(binding is None,'observer_already_retained')
            binding=value
        binding,phase=F.wait_fault_phase('claim_watchdog_kill',collector,api_id,receipt,binding_ready=retain_observer)
        import subprocess
        if STRESS_CASE=='memory':
            memory_events=os.open('memory.events',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=binding.cgroup.fd)
            def counters():
                return dict((k,int(v)) for k,v in (line.split() for line in os.pread(memory_events,4096,0).decode().splitlines()))
            initial=counters();receipt['memory_events_before']=initial
        child=subprocess.Popen(['/usr/bin/docker','exec','--user','2001:2001',receipt['receiver_id'],
                                'python','-I','-S','-B','-u','-c',program(STRESS_CASE)],
                               stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        started=time.monotonic_ns()
        receipt['stage']='stress_started'
        if STRESS_CASE in ('combined','flood'):
            out,err=capture(child,time.monotonic_ns()+2_000_000_000,first_line=True)
            require(out==b'streams_verified\n' and not err,'stream_write_failed')
            time.sleep(.2)
            require(F.manager_view(H.UNITS[0])['ActiveState']=='active','forged_result_trusted')
            require(H.docker('logs',api_id).stdout.decode().splitlines()==['ready','seen_0'],'forged_result_advanced_api')
            receipt['streams_verified']=True
            started=time.monotonic_ns()
            receipt['stage']='output_reclaim'
            H.docker('exec','--user','2001:2001',receipt['receiver_id'],'python','-I','-S','-B','-c',
                     "open('/tmp/stress-go','wb').close()")
            F.wait_reclaimed(binding,started)
            receipt['forged_result_did_not_complete']=True
            receipt['combined_stdout_stderr_overflow_terminated']=STRESS_CASE=='combined'
            receipt['unbounded_output_terminated']=STRESS_CASE=='flood'
        elif STRESS_CASE=='limits':
            receipt['stage']='limits_capture'
            out,err=capture(child,time.monotonic_ns()+3_000_000_000)
            require(child.returncode==0 and not err and len(out)<4096,'limit_pressure_failed')
            facts=json.loads(out);require(all(facts[k] is True for k in ('nofile_emfile','tmpfs_inodes_enospc','tmpfs_bytes_enospc','fork_seccomp_denied','setsid_denied')),'limit_pressure_unverified')
            receipt['pressure']=facts
            require(stop_session(H.ROOT,H.NONCE,engine=engine,collector=collector,binding=binding)=='isolation_terminated','pressure_reclaim_unknown')
        else:
            receipt['stage']='memory_capture'
            out,err=capture(child,time.monotonic_ns()+4_000_000_000)
            require(out==b'memory_pressure_started\n' and len(err)<4096 and child.returncode!=0,'memory_pressure_not_killed')
            after=counters();require(after['oom_kill']>initial['oom_kill'],'oom_kernel_event_missing')
            receipt['memory_events_after']=after
            require(stop_session(H.ROOT,H.NONCE,engine=engine,collector=collector,binding=binding)=='isolation_terminated','memory_reclaim_unknown')
        receipt['elapsed_ns']=time.monotonic_ns()-started
        require(binding.container_running(time.monotonic_ns()+500_000_000) is False and binding.tasks_remaining()==0,'original_cgroup_not_empty')
        require(H.assert_owned(api_id,image_id,'api')['State']['Running'],'api_stopped')
        receipt.update(receiver_stopped=True,observer_cgroup_empty=True,api_survived=True)
        until=time.monotonic()+4
        while time.monotonic()<until and F.manager_view(H.UNITS[0])['ActiveState'] not in ('inactive','failed'):time.sleep(.02)
        H.summarize_runtime(receipt)
        require(receipt['journal_summary']['closed_by']=='reclaim_verified','journal_not_closed')
        if STRESS_CASE in ('combined','flood'):
            logs=H.run(['/usr/bin/journalctl','--no-pager','-o','cat','-u',H.UNITS[0]],timeout=2).stdout
            require(b'"status":"isolation_terminated"' in logs and b'00000000-0000-0000-0000-000000000001' not in logs and b'forged-stderr' not in logs,'receiver_output_forwarded')
        receipt['verified']=True
    except Exception as error:
        known=(RuntimeError,F.FaultFailure,H.ProbeFailure)
        code=str(error) if type(error) in known else ''
        receipt['failure_code']=code if re.fullmatch('[a-z_]{1,64}',code) else 'stress_probe_unknown'
        receipt['error_type']=type(error).__name__
    finally:
        if binding is not None:
            try:
                receipt['boundary_tasks_remaining']=binding.tasks_remaining()
                receipt['boundary_engine_running']=binding.container_running(time.monotonic_ns()+250_000_000)
            except Exception:receipt['boundary_observation']='unknown'
        if child is not None:
            try:child.wait(timeout=.2)
            except Exception:
                child.kill()
                try:child.wait(timeout=.2)
                except Exception:pass
            for stream in (child.stdout,child.stderr):
                if stream is not None:stream.close()
        if memory_events is not None:os.close(memory_events)
        if H.ROOT.exists():
            H.summarize_runtime(receipt,'post_observation_');F.cleanup(receipt,binding,collector)
            trace=H.ROOT/'stress-trace.jsonl'
            if trace.exists():
                receipt['diagnostic_trace']=[json.loads(line) for line in trace.read_text().splitlines()[-512:]]
            if H.ROOT.exists():H.record_receipt(receipt)
        print(json.dumps(receipt,sort_keys=True),flush=True)
    require(receipt['verified'] and receipt['resources_cleaned'],'stress_not_verified')
    print('runtime_stress_verified:'+STRESS_CASE,flush=True)


if __name__=='__main__':
    try:main(sys.argv[1])
    except Exception:
        print('runtime_stress_failed',flush=True)
        raise SystemExit(1)
