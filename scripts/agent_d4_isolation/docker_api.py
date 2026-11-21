"""Fixed Docker Engine surface, bound to the create-intent journal.

Every state-changing call is authorised by re-reading the journal *inside* the
same call, immediately before bytes reach the transport. A caller cannot pass a
forged "authorisation" value: there is no such parameter. It names a locator
(nonce, revision, exact container id) and the journal decides.

Consequences that matter for the isolation design:

* A `delete` is sent only when the journal says this exact intent is `closed`
  with `reclaim_verified` at the named revision. Everything else refuses with
  zero bytes sent.
* A `create` is never reported as "nothing was created". Once bytes may have
  reached the daemon, no answer can prove that no object exists; a negative or
  unclear answer turns the intent permanently doubtful instead.
* A transport failure leaves the intent unresolved, which blocks the next
  session. Guessing "it probably failed" is exactly what this module refuses to
  do.

This is a pure layer: it proves nothing about a real daemon, image or container.
"""
from dataclasses import dataclass
import json
import re
from typing import Protocol

from .journal import (BOUND, CLOSED, CREATE_INFLIGHT, INTENT_PENDING, RECLAIM_VERIFIED,
                      STOPPING, UNRESOLVED)

ID_HEX = re.compile(r'[a-f0-9]{64}')
DIGEST = re.compile(r'sha256:[a-f0-9]{64}')

ALLOWED_OPS = frozenset(('create', 'start', 'attach', 'inspect', 'list_by_nonce',
                         'stop', 'delete'))

REQUEST_REJECTED = 'request_rejected'
TRANSPORT_FAILED = 'transport_failed'
RESPONSE_INVALID = 'response_invalid'
RESPONSE_TOO_LARGE = 'response_too_large'
DEADLINE_EXCEEDED = 'deadline_exceeded'
JOURNAL_UNAVAILABLE = 'journal_unavailable'
JOURNAL_STATE = 'journal_state'
MAX_DEADLINE_NS = 10 * 10 ** 9
MAX_RESPONSE_BYTES = 256 * 1024


class DockerError(ValueError):
    """A call that was refused, or whose outcome cannot be known."""

    def __init__(self, code=REQUEST_REJECTED):
        super().__init__(code)


class TransportError(OSError):
    """The transport itself failed; the daemon state is unknown."""


def _require(condition, code=REQUEST_REJECTED):
    if not condition:
        raise DockerError(code)


def _is_id(value):
    return type(value) is str and ID_HEX.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class JournalLocator:
    """Which recorded intent a state-changing call is about.

    This is a *locator*, not evidence: it carries no trusted stamp. The journal
    is re-read for every call, so holding one of these grants nothing.
    """
    nonce: str
    revision: int
    container_id: str

    def __post_init__(self):
        _require(_is_id(self.nonce) and _is_id(self.container_id))
        _require(type(self.revision) is int and self.revision >= 0)


@dataclass(frozen=True, slots=True)
class DockerRequest:
    """One structured call. The field set is closed per operation."""
    op: str
    container_id: str | None = None
    nonce: str | None = None
    locator: JournalLocator | None = None

    def __post_init__(self):
        _require(self.op in ALLOWED_OPS)
        if self.op == 'create':
            _require(_is_id(self.nonce) and self.container_id is None and self.locator is None)
        elif self.op == 'list_by_nonce':
            _require(_is_id(self.nonce) and self.container_id is None and self.locator is None)
        elif self.op == 'inspect':
            _require(_is_id(self.container_id) and self.nonce is None and self.locator is None)
        else:                       # start / attach / stop / delete
            _require(_is_id(self.container_id) and self.nonce is None)
            _require(type(self.locator) is JournalLocator)
            _require(self.locator.container_id == self.container_id)


@dataclass(frozen=True, slots=True)
class CreateOutcome:
    """Only `created` and `ambiguous` exist; there is no safe negative."""
    kind: str
    container_id: str | None
    reason: str

    def __post_init__(self):
        _require(self.kind in ('created', 'ambiguous'))
        _require((self.kind == 'created') == (self.container_id is not None))
        _require(type(self.reason) is str and self.reason != '')


@dataclass(frozen=True, slots=True)
class InspectOutcome:
    exists: bool
    running: bool
    container_id: str

    def __post_init__(self):
        _require(_is_id(self.container_id))
        _require(type(self.exists) is bool and type(self.running) is bool)
        _require(self.exists or not self.running)


@dataclass(frozen=True, slots=True)
class OperationOutcome:
    done: bool
    container_id: str
    reason: str

    def __post_init__(self):
        _require(_is_id(self.container_id))
        _require(type(self.done) is bool)
        _require(type(self.reason) is str and self.reason != '')


@dataclass(frozen=True, slots=True)
class AttachChannel:
    """Opaque handle for the future one-shot stdin write.

    I3 only establishes that the intent is bound and the id is exact. Writing the
    configuration, bounding the output and the single-delivery guarantee are I7.
    """
    container_id: str

    def __post_init__(self):
        _require(_is_id(self.container_id))


@dataclass(frozen=True, slots=True)
class IdentityFacts:
    """Raw facts a trusted collector must fill for `ReceiverIdentity`.

    `daemon_instance` must be a per-process fact (pidfd start time or systemd
    InvocationID), not Docker's stable `info.ID` plus a boot id: a dockerd restart
    inside one boot keeps both unchanged.
    """
    daemon_instance: str
    container_id: str
    nonce: str
    image_id: str
    netns_inode: int
    uid_map_line: str
    cgroup_path: str

    def __post_init__(self):
        _require(type(self.daemon_instance) is str and self.daemon_instance != '')
        _require(_is_id(self.container_id) and _is_id(self.nonce))
        _require(type(self.image_id) is str and DIGEST.fullmatch(self.image_id) is not None)
        _require(type(self.netns_inode) is int and self.netns_inode > 0)
        _require(type(self.uid_map_line) is str and self.uid_map_line != '')
        _require(type(self.cgroup_path) is str and self.cgroup_path.startswith('/'))


class Transport(Protocol):
    """Bounded request/response seam. Implementations must honour `limit`."""

    def exchange(self, payload: bytes, *, deadline_ns: int, limit: int) -> bytes:
        ...


def _unique_pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, RESPONSE_INVALID)
        result[key] = value
    return result


class DockerApi:
    """The whole surface the controller may use; everything else is refused."""

    def __init__(self, transport, image_digest, *, journal, clock,
                 op_deadline_ns, response_limit):
        _require(type(image_digest) is str and DIGEST.fullmatch(image_digest) is not None)
        _require(callable(clock))
        _require(callable(getattr(transport, 'exchange', None)))
        _require(callable(getattr(journal, 'load', None))
                 and callable(getattr(journal, 'transition', None)))
        _require(type(op_deadline_ns) is int and 0 < op_deadline_ns <= MAX_DEADLINE_NS)
        _require(type(response_limit) is int and 0 < response_limit <= MAX_RESPONSE_BYTES)
        for name, value in (('_transport', transport), ('_image_digest', image_digest),
                            ('_journal', journal), ('_clock', clock),
                            ('_deadline_ns', op_deadline_ns), ('_limit', response_limit)):
            object.__setattr__(self, name, value)

    def __setattr__(self, name, value):
        raise AttributeError('DockerApi is immutable')

    # -- journal authorisation -------------------------------------------
    def _entry(self, nonce):
        """Read one intent; any storage failure becomes a refusal, never a send."""
        try:
            entry = self._journal.load(nonce)
        except Exception:
            raise DockerError(JOURNAL_UNAVAILABLE) from None
        if entry is None or getattr(entry, 'nonce', None) != nonce:
            raise DockerError(JOURNAL_UNAVAILABLE)
        return entry

    def _authorize(self, request):
        """Decide from the journal, immediately before the transport is used."""
        locator = request.locator
        _require(type(locator) is JournalLocator)
        _require(request.container_id == locator.container_id, JOURNAL_STATE)
        entry = self._entry(locator.nonce)
        _require(entry.revision == locator.revision, JOURNAL_STATE)
        _require(entry.container_id == locator.container_id, JOURNAL_STATE)
        if request.op == 'delete':
            # Deletion is the only irreversible call: it needs a *closed intent
            # whose closing evidence is a verified reclaim* of this exact object.
            _require(entry.state == CLOSED and entry.closed_by == RECLAIM_VERIFIED,
                     JOURNAL_STATE)
        elif request.op == 'stop':
            _require(entry.state in (BOUND, STOPPING), JOURNAL_STATE)
        elif request.op == 'start':
            # Only a bound intent names a container: `intent_pending` and
            # `create_inflight` have no id yet, so they cannot authorise a start.
            _require(entry.state == BOUND, JOURNAL_STATE)
        elif request.op == 'attach':
            _require(entry.state == BOUND, JOURNAL_STATE)
        else:
            _require(False, JOURNAL_STATE)

    def _doubt(self, nonce):
        """Record that this create may have produced an object. Never raises."""
        try:
            entry = self._journal.load(nonce)
            if entry.state != UNRESOLVED and entry.state != CLOSED:
                self._journal.transition(nonce, entry.revision, UNRESOLVED)
        except Exception:
            pass

    # -- encoding ---------------------------------------------------------
    def _payload(self, op, container_id, nonce):
        # Takes plain validated values, never the request object: a str subclass
        # with a spoofed __eq__ must not be able to compare as one operation and
        # serialise as another.
        body = {'op': op, 'image_digest': None,
                'container_id': container_id, 'nonce': nonce,
                'authorized_delete': op == 'delete'}
        if op == 'create':
            body['image_digest'] = self._image_digest
        return json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')

    def _revalidate(self, request):
        """Rebuild the call from exact primitives, ignoring the object's fields.

        Frozen dataclasses are not a security boundary: `object.__setattr__` can
        replace a field, and a str subclass can satisfy an `==` check while
        serialising as something else. Everything the daemon sees is re-derived
        here from values whose exact type is checked.
        """
        _require(type(request) is DockerRequest)
        op = request.op
        _require(type(op) is str and op in ALLOWED_OPS, REQUEST_REJECTED)
        container_id, nonce, locator = request.container_id, request.nonce, request.locator
        if locator is not None:
            _require(type(locator) is JournalLocator, REQUEST_REJECTED)
            _require(type(locator.nonce) is str and _is_id(locator.nonce), REQUEST_REJECTED)
            _require(_is_id(locator.container_id), REQUEST_REJECTED)
            _require(type(locator.revision) is int and locator.revision >= 0, REQUEST_REJECTED)
        if op == 'create':
            _require(_is_id(nonce) and container_id is None and locator is None, REQUEST_REJECTED)
        elif op == 'list_by_nonce':
            _require(_is_id(nonce) and container_id is None and locator is None, REQUEST_REJECTED)
        elif op == 'inspect':
            _require(_is_id(container_id) and nonce is None and locator is None, REQUEST_REJECTED)
        else:
            _require(_is_id(container_id) and nonce is None, REQUEST_REJECTED)
            _require(locator is not None and locator.container_id == container_id,
                     REQUEST_REJECTED)
        return op, container_id, nonce, locator

    def _call(self, request, *, expected_revision=None):
        op, container_id, nonce, locator = self._revalidate(request)
        if op == 'create':
            # The single send is claimed here, durably: the intent must still be
            # intent_pending, and this call moves it to create_inflight. A second
            # call, however it is constructed, can no longer send.
            _require(type(expected_revision) is int and expected_revision >= 0, REQUEST_REJECTED)
            entry = self._entry(nonce)
            _require(entry.state == INTENT_PENDING, JOURNAL_STATE)
            _require(entry.revision == expected_revision, JOURNAL_STATE)
            try:
                self._journal.transition(nonce, expected_revision, CREATE_INFLIGHT)
            except Exception:
                raise DockerError(JOURNAL_UNAVAILABLE) from None
        elif op in ('inspect', 'list_by_nonce'):
            pass            # read-only: they authorise nothing, so nothing to check
        else:
            # Re-read the journal here, not only in the public wrapper: a direct
            # call to this seam must not be able to skip the check.
            self._authorize(request)
        deadline = self._clock() + self._deadline_ns
        target = locator.container_id if locator else container_id
        try:
            raw = self._transport.exchange(self._payload(op, target, nonce),
                                           deadline_ns=deadline, limit=self._limit)
        except TransportError:
            if op == 'create':
                self._doubt(nonce)
            raise DockerError(TRANSPORT_FAILED) from None
        except (OSError, TimeoutError):
            if op == 'create':
                self._doubt(nonce)
            raise DockerError(TRANSPORT_FAILED) from None
        if type(raw) is not bytes:
            raise DockerError(RESPONSE_INVALID)
        if len(raw) > self._limit:
            raise DockerError(RESPONSE_TOO_LARGE)
        if self._clock() > deadline:
            raise DockerError(DEADLINE_EXCEEDED)
        value = None
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs)
        except (ValueError, UnicodeError, RecursionError):
            pass
        _require(type(value) is dict, RESPONSE_INVALID)
        return value

    # -- operations -------------------------------------------------------
    def create(self, nonce, *, expected_revision):
        """Persist `create_inflight`, then send; any doubt blocks the next session."""
        try:
            reply = self._call(DockerRequest('create', nonce=nonce),
                               expected_revision=expected_revision)
        except DockerError as error:
            self._doubt(nonce)
            return CreateOutcome('ambiguous', None, str(error))
        except Exception:
            # An adapter bug is still an unknown create: never a silent absence.
            self._doubt(nonce)
            return CreateOutcome('ambiguous', None, TRANSPORT_FAILED)
        if reply.get('nonce') != nonce:
            self._doubt(nonce)
            return CreateOutcome('ambiguous', None, RESPONSE_INVALID)
        if reply.get('created') is True and _is_id(reply.get('container_id')):
            return CreateOutcome('created', reply['container_id'], 'created')
        # Everything else — including a bare `created: false` — is doubt. The
        # engine protocol here has no "provably nothing was created" answer.
        self._doubt(nonce)
        return CreateOutcome('ambiguous', None, RESPONSE_INVALID)

    def list_by_nonce(self, nonce):
        """Exact full ids only; the reply must echo the nonce it answers."""
        reply = self._call(DockerRequest('list_by_nonce', nonce=nonce))
        if reply.get('nonce') != nonce or set(reply) != {'container_ids', 'nonce'}:
            raise DockerError(RESPONSE_INVALID)
        found = reply.get('container_ids')
        if type(found) is not list or len(found) > 8 or not all(_is_id(item) for item in found):
            raise DockerError(RESPONSE_INVALID)
        return tuple(sorted(set(found)))

    INSPECT_KEYS = frozenset(('container_id', 'exists', 'running'))
    IDENTITY_KEYS = frozenset(('container_id', 'daemon_instance', 'image_id',
                               'netns_inode', 'nonce', 'uid_map_line', 'cgroup_path'))

    def inspect(self, container_id):
        """Read-only existence check. It grants no permission for any action."""
        reply = self._call(DockerRequest('inspect', container_id=container_id))
        if set(reply) != self.INSPECT_KEYS:
            raise DockerError(RESPONSE_INVALID)
        if reply.get('container_id') != container_id:
            raise DockerError(RESPONSE_INVALID)
        exists, running = reply.get('exists'), reply.get('running')
        if type(exists) is not bool or type(running) is not bool:
            raise DockerError(RESPONSE_INVALID)
        return InspectOutcome(exists, running, container_id)

    def collect_identity(self, locator):
        """Read the facts a trusted collector needs, without authorising an action."""
        _require(type(locator) is JournalLocator)
        entry = self._entry(locator.nonce)
        _require(entry.container_id == locator.container_id, JOURNAL_STATE)
        reply = self._call(DockerRequest('inspect', container_id=locator.container_id))
        if set(reply) != self.IDENTITY_KEYS:
            raise DockerError(RESPONSE_INVALID)
        if reply.get('container_id') != locator.container_id or reply.get('nonce') != locator.nonce:
            raise DockerError(RESPONSE_INVALID)
        return IdentityFacts(**reply)

    def start(self, locator):
        reply = self._call(DockerRequest('start', container_id=locator.container_id,
                                         locator=locator))
        if set(reply) != {'container_id', 'started'}:
            raise DockerError(RESPONSE_INVALID)
        if reply.get('container_id') != locator.container_id or type(reply.get('started')) is not bool:
            raise DockerError(RESPONSE_INVALID)
        return OperationOutcome(reply['started'], locator.container_id,
                                'started' if reply['started'] else 'not_started')

    def attach(self, locator):
        """Establish the bounded control channel; no secret is written in I3."""
        reply = self._call(DockerRequest('attach', container_id=locator.container_id,
                                         locator=locator))
        if set(reply) != {'container_id', 'attached'}:
            raise DockerError(RESPONSE_INVALID)
        if reply.get('container_id') != locator.container_id or reply.get('attached') is not True:
            raise DockerError(RESPONSE_INVALID)
        return AttachChannel(locator.container_id)

    def stop(self, locator):
        reply = self._call(DockerRequest('stop', container_id=locator.container_id,
                                         locator=locator))
        if set(reply) != {'container_id', 'stopped'}:
            raise DockerError(RESPONSE_INVALID)
        if reply.get('container_id') != locator.container_id or type(reply.get('stopped')) is not bool:
            raise DockerError(RESPONSE_INVALID)
        return OperationOutcome(reply['stopped'], locator.container_id,
                                'stopped' if reply['stopped'] else 'not_stopped')

    def delete(self, locator):
        """Send a delete only for a closed, reclaim-verified intent."""
        _require(type(locator) is JournalLocator)
        reply = self._call(DockerRequest('delete', container_id=locator.container_id,
                                         locator=locator))
        if set(reply) != {'container_id', 'deleted'}:
            raise DockerError(RESPONSE_INVALID)
        if reply.get('container_id') != locator.container_id or type(reply.get('deleted')) is not bool:
            raise DockerError(RESPONSE_INVALID)
        return OperationOutcome(reply['deleted'], locator.container_id,
                                'deleted' if reply['deleted'] else 'not_deleted')
