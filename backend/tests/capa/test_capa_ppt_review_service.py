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
        d1_team=[{"name": "张三", "role": "负责人"}],
        d2_description="d2", d3_interim="d3", d4_root_cause="d4", d5_correction="d5",
        d6_verification="d6", d7_prevention="d7", d8_closure="d8",
    )
    db.add(capa)
    await db.flush()
    return capa


class _PC:
    pass  # fake provider client


async def test_skipped_when_clean_and_llm_off(db, admin_user, default_factory):
    """完整 CAPA + pc=None → skipped, report=None（无规则 issues，无 LLM）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, None, "public",
    )
    assert review.status == "skipped"
    assert review.rounds == 0
    assert review.report is None


async def test_rule_issues_return_needs_review(db, admin_user, default_factory):
    """残留规则 issues（D1 空，校正无法补全）→ needs_review + 报告暴露（不静默 skipped，§92 内容不完整）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    capa.d1_team = []  # D1 空 → 规则 issue，校正（重新查数据）无法补全
    await db.flush()
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, None, "public",
    )
    assert review.status == "needs_review"
    assert review.rounds == 0
    assert review.report is not None
    assert any("D1" in i for i in review.report["issues"])


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


async def test_llm_exception_raises_failed(db, admin_user, default_factory, monkeypatch):
    """LLM 运行时异常（非未配置）→ 审查闭环异常应失败（抛出），不降级为 needs_review（故事 §92）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)

    async def _boom(pc, prompt, response_schema):
        raise RuntimeError("boom")

    monkeypatch.setattr(provider_adapter, "complete_json", _boom)
    with pytest.raises(RuntimeError):
        await capa_ppt_review_service.review_and_correct(
            db, capa.report_id, _PC(), "public",
        )


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
