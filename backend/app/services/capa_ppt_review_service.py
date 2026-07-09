"""PPT sub-agent 审查 + 校正闭环（US-E2E-01.10）。

只返回 (PptContent, ReviewResult)，不渲染 pptx——最终渲染在 API 层做一次。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import agent_review_skill_service, capa_ppt_service, capa_service
from app.services.capa_ppt_service import PptContent
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
        # 校正后重新校验；若仍存在（数据缺失无法自动补），保留以在报告中暴露
        rule_issues = capa_ppt_service._validate_ppt_content(content, capa)

    # 2. LLM 未配置 → 跳过 sub-agent 审查；但内置规则 issues 须在报告中暴露（不静默丢弃）
    if pc is None:
        report = {"issues": rule_issues, "suggestions": []} if rule_issues else None
        return content, ReviewResult("skipped", 0, report)

    # 3. LLM 审查闭环（3 轮上限）
    skill = await agent_review_skill_service.get_by_name(db, tenant_schema, "capa_ppt_review")
    if skill is None:
        # skill 未配置/未 seed —— 不掩盖成 "LLM 调用异常"，直接报具体配置问题
        return content, ReviewResult("needs_review", 0, {
            "issues": ["审查 skill 未配置（capa_ppt_review），请管理员配置或检查 seed"],
            "suggestions": [],
        })
    last_report: dict = {"issues": [], "suggestions": []}
    for round_idx in range(1, 4):
        # 审查闭环异常（超时/鉴权/响应格式）属故事 §92 FAILED 条件，不在此吞掉降级为 needs_review；
        # 让异常上抛，由 API 层转为 500。LLM 未配置（ProviderNotConfigured）已在 API 层 pc=None 处理为 skipped。
        review = await _subagent_review(pc, skill, content)
        last_report = review.report
        if review.passed:
            return content, ReviewResult("passed", round_idx, last_report)
        if round_idx < 3:
            content = await _correct_by_suggestions(db, capa_id, review.suggestions)
        else:
            return content, ReviewResult("needs_review", 3, last_report)


async def _subagent_review(pc, skill, content) -> ReviewOutcome:
    """构造审查 prompt = skill.content + PptContent 序列化 → LLM → 解析。"""
    prompt = f"{skill.content}\n\n--- 待审查 PPT 内容 ---\n{_serialize_content(content)}"
    result = await provider_adapter.complete_json(pc, prompt, REVIEW_SCHEMA)
    return ReviewOutcome(
        passed=result["passed"], issues=result["issues"], suggestions=result["suggestions"],
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
    """按规则 issues 重组 PptContent（不渲染 pptx）。

    故事 §46「校正＝重新查数据/修结构，非 LLM 重写」。当前实现：重新查最新落库数据
    （generate_content）以拾取数据变更；结构由 generate_content 固定产出 11 页，无需修补。
    issues 中的「D 页内容为空」属数据缺失，按 §101「不编造数据」不可自动补全。
    真正按反馈改写内容需 LLM 重写，故事 §101/§109 明确为后续迭代——见 follow-up。
    """
    return await capa_ppt_service.generate_content(db, capa_id)


async def _correct_by_suggestions(db, capa_id, suggestions) -> PptContent:
    """按 LLM suggestions 重组 PptContent（不渲染 pptx）。数据源缺失则跳过。

    与 _correct_by_issues 同理：当前只能重新查最新落库数据（§46），无法按 LLM 内容建议
    改写文本（需 LLM 重写，§101/§109 后续迭代）。故 3 轮闭环在 LLM 重写落地前，
    若首轮不通过且数据未变更，后续轮次审查的是近乎相同的内容——这是当前范围的已知约束，
    非 bug；达上限返回 needs_review + 审查报告（故事 §73）。
    """
    return await capa_ppt_service.generate_content(db, capa_id)
