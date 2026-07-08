import uuid

import pytest

from app.models.capa import CAPAEightD
from app.services import agent_review_skill_service, capa_ppt_review_service, capa_ppt_service
from app.services.agent import provider_adapter

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no="8D-REV-001", title="t",
        product_line_code="DC-DC-100", factory_id=factory_id, created_by=user_id,
        status="D8_CLOSURE",
        d2_description="d2", d3_interim="d3", d4_root_cause="d4", d5_correction="d5",
        d6_verification="d6", d7_prevention="d7", d8_closure="d8",
    )
    db.add(capa)
    await db.flush()
    return capa


class _PC:
    pass  # fake provider client


async def test_skip_when_llm_not_configured(db, admin_user, default_factory):
    """pc=None → review_status=skipped, rounds=0, 不调 LLM。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, None, "public",
    )
    assert review.status == "skipped"
    assert review.rounds == 0
    assert review.report is None


async def test_pass_first_round(db, admin_user, default_factory, monkeypatch):
    """LLM 首轮通过 → passed, rounds=1。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)

    async def _ok(pc, prompt, response_schema):
        return {"passed": True, "issues": [], "suggestions": []}

    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    assert review.status == "passed"
    assert review.rounds == 1


async def test_pass_after_correction(db, admin_user, default_factory, monkeypatch):
    """首轮不通过 + 第 2 轮通过 → passed, rounds=2。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    calls = {"n": 0}

    async def _ok(pc, prompt, response_schema):
        calls["n"] += 1
        return {"passed": calls["n"] >= 2, "issues": ["issue1"], "suggestions": ["fix1"]}

    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    assert review.status == "passed"
    assert review.rounds == 2


async def test_needs_review_after_3_rounds(db, admin_user, default_factory, monkeypatch):
    """3 轮全不通过 → needs_review, rounds=3, 返回报告。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)

    async def _fail(pc, prompt, response_schema):
        return {"passed": False, "issues": ["i"], "suggestions": ["s"]}

    monkeypatch.setattr(provider_adapter, "complete_json", _fail)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    assert review.status == "needs_review"
    assert review.rounds == 3
    assert review.report == {"issues": ["i"], "suggestions": ["s"]}


async def test_llm_exception_continues(db, admin_user, default_factory, monkeypatch):
    """LLM 异常该轮失败继续；3 轮全失败 → needs_review。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)

    async def _boom(pc, prompt, response_schema):
        raise RuntimeError("boom")

    monkeypatch.setattr(provider_adapter, "complete_json", _boom)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    assert review.status == "needs_review"
    assert review.rounds == 3


async def test_skill_not_configured_reports_config_issue(db, admin_user, default_factory, monkeypatch):
    """skill 未配置（get_by_name 返回 None）→ needs_review + 报具体配置问题（不掩盖成 LLM 异常）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)

    async def _no_skill(db, tenant_schema, name):
        return None

    monkeypatch.setattr(agent_review_skill_service, "get_by_name", _no_skill)
    # complete_json 不应被调用（skill is None 时短路）
    async def _should_not_call(pc, prompt, response_schema):
        raise AssertionError("complete_json should not be called when skill is None")

    monkeypatch.setattr(provider_adapter, "complete_json", _should_not_call)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    assert review.status == "needs_review"
    assert review.rounds == 0
    assert review.report is not None
    assert any("skill" in i.lower() for i in review.report["issues"])
