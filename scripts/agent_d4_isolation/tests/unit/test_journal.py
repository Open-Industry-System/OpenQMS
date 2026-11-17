"""Behavioral tests for the I2 create-intent journal.

Everything here is a real local file in a pytest temporary directory plus an
injected monotonic clock; nothing sleeps, connects or reads the wall clock.
The fake daemon only scripts what a caller would observe, so `deliveries`
staying empty is what proves secret delivery stayed blocked.
"""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat

import pytest

spec = importlib.util.spec_from_file_location(
    '_i2_helpers_journal', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
j = h.load('journal')

BUDGET_NS = 30 * 10 ** 9
NONCE = 'a' * 64
SECOND = 'b' * 64
CONTAINER = 'c' * 64
OTHER_CONTAINER = 'd' * 64


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


class Clock:
    """Injected monotonic clock; tests advance it instead of sleeping."""

    def __init__(self):
        self.value = 10 ** 12

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += int(seconds * 10 ** 9)


class FakeDaemon:
    """Scripted create/enumerate surface that records every operation it got.

    `deliveries` records every attempted hand-over; a blocked session must leave
    it empty, and only a `delivery_gate`-allowed session may append.
    """

    def __init__(self):
        self.visible = {}
        self.calls = []
        self.deliveries = []
        self.generation = 1

    def create(self, nonce, outcome='accepted'):
        self.calls.append(('create', nonce, outcome))
        if outcome == 'accepted':
            self.visible.setdefault(nonce, [])
        return outcome

    def appear(self, nonce, container_id):
        self.visible.setdefault(nonce, []).append(container_id)

    def enumerate(self, nonce):
        self.calls.append(('enumerate', nonce))
        return tuple(self.visible.get(nonce, ()))

    def stop(self, container_id):
        self.calls.append(('stop', container_id))
        for ids in self.visible.values():
            if container_id in ids:
                ids.remove(container_id)

    def deliver(self, nonce, secret):
        self.calls.append(('deliver', nonce))
        self.deliveries.append(secret)

    def restart(self):
        self.generation += 1
        return self.generation

    def stopped(self):
        return [call[1] for call in self.calls if call[0] == 'stop']


def open_session(journal, daemon, nonce):
    """Stand-in for the caller contract: ask the per-intent gate, never the state.

    `admission()` is the global all-clear gate and is false during any live
    session, so using it here would make every `deliveries == []` assertion
    vacuous.
    """
    if not journal.delivery_gate(nonce).allowed:
        return False
    daemon.deliver(nonce, 'synthetic-secret-123456789')
    return True


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def root(tmp_path):
    directory = Path(os.path.realpath(tmp_path)) / 'journal'
    directory.mkdir(mode=0o700)
    return directory


@pytest.fixture
def journal(root, clock):
    return j.IntentJournal(root, clock=clock, budget_ns=BUDGET_NS)


def entry_path(root, nonce=NONCE):
    return root / (nonce + '.json')


def valid_entry(**changes):
    value = {'nonce': NONCE, 'state': j.INTENT_PENDING, 'revision': 0,
             'deadline_ns': 1, 'container_id': None, 'closed_by': None,
             'doubted': False}
    value.update(changes)
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def drive(journal, path, nonce=NONCE):
    """Walk one legal state path and return the entry in its final state."""
    journal.record_intent(nonce)
    entry = journal.load(nonce)
    for target in path[1:]:
        kwargs = {}
        if target == j.BOUND:
            kwargs['container_id'] = CONTAINER
        elif target == j.CLOSED:
            kwargs['evidence'] = j.RECLAIM_VERIFIED if entry.state == j.STOPPING else j.CREATE_ABSENT
        entry = journal.transition(nonce, entry.revision, target, **kwargs)
    return entry


OPEN_PATHS = {
    j.INTENT_PENDING: (j.INTENT_PENDING,),
    j.CREATE_INFLIGHT: (j.INTENT_PENDING, j.CREATE_INFLIGHT),
    j.BOUND: (j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND),
    j.STOPPING: (j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND, j.STOPPING),
    j.UNRESOLVED: (j.INTENT_PENDING, j.CREATE_INFLIGHT, j.UNRESOLVED),
}


# --------------------------------------------------------------------------
# Registration: atomic, owner-only, no-clobber
# --------------------------------------------------------------------------

def test_registration_is_written_owner_only_without_leftovers(root, journal):
    entry = journal.record_intent(NONCE)
    assert entry.state == j.INTENT_PENDING and entry.revision == 0
    info = entry_path(root).stat()
    assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert sorted(os.listdir(root)) == ['.lock', NONCE + '.json']
    assert journal.load(NONCE) == entry


def test_registration_is_fsynced_around_the_name_appearing(root, journal, monkeypatch):
    trace = []
    real_fsync, real_link = os.fsync, os.link

    def fsync(fd):
        trace.append('fsync:' + ('dir' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file'))
        return real_fsync(fd)

    def link(*args, **kwargs):
        trace.append('link')
        return real_link(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', fsync)
        patch.setattr(os, 'link', link)
        journal.record_intent(NONCE)
    # Durability of the bytes must precede the durability of the name, and the
    # temporary name must be removed durably as well.
    assert trace == ['fsync:file', 'link', 'fsync:dir', 'fsync:dir'], trace
    assert journal.load(NONCE).state == j.INTENT_PENDING


def test_update_replaces_the_entry_and_fsyncs_both_sides(root, journal, monkeypatch):
    journal.record_intent(NONCE)
    trace = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        trace.append('fsync:' + ('dir' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file'))
        return real_fsync(fd)

    def replace(*args, **kwargs):
        trace.append('replace')
        return real_replace(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', fsync)
        patch.setattr(os, 'replace', replace)
        journal.transition(NONCE, 0, j.CREATE_INFLIGHT)
    # rename(2) removes the temporary name atomically, so one directory fsync
    # after it covers both the new name and the old one's disappearance.
    assert trace == ['fsync:file', 'replace', 'fsync:dir'], trace


def test_existing_closed_registration_is_never_overwritten(root, journal):
    """A reused nonce must fail instead of silently replacing the record."""
    journal.record_intent(NONCE)
    journal.transition(NONCE, 0, j.CLOSED, evidence=j.CREATE_ABSENT)
    before = entry_path(root).read_bytes()
    with pytest.raises(j.JournalError) as error:
        journal.record_intent(NONCE)
    assert str(error.value) == 'journal_invalid'
    assert error.value.__context__ is None
    assert entry_path(root).read_bytes() == before


def test_symlinked_registration_is_refused(root, journal):
    elsewhere = root.parent / 'elsewhere.json'
    elsewhere.write_bytes(b'{"sealed":1}')
    elsewhere.chmod(0o600)
    entry_path(root).symlink_to(elsewhere)
    with pytest.raises(j.JournalError) as error:
        journal.load(NONCE)
    assert str(error.value) == 'journal_invalid'
    assert error.value.__context__ is None
    assert elsewhere.read_bytes() == b'{"sealed":1}'
    assert journal.admission().may_open_session is False


def test_symlinked_root_is_refused(root, journal):
    journal.record_intent(NONCE)
    moved = root.with_name('moved')
    root.rename(moved)
    root.symlink_to(moved, target_is_directory=True)
    with pytest.raises(j.JournalError):
        journal.load(NONCE)
    assert entry_path(moved).exists()
    assert journal.admission().may_open_session is False


@pytest.mark.parametrize('mode', [0o755, 0o770, 0o600])
def test_unsafe_directory_mode_is_refused(root, journal, mode):
    root.chmod(mode)
    with pytest.raises(j.JournalError) as error:
        journal.record_intent(NONCE)
    assert str(error.value) == 'journal_invalid'
    admission = journal.admission()
    assert (admission.may_open_session, admission.may_deliver_secret) == (False, False)
    assert admission.reason == 'journal_invalid'


@pytest.mark.parametrize('nonce', ['', '..', '../x', 'a' * 63, 'a' * 65, 'A' * 64,
                                   'a' * 64 + '/../b', '/tmp/absolute', 'a' * 64 + '\x00',
                                   None, 123])
def test_nonce_must_be_a_canonical_hex_identifier(root, journal, nonce):
    calls = (lambda: journal.record_intent(nonce),
             lambda: journal.load(nonce),
             lambda: journal.transition(nonce, 0, j.CREATE_INFLIGHT))
    for call in calls:
        with pytest.raises(j.JournalError) as error:
            call()
        assert str(error.value) == 'journal_invalid'
        assert error.value.__context__ is None
    # Nothing was created: a hostile nonce never becomes a path component.
    assert os.listdir(root) == []


@pytest.mark.parametrize('change', ['file-mode', 'hardlink', 'oversize', 'fifo'])
def test_unsafe_entry_file_is_refused(root, journal, change):
    journal.record_intent(NONCE)
    path = entry_path(root)
    if change == 'file-mode':
        path.chmod(0o644)
    elif change == 'hardlink':
        os.link(path, root.parent / 'alias.json')
    elif change == 'oversize':
        path.write_bytes(b' ' * (j.ENTRY_LIMIT + 1))
    elif change == 'fifo':
        path.unlink()
        os.mkfifo(path, 0o600)
    with pytest.raises(j.JournalError) as error:
        journal.load(NONCE)
    assert str(error.value) == 'journal_invalid'
    assert error.value.__context__ is None
    assert journal.admission().may_deliver_secret is False


# --------------------------------------------------------------------------
# Revision CAS and the transition table
# --------------------------------------------------------------------------

def test_transition_requires_the_current_revision(root, journal):
    journal.record_intent(NONCE)
    updated = journal.transition(NONCE, 0, j.CREATE_INFLIGHT)
    assert updated.revision == 1
    assert journal.load(NONCE) == updated
    for stale in (0, 7):
        with pytest.raises(j.RevisionConflict) as error:
            journal.transition(NONCE, stale, j.UNRESOLVED)
        assert str(error.value) == 'revision_conflict'
        assert error.value.__context__ is None
        assert journal.load(NONCE) == updated


def test_concurrent_writer_fails_closed(root, journal):
    journal.record_intent(NONCE)
    before = entry_path(root).read_bytes()
    fd = os.open(str(root / '.lock'), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(j.JournalBusy) as error:
            journal.transition(NONCE, 0, j.CREATE_INFLIGHT)
        assert str(error.value) == 'journal_busy'
        assert error.value.__context__ is None
        assert entry_path(root).read_bytes() == before
        with pytest.raises(j.JournalBusy):
            journal.record_intent(SECOND)
    finally:
        os.close(fd)
    assert journal.transition(NONCE, 0, j.CREATE_INFLIGHT).state == j.CREATE_INFLIGHT


def test_revision_advances_by_one_per_accepted_transition(root, journal):
    entry = journal.record_intent(NONCE)
    assert entry.revision == 0
    for target, kwargs in ((j.CREATE_INFLIGHT, {}), (j.BOUND, {'container_id': CONTAINER}),
                           (j.STOPPING, {}), (j.CLOSED, {'evidence': j.RECLAIM_VERIFIED})):
        expected = entry.revision
        entry = journal.transition(NONCE, expected, target, **kwargs)
        assert entry.revision == expected + 1
        assert journal.load(NONCE) == entry


@pytest.mark.parametrize('path,target', [
    ((j.INTENT_PENDING,), j.BOUND),
    ((j.INTENT_PENDING,), j.STOPPING),
    ((j.INTENT_PENDING,), j.INTENT_PENDING),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT), j.STOPPING),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT), j.INTENT_PENDING),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND), j.CLOSED),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND), j.CREATE_INFLIGHT),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND, j.STOPPING), j.BOUND),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND, j.STOPPING, j.CLOSED), j.UNRESOLVED),
])
def test_illegal_transitions_are_refused(root, journal, path, target):
    entry = drive(journal, path)
    kwargs = {'container_id': CONTAINER} if target == j.BOUND else {}
    with pytest.raises(j.TransitionRejected) as error:
        journal.transition(NONCE, entry.revision, target, **kwargs)
    assert str(error.value) == 'transition_rejected'
    assert error.value.__context__ is None
    assert journal.load(NONCE) == entry


@pytest.mark.parametrize('path,evidence', [
    ((j.INTENT_PENDING,), None),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT), None),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT), j.RECLAIM_VERIFIED),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND), j.RECLAIM_VERIFIED),
    ((j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND, j.STOPPING), j.CREATE_ABSENT),
    ((j.INTENT_PENDING,), 'trusted-by-caller'),
])
def test_closing_needs_matching_trusted_evidence(root, journal, path, evidence):
    entry = drive(journal, path)
    with pytest.raises(j.TransitionRejected):
        journal.transition(NONCE, entry.revision, j.CLOSED, evidence=evidence)
    assert journal.load(NONCE) == entry
    assert journal.admission().may_deliver_secret is False


def test_evidence_is_rejected_outside_closing(root, journal):
    journal.record_intent(NONCE)
    with pytest.raises(j.TransitionRejected):
        journal.transition(NONCE, 0, j.CREATE_INFLIGHT, evidence=j.CREATE_ABSENT)
    with pytest.raises(j.TransitionRejected):
        journal.transition(NONCE, 0, j.CREATE_INFLIGHT, container_id=CONTAINER)


@pytest.mark.parametrize('container_id', [None, '', 'c' * 63, 'c' * 65, 'C' * 64,
                                          'c' * 64 + '\n', 7, True])
def test_binding_needs_one_exact_container_id(root, journal, container_id):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    with pytest.raises(j.TransitionRejected):
        journal.transition(NONCE, entry.revision, j.BOUND, container_id=container_id)
    assert journal.load(NONCE) == entry


def test_intent_never_rebinds_to_a_different_object(root, journal):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND))
    entry = journal.transition(NONCE, entry.revision, j.UNRESOLVED)
    assert entry.container_id == CONTAINER
    # A bare transition may not re-bind at all: doubt is cleared only by a
    # trusted observation, and a different id there is folded into doubt.
    with pytest.raises(j.TransitionRejected):
        journal.transition(NONCE, entry.revision, j.BOUND, container_id=OTHER_CONTAINER)
    still, plan = journal.observe(NONCE, entry.revision, (OTHER_CONTAINER,), trusted=True)
    assert still.state == j.UNRESOLVED and plan.action == 'none'
    rebound, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert rebound.container_id == CONTAINER and rebound.state == j.BOUND
    assert plan.action == 'stop'


def test_bare_transition_cannot_clear_doubt_into_a_bound_intent(root, journal):
    """`unresolved` is cleared by observation only, never by an assertion."""
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    entry, plan = journal.observe(NONCE, entry.revision, (), trusted=False)
    assert entry.state == j.UNRESOLVED
    with pytest.raises(j.TransitionRejected):
        journal.transition(NONCE, entry.revision, j.BOUND, container_id=CONTAINER)
    with pytest.raises(j.TransitionRejected):
        journal.transition(NONCE, entry.revision, j.BOUND, container_id=OTHER_CONTAINER)
    assert journal.load(NONCE).state == j.UNRESOLVED
    assert journal.delivery_gate(NONCE).allowed is False


def test_record_claiming_reclaim_without_an_object_is_rejected(root):
    """`reclaim_verified` must name the object it reclaimed."""
    entry_path(root).write_bytes(valid_entry(state=j.CLOSED, revision=4,
                                             closed_by=j.RECLAIM_VERIFIED))
    entry_path(root).chmod(0o600)
    with pytest.raises(j.JournalError):
        j.IntentJournal(root).load(NONCE)


def test_public_transition_into_doubt_also_marks_it(root, journal):
    """Doubt entered through `transition` must not be rebindable into a delivery."""
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    entry = journal.transition(NONCE, entry.revision, j.UNRESOLVED)
    assert entry.doubted is True
    assert journal.load(NONCE).doubted is True
    entry, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert entry.state == j.BOUND
    gate = journal.delivery_gate(NONCE)
    assert (gate.allowed, gate.reason) == (False, 'reclaimed_after_doubt')
    assert plan.action == 'stop'          # reclaim path is preserved


def test_open_session_delivers_once_a_clean_intent_is_bound(root, journal):
    """Positive control: the gate must be able to say yes, not only no."""
    daemon = FakeDaemon()
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    entry, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert journal.delivery_gate(NONCE).allowed is True
    assert open_session(journal, daemon, NONCE) is True
    assert daemon.deliveries == ['synthetic-secret-123456789']


def test_record_with_unresolved_state_must_carry_the_doubt_flag(root):
    entry_path(root).write_bytes(valid_entry(state=j.UNRESOLVED, revision=2))
    entry_path(root).chmod(0o600)
    with pytest.raises(j.JournalError):
        j.IntentJournal(root).load(NONCE)


def test_non_string_evidence_is_a_rejected_transition(root, journal):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    for bad in (['x'], {'a': 1}, 0):
        with pytest.raises(j.TransitionRejected):
            journal.transition(NONCE, entry.revision, j.CLOSED, evidence=bad)
    assert journal.load(NONCE).state == j.CREATE_INFLIGHT


def test_a_second_intent_is_refused_while_one_is_open(root, journal):
    drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    with pytest.raises(j.SessionBlocked) as error:
        journal.record_intent(SECOND)
    assert str(error.value) == 'session_blocked'
    assert error.value.__context__ is None
    assert not entry_path(root, SECOND).exists()
    entry = journal.load(NONCE)
    journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.CREATE_ABSENT)
    assert journal.record_intent(SECOND).state == j.INTENT_PENDING


# --------------------------------------------------------------------------
# Derived admission: fail closed, never inferred by the caller
# --------------------------------------------------------------------------

@pytest.mark.parametrize('state', sorted(OPEN_PATHS))
def test_admission_denies_every_open_state(root, journal, state):
    assert drive(journal, OPEN_PATHS[state]).state == state
    admission = journal.admission()
    assert (admission.may_open_session, admission.may_deliver_secret) == (False, False)
    assert admission.reason == state


def test_admission_is_clear_only_without_open_intents(root, journal):
    clear = journal.admission()
    assert (clear.may_open_session, clear.may_deliver_secret, clear.reason) == (True, True, 'clear')
    entry = journal.record_intent(NONCE)
    assert journal.admission().may_open_session is False
    journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.CREATE_ABSENT)
    assert journal.admission().may_open_session is True


def test_admission_fails_closed_when_any_entry_is_unreadable(root, journal):
    entry = journal.record_intent(NONCE)
    journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.CREATE_ABSENT)
    broken = entry_path(root, SECOND)
    broken.write_bytes(b'{"state":')
    broken.chmod(0o600)
    admission = journal.admission()
    assert (admission.may_open_session, admission.may_deliver_secret) == (False, False)
    assert admission.reason == 'journal_invalid'
    with pytest.raises(j.JournalError) as error:
        journal.load(SECOND)
    assert str(error.value) == 'journal_invalid'


def test_admission_denies_when_the_journal_cannot_be_opened(tmp_path, clock):
    missing = j.IntentJournal(Path(os.path.realpath(tmp_path)) / 'missing',
                              clock=clock, budget_ns=BUDGET_NS)
    admission = missing.admission()
    assert (admission.may_open_session, admission.may_deliver_secret) == (False, False)
    assert admission.reason == 'journal_invalid'


@pytest.mark.parametrize('root_value', ['', 'journal/../escape', None, 5])
def test_root_input_is_validated(root_value, clock):
    with pytest.raises(j.JournalError) as error:
        j.IntentJournal(root_value, clock=clock, budget_ns=BUDGET_NS)
    assert str(error.value) == 'journal_invalid'


@pytest.mark.parametrize('budget_ns', [0, -1, 1.5, True, '30'])
def test_budget_input_is_validated(root, clock, budget_ns):
    with pytest.raises(j.JournalError):
        j.IntentJournal(root, clock=clock, budget_ns=budget_ns)


# --------------------------------------------------------------------------
# Late creation: the accepted create that nobody ever answered
# --------------------------------------------------------------------------

def test_late_target_stays_blocked_until_verified_and_reclaimed(root, journal, clock):
    daemon = FakeDaemon()
    entry = journal.record_intent(NONCE)          # persisted BEFORE any create
    assert entry.state == j.INTENT_PENDING
    assert daemon.calls == []                     # nothing was requested yet
    entry = journal.transition(NONCE, entry.revision, j.CREATE_INFLIGHT)
    assert daemon.create(NONCE) == 'accepted'     # daemon took it, caller died
    assert open_session(journal, daemon, NONCE) is False
    assert daemon.deliveries == []

    for _ in range(2):                            # first and second enumeration: empty
        entry, plan = journal.observe(NONCE, entry.revision, daemon.enumerate(NONCE), trusted=True)
        assert entry.state == j.CREATE_INFLIGHT
        assert (plan.action, plan.container_id) == ('none', None)
        assert journal.admission().may_deliver_secret is False
        assert open_session(journal, daemon, NONCE) is False
        assert daemon.stopped() == []

    clock.advance(30)                             # prepare window expires
    entry, plan = journal.observe(NONCE, entry.revision, daemon.enumerate(NONCE), trusted=True)
    assert entry.state == j.UNRESOLVED
    assert journal.result(NONCE).as_dict() == {'status': 'isolation_unknown'}
    assert journal.admission().may_open_session is False
    assert open_session(journal, daemon, NONCE) is False

    daemon.appear(NONCE, CONTAINER)               # the late container shows up
    entry, plan = journal.observe(NONCE, entry.revision, daemon.enumerate(NONCE), trusted=True)
    assert (entry.state, entry.container_id) == (j.BOUND, CONTAINER)
    assert (plan.action, plan.container_id) == ('stop', CONTAINER)
    # Recovered after doubt: a reclaim target, never a delivery target, because
    # the controller that would have consumed the text is gone.
    assert journal.delivery_gate(NONCE).allowed is False
    assert open_session(journal, daemon, NONCE) is False

    entry = journal.transition(NONCE, entry.revision, j.STOPPING)
    daemon.stop(CONTAINER)
    assert daemon.stopped() == [CONTAINER]
    assert open_session(journal, daemon, NONCE) is False
    journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.RECLAIM_VERIFIED)
    assert journal.result(NONCE).as_dict() == {'status': 'isolation_terminated'}
    assert journal.admission().may_open_session is True
    assert daemon.deliveries == []                # no secret ever reached it
    # A closed intent is never a delivery target either; a fresh session is the
    # only place a config may be offered.
    assert open_session(journal, daemon, NONCE) is False
    assert daemon.deliveries == []


@pytest.mark.parametrize('polls', [1, 3, 9])
def test_repeated_empty_enumerations_never_close(root, journal, clock, polls):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    for _ in range(polls):
        entry, plan = journal.observe(NONCE, entry.revision, (), trusted=True)
        assert entry.state != j.CLOSED
        assert (plan.action, plan.container_id) == ('none', None)
        assert journal.admission().may_deliver_secret is False
        assert journal.result(NONCE).as_dict() == {'status': 'isolation_unknown'}
        clock.advance(60)
    # Expiry is only ever an observation by the caller, never spontaneous.
    entry, plan = journal.observe(NONCE, entry.revision, (), trusted=True)
    assert entry.state == j.UNRESOLVED


def test_timeout_reports_unknown_and_blocks_the_next_session(root, journal, clock):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    clock.advance(31)
    entry, plan = journal.observe(NONCE, entry.revision, (), trusted=True)
    assert (entry.state, entry.closed_by) == (j.UNRESOLVED, None)
    status = journal.result(NONCE).as_dict()['status']
    assert status == 'isolation_unknown'
    assert status not in ('isolation_exited', 'isolation_terminated')
    with pytest.raises(j.SessionBlocked):
        journal.record_intent(SECOND)


def test_late_error_alone_never_closes_the_intent(root, journal, clock):
    daemon = FakeDaemon()
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    daemon.create(NONCE, outcome='error-after-exit')
    # An answer the caller cannot prove continuous is doubt: the intent becomes
    # unresolved instead of being closed as "the error cancelled it".
    entry, plan = journal.observe(NONCE, entry.revision, daemon.enumerate(NONCE), trusted=False)
    assert entry.state == j.UNRESOLVED
    assert entry.closed_by is None
    assert journal.admission().may_deliver_secret is False
    clock.advance(31)
    entry, plan = journal.observe(NONCE, entry.revision, (), trusted=False)
    assert entry.state == j.UNRESOLVED
    assert journal.admission().may_open_session is False


def test_repeated_identical_answer_is_not_ambiguity(root, journal):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    entry, plan = journal.observe(NONCE, entry.revision, (CONTAINER, CONTAINER), trusted=True)
    assert (entry.state, entry.container_id) == (j.BOUND, CONTAINER)
    assert (plan.action, plan.container_id) == ('stop', CONTAINER)


def test_two_targets_stay_unresolved_and_nothing_is_stopped(root, journal):
    daemon = FakeDaemon()
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    daemon.appear(NONCE, CONTAINER)
    daemon.appear(NONCE, OTHER_CONTAINER)
    entry, plan = journal.observe(NONCE, entry.revision, daemon.enumerate(NONCE), trusted=True)
    assert entry.state == j.UNRESOLVED
    assert entry.container_id is None
    assert (plan.action, plan.container_id) == ('none', None)
    assert daemon.stopped() == []                 # no prefix/label guessing
    assert journal.admission().may_deliver_secret is False
    again, plan = journal.observe(NONCE, entry.revision, daemon.enumerate(NONCE), trusted=True)
    assert again.state == j.UNRESOLVED and plan.action == 'none'


def test_daemon_restart_makes_the_bound_target_unverifiable(root, journal):
    daemon = FakeDaemon()
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND))
    daemon.appear(NONCE, CONTAINER)
    first = daemon.generation
    assert daemon.restart() != first
    entry, plan = journal.observe(NONCE, entry.revision, daemon.enumerate(NONCE), trusted=False)
    assert entry.state == j.UNRESOLVED
    assert entry.container_id == CONTAINER        # maintenance evidence only
    assert (plan.action, plan.container_id) == ('none', None)
    assert journal.admission().may_open_session is False
    assert journal.admission().may_deliver_secret is False


def test_unresolved_maintenance_can_only_verify_and_stop(root, journal, clock):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    clock.advance(31)
    entry, plan = journal.observe(NONCE, entry.revision, (), trusted=True)
    assert entry.state == j.UNRESOLVED
    for target in (j.INTENT_PENDING, j.CREATE_INFLIGHT, j.STOPPING):
        with pytest.raises(j.TransitionRejected):
            journal.transition(NONCE, entry.revision, target)
    assert journal.admission().may_deliver_secret is False
    bound, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert (bound.state, plan.action) == (j.BOUND, 'stop')
    assert journal.admission().may_deliver_secret is False
    stopping = journal.transition(NONCE, bound.revision, j.STOPPING)
    assert journal.admission().may_deliver_secret is False
    journal.transition(NONCE, stopping.revision, j.CLOSED, evidence=j.RECLAIM_VERIFIED)
    assert journal.admission().may_deliver_secret is True


def test_untrusted_observation_cannot_bind_a_target(root, journal):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    entry, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=False)
    assert entry.state == j.UNRESOLVED
    assert entry.container_id is None
    assert plan.action == 'none'


def test_malformed_answer_is_doubt_not_evidence(root, journal):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    for matches in ((CONTAINER.upper(),), ('c' * 63,), ('../' + CONTAINER,), (None,), (7,)):
        entry, plan = journal.observe(NONCE, entry.revision, matches, trusted=True)
        assert entry.state == j.UNRESOLVED
        assert plan.action == 'none'
        assert journal.admission().may_deliver_secret is False


# --------------------------------------------------------------------------
# Durability and fixed diagnostics
# --------------------------------------------------------------------------

@pytest.mark.parametrize('operation', ['fsync', 'replace'])
def test_failed_write_keeps_the_open_intent(root, journal, monkeypatch, operation):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT, j.BOUND, j.STOPPING))
    before = entry_path(root).read_bytes()

    def failing(*args, **kwargs):
        raise OSError(28, 'No space left on device')

    with monkeypatch.context() as patch:
        patch.setattr(os, operation, failing)
        with pytest.raises(j.JournalError) as error:
            journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.RECLAIM_VERIFIED)
    assert str(error.value) == 'journal_invalid'
    assert error.value.__context__ is None
    assert entry_path(root).read_bytes() == before
    assert journal.load(NONCE) == entry            # never silently cleared
    assert journal.admission().may_deliver_secret is False


def test_failed_registration_leaves_nothing_behind(root, journal, monkeypatch):
    def failing(*args, **kwargs):
        raise OSError(30, 'Read-only file system')

    with monkeypatch.context() as patch:
        patch.setattr(os, 'link', failing)
        with pytest.raises(j.JournalError) as error:
            journal.record_intent(NONCE)
    assert str(error.value) == 'journal_invalid'
    assert not entry_path(root).exists()
    assert journal.admission().may_open_session is True


def test_stale_temporary_file_does_not_block_maintenance(root, journal):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    stale = root / ('.' + NONCE + '.tmp')
    stale.write_bytes(b'leftover-from-a-crash')
    stale.chmod(0o600)
    updated = journal.transition(NONCE, entry.revision, j.UNRESOLVED)
    assert updated.state == j.UNRESOLVED
    assert not stale.exists()
    # The unreadable-looking leftover never turned into a phantom intent.
    assert journal.admission().reason == j.UNRESOLVED


@pytest.mark.parametrize('raw', [
    b'', b'{', b'{}', b'null', b'\xff', b'[1]', b'{"nonce":"' + NONCE.encode() + b'"}',
    valid_entry(extra='x'),
    valid_entry(revision=True),
    valid_entry(revision=-1),
    valid_entry(state='done'),
    valid_entry(nonce=SECOND),
    valid_entry(closed_by=j.CREATE_ABSENT),
    valid_entry(state=j.CLOSED),
    valid_entry(state=j.BOUND),
    valid_entry(container_id='not-hex'),
    valid_entry(deadline_ns='soon'),
])
def test_corrupt_entry_is_a_fixed_diagnostic(root, journal, raw):
    path = entry_path(root)
    path.write_bytes(raw)
    path.chmod(0o600)
    with pytest.raises(j.JournalError) as error:
        journal.load(NONCE)
    assert str(error.value) == 'journal_invalid'
    assert error.value.__context__ is None
    admission = journal.admission()
    assert (admission.may_open_session, admission.reason) == (False, 'journal_invalid')


def test_missing_entry_is_a_fixed_diagnostic(root, journal):
    with pytest.raises(j.JournalError) as error:
        journal.load(SECOND)
    assert str(error.value) == 'journal_invalid'
    assert error.value.__context__ is None
    assert str(root) not in str(error.value)


def test_result_maps_every_state_to_a_fixed_status(root, journal, clock):
    entry = journal.record_intent(NONCE)
    assert journal.result(NONCE).as_dict() == {'status': 'isolation_unknown'}
    entry = journal.transition(NONCE, entry.revision, j.CREATE_INFLIGHT)
    assert journal.result(NONCE).as_dict() == {'status': 'isolation_unknown'}
    journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.CREATE_ABSENT)
    # A create_absent close proves no object existed, which is doubt about the
    # controller, not an observed exit.
    assert journal.result(NONCE).as_dict() == {'status': 'isolation_unknown'}


def test_observe_also_needs_the_current_revision(root, journal):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    with pytest.raises(j.RevisionConflict) as error:
        journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert str(error.value) == 'revision_conflict'
    assert journal.load(NONCE).state == j.BOUND


def test_closed_intent_is_never_changed_by_later_observations(root, journal):
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    entry = journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.CREATE_ABSENT)
    observed, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert observed == entry
    assert (plan.action, plan.container_id) == ('none', None)
    assert journal.admission().may_open_session is True


def test_repr_does_not_expose_the_journal_path(root, journal):
    journal.record_intent(NONCE)
    entry = journal.load(NONCE)
    assert str(root) not in repr(entry)


def test_create_absent_cannot_close_an_intent_that_bound_an_object(root, journal):
    """`create_absent` means no object exists. A record naming one contradicts it."""
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    entry, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert (plan.action, plan.container_id) == ('stop', CONTAINER)
    entry, plan = journal.observe(NONCE, entry.revision, (), trusted=False)
    assert entry.state == j.UNRESOLVED
    with pytest.raises(j.TransitionRejected):
        journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.CREATE_ABSENT)
    assert journal.load(NONCE).state == j.UNRESOLVED
    assert journal.admission().may_open_session is False
    # Only a verified reclaim may end it, so the object keeps its reclaim path:
    # a trusted observation re-binds the exact id, then stop, then reclaim.
    entry, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert (plan.action, plan.container_id) == ('stop', CONTAINER)
    entry = journal.transition(NONCE, entry.revision, j.STOPPING)
    entry = journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.RECLAIM_VERIFIED)
    assert journal.result(NONCE).as_dict() == {'status': 'isolation_terminated'}


def test_record_claiming_no_object_while_holding_one_is_rejected(root):
    entry_path(root).write_bytes(valid_entry(state=j.CLOSED, revision=4, container_id=CONTAINER,
                                             closed_by=j.CREATE_ABSENT))
    entry_path(root).chmod(0o600)
    with pytest.raises(j.JournalError):
        j.IntentJournal(root).load(NONCE)


def test_observe_requires_an_explicit_trust_declaration(root, journal):
    """Silence must not be read as proof of a continuous view."""
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    with pytest.raises(TypeError):
        journal.observe(NONCE, entry.revision, (CONTAINER,))
    assert journal.load(NONCE).state == j.CREATE_INFLIGHT


def test_crash_between_link_and_unlink_stays_readable_and_heals(root, journal):
    journal.record_intent(NONCE)
    temporary = root / ('.' + NONCE + '.tmp')
    os.link(entry_path(root), temporary)  # the link(2) -> unlink(2) crash window
    assert journal.load(NONCE).state == j.INTENT_PENDING
    assert journal.admission().may_open_session is False
    entry = journal.transition(NONCE, 0, j.CREATE_INFLIGHT)
    assert entry.state == j.CREATE_INFLIGHT
    assert not temporary.exists()


def test_delivery_gate_allows_only_a_currently_bound_intent(root, journal):
    entry = journal.record_intent(NONCE)
    assert journal.delivery_gate(NONCE).allowed is False
    entry = journal.transition(NONCE, entry.revision, j.CREATE_INFLIGHT)
    assert journal.delivery_gate(NONCE).allowed is False
    entry, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    gate = journal.delivery_gate(NONCE)
    assert (gate.allowed, gate.reason) == (True, 'bound')
    entry = journal.transition(NONCE, entry.revision, j.STOPPING)
    assert journal.delivery_gate(NONCE).allowed is False
    entry = journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.RECLAIM_VERIFIED)
    assert journal.delivery_gate(NONCE).allowed is False


def test_delivery_gate_denies_after_doubt_even_when_rebound(root, journal):
    """A recovered object is a reclaim target, not a delivery target."""
    entry = drive(journal, (j.INTENT_PENDING, j.CREATE_INFLIGHT))
    entry, plan = journal.observe(NONCE, entry.revision, (), trusted=False)
    assert entry.state == j.UNRESOLVED
    entry, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert entry.state == j.BOUND
    gate = journal.delivery_gate(NONCE)
    assert (gate.allowed, gate.reason) == (False, 'reclaimed_after_doubt')


def test_delivery_gate_reports_unknown_nonce_as_blocked(root, journal):
    journal.record_intent(NONCE)
    gate = journal.delivery_gate(SECOND)
    assert (gate.allowed, gate.reason) == (False, 'unknown_intent')


def test_result_reports_unknown_instead_of_raising_on_corruption(root, journal):
    entry_path(root).write_bytes(b'{not json')
    entry_path(root).chmod(0o600)
    assert journal.result(NONCE).as_dict() == {'status': 'isolation_unknown'}


def test_result_never_claims_an_observed_process_exit(root, journal):
    """Nothing was created, so no exit happened that I2 could have observed."""
    entry = journal.record_intent(NONCE)
    journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.CREATE_ABSENT)
    assert journal.result(NONCE).as_dict() == {'status': 'isolation_unknown'}


def test_relative_journal_root_is_rejected(clock):
    with pytest.raises(j.JournalError):
        j.IntentJournal('relative/journal', clock=clock)


def test_lock_file_permissions_are_checked(root, journal):
    entry = journal.record_intent(NONCE)
    (root / '.lock').chmod(0o666)
    with pytest.raises(j.JournalError):
        journal.transition(NONCE, entry.revision, j.CREATE_INFLIGHT)


def test_temporary_file_cannot_be_a_preplanted_link(root, journal):
    victim = root.parent / 'victim'
    victim.write_bytes(b'do not overwrite')
    os.link(victim, root / ('.' + NONCE + '.tmp'))
    with pytest.raises(j.JournalError):
        journal.record_intent(NONCE)
    assert victim.read_bytes() == b'do not overwrite'


def test_duplicate_json_key_in_a_record_is_rejected(root):
    raw = valid_entry()
    # Duplicate a key with the SAME value: the record stays semantically valid,
    # so only duplicate-key detection can reject it.
    duplicated = raw.replace(b'"deadline_ns":1', b'"deadline_ns":1,"deadline_ns":1')
    assert duplicated != raw and duplicated.count(b'"deadline_ns"') == 2
    entry_path(root).write_bytes(duplicated)
    entry_path(root).chmod(0o600)
    with pytest.raises(j.JournalError):
        j.IntentJournal(root).load(NONCE)


def test_unexpected_object_while_still_pending_becomes_doubt(root, journal):
    entry = journal.record_intent(NONCE)
    observed, plan = journal.observe(NONCE, entry.revision, (CONTAINER,), trusted=True)
    assert observed.state == j.UNRESOLVED
    assert (plan.action, plan.container_id) == ('none', None)
    assert journal.admission().may_open_session is False
