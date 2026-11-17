"""Bounded, evidence-based reclamation of one receiver container.

The handler never guesses which container to stop: it is given the exact full id
from the registration and a backend that can act on it. What it decides is only
*how far* to escalate and *when to give up*:

1. ask the daemon to stop it (short grace),
2. verify no task remains in the receiver's cgroup,
3. if not verified, force-stop, then verify again,
4. when the reclaim budget runs out, report `unknown` — never "probably stopped".

`unknown` is a real outcome here: the caller must keep the journal open, keep
refusing new sessions and preserve the evidence. Claiming success would be the
only unforgivable answer.
"""
from dataclasses import dataclass

TERMINATED = 'terminated'
UNKNOWN = 'unknown'
RESULTS = (TERMINATED, UNKNOWN)

# Design 8.3.
TERM_GRACE_NS = 200 * 10 ** 6
VERIFY_BUDGET_NS = 5 * 10 ** 9
POLL_NS = 100 * 10 ** 6


def _require(condition, message='stop_invalid'):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class Outcome:
    result: str
    reason: str
    escalations: int

    def __post_init__(self):
        _require(self.result in RESULTS)
        _require(type(self.reason) is str and self.reason != '')
        _require(type(self.escalations) is int and 0 <= self.escalations <= 2)
        _require((self.result == TERMINATED) or True)     # unknown carries evidence


class Backend:
    """What the handler needs; the real one talks to Docker and cgroup v2."""

    def stop(self, container_id, *, grace_ns):        # pragma: no cover - protocol
        raise NotImplementedError

    def kill(self, container_id):                     # pragma: no cover - protocol
        raise NotImplementedError

    def tasks_remaining(self, container_id):          # pragma: no cover - protocol
        """Number of tasks still in the receiver cgroup, or None if unprovable."""
        raise NotImplementedError


def reclaim(backend, container_id, *, clock):
    """Stop and verify one exact container within the reclaim budget.

    A backend exception is not evidence of anything: it ends the attempt as
    `unknown` with the exception class recorded, and the caller keeps the
    journal open.
    """
    _require(callable(getattr(backend, 'stop', None)), 'backend_invalid')
    _require(callable(getattr(backend, 'kill', None)), 'backend_invalid')
    _require(callable(getattr(backend, 'tasks_remaining', None)), 'backend_invalid')
    _require(type(container_id) is str and len(container_id) == 64, 'container_invalid')
    _require(callable(clock), 'clock_invalid')
    start = clock()
    overall = start + VERIFY_BUDGET_NS
    escalations = 0
    try:
        backend.stop(container_id, grace_ns=TERM_GRACE_NS)
        escalations = 1
        # The polite window is bounded separately, so a slow stop cannot consume
        # the budget the forced kill needs for its own verification.
        polite = min(overall, clock() + TERM_GRACE_NS + POLL_NS)
        if _settled(backend, container_id, clock, polite):
            return Outcome(TERMINATED, 'stopped', escalations)
        backend.kill(container_id)
        escalations = 2
        if _settled(backend, container_id, clock, overall):
            return Outcome(TERMINATED, 'killed', escalations)
        return Outcome(UNKNOWN, 'still_running', escalations)
    except Exception as error:
        return Outcome(UNKNOWN, type(error).__name__, escalations)


def _settled(backend, container_id, clock, deadline):
    """Poll until the cgroup reports zero tasks, or the budget is spent."""
    while clock() <= deadline:
        remaining = backend.tasks_remaining(container_id)
        if remaining == 0:
            return True
        if remaining is None:
            # Cannot prove the cgroup is empty: do not escalate on a guess, but
            # do not claim success either. Keep polling until the budget ends.
            pass
        if clock() > deadline:
            break
        _advance(clock)
    return False


def _advance(clock):
    """Give the backend a moment without sleeping in this module's logic."""
    sleeper = getattr(clock, 'sleep', None)
    if callable(sleeper):
        sleeper(POLL_NS)
