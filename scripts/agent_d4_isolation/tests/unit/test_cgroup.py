"""Behavioural tests for journal-bound cgroup termination (fake backend only).

The fake backend counts calls and can refuse, raise or lie. These tests prove the
guard never turns a stale or unreadable journal into a kill, and never lets a
caller substitute a different target. They prove nothing about a real cgroup.
"""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    '_i3_helpers_cgroup', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
g = h.load('cgroup')
j = h.load('journal')

NONCE = 'a' * 64
CID = 'c' * 64
BOOT = 'feedface-cafe-beef-feed-facecafebeef'


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


class Clock:
    def __init__(self):
        self.value = 10 ** 12

    def __call__(self):
        return self.value


@pytest.fixture
def journal(tmp_path):
    root = tmp_path / 'journal'
    root.mkdir(mode=0o700)
    return j.IntentJournal(root, clock=Clock())


class Backend:
    """Fake trusted backend: verifies nothing, but records every attempt."""

    def __init__(self, result=None, *, error=None, token=b'object-specific'):
        self.result = result or g.TerminationResult(True, g.VERIFIED)
        self.error = error
        self.token = token
        self.calls = []

    def terminate(self, ref):
        self.calls.append(ref)
        if self.error:
            raise self.error
        return self.result

    def identity_token(self, ref):
        if self.error:
            raise self.error
        return self.token


def birth(**changes):
    value = {'device': 4, 'inode': 12345, 'boot_id': BOOT}
    value.update(changes)
    return g.KernelBirth(**value)


def bound(journal):
    entry = journal.record_intent(NONCE)
    entry = journal.transition(NONCE, entry.revision, j.CREATE_INFLIGHT)
    return journal.transition(NONCE, entry.revision, j.BOUND, container_id=CID)


def ref():
    return g.CgroupRef(NONCE, CID)


def test_terminate_calls_the_backend_once_for_a_bound_intent(journal):
    backend = Backend()
    entry = bound(journal)
    result = g.CgroupGuard(backend, journal).terminate(ref(), expected_revision=entry.revision)
    assert (result.terminated, result.reason) == (True, g.VERIFIED)
    assert len(backend.calls) == 1


@pytest.mark.parametrize('prepare', ['pending', 'closed', 'unresolved'])
def test_terminate_refuses_when_the_journal_is_not_live(journal, prepare):
    """Non-live records are refused; most reject on the missing id first.

    Only the matching-id `closed(reclaim)` case below isolates the state check.
    """
    backend = Backend()
    entry = journal.record_intent(NONCE)
    if prepare == 'closed':
        entry = journal.transition(NONCE, entry.revision, j.CLOSED, evidence=j.CREATE_ABSENT)
        entry = journal.record_intent('b' * 64)
        entry = journal.transition('b' * 64, entry.revision, j.CLOSED,
                                   evidence=j.CREATE_ABSENT)
    elif prepare == 'unresolved':
        entry = journal.transition(NONCE, entry.revision, j.UNRESOLVED)
    result = g.CgroupGuard(backend, journal).terminate(ref(), expected_revision=entry.revision)
    assert result.terminated is False
    assert backend.calls == []


def test_terminate_refuses_a_stale_revision(journal):
    backend = Backend()
    entry = bound(journal)
    result = g.CgroupGuard(backend, journal).terminate(ref(), expected_revision=entry.revision + 1)
    assert (result.terminated, result.reason) == (False, g.UNKNOWN)
    assert backend.calls == []


def test_terminate_refuses_a_different_container_id(journal):
    backend = Backend()
    entry = bound(journal)
    result = g.CgroupGuard(backend, journal).terminate(
        g.CgroupRef(NONCE, 'd' * 64), expected_revision=entry.revision)
    assert result.terminated is False
    assert backend.calls == []


@pytest.mark.parametrize('outcome', [
    g.TerminationResult(False, g.OBJECT_REPLACED),
    g.TerminationResult(False, g.HANDLE_MISSING),
    g.TerminationResult(False, g.BIRTH_UNAVAILABLE),
])
def test_backend_refusals_are_propagated_unchanged(journal, outcome):
    entry = bound(journal)
    result = g.CgroupGuard(Backend(outcome), journal).terminate(
        ref(), expected_revision=entry.revision)
    assert (result.terminated, result.reason) == (False, outcome.reason)


@pytest.mark.parametrize('error', [OSError('gone'), RuntimeError('bug'), ValueError('x')])
def test_backend_exception_is_unknown_and_never_a_kill(journal, error):
    entry = bound(journal)
    result = g.CgroupGuard(Backend(error=error), journal).terminate(
        ref(), expected_revision=entry.revision)
    assert (result.terminated, result.reason) == (False, g.UNKNOWN)


def test_backend_returning_a_foreign_type_is_unknown(journal):
    class Bad(Backend):
        def terminate(self, ref):
            return {'terminated': True}

    entry = bound(journal)
    result = g.CgroupGuard(Bad(), journal).terminate(ref(), expected_revision=entry.revision)
    assert (result.terminated, result.reason) == (False, g.UNKNOWN)


def test_unreadable_journal_never_calls_the_backend():
    class Broken:
        def load(self, nonce):
            raise RuntimeError('storage gone')

    backend = Backend()
    result = g.CgroupGuard(backend, Broken()).terminate(ref(), expected_revision=0)
    assert result.terminated is False
    assert backend.calls == []


def test_guard_constructor_requires_a_real_backend_and_journal(journal):
    with pytest.raises(ValueError):
        g.CgroupGuard(object(), journal)            # backend has no terminate
    with pytest.raises(ValueError):
        g.CgroupGuard(Backend(), object())          # journal has no load


def test_terminate_refuses_a_closed_reclaim_entry(journal):
    """container_id matches here, so only the state check can refuse it."""
    backend = Backend()
    entry = bound(journal)
    entry = journal.transition(NONCE, entry.revision, j.STOPPING)
    entry = journal.transition(NONCE, entry.revision, j.CLOSED,
                               evidence=j.RECLAIM_VERIFIED)
    result = g.CgroupGuard(backend, journal).terminate(ref(), expected_revision=entry.revision)
    assert (result.terminated, result.reason) == (False, g.UNKNOWN)
    assert backend.calls == []


def test_identity_token_needs_a_live_journal_entry(journal):
    backend = Backend(token=b'cap')
    guard = g.CgroupGuard(backend, journal)
    # Never recorded: no token, however willing the backend is.
    assert guard.identity_token(ref()) is None
    entry = bound(journal)
    assert guard.identity_token(ref()) == b'cap'
    journal.transition(NONCE, entry.revision, j.STOPPING)
    assert guard.identity_token(ref()) == b'cap'
    journal.transition(NONCE, entry.revision + 1, j.UNRESOLVED)
    assert guard.identity_token(ref()) is None


# -- KernelObject bridge -------------------------------------------------

def test_boot_id_alone_is_not_a_continuity_token():
    """Two objects in one boot would otherwise share the token."""
    with pytest.raises(ValueError):
        birth().to_kernel_object(None)
    with pytest.raises(ValueError):
        birth().to_kernel_object(b'')


def test_object_specific_token_distinguishes_equal_birth_facts():
    """Same device/inode/boot, different live capability -> different object."""
    first = birth().to_kernel_object(b'handle-A')
    second = birth().to_kernel_object(b'handle-B')
    assert first != second
    assert first.continuity_token != second.continuity_token


def test_token_from_the_live_backend_is_used_verbatim(journal):
    entry = bound(journal)
    guard = g.CgroupGuard(Backend(token=b'cap-7'), journal)
    token = guard.identity_token(ref())
    assert token == b'cap-7'
    assert birth().to_kernel_object(token).continuity_token == b'cap-7'


def test_identity_token_is_dropped_when_the_backend_fails(journal):
    entry = bound(journal)
    guard = g.CgroupGuard(Backend(error=OSError('gone')), journal)
    assert guard.identity_token(ref()) is None


@pytest.mark.parametrize('bad', ['deadbeef', '0' * 32, 'not-a-uuid', ''])
def test_short_or_malformed_boot_ids_are_rejected(bad):
    with pytest.raises(ValueError):
        birth(boot_id=bad)


def test_reference_and_result_shapes_are_validated():
    with pytest.raises(ValueError):
        g.CgroupRef('short', CID)
    with pytest.raises(ValueError):
        g.CgroupRef(NONCE, 'short')
    with pytest.raises(ValueError):
        g.TerminationResult(True, g.OBJECT_REPLACED)     # must be consistent
    with pytest.raises(ValueError):
        g.TerminationResult(False, g.VERIFIED)
