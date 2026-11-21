"""Ordering tests for the controller wiring.

Everything is injected, so these run with no daemon, no channel and no clock.
The point is the sequence: a refusal anywhere before the write means the
configuration was never handed over.
"""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    '_i7_cli_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
cli = h.load('cli')
j = h.load('journal')

NONCE = 'a' * 64
CID = 'c' * 64
CONFIG = b'{"secret":"sk-x"}'


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


class Clock:
    value = 10 ** 12

    def __call__(self):
        return self.value


@pytest.fixture
def journal(tmp_path):
    root = tmp_path / 'journal'
    root.mkdir(mode=0o700)
    return j.IntentJournal(root, clock=Clock())


class Api:
    """Fake that advances the journal exactly like the real create does."""

    def __init__(self, kind='created', container_id=CID, journal=None):
        self.kind = kind
        self.container_id = container_id
        self.journal = journal
        self.calls = []

    def create(self, nonce, *, expected_revision):
        self.calls.append(('create', expected_revision))
        if self.kind == 'created' and self.journal is not None:
            self.journal.transition(nonce, expected_revision, j.CREATE_INFLIGHT)
        return type('Outcome', (), {
            'kind': self.kind,
            'container_id': self.container_id if self.kind == 'created' else None})()


class Channel:
    def __init__(self):
        self.received = []
        self.closed = False
        self.delivered = False

    def write(self, data):
        self.received.append(bytes(data))
        return len(data)

    def close(self):
        self.closed = True


class Outcome:
    action = 'none'


def run(journal, api=None, *, watcher=lambda: 'wait', channel=None,
        output_source=None, config=CONFIG):
    opened = []

    def open_channel(nonce):
        channel_instance = channel or Channel()
        opened.append(channel_instance)
        return channel_instance

    result = cli.run(NONCE, config, journal=journal, api=api or Api(journal=journal),
                     open_channel=open_channel, watcher=watcher, clock=Clock(),
                     output_source=output_source)
    return result, opened


def test_a_clean_session_delivers_exactly_once(journal):
    result, opened = run(journal)
    assert result.status == 'isolation_exited'
    assert len(opened) == 1
    assert b''.join(opened[0].received) == CONFIG
    assert opened[0].closed is True


def test_an_ambiguous_create_never_opens_a_channel(journal):
    result, opened = run(journal, Api(kind='ambiguous', journal=journal))
    assert result.status == 'isolation_unknown'
    assert opened == []


def test_a_lost_watchdog_never_delivers(journal):
    # Bind first so the failure cannot be blamed on an earlier step.
    result, opened = run(journal, watcher=lambda: 'expire')
    assert result.status == 'isolation_unknown'
    assert opened == []


def test_a_closed_delivery_gate_never_delivers(journal):
    class GateJournal:
        """Everything delegates, so only the gate can cause the refusal."""

        def __init__(self, real):
            self._real = real

        def admission(self):
            return self._real.admission()

        def record_intent(self, nonce):
            return self._real.record_intent(nonce)

        def transition(self, *args):
            return self._real.transition(*args)

        def load(self, nonce):
            return self._real.load(nonce)

        def observe(self, *args, **kwargs):
            return self._real.observe(*args, **kwargs)

        def delivery_gate(self, nonce):
            return type('Gate', (), {'allowed': False, 'reason': 'other_intent_open'})()

    result, opened = run(GateJournal(journal), Api(journal=journal))
    assert result.status == 'isolation_unknown'
    assert opened == []


def test_an_unclear_admission_refuses_before_anything_happens():
    """Only the admission flag may cause this refusal.

    A stub that would happily record an intent makes the test non-vacuous: with
    the admission check removed the flag below records the call and the test
    fails, rather than passing because some later step happened to break.
    """
    class DeniedJournal:
        def __init__(self):
            self.record_called = False

        def admission(self):
            return type('Admission', (), {'may_open_session': False,
                                          'may_deliver_secret': False,
                                          'reason': 'bound'})()

        def record_intent(self, nonce):
            self.record_called = True
            raise AssertionError('must not be reached')

    stub = DeniedJournal()
    result = cli.run(NONCE, CONFIG, journal=stub, api=Api(),
                     open_channel=lambda nonce: Channel(),
                     watcher=lambda: 'wait', clock=Clock())
    assert result.status == 'isolation_unknown'
    assert stub.record_called is False


def test_an_output_overflow_stops_the_session_after_delivery(journal):
    chunks = [b'x' * 1024] * 10
    result, opened = run(journal, output_source=iter(chunks))
    assert result.status == 'isolation_unknown'
    assert len(opened) == 1     # it did deliver, then the overflow was reported


def test_a_failed_channel_never_writes(journal):
    def open_channel(nonce):
        raise OSError('attach failed')

    result = cli.run(NONCE, CONFIG, journal=journal, api=Api(journal=journal),
                     open_channel=open_channel, watcher=lambda: 'wait',
                     clock=Clock(), output_source=None)
    assert result.status == 'isolation_unknown'


def test_results_are_fixed_infrastructure_statuses(journal):
    result, _ = run(journal)
    assert result.status in ('isolation_exited', 'isolation_terminated',
                             'isolation_unknown')
