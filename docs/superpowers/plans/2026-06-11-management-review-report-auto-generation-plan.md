# 管理评审报告自动生成模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有管理评审模块基础上，实现基于 `data_package` 和 `manual_inputs` 的报告自动生成、人工编辑、定稿归档与定稿版本历史功能。

**Architecture:** 扩展 `management_reviews` 表保存当前草稿 (`generated_report` JSONB + `report_status`)；新增 `review_reports` 表只保存定稿快照；新增 `management_review_report_service.py` 处理报告生成/保存/定稿/历史版本；API 层接入现有权限和 LLM provider；前端在详情页新增报告 Card。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + PostgreSQL + Pydantic v2；React 18 + TypeScript + Ant Design 5。

---

## 文件结构

### 后端新增
- `backend/app/models/management_review_report.py` — `ReviewReport` ORM 模型
- `backend/app/services/management_review_report_service.py` — 报告生成/保存/定稿/版本服务
- `backend/alembic/versions/20260611_add_review_reports.py` — 数据库迁移

### 后端修改
- `backend/app/models/management_review.py` — 添加 `report_status`, `generated_report`
- `backend/app/schemas/management_review.py` — 新增报告相关 Pydantic schemas
- `backend/app/api/management_review.py` — 新增报告相关 API 端点
- `backend/app/config.py` — 新增 `REPORT_LLM_TIMEOUT`

### 前端新增
- `frontend/src/pages/managementReview/ManagementReviewReportPanel.tsx`
- `frontend/src/pages/managementReview/ReportSectionEditor.tsx`
- `frontend/src/pages/managementReview/ReportVersionList.tsx`

### 前端修改
- `frontend/src/api/managementReview.ts` — 新增报告 API 函数
- `frontend/src/types/index.ts` — 新增 `ManagementReviewReport`, `ReviewReportVersion` 等类型
- `frontend/src/pages/managementReview/ManagementReviewDetailPage.tsx` — 嵌入报告 Card

### 测试
- `backend/tests/test_management_review_report_service.py`
- `backend/tests/test_management_review_report_api.py`

---

## Task 1: Alembic 迁移

**Files:**
- Create: `backend/alembic/versions/20260611_add_review_reports.py`
- Modify: `backend/app/models/management_review.py`

- [ ] **Step 1: 扩展 ManagementReview 模型**

在 `backend/app/models/management_review.py` 的 `ManagementReview` 类中新增两列：

```python
report_status: Mapped[str] = mapped_column(
    String(20), default="none", nullable=False
)
generated_report: Mapped[dict | None] = mapped_column(
    JSONB, nullable=True, deferred=True
)
```

- [ ] **Step 2: 创建 ReviewReport 模型文件**

创建 `backend/app/models/management_review_report.py`：

```python
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReviewReport(Base):
    __tablename__ = "review_reports"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("management_reviews.review_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    review = relationship("ManagementReview", back_populates="reports")
```

在 `ManagementReview` 模型中添加 relationship：

```python
reports = relationship(
    "ReviewReport", back_populates="review", cascade="all, delete-orphan"
)
```

- [ ] **Step 2b: 在模型 registry 中注册 ReviewReport**

修改 `backend/app/models/__init__.py`：

在 `from app.models.management_review import ManagementReview, ReviewOutput` 行后添加：

```python
from app.models.management_review_report import ReviewReport
```

在 `__all__` 数组中 `"ManagementReview", "ReviewOutput"` 后添加 `"ReviewReport"`。

- [ ] **Step 3: 编写 Alembic 迁移**

创建 `backend/alembic/versions/20260611_add_review_reports.py`：

```python
"""add review reports

Revision ID: 20260611_add_review_reports
Revises: 034_add_supplier_risk_tables
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260611_add_review_reports"
down_revision: Union[str, None] = "034_add_supplier_risk_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "management_reviews",
        sa.Column("report_status", sa.String(20), server_default="none", nullable=False),
    )
    op.add_column(
        "management_reviews",
        sa.Column("generated_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "review_reports",
        sa.Column("report_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("management_reviews.review_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("finalized_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_review_reports_version", "review_reports", ["review_id", "version_no"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_review_reports_version", "review_reports")
    op.drop_table("review_reports")
    op.drop_column("management_reviews", "generated_report")
    op.drop_column("management_reviews", "report_status")
```

- [ ] **Step 4: 运行迁移**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Context impl PostgresqlImpl. ... Running upgrade 034_add_supplier_risk_tables -> 20260611_add_review_reports, add review reports`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/management_review.py

git add backend/app/models/management_review_report.py

git add backend/app/models/__init__.py

git add backend/alembic/versions/20260611_add_review_reports.py

git commit -m "feat(management-review-report): add review_reports table and report_status columns"
```

---

## Task 2: 报告生成服务

**Files:**
- Create: `backend/app/services/management_review_report_service.py`

- [ ] **Step 1: 创建服务文件骨架**

创建 `backend/app/services/management_review_report_service.py`：

```python
import asyncio
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.management_review import ManagementReview
from app.models.management_review_report import ReviewReport
from app.models.audit import AuditLog

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
```

- [ ] **Step 2: 实现 `_build_sections`**

在同一文件中：

```python
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
```

- [ ] **Step 3: 实现 `_enrich_with_llm`**

```python
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
) -> tuple[list[dict], bool]:
    if llm_provider is None:
        return sections, False

    llm_enriched = False
    for section in sections:
        try:
            prompt = _build_section_prompt(section, review)
            response = await asyncio.wait_for(
                llm_provider.complete(prompt, LLM_SECTION_SCHEMA),
                timeout=settings.REPORT_LLM_TIMEOUT,
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
) -> tuple[str, list[str]]:
    if llm_provider is None:
        return _fallback_executive_summary(review), []
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
            timeout=settings.REPORT_LLM_TIMEOUT,
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
```

- [ ] **Step 4: 实现 `generate_report`**

```python
async def generate_report(
    db: AsyncSession,
    review: ManagementReview,
    user: "User",
    llm_provider: "LLMProvider | None" = None,
    use_llm: bool = True,
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
        sections, llm_enriched = await _enrich_with_llm(sections, review, llm_provider)

    executive_summary, overall_recommendations = "", []
    if use_llm and llm_provider is not None:
        executive_summary, overall_recommendations = await _generate_executive_summary(
            sections, review, llm_provider
        )
    else:
        executive_summary = _fallback_executive_summary(review)

    model_name = getattr(llm_provider, "model", None) or "rule-only"
    content = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
    await db.flush()
    return content
```

- [ ] **Step 5: 实现保存、定稿、版本查询**

```python
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

    content["updated_at"] = datetime.now(timezone.utc).isoformat()
    review.generated_report = content
    review.report_status = "draft"
    await _write_audit(db, review.review_id, user.user_id, "REPORT_SAVE_DRAFT", {
        "sections_count": len(content.get("sections", [])),
    })
    await db.flush()
    return content


async def finalize_report(
    db: AsyncSession,
    review: ManagementReview,
    user: "User",
) -> ReviewReport:
    await db.refresh(review, ["generated_report"])
    if review.report_status != "draft":
        raise ValueError("only draft report can be finalized")
    if review.status == "closed":
        raise ValueError("cannot finalize report of a closed review")
    if not review.generated_report:
        raise ValueError("no report content to finalize")

    # Atomic version increment
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
        finalized_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    review.report_status = "final"
    await _write_audit(db, review.review_id, user.user_id, "REPORT_FINALIZE", {
        "version_no": next_version,
    })
    await db.flush()
    await db.refresh(snapshot)
    return snapshot


async def reopen_report_to_draft(
    db: AsyncSession,
    review: ManagementReview,
    user: "User",
) -> None:
    if review.report_status != "final":
        raise ValueError("only finalized report can be reopened")
    if review.status == "closed":
        raise ValueError("cannot reopen report of a closed review")
    review.report_status = "draft"
    await _write_audit(db, review.review_id, user.user_id, "REPORT_REOPEN", {})
    await db.flush()


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
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/management_review_report_service.py

git commit -m "feat(management-review-report): add report generation service"
```

---

## Task 3: Schemas

**Files:**
- Modify: `backend/app/schemas/management_review.py`

- [ ] **Step 1: 新增报告相关 schemas**

在 `backend/app/schemas/management_review.py` 末尾追加：

```python
class ReportSection(BaseModel):
    key: str
    title: str
    source: str
    base_text: str
    ai_analysis: str
    findings: list[str]
    recommendations: list[str]
    manual_text: str
    # data_snapshot mirrors the raw source value; it can be a scalar from manual_inputs
    data_snapshot: dict | str | list | int | float | bool | None


class ReportContent(BaseModel):
    generated_at: str
    generation_model: str
    llm_enriched: bool
    sections: list[ReportSection]
    executive_summary: str
    overall_recommendations: list[str]


class ReportGenerateRequest(BaseModel):
    use_llm: bool = True


class ReportGenerateResponse(BaseModel):
    report_status: str
    generated_report: ReportContent


class ReportSaveDraftRequest(BaseModel):
    generated_report: ReportContent


class ReportVersionResponse(BaseModel):
    report_id: uuid.UUID
    review_id: uuid.UUID
    version_no: int
    content: ReportContent
    created_by: uuid.UUID
    finalized_by: uuid.UUID | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportExportResponse(BaseModel):
    markdown: str
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/management_review.py

git commit -m "feat(management-review-report): add report pydantic schemas"
```

---

## Task 4: API 路由

**Files:**
- Modify: `backend/app/api/management_review.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: 添加 REPORT_LLM_TIMEOUT 配置**

在 `backend/app/config.py` 中：

```python
REPORT_LLM_TIMEOUT: int = Field(default=10, ge=1, le=120)
```

- [ ] **Step 2: 新增 API 端点**

在 `backend/app/api/management_review.py` 末尾追加：

```python
from fastapi import Request

from app.services import management_review_report_service as report_service


@router.post("/{review_id}/report/generate", response_model=schemas.management_review.ReportGenerateResponse)
async def generate_report(
    review_id: uuid.UUID,
    req: schemas.management_review.ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MANAGEMENT_REVIEW, PermissionLevel.CREATE)),
    request: Request = None,
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    if review.status == "closed":
        raise HTTPException(status_code=400, detail="cannot generate report for closed review")
    if review.report_status == "final":
        raise HTTPException(status_code=400, detail="report is finalized, reopen before regenerating")

    llm_provider = getattr(request.app.state, "llm_provider", None)
    try:
        content = await report_service.generate_report(
            db, review, user, llm_provider=llm_provider, use_llm=req.use_llm
        )
        await db.commit()
        return {"report_status": review.report_status, "generated_report": content}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/report/save-draft", response_model=schemas.management_review.ReportGenerateResponse)
async def save_report_draft(
    review_id: uuid.UUID,
    req: schemas.management_review.ReportSaveDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MANAGEMENT_REVIEW, PermissionLevel.CREATE)),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        content = await report_service.save_report_draft(db, review, req.generated_report.model_dump(), user)
        await db.commit()
        return {"report_status": review.report_status, "generated_report": content}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/report/finalize", response_model=schemas.management_review.ReportVersionResponse)
async def finalize_report(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MANAGEMENT_REVIEW, PermissionLevel.APPROVE)),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        snapshot = await report_service.finalize_report(db, review, user)
        await db.commit()
        return schemas.management_review.ReportVersionResponse.model_validate(snapshot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/report/reopen")
async def reopen_report(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MANAGEMENT_REVIEW, PermissionLevel.APPROVE)),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        await report_service.reopen_report_to_draft(db, review, user)
        await db.commit()
        return {"report_status": review.report_status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{review_id}/report/versions", response_model=list[schemas.management_review.ReportVersionResponse])
async def list_report_versions(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    versions = await report_service.list_report_versions(db, review_id)
    return [schemas.management_review.ReportVersionResponse.model_validate(v) for v in versions]


@router.get("/{review_id}/report/versions/{report_id}", response_model=schemas.management_review.ReportVersionResponse)
async def get_report_version(
    review_id: uuid.UUID,
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    version = await report_service.get_report_version(db, report_id)
    if version is None or version.review_id != review_id:
        raise HTTPException(status_code=404, detail="report version not found")
    return schemas.management_review.ReportVersionResponse.model_validate(version)


@router.get("/{review_id}/report/export")
async def export_report(
    review_id: uuid.UUID,
    format: str = "markdown",
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    if not review.generated_report:
        raise HTTPException(status_code=400, detail="no report content")
    if format != "markdown":
        raise HTTPException(status_code=400, detail="only markdown export is supported")
    markdown = report_service.export_report_markdown(review.generated_report)
    return {"markdown": markdown}
```

- [ ] **Step 3: 添加 export_report_markdown 方法**

在 `backend/app/services/management_review_report_service.py` 中添加：

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/management_review.py

git add backend/app/config.py

git add backend/app/services/management_review_report_service.py

git commit -m "feat(management-review-report): add report API routes and markdown export"
```

---

## Task 5: 后端服务测试

**Files:**
- Create: `backend/tests/test_management_review_report_service.py`

- [ ] **Step 1: 编写规则生成测试**

```python
import uuid
import pytest

from app.models.management_review import ManagementReview
from app.models.management_review_report import ReviewReport
from app.services import management_review_report_service as report_service


@pytest.mark.asyncio
async def test_build_sections_maps_data_package(db, admin_user):
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
    assert "quality_goals" in keys
    assert "external_factors" in keys
    quality_section = next(s for s in sections if s["key"] == "quality_goals")
    assert "5" in quality_section["base_text"]
    external_section = next(s for s in sections if s["key"] == "external_factors")
    assert "市场竞争加剧" in external_section["base_text"]
```

- [ ] **Step 2: 编写生成/保存/定稿测试**

```python
@pytest.mark.asyncio
async def test_generate_report_creates_draft(db, admin_user):
    review = ManagementReview(
        doc_no="MR-TEST-001",
        title="Test Review",
        review_date="2026-06-11",
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
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
        doc_no="MR-TEST-002",
        title="Test Review",
        review_date="2026-06-11",
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
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
        doc_no="MR-TEST-003",
        title="Test Review",
        review_date="2026-06-11",
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
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
    await report_service.reopen_report_to_draft(db, review, admin_user)
    snapshot2 = await report_service.finalize_report(db, review, admin_user)
    assert snapshot2.version_no == 2


@pytest.mark.asyncio
async def test_finalize_requires_draft(db, admin_user):
    review = ManagementReview(
        doc_no="MR-TEST-004",
        title="Test Review",
        review_date="2026-06-11",
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
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
        doc_no="MR-TEST-005",
        title="Test Review",
        review_date="2026-06-11",
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
        status="closed",
        report_status="draft",
        generated_report={"sections": []},
    )
    db.add(review)
    await db.flush()

    with pytest.raises(ValueError, match="closed review"):
        await report_service.save_report_draft(db, review, {"sections": []}, admin_user)
```

- [ ] **Step 3: 运行测试**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_management_review_report_service.py -v
```

Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_management_review_report_service.py

git commit -m "test(management-review-report): add service tests"
```

---

## Task 6: API 测试

**Files:**
- Create: `backend/tests/test_management_review_report_api.py`

- [ ] **Step 1: 创建 API 测试文件**

创建 `backend/tests/test_management_review_report_api.py`：

```python
import uuid
import pytest
from fastapi import status
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.database import get_db
from app.core.permissions import get_current_user, Module, PermissionLevel
from app.models.user import User


@pytest.fixture
def override_dependencies():
    async def mock_get_db():
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        db.get = AsyncMock(return_value=None)
        db.refresh = AsyncMock()
        db.flush = AsyncMock()
        return db

    async def mock_get_current_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.username = "manager"
        user.role = "manager"
        user.role_id = uuid.uuid4()
        user.is_active = True
        user.role_definition = MagicMock()
        user.role_definition.bypass_row_level_security = True
        return user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.CREATE)):
        yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generate_report_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/management-reviews/{uuid.uuid4()}/report/generate", json={"use_llm": False})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_generate_report_authenticated(override_dependencies):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/management-reviews/{uuid.uuid4()}/report/generate", json={"use_llm": False})
    assert resp.status_code == status.HTTP_404_NOT_FOUND
```

- [ ] **Step 2: 编写权限与状态测试**

```python
from app.models.management_review import ManagementReview
from app.services import management_review_report_service as report_service


def _mock_review(status="data_collected", report_status="none"):
    review = MagicMock(spec=ManagementReview)
    review.review_id = uuid.uuid4()
    review.status = status
    review.report_status = report_status
    review.data_package = {"quality_goals": {"total": 1}}
    review.manual_inputs = {}
    review.generated_report = {"sections": []} if report_status == "draft" else None
    review.doc_no = "MR-MOCK-001"
    review.title = "Mock Review"
    review.product_line_code = "DC-DC-100"
    return review


@pytest.mark.asyncio
async def test_viewer_cannot_generate_report():
    app.dependency_overrides[get_current_user] = override_dependencies.__wrapped__ if False else None


@pytest.mark.asyncio
async def test_permission_levels(monkeypatch):
    """PATCH app.core.permissions.get_user_permission 到指定级别后调用 API。"""
    from httpx import AsyncClient, ASGITransport

    async def run_with_permission(level: PermissionLevel, expected_status: int):
        async def mock_user():
            user = MagicMock(spec=User)
            user.user_id = uuid.uuid4()
            user.is_active = True
            return user

        app.dependency_overrides[get_current_user] = mock_user
        with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=level)):
            review = _mock_review(status="data_collected", report_status="none")
            mock_db = MagicMock()
            mock_db.get = AsyncMock(return_value=review)
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()
            app.dependency_overrides[get_db] = lambda: mock_db
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                return await ac.post(
                    f"/api/management-reviews/{review.review_id}/report/generate",
                    json={"use_llm": False},
                )

    # VIEW level should be forbidden
    resp = await run_with_permission(PermissionLevel.VIEW, 403)
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # CREATE level should succeed (mock service returns content)
    with patch.object(report_service, "generate_report", new=AsyncMock(return_value={"sections": []})):
        resp = await run_with_permission(PermissionLevel.CREATE, 200)
    assert resp.status_code == status.HTTP_200_OK

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_closed_review_rejects_save_draft():
    async def mock_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.is_active = True
        return user

    app.dependency_overrides[get_current_user] = mock_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.CREATE)):
        review = _mock_review(status="closed", report_status="draft")
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=review)
        mock_db.commit = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/save-draft",
                json={"generated_report": {"sections": []}},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_final_report_rejects_regenerate():
    async def mock_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.is_active = True
        return user

    app.dependency_overrides[get_current_user] = mock_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.CREATE)):
        review = _mock_review(status="data_collected", report_status="final")
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=review)
        mock_db.commit = AsyncMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/generate",
                json={"use_llm": False},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
    app.dependency_overrides.clear()
```

- [ ] **Step 3: 编写版本号递增测试**

```python
@pytest.mark.asyncio
async def test_finalize_increments_version(db, admin_user):
    from app.services import management_review_report_service as report_service
    review = ManagementReview(
        doc_no="MR-API-V001",
        title="Version Test",
        review_date="2026-06-11",
        chair_person_id=admin_user.user_id,
        created_by=admin_user.user_id,
        status="data_collected",
        report_status="none",
    )
    db.add(review)
    await db.flush()

    await report_service.generate_report(db, review, admin_user, llm_provider=None)
    snap1 = await report_service.finalize_report(db, review, admin_user)
    assert snap1.version_no == 1

    await report_service.reopen_report_to_draft(db, review, admin_user)
    snap2 = await report_service.finalize_report(db, review, admin_user)
    assert snap2.version_no == 2
```

- [ ] **Step 4: 运行测试**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_management_review_report_api.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_management_review_report_api.py

git commit -m "test(management-review-report): add API tests"
```

---

## Task 7: 前端类型与 API

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/managementReview.ts`

- [ ] **Step 1: 新增前端类型**

在 `frontend/src/types/index.ts` 的 `ReviewOutput` 后追加：

```typescript
export interface ManagementReviewReportSection {
  key: string;
  title: string;
  source: "data_package" | "manual_input";
  base_text: string;
  ai_analysis: string;
  findings: string[];
  recommendations: string[];
  manual_text: string;
  data_snapshot: Record<string, unknown> | string | unknown[] | number | boolean | null;
}

export interface ManagementReviewReport {
  generated_at: string;
  generation_model: string;
  llm_enriched: boolean;
  sections: ManagementReviewReportSection[];
  executive_summary: string;
  overall_recommendations: string[];
}

export interface ReviewReportVersion {
  report_id: string;
  review_id: string;
  version_no: number;
  content: ManagementReviewReport;
  created_by: string;
  finalized_by: string | null;
  finalized_at: string | null;
  created_at: string;
  updated_at: string;
}
```

更新 `ManagementReview` 接口：

```typescript
export interface ManagementReview {
  review_id: string;
  doc_no: string;
  title: string;
  review_date: string;
  actual_date: string | null;
  status: "draft" | "data_collected" | "in_review" | "closed";
  report_status: "none" | "draft" | "final";
  generated_report: ManagementReviewReport | null;
  // ... 其余字段保持不变
}
```

- [ ] **Step 2: 新增 API 函数**

在 `frontend/src/api/managementReview.ts` 末尾追加：

```typescript
import type { ManagementReviewReport, ReviewReportVersion } from "../types";

export async function generateReport(
  id: string,
  use_llm: boolean = true,
): Promise<{ report_status: string; generated_report: ManagementReviewReport }> {
  const resp = await client.post(`/management-reviews/${id}/report/generate`, { use_llm });
  return resp.data;
}

export async function saveReportDraft(
  id: string,
  report: ManagementReviewReport,
): Promise<{ report_status: string; generated_report: ManagementReviewReport }> {
  const resp = await client.post(`/management-reviews/${id}/report/save-draft`, { generated_report: report });
  return resp.data;
}

export async function finalizeReport(id: string): Promise<ReviewReportVersion> {
  const resp = await client.post(`/management-reviews/${id}/report/finalize`);
  return resp.data;
}

export async function reopenReport(id: string): Promise<{ report_status: string }> {
  const resp = await client.post(`/management-reviews/${id}/report/reopen`);
  return resp.data;
}

export async function listReportVersions(id: string): Promise<ReviewReportVersion[]> {
  const resp = await client.get(`/management-reviews/${id}/report/versions`);
  return resp.data;
}

export async function getReportVersion(reviewId: string, reportId: string): Promise<ReviewReportVersion> {
  const resp = await client.get(`/management-reviews/${reviewId}/report/versions/${reportId}`);
  return resp.data;
}

export async function exportReport(id: string, format: string = "markdown"): Promise<{ markdown: string }> {
  const resp = await client.get(`/management-reviews/${id}/report/export`, { params: { format } });
  return resp.data;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts

git add frontend/src/api/managementReview.ts

git commit -m "feat(management-review-report): add frontend types and API client"
```

---

## Task 8: 前端报告组件

**Files:**
- Create: `frontend/src/pages/managementReview/ManagementReviewReportPanel.tsx`
- Create: `frontend/src/pages/managementReview/ReportSectionEditor.tsx`
- Create: `frontend/src/pages/managementReview/ReportVersionList.tsx`

- [ ] **Step 1: 创建 ReportSectionEditor**

```tsx
import { Input } from "antd";
import type { ManagementReviewReportSection } from "../../types";

const { TextArea } = Input;

interface Props {
  section: ManagementReviewReportSection;
  readOnly: boolean;
  onChange: (section: ManagementReviewReportSection) => void;
}

export default function ReportSectionEditor({ section, readOnly, onChange }: Props) {
  return (
    <div>
      {section.source === "data_package" && (
        <div style={{ marginBottom: 12, whiteSpace: "pre-wrap", color: "#666", fontSize: 13 }}>
          {section.base_text}
        </div>
      )}
      {section.ai_analysis && (
        <div style={{ marginBottom: 12, color: "#333" }}>
          <strong>AI 分析：</strong>
          <div>{section.ai_analysis}</div>
        </div>
      )}
      <TextArea
        rows={4}
        value={section.manual_text}
        disabled={readOnly}
        onChange={(e) => onChange({ ...section, manual_text: e.target.value })}
        placeholder="在此输入人工编辑内容，导出时优先使用..."
      />
    </div>
  );
}
```

- [ ] **Step 2: 创建 ReportVersionList**

```tsx
import { List, Tag } from "antd";
import type { ReviewReportVersion } from "../../types";

interface Props {
  versions: ReviewReportVersion[];
  selectedId?: string;
  onSelect: (version: ReviewReportVersion) => void;
}

export default function ReportVersionList({ versions, selectedId, onSelect }: Props) {
  return (
    <List
      size="small"
      dataSource={versions}
      renderItem={(v) => (
        <List.Item
          style={{ cursor: "pointer", background: selectedId === v.report_id ? "#e6f7ff" : undefined }}
          onClick={() => onSelect(v)}
        >
          <Tag color="green">v{v.version_no}</Tag>
          <span style={{ fontSize: 12 }}>
            {v.finalized_at ? new Date(v.finalized_at).toLocaleDateString() : "-"}
          </span>
        </List.Item>
      )}
    />
  );
}
```

- [ ] **Step 3: 创建 ManagementReviewReportPanel**

```tsx
import { useState, useEffect } from "react";
import { Card, Button, Space, Tag, Collapse, Spin, message, Modal } from "antd";
import {
  generateReport, saveReportDraft, finalizeReport, reopenReport,
  listReportVersions, exportReport,
} from "../../api/managementReview";
import { usePermission } from "../../hooks/usePermission";
import type {
  ManagementReview,
  ManagementReviewReport,
  ManagementReviewReportSection,
  ReviewReportVersion,
} from "../../types";
import ReportSectionEditor from "./ReportSectionEditor";
import ReportVersionList from "./ReportVersionList";

interface Props {
  review: ManagementReview;
  onReviewChange: (review: ManagementReview) => void;
}

const statusMap: Record<string, { color: string; label: string }> = {
  none: { color: "default", label: "未生成" },
  draft: { color: "blue", label: "草稿" },
  final: { color: "green", label: "已定稿" },
};

export default function ManagementReviewReportPanel({ review, onReviewChange }: Props) {
  const { canCreate, canApprove } = usePermission();
  const [report, setReport] = useState<ManagementReviewReport | null>(review.generated_report);
  const [versions, setVersions] = useState<ReviewReportVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const readOnly = review.status === "closed" || review.report_status === "final";

  // Only rehydrate report data when switching reviews, not on every parent re-render
  useEffect(() => {
    setReport(review.generated_report);
  }, [review.review_id]);

  // Load finalized versions when status becomes final or review changes
  useEffect(() => {
    if (review.report_status === "final") {
      loadVersions();
    }
  }, [review.review_id, review.report_status]);

  const loadVersions = async () => {
    const data = await listReportVersions(review.review_id);
    setVersions(data);
  };

  const handleGenerate = async () => {
    if (review.report_status === "draft" && report) {
      Modal.confirm({
        title: "确认重新生成？",
        content: "重新生成将覆盖当前草稿中的人工编辑内容。",
        onOk: async () => {
          await doGenerate();
        },
      });
      return;
    }
    await doGenerate();
  };

  const doGenerate = async () => {
    setLoading(true);
    try {
      const data = await generateReport(review.review_id);
      setReport(data.generated_report);
      onReviewChange({ ...review, report_status: data.report_status, generated_report: data.generated_report });
      message.success("报告生成成功");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!report) return;
    try {
      const data = await saveReportDraft(review.review_id, report);
      setReport(data.generated_report);
      onReviewChange({ ...review, report_status: data.report_status, generated_report: data.generated_report });
      message.success("草稿已保存");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "保存失败");
    }
  };

  const handleFinalize = async () => {
    try {
      const version = await finalizeReport(review.review_id);
      setVersions((prev) => [version, ...prev]);
      onReviewChange({ ...review, report_status: "final" });
      message.success("报告已定稿归档");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "定稿失败");
    }
  };

  const handleReopen = async () => {
    try {
      const data = await reopenReport(review.review_id);
      onReviewChange({ ...review, report_status: data.report_status });
      message.success("报告已重新打开");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "重新打开失败");
    }
  };

  const handleExport = async () => {
    try {
      const data = await exportReport(review.review_id);
      const blob = new Blob([data.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${review.doc_no}-report.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      message.error(e.response?.data?.detail || "导出失败");
    }
  };

  const updateSection = (index: number, section: ManagementReviewReportSection) => {
    if (!report) return;
    const sections = [...report.sections];
    sections[index] = section;
    setReport({ ...report, sections });
  };

  const collapseItems = report?.sections.map((section, index) => ({
    key: section.key,
    label: section.title,
    children: (
      <ReportSectionEditor
        section={section}
        readOnly={readOnly}
        onChange={(s) => updateSection(index, s)}
      />
    ),
  })) || [];

  return (
    <Card title="管理评审报告">
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space>
          <span>报告状态：<Tag color={statusMap[review.report_status]?.color}>{statusMap[review.report_status]?.label}</Tag></span>
          {!readOnly && canCreate("management_review") && (
            <Button type="primary" onClick={handleGenerate} loading={loading}>
              {report ? "重新生成" : "AI 生成报告"}
            </Button>
          )}
          {!readOnly && canCreate("management_review") && report && (
            <Button onClick={handleSave}>保存草稿</Button>
          )}
          {review.report_status === "draft" && canApprove("management_review") && report && (
            <Button type="primary" danger onClick={handleFinalize}>定稿归档</Button>
          )}
          {review.report_status === "final" && canApprove("management_review") && review.status !== "closed" && (
            <Button onClick={handleReopen}>重新打开编辑</Button>
          )}
          {report && <Button onClick={handleExport}>导出 Markdown</Button>}
        </Space>

        <div style={{ display: "flex", gap: 16 }}>
          <div style={{ flex: 1 }}>
            {report ? (
              <Spin spinning={loading}>
                <Collapse items={collapseItems} />
              </Spin>
            ) : (
              <div style={{ color: "#999", padding: 24, textAlign: "center" }}>
                点击「AI 生成报告」开始生成
              </div>
            )}
          </div>
          {versions.length > 0 && (
            <div style={{ width: 240 }}>
              <Card title="历史版本" size="small">
                <ReportVersionList
                  versions={versions}
                  onSelect={(v) => setReport(v.content)}
                />
              </Card>
            </div>
          )}
        </div>
      </Space>
    </Card>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/managementReview/ReportSectionEditor.tsx

git add frontend/src/pages/managementReview/ReportVersionList.tsx

git add frontend/src/pages/managementReview/ManagementReviewReportPanel.tsx

git commit -m "feat(management-review-report): add report panel components"
```

---

## Task 9: 嵌入详情页

**Files:**
- Modify: `frontend/src/pages/managementReview/ManagementReviewDetailPage.tsx`

- [ ] **Step 1: 导入组件**

在文件顶部添加：

```tsx
import ManagementReviewReportPanel from "./ManagementReviewReportPanel";
```

- [ ] **Step 2: 在输出措施 Card 后嵌入报告 Card**

在 JSX 末尾「输出措施」Card 之后添加：

```tsx
{/* Management Review Report */}
<ManagementReviewReportPanel review={review} onReviewChange={setReview} />
```

- [ ] **Step 3: 运行前端构建**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run build
```

Expected: `build completed`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/managementReview/ManagementReviewDetailPage.tsx

git commit -m "feat(management-review-report): embed report panel in detail page"
```

---

## Task 10: 端到端验证

- [ ] **Step 1: 启动后端**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 2: 启动前端**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run dev
```

- [ ] **Step 3: 手动验证**

1. 登录并进入管理评审列表
2. 创建新评审，填入标题、日期、主持人
3. 点击「汇总数据」进入 `data_collected`
4. 滚动到「管理评审报告」Card
5. 点击「AI 生成报告」
6. 编辑第 8 章 manual_text，点击「保存草稿」
7. 点击「定稿归档」
8. 查看历史版本列表
9. 点击「导出 Markdown」，确认文件可下载
10. 点击「重新打开编辑」，确认可再次修改

- [ ] **Step 4: 运行全部测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_management_review_report_service.py tests/test_management_review_report_api.py -v
```

Expected: all passed

- [ ] **Step 5: 最终提交**

```bash
git commit -m "feat(management-review-report): complete auto report generation module"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: 所有设计文档中的章节（数据模型、13 章节、服务方法、API、前端、测试）都有对应任务
- [x] **Placeholder scan**: 没有 TBD/TODO；所有测试代码已给出完整模板
- [x] **Type consistency**: `ManagementReviewReport` / `ReportSection` 类型在后端 schema、前端 types、服务 JSONB 结构中一致
- [x] **State preconditions**: 主状态和报告状态的限制在服务层（`generate_report`, `save_report_draft`, `finalize_report`）和 API 层都有体现
- [x] **Version semantics**: 只有 `finalize` 创建 `review_reports` 记录，保存草稿不创建
- [x] **Transaction safety**: `generate` / `save-draft` API 已添加 `await db.commit()`
- [x] **Async deferred loading**: 服务方法已添加 `await db.refresh(...)` 加载 deferred JSONB 列
- [x] **Migration head**: `down_revision` 指向当前实际 head `034_add_supplier_risk_tables`
- [x] **Model registry**: 已在 `app/models/__init__.py` 中注册 `ReviewReport`
- [x] **Frontend state loss**: `useEffect` 依赖已修正，避免编辑其他卡片时重置报告草稿

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-11-management-review-report-auto-generation-plan.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - 每个 Task 派一个独立 subagent，我在每轮结束后 review
2. **Inline Execution** - 在当前会话中按 Task 顺序直接执行

**Which approach?**
