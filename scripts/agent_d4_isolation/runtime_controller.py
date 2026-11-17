"""Real controller wiring; receiver output is never interpreted or returned."""
import os
from pathlib import Path
import re
import signal
import time

from .contracts import InfrastructureResult, validate_binding
from .controller import OutputBudget
from .docker_api import JournalLocator

UNKNOWN = 'isolation_unknown'
EXITED = 'isolation_exited'
TERMINATED = 'isolation_terminated'


class StopRequested(Exception):
    def __init__(self):
        super().__init__('controller_stopping')


def _stop_signal(signum, frame):
    raise StopRequested()


def _require(value):
    if not value:
        raise ValueError('controller_invalid')


def drive(nonce, *, store, journal, api, transport, collector, permit,
          config_loader, invocation_id, watchdog_probe, network_probe, preparation_probe,
          exited_probe, stop, clock=time.monotonic_ns, sleep=time.sleep, install_signals=False):
    """Consume the launcher's persisted intent; never create a second intent."""
    from .runtime_state import StateBusy
    def state_call(method, *args, **changes):
        deadline = clock() + 500_000_000
        while True:
            try:
                return getattr(store, method)(*args, **changes)
            except StateBusy:
                _require(clock() < deadline)
                sleep(.005)
    binding = channel = None
    desired, reclaimed = UNKNOWN, UNKNOWN
    previous_signals = {}
    try:
        if install_signals:
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous_signals[signum] = signal.getsignal(signum)
                signal.signal(signum, _stop_signal)
        _require(type(invocation_id) is str and re.fullmatch('[a-f0-9]{32}', invocation_id))
        state = state_call('read', nonce)
        _require(not state['invalidated'] and state['phase'] == 'prepare')
        _require(state['controller_invocation_id'] in (None, invocation_id))
        state = state_call('claim_invocation', nonce, 'controller_invocation_id', invocation_id)
        _require(clock() < state['deadline_ns'] and watchdog_probe(state, state['deadline_ns']))
        _require(state.get('preparation') and preparation_probe(state, state['deadline_ns']))
        intent = journal.load(nonce)
        _require(intent.state == 'intent_pending')
        outcome = api.create(nonce, expected_revision=intent.revision)
        _require(outcome.kind == 'created')
        current = journal.load(nonce)
        entry, _ = journal.observe(nonce, current.revision, (outcome.container_id,), trusted=True)
        _require(entry.state == 'bound' and not entry.doubted)
        state = state_call('read', nonce)
        state = state_call('merge', nonce, receiver_id=outcome.container_id, create_converged=True)
        locator = JournalLocator(nonce, entry.revision, outcome.container_id)
        # The immutable receiver starts without credentials and blocks on stdin.
        api.attach(locator)
        channel = transport.take_attach(outcome.container_id)
        _require(api.start(locator).done)
        binding = collector.bind(nonce, outcome.container_id, deadline_ns=state['deadline_ns'])
        state = state_call('read', nonce)
        snapshot = binding.snapshot()
        _require(all(snapshot.get(key) == value for key, value in state['preparation'].items()))
        state_call('merge', nonce, snapshot=snapshot)

        # Wait only within the original preparation deadline for the independent
        # watchdog to bind its own live references. Controller facts do not ack it.
        while True:
            state = state_call('read', nonce)
            _require(not state['invalidated'] and clock() < state['deadline_ns'])
            _require(watchdog_probe(state, state['deadline_ns']))
            if state_call('read', nonce)['watchdog_bound_verified']:
                break
            sleep(.02)

        def checked_state():
            state = state_call('read', nonce)
            _require(not state['invalidated'] and state['watchdog_bound_verified'])
            _require(state['controller_invocation_id'] == invocation_id)
            _require(clock() < state['deadline_ns'])
            _require(watchdog_probe(state, state['deadline_ns']))
            _require(journal.delivery_gate(nonce).allowed)
            _require(collector.revalidate(binding, deadline_ns=state['deadline_ns'], delivery=True) is not None)
            _require(network_probe(binding, state['deadline_ns']))
            _require(preparation_probe(state, state['deadline_ns']))
            # Observations above may block. Re-read after them, then check the
            # current watchdog instance immediately before returning to write.
            state = state_call('read', nonce)
            _require(not state['invalidated'] and state['watchdog_bound_verified'])
            _require(state['controller_invocation_id'] == invocation_id and clock() < state['deadline_ns'])
            _require(journal.delivery_gate(nonce).allowed)
            _require(watchdog_probe(state, state['deadline_ns']))
            _require(not state_call('read', nonce)['invalidated'])
            return state

        checked_state()
        config = config_loader()
        validate_binding(config, permit)
        payload = config.to_stdin()
        state_call('begin_delivery', nonce)  # durable absolute deadline before first byte
        offset = 0
        while offset < len(payload):
            state = checked_state()
            count = channel.write(payload[offset:], deadline_ns=state['deadline_ns'])
            _require(type(count) is int and 0 < count <= len(payload) - offset)
            offset += count
        channel.close_stdin()
        budget = OutputBudget()
        state = state_call('read', nonce)
        for chunk in channel.chunks(deadline_ns=state['deadline_ns']):
            if not budget.consume(chunk):
                desired = TERMINATED
                # stdin was already fully sent and half-closed above. Release
                # overflowing output before Engine exit confirmation: Docker
                # can hold its exit/inspect lock while attach output is blocked.
                # Keep the original kernel binding through stop verification.
                channel.close()
                break
            _require(not state_call('read', nonce)['invalidated'])
        else:
            # EOF and a current Engine fact, not completed/count/exit0 from the
            # receiver, establish only that this process exited.
            if exited_probe(outcome.container_id, state['deadline_ns']):
                desired = EXITED
    except Exception:
        desired = UNKNOWN
    finally:
        # The manager still has SIGKILL/TimeoutStopSec. Repeated polite signals
        # must not interrupt the one bounded cleanup while capabilities are live.
        for signum in previous_signals:
            signal.signal(signum, signal.SIG_IGN)
        try:
            try:
                reclaimed = stop(binding)
            except Exception:
                reclaimed = UNKNOWN
            if channel is not None:
                try:
                    channel.close_stdin()
                    channel.close()
                except Exception:
                    pass
            if binding is not None:
                binding.close()
        finally:
            for signum, previous in previous_signals.items():
                signal.signal(signum, previous)
    return InfrastructureResult(desired if reclaimed == TERMINATED else UNKNOWN)


def main(argv=None):
    import sys
    from .contracts import DeploymentPermit, read_private_config
    from .docker_api import DockerApi
    from .journal import IntentJournal
    from .linux_engine import EngineClient, EngineTransport
    from .linux_identity import KernelCollector
    from .runtime_network import NamespacePolicy, prepare_api
    from .runtime_state import StateStore, load_deployment
    from .runtime_supervisor import read_unit, stop_session, unit_names, state_call as bounded_state_call

    result = InfrastructureResult(UNKNOWN)
    daemon_lease = api_lease = None
    try:
        supplied = list(sys.argv[1:] if argv is None else argv)
        _require(len(supplied) == 2 and supplied[0] == '--nonce')
        _require(re.fullmatch('[a-f0-9]{64}', supplied[1]) is not None)
        nonce = supplied[1]
        _require(os.geteuid() == 0)
        root = Path(__file__).resolve().parent.parent
        manifest = load_deployment(root)
        permit = DeploymentPermit.from_mapping(manifest['permit'])
        store = StateStore(root)
        journal = IntentJournal(store.journal_path, clock=time.monotonic_ns)
        engine = EngineClient()
        transport = EngineTransport(engine, permit.image_digest, manifest['api_container_id'])
        api = DockerApi(transport, permit.image_digest, journal=journal,
                        clock=time.monotonic_ns, op_deadline_ns=10 * 10**9, response_limit=256 * 1024)
        collector = KernelCollector(engine, permit.image_digest, manifest['api_container_id'])
        _, watchdog = unit_names(nonce)
        state = bounded_state_call(lambda: store.read(nonce), time.monotonic_ns() + 500_000_000)
        daemon_lease = collector.pin_daemon(state['deadline_ns'])
        api_lease = prepare_api(engine, manifest, state['deadline_ns'], install=False)

        def prepared(state, deadline_ns):
            return (daemon_lease.current(deadline_ns) and api_lease.verify(deadline_ns)
                    and {**daemon_lease.snapshot(), **api_lease.snapshot()} == state['preparation'])

        def watched(state, deadline_ns):
            unit = read_unit(watchdog, min(deadline_ns, time.monotonic_ns() + 500_000_000))
            stamp = int(unit.get('WatchdogTimestampMonotonic', '0')) * 1000
            return (unit.get('ActiveState') == 'active' and unit.get('SubState') == 'running'
                    and unit.get('InvocationID') == state['watchdog_invocation_id']
                    and stamp > 0 and 0 <= time.monotonic_ns() - stamp <= 2 * 10**9)

        result = drive(nonce, store=store, journal=journal, api=api, transport=transport,
                       collector=collector, permit=permit,
                       config_loader=lambda: read_private_config(store.config_path),
                       invocation_id=os.environ.get('INVOCATION_ID'), watchdog_probe=watched,
                       preparation_probe=prepared,
                       network_probe=lambda binding, deadline: NamespacePolicy(binding.netns_fd, permit).verify(deadline),
                       exited_probe=lambda cid, deadline: engine.inspect(cid, deadline_ns=deadline)['State']['Running'] is False,
                       stop=lambda binding: stop_session(root, nonce, engine=engine,
                                                         collector=collector, binding=binding),
                       install_signals=True)
    except Exception:
        pass
    finally:
        if daemon_lease is not None:
            daemon_lease.close()
        if api_lease is not None:
            api_lease.close()
    print('{"status":"%s"}' % result.status, flush=True)
    return 1 if result.status == UNKNOWN else 0


if __name__ == '__main__':
    raise SystemExit(main())
