"""Fixed systemd launch and conservative, independently callable reclamation."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import time
from .runtime_state import StateStore, StateError, StateBusy, require, directory, load_deployment, HEX64
from .journal import IntentJournal as Journal, CLOSED, BOUND, STOPPING, UNRESOLVED, RECLAIM_VERIFIED, INTENT_PENDING, CREATE_ABSENT, RevisionConflict

class StopBusy(StateError):
    """Only a competing trusted reclaim holds this root's stop lock."""


def state_call(call,deadline_ns,*,clock=time.monotonic_ns,sleep=time.sleep):
    """Retry only known lock contention inside a caller's unchanged deadline."""
    while True:
        try: return call()
        except StateBusy:
            remaining=deadline_ns-clock()
            if remaining<=0: raise
            sleep(min(.005,remaining/1e9))

def unit_names(nonce):
    require(type(nonce) is str and HEX64.fullmatch(nonce))
    return tuple('openqms-d4-'+role+'-'+nonce+'.service' for role in ('controller','watchdog'))

def _run(argv,deadline_ns,*,max_seconds=1):
    remaining=(deadline_ns-time.monotonic_ns())/1e9
    require(remaining>0)
    result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={},timeout=min(remaining,max_seconds),check=False)
    require(result.returncode==0 and len(result.stdout)<=4096)
    return result.stdout

def read_unit(unit,deadline_ns):
    require(any(unit.startswith('openqms-d4-'+role+'-') and unit.endswith('.service') and HEX64.fullmatch(unit[len('openqms-d4-'+role+'-'):-8]) for role in ('controller','watchdog')))
    raw=_run(['/usr/bin/systemctl','show',unit,'--property=ActiveState,SubState,InvocationID,WatchdogTimestampMonotonic'],deadline_ns)
    value={}
    for line in raw.decode('ascii').splitlines():
        key,sep,item=line.partition('='); require(sep and key not in value); value[key]=item
    require(set(value)=={'ActiveState','SubState','InvocationID','WatchdogTimestampMonotonic'})
    return value

class SystemdUnits:
    def __init__(self,root): self.root=Path(root)
    def show(self,unit,deadline_ns): return read_unit(unit,deadline_ns)
    def start(self,unit,deadline_ns):
        nonce=unit[-72:-8];controller,watchdog=unit_names(nonce)
        role='controller' if unit==controller else 'watchdog'
        entry=self.root/'agent_d4_isolation'/'deploy'/'runtime_entry.py'
        validate_entry(self.root,entry)
        command='/usr/bin/python3 -I -S -B '+str(entry)+' stop --nonce '+nonce
        argv=['/usr/bin/systemd-run','--quiet','--unit='+unit,'--property=User=root','--property=Group=root','--property=Restart=no','--property=KillMode=control-group','--property=LimitCORE=0','--property=TimeoutStopSec=6s','--property=ExecStopPost='+command]
        if role=='watchdog': argv+=['--property=Type=notify','--property=NotifyAccess=main','--property=WatchdogSec=1s','--property=TimeoutStartSec=10s']
        else: argv+=['--property=Type=exec','--property=BindsTo='+watchdog,'--property=After='+watchdog,'--property=TimeoutStartSec=30s']
        argv+=['/usr/bin/python3','-I','-S','-B',str(entry),role,'--nonce',nonce]
        _run(argv,deadline_ns,max_seconds=10)

def validate_entry(root,entry):
    require(os.getuid()==0)
    with directory(root,0): pass
    # Every trusted executable/import component must be root-owned and unwritable
    # by group/others; no symlink may alter the fixed package path.
    for path in (Path(root)/'agent_d4_isolation',Path(root)/'agent_d4_isolation'/'deploy'):
        with directory(path,0,private=False) as fd: require(os.fstat(fd).st_mode & 0o022 == 0)
    with directory(Path(entry).parent,0,private=False) as fd:
        handle=os.open(Path(entry).name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        try:
            info=os.fstat(handle);require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and info.st_mode&0o022==0)
        finally:os.close(handle)

def launch_session(root,nonce,*,store=None,journal=None,units=None,preparation_leases=None):
    production=units is None
    store=store or StateStore(root);journal=journal or Journal(store.journal_path);units=units or SystemdUnits(root)
    if production:
        with directory(root,0) as fd:
            try: os.mkdir('state',0o700,dir_fd=fd)
            except FileExistsError: pass
        with directory(Path(root)/'state',0) as fd:
            try: os.mkdir('journal',0o700,dir_fd=fd)
            except FileExistsError: pass
    # Journal admission/intent is durable before registration and before either unit.
    journal.record_intent(nonce)
    state=store.create(nonce);controller,watchdog=unit_names(nonce)
    daemon_lease=api_lease=None
    try:
        if preparation_leases is None:
            from .linux_engine import EngineClient
            from .linux_identity import KernelCollector
            from .runtime_network import prepare_api
            engine=EngineClient();manifest=load_deployment(root)
            collector=KernelCollector(engine,manifest['permit']['image_digest'],manifest['api_container_id'])
            daemon_lease=collector.pin_daemon(state['deadline_ns'])
            api_lease=prepare_api(engine,manifest,state['deadline_ns'],install=True)
        else: daemon_lease,api_lease=preparation_leases
        from .watchdog_main import check_preparation
        require(daemon_lease.current(state['deadline_ns']) and api_lease.verify(state['deadline_ns']))
        state=state_call(lambda:store.merge(nonce,preparation={**daemon_lease.snapshot(),**api_lease.snapshot()}),state['deadline_ns'])
        require(check_preparation(state,daemon_lease,api_lease,state['deadline_ns']))
        units.start(watchdog,state['deadline_ns'])
        view=units.show(watchdog,state['deadline_ns'])
        require(view['ActiveState']=='active' and view['SubState']=='running' and view['InvocationID'])
        state=state_call(lambda:store.claim_invocation(nonce,'watchdog_invocation_id',view['InvocationID']),state['deadline_ns'])
        require(check_preparation(state,daemon_lease,api_lease,state['deadline_ns']))
        units.start(controller,state['deadline_ns'])
        view=units.show(controller,state['deadline_ns'])
        require(view['ActiveState']=='active' and view['InvocationID'])
        current=state_call(lambda:store.claim_invocation(nonce,'controller_invocation_id',view['InvocationID']),state['deadline_ns'])
        require(check_preparation(current,daemon_lease,api_lease,current['deadline_ns']))
        return 'isolation_unknown'
    except Exception:
        store.invalidate(nonce)
        return 'isolation_unknown'
    finally:
        if api_lease is not None: api_lease.close()
        if daemon_lease is not None: daemon_lease.close()

@contextmanager
def _stop_lock(store,*,deadline_ns=None,clock=time.monotonic_ns,sleep=time.sleep):
    with directory(store.root/'state',store.owner_uid) as fd:
        handle=os.open('.stop.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            info=os.fstat(handle);require(stat.S_ISREG(info.st_mode) and info.st_uid==store.owner_uid and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
            while True:
                try:
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if deadline_ns is None or clock()>=deadline_ns:raise StopBusy() from None
                    sleep(min(.005,max(0,(deadline_ns-clock())/1e9)))
            yield
        finally:os.close(handle)

def stop_session(root,nonce,*,store=None,journal=None,engine=None,collector=None,binding=None,clock=time.monotonic_ns,sleep=time.sleep,_maintenance=False,_cap_deadline=None):
    store=store or StateStore(root);journal=journal or Journal(store.journal_path)
    owned_binding=binding is None
    state=None
    attempt_deadline=clock()+5_000_000_000
    if _cap_deadline is not None:
        if type(_cap_deadline) is not int: return 'isolation_unknown'
        attempt_deadline=min(attempt_deadline,_cap_deadline)
    try:
        try: state=state_call(lambda:store.invalidate(nonce),min(attempt_deadline,clock()+500_000_000),clock=clock,sleep=sleep)  # before the reclaim lock
        except Exception:
            # Failed persistence cannot justify discarding a live capability.
            # Journal STOPPING revokes delivery before a bounded retained-fd kill.
            if binding is not None and not owned_binding:
                entry=journal.load(nonce);snapshot=binding.snapshot()
                require(snapshot.get('nonce')==nonce and snapshot.get('container_id')==entry.container_id)
                require(entry.state in (BOUND,STOPPING))
                if entry.state==BOUND: journal.transition(nonce,entry.revision,STOPPING)
                binding.terminate(deadline_ns=attempt_deadline)
            return 'isolation_unknown'
        deadline=attempt_deadline if _maintenance else min(attempt_deadline,state['deadline_ns'])
        with _stop_lock(store,deadline_ns=min(deadline,clock()+100_000_000),clock=clock,sleep=sleep):
            entry=journal.load(nonce)
            if entry.state==CLOSED: return journal.result(nonce).status
            require(clock()<deadline)
            if engine is None:
                from .linux_engine import EngineClient
                engine=EngineClient()
            try:
                matches=tuple(engine.list_by_nonce(nonce,deadline_ns=min(deadline,clock()+500_000_000)))
            except Exception:
                if binding is not None and binding.snapshot()==state['snapshot']:
                    binding.terminate(deadline_ns=deadline)
                return 'isolation_unknown'
            if entry.state==INTENT_PENDING and not matches:
                # Create must CAS to INFLIGHT before any request can be sent.
                # This original revision therefore excludes in-flight creates;
                # a concurrent creator wins the CAS or is blocked by this close.
                journal.transition(nonce,entry.revision,CLOSED,evidence=CREATE_ABSENT)
                return journal.result(nonce).status
            entry,plan=journal.observe(nonce,entry.revision,matches,trusted=True)
            if plan.action!='stop' or len(set(matches))!=1: return 'isolation_unknown'
            cid=plan.container_id
            if collector is None:
                from .linux_identity import KernelCollector
                manifest=load_deployment(root)
                collector=KernelCollector(engine,manifest['permit']['image_digest'],manifest['api_container_id'])
            if binding is None and not state['snapshot'] and collector.verify_created(nonce,cid,min(deadline,clock()+500_000_000)):
                # Never-started fixed recipe: no process/cgroup has existed. Only
                # the completed create plus verified non-forced removal and a
                # precise daemon 404 can close this special branch.
                from .linux_engine import EngineError
                engine.remove(cid,deadline_ns=min(deadline,clock()+500_000_000))
                absent=False
                try: engine.inspect(cid,deadline_ns=min(deadline,clock()+500_000_000))
                except EngineError as error: absent=str(error)=='engine_not_found'
                require(absent)
                if not state['create_converged']: return 'isolation_unknown'
                if entry.state==BOUND: entry=journal.transition(nonce,entry.revision,STOPPING)
                journal.transition(nonce,entry.revision,CLOSED,evidence=RECLAIM_VERIFIED)
                return 'isolation_terminated'
            if binding is not None:
                require(binding.snapshot()==state['snapshot'])
            elif state['snapshot']:
                from .linux_identity import fresh_stop_binding
                binding=fresh_stop_binding(state['snapshot'],nonce,min(deadline,clock()+500_000_000),engine=engine)
            else:
                # A late create is collected afresh; it never regains delivery authority.
                binding=collector.bind(nonce,cid,min(deadline,clock()+500_000_000))
            require(binding is not None)
            if entry.state==BOUND: entry=journal.transition(nonce,entry.revision,STOPPING)
            kernel_attempted=False
            def kernel_fallback():
                nonlocal kernel_attempted
                # Only the original caller's retained capability may use kernel
                # termination. A JSON-reconstructed binding never gains it.
                if not owned_binding and not kernel_attempted and binding.snapshot()==state['snapshot'] and clock()<deadline:
                    kernel_attempted=True
                    try: binding.terminate(deadline_ns=deadline)
                    except Exception: pass
            def settled(check_deadline):
                running=binding.container_running(check_deadline)
                if running is None: kernel_fallback()
                return running is False and binding.tasks_remaining()==0
            term_deadline=min(deadline,clock()+200_000_000)
            term_ok=binding.signal('SIGTERM',term_deadline)
            polite=term_deadline if term_ok is not False else clock()
            while clock()<polite:
                if settled(polite): break
                sleep(min(.02,max(0,(polite-clock())/1e9)))
            else:
                if binding.signal('SIGKILL',min(deadline,clock()+500_000_000)) is False: kernel_fallback()
                if binding.tasks_remaining()!=0: kernel_fallback()
            verified=False
            while clock()<deadline:
                if settled(min(deadline,clock()+100_000_000)):
                    verified=True;break
                sleep(min(.02,max(0,(deadline-clock())/1e9)))
            # Stopping a late object cannot establish create convergence. Closing
            # still requires the separately recorded trusted completion fact.
            if verified and state['create_converged']:
                journal.transition(nonce,entry.revision,CLOSED,evidence=RECLAIM_VERIFIED)
                return 'isolation_terminated'
    except StopBusy:
        # Another stopper may hold the lock while Engine RPCs block. Preserve
        # the original caller's exact live capability rather than abandoning it.
        # This branch cannot conclude reclaim or confer kernel authority on a
        # fresh JSON reconstruction; it can only revoke the gate and terminate.
        try:
            require(not owned_binding and binding is not None and state is not None)
            snapshot=binding.snapshot()
            require(snapshot==state['snapshot'] and snapshot.get('nonce')==nonce)
            for _ in range(3):
                entry=journal.load(nonce)
                require(entry.container_id==snapshot.get('container_id'))
                if entry.state==BOUND:
                    try:entry=journal.transition(nonce,entry.revision,STOPPING)
                    except RevisionConflict:continue
                require(entry.state==STOPPING)
                if clock()<deadline:binding.terminate(deadline_ns=deadline)
                break
        except Exception:pass
    except Exception: pass
    finally:
        if owned_binding and binding is not None: binding.close()
    return 'isolation_unknown'

def maintain(root,nonce):
    """Maintenance has only stop authority; it cannot launch or replay stdin."""
    return stop_session(root,nonce,_maintenance=True)
