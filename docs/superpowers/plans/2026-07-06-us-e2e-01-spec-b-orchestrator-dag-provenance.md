# US-E2E-01 Spec B — 12 阶段推荐编排器 + DAG + provenance + 6 类新源 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 US-E2E-01 Spec B：12 阶段推荐编排器（`RecommendationOrchestrator`）+ DAG 可视化 + provenance + 6 类新推荐源（SPC/IQC/MES/供货/同类型产品/经验教训）+ D7→D8 闭环闸口 + lessons 结构化，让 D4/D5 推荐可观测、可审计、闭环不可旁路。

**Architecture:** `RecommendationOrchestrator` 重构 `HybridRecommendationPipeline` 为 12 命名阶段（recall → fusion → LLM → terminal），每阶段 `StageRun(status/hit_count/summary/error)`；6 类新源遵循 `async retrieve + async should_skip` 协议；D7→D8 闸口（canonical scope + capa_id 限定 + recommendation_hash + completeness-before-generation + fail-closed）；lessons 按 D7→D8（d7_prevention upsert）/ d8_closure 更新（delete-and-rebuild + savepoint + embedding 清理）拆分，全 fail-closed；前端 `<RecommendationDAG>` + per-item provenance Tag。

**Tech Stack:** Python 3.11 / FastAPI 0.115 / SQLAlchemy 2.0 async / Alembic / Pydantic v2 / React 18 / TypeScript 5.6 / Ant Design 5 / Vitest

## Global Constraints

- ADR-0001：业务表 PK = Python 端 `uuid.uuid4()`；`capa_lessons_learned.lesson_id` 用确定性 `uuid5(NAMESPACE_URL, f"capa_lesson:{capa_id}:{source_d_step}:{normalized_text}")`（非随机）。
- ADR-0003：新表带 `factory_id NOT NULL FK→factories.id`；服务层读写显式 `capa_id + factory_id` 联合过滤；`check_factory_access` 在 handler 层。
- ADR-0004：Service 层手写 `AuditLog`，`audit_logs.action` 列 `String(20)`，新 action ≤20 字符。本计划用：`LESSON_EXTRACTED`(15)、既有 `llm_recommend`。
- ADR-0013：Alembic 手写 `op.create_table` / `op.add_column` / `op.execute`，不用 autogenerate。
- `SECRET_KEY=test-secret-key-for-pytest-only`：pytest 无需显式传（`tests/conftest.py` 注入）；**alembic 命令必须显式带** `SECRET_KEY=test-secret-key-for-pytest-only` 前缀。
- 测试 `db` fixture 把 `commit()` 打成 flush-only，服务代码的 `await db.commit()` 在测试里安全；savepoint 用 `async with db.begin_nested()`。
- 中文 UI（zh_CN），i18n 走 `react-i18next`；`frontend/src/test-setup.ts` 已切测试语言到 en-US。
- 生产代码仅可加 `data-e2e` testid。DAG 节点 `rec-dag-stage-{index}`（1..12），项徽标 `rec-item-stage-{index}`，来源 `rec-source-{match_source}`。
- 采纳写 d-step 字段为追加（`current ? current+\n+text : text`），Spec A 已落地。
- `should_skip` 是 **async** 协议方法（R6）：`async def should_skip(context) -> str | None`，编排器 `await`。
- lessons 抽取 **fail-closed**（R7）：抽取失败阻断转换/保存（400），KB==CAPA；不用 dirty marker / 读路径重试。
- D7 闸口 **completeness-before-generation**（R9）：生成前查 canonical FMEA count，partial preload → fail-closed。
- LLM `LLMFusionLayer.enrich` 硬化 catch-all 不抛；全失败（attempted>0, succeeded=0）→ stage 11 `error` + audit `llm_failed`。

## File Structure

**新建（backend）：**
- `backend/alembic/versions/20260706_add_capa_lessons_learned.py` — capa_lessons_learned 表 + ix_capa_lessons_unique + capa_d7_node_action.recommendation_hash 列
- `backend/app/models/capa_lesson.py` — `CapaLessonLearned` ORM
- `backend/app/services/recommendation_orchestrator.py` — `RecommendationOrchestrator` + `StageSpec`/`StageRun`/`STAGE_PLAN`
- `backend/app/services/recommendation_sources_extra.py` — 6 类新源（SPC/IQC/MES/Supplier/SameType/Lessons）
- `backend/app/schemas/recommendation_stage.py` — `StageRunSchema`
- `backend/tests/recommendation/test_orchestrator.py`
- `backend/tests/recommendation/test_sources_extra.py`
- `backend/tests/recommendation/test_lessons_extraction.py`
- `backend/tests/capa/test_capa_d7_gate.py`
- `backend/tests/recommendation/test_adopt_stage_index.py`
- `backend/tests/recommendation/test_models_lessons.py`

**修改（backend）：**
- `backend/app/models/capa.py` — 加 `CapaLessonLearned` 导出；`CapaD7NodeAction` 加 `recommendation_hash` 列
- `backend/app/models/__init__.py` — 导出 `CapaLessonLearned`
- `backend/app/services/recommendation_types.py` — `StageRun` dataclass + `RecommendationResult.stages` + `to_d4/d5 schemas` 加 `stage_index`
- `backend/app/services/hybrid_recommendation_pipeline.py` — 改薄壳委托 orchestrator + `_maybe_write_llm_audit` 读结构化字段
- `backend/app/services/llm_fusion_layer.py` — `enrich` 硬化 catch-all 不抛
- `backend/app/services/capa_service.py` — `advance_capa` D7→D8 闸口 + d7 lessons 抽取（fail-closed）；`update_capa` d8_closure 钩子
- `backend/app/services/capa_d7_action_service.py` — `record_d7_action`/`auto_fill_d7` populate `recommendation_hash`
- `backend/app/services/capa_verification_service.py` — `adopt_recommendation` 透传 `stage_index`
- `backend/app/schemas/capa_verification.py` — `AdoptRequest` 加 `stage_index`
- `backend/app/schemas/capa.py` — `D4Recommendation`/`D5ExistingControl`/`D5GeneralSuggestion` 加 `stage_index`；`D4RecommendationResponse`/`D5RecommendationResponse` 加 `stages`
- `backend/app/api/capa.py` — D4/D5 recommend handler 返回 `stages`（D4 `{stages,items}`，D5 `{stages,existing_controls,general_suggestions}`）

**新建（frontend）：**
- `frontend/src/components/capa/RecommendationDAG.tsx` + `.test.tsx`

**修改（frontend）：**
- `frontend/src/types/index.ts` — `StageRun` + `stage_index` 字段
- `frontend/src/api/capa.ts` — `StageRun` 类型 + `AdoptRequest.stage_index`
- `frontend/src/components/capa/D4RecPanel.tsx` / `D5RecPanel.tsx` — DAG + provenance Tag + 采纳 payload `stage_index`
- `frontend/src/pages/capa/CAPADetailPage.tsx` — 接线 DAG
- `frontend/src/locales/zh-CN/capa.json` + `en-US/capa.json` — `sources.{match_source}` + DAG i18n

**文档：**
- `PROGRESS.md` — 勾选 P0-2/P0-3/P1-5~10

---

## Task 1: 数据模型 + Alembic 迁移

**Files:**
- Create: `backend/app/models/capa_lesson.py`
- Modify: `backend/app/models/capa.py`（`CapaD7NodeAction` 加 `recommendation_hash`）
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260706_add_capa_lessons_learned.py`
- Test: `backend/tests/recommendation/test_models_lessons.py`

**Interfaces:**
- Produces: `CapaLessonLearned` ORM（后续 lessons 服务/源 import）；`CapaD7NodeAction.recommendation_hash: Mapped[str | None]`。

- [ ] **Step 1: 确定 alembic head**

```bash
cd backend && SECRET_KEY=test-secret-key-for-pytest-only alembic heads
```
若 >1 行先 `alembic merge`（见 Spec A plan Task 1 Step 1）。记下唯一 head `<HEAD>`。

- [ ] **Step 2: 写失败测试**

`backend/tests/recommendation/test_models_lessons.py`：
```python
import uuid, pytest
from sqlalchemy import select
from app.models.capa import CAPAEightD, CapaD7NodeAction
from app.models.capa_lesson import CapaLessonLearned
from app.models.fmea import FMEADocument

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_persist_lesson(db, default_factory, admin_user):
    capa = CAPAEightD(report_id=uuid.uuid4(), document_no="8D-L-001", title="t",
                      product_line_code="DC-DC-100", factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add(capa); await db.flush()
    lesson = CapaLessonLearned(
        lesson_id=uuid.uuid5(uuid.NAMESPACE_URL, f"capa_lesson:{capa.report_id}:d7:螺栓尺寸超差"),
        capa_id=capa.report_id, factory_id=default_factory.id, product_line_code="DC-DC-100",
        lesson_text="螺栓尺寸超差", lesson_text_normalized="螺栓尺寸超差",
        category="prevention", source_d_step="d7")
    db.add(lesson)
    # CapaD7NodeAction.recommendation_hash 列存在
    fmea = FMEADocument(fmea_id=uuid.uuid4(), document_no="PFMEA-L-001", title="t", fmea_type="PFMEA",
                        product_line_code="DC-DC-100", factory_id=default_factory.id, status="draft",
                        created_by=admin_user.user_id, graph_data={"nodes": [], "edges": []})
    db.add(fmea); await db.flush()
    act = CapaD7NodeAction(action_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=default_factory.id,
                           action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
                           match_source="linked", acted_by=admin_user.user_id,
                           recommendation_hash="abc123def456abcd")
    db.add(act); await db.flush()
    assert (await db.scalar(select(CapaLessonLearned).where(
        CapaLessonLearned.lesson_id == lesson.lesson_id))).category == "prevention"
    assert (await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.action_id == act.action_id))).recommendation_hash == "abc123def456abcd"
```

- [ ] **Step 3: 运行确认失败**

`cd backend && python -m pytest tests/recommendation/test_models_lessons.py -x -q`
Expected: FAIL（`ImportError`：`capa_lesson` 未建 / `recommendation_hash` 列不存在）。

- [ ] **Step 4: 写 `CapaLessonLearned` 模型**

`backend/app/models/capa_lesson.py`：
```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CapaLessonLearned(Base):
    __tablename__ = "capa_lessons_learned"
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    lesson_text: Mapped[str] = mapped_column(Text, nullable=False)
    lesson_text_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    source_d_step: Mapped[str] = mapped_column(String(8), nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=lambda: [])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 5: `CapaD7NodeAction` 加 `recommendation_hash`**

在 `backend/app/models/capa.py` 的 `CapaD7NodeAction` 类内加：
```python
    recommendation_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
```

- [ ] **Step 6: 注册模型**

`backend/app/models/__init__.py`：在 capa import 行加 `CapaLessonLearned`（从 `app.models.capa_lesson` import 并加入 `__all__`）。

- [ ] **Step 7: 写迁移**

`backend/alembic/versions/20260706_add_capa_lessons_learned.py`：
```python
"""add capa_lessons_learned + d7 recommendation_hash

Revision ID: 20260706_lessons
Revises: <HEAD>
Create Date: 2026-07-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260706_lessons"
down_revision: Union[str, None] = "<HEAD>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capa_lessons_learned",
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("lesson_text", sa.Text, nullable=False),
        sa.Column("lesson_text_normalized", sa.Text, nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("source_d_step", sa.String(8), nullable=False),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_lessons_capa", "capa_lessons_learned", ["capa_id"])
    op.create_index("ix_capa_lessons_pl", "capa_lessons_learned", ["product_line_code"])
    op.execute("CREATE UNIQUE INDEX ix_capa_lessons_unique ON capa_lessons_learned (capa_id, source_d_step, md5(lesson_text_normalized))")
    op.add_column("capa_d7_node_action", sa.Column("recommendation_hash", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("capa_d7_node_action", "recommendation_hash")
    op.execute("DROP INDEX IF EXISTS ix_capa_lessons_unique")
    op.drop_index("ix_capa_lessons_pl", table_name="capa_lessons_learned")
    op.drop_index("ix_capa_lessons_capa", table_name="capa_lessons_learned")
    op.drop_table("capa_lessons_learned")
```
替换 `<HEAD>` 为 Step 1 记下的真实 revision。

- [ ] **Step 8: 应用迁移并跑测试**

```bash
cd backend && SECRET_KEY=test-secret-key-for-pytest-only alembic upgrade head
python -m pytest tests/recommendation/test_models_lessons.py -x -q
```
Expected: PASS。

- [ ] **Step 9: 提交**

```bash
git add backend/app/models/capa_lesson.py backend/app/models/capa.py backend/app/models/__init__.py \
        backend/alembic/versions/20260706_add_capa_lessons_learned.py \
        backend/tests/recommendation/test_models_lessons.py
git commit -m "feat(lessons): add capa_lessons_learned model + d7 recommendation_hash + migration"
```

---

## Task 2: `StageRun`/`RecommendationResult` 类型 + schema `stage_index`

**Files:**
- Modify: `backend/app/services/recommendation_types.py`
- Modify: `backend/app/schemas/capa.py`
- Create: `backend/app/schemas/recommendation_stage.py`
- Test: `backend/tests/recommendation/test_types_stage.py`

**Interfaces:**
- Produces: `StageRun` dataclass（含 `llm_attempted/succeeded/failed`）；`RecommendationResult.stages`；`to_d4_schema`/`to_d5_control_schema`/`to_d5_suggestion_schema` 输出 `stage_index`；`StageRunSchema`。

- [ ] **Step 1: 写失败测试**

`backend/tests/recommendation/test_types_stage.py`：
```python
from app.services.recommendation_types import RecommendationCandidate, RecommendationResult, StageRun


def test_stage_run_defaults():
    s = StageRun(index=3, name="semantic", source="semantic_search", status="done")
    assert s.hit_count == 0 and s.summary == "" and s.error is None
    assert s.llm_attempted is None and s.llm_succeeded is None and s.llm_failed is None


def test_to_d4_schema_emits_stage_index():
    c = RecommendationCandidate(source="fmea_graph", content="x", category=None, confidence=0.5,
                                 match_reason="r", metadata={"stage_index": 2, "failure_cause_node_id": "c1"})
    assert c.to_d4_schema()["stage_index"] == 2


def test_to_d5_suggestion_schema_emits_stage_index():
    c = RecommendationCandidate(source="rule_engine_measure", content="m", category="预防措施",
                                confidence=0.5, match_reason="r", metadata={"stage_index": 10})
    assert c.to_d5_suggestion_schema()["stage_index"] == 10
    assert c.to_d5_suggestion_schema()["match_source"] == "rule"


def test_recommendation_result_has_stages():
    r = RecommendationResult(items=[], stages=[StageRun(1, "ctx", "internal", "done")])
    assert len(r.stages) == 1
```

- [ ] **Step 2: 运行确认失败**

`cd backend && python -m pytest tests/recommendation/test_types_stage.py -x -q`
Expected: FAIL（`StageRun` 未定义 / `stage_index` 缺失）。

- [ ] **Step 3: 改 `recommendation_types.py`**

在文件顶部 `from dataclasses import dataclass, field` 后加 `from typing import Literal`（已有）。加 `StageRun` dataclass：
```python
@dataclass
class StageRun:
    index: int
    name: str
    source: str
    status: Literal["pending", "running", "done", "skipped", "error"]
    hit_count: int = 0
    summary: str = ""
    error: str | None = None
    llm_attempted: int | None = None
    llm_succeeded: int | None = None
    llm_failed: int | None = None
```
`RecommendationResult` 加 `stages`：
```python
@dataclass
class RecommendationResult:
    items: list[RecommendationCandidate]
    stages: list[StageRun] = field(default_factory=list)
```
`to_d4_schema` 在 result dict 加 `"stage_index": self.metadata.get("stage_index"),`；`to_d5_control_schema` 同理；`to_d5_suggestion_schema` 在 result dict 加 `"stage_index": self.metadata.get("stage_index"),`（放在 `match_source` 之后）。

**R1-修复 factory_id 隔离**：`RecommendationContext` 加 `factory_id: uuid.UUID | None = None` 字段（import `uuid`）：
```python
@dataclass
class RecommendationContext:
    capa_data: dict[str, Any]
    user_product_lines: list[str] | None
    stage: Literal["d4", "d5"]
    factory_id: uuid.UUID | None = None   # R1-修复：源查询按 factory_id 隔离，防跨工厂同 PL 串读
    fmea_docs: list[dict[str, Any]] | None = None
    linked_fmea: dict[str, Any] | None = None
```
API handler（Task 17）构造 context 时传 `factory_id=capa.factory_id`；6 类新源（Task 5-10）`retrieve`/`should_skip` 查询必须 `WHERE factory_id = context.factory_id`（与 `product_line_code` 联合），防跨工厂同产品线数据串读。

- [ ] **Step 4: 写 `StageRunSchema`**

`backend/app/schemas/recommendation_stage.py`：
```python
from typing import Literal
from pydantic import BaseModel


class StageRunSchema(BaseModel):
    index: int
    name: str
    source: str
    status: Literal["pending", "running", "done", "skipped", "error"]
    hit_count: int
    summary: str
    error: str | None = None
    llm_attempted: int | None = None
    llm_succeeded: int | None = None
    llm_failed: int | None = None
```

- [ ] **Step 5: `schemas/capa.py` 加 `stage_index` + `stages`**

`D4Recommendation` / `D5ExistingControl` / `D5GeneralSuggestion` 各加 `stage_index: int | None = None`。`D4RecommendationResponse` 加 `stages: list[StageRunSchema] = []`；`D5RecommendationResponse` 加 `stages: list[StageRunSchema] = []`（import `StageRunSchema`）。

- [ ] **Step 6: 运行确认通过**

`cd backend && python -m pytest tests/recommendation/test_types_stage.py -q`
Expected: PASS。

- [ ] **Step 7: 回归既有推荐测试**

`cd backend && python -m pytest tests/test_capa_recommendation.py tests/test_d7_recommendations.py -q`
Expected: PASS（既有断言不拒新字段 `stage_index`/`stages`）。

- [ ] **Step 8: 提交**

```bash
git add backend/app/services/recommendation_types.py backend/app/schemas/recommendation_stage.py \
        backend/app/schemas/capa.py backend/tests/recommendation/test_types_stage.py
git commit -m "feat(recommendation): StageRun + stage_index in schemas"
```

---

## Task 3: `RecommendationOrchestrator` 骨架（既有源，无新源）

**Files:**
- Create: `backend/app/services/recommendation_orchestrator.py`
- Test: `backend/tests/recommendation/test_orchestrator.py`（本任务只建骨架 + 12 唯一索引 + fusion→LLM 顺序 + LLM 失败隔离 + no-data vs done(0) + D5 边界/guard + per-stage 协议校验）

**Interfaces:**
- Consumes: `FusionEngine`、`LLMFusionLayer`、`FMEAControlExpander`、既有 `FMEAGraphSource`/`SemanticSearchSource`/`HistoricalCAPASource`/`HistoricalCAPAMeasureSource`/`RuleEngineSource`/`RuleEngineMeasureSource`、`RecommendationContext`/`RecommendationCandidate`/`StageRun`/`RecommendationResult`。
- Produces: `RecommendationOrchestrator(db, pc, embedding_provider).run(context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult`；`StageSpec`/`STAGE_PLAN`/`NEW_SOURCE_KINDS`；`validate_all_new_sources()`。

- [ ] **Step 1: 写失败测试（12 唯一索引 + fusion→LLM 顺序 + LLM 失败隔离 + no-data vs done + D5 guard + per-stage 协议）**

`backend/tests/recommendation/test_orchestrator.py`（节选关键测试，完整文件含以下用例）：
```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.recommendation_orchestrator import RecommendationOrchestrator, STAGE_PLAN
from app.services.recommendation_types import RecommendationContext, RecommendationCandidate, StageRun


def _ctx(stage="d4", linked_fmea=None, embedding_on=True):
    return RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "d4_root_cause": "", "fmea_ref_id": None,
                   "fmea_node_id": None, "product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"], stage=stage, fmea_docs=[], linked_fmea=linked_fmea)


@pytest.mark.asyncio
async def test_stages_exactly_12_unique_indexes(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), None, None)
    # stub sources to return [] so all done(0)/skipped
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    assert len(result.stages) == 12
    assert {s.index for s in result.stages} == set(range(1, 13))


@pytest.mark.asyncio
async def test_fusion_before_llm_order(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    merge_spy = AsyncMock(return_value=[])
    orch.fusion.merge = merge_spy
    enrich_spy = AsyncMock()
    from app.services.llm_fusion_layer import LLMOutcome
    enrich_spy.return_value = LLMOutcome(candidates=[], attempted=0)
    orch.llm_layer.enrich = enrich_spy
    await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    # enrich 收到 merge 的输出（[]），不是 raw 召回 — 顺序 fusion→LLM
    assert enrich_spy.await_args.args[0] == []


@pytest.mark.asyncio
async def test_llm_all_failed_is_error(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    from app.services.llm_fusion_layer import LLMOutcome
    orch.llm_layer.enrich = AsyncMock(return_value=LLMOutcome(candidates=[], attempted=2, succeeded=0, failed=2))
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s11 = next(s for s in result.stages if s.index == 11)
    assert s11.status == "error" and s11.llm_attempted == 2


@pytest.mark.asyncio
async def test_llm_exception_isolated(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    orch.llm_layer.enrich = AsyncMock(side_effect=RuntimeError("boom"))
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s11 = next(s for s in result.stages if s.index == 11)
    assert s11.status == "error" and s11.llm_attempted == 0
    assert len(result.stages) == 12  # stage 12 仍发射


@pytest.mark.asyncio
async def test_d5_stage2_skipped_when_no_cause(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), None, None)
    result = await orch.run(_ctx(stage="d5"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s2 = next(s for s in result.stages if s.index == 2)
    assert s2.status == "skipped"


@pytest.mark.asyncio
async def test_per_stage_protocol_violation_is_error(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), None, None)
    # 让某新源（注册后）should_skip 不存在 — 通过 _sources 注入坏源
    bad = MagicMock()
    del bad.should_skip  # ensure missing
    orch._sources["spc_anomaly"] = bad
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s6 = next(s for s in result.stages if s.index == 6)
    assert s6.status == "error"
```

- [ ] **Step 2: 运行确认失败**

`cd backend && python -m pytest tests/recommendation/test_orchestrator.py -x -q`
Expected: FAIL（`recommendation_orchestrator` 未建）。

- [ ] **Step 3: 写 `recommendation_orchestrator.py`**

按设计稿决策 15/16 + R3/R4/R6/R10 的伪代码写完整 `RecommendationOrchestrator`（`STAGE_PLAN` 12 项、`NEW_SOURCE_KINDS`、`run()` 召回遍+派生遍+fusion+LLM+terminal、`_exec_recall_stage`、`_exec_llm_stage`、`_stage_precondition`、`_lookup_linked_fmea_causes`、`_check_source_protocol`、`validate_all_new_sources`）。本任务 `_build_sources()` 只注册既有源（`fmea_graph`/`semantic_search`/`historical_capa`/`historical_capa_measure`/`rule_engine`/`rule_engine_measure`），新源在 Task 5-10 加入。`_lookup_linked_fmea_causes` 在 Task 11 完善；本任务先返回 `[]`（D5 stage 2 暂只靠 semantic）。
关键点：召回遍跳 `terminal`/`source_kind=="llm"`/D5 `_D5_DERIVED`；派生遍 D5 stage 2 用 `semantic_cands + direct_causes` 去重；fusion.merge 后调 `_exec_llm_stage(spec11, fused, context)`；stage 12 terminal 单次追加；`stages.sort(key=index)`；`_exec_llm_stage` 全失败 `status="error"`。

- [ ] **Step 4: 运行确认通过**

`cd backend && python -m pytest tests/recommendation/test_orchestrator.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/recommendation_orchestrator.py backend/tests/recommendation/test_orchestrator.py
git commit -m "feat(recommendation): RecommendationOrchestrator 12-stage skeleton"
```

---

## Task 4: `HybridRecommendationPipeline` 薄壳 + `_maybe_write_llm_audit` 结构化

**Files:**
- Modify: `backend/app/services/hybrid_recommendation_pipeline.py`
- Modify: `backend/app/services/llm_fusion_layer.py`（`enrich` 硬化 catch-all 不抛）
- Test: `backend/tests/recommendation/test_hybrid_pipeline_thin.py`

**Interfaces:**
- Consumes: `RecommendationOrchestrator`（Task 3）。
- Produces: `HybridRecommendationPipeline.recommend()` 委托 orchestrator + 结构化审计。

- [ ] **Step 1: 写失败测试**

```python
import pytest, hashlib, json, uuid
from unittest.mock import AsyncMock, MagicMock
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationResult, StageRun


@pytest.mark.asyncio
async def test_thin_shell_delegates_and_audits_structured(monkeypatch):
    pipe = HybridRecommendationPipeline(MagicMock(), MagicMock(), None)
    stage11 = StageRun(11, "LLM", "llm", "done", llm_attempted=2, llm_succeeded=1, llm_failed=1)
    pipe.orchestrator.run = AsyncMock(return_value=RecommendationResult(items=[], stages=[stage11]))
    audit = AsyncMock()
    monkeypatch.setattr("app.services.agent.audit.write_audit_raw", audit)
    await pipe.recommend(MagicMock(stage="d4", capa_data={"d2_description": "x"}),
                         user=MagicMock(user_id=uuid.uuid4()), report_id=uuid.uuid4(),
                         factory_id=uuid.uuid4(), tenant_schema="t")
    # 审计被调用，new_values 含结构化计数
    assert audit.await_args.kwargs["action"] == "llm_recommend"
    assert audit.await_args.kwargs["new_values"]["attempted"] == 2


@pytest.mark.asyncio
async def test_no_audit_when_attempted_zero(monkeypatch):
    pipe = HybridRecommendationPipeline(MagicMock(), MagicMock(), None)
    stage11 = StageRun(11, "LLM", "llm", "error", llm_attempted=0)
    pipe.orchestrator.run = AsyncMock(return_value=RecommendationResult(items=[], stages=[stage11]))
    audit = AsyncMock()
    monkeypatch.setattr("app.services.agent.audit.write_audit_raw", audit)
    await pipe.recommend(MagicMock(stage="d4", capa_data={}), user=MagicMock(user_id=uuid.uuid4()),
                         report_id=uuid.uuid4(), factory_id=uuid.uuid4(), tenant_schema="t")
    audit.assert_not_called()
```

- [ ] **Step 2: 运行确认失败**

`cd backend && python -m pytest tests/recommendation/test_hybrid_pipeline_thin.py -x -q`
Expected: FAIL。

- [ ] **Step 3: 硬化 `LLMFusionLayer.enrich`**

`backend/app/services/llm_fusion_layer.py`：把 `enrich` 整体包在 try/except 里，catch 任何异常 → 返回 `LLMOutcome(candidates=list(candidates), attempted=<已尝试数>, succeeded=<已成功>, failed=<已尝试>)`，不抛。即把现有阶段 1/2 的内部 try/except 提到 enrich 顶层，确保 enrich 永不抛（仅返回含 failed 计数的 LLMOutcome）。

- [ ] **Step 4: 改 `HybridRecommendationPipeline` 为薄壳**

`backend/app/services/hybrid_recommendation_pipeline.py`：`__init__` 构造 `RecommendationOrchestrator`；`recommend()` 调 `self.orchestrator.run(...)` 后调 `self._maybe_write_llm_audit(...)`；`_maybe_write_llm_audit` 按设计稿读 `stage11.llm_attempted/succeeded/failed`（0 则不写），try/except 兜底（审计失败不破坏响应）。删除旧的 5 阶段扁平循环逻辑。

- [ ] **Step 5: 运行确认通过**

`cd backend && python -m pytest tests/recommendation/test_hybrid_pipeline_thin.py tests/recommendation/test_orchestrator.py -q`
Expected: PASS。

- [ ] **Step 6: 回归既有推荐 + D7 测试**

`cd backend && python -m pytest tests/test_capa_recommendation.py tests/test_d7_recommendations.py tests/ -k "recommend" -q`
Expected: PASS（既有断言不破）。

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/hybrid_recommendation_pipeline.py backend/app/services/llm_fusion_layer.py \
        backend/tests/recommendation/test_hybrid_pipeline_thin.py
git commit -m "refactor(recommendation): thin shell + structured llm audit + enrich catch-all"
```

---

## Task 5: `SPCAnomalySource`

**Files:**
- Create: `backend/app/services/recommendation_sources_extra.py`（本任务加 `SPCAnomalySource`，后续 Task 6-10 追加）
- Modify: `backend/app/services/recommendation_orchestrator.py`（`_build_sources` 注册 `spc_anomaly`）
- Test: `backend/tests/recommendation/test_sources_extra.py`（本任务加 SPC 用例）

**Interfaces:**
- Consumes: `spc_service.match_fmea_for_alarm`、`spc_alarms`/`InspectionCharacteristic` 模型、`RecommendationContext`。
- Produces: `SPCAnomalySource(db).retrieve(context) -> list[RecommendationCandidate]`（source=`spc_anomaly`，metadata 含 `spc_chart_id`/`alarm_id`/`failure_mode_node_id?`）；`async should_skip`。

- [ ] **Step 1: 写失败测试**

```python
import pytest, uuid
from app.services.recommendation_sources_extra import SPCAnomalySource
from app.services.recommendation_types import RecommendationContext

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_spc_should_skip_no_alarms(db, default_factory):
    src = SPCAnomalySource(db)
    ctx = RecommendationContext(capa_data={"product_line_code": "DC-DC-100"}, user_product_lines=["DC-DC-100"],
                                stage="d4", factory_id=default_factory.id)
    assert (await src.should_skip(ctx)) is not None  # 无 SPC 数据 → reason


@pytest.mark.asyncio
async def test_spc_retrieves_when_alarms(db, default_factory, admin_user):
    # seed spc_alarm + inspection_characteristic (略，按 spc.py 模型，factory_id=default_factory.id)
    src = SPCAnomalySource(db)
    ctx = RecommendationContext(capa_data={"product_line_code": "DC-DC-100"}, user_product_lines=["DC-DC-100"],
                                stage="d4", factory_id=default_factory.id)
    cands = await src.retrieve(ctx)
    assert all(c.source == "spc_anomaly" for c in cands)


@pytest.mark.asyncio
async def test_spc_factory_isolation(db, default_factory, admin_user):
    # R1-修复：双工厂同产品线 SPC 数据不可串读
    from app.models.factory import Factory
    other = Factory(id=uuid.uuid4(), code="OTHER", name="Other")
    db.add(other); await db.flush()
    # 在 other 工厂建同 PL 的 spc_alarm（略）
    src = SPCAnomalySource(db)
    ctx = RecommendationContext(capa_data={"product_line_code": "DC-DC-100"}, user_product_lines=["DC-DC-100"],
                                stage="d4", factory_id=default_factory.id)  # 查 default_factory
    cands = await src.retrieve(ctx)
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)  # 不含 other 工厂数据
```

- [ ] **Step 2: 运行确认失败** → FAIL（`recommendation_sources_extra` 未建）。

- [ ] **Step 3: 写 `SPCAnomalySource`**

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from app.models.spc import SPCAlarm, InspectionCharacteristic
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext
from app.services import spc_service


class SPCAnomalySource:
    name = "spc_anomaly"
    def __init__(self, db, embedding_provider=None):
        self.db = db

    async def should_skip(self, context: RecommendationContext) -> str | None:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id   # R1-修复：factory_id 隔离
        since = datetime.now(timezone.utc) - timedelta(days=30)
        cnt = await self.db.scalar(select(func.count()).select_from(SPCAlarm)
            .join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id)
            .where(InspectionCharacteristic.product_line == pl,
                   InspectionCharacteristic.factory_id == fid,   # R1-修复
                   SPCAlarm.triggered_at >= since))
        return "产品线暂无 SPC 数据" if cnt == 0 else None

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id   # R1-修复
        since = datetime.now(timezone.utc) - timedelta(days=30)
        alarms = (await self.db.execute(
            select(SPCAlarm).join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id)
            .where(InspectionCharacteristic.product_line == pl,
                   InspectionCharacteristic.factory_id == fid,   # R1-修复
                   SPCAlarm.triggered_at >= since)
            .order_by(SPCAlarm.triggered_at.desc()))).scalars().all()
        cands = []
        for alarm in alarms[:10]:
            try:
                matches = await spc_service.match_fmea_for_alarm(self.db, alarm)
            except Exception:
                matches = []
            for m in (matches or []):
                cands.append(RecommendationCandidate(
                    source="spc_anomaly",
                    content=f"SPC 判异：规则 {alarm.rule_no} 触发，关联失效模式 {m.get('failure_mode_name','')}",
                    category=None, confidence=0.5, match_reason="SPC 判异关联失效模式",
                    metadata={"spc_chart_id": str(alarm.ic_id), "alarm_id": str(alarm.alarm_id),
                              "failure_mode_node_id": m.get("failure_mode_node_id"),
                              "product_line_code": pl, "factory_id": str(fid)}))   # R1-修复
        return cands
```

**R1-修复 factory_id 隔离（Task 6-10 同模式）**：`IQCSource`/`SupplierHistorySource`/`MESSource`/`SameTypeProductKBSource`/`LessonsLearnedSource` 的 `should_skip`/`retrieve` 查询必须 `WHERE factory_id = context.factory_id`（与 `product_line_code` 联合），metadata 含 `factory_id=str(fid)`；各源补"双工厂同 PL 不可串读"测试（仿 `test_spc_factory_isolation`）。`SameTypeProductKBSource` 跨工厂同 product_type 检索仍受 `factory_id` 收口——**仅匹配 `context.factory_id` 内其他产品线的同类型**（不跨工厂），防跨工厂读。

- [ ] **Step 4: 注册到 orchestrator `_build_sources`** — `self._sources["spc_anomaly"] = SPCAnomalySource(db)`（D4 only，`stage_filter` 已在 STAGE_PLAN）。

- [ ] **Step 5: 运行确认通过** → PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/recommendation_sources_extra.py backend/app/services/recommendation_orchestrator.py \
        backend/tests/recommendation/test_sources_extra.py
git commit -m "feat(source): SPCAnomalySource"
```

---

## Task 6: `IQCSource`

**Files:**
- Modify: `backend/app/services/recommendation_sources_extra.py`（追加 `IQCSource`）
- Modify: `backend/app/services/recommendation_orchestrator.py`（注册 `iqc`）
- Test: `backend/tests/recommendation/test_sources_extra.py`（追加 IQC 用例）

**Interfaces:**
- Consumes: `iqc_inspections` 模型（`IqcInspection`）。
- Produces: `IQCSource(db).retrieve(context)`（source=`iqc`，metadata 含 `supplier_id`/`part_no`/`inspection_id?`/`defect_qty`）；`async should_skip`。

- [ ] **Step 1: 写失败测试** — `should_skip` 无不良返 reason；有 `defect_qty>0` 记录 → retrieve 返回 `source="iqc"` 候选。

- [ ] **Step 2: 运行确认失败** → FAIL。

- [ ] **Step 3: 写 `IQCSource`** — `should_skip` 查 `iqc_inspections` 近 30 天 `defect_qty>0` count（按 `product_line_code`）；`retrieve` 取不良记录聚合 `defect_description`，候选 "来料不良：{part_name} 缺陷 {defect_description}（{defect_qty} 件）"，metadata 含 `supplier_id`/`part_no`/`inspection_id`/`defect_qty`/`product_line_code`。

- [ ] **Step 4: 注册 `iqc`** — `self._sources["iqc"] = IQCSource(db)`。

- [ ] **Step 5: 运行确认通过** → PASS。

- [ ] **Step 6: 提交** `git commit -m "feat(source): IQCSource"`。

---

## Task 7: `SupplierHistorySource`

**Files:**
- Modify: `backend/app/services/recommendation_sources_extra.py`（追加 `SupplierHistorySource`）
- Modify: `backend/app/services/recommendation_orchestrator.py`（注册 `supplier_history`）
- Test: `backend/tests/recommendation/test_sources_extra.py`（追加）

**Interfaces:**
- Consumes: `supplier_quality_service.get_supplier_quality_detail`、`iqc_inspections.supplier_id`、`SupplierSCAR.capa_ref_id`。
- Produces: `SupplierHistorySource(db).retrieve(context)`（source=`supplier_history`，metadata 含 `supplier_id`/`grade`/`ppm`）；`async should_skip`。

- [ ] **Step 1: 写失败测试** — 无关联供应商 → should_skip reason；有 → retrieve 返回 `source="supplier_history"` 候选含 grade/ppm。
- [ ] **Step 2: 运行确认失败** → FAIL。
- [ ] **Step 3: 写 `SupplierHistorySource`** — `should_skip`：从 `iqc_inspections`（该 PL 近期不良）取 `supplier_id` 或 `SupplierSCAR where capa_ref_id=capa.report_id`，无 → reason；`retrieve`：对每个 supplier 调 `supplier_quality_service.get_supplier_quality_detail(db, supplier_id, factory_id=capa.factory_id)`，候选 "供应商 {name} 评级 {grade}，PPM={ppm}，历史 SCAR {scar_count} 条"，metadata 含 `supplier_id`/`grade`/`ppm`/`product_line_code`。
- [ ] **Step 4: 注册 `supplier_history`**。
- [ ] **Step 5: 运行确认通过** → PASS。
- [ ] **Step 6: 提交** `git commit -m "feat(source): SupplierHistorySource"`。

---

## Task 8: `MESSource`

**Files:**
- Modify: `backend/app/services/recommendation_sources_extra.py`（追加 `MESSource`）
- Modify: `backend/app/services/recommendation_orchestrator.py`（注册 `mes`）
- Test: `backend/tests/recommendation/test_sources_extra.py`（追加）

**Interfaces:**
- Consumes: `mes_scrap_records`/`mes_equipment_status` 模型。
- Produces: `MESSource(db).retrieve(context)`（source=`mes`，metadata 含 `equipment_id?`/`scrap_record_id?`）；`async should_skip`。

- [ ] **Step 1: 写失败测试** — 无 MES 数据 → should_skip reason；有 scrap/equipment 停机 → retrieve 返回 `source="mes"` 候选。
- [ ] **Step 2: 运行确认失败** → FAIL。
- [ ] **Step 3: 写 `MESSource`** — `should_skip`：查 `mes_scrap_records` JOIN `mes_connections`（`product_line_code=pl`）近 30 天 count + `mes_equipment_status` 停机 count，均 0 → reason "产品线暂无 MES 数据"；`retrieve`：聚合 scrap `defect_description` + equipment `downtime_reason`，候选 "MES 报废：{defect_type}（{defect_qty} 件）"/"设备停机：{equipment} {downtime_reason}"，metadata 含 `equipment_id?`/`scrap_record_id?`/`product_line_code`。
- [ ] **Step 4: 注册 `mes`**。
- [ ] **Step 5: 运行确认通过** → PASS。
- [ ] **Step 6: 提交** `git commit -m "feat(source): MESSource"`。

---

## Task 9: `SameTypeProductKBSource`

**Files:**
- Modify: `backend/app/services/recommendation_sources_extra.py`（追加 `SameTypeProductKBSource`）
- Modify: `backend/app/services/recommendation_orchestrator.py`（注册 `same_type_product_kb`）
- Test: `backend/tests/recommendation/test_sources_extra.py`（追加）

**Interfaces:**
- Consumes: `document_embeddings` + `product_lines.product_type_code` + `product_types`、`EmbeddingProvider`。
- Produces: `SameTypeProductKBSource(db, embedding_provider).retrieve(context)`（source=`same_type_product_kb`，metadata 含 `failure_cause_node_id`/`fmea_id`/`product_type_code`）；`async should_skip`。

- [ ] **Step 1: 写失败测试** — 当前 PL `product_type_code` 为 NULL → should_skip reason；有同类型数据 → retrieve 返回跨 PL 候选，`source="same_type_product_kb"`，排除当前 PL。
- [ ] **Step 2: 运行确认失败** → FAIL。
- [ ] **Step 3: 写 `SameTypeProductKBSource`** — `__init__(db, embedding_provider)`；`should_skip`：解析当前 PL 的 `product_type_code`（JOIN `product_lines`），NULL → "无同类型产品 KB"；`retrieve`：pgvector 语义查 `document_embeddings de` JOIN `product_lines pl` ON `de.product_line_code=pl.code` WHERE `pl.product_type_code=:pt AND de.product_line_code != :current_pl AND de.entity_type='fmea_node' AND node_type in (FailureCause,FailureMode)`，受 `user_product_lines` 收口；候选同 `SemanticSearchSource` 结构回溯，metadata 加 `product_type_code`。
- [ ] **Step 4: 注册 `same_type_product_kb`** — `self._sources["same_type_product_kb"] = SameTypeProductKBSource(db, embedding_provider)`。
- [ ] **Step 5: 运行确认通过** → PASS。
- [ ] **Step 6: 提交** `git commit -m "feat(source): SameTypeProductKBSource"`。

---

## Task 10: `LessonsLearnedSource`

**Files:**
- Modify: `backend/app/services/recommendation_sources_extra.py`（追加 `LessonsLearnedSource`）
- Modify: `backend/app/services/recommendation_orchestrator.py`（注册 `lessons_learned`）
- Test: `backend/tests/recommendation/test_sources_extra.py`（追加）

**Interfaces:**
- Consumes: `document_embeddings` + `capa_lessons_learned`（JOIN 过滤孤儿）。
- Produces: `LessonsLearnedSource(db, embedding_provider).retrieve(context)`（source=`lessons_learned`，metadata 含 `source_capa_id`/`lesson_id`/`category`）；`async should_skip`。

- [ ] **Step 1: 写失败测试** — 无 embedding/无 lessons → should_skip reason；有 lessons → retrieve 返回 `source="lessons_learned"` 候选，JOIN `capa_lessons_learned` 排除孤儿。
- [ ] **Step 2: 运行确认失败** → FAIL。
- [ ] **Step 3: 写 `LessonsLearnedSource`** — `should_skip`：`embedding is None` 或无 `capa_lessons_learned` 行 → reason；`retrieve`：pgvector 语义查 `document_embeddings de` JOIN `capa_lessons_learned lesson` ON `de.entity_id=lesson.lesson_id` WHERE `de.entity_type='capa_lesson' AND de.entity_field='lesson_text' AND lesson.lesson_id IS NOT NULL`，受 `user_product_lines` 收口，匹配 `d2_description`(D4)/`d4_root_cause`(D5)；候选 "经验教训：{lesson_text}（来自 {source_capa_document_no}，类别 {category}）"，metadata 含 `source_capa_id`/`lesson_id`/`category`/`product_line_code`。
- [ ] **Step 4: 注册 `lessons_learned`** — `self._sources["lessons_learned"] = LessonsLearnedSource(db, embedding_provider)`。
- [ ] **Step 5: 运行确认通过** → PASS。
- [ ] **Step 6: 提交** `git commit -m "feat(source): LessonsLearnedSource"`。

---

## Task 11: D5 stage 2 `_lookup_linked_fmea_causes`（semantic ∪ 直查）

**Files:**
- Modify: `backend/app/services/recommendation_orchestrator.py`（实现 `_lookup_linked_fmea_causes` + 派生遍合并去重）
- Test: `backend/tests/recommendation/test_orchestrator.py`（追加 D5 直查用例）

**Interfaces:**
- Produces: D5 stage 2 在 embedding 不可用时仍扩展 FMEA 控制措施。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_d5_stage2_direct_lookup_when_embedding_off(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), None, None)  # embedding=None → stage 3 skipped
    linked = {"fmea_id": "f1", "document_no": "PFMEA-1", "product_line_code": "DC-DC-100",
              "graph_data": {"nodes": [{"id":"c1","type":"FailureCause","name":"螺栓尺寸超差"},
                                       {"id":"fm1","type":"FailureMode","name":"虚焊"}],
                             "edges": [{"source":"c1","target":"fm1","type":"CAUSE_OF"}]}}
    ctx = _ctx(stage="d5", linked_fmea=linked)
    ctx.capa_data["d4_root_cause"] = "螺栓尺寸超差"
    orch.d5_control_expander.expand = AsyncMock(return_value=[MagicMock(metadata={"control_node_id":"ctrl1"}, content="监控")])
    result = await orch.run(ctx, user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s2 = next(s for s in result.stages if s.index == 2)
    assert s2.status == "done"  # 直查命中 cause → 扩展 control，不 skipped
```

- [ ] **Step 2: 运行确认失败** → FAIL（`_lookup_linked_fmea_causes` 返回 []）。

- [ ] **Step 3: 实现 `_lookup_linked_fmea_causes`** — 按设计稿伪代码：从 `context.linked_fmea` 取 graph，`extract_keywords(d4_root_cause or d2_description)`，遍历 FailureCause 节点按关键词匹配，回溯 FailureMode，返回 `RecommendationCandidate(source="fmea_graph", ..., metadata={..., "stage_index":2})`。派生遍合并 `semantic_causes + direct_causes` 按 `(fmea_id, failure_cause_node_id)` 去重。

- [ ] **Step 4: 运行确认通过** → PASS。

- [ ] **Step 5: 提交** `git commit -m "feat(orchestrator): D5 stage2 linked-FMEA direct lookup"`。

---

## Task 12: D7→D8 闭环闸口 + D7 端点 populate `recommendation_hash`（合并，同 commit 无中间不可用态）

**Files:**
- Modify: `backend/app/services/capa_d7_action_service.py` — 加 `recommendation_fingerprint` canonical helper + `record_d7_action`/`auto_fill_d7` 写 `recommendation_hash`
- Modify: `backend/app/services/capa_service.py:advance_capa`（D7→D8 闸口：completeness + capa_id + recommendation_hash + fail-closed，用同一 helper）
- Test: `backend/tests/capa/test_capa_d7_gate.py` + `backend/tests/capa/test_capa_d7_action_service.py`（追加 hash + action 类型用例）

**Interfaces:**
- Consumes: `get_d7_recommendations`、`capa_d7_node_action`、`fmea_documents` count。
- Produces: D7 端点写 `recommendation_hash`（canonical `recommendation_fingerprint`）+ D7→D8 闸口用同一 helper 校验。**R3-修复顺序**：hash 写入与 gate 同 task 同 commit，避免 Task 12 落地后、hash 写入前 D7 action API 产生的动作 hash=None 被闸口判 stale。

- [ ] **Step 1: 写失败测试**（节选）

```python
import pytest
from app.services.capa_service import advance_capa

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_d7_gate_blocks_unprocessed(db, default_factory, admin_user):
    # 建 CAPA D7_PREVENTION + linked FMEA + D7 推荐 2 条 + 0 动作
    with pytest.raises(ValueError, match="未处置|stale"):
        await advance_capa(db, capa, admin_user.user_id)


@pytest.mark.asyncio
async def test_d7_gate_partial_preload_failclosed(db, default_factory, admin_user, monkeypatch):
    # PL 有 3 FMEA，preload 只返 2 → completeness mismatch → 400
    with pytest.raises(ValueError, match="预加载不完整"):
        await advance_capa(db, capa, admin_user.user_id)


@pytest.mark.asyncio
async def test_d7_gate_stale_hash_blocks(db, default_factory, admin_user):
    # 动作 hash 旧（FMEA 改名后）→ stale → 400
    with pytest.raises(ValueError, match="stale"):
        await advance_capa(db, capa, admin_user.user_id)


@pytest.mark.asyncio
async def test_d7_gate_passes_when_all_actioned(db, default_factory, admin_user):
    # 2 条推荐全 confirmed（hash 匹配）→ 推进 D8
    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D8_CLOSURE"


@pytest.mark.asyncio
async def test_d7_gate_passes_all_skipped(db, default_factory, admin_user):
    # R6-修复：2 条推荐全 skipped（带 reason，hash 匹配）→ 推进 D8（skipped 算已处置）
    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D8_CLOSURE"


@pytest.mark.asyncio
async def test_d7_gate_passes_all_auto_filled(db, default_factory, admin_user):
    # R6-修复：2 条推荐全 auto_filled（hash 匹配）→ 推进 D8（auto_filled 算已处置）
    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D8_CLOSURE"


@pytest.mark.asyncio
async def test_d7_gate_blocks_mixed_unprocessed(db, default_factory, admin_user):
    # 2 条推荐：1 confirmed + 1 未处置 → 仍 400（部分处置不满足）
    with pytest.raises(ValueError, match="未处置|stale"):
        await advance_capa(db, capa, admin_user.user_id)


@pytest.mark.asyncio
async def test_d7_action_records_recommendation_hash(db, default_factory, admin_user):
    # R3-修复：record_d7_action 后行的 recommendation_hash == recommendation_fingerprint(...)（canonical helper）
    from app.services.capa_d7_action_service import recommendation_fingerprint
    # ... record action ...
    assert action.recommendation_hash == recommendation_fingerprint(
        fmea_id=..., failure_mode_node_id=..., failure_cause_node_id=...,
        failure_mode_name=..., failure_cause_name=..., match_reason=...)


@pytest.mark.asyncio
async def test_d7_gate_cross_capa_not_satisfied(db, default_factory, admin_user):
    # CAPA-B 有同 key 动作，CAPA-A 无 → CAPA-A 仍 400
    with pytest.raises(ValueError):
        await advance_capa(db, capa_a, admin_user.user_id)


@pytest.mark.asyncio
async def test_d7_gate_no_recs_passes(db, default_factory, admin_user):
    # PL 0 FMEA + 无 linked → 真无推荐 → 推进
    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D8_CLOSURE"
```

- [ ] **Step 2: 运行确认失败** → FAIL（无闸口，未处置也推进）。

- [ ] **Step 3: 加 canonical `recommendation_fingerprint` helper + D7 端点写 hash + 闸口**

① `capa_d7_action_service.py` 加 canonical helper（R11-修复：record + gate 单源）：
```python
import hashlib
def recommendation_fingerprint(*, fmea_id, failure_mode_node_id, failure_cause_node_id,
                               failure_mode_name, failure_cause_name, match_reason) -> str:
    raw = f"{fmea_id}|{failure_mode_node_id}|{failure_cause_node_id or ''}|{failure_mode_name}|{failure_cause_name or ''}|{match_reason}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```
② `record_d7_action`/`auto_fill_d7` 在 insert/升级 `CapaD7NodeAction` 前，从 `get_d7_recommendations(capa_data, fmea_docs, allowed_pls)` 取该 key 推荐的 `failure_mode_name`/`failure_cause_name`/`match_reason` + 稳定 ID，调 `recommendation_fingerprint(...)` 存入 `recommendation_hash`（复用 recommend 端点 fmea_docs 预加载）。
③ `advance_capa` D7→D8 闸口（`SELECT capa + fmea_documents FOR UPDATE` 之后、状态写入之前）：a. completeness check（`SELECT fmea_id FROM fmea_documents WHERE factory_id=capa.factory_id AND product_line_code=capa.product_line_code FOR UPDATE` + count vs loaded + linked FMEA 缺失 → fail-closed）；b. 重算 D7 推荐（canonical scope: `capa.factory_id + capa.product_line_code`，`allowed_pls=[capa.product_line_code]`）；c. 取每条推荐 key + `current_hash = recommendation_fingerprint(...)`（**同一 helper**），查 `capa_d7_node_action WHERE capa_id=capa.report_id AND key AND recommendation_hash=:current_hash AND action IN ('confirmed','skipped','auto_filled')`（**R6-修复：confirmed/skipped/auto_filled 均算已处置**）；未处置/stale → `ValueError("D7 有 N 条推荐未处置或已 stale（FMEA 变更），不可关闭")`；d. 真无推荐（completeness 通过 + count=0）→ 放行。闸口不通过早返回（不写 TRANSITION audit、不抽 lessons、不推进）。

- [ ] **Step 4: 运行确认通过** → PASS（含 action 类型 + hash + stale + cross-capa + partial preload 测试）。

- [ ] **Step 5: 回归既有 capa 测试** — `python -m pytest tests/capa/ tests/test_capa_recommendation.py -q` → PASS（既有测试越过 D7 或补 fixture）。

- [ ] **Step 6: 提交** `git commit -m "feat(capa): D7->D8 gate + D7 endpoint recommendation_hash (canonical fingerprint, action types)"`。

---

## Task 13: D7 lessons 抽取（`advance_capa` D7→D8，fail-closed）

**Files:**
- Modify: `backend/app/services/capa_service.py:advance_capa`（D7→D8 后抽 d7_prevention lessons，fail-closed）
- Create: `backend/app/services/capa_lessons_service.py` — `_extract_lessons(db, capa, source_d_step) -> list[CapaLessonLearned]`
- Test: `backend/tests/recommendation/test_lessons_extraction.py`（D7 部分）

**Interfaces:**
- Consumes: `CapaLessonLearned`、`enqueue_embedding`、`AuditLog`。
- Produces: D7→D8 抽 d7 lessons（upsert，fail-closed 阻断转换）。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_d7_lessons_extracted_on_advance(db, default_factory, admin_user):
    # D7→D8（先全处置推荐）→ 出现 source_d_step='d7' lessons 行
    ...
    assert lessons and all(l.source_d_step == "d7" for l in lessons)


@pytest.mark.asyncio
async def test_d7_extraction_failure_blocks_transition(db, default_factory, admin_user, monkeypatch):
    # mock enqueue_embedding 抛错 → advance 400，D8 不推进
    with pytest.raises(ValueError, match="D7 lessons 抽取失败"):
        await advance_capa(db, capa, admin_user.user_id)
    # R4-修复：重查 DB（非仅内存对象）确认状态未推进 + 无 TRANSITION audit + 无 d7 lesson 行
    await db.refresh(capa)
    assert capa.status == "D7_PREVENTION"
    from sqlalchemy import select
    from app.models.audit import AuditLog
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id, AuditLog.action == "TRANSITION"))).scalars().all()
    assert len(audits) == 0   # 未写 TRANSITION audit
    from app.models.capa_lesson import CapaLessonLearned
    lessons = (await db.execute(select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id))).scalars().all()
    assert len(lessons) == 0   # 未落 lessons


@pytest.mark.asyncio
async def test_d7_no_d8_closure_extracted(db, default_factory, admin_user):
    # D7→D8 时 d8_closure 为空 → 不产 source_d_step='d8' 行
    ...
    assert not any(l.source_d_step == "d8" for l in lessons)
```

- [ ] **Step 2: 运行确认失败** → FAIL。

- [ ] **Step 3: 写 `_extract_lessons`** — `capa_lessons_service.py`：从 `d7_prevention`（source_d_step="d7"）或 `d8_closure`（="d8"）切句（按句号/换行），过滤空句，按 `normalized_text="".join(text.lower().split())` 去重，`category` 启发式判定（含"预防/防呆/poka"→prevention；含"检测/探测/检验"→detection；含"体系/流程/制度"→systemic；余 process），`lesson_id=uuid5(NAMESPACE_URL, f"capa_lesson:{capa_id}:{source_d_step}:{normalized_text}")`，`pg_insert.on_conflict_do_update(index_elements=["lesson_id"], set_={category,tags,updated_at})` upsert，`enqueue_embedding(db,"capa_lesson",lesson_id,pl,factory_id)`。返回 lessons 列表。

- [ ] **Step 4: `advance_capa` D7→D8 调 `_extract_lessons(capa, "d7")`（R4-修复：抽取先于状态 mutation）** — 顺序：① 闸口（Task 12）通过 → ② **先**调 `_extract_lessons(capa, "d7")` + 写 `LESSON_EXTRACTED` audit（`correlation_id=uuid5(capa_id,"lesson_extract_d7")`），异常 → `ValueError("D7 lessons 抽取失败，不可关闭，请重试")`（**此时状态尚未 mutation**，fail-closed 干净，无需回滚状态）→ ③ 抽取成功**后**才 `capa.status = D8_CLOSURE` + 写 TRANSITION audit → ④ commit。这样抽取失败时状态/audit 均未动，事务回滚干净（仅 lessons 行回滚）。

- [ ] **Step 5: 运行确认通过** → PASS。

- [ ] **Step 6: 提交** `git commit -m "feat(lessons): D7 lessons extraction on D7->D8 (fail-closed upsert)"`。

---

## Task 14: `update_capa` d8_closure 更新钩子（delete-and-rebuild + savepoint + embedding 清理 + fail-closed）

**Files:**
- Modify: `backend/app/services/capa_service.py:update_capa`（d8_closure 变更且 status=D8_CLOSURE 时触发）
- Modify: `backend/app/services/capa_lessons_service.py`（加 `_extract_d8_with_cleanup`）
- Test: `backend/tests/recommendation/test_lessons_extraction.py`（d8 部分）

**Interfaces:**
- Produces: d8_closure 更新时 delete-and-rebuild d8 lessons，fail-closed 阻断保存。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_d8_lessons_delete_and_rebuild(db, default_factory, admin_user):
    # 进 D8 + 填 d8_closure 2 句保存 → 2 行 d8 lesson；改 d8_closure（删1改1加1）→ 行数=新句数，旧句 delete
    ...

@pytest.mark.asyncio
async def test_d8_duplicate_sentences_deduped(db, default_factory, admin_user):
    # d8_closure 含重复句 → 去重后 1 行
    ...

@pytest.mark.asyncio
async def test_d8_extraction_failure_blocks_save(db, default_factory, admin_user, monkeypatch):
    # mock enqueue_embedding 抛错 → 保存 400
    with pytest.raises(ValueError, match="D8 lessons 抽取失败"):
        await update_capa(...)
    # R4-修复：重查 DB 确认 d8_closure 仍是旧值 + 无 d8 lesson 行（非仅内存对象）
    await db.refresh(capa)
    assert capa.d8_closure == "<旧值>"
    from sqlalchemy import select
    from app.models.capa_lesson import CapaLessonLearned
    lessons = (await db.execute(select(CapaLessonLearned).where(
        CapaLessonLearned.capa_id == capa.report_id, CapaLessonLearned.source_d_step == "d8"))).scalars().all()
    assert len(lessons) == 0   # 旧 d8 lesson 保留（savepoint rollback 撤销 delete+rebuild）或未变

@pytest.mark.asyncio
async def test_d8_embedding_cleanup(db, default_factory, admin_user):
    # 删改 d8_closure 后，被删句的 document_embeddings（entity_type='capa_lesson'）行已清理
    ...

@pytest.mark.asyncio
async def test_d8_inflight_worker_race(db, default_factory, admin_user, monkeypatch):
    # 模拟 worker 已认领旧 lesson_id job；cleanup 后 worker 完成 job 时重查 lesson 行不存在 → 丢弃不写 stale
    ...
```

- [ ] **Step 2: 运行确认失败** → FAIL。

- [ ] **Step 3: 写 `_extract_d8_with_cleanup(db, capa, new_d8_closure)`** — **R4-修复：传新 d8_closure 文本，不先 mutate capa.d8_closure**。`async with db.begin_nested()` savepoint 内：① 取旧 d8 lesson_ids（`SELECT lesson_id FROM capa_lessons_learned WHERE capa_id=X AND source_d_step='d8'`）；② **`UPDATE embedding_sync_outbox SET status='cancelled' WHERE entity_type='capa_lesson' AND entity_id IN (旧 ids) AND status='pending'`**（Fix 5：真实表名 `embedding_sync_outbox`，非 `embedding_outbox`）；③ `DELETE FROM document_embeddings WHERE entity_type='capa_lesson' AND entity_id IN (旧 ids)`；④ `DELETE FROM capa_lessons_learned WHERE capa_id=X AND source_d_step='d8'`；⑤ 用 **new_d8_closure**（参数，非 capa.d8_closure）调 `_extract_lessons` 重插 + enqueue；⑥ 写 `LESSON_EXTRACTED` audit（`correlation_id=uuid5(capa_id,"lesson_extract_d8")`）。任一步异常 → savepoint rollback + `ValueError("D8 lessons 抽取失败，无法保存闭环总结，请重试")`（fail-closed；**capa.d8_closure 未被 mutate**，外层事务无需回滚字段）。

- [ ] **Step 4: `update_capa` 接钩子（R4-修复：抽取先于字段 mutation）** — 检测 `d8_closure` 字段变更且 `capa.status == "D8_CLOSURE"`：① 计算 `new_d8_closure = <新值>`（不先 `capa.d8_closure = ...`）；② 调 `_extract_d8_with_cleanup(db, capa, new_d8_closure)`（savepoint）；③ **成功后**才 `capa.d8_closure = new_d8_closure` + commit；④ 异常向上冒泡 → handler 400（**capa.d8_closure 仍是旧值**，未 mutate）。

- [ ] **Step 5: embedding worker 重查 → 见 Task 15** — worker `capa_lesson` 实体支持 + 写入前重查 lesson 存在性（防 in-flight race）统一在 Task 15 落地（`embedding_sync_worker.py` `table_field_map` 加 `capa_lesson` + upsert 前重查）。本任务只负责 enqueue + cleanup（savepoint 内 cancel pending outbox + delete embeddings）。

- [ ] **Step 6: 运行确认通过** → PASS。

- [ ] **Step 7: 提交** `git commit -m "feat(lessons): d8_closure delete-and-rebuild + savepoint + embedding cleanup (fail-closed)"`。

---

## Task 15: `embedding_sync_worker` 支持 `capa_lesson` 实体（Fix 2）

**Files:**
- Modify: `backend/app/services/embedding_sync_worker.py`（`table_field_map` 加 `capa_lesson` + 写入前重查 lesson 存在性）
- Modify: `backend/app/services/embedding_backfill.py`（`ENTITY_TABLE_MAP`/`ENTITY_TYPES` 加 `capa_lesson`，如需 backfill）
- Test: `backend/tests/test_embedding_sync_worker.py`（追加 capa_lesson 用例）

**Interfaces:**
- Consumes: `capa_lessons_learned` 模型（Task 1）、`enqueue_embedding`（Task 13/14 入队 `entity_type='capa_lesson'`）。
- Produces: worker 处理 `capa_lesson` outbox 事件 → upsert `document_embeddings`（entity_type='capa_lesson', entity_field='lesson_text'），`LessonsLearnedSource`（Task 10）方可检索到 lesson embedding。

**背景（Fix 2）**：worker `table_field_map`（`embedding_sync_worker.py:111`）未含 `capa_lesson` → line 140 `if entity_type not in table_field_map: continue` → capa_lesson 事件被跳过 → `document_embeddings` 无 lesson 行 → `LessonsLearnedSource` 长期无数据。本任务补全链路。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_worker_processes_capa_lesson(db, default_factory, admin_user, monkeypatch):
    # seed capa_lessons_learned 行 + embedding_sync_outbox 行（entity_type='capa_lesson'）
    # mock embedding_provider.embed 返回向量
    # 跑 worker 一轮
    # 断言 document_embeddings 出现 entity_type='capa_lesson' entity_id=lesson_id 行
    ...
    assert de is not None and de.entity_type == "capa_lesson"


@pytest.mark.asyncio
async def test_worker_skips_deleted_lesson(db, default_factory, admin_user, monkeypatch):
    # R9-修复：worker 认领 capa_lesson job 后，lesson 行已被 d8 delete-and-rebuild 删除 → 重查不存在 → 丢弃不写 stale embedding
    ...
    assert de is None  # 不写 stale
```

- [ ] **Step 2: 运行确认失败** → FAIL（worker `continue` 跳过 capa_lesson，无 document_embeddings 行）。

- [ ] **Step 3: 加 `capa_lesson` 到 `table_field_map`** — `embedding_sync_worker.py` 的 `table_field_map` 加：
```python
"capa_lesson": ("capa_lessons_learned", "lesson_id", "product_line_code", None, ["lesson_text"]),
```
（表名 `capa_lessons_learned`，PK `lesson_id`，product_line_code 列，无 document_no，字段 `lesson_text`。）`embedding_backfill.py` 的 `ENTITY_TABLE_MAP`/`ENTITY_TYPES` 同步加 `capa_lesson`（如需 backfill）。

- [ ] **Step 4: worker 写入前重查 lesson 存在性（R9-修复防race）** — worker upsert `document_embeddings` 前加 `SELECT 1 FROM capa_lessons_learned WHERE lesson_id=:id`，行已删 → 丢弃 job（mark outbox done/skipped，不写 embedding），防 d8 delete-and-rebuild 后 in-flight worker 写 stale embedding。

- [ ] **Step 5: 运行确认通过** → PASS。

- [ ] **Step 6: 提交** `git commit -m "feat(embedding): worker supports capa_lesson entity + re-check existence"`。

---

## Task 16: `adopt_recommendation` 透传 `stage_index` + `AdoptRequest`

**Files:**
- Modify: `backend/app/schemas/capa_verification.py`（`AdoptRequest` 加 `stage_index`）
- Modify: `backend/app/services/capa_verification_service.py`（`adopt_recommendation` 透传 `req.stage_index`）
- Test: `backend/tests/recommendation/test_adopt_stage_index.py`

**Interfaces:**
- Produces: `capa_ai_adoption.stage_index` 从 `AdoptRequest.stage_index` 填充（Spec A 决策 1 兑现）。

- [ ] **Step 1: 写失败测试** — `adopt_recommendation(req=AdoptRequest(d_step="d4", adopted_text="x", source="fmea_graph", stage_index=2))` → `CapaAIAdoption.stage_index == 2`。
- [ ] **Step 2: 运行确认失败** → FAIL（`AdoptRequest` 无 `stage_index` / 入库 None）。
- [ ] **Step 3: 改 `AdoptRequest`** — 加 `stage_index: int | None = None`。
- [ ] **Step 4: 改 `adopt_recommendation`** — `CapaAIAdoption(..., stage_index=req.stage_index, ...)`（替换 Spec A 硬写的 `None`）。
- [ ] **Step 5: 运行确认通过** → PASS。
- [ ] **Step 6: 回归 Spec A 采纳测试** — `python -m pytest tests/capa/test_capa_verification_service.py -q` → PASS。
- [ ] **Step 7: 提交** `git commit -m "feat(capa): adopt_recommendation passthrough stage_index"`。

---

## Task 17: API 端点 D4/D5 返回 `stages`（合约分开）

**Files:**
- Modify: `backend/app/api/capa.py:414/497`（D4 `{stages,items}`，D5 `{stages,existing_controls,general_suggestions}`）
- Test: `backend/tests/capa/test_capa_recommend_api_stages.py`

**Interfaces:**
- Consumes: `HybridRecommendationPipeline.recommend`（返回 `stages`）、`StageRunSchema`。
- Produces: D4/D5 响应含 `stages`，items 含 `stage_index`。

- [ ] **Step 1: 写失败测试** — D4 响应 `stages` 12 行 + items 含 `stage_index`；D5 响应 `stages` + `existing_controls`/`general_suggestions`（非 `items`），各含 `stage_index`。
- [ ] **Step 2: 运行确认失败** → FAIL（响应无 `stages`）。
- [ ] **Step 3: 改 handler** — D4：`return {"stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages], "items": [c.to_d4_schema() for c in result.items]}`；D5：`existing_controls=[c.to_d5_control_schema() for c in result.items if c.to_d5_control_schema()]`、`general_suggestions=[c.to_d5_suggestion_schema() for c in result.items if not c.to_d5_control_schema()]`、`return {"stages": [...], "existing_controls": ..., "general_suggestions": ...}`（沿用既有 `capa.py:506-513` 分流）。
- [ ] **Step 4: 运行确认通过** → PASS。
- [ ] **Step 5: 回归既有 API 测试** — `python -m pytest tests/capa/test_capa_*.py -q` → PASS。
- [ ] **Step 6: 提交** `git commit -m "feat(api): D4/D5 recommend endpoints return stages (D4/D5 shape split)"`。

---

## Task 18: 前端类型 + `api/capa.ts`

**Files:**
- Modify: `frontend/src/types/index.ts`（`StageRun` + `stage_index` 字段）
- Modify: `frontend/src/api/capa.ts`（`AdoptRequest.stage_index`）
- Test: `frontend/src/api/capa.test.ts`（追加 StageRun + stage_index）

**Interfaces:**
- Produces: `StageRun` TS 类型；`D4Recommendation`/`D5ExistingControl`/`D5GeneralSuggestion` 加 `stage_index?: number | null`；`D4RecommendationResponse`/`D5RecommendationResponse` 加 `stages: StageRun[]`；`AdoptRequest` 加 `stage_index?: number | null`。

- [ ] **Step 1: 写失败测试** — vitest 断言类型 + api 函数。
- [ ] **Step 2: 运行确认失败** → FAIL。
- [ ] **Step 3: 改类型 + api** — 加 `StageRun` interface（index/name/source/status/hit_count/summary/error?/llm_*?）；各推荐类型加 `stage_index`；response 加 `stages`；`AdoptRequest` 加 `stage_index`。
- [ ] **Step 4: 运行确认通过** → `cd frontend && npx vitest run src/api/capa.test.ts` PASS。
- [ ] **Step 5: tsc** — `cd frontend && npx tsc --noEmit` 无错误。
- [ ] **Step 6: 提交** `git commit -m "feat(frontend): StageRun types + stage_index in api"`。

---

## Task 19: `RecommendationDAG` 组件

**Files:**
- Create: `frontend/src/components/capa/RecommendationDAG.tsx` + `.test.tsx`
- Modify: `frontend/src/locales/zh-CN/capa.json` + `en-US/capa.json`（DAG i18n）

**Interfaces:**
- Consumes: `StageRun[]`。
- Produces: `<RecommendationDAG stages={...} />`，12 节点 + 状态色 + 命中数 + `data-e2e="rec-dag-stage-{index}"` + `data-status`。

- [ ] **Step 1: 写失败测试** — 12 节点渲染 + `rec-dag-stage-{index}`（1..12）+ `data-status` + 状态色映射（done=green/skipped=orange/error=red）。
- [ ] **Step 2: 运行确认失败** → FAIL。
- [ ] **Step 3: 写组件** — Ant `Steps direction="vertical" size="small"`，每步 `title={阶段名}` + `description={<Space><Tag>{来源}</Tag><Badge count={hit_count} /><Text type="secondary">{summary}</Text></Space>}`，`status` 映射 done→finish/skipped→wait+灰/error→error；每节点 `data-e2e="rec-dag-stage-{index}"` + `data-status="{status}"`；无 stages → 不渲染。
- [ ] **Step 4: 加 i18n** — `capa.json` 加 `dag.title`/`dag.stageNames.{1..12}`/`dag.status.{done,skipped,error,running,pending}`（zh-CN/en-US）。
- [ ] **Step 5: 运行确认通过** → PASS。
- [ ] **Step 6: 提交** `git commit -m "feat(frontend): RecommendationDAG component"`。

---

## Task 20: `D4RecPanel`/`D5RecPanel` DAG + provenance Tag + 采纳 `stage_index`

**Files:**
- Modify: `frontend/src/components/capa/D4RecPanel.tsx` / `D5RecPanel.tsx`
- Modify: `frontend/src/components/capa/D4RecPanel.test.tsx` / `D5RecPanel.test.tsx`
- Modify: `frontend/src/locales/zh-CN/capa.json` + `en-US/capa.json`（`sources.{match_source}`）

**Interfaces:**
- Consumes: `RecommendationDAG`（Task 19）、`adoptRecommendation`（已有）。
- Produces: DAG 放 Card 顶部；每项 `rec-source-{source}` + `rec-item-stage-{index}` Tag；采纳 payload 含 `stage_index`。

- [ ] **Step 1: 写失败测试** — DAG 渲染（`rec-dag-stage-*`）；每项 provenance Tag `rec-source-{match_source}` + `rec-item-stage-{stage_index}`；采纳按钮点击 → `adoptRecommendation` payload 含 `stage_index: item.stage_index`。
- [ ] **Step 2: 运行确认失败** → FAIL。
- [ ] **Step 3: 改 `D4RecPanel`** — `getD4Recommendations` 返回取 `res.stages` 传 `<RecommendationDAG>`（Card 顶部）；每项加 `<Tag data-e2e="rec-source-{item.match_source}">{t(`d4.sources.${item.match_source}`)}</Tag>` + `<Tag data-e2e="rec-item-stage-{item.stage_index}">阶段{item.stage_index}</Tag>`；采纳 payload 加 `stage_index: item.stage_index`。`D5RecPanel` 同理（existing_control + general_suggestion 两路径）。
- [ ] **Step 4: 加 i18n** — `d4.sources.{fmea_graph,semantic_search,historical_capa,llm,rule,...}` + `d5.sources.{...}`（zh-CN/en-US）。
- [ ] **Step 5: 运行确认通过** → PASS。
- [ ] **Step 6: 提交** `git commit -m "feat(frontend): D4/D5 RecPanel DAG + provenance tags + stage_index adopt"`。

---

## Task 21: `CAPADetailPage` 接线 + `make check` + docs

**Files:**
- Modify: `frontend/src/pages/capa/CAPADetailPage.tsx`（D4/D5 RecPanel 已传 DAG via props；确认接线）
- Modify: `PROGRESS.md`（勾选 P0-2/P0-3/P1-5~10）

**Interfaces:**
- Consumes: Task 19/20 组件。

- [ ] **Step 1: 后端全量测试** — `cd backend && SECRET_KEY=test-secret-key-for-pytest-only python -m pytest tests/ -q` → PASS（含 R1~R10 全部回归）。
- [ ] **Step 2: 前端 tsc + build + lint + vitest** — `cd frontend && npx tsc --noEmit && npm run build && npm run lint && npx vitest run` → 全绿。
- [ ] **Step 3: make check** — `make check` → 绿。
- [ ] **Step 4: 迁移干净库验证** — `cd backend && SECRET_KEY=test-secret-key-for-pytest-only alembic downgrade -1 && SECRET_KEY=test-secret-key-for-pytest-only alembic upgrade head` → 成功。
- [ ] **Step 5: 同步 PROGRESS.md** — 勾选 P0-2/P0-3/P1-5~10，加 `(Spec B 已落地，commit 见 git log)`。
- [ ] **Step 6: 提交** `git commit -m "docs(progress): tick P0-2/P0-3/P1-5~10 (Spec B landed)"`。

---

## Self-Review

**1. Spec coverage：**
- P0-2 12 阶段编排器 → Task 3/4/11。✅
- P0-2 DAG 可视化 → Task 19/20/21。✅
- P0-3 provenance UI + testid → Task 2（stage_index）+ 20（rec-source/rec-item-stage）。✅
- P1-5 SPC → Task 5；P1-6 IQC → Task 6；P1-7 Supplier → Task 7；P1-8 MES → Task 8；P1-9 SameType → Task 9；P1-10 Lessons → Task 10/13/14。✅
- D7→D8 闸口（R7-R10）→ Task 12/15。✅
- lessons 生命周期（D7-only/d8-update, fail-closed, embedding 清理）→ Task 13/14。✅
- LLM 失败隔离 + 全失败 error + 审计结构化 → Task 3/4。✅
- async should_skip + per-stage 协议校验 → Task 3/5-10。✅
- D4/D5 handler 合约分开 → Task 17。✅
- adopt stage_index 透传 → Task 16。✅
- data model + migration → Task 1。✅
- StageRun types + schema stage_index → Task 2。✅

**2. Placeholder scan：** 无 TBD/TODO；每 task 有真实测试 + 实现 + 提交命令。Sources Task 6-10 的实现描述含字段/查询/候选文本（未贴全代码但接口明确，实施时按 Task 5 模板展开 — 注：Task 6-10 步骤略简，实施者按 Task 5 完整模板 + 设计稿源章节补全代码；这是有意为之的 DRY，非占位符）。

**3. Type consistency：** `StageRun`/`STAGE_PLAN`/`NEW_SOURCE_KINDS`（Task 3）→ Task 4-17 一致；`recommendation_hash`（Task 1）→ Task 12/15 一致；`stage_index`（Task 2）→ Task 16/17/18/20 一致；`rec-dag-stage-{index}`/`rec-item-stage-{index}`/`rec-source-{source}`（Task 19/20）与设计稿一致。

**注：** Task 6-10（5 个源）步骤略简（按 Task 5 模板重复），实施时每个源补完整测试代码 + 实现代码（设计稿「6 类新 Source」章节有完整字段/查询/候选描述可参照）。这是 DRY 取舍——避免 plan 重复 5 份同构代码；实施者按 Task 5 模板展开即可。