"""Persistent create-intent journal: the only gate in front of a create request.

Scope: stdlib file I/O inside one owner-only directory plus an injected
monotonic clock. Nothing here contacts Docker, the network or a subprocess, and
nothing here proves that a container exists, was created or was reclaimed. The
journal records what a trusted caller observed and returns what the caller may
still do; the observations themselves (a trusted enumerator, cgroup checks) are
I3/I5/I7 work.

Four rules drive the module:

* An intent is written, fsynced and no-clobber-renamed into place BEFORE the
  create request is issued, and no failure path removes it afterwards.
* Every transition carries the revision it expects; a stale expectation is a
  conflict, never an overwrite.
* Callers never read state strings to decide security. `admission()` answers the
  global question and any non-`closed` intent denies a new session; delivery is
  per intent via `delivery_gate()`, which only a currently `bound` intent with no
  other open intent can pass.
* Empty enumerations, unanswered creates and deadlines are doubt, not absence:
  they can only move an intent to `unresolved`, never to `closed`.
"""
from contextlib import contextmanager
from dataclasses import dataclass, replace
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time

from .contracts import InfrastructureResult

INTENT_PENDING = 'intent_pending'
CREATE_INFLIGHT = 'create_inflight'
BOUND = 'bound'
STOPPING = 'stopping'
UNRESOLVED = 'unresolved'
CLOSED = 'closed'
STATES = frozenset((INTENT_PENDING, CREATE_INFLIGHT, BOUND, STOPPING, UNRESOLVED, CLOSED))

# Closing is centralised in `_CLOSING` below: these are the only two facts that
# may ever end an intent, and neither may be inferred from an enumeration.
CREATE_ABSENT = 'create_absent'        # trusted: no object exists and nothing is in flight
RECLAIM_VERIFIED = 'reclaim_verified'  # trusted: create converged and the target is gone
CLOSING_EVIDENCE = frozenset((CREATE_ABSENT, RECLAIM_VERIFIED))

ENTRY_LIMIT = 4096
# Design §8.3 prepare window. A proposed initial value, not a measured one.
DEFAULT_BUDGET_NS = 30 * 10 ** 9

_HEX64 = re.compile(r'[a-f0-9]{64}')
_ENTRY_FILE = re.compile(r'[a-f0-9]{64}\.json')
_LOCK_FILE = '.lock'
_KEYS = ('closed_by', 'container_id', 'deadline_ns', 'doubted', 'nonce', 'revision', 'state')

# The complete transition table. `closed` has no successor, so a closed intent
# can never be revived or changed by a later observation.
_TRANSITIONS = {
    INTENT_PENDING: frozenset((CREATE_INFLIGHT, UNRESOLVED, CLOSED)),
    CREATE_INFLIGHT: frozenset((BOUND, UNRESOLVED, CLOSED)),
    BOUND: frozenset((STOPPING, UNRESOLVED)),
    STOPPING: frozenset((CLOSED, UNRESOLVED)),
    UNRESOLVED: frozenset((BOUND, CLOSED)),
    CLOSED: frozenset(),
}
_CLOSING = {
    # A trusted "nothing was produced and nothing is in flight" fact may end an
    # intent that has not been verified reclaimed; a verified reclaim may only
    # end an intent that was first stopped.
    CREATE_ABSENT: frozenset((INTENT_PENDING, CREATE_INFLIGHT, UNRESOLVED)),
    RECLAIM_VERIFIED: frozenset((STOPPING,)),
}


class JournalError(ValueError):
    """Storage/corruption rejection with ONE fixed, content-free message.

    No path, nonce, container id or file fragment may appear in this text: it is
    an operator-facing diagnostic that may reach the I6 log chain.
    """
    code = 'journal_invalid'

    def __init__(self):
        super().__init__(self.code)


class JournalBusy(JournalError):
    """Another writer holds the journal lock. Nothing was read or changed."""
    code = 'journal_busy'


class SessionBlocked(JournalError):
    """A non-closed intent exists, so no further intent may be registered."""
    code = 'session_blocked'


class RevisionConflict(JournalError):
    """The expected revision is not the one on disk. Nothing was overwritten."""
    code = 'revision_conflict'


class TransitionRejected(JournalError):
    """The requested successor state, or the evidence offered for it, is illegal."""
    code = 'transition_rejected'


def _require(condition):
    if not condition:
        raise JournalError()


@dataclass(frozen=True, slots=True)
class IntentEntry:
    """One persisted intent. Immutable; every accepted change bumps `revision`."""
    nonce: str
    state: str
    revision: int
    deadline_ns: int
    container_id: str | None = None
    closed_by: str | None = None
    # Set once the intent was ever in doubt. A late object recovered after that
    # is a reclaim target, never a delivery target: its controller is gone.
    doubted: bool = False

    def __post_init__(self):
        _require(type(self.nonce) is str and _HEX64.fullmatch(self.nonce) is not None)
        _require(type(self.state) is str and self.state in STATES)
        # `type(x) is int` also rejects bool, which would otherwise pass as 0/1.
        _require(type(self.revision) is int and self.revision >= 0)
        _require(type(self.deadline_ns) is int)
        _require(type(self.doubted) is bool)
        _require(self.container_id is None
                 or (type(self.container_id) is str and _HEX64.fullmatch(self.container_id) is not None))
        _require(self.closed_by is None or self.closed_by in CLOSING_EVIDENCE)
        # `closed` exists only together with the evidence that allowed it, and no
        # other state may carry that evidence.
        _require((self.state == CLOSED) == (self.closed_by is not None))
        # `create_absent` means no object exists. A record that names one refutes
        # its own evidence, and closing would strand that object with no reclaim
        # path left (closed has no successor).
        _require(not (self.closed_by == CREATE_ABSENT and self.container_id is not None))
        # Symmetric rule: "verified reclaimed" cannot be claimed without the id.
        _require(not (self.closed_by == RECLAIM_VERIFIED and self.container_id is None))
        # Doubt is a fact about the intent's history, so an unresolved record
        # must say so; this also blocks a hand-written record from hiding it.
        _require(self.state != UNRESOLVED or self.doubted)
        _require(self.state not in (BOUND, STOPPING) or self.container_id is not None)


@dataclass(frozen=True, slots=True)
class ReclaimPlan:
    """What the caller may still touch: only ever one exact, currently bound id.

    `action == 'none'` means no object may be stopped on this intent's behalf.
    An ambiguous or unverifiable intent therefore cannot turn into a guess.
    """
    nonce: str
    container_id: str | None
    action: str

    def __post_init__(self):
        _require(self.action in ('stop', 'none'))
        _require(type(self.nonce) is str and _HEX64.fullmatch(self.nonce) is not None)
        _require((self.action == 'stop') == (self.container_id is not None))


@dataclass(frozen=True, slots=True)
class DeliveryGate:
    """Per-intent delivery conclusion; the caller must not infer it from state.

    `allowed` still requires I3 to confirm the bound identity, and I7 to send the
    configuration exactly once. This only answers "may this session talk about
    this intent at all right now".
    """
    allowed: bool
    reason: str

    def __post_init__(self):
        _require(type(self.allowed) is bool)
        _require(self.reason in frozenset(STATES)
                 | {'bound', 'unknown_intent', 'journal_invalid', 'other_intent_open',
                    'reclaimed_after_doubt'})


@dataclass(frozen=True, slots=True)
class Admission:
    """The explicit conclusion callers must use instead of reading state strings.

    Both flags are false whenever any intent is not `closed`, when the journal
    cannot be read, or when its directory is unsafe. Both are therefore a global
    all-clear signal: while a session is legitimately running (its intent is
    `bound`) they are false by construction, so they must never be read as a
    delivery licence. Per-intent delivery is `delivery_gate(nonce)`, and I7 adds
    the single stdin write on top of it.
    """
    may_open_session: bool
    may_deliver_secret: bool
    reason: str

    def __post_init__(self):
        _require(type(self.may_open_session) is bool and type(self.may_deliver_secret) is bool)
        _require(self.may_open_session or not self.may_deliver_secret)
        _require(self.reason in frozenset(STATES) | {'clear', 'journal_invalid'})


def _translate(call):
    """Run one storage operation, mapping every OS failure to ONE fixed message.

    The re-raise happens outside the handler, so the fixed diagnostic carries no
    chained OSError filename and no file fragment.
    """
    failed = False
    try:
        return call()
    except JournalError:
        raise
    except (OSError, ValueError, TypeError, RecursionError):
        failed = True
    _require(not failed)


def _dump(entry):
    raw = None
    try:
        raw = json.dumps({key: getattr(entry, key) for key in _KEYS},
                         sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    except (TypeError, ValueError):
        pass
    _require(raw is not None and len(raw) <= ENTRY_LIMIT)
    return raw


def _unique_pairs(items):
    """Reject duplicate keys; last-value-wins would let a record hide a field.

    Same strictness as I1's config parser: a duplicated key is corruption even
    when both occurrences agree.
    """
    result = {}
    for key, value in items:
        _require(key not in result)
        result[key] = value
    return result


def _parse(raw, nonce):
    """Strict read of one record. Any deviation is corruption, not a new state."""
    _require(type(raw) is bytes and len(raw) <= ENTRY_LIMIT)
    value = None
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError, RecursionError):
        pass
    _require(type(value) is dict and set(value) == set(_KEYS))
    # The record must belong to the name it was found under, so a copied or
    # renamed file cannot impersonate another intent.
    _require(value['nonce'] == nonce)
    return IntentEntry(**value)


def advance(entry, state, *, evidence=None, container_id=None):
    """Pure transition table: the only place that decides what may follow what."""
    _require(type(entry) is IntentEntry)
    if evidence is not None and type(evidence) is not str:
        raise TransitionRejected()
    if state not in _TRANSITIONS[entry.state]:
        raise TransitionRejected()
    if state == CLOSED:
        if entry.state not in _CLOSING.get(evidence, frozenset()):
            raise TransitionRejected()
        if evidence == CREATE_ABSENT and entry.container_id is not None:
            # The record already proves an object existed, so "nothing was
            # produced" cannot hold: keep the intent open for a real reclaim.
            raise TransitionRejected()
        return replace(entry, state=CLOSED, revision=entry.revision + 1, closed_by=evidence)
    if evidence is not None:
        # Evidence is meaningful only for closing; elsewhere it would be a
        # caller quietly smuggling a reason into an open intent.
        raise TransitionRejected()
    if state == BOUND:
        if type(container_id) is not str or _HEX64.fullmatch(container_id) is None:
            raise TransitionRejected()
        if entry.container_id is not None and entry.container_id != container_id:
            # Re-verifying the same object is allowed; re-pointing the intent at a
            # different one is not.
            raise TransitionRejected()
        return replace(entry, state=BOUND, revision=entry.revision + 1, container_id=container_id)
    if container_id is not None:
        raise TransitionRejected()
    if state == UNRESOLVED:
        # Doubt must be recorded by the transition itself, not only by
        # reconcile(): otherwise a caller could enter doubt through the public
        # transition and then rebind as if nothing had ever been doubted.
        return replace(entry, state=state, revision=entry.revision + 1, doubted=True)
    return replace(entry, state=state, revision=entry.revision + 1)


def _doubt(entry):
    """Record unexplained doubt without inventing evidence or dropping the intent."""
    if entry.state == UNRESOLVED:
        return entry          # the record invariant guarantees doubted is set
    return advance(entry, UNRESOLVED)


def reconcile(entry, matches, *, trusted, now_ns):
    """Fold one enumeration into the intent. Never guesses, never closes.

    `trusted=False` marks a view the caller cannot prove continuous (daemon
    restart, released object reference) and `matches` that are not exact full
    container ids are treated the same way: doubt, not absence.
    """
    _require(type(entry) is IntentEntry and type(trusted) is bool)
    _require(type(matches) is tuple and type(now_ns) is int)
    if entry.state == CLOSED:
        return entry
    verified = trusted and all(type(item) is str and _HEX64.fullmatch(item) is not None
                               for item in matches)
    if not verified:
        # Nothing can be bound or closed from a view we cannot trust. An intent
        # that never issued a create has nothing to doubt yet.
        return entry if entry.state == INTENT_PENDING else _doubt(entry)
    found = set(matches)
    if len(found) > 1:
        # Several objects answer to our nonce. Picking one, or deleting by label
        # or prefix, would be a guess: keep the intent open and block delivery.
        return _doubt(entry)
    if found:
        container_id = found.pop()
        if entry.state in (BOUND, STOPPING):
            return entry if entry.container_id == container_id else _doubt(entry)
        if entry.state == INTENT_PENDING:
            # No create was issued yet, so an object answering to this nonce is
            # unexplained: record doubt instead of binding or raising.
            return _doubt(entry)
        if entry.container_id is not None and entry.container_id != container_id:
            # Re-binding to a different object would be a guess; fold it into
            # doubt the same way the BOUND/STOPPING branch does.
            return _doubt(entry)
        return advance(entry, BOUND, container_id=container_id)
    # Zero matches: not evidence of absence, so it can never close anything. A
    # create that is still in flight when the budget expires is unknown, not
    # cancelled.
    if entry.state == CREATE_INFLIGHT and now_ns >= entry.deadline_ns:
        return _doubt(entry)
    return entry


def plan_for(entry):
    """Only a currently bound/stopping exact id may be stopped."""
    _require(type(entry) is IntentEntry)
    if entry.state in (BOUND, STOPPING) and entry.container_id is not None:
        return ReclaimPlan(entry.nonce, entry.container_id, 'stop')
    return ReclaimPlan(entry.nonce, None, 'none')


class IntentJournal:
    """One owner-only directory of intent records, written before any create."""

    def __init__(self, root, *, clock=time.monotonic_ns, budget_ns=DEFAULT_BUDGET_NS):
        supplied = None
        try:
            supplied = os.fspath(root)
        except TypeError:
            pass
        # A relative or '..'-bearing root would be resolved against the caller's
        # cwd; only an absolute, already-reviewed deployment path is accepted.
        _require(type(supplied) is str and supplied != '' and '\x00' not in supplied)
        _require('..' not in supplied.split('/'))
        # Absolute only: a relative journal root would land under the caller's
        # cwd, which no deployment review covers.
        _require(supplied.startswith('/'))
        _require(type(budget_ns) is int and budget_ns > 0)
        _require(callable(clock))
        self._absolute = Path(os.path.abspath(supplied))
        self._clock = clock
        self._budget_ns = budget_ns

    # -- directory pinning ------------------------------------------------
    @contextmanager
    def _dir(self):
        """Open the owner-only journal directory without following any symlink.

        Every later operation uses this descriptor, so a path swapped after the
        open cannot redirect the write. Parity with I1's private-config loader:
        the owner/0700 assertion covers the journal directory itself and the
        trusted-host premise is the same one I1 records.
        """
        parts = self._absolute.parts
        _require(len(parts) >= 3)
        directory_fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in parts[1:]:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            info = os.fstat(directory_fd)
            _require(stat.S_ISDIR(info.st_mode))
            _require(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid())
            yield directory_fd
        finally:
            os.close(directory_fd)

    @contextmanager
    def _locked(self, directory_fd):
        """Serialise read-modify-write so the revision check is real, not advisory."""
        fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600,
                     dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                     and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600)
            busy = False
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                busy = True     # another writer holds it: fail closed, change nothing
            if busy:
                raise JournalBusy()
            yield
        finally:
            os.close(fd)        # closing the descriptor releases the lock

    # -- one record -------------------------------------------------------
    def _read(self, directory_fd, nonce):
        fd = os.open(nonce + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode))
            _require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid()
                     and info.st_size <= ENTRY_LIMIT)
            # nlink == 2 is the crash window between link(2) and unlink(2); accept
            # it only when the extra name is this nonce's canonical temporary and
            # literally the same inode, so the intent stays readable and reconcilable.
            _require(info.st_nlink in (1, 2))
            if info.st_nlink == 2:
                _require(self._temporary_is_same_inode(directory_fd, nonce, info))
            chunks, remaining = [], ENTRY_LIMIT + 1
            while remaining > 0:
                chunk = os.read(fd, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(fd)
            _require((after.st_uid, after.st_mode, after.st_nlink, after.st_size)
                     == (info.st_uid, info.st_mode, info.st_nlink, info.st_size))
        finally:
            os.close(fd)
        raw = b''.join(chunks)
        _require(len(raw) <= ENTRY_LIMIT)
        return _parse(raw, nonce)

    def _temporary_is_same_inode(self, directory_fd, nonce, info):
        try:
            temporary = os.stat('.' + nonce + '.tmp', dir_fd=directory_fd,
                                follow_symlinks=False)
        except OSError:
            return False
        return ((temporary.st_dev, temporary.st_ino) == (info.st_dev, info.st_ino)
                and stat.S_ISREG(temporary.st_mode))

    def _heal(self, directory_fd, nonce):
        """Drop a temporary left by a crash between link(2) and unlink(2).

        Only this nonce's canonical temporary is removed, and only when it is the
        same inode as the record, under the writer lock.
        """
        try:
            record = os.stat(nonce + '.json', dir_fd=directory_fd, follow_symlinks=False)
            temporary = os.stat('.' + nonce + '.tmp', dir_fd=directory_fd,
                                follow_symlinks=False)
        except OSError:
            return
        if (record.st_nlink == 2 and stat.S_ISREG(temporary.st_mode)
                and (record.st_dev, record.st_ino) == (temporary.st_dev, temporary.st_ino)):
            try:
                os.unlink('.' + nonce + '.tmp', dir_fd=directory_fd)
            except OSError:
                pass

    def _entries(self, directory_fd):
        # Only canonical record names count; `.lock` and any leftover temporary
        # from a crash are ignored rather than parsed as intents.
        return [self._read(directory_fd, name[:-len('.json')])
                for name in sorted(os.listdir(directory_fd)) if _ENTRY_FILE.fullmatch(name)]

    def _write(self, directory_fd, entry, *, create):
        """Durably publish one record: fsync bytes, then make the name durable.

        A create uses link(2), which fails with EEXIST instead of replacing a
        record that already exists. rename(2) would silently clobber it, so a
        reused nonce or a racing writer could destroy the only evidence of an
        open intent.
        """
        name = entry.nonce + '.json'
        temporary = '.' + entry.nonce + '.tmp'
        raw = _dump(entry)
        try:
            # No O_TRUNC and no O_EXCL: the lock is held so the name is ours, and a
            # leftover temporary from a crash must not block maintenance forever.
            # Truncation happens only after the attribute checks, because O_TRUNC
            # would already have emptied a pre-planted hard link to another file.
            fd = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
            try:
                staging = os.fstat(fd)
                _require(stat.S_ISREG(staging.st_mode) and staging.st_uid == os.getuid()
                         and staging.st_nlink == 1
                         and stat.S_IMODE(staging.st_mode) == 0o600)
                os.ftruncate(fd, 0)
                view = memoryview(raw)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)        # the bytes exist before the name does
            finally:
                os.close(fd)
            if create:
                os.link(temporary, name, src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd, follow_symlinks=False)
            else:
                os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)  # the new name (and any rename) survives a crash
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except OSError:
                pass
            raise
        if create:
            # link(2) leaves the temporary behind; replace(2) already consumed it.
            os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)  # and so does the temporary's removal

    # -- public surface ---------------------------------------------------
    def record_intent(self, nonce):
        """Persist `intent_pending` for `nonce`. Call this BEFORE any create."""
        return _translate(lambda: self._record_intent(nonce))

    def _record_intent(self, nonce):
        _require(type(nonce) is str and _HEX64.fullmatch(nonce) is not None)
        with self._dir() as directory_fd, self._locked(directory_fd):
            # One live intent at a time: a new session may not start while any
            # earlier create is still unexplained.
            if [entry for entry in self._entries(directory_fd) if entry.state != CLOSED]:
                raise SessionBlocked()
            entry = IntentEntry(nonce=nonce, state=INTENT_PENDING, revision=0,
                                deadline_ns=self._clock() + self._budget_ns)
            self._write(directory_fd, entry, create=True)
        return entry

    def load(self, nonce):
        return _translate(lambda: self._load(nonce))

    def _load(self, nonce):
        _require(type(nonce) is str and _HEX64.fullmatch(nonce) is not None)
        with self._dir() as directory_fd:
            return self._read(directory_fd, nonce)

    def transition(self, nonce, expected_revision, state, *, evidence=None, container_id=None):
        """Move one intent, refusing to act on a revision other than the on-disk one."""
        return _translate(
            lambda: self._transition(nonce, expected_revision, state, evidence, container_id))

    def _transition(self, nonce, expected_revision, state, evidence, container_id):
        _require(type(nonce) is str and _HEX64.fullmatch(nonce) is not None)
        _require(type(expected_revision) is int and expected_revision >= 0)
        _require(type(state) is str and state in STATES)
        with self._dir() as directory_fd, self._locked(directory_fd):
            self._heal(directory_fd, nonce)
            entry = self._read(directory_fd, nonce)
            if entry.revision != expected_revision:
                raise RevisionConflict()
            if entry.state == UNRESOLVED and state == BOUND:
                # Doubt may only be cleared by a trusted observation, never by a
                # caller asserting an id: otherwise `transition` would silently
                # turn suspicion into a delivery licence and a stop authorisation.
                raise TransitionRejected()
            updated = advance(entry, state, evidence=evidence, container_id=container_id)
            self._write(directory_fd, updated, create=False)
        return updated

    def observe(self, nonce, expected_revision, matches=(), *, trusted):
        """Record what one enumeration saw and return the entry plus the allowed plan."""
        return _translate(lambda: self._observe(nonce, expected_revision, matches, trusted))

    def _observe(self, nonce, expected_revision, matches, trusted):
        _require(type(nonce) is str and _HEX64.fullmatch(nonce) is not None)
        _require(type(expected_revision) is int and expected_revision >= 0)
        with self._dir() as directory_fd, self._locked(directory_fd):
            self._heal(directory_fd, nonce)
            entry = self._read(directory_fd, nonce)
            if entry.revision != expected_revision:
                raise RevisionConflict()
            updated = reconcile(entry, matches, trusted=trusted, now_ns=self._clock())
            if updated != entry:
                self._write(directory_fd, updated, create=False)
        return updated, plan_for(updated)

    def admission(self):
        """One derived conclusion; every unreadable or open intent denies both."""
        entries = None
        try:
            with self._dir() as directory_fd:
                entries = self._entries(directory_fd)
        except (JournalError, OSError, ValueError, TypeError, RecursionError):
            return Admission(False, False, 'journal_invalid')
        open_entries = sorted((entry for entry in entries if entry.state != CLOSED),
                              key=lambda entry: entry.nonce)
        if open_entries:
            return Admission(False, False, open_entries[0].state)
        return Admission(True, True, 'clear')

    def delivery_gate(self, nonce):
        """Whether this session may hand its configuration to `nonce`'s receiver."""
        if type(nonce) is not str or _HEX64.fullmatch(nonce) is None:
            return DeliveryGate(False, 'unknown_intent')
        try:
            with self._dir() as directory_fd:
                entries = self._entries(directory_fd)
        except (JournalError, OSError, ValueError, TypeError, RecursionError):
            return DeliveryGate(False, 'journal_invalid')
        mine = [entry for entry in entries if entry.nonce == nonce]
        if not mine:
            return DeliveryGate(False, 'unknown_intent')
        blocking = sorted((entry for entry in entries
                           if entry.nonce != nonce and entry.state != CLOSED),
                          key=lambda entry: entry.nonce)
        if blocking:
            # One live session at a time: another open intent still blocks.
            return DeliveryGate(False, 'other_intent_open')
        entry = mine[0]
        if entry.doubted:
            # Recovered after doubt: reclaim only, never deliver.
            return DeliveryGate(False, 'reclaimed_after_doubt')
        if entry.state != BOUND or entry.container_id is None:
            return DeliveryGate(False, entry.state)
        return DeliveryGate(True, 'bound')

    def result(self, nonce):
        """Fixed infrastructure status for one intent; never receiver output.

        Unreadable or corrupt state is doubt, so it reports unknown instead of
        raising, and a `create_absent` close observed no process at all.
        """
        entry = None
        try:
            entry = self.load(nonce)
        except (JournalError, OSError, ValueError, TypeError, RecursionError):
            entry = None
        if entry is None or entry.state != CLOSED:
            return InfrastructureResult('isolation_unknown')
        if entry.closed_by == RECLAIM_VERIFIED:
            return InfrastructureResult('isolation_terminated')
        return InfrastructureResult('isolation_unknown')
