# 质量趋势 AI 解读 Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在自定义仪表盘中实现一个质量趋势 AI 解读 Widget，默认展示规则摘要，用户点击后按需调用 LLM 生成结构化深度解读。

**Architecture:** 复用现有 dashboard widget 体系与 `LLMProvider` 抽象，新增 `quality_trend_ai_summary` widget type。规则摘要实时聚合 SPC/CAPA/FMEA 核心闭环指标；AI 解读通过 `/api/dashboard/widgets/quality-trend/interpret` 按需触发。权限先由 dashboard 可见性控制 Widget 布局，再按 `spc/capa/fmea` 模块 view 权限过滤 evidence；未配置 LLM 时仅返回规则摘要。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 | React 18 + TypeScript + Ant Design 5 | Python tests + frontend manual build/lint verification

---

## File Structure

### Backend (new)
| File | Responsibility |
|------|----------------|
| `backend/app/schemas/quality_trend.py` | QualityTrend schema 定义：summary / metadata / interpretation payload |
| `backend/app/services/quality_trend_service.py` | 趋势聚合、规则摘要、hash 计算、限流、LLM prompt 构造、解读生成与缓存 |
| `backend/tests/test_quality_trend_service.py` | 服务层单测：权限过滤、数据不足、LLM 失败、缓存与限流 |

### Backend (modify)
| File | Change |
|------|--------|
| `backend/app/schemas/dashboard_layout.py` | `DashboardWidgetsResponse` 增加 `quality_trend` 字段 |
| `backend/app/services/dashboard_service.py` | `WIDGET_MODULE_MAP` / `WIDGET_MIN_SIZES` 增加 `quality_trend_ai_summary`；`get_widgets_data` 增加聚合分支；`get_recent_actions` 过滤 `AI_TREND_INTERPRET` |
| `backend/app/api/dashboard.py` | `get_widgets` 增加模块权限判断并透传 `allowed_modules`；新增 `POST /widgets/quality-trend/interpret` |
| `backend/app/models/audit.py` | 文档化 `AI_TREND_INTERPRET` 写入约定（实现侧使用现有字段） |

### Frontend (new)
| File | Responsibility |
|------|----------------|
| `frontend/src/components/dashboard/widgets/QualityTrendAIWidget.tsx` | 规则摘要展示、AI 按钮、stale 提示、解读结果渲染 |

### Frontend (modify)
| File | Change |
|------|--------|
| `frontend/src/components/dashboard/widgets/types.ts` | 扩展 `WidgetCategory` union、补充 `DashboardWidgetsData.quality_trend` 和相关接口 |
| `frontend/src/components/dashboard/widgets/registry.ts` | 注册 `quality_trend_ai_summary` widget 组件与 meta |
| `frontend/src/pages/dashboard/DashboardPage.tsx` | `createEmptyData()` 增加 `quality_trend: {}` |
| `frontend/src/api/dashboard.ts` | 新增 `interpretQualityTrend()` API 函数 |
| `frontend/src/components/dashboard/WidgetLibraryPanel.tsx` | 增加 `ai` 分类标签与默认展开支持 |

---

## Task 1: Backend Schema for Quality Trend Widget

**Files:**
- Create: `backend/app/schemas/quality_trend.py`
- Modify: `backend/app/schemas/dashboard_layout.py`
- Test: `backend/tests/test_quality_trend_service.py` (schema 验证部分)

- [ ] **Step 1: Write failing tests for summary schema**

```python
# backend/tests/test_quality_trend_service.py
import pytest
from app.schemas.quality_trend import QualityTrendMetadata, QualityTrendSummary


def test_quality_trend_summary_metadata_fields():
    summary = QualityTrendSummary(
        risk_level="medium",
        headline="SPC 异常增加",
        evidence=[{"id": "spc_alarm_count", "label": "SPC 异常告警", "value": 4, "trend": "+2", "severity": "warning"}],
        actions=[{"priority": "high", "text": "复核异常"}],
        data_window_days=30,
        generated_at="2026-06-09T00:00:00Z",
        evidence_hash="hash",
        ai_available=True,
        metadata=QualityTrendMetadata(
            omitted_modules=[],
            available_modules=["spc", "capa"],
            scope_description="产品线范围：DC-DC-100",
            selected_product_line="DC-DC-100",
        ),
    )
    assert summary.metadata.available_modules == ["spc", "capa"]
    assert summary.metadata.omitted_modules == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_quality_trend_service.py -q`
Expected: FAIL with import error / missing schema.

- [ ] **Step 3: Implement schemas**

```python
# backend/app/schemas/quality_trend.py
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "insufficient_data"]


class QualityTrendEvidence(BaseModel):
    id: str
    label: str
    value: int | float
    trend: str
    severity: Literal["info", "warning", "critical", "none"]


class QualityTrendAction(BaseModel):
    priority: Literal["low", "medium", "high"]
    text: str


class QualityTrendMetadata(BaseModel):
    omitted_modules: list[str] = Field(default_factory=list)
    available_modules: list[str] = Field(default_factory=list)
    scope_description: str = ""
    selected_product_line: str | None = None


class QualityTrendSummary(BaseModel):
    risk_level: RiskLevel
    headline: str
    evidence: list[QualityTrendEvidence]
    actions: list[QualityTrendAction]
    data_window_days: int = 30
    generated_at: str
    evidence_hash: str
    ai_available: bool
    metadata: QualityTrendMetadata = Field(default_factory=QualityTrendMetadata)


class QualityTrendInterpretation(BaseModel):
    summary: str
    possible_causes: list[str]
    impact_scope: list[str]
    recommended_actions: list[dict]
    evidence_refs: list[str]
    confidence: Literal["low", "medium", "high"]
    model: str
    evidence_hash: str
    scope_hash: str
    generated_at: str
    cached: bool = False
```

- [ ] **Step 4: Extend DashboardWidgetsResponse**

```python
# backend/app/schemas/dashboard_layout.py
from app.schemas.quality_trend import QualityTrendSummary


class DashboardWidgetsResponse(BaseModel):
    kpi: dict = Field(default_factory=dict)
    alerts: dict = Field(default_factory=dict)
    recent_actions: list = Field(default_factory=list)
    spc: dict = Field(default_factory=dict)
    msa: dict = Field(default_factory=dict)
    iqc: dict = Field(default_factory=dict)
    mes: dict = Field(default_factory=dict)
    supplier: dict = Field(default_factory=dict)
    quality_trend: dict = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_quality_trend_service.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/quality_trend.py backend/app/schemas/dashboard_layout.py backend/tests/test_quality_trend_service.py
git commit -m "feat(quality): add quality trend schema and dashboard payload field"
```

---

## Task 2: Dashboard White-List & Recent Actions Filter

**Files:**
- Modify: `backend/app/services/dashboard_service.py`
- Modify: `backend/app/api/dashboard.py`

- [ ] **Step 1: Write failing tests for widget registration and audit filtering**

```python
# backend/tests/test_quality_trend_service.py
from app.services.dashboard_service import WIDGET_MODULE_MAP, WIDGET_MIN_SIZES


def test_quality_trend_widget_registered():
    assert WIDGET_MODULE_MAP["quality_trend_ai_summary"] == "dashboard"
    assert WIDGET_MIN_SIZES["quality_trend_ai_summary"]["w"] >= 4
    assert WIDGET_MIN_SIZES["quality_trend_ai_summary"]["h"] >= 3
```

```python
# backend/tests/test_dashboard_recent_actions_filter.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from app.services.dashboard_service import get_recent_actions


@pytest.mark.anyio
async def test_recent_actions_filters_ai_trend_interpret():
    audit_logs = [
        MagicMock(
            record_id="r1",
            table_name="quality_trends",
            action="AI_TREND_INTERPRET",
            operated_at=datetime.now(timezone.utc),
            operated_by="u1",
        ),
        MagicMock(
            record_id="r2",
            table_name="fmea_documents",
            action="UPDATE",
            operated_at=datetime.now(timezone.utc),
            operated_by="u1",
        ),
    ]
    db = AsyncMock()
    db.execute.return_value.scalars.return_value.all.return_value = audit_logs
    db.scalar.return_value = "FMEA-2026-001"

    actions = await get_recent_actions(db, user_id="u1", limit=5)
    assert all(a["action"] != "AI_TREND_INTERPRET" for a in actions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_quality_trend_service.py tests/test_dashboard_recent_actions_filter.py -q`
Expected: FAIL

- [ ] **Step 3: Register widget type and minimum sizes**

```python
# backend/app/services/dashboard_service.py
WIDGET_MODULE_MAP = {
    **WIDGET_MODULE_MAP,
    "quality_trend_ai_summary": "dashboard",
}
WIDGET_MIN_SIZES = {
    **WIDGET_MIN_SIZES,
    "quality_trend_ai_summary": {"w": 6, "h": 4},
}
```

- [ ] **Step 4: Filter AI trend audit logs from recent actions**

```python
# backend/app/services/dashboard_service.py
async def get_recent_actions(db: AsyncSession, user_id: str, limit: int = 5) -> list[dict]:
    from app.models.audit import AuditLog

    query = (
        select(AuditLog)
        .where(AuditLog.operated_by == user_id)
        .where(AuditLog.action != "AI_TREND_INTERPRET")
        .where(AuditLog.table_name != "quality_trends")
        .order_by(AuditLog.operated_at.desc())
        .limit(limit)
    )
    ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_quality_trend_service.py tests/test_dashboard_recent_actions_filter.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard_service.py backend/tests/test_dashboard_recent_actions_filter.py backend/tests/test_quality_trend_service.py
git commit -m "feat(quality): register quality trend widget and filter ai trend audit logs"
```

---

## Task 3: Backend Trend Aggregation Service

**Files:**
- Create: `backend/app/services/quality_trend_service.py`
- Test: `backend/tests/test_quality_trend_service.py`

- [ ] **Step 1: Write failing tests for aggregation behavior**

```python
# backend/tests/test_quality_trend_service.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.services.quality_trend_service import build_quality_trend_summary


@pytest.mark.anyio
async def test_returns_insufficient_data_when_no_modules_allowed():
    summary = await build_quality_trend_summary(
        db=AsyncMock(),
        filter_codes=["DC-DC-100"],
        allowed_modules=set(),
        scope_description="产品线范围：DC-DC-100",
        selected_product_line="DC-DC-100",
    )
    assert summary.risk_level == "insufficient_data"
    assert summary.ai_available is False
    assert "spc" in summary.metadata.available_modules or summary.metadata.available_modules == []


@pytest.mark.anyio
async def test_detects_open_spc_and_capa_risk():
    db = AsyncMock()
    db.scalar.side_effect = [
        4,   # SPC current window
        1,   # SPC previous window
        2,   # SPC open alarms
        3,   # CAPA open
        2,   # CAPA overdue
        1,   # FMEA high rpn
        0,   # FMEA high rpn prev
    ]

    summary = await build_quality_trend_summary(
        db=db,
        filter_codes=["DC-DC-100"],
        allowed_modules={"spc", "capa", "fmea"},
        scope_description="产品线范围：DC-DC-100",
        selected_product_line="DC-DC-100",
    )
    assert summary.risk_level in {"medium", "high"}
    assert any(e.id == "spc_alarm_count" for e in summary.evidence)
    assert summary.ai_available is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_quality_trend_service.py -q`
Expected: FAIL

- [ ] **Step 3: Implement aggregation service**

```python
# backend/app/services/quality_trend_service.py
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.spc import SPCAlarm
from app.utils.fmea_graph import build_rpn_rows
from app.schemas.quality_trend import QualityTrendSummary, QualityTrendMetadata


WINDOW_DAYS = 30
MIN_REQUIRED_MODULES = 1
RISK_THRESHOLDS = {"medium": 2, "high": 4}


async def build_quality_trend_summary(
    db: AsyncSession,
    filter_codes: list[str],
    allowed_modules: set[str],
    scope_description: str,
    selected_product_line: str | None,
) -> QualityTrendSummary:
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=WINDOW_DAYS)
    previous_start = now - timedelta(days=WINDOW_DAYS * 2)
    omitted_modules = sorted({"spc", "capa", "fmea"} - allowed_modules)
    available_modules = sorted(allowed_modules)
    evidence = []
    actions = []
    score = 0

    if "spc" in allowed_modules:
        current_q = select(func.count()).where(SPCAlarm.triggered_at >= current_start)
        previous_q = select(func.count()).where(SPCAlarm.triggered_at >= previous_start, SPCAlarm.triggered_at < current_start)
        open_q = select(func.count()).where(SPCAlarm.status == "open", SPCAlarm.acknowledged_at.is_(None))
        if filter_codes:
            from app.models.spc import InspectionCharacteristic
            current_q = current_q.join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id).where(InspectionCharacteristic.product_line.in_(filter_codes))
            previous_q = previous_q.join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id).where(InspectionCharacteristic.product_line.in_(filter_codes))
            open_q = open_q.join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id).where(InspectionCharacteristic.product_line.in_(filter_codes))
        current_count = await db.scalar(current_q) or 0
        previous_count = await db.scalar(previous_q) or 0
        open_count = await db.scalar(open_q) or 0
        trend_delta = current_count - previous_count
        evidence.append({"id": "spc_alarm_count", "label": "SPC 异常告警", "value": current_count, "trend": f"{trend_delta:+d}", "severity": "warning" if current_count else "none"})
        if open_count:
            evidence.append({"id": "spc_open_unack", "label": "未确认告警", "value": open_count, "trend": "-", "severity": "warning"})
            actions.append({"priority": "high", "text": "优先复核未确认 SPC 异常"})
        score += max(0, trend_delta)

    if "capa" in allowed_modules:
        open_capa_q = select(func.count()).where(CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]))
        overdue_capa_q = select(func.count()).where(CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]), CAPAEightD.due_date.isnot(None), CAPAEightD.due_date < now.date())
        if filter_codes:
            open_capa_q = open_capa_q.where(CAPAEightD.product_line_code.in_(filter_codes))
            overdue_capa_q = overdue_capa_q.where(CAPAEightD.product_line_code.in_(filter_codes))
        open_capa = await db.scalar(open_capa_q) or 0
        overdue_capa = await db.scalar(overdue_capa_q) or 0
        evidence.append({"id": "capa_open_count", "label": "打开 CAPA", "value": open_capa, "trend": "-", "severity": "info" if open_capa else "none"})
        if overdue_capa:
            evidence.append({"id": "capa_overdue_count", "label": "超期 CAPA", "value": overdue_capa, "trend": "-", "severity": "warning"})
            actions.append({"priority": "high", "text": "清理超期 CAPA"})
            score += overdue_capa

    if "fmea" in allowed_modules:
        fmea_q = select(FMEADocument.fmea_id, FMEADocument.graph_data)
        if filter_codes:
            fmea_q = fmea_q.where(FMEADocument.product_line_code.in_(filter_codes))
        result = await db.execute(fmea_q)
        rows = result.all()
        high_rpn = 0
        for row in rows:
            graph = row.graph_data or {}
            for rpn_row in build_rpn_rows(graph.get("nodes", []), graph.get("edges", [])):
                rpn = rpn_row.get("severity", 0) * rpn_row.get("occurrence", 0) * rpn_row.get("detection", 0)
                if rpn >= 200:
                    high_rpn += 1
        evidence.append({"id": "high_rpn_count", "label": "高 RPN 节点", "value": high_rpn, "trend": "-", "severity": "warning" if high_rpn else "none"})
        if high_rpn:
            actions.append({"priority": "high", "text": "复核高 RPN 风险项"})
            score += high_rpn

    has_enough_data = len([m for m in available_modules if m in allowed_modules]) >= MIN_REQUIRED_MODULES and len(evidence) > 0
    risk_level = "insufficient_data"
    if has_enough_data:
        risk_level = "low"
        if score >= RISK_THRESHOLDS["high"]:
            risk_level = "high"
        elif score >= RISK_THRESHOLDS["medium"]:
            risk_level = "medium"

    if not actions:
        actions.append({"priority": "low", "text": "继续监控关键指标"})

    generated_at = datetime.now(timezone.utc).isoformat()
    metadata = QualityTrendMetadata(
        omitted_modules=omitted_modules,
        available_modules=available_modules,
        scope_description=scope_description,
        selected_product_line=selected_product_line,
    )
    summary = QualityTrendSummary(
        risk_level=risk_level,
        headline=_headline_for_level(risk_level),
        evidence=evidence,
        actions=actions,
        data_window_days=WINDOW_DAYS,
        generated_at=generated_at,
        evidence_hash=_hash_evidence(scope_description, available_modules, omitted_modules, WINDOW_DAYS, evidence, actions),
        ai_available=risk_level not in {"insufficient_data", "low"},
        metadata=metadata,
    )
    return summary


def _headline_for_level(risk_level: str) -> str:
    if risk_level == "high":
        return "质量风险明显上升"
    if risk_level == "medium":
        return "质量风险呈上升趋势"
    if risk_level == "low":
        return "质量趋势暂无明显恶化"
    return "数据不足以判断趋势"


def _hash_evidence(scope_description: str, available_modules: list[str], omitted_modules: list[str], window_days: int, evidence: list[dict], actions: list[dict]) -> str:
    payload = json.dumps({
        "scope_description": scope_description,
        "available_modules": available_modules,
        "omitted_modules": omitted_modules,
        "window_days": window_days,
        "evidence": sorted(evidence, key=lambda x: x["id"]),
        "actions": actions,
    }, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def build_scope_hash(filter_codes: list[str]) -> str:
    payload = json.dumps(filter_codes, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_quality_trend_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/quality_trend_service.py backend/tests/test_quality_trend_service.py
git commit -m "feat(quality): implement rule-based quality trend aggregation service"
```

---

## Task 4: Dashboard Widgets Integration

**Files:**
- Modify: `backend/app/services/dashboard_service.py`
- Modify: `backend/app/api/dashboard.py`

- [ ] **Step 1: Write failing test for GET /api/dashboard/widgets payload**

```python
# backend/tests/test_dashboard_quality_trend_api.py
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.anyio
async def test_dashboard_widgets_includes_quality_trend(authed_client: AsyncClient):
    response = await authed_client.get("/api/dashboard/widgets", params={"types": "quality_trend_ai_summary", "product_line": "DC-DC-100"})
    assert response.status_code == 200
    body = response.json()
    assert "quality_trend" in body
    assert "summary" in body["quality_trend"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dashboard_quality_trend_api.py -q`
Expected: FAIL

- [ ] **Step 3: Implement widget aggregation path in dashboard service**

```python
# backend/app/services/dashboard_service.py
needs_quality_trend = "quality_trend_ai_summary" in types

if needs_quality_trend:
    try:
        allowed_modules = set()
        for module in ["spc", "capa", "fmea"]:
            if await _user_can_view_module_by_key(user_id, module):
                allowed_modules.add(module)
        from app.services.quality_trend_service import build_quality_trend_summary
        summary = await build_quality_trend_summary(
            db=db,
            filter_codes=product_line_codes or [],
            allowed_modules=allowed_modules,
            scope_description=_build_scope_description(product_line_codes),
            selected_product_line=product_line_codes[0] if product_line_codes and len(product_line_codes) == 1 else None,
        )
        result["quality_trend"] = {"summary": summary.model_dump()}
    except Exception as e:
        result["errors"]["quality_trend"] = str(e)
```

- [ ] **Step 4: Add module-aware permission handling in dashboard route**

```python
# backend/app/api/dashboard.py
allowed_types = []
allowed_modules = set()
for widget_type in type_list:
    module = WIDGET_MODULE_MAP[widget_type]
    if await _user_can_view_module(user, module, db):
        allowed_types.append(widget_type)
        allowed_modules.add(module)

...
data = await dashboard_service.get_widgets_data(db, allowed_types, filter_codes, user.user_id, allowed_modules=allowed_modules)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dashboard_quality_trend_api.py tests/test_quality_trend_service.py tests/test_dashboard_recent_actions_filter.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard_service.py backend/app/api/dashboard.py backend/tests/test_dashboard_quality_trend_api.py
git commit -m "feat(quality): wire quality trend widget into dashboard api"
```

---

## Task 5: Manual AI Interpretation Endpoint

**Files:**
- Modify: `backend/app/api/dashboard.py`
- Modify: `backend/app/services/quality_trend_service.py`
- Test: `backend/tests/test_quality_trend_interpret_api.py`

- [ ] **Step 1: Write failing tests for interpret API contract**

```python
# backend/tests/test_quality_trend_interpret_api.py
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.anyio
async def test_interpret_returns_503_when_llm_not_configured(authed_client: AsyncClient):
    response = await authed_client.post("/api/dashboard/widgets/quality-trend/interpret", json={"product_line": "DC-DC-100"})
    assert response.status_code == 503


@pytest.mark.anyio
async def test_interpret_returns_success_with_fake_llm(authed_client: AsyncClient, fake_llm_provider):
    response = await authed_client.post("/api/dashboard/widgets/quality-trend/interpret", json={"product_line": "DC-DC-100"})
    assert response.status_code == 200
    body = response.json()
    assert body["evidence_hash"] != ""
    assert body["scope_hash"] != ""
    assert "cached" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_quality_trend_interpret_api.py -q`
Expected: FAIL

- [ ] **Step 3: Implement interpret service with rate limit and cache**

```python
# backend/app/services/quality_trend_service.py
_interpret_cache: dict[str, tuple[QualityTrendInterpretation, float]] = {}
_rate_limit: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60.0
RATE_LIMIT_MAX = 5
CACHE_TTL = 30 * 60
```

```python
async def interpret_quality_trend(
    db: AsyncSession,
    user_id: str,
    llm_provider,
    filter_codes: list[str],
    allowed_modules: set[str],
    scope_description: str,
    selected_product_line: str | None,
    scope_hash: str,
) -> QualityTrendInterpretation:
    if llm_provider is None:
        raise LLMNotConfiguredError()
    _enforce_rate_limit(user_id)
    summary = await build_quality_trend_summary(db, filter_codes, allowed_modules, scope_description, selected_product_line)
    cache_key = f"{scope_hash}:{summary.data_window_days}:{summary.evidence_hash}"
    cached = _get_cached_interpretation(cache_key)
    if cached:
        return cached
    prompt = _build_interpret_prompt(summary, allowed_modules, scope_description)
    raw = await llm_provider.complete(prompt, {})
    result = _parse_interpretation(raw, summary, scope_hash)
    _set_cached_interpretation(cache_key, result)
    return result
```

- [ ] **Step 4: Add POST /interpret endpoint**

```python
# backend/app/api/dashboard.py
@router.post("/widgets/quality-trend/interpret")
async def interpret_quality_trend(...):
    ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_quality_trend_interpret_api.py tests/test_quality_trend_service.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/dashboard.py backend/app/services/quality_trend_service.py backend/tests/test_quality_trend_interpret_api.py
git commit -m "feat(quality): add manual quality trend interpretation endpoint"
```

---

## Task 6: Frontend Types, Registry, and Empty Data

**Files:**
- Modify: `frontend/src/components/dashboard/widgets/types.ts`
- Modify: `frontend/src/components/dashboard/widgets/registry.ts`
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/api/dashboard.ts`

- [ ] **Step 1: Extend frontend types**

```typescript
// frontend/src/components/dashboard/widgets/types.ts
export type WidgetCategory = "kpi" | "alert" | "chart" | "list" | "ai";

export interface QualityTrendMetadata {
  omitted_modules?: string[];
  available_modules?: string[];
  scope_description?: string;
  selected_product_line?: string | null;
}

export interface QualityTrendSummary {
  risk_level?: string;
  headline?: string;
  evidence?: Array<{ id?: string; label?: string; value?: number; trend?: string; severity?: string }>;
  actions?: Array<{ priority?: string; text?: string }>;
  data_window_days?: number;
  generated_at?: string;
  evidence_hash?: string;
  ai_available?: boolean;
  metadata?: QualityTrendMetadata;
}

export interface DashboardWidgetsData {
  ...
  quality_trend?: { summary?: QualityTrendSummary };
  errors: Record<string, string>;
}
```

- [ ] **Step 2: Register widget component**

```typescript
// frontend/src/components/dashboard/widgets/registry.ts
{
  type: "quality_trend_ai_summary",
  name: "质量趋势 AI 解读",
  category: "ai",
  defaultSize: { w: 8, h: 5 },
  minSize: { w: 6, h: 4 },
  module: "dashboard",
}
```

- [ ] **Step 3: Add API function**

```typescript
// frontend/src/api/dashboard.ts
export async function interpretQualityTrend(params: { product_line?: string }) {
  const { data } = await api.post(`/dashboard/widgets/quality-trend/interpret`, params);
  return data as QualityTrendInterpretation;
}
```

- [ ] **Step 4: Extend createEmptyData**

```typescript
// frontend/src/pages/dashboard/DashboardPage.tsx
function createEmptyData(): DashboardWidgetsData {
  return {
    ...
    quality_trend: {},
    errors: {},
  };
}
```

- [ ] **Step 5: Build & lint to verify**

Run: `cd frontend && npm run build && npm run lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dashboard/widgets/types.ts frontend/src/components/dashboard/widgets/registry.ts frontend/src/pages/dashboard/DashboardPage.tsx frontend/src/api/dashboard.ts
git commit -m "feat(quality): add frontend types and registry for quality trend widget"
```

---

## Task 7: Quality Trend AI Widget UI

**Files:**
- Create: `frontend/src/components/dashboard/widgets/QualityTrendAIWidget.tsx`

- [ ] **Step 1: Implement widget with rule summary, loading, stale, and interpret state**

```typescript
// frontend/src/components/dashboard/widgets/QualityTrendAIWidget.tsx
import { useMemo, useState } from "react";
import { Alert, Button, List, Space, Tag, Typography } from "antd";
import type { WidgetProps } from "./types";
import { interpretQualityTrend } from "../../../api/dashboard";
import { useProductLineStore } from "../../../store/productLineStore";

const riskColor: Record<string, string> = {
  high: "red",
  medium: "orange",
  low: "green",
  insufficient_data: "default",
};

export default function QualityTrendAIWidget({ data, loading, error, onRetry }: WidgetProps) {
  const summary = data.quality_trend?.summary;
  const productLine = useProductLineStore((s) => s.selected);
  const [busy, setBusy] = useState(false);
  const [interpretation, setInterpretation] = useState<any>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  const isStale = useMemo(() => {
    if (!summary?.evidence_hash || !interpretation?.evidence_hash) return false;
    return summary.evidence_hash !== interpretation.evidence_hash;
  }, [summary?.evidence_hash, interpretation?.evidence_hash]);

  const handleInterpret = async () => {
    if (!summary?.ai_available) return;
    setBusy(true);
    setAiError(null);
    try {
      const result = await interpretQualityTrend({ product_line: productLine || undefined });
      setInterpretation(result);
    } catch {
      setAiError("AI 解读暂不可用，请稍后重试");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div>加载中...</div>;
  if (error) return <div>加载失败 <Button size="small" onClick={onRetry}>重试</Button></div>;
  if (!summary) return <div>暂无趋势数据</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Space>
        <Tag color={riskColor[summary.risk_level] ?? "default"}>{summary.risk_level}</Tag>
        <Typography.Text strong>{summary.headline}</Typography.Text>
      </Space>

      {summary.metadata?.omitted_modules && summary.metadata.omitted_modules.length > 0 && (
        <Alert
          type="info"
          showIcon
          message={`当前视图缺少模块权限，已忽略：${summary.metadata.omitted_modules.join(", ")}`}
        />
      )}

      <List
        size="small"
        header={<div>关键证据</div>}
        dataSource={summary.evidence ?? []}
        renderItem={(item) => (
          <List.Item>
            {item.label}: {item.value}（趋势：{item.trend}）
          </List.Item>
        )}
      />

      <List
        size="small"
        header={<div>建议动作</div>}
        dataSource={summary.actions ?? []}
        renderItem={(item) => (
          <List.Item>
            [{item.priority}] {item.text}
          </List.Item>
        )}
      />

      <Space>
        <Button type="primary" loading={busy} disabled={!summary.ai_available} onClick={handleInterpret}>
          AI 深度解读
        </Button>
        {!summary.ai_available && <Typography.Text type="secondary">未配置 LLM 或数据不足时不可用</Typography.Text>}
      </Space>

      {isStale && (
        <Alert
          type="warning"
          showIcon
          message="数据已更新，点击重新生成 AI 解读"
        />
      )}

      {aiError && <Alert type="error" showIcon message={aiError} />}

      {interpretation && (
        <div style={{ marginTop: 8 }}>
          <Typography.Paragraph>{interpretation.summary}</Typography.Paragraph>
          <Typography.Text type="secondary">置信度：{interpretation.confidence}，缓存：{interpretation.cached ? "是" : "否"}</Typography.Text>
        </div>
      )}
    </div>
  );
}
```

实现要求：
- 默认展示 `summary.headline`、risk badge、evidence list、actions
- AI 按钮受 `ai_available` 和 loading 控制
- 当 `summary.evidence_hash` 与 interpret 响应中的 `evidence_hash` 不一致时显示过期提示
- 调用失败显示“AI 解读暂不可用，请稍后重试”，不隐藏规则摘要
- 必须展示 `metadata.omitted_modules`（若有）作为提示

- [ ] **Step 2: Build & lint to verify**

Run: `cd frontend && npm run build && npm run lint`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/widgets/QualityTrendAIWidget.tsx
git commit -m "feat(quality): add quality trend ai widget ui"
```

---

## Task 8: Widget Library Category & Integration Test

**Files:**
- Modify: `frontend/src/components/dashboard/WidgetLibraryPanel.tsx`
- Test: `frontend manual + backend api tests`

- [ ] **Step 1: Add ai category and default expand support**

```typescript
// frontend/src/components/dashboard/WidgetLibraryPanel.tsx
categoryLabels: {
  ...
  ai: "AI/高级分析",
}
```

- [ ] **Step 2: Run integration verification**

Run:
- `cd backend && python -m pytest tests/test_dashboard_quality_trend_api.py tests/test_quality_trend_interpret_api.py -q`
- `cd frontend && npm run build`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/WidgetLibraryPanel.tsx
git commit -m "feat(quality): add ai category to widget library panel"
```

---

## Task 9: Spec Compliance Verification

**Files:**
- Verify only: `docs/superpowers/specs/2026-06-09-quality-trend-ai-interpretation-widget-design.md`

- [ ] **Step 1: Verify backend spec coverage**

Check:
- dashboard 权限 + spc/capa/fmea 模块权限过滤
- omitted_modules 进入 metadata、prompt、hash
- scope_hash 用于缓存 key
- LLM 未配置返回 503
- LLM 解析失败返回 502
- 数据不足 POST 返回 422
- AI audit 写入 `quality_trends` 并过滤出 recent actions

- [ ] **Step 2: Verify frontend spec coverage**

Check:
- Widget 出现在 `ai` 分类
- ai_available=false 时禁用按钮
- evidence_hash stale 时提示过期
- POST 响应展示 `cached`

- [ ] **Step 3: Commit final plan doc only**

```bash
git add docs/superpowers/plans/2026-06-09-quality-trend-ai-interpretation-widget-plan.md
git commit -m "docs: add quality trend ai widget implementation plan"
```

---

## Commit Strategy

| After Task | Commit |
|---|---|
| 1 | Schema and payload model |
| 2 | Widget white-list and recent actions filter |
| 3 | Rule-based aggregation service |
| 4 | Dashboard widget integration |
| 5 | Manual interpret endpoint |
| 6 | Frontend types + registry + API |
| 7 | Widget UI |
| 8 | Widget library category |
| 9 | Plan doc |

---

## Verification Commands

### Backend
```bash
cd backend
python -m pytest tests/test_quality_trend_service.py tests/test_dashboard_recent_actions_filter.py tests/test_dashboard_quality_trend_api.py tests/test_quality_trend_interpret_api.py -q
```

### Frontend
```bash
cd frontend
npm run build
npm run lint
```
