"""Decision tests for the watchdog and the bounded reclaim handler.

No timers, no signals, no daemon: a fake clock and a fake backend. What is pinned
here is only the decision table; whether systemd really runs the handler is a
Linux test.
"""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    '_i5_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
w = h.load('watchdog')
s = h.load('stop_handler')

NONCE = 'a' * 64
CID = 'c' * 64


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


class Clock:
    """Monotonic ns clock that can also advance itself in sleep()."""

    def __init__(self, start=10 ** 12):
        self.value = start

    def __call__(self):
        return self.value

    def sleep(self, delta):
        self.value += delta


def register(**changes):
    values = {'nonce': NONCE, 'container_id': CID, 'unit': 'openqms-d4-controller@x',
              'phase': 'delivery', 'deadline_ns': 10 ** 12 + w.DELIVERY_NS}
    values.update(changes)
    return w.Registration(**values)


# -- watchdog ----------------------------------------------------------

def test_a_live_session_before_its_deadline_waits():
    decision = w.decide(10 ** 12, register(), controller_alive=True, systemd_alive=True)
    assert (decision.action, decision.reason) == (w.WAIT, 'running')


def test_a_dead_controller_expires_even_before_the_deadline():
    decision = w.decide(10 ** 12, register(), controller_alive=False, systemd_alive=True)
    assert (decision.action, decision.reason) == (w.EXPIRE, 'controller_gone')


def test_a_missed_deadline_expires():
    entry = register()
    decision = w.decide(entry.deadline_ns, entry, controller_alive=True, systemd_alive=True)
    assert (decision.action, decision.reason) == (w.EXPIRE, 'deadline')


def test_a_dead_supervisor_stops_the_controller():
    decision = w.decide(10 ** 12, register(), controller_alive=True, systemd_alive=False)
    assert decision.action == w.STOP_CONTROLLER


def test_the_check_interval_may_not_exceed_one_second():
    assert w.valid_interval_ns(w.INTERVAL_NS) == w.INTERVAL_NS
    for bad in (0, w.INTERVAL_NS + 1, -1):
        with pytest.raises(ValueError):
            w.valid_interval_ns(bad)


def test_registration_is_strict():
    for changes in ({'nonce': 'short'}, {'container_id': 'x'},
                    {'phase': 'unknown'}, {'unit': ''}, {'deadline_ns': '1'},
                    {'revision': -1}):
        with pytest.raises(ValueError):
            register(**changes)


def test_phase_budgets_match_the_design():
    assert (w.PREPARE_NS, w.DELIVERY_NS, w.RECLAIM_NS) == (30 * 10 ** 9, 60 * 10 ** 9, 5 * 10 ** 9)
    assert w.remaining_ns(10 ** 12, register()) == w.DELIVERY_NS
    assert w.remaining_ns(10 ** 18, register()) == 0


# -- reclaim -----------------------------------------------------------

class Backend:
    """Fake backend: tasks survive until a kill happens, or as configured."""

    def __init__(self, *, survives=False, unprovable=False,
                 stop_error=None, kill_error=None):
        self.survives = survives
        self.unprovable = unprovable
        self.stop_error = stop_error
        self.kill_error = kill_error
        self.killed = False
        self.calls = []

    def stop(self, container_id, *, grace_ns):
        self.calls.append(('stop', grace_ns))
        if self.stop_error:
            raise self.stop_error

    def kill(self, container_id):
        self.calls.append(('kill', None))
        if self.kill_error:
            raise self.kill_error
        self.killed = True

    def tasks_remaining(self, container_id):
        if self.unprovable:
            return None
        if self.killed or not self.survives:
            return 0
        return 1


def test_a_clean_stop_is_verified_without_escalation():
    backend = Backend()
    outcome = s.reclaim(backend, CID, clock=Clock())
    assert (outcome.result, outcome.reason, outcome.escalations) == (s.TERMINATED, 'stopped', 1)
    assert [name for name, _ in backend.calls] == ['stop']


def test_a_surviving_process_forces_a_kill():
    backend = Backend(survives=True)
    outcome = s.reclaim(backend, CID, clock=Clock())
    assert (outcome.result, outcome.escalations) == (s.TERMINATED, 2)
    assert [name for name, _ in backend.calls] == ['stop', 'kill']


def test_an_unprovable_cgroup_is_never_reported_as_terminated():
    backend = Backend(unprovable=True)
    outcome = s.reclaim(backend, CID, clock=Clock())
    assert (outcome.result, outcome.reason) == (s.UNKNOWN, 'still_running')


def test_backend_exceptions_become_unknown_not_success():
    outcome = s.reclaim(Backend(stop_error=OSError('daemon gone')), CID, clock=Clock())
    assert (outcome.result, outcome.reason) == (s.UNKNOWN, 'OSError')
    outcome = s.reclaim(Backend(survives=True, kill_error=RuntimeError('nope')), CID,
                        clock=Clock())
    assert (outcome.result, outcome.reason) == (s.UNKNOWN, 'RuntimeError')


def test_the_reclaim_budget_is_finite():
    clock = Clock()
    start = clock()
    s.reclaim(Backend(unprovable=True), CID, clock=clock)
    assert clock() - start <= s.VERIFY_BUDGET_NS + s.POLL_NS


def test_reclaim_validates_its_inputs():
    with pytest.raises(ValueError):
        s.reclaim(object(), CID, clock=Clock())
    with pytest.raises(ValueError):
        s.reclaim(Backend(), 'short', clock=Clock())
    with pytest.raises(ValueError):
        s.reclaim(Backend(), CID, clock=object())
