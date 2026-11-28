"""Controller orchestration for one D4 isolation session.

Everything external is injected: the journal, the Docker surface, a channel
factory, the watchdog decision source and a clock. That keeps the order of
operations testable without a daemon, and it keeps the security-relevant
sequence in one readable place instead of scattered across call sites.

The order below is the contract:

1. refuse to start at all if admission is not clear;
2. record the intent, then create, and treat anything but `created` as unknown;
3. bind only through a trusted observation;
4. re-check the delivery gate immediately before the single stdin write;
5. report one fixed infrastructure result and never a receiver claim.
"""
from .controller import DELIVERED, deliver_once, read_bounded, OutputBudget
from .contracts import InfrastructureResult

UNKNOWN = 'isolation_unknown'
TERMINATED = 'isolation_terminated'
EXITED = 'isolation_exited'


def _require(condition, message='controller_invalid'):
    if not condition:
        raise ValueError(message)


class Session:
    """Fixed results only; no receiver text ever becomes a conclusion."""

    def __init__(self):
        self.notes = []

    def note(self, value):
        self.notes.append(value)

    def result(self, value):
        _require(value in (UNKNOWN, TERMINATED, EXITED))
        return InfrastructureResult(value)


def run(nonce, config_bytes, *, journal, api, open_channel, watcher, clock,
        output_source=None):
    """Drive one session to a fixed infrastructure result.

    `watcher` is a callable returning the watchdog decision action; `open_channel`
    returns the attached stdin for `nonce`. A refusal at any earlier step means
    the configuration is never written.
    """
    session = Session()
    admission = journal.admission()
    if not admission.may_open_session:
        session.note('admission_denied')
        return session.result(UNKNOWN)

    try:
        entry = journal.record_intent(nonce)
    except Exception:
        session.note('record_failed')
        return session.result(UNKNOWN)

    outcome = api.create(nonce, expected_revision=entry.revision)
    if outcome.kind != 'created':
        session.note('create_' + outcome.kind)
        return session.result(UNKNOWN)

    try:
        # `create` advanced the record to create_inflight itself, so the revision
        # captured before it is stale: re-read before observing.
        current = journal.load(nonce)
        entry, plan = journal.observe(nonce, current.revision,
                                      (outcome.container_id,), trusted=True)
    except Exception:
        session.note('bind_failed')
        return session.result(UNKNOWN)
    if entry.state != 'bound':
        session.note('bind_state_' + entry.state)
        return session.result(UNKNOWN)

    # Re-check immediately before the write: a session that lost its watchdog
    # must not deliver, even if everything above succeeded.
    if watcher() != 'wait':
        session.note('watchdog_stopped')
        return session.result(UNKNOWN)

    gate = journal.delivery_gate(nonce)
    if not gate.allowed:
        session.note('gate_' + gate.reason)
        return session.result(UNKNOWN)

    try:
        channel = open_channel(nonce)
    except Exception:
        session.note('channel_failed')
        return session.result(UNKNOWN)

    delivery = deliver_once(channel, config_bytes)
    if delivery.result != DELIVERED:
        session.note('delivery_' + delivery.reason)
        return session.result(UNKNOWN)

    if output_source is not None:
        budget = OutputBudget()
        overflow = read_bounded(output_source, budget)
        if overflow is not None:
            # The caller terminates the whole cgroup; this layer only reports it.
            session.note('output_overflow')
            return session.result(UNKNOWN)

    # A bound intent always carries a stop plan; that is the normal teardown a
    # caller performs afterwards, not a failure of this session.
    session.note('delivered_' + str(getattr(plan, 'action', 'none')))
    return session.result(EXITED)
