"""R7 receipt storage and serialization within a caller-owned transaction.

The runtime must first lock and verify installation/task/run and authorize the
bound sources and receiver. This module independently serializes accounting
on the run row. It never commits or sends a response.
"""

import hmac
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_task import AgentRun
from app.schemas.pfmea_impact import ImpactSourceRef
from app.services.agent_runtime.pfmea_impact_release import (
    FMEA_MAX_ATTEMPTS,
    FMEA_MAX_BYTES,
    FmeaReleaseBudget,
    PageConfirmation,
    PageConfirmationMismatch,
    PageRelease,
    PageScope,
    ProjectionBudgetExceeded,
    confirm_page,
    confirmed_page_keys,
    reserve_fmea_release,
    verify_page_payload,
)

_MAX_RELEASES = 32
_MAX_SOURCE_REFS = 256


class IncompleteCoverage(PageConfirmationMismatch):
    """This scope has valid confirmations, but the expected set is incomplete."""


def scope_digest(scope: PageScope) -> str:
    coordinates = (str(scope.task_id), str(scope.run_id), scope.lease_epoch,
                   scope.binding_digest, scope.snapshot_digest, scope.scope_ref)
    return sha256(json.dumps(coordinates, separators=(",", ":")).encode()).hexdigest()


def sign_page_confirmation_token(
    scope: PageScope, release_id: UUID, page_key: str, payload_digest: str,
) -> str:
    value = json.dumps(
        ("openqms.r7.page-confirmation.v1", scope_digest(scope), str(release_id),
         page_key, payload_digest), separators=(",", ":"),
    ).encode()
    return hmac.new(settings.SECRET_KEY.encode(), value, sha256).hexdigest()


def require_page_confirmation_token(
    scope: PageScope, release_id: UUID, page_key: str, payload_digest: str, token: str,
) -> None:
    if (
        not isinstance(token, str) or len(token) != 64 or not token.isascii()
        or not hmac.compare_digest(
            token, sign_page_confirmation_token(scope, release_id, page_key, payload_digest),
        )
    ):
        raise PageConfirmationMismatch("Invalid page confirmation")


def fmea_usage_from_releases(rows) -> FmeaReleaseBudget:
    attempts = byte_count = 0
    elements = set()
    for row in rows:
        if row.kind != "release":
            continue
        if not isinstance(row.payload, dict) or row.payload.get("module") not in ("fmea", "capa"):
            raise PermissionError("Invalid release accounting")
        if row.payload["module"] == "capa":
            continue
        count = row.payload.get("byte_count")
        keys = row.payload.get("element_keys")
        if (type(count) is not int or count <= 0 or not isinstance(keys, list)
                or any(not isinstance(key, str) or not key for key in keys)):
            raise PermissionError("Invalid release accounting")
        attempts += 1
        byte_count += count
        elements.update(keys)
    return FmeaReleaseBudget(attempts, byte_count, frozenset(elements))


def make_release_payload(
    scope: PageScope, *, module: Literal["capa", "fmea"], body: bytes,
    element_keys: Iterable[str], sources: Iterable[ImpactSourceRef],
    page_key: str | None = None, expected_page_digests: Mapping[str, str] | None = None,
) -> dict:
    """Capture metadata of the exact projection before any bytes leave."""
    if module not in ("capa", "fmea") or not isinstance(body, bytes) or not body:
        raise ValueError("Invalid projection release")
    if len(body) > FMEA_MAX_BYTES:
        raise ProjectionBudgetExceeded("Projection bytes exceeded")
    keys = sorted(set(element_keys))
    refs = tuple(sources)
    if (
        len(refs) > _MAX_SOURCE_REFS or any(not isinstance(ref, ImpactSourceRef) for ref in refs)
        or any(not isinstance(key, str) or not key or len(key.encode()) > 4096 for key in keys)
        or (module == "capa" and keys)
    ):
        raise ValueError("Invalid projection metadata")
    if page_key is not None:
        if module != "fmea" or expected_page_digests is None:
            raise PageConfirmationMismatch("Canonical FMEA page plan required")
        digest = verify_page_payload(page_key, body, expected_page_digests=expected_page_digests)
    else:
        if expected_page_digests is not None:
            raise PageConfirmationMismatch("Canonical page required")
        digest = sha256(body).hexdigest()
    return {
        "module": module, "binding_digest": scope.binding_digest,
        "snapshot_digest": scope.snapshot_digest, "scope_ref": scope.scope_ref,
        "payload_digest": digest, "byte_count": len(body), "element_keys": keys,
        "sources": [source.model_dump(mode="json") for source in refs],
    }


async def _lock_run(db: AsyncSession, scope: PageScope) -> None:
    from app.models.agent_pfmea_impact import AgentPfmeaImpactBinding

    run = await db.scalar(select(AgentRun).where(
        AgentRun.run_id == scope.run_id, AgentRun.task_id == scope.task_id,
    ).with_for_update().execution_options(populate_existing=True))
    if (
        run is None or run.status != "active" or run.lease_epoch != scope.lease_epoch
        or run.lease_expires_at is None or run.lease_expires_at <= datetime.now(UTC)
    ):
        raise PermissionError("Impact run unavailable")
    digest = await db.scalar(select(AgentPfmeaImpactBinding.binding_digest).where(
        AgentPfmeaImpactBinding.task_id == scope.task_id,
    ))
    if digest is None or digest != scope.binding_digest:
        raise PermissionError("Impact binding unavailable")


async def record_release(
    db: AsyncSession, scope: PageScope, *, module: Literal["capa", "fmea"], body: bytes,
    element_keys: Iterable[str], sources: Iterable[ImpactSourceRef],
    page_key: str | None = None, expected_page_digests: Mapping[str, str] | None = None,
    next_cursor: str | None = None,
) -> UUID:
    """Reserve and flush a potentially released receipt. Commit before sending."""
    from app.models.agent_pfmea_impact import AgentPfmeaImpactReceipt

    payload = make_release_payload(scope, module=module, body=body, element_keys=element_keys,
                                   sources=sources, page_key=page_key,
                                   expected_page_digests=expected_page_digests)
    if next_cursor is not None:
        payload["next_cursor"] = next_cursor
    if not payload["sources"]:
        raise PermissionError("Projection sources unavailable")
    await _lock_run(db, scope)
    receipt = AgentPfmeaImpactReceipt
    releases = (await db.scalars(select(receipt).where(
        receipt.task_id == scope.task_id, receipt.run_id == scope.run_id,
        receipt.lease_epoch == scope.lease_epoch, receipt.kind == "release",
    ).limit(_MAX_RELEASES))).all()
    if len(releases) >= _MAX_RELEASES:
        raise ProjectionBudgetExceeded("Run projection limit exceeded")
    if module == "fmea":
        reserve_fmea_release(fmea_usage_from_releases(releases), projection_bytes=body,
                             element_keys=payload["element_keys"])
    row = receipt(
        receipt_id=uuid4(), task_id=scope.task_id, run_id=scope.run_id,
        lease_epoch=scope.lease_epoch, kind="release", scope_digest=scope_digest(scope),
        page_key=page_key, payload=payload,
    )
    db.add(row)
    await db.flush()
    return row.receipt_id


async def record_confirmation(
    db: AsyncSession, scope: PageScope, *, release_id: UUID, page_key: str,
    payload_digest: str, token: str, expected_page_digests: Mapping[str, str],
) -> UUID:
    """Record one page ACK independently of the send attempt.

    The runtime still verifies current authority before calling. A receipt ID
    grants neither authority nor proof of the confirmation value.
    """
    from app.models.agent_pfmea_impact import AgentPfmeaImpactReceipt

    require_page_confirmation_token(scope, release_id, page_key, payload_digest, token)
    await _lock_run(db, scope)
    receipt = AgentPfmeaImpactReceipt
    matching_scope = (
        receipt.task_id == scope.task_id, receipt.run_id == scope.run_id,
        receipt.lease_epoch == scope.lease_epoch, receipt.scope_digest == scope_digest(scope),
    )
    row = await db.scalar(select(receipt).where(
        *matching_scope, receipt.kind == "release", receipt.receipt_id == release_id,
    ))
    if row is None or row.page_key is None or row.payload.get("module") != "fmea":
        raise PageConfirmationMismatch("Projection receipt unavailable")
    ack = confirm_page(
        PageRelease(row.receipt_id, scope, row.page_key, row.payload["payload_digest"]),
        scope=scope, release_ref=release_id, page_key=page_key, payload_digest=payload_digest,
    )
    confirmed_page_keys(scope, (ack,), expected_page_digests=expected_page_digests)

    existing = await db.scalar(select(receipt).where(
        *matching_scope, receipt.kind == "page_confirmation", receipt.page_key == page_key,
    ))
    if existing is not None:
        if existing.payload.get("payload_digest") != payload_digest:
            raise PageConfirmationMismatch("Conflicting page confirmation")
        return existing.receipt_id

    confirmation = receipt(
        receipt_id=uuid4(), task_id=scope.task_id, run_id=scope.run_id,
        lease_epoch=scope.lease_epoch, kind="page_confirmation", scope_digest=scope_digest(scope),
        page_key=page_key, payload={"release_ref": str(release_id), "payload_digest": payload_digest},
    )
    db.add(confirmation)
    await db.flush()
    return confirmation.receipt_id


async def record_coverage(
    db: AsyncSession, scope: PageScope, *, expected_page_digests: Mapping[str, str],
) -> UUID:
    """Issue a scope receipt only when the canonical confirmed page set is complete."""
    from app.models.agent_pfmea_impact import AgentPfmeaImpactReceipt

    if not expected_page_digests or len(expected_page_digests) > FMEA_MAX_ATTEMPTS:
        raise PageConfirmationMismatch("Canonical page plan unavailable")
    await _lock_run(db, scope)
    receipt = AgentPfmeaImpactReceipt
    matching_scope = (
        receipt.task_id == scope.task_id, receipt.run_id == scope.run_id,
        receipt.lease_epoch == scope.lease_epoch, receipt.scope_digest == scope_digest(scope),
    )
    rows = (await db.scalars(select(receipt).where(
        *matching_scope, receipt.kind == "page_confirmation",
    ).order_by(receipt.page_key))).all()
    confirmations = (
        PageConfirmation(scope, row.page_key, UUID(row.payload["release_ref"]), row.payload["payload_digest"])
        for row in rows
    )
    keys = confirmed_page_keys(scope, confirmations, expected_page_digests=expected_page_digests)
    if keys != set(expected_page_digests):
        raise IncompleteCoverage("Incomplete scope coverage")
    payload = {"confirmed_page_refs": [str(row.receipt_id) for row in rows],
               "binding_digest": scope.binding_digest, "snapshot_digest": scope.snapshot_digest,
               "scope_ref": scope.scope_ref}
    existing = await db.scalar(select(receipt).where(*matching_scope, receipt.kind == "coverage"))
    if existing is not None:
        if existing.payload != payload:
            raise PageConfirmationMismatch("Conflicting scope receipt")
        return existing.receipt_id
    coverage = receipt(
        receipt_id=uuid4(), task_id=scope.task_id, run_id=scope.run_id,
        lease_epoch=scope.lease_epoch, kind="coverage", scope_digest=scope_digest(scope),
        payload=payload,
    )
    db.add(coverage)
    await db.flush()
    return coverage.receipt_id
