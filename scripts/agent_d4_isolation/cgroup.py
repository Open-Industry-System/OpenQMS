"""Cgroup termination bound to a trusted backend, not to a caller's opinion.

The decision and the action must be the same operation. This module therefore
does not hand out an "allowed = True" value that a caller may then apply to some
other object; it calls a trusted backend whose `terminate` re-verifies the
retained capability and acts through it in one step.

What the backend must actually be able to do (I4/I5, NOT implemented here):

* hold a directory descriptor or `O_PATH` descriptor opened on the receiver's
  own cgroup, never re-resolve a path or a container name;
* prove the descriptor still names the same kernel object (identity of the live
  handle, not only `(device, inode, boot_id)`, which a re-used inode or a
  same-boot re-creation can reproduce);
* write the cgroup's `cgroup.kill` (or equivalent) through that descriptor,
  relative to the retained directory, and confirm no task remains;
* keep the session dead once its generation changes: a restarted daemon or a
  replaced namespace may only be used for reclamation, never for delivery.

Everything above is a real-Linux question. A unit test with a fake backend shows
only that this layer refuses the obvious mistakes.
"""
from dataclasses import dataclass
import re
from typing import Protocol

from .identity import KernelObject
from .journal import BOUND, STOPPING

ID_HEX = re.compile(r'[a-f0-9]{64}')
# A real kernel boot id is exactly a canonical UUID (36 chars, hyphens); a short
# hex form would make a 32-bit collision look like continuity.
BOOT_ID = re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}')

VERIFIED = 'verified'
HANDLE_MISSING = 'handle_missing'
OBJECT_REPLACED = 'object_replaced'
BIRTH_UNAVAILABLE = 'birth_unavailable'
UNKNOWN = 'unknown'


def _require(condition, message='cgroup_reference_invalid'):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class KernelBirth:
    """Birth facts recorded when the handle was bound; a record, not authority."""
    device: int
    inode: int
    boot_id: str

    def __post_init__(self):
        _require(type(self.device) is int and self.device >= 0)
        _require(type(self.inode) is int and self.inode > 0)
        _require(type(self.boot_id) is str and BOOT_ID.fullmatch(self.boot_id) is not None)

    def to_kernel_object(self, continuity_token):
        """Bridge to I1's KernelObject using a token the backend vouched for.

        The boot id is deliberately NOT reused as the token: two distinct objects
        created in the same boot would then share it. Only a live capability can
        say that this birth still belongs to the object it was bound to.
        """
        _require(type(continuity_token) is bytes and bool(continuity_token),
                 'continuity_token_missing')
        return KernelObject(self.device, self.inode, continuity_token)


@dataclass(frozen=True, slots=True)
class CgroupRef:
    """Locator for one recorded intent. Holding it grants no authority."""
    nonce: str
    container_id: str

    def __post_init__(self):
        _require(type(self.nonce) is str and ID_HEX.fullmatch(self.nonce) is not None)
        _require(type(self.container_id) is str
                 and ID_HEX.fullmatch(self.container_id) is not None)


@dataclass(frozen=True, slots=True)
class TerminationResult:
    terminated: bool
    reason: str

    def __post_init__(self):
        _require(type(self.terminated) is bool)
        _require(self.reason in (VERIFIED, HANDLE_MISSING, OBJECT_REPLACED,
                                 BIRTH_UNAVAILABLE, UNKNOWN))
        _require((self.reason == VERIFIED) == self.terminated)


class TrustedCgroupBackend(Protocol):
    """Trusted seam: verify-and-terminate through one retained capability.

    Implementations must perform verification and the kill in the same call,
    against the same retained handle, and must never accept a path, a PID or a
    container name from the caller.
    """

    def terminate(self, ref: CgroupRef) -> TerminationResult:
        ...

    def identity_token(self, ref: CgroupRef) -> bytes | None:
        """Object-specific continuity token, or None when it cannot be proven."""
        ...


class CgroupGuard:
    """Refuses to act unless the journal still describes this exact object."""

    def __init__(self, backend, journal):
        _require(callable(getattr(backend, 'terminate', None)), 'backend_invalid')
        _require(callable(getattr(journal, 'load', None)), 'journal_invalid')
        object.__setattr__(self, '_backend', backend)
        object.__setattr__(self, '_journal', journal)

    def __setattr__(self, name, value):
        raise AttributeError('CgroupGuard is immutable')

    def _entry(self, ref):
        try:
            entry = self._journal.load(ref.nonce)
        except Exception:
            return None
        if entry is None or getattr(entry, 'nonce', None) != ref.nonce:
            return None
        if getattr(entry, 'container_id', None) != ref.container_id:
            return None
        if entry.state not in (BOUND, STOPPING):
            return None
        return entry

    def terminate(self, ref, *, expected_revision):
        """Terminate only the object the journal currently binds to this intent."""
        _require(type(ref) is CgroupRef)
        _require(type(expected_revision) is int and expected_revision >= 0)
        entry = self._entry(ref)
        if entry is None or entry.revision != expected_revision:
            return TerminationResult(False, UNKNOWN)
        try:
            result = self._backend.terminate(ref)
        except Exception:
            # An unverifiable backend is unknown, never "probably fine".
            return TerminationResult(False, UNKNOWN)
        if type(result) is not TerminationResult:
            return TerminationResult(False, UNKNOWN)
        return result

    def identity_token(self, ref):
        # A token may only be issued for an intent the journal still binds to this
        # exact object; otherwise any caller could obtain one for anything.
        if type(ref) is not CgroupRef or self._entry(ref) is None:
            return None
        try:
            token = self._backend.identity_token(ref)
        except Exception:
            return None
        if type(token) is not bytes or not token:
            return None
        return token
