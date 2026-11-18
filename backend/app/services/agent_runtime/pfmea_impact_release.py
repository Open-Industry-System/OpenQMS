"""Rules for R7 projection accounting against a caller-locked run ledger."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID


FMEA_MAX_ATTEMPTS = 16
FMEA_MAX_ELEMENTS = 200
FMEA_MAX_BYTES = 256 * 1024


class ProjectionBudgetExceeded(ValueError):
    """The next send would exceed a run's committed budget."""


class PageConfirmationMismatch(ValueError):
    """Confirmation and committed release do not bind the same page."""


@dataclass(frozen=True, slots=True)
class FmeaReleaseBudget:
    """Usage reserved by already committed FMEA release attempts."""

    attempts: int = 0
    byte_count: int = 0
    element_keys: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class PageScope:
    task_id: UUID
    run_id: UUID
    lease_epoch: int
    binding_digest: str
    snapshot_digest: str
    scope_ref: str


@dataclass(frozen=True, slots=True)
class PageRelease:
    """Identity of a committed, potentially released canonical page."""

    release_ref: UUID
    scope: PageScope
    page_key: str
    payload_digest: str


@dataclass(frozen=True, slots=True)
class PageConfirmation:
    scope: PageScope
    page_key: str
    release_ref: UUID
    payload_digest: str


def reserve_fmea_release(
    budget: FmeaReleaseBudget, *, projection_bytes: bytes, element_keys: Iterable[str],
) -> FmeaReleaseBudget:
    """Price the next send from fresh ledger usage, under the caller's run lock.

    The caller must commit this reservation and its complete source references
    before sending the same serialized projection. Failed or ambiguous sends
    remain charged. Only send attempts call this function; confirmations are
    recorded separately and free. Element keys come from the server projection.
    """
    if any(type(value) is not int or value < 0 for value in (budget.attempts, budget.byte_count)):
        raise ValueError("Invalid release ledger counts")
    if not isinstance(projection_bytes, bytes):
        raise TypeError("Projection must be serialized bytes")
    attempts = budget.attempts + 1
    if attempts > FMEA_MAX_ATTEMPTS:
        raise ProjectionBudgetExceeded("FMEA projection attempts exceeded")
    byte_count = budget.byte_count + len(projection_bytes)
    if byte_count > FMEA_MAX_BYTES:
        raise ProjectionBudgetExceeded("FMEA projection bytes exceeded")
    elements = budget.element_keys.union(element_keys)
    if len(elements) > FMEA_MAX_ELEMENTS:
        raise ProjectionBudgetExceeded("FMEA projection elements exceeded")
    return FmeaReleaseBudget(attempts, byte_count, elements)


def confirm_page(
    release: PageRelease, *, scope: PageScope, release_ref: UUID,
    page_key: str, payload_digest: str,
) -> PageConfirmation:
    """Check a verified ACK against its stored release before writing coverage.

    The caller resolves the current authorized scope and verifies the signed
    confirmation value. It loads the committed release and persists the result
    at most once for the scope and canonical page key.
    """
    if (scope, release_ref, page_key, payload_digest) != (
        release.scope, release.release_ref, release.page_key, release.payload_digest,
    ):
        raise PageConfirmationMismatch("Acknowledgement does not match the committed page")
    return PageConfirmation(scope, page_key, release_ref, payload_digest)


def _require_expected_digest(
    page_key: str, digest: str, expected_page_digests: Mapping[str, str],
) -> None:
    expected = expected_page_digests.get(page_key)
    if expected is None or expected != digest:
        raise PageConfirmationMismatch("Projection does not match the canonical page")


def verify_page_payload(
    page_key: str, projection_bytes: bytes, *, expected_page_digests: Mapping[str, str],
) -> str:
    """Check exact projection bytes against the trusted plan before sending.

    The caller supplies expectations computed from the same authorized scope's
    canonical pages and transport projection format, without the ACK token.
    The page key selects geometry. The digest binds actual projection bytes
    and must not be taken from a previous attempt or the proposed response.
    """
    if not isinstance(projection_bytes, bytes):
        raise TypeError("Projection must be serialized bytes")
    digest = sha256(projection_bytes).hexdigest()
    _require_expected_digest(page_key, digest, expected_page_digests)
    return digest


def confirmed_page_keys(
    scope: PageScope, confirmations: Iterable[PageConfirmation],
    *, expected_page_digests: Mapping[str, str],
) -> frozenset[str]:
    """Extract deduplicated persisted ACKs matching the trusted plan for scope."""
    keys: set[str] = set()
    for confirmation in confirmations:
        if not isinstance(confirmation, PageConfirmation):
            raise PageConfirmationMismatch("Coverage requires a confirmed page")
        if confirmation.scope != scope:
            continue
        _require_expected_digest(
            confirmation.page_key, confirmation.payload_digest, expected_page_digests,
        )
        keys.add(confirmation.page_key)
    return frozenset(keys)
