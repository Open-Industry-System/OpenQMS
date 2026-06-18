import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit import AuditLog
from app.models.management_review import ManagementReview
from app.models.management_review_report import ReviewReport

if TYPE_CHECKING:
    from app.models.user import User
    from app.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

REPORT_SECTIONS = [
    {"key": "previous_review_actions", "title": "1. 以往管理评审措施落实情况", "source": "data_package"},
    {"key": "quality_goals", "title": "2. 质量目标实现程度", "source": "data_package"},
    {"key": "internal_audits", "title": "3. 审核结果", "source": "data_package"},
    {"key": "capa_stats", "title": "4. 不合格与纠正措施", "source": "data_package"},
    {"key": "fmea_risks", "title": "5. FMEA 风险分析", "source": "data_package"},
    {"key": "spc_capability", "title": "6. SPC 过程能力", "source": "data_package"},
    {"key": "supplier_performance", "title": "7. 外部供方绩效", "source": "data_package"},
    {"key": "external_factors", "title": "8. 内外部因素变化", "source": "manual_input"},
    {"key": "resource_adequacy", "title": "9. 资源充分性", "source": "manual_input"},
    {"key": "customer_satisfaction", "title": "10. 顾客满意与反馈", "source": "manual_input"},
    {"key": "equipment_monitoring", "title": "11. 监视测量结果（设备）", "source": "manual_input"},
    {"key": "copq", "title": "12. 不良质量成本", "source": "manual_input"},
    {"key": "manufacturing_feasibility", "title": "13. 制造可行性评估", "source": "manual_input"},
]

LLM_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["analysis", "findings", "recommendations"],
}

LLM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "analysis": {"type": "string"},
                    "findings": {"type": "array", "items": {"type": "string"}},
                    "recommendations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "analysis", "findings", "recommendations"],
            },
        },
        "executive_summary": {"type": "string"},
        "overall_recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sections", "executive_summary", "overall_recommendations"],
}


def _format_data_package_section(key: str, data: dict | None) -> str:
    if not data:
        return "暂无数据。"
    lines = []
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"- {k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines) or "暂无数据。"


def _format_manual_input_section(key: str, data: dict | str | None) -> str:
    if data is None:
        return "未录入。"
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return data.get("summary", "未录入。")
    return "未录入。"


def _build_sections(data_package: dict | None, manual_inputs: dict | None) -> list[dict]:
    data_package = data_package or {}
    manual_inputs = manual_inputs or {}
    sections = []
    for meta in REPORT_SECTIONS:
        key = meta["key"]
        if meta["source"] == "data_package":
            snapshot = data_package.get(key)
            base_text = _format_data_package_section(key, snapshot)
        else:
            snapshot = manual_inputs.get(key)
            base_text = _format_manual_input_section(key, snapshot)
        sections.append({
            "key": key,
            "title": meta["title"],
            "source": meta["source"],
            "base_text": base_text,
            "ai_analysis": "",
            "findings": [],
            "recommendations": [],
            "manual_text": "",
            "data_snapshot": snapshot,
        })
    return sections


def _build_section_prompt(section: dict, review: ManagementReview) -> str:
    return f"""你是一位资深的质量管理体系审核员，正在为 ISO 9001 §9.3 管理评审撰写报告章节。

【评审信息】
评审编号：{review.doc_no}
评审主题：{review.title}
产品线：{review.product_line_code or "全厂"}

【章节】{section['title']}

【基础内容】
{section['base_text'][:1500]}

请基于以上内容，生成该章节的分析、关键发现和改进建议。
输出必须严格为 JSON，不要包含任何 Markdown 代码块或其他说明。"""


async def _enrich_with_llm(
    sections: list[dict],
    review: ManagementReview,
    llm_provider: "LLMProvider | None",
    report_llm_timeout: int | None = None,
) -> tuple[list[dict], bool]:
    if llm_provider is None:
        return sections, False

    timeout = report_llm_timeout or settings.REPORT_LLM_TIMEOUT
    llm_enriched = False
    for section in sections:
        try:
            prompt = _build_section_prompt(section, review)
            response = await asyncio.wait_for(
                llm_provider.complete(prompt, LLM_SECTION_SCHEMA),
                timeout=timeout,
            )
            section["ai_analysis"] = str(response.get("analysis", "")).strip()
            section["findings"] = [str(x) for x in response.get("findings", []) if x]
            section["recommendations"] = [str(x) for x in response.get("recommendations", []) if x]
            llm_enriched = True
        except Exception as e:
            logger.warning("LLM enrichment failed for section %s: %s", section["key"], e)
    return sections, llm_enriched


def _build_executive_prompt(sections: list[dict], review: ManagementReview) -> str:
    summary_lines = []
    for s in sections:
        summary_lines.append(f"{s['title']}: {s['base_text'][:200]}")
    combined = "\n".join(summary_lines)
    return f"""基于以下管理评审各章节摘要，生成一份执行摘要（executive summary）和整体改进建议列表。

【评审编号】{review.doc_no}
【评审主题】{review.title}

【章节摘要】
{combined[:3000]}

请输出 JSON，包含 executive_summary（字符串）和 overall_recommendations（字符串数组）。"""


async def _generate_executive_summary(
    sections: list[dict],
    review: ManagementReview,
    llm_provider: "LLMProvider | None",
    report_llm_timeout: int | None = None,
) -> tuple[str, list[str]]:
    if llm_provider is None:
        return _fallback_executive_summary(review), []
    timeout = report_llm_timeout or settings.REPORT_LLM_TIMEOUT
    try:
        response = await asyncio.wait_for(
            llm_provider.complete(
                _build_executive_prompt(sections, review),
                {
                    "type": "object",
                    "properties": {
                        "executive_summary": {"type": "string"},
                        "overall_recommendations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["executive_summary", "overall_recommendations"],
                },
            ),
            timeout=timeout,
        )
        return (
            str(response.get("executive_summary", "")).strip(),
            [str(x) for x in response.get("overall_recommendations", []) if x],
        )
    except Exception as e:
        logger.warning("LLM executive summary failed: %s", e)
        return _fallback_executive_summary(review), []


def _fallback_executive_summary(review: ManagementReview) -> str:
    if not review.data_package:
        return "【提示】当前尚未汇总数据，报告内容基于现有手工输入生成。建议在「汇总数据」后重新生成以获得完整报告。"
    return "（未配置 AI 服务或 AI 生成失败，已回退到规则生成的章节内容。）"


async def generate_report(
    db: AsyncSession,
    review: ManagementReview,
    user: "User",
    llm_provider: "LLMProvider | None" = None,
    use_llm: bool = True,
    report_llm_timeout: int | None = None,
) -> dict:
    if review.status == "closed":
        raise ValueError("cannot generate report for closed review")
    if review.report_status == "final":
        raise ValueError("report is finalized, reopen before regenerating")

    # Explicitly load deferred JSONB columns to avoid MissingGreenlet in async mode
    await db.refresh(review, ["data_package", "manual_inputs", "generated_report"])
    sections = _build_sections(review.data_package, review.manual_inputs)
    llm_enriched = False
    if use_llm and llm_provider is not None:
        sections, llm_enriched = await _enrich_with_llm(
            sections, review, llm_provider, report_llm_timeout=report_llm_timeout
        )

    executive_summary, overall_recommendations = "", []
    if use_llm and llm_provider is not None:
        executive_summary, overall_recommendations = await _generate_executive_summary(
            sections, review, llm_provider, report_llm_timeout=report_llm_timeout
        )
    else:
        executive_summary = _fallback_executive_summary(review)

    model_name = getattr(llm_provider, "model", None) or "rule-only"
    content = {
        "generated_at": datetime.now(UTC).isoformat(),
        "generation_model": model_name,
        "llm_enriched": llm_enriched,
        "sections": sections,
        "executive_summary": executive_summary,
        "overall_recommendations": overall_recommendations,
    }

    review.generated_report = content
    review.report_status = "draft"
    await _write_audit(db, review.review_id, user.user_id, "REPORT_GENERATE", {
        "model": model_name, "llm_enriched": llm_enriched,
    })
    await db.commit()
    return content


async def save_report_draft(
    db: AsyncSession,
    review: ManagementReview,
    content: dict,
    user: "User",
) -> dict:
    await db.refresh(review, ["generated_report"])
    if review.report_status == "final":
        raise ValueError("report is finalized, reopen before editing")
    if review.status == "closed":
        raise ValueError("cannot edit report of a closed review")

    content = {**content, "updated_at": datetime.now(UTC).isoformat()}
    review.generated_report = content
    review.report_status = "draft"
    await _write_audit(db, review.review_id, user.user_id, "REPORT_SAVE_DRAFT", {
        "sections_count": len(content.get("sections", [])),
    })
    await db.commit()
    return content


async def finalize_report(
    db: AsyncSession,
    review: ManagementReview,
    user: "User",
) -> ReviewReport:
    # Lock review row first, then re-read state under lock to prevent stale checks
    await db.execute(
        select(ManagementReview)
        .where(ManagementReview.review_id == review.review_id)
        .with_for_update()
    )
    await db.refresh(review, ["generated_report"])
    if review.report_status != "draft":
        raise ValueError("only draft report can be finalized")
    if review.status == "closed":
        raise ValueError("cannot finalize report of a closed review")
    if not review.generated_report:
        raise ValueError("no report content to finalize")

    result = await db.execute(
        select(func.coalesce(func.max(ReviewReport.version_no), 0))
        .where(ReviewReport.review_id == review.review_id)
    )
    next_version = (result.scalar() or 0) + 1

    snapshot = ReviewReport(
        review_id=review.review_id,
        version_no=next_version,
        content=review.generated_report,
        created_by=user.user_id,
        finalized_by=user.user_id,
        finalized_at=datetime.now(UTC),
    )
    db.add(snapshot)
    review.report_status = "final"
    await _write_audit(db, review.review_id, user.user_id, "REPORT_FINALIZE", {
        "version_no": next_version,
    })
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("version conflict detected, please retry")
    await db.refresh(snapshot)
    return snapshot


async def reopen_report_to_draft(
    db: AsyncSession,
    review: ManagementReview,
    user: "User",
) -> ManagementReview:
    if review.report_status != "final":
        raise ValueError("only finalized report can be reopened")
    if review.status == "closed":
        raise ValueError("cannot reopen report of a closed review")
    review.report_status = "draft"
    await _write_audit(db, review.review_id, user.user_id, "REPORT_REOPEN", {})
    await db.commit()
    await db.refresh(review)
    return review


async def list_report_versions(
    db: AsyncSession,
    review_id: uuid.UUID,
) -> list[ReviewReport]:
    result = await db.execute(
        select(ReviewReport)
        .where(ReviewReport.review_id == review_id)
        .order_by(ReviewReport.version_no.desc())
    )
    return list(result.scalars().all())


async def get_report_version(
    db: AsyncSession,
    report_id: uuid.UUID,
) -> ReviewReport | None:
    return await db.get(ReviewReport, report_id)


async def _write_audit(
    db: AsyncSession,
    review_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    changed_fields: dict,
) -> None:
    db.add(AuditLog(
        table_name="management_reviews",
        record_id=review_id,
        action=action,
        changed_fields=changed_fields,
        operated_by=user_id,
    ))


def export_report_markdown(content: dict) -> str:
    lines = []
    lines.append("# 管理评审报告")
    lines.append("")
    lines.append(f"生成时间：{content.get('generated_at', '')}")
    lines.append(f"生成模型：{content.get('generation_model', '')}")
    lines.append("")

    summary = content.get("executive_summary", "")
    if summary:
        lines.append("## 执行摘要")
        lines.append(summary)
        lines.append("")

    for section in content.get("sections", []):
        lines.append(f"## {section['title']}")
        if section.get("manual_text"):
            lines.append(section["manual_text"])
        else:
            lines.append(section.get("base_text", ""))
            if section.get("ai_analysis"):
                lines.append("")
                lines.append("**分析：**")
                lines.append(section["ai_analysis"])
            if section.get("findings"):
                lines.append("")
                lines.append("**关键发现：**")
                for finding in section["findings"]:
                    lines.append(f"- {finding}")
            if section.get("recommendations"):
                lines.append("")
                lines.append("**改进建议：**")
                for rec in section["recommendations"]:
                    lines.append(f"- {rec}")
        lines.append("")

    overall = content.get("overall_recommendations", [])
    if overall:
        lines.append("## 总体改进建议")
        for rec in overall:
            lines.append(f"- {rec}")
        lines.append("")

    return "\n".join(lines)
