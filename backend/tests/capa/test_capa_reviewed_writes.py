"""Reviewed CAPA materials reject every writer before side effects."""

import pytest

from app.schemas.capa_verification import (
    AdoptRequest,
    D7AutoFillRequest,
    D7NodeActionCreate,
    VerificationCreate,
    VerificationUpdate,
)
from app.services.capa_review_guard import ReviewedContentLocked

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["D8_CLOSURE", "ARCHIVED"])
async def test_core_writer_paths_reject_reviewed_capa_before_side_effects(review_case, status):
    """Would fail if a closed CAPA writer mutated material, audit, or outbox data."""
    from app.models.user import User
    from app.services.capa_d7_action_service import auto_fill_d7, record_d7_action
    from app.services.capa_doc_gate_service import (
        _phase1_create_running,
        confirm_no_affected,
        record_defer,
        record_gate_waiver,
        run_audit,
    )
    from app.services.capa_service import link_fmea, update_capa
    from app.services.capa_verification_service import (
        adopt_recommendation,
        create_verification,
        update_verification,
    )

    await review_case.set_status(status)
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        user = await db.get(User, review_case.actor_id)
        writers = (
            lambda: update_capa(db, capa, {"d4_root_cause": "未审核改写"}, user.user_id),
            lambda: link_fmea(db, capa, review_case.report_id, user.user_id),
            lambda: adopt_recommendation(db, capa, AdoptRequest(
                d_step="d5", adopted_text="未审核追加", source="manual"), user),
            lambda: create_verification(db, capa, VerificationCreate(
                root_cause_text="未审核根因"), user),
            lambda: update_verification(db, capa, review_case.verification_id,
                                        VerificationUpdate(result="未审核证据"), user),
            lambda: record_d7_action(db, capa, D7NodeActionCreate(
                action="confirmed", failure_mode_node_id="missing", match_source="manual"), user),
            lambda: auto_fill_d7(db, capa, D7AutoFillRequest(
                fmea_id=review_case.report_id, failure_mode_node_id="missing",
                failure_cause_node_id="missing", match_source="manual"), user),
            lambda: _phase1_create_running(db, capa, user.user_id),
            lambda: run_audit(db, capa, user.user_id),
            lambda: record_defer(db, capa, "未审核延期", user.user_id, "2026-12-31", user.user_id),
            lambda: confirm_no_affected(db, capa, user.user_id),
            lambda: record_gate_waiver(db, capa, "未审核豁免", [{"target_key": "missing"}], user.user_id),
        )
        for write in writers:
            with pytest.raises(ReviewedContentLocked, match="^CAPA_REVIEWED_CONTENT_LOCKED$"):
                await write()
            assert await review_case.snapshot(db) == before
        await db.rollback()
    assert await review_case.snapshot() == before
