import uuid
import pytest
from datetime import date

from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.management_review import ManagementReview
from app.services import management_review_report_service as report_service
from app.services.agent import provider_adapter


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


async def _review(db, default_factory, user=None):
    owner_id = user.user_id if user else uuid.uuid4()
    review = ManagementReview(
        doc_no=f"MR-TEST-{uuid.uuid4().hex[:8]}",
        title="Test Review",
        review_date=date(2026, 6, 11),
        chair_person_id=owner_id,
        created_by=owner_id,
        factory_id=default_factory.id,
        status="data_collected",
        data_package={"quality_goals": {"total": 1, "achieved": 1}},
    )
    db.add(review)
    await db.flush()
    return review


class _PC:
    model = "test-model"


@pytest.mark.asyncio
async def test_enrich_returns_section_outcome(db, default_factory, admin_user, monkeypatch):
    """_enrich_with_llm returns (sections, section_attempted, section_failed_keys)."""
    from app.services.management_review_report_service import _enrich_with_llm
    async def _ok(pc, prompt, schema):
        return {"analysis": "a", "findings": ["f"], "recommendations": ["r"]}
    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    sections = [{"key": "k1", "title": "t1", "base_text": "b1"},
                {"key": "k2", "title": "t2", "base_text": "b2"}]
    out_sections, attempted, failed_keys = await _enrich_with_llm(
        sections, await _review(db, default_factory, admin_user), _PC(), None
    )
    assert attempted == 2 and failed_keys == []


@pytest.mark.asyncio
async def test_enrich_tracks_failed_sections(db, default_factory, admin_user, monkeypatch):
    from app.services.management_review_report_service import _enrich_with_llm
    calls = {"n": 0}
    async def _boom_on_second(pc, prompt, schema):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return {"analysis": "a", "findings": [], "recommendations": []}
    monkeypatch.setattr(provider_adapter, "complete_json", _boom_on_second)
    sections = [{"key": "k1", "title": "t1", "base_text": "b1"},
                {"key": "k2", "title": "t2", "base_text": "b2"}]
    _, attempted, failed_keys = await _enrich_with_llm(
        sections, await _review(db, default_factory, admin_user), _PC(), None
    )
    assert attempted == 2 and failed_keys == ["k2"]


@pytest.mark.asyncio
async def test_generate_report_writes_success_audit(db, default_factory, admin_user, monkeypatch):
    async def _ok_client(db_arg):
        return _PC()
    async def _ok(pc, prompt, schema):
        # section schema vs summary schema — return plausible dict for either
        return {"analysis": "a", "findings": [], "recommendations": [],
                "executive_summary": "s", "overall_recommendations": []}
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    from app.services.management_review_report_service import generate_report
    review = await _review(db, default_factory, admin_user)
    content = await generate_report(db, review, admin_user, use_llm=True,
                                    report_llm_timeout=None, tenant_schema="public")
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_report_generate")
        .where(AuditLog.record_id == review.review_id)
    )).scalars().all()
    assert any(r.new_values.get("status") == "success" for r in rows), rows
    assert rows[0].tenant_schema == "public"
    # CRUD audit still present
    crud = (await db.execute(
        select(AuditLog).where(AuditLog.action == "REPORT_GENERATE")
    )).scalars().all()
    assert len(crud) >= 1


@pytest.mark.asyncio
async def test_generate_report_llm_failed_audit_with_detail(db, default_factory, admin_user, monkeypatch):
    async def _ok_client(db_arg):
        return _PC()
    async def _boom(pc, prompt, schema):
        raise RuntimeError("down")
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _boom)
    from app.services.management_review_report_service import generate_report
    review = await _review(db, default_factory, admin_user)
    content = await generate_report(db, review, admin_user, use_llm=True,
                                    report_llm_timeout=None, tenant_schema="public")
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_report_generate")
    )).scalars().all()
    assert any(r.new_values.get("status") == "llm_failed" for r in rows)
    # failed detail present (section_failed_keys non-empty and/or summary_failed True)
    assert any(
        r.new_values.get("section_failed_keys") or r.new_values.get("summary_failed")
        for r in rows
    )


@pytest.mark.asyncio
async def test_generate_report_pc_none_no_audit_no_attribute_error(db, default_factory, admin_user, monkeypatch):
    async def _raise(db_arg):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    from app.services.management_review_report_service import generate_report
    review = await _review(db, default_factory, admin_user)
    # Must not raise AttributeError on pc.model when pc is None
    content = await generate_report(db, review, admin_user, use_llm=True,
                                    report_llm_timeout=None, tenant_schema="public")
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_report_generate")
    )).scalars().all()
    assert rows == []


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

    content = await report_service.generate_report(db, review, admin_user)
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
