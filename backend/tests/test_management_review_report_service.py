import uuid
import pytest
from datetime import date

from app.models.management_review import ManagementReview
from app.services import management_review_report_service as report_service


@pytest.mark.asyncio
async def test_build_sections_maps_data_package():
    data_package = {
        "quality_goals": {"total": 5, "achieved": 3, "behind": 1},
        "previous_review_actions": {"total_outputs": 10, "completed": 8},
    }
    manual_inputs = {
        "external_factors": "市场竞争加剧",
        "customer_satisfaction": {"summary": "客户满意度 92%"},
    }
    sections = report_service._build_sections(data_package, manual_inputs)
    keys = [s["key"] for s in sections]
    assert len(sections) == 13
    assert "quality_goals" in keys
    assert "external_factors" in keys
    quality_section = next(s for s in sections if s["key"] == "quality_goals")
    assert "5" in quality_section["base_text"]
    external_section = next(s for s in sections if s["key"] == "external_factors")
    assert "市场竞争加剧" in external_section["base_text"]


@pytest.mark.asyncio
async def test_generate_report_creates_draft(db, admin_user):
    review = ManagementReview(
        doc_no=f"MR-TEST-{uuid.uuid4().hex[:8]}",
        title="Test Review",
        review_date=date(2026, 6, 11),
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
        factory_id=admin_user.factory_id,
        status="data_collected",
        data_package={"quality_goals": {"total": 1, "achieved": 1}},
    )
    db.add(review)
    await db.flush()

    content = await report_service.generate_report(db, review, admin_user, llm_provider=None)
    assert review.report_status == "draft"
    assert review.generated_report is not None
    assert len(content["sections"]) == 13


@pytest.mark.asyncio
async def test_save_draft_does_not_create_version(db, admin_user):
    review = ManagementReview(
        doc_no=f"MR-TEST-{uuid.uuid4().hex[:8]}",
        title="Test Review",
        review_date=date(2026, 6, 11),
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
        factory_id=admin_user.factory_id,
        status="data_collected",
        report_status="draft",
        generated_report={"sections": []},
    )
    db.add(review)
    await db.flush()

    await report_service.save_report_draft(db, review, {"sections": [{"key": "x"}]}, admin_user)
    versions = await report_service.list_report_versions(db, review.review_id)
    assert len(versions) == 0


@pytest.mark.asyncio
async def test_finalize_creates_version_snapshot(db, admin_user):
    review = ManagementReview(
        doc_no=f"MR-TEST-{uuid.uuid4().hex[:8]}",
        title="Test Review",
        review_date=date(2026, 6, 11),
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
        factory_id=admin_user.factory_id,
        status="data_collected",
        report_status="draft",
        generated_report={"sections": []},
    )
    db.add(review)
    await db.flush()

    snapshot = await report_service.finalize_report(db, review, admin_user)
    assert snapshot.version_no == 1
    assert review.report_status == "final"

    # second finalize after reopen
    review2 = await report_service.reopen_report_to_draft(db, review, admin_user)
    assert review2.report_status == "draft"
    snapshot2 = await report_service.finalize_report(db, review2, admin_user)
    assert snapshot2.version_no == 2


@pytest.mark.asyncio
async def test_finalize_requires_draft(db, admin_user):
    review = ManagementReview(
        doc_no=f"MR-TEST-{uuid.uuid4().hex[:8]}",
        title="Test Review",
        review_date=date(2026, 6, 11),
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
        factory_id=admin_user.factory_id,
        status="data_collected",
        report_status="none",
    )
    db.add(review)
    await db.flush()

    with pytest.raises(ValueError, match="only draft report can be finalized"):
        await report_service.finalize_report(db, review, admin_user)


@pytest.mark.asyncio
async def test_closed_review_cannot_edit_report(db, admin_user):
    review = ManagementReview(
        doc_no=f"MR-TEST-{uuid.uuid4().hex[:8]}",
        title="Test Review",
        review_date=date(2026, 6, 11),
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
        factory_id=admin_user.factory_id,
        status="closed",
        report_status="draft",
        generated_report={"sections": []},
    )
    db.add(review)
    await db.flush()

    with pytest.raises(ValueError, match="closed review"):
        await report_service.save_report_draft(db, review, {"sections": []}, admin_user)
