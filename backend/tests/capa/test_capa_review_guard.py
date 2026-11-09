"""Outcome-review parent-lock and material-write guard tests."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.capa_review_errors import register_capa_review_errors
from app.main import app as production_app
from app.services.capa_review_guard import (
    OutcomeReviewConflict,
    OutcomeReviewLimit,
    OutcomeReviewRequired,
    ReviewedContentLocked,
    lock_material_write,
)

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["D8_CLOSURE", "ARCHIVED"])
@pytest.mark.parametrize("field", [
    "d4_root_cause", "d5_correction", "d6_verification",
    "d7_prevention", "fmea_ref_id", "fmea_node_id", "severity",
])
async def test_closed_core_material_fields_are_locked(review_case, status, field):
    """Would fail if a reviewed CAPA accepted a protected material field."""
    await review_case.set_status(status)
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
            await lock_material_write(db, capa, {field})


@pytest.mark.asyncio
async def test_closed_child_or_association_write_without_field_set_is_locked(review_case):
    """Would fail if a closed CAPA allowed a child or association mutation."""
    await review_case.set_status("D8_CLOSURE")
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
            await lock_material_write(db, capa)


@pytest.mark.asyncio
async def test_closed_explicit_null_core_field_is_locked(review_case):
    """Would fail if an explicit null bypassed the material-field lock."""
    await review_case.set_status("ARCHIVED")
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
            await lock_material_write(db, capa, {"supplier_id"})


@pytest.mark.asyncio
async def test_d8_closure_supplement_is_not_a_reviewed_core_field(review_case):
    """Would fail if the review guard blocked the D8 closure supplement exception."""
    await review_case.set_status("D8_CLOSURE")
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        fresh = await lock_material_write(db, capa, {"d8_closure"})
    assert fresh.status == "D8_CLOSURE"


@pytest.mark.asyncio
async def test_pending_capa_remains_materially_writable(review_case):
    """Would fail if the guard froze a CAPA before review completion."""
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        fresh = await lock_material_write(db, capa, {"d4_root_cause"})
    assert fresh.status == "D8_APPROVAL_PENDING"


@pytest.mark.asyncio
async def test_parent_lock_refreshes_stale_identity_map_before_allowing_write(review_case):
    """Would fail if a stale pending object bypassed a newly reviewed state."""
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        await db.execute(text(
            "UPDATE capa_eightd SET status = 'D8_CLOSURE' WHERE report_id = :report_id"
        ), {"report_id": review_case.report_id})
        assert capa.status == "D8_APPROVAL_PENDING"
        with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
            await lock_material_write(db, capa, {"d5_correction"})


@pytest.mark.asyncio
@pytest.mark.parametrize("status, fields", [
    ("D8_CLOSURE", {"d4_root_cause"}),
    ("ARCHIVED", None),
])
async def test_rejected_material_write_has_no_committed_or_transactional_side_effects(
    review_case, status, fields,
):
    """Would fail if a rejected reviewed-material write changed data or committed it."""
    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        transaction = db.sync_session.get_transaction()
        with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
            await lock_material_write(db, capa, fields)
        assert db.sync_session.get_transaction() is transaction
        assert transaction.is_active
        assert await review_case.snapshot(db) == before
        await db.rollback()
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("status, fields", [
    ("D8_APPROVAL_PENDING", {"d4_root_cause"}),
    ("D8_CLOSURE", {"d8_closure"}),
])
async def test_permitted_guard_path_has_no_unrelated_side_effects(review_case, status, fields):
    """Would fail if a permitted guard check changed material, audit, embedding, or outbox state."""
    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        transaction = db.sync_session.get_transaction()
        fresh = await lock_material_write(db, capa, fields)
        assert fresh.status == status
        assert db.sync_session.get_transaction() is transaction
        assert transaction.is_active
        assert await review_case.snapshot(db) == before
        await db.rollback()
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type, code", [
    (ReviewedContentLocked, "CAPA_REVIEWED_CONTENT_LOCKED"),
    (OutcomeReviewConflict, "CAPA_OUTCOME_REVIEW_CHANGED"),
    (OutcomeReviewRequired, "CAPA_OUTCOME_REVIEW_REQUIRED"),
    (OutcomeReviewLimit, "CAPA_OUTCOME_REVIEW_LIMIT"),
])
async def test_registered_review_errors_return_only_fixed_409_code(error_type, code):
    """Would fail if a review error exposed free text or a non-conflict response."""
    test_app = FastAPI()
    register_capa_review_errors(test_app)

    @test_app.get("/raise")
    async def raise_review_error():
        raise error_type()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/raise")

    assert response.status_code == 409
    assert response.json() == {"detail": code}
    assert error_type in production_app.exception_handlers
