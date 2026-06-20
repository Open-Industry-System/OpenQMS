# DFMEA 向导 5T「工具 / 趋势」推荐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 DFMEA 向导 Step 0 的「工具」「趋势」字段增加多选推荐——静态预设快选 + 可选 ✨AI 推荐，存为「、」分隔 string。

**Architecture:** 新增 `wizardScopeTokens` 工具做 string↔string[] 序列化；新增复用组件 `ScopeTagField`（antd Select mode=tags + 未选中预设快选 chip + ✨AI 按钮，复用现有 `/fmea/{id}/recommend` 端点）；后端在 `RecommendRequest.trigger_type` 加 `dfmea_tool`/`dfmea_trend`、加两段 prompt 模板、并在推荐端点为新 trigger 适配短输入 anchor（否则 AI 永不触发）。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.29 + Vite + vitest 4（前端）| FastAPI + Pydantic v2 + pytest-asyncio `asyncio_mode=auto`（后端）

## Global Constraints

- 5T「工具/趋势」存盘为「、」(顿号) 分隔 `string`，内存为 `string[]`；多选。
- ✨AI 按钮为显式触发（不做输入防抖）；请求 `scope: "current_product_line"`、`include_graph: false`；AI 建议点击才加入（不自动填）。
- 后端**不新建 API 端点**；共三处改动：① `trigger_type` Literal ② `PROMPT_TEMPLATES` ③ 推荐端点 anchor。
- UI：antd `Select mode="tags"`（已选项为控件内 tag，移除用 tag 原生 ×）+ 下方仅显示**未选中**预设作为 `+ add` 快选 chip + ✨AI 按钮 + 紫色 AI 建议 chip。
- 中文 UI 主，en-US 镜像；预设经 i18n 数组取用，TS 中需 `as string[]` 强转。
- `fmea` 类型为 `FMEADocument | null`，访问其字段用 `?.` 与 `?? ""`。
- **不改动**：孤儿组件 `GenerationWizard.tsx`；team / timeframe / task 字段；wizardScope 存盘结构；推荐端点与 `SmartSuggestionDropdown` 本身。
- 提交规范：`feat(dfmea):` / `feat(dfmea):` 前端，`feat(fmea):` / `feat(recommend):` 后端；每个任务一个提交。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `frontend/src/utils/wizardScopeTokens.ts` | 「、」分隔 string ↔ string[] 序列化（split/trim/去空/去重/保序） | Create |
| `frontend/src/utils/wizardScopeTokens.test.ts` | 工具函数单测 | Create |
| `backend/app/schemas/recommendation.py` | `trigger_type` Literal 增 `dfmea_tool`/`dfmea_trend` | Modify |
| `backend/app/api/fmea.py` | 新增模块级 `_recommend_anchor` 并在推荐端点使用 | Modify |
| `backend/app/services/recommendation_service.py` | `PROMPT_TEMPLATES` 增两模板 | Modify |
| `backend/tests/test_dfmea_tool_trend_recommendation.py` | 后端 anchor + prompt 模板单测 | Create |
| `frontend/src/components/dfmea/ScopeTagField.tsx` | 复用组件（Select tags + 预设快选 + AI 按钮） | Create |
| `frontend/src/components/dfmea/ScopeTagField.test.tsx` | 组件单测 | Create |
| `frontend/src/locales/zh-CN/dfmea.json` | `wizard.scope` 增预设数组 + AI 按钮文案 | Modify |
| `frontend/src/locales/en-US/dfmea.json` | 同上英文镜像 | Modify |
| `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` | `renderStep0` 工具/趋势换 `ScopeTagField` | Modify |

---

### Task 1: wizardScopeTokens 序列化工具

**Files:**
- Create: `frontend/src/utils/wizardScopeTokens.ts`
- Test: `frontend/src/utils/wizardScopeTokens.test.ts`

**Interfaces:**
- Produces: `parseScopeTokens(s: string | null | undefined): string[]`、`stringifyScopeTokens(arr: string[] | null | undefined): string`（Task 4 的 `ScopeTagField` 依赖这两个）

- [ ] **Step 1: 写失败测试**

`frontend/src/utils/wizardScopeTokens.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { parseScopeTokens, stringifyScopeTokens } from "./wizardScopeTokens";

describe("parseScopeTokens", () => {
  it("splits on 、", () => {
    expect(parseScopeTokens("边界图、P图、接口矩阵")).toEqual(["边界图", "P图", "接口矩阵"]);
  });
  it("splits on ASCII and fullwidth , ; ，；", () => {
    expect(parseScopeTokens("a,b；c，d;e")).toEqual(["a", "b", "c", "d", "e"]);
  });
  it("trims tokens", () => {
    expect(parseScopeTokens(" 边界图 、 P图 ")).toEqual(["边界图", "P图"]);
  });
  it("dedupes preserving first-seen order", () => {
    expect(parseScopeTokens("边界图、P图、边界图")).toEqual(["边界图", "P图"]);
  });
  it("returns [] for empty/whitespace/null/undefined", () => {
    expect(parseScopeTokens("")).toEqual([]);
    expect(parseScopeTokens("   ")).toEqual([]);
    expect(parseScopeTokens(null)).toEqual([]);
    expect(parseScopeTokens(undefined)).toEqual([]);
  });
  it("returns a single value as one-element array", () => {
    expect(parseScopeTokens("FMEA模板")).toEqual(["FMEA模板"]);
  });
});

describe("stringifyScopeTokens", () => {
  it("joins with 、", () => {
    expect(stringifyScopeTokens(["边界图", "P图"])).toBe("边界图、P图");
  });
  it("returns '' for empty/null/undefined", () => {
    expect(stringifyScopeTokens([])).toBe("");
    expect(stringifyScopeTokens(null)).toBe("");
    expect(stringifyScopeTokens(undefined)).toBe("");
  });
  it("trims and drops empty tokens", () => {
    expect(stringifyScopeTokens([" 边界图 ", "", "P图"])).toBe("边界图、P图");
  });
  it("dedupes preserving first-seen order", () => {
    expect(stringifyScopeTokens(["边界图", "P图", "边界图"])).toBe("边界图、P图");
  });
  it("round-trips via parse", () => {
    const s = "边界图、P图、接口矩阵";
    expect(stringifyScopeTokens(parseScopeTokens(s))).toBe(s);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test -- --run src/utils/wizardScopeTokens.test.ts`
Expected: FAIL — "Failed to resolve import … wizardScopeTokens"（模块尚未创建）。

- [ ] **Step 3: 写最小实现**

`frontend/src/utils/wizardScopeTokens.ts`:

```ts
/**
 * DFMEA 向导 5T「工具/趋势」字段的 token 序列化工具。
 * 存盘为「、」(顿号) 分隔的 string；内存为 string[] 供 antd Select mode="tags" 使用。
 * 双向都做 trim、去空、去重（保持首次出现顺序），避免「手输 + chip toggle + AI chip」产生重复 tag。
 */

const SEPARATOR = "、";
const SPLIT_RE = /[、,;，；]/;

/** 「、,;，；」分隔的 string → 去空去重保序的 string[]。 */
export function parseScopeTokens(s: string | null | undefined): string[] {
  if (!s) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of s.split(SPLIT_RE)) {
    const tok = raw.trim();
    if (!tok || seen.has(tok)) continue;
    seen.add(tok);
    out.push(tok);
  }
  return out;
}

/** string[] → 「、」分隔的 string（同样 trim、去空、去重保序）。 */
export function stringifyScopeTokens(arr: string[] | null | undefined): string {
  if (!arr || arr.length === 0) return "";
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of arr) {
    const tok = raw.trim();
    if (!tok || seen.has(tok)) continue;
    seen.add(tok);
    out.push(tok);
  }
  return out.join(SEPARATOR);
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test -- --run src/utils/wizardScopeTokens.test.ts`
Expected: PASS（全部用例绿）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/utils/wizardScopeTokens.ts frontend/src/utils/wizardScopeTokens.test.ts
git commit -m "feat(dfmea): wizardScopeTokens helper for 5T tool/trend delimited-string<->array"
```

---

### Task 2: 后端 — 接受新 trigger + 短输入 anchor 适配（关键修复）

**Files:**
- Modify: `backend/app/schemas/recommendation.py:7-9`
- Modify: `backend/app/api/fmea.py`（新增模块级 `_recommend_anchor`；替换 289–292 行的 inline anchor）
- Test: `backend/tests/test_dfmea_tool_trend_recommendation.py`（新建）

**Interfaces:**
- Produces: `RecommendRequest.trigger_type` 现接受 `"dfmea_tool"` | `"dfmea_trend"`；`_recommend_anchor(trigger_type: str, context: dict) -> str`（模块级纯函数）

**背景：** 当前 `recommend()` 端点（`api/fmea.py` 约 289–298 行）对非 `failure_mode` 的 trigger，anchor 只取 `failure_mode or input_text`；本组件只传 `fmea_title/product_line_code/task/team`，二者都没有 → anchor 为空 → `len < 2` 提前返回空建议，**请求到不了 `RecommendationService`**，AI 永不触发。本任务修复。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_dfmea_tool_trend_recommendation.py`:

```python
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

from app.api.fmea import _recommend_anchor


class TestRecommendAnchor:
    def test_failure_mode_uses_function_description(self):
        assert _recommend_anchor("failure_mode", {"function_description": "电压采集"}) == "电压采集"

    def test_failure_mode_falls_back_to_input_text(self):
        assert _recommend_anchor("failure_mode", {"input_text": "采集"}) == "采集"

    def test_empty_stored_key_does_not_gate_other_filled_field(self):
        # 空的 function_description 不能挡住已填的 input_text（`or` 链式回退）
        assert _recommend_anchor("failure_mode", {"function_description": "", "input_text": "采集"}) == "采集"

    def test_dfmea_tool_uses_task(self):
        assert _recommend_anchor("dfmea_tool", {"task": "分析DC-DC转换器"}) == "分析DC-DC转换器"

    def test_dfmea_trend_falls_back_to_title(self):
        assert _recommend_anchor("dfmea_trend", {"fmea_title": "DC-DC转换器设计FMEA"}) == "DC-DC转换器设计FMEA"

    def test_dfmea_tool_falls_back_to_team(self):
        assert _recommend_anchor("dfmea_tool", {"team": "质量小组"}) == "质量小组"

    def test_dfmea_trigger_input_text_last_resort(self):
        assert _recommend_anchor("dfmea_trend", {"input_text": "客户投诉"}) == "客户投诉"

    def test_dfmea_tool_empty_when_no_context(self):
        assert _recommend_anchor("dfmea_tool", {}) == ""

    def test_other_trigger_uses_failure_mode(self):
        assert _recommend_anchor("failure_effect", {"failure_mode": "焊缝气孔"}) == "焊缝气孔"

    def test_other_trigger_empty_when_no_failure_mode(self):
        assert _recommend_anchor("optimization", {}) == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_dfmea_tool_trend_recommendation.py -v`
Expected: FAIL — `ImportError: cannot import name '_recommend_anchor' from 'app.api.fmea'`。

- [ ] **Step 3: 实现 — schema Literal + anchor helper + 端点接线**

3a. 修改 `backend/app/schemas/recommendation.py:7-9`，把：

```python
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization"
    ]
```

改为：

```python
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization",
        "dfmea_tool", "dfmea_trend",
    ]
```

3b. 在 `backend/app/api/fmea.py` 中、`@router.post("/{fmea_id}/recommend", ...)` 之前（例如在 import 区之后、第一个 `@router` 之前，或紧邻该端点上方）新增模块级纯函数：

```python
def _recommend_anchor(trigger_type: str, context: dict) -> str:
    """短输入守卫的 anchor 文本；无可用 anchor 时返回 ''。

    failure_mode 取自 function_description；dfmea_tool/dfmea_trend 取自 5T 范围字段
    （task → title → team）；其余 trigger 取自 failure_mode。input_text 是所有 trigger
    的最后兜底。

    NOTE: dict.get(k, default) 在存储值为 "" 时也返回 ""，故用 `or` 链式回退，否则
    一个空的 function_description 键会挡住已填的 failure_mode/input_text。
    """
    if trigger_type == "failure_mode":
        return context.get("function_description") or context.get("input_text") or ""
    if trigger_type in ("dfmea_tool", "dfmea_trend"):
        return (
            context.get("task")
            or context.get("fmea_title")
            or context.get("team")
            or context.get("input_text")
            or ""
        )
    return context.get("failure_mode") or context.get("input_text") or ""
```

3c. 把 `backend/app/api/fmea.py` 中端点内当前的 anchor 代码（约 289–292 行）：

```python
    if request.trigger_type == "failure_mode":
        anchor = request.context.get("function_description") or request.context.get("input_text") or ""
    else:
        anchor = request.context.get("failure_mode") or request.context.get("input_text") or ""
```

替换为：

```python
    anchor = _recommend_anchor(request.trigger_type, request.context)
```

（其后的 `if len(anchor) < 2: return RecommendResponse(...)` 不变。）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_dfmea_tool_trend_recommendation.py -v`
Expected: PASS（全部 10 个 anchor 用例绿）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/schemas/recommendation.py backend/app/api/fmea.py backend/tests/test_dfmea_tool_trend_recommendation.py
git commit -m "feat(recommend): accept dfmea_tool/trend triggers + short-input anchor fix"
```

---

### Task 3: 后端 — dfmea_tool/trend prompt 模板

**Files:**
- Modify: `backend/app/services/recommendation_service.py`（`PROMPT_TEMPLATES` dict，约 248 行起，在 `"optimization"` 条目之后、dict 闭合 `}` 之前加两键）
- Test: 追加到 `backend/tests/test_dfmea_tool_trend_recommendation.py`

**Interfaces:**
- Produces: `PROMPT_TEMPLATES["dfmea_tool"]`、`PROMPT_TEMPLATES["dfmea_trend"]`（`_build_prompt` 通过 `format_map` 填占位符 `{fmea_title}` / `{product_line_code}` / `{task}` / `{team}` / `{historical_patterns}`）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_dfmea_tool_trend_recommendation.py` 末尾追加：

```python
from app.services.recommendation_service import RecommendationService


class StubGraphRepo:
    async def find_similar_nodes_advanced(self, **kwargs):
        return []

    async def get_impact_chain(self, *a, **kw):
        return {"nodes": [], "edges": []}

    async def get_cause_chain(self, *a, **kw):
        return {"nodes": [], "edges": []}

    async def get_cross_fmea_stats(self, *a, **kw):
        return {}

    async def get_global_stats(self):
        return {}

    async def analyze_change_impact(self, *a, **kw):
        from app.schemas.change_impact import ChangeImpactResult, ImpactSummary
        return ChangeImpactResult(affected_nodes=[], summary=ImpactSummary(
            total_affected=0, failure_modes_affected=0, controls_affected=0,
            ap_upgraded_count=0, max_hop_distance=0,
        ))


class TestBuildPromptForToolTrend:
    def _svc(self):
        return RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())

    def test_tool_template_fills_placeholders(self):
        prompt = self._svc()._build_prompt("dfmea_tool", {
            "fmea_title": "DC-DC转换器设计FMEA",
            "product_line_code": "DC-DC-100",
            "task": "分析电压采集功能",
            "team": "质量小组",
        })
        assert "DC-DC转换器设计FMEA" in prompt
        assert "DC-DC-100" in prompt
        assert "分析电压采集功能" in prompt
        assert "质量小组" in prompt
        # 无残留占位符
        assert "{fmea_title}" not in prompt
        assert "{task}" not in prompt
        assert "{product_line_code}" not in prompt
        assert "{team}" not in prompt

    def test_trend_template_fills_placeholders(self):
        prompt = self._svc()._build_prompt("dfmea_trend", {
            "fmea_title": "DC-DC转换器设计FMEA",
            "product_line_code": "DC-DC-100",
            "task": "分析电压采集功能",
        })
        assert "DC-DC转换器设计FMEA" in prompt
        assert "DC-DC-100" in prompt
        assert "分析电压采集功能" in prompt
        assert "{fmea_title}" not in prompt
        assert "{task}" not in prompt
        assert "{product_line_code}" not in prompt

    def test_missing_context_does_not_raise_and_keeps_body(self):
        # _SafeDict 对缺失键返回 ""，不得抛 KeyError
        prompt = self._svc()._build_prompt("dfmea_tool", {})
        assert "分析工具" in prompt  # 模板正文仍在
        assert "{task}" not in prompt


# --- recommend() 集成：验证新 trigger 走完整链路 + source 分支（spec §9） ---
# 通过 monkeypatch 绕过 db（_get_fmea_or_404 / _get_cached / _assemble_context /
# _cache_result）与权限（get_user_permission），直接驱动 recommend() 逻辑。
# RuleEngine.evaluate 对未知 trigger 返回空、quality="generic"（已核实
# recommendation_service.py:138-140），不抛异常，故无需 patch rules。
from unittest.mock import AsyncMock
import uuid as _uuid

from app.schemas.recommendation import RecommendRequest
from app.core.permissions import PermissionLevel


class _StubFmea:
    def __init__(self):
        self.id = _uuid.uuid4()
        self.product_line_code = "DC-DC-100"
        self.fmea_type = "DFMEA"
        self.title = "DC-DC转换器设计FMEA"
        self.factory_id = _uuid.uuid4()


class _OkLlm:
    async def complete(self, prompt, kwargs):
        return {"suggestions": [{"name": "边界图", "confidence": 0.85, "explanation": "适合结构分析"}]}


class _ThrowLlm:
    async def complete(self, prompt, kwargs):
        raise RuntimeError("llm boom")


class TestRecommendIntegrationForToolTrend:
    """dfmea_tool/trend 真正走完 recommend()：规则→（可选）LLM→source 分支。"""

    def _svc(self, llm):
        return RecommendationService(db=None, llm_provider=llm, graph_repo=StubGraphRepo())

    def _patch(self, svc, monkeypatch):
        fmea = _StubFmea()
        monkeypatch.setattr(svc, "_get_fmea_or_404", AsyncMock(return_value=fmea))
        monkeypatch.setattr(svc, "_get_cached", AsyncMock(return_value=None))
        monkeypatch.setattr(svc, "_assemble_context", AsyncMock(return_value={}))
        monkeypatch.setattr(svc, "_cache_result", AsyncMock())
        monkeypatch.setattr(
            "app.core.permissions.get_user_permission",
            AsyncMock(return_value=PermissionLevel.VIEW),
        )
        return fmea

    async def test_dfmea_tool_with_llm_returns_suggestions(self, monkeypatch):
        svc = self._svc(_OkLlm())
        fmea = self._patch(svc, monkeypatch)
        req = RecommendRequest(
            trigger_type="dfmea_tool",
            context={"task": "分析DC-DC转换器", "fmea_title": fmea.title},
            scope="current_product_line",
            include_graph=False,
        )
        res = await svc.recommend(fmea.id, req, user=object())
        assert any(s.name == "边界图" for s in res.suggestions)
        assert res.source in ("hybrid", "graph_enriched")

    async def test_dfmea_tool_no_llm_returns_empty_with_source_rule(self, monkeypatch):
        svc = self._svc(None)
        fmea = self._patch(svc, monkeypatch)
        req = RecommendRequest(
            trigger_type="dfmea_tool",
            context={"task": "分析DC-DC转换器"},
            scope="current_product_line",
            include_graph=False,
        )
        res = await svc.recommend(fmea.id, req, user=object())
        assert res.suggestions == []
        assert res.source == "rule"

    async def test_dfmea_trend_llm_failure_returns_rule_fallback(self, monkeypatch):
        svc = self._svc(_ThrowLlm())
        fmea = self._patch(svc, monkeypatch)
        req = RecommendRequest(
            trigger_type="dfmea_trend",
            context={"task": "分析DC-DC转换器"},
            scope="current_product_line",
            include_graph=False,
        )
        res = await svc.recommend(fmea.id, req, user=object())
        assert res.source == "rule_fallback"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_dfmea_tool_trend_recommendation.py::TestBuildPromptForToolTrend -v`
Expected: FAIL — `_build_prompt` 对未知 trigger 返回空串（模板不存在），`"分析工具" in prompt` 不成立。

- [ ] **Step 3: 实现 — 加两段 prompt 模板**

在 `backend/app/services/recommendation_service.py` 的 `PROMPT_TEMPLATES` dict 中，找到 `"optimization"` 条目结束的 `"""\n` 之后、dict 闭合 `}` 之前，加入：

```python
    "dfmea_tool": """你是资深DFMEA(设计FMEA)工程师，精通AIAG-VDA方法论。

【任务】为下方DFMEA分析推荐 3-5 个合适的「分析工具/方法」。
【工具定义】用于结构/功能/接口/失效分析的方法与图样，例如边界图、P图(参数图)、接口矩阵、功能分析、故障树(FTA)等。
【方向约束】推荐具体、可执行的方法或图样名称，不要泛泛的"质量工具"。

【当前上下文】
- FMEA 标题: {fmea_title}
- 产品线: {product_line_code}
- 分析任务: {task}
- 团队: {team}

【历史相似案例】
{historical_patterns}

【示例】分析工具: 边界图 / P图(参数图) / 接口矩阵 / 功能分析 / 故障树分析(FTA)

【要求】与当前任务/产品直接相关，便于据此开展结构分析与功能分析。
返回 JSON：
{{"suggestions": [{{"name": "工具/方法名称", "confidence": 0.0-1.0, "explanation": "为何适合当前DFMEA分析"}}]}}
""",
    "dfmea_trend": """你是资深DFMEA(设计FMEA)工程师，精通AIAG-VDA方法论。

【任务】为下方DFMEA分析推荐 3-5 个「趋势数据/信息源」。
【趋势定义】指导本次分析的输入信息与历史数据来源，例如历史FMEA、售后/现场故障数据、客户投诉、CAPA记录、召回/法规数据等。
【方向约束】推荐具体的数据源类别，便于据此收集分析输入。

【当前上下文】
- FMEA 标题: {fmea_title}
- 产品线: {product_line_code}
- 分析任务: {task}
- 团队: {team}

【历史相似案例】
{historical_patterns}

【示例】趋势数据: 历史FMEA / 售后现场故障数据 / 客户投诉 / CAPA记录 / 召回法规数据

【要求】与当前产品线/任务相关、能指导风险识别的数据源。
返回 JSON：
{{"suggestions": [{{"name": "趋势数据/信息源", "confidence": 0.0-1.0, "explanation": "为何该数据源对本次分析有价值"}}]}}
""",
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_dfmea_tool_trend_recommendation.py -v`
Expected: PASS（anchor + build_prompt + recommend() 集成全部绿；asyncio_mode=auto 自动运行 async 用例）。

- [ ] **Step 5: 回归既有推荐测试**

Run: `cd backend && pytest tests/test_recommendation_service.py -v`
Expected: PASS（既有用例不受影响）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_dfmea_tool_trend_recommendation.py
git commit -m "feat(recommend): dfmea_tool/trend prompt templates"
```

---

### Task 4: 前端 — ScopeTagField 复用组件

**Files:**
- Create: `frontend/src/components/dfmea/ScopeTagField.tsx`
- Test: `frontend/src/components/dfmea/ScopeTagField.test.tsx`

**Interfaces:**
- Consumes: `parseScopeTokens` / `stringifyScopeTokens`（Task 1）、`getRecommendations`（`frontend/src/api/recommendation.ts`，已存在）
- Produces: 默认导出 `ScopeTagField`，props `{ value: string; onChange: (v: string) => void; presets: string[]; triggerType: "dfmea_tool" | "dfmea_trend"; fmeaId: string; context: Record<string, unknown> }`（Task 6 依赖）

**UX 决策（实现 §5 的 Select-tags 形态）：** 已选项作为 tag 显示在 `Select` 控件内，移除走 tag 原生 ×（antd 内建，上游已测）；下方「快选」仅渲染**未选中**预设为 `+ 名称` chip（点击即加入并从快选行消失），这忠实呈现已批准的 Select-tags 预览（选中项在控件内、未选中项在下方）。

**异步 stale 处理：** ✨AI 请求是异步的，返回前用户可能已改动选择。用 `useRef` 持有最新 `value`，回调里用 `parseScopeTokens(valueRef.current)` 重新计算「已选集合」来过滤 AI 建议，避免用 click 时的旧 `tokenSet`。点击 AI chip 添加时用的是当前 render 的 `tokens`（chip onClick 每次 render 重建，天然最新），故无需额外处理。

**Loading 文案：** AI 按钮在 `aiLoading` 时显示 `t("wizard.scope.aiRecommendLoading")`，否则 `t("wizard.scope.aiRecommend")`，使 Task 5 的两个文案键都被使用（避免死文案）。

- [ ] **Step 1: 写失败测试**

`frontend/src/components/dfmea/ScopeTagField.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import ScopeTagField from "./ScopeTagField";
import { getRecommendations } from "../../api/recommendation";

vi.mock("../../api/recommendation", () => ({
  getRecommendations: vi.fn(),
}));

const mockedGetRecommendations = vi.mocked(getRecommendations);

const AI_RESPONSE = {
  suggestions: [],
  source: "rule" as const,
  cached: false,
  llm_available: false,
  graph_match_count: 0,
  effective_scope: "current_product_line" as const,
};

function renderField(overrides: Partial<React.ComponentProps<typeof ScopeTagField>> = {}) {
  return render(
    <ScopeTagField
      value=""
      onChange={() => {}}
      presets={["边界图", "P图", "接口矩阵"]}
      triggerType="dfmea_tool"
      fmeaId="fmea-1"
      context={{ fmea_title: "DC-DC", product_line_code: "DC-DC-100", task: "分析" }}
      {...overrides}
    />,
  );
}

describe("ScopeTagField", () => {
  beforeEach(() => mockedGetRecommendations.mockReset());

  it("renders unselected preset quick-add chips", () => {
    renderField();
    expect(screen.getByText("+ 边界图")).toBeInTheDocument();
    expect(screen.getByText("+ P图")).toBeInTheDocument();
    expect(screen.getByText("+ 接口矩阵")).toBeInTheDocument();
  });

  it("hides a preset chip once selected and calls onChange to add", () => {
    const onChange = vi.fn();
    renderField({ onChange });
    fireEvent.click(screen.getByText("+ 边界图"));
    expect(onChange).toHaveBeenCalledWith("边界图");
  });

  it("does not show a chip for an already-selected preset", () => {
    renderField({ value: "边界图" });
    expect(screen.queryByText("+ 边界图")).not.toBeInTheDocument();
    expect(screen.getByText("+ P图")).toBeInTheDocument();
  });

  it("AI button fetches suggestions and renders purple AI chips", async () => {
    mockedGetRecommendations.mockResolvedValueOnce({
      ...AI_RESPONSE,
      suggestions: [{ name: "故障树分析(FTA)", confidence: 0.8, source: "llm", explanation: "" }],
      source: "hybrid",
      llm_available: true,
    });
    renderField();
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(mockedGetRecommendations).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("故障树分析(FTA)")).toBeInTheDocument());
  });

  it("clicking an AI chip adds it via onChange", async () => {
    mockedGetRecommendations.mockResolvedValueOnce({
      ...AI_RESPONSE,
      suggestions: [{ name: "设计评审", confidence: 0.7, source: "llm", explanation: "" }],
      source: "hybrid",
      llm_available: true,
    });
    const onChange = vi.fn();
    renderField({ onChange });
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(screen.getByText("设计评审")).toBeInTheDocument());
    fireEvent.click(screen.getByText("设计评审"));
    expect(onChange).toHaveBeenCalledWith("设计评审");
  });

  it("does not render AI chips when AI returns empty", async () => {
    mockedGetRecommendations.mockResolvedValueOnce(AI_RESPONSE);
    renderField();
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(mockedGetRecommendations).toHaveBeenCalled());
    expect(screen.queryByText("故障树分析(FTA)")).not.toBeInTheDocument();
  });

  it("does not render AI chips when the call rejects", async () => {
    mockedGetRecommendations.mockRejectedValueOnce(new Error("boom"));
    renderField();
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(mockedGetRecommendations).toHaveBeenCalled());
    expect(screen.queryByText("故障树分析(FTA)")).not.toBeInTheDocument();
  });

  it("passes trigger_type, scope and include_graph:false to getRecommendations", async () => {
    mockedGetRecommendations.mockResolvedValueOnce(AI_RESPONSE);
    renderField({ triggerType: "dfmea_trend" });
    fireEvent.click(screen.getByTestId("scope-ai-btn"));
    await waitFor(() => expect(mockedGetRecommendations).toHaveBeenCalled());
    const arg = mockedGetRecommendations.mock.calls[0][1];
    expect(arg.trigger_type).toBe("dfmea_trend");
    expect(arg.scope).toBe("current_product_line");
    expect(arg.include_graph).toBe(false);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test -- --run src/components/dfmea/ScopeTagField.test.tsx`
Expected: FAIL — "Failed to resolve import … ScopeTagField"。

- [ ] **Step 3: 写最小实现**

`frontend/src/components/dfmea/ScopeTagField.tsx`:

```tsx
import { useState, useRef } from "react";
import { Select, Button, Tag, Spin, message } from "antd";
import { StarOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getRecommendations, type Suggestion } from "../../api/recommendation";
import { parseScopeTokens, stringifyScopeTokens } from "../../utils/wizardScopeTokens";

export type ScopeTriggerType = "dfmea_tool" | "dfmea_trend";

interface ScopeTagFieldProps {
  /** 「、」分隔的存盘 string */
  value: string;
  /** 回写「、」分隔 string */
  onChange: (v: string) => void;
  /** 预设清单（从 i18n 取，调用处 `as string[]`） */
  presets: string[];
  triggerType: ScopeTriggerType;
  fmeaId: string;
  /** AI 请求上下文：{ fmea_title, product_line_code, task, team } */
  context: Record<string, unknown>;
}

export default function ScopeTagField({
  value,
  onChange,
  presets,
  triggerType,
  fmeaId,
  context,
}: ScopeTagFieldProps) {
  const { t } = useTranslation("dfmea");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<string[]>([]);

  // 用 ref 持有最新 value：异步 AI 回调过滤「已选」时取最新值，
  // 避免请求返回前用户改动选择造成的 stale tokenSet。
  const valueRef = useRef(value);
  valueRef.current = value;

  const tokens = parseScopeTokens(value);
  const tokenSet = new Set(tokens);

  const emit = (next: string[]) => onChange(stringifyScopeTokens(next));

  const addPreset = (preset: string) => {
    if (tokenSet.has(preset)) return;
    emit([...tokens, preset]);
  };

  const addAiSuggestion = (name: string) => {
    if (tokenSet.has(name)) return;
    emit([...tokens, name]);
  };

  const handleAiClick = async () => {
    setAiLoading(true);
    try {
      const res = await getRecommendations(fmeaId, {
        trigger_type: triggerType,
        context,
        scope: "current_product_line",
        include_graph: false,
      });
      const names = res.suggestions.map((s: Suggestion) => s.name).filter(Boolean);
      // 用 valueRef 取最新已选集合，避免请求返回前用户改动造成的 stale tokenSet
      const current = new Set(parseScopeTokens(valueRef.current));
      const fresh = Array.from(new Set(names.filter((n) => !current.has(n))));
      setAiSuggestions(fresh);
      if (fresh.length === 0) {
        message.warning(t("wizard.scope.aiRecommendEmpty"));
      }
    } catch {
      setAiSuggestions([]);
      message.warning(t("wizard.scope.aiRecommendFailed"));
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div>
      <Select
        mode="tags"
        style={{ width: "100%" }}
        tokenSeparators={[",", "、", ";", "，", "；"]}
        value={tokens}
        onChange={(next) => emit(next as string[])}
      />
      <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {presets
          .filter((p) => !tokenSet.has(p))
          .map((p) => (
            <Tag key={p} style={{ cursor: "pointer" }} onClick={() => addPreset(p)}>
              + {p}
            </Tag>
          ))}
        <Button
          size="small"
          type="dashed"
          data-testid="scope-ai-btn"
          icon={aiLoading ? <Spin size="small" /> : <StarOutlined />}
          onClick={handleAiClick}
          disabled={aiLoading}
        >
          {aiLoading ? t("wizard.scope.aiRecommendLoading") : t("wizard.scope.aiRecommend")}
        </Button>
        {aiSuggestions.map((name) => (
          <Tag
            key={name}
            color="purple"
            style={{ cursor: "pointer" }}
            onClick={() => addAiSuggestion(name)}
          >
            <StarOutlined /> {name}
          </Tag>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npm test -- --run src/components/dfmea/ScopeTagField.test.tsx`
Expected: PASS（全部用例绿）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/dfmea/ScopeTagField.tsx frontend/src/components/dfmea/ScopeTagField.test.tsx
git commit -m "feat(dfmea): ScopeTagField component (Select tags + preset quick-add + AI button)"
```

---

### Task 5: i18n 预设数组 + AI 按钮文案

**Files:**
- Modify: `frontend/src/locales/zh-CN/dfmea.json`（`wizard.scope` 对象）
- Modify: `frontend/src/locales/en-US/dfmea.json`（`wizard.scope` 对象）

**Interfaces:**
- Produces: `wizard.scope.toolPresets` / `wizard.scope.trendPresets`（string[]）、`wizard.scope.aiRecommend` / `aiRecommendLoading` / `aiRecommendEmpty` / `aiRecommendFailed`（string）。Task 6 用 `t("wizard.scope.toolPresets", { returnObjects: true }) as string[]` 取预设；Task 4 组件用 `t("wizard.scope.aiRecommend*")` 取按钮/提示文案。

- [ ] **Step 1: zh-CN — 在 `wizard.scope` 对象末尾（`"legacyTimeframe"` 行之后）追加键**

把 `frontend/src/locales/zh-CN/dfmea.json` 中：

```json
  "legacyTimeframe": "当前旧格式值：{{value}}（重新选择以更新）"
```

改为：

```json
  "legacyTimeframe": "当前旧格式值：{{value}}（重新选择以更新）",
  "toolPresets": ["边界图", "P图/参数图", "接口矩阵", "功能分析", "故障树分析", "DFMEA模板", "历史经验教训库"],
  "trendPresets": ["历史FMEA", "售后/现场故障数据", "客户投诉", "CAPA记录", "召回/法规数据", "审核发现", "设计变更历史"],
  "aiRecommend": "✨ AI推荐",
  "aiRecommendLoading": "推荐中…",
  "aiRecommendEmpty": "暂无 AI 建议",
  "aiRecommendFailed": "AI 推荐失败，请稍后重试"
```

- [ ] **Step 2: en-US — 在 `wizard.scope` 对象末尾追加对应英文键**

把 `frontend/src/locales/en-US/dfmea.json` 中 `wizard.scope` 的最后一个键（`"legacyTimeframe"` 行，值形如 `"Legacy value: {{value}} …"`）替换为该行 + 逗号 + 下列键：

```json
  "legacyTimeframe": "Legacy value: {{value}} (re-select to update)",
  "toolPresets": ["Boundary Diagram", "Parameter Diagram (P-Diagram)", "Interface Matrix", "Function Analysis", "Fault Tree Analysis (FTA)", "DFMEA Template", "Lessons Learned Library"],
  "trendPresets": ["Historical FMEA", "Field/Warranty Data", "Customer Complaints", "CAPA Records", "Recall/Regulatory Data", "Audit Findings", "Design Change History"],
  "aiRecommend": "✨ AI Recommend",
  "aiRecommendLoading": "Recommending…",
  "aiRecommendEmpty": "No AI suggestions",
  "aiRecommendFailed": "AI recommendation failed, please retry"
```

（若 en-US 现有 `legacyTimeframe` 值与上例不同，保留其原值不变，仅在其后加逗号并追加后续键。）

- [ ] **Step 3: 校验 JSON 合法 + 类型不回归**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/dfmea.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/dfmea.json','utf8')); console.log('ok')"`
Expected: 输出 `ok`（两文件均为合法 JSON）。

Run: `cd frontend && npm run build`
Expected: tsc --noEmit 通过（`t(...,{returnObjects:true}) as string[]` 类型正确；新键不影响其它翻译）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/locales/zh-CN/dfmea.json frontend/src/locales/en-US/dfmea.json
git commit -m "feat(dfmea): i18n presets + AI button copy for wizard tool/trend"
```

---

### Task 6: 接入向导 — DFMEAWizardPage Step 0

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`（顶部 import 区 + `renderStep0()` 的 tool/trend 字段，约 185–193 行）

**Interfaces:**
- Consumes: `ScopeTagField`（Task 4）、i18n `wizard.scope.toolPresets`/`trendPresets`（Task 5）、`fmeaId`/`fmea`/`wizardScope`/`updateGraphData`（页面已有）

**类型确认（已核实）：** `FMEADocument`（`frontend/src/types/index.ts:109`）含 `title: string`（112）与 `product_line_code: string`（114，均非空）。但页面 `fmea` 状态为 `FMEADocument | null`，故访问须用 `fmea?.title`、`fmea?.product_line_code ?? ""`。

- [ ] **Step 1: 加 import**

在 `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` 顶部 import 区（已有的 `import WizardGuidanceCard from '../../../components/dfmea/WizardGuidanceCard';` 附近）加一行：

```tsx
import ScopeTagField from '../../../components/dfmea/ScopeTagField';
```

- [ ] **Step 2: 替换 tool/trend 两处 Input**

把 `renderStep0()` 中的（约 185–193 行）：

```tsx
        <Field label={t('wizard.scope.tool')}>
          <Input value={wizardScope.tool || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, tool: e.target.value })} />
        </Field>
        <Field label={t('wizard.scope.task')}>
          <Input value={wizardScope.task || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, task: e.target.value })} />
        </Field>
        <Field label={t('wizard.scope.trend')}>
          <Input value={wizardScope.trend || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, trend: e.target.value })} />
        </Field>
```

替换为：

```tsx
        <Field label={t('wizard.scope.tool')}>
          <ScopeTagField
            value={wizardScope.tool || ''}
            onChange={v => updateGraphData(nodes, edges, { ...wizardScope, tool: v })}
            presets={t('wizard.scope.toolPresets', { returnObjects: true }) as string[]}
            triggerType="dfmea_tool"
            fmeaId={fmeaId!}
            context={{ fmea_title: fmea?.title, product_line_code: fmea?.product_line_code ?? '', task: wizardScope.task || '', team: wizardScope.team || '' }}
          />
        </Field>
        <Field label={t('wizard.scope.task')}>
          <Input value={wizardScope.task || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, task: e.target.value })} />
        </Field>
        <Field label={t('wizard.scope.trend')}>
          <ScopeTagField
            value={wizardScope.trend || ''}
            onChange={v => updateGraphData(nodes, edges, { ...wizardScope, trend: v })}
            presets={t('wizard.scope.trendPresets', { returnObjects: true }) as string[]}
            triggerType="dfmea_trend"
            fmeaId={fmeaId!}
            context={{ fmea_title: fmea?.title, product_line_code: fmea?.product_line_code ?? '', task: wizardScope.task || '', team: wizardScope.team || '' }}
          />
        </Field>
```

（team / timeframe / task 字段保持原样；task 仍为 `<Input>`。）

- [ ] **Step 3: 类型 + lint 校验**

Run: `cd frontend && npm run build`
Expected: tsc --noEmit 通过，vite build 成功（确认 `ScopeTagField` props 类型匹配、`as string[]` 转换合法、`fmeaId!` 非空断言可用）。

Run: `cd frontend && npm run lint`
Expected: 无新增 error/warning（`Input` 仍被其它步骤使用，故不会有 unused import；若 lint 报 `Input` unused，说明误删了 task 的 Input，需回退）。

- [ ] **Step 4: 全量前端测试回归**

Run: `cd frontend && npm test -- --run`
Expected: 全绿（含 Task 1、Task 4 新测 + 既有 dfmea 测试）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea): wire ScopeTagField into wizard Step 0 tool/trend fields"
```

---

## Self-Review

**1. Spec 覆盖：**
- §3 决策表（混合/多选/Select tags/三处后端）→ Task 1（序列化）、Task 4（组件）、Task 2+3（后端三处）。
- §4 数据模型 + 去重保序 → Task 1（parse/stringify 含去重 + 测试）。
- §5 ScopeTagField + 类型注意（`as string[]`、`fmea?.product_line_code ?? ""`）→ Task 4 + Task 6（已用守卫）。
- §6 预设清单内容 → Task 5（zh/en 数组与 §6 表一致）。
- §7.1 schema Literal → Task 2 Step 3a。
- §7.2 PROMPT_TEMPLATES → Task 3 Step 3。
- §7.3 anchor 修复 → Task 2 Step 3b/3c。
- §8 i18n 文案 → Task 5。
- §9 测试全覆盖：前端工具函数（Task 1）、组件（Task 4）、后端 anchor（Task 2）、build_prompt + recommend() 集成（Task 3）。Task 3 的 `TestRecommendIntegrationForToolTrend` 用 monkeypatch 绕过 db（`_get_fmea_or_404`/`_get_cached`/`_assemble_context`/`_cache_result`）与权限（`get_user_permission`），直接验证新 trigger 走完整链路：mock LLM → 返回建议 + source∈{hybrid,graph_enriched}；无 LLM → 空 + `source="rule"`；LLM 抛异常 → `source="rule_fallback"`。`RuleEngine.evaluate` 对未知 trigger 返回空（quality="generic"，已核实 recommendation_service.py:138-140），不抛异常，故无需 patch rules。
- §10 范围边界：未触碰 `GenerationWizard.tsx`、team/timeframe/task、wizardScope 存盘结构。

**2. 占位符扫描：** 无 TBD/TODO；每步含可执行命令与完整代码。

**3. 类型一致性：** `parseScopeTokens`/`stringifyScopeTokens`（Task 1）签名与 Task 4/6 使用一致；`ScopeTagField` props（Task 4）与 Task 6 传参一致（`value/onChange/presets/triggerType/fmeaId/context`）；`_recommend_anchor(trigger_type, context) -> str`（Task 2）与端点调用一致；`trigger_type` Literal 新值（Task 2 schema）与组件请求 `trigger_type: triggerType`（Task 4，类型 `ScopeTriggerType = "dfmea_tool" | "dfmea_trend"`）一致；`data-testid="scope-ai-btn"`（Task 4 实现 + 测试）一致。

无问题，计划可执行。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-dfmea-wizard-tool-trend-recommendations.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?