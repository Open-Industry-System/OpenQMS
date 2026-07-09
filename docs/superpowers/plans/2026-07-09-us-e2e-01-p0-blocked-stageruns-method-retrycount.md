# US-E2E-01 P0 收尾 Implementation Plan（切片 A + B 合并）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 US-E2E-01 子故事 01.2 / 01.3 的 P0 硬 gap——01.2 LLM 未配置严格 BLOCKED + stage_runs 持久化；01.3 method 枚举 + conclusion 驱动 retry_count 回退计数器。

**Architecture:** 切片 A 在 orchestrator 顶部判 BLOCKED（pc is None）+ 新增 CAPA 专属缓存写入路径（write-only，report_id 键）；切片 B 用 conclusion 枚举（pending/passed/failed）替代 is_verified 请求语义，retry_count 仅 conclusion→failed 跃迁递增（双行锁去重），warning 在 API 层算。两切片无代码依赖。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + Alembic | React 18 + TypeScript 5.6 + Ant Design 5 | pytest + vitest + Playwright。

**Spec:** `docs/superpowers/specs/2026-07-09-us-e2e-01-p0-blocked-stageruns-method-retrycount-design.md`（三轮评审通过，commit `f329dfee`）。每个任务的实现须对照 spec 对应章节。

## Global Constraints

- 测试用本机 backend venv：`cd backend && SECRET_KEY=test-secret-key pytest ...`（CLAUDE.md 记录的 worktree/backend 测试约定）。
- `make check` = backend pytest + frontend `tsc --noEmit` + vite build，全绿才算完成。
- 前端 i18n 必须同步 zh-CN + en-US（CLAUDE.md 约定）。
- 每个迁移须可 upgrade/downgrade 干净；CHECK 约束须同时进 Alembic + 模型 `__table_args__`（Base.metadata.create_all 测试路径）。
- `factory_id` 行级隔离贯穿（既有约定）。
- Pydantic v2：`model_config = ConfigDict(extra='forbid')` 防旧字段静默忽略。
- 不引入 PG enum（用 String + Literal + CHECK）。
- 生产门控：`/api/e2e/*` 只在非 production 模式载入（既有，本计划不动）。

---

## File Structure

**切片 A 修改/新增：**
- `backend/app/services/recommendation_types.py` — StageRun.status 加 "blocked"；RecommendationResult 加 blocked 字段
- `backend/app/services/recommendation_orchestrator.py` — run() 顶部 BLOCKED 判定 + _blocked_stages()
- `backend/app/services/hybrid_recommendation_pipeline.py` — recommend() 透传 blocked + 新增 _cache_capa_result + _serialize_capa_suggestions
- `backend/app/models/recommendation_cache.py` — 加 stage_runs JSONB 列
- `backend/alembic/versions/<new>_capa_cache_stage_runs.py` — 迁移
- `backend/app/api/capa.py` — D4/D5 endpoint 422 blocked；advance endpoint response_model + API 层 warning
- `backend/app/schemas/capa.py` — 新增 CAPAAdvanceResponse
- `backend/tests/...` — orchestrator/pipeline/cache/api 新测
- `frontend/src/components/capa/{D4,D5}RecPanel.tsx` — blocked banner
- `frontend/e2e/specs/m1-core/capa-story-ai-recommend.spec.ts`（新）+ `capa-story-closed-loop.spec.ts`（改写）

**切片 B 修改/新增：**
- `backend/app/models/capa.py` — CapaRootCauseVerification 加 conclusion 列 + __table_args__ CheckConstraint(method)+CheckConstraint(conclusion)；CAPAEightD 加 d4_retry_count
- `backend/alembic/versions/<new>_conclusion_retrycount.py` — 迁移（含 is_verified→conclusion 回填）
- `backend/app/schemas/capa_verification.py` — method Literal + conclusion Literal + 删 is_verified 请求字段 + extra='forbid'
- `backend/app/services/capa_verification_service.py` — conclusion 驱动 create/update + retry_count 双行锁递增 + 审计重命名
- `backend/app/api/capa.py` — advance endpoint warning（与切片 A 合并到同一任务）
- `backend/tests/capa/...` — 4 个既有测试迁移到 conclusion + 新测
- `frontend/src/components/capa/D4VerificationCard.tsx` — conclusion 按钮 + method Select
- `frontend/src/types/index.ts` — VerificationCreate/Update 类型迁移

---

## 切片 A：01.2 BLOCKED 语义 + stage_runs 持久化

### Task A1: StageRun/RecommendationResult 加 blocked 语义

**Files:**
- Modify: `backend/app/services/recommendation_types.py:8-20`（StageRun）、`116-119`（RecommendationResult）
- Test: `backend/tests/recommendations/test_recommendation_types.py`（新增）

**Interfaces:**
- Produces: `StageRun.status` 新增合法值 `"blocked"`；`RecommendationResult.blocked: bool = False`。下游 orchestrator/pipeline/schema 依赖这两个。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/recommendations/test_recommendation_types.py
from app.services.recommendation_types import StageRun, RecommendationResult


def test_stage_run_accepts_blocked_status():
    sr = StageRun(index=11, name="LLM 融合", source="llm", status="blocked",
                  hit_count=0, summary="未配置 LLM 凭证")
    assert sr.status == "blocked"


def test_recommendation_result_default_not_blocked():
    r = RecommendationResult(items=[])
    assert r.blocked is False


def test_recommendation_result_blocked_flag():
    r = RecommendationResult(items=[], stages=[StageRun(1, "上下文", "internal", "done")], blocked=True)
    assert r.blocked is True
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_recommendation_types.py -v`
Expected: FAIL（StageRun.status Literal 不含 "blocked"，dataclass 不校验 Literal 所以可能 PASS——改用 StageRunSchema 校验测试，见下）

> 注：`@dataclass` 不强制 Literal 校验。改测 StageRunSchema（pydantic 校验 status）：

```python
# 追加到同文件
from app.schemas.recommendation_stage import StageRunSchema
import pytest

def test_stage_run_schema_accepts_blocked():
    s = StageRunSchema(index=11, name="LLM", source="llm", status="blocked",
                      hit_count=0, summary="x")
    assert s.status == "blocked"

def test_stage_run_schema_rejects_unknown_status():
    with pytest.raises(Exception):
        StageRunSchema(index=11, name="LLM", source="llm", status="bogus",
                       hit_count=0, summary="x")
```

- [ ] **Step 3: 实现**

`recommendation_types.py` StageRun（line 11）：

```python
    status: Literal["pending", "running", "done", "skipped", "error", "blocked"]
```

RecommendationResult（line 117-119）：

```python
@dataclass
class RecommendationResult:
    """管道输出。"""
    items: list[RecommendationCandidate]
    stages: list[StageRun] = field(default_factory=list)
    blocked: bool = False
```

`backend/app/schemas/recommendation_stage.py` StageRunSchema.status：

```python
    status: Literal["pending", "running", "done", "skipped", "error", "blocked"]
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_recommendation_types.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 回归**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/ tests/test_recommendation_orchestrator.py -q 2>/dev/null; pytest tests/ -k "recommend" -q --co 2>/dev/null | head`（确认既有推荐测试集合名）
Expected: 既有测试不破（status 新增值是纯加法）。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/recommendation_types.py backend/app/schemas/recommendation_stage.py backend/tests/recommendations/test_recommendation_types.py
git commit -m "feat(recommend): add 'blocked' status + RecommendationResult.blocked flag"
```

---

### Task A2: Orchestrator 顶部 BLOCKED 判定 + _blocked_stages

**Files:**
- Modify: `backend/app/services/recommendation_orchestrator.py`（run 方法顶部 + 新增 _blocked_stages）
- Test: `backend/tests/recommendations/test_recommendation_orchestrator.py`（扩展）

**Interfaces:**
- Consumes: Task A1 `RecommendationResult.blocked`、StageRun status="blocked"
- Produces: `RecommendationOrchestrator.run(...)` 在 `self.pc is None` 时返回 `RecommendationResult(items=[], stages=_blocked_stages(), blocked=True)`。`_blocked_stages(context)` 返回 12 行 StageRun。

- [ ] **Step 1: 写失败测试**

```python
# 追加到 backend/tests/recommendations/test_recommendation_orchestrator.py
import asyncio
from app.services.recommendation_orchestrator import RecommendationOrchestrator
from app.services.recommendation_types import RecommendationContext

def _make_orchestrator_with_pc_none():
    # pc=None 模拟未配置 LLM
    return RecommendationOrchestrator(db=None, pc=None, embedding_provider=None)

def test_run_blocked_when_pc_none():
    orch = _make_orchestrator_with_pc_none()
    ctx = RecommendationContext(
        capa_data={"d2_description": "x", "d4_root_cause": "", "report_id": None,
                   "product_line_code": "PL", "fmea_ref_id": None, "fmea_node_id": None},
        user_product_lines=None, stage="d4", factory_id=None, fmea_docs=[], linked_fmea=None,
    )
    result = asyncio.get_event_loop().run_until_complete(
        orch.run(ctx, user=None, report_id=None, factory_id=None, tenant_schema=None)
    )
    assert result.blocked is True
    assert result.items == []
    assert len(result.stages) == 12
    s1 = next(s for s in result.stages if s.index == 1)
    assert s1.status == "done"  # 上下文已知
    s11 = next(s for s in result.stages if s.index == 11)
    assert s11.status == "blocked"
    assert "未配置" in s11.summary
    others = [s for s in result.stages if s.index not in (1, 11)]
    assert all(s.status == "skipped" for s in others)
```

> 注：测试中 `RecommendationContext` 构造参数须与 `recommendation_types.py:24` 实际签名对齐；若字段名不符，按实际调整。

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_recommendation_orchestrator.py::test_run_blocked_when_pc_none -v`
Expected: FAIL（run() 当 pc=None 时走既有路径不返回 blocked）

- [ ] **Step 3: 实现**

`recommendation_orchestrator.py` run 方法顶部（在既有编排逻辑之前插入）：

```python
    async def run(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
        # 顶部 BLOCKED 判定（AI_REQUIRED=true，故事契约不可降级）
        if self.pc is None:
            return RecommendationResult(items=[], stages=self._blocked_stages(), blocked=True)
        # 正常编排（既有逻辑不变）
        ...
```

新增 `_blocked_stages` 方法（与 run 同类）：

```python
    def _blocked_stages(self) -> list[StageRun]:
        """pc=None 时构造 12 行结构化 BLOCKED 状态（stage 1 done、stage 11 blocked、其余 skipped）。"""
        from app.services.recommendation_orchestrator import STAGE_PLAN  # 既有 12 阶段定义
        stages = []
        for spec in STAGE_PLAN:
            if spec.index == 1:
                stages.append(StageRun(spec.index, spec.name, "internal", "done",
                                       summary="上下文已采集（D2/D4 + 关联 FMEA + 产品线）"))
            elif spec.index == 11:
                stages.append(StageRun(spec.index, spec.name, "llm", "blocked",
                                       summary="未配置 LLM 凭证"))
            else:
                stages.append(StageRun(spec.index, spec.name, spec.source_kind, "skipped",
                                       summary="LLM 未配置，编排未执行"))
        stages.sort(key=lambda s: s.index)
        return stages
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_recommendation_orchestrator.py::test_run_blocked_when_pc_none -v`
Expected: PASS

- [ ] **Step 5: 回归（既有 12 阶段编排不破）**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_recommendation_orchestrator.py tests/test_recommendation_orchestrator.py -q 2>/dev/null; pytest tests/ -k orchestrator -q`
Expected: 既有测试全绿（pc 非 None 时走既有路径，blocked=False 默认）。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/recommendation_orchestrator.py backend/tests/recommendations/test_recommendation_orchestrator.py
git commit -m "feat(recommend): orchestrator BLOCKED when pc=None + _blocked_stages"
```

---

### Task A3: RecommendationCache 加 stage_runs 列 + 迁移

**Files:**
- Modify: `backend/app/models/recommendation_cache.py:50`（加列）
- Create: `backend/alembic/versions/<ts>_capa_cache_stage_runs.py`
- Test: `backend/tests/migrations/test_migration_cache_stage_runs.py`（新增）

**Interfaces:**
- Produces: `RecommendationCache.stage_runs: Mapped[list] = JSONB nullable`。迁移 `ALTER TABLE recommendation_cache ADD COLUMN stage_runs JSONB`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/migrations/test_migration_cache_stage_runs.py
import pytest
from alembic import command
from alembic.config import Config

@pytest.mark.asyncio
async def test_stage_runs_column_added_and_removed(clean_alembic_db):
    # upgrade 后 stage_runs 列存在；downgrade 后移除。复用既有迁移测试 fixture 模式
    # 参考既有 backend/tests/migrations/ 下其他迁移测试的 fixture
    ...
```

> 注：本仓库迁移测试模式参考既有 `backend/tests/migrations/` 文件（如 lessons↔capa_verif 迁移测试）。实现时复用其 fixture（`clean_alembic_db` 或等价），断言 `information_schema.columns` 含 `stage_runs`。

简化版（用模型直接断言，覆盖 create_all 路径）：

```python
# backend/tests/recommendations/test_cache_model_stage_runs.py
from app.models.recommendation_cache import RecommendationCache

def test_recommendation_cache_has_stage_runs_column():
    col = RecommendationCache.__table__.columns.get("stage_runs")
    assert col is not None
    assert col.nullable is True
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_cache_model_stage_runs.py -v`
Expected: FAIL（列不存在）

- [ ] **Step 3: 实现模型列**

`recommendation_cache.py` 在 `suggestions` 行（line 50）后加：

```python
    suggestions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    stage_runs: Mapped[list] = mapped_column(JSONB, nullable=True)  # 12 行 StageRun 序列化（CAPA 回溯）
```

- [ ] **Step 4: 写迁移**

```python
# backend/alembic/versions/<ts>_capa_cache_stage_runs.py
"""capa cache stage_runs

Revision ID: <new_rev>
Revises: <current_head>
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "<new_rev>"
down_revision = "<current_head>"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("recommendation_cache", sa.Column("stage_runs", JSONB(), nullable=True))

def downgrade():
    op.drop_column("recommendation_cache", "stage_runs")
```

> `<current_head>` = `cd backend && alembic heads` 的输出；`<new_rev>` = 新唯一 revision id。

- [ ] **Step 5: 跑测试验证通过 + 迁移 up/down**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_cache_model_stage_runs.py -v && alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: 模型测试 PASS；迁移 up/down 干净。

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/recommendation_cache.py backend/alembic/versions/<ts>_capa_cache_stage_runs.py backend/tests/recommendations/test_cache_model_stage_runs.py
git commit -m "feat(cache): add recommendation_cache.stage_runs JSONB column + migration"
```

---

### Task A4: Pipeline 透传 blocked + 新增 _cache_capa_result + _serialize_capa_suggestions

**Files:**
- Modify: `backend/app/services/hybrid_recommendation_pipeline.py`（recommend 方法 + 新增两方法）
- Test: `backend/tests/recommendations/test_hybrid_recommendation_pipeline.py`（扩展）、`test_cache_capa_result.py`（新增）

**Interfaces:**
- Consumes: Task A1 RecommendationResult.blocked；Task A3 RecommendationCache.stage_runs
- Produces: `HybridRecommendationPipeline.recommend(...)` blocked 时不写审计/cache；正常路径调 `_cache_capa_result(report_id, context, result)`。`_serialize_capa_suggestions(stage, items) -> list[dict]`（统一 list + kind 判别）。`_cache_capa_result(report_id, context, result)` upsert RecommendationCache（report_id 键）。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/recommendations/test_cache_capa_result.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext, RecommendationResult, StageRun

@pytest.mark.asyncio
async def test_serialize_capa_suggestions_d4_is_list_with_kind():
    pipe = HybridRecommendationPipeline(db=MagicMock(), pc=None, embedding_provider=None)
    cand = RecommendationCandidate(source="fmea_graph", content="cause1", confidence=0.5,
                                    match_reason="r", metadata={"stage_index": 2})
    out = pipe._serialize_capa_suggestions("d4", [cand])
    assert isinstance(out, list)
    assert out[0]["kind"] == "d4_cause"
    assert "failure_cause_name" in out[0]

@pytest.mark.asyncio
async def test_serialize_capa_suggestions_d5_mutually_exclusive():
    pipe = HybridRecommendationPipeline(db=MagicMock(), pc=None, embedding_provider=None)
    # 一个 control 候选（to_d5_control_schema 非空）+ 一个 suggestion 候选（返回 None）
    ctrl = MagicMock(); ctrl.to_d5_control_schema.return_value = {"control_node_id": "n1", "name": "c"}
    ctrl.to_d5_suggestion_schema.return_value = {"content": "should not appear"}
    sugg = MagicMock(); sugg.to_d5_control_schema.return_value = None
    sugg.to_d5_suggestion_schema.return_value = {"content": "s1"}
    out = pipe._serialize_capa_suggestions("d5", [ctrl, sugg])
    kinds = [x["kind"] for x in out]
    assert kinds == ["d5_control", "d5_suggestion"]  # control 不重复进 suggestion
    assert len(out) == 2

@pytest.mark.asyncio
async def test_cache_capa_result_persists_stage_runs(monkeypatch):
    # mock db.execute 捕获 upsert 语句的 values
    db = MagicMock(); db.execute = AsyncMock()
    pipe = HybridRecommendationPipeline(db=db, pc=MagicMock(), embedding_provider=None)
    ctx = RecommendationContext(capa_data={"d2_description":"d","d3_interim":"","d4_root_cause":"rc",
        "fmea_ref_id":None,"fmea_node_id":None,"product_line_code":"PL","report_id":None},
        user_product_lines=None, stage="d4", factory_id=None, fmea_docs=[], linked_fmea=None)
    result = RecommendationResult(items=[],
        stages=[StageRun(i, f"s{i}", "internal", "done") for i in range(1, 13)], blocked=False)
    import uuid
    await pipe._cache_capa_result(uuid.uuid4(), ctx, result)
    db.execute.assert_awaited_once()
    # 验证调用参数含 stage_runs（通过 stmt.values，需解析 compiled params——简化为断言 execute 被调用且不抛）
```

```python
# 追加：降级测试（三轮 P1-1）——构造一个确实触发 StageRunSchema 序列化异常的 StageRun，断言 stage_runs=NULL 但 suggestions 正常写入
@pytest.mark.asyncio
async def test_cache_capa_result_stage_runs_serialize_failure_degrades(monkeypatch):
    db = MagicMock(); db.execute = AsyncMock()
    pipe = HybridRecommendationPipeline(db=db, pc=MagicMock(), embedding_provider=None)
    ctx = RecommendationContext(capa_data={"d2_description":"d","d3_interim":"","d4_root_cause":"rc",
        "fmea_ref_id":None,"fmea_node_id":None,"product_line_code":"PL","report_id":None},
        user_product_lines=None, stage="d4", factory_id=None, fmea_docs=[], linked_fmea=None)
    # status 非法 → StageRunSchema 构造抛 ValidationError
    bad_stage = StageRun(11, "LLM", "llm", "bogus_status")  # 非法 status
    result = RecommendationResult(items=[MagicMock(to_d4_schema=lambda: {"k": "v"})],
                                   stages=[bad_stage], blocked=False)
    import uuid
    await pipe._cache_capa_result(uuid.uuid4(), ctx, result)  # 不抛
    db.execute.assert_awaited_once()
    # 断言写入的 stage_runs 为 None（降级），suggestions 仍写入——需解析 stmt bound params
    # 简化：断言未抛异常即可；完整断言解析 compiled params 的 stage_runs is None

```python
# 追加到 backend/tests/recommendations/test_hybrid_recommendation_pipeline.py
@pytest.mark.asyncio
async def test_blocked_skips_audit_and_cache(monkeypatch):
    pipe = HybridRecommendationPipeline(db=MagicMock(), pc=None, embedding_provider=None)
    # mock orchestrator.run 返回 blocked=True
    pipe.orchestrator = MagicMock(); pipe.orchestrator.run = AsyncMock(return_value=RecommendationResult(items=[], stages=[], blocked=True))
    pipe._maybe_write_llm_audit = AsyncMock()
    pipe._cache_capa_result = AsyncMock()
    from app.models.user import User
    u = MagicMock(spec=User)
    result = await pipe.recommend(MagicMock(), user=u, report_id=None, factory_id=None, tenant_schema=None)
    assert result.blocked is True
    pipe._maybe_write_llm_audit.assert_not_awaited()
    pipe._cache_capa_result.assert_not_awaited()
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_cache_capa_result.py tests/recommendations/test_hybrid_recommendation_pipeline.py::test_blocked_skips_audit_and_cache -v`
Expected: FAIL（方法不存在/行为不符）

- [ ] **Step 3: 实现**

`hybrid_recommendation_pipeline.py` 改 imports（加 pg_insert/text/func/RecommendationCache/StageRunSchema）：

```python
import hashlib
import json
import logging
import uuid

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.recommendation_cache import RecommendationCache
from app.models.user import User
from app.schemas.recommendation_stage import StageRunSchema
from app.services.agent import audit as audit_mod
from app.services.recommendation_orchestrator import RecommendationOrchestrator
from app.services.recommendation_types import (
    RecommendationCandidate, RecommendationContext, RecommendationResult, StageRun,
)
```

改 `recommend` 方法：

```python
    async def recommend(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
        result = await self.orchestrator.run(context, user=user, report_id=report_id,
                                              factory_id=factory_id, tenant_schema=tenant_schema)
        if not result.blocked:  # BLOCKED 时跳过审计与 cache 写入
            await self._maybe_write_llm_audit(result, context, user, report_id, factory_id, tenant_schema)
            await self._cache_capa_result(report_id, context, result)
        return result
```

新增 `_serialize_capa_suggestions` + `_cache_capa_result`（加在类内）：

```python
    def _serialize_capa_suggestions(self, stage: str, items: list[RecommendationCandidate]) -> list[dict]:
        """统一为候选 list + kind 判别（D4: d4_cause；D5: d5_control|d5_suggestion 互斥单次遍历）。"""
        out: list[dict] = []
        if stage == "d4":
            for c in items:
                out.append({"kind": "d4_cause", **c.to_d4_schema()})
        else:  # d5
            for c in items:
                control = c.to_d5_control_schema()
                if control:
                    out.append({"kind": "d5_control", **control})
                else:
                    out.append({"kind": "d5_suggestion", **c.to_d5_suggestion_schema()})
        return out

    async def _cache_capa_result(self, report_id, context: RecommendationContext, result: RecommendationResult) -> None:
        """CAPA 专属缓存写入（write-only，report_id 键 + uq_cache_capa upsert）。"""
        if report_id is None:
            return
        context_hash = hashlib.sha256(json.dumps({
            "d2": context.capa_data.get("d2_description"),
            "d3": context.capa_data.get("d3_interim"),
            "d4": context.capa_data.get("d4_root_cause"),
            "fmea_ref_id": str(context.capa_data.get("fmea_ref_id")) if context.capa_data.get("fmea_ref_id") else None,
            "fmea_node_id": context.capa_data.get("fmea_node_id"),
            "product_line_code": context.capa_data.get("product_line_code"),
        }, sort_keys=True, default=str).encode()).hexdigest()[:16]
        trigger_type = context.stage
        suggestions = self._serialize_capa_suggestions(context.stage, result.items)
        try:
            # 整个列表推导放入 try（StageRunSchema 构造 + model_dump 才是可能抛错点，三轮 P1-1）
            stage_runs_json = [StageRunSchema(**s.__dict__).model_dump() for s in result.stages]
        except Exception as e:
            logger.warning(f"stage_runs serialize failed (degrade to NULL): {e}")
            stage_runs_json = None
        source = "hybrid"
        stmt = (
            pg_insert(RecommendationCache)
            .values(
                report_id=report_id, trigger_type=trigger_type, context_hash=context_hash,
                product_line_code=context.capa_data.get("product_line_code") or "",
                factory_id=context.factory_id, doc_type="capa",
                suggestions=suggestions, stage_runs=stage_runs_json, source=source,
                llm_available=(self.pc is not None),
                expires_at=func.now() + text("INTERVAL '24 hours'"),
            )
            .on_conflict_do_update(
                index_elements=["report_id", "trigger_type", "context_hash"],
                index_where=text("report_id IS NOT NULL"),
                set_={
                    "suggestions": suggestions, "stage_runs": stage_runs_json, "source": source,
                    "llm_available": (self.pc is not None), "created_at": func.now(),
                    "expires_at": func.now() + text("INTERVAL '24 hours'"),
                },
            )
        )
        await self.db.execute(stmt)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/recommendations/test_cache_capa_result.py tests/recommendations/test_hybrid_recommendation_pipeline.py::test_blocked_skips_audit_and_cache -v`
Expected: PASS

- [ ] **Step 5: 回归（既有 D4/D5 推荐 pipeline 测试）**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "recommend or capa_d4 or capa_d5" -q`
Expected: 既有测试不破（注意：既有 pipeline 测试可能未 mock `_cache_capa_result`，若 db 是真实 DB 则会真实写——确认既有测试用真实 DB 时 cache 写入不破坏断言；若 mock pipeline 则需补 mock）。

> 若回归红：既有 pipeline 测试断言了 `db.execute` 调用次数等，新增 cache 写入会改变——按需在既有测试 mock `_cache_capa_result` 或调整断言。记录在 task report。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/hybrid_recommendation_pipeline.py backend/tests/recommendations/test_cache_capa_result.py backend/tests/recommendations/test_hybrid_recommendation_pipeline.py
git commit -m "feat(recommend): pipeline passes through BLOCKED + adds _cache_capa_result (write-only) + _serialize_capa_suggestions"
```

---

### Task A5: D4/D5 endpoint 返回 422 blocked

**Files:**
- Modify: `backend/app/api/capa.py:437-448`（D4）、`525-545`（D5）
- Test: `backend/tests/capa/test_capa_api_d4_d5.py`（新增/扩展）

**Interfaces:**
- Consumes: Task A2/A4 `result.blocked`
- Produces: D4/D5 endpoint 在 `result.blocked` 时 `raise HTTPException(422, detail={blocked, reason, stages})`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/capa/test_capa_api_d4_d5.py
import pytest

@pytest.mark.asyncio
async def test_d4_endpoint_returns_422_blocked_when_no_llm(authed_client_factory, e2e_seed):
    # provider_adapter.build_client 抛 ProviderNotConfiguredError（无 LLM 配置）
    # 复用既有 capa API 测试 fixture；构造一个 D4 状态的 8D
    ...
    r = await client.get(f"/api/capa/{report_id}/d4-fmea-recommendations")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["blocked"] is True
    assert "stages" in detail and len(detail["stages"]) == 12
```

> 注：复用既有 capa API 测试的 client/seed fixture（参考 `backend/tests/capa/test_capa_verification_api.py` 的 fixture 模式）。确保无 LLM 配置（mock `provider_adapter.build_client` 抛 `ProviderNotConfiguredError` 或环境无配置）。

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_capa_api_d4_d5.py::test_d4_endpoint_returns_422_blocked_when_no_llm -v`
Expected: FAIL（当前返回 200 + rule-only 结果）

- [ ] **Step 3: 实现**

`capa.py` D4 endpoint（line 437-448）改：

```python
    result = await pipeline.recommend(
        context, user=scope.user, report_id=report_id,
        factory_id=capa.factory_id, tenant_schema=tenant_schema(request),
    )
    await db.commit()
    if result.blocked:
        raise HTTPException(
            status_code=422,
            detail={"blocked": True, "reason": "LLM credentials not configured",
                    "stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages]},
        )
    return {"stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages],
            "items": [c.to_d4_schema() for c in result.items]}
```

D5 endpoint（line 525-545）同样改：blocked 分支 raise 422；返回 `{stages, existing_controls, general_suggestions}`。

- [ ] **Step 4: 跑测试验证通过 + 回归**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_capa_api_d4_d5.py tests/capa/test_capa_d4_gate.py -q`
Expected: 新测 PASS + 既有 D4 gate 测试不破。

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/capa.py backend/tests/capa/test_capa_api_d4_d5.py
git commit -m "feat(capa): D4/D5 recommendation endpoint returns 422 BLOCKED when no LLM creds"
```

---

### Task A6: 前端 D4/D5RecPanel BLOCKED banner

**Files:**
- Modify: `frontend/src/components/capa/D4RecPanel.tsx`、`D5RecPanel.tsx`、`frontend/src/api/capa.ts`（axios 拦截器/错误处理）
- Test: `frontend/src/components/capa/D4RecPanel.test.tsx`（扩展）

**Interfaces:**
- Consumes: Task A5 422 + `detail.blocked`
- Produces: 面板收到 422 blocked 时渲染 `data-e2e="rec-blocked-banner"`，不清 token、不崩。

- [ ] **Step 1: 写失败测试**

```tsx
// frontend/src/components/capa/D4RecPanel.test.tsx
it("renders BLOCKED banner on 422 detail.blocked", async () => {
  // mock getD4Recommendations reject with response 422 { detail: { blocked: true, reason: "...", stages: [] } }
  // render D4RecPanel；断言 rec-blocked-banner 出现且含"未配置"
});
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd frontend && npx vitest run src/components/capa/D4RecPanel.test.tsx`
Expected: FAIL

- [ ] **Step 3: 实现**

`api/capa.ts`：在 D4/D5 推荐函数 catch 422 + `detail.blocked`，抛一个 `BlockedError`（自定义）而非走 401 清 token 分支：

```ts
// 既有 api/capa.ts: import client from "./client"；既有 getD4Recommendations/getD5... 用 client.get
export class RecommendationBlockedError extends Error {
  detail: { blocked: true; reason: string; stages: any[] };
  constructor(detail) { super(detail.reason); this.detail = detail; }
}

export async function getD4Recommendations(reportId: string) {
  try {
    return (await client.get(`/capa/${reportId}/d4-fmea-recommendations`)).data;
  } catch (e: any) {
    if (e.response?.status === 422 && e.response?.data?.detail?.blocked) {
      throw new RecommendationBlockedError(e.response.data.detail);
    }
    throw e;
  }
}
// getD5Recommendations 同样改（既有函数名按实际对齐）
```

`D4RecPanel.tsx`：catch `RecommendationBlockedError` → set state `blocked`，渲染 banner：

```tsx
{blocked && (
  <Alert data-e2e="rec-blocked-banner" type="warning" showIcon
    message="AI 推荐不可用——未配置 LLM 凭证。请联系管理员配置 /admin/ai-config" />
)}
```

i18n 补 `d4.blocked.banner`（zh-CN + en-US）。D5RecPanel 同样改。

- [ ] **Step 4: 跑测试验证通过 + tsc**

Run: `cd frontend && npx vitest run src/components/capa/D4RecPanel.test.tsx src/components/capa/D5RecPanel.test.tsx && npx tsc --noEmit`
Expected: PASS + tsc 干净

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/capa/D4RecPanel.tsx frontend/src/components/capa/D5RecPanel.tsx frontend/src/api/capa.ts frontend/src/locales/
git commit -m "feat(capa-frontend): D4/D5RecPanel BLOCKED banner on 422 + RecommendationBlockedError"
```

---

### Task A7: e2e 拆分 — capa-story-ai-recommend.spec.ts + capa-story-closed-loop.spec.ts 改写

**Files:**
- Create: `frontend/e2e/specs/m1-core/capa-story-ai-recommend.spec.ts`
- Modify: `frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts`（移除 D4/D5 AI 推荐断言，保留非 AI 闭环）
- Test: e2e 跑 `make e2e`

**Interfaces:**
- Consumes: Task A5 422 blocked；既有 `hasLLMCreds()` helper（`capa-story-closed-loop.spec.ts:30`）

- [ ] **Step 1: 写 capa-story-ai-recommend.spec.ts**

```ts
// frontend/e2e/specs/m1-core/capa-story-ai-recommend.spec.ts
import { test, expect } from "@playwright/test";
// 复用 capa-story-closed-loop.spec.ts 的 hasLLMCreds + login helper
function hasLLMCreds(): boolean { /* 同既有实现 */ }

test("AI D4 recommendation DAG (200 done | 422 BLOCKED)", async ({ page, request }) => {
  // 登录 engineer；8D 推进到 D4
  const llm = hasLLMCreds();
  const r = await request.get(`/api/capa/${reportId}/d4-fmea-recommendations`, { headers });
  if (llm) {
    expect(r.status()).toBe(200);
    const body = await r.json();
    const s11 = body.stages.find((s) => s.index === 11);
    expect(s11.status).toBe("done");
  } else {
    expect(r.status()).toBe(422);
    const detail = (await r.json()).detail;
    expect(detail.blocked).toBe(true);
    test.skip(true, "BLOCKED: no LLM creds");
  }
});
```

- [ ] **Step 2: 改写 capa-story-closed-loop.spec.ts**

移除 D4/D5 AI 推荐断言（stage 11 done/skipped 分支等），保留 D1-D3 / D7 审批 / D8_APPROVAL_PENDING→D8_CLOSURE / viewer 只读。这些非 AI 步始终照跑，无凭证也全绿。D4 验证子流程（method/conclusion/retry_count）放到此 spec（切片 B 落地后——本任务先占位，切片 B Task B8 补完验证断言）。

- [ ] **Step 3: 跑 e2e**

Run: `make e2e`
Expected: 无凭证时 `capa-story-ai-recommend.spec.ts` skip；`capa-story-closed-loop.spec.ts` 全绿。

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/specs/m1-core/capa-story-ai-recommend.spec.ts frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts
git commit -m "test(e2e): split AI recommend spec (BLOCKED skip) from non-AI closed-loop spec"
```

---

## 切片 B：01.3 method 枚举 + retry_count

### Task B1: CapaRootCauseVerification + CAPAEightD 模型字段 + 迁移

**Files:**
- Modify: `backend/app/models/capa.py:45-59`（CapaRootCauseVerification 加 conclusion + __table_args__）、`11-40`（CAPAEightD 加 d4_retry_count）
- Create: `backend/alembic/versions/<ts>_conclusion_retrycount.py`（含 is_verified→conclusion 回填 + method/conclusion CHECK）
- Test: `backend/tests/capa/test_models_conclusion_retrycount.py`（新增）

**Interfaces:**
- Produces: `CapaRootCauseVerification.conclusion: str NOT NULL server_default 'pending'`；`CAPAEightD.d4_retry_count: int NOT NULL server_default 0`；`__table_args__` 含 `chk_verification_method` + `chk_verification_conclusion`。迁移回填：旧行 `is_verified=True → conclusion='passed'`，`is_verified=False → conclusion='pending'`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/capa/test_models_conclusion_retrycount.py
from app.models.capa import CapaRootCauseVerification, CAPAEightD

def test_verification_has_conclusion_column():
    assert "conclusion" in CapaRootCauseVerification.__table__.columns
    col = CapaRootCauseVerification.__table__.columns["conclusion"]
    assert col.nullable is False

def test_verification_has_method_check_constraint():
    consts = [c.name for c in CapaRootCauseVerification.__table__.constraints if hasattr(c, "name")]
    assert "chk_verification_method" in consts

def test_verification_has_conclusion_check_constraint():
    consts = [c.name for c in CapaRootCauseVerification.__table__.constraints if hasattr(c, "name")]
    assert "chk_verification_conclusion" in consts

def test_eightd_has_d4_retry_count():
    assert "d4_retry_count" in CAPAEightD.__table__.columns
    col = CAPAEightD.__table__.columns["d4_retry_count"]
    assert col.nullable is False
```

```python
# 追加：脏数据前置断言测试（三轮 P0-1）——插入非法 method 行后 upgrade 应明确失败且不留下半迁移结构
@pytest.mark.asyncio
async def test_migration_aborts_on_dirty_method_data(alembic_engine):
    # 在 pre-migration 表中插入 method='guess'（非法），跑 upgrade → 期望 RuntimeError，
    # 且 conclusion 列未被添加（半迁移结构未残留）。复用既有 alembic 迁移测试 fixture 模式。
    # 参考 backend/tests/migrations/ 既有迁移测试的 engine/fixture。
    ...
```

> 注：该测试复用既有 `backend/tests/migrations/` 迁移测试 fixture（alembic_engine 或等价）。断言：插入 `method='guess'` 行 → `alembic upgrade head` 抛 `RuntimeError`（含 "non-enum method"）→ 事后 `information_schema.columns` 不含 `conclusion`（即 method CHECK 已加但 conclusion 列未加，验证中止在断言点而非半应用完）。若 fixture 不便构造，替代方案：直接单测 `upgrade()` 函数传一个含脏数据的 bind mock，断言 raise。

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_models_conclusion_retrycount.py -v`
Expected: FAIL

- [ ] **Step 3: 实现模型**

`capa.py` 顶部加 import：

```python
from sqlalchemy import CheckConstraint
```

`CapaRootCauseVerification`（line 45）加 `__table_args__` + conclusion 列：

```python
class CapaRootCauseVerification(Base):
    __tablename__ = "capa_root_cause_verification"
    __table_args__ = (
        CheckConstraint(
            "method IS NULL OR method IN ('measurement','observation','reproduction')",
            name="chk_verification_method",
        ),
        CheckConstraint(
            "conclusion IN ('pending','passed','failed')",
            name="chk_verification_conclusion",
        ),
    )
    verification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    root_cause_text: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 列保留，conclusion 派生
    conclusion: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    evidence_attachments: Mapped[list] = mapped_column(JSONB, default=lambda: [])
    source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

`CAPAEightD`（line 11-40 范围）加列（加在 status 等字段后）：

```python
    d4_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
```

> 确认 `Integer`/`String`/`CheckConstraint` 已在 capa.py import（既有 import 行）。

- [ ] **Step 4: 写迁移（含回填）**

```python
# backend/alembic/versions/<ts>_conclusion_retrycount.py
"""conclusion enum + d4_retry_count

Revision ID: <new_rev>
Revises: <Task A3 head>
"""
from alembic import op
import sqlalchemy as sa

revision = "<new_rev>"
down_revision = "<Task_A3_head>"

def upgrade():
    bind = op.get_bind()
    # 1. method 前置断言（三轮 P0-1）：op.execute 丢弃结果，须用 bind.scalar 读取并在脏数据时显式 raise
    dirty_method = bind.scalar(sa.text(
        "SELECT count(*) FROM capa_root_cause_verification "
        "WHERE method IS NOT NULL AND method NOT IN ('measurement','observation','reproduction')"
    ))
    if dirty_method:
        raise RuntimeError(
            f"Aborting migration: {dirty_method} verification row(s) have non-enum method value; "
            "clean before upgrade (allowed: measurement/observation/reproduction)"
        )
    op.create_check_constraint("chk_verification_method", "capa_root_cause_verification",
        "method IS NULL OR method IN ('measurement','observation','reproduction')")
    # 2. conclusion 列 + 回填（旧行 is_verified=True → passed，False → pending）
    op.add_column("capa_root_cause_verification", sa.Column("conclusion", sa.String(20), nullable=False, server_default="pending"))
    op.execute("UPDATE capa_root_cause_verification SET conclusion = CASE WHEN is_verified THEN 'passed' ELSE 'pending' END")
    op.create_check_constraint("chk_verification_conclusion", "capa_root_cause_verification",
        "conclusion IN ('pending','passed','failed')")
    # 3. d4_retry_count
    op.add_column("capa_eightd", sa.Column("d4_retry_count", sa.Integer(), nullable=False, server_default="0"))

def downgrade():
    op.drop_column("capa_eightd", "d4_retry_count")
    op.drop_constraint("chk_verification_conclusion", "capa_root_cause_verification", type_="check")
    op.drop_column("capa_root_cause_verification", "conclusion")
    op.drop_constraint("chk_verification_method", "capa_root_cause_verification", type_="check")
```

- [ ] **Step 5: 跑测试 + 迁移 up/down**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_models_conclusion_retrycount.py -v && alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: 模型测试 PASS；迁移 up/down 干净（回填后 is_verified=True 旧行 conclusion=passed）。

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/capa.py backend/alembic/versions/<ts>_conclusion_retrycount.py backend/tests/capa/test_models_conclusion_retrycount.py
git commit -m "feat(capa): add verification.conclusion + d4_retry_count + CHECK constraints + backfill migration"
```

---

### Task B2: Verification schemas — conclusion Literal + 删 is_verified 请求字段 + extra='forbid'

**Files:**
- Modify: `backend/app/schemas/capa_verification.py:18-58`
- Test: `backend/tests/capa/test_verification_schemas.py`（新增）

**Interfaces:**
- Produces: `VerificationCreate`（root_cause_text/method Literal/conclusion Literal default pending/result/evidence_attachments/source_ref，无 is_verified，`extra='forbid'`）；`VerificationUpdate`（method/conclusion/result/evidence_attachments，无 is_verified，`extra='forbid'`）；`VerificationResponse` 加 conclusion（保留 is_verified 响应字段）。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/capa/test_verification_schemas.py
import pytest
from app.schemas.capa_verification import VerificationCreate, VerificationUpdate

def test_create_accepts_conclusion():
    v = VerificationCreate(root_cause_text="rc", conclusion="passed")
    assert v.conclusion == "passed"

def test_create_default_conclusion_pending():
    v = VerificationCreate(root_cause_text="rc")
    assert v.conclusion == "pending"

def test_create_rejects_is_verified_field():
    with pytest.raises(Exception):
        VerificationCreate(root_cause_text="rc", is_verified=True)  # extra='forbid' → 422

def test_create_rejects_invalid_conclusion():
    with pytest.raises(Exception):
        VerificationCreate(root_cause_text="rc", conclusion="bogus")

def test_create_rejects_invalid_method():
    with pytest.raises(Exception):
        VerificationCreate(root_cause_text="rc", method="guess")

def test_update_rejects_is_verified_field():
    with pytest.raises(Exception):
        VerificationUpdate(is_verified=True)
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_verification_schemas.py -v`
Expected: FAIL（字段/extra 不符）

- [ ] **Step 3: 实现**

`capa_verification.py` 改：

```python
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator


class AdoptRequest(BaseModel):
    d_step: Literal["d4", "d5"]
    adopted_text: str
    source: str
    stage_index: int | None = None
    item_ref: dict | None = None


class AdoptResponse(BaseModel):
    adoption_id: uuid.UUID
    d_step: str
    field_value: str


class VerificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_cause_text: str
    method: Literal["measurement", "observation", "reproduction"] | None = None
    result: str | None = None
    conclusion: Literal["pending", "passed", "failed"] = "pending"
    evidence_attachments: list[dict] = []
    source_ref: dict | None = None

    @field_validator("root_cause_text")
    @classmethod
    def root_cause_text_must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("root_cause_text 不能为空")
        return v.strip()


class VerificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["measurement", "observation", "reproduction"] | None = None
    result: str | None = None
    conclusion: Literal["pending", "passed", "failed"] | None = None
    evidence_attachments: list[dict] | None = None


class VerificationResponse(BaseModel):
    verification_id: uuid.UUID
    capa_id: uuid.UUID
    root_cause_text: str
    method: Literal["measurement", "observation", "reproduction"] | None
    result: str | None
    is_verified: bool  # 响应字段保留（列派生）
    conclusion: Literal["pending", "passed", "failed"]
    evidence_attachments: list[dict]
    source_ref: dict | None
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_verification_schemas.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/capa_verification.py backend/tests/capa/test_verification_schemas.py
git commit -m "feat(capa): verification schemas — conclusion Literal, drop is_verified request field, extra=forbid"
```

---

### Task B3: capa_verification_service — conclusion 驱动 + retry_count 双行锁递增 + 审计重命名

**Files:**
- Modify: `backend/app/services/capa_verification_service.py`（create_verification + update_verification 重写）
- Test: `backend/tests/capa/test_capa_verification_conclusion.py`（新增）

**Interfaces:**
- Consumes: Task B1 conclusion 列 + d4_retry_count；Task B2 schema（conclusion，无 is_verified 请求）
- Produces: `create_verification` 写 conclusion（默认 pending）+ is_verified 派生（conclusion=passed→True）；`update_verification` 双行锁（verification + capa）+ conclusion→failed 跃迁递增 d4_retry_count + is_verified 派生；审计 `D4_VERIFICATION_PASSED`/`D4_VERIFICATION_FAILED`（含 retry_count），pending 不写结论审计。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/capa/test_capa_verification_conclusion.py
import pytest, asyncio
from app.schemas.capa_verification import VerificationCreate, VerificationUpdate

@pytest.mark.asyncio
async def test_create_default_pending_no_increment(db_session, capa_factory, admin_user):
    capa = await capa_factory()
    rec = await create_verification(db_session, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    assert rec.conclusion == "pending"
    assert rec.is_verified is False
    await db_session.refresh(capa)
    assert capa.d4_retry_count == 0

@pytest.mark.asyncio
async def test_conclusion_failed_increments_retry_count(db_session, capa_factory, admin_user):
    capa = await capa_factory()
    rec = await create_verification(db_session, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    await update_verification(db_session, capa, rec.verification_id, VerificationUpdate(conclusion="failed"), admin_user)
    await db_session.refresh(capa)
    assert capa.d4_retry_count == 1
    assert rec.conclusion == "failed"
    assert rec.is_verified is False

@pytest.mark.asyncio
async def test_conclusion_passed_no_increment(db_session, capa_factory, admin_user):
    capa = await capa_factory()
    rec = await create_verification(db_session, capa, VerificationCreate(root_cause_text="rc", method="measurement", result="ok", evidence_attachments=[{"u":1}]), admin_user)
    await update_verification(db_session, capa, rec.verification_id, VerificationUpdate(conclusion="passed"), admin_user)
    await db_session.refresh(capa)
    assert capa.d4_retry_count == 0
    assert rec.is_verified is True

@pytest.mark.asyncio
async def test_failed_no_transition_no_double_count(db_session, capa_factory, admin_user):
    capa = await capa_factory()
    rec = await create_verification(db_session, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    await update_verification(db_session, capa, rec.verification_id, VerificationUpdate(conclusion="failed"), admin_user)
    # 再次 failed（无跃迁）→ 不递增
    await update_verification(db_session, capa, rec.verification_id, VerificationUpdate(result="more"), admin_user)
    await db_session.refresh(capa)
    assert capa.d4_retry_count == 1

@pytest.mark.asyncio
async def test_same_record_concurrent_failed_increments_once(sessionmaker, capa_factory, admin_user):
    # 三轮 P1-2：单 AsyncSession 不支持并发，须每 worker 独立 session。
    # seed：建 capa + verification（pending），提交并关闭 seed session
    seed_session = sessionmaker()
    capa = await capa_factory(session=seed_session)
    rec = await create_verification(seed_session, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    rid = rec.verification_id; cid = capa.report_id
    await seed_session.commit(); await seed_session.close()

    async def worker():
        s = sessionmaker()
        # 每 worker 重新加载 capa 对象（独立 session，独立 identity map）
        w_capa = await s.get(CAPAEightD, cid)
        try:
            await update_verification(s, w_capa, rid, VerificationUpdate(conclusion="failed"), admin_user)
            await s.commit()
        except Exception:
            await s.rollback()
            raise
        finally:
            await s.close()

    await asyncio.gather(worker(), worker())  # 同一记录两个并发 failed
    # 第三 session 回读
    check = sessionmaker()
    c = await check.get(CAPAEightD, cid)
    assert c.d4_retry_count == 1  # verification 行锁去重，仅 +1
    await check.close()

@pytest.mark.asyncio
async def test_different_records_concurrent_failed_increments_twice(sessionmaker, capa_factory, admin_user):
    # 同一 CAPA 两条不同 verification 记录并发 failed → +2（capa 行锁防跨记录丢计数）
    seed = sessionmaker()
    capa = await capa_factory(session=seed)
    r1 = await create_verification(seed, capa, VerificationCreate(root_cause_text="rc1"), admin_user)
    r2 = await create_verification(seed, capa, VerificationCreate(root_cause_text="rc2"), admin_user)
    cid = capa.report_id; rid1, rid2 = r1.verification_id, r2.verification_id
    await seed.commit(); await seed.close()

    async def worker(rid):
        s = sessionmaker()
        w_capa = await s.get(CAPAEightD, cid)
        try:
            await update_verification(s, w_capa, rid, VerificationUpdate(conclusion="failed"), admin_user)
            await s.commit()
        except Exception:
            await s.rollback(); raise
        finally:
            await s.close()

    await asyncio.gather(worker(rid1), worker(rid2))
    check = sessionmaker()
    c = await check.get(CAPAEightD, cid)
    assert c.d4_retry_count == 2  # 跨记录各计一次，capa 行锁防丢
    await check.close()
```

> 注：`sessionmaker` fixture 须返回一个 `async_sessionmaker`（每调用新建独立 AsyncSession）。复用既有 `backend/tests/conftest.py` 或 capa 测试的 sessionmaker fixture；若无，在 conftest 新增 `async_sessionmaker` fixture（基于既有 engine）。每个 worker 用 `s.get(CAPAEightD, cid)` 重新加载独立 capa 对象，避免共享 identity map。三段式：seed session 提交关闭 → 并发 workers 各自独立 session → check session 回读。

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_capa_verification_conclusion.py -v`
Expected: FAIL（create/update 仍读 req.is_verified，无 conclusion 处理/递增）

- [ ] **Step 3: 实现**

`capa_verification_service.py` 重写 `create_verification`：

```python
async def create_verification(db: AsyncSession, capa, req: VerificationCreate, user):
    conclusion = req.conclusion
    is_verified = (conclusion == "passed")
    if is_verified:
        _assert_verified_has_details(req.method, req.result, req.evidence_attachments)
    rec = CapaRootCauseVerification(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        root_cause_text=req.root_cause_text, method=req.method, result=req.result,
        is_verified=is_verified, conclusion=conclusion,
        evidence_attachments=req.evidence_attachments, source_ref=req.source_ref,
        verified_by=user.user_id if is_verified else None,
        verified_at=func.now() if is_verified else None,
        created_at=func.clock_timestamp(),
    )
    db.add(rec)
    if conclusion == "passed":
        db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_PASSED",
            changed_fields={"root_cause_text": req.root_cause_text, "method": req.method},
            operated_by=user.user_id, factory_id=capa.factory_id))
    elif conclusion == "failed":
        # 创建即 failed（罕见，但支持）→ 递增
        # 三轮 P0-2：锁后必须 refresh capa 读最新 retry_count，否则传入的 capa 对象可能缓存旧值
        await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).with_for_update())
        await db.refresh(capa)  # 锁后重读最新值（同 adopt_recommendation:49-51 既有模式）
        capa.d4_retry_count = (capa.d4_retry_count or 0) + 1
        db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_FAILED",
            changed_fields={"root_cause_text": req.root_cause_text, "method": req.method,
                            "retry_count": capa.d4_retry_count},
            operated_by=user.user_id, factory_id=capa.factory_id))
    # pending：不写结论审计
    await db.commit()
    await db.refresh(rec)
    return rec
```

重写 `update_verification`（双行锁 + conclusion 跃迁递增）：

```python
async def update_verification(db: AsyncSession, capa, vid, req: VerificationUpdate, user):
    # 锁 verification 行，序列化同记录并发跃迁（去重）
    rec = await db.scalar(select(CapaRootCauseVerification).where(
        CapaRootCauseVerification.verification_id == vid,
        CapaRootCauseVerification.capa_id == capa.report_id,
        CapaRootCauseVerification.factory_id == capa.factory_id,
    ).with_for_update())
    if rec is None:
        raise LookupError("verification not found")
    updates = req.model_dump(exclude_unset=True)
    old_conclusion = rec.conclusion
    if "method" in updates:
        rec.method = updates["method"]
    if "result" in updates:
        rec.result = updates["result"]
    if "evidence_attachments" in updates:
        rec.evidence_attachments = updates["evidence_attachments"] or []
    if "conclusion" in updates and updates["conclusion"] is not None:
        rec.conclusion = updates["conclusion"]
    # is_verified 派生
    rec.is_verified = (rec.conclusion == "passed")
    if rec.is_verified:
        rec.verified_by = user.user_id
        rec.verified_at = func.now()
    else:
        rec.verified_by = None
        rec.verified_at = None
    if rec.is_verified:
        _assert_verified_has_details(rec.method, rec.result, rec.evidence_attachments)
    # conclusion→failed 跃迁递增 retry_count（仅跃迁，防重复计；锁 capa 行防跨记录丢计数）
    if old_conclusion != "failed" and rec.conclusion == "failed":
        # 三轮 P0-3：锁后必须 refresh capa 读最新 retry_count；不同 verification 并发失败时
        # 各 session 的 capa 可能缓存旧 retry_count=0，不 refresh 会丢失跨记录计数
        await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).with_for_update())
        await db.refresh(capa)  # 锁后重读最新值（同 adopt_recommendation 既有模式）
        capa.d4_retry_count = (capa.d4_retry_count or 0) + 1
        db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_FAILED",
            changed_fields={"verification_id": str(vid), "method": rec.method,
                            "root_cause_text": rec.root_cause_text,
                            "retry_count": capa.d4_retry_count},
            operated_by=user.user_id, factory_id=capa.factory_id))
    elif old_conclusion != "passed" and rec.conclusion == "passed":
        db.add(AuditLog(table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_PASSED",
            changed_fields={"verification_id": str(vid), "method": rec.method,
                            "root_cause_text": rec.root_cause_text},
            operated_by=user.user_id, factory_id=capa.factory_id))
    await db.commit()
    await db.refresh(rec)
    return rec
```

> 既有 `from sqlalchemy import func, select` 已在文件顶部；`CAPAEightD` 已 import。

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_capa_verification_conclusion.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/capa_verification_service.py backend/tests/capa/test_capa_verification_conclusion.py
git commit -m "feat(capa): verification service conclusion-driven + dual-lock retry_count increment + audit rename"
```

---

### Task B4: CAPAAdvanceResponse + advance endpoint API 层 warning + d4_retry_count 可观察契约

**Files:**
- Modify: `backend/app/schemas/capa.py`（新增 CAPAAdvanceResponse + CAPAResponse 加 d4_retry_count）
- Modify: `backend/app/api/capa.py:217-231`（advance endpoint）
- Modify: `frontend/src/types/index.ts`（CAPAReport 加 d4_retry_count）
- Test: `backend/tests/capa/test_advance_warning.py`（新增）

**Interfaces:**
- Consumes: Task B1 `capa.d4_retry_count`；service `advance_capa(...) -> CAPAEightD`（签名不变）
- Produces: `CAPAAdvanceResponse { capa: CAPAResponse, warning: str | None }`；`CAPAResponse.d4_retry_count: int`（三轮 P1-3：e2e/API 可观察 retry_count）；advance endpoint `response_model=CAPAAdvanceResponse`，warning 据 `from_status == D4_ROOT_CAUSE and capa.d4_retry_count >= 3`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/capa/test_advance_warning.py
import pytest
from app.state_machines.eightd_state import EightDState

@pytest.mark.asyncio
async def test_advance_d4_to_d5_warns_at_threshold(client_factory, capa_at_d4_with_retry3):
    # capa 处于 D4_ROOT_CAUSE，d4_retry_count=3
    r = await client.post(f"/api/capa/{report_id}/advance", json={}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert "warning" in body and "建议升级处理" in (body["warning"] or "")
    assert body["capa"]["status"] == "D5_CORRECTION"
    assert body["capa"]["d4_retry_count"] == 3  # 三轮 P1-3：可观察

@pytest.mark.asyncio
async def test_capa_response_exposes_d4_retry_count(client_factory, capa_factory):
    capa = await capa_factory()  # d4_retry_count=0 default
    r = await client.get(f"/api/capa/{capa.report_id}", headers=auth)
    assert r.json()["d4_retry_count"] == 0  # CAPAResponse 暴露 retry_count

@pytest.mark.asyncio
async def test_advance_non_d4_edge_no_warning(client_factory, capa_at_d5):
    r = await client.post(f"/api/capa/{report_id}/advance", json={}, headers=auth)
    body = r.json()
    assert body["warning"] is None  # D5→D6 边不触发

@pytest.mark.asyncio
async def test_advance_below_threshold_no_warning(client_factory, capa_at_d4_retry1):
    r = await client.post(f"/api/capa/{report_id}/advance", json={}, headers=auth)
    body = r.json()
    assert body["warning"] is None
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_advance_warning.py -v`
Expected: FAIL（响应无 warning 字段）

- [ ] **Step 3: 实现**

`schemas/capa.py` — CAPAResponse 加 d4_retry_count（三轮 P1-3）+ 新增 CAPAAdvanceResponse：

```python
class CAPAResponse(BaseModel):
    report_id: uuid.UUID
    document_no: str
    title: str
    product_line_code: str
    status: str
    severity: str
    d1_team: list | None = None
    d2_description: str | None = None
    d3_interim: str | None = None
    d4_root_cause: str | None = None
    d5_correction: str | None = None
    d6_verification: str | None = None
    d7_prevention: str | None = None
    d8_closure: str | None = None
    fmea_ref_id: uuid.UUID | None = None
    fmea_node_id: str | None = None
    due_date: date | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    d4_retry_count: int = 0  # 三轮 P1-3：e2e/API 可观察 D4 回退计数

    model_config = {"from_attributes": True}


class CAPAAdvanceResponse(BaseModel):
    capa: CAPAResponse
    warning: str | None = None
    model_config = {"from_attributes": True}
```

`frontend/src/types/index.ts` — CAPAReport 加 `d4_retry_count: number`。

`capa.py` advance endpoint（line 217-231）改：

```python
from app.state_machines.eightd_state import EightDState  # 顶部 import（若未导入）

D4_RETRY_THRESHOLD = 3

@router.post("/{report_id}/advance", response_model=CAPAAdvanceResponse)
async def advance_capa(
    report_id: uuid.UUID,
    body: AdvanceRequest | None = None,
    db: AsyncSession = Depends(get_db),
    result: tuple[RequestScope, Any] = Depends(require_advance_permission),
):
    scope, capa = result
    from_status = capa.status  # 推进前状态
    try:
        capa = await capa_service.advance_capa(
            db, capa, scope.user.user_id, body or AdvanceRequest()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    warning = None
    if from_status == EightDState.D4_ROOT_CAUSE.value and (capa.d4_retry_count or 0) >= D4_RETRY_THRESHOLD:
        warning = "建议升级处理（D4 验证已回退 {} 次）".format(capa.d4_retry_count)
    return CAPAAdvanceResponse(capa=CAPAResponse.model_validate(capa), warning=warning)
```

> `from_status` 是 `capa.status` 字符串值（EightDState.D4_ROOT_CAUSE.value == "D4_ROOT_CAUSE"）。确认 `CAPAAdvanceResponse` 在 import 中。

- [ ] **Step 4: 跑测试验证通过 + 回归（既有 advance 测试 service 签名不变）**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/test_advance_warning.py tests/ -k "advance" -q`
Expected: 新测 PASS；既有 advance 测试若断言响应是 CAPAResponse 形状，可能需适配 `{capa, warning}`——记录并调整。

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/capa.py backend/app/api/capa.py backend/tests/capa/test_advance_warning.py
git commit -m "feat(capa): CAPAAdvanceResponse + API-layer D4→D5 retry warning (service signature unchanged)"
```

---

### Task B5: 既有 4 个后端测试迁移到 conclusion + 回归

**Files:**
- Modify: `backend/tests/capa/test_capa_d4_gate.py`、`test_capa_verification_api.py`、`test_capa_verification_service.py`、`test_models_verification_adoption.py`
- Test: 回归跑全部 capa 测试

**Interfaces:**
- Consumes: Task B2/B3 新 schema + service

- [ ] **Step 1: 迁移 test_capa_d4_gate.py**

逐行替换（**method 字面量也必须迁移**——三轮 P0-4：新 Literal 只接受 measurement/observation/reproduction，`method="复测"`/`method="m"` 会在进 service 前被 Pydantic 拒）：
- `VerificationCreate(root_cause_text="rc", method="复测", is_verified=True)` → `VerificationCreate(root_cause_text="rc", method="reproduction", conclusion="passed")`（line 31/48/59；复测→reproduction）
- `VerificationCreate(root_cause_text="rc", is_verified=False)` → `VerificationCreate(root_cause_text="rc", conclusion="pending")`（line 39，草稿门禁用例）
- 闸口断言不变（仍读 is_verified 列，conclusion=passed 派生）

- [ ] **Step 2: 迁移 test_capa_verification_api.py**

- `json={"root_cause_text": "rc", "method": "复测", "is_verified": True}` → `json={"root_cause_text": "rc", "method": "reproduction", "conclusion": "passed"}`（line 69；复测→reproduction）
- `assert r1.json()["is_verified"] is True` → 保留（响应字段保留）+ 加 `assert r1.json()["conclusion"] == "passed"`
- `json={"is_verified": True}`（PATCH，line 86）→ `json={"conclusion": "passed"}`
- `json={"root_cause_text": "rc", "is_verified": False}`（line 202）→ `json={"root_cause_text": "rc", "conclusion": "pending"}`
- `json={"is_verified": True}`（line 206）→ `json={"conclusion": "passed"}`
- `json={"root_cause_text": "rc", "is_verified": True}`（line 214）→ `json={"root_cause_text": "rc", "conclusion": "passed"}`
- 加新测：旧 `is_verified` 请求 → 422（`extra='forbid'`）
- 加新测：`method="复测"` / `method="m"` → 422（非法 method，回归保护）

- [ ] **Step 3: 迁移 test_capa_verification_service.py**

- `VerificationCreate(root_cause_text="rc", method="m", result="r", is_verified=True)`（line 109）→ `conclusion="passed", method="measurement"`（m→measurement）
- `VerificationCreate(root_cause_text="rc", is_verified=False)`（line 119）→ `conclusion="pending"`
- `VerificationUpdate(is_verified=True)`（line 132）→ `VerificationUpdate(conclusion="passed")`
- `VerificationCreate(..., is_verified=True)`（line 141）→ `conclusion="passed"`（若该行有 method 字面量，同步迁移）
- `VerificationUpdate(is_verified=False)`（line 143）→ `conclusion="failed"`（注意：原 is_verified=False 的语义——若该用例是「从通过回退到不通过」，conclusion="failed"；若是「草稿清空」，conclusion="pending"。按用例注释判断。）
- 全仓 method 字面量搜索确认无遗漏（三轮 P0-4）：

```bash
grep -rn "method=\"复测\"\|method='复测'\|method=\"m\"\|method='m'\|method: \"复测\"\|method: \"m\"\|, method=" backend/tests/capa/ frontend/src/components/capa/
```

预期：除已迁移点外无其他非法 method 字面量。若有，按 measurement/observation/reproduction 语义迁移。

- [ ] **Step 4: 迁移 test_models_verification_adoption.py**

- line 33 `is_verified=True` 是直接设模型列（非 schema）→ **列保留，不改**。确认该测试不通过 schema 提交 is_verified。

- [ ] **Step 5: 跑全部 capa 测试回归**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/capa/ -q`
Expected: 全绿（含新 conclusion 测试 + 迁移后的既有测试）

> 若红：逐个用例按 conclusion 语义修正（特别是 is_verified=False 的歧义用例——草稿用 pending，回退用 failed）。

- [ ] **Step 6: Commit**

```bash
git add backend/tests/capa/test_capa_d4_gate.py backend/tests/capa/test_capa_verification_api.py backend/tests/capa/test_capa_verification_service.py backend/tests/capa/test_models_verification_adoption.py
git commit -m "test(capa): migrate 4 existing test files from is_verified to conclusion"
```

---

### Task B6: 前端 D4VerificationCard — conclusion 按钮 + method Select + types

**Files:**
- Modify: `frontend/src/components/capa/D4VerificationCard.tsx`、`frontend/src/types/index.ts`、`frontend/src/api/capa.ts`
- Test: `frontend/src/components/capa/D4VerificationCard.test.tsx`

**Interfaces:**
- Consumes: Task B2/B4 backend contract（conclusion，CAPAAdvanceResponse）
- Produces: 验证卡 method Select + conclusion 按钮（通过/不通过/保存草稿）；types VerificationCreate/Update 用 conclusion；advance 调用方读 `{ capa, warning }`。

- [ ] **Step 1: 写失败测试**

```tsx
// D4VerificationCard.test.tsx — 改 mock 断言 conclusion
it("submits conclusion=passed via verify-pass button", async () => {
  // render；click verify-pass；assert createVerification/updateVerification called with { conclusion: "passed" }（无 is_verified）
});
it("submits conclusion=failed via verify-fail button", async () => {
  // click verify-fail；assert { conclusion: "failed" }
});
it("renders method Select with three options", async () => {
  // assert verification-method select has measurement/observation/reproduction
});
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd frontend && npx vitest run src/components/capa/D4VerificationCard.test.tsx`
Expected: FAIL

- [ ] **Step 3: 实现**

`types/index.ts` — VerificationCreate/Update：

```ts
export interface VerificationCreate {
  root_cause_text: string;
  method?: "measurement" | "observation" | "reproduction";
  result?: string;
  conclusion?: "pending" | "passed" | "failed";
  evidence_attachments?: Record<string, unknown>[];
  source_ref?: Record<string, unknown> | null;
}
export interface VerificationUpdate {
  method?: "measurement" | "observation" | "reproduction";
  result?: string;
  conclusion?: "pending" | "passed" | "failed";
  evidence_attachments?: Record<string, unknown>[];
}
// 删除 is_verified 字段
```

`D4VerificationCard.tsx` — 替换 `is_verified` Switch 为结论按钮 + method Select：

```tsx
<Form.Item name="method" label={t("d4.method")}>
  <Select data-e2e="verification-method" placeholder={t("d4.methodPlaceholder")}>
    <Option value="measurement">{t("verification.method.measurement")}</Option>
    <Option value="observation">{t("verification.method.observation")}</Option>
    <Option value="reproduction">{t("verification.method.reproduction")}</Option>
  </Select>
</Form.Item>
{/* 提交结论按钮 */}
<Button data-e2e="verify-pass" onClick={() => submit({ conclusion: "passed" })}>{t("verification.conclusion.passed")}</Button>
<Button data-e2e="verify-fail" onClick={() => submit({ conclusion: "failed" })}>{t("verification.conclusion.failed")}</Button>
<Button data-e2e="verify-save-draft" onClick={() => submit({ conclusion: "pending" })}>{t("verification.conclusion.saveDraft")}</Button>
```

`submit` 调 `createVerification`/`updateVerification`（去掉 is_verified，用 conclusion）。i18n 补 `verification.method.*` + `verification.conclusion.*`（zh-CN + en-US）。

`api/capa.ts` — advance 调用方适配 `CAPAAdvanceResponse`（三轮命名修正：既有符号是 `client`（default import from `./client`）+ `advanceCAPA`，非 `api`/`advanceCapa`）：

```ts
// frontend/src/api/capa.ts 既有：import client from "./client"; export async function advanceCAPA(id, req = {}): Promise<CAPAReport>
// 改为返回 { capa, warning } 适配，调用方继续用 capa：
import client from "./client";
import { message } from "antd";

export interface CAPAAdvanceResponse { capa: CAPAReport; warning: string | null }

export async function advanceCAPA(id: string, req: AdvanceRequest = {}): Promise<CAPAReport> {
  const r = (await client.post(`/capa/${id}/advance`, req)).data as CAPAAdvanceResponse;
  if (r.warning) message.warning(r.warning);
  return r.capa;  // 调用方继续用 capa（保持既有返回类型 CAPAReport，不破现有调用方）
}
```

- [ ] **Step 4: 跑测试 + tsc + build**

Run: `cd frontend && npx vitest run src/components/capa/D4VerificationCard.test.tsx src/api/capa.test.ts && npx tsc --noEmit && npm run build`
Expected: PASS + tsc 干净 + build 绿

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/capa/D4VerificationCard.tsx frontend/src/types/index.ts frontend/src/api/capa.ts frontend/src/components/capa/D4VerificationCard.test.tsx frontend/src/api/capa.test.ts frontend/src/locales/
git commit -m "feat(capa-frontend): D4VerificationCard conclusion buttons + method Select + CAPAAdvanceResponse adapter"
```

---

### Task B7: e2e capa-story-closed-loop 补 D4 验证子流程断言

**Files:**
- Modify: `frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts`（补验证子流程）
- Test: `make e2e`

**Interfaces:**
- Consumes: Task B6 前端 testid（verify-pass/verify-fail/verify-save-draft/verification-method）；Task B4 `CAPAResponse.d4_retry_count`（三轮 P1-3：可观察契约）

- [ ] **Step 1: 补 e2e 断言**

在 `capa-story-closed-loop.spec.ts` D4 步加（retry_count 通过 `GET /api/capa/{id}` 的 `d4_retry_count` 字段或 advance 响应 `capa.d4_retry_count` 回读——三轮 P1-3 已暴露）：

```ts
test("D4 verification subflow: method enum + conclusion + retry_count", async ({ page, request }) => {
  // 登录 engineer；8D 推进到 D4
  // 选根因 → 选 method（verification-method select → measurement）
  // 填 result → 上传证据 → 保存草稿（verify-save-draft）
  //   → GET /api/capa/{id} → 断 response.d4_retry_count == 0（草稿未递增）
  // 提交结论不通过（verify-fail）→ GET /api/capa/{id} → 断 d4_retry_count == 1
  // 重选另一条根因 → 提交结论通过（verify-pass）→ POST advance
  //   → advance 响应 capa.status == "D5_CORRECTION"
  // 若 d4_retry_count>=3 → 断 advance 响应 warning 含"建议升级处理" + UI toast
});
```

- [ ] **Step 2: 跑 e2e**

Run: `make e2e`
Expected: capa-story-closed-loop.spec.ts 全绿（含 D4 验证子流程；非 AI 步无凭证也照跑）

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts
git commit -m "test(e2e): D4 verification subflow — method/conclusion/retry_count assertions"
```

---

### Task B8: 整体验收 + PROGRESS.md 更新

**Files:**
- Modify: `PROGRESS.md`（勾选 P0 项）

- [ ] **Step 1: make check**

Run: `make check`
Expected: backend pytest 全绿（含新测 + 回归）+ frontend tsc + vite build 绿

- [ ] **Step 2: e2e**

Run: `make e2e`
Expected: `capa-story-ai-recommend.spec.ts` 无凭证 skip / 有凭证 done；`capa-story-closed-loop.spec.ts` 全绿（含 D4 验证子流程）

- [ ] **Step 3: 更新 PROGRESS.md**

在「US-E2E-01 v8.1 待办任务」P0 段勾选：
- `[x] 01.2 12 源推荐收尾` — BLOCKED 语义 + stage_runs 持久化 + CAPA 缓存写入路径
- `[x] 01.3 D4 验证 method 枚举 + 回退计数器切片` — conclusion 枚举 + retry_count + 阈值提示

- [ ] **Step 4: Commit**

```bash
git add PROGRESS.md
git commit -m "docs(progress): tick US-E2E-01 P0 收尾 (01.2 BLOCKED+stage_runs, 01.3 method+retry_count)"
```

---

## Self-Review Checklist（计划作者已跑）

**1. Spec coverage:**
- §4.1.1 BLOCKED 判定 → Task A1/A2 ✓
- §4.1.2 pipeline 透传 + cache 写 → Task A4 ✓
- §4.1.3 API 422 → Task A5 ✓
- §4.1.4 stage_runs 列 + _cache_capa_result → Task A3/A4 ✓
- §4.1.5 前端 banner → Task A6 ✓
- §4.1.6 e2e 拆分 → Task A7 ✓
- §4.2.1 conclusion + CHECK + 删 is_verified 请求 + extra='forbid' + 迁移回填 → Task B1/B2 ✓
- §4.2.2 d4_retry_count + 双行锁 → Task B1/B3 ✓
- §4.2.3 CAPAAdvanceResponse + API 层 warning → Task B4 ✓
- §4.2.4 审计重命名 → Task B3 ✓
- §4.2.5 前端验证卡 → Task B6 ✓
- §5/§6 错误处理（并发去重/extra forbid/迁移回填）→ Task B1/B2/B3 测试覆盖 ✓
- §7 测试策略 → 各 task 内测试 ✓

**2. Placeholder scan:** 无 TBD/TODO；每步含实际代码或命令。（部分测试 fixture 名如 `capa_factory`/`db_session` 标注「复用既有 fixture 模式」——实现时按既有 fixture 实际名对齐，已在 task 内注明参考文件。）

**3. Type consistency:**
- `conclusion: Literal["pending","passed","failed"]` 全链一致（schema/model/service/frontend）✓
- `d4_retry_count` server_default="0" 一致；CAPAResponse + 前端 CAPAReport 暴露 `d4_retry_count: int`（三轮 P1-3 可观察契约）✓
- `StageRun.status` "blocked" 在 types.py + recommendation_stage.py 双声明 ✓
- `RecommendationResult.blocked` 字段名一致 ✓
- `_cache_capa_result`/`_serialize_capa_suggestions` 方法名一致 ✓
- `CAPAAdvanceResponse { capa, warning }` 字段名一致 ✓
- advance service 签名 `-> CAPAEightD` 不变 ✓
- 前端符号 `client`（default import）+ `advanceCAPA`（非 api/advanceCapa），三轮命名修正 ✓

**4. 依赖顺序:** A1→A2→A3→A4→A5→A6→A7（切片 A）；B1→B2→B3→B4→B5→B6→B7→B8（切片 B）。切片 A 与 B 无代码依赖可并行，但建议 A 先（解锁 BLOCKED 语义）。B5（测试迁移）依赖 B2/B3 落地。B7 e2e 依赖 B4（d4_retry_count 可观察）+ B6（前端 testid）。

**已知风险（实现时注意）：**
- 既有 pipeline 测试可能未 mock `_cache_capa_result`，真实 DB 写入可能改变 `db.execute` 断言（Task A4 Step 5）。
- 既有 advance 测试断言响应为 CAPAResponse 形状，需适配 `{capa, warning}`（Task B4 Step 4）；CAPAResponse 加 `d4_retry_count` 字段不破既有（新字段默认 0）。
- `is_verified=False` 既有用例语义歧义（草稿 vs 回退），迁移时按用例注释判 pending/failed（Task B5 Step 3）。
- 并发测试须用独立 AsyncSession per worker（Task B3 `test_same_record_concurrent_failed_increments_once` / `test_different_records_concurrent_failed_increments_twice`）；若 `backend/tests/conftest.py` 无 `async_sessionmaker` fixture，新增一个。
- 测试 fixture 名以既有 `backend/tests/capa/` 实际为准，task 内给的是参考名。

---

## 计划评审修订记录

### 第一轮（人工复审，2026-07-09）：4 P0 + 3 P1，全部接受

| 评审项 | 级别 | 缺陷 | 修订 |
|---|---|---|---|
| 脏数据前置断言未断言 | P0 | `op.execute(SELECT count(*))` 丢弃结果、不中止，CHECK 会以普通约束错误失败 | Task B1 迁移改 `bind = op.get_bind(); dirty = bind.scalar(sa.text(...)); if dirty: raise RuntimeError` + 脏数据升级中止测试 |
| CAPA 行锁后用旧值递增（create） | P0 | 锁查询结果丢弃，传入的 capa 对象可能缓存旧 retry_count → 跨记录丢计数 | Task B3 create_verification failed 分支：锁后 `await db.refresh(capa)` 读最新值再递增（同 adopt_recommendation:49-51 既有模式） |
| update 路径同样锁后改陈旧 capa | P0 | 不同 verification 并发失败各 session capa 缓存旧值 → DB 仍为 1 | Task B3 update_verification failed 跃迁：锁后 `await db.refresh(capa)` 再递增 |
| 既有测试仍用非法 method 值 | P0 | `method='复测'`/`'m'` 被新 Literal 拒 → 422 | Task B5 迁移 method 字面量（复测→reproduction, m→measurement）+ 全仓 grep 确认无遗漏 + 非法 method 422 回归测试 |
| stage_runs 降级 try 位置无效 | P1 | try 内仅变量赋值，序列化异常在 try 外抛 | Task A4 `_cache_capa_result` 把列表推导放入 try + 降级测试构造非法 status StageRun 触发异常 |
| 并发测试共用 AsyncSession | P1 | 单 AsyncSession 不支持并发，gather 触发 session 并发错误而非验证锁 | Task B3 并发测试改三段式独立 session：seed session 提交关闭 → 每 worker 独立 session 重新加载 capa → check session 回读 |
| E2E 无可观察 retry_count | P1 | CAPAResponse/CAPAReport 不暴露 d4_retry_count，e2e 无法回读断言 | Task B4 CAPAResponse 加 `d4_retry_count: int` + 前端 CAPAReport 类型 + 响应测试；Task B7 e2e 经 GET/advance 回读 |

另：Task B6 命名修正 `api`→`client`、`advanceCapa`→`advanceCAPA`（既有符号）。

15 项计划评审全部闭合。