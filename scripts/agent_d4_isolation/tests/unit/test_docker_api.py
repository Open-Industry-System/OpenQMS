"""Behavioural tests for the journal-bound Docker surface (fake transport only).

Every test uses a real `IntentJournal` on a temporary directory, so the
authorisation checks exercised here are the real file-backed ones. The transport
is fake and counts payloads: "zero sends" means the transport was never called.
"""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    '_i3_helpers_docker', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
d = h.load('docker_api')
j = h.load('journal')

NONCE = 'a' * 64
CID = 'c' * 64
OTHER = 'd' * 64
DIGEST = 'sha256:' + 'e' * 64


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


class Clock:
    """Monotonic ns clock; tests advance it explicitly."""

    def __init__(self):
        self.value = 10 ** 12

    def __call__(self):
        return self.value


class Transport:
    def __init__(self, reply=None, *, fail=None):
        self.reply = reply
        self.fail = fail
        self.payloads = []

    def exchange(self, payload, *, deadline_ns, limit):
        self.payloads.append(payload)
        if self.fail == 'timeout':
            raise TimeoutError()
        if self.fail == 'oserror':
            raise OSError('connection reset')
        if self.fail == 'runtime':
            raise RuntimeError('bug in the adapter')
        return self.reply


def wire(**fields):
    return json.dumps(fields).encode()


@pytest.fixture
def journal(tmp_path):
    root = tmp_path / 'journal'
    root.mkdir(mode=0o700)
    return j.IntentJournal(root, clock=Clock())


def api(transport, journal, clock=None):
    return d.DockerApi(transport, DIGEST, journal=journal, clock=clock or Clock(),
                       op_deadline_ns=10 * 10 ** 9, response_limit=4096)


def started(journal):
    """Register one intent and move it to create_inflight."""
    entry = journal.record_intent(NONCE)
    return journal.transition(NONCE, entry.revision, j.CREATE_INFLIGHT)


def bound(journal):
    entry = started(journal)
    entry = journal.transition(NONCE, entry.revision, j.BOUND, container_id=CID)
    return entry


def closed_reclaim(journal):
    entry = bound(journal)
    entry = journal.transition(NONCE, entry.revision, j.STOPPING)
    return journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.RECLAIM_VERIFIED)


# -- create -------------------------------------------------------------

def test_create_persists_inflight_before_the_request(journal):
    transport = Transport(wire(created=True, container_id=CID, nonce=NONCE))
    entry = journal.record_intent(NONCE)
    outcome = api(transport, journal).create(NONCE, expected_revision=entry.revision)
    assert (outcome.kind, outcome.container_id) == ('created', CID)
    assert len(transport.payloads) == 1
    # The record was moved to create_inflight before the payload left.
    assert journal.load(NONCE).state == j.CREATE_INFLIGHT


def test_create_refuses_when_the_journal_write_fails(journal, monkeypatch):
    transport = Transport(wire(created=True, container_id=CID, nonce=NONCE))
    entry = journal.record_intent(NONCE)

    def boom(*args, **kwargs):
        raise j.JournalError()

    monkeypatch.setattr(journal, 'transition', boom)
    outcome = api(transport, journal).create(NONCE, expected_revision=entry.revision)
    assert outcome.kind == 'ambiguous'
    assert transport.payloads == []          # nothing was sent
    assert journal.load(NONCE).state == j.INTENT_PENDING


def test_create_refuses_a_stale_revision_without_sending(journal):
    transport = Transport(wire(created=True, container_id=CID, nonce=NONCE))
    entry = journal.record_intent(NONCE)
    outcome = api(transport, journal).create(NONCE, expected_revision=entry.revision + 5)
    assert outcome.kind == 'ambiguous'
    assert transport.payloads == []


@pytest.mark.parametrize('reply', [
    wire(created=False, nonce=NONCE),                 # bare negative
    wire(created=False, status='error', nonce=NONCE),
    wire(created=True),                               # no id
    wire(created=True, container_id='short', nonce=NONCE),
    wire(status='accepted', nonce=NONCE),
    wire(created=True, container_id=CID),             # no nonce echo
    wire(created=True, container_id=CID, nonce=OTHER),
    b'{}',
    b'not json',
])
def test_create_never_reports_absence_and_marks_doubt(journal, reply):
    transport = Transport(reply)
    entry = journal.record_intent(NONCE)
    outcome = api(transport, journal).create(NONCE, expected_revision=entry.revision)
    assert (outcome.kind, outcome.container_id) == ('ambiguous', None)
    record = journal.load(NONCE)
    assert record.state == j.UNRESOLVED and record.doubted is True
    # Doubt means the next session is refused and the secret never delivered.
    assert journal.admission().may_open_session is False
    assert journal.delivery_gate(NONCE).allowed is False


@pytest.mark.parametrize('failure', ['timeout', 'oserror', 'runtime'])
def test_create_transport_failure_leaves_the_intent_unresolved(journal, failure):
    transport = Transport(b'', fail=failure)
    entry = journal.record_intent(NONCE)
    outcome = api(transport, journal).create(NONCE, expected_revision=entry.revision)
    assert outcome.kind == 'ambiguous'
    assert journal.load(NONCE).state == j.UNRESOLVED


def test_late_success_after_timeout_is_never_delivered(journal):
    """The object may exist; the journal must stay closed to new delivery."""
    transport = Transport(b'', fail='timeout')
    entry = journal.record_intent(NONCE)
    api(transport, journal).create(NONCE, expected_revision=entry.revision)
    record = journal.load(NONCE)
    # A later trusted observation may bind the late object, but never deliver.
    record, plan = journal.observe(NONCE, record.revision, (CID,), trusted=True)
    assert plan.action == 'stop'
    assert journal.delivery_gate(NONCE).reason == 'reclaimed_after_doubt'


def test_oversized_reply_is_reported_honestly(journal):
    big = json.dumps({'created': False, 'nonce': NONCE, 'pad': 'x' * 5000}).encode()
    entry = journal.record_intent(NONCE)
    assert api(Transport(big), journal).create(NONCE, expected_revision=entry.revision).reason \
        == d.RESPONSE_TOO_LARGE


def test_late_reply_is_reported_honestly(tmp_path):
    clock = Clock()

    class Late(Transport):
        def exchange(self, payload, *, deadline_ns, limit):
            reply = super().exchange(payload, deadline_ns=deadline_ns, limit=limit)
            clock.value = deadline_ns + 1      # the answer landed past the deadline
            return reply

    root = tmp_path / 'late'
    root.mkdir(mode=0o700)
    journal = j.IntentJournal(root, clock=clock)
    nonce = 'b' * 64
    entry = journal.record_intent(nonce)
    outcome = api(Late(wire(created=True, container_id=CID, nonce=nonce)), journal,
                  clock).create(nonce, expected_revision=entry.revision)
    assert outcome.reason == d.DEADLINE_EXCEEDED


# -- delete -------------------------------------------------------------

@pytest.mark.parametrize('prepare', ['bound', 'stopping', 'create_absent', 'unresolved'])
def test_delete_is_refused_unless_the_intent_closed_as_reclaimed(journal, prepare):
    """Every non-reclaim state refuses, and nothing is sent.

    The `create_absent` and `unresolved` cases are over-determined: neither
    record names an object, so the id check rejects before the state/evidence
    check can. That is defence in depth, not proof either check fires alone.
    `bound`/`stopping` isolate the state check, and the stub-journal test below
    isolates the `closed_by` evidence check.
    """
    transport = Transport(wire(container_id=CID, deleted=True))
    if prepare == 'bound':
        entry = bound(journal)
    elif prepare == 'stopping':
        entry = journal.transition(NONCE, bound(journal).revision, j.STOPPING)
    elif prepare == 'create_absent':
        entry = journal.record_intent(NONCE)
        entry = journal.transition(NONCE, entry.revision, j.CLOSED,
                                   evidence=j.CREATE_ABSENT)
    else:
        entry = journal.transition(NONCE, started(journal).revision, j.UNRESOLVED)
    locator = d.JournalLocator(NONCE, entry.revision, CID)
    with pytest.raises(d.DockerError) as error:
        api(transport, journal).delete(locator)
    assert str(error.value) == d.JOURNAL_STATE
    assert transport.payloads == []


def test_delete_is_sent_for_a_reclaim_verified_close(journal):
    transport = Transport(wire(container_id=CID, deleted=True))
    entry = closed_reclaim(journal)
    locator = d.JournalLocator(NONCE, entry.revision, CID)
    outcome = api(transport, journal).delete(locator)
    assert outcome.done is True
    assert len(transport.payloads) == 1
    assert json.loads(transport.payloads[0])['authorized_delete'] is True


@pytest.mark.parametrize('field,code', [
    ('nonce', d.JOURNAL_UNAVAILABLE),      # no record under that nonce
    ('container_id', d.JOURNAL_STATE),     # record names another object
    ('revision', d.JOURNAL_STATE),         # stale revision
])
def test_delete_locator_must_match_the_record_exactly(journal, field, code):
    transport = Transport(wire(container_id=CID, deleted=True))
    entry = closed_reclaim(journal)
    values = {'nonce': NONCE, 'container_id': CID, 'revision': entry.revision}
    values[field] = {'nonce': 'b' * 64, 'container_id': OTHER, 'revision': entry.revision + 1}[field]
    locator = d.JournalLocator(**values)
    with pytest.raises(d.DockerError) as error:
        api(transport, journal).delete(locator)
    assert str(error.value) == code        # the intended check, not a stray one
    assert transport.payloads == []


def test_direct_call_to_the_send_seam_cannot_skip_the_journal(journal):
    transport = Transport(wire(container_id=CID, deleted=True))
    entry = bound(journal)
    locator = d.JournalLocator(NONCE, entry.revision, CID)
    request = d.DockerRequest('delete', container_id=CID, locator=locator)
    with pytest.raises(d.DockerError):
        api(transport, journal)._call(request)
    assert transport.payloads == []


def test_unreadable_journal_sends_nothing_and_never_authorises(tmp_path):
    transport = Transport(wire(container_id=CID, deleted=True))

    class Broken:
        def load(self, nonce):
            raise RuntimeError('storage gone')

        def transition(self, *args, **kwargs):
            raise RuntimeError('storage gone')

    locator = d.JournalLocator(NONCE, 3, CID)
    with pytest.raises(d.DockerError) as error:
        api(transport, Broken()).delete(locator)
    assert str(error.value) == d.JOURNAL_UNAVAILABLE
    assert transport.payloads == []


# -- other state-changing operations ------------------------------------

@pytest.mark.parametrize('op', ['start', 'attach', 'stop'])
def test_raw_operations_refuse_an_unregistered_container(journal, op):
    transport = Transport(wire(container_id=CID, stopped=True, started=True))
    locator = d.JournalLocator(NONCE, 0, CID)      # nothing recorded for this nonce
    with pytest.raises(d.DockerError):
        getattr(api(transport, journal), op)(locator)
    assert transport.payloads == []


def test_attach_requires_a_bound_intent(journal):
    transport = Transport(b'{}')
    entry = started(journal)
    with pytest.raises(d.DockerError):
        api(transport, journal).attach(d.JournalLocator(NONCE, entry.revision, CID))
    assert transport.payloads == []


def test_attach_returns_an_opaque_channel_and_writes_nothing(journal):
    transport = Transport(wire(container_id=CID, attached=True))
    entry = bound(journal)
    channel = api(transport, journal).attach(d.JournalLocator(NONCE, entry.revision, CID))
    assert type(channel) is d.AttachChannel
    assert channel.container_id == CID
    assert b'secret' not in transport.payloads[0]


def test_inspect_grants_no_authorisation(journal):
    transport = Transport(wire(container_id=CID, exists=True, running=True))
    entry = bound(journal)
    assert api(transport, journal).inspect(CID).exists is True
    # The same id cannot then be deleted without a reclaim-verified close.
    with pytest.raises(d.DockerError):
        api(transport, journal).delete(d.JournalLocator(NONCE, entry.revision, CID))
    assert len(transport.payloads) == 1     # only the inspect left


def test_inspect_rejects_any_extra_field(journal):
    for reply in (wire(container_id=CID, exists=False, running=False, error='timeout'),
                  wire(container_id=OTHER, exists=True, running=False)):
        with pytest.raises(d.DockerError):
            api(Transport(reply), journal).inspect(CID)


def test_collect_identity_requires_the_fixed_field_set(journal):
    good = dict(container_id=CID, daemon_instance='boot:1234:starttime:99',
                image_id=DIGEST, netns_inode=4026531840, nonce=NONCE,
                uid_map_line='2001 2001 1', cgroup_path='/system.slice/x.scope')
    entry = bound(journal)
    locator = d.JournalLocator(NONCE, entry.revision, CID)
    facts = api(Transport(wire(**good)), journal).collect_identity(locator)
    assert facts.daemon_instance.startswith('boot:')
    broken = dict(good)
    broken.pop('netns_inode')
    with pytest.raises(d.DockerError):
        api(Transport(wire(**broken)), journal).collect_identity(locator)


def test_start_requires_a_bound_intent(journal):
    transport = Transport(wire(container_id=CID, started=True))
    entry = started(journal)
    with pytest.raises(d.DockerError):
        api(transport, journal).start(d.JournalLocator(NONCE, entry.revision, CID))
    assert transport.payloads == []
    # Same intent, advanced to bound: now the id exists and a start is allowed.
    entry = journal.transition(NONCE, entry.revision, j.BOUND, container_id=CID)
    outcome = api(transport, journal).start(d.JournalLocator(NONCE, entry.revision, CID))
    assert outcome.done is True


def test_direct_create_call_cannot_skip_the_inflight_record(journal):
    """The old boolean flag let any caller send a create the journal never saw."""
    transport = Transport(wire(created=True, container_id=CID, nonce=NONCE))
    journal.record_intent(NONCE)                    # still intent_pending
    request = d.DockerRequest('create', nonce=NONCE)
    with pytest.raises(d.DockerError):
        api(transport, journal)._call(request, expected_revision=1)
    with pytest.raises(TypeError):
        api(transport, journal)._call(request, create_authorized=True)
    assert transport.payloads == []


class _SpoofedOp(str):
    """Compares as 'inspect', serialises as the real write operation."""

    def __hash__(self):
        return hash('inspect')

    def __eq__(self, other):
        return other == 'inspect'

    def __ne__(self, other):
        return not self.__eq__(other)


def test_operation_subclass_cannot_smuggle_a_write_past_the_read_only_branch(journal):
    """The dangerous shape: a bare inspect request rewritten to a write op.

    It carries no locator, so the read-only branch really is taken; only the
    exact-type check stops the payload from serialising as `start`.
    """
    transport = Transport(wire(container_id=CID, started=True))
    bound(journal)
    request = d.DockerRequest('inspect', container_id=CID)
    object.__setattr__(request, 'op', _SpoofedOp('start'))
    with pytest.raises(d.DockerError) as error:
        api(transport, journal)._call(request)
    assert str(error.value) == d.REQUEST_REJECTED
    assert transport.payloads == []
    # Note: the constructor may still *accept* such a subclass (its membership
    # test can be spoofed); the guarantee that matters is that the send seam
    # refuses to serialise it, which is what this test pins.


def _spoofed_id(actual, claimed):
    """A str subclass equal to `claimed` but serialising as `actual`."""

    class _SpoofedId(str):
        def __hash__(self):
            return hash(claimed)

        def __eq__(self, other):
            return other == claimed

        def __ne__(self, other):
            return not self.__eq__(other)

    return _SpoofedId(actual)


def test_id_subclass_cannot_redirect_an_authorised_delete(journal):
    transport = Transport(wire(container_id=OTHER, deleted=True))
    entry = closed_reclaim(journal)
    request = d.DockerRequest('delete', container_id=CID,
                              locator=d.JournalLocator(NONCE, entry.revision, CID))
    object.__setattr__(request, 'container_id', _spoofed_id(OTHER, CID))
    with pytest.raises(d.DockerError) as error:
        api(transport, journal)._call(request)
    assert str(error.value) == d.REQUEST_REJECTED
    assert transport.payloads == []
    with pytest.raises(d.DockerError):
        d.JournalLocator(NONCE, entry.revision, _spoofed_id(OTHER, CID))


def test_locator_nonce_and_id_must_be_exact_strings_at_the_seam(journal):
    """A str subclass must be rejected by the seam's own primitive check.

    `JournalLocator` also validates, so this constructs a valid one and then
    rewrites the field, which is exactly what the frozen-dataclass reflection
    path allows.
    """
    transport = Transport(wire(container_id=OTHER, deleted=True))
    entry = closed_reclaim(journal)
    for field, bad in (('container_id', _spoofed_id(OTHER, CID)),
                       ('nonce', _spoofed_id('b' * 64, NONCE))):
        request = d.DockerRequest('delete', container_id=CID,
                                  locator=d.JournalLocator(NONCE, entry.revision, CID))
        object.__setattr__(request.locator, field, bad)
        with pytest.raises(d.DockerError) as error:
            api(transport, journal)._call(request)
        assert str(error.value) == d.REQUEST_REJECTED
    assert transport.payloads == []


def test_direct_create_seam_cannot_replay_the_single_send(journal):
    transport = Transport(wire(created=True, container_id=CID, nonce=NONCE))
    entry = journal.record_intent(NONCE)
    api_obj = api(transport, journal)
    request = d.DockerRequest('create', nonce=NONCE)
    first = api_obj._call(request, expected_revision=entry.revision)
    assert first['created'] is True
    assert journal.load(NONCE).state == j.CREATE_INFLIGHT
    with pytest.raises(d.DockerError) as error:
        api_obj._call(request, expected_revision=entry.revision)
    assert str(error.value) == d.JOURNAL_STATE
    # Even with the *current* revision (which defeats the revision check), the
    # state check alone must still refuse a replay.
    current = journal.load(NONCE).revision
    with pytest.raises(d.DockerError) as error:
        api_obj._call(request, expected_revision=current)
    assert str(error.value) == d.JOURNAL_STATE
    assert len(transport.payloads) == 1              # exactly one send, ever


def test_payload_cannot_name_a_different_container_than_the_locator(journal):
    """`object.__setattr__` on a frozen request must not redirect the delete."""
    transport = Transport(wire(container_id=OTHER, deleted=True))
    entry = closed_reclaim(journal)
    request = d.DockerRequest('delete', container_id=CID,
                              locator=d.JournalLocator(NONCE, entry.revision, CID))
    object.__setattr__(request, 'container_id', OTHER)   # bypasses frozen-ness
    with pytest.raises(d.DockerError):
        api(transport, journal)._call(request)
    assert transport.payloads == []


def test_collect_identity_must_match_the_locator(journal):
    good = dict(container_id=OTHER, daemon_instance='boot:1:starttime:2',
                image_id=DIGEST, netns_inode=4026531840, nonce=NONCE,
                uid_map_line='2001 2001 1', cgroup_path='/system.slice/x.scope')
    bound(journal)
    with pytest.raises(d.DockerError):
        api(Transport(wire(**good)), journal).collect_identity(
            d.JournalLocator(NONCE, 2, CID))


def test_attach_requires_an_echoed_id_and_an_established_channel(journal):
    transport = Transport(b'{}')
    entry = bound(journal)
    locator = d.JournalLocator(NONCE, entry.revision, CID)
    with pytest.raises(d.DockerError):
        api(transport, journal).attach(locator)
    ok = api(Transport(wire(container_id=CID, attached=True)), journal).attach(locator)
    assert ok.container_id == CID


def test_start_refuses_a_stopping_intent(journal):
    transport = Transport(wire(container_id=CID, started=True))
    entry = journal.transition(NONCE, bound(journal).revision, j.STOPPING)
    with pytest.raises(d.DockerError):
        api(transport, journal).start(d.JournalLocator(NONCE, entry.revision, CID))
    assert transport.payloads == []


def test_stop_is_allowed_while_stopping(journal):
    transport = Transport(wire(container_id=CID, stopped=True))
    entry = journal.transition(NONCE, bound(journal).revision, j.STOPPING)
    assert api(transport, journal).stop(
        d.JournalLocator(NONCE, entry.revision, CID)).done is True
    assert len(transport.payloads) == 1


def test_stop_refuses_a_closed_intent(journal):
    """closed(reclaim) names the id, so only the state check can refuse a stop."""
    transport = Transport(wire(container_id=CID, stopped=True))
    entry = closed_reclaim(journal)
    with pytest.raises(d.DockerError) as error:
        api(transport, journal).stop(d.JournalLocator(NONCE, entry.revision, CID))
    assert str(error.value) == d.JOURNAL_STATE
    assert transport.payloads == []


def test_attach_refuses_a_stopping_intent(journal):
    transport = Transport(wire(container_id=CID, attached=True))
    entry = journal.transition(NONCE, bound(journal).revision, j.STOPPING)
    with pytest.raises(d.DockerError):
        api(transport, journal).attach(d.JournalLocator(NONCE, entry.revision, CID))
    assert transport.payloads == []


def test_delete_rejects_a_closed_record_without_reclaim_evidence(journal):
    """Defence in depth: a stub journal that names an id but closes otherwise."""
    class Entry:
        nonce = NONCE
        revision = 3
        container_id = CID
        state = j.CLOSED
        closed_by = j.CREATE_ABSENT        # impossible in a real record

    class Stub:
        def load(self, nonce):
            return Entry()

        def transition(self, *args, **kwargs):
            raise AssertionError('must not write')

    transport = Transport(wire(container_id=CID, deleted=True))
    with pytest.raises(d.DockerError) as error:
        api(transport, Stub()).delete(d.JournalLocator(NONCE, 3, CID))
    assert str(error.value) == d.JOURNAL_STATE
    assert transport.payloads == []


# -- payload shape -------------------------------------------------------

def test_payload_carries_only_the_reviewed_image(journal):
    transport = Transport(wire(created=True, container_id=CID, nonce=NONCE))
    entry = journal.record_intent(NONCE)
    api(transport, journal).create(NONCE, expected_revision=entry.revision)
    body = json.loads(transport.payloads[0])
    assert body['image_digest'] == DIGEST
    assert set(body) == {'op', 'image_digest', 'container_id', 'nonce', 'authorized_delete'}


def test_caller_cannot_declare_an_image_command_or_bare_delete(journal):
    with pytest.raises(TypeError):
        d.DockerRequest('create', nonce=NONCE, image='evil:latest')
    with pytest.raises(d.DockerError):
        d.DockerRequest('run', nonce=NONCE)
    with pytest.raises(d.DockerError):
        d.DockerRequest('delete', container_id=CID)          # no locator
    with pytest.raises(d.DockerError):
        d.DockerRequest('delete', container_id=CID, locator=d.JournalLocator(NONCE, 0, OTHER))


def test_list_by_nonce_requires_the_echoed_nonce(journal):
    assert api(Transport(wire(container_ids=[CID, CID], nonce=NONCE)),
               journal).list_by_nonce(NONCE) == (CID,)
    for reply in (wire(container_ids=[CID]),
                  wire(container_ids=['short'], nonce=NONCE),
                  wire(container_ids=[CID] * 9, nonce=NONCE)):
        with pytest.raises(d.DockerError):
            api(Transport(reply), journal).list_by_nonce(NONCE)


def test_constructor_rejects_unbounded_or_missing_settings(journal):
    for kwargs in ({'op_deadline_ns': 0}, {'op_deadline_ns': 11 * 10 ** 9},
                   {'response_limit': 0}, {'response_limit': 512 * 1024}):
        base = {'op_deadline_ns': 10 ** 9, 'response_limit': 4096}
        base.update(kwargs)
        with pytest.raises(d.DockerError):
            d.DockerApi(Transport(b''), DIGEST, journal=journal, clock=Clock(), **base)
    with pytest.raises(d.DockerError):
        d.DockerApi(Transport(b''), 'linux:latest', journal=journal, clock=Clock(),
                    op_deadline_ns=10 ** 9, response_limit=4096)
    with pytest.raises(d.DockerError):
        d.DockerApi(Transport(b''), DIGEST, journal=object(), clock=Clock(),
                    op_deadline_ns=10 ** 9, response_limit=4096)
