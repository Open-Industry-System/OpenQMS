"""Independent systemd-observed watchdog; no receiver/controller heartbeat trust."""
import os
import socket
import time
from .runtime_state import StateStore, require, HEX32, load_deployment
from .runtime_supervisor import unit_names, read_unit, state_call, stop_session
from .journal import IntentJournal, CLOSED, INTENT_PENDING, CREATE_INFLIGHT

def check_preparation(state,daemon,api,deadline_ns):
    """Reopening capabilities must match the launcher epoch, never establish it."""
    try:
        frozen=state['preparation']
        return (bool(frozen) and {**daemon.snapshot(),**api.snapshot()}==frozen
                and daemon.current(deadline_ns) and api.verify(deadline_ns))
    except Exception: return False

def controller_alive(state,view):
    expected=state['controller_invocation_id']
    if expected is None:
        # Before launch only; after an InvocationID has been frozen inactivity
        # can never be mistaken for a not-yet-started controller.
        return state['phase']=='prepare' and view['ActiveState'] in ('inactive','activating','active')
    return view['ActiveState']=='active' and view['InvocationID']==expected

def notify(message):
    address=os.environ.get('NOTIFY_SOCKET')
    require(type(address) is str and address and '\x00' not in address)
    if address.startswith('@'): address='\x00'+address[1:]
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as channel:
        channel.settimeout(.1);channel.connect(address);channel.sendall(message.encode('ascii'))

def run(root,nonce,*,store=None,engine=None,collector=None,clock=time.monotonic_ns,sleep=time.sleep,unit_reader=read_unit,notifier=notify):
    store=store or StateStore(root);journal=IntentJournal(store.journal_path)
    from .linux_engine import EngineClient
    from .linux_identity import KernelCollector
    manifest=load_deployment(root)
    engine=engine or EngineClient()
    collector=collector or KernelCollector(engine,manifest['permit']['image_digest'],manifest['api_container_id'])
    invocation=os.environ.get('INVOCATION_ID')
    require(type(invocation) is str and HEX32.fullmatch(invocation))
    binding=None
    lease=None
    daemon_lease=None
    try:
        state=state_call(lambda:store.read(nonce),clock()+500_000_000,clock=clock,sleep=sleep)
        require(not state['invalidated'] and clock()<state['deadline_ns'])
        state=state_call(lambda:store.claim_invocation(nonce,'watchdog_invocation_id',invocation),min(state['deadline_ns'],clock()+500_000_000),clock=clock,sleep=sleep)
        require(state['watchdog_invocation_id']==invocation)
        from .runtime_network import prepare_api, NamespacePolicy
        from .contracts import DeploymentPermit
        daemon_lease=collector.pin_daemon(min(state['deadline_ns'],clock()+500_000_000))
        lease=prepare_api(engine,manifest,min(state['deadline_ns'],clock()+500_000_000),install=False)
        require(check_preparation(state,daemon_lease,lease,min(state['deadline_ns'],clock()+500_000_000)))
        state=state_call(lambda:store.read(nonce),min(state['deadline_ns'],clock()+500_000_000),clock=clock,sleep=sleep)
        require(not state['invalidated'] and state['phase']=='prepare' and clock()<state['deadline_ns'])
        require(state['watchdog_invocation_id']==invocation)
        notifier('READY=1')
        while True:
            started=clock();state=state_call(lambda:store.read(nonce),started+500_000_000,clock=clock,sleep=sleep)
            require(started<state['deadline_ns'] and state['watchdog_invocation_id']==invocation)
            # Poll every .25s; with the .5s probe budget and .1s notify bound,
            # heartbeat gaps retain margin under the 1s manager lease.
            # All management I/O shares one short absolute budget. A blocked
            # operation cannot extend the systemd heartbeat lease indefinitely.
            deadline=min(state['deadline_ns'],started+500_000_000)
            controller,watchdog=unit_names(nonce)
            own=unit_reader(watchdog,deadline)
            require(own['ActiveState'] in ('active','activating') and own['InvocationID']==invocation)
            view=unit_reader(controller,deadline)
            require(controller_alive(state,view))
            if state['controller_invocation_id'] is None and view['ActiveState']=='active':
                state=state_call(lambda:store.claim_invocation(nonce,'controller_invocation_id',view['InvocationID']),deadline,clock=clock,sleep=sleep)
            if state['invalidated']:
                # A live controller closes stdin before entering bounded reclaim.
                # Keep its existing supervisor/reference lease until it can finish
                # the independent proof and print its infrastructure conclusion.
                # This branch never reopens delivery or revives a restarted unit.
                require(state['phase']=='reclaim' and state['controller_invocation_id'] is not None)
                require(0<state['deadline_ns']-state['phase_started_ns']<=5_000_000_000)
                require(clock()<deadline)
                notifier('WATCHDOG=1')
                sleep(max(0,.25-(clock()-started)/1e9))
                continue
            require(check_preparation(state,daemon_lease,lease,deadline))
            entry=journal.load(nonce)
            require(entry.state!=CLOSED and not entry.doubted)
            if state['receiver_id'] is not None and state['snapshot']:
                require(entry.container_id==state['receiver_id'] and journal.delivery_gate(nonce).allowed)
                if binding is None: binding=collector.bind(nonce,state['receiver_id'],deadline)
                require(binding.snapshot()==state['snapshot'])
                require(all(binding.snapshot()[key]==value for key,value in state['preparation'].items()))
                require(collector.revalidate(binding,deadline,delivery=True) is not None)
                require(NamespacePolicy(binding.netns_fd,DeploymentPermit.from_mapping(manifest['permit'])).verify(deadline))
                if not state['watchdog_bound_verified']:
                    state=state_call(lambda:store.merge(nonce,watchdog_bound_verified=True),deadline,clock=clock,sleep=sleep)
            else:
                require(state['phase']=='prepare' and entry.state in (INTENT_PENDING,CREATE_INFLIGHT,'bound'))
            require(clock()<deadline)
            notifier('WATCHDOG=1')
            sleep(max(0,.25-(clock()-started)/1e9))
    except Exception:
        # Use the capability we still hold before losing it. Keep this final
        # action shorter than a heartbeat lease; systemd's independent handler
        # remains responsible for a separate conservative reclaim conclusion.
        stop_deadline=clock()+500_000_000
        try:
            stopped=store.invalidate(nonce)
            stop_deadline=min(stop_deadline,stopped['deadline_ns'])
        except Exception: pass
        if binding is not None:
            try:
                require(clock()<stop_deadline)
                result=stop_session(root,nonce,store=store,journal=journal,engine=engine,
                                    collector=collector,binding=binding,clock=clock,sleep=sleep,
                                    _cap_deadline=stop_deadline)
                if result!='isolation_terminated' and clock()<stop_deadline:
                    entry=journal.load(nonce)
                    require(entry.container_id==binding.snapshot()['container_id'])
                    if entry.state=='bound': journal.transition(nonce,entry.revision,'stopping')
                    binding.terminate(deadline_ns=stop_deadline)
            except Exception: pass
        return 1
    finally:
        if binding is not None: binding.close()
        if lease is not None: lease.close()
        if daemon_lease is not None: daemon_lease.close()
