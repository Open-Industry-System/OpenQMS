"""PPT sub-agent 审查 + 校正闭环（US-E2E-01.10）。

只返回 (PptContent, ReviewResult)，不渲染 pptx——最终渲染在 API 层做一次。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import agent_review_skill_service, capa_ppt_service, capa_service
from app.services.capa_ppt_service import PptContent, PptPage
from app.services.agent import provider_adapter


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["passed", "issues", "suggestions"],
}


# 校正输出：仅各页 section 的 value（呈现层），不动 linked/verification 等落库事实
CORRECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["label", "value"],
                        },
                    },
                },
                "required": ["title", "sections"],
            },
        }
    },
    "required": ["pages"],
}


@dataclass
class ReviewOutcome:
    passed: bool
    issues: list[str]
    suggestions: list[str]

    @property
    def report(self) -> dict:
        return {"issues": self.issues, "suggestions": self.suggestions}


@dataclass
class ReviewResult:
    status: str           # passed/skipped/needs_review
    rounds: int           # 0=未审查/跳过，1-3=审查轮数
    report: dict | None   # {"issues":[...], "suggestions":[...]} 或 None（skipped）


async def review_and_correct(
    db: AsyncSession, capa_id: uuid.UUID, pc, tenant_schema: str,
) -> tuple[PptContent, ReviewResult]:
    """生成 → 审查 → 校正闭环，3 轮上限。pc=None 表示 LLM 未配置。返回 (content, review)。"""
    capa = await capa_service.get_capa(db, capa_id)
    if capa is None:
        raise ValueError("CAPA 不存在")
    content = await capa_ppt_service.generate_content(db, capa_id)

    # 1. 内置规则校验（不耗 LLM 轮次）
    rule_issues = capa_ppt_service._validate_ppt_content(content, capa)
    if rule_issues:
        content = await _correct_by_issues(db, capa_id, rule_issues)
        # 校正后重新校验；若仍存在（数据缺失无法自动补全，§101 不编造数据），保留以暴露
        rule_issues = capa_ppt_service._validate_ppt_content(content, capa)

    # 残留规则 issues = 结构/数据缺口，校正（重新查数据，§46）无法补全 → needs_review 并暴露报告；
    # 不静默 skipped，也不耗 LLM 轮次（数据缺失 LLM 亦无法修复，跑 3 轮等同空耗）。
    if rule_issues:
        return content, ReviewResult("needs_review", 0, {"issues": rule_issues, "suggestions": []})

    # 2. 无规则 issues：LLM 未配置 → 跳过 sub-agent 审查
    if pc is None:
        return content, ReviewResult("skipped", 0, None)

    # 3. LLM 审查闭环（3 轮上限）
    skill = await agent_review_skill_service.get_by_name(db, tenant_schema, "capa_ppt_review")
    if skill is None:
        # skill 未配置/未 seed —— 不掩盖成 "LLM 调用异常"，直接报具体配置问题
        return content, ReviewResult("needs_review", 0, {
            "issues": ["审查 skill 未配置（capa_ppt_review），请管理员配置或检查 seed"],
            "suggestions": [],
        })
    last_report: dict = {"issues": [], "suggestions": []}
    corrected = False  # 是否采用了 LLM 校正后的内容（采用 → 不得自动 passed，强制 needs_review）
    for round_idx in range(1, 4):
        # 审查闭环异常（超时/鉴权/响应格式）属故事 §92 FAILED 条件，不在此吞掉降级为 needs_review；
        # 让异常上抛，由 API 层转为 500。LLM 未配置（ProviderNotConfigured）已在 API 层 pc=None 处理为 skipped。
        review = await _subagent_review(pc, skill, content)
        last_report = review.report
        if review.passed:
            if corrected:
                # 内容经 LLM 自动校正（§101「不编造数据」无法用结构校验保证事实真实）→
                # 不自动标记 passed，强制 needs_review + 标注需人工复核确认未编造数据。
                last_report = {
                    "issues": list(last_report.get("issues", [])) + ["内容经 LLM 自动校正，需人工复核确认未编造数据"],
                    "suggestions": last_report.get("suggestions", []),
                }
                return content, ReviewResult("needs_review", round_idx, last_report)
            return content, ReviewResult("passed", round_idx, last_report)
        if round_idx < 3:
            corrected_content = await _correct_by_suggestions(pc, skill, content, review.suggestions)
            # 仅当校正产生了「新内容且通过规则校验」才采用并标记 corrected（回退原内容不计）
            if corrected_content is not content and not capa_ppt_service._validate_ppt_content(corrected_content, capa):
                content = corrected_content
                corrected = True
            # else: 校正回退原内容（结构不符/LLM 异常）或破坏规则 → 保留原 content，corrected 不变
        else:
            return content, ReviewResult("needs_review", 3, last_report)


async def _subagent_review(pc, skill, content) -> ReviewOutcome:
    """构造审查 prompt = skill.content + PptContent 序列化 → LLM → 解析。"""
    prompt = f"{skill.content}\n\n--- 待审查 PPT 内容 ---\n{_serialize_content(content)}"
    result = await provider_adapter.complete_json(pc, prompt, REVIEW_SCHEMA)
    return ReviewOutcome(
        passed=result["passed"], issues=result["issues"], suggestions=result["suggestions"],
    )


async def _subagent_correct(pc, skill, content, suggestions) -> PptContent:
    """LLM 按 suggestions 重写各页 section 的 value（呈现层）。

    约束（故事 §101「不编造数据」）：仅改写已存在内容的呈现，不得添加输入中不存在的
    事实；保持 11 页结构与 label 不变；linked_fmea_node/scars/alerts/verifications
    等落库事实不动。结构不符（页数/标题对不上）→ 回退原内容（不破坏），下一轮审查原内容。
    """
    sug_text = "\n".join(f"- {s}" for s in suggestions) or "- (无具体建议)"
    prompt = (
        f"{skill.content}\n\n--- 待校正 PPT 内容 ---\n{_serialize_content(content)}"
        f"\n\n--- 审查建议 ---\n{sug_text}"
        "\n\n请据此修订各页 section 的 value 以回应建议。约束：仅改写已存在内容的呈现，"
        "不得添加输入中不存在的事实（不编造数据）；保持页数与各页 title/label 不变。"
        "输出 JSON: {pages: [{title, sections: [{label, value}]}]}"
    )
    result = await provider_adapter.complete_json(pc, prompt, CORRECTION_SCHEMA)
    return _apply_revised_pages(content, result.get("pages", []))


def _apply_revised_pages(content: PptContent, revised_pages: list) -> PptContent:
    """将 LLM 修订的 pages 应用回 PptContent。

    严格结构保护（防止 LLM 破坏 PPT 结构）：页数、各页 title、各页 section 数量、label
    序列必须与原内容完全一致；任一不符 → 回退原内容（不删除 section、不改 label、不新增）。
    仅允许改写各 section 的 value（呈现层）。语义校验（必填非空等）由调用方重新跑
    _validate_ppt_content 兜底。
    """
    if not revised_pages or len(revised_pages) != len(content.pages):
        return content
    revised = []
    for orig, rev in zip(content.pages, revised_pages):
        if rev.get("title") != orig.title:
            return content
        rev_sections = rev.get("sections") or []
        orig_labels = [s["label"] for s in orig.sections]
        rev_labels = [s.get("label", "") for s in rev_sections]
        # section 数量与 label 序列必须一致（不允许删除/新增/改 label）
        if len(rev_sections) != len(orig.sections) or rev_labels != orig_labels:
            return content
        revised.append(PptPage(title=orig.title, sections=[
            {"label": s.get("label", ""), "value": s.get("value", "")} for s in rev_sections
        ]))
    return PptContent(
        capa_id=content.capa_id, pages=revised,
        linked_fmea_node=content.linked_fmea_node, linked_scars=content.linked_scars,
        linked_risk_alerts=content.linked_risk_alerts,
        root_cause_verifications=content.root_cause_verifications,
    )


def _serialize_content(content) -> str:
    """PptContent 序列化为 LLM 可读文本。"""
    lines = []
    for p in content.pages:
        lines.append(f"## {p.title}")
        for s in p.sections:
            lines.append(f"- {s['label']}: {s['value']}")
    return "\n".join(lines)


async def _correct_by_issues(db, capa_id, issues) -> PptContent:
    """按规则 issues 重组 PptContent：重新查最新落库数据（§46「重新查数据」）。

    规则 issues（页数/必填非空/FMEA 一致性）属结构或数据缺口：结构由 generate_content 固定
    产出 11 页（页数 issue 不会触发）；「D 页内容为空」属数据缺失，按 §101「不编造数据」
    不可自动补全 → 残留时由 review_and_correct 短路为 needs_review（不耗 LLM 轮次）。
    """
    return await capa_ppt_service.generate_content(db, capa_id)


async def _correct_by_suggestions(pc, skill, content, suggestions) -> PptContent:
    """按 LLM suggestions 用 LLM 重写各页 section 呈现（§101「不编造数据」约束下）。

    校正异常 → 不上抛 500：审查已成功产出报告，仅自动校正失败 → 回退原内容，下一轮审查
    原内容；最终达 3 轮仍不通过 → needs_review + 报告（保留审查产出，用户可见 issues/suggestions）。
    """
    try:
        return await _subagent_correct(pc, skill, content, suggestions)
    except Exception:
        return content
