"""Sealed R7 read projections. Commit possible release before returning bytes."""

import hmac
import json
from base64 import b64encode, urlsafe_b64decode, urlsafe_b64encode
from dataclasses import asdict
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import settings
from app.models.agent_pfmea_impact import AgentPfmeaImpactReceipt
from app.models.audit import AuditLog
from app.services.agent_runtime.pfmea_impact_cursor import read_cursor, sign_cursor
from app.services.agent_runtime.pfmea_impact_ledger import (
    IncompleteCoverage,
    record_confirmation,
    record_coverage,
    record_release,
    scope_digest,
    sign_page_confirmation_token,
)
from app.services.agent_runtime.pfmea_impact_release import PageScope
from app.services.agent_runtime.pfmea_impact_runtime import ImpactRuntime, ImpactRuntimeUnavailable, target_source
from app.services.fmea_impact_projection import (
    canonical_page_digests,
    discover_snapshot_steps,
    plan_step_coverage,
)


def _bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _scope(current: ImpactRuntime, reference: str) -> PageScope:
    return PageScope(current.task.task_id, current.run.run_id, current.epoch, current.binding_digest,
                     current.binding.target.snapshot_hash, reference)


def step_handle(scope: PageScope, step_id: str) -> str:
    if not isinstance(step_id, str) or not 1 <= len(step_id) <= 256:
        raise ImpactRuntimeUnavailable()
    encoded = urlsafe_b64encode(step_id.encode("utf-8")).decode("ascii")
    value = f"openqms.r7.step.v1:{scope_digest(scope)}:{encoded}".encode("ascii")
    mac = hmac.new(settings.SECRET_KEY.encode(), value, sha256).hexdigest()
    return f"{encoded}.{mac}"


def read_step_handle(scope: PageScope, handle: str) -> str:
    if not isinstance(handle, str) or len(handle) > 1600 or not handle.isascii():
        raise ImpactRuntimeUnavailable()
    try:
        raw, _ = handle.split(".", 1)
        node_id = urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        if hmac.compare_digest(handle, step_handle(scope, node_id)):
            return node_id
    except (ValueError, UnicodeError):
        pass
    raise ImpactRuntimeUnavailable()


def release_envelope(
    scope: PageScope, receipt_id: UUID, body: bytes, *, page_key: str | None = None, cursor: str | None = None,
) -> dict:
    digest = sha256(body).hexdigest()
    return {
        "task_id": str(scope.task_id), "run_id": str(scope.run_id), "lease_epoch": scope.lease_epoch,
        "receipt_id": str(receipt_id), "projection_bytes": b64encode(body).decode("ascii"),
        "snapshot_digest": scope.snapshot_digest, "payload_digest": digest,
        "scope_ref": None if page_key is None else scope.scope_ref, "page_key": page_key,
        "confirmation_token": None if page_key is None else
        sign_page_confirmation_token(scope, receipt_id, page_key, digest),
        "next_cursor": cursor,
    }


QUERY_GAP_AUDIT = "R7_IMPACT_QUERY_GAP"
QueryGap = Literal["scope_incomplete", "budget_exhausted"]


async def query_gap(db, current: ImpactRuntime, reason: QueryGap, *, scope_ref: str | None = None) -> dict:
    """Return a current read limit without constructing a source or coverage receipt."""
    audit_id = uuid4()
    db.add(AuditLog(
        log_id=audit_id, table_name="agent_runs", record_id=current.run.run_id, action=QUERY_GAP_AUDIT,
        operated_by=current.task.executor_user_id, factory_id=current.task.factory_id,
        correlation_id=current.run.run_id, changed_fields={"lease_epoch": current.epoch, "reason": reason},
    ))
    response = release_envelope(_scope(current, scope_ref or "query-gap"), audit_id, _bytes({"gap": reason}))
    response["scope_ref"] = scope_ref
    await db.commit()
    return response


async def material_projection(db, current: ImpactRuntime) -> dict:
    scope = _scope(current, "capa.material")
    body = _bytes(current.material.model_dump(mode="json"))
    receipt_id = await record_release(db, scope, module="capa", body=body, element_keys=(),
                                      sources=current.binding.capa.sources)
    response = release_envelope(scope, receipt_id, body)
    await db.commit()
    return response


async def search_projection(db, current: ImpactRuntime, *, term: str, cursor: str | None) -> dict:
    # Keep the cursor term-specific without retaining raw model query text in the ledger.
    scope = _scope(current, "search:" + sha256(term.encode("utf-8")).hexdigest())
    offset = 0 if cursor is None else read_cursor(scope, "search", cursor)
    page = discover_snapshot_steps(current.snapshot.graph, term=term, offset=offset)
    directory = _scope(current, "directory")
    sources = [target_source(current.binding)]
    candidates = []
    for element in page.elements:
        source = target_source(current.binding, element.node_id)
        sources.append(source)
        candidates.append({**asdict(element), "source_id": str(source.source_id),
                           "scope_ref": step_handle(directory, element.node_id)})
    next_cursor = None
    if page.next_offset is not None and page.next_offset <= 500:
        next_cursor = sign_cursor(scope, "search", page.next_offset)
    body = _bytes({"candidates": candidates, "truncated": page.next_offset is not None and next_cursor is None})
    receipt_id = await record_release(db, scope, module="fmea", body=body,
        element_keys=(e.accounting_key for e in page.elements), sources=sources, next_cursor=next_cursor)
    response = release_envelope(scope, receipt_id, body, cursor=next_cursor)
    await db.commit()
    return response


def _step_plan(current: ImpactRuntime, scope_ref: str):
    step_id = read_step_handle(_scope(current, "directory"), scope_ref)
    return plan_step_coverage(current.snapshot.graph, step_id=step_id,
                              snapshot_digest=current.binding.target.snapshot_hash)


async def page_projection(db, current: ImpactRuntime, *, scope_ref: str, cursor: str | None) -> dict:
    scope = _scope(current, scope_ref)
    index = 0 if cursor is None else read_cursor(scope, "page", cursor)
    pages = _step_plan(current, scope_ref)
    if index >= len(pages):
        raise ImpactRuntimeUnavailable()
    page = pages[index]
    next_cursor = sign_cursor(scope, "page", index + 1) if index + 1 < len(pages) else None
    sources = [target_source(current.binding), *(
        target_source(current.binding, node_id) for node_id in sorted({
            node_id for e in page.elements for node_id in (e.node_id, e.source_id, e.target_id) if node_id is not None
        })
    )]
    body = page.projection_bytes()
    receipt_id = await record_release(db, scope, module="fmea", body=body,
        element_keys=(e.accounting_key for e in page.elements), sources=sources,
        page_key=page.key, expected_page_digests=canonical_page_digests(pages), next_cursor=next_cursor)
    response = release_envelope(scope, receipt_id, body, page_key=page.key, cursor=next_cursor)
    await db.commit()
    return response


async def confirm_projection(
    db, current: ImpactRuntime, *, release_id: UUID, page_key: str, payload_digest: str, token: str,
) -> dict:
    receipt = AgentPfmeaImpactReceipt
    release = await db.scalar(select(receipt).where(
        receipt.receipt_id == release_id, receipt.kind == "release", receipt.page_key == page_key,
        receipt.task_id == current.task.task_id, receipt.run_id == current.run.run_id,
        receipt.lease_epoch == current.epoch,
    ))
    if release is None or not isinstance(release.payload, dict):
        raise ImpactRuntimeUnavailable()
    scope_ref = release.payload.get("scope_ref")
    scope = _scope(current, scope_ref)
    expected = canonical_page_digests(_step_plan(current, scope_ref))
    confirmation_id = await record_confirmation(db, scope, release_id=release_id,
        page_key=page_key, payload_digest=payload_digest, token=token, expected_page_digests=expected)
    try:
        coverage = await record_coverage(db, scope, expected_page_digests=expected)
    except IncompleteCoverage:
        coverage = None
    response = {
        "task_id": str(scope.task_id), "run_id": str(scope.run_id), "lease_epoch": scope.lease_epoch,
        "confirmation_id": str(confirmation_id), "coverage_id": str(coverage) if coverage is not None else None,
    }
    await db.commit()
    return response
