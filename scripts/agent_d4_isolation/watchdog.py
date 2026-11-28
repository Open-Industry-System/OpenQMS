"""Watchdog decisions for one isolation session: pure, no timers, no signals.

The watchdog exists because the controller can die. It is deliberately dumb: it
holds one root-owned registration, wakes at most once a second, and answers a
single question — may this session continue, or must it be torn down now?

It never accepts a heartbeat from the receiver or the controller as proof of
life. Liveness is the systemd-observed fact passed in by the caller; this module
only applies the deadline and the phase budget.
"""
from dataclasses import dataclass
import re

NONCE = re.compile(r'[a-f0-9]{64}')
CONTAINER = re.compile(r'[a-f0-9]{64}')

PREPARE_NS = 30 * 10 ** 9      # design 8.3: preparation, no secret yet
DELIVERY_NS = 60 * 10 ** 9     # design 8.3: from the first stdin byte
RECLAIM_NS = 5 * 10 ** 9       # design 8.3: bounded reclaim verification
INTERVAL_NS = 1 * 10 ** 9      # design 8.3: at most one check per second
TERM_GRACE_NS = 200 * 10 ** 6  # design 8.3: TERM then force

PHASES = ('prepare', 'delivery', 'reclaim')
BUDGETS = {'prepare': PREPARE_NS, 'delivery': DELIVERY_NS, 'reclaim': RECLAIM_NS}

WAIT = 'wait'
EXPIRE = 'expire'
STOP_CONTROLLER = 'stop_controller'
ACTIONS = (WAIT, EXPIRE, STOP_CONTROLLER)


def _require(condition, message='registration_invalid'):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class Registration:
    """One session, written before any secret is delivered."""
    nonce: str
    container_id: str
    unit: str
    phase: str
    deadline_ns: int
    revision: int = 0

    def __post_init__(self):
        _require(type(self.nonce) is str and NONCE.fullmatch(self.nonce) is not None)
        _require(type(self.container_id) is str
                 and CONTAINER.fullmatch(self.container_id) is not None)
        _require(type(self.unit) is str and self.unit != '' and '\n' not in self.unit)
        _require(self.phase in PHASES)
        _require(type(self.deadline_ns) is int)
        _require(type(self.revision) is int and self.revision >= 0)


@dataclass(frozen=True, slots=True)
class Decision:
    action: str
    reason: str

    def __post_init__(self):
        _require(self.action in ACTIONS, 'decision_invalid')
        _require(type(self.reason) is str and self.reason != '')


def decide(now_ns, registration, *, controller_alive, systemd_alive):
    """The whole policy, in one place.

    `controller_alive` and `systemd_alive` are observed facts, not claims the
    receiver can influence. A dead controller means the session is over even if
    the deadline has not passed: nothing may keep delivering a secret.
    """
    _require(type(registration) is Registration)
    _require(type(now_ns) is int)
    _require(type(controller_alive) is bool and type(systemd_alive) is bool)
    if not systemd_alive:
        # Without the supervisor there is no one to reap; refuse to pretend.
        return Decision(EXPIRED_OR_STOP, EXPIRED_REASON)
    if not controller_alive:
        return Decision(EXPIRE, 'controller_gone')
    if now_ns >= registration.deadline_ns:
        return Decision(EXPIRE, 'deadline')
    return Decision(WAIT, 'running')


EXPIRED_OR_STOP = STOP_CONTROLLER
EXPIRED_REASON = 'supervisor_gone'


def next_deadline(registration):
    """Absolute deadline for the current phase, from its start."""
    _require(type(registration) is Registration)
    return registration.deadline_ns + BUDGETS[registration.phase]


def remaining_ns(now_ns, registration):
    _require(type(now_ns) is int)
    return max(0, registration.deadline_ns - now_ns)


def valid_interval_ns(interval_ns):
    _require(type(interval_ns) is int and 0 < interval_ns <= INTERVAL_NS,
             'interval_too_long')
    return interval_ns
