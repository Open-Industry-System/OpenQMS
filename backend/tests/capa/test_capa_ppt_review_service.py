import uuid

import pytest

from app.models.capa import CAPAEightD
from app.services import agent_review_skill_service, capa_ppt_review_service, capa_ppt_service
from app.services.agent import provider_adapter
from app.services.capa_ppt_service import PptContent, PptPage

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
    """首轮不通过 + LLM 校正 + 第 2 轮通过 → passed, rounds=2。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    review_calls = {"n": 0}

    async def _mock(pc, prompt, response_schema):
        if "passed" in response_schema.get("properties", {}):  # 审查调用
            review_calls["n"] += 1
            return {"passed": review_calls["n"] >= 2, "issues": ["issue1"], "suggestions": ["fix1"]}
        # 校正调用 → 返回空 pages → 回退原内容（不破坏结构）
        return {"pages": []}

    monkeypatch.setattr(provider_adapter, "complete_json", _mock)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    assert review.status == "passed"
    assert review.rounds == 2


async def test_needs_review_after_3_rounds(db, admin_user, default_factory, monkeypatch):
    """3 轮全不通过 → needs_review, rounds=3, 返回最后审查报告。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)

    async def _mock(pc, prompt, response_schema):
        if "passed" in response_schema.get("properties", {}):  # 审查调用
            return {"passed": False, "issues": ["i"], "suggestions": ["s"]}
        return {"pages": []}  # 校正回退原内容

    monkeypatch.setattr(provider_adapter, "complete_json", _mock)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    assert review.status == "needs_review"
    assert review.rounds == 3
    assert review.report == {"issues": ["i"], "suggestions": ["s"]}


def _base_content():
    return PptContent(
        capa_id=uuid.uuid4(),
        pages=[PptPage("A", [{"label": "x", "value": "1"}]), PptPage("B", [{"label": "y", "value": "2"}])],
        linked_fmea_node=None, linked_scars=[], linked_risk_alerts=[], root_cause_verifications=[],
    )


def test_apply_revised_pages_applies_values_preserves_linked():
    """LLM 修订有效 → 各页 value 改写，落库事实（linked_*）保留不变。"""
    base = _base_content()
    revised = [
        {"title": "A", "sections": [{"label": "x", "value": "1R"}]},
        {"title": "B", "sections": [{"label": "y", "value": "2"}]},
    ]
    out = capa_ppt_review_service._apply_revised_pages(base, revised)
    assert out.pages[0].sections[0]["value"] == "1R"   # 改写
    assert out.pages[1].sections[0]["value"] == "2"     # 未动
    assert out.linked_fmea_node is None and out.linked_scars == []  # 落库事实保留
    assert out.capa_id == base.capa_id


def test_apply_revised_pages_wrong_count_falls_back():
    """修订页数不符 → 回退原内容（不破坏结构）。"""
    base = _base_content()
    out = capa_ppt_review_service._apply_revised_pages(base, [{"title": "A", "sections": []}])
    assert out is base  # 回退，返回原对象


def test_apply_revised_pages_title_mismatch_falls_back():
    """修订标题对不上 → 回退原内容。"""
    base = _base_content()
    revised = [
        {"title": "WRONG", "sections": [{"label": "x", "value": "1R"}]},
        {"title": "B", "sections": [{"label": "y", "value": "2"}]},
    ]
    out = capa_ppt_review_service._apply_revised_pages(base, revised)
    assert out is base


def test_apply_revised_pages_section_count_mismatch_falls_back():
    """LLM 删除 section（section 数量变化）→ 回退原内容，不允许删 D4 验证等。"""
    base = _base_content()
    revised = [
        {"title": "A", "sections": []},  # 删除了 x section
        {"title": "B", "sections": [{"label": "y", "value": "2"}]},
    ]
    out = capa_ppt_review_service._apply_revised_pages(base, revised)
    assert out is base


def test_apply_revised_pages_label_changed_falls_back():
    """LLM 修改 label → 回退原内容（不允许改标签）。"""
    base = _base_content()
    revised = [
        {"title": "A", "sections": [{"label": "CHANGED", "value": "1R"}]},
        {"title": "B", "sections": [{"label": "y", "value": "2"}]},
    ]
    out = capa_ppt_review_service._apply_revised_pages(base, revised)
    assert out is base


def test_apply_revised_pages_added_section_falls_back():
    """LLM 新增 section（含编造事实）→ section 数量变化 → 回退原内容。"""
    base = _base_content()
    revised = [
        {"title": "A", "sections": [{"label": "x", "value": "1"}, {"label": "fabricated", "value": "fake"}]},
        {"title": "B", "sections": [{"label": "y", "value": "2"}]},
    ]
    out = capa_ppt_review_service._apply_revised_pages(base, revised)
    assert out is base


async def test_correction_empties_d_page_falls_back_via_rule_revalidation(
    db, admin_user, default_factory, monkeypatch
):
    """LLM 校正清空某 D 页 value → _apply 通过结构（label/数量一致）但规则再校验失败 → 回退原内容。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    base = await capa_ppt_service.generate_content(db, capa.report_id)
    # 构造「结构合法但 D3 value 被清空」的修订：保持 label/数量，仅清空 D3 的 value
    revised_pages = []
    for p in base.pages:
        secs = []
        for s in p.sections:
            val = "" if p.title == "D3 遏制措施" else s["value"]
            secs.append({"label": s["label"], "value": val})
        revised_pages.append({"title": p.title, "sections": secs})

    review_calls = {"n": 0}

    async def _mock(pc, prompt, response_schema):
        if "passed" in response_schema.get("properties", {}):
            review_calls["n"] += 1
            return {"passed": review_calls["n"] >= 2, "issues": ["i"], "suggestions": ["s"]}
        return {"pages": revised_pages}  # 校正清空 D3

    monkeypatch.setattr(provider_adapter, "complete_json", _mock)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    # 校正清空 D3 → 规则再校验失败 → 回退原内容（D3 仍非空）→ 最终 review 看原内容
    d3 = next(p for p in content.pages if p.title == "D3 遏制措施")
    assert d3.sections[0]["value"] == "d3", "校正清空 D3 应被规则再校验拒绝并回退原内容"


async def test_corrected_content_forced_needs_review_not_passed(
    db, admin_user, default_factory, monkeypatch
):
    """LLM 校正被采用（结构合法、规则通过，但篡改事实如 D8 关闭结论）+ 后续轮 LLM 自判 passed
    → 仍强制 needs_review（不自动 passed），报告标注需人工复核（§101「不编造数据」）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    base = await capa_ppt_service.generate_content(db, capa.report_id)
    # 篡改 D8 关闭结论：label/数量/结构保持，规则校验通过（非空），但 value 为虚构文本
    revised_pages = []
    for p in base.pages:
        secs = [
            {"label": s["label"], "value": ("虚构客户已确认验收" if p.title == "D8 关闭结论" else s["value"])}
            for s in p.sections
        ]
        revised_pages.append({"title": p.title, "sections": secs})

    review_calls = {"n": 0}

    async def _mock(pc, prompt, response_schema):
        if "passed" in response_schema.get("properties", {}):
            review_calls["n"] += 1
            return {"passed": review_calls["n"] >= 2, "issues": [], "suggestions": ["补充关闭确认"]}
        return {"pages": revised_pages}  # 校正篡改 D8

    monkeypatch.setattr(provider_adapter, "complete_json", _mock)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    # 第 2 轮 LLM 自判 passed，但因内容经 LLM 校正 → 强制 needs_review，不得自动 passed
    assert review.status == "needs_review", "采用 LLM 校正后的内容不得自动标记 passed"
    assert review.rounds == 2
    d8 = next(p for p in content.pages if p.title == "D8 关闭结论")
    assert "虚构客户已确认验收" in d8.sections[0]["value"]  # 校正被采用（内容已改）
    assert any("人工复核" in i for i in review.report["issues"]), "报告须标注需人工复核"


async def test_uncorrected_pass_still_passed(db, admin_user, default_factory, monkeypatch):
    """无校正（首轮即通过，内容 DB-faithful）→ 仍可 passed（不误伤：仅校正过的才强制 needs_review）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)

    async def _mock(pc, prompt, response_schema):
        return {"passed": True, "issues": [], "suggestions": []}

    monkeypatch.setattr(provider_adapter, "complete_json", _mock)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    assert review.status == "passed"
    assert review.rounds == 1


async def test_correction_llm_failure_falls_back_not_500(db, admin_user, default_factory, monkeypatch):
    """校正 LLM 异常 → 回退原内容（不上抛 500），审查报告保留；最终 needs_review。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)

    async def _mock(pc, prompt, response_schema):
        if "passed" in response_schema.get("properties", {}):
            return {"passed": False, "issues": ["i"], "suggestions": ["s"]}
        raise RuntimeError("correction boom")  # 校正异常

    monkeypatch.setattr(provider_adapter, "complete_json", _mock)
    content, review = await capa_ppt_review_service.review_and_correct(
        db, capa.report_id, _PC(), "public",
    )
    # 校正异常未上抛；3 轮审查均不通过 → needs_review + 报告
    assert review.status == "needs_review"
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
