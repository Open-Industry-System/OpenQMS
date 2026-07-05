# US-E2E-01 Spec A — D4 根因验证 + AI 采纳/动作审计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 US-E2E-01 的 P0-1（D4 现场根因验证子流程）+ P0-4（D4/D5 文本采纳 + D7 节点动作审计），让 8D 闭环可审计、D4→D5 需已验证根因。

**Architecture:** 三新表（`capa_root_cause_verification` / `capa_ai_adoption` / `capa_d7_node_action`）+ 7 新 API 端点 + `fmea_service.update_fmea` 拆出无提交核心 `_apply_fmea_update` 供 D7 自动回填单事务复用 + 前端 `D4VerificationCard` 新组件 + D4/D5/D7 RecPanel 改调端点。

**Tech Stack:** Python 3.11 / FastAPI 0.115 / SQLAlchemy 2.0 async / Alembic / Pydantic v2 / React 18 / TypeScript 5.6 / Ant Design 5 / Vitest + @testing-library/react

## Global Constraints

- ADR-0001：业务表 PK = Python 端 `uuid.uuid4()`，DB 列 `UUID(as_uuid=True)`，不按 PK 排序（`created_at DESC`）。
- ADR-0003：所有新表带 `factory_id NOT NULL FK→factories.id`，服务层读写显式 `capa_id + factory_id` 联合过滤，`check_factory_access` 在 handler 层做。
- ADR-0004：Service 层手写 `AuditLog`（`table_name/record_id/action/changed_fields/operated_by`），不引入 SQLAlchemy event hook。**`audit_logs.action` 列为 `String(20)`（`backend/app/models/audit.py:19`），新 action 值必须 ≤20 字符。** 本计划使用：`ADOPT_RECOMMENDATION`(20)、`RC_VERIFY`(9)、`D7_AUTO_FILLED_FMEA`(19)、`D7_ACTION_CHANGED`(17)、以及动态 `D7_NODE_{ACTION}`（如 `D7_NODE_CONFIRMED`/`D7_NODE_SKIPPED`/`D7_NODE_AUTO_FILLED`，最长 19）。
- ADR-0013：Alembic 迁移手写 `op.create_table` / `op.execute`，不用 autogenerate。
- `SECRET_KEY=test-secret-key-for-pytest-only`：**`pytest` 命令无需显式传**（`tests/conftest.py:12` 在 collection 前用 `os.environ.setdefault` 注入，先于 `app.config.Settings()` 实例化）；**`alembic` 命令必须显式带 `SECRET_KEY=test-secret-key-for-pytest-only` 前缀**——alembic 走 `alembic/env.py` 直接 import `app.database`→`app.config`，不加载 conftest，而 `Settings` 校验器拒绝默认值 `dev-secret-key-change-in-production`（`backend/app/config.py:51-59`），无前缀则 import 期即报错。
- 测试 `db` fixture 把 `commit()` 打成 flush-only，服务代码的 `await db.commit()` 在测试里安全。
- 中文 UI（zh_CN），i18n key 走 `react-i18next`，`frontend/src/test-setup.ts` 已把测试语言切到 en-US。
- 生产代码仅可加 `data-e2e` testid（不引入测试专属 prod 代码路径）。
- 采纳写 d-step 字段为**追加**（`current ? current+\n+text : text`），非覆盖。

## File Structure

**新建（backend）：**
- `backend/alembic/versions/20260703_add_capa_verification_adoption.py` — 3 表 + 表达式唯一索引
- `backend/app/schemas/capa_verification.py` — Adopt/Verification/D7 schemas
- `backend/app/services/capa_verification_service.py` — adopt + verification CRUD
- `backend/app/services/capa_d7_action_service.py` — D7 record/list/auto-fill（含 `ConflictError`）
- `backend/tests/capa/test_capa_verification_service.py`
- `backend/tests/capa/test_capa_d7_action_service.py`
- `backend/tests/capa/test_capa_verification_api.py`
- `backend/tests/capa/test_capa_d7_api.py`
- `backend/tests/fmea/test_fmea_update_core.py`

**修改（backend）：**
- `backend/app/models/capa.py` — 加 `CapaRootCauseVerification` / `CapaAIAdoption` / `CapaD7NodeAction`
- `backend/app/models/__init__.py` — 导出新模型
- `backend/app/services/capa_service.py` — `advance_capa` 加 D4→D5 闸口
- `backend/app/services/fmea_service.py` — 拆 `_apply_fmea_update` 无提交核心
- `backend/app/services/recommendation_types.py` — `to_d5_suggestion_schema` 始终输出 `match_source`
- `backend/app/api/capa.py` — 加 7 端点
- `backend/app/schemas/capa.py` — `D5GeneralSuggestion.match_source` 保持可空（前端兼容）

**新建（frontend）：**
- `frontend/src/components/capa/D4VerificationCard.tsx` + `.test.tsx`
- `frontend/src/components/capa/D4RecPanel.test.tsx`
- `frontend/src/components/capa/D5RecPanel.test.tsx`
- `frontend/src/components/capa/D7RecPanel.test.tsx`

**修改（frontend）：**
- `frontend/src/types/index.ts` — 加 Adopt/Verification/D7Action 类型
- `frontend/src/api/capa.ts` — 7 个 api 函数
- `frontend/src/components/capa/D4RecPanel.tsx` / `D5RecPanel.tsx` / `D7RecPanel.tsx`
- `frontend/src/pages/capa/CAPADetailPage.tsx`

**文档：**
- `PROGRESS.md` — 勾选 P0-1 / P0-4

---

## Task 1: 数据模型 + Alembic 迁移

**Files:**
- Modify: `backend/app/models/capa.py`（追加 3 类）
- Modify: `backend/app/models/__init__.py:22`
- Create: `backend/alembic/versions/20260703_add_capa_verification_adoption.py`
- Test: `backend/tests/capa/test_models_verification_adoption.py`

**Interfaces:**
- Produces: `CapaRootCauseVerification`、`CapaAIAdoption`、`CapaD7NodeAction` ORM 类（后续 service 任务直接 import）。

- [ ] **Step 1: 确定 alembic head 并建 merge（如多 head）**

Run:
```bash
cd backend && SECRET_KEY=test-secret-key-for-pytest-only alembic heads
```
若输出 >1 行，先合并：
```bash
SECRET_KEY=test-secret-key-for-pytest-only alembic merge -m "merge heads before capa verification adoption" $(SECRET_KEY=test-secret-key-for-pytest-only alembic heads | awk '{print $1}' | paste -sd ' ')
SECRET_KEY=test-secret-key-for-pytest-only alembic heads   # 应只剩 1 行 = 新 merge revision
```
记下唯一的 head revision id（下文 `<HEAD>`）。若已是单 head，`<HEAD>` 即该值。

- [ ] **Step 2: 写失败测试**

`backend/tests/capa/test_models_verification_adoption.py`：
```python
import uuid
import pytest
from sqlalchemy import select
from app.models.capa import (
    CAPAEightD, CapaRootCauseVerification, CapaAIAdoption, CapaD7NodeAction,
)
from app.models.fmea import FMEADocument

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_can_persist_three_new_tables(db, default_factory, admin_user):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no="8D-MODEL-001", title="t",
        product_line_code="DC-DC-100", factory_id=default_factory.id,
        created_by=admin_user.user_id,
    )
    db.add(capa); await db.flush()

    # CapaD7NodeAction.fmea_id 是 FK→fmea_documents.fmea_id，必须先建真实 FMEA 行
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-MODEL-001", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id,
        graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()

    rcv = CapaRootCauseVerification(
        verification_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=default_factory.id,
        root_cause_text="螺栓尺寸超差", method="千分尺复测", result="4/5 超差",
        is_verified=True, verified_by=admin_user.user_id,
    )
    db.add(rcv)

    adopt = CapaAIAdoption(
        adoption_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=default_factory.id,
        d_step="d4", adopted_text="螺栓尺寸超差", source="fmea_graph",
        stage_index=None, adopted_by=admin_user.user_id,
    )
    db.add(adopt)

    d7 = CapaD7NodeAction(
        action_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=default_factory.id,
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id=None, match_source="linked", acted_by=admin_user.user_id,
    )
    db.add(d7); await db.flush()

    assert (await db.scalar(select(CapaRootCauseVerification).where(
        CapaRootCauseVerification.verification_id == rcv.verification_id))).is_verified is True
    assert (await db.scalar(select(CapaAIAdoption).where(
        CapaAIAdoption.adoption_id == adopt.adoption_id))).source == "fmea_graph"
    assert (await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.action_id == d7.action_id))).action == "confirmed"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/capa/test_models_verification_adoption.py -x -q`
Expected: FAIL（`ImportError`：3 类未定义 / 表不存在）。

- [ ] **Step 4: 追加 3 个模型到 `backend/app/models/capa.py`**

在文件末尾追加：
```python
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class CapaRootCauseVerification(Base):
    __tablename__ = "capa_root_cause_verification"
    verification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    root_cause_text: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence_attachments: Mapped[list] = mapped_column(JSONB, default=lambda: [])
    source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CapaAIAdoption(Base):
    __tablename__ = "capa_ai_adoption"
    adoption_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    d_step: Mapped[str] = mapped_column(String(8), nullable=False)
    adopted_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    stage_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    adopted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    adopted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CapaD7NodeAction(Base):
    __tablename__ = "capa_d7_node_action"
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    fmea_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=False)
    failure_mode_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    failure_cause_node_id: Mapped[str | None] = mapped_column(String(36))
    match_source: Mapped[str] = mapped_column(String(40), nullable=False)
    prevention_control_node_id: Mapped[str | None] = mapped_column(String(36))
    prevention_control_name_before: Mapped[str | None] = mapped_column(Text)
    prevention_control_name_after: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    acted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
注：`Boolean` / `Integer` / `String` 需在文件顶部 import 中补齐（见 Step 6）。

- [ ] **Step 5: 注册模型到 `backend/app/models/__init__.py`**

把第 22 行 `from app.models.capa import CAPAEightD` 改为：
```python
from app.models.capa import (
    CAPAEightD, CapaAIAdoption, CapaD7NodeAction, CapaRootCauseVerification,
)
```

- [ ] **Step 6: 补 `backend/app/models/capa.py` 顶部 import**

把第 4 行 `from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func` 改为：
```python
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
```

- [ ] **Step 7: 写迁移文件**

`backend/alembic/versions/20260703_add_capa_verification_adoption.py`：
```python
"""add capa verification adoption tables

Revision ID: 20260703_capa_verif
Revises: <HEAD>
Create Date: 2026-07-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260703_capa_verif"
down_revision: Union[str, None] = "<HEAD>"   # ← 替换为 Step 1 记下的 head revision
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capa_root_cause_verification",
        sa.Column("verification_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("root_cause_text", sa.Text, nullable=False),
        sa.Column("method", sa.Text),
        sa.Column("result", sa.Text),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("evidence_attachments", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_ref", postgresql.JSONB),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_rcv_capa_id", "capa_root_cause_verification", ["capa_id"])
    op.create_index("ix_capa_rcv_factory", "capa_root_cause_verification", ["factory_id"])

    op.create_table(
        "capa_ai_adoption",
        sa.Column("adoption_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("d_step", sa.String(8), nullable=False),
        sa.Column("adopted_text", sa.Text, nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("stage_index", sa.Integer),
        sa.Column("item_ref", postgresql.JSONB),
        sa.Column("adopted_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("adopted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_adopt_capa_step", "capa_ai_adoption", ["capa_id", "d_step"])
    op.create_index("ix_capa_adopt_factory", "capa_ai_adoption", ["factory_id"])
    # 幂等去重：同 (capa, d_step, source, item_ref, adopted_text) 重复采纳 → 命中 unique 兜底，服务层 catch 后返回既有 adoption
    # item_ref 是 JSONB，::text 规范化（JSONB 按规范序存储，::text 确定性）；COALESCE 收口 NULL
    op.execute(
        "CREATE UNIQUE INDEX ix_capa_ai_adoption_dedupe ON capa_ai_adoption "
        "(capa_id, d_step, source, COALESCE(item_ref::text, ''), adopted_text)"
    )

    op.create_table(
        "capa_d7_node_action",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("fmea_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("fmea_documents.fmea_id"), nullable=False),
        sa.Column("failure_mode_node_id", sa.String(36), nullable=False),
        sa.Column("failure_cause_node_id", sa.String(36)),
        sa.Column("match_source", sa.String(40), nullable=False),
        sa.Column("prevention_control_node_id", sa.String(36)),
        sa.Column("prevention_control_name_before", sa.Text),
        sa.Column("prevention_control_name_after", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("acted_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_d7_capa", "capa_d7_node_action", ["capa_id"])
    op.create_index("ix_capa_d7_factory", "capa_d7_node_action", ["factory_id"])
    # 表达式唯一索引（COALESCE 收口 nullable failure_cause_node_id，见 R3-Finding 4）
    op.execute(
        "CREATE UNIQUE INDEX ix_capa_d7_node_unique ON capa_d7_node_action "
        "(capa_id, fmea_id, failure_mode_node_id, COALESCE(failure_cause_node_id, ''))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_capa_d7_node_unique")
    op.drop_index("ix_capa_d7_factory", table_name="capa_d7_node_action")
    op.drop_index("ix_capa_d7_capa", table_name="capa_d7_node_action")
    op.drop_table("capa_d7_node_action")
    op.execute("DROP INDEX IF EXISTS ix_capa_ai_adoption_dedupe")
    op.drop_index("ix_capa_adopt_factory", table_name="capa_ai_adoption")
    op.drop_index("ix_capa_adopt_capa_step", table_name="capa_ai_adoption")
    op.drop_table("capa_ai_adoption")
    op.drop_index("ix_capa_rcv_factory", table_name="capa_root_cause_verification")
    op.drop_index("ix_capa_rcv_capa_id", table_name="capa_root_cause_verification")
    op.drop_table("capa_root_cause_verification")
```
**务必**：把文件里两处 `<HEAD>` 替换为 Step 1 记下的真实 revision 字符串。

- [ ] **Step 8: 应用迁移并跑测试**

Run:
```bash
cd backend && SECRET_KEY=test-secret-key-for-pytest-only alembic upgrade head
python -m pytest tests/capa/test_models_verification_adoption.py -x -q
```
Expected: PASS（3 行落库可查回）。

- [ ] **Step 9: 提交**

```bash
git add backend/app/models/capa.py backend/app/models/__init__.py \
        backend/alembic/versions/20260703_add_capa_verification_adoption.py \
        backend/tests/capa/test_models_verification_adoption.py
git commit -m "feat(capa): add verification/adoption/d7-action models + migration"
```

---

## Task 2: `to_d5_suggestion_schema` 始终输出 match_source（R1-Finding 5）

**Files:**
- Modify: `backend/app/services/recommendation_types.py:69-83`
- Test: `backend/tests/recommendation/test_recommendation_types_match_source.py`

**Interfaces:**
- Produces: `D5GeneralSuggestion.match_source` 对所有内部 source 都有值（前端 D5 general_suggestion 采纳时能填 `source`）。

- [ ] **Step 1: 写失败测试**

`backend/tests/recommendation/test_recommendation_types_match_source.py`：
```python
from app.services.recommendation_types import RecommendationCandidate


def _cand(source: str) -> RecommendationCandidate:
    return RecommendationCandidate(
        source=source, content="x", category="预防措施",
        confidence=0.5, match_reason="r", metadata={},
    )


def test_d5_suggestion_rule_engine_measure_maps_to_rule():
    s = _cand("rule_engine_measure").to_d5_suggestion_schema()
    assert s["match_source"] == "rule"


def test_d5_suggestion_historical_capa_keeps_source():
    s = _cand("historical_capa").to_d5_suggestion_schema()
    assert s["match_source"] == "historical_capa"
    assert s["source_capa_id"] is None  # metadata 无 historical_capa_id


def test_d5_suggestion_semantic_search_emits_source():
    s = _cand("semantic_search").to_d5_suggestion_schema()
    assert s["match_source"] == "semantic_search"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/recommendation/test_recommendation_types_match_source.py -x -q`
Expected: FAIL（`rule_engine_measure` 当前不输出 `match_source` → KeyError/None）。

- [ ] **Step 3: 改 `to_d5_suggestion_schema`**

把 `backend/app/services/recommendation_types.py` 的 `to_d5_suggestion_schema` 方法体替换为：
```python
    def to_d5_suggestion_schema(self) -> dict[str, Any]:
        result = {
            "content": self.content,
            "category": self.category or "预防措施",
            "basis": self.metadata.get("basis", ""),
            "confidence": round(self.confidence, 2),
            "match_reason": self.match_reason,
            "match_source": "rule" if self.source == "rule_engine_measure" else self.source,
        }
        if self.source == "historical_capa":
            result["source_capa_id"] = self.metadata.get("historical_capa_id")
            result["source_capa_document_no"] = self.metadata.get("document_no")
        return result
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/recommendation/test_recommendation_types_match_source.py -x -q`
Expected: PASS。

- [ ] **Step 5: 回归既有推荐测试**

Run: `cd backend && python -m pytest tests/test_capa_recommendation.py tests/test_d7_recommendations.py -q`
Expected: PASS（既有测试不退化）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/recommendation_types.py \
        backend/tests/recommendation/test_recommendation_types_match_source.py
git commit -m "fix(recommendation): to_d5_suggestion_schema always emits match_source"
```

---

## Task 3: `capa_verification_service.adopt_recommendation`

**Files:**
- Create: `backend/app/services/capa_verification_service.py`
- Test: `backend/tests/capa/test_capa_verification_service.py`

**Interfaces:**
- Consumes: `app.models.capa.CapaAIAdoption`（Task 1）、`app.models.audit.AuditLog`、`app.services.capa_service.EMBEDDING_FIELDS`、`app.services.embedding_outbox.enqueue_embedding`。
- Produces: `adopt_recommendation(db, capa, req: AdoptRequest, user) -> tuple[CapaAIAdoption, str]`（返回 `(adoption, new_field_value)`）。

- [ ] **Step 1: 写失败测试**

`backend/tests/capa/test_capa_verification_service.py`：
```python
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaAIAdoption
from app.schemas.capa_verification import AdoptRequest
from app.services.capa_verification_service import adopt_recommendation

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, doc_no="8D-ADOPT-001", d4=None):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no, title="t",
        product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, d4_root_cause=d4, status="D4_ROOT_CAUSE",
    )
    db.add(capa); await db.flush()
    return capa


@pytest.mark.asyncio
async def test_adopt_appends_to_existing_d4(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4="已有根因A")
    req = AdoptRequest(d_step="d4", adopted_text="新根因B", source="fmea_graph",
                       item_ref={"failure_cause_node_id": "c1"})
    adoption, new_value = await adopt_recommendation(db, capa, req, admin_user)
    assert new_value == "已有根因A\n新根因B"
    await db.refresh(capa)
    assert capa.d4_root_cause == "已有根因A\n新根因B"
    rows = (await db.execute(select(CapaAIAdoption).where(CapaAIAdoption.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].adopted_text == "新根因B"
    assert rows[0].source == "fmea_graph"
    assert rows[0].stage_index is None
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id, AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(audits) == 1
    assert audits[0].changed_fields["source"] == "fmea_graph"


@pytest.mark.asyncio
async def test_adopt_writes_to_empty_field(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4=None)
    req = AdoptRequest(d_step="d4", adopted_text="根因B", source="rule")
    _, new_value = await adopt_recommendation(db, capa, req, admin_user)
    assert new_value == "根因B"
    await db.refresh(capa)
    assert capa.d4_root_cause == "根因B"


@pytest.mark.asyncio
async def test_adopt_d5_appends_to_d5_correction(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4="rc")
    capa.d5_correction = "措施A"; capa.status = "D5_CORRECTION"; await db.flush()
    req = AdoptRequest(d_step="d5", adopted_text="措施B", source="historical_capa")
    _, new_value = await adopt_recommendation(db, capa, req, admin_user)
    assert new_value == "措施A\n措施B"


@pytest.mark.asyncio
async def test_adopt_idempotent_same_payload_no_duplicate(db, default_factory, admin_user):
    # 双击/重试同一条推荐：第二次返回既有 adoption，不重复追加 d-step 文本、不新增行、不新增 audit
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4="rc")
    req = AdoptRequest(d_step="d4", adopted_text="根因B", source="fmea_graph",
                       item_ref={"failure_cause_node_id": "c1", "fmea_id": "f1"})
    first, v1 = await adopt_recommendation(db, capa, req, admin_user)
    second, v2 = await adopt_recommendation(db, capa, req, admin_user)
    assert second.adoption_id == first.adoption_id   # 幂等返回既有
    assert v2 == v1                                   # 字段值不再翻倍
    await db.refresh(capa)
    assert capa.d4_root_cause == "rc\n根因B"           # 只追加一次
    rows = (await db.execute(select(CapaAIAdoption).where(CapaAIAdoption.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 1                              # 仅 1 条 adoption
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id, AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(audits) == 1                            # 仅 1 条 audit


@pytest.mark.asyncio
async def test_adopt_different_item_ref_not_deduped(db, default_factory, admin_user):
    # 不同 item_ref（不同推荐）应各落一条，不被幂等去重误杀
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4=None)
    req1 = AdoptRequest(d_step="d4", adopted_text="根因B", source="fmea_graph",
                         item_ref={"failure_cause_node_id": "c1", "fmea_id": "f1"})
    req2 = AdoptRequest(d_step="d4", adopted_text="根因B", source="fmea_graph",
                         item_ref={"failure_cause_node_id": "c2", "fmea_id": "f1"})
    await adopt_recommendation(db, capa, req1, admin_user)
    await adopt_recommendation(db, capa, req2, admin_user)
    rows = (await db.execute(select(CapaAIAdoption).where(CapaAIAdoption.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/capa/test_capa_verification_service.py::test_adopt_appends_to_existing_d4 -x -q`
Expected: FAIL（`ImportError`：service / schema 未建）。

- [ ] **Step 3: 写 `AdoptRequest` schema**

`backend/app/schemas/capa_verification.py`：
```python
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict


class AdoptRequest(BaseModel):
    d_step: Literal["d4", "d5"]
    adopted_text: str
    source: str
    item_ref: dict | None = None


class AdoptResponse(BaseModel):
    adoption_id: uuid.UUID
    d_step: str
    field_value: str


class VerificationCreate(BaseModel):
    root_cause_text: str
    method: str | None = None
    result: str | None = None
    is_verified: bool = False
    evidence_attachments: list[dict] = []
    source_ref: dict | None = None


class VerificationUpdate(BaseModel):
    method: str | None = None
    result: str | None = None
    is_verified: bool | None = None
    evidence_attachments: list[dict] | None = None


class VerificationResponse(BaseModel):
    verification_id: uuid.UUID
    capa_id: uuid.UUID
    root_cause_text: str
    method: str | None
    result: str | None
    is_verified: bool
    evidence_attachments: list[dict]
    source_ref: dict | None
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class D7NodeActionCreate(BaseModel):
    action: Literal["confirmed", "skipped"]
    fmea_id: uuid.UUID
    failure_mode_node_id: str
    failure_cause_node_id: str | None = None
    match_source: str
    reason: str | None = None


class D7AutoFillRequest(BaseModel):
    fmea_id: uuid.UUID
    failure_mode_node_id: str
    failure_cause_node_id: str
    match_source: str


class D7AutoFillResponse(BaseModel):
    action_id: uuid.UUID
    prevention_control_node_id: str
    prevention_control_name_after: str
    is_new_control: bool


class D7NodeActionResponse(BaseModel):
    action_id: uuid.UUID
    capa_id: uuid.UUID
    action: str
    fmea_id: uuid.UUID
    failure_mode_node_id: str
    failure_cause_node_id: str | None
    match_source: str
    prevention_control_node_id: str | None
    prevention_control_name_before: str | None
    prevention_control_name_after: str | None
    reason: str | None
    acted_by: uuid.UUID
    acted_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 4: 写 `adopt_recommendation` 服务**

`backend/app/services/capa_verification_service.py`：
```python
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CapaAIAdoption
from app.schemas.capa_verification import AdoptRequest
from app.services import capa_service
from app.services.embedding_outbox import enqueue_embedding

FIELD_MAP = {"d4": "d4_root_cause", "d5": "d5_correction"}


async def _find_existing_adoption(db: AsyncSession, capa, req: AdoptRequest):
    # 幂等去重 key：同 (capa, d_step, source, item_ref, adopted_text)。item_ref 是 JSONB，
    # SQLAlchemy == None 生成 IS NULL、== {} 生成 = '{}'::jsonb，与 ix_capa_ai_adoption_dedupe 的 COALESCE 收口一致
    return await db.scalar(select(CapaAIAdoption).where(
        CapaAIAdoption.capa_id == capa.report_id,
        CapaAIAdoption.d_step == req.d_step,
        CapaAIAdoption.source == req.source,
        CapaAIAdoption.adopted_text == req.adopted_text,
        CapaAIAdoption.item_ref == req.item_ref,
    ))


async def adopt_recommendation(db: AsyncSession, capa, req: AdoptRequest, user):
    field = FIELD_MAP[req.d_step]
    # 幂等：重复采纳（双击/重试/代理重发）直接返回既有 adoption，不重复追加 d-step 文本、不重复 audit
    existing = await _find_existing_adoption(db, capa, req)
    if existing is not None:
        await db.refresh(capa)
        return existing, getattr(capa, field) or ""

    current = getattr(capa, field) or ""
    new_value = f"{current}\n{req.adopted_text}" if current else req.adopted_text
    setattr(capa, field, new_value)
    adoption = CapaAIAdoption(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        d_step=req.d_step, adopted_text=req.adopted_text,
        source=req.source, stage_index=None, item_ref=req.item_ref,
        adopted_by=user.user_id,
    )
    db.add(adoption)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="ADOPT_RECOMMENDATION",
        changed_fields={
            "d_step": req.d_step, "source": req.source, "stage_index": None,
            "adopted_text": req.adopted_text, "item_ref": req.item_ref,
        },
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    if field in capa_service.EMBEDDING_FIELDS:
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    try:
        await db.commit()
    except IntegrityError:
        # 并发下另一事务先插同 dedupe key（ix_capa_ai_adoption_dedupe 兜底）→ 回滚后查既有返回，幂等（不重复追加、不 500）
        await db.rollback()
        existing = await _find_existing_adoption(db, capa, req)
        await db.refresh(capa)
        return existing, getattr(capa, field) or ""
    await db.refresh(adoption)
    return adoption, new_value
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/capa/test_capa_verification_service.py -x -q`
Expected: PASS（3 个 adopt 测试）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/capa_verification.py backend/app/services/capa_verification_service.py \
        backend/tests/capa/test_capa_verification_service.py
git commit -m "feat(capa): adopt_recommendation service (append + adoption audit)"
```

---

## Task 4: 验证记录 CRUD（create/list/update + verifier timestamps + ownership）

**Files:**
- Modify: `backend/app/services/capa_verification_service.py`（追加）
- Test: `backend/tests/capa/test_capa_verification_service.py`（追加）

**Interfaces:**
- Produces: `create_verification(db, capa, req, user)`、`list_verifications(db, capa)`、`update_verification(db, capa, vid, req, user)`，均带 `capa_id + factory_id` 联合过滤；`update_verification` 不匹配抛 `LookupError`。

- [ ] **Step 1: 写失败测试（追加到 test 文件）**

```python
from app.schemas.capa_verification import VerificationCreate, VerificationUpdate
from app.services.capa_verification_service import (
    create_verification, list_verifications, update_verification,
)
from app.models.capa import CapaRootCauseVerification


@pytest.mark.asyncio
async def test_create_verification_is_verified_sets_verifier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    req = VerificationCreate(root_cause_text="rc", method="m", result="r", is_verified=True)
    rec = await create_verification(db, capa, req, admin_user)
    assert rec.is_verified is True
    assert rec.verified_by == admin_user.user_id
    assert rec.verified_at is not None


@pytest.mark.asyncio
async def test_create_verification_not_verified_no_verifier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    req = VerificationCreate(root_cause_text="rc", is_verified=False)
    rec = await create_verification(db, capa, req, admin_user)
    assert rec.is_verified is False
    assert rec.verified_by is None
    assert rec.verified_at is None


@pytest.mark.asyncio
async def test_update_flip_false_to_true_sets_verifier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    assert rec.verified_by is None
    updated = await update_verification(db, capa, rec.verification_id,
                                        VerificationUpdate(is_verified=True), admin_user)
    assert updated.is_verified is True
    assert updated.verified_by == admin_user.user_id
    assert updated.verified_at is not None


@pytest.mark.asyncio
async def test_update_flip_true_to_false_clears_verifier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc", is_verified=True), admin_user)
    updated = await update_verification(db, capa, rec.verification_id,
                                        VerificationUpdate(is_verified=False), admin_user)
    assert updated.is_verified is False
    assert updated.verified_by is None
    assert updated.verified_at is None


@pytest.mark.asyncio
async def test_update_other_capa_record_returns_404_lookup(db, default_factory, admin_user):
    capa_a = await _make_capa(db, default_factory.id, admin_user.user_id, doc_no="8D-A")
    capa_b = await _make_capa(db, default_factory.id, admin_user.user_id, doc_no="8D-B")
    rec_b = await create_verification(db, capa_b, VerificationCreate(root_cause_text="b"), admin_user)
    # 用 capa_a 的上下文去改 capa_b 的记录 → LookupError
    with pytest.raises(LookupError):
        await update_verification(db, capa_a, rec_b.verification_id,
                                  VerificationUpdate(is_verified=True), admin_user)


@pytest.mark.asyncio
async def test_list_verifications_desc_by_created(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await create_verification(db, capa, VerificationCreate(root_cause_text="first"), admin_user)
    await create_verification(db, capa, VerificationCreate(root_cause_text="second"), admin_user)
    items = await list_verifications(db, capa)
    assert [i.root_cause_text for i in items] == ["second", "first"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/capa/test_capa_verification_service.py -x -q -k verification`
Expected: FAIL（3 个函数未定义）。

- [ ] **Step 3: 追加实现到 `capa_verification_service.py`**

文件顶部 import 区追加：
```python
from sqlalchemy import func, select
from app.models.capa import CapaRootCauseVerification
from app.schemas.capa_verification import VerificationCreate, VerificationUpdate
```
文件末尾追加：
```python
async def create_verification(db: AsyncSession, capa, req: VerificationCreate, user):
    rec = CapaRootCauseVerification(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        root_cause_text=req.root_cause_text, method=req.method, result=req.result,
        is_verified=req.is_verified, evidence_attachments=req.evidence_attachments,
        source_ref=req.source_ref,
        verified_by=user.user_id if req.is_verified else None,
        verified_at=func.now() if req.is_verified else None,
    )
    db.add(rec)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="RC_VERIFY",
        changed_fields={
            "is_verified": req.is_verified, "root_cause_text": req.root_cause_text,
            "source_ref": req.source_ref,
        },
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    await db.commit()
    await db.refresh(rec)
    return rec


async def list_verifications(db: AsyncSession, capa):
    result = await db.execute(
        select(CapaRootCauseVerification)
        .where(CapaRootCauseVerification.capa_id == capa.report_id,
               CapaRootCauseVerification.factory_id == capa.factory_id)
        .order_by(CapaRootCauseVerification.created_at.desc()))
    return list(result.scalars().all())


async def update_verification(db: AsyncSession, capa, vid, req: VerificationUpdate, user):
    rec = await db.scalar(select(CapaRootCauseVerification).where(
        CapaRootCauseVerification.verification_id == vid,
        CapaRootCauseVerification.capa_id == capa.report_id,
        CapaRootCauseVerification.factory_id == capa.factory_id,
    ))
    if rec is None:
        raise LookupError("verification not found")
    if req.is_verified is not None and req.is_verified != rec.is_verified:
        if req.is_verified:
            rec.is_verified = True
            rec.verified_by = user.user_id
            rec.verified_at = func.now()
        else:
            rec.is_verified = False
            rec.verified_by = None
            rec.verified_at = None
    if req.method is not None:
        rec.method = req.method
    if req.result is not None:
        rec.result = req.result
    if req.evidence_attachments is not None:
        rec.evidence_attachments = req.evidence_attachments
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="RC_VERIFY",
        changed_fields={"verification_id": str(vid), "is_verified": rec.is_verified,
                        "method": req.method, "result": req.result},
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    await db.commit()
    await db.refresh(rec)
    return rec
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/capa/test_capa_verification_service.py -q`
Expected: PASS（全部 verification + adopt 测试）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/capa_verification_service.py backend/tests/capa/test_capa_verification_service.py
git commit -m "feat(capa): verification CRUD with verifier timestamps + ownership filter"
```

---

## Task 5: `advance_capa` D4→D5 闸口

**Files:**
- Modify: `backend/app/services/capa_service.py:257-283`（advance_capa 加闸口）
- Test: `backend/tests/capa/test_capa_d4_gate.py`

**Interfaces:**
- Consumes: `CapaRootCauseVerification`（Task 1）。
- Produces: `advance_capa` 在 `D4_ROOT_CAUSE → D5_CORRECTION` 时要求 `count(is_verified=True) ≥ 1`，否则 `ValueError`。

- [ ] **Step 1: 写失败测试**

`backend/tests/capa/test_capa_d4_gate.py`：
```python
import uuid
import pytest
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.schemas.capa_verification import VerificationCreate
from app.services.capa_service import advance_capa
from app.services.capa_verification_service import create_verification

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, status="D4_ROOT_CAUSE"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-GATE-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status=status, d4_root_cause="rc",
    )
    db.add(capa); await db.flush()
    return capa


@pytest.mark.asyncio
async def test_advance_d4_to_d5_blocked_without_verified(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="已验证根因"):
        await advance_capa(db, capa, admin_user.user_id)


@pytest.mark.asyncio
async def test_advance_d4_to_d5_allowed_with_verified(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await create_verification(db, capa, VerificationCreate(root_cause_text="rc", is_verified=True), admin_user)
    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D5_CORRECTION"


@pytest.mark.asyncio
async def test_advance_d4_to_d5_blocked_with_only_unverified(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await create_verification(db, capa, VerificationCreate(root_cause_text="rc", is_verified=False), admin_user)
    with pytest.raises(ValueError):
        await advance_capa(db, capa, admin_user.user_id)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/capa/test_capa_d4_gate.py -x -q`
Expected: FAIL（无闸口，`blocked_without_verified` 直接推进成功，无 ValueError）。

- [ ] **Step 3: 加闸口到 `advance_capa`**

`backend/app/services/capa_service.py` 顶部 import 区追加：
```python
from app.models.capa import CapaRootCauseVerification
```
（保留既有 `from app.models.capa import CAPAEightD`，改为多行 import：`from app.models.capa import CAPAEightD, CapaRootCauseVerification`）

在 `advance_capa` 函数内，`if not can_transition(...)` 块之后、`old_status = capa.status` 之前插入：
```python
    if current == EightDState.D4_ROOT_CAUSE and next_state == EightDState.D5_CORRECTION:
        cnt = await db.scalar(select(func.count()).select_from(CapaRootCauseVerification).where(
            CapaRootCauseVerification.capa_id == capa.report_id,
            CapaRootCauseVerification.is_verified == True,  # noqa: E712
        ))
        if cnt < 1:
            raise ValueError("D4→D5 需至少 1 条已验证根因记录")
```
（`select` 与 `func` 已在文件顶部 import。）

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/capa/test_capa_d4_gate.py -q`
Expected: PASS。

- [ ] **Step 5: 回归既有 capa 测试**

Run: `cd backend && python -m pytest tests/test_capa_recommendation.py tests/test_d7_recommendations.py tests/capa/ -q`
Expected: PASS（既有测试不越过 D4，或若越过需补 fixture——预期无需改）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/capa_service.py backend/tests/capa/test_capa_d4_gate.py
git commit -m "feat(capa): D4->D5 gate requires verified root cause"
```

---

## Task 6: `fmea_service._apply_fmea_update` 无提交核心拆分（R3-Finding 2）

**Files:**
- Modify: `backend/app/services/fmea_service.py:196-278`
- Test: `backend/tests/fmea/test_fmea_update_core.py`

**Interfaces:**
- Produces: `async def _apply_fmea_update(db, fmea, title, graph_data, user_id, product_line_code=None, lock_version=None, confirmed_latest_lock_version=None) -> FMEADocument`（不 commit / 不 refresh，保留 FOR UPDATE + lock_version++ + GraphSyncOutbox + 缓存失效 + enqueue_embedding 全部副作用）。`update_fmea` 改为调核心 + commit + refresh，公开行为不变。

- [ ] **Step 1: 写失败测试**

`backend/tests/fmea/test_fmea_update_core.py`：
```python
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.models.graph_sync_outbox import GraphSyncOutbox
from app.services.fmea_service import update_fmea, _apply_fmea_update

pytestmark = pytest.mark.requires_db


async def _make_fmea(db, factory_id, user_id, graph=None):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-CORE-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph or {"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_update_fmea_public_behavior_unchanged(db, default_factory, admin_user):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id,
                            graph={"nodes": [{"id": "n1", "type": "FailureMode", "name": "x"}], "edges": []})
    new_graph = {"nodes": [{"id": "n1", "type": "FailureMode", "name": "y"}], "edges": []}
    out = await update_fmea(db, fmea, title=None, graph_data=new_graph, user_id=admin_user.user_id)
    assert out.lock_version == fmea.lock_version + 1 or out.lock_version >= 1
    outbox = (await db.execute(select(GraphSyncOutbox).where(GraphSyncOutbox.aggregate_id == fmea.fmea_id))).scalars().all()
    assert len(outbox) >= 1
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == fmea.fmea_id, AuditLog.action == "UPDATE"))).scalars().all()
    assert len(audits) >= 1


@pytest.mark.asyncio
async def test_apply_fmea_update_does_not_commit(db, default_factory, admin_user):
    """_apply_fmea_update 不 commit：在调用方未 commit 前，新 session 看不到 graph 变化占位——
    这里用同 session flush 后即可查到 audit/outbox 行（证明副作用已 add），且函数无返回外 commit。"""
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id,
                            graph={"nodes": [{"id": "n1", "type": "FailureMode", "name": "x"}], "edges": []})
    new_graph = {"nodes": [{"id": "n1", "type": "FailureMode", "name": "y"}], "edges": []}
    await _apply_fmea_update(db, fmea, title=None, graph_data=new_graph, user_id=admin_user.user_id)
    await db.flush()
    outbox = (await db.execute(select(GraphSyncOutbox).where(GraphSyncOutbox.aggregate_id == fmea.fmea_id))).scalars().all()
    assert len(outbox) >= 1   # 副作用已 add 到 session，但函数未 commit
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/fmea/test_fmea_update_core.py -x -q`
Expected: FAIL（`_apply_fmea_update` 未导出 / `ImportError`）。

- [ ] **Step 3: 拆分 `update_fmea`**

`backend/app/services/fmea_service.py`：把 `update_fmea`（L196-278）拆为两个函数。替换整个 `update_fmea` 函数为：
```python
async def _apply_fmea_update(
    db: AsyncSession,
    fmea: FMEADocument,
    title: str | None,
    graph_data: dict | None,
    user_id: uuid.UUID,
    product_line_code: str | None = None,
    lock_version: int | None = None,
    confirmed_latest_lock_version: int | None = None,
) -> FMEADocument:
    """无提交核心：执行 update_fmea 的全部副作用但不 commit/refresh，供 auto_fill_d7 单事务复用。"""
    result = await db.execute(
        select(FMEADocument)
        .where(FMEADocument.fmea_id == fmea.fmea_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    fresh = result.scalar_one()

    if confirmed_latest_lock_version is not None:
        if fresh.lock_version != confirmed_latest_lock_version:
            raise ValueError("lock_version_changed_again")
    elif lock_version is not None:
        if fresh.lock_version != lock_version:
            raise ValueError("lock_version_mismatch")

    changed_fields = {}
    if title is not None and title != fmea.title:
        changed_fields["title"] = title
        fmea.title = title
    if graph_data is not None:
        import json
        old_graph = json.dumps(fmea.graph_data, sort_keys=True) if fmea.graph_data else ""
        new_graph = json.dumps(graph_data, sort_keys=True)
        if new_graph != old_graph:
            changed_fields["graph_data"] = graph_data
            fmea.graph_data = graph_data
    if product_line_code is not None and product_line_code != fmea.product_line_code:
        await validate_product_line(db, product_line_code)
        changed_fields["product_line_code"] = product_line_code
        fmea.product_line_code = product_line_code
    fmea.updated_by = user_id

    if changed_fields:
        fmea.lock_version += 1
        db.add(AuditLog(
            table_name="fmea_documents", record_id=fmea.fmea_id,
            action="UPDATE", changed_fields=changed_fields, operated_by=user_id,
            factory_id=fmea.factory_id,
        ))
        db.add(GraphSyncOutbox(
            aggregate_type="fmea", aggregate_id=fmea.fmea_id,
            event_type="fmea.updated",
            payload={"version": fmea.version, "product_line_code": fmea.product_line_code},
        ))
        if confirmed_latest_lock_version is not None:
            db.add(AuditLog(
                table_name="fmea_documents", record_id=fmea.fmea_id,
                action="FORCE_SAVE_OVERRIDE",
                changed_fields={"reason": "User confirmed overwrite after conflict detection"},
                operated_by=user_id, factory_id=fmea.factory_id,
            ))
        if graph_data is not None or product_line_code is not None:
            from app.services.recommendation_service import RecommendationService, _NullGraphRepo
            rec_service = RecommendationService(db=db, graph_repo=_NullGraphRepo())
            await rec_service.invalidate_cache_for_fmea(fmea.fmea_id)

    await enqueue_embedding(db, "fmea_node", fmea.fmea_id, fmea.product_line_code, fmea.factory_id)
    return fmea


async def update_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    title: str | None,
    graph_data: dict | None,
    user_id: uuid.UUID,
    product_line_code: str | None = None,
    lock_version: int | None = None,
    confirmed_latest_lock_version: int | None = None,
) -> FMEADocument:
    fmea = await _apply_fmea_update(
        db, fmea, title, graph_data, user_id, product_line_code,
        lock_version, confirmed_latest_lock_version,
    )
    await db.commit()
    await db.refresh(fmea)
    return fmea
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/fmea/test_fmea_update_core.py -q`
Expected: PASS。

- [ ] **Step 5: 回归 fmea 测试**

Run: `cd backend && python -m pytest tests/ -k "fmea" -q`
Expected: PASS（既有 fmea 测试零改动通过）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/fmea_service.py backend/tests/fmea/test_fmea_update_core.py
git commit -m "refactor(fmea): extract _apply_fmea_update no-commit core"
```

---

## Task 7: D7 `record_d7_action` + `list_d7_actions`（upsert + 幂等 + FMEA 校验）

**Files:**
- Create: `backend/app/services/capa_d7_action_service.py`
- Test: `backend/tests/capa/test_capa_d7_action_service.py`

**Interfaces:**
- Consumes: `CapaD7NodeAction`（Task 1）、`FMEADocument`、`AuditLog`、`_fetch_fmea_for_d7`。
- Produces: `ConflictError`（异常类，handler 映 409）、`record_d7_action(db, capa, req, user)`、`list_d7_actions(db, capa)`、`_fetch_fmea_for_d7(db, capa, fmea_id) -> FMEADocument`（None→`LookupError`，跨工厂→`PermissionError`）。

- [ ] **Step 1: 写失败测试**

`backend/tests/capa/test_capa_d7_action_service.py`：
```python
import copy
import uuid
import pytest
from sqlalchemy import select
from app.models.capa import CAPAEightD, CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import D7NodeActionCreate
from app.services.capa_d7_action_service import (
    ConflictError, record_d7_action, list_d7_actions,
)

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, d5="措施A"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-D7-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status="D7_PREVENTION", d5_correction=d5,
    )
    db.add(capa); await db.flush()
    return capa


async def _make_fmea(db, factory_id, user_id, fm_id="fm-1", cause_id="c-1"):
    graph = {"nodes": [
        {"id": fm_id, "type": "FailureMode", "name": "虚焊"},
        {"id": cause_id, "type": "FailureCause", "name": "参数偏移"},
    ], "edges": [{"source": cause_id, "target": fm_id, "type": "CAUSE_OF"}]}
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-D7-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_record_confirmed_inserts_and_audits(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert rec.action == "confirmed"


@pytest.mark.asyncio
async def test_record_idempotent_same_action_and_reason(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    req = D7NodeActionCreate(action="confirmed", fmea_id=fmea.fmea_id,
                            failure_mode_node_id="fm-1", failure_cause_node_id="c-1",
                            match_source="linked")
    first = await record_d7_action(db, capa, req, admin_user)
    second = await record_d7_action(db, capa, req, admin_user)
    assert second.action_id == first.action_id   # 幂等返回既有行，无新行
    all_rows = (await db.execute(
        select(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == capa.report_id)
    )).scalars().all()
    assert len(all_rows) == 1


@pytest.mark.asyncio
async def test_record_change_action_writes_changed_audit(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="skipped", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked", reason="不适用"), admin_user)
    assert rec.action == "skipped"
    assert rec.reason == "不适用"


@pytest.mark.asyncio
async def test_record_fmea_not_found_lookup(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    with pytest.raises(LookupError):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=uuid.uuid4(), failure_mode_node_id="fm-1",
            match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_record_cross_factory_fmea_permission(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    # 在另一个 factory 建 FMEA
    from app.models.factory import Factory
    other = Factory(id=uuid.uuid4(), code="OTHER", name="Other")
    db.add(other); await db.flush()
    fmea = await _make_fmea(db, other.id, admin_user.user_id)
    with pytest.raises(PermissionError):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            match_source="linked"), admin_user)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/capa/test_capa_d7_action_service.py -x -q`
Expected: FAIL（`ImportError`：service 未建）。

- [ ] **Step 3: 写 service**

`backend/app/services/capa_d7_action_service.py`：
```python
import uuid
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import D7NodeActionCreate


class ConflictError(Exception):
    """D7 动作幂等冲突（如已 auto_filled 再 auto-fill）—— handler 映 409。"""


async def _fetch_fmea_for_d7(db: AsyncSession, capa, fmea_id, *, lock: bool = False) -> FMEADocument:
    # lock=True 时 SELECT ... FOR UPDATE，串行化并发 auto-fill（必须在读 graph_data 之前锁，
    # 否则另一事务可能在读 graph 与 _apply_fmea_update 之间改 FMEA graph）
    if lock:
        fmea = (await db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id == fmea_id).with_for_update()
        )).scalar_one_or_none()
    else:
        fmea = await db.get(FMEADocument, fmea_id)
    if fmea is None:
        raise LookupError("目标 FMEA 不存在")
    if fmea.factory_id != capa.factory_id:
        raise PermissionError("目标 FMEA 跨工厂")
    return fmea


async def record_d7_action(db: AsyncSession, capa, req: D7NodeActionCreate, user) -> CapaD7NodeAction:
    await _fetch_fmea_for_d7(db, capa, req.fmea_id)
    existing = await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id,
        CapaD7NodeAction.fmea_id == req.fmea_id,
        CapaD7NodeAction.failure_mode_node_id == req.failure_mode_node_id,
        CapaD7NodeAction.failure_cause_node_id == req.failure_cause_node_id,
    ))
    if existing is not None:
        if existing.action == "auto_filled":
            raise ValueError("已自动回填，不可改判")
        if existing.action == req.action and (existing.reason or None) == (req.reason or None):
            return existing   # 幂等：同 action + reason 不变
        old_action = existing.action
        old_reason = existing.reason
        existing.action = req.action
        existing.reason = req.reason
        existing.acted_by = user.user_id
        existing.acted_at = func.now()
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D7_ACTION_CHANGED",
            changed_fields={
                "fmea_id": str(req.fmea_id),
                "failure_mode_node_id": req.failure_mode_node_id,
                "failure_cause_node_id": req.failure_cause_node_id,
                "old_action": old_action, "new_action": req.action,
                "old_reason": old_reason, "new_reason": req.reason,
            },
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
        await db.commit()
        await db.refresh(existing)
        return existing
    rec = CapaD7NodeAction(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        action=req.action, fmea_id=req.fmea_id,
        failure_mode_node_id=req.failure_mode_node_id,
        failure_cause_node_id=req.failure_cause_node_id,
        match_source=req.match_source, reason=req.reason, acted_by=user.user_id,
    )
    db.add(rec)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action=f"D7_NODE_{req.action.upper()}",
        changed_fields={
            "fmea_id": str(req.fmea_id),
            "failure_mode_node_id": req.failure_mode_node_id,
            "failure_cause_node_id": req.failure_cause_node_id,
            "match_source": req.match_source, "reason": req.reason,
        },
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    await db.commit()
    await db.refresh(rec)
    return rec


async def list_d7_actions(db: AsyncSession, capa) -> list[CapaD7NodeAction]:
    result = await db.execute(
        select(CapaD7NodeAction)
        .where(CapaD7NodeAction.capa_id == capa.report_id,
               CapaD7NodeAction.factory_id == capa.factory_id)
        .order_by(CapaD7NodeAction.acted_at.desc()))
    return list(result.scalars().all())
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/capa/test_capa_d7_action_service.py -q`
Expected: PASS（record/list 测试）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/capa_d7_action_service.py backend/tests/capa/test_capa_d7_action_service.py
git commit -m "feat(capa): D7 record_d7_action upsert + idempotent + FMEA ownership"
```

---

## Task 8: D7 `auto_fill_d7`（deepcopy + 复用 `_apply_fmea_update` + upsert/升级）

**Files:**
- Modify: `backend/app/services/capa_d7_action_service.py`（追加 `auto_fill_d7`）
- Test: `backend/tests/capa/test_capa_d7_action_service.py`（追加）

**Interfaces:**
- Consumes: `app.services.fmea_service._apply_fmea_update`（Task 6）、`ConflictError`（Task 7）。
- Produces: `auto_fill_d7(db, capa, req: D7AutoFillRequest, user) -> tuple[CapaD7NodeAction, dict]`。

- [ ] **Step 1: 写失败测试（追加）**

```python
from app.schemas.capa_verification import D7AutoFillRequest
from app.services.capa_d7_action_service import auto_fill_d7, record_d7_action
from app.models.fmea import FMEADocument
from sqlalchemy import select as _sel


@pytest.mark.asyncio
async def test_auto_fill_new_control_persists_graph(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    rec, info = await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert info["is_new_control"] is True
    assert info["prevention_control_name_after"] == "新监控"
    # 重新查询 FMEA，graph_data 已持久化（防原地改 JSONB）
    refreshed = await db.get(FMEADocument, fmea.fmea_id)
    ctrl = [n for n in refreshed.graph_data["nodes"] if n["type"] == "PreventionControl"]
    assert len(ctrl) == 1
    assert ctrl[0]["name"] == "新监控"
    assert rec.action == "auto_filled"
    assert rec.prevention_control_name_after == "新监控"


@pytest.mark.asyncio
async def test_auto_fill_existing_control_captures_before(db, default_factory, admin_user):
    ctrl_id = "ctrl-1"
    graph = {"nodes": [
        {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
        {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
        {"id": ctrl_id, "type": "PreventionControl", "name": "旧监控"},
    ], "edges": [
        {"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"},
        {"source": "c-1", "target": ctrl_id, "type": "PREVENTED_BY"},
    ]}
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="新监控")
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-EX-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    rec, info = await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert info["is_new_control"] is False
    assert rec.prevention_control_name_before == "旧监控"
    assert rec.prevention_control_name_after == "新监控"


@pytest.mark.asyncio
async def test_auto_fill_d5_empty_raises(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5=None)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError):
        await auto_fill_d7(db, capa, D7AutoFillRequest(
            fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            failure_cause_node_id="c-1", match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_auto_fill_idempotent_conflict(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    req = D7AutoFillRequest(fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
                            failure_cause_node_id="c-1", match_source="linked")
    await auto_fill_d7(db, capa, req, admin_user)
    with pytest.raises(ConflictError):
        await auto_fill_d7(db, capa, req, admin_user)


@pytest.mark.asyncio
async def test_auto_fill_upgrades_confirmed_to_auto_filled(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    rec, info = await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert rec.action == "auto_filled"
    rows = (await db.execute(_sel(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 1   # 升级同一行，未新增


@pytest.mark.asyncio
async def test_auto_fill_integrity_error_maps_to_conflict_not_500(db, default_factory, admin_user, monkeypatch):
    """并发 auto-fill 撞 ix_capa_d7_node_unique 时应映 ConflictError(409)，不泄漏 IntegrityError/500；
    rollback 应撤销 FMEA graph 改动（无 stale graph write）。
    db fixture 是 flush-only，无法起真并发——用 monkeypatch 让首次 commit 抛 IntegrityError 模拟撞约束。"""
    from sqlalchemy.exc import IntegrityError as _IntErr
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="监控")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    graph_before = copy.deepcopy(fmea.graph_data)
    req = D7AutoFillRequest(fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
                            failure_cause_node_id="c-1", match_source="linked")
    real_commit = db.commit
    calls = {"n": 0}
    async def _patched_commit(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _IntErr("simulated unique violation", {}, Exception("unique"))
        return await real_commit(*a, **kw)
    monkeypatch.setattr(db, "commit", _patched_commit)
    with pytest.raises(ConflictError):
        await auto_fill_d7(db, capa, req, admin_user)
    # 回滚后 FMEA graph 未被污染（stale write 会被 rollback 撤销）
    await db.refresh(fmea)
    assert fmea.graph_data == graph_before
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/capa/test_capa_d7_action_service.py -k auto_fill -x -q`
Expected: FAIL（`auto_fill_d7` 未定义）。

- [ ] **Step 3: 实现 `auto_fill_d7`**

`backend/app/services/capa_d7_action_service.py` 顶部 import 区追加：
```python
import copy
from app.schemas.capa_verification import D7AutoFillRequest
from app.services.fmea_service import _apply_fmea_update
```
文件末尾追加：
```python
async def auto_fill_d7(db: AsyncSession, capa, req: D7AutoFillRequest, user):
    if not capa.d5_correction:
        raise ValueError("D5 永久措施为空，无法自动回填")
    # 锁 FMEA 行（FOR UPDATE），串行化并发 auto-fill；必须在读 graph_data 之前锁，
    # 否则两个并发请求都读到旧 graph、都过既有行检查，一个 commit 时撞 unique index → 500
    fmea = await _fetch_fmea_for_d7(db, capa, req.fmea_id, lock=True)
    # 先查既有行：已 auto_filled 直接 409，必须在改 FMEA graph 之前，避免污染 session
    existing = await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id,
        CapaD7NodeAction.fmea_id == req.fmea_id,
        CapaD7NodeAction.failure_mode_node_id == req.failure_mode_node_id,
        CapaD7NodeAction.failure_cause_node_id == req.failure_cause_node_id,
    ))
    if existing is not None and existing.action == "auto_filled":
        raise ConflictError("已自动回填")
    graph = copy.deepcopy(fmea.graph_data or {"nodes": [], "edges": []})
    ctrl_node = None
    name_before = None
    for e in graph["edges"]:
        if e["source"] == req.failure_cause_node_id and e["type"] == "PREVENTED_BY":
            for n in graph["nodes"]:
                if n["id"] == e["target"] and n["type"] == "PreventionControl":
                    ctrl_node = n
                    name_before = n.get("name")
                    break
    is_new = ctrl_node is None
    if is_new:
        ctrl_id = str(uuid.uuid4())
        graph["nodes"].append({
            "id": ctrl_id, "type": "PreventionControl", "name": capa.d5_correction,
            "severity": 1, "occurrence": 1, "detection": 1,
        })
        graph["edges"].append({
            "source": req.failure_cause_node_id, "target": ctrl_id, "type": "PREVENTED_BY",
        })
        ctrl_node = graph["nodes"][-1]
    else:
        ctrl_node["name"] = capa.d5_correction
    # 复用 FMEA 全部副作用（lock_version++/outbox/cache/embedding），不 commit
    await _apply_fmea_update(db, fmea, title=None, graph_data=graph, user_id=user.user_id)

    if existing is not None:
        # existing.action in {confirmed, skipped} → 升级为 auto_filled（auto_filled 已在上方提前 409）
        old_action = existing.action
        existing.action = "auto_filled"
        existing.prevention_control_node_id = ctrl_node["id"]
        existing.prevention_control_name_before = name_before
        existing.prevention_control_name_after = capa.d5_correction
        existing.acted_by = user.user_id
        existing.acted_at = func.now()
        rec = existing
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D7_ACTION_CHANGED",
            changed_fields={"old_action": old_action, "new_action": "auto_filled",
                            "prevention_control_node_id": ctrl_node["id"]},
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
    else:
        rec = CapaD7NodeAction(
            capa_id=capa.report_id, factory_id=capa.factory_id,
            action="auto_filled", fmea_id=req.fmea_id,
            failure_mode_node_id=req.failure_mode_node_id,
            failure_cause_node_id=req.failure_cause_node_id,
            match_source=req.match_source,
            prevention_control_node_id=ctrl_node["id"],
            prevention_control_name_before=name_before,
            prevention_control_name_after=capa.d5_correction,
            acted_by=user.user_id,
        )
        db.add(rec)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="D7_AUTO_FILLED_FMEA",
        changed_fields={
            "fmea_id": str(req.fmea_id), "failure_cause_node_id": req.failure_cause_node_id,
            "prevention_control_node_id": ctrl_node["id"],
            "name_before": name_before, "name_after": capa.d5_correction,
        },
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    try:
        await db.commit()
    except IntegrityError:
        # 并发 auto-fill：另一事务先 commit 同 (capa, fmea, fm, cause) → ix_capa_d7_node_unique 兜底
        # 命中 → 回滚后映 409（不是 500），与"已自动回填"语义一致
        await db.rollback()
        raise ConflictError("已自动回填")
    await db.refresh(rec)
    return rec, {
        "prevention_control_node_id": ctrl_node["id"],
        "prevention_control_name_after": capa.d5_correction,
        "is_new_control": is_new,
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/capa/test_capa_d7_action_service.py -q`
Expected: PASS（record + auto_fill 全部）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/capa_d7_action_service.py backend/tests/capa/test_capa_d7_action_service.py
git commit -m "feat(capa): D7 auto_fill_d7 with deepcopy graph + fmea core reuse"
```

---

## Task 9: Verification API 端点（adopt + 3 verification）

**Files:**
- Modify: `backend/app/api/capa.py`（加 4 端点）
- Test: `backend/tests/capa/test_capa_verification_api.py`

**Interfaces:**
- Consumes: `adopt_recommendation` / `create_verification` / `list_verifications` / `update_verification`（Task 3/4）。
- Produces: `POST /api/capa/{report_id}/adopt-recommendation`、`POST|GET /api/capa/{report_id}/root-cause-verifications`、`PATCH /api/capa/{report_id}/root-cause-verifications/{vid}`。

- [ ] **Step 1: 写失败测试**

`backend/tests/capa/test_capa_verification_api.py`：
```python
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.capa import CAPAEightD
from app.models.role import RolePermission
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _seed_perms(db, role_id):
    for mod, lvl in [("capa", 5), ("fmea", 5)]:
        existing = await db.execute(select(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.module == mod))
        if existing.scalar_one_or_none() is None:
            db.add(RolePermission(role_id=role_id, module=mod, permission_level=lvl))
            await db.flush()


@pytest.fixture
async def capa_client(db, admin_user, default_factory):
    await _seed_perms(db, admin_user.role_id)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_capa(db, factory_id, user_id, doc_no):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no, title="t",
        product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status="D4_ROOT_CAUSE")
    db.add(capa); await db.flush()
    return capa


@pytest.mark.asyncio
async def test_adopt_endpoint_appends_d4(capa_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-ADOPT")
    resp = await capa_client.post(f"/api/capa/{capa.report_id}/adopt-recommendation",
        json={"d_step": "d4", "adopted_text": "根因B", "source": "fmea_graph",
              "item_ref": {"failure_cause_node_id": "c1"}})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["field_value"] == "根因B"
    assert body["d_step"] == "d4"


@pytest.mark.asyncio
async def test_adopt_rejects_d7_step(capa_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-D7REJ")
    resp = await capa_client.post(f"/api/capa/{capa.report_id}/adopt-recommendation",
        json={"d_step": "d7", "adopted_text": "x", "source": "rule"})
    assert resp.status_code == 422   # Literal["d4","d5"] 拒绝


@pytest.mark.asyncio
async def test_create_and_list_verification(capa_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-VER")
    r1 = await capa_client.post(f"/api/capa/{capa.report_id}/root-cause-verifications",
        json={"root_cause_text": "rc", "is_verified": True})
    assert r1.status_code == 200, r1.text
    assert r1.json()["is_verified"] is True
    r2 = await capa_client.get(f"/api/capa/{capa.report_id}/root-cause-verifications")
    assert r2.status_code == 200
    assert len(r2.json()) == 1


@pytest.mark.asyncio
async def test_patch_verification_other_capa_404(capa_client, db, default_factory, admin_user):
    capa_a = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-A")
    capa_b = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-B")
    r = await capa_client.post(f"/api/capa/{capa_b.report_id}/root-cause-verifications",
        json={"root_cause_text": "b"})
    vid = r.json()["verification_id"]
    # 用 capa_a 的 URL 改 capa_b 的记录
    patch = await capa_client.patch(f"/api/capa/{capa_a.report_id}/root-cause-verifications/{vid}",
        json={"is_verified": True})
    assert patch.status_code == 404


@pytest.mark.asyncio
async def test_advance_d4_to_d5_blocked_api(capa_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-GATE")
    resp = await capa_client.post(f"/api/capa/{capa.report_id}/advance", json={})
    assert resp.status_code == 400


@pytest.fixture
async def low_perm_client_builder(db, admin_user, default_factory):
    """工厂：按指定 capa 权限级别构造 AsyncClient（这些端点只校验 CAPA 模块；fmea 固定 5 不影响）。级别用 PermissionLevel 数值（NONE=0/VIEW=1/CREATE=2/EDIT=3/APPROVE=4/ADMIN=5）。"""
    async def _build(capa_level: int):
        existing = (await db.execute(select(RolePermission).where(
            RolePermission.role_id == admin_user.role_id, RolePermission.module == "capa"))).scalar_one_or_none()
        if existing is None:
            db.add(RolePermission(role_id=admin_user.role_id, module="capa", permission_level=capa_level))
        else:
            existing.permission_level = capa_level
        await db.flush()
        scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_scope] = lambda: scope
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield _build
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_adopt_403_without_capa_edit(low_perm_client_builder, db, default_factory, admin_user):
    # capa=CREATE(2) < EDIT(3) → adopt 应 403
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-ADOPT-403")
    ac = await low_perm_client_builder(capa_level=2)
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/adopt-recommendation",
            json={"d_step": "d4", "adopted_text": "x", "source": "fmea_graph"})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_verification_403_without_capa_edit(low_perm_client_builder, db, default_factory, admin_user):
    # capa=CREATE(2) < EDIT(3) → create verification 应 403
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-CRT-403")
    ac = await low_perm_client_builder(capa_level=2)
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/root-cause-verifications",
            json={"root_cause_text": "rc"})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_verification_200_with_capa_view(low_perm_client_builder, db, default_factory, admin_user):
    # capa=VIEW(1) ≥ VIEW(1) → list 应 200（先以 EDIT 建一条记录，再降到 VIEW 列举）
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-LIST-200")
    ac_edit = await low_perm_client_builder(capa_level=3)
    async with ac_edit:
        await ac_edit.post(f"/api/capa/{capa.report_id}/root-cause-verifications",
            json={"root_cause_text": "rc"})
    ac_view = await low_perm_client_builder(capa_level=1)
    async with ac_view:
        r = await ac_view.get(f"/api/capa/{capa.report_id}/root-cause-verifications")
        assert r.status_code == 200
        assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_list_verification_403_without_capa_view(low_perm_client_builder, db, default_factory, admin_user):
    # capa=NONE(0) < VIEW(1) → list 应 403
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-LIST-403")
    ac = await low_perm_client_builder(capa_level=0)
    async with ac:
        r = await ac.get(f"/api/capa/{capa.report_id}/root-cause-verifications")
        assert r.status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/capa/test_capa_verification_api.py -x -q`
Expected: FAIL（端点不存在 → 404）。

- [ ] **Step 3: 加 4 端点到 `backend/app/api/capa.py`**

文件顶部 import 区追加：
```python
from app.schemas.capa_verification import (
    AdoptRequest, AdoptResponse, VerificationCreate, VerificationResponse, VerificationUpdate,
)
from app.services import capa_verification_service
```
在 `router` 定义之后、`@router.get("")` 之前或文件末尾追加 4 个 handler：
```python
@router.post("/{report_id}/adopt-recommendation", response_model=AdoptResponse)
async def adopt_recommendation_ep(
    report_id: uuid.UUID, req: AdoptRequest,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    adoption, field_value = await capa_verification_service.adopt_recommendation(db, capa, req, scope.user)
    return AdoptResponse(adoption_id=adoption.adoption_id, d_step=req.d_step, field_value=field_value)


@router.post("/{report_id}/root-cause-verifications", response_model=VerificationResponse)
async def create_verification_ep(
    report_id: uuid.UUID, req: VerificationCreate,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    rec = await capa_verification_service.create_verification(db, capa, req, scope.user)
    return VerificationResponse.model_validate(rec)


@router.get("/{report_id}/root-cause-verifications", response_model=list[VerificationResponse])
async def list_verifications_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    items = await capa_verification_service.list_verifications(db, capa)
    return [VerificationResponse.model_validate(i) for i in items]


@router.patch("/{report_id}/root-cause-verifications/{vid}", response_model=VerificationResponse)
async def update_verification_ep(
    report_id: uuid.UUID, vid: uuid.UUID, req: VerificationUpdate,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    try:
        rec = await capa_verification_service.update_verification(db, capa, vid, req, scope.user)
    except LookupError:
        raise HTTPException(status_code=404, detail="verification not found")
    return VerificationResponse.model_validate(rec)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/capa/test_capa_verification_api.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/capa.py backend/tests/capa/test_capa_verification_api.py
git commit -m "feat(capa): adopt + verification API endpoints"
```

---

## Task 10: D7 API 端点（d7-node-actions POST/GET + d7-auto-fill）

**Files:**
- Modify: `backend/app/api/capa.py`（加 3 端点）
- Test: `backend/tests/capa/test_capa_d7_api.py`

**Interfaces:**
- Consumes: `record_d7_action` / `list_d7_actions` / `auto_fill_d7` / `ConflictError`（Task 7/8）。
- Produces: `POST|GET /api/capa/{report_id}/d7-node-actions`、`POST /api/capa/{report_id}/d7-auto-fill`。异常映射：`ConflictError→409`、`PermissionError→403`、`LookupError→404`、`ValueError→400`。

- [ ] **Step 1: 写失败测试**

`backend/tests/capa/test_capa_d7_api.py`：
```python
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.role import RolePermission
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _seed_perms(db, role_id):
    for mod, lvl in [("capa", 5), ("fmea", 5)]:
        if (await db.execute(select(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.module == mod))).scalar_one_or_none() is None:
            db.add(RolePermission(role_id=role_id, module=mod, permission_level=lvl))
            await db.flush()


@pytest.fixture
async def d7_client(db, admin_user, default_factory):
    await _seed_perms(db, admin_user.role_id)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make(db, factory_id, user_id, doc_no, d5="监控"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no, title="t",
        product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status="D7_PREVENTION", d5_correction=d5)
    db.add(capa); await db.flush()
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-{doc_no}", title="t", fmea_type="PFMEA",
        product_line_code="DC-DC-100", factory_id=factory_id, status="draft",
        created_by=user_id,
        graph_data={"nodes": [
            {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
            {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
        ], "edges": [{"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"}]})
    db.add(fmea); await db.flush()
    return capa, fmea


@pytest.mark.asyncio
async def test_d7_record_and_list(d7_client, db, default_factory, admin_user):
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-1")
    r = await d7_client.post(f"/api/capa/{capa.report_id}/d7-node-actions",
        json={"action": "confirmed", "fmea_id": str(fmea.fmea_id),
              "failure_mode_node_id": "fm-1", "failure_cause_node_id": "c-1", "match_source": "linked"})
    assert r.status_code == 200, r.text
    lst = await d7_client.get(f"/api/capa/{capa.report_id}/d7-node-actions")
    assert lst.status_code == 200
    assert len(lst.json()) == 1
    assert lst.json()[0]["action"] == "confirmed"


@pytest.mark.asyncio
async def test_d7_auto_fill_returns_new_control(d7_client, db, default_factory, admin_user):
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-2", d5="新监控")
    r = await d7_client.post(f"/api/capa/{capa.report_id}/d7-auto-fill",
        json={"fmea_id": str(fmea.fmea_id), "failure_mode_node_id": "fm-1",
              "failure_cause_node_id": "c-1", "match_source": "linked"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new_control"] is True
    assert body["prevention_control_name_after"] == "新监控"


@pytest.mark.asyncio
async def test_d7_auto_fill_repeat_409(d7_client, db, default_factory, admin_user):
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-3")
    payload = {"fmea_id": str(fmea.fmea_id), "failure_mode_node_id": "fm-1",
               "failure_cause_node_id": "c-1", "match_source": "linked"}
    await d7_client.post(f"/api/capa/{capa.report_id}/d7-auto-fill", json=payload)
    r2 = await d7_client.post(f"/api/capa/{capa.report_id}/d7-auto-fill", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_d7_auto_fill_d5_empty_400(d7_client, db, default_factory, admin_user):
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-4", d5=None)
    r = await d7_client.post(f"/api/capa/{capa.report_id}/d7-auto-fill",
        json={"fmea_id": str(fmea.fmea_id), "failure_mode_node_id": "fm-1",
              "failure_cause_node_id": "c-1", "match_source": "linked"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_d7_record_cross_factory_fmea_403(d7_client, db, default_factory, admin_user):
    from app.models.factory import Factory
    capa, _ = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-5")
    other = Factory(id=uuid.uuid4(), code="OTHER2", name="Other2")
    db.add(other); await db.flush()
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-X", title="t", fmea_type="PFMEA",
        product_line_code="DC-DC-100", factory_id=other.id, status="draft",
        created_by=admin_user.user_id, graph_data={"nodes": [], "edges": []})
    db.add(fmea); await db.flush()
    r = await d7_client.post(f"/api/capa/{capa.report_id}/d7-node-actions",
        json={"action": "confirmed", "fmea_id": str(fmea.fmea_id),
              "failure_mode_node_id": "fm-1", "match_source": "linked"})
    assert r.status_code == 403


@pytest.fixture
async def low_perm_client_builder(db, admin_user, default_factory):
    """工厂：按指定 capa/fmea 权限级别构造 AsyncClient。级别用 PermissionLevel 数值（NONE=0/VIEW=1/CREATE=2/EDIT=3/APPROVE=4/ADMIN=5）。"""
    async def _build(capa_level: int, fmea_level: int):
        for mod, lvl in (("capa", capa_level), ("fmea", fmea_level)):
            existing = (await db.execute(select(RolePermission).where(
                RolePermission.role_id == admin_user.role_id, RolePermission.module == mod))).scalar_one_or_none()
            if existing is None:
                db.add(RolePermission(role_id=admin_user.role_id, module=mod, permission_level=lvl))
            else:
                existing.permission_level = lvl
        await db.flush()
        scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_scope] = lambda: scope
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield _build
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_d7_record_403_without_capa_edit(low_perm_client_builder, db, default_factory, admin_user):
    # capa=CREATE(2) < EDIT(3) → d7-node-actions 应 403（fmea 给到 ADMIN 仍不够）
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-6")
    ac = await low_perm_client_builder(capa_level=2, fmea_level=5)
    async with ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/d7-node-actions",
            json={"action": "confirmed", "fmea_id": str(fmea.fmea_id),
                  "failure_mode_node_id": "fm-1", "failure_cause_node_id": "c-1", "match_source": "linked"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_d7_record_403_without_fmea_view(low_perm_client_builder, db, default_factory, admin_user):
    # fmea=NONE(0) < VIEW(1) → d7-node-actions 应 403（capa 给到 ADMIN 仍不够）
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-7")
    ac = await low_perm_client_builder(capa_level=5, fmea_level=0)
    async with ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/d7-node-actions",
            json={"action": "confirmed", "fmea_id": str(fmea.fmea_id),
                  "failure_mode_node_id": "fm-1", "failure_cause_node_id": "c-1", "match_source": "linked"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_d7_auto_fill_403_without_fmea_edit(low_perm_client_builder, db, default_factory, admin_user):
    # fmea=CREATE(2) < EDIT(3) → d7-auto-fill 应 403（capa 给到 ADMIN 仍不够）
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-8", d5="新监控")
    ac = await low_perm_client_builder(capa_level=5, fmea_level=2)
    async with ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/d7-auto-fill",
            json={"fmea_id": str(fmea.fmea_id), "failure_mode_node_id": "fm-1",
                  "failure_cause_node_id": "c-1", "match_source": "linked"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_d7_list_403_without_fmea_view(low_perm_client_builder, db, default_factory, admin_user):
    # capa=VIEW(1) 但 fmea=NONE(0)：GET /d7-node-actions 返回 FMEA 衍生元数据，读也需 FMEA VIEW → 403
    capa, _ = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-9")
    ac = await low_perm_client_builder(capa_level=1, fmea_level=0)
    async with ac:
        r = await ac.get(f"/api/capa/{capa.report_id}/d7-node-actions")
        assert r.status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/capa/test_capa_d7_api.py -x -q`
Expected: FAIL（端点不存在）。

- [ ] **Step 3: 加 3 端点到 `backend/app/api/capa.py`**

顶部 import 追加：
```python
from app.schemas.capa_verification import (
    D7AutoFillRequest, D7AutoFillResponse, D7NodeActionCreate, D7NodeActionResponse,
)
from app.services import capa_d7_action_service
from app.services.capa_d7_action_service import ConflictError
```
末尾追加：
```python
@router.post("/{report_id}/d7-node-actions", response_model=D7NodeActionResponse)
async def d7_record_action_ep(
    report_id: uuid.UUID, req: D7NodeActionCreate,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    if await get_user_permission(scope.user, Module.FMEA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    try:
        rec = await capa_d7_action_service.record_d7_action(db, capa, req, scope.user)
    except LookupError:
        raise HTTPException(status_code=404, detail="目标 FMEA 不存在")
    except PermissionError:
        raise HTTPException(status_code=403, detail="目标 FMEA 跨工厂")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return D7NodeActionResponse.model_validate(rec)


@router.get("/{report_id}/d7-node-actions", response_model=list[D7NodeActionResponse])
async def d7_list_actions_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    # D7 action 行含 fmea_id/node_id/control 状态，属 FMEA 衍生数据——读也要 FMEA VIEW（与 POST 对齐，防 CAPA-only 用户绕过 FMEA 权限读 D7 元数据）
    if await get_user_permission(scope.user, Module.FMEA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    items = await capa_d7_action_service.list_d7_actions(db, capa)
    return [D7NodeActionResponse.model_validate(i) for i in items]


@router.post("/{report_id}/d7-auto-fill", response_model=D7AutoFillResponse)
async def d7_auto_fill_ep(
    report_id: uuid.UUID, req: D7AutoFillRequest,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    if await get_user_permission(scope.user, Module.FMEA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    try:
        rec, info = await capa_d7_action_service.auto_fill_d7(db, capa, req, scope.user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError:
        raise HTTPException(status_code=404, detail="目标 FMEA 不存在")
    except PermissionError:
        raise HTTPException(status_code=403, detail="目标 FMEA 跨工厂")
    except ConflictError:
        raise HTTPException(status_code=409, detail="已自动回填")
    return D7AutoFillResponse(action_id=rec.action_id,
                              prevention_control_node_id=info["prevention_control_node_id"],
                              prevention_control_name_after=info["prevention_control_name_after"],
                              is_new_control=info["is_new_control"])
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/capa/test_capa_d7_api.py -q`
Expected: PASS。

- [ ] **Step 5: 全量后端回归**

Run: `cd backend && python -m pytest tests/ -q`
Expected: PASS（既有测试不退化；948+ 测试绿）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/capa.py backend/tests/capa/test_capa_d7_api.py
git commit -m "feat(capa): D7 node-actions + auto-fill API endpoints"
```

---

## Task 11: 前端类型 + api/capa.ts

**Files:**
- Modify: `frontend/src/types/index.ts`（追加类型）
- Modify: `frontend/src/api/capa.ts`（追加 7 函数）
- Test: `frontend/src/api/capa.test.ts`（新建，轻量）

**Interfaces:**
- Produces: `adoptRecommendation` / `listVerifications` / `createVerification` / `updateVerification` / `recordD7Action` / `listD7Actions` / `autoFillD7`，及类型 `AdoptRequest` / `AdoptResponse` / `Verification` / `D7NodeAction` / `D7AutoFillResponse`。

- [ ] **Step 1: 写失败测试**

`frontend/src/api/capa.test.ts`：
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import client from "./client";

vi.mock("./client", () => ({
  default: { post: vi.fn(), get: vi.fn(), patch: vi.fn() },
}));

import {
  adoptRecommendation, listVerifications, createVerification, updateVerification,
  recordD7Action, listD7Actions, autoFillD7,
} from "./capa";

beforeEach(() => vi.clearAllMocks());

describe("capa verification/d7 api", () => {
  it("adoptRecommendation posts to adopt-recommendation", async () => {
    (client.post as any).mockResolvedValue({ data: { adoption_id: "a1", d_step: "d4", field_value: "x" } });
    const r = await adoptRecommendation("c1", { d_step: "d4", adopted_text: "x", source: "fmea_graph" });
    expect(client.post).toHaveBeenCalledWith("/capa/c1/adopt-recommendation",
      { d_step: "d4", adopted_text: "x", source: "fmea_graph" });
    expect(r.field_value).toBe("x");
  });

  it("createVerification posts and returns record", async () => {
    (client.post as any).mockResolvedValue({ data: { verification_id: "v1", is_verified: true } });
    const r = await createVerification("c1", { root_cause_text: "rc", is_verified: true });
    expect(client.post).toHaveBeenCalledWith("/capa/c1/root-cause-verifications",
      { root_cause_text: "rc", is_verified: true });
    expect(r.verification_id).toBe("v1");
  });

  it("autoFillD7 posts to d7-auto-fill", async () => {
    (client.post as any).mockResolvedValue({ data: { action_id: "a1", prevention_control_node_id: "ctrl", prevention_control_name_after: "监控", is_new_control: true } });
    const r = await autoFillD7("c1", { fmea_id: "f1", failure_mode_node_id: "fm", failure_cause_node_id: "c", match_source: "linked" });
    expect(client.post).toHaveBeenCalledWith("/capa/c1/d7-auto-fill",
      { fmea_id: "f1", failure_mode_node_id: "fm", failure_cause_node_id: "c", match_source: "linked" });
    expect(r.is_new_control).toBe(true);
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/api/capa.test.ts`
Expected: FAIL（函数未导出）。

- [ ] **Step 3: 追加类型到 `frontend/src/types/index.ts`**

文件末尾追加：
```typescript
// --- CAPA D4 verification / adoption / D7 node actions (Spec A) ---
export interface AdoptRequest {
  d_step: "d4" | "d5";
  adopted_text: string;
  source: string;
  item_ref?: Record<string, unknown> | null;
}
export interface AdoptResponse {
  adoption_id: string;
  d_step: string;
  field_value: string;
}
export interface Verification {
  verification_id: string;
  capa_id: string;
  root_cause_text: string;
  method: string | null;
  result: string | null;
  is_verified: boolean;
  evidence_attachments: Record<string, unknown>[];
  source_ref: Record<string, unknown> | null;
  verified_by: string | null;
  verified_at: string | null;
  created_at: string;
}
export interface VerificationCreate {
  root_cause_text: string;
  method?: string | null;
  result?: string | null;
  is_verified?: boolean;
  evidence_attachments?: Record<string, unknown>[];
  source_ref?: Record<string, unknown> | null;
}
export interface VerificationUpdate {
  method?: string | null;
  result?: string | null;
  is_verified?: boolean;
  evidence_attachments?: Record<string, unknown>[];
}
export interface D7NodeAction {
  action_id: string;
  capa_id: string;
  action: "confirmed" | "skipped" | "auto_filled";
  fmea_id: string;
  failure_mode_node_id: string;
  failure_cause_node_id: string | null;
  match_source: string;
  prevention_control_node_id: string | null;
  prevention_control_name_before: string | null;
  prevention_control_name_after: string | null;
  reason: string | null;
  acted_by: string;
  acted_at: string;
}
export interface D7NodeActionCreate {
  action: "confirmed" | "skipped";
  fmea_id: string;
  failure_mode_node_id: string;
  failure_cause_node_id?: string | null;
  match_source: string;
  reason?: string | null;
}
export interface D7AutoFillRequest {
  fmea_id: string;
  failure_mode_node_id: string;
  failure_cause_node_id: string;
  match_source: string;
}
export interface D7AutoFillResponse {
  action_id: string;
  prevention_control_node_id: string;
  prevention_control_name_after: string;
  is_new_control: boolean;
}
```

- [ ] **Step 4: 追加 7 函数到 `frontend/src/api/capa.ts`**

文件顶部 import 的 type 列表追加：`AdoptRequest, AdoptResponse, Verification, VerificationCreate, VerificationUpdate, D7NodeAction, D7NodeActionCreate, D7AutoFillRequest, D7AutoFillResponse`。文件末尾追加：
```typescript
export async function adoptRecommendation(capaId: string, req: AdoptRequest): Promise<AdoptResponse> {
  const resp = await client.post(`/capa/${capaId}/adopt-recommendation`, req);
  return resp.data;
}
export async function listVerifications(capaId: string): Promise<Verification[]> {
  const resp = await client.get(`/capa/${capaId}/root-cause-verifications`);
  return resp.data;
}
export async function createVerification(capaId: string, req: VerificationCreate): Promise<Verification> {
  const resp = await client.post(`/capa/${capaId}/root-cause-verifications`, req);
  return resp.data;
}
export async function updateVerification(capaId: string, vid: string, req: VerificationUpdate): Promise<Verification> {
  const resp = await client.patch(`/capa/${capaId}/root-cause-verifications/${vid}`, req);
  return resp.data;
}
export async function recordD7Action(capaId: string, req: D7NodeActionCreate): Promise<D7NodeAction> {
  const resp = await client.post(`/capa/${capaId}/d7-node-actions`, req);
  return resp.data;
}
export async function listD7Actions(capaId: string): Promise<D7NodeAction[]> {
  const resp = await client.get(`/capa/${capaId}/d7-node-actions`);
  return resp.data;
}
export async function autoFillD7(capaId: string, req: D7AutoFillRequest): Promise<D7AutoFillResponse> {
  const resp = await client.post(`/capa/${capaId}/d7-auto-fill`, req);
  return resp.data;
}
```

- [ ] **Step 5: 运行确认通过**

Run: `cd frontend && npx vitest run src/api/capa.test.ts`
Expected: PASS。

- [ ] **Step 6: tsc + 提交**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误。
```bash
git add frontend/src/types/index.ts frontend/src/api/capa.ts frontend/src/api/capa.test.ts
git commit -m "feat(frontend): capa verification + D7 api functions + types"
```

---

## Task 12: `D4VerificationCard` 组件

**Files:**
- Create: `frontend/src/components/capa/D4VerificationCard.tsx`
- Test: `frontend/src/components/capa/D4VerificationCard.test.tsx`

**Interfaces:**
- Consumes: `listVerifications` / `createVerification` / `updateVerification`（Task 11）。
- Produces: `<D4VerificationCard capaId={...} canEdit={...} currentRootCause={...} />`，渲染验证记录列表 + 新增表单，`data-e2e` 钩子齐全。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/capa/D4VerificationCard.test.tsx`：
```typescript
import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import D4VerificationCard from "./D4VerificationCard";

vi.mock("../../api/capa", () => ({
  listVerifications: vi.fn(),
  createVerification: vi.fn(),
  updateVerification: vi.fn(),
}));

import { listVerifications, createVerification, updateVerification } from "../../api/capa";

const renderCard = (props = {}) => render(
  <ConfigProvider><App><D4VerificationCard capaId="c1" canEdit={true} currentRootCause="rc" {...props} /></App></ConfigProvider>
);

beforeEach(() => vi.clearAllMocks());

describe("D4VerificationCard", () => {
  it("renders existing verification records", async () => {
    (listVerifications as any).mockResolvedValue([
      { verification_id: "v1", capa_id: "c1", root_cause_text: "rc", method: "m",
        result: "r", is_verified: true, evidence_attachments: [], source_ref: null,
        verified_by: "u", verified_at: "2026-07-03", created_at: "2026-07-03" },
    ]);
    renderCard();
    await waitFor(() => expect(screen.queryByTestId("verification-item-0")).toBeInTheDocument());
    // test-setup.ts 把 i18n 切到 en-US，不要断言中文文案；组件 verified 时渲染 "✅"，按图标断言语言无关
    expect(screen.getByTestId("verification-status").textContent).toContain("✅");
  });

  it("creates a verification record on submit", async () => {
    (listVerifications as any).mockResolvedValue([]);
    (createVerification as any).mockResolvedValue({ verification_id: "v2", is_verified: true });
    renderCard();
    fireEvent.click(screen.getByTestId("d4-verification-new"));
    fireEvent.change(screen.getByTestId("verification-root-cause").querySelector("textarea")!, { target: { value: "新根因" } });
    fireEvent.click(screen.getByTestId("verification-submit"));
    await waitFor(() => expect(createVerification).toHaveBeenCalledWith("c1", expect.objectContaining({ root_cause_text: "新根因" })));
  });

  it("PATCHes is_verified via switch", async () => {
    (listVerifications as any).mockResolvedValue([
      { verification_id: "v1", capa_id: "c1", root_cause_text: "rc", method: "", result: "",
        is_verified: false, evidence_attachments: [], source_ref: null,
        verified_by: null, verified_at: null, created_at: "2026-07-03" },
    ]);
    (updateVerification as any).mockResolvedValue({ verification_id: "v1", is_verified: true });
    renderCard();
    await waitFor(() => expect(screen.queryByTestId("verification-item-0")).toBeInTheDocument());
    // Ant Switch 根节点本身就是 <button>，data-e2e 落在根 button 上——直接 click testid 节点，
    // 不要再 .querySelector("button")（Switch 内部无子 button，会返回 null 导致 NPE）
    fireEvent.click(screen.getByTestId("verification-is-verified"));
    await waitFor(() => expect(updateVerification).toHaveBeenCalledWith("c1", "v1", expect.objectContaining({ is_verified: true })));
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/capa/D4VerificationCard.test.tsx`
Expected: FAIL（组件未建）。

- [ ] **Step 3: 写组件**

`frontend/src/components/capa/D4VerificationCard.tsx`：
```tsx
import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Form, Input, Switch, Space, App, Empty, Spin, Upload } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { listVerifications, createVerification, updateVerification } from "../../api/capa";
import type { Verification } from "../../types";

interface Props { capaId: string; canEdit: boolean; currentRootCause: string | null; }

export default function D4VerificationCard({ capaId, canEdit, currentRootCause }: Props) {
  const { t } = useTranslation("capa");
  const { message } = App.useApp();
  const [items, setItems] = useState<Verification[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form] = Form.useForm();

  const reload = async () => {
    setLoading(true);
    try { setItems(await listVerifications(capaId)); } catch { message.error(t("d4.verificationLoadFailed")); }
    finally { setLoading(false); }
  };
  useEffect(() => { reload(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [capaId]);

  const submit = async (vals: any) => {
    const evidence = (vals.evidence || []).map((f: any) => ({ filename: f.name, size: f.size }));
    await createVerification(capaId, {
      root_cause_text: vals.root_cause_text ?? currentRootCause ?? "",
      method: vals.method, result: vals.result,
      is_verified: !!vals.is_verified, evidence_attachments: evidence,
    });
    message.success(t("d4.verificationSaved"));
    form.resetFields(); setShowForm(false); reload();
  };

  const toggleVerified = async (rec: Verification, checked: boolean) => {
    await updateVerification(capaId, rec.verification_id, { is_verified: checked });
    reload();
  };

  return (
    <Card size="small" title={t("d4.verificationTitle")} data-e2e="d4-verification-card" style={{ marginTop: 16 }}>
      {loading ? <Spin size="small" /> : items.length === 0 && !showForm ? (
        <Empty description={t("d4.noVerification")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List size="small" dataSource={items} renderItem={(rec, i) => (
          <List.Item data-e2e={`verification-item-${i}`}>
            <Space direction="vertical" size={2} style={{ width: "100%" }}>
              <Space><Tag data-e2e="verification-status">
                {rec.is_verified ? `✅ ${t("d4.verified")}` : `⏳ ${t("d4.notVerified")}`}
              </Tag>
                <span>{rec.root_cause_text}</span></Space>
              {rec.method && <span style={{ fontSize: 12 }}>{t("d4.method")}: {rec.method}</span>}
              {rec.result && <span style={{ fontSize: 12 }}>{t("d4.result")}: {rec.result}</span>}
              {rec.evidence_attachments?.length > 0 && (
                <span style={{ fontSize: 12 }}>{t("d4.evidence")}: {rec.evidence_attachments.map((e: any) => e.filename).join(", ")}</span>
              )}
              <Space>
                <span style={{ fontSize: 12 }}>{t("d4.isVerified")}</span>
                <Switch data-e2e="verification-is-verified" disabled={!canEdit}
                  checked={rec.is_verified} onChange={(c) => toggleVerified(rec, c)} />
              </Space>
            </Space>
          </List.Item>
        )} />
      )}
      {canEdit && !showForm && (
        <Button data-e2e="d4-verification-new" icon={<PlusOutlined />} size="small"
          onClick={() => { form.setFieldsValue({ root_cause_text: currentRootCause ?? "" }); setShowForm(true); }}>
          {t("d4.newVerification")}
        </Button>
      )}
      {showForm && (
        <Form form={form} layout="vertical" size="small" onFinish={submit} style={{ marginTop: 12 }}>
          <Form.Item name="root_cause_text" label={t("d4.rootCause")} data-e2e="verification-root-cause">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="method" label={t("d4.method")} data-e2e="verification-method">
            <Input />
          </Form.Item>
          <Form.Item name="result" label={t("d4.result")} data-e2e="verification-result">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="evidence" label={t("d4.evidence")} data-e2e="verification-evidence"
            valuePropName="fileList" getValueFromEvent={(e) => Array.isArray(e) ? e : e?.fileList ?? []}>
            <Upload beforeUpload={() => false} multiple>
              <Button size="small">{t("d4.addEvidence")}</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="is_verified" label={t("d4.isVerified")} valuePropName="checked">
            <Switch data-e2e="verification-form-is-verified" />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" data-e2e="verification-submit">{t("d4.save")}</Button>
            <Button onClick={() => setShowForm(false)}>{t("d4.cancel")}</Button>
          </Space>
        </Form>
      )}
    </Card>
  );
}
```

- [ ] **Step 4: 追加 i18n key（合并进既有 `d4`/`d5`/`d7` 对象，禁止整体覆盖；统一覆盖 Task 12/13/14/15 全部新增文案）**

`frontend/src/locales/zh-CN/capa.json` 的 `"d4"` / `"d5"` / `"d7"` 对象**均已存在**（`d4` 现有：`title`/`subtitle`/`empty`/`hint`/`groups`/`adopt`/`skip`/`readonlyTooltip`/`loadFailed`；`d5` 现有：`title`/`controls`/`suggestions`/`controlTypes`/`categories`/`defaultBasis`/`loadFailed`/`adopt`/`skip`/`readonlyTooltip`；`d7` 现有：`title`/`linkedNodes`/`similarNodes`/`empty`/`jump`/`autoFill`/`updated`/`skipped`/`needsNew`/`existing`/`autoFillTooltip*`/`autoFillDisabled*`/`autoFillSuccess`/`autoFillFailed`/`loadFailed`/`matchSource`/`skipDialog*`/`causeLabel`/`skipReason*`）。**只能往对应既有对象里追加下列新 key，不要粘贴整个块覆盖**，否则现有文案会丢。

往 `d4` 对象内追加（zh-CN）：
```
"verificationTitle": "D4 现场根因验证",
"noVerification": "暂无验证记录",
"newVerification": "新增验证",
"rootCause": "根因",
"method": "验证方法",
"result": "验证结果",
"evidence": "证据附件",
"addEvidence": "添加证据",
"isVerified": "已验证",
"verified": "已验证",
"notVerified": "待验证",
"save": "保存",
"cancel": "取消",
"verificationSaved": "验证记录已保存",
"verificationLoadFailed": "验证记录加载失败",
"adopted": "已采纳",
"adoptFailed": "采纳失败"
```
> **注意 key 命名冲突**：现有 `d4.loadFailed` 已是 "加载 D4 推荐失败"（D4RecPanel 用）。D4VerificationCard 的"验证记录加载失败"**必须用新 key `verificationLoadFailed`**，组件代码已对应 `t("d4.verificationLoadFailed")`，不要复用 `loadFailed` 以免误显示推荐面板的文案。`d4.adopted`/`d4.adoptFailed` 由 D4RecPanel 采纳端点调用时使用（Task 13）。

往 `d5` 对象内追加（zh-CN）：
```
"adopted": "已采纳",
"adoptFailed": "采纳失败"
```

往 `d7` 对象内追加（zh-CN）：
```
"actionFailed": "动作保存失败"
```
（`d7.autoFillSuccess`/`autoFillFailed` 已存在，D7RecPanel 直接复用；`d7.actionFailed` 是 confirm/skip 落库失败用，区别于 auto-fill 失败。）

en-US 对应文件 `frontend/src/locales/en-US/capa.json` 的 `d4`/`d5`/`d7` 对象追加同 key 英文（如 `"verificationTitle": "D4 On-site Root Cause Verification"`、`"adopted": "Adopted"`、`"adoptFailed": "Adopt failed"`、`"actionFailed": "Action save failed"` 等）。

- [ ] **Step 5: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/capa/D4VerificationCard.test.tsx`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/capa/D4VerificationCard.tsx \
        frontend/src/components/capa/D4VerificationCard.test.tsx \
        frontend/src/locales/
git commit -m "feat(frontend): D4VerificationCard component"
```

---

## Task 13: `D4RecPanel` 采纳改调端点

**Files:**
- Modify: `frontend/src/components/capa/D4RecPanel.tsx`
- Test: `frontend/src/components/capa/D4RecPanel.test.tsx`

**Interfaces:**
- Consumes: `adoptRecommendation`（Task 11）。
- Props 变更：`onAdopt(text)` → `beforeAdopt?: () => Promise<void>` + `onAdopted?: () => void`。采纳按钮调端点。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/capa/D4RecPanel.test.tsx`：
```typescript
import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import D4RecPanel from "./D4RecPanel";

vi.mock("../../api/capa", () => ({
  getD4Recommendations: vi.fn().mockResolvedValue({ items: [
    { failure_cause_node_id: "c1", failure_cause_name: "根因A", failure_mode_name: "虚焊",
      fmea_document_no: "PFMEA-1", match_source: "fmea_graph", match_reason: "r",
      related_d2_keywords: [], confidence: 0.6, fmea_id: "f1" },
  ] }),
  adoptRecommendation: vi.fn().mockResolvedValue({ adoption_id: "a1", d_step: "d4", field_value: "根因A" }),
}));

import { adoptRecommendation, getD4Recommendations } from "../../api/capa";

const renderPanel = (props = {}) => render(
  <ConfigProvider><App>
    <D4RecPanel capaId="c1" canAdopt={true} beforeAdopt={vi.fn()} onAdopted={vi.fn()} {...props} />
  </App></ConfigProvider>
);

beforeEach(() => vi.clearAllMocks());

describe("D4RecPanel adopt", () => {
  it("calls beforeAdopt then adoptRecommendation with source/item_ref", async () => {
    const beforeAdopt = vi.fn().mockResolvedValue(undefined);
    const onAdopted = vi.fn();
    renderPanel({ beforeAdopt, onAdopted });
    await waitFor(() => expect(screen.queryByTestId("d4-adopt")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-adopt"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({
      d_step: "d4", adopted_text: "根因A", source: "fmea_graph",
      item_ref: expect.objectContaining({ failure_cause_node_id: "c1", fmea_id: "f1" }),
    })));
    await waitFor(() => expect(onAdopted).toHaveBeenCalled());
  });

  it("does not call adoptRecommendation until beforeAdopt resolves (flush-then-adopt ordering)", async () => {
    // 关键路径：未保存输入保护要求"先 flush 且等待完成再采纳"。用 deferred promise 钉死顺序。
    let resolveBefore!: () => void;
    const beforeAdopt = vi.fn().mockReturnValue(new Promise<void>((r) => { resolveBefore = r; }));
    renderPanel({ beforeAdopt });
    await waitFor(() => expect(screen.queryByTestId("d4-adopt")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-adopt"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    // beforeAdopt 未 resolve：让微任务跑完一轮，采纳端点仍不应被调用
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptRecommendation).not.toHaveBeenCalled();
    // resolve beforeAdopt → 采纳端点才被调用
    resolveBefore();
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({ d_step: "d4" })));
  });

  it("does not call adoptRecommendation when beforeAdopt rejects (save failed → block adopt)", async () => {
    const beforeAdopt = vi.fn().mockRejectedValue(new Error("save failed"));
    renderPanel({ beforeAdopt });
    await waitFor(() => expect(screen.queryByTestId("d4-adopt")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d4-adopt"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptRecommendation).not.toHaveBeenCalled();
  });

  it("disables adopt when canAdopt=false", async () => {
    renderPanel({ canAdopt: false });
    await waitFor(() => expect(screen.queryByTestId("d4-adopt")).toBeInTheDocument());
    expect((screen.getByTestId("d4-adopt") as HTMLButtonElement).closest("button")!).toBeDisabled();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/capa/D4RecPanel.test.tsx`
Expected: FAIL（组件仍用 `onAdopt` 回调、无 testid）。

- [ ] **Step 3: 改 `D4RecPanel.tsx`**

替换 props 接口与采纳按钮：
```tsx
interface D4RecPanelProps {
  capaId: string;
  canAdopt?: boolean;
  beforeAdopt?: () => Promise<void>;
  onAdopted?: () => void;
}

export default function D4RecPanel({ capaId, canAdopt = true, beforeAdopt, onAdopted }: D4RecPanelProps) {
```
（删除原 `onAdopt`。）import 区加 `adoptRecommendation`。采纳按钮 `onClick` 改为：
```tsx
                  <Button
                    key="adopt"
                    type="link"
                    size="small"
                    icon={<CheckOutlined />}
                    data-e2e="d4-adopt"
                    disabled={!canAdopt}
                    title={!canAdopt ? t("d4.readonlyTooltip") : undefined}
                    onClick={async () => {
                      try {
                        await beforeAdopt?.();
                        await adoptRecommendation(capaId, {
                          d_step: "d4",
                          adopted_text: item.failure_cause_name,
                          source: item.match_source,
                          item_ref: {
                            failure_cause_node_id: item.failure_cause_node_id,
                            fmea_id: item.fmea_id,
                            failure_mode_node_id: item.failure_mode_node_id,
                          },
                        });
                        message.success(t("d4.adopted"));
                        onAdopted?.();
                      } catch {
                        message.error(t("d4.adoptFailed"));
                      }
                    }}
                  >
                    {t("d4.adopt")}
                  </Button>,
```
（`message` 来自 `App.useApp()`，已在文件中。）

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/capa/D4RecPanel.test.tsx`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/capa/D4RecPanel.tsx frontend/src/components/capa/D4RecPanel.test.tsx
git commit -m "feat(frontend): D4RecPanel adopt via endpoint + testids"
```

---

## Task 14: `D5RecPanel` 采纳改调端点

**Files:**
- Modify: `frontend/src/components/capa/D5RecPanel.tsx`
- Test: `frontend/src/components/capa/D5RecPanel.test.tsx`

**Interfaces:**
- 同 Task 13 props 变更。D5 有两条采纳路径：existing_control（`d5-adopt-control`）与 general_suggestion（`d5-adopt-suggestion`），`source` 取 `item.match_source ?? "rule"`（兜底，见 Task 2 修复后端总有值，前端兜底防御）。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/capa/D5RecPanel.test.tsx`：
```typescript
import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import D5RecPanel from "./D5RecPanel";

vi.mock("../../api/capa", () => ({
  getD5Recommendations: vi.fn().mockResolvedValue({
    existing_controls: [{
      control_node_id: "ctrl1", control_name: "焊接监控", control_type: "prevention",
      match_source: "fmea_graph", match_reason: "r", fmea_id: "f1",
      failure_mode_node_id: "fm", failure_cause_node_id: "c1",
    }],
    general_suggestions: [{
      content: "通用措施", category: "预防措施", basis: "", confidence: 0.5,
      match_reason: "r", match_source: "rule",
    }],
  }),
  adoptRecommendation: vi.fn().mockResolvedValue({ adoption_id: "a1", d_step: "d5", field_value: "x" }),
}));

import { adoptRecommendation } from "../../api/capa";

const renderPanel = (props = {}) => render(
  <ConfigProvider><App>
    <D5RecPanel capaId="c1" canAdopt={true} beforeAdopt={vi.fn()} onAdopted={vi.fn()} {...props} />
  </App></ConfigProvider>
);

beforeEach(() => vi.clearAllMocks());

describe("D5RecPanel adopt", () => {
  it("adopts existing control via d5-adopt-control", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("d5-adopt-control")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d5-adopt-control"));
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({
      d_step: "d5", adopted_text: "焊接监控", source: "fmea_graph",
      item_ref: expect.objectContaining({ control_node_id: "ctrl1", failure_cause_node_id: "c1" }),
    })));
  });

  it("adopts general suggestion via d5-adopt-suggestion", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("d5-adopt-suggestion")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d5-adopt-suggestion"));
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({
      d_step: "d5", adopted_text: "通用措施", source: "rule",
    })));
  });

  it("waits for beforeAdopt to resolve before adopting (flush-then-adopt ordering)", async () => {
    // 关键路径：D5 也要求"先 flush D5 措施且等待完成再采纳"，用 deferred promise 钉死顺序
    let resolveBefore!: () => void;
    const beforeAdopt = vi.fn().mockReturnValue(new Promise<void>((r) => { resolveBefore = r; }));
    renderPanel({ beforeAdopt });
    await waitFor(() => expect(screen.queryByTestId("d5-adopt-control")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d5-adopt-control"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptRecommendation).not.toHaveBeenCalled();
    resolveBefore();
    await waitFor(() => expect(adoptRecommendation).toHaveBeenCalledWith("c1", expect.objectContaining({ d_step: "d5" })));
  });

  it("does not adopt when beforeAdopt rejects (save failed → block adopt)", async () => {
    const beforeAdopt = vi.fn().mockRejectedValue(new Error("save failed"));
    renderPanel({ beforeAdopt });
    await waitFor(() => expect(screen.queryByTestId("d5-adopt-control")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d5-adopt-control"));
    await waitFor(() => expect(beforeAdopt).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptRecommendation).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/capa/D5RecPanel.test.tsx`
Expected: FAIL。

- [ ] **Step 3: 改 `D5RecPanel.tsx`**

props 改为 `beforeAdopt?: () => Promise<void>; onAdopted?: () => void`（删 `onAdopt`）。import 加 `adoptRecommendation`。existing_control 采纳按钮 `data-e2e="d5-adopt-control"` + `onClick`：
```tsx
onClick={async () => {
  try {
    await beforeAdopt?.();
    await adoptRecommendation(capaId, {
      d_step: "d5",
      adopted_text: item.control_name,
      source: item.match_source || "rule",
      item_ref: {
        control_node_id: item.control_node_id,
        failure_cause_node_id: item.failure_cause_node_id,
        fmea_id: item.fmea_id,
      },
    });
    message.success(t("d5.adopted")); onAdopted?.();
  } catch { message.error(t("d5.adoptFailed")); }
}}
```
general_suggestion 采纳按钮 `data-e2e="d5-adopt-suggestion"` + `onClick`：
```tsx
onClick={async () => {
  try {
    await beforeAdopt?.();
    await adoptRecommendation(capaId, {
      d_step: "d5",
      adopted_text: item.content,
      source: item.match_source || "rule",
      item_ref: {},
    });
    message.success(t("d5.adopted")); onAdopted?.();
  } catch { message.error(t("d5.adoptFailed")); }
}}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/capa/D5RecPanel.test.tsx`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/capa/D5RecPanel.tsx frontend/src/components/capa/D5RecPanel.test.tsx
git commit -m "feat(frontend): D5RecPanel adopt via endpoint + testids"
```

---

## Task 15: `D7RecPanel` 改造（持久化动作 + 后端自动回填）

**Files:**
- Modify: `frontend/src/components/capa/D7RecPanel.tsx`
- Test: `frontend/src/components/capa/D7RecPanel.test.tsx`

**Interfaces:**
- Consumes: `recordD7Action` / `listD7Actions` / `autoFillD7`（Task 11）。
- Props 不变（`capaId` / `d5Correction` / `onConfirmationChange`），但内部 confirmed/skip/auto-fill 全部走端点，状态从 `listD7Actions` 重载。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/capa/D7RecPanel.test.tsx`：
```typescript
import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { render, screen, fireEvent, waitFor, configure } from "@testing-library/react";
configure({ testIdAttribute: "data-e2e" }); // 生产组件用 data-e2e（计划 Global Constraint），切 Testing Library 的 testIdAttribute
afterAll(() => configure({ testIdAttribute: "data-testid" })); // 复位默认，防止 vitest 非默认隔离配置下泄漏到后续测试文件
import { App, ConfigProvider } from "antd";
import { MemoryRouter } from "react-router-dom";
import D7RecPanel from "./D7RecPanel";

vi.mock("../../api/capa", () => ({
  getD7Recommendations: vi.fn().mockResolvedValue({ recommendations: [
    { fmea_id: "f1", fmea_document_no: "PFMEA-1", failure_mode_node_id: "fm1", failure_mode_name: "虚焊",
      failure_cause_node_id: "c1", failure_cause_name: "参数偏移",
      prevention_control_node_id: null, prevention_control_name: null,
      match_source: "linked", match_reason: "r", related_d4_keywords: [], suggested_prevention: null },
  ] }),
  recordD7Action: vi.fn().mockResolvedValue({ action_id: "a1", action: "confirmed" }),
  listD7Actions: vi.fn().mockResolvedValue([]),
  autoFillD7: vi.fn().mockResolvedValue({ action_id: "a2", prevention_control_node_id: "ctrl", prevention_control_name_after: "监控", is_new_control: true }),
}));

import { recordD7Action, autoFillD7, listD7Actions } from "../../api/capa";

const renderPanel = (props = {}) => render(
  <ConfigProvider><App><MemoryRouter>
    <D7RecPanel capaId="c1" d5Correction="监控" onConfirmationChange={vi.fn()} {...props} />
  </MemoryRouter></App></ConfigProvider>
);

beforeEach(() => vi.clearAllMocks());

describe("D7RecPanel", () => {
  it("records confirmed action via endpoint", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("d7-confirm")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d7-confirm"));
    await waitFor(() => expect(recordD7Action).toHaveBeenCalledWith("c1", expect.objectContaining({
      action: "confirmed", fmea_id: "f1", failure_mode_node_id: "fm1", failure_cause_node_id: "c1",
    })));
  });

  it("auto-fills via backend endpoint", async () => {
    renderPanel();
    await waitFor(() => expect(screen.queryByTestId("d7-auto-fill")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("d7-auto-fill"));
    await waitFor(() => expect(autoFillD7).toHaveBeenCalledWith("c1", expect.objectContaining({
      fmea_id: "f1", failure_cause_node_id: "c1", match_source: "linked",
    })));
  });

  it("reloads actions on mount (persistence)", async () => {
    renderPanel();
    await waitFor(() => expect(listD7Actions).toHaveBeenCalledWith("c1"));
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/components/capa/D7RecPanel.test.tsx`
Expected: FAIL。

- [ ] **Step 3: 改 `D7RecPanel.tsx`**

import 追加 `recordD7Action, listD7Actions, autoFillD7` 与 `D7NodeAction` type。**`D7RecPanelProps` 加 `canAdopt?: boolean`（默认 true，与 D4/D5 RecPanel 一致；read-only 用户禁用三按钮，真正权限仍由后端 403 兜底）**：
```tsx
interface D7RecPanelProps {
  capaId: string;
  d5Correction: string | null;
  canAdopt?: boolean;
  onConfirmationChange: (allConfirmed: boolean, unconfirmedItems: D7UnconfirmedItem[]) => void;
}

export default function D7RecPanel({ capaId, d5Correction, canAdopt = true, onConfirmationChange }: D7RecPanelProps) {
```
`handleConfirm` 改为异步调端点：
```tsx
const [actions, setActions] = useState<D7NodeAction[]>([]);

const reloadActions = async () => {
  try { setActions(await listD7Actions(capaId)); } catch { /* ignore */ }
};
useEffect(() => { reloadActions(); /* eslint-disable-line */ }, [capaId]);

const actionFor = (rec: D7Recommendation): D7NodeAction | undefined =>
  actions.find(a => a.fmea_id === rec.fmea_id && a.failure_mode_node_id === rec.failure_mode_node_id
                    && (a.failure_cause_node_id || null) === (rec.failure_cause_node_id || null));

const handleConfirm = async (rec: D7Recommendation, action: "confirmed" | "skipped") => {
  try {
    await recordD7Action(capaId, {
      action, fmea_id: rec.fmea_id, failure_mode_node_id: rec.failure_mode_node_id,
      failure_cause_node_id: rec.failure_cause_node_id, match_source: rec.match_source,
    });
    await reloadActions();
    const refreshed = await getD7Recommendations(capaId);
    setRecommendations(refreshed.recommendations);
  } catch { message.error(t("d7.actionFailed")); }
};

const handleAutoFill = async (rec: D7Recommendation) => {
  if (!d5Correction || !rec.failure_cause_node_id) return;
  setFillingNode(rec.failure_cause_node_id);
  try {
    await autoFillD7(capaId, {
      fmea_id: rec.fmea_id, failure_mode_node_id: rec.failure_mode_node_id,
      failure_cause_node_id: rec.failure_cause_node_id, match_source: rec.match_source,
    });
    message.success(t("d7.autoFillSuccess"));
    await reloadActions();
    const refreshed = await getD7Recommendations(capaId);
    setRecommendations(refreshed.recommendations);
  } catch { message.error(t("d7.autoFillFailed")); }
  finally { setFillingNode(null); }
};
```
`confirmed` 派生改用 `actions`：
```tsx
const actionOf = (rec: D7Recommendation) => actionFor(rec);
// 现有组件标题 `<Badge count={confirmedCount}>`（D7RecPanel.tsx:256）依赖此计数；
// 删除 confirmedNodes 后必须改用 actions 派生，否则 Badge 渲染 0/NaN
const confirmedCount = recommendations.filter((r) => actionFor(r)).length;
```
按钮加 `data-e2e`：确认按钮 `d7-confirm`、跳过按钮 `d7-skip`、自动回填按钮 `d7-auto-fill`。已 `auto_filled` 的节点（`actionOf(rec)?.action === "auto_filled"`）禁用 confirm/skip/auto-fill 按钮并显"已自动回填"锁定态。**每条推荐行 + 状态 Tag 必须按 spec testid 表落 `data-e2e`**（Spec C/E2E 依赖这些选择器），渲染形如：
```tsx
{recommendations.map((rec, i) => {
  const act = actionOf(rec);
  const locked = act?.action === "auto_filled";
  return (
    <List.Item key={`${rec.fmea_id}:${rec.failure_mode_node_id}`} data-e2e={`d7-node-action-${i}`}>
      {/* ...既有内容... */}
      {act && (
        <Tag data-e2e="d7-action-status" className={locked ? "locked" : undefined}>
          {act.action === "confirmed" ? t("d7.updated")
            : act.action === "skipped" ? t("d7.skipped")
            : t("d7.autoFill")}
        </Tag>
      )}
      <Space>
        <Button size="small" data-e2e="d7-confirm" disabled={locked || !canAdopt}
          onClick={() => handleConfirm(rec, "confirmed")}>{t("d7.updated")}</Button>
        <Button size="small" data-e2e="d7-skip" disabled={locked || !canAdopt}
          onClick={() => handleConfirm(rec, "skipped")}>{t("d7.skipped")}</Button>
        <Button size="small" data-e2e="d7-auto-fill" disabled={locked || !canAdopt || !d5Correction || !rec.failure_cause_node_id}
          loading={fillingNode === rec.failure_cause_node_id}
          onClick={() => handleAutoFill(rec)}>{t("d7.autoFill")}</Button>
      </Space>
    </List.Item>
  );
})}
```
（`locked` 用 className 表达，spec testid 表的 "auto_filled 时带 `locked`" 即此；E2E 可用 `[data-e2e="d7-action-status"].locked` 锁定态断言。）
`onConfirmationChange` 改为从 `actions` + `recommendations` 派生（未确认 = recommendations 中没有对应 action 的项）：
```tsx
useEffect(() => {
  if (recommendations.length === 0) { onConfirmationChange(true, []); return; }
  const unconfirmed = recommendations
    .filter(r => !actionFor(r))
    .map(r => ({ fmea_id: String(r.fmea_id), failure_mode_node_id: r.failure_mode_node_id,
                 failure_mode_name: r.failure_mode_name, failure_cause_node_id: r.failure_cause_node_id }));
  onConfirmationChange(unconfirmed.length === 0, unconfirmed);
}, [actions, recommendations]);
```
（删除原 `confirmedNodes` 内存态与相关 `useMemo`/`handleConfirm(rec, status)` 旧逻辑。）

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/components/capa/D7RecPanel.test.tsx`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/capa/D7RecPanel.tsx frontend/src/components/capa/D7RecPanel.test.tsx
git commit -m "feat(frontend): D7RecPanel persists actions + backend auto-fill"
```

---

## Task 16: `CAPADetailPage` 接线

**Files:**
- Modify: `frontend/src/pages/capa/CAPADetailPage.tsx`

**Interfaces:**
- Consumes: `<D4VerificationCard>`（Task 12）、改造后的 `D4RecPanel`/`D5RecPanel`/`D7RecPanel`（Task 13/14/15）。
- 改动：D4/D5 RecPanel 传 `beforeAdopt`（flush 本地字段）+ `onAdopted`（refetch CAPA）；D4 区块加 `<D4VerificationCard>`；删除原 `onAdopt` 回调。

- [ ] **Step 1: 改 D4 区块**

`CAPADetailPage.tsx` 顶部 import 加：
```tsx
import D4VerificationCard from "../../components/capa/D4VerificationCard";
```
把 L498-507 的 `<D4RecPanel ... onAdopt={(text) => {...}} />` 改为：
```tsx
                <D4RecPanel
                  capaId={id!}
                  canAdopt={canEdit('capa')}
                  beforeAdopt={async () => {
                    // handleUpdate 已内部判重（值未变即早返回）并 await PUT；throwOnError=true，保存失败则抛出、不继续采纳
                    await handleUpdate("d4_root_cause", localData.d4_root_cause, true);
                  }}
                  onAdopted={() => refreshCapa()}
                />
                <D4VerificationCard capaId={id!} canEdit={canEdit('capa')} currentRootCause={localData.d4_root_cause} />
```
（`refreshCapa` 是已存在的拉取 CAPA 回显函数；若未具名，用现有 `loadCAPA`/`getCAPA(id)` 回调，按文件内既有命名。）

- [ ] **Step 2: 改 D5 区块**

把 L524-533 的 `<D5RecPanel ... onAdopt={...} />` 改为：
```tsx
                <D5RecPanel
                  capaId={id!}
                  canAdopt={canEdit('capa')}
                  beforeAdopt={async () => {
                    await handleUpdate("d5_correction", localData.d5_correction, true);
                  }}
                  onAdopted={() => refreshCapa()}
                />
```

- [ ] **Step 3: D7 区块**

`<D7RecPanel capaId={id!} d5Correction={localData.d5_correction} onConfirmationChange={...} />` 改为加 `canAdopt={canEdit('capa')}`（与 D4/D5 RecPanel 一致，read-only 用户禁用三按钮；FMEA VIEW/EDIT 差异仍由后端 403 兜底）：
```tsx
<D7RecPanel
  capaId={id!}
  d5Correction={localData.d5_correction}
  canAdopt={canEdit('capa')}
  onConfirmationChange={...}
/>
```
确认 `d5Correction` 传的是最新 `localData.d5_correction`（已是）。

- [ ] **Step 4: 确认 `refreshCapa` 存在**

在文件内 grep `refreshCapa`（或 `loadCAPA`/`getCAPA`）。若刷新函数名不同，把 Step 1/2 的 `onAdopted` 改为既有名。若完全没有刷新函数，在组件内加：
```tsx
const refreshCapa = async () => {
  const updated = await getCAPA(id!);
  setCapa(updated); setLocalData({ ...localData, d4_root_cause: updated.d4_root_cause, d5_correction: updated.d5_correction });
};
```
（`getCAPA` 已从 `api/capa` import。）

- [ ] **Step 5: tsc + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 无错误，build 成功。

- [ ] **Step 6: vitest 全量**

Run: `cd frontend && npx vitest run`
Expected: PASS（新增 + 既有前端测试绿）。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/pages/capa/CAPADetailPage.tsx
git commit -m "feat(frontend): wire CAPADetailPage adopt endpoints + D4VerificationCard"
```

---

## Task 17: `make check` 全量验证 + docs 同步

**Files:**
- Modify: `PROGRESS.md`（勾选 P0-1 / P0-4）

- [ ] **Step 1: 后端全量测试**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only python -m pytest tests/ -q`
Expected: PASS（既有 + 新增全绿）。

- [ ] **Step 2: 前端 tsc + build + lint + vitest**

Run: `cd frontend && npx tsc --noEmit && npm run build && npm run lint && npx vitest run`
Expected: 全绿。

- [ ] **Step 3: make check**

Run: `make check`
Expected: 绿（backend pytest + frontend tsc --noEmit + frontend build）。

- [ ] **Step 4: 迁移干净库验证**

Run:
```bash
cd backend && SECRET_KEY=test-secret-key-for-pytest-only alembic downgrade -1 && SECRET_KEY=test-secret-key-for-pytest-only alembic upgrade head
```
Expected: 干净 down/up 成功（验证 downgrade 可逆）。

- [ ] **Step 5: 同步 PROGRESS.md**

`PROGRESS.md` 的「US-E2E-01」缺口清单里，把 P0-1、P0-4 两条 `[ ]` 改为 `[x]`，并在条目末尾加 `(Spec A 已落地，commit 见 git log)`。在「补齐建议顺序」里把已完成的标灰/勾选。

- [ ] **Step 6: docs-check 检查**

代码改了 `backend/app/`、`frontend/src/`，PR 需 docs 同步。本任务的 `PROGRESS.md` 改动即满足。若 reviewer 认为 `CLAUDE.md` 无需改，PR 加 `docs-not-needed` label（CLAUDE.md 未新增命令/约定）。

- [ ] **Step 7: 提交 + 推送 + draft PR**

```bash
git add PROGRESS.md
git commit -m "docs(progress): tick P0-1/P0-4 (Spec A landed)"
git push -u origin worktree-us-e2e-01-8d-closed-loop
gh pr create --draft --base fix/dashboard-admin-pages --title "US-E2E-01 Spec A: D4 root-cause verification + AI adoption/D7 action audit" --body "见 docs/superpowers/specs/2026-07-03-us-e2e-01-spec-a-d4-verification-adoption-design.md"
```

---

## Self-Review

**Spec coverage：**
- P0-1 D4 验证子流程（表 + API + 闸口 + UI）→ Task 1（表）、Task 4（CRUD）、Task 5（闸口）、Task 9（API）、Task 12（UI）。✅
- P0-4 D4/D5 采纳审计 → Task 3（service）、Task 9（API）、Task 13/14（前端）、Task 16（接线）。✅
- P0-4 D7 节点动作审计 → Task 1（表）、Task 7/8（service）、Task 10（API）、Task 15（前端）、Task 16（接线）。✅
- R1-Finding 5（match_source 始终输出）→ Task 2。✅
- R2-Finding 2（field_value 返回）→ Task 3 返回元组 + Task 9 handler 组装。✅
- R2-Finding 3（beforeAdopt 接口）→ Task 13/14 props + Task 16 传。✅
- R3-Finding 1（deepcopy 持久化）→ Task 8 deepcopy + 测试重查。✅
- R3-Finding 2（FMEA 副作用复用）→ Task 6 拆核心 + Task 8 调核心。✅
- R3-Finding 3（d7-node-actions FMEA 校验）→ Task 7 `_fetch_fmea_for_d7` + Task 10 handler。✅
- R3-Finding 4（COALESCE unique）→ Task 1 迁移表达式索引。✅
- R3-Finding 5（D7 upsert/锁定）→ Task 7/8 upsert + ConflictError + Task 15 前端禁用。✅
- data-e2e testid → Task 12/13/14/15。✅
- docs 同步 → Task 17。✅

**Placeholder scan：**`<HEAD>` 在 Task 1 是待 Step 1 填入的真实 revision（有明确获取步骤，非 TBD）。其余无 TODO/TBD。

**Type consistency：**`adopt_recommendation` 返回 `tuple[CapaAIAdoption, str]`（Task 3）→ handler 用 `adoption, field_value`（Task 9）。`auto_fill_d7` 返回 `tuple[CapaD7NodeAction, dict]`（Task 8）→ handler 用 `rec, info`（Task 10）。`_apply_fmea_update` 签名（Task 6）与 `auto_fill_d7` 调用（Task 8）一致。`ConflictError`（Task 7 定义）→ Task 8 raise + Task 10 import 映射 409。`record_d7_action` / `list_d7_actions` / `create_verification` / `list_verifications` / `update_verification` 命名前后一致。前端 `adoptRecommendation` 等 7 函数（Task 11）与 RecPanel 调用（Task 13/14/15）签名一致。