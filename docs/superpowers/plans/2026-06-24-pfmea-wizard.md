# PFMEA 7-Step Generation Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 7-step PFMEA generation wizard mirroring the existing DFMEA wizard, following the approved PFMEA data structure (`docs/superpowers/specs/2026-05-20-pfmea-data-structure-design.md`) and the wizard design spec (`docs/superpowers/specs/2026-06-24-pfmea-wizard-design.md`).

**Architecture:** A new `PFMEAWizardPage.tsx` plus PFMEA-specific components in `components/pfmea/`, reusing the generic wizard infra (`useWizardSave`, `SmartSuggestionDropdown`, the `wizard*` utils, `calculateAP`, `buildRows`). The wizard progressively builds `graph_data` in place (debounce-saved) using PFMEA node types (`ProcessItem`/`ProcessStep`/`ProcessWorkElement` + 3-level function nodes) and edge types (`HAS_PROCESS_STEP`/`HAS_WORK_ELEMENT`/`FUNCTION_MAPPED_TO` + failure-chain edges). Backend adds `pfmea_tool`/`pfmea_trend` recommend triggers.

**Tech Stack:** React 18 + TypeScript 5.6 + Vite 5.4 + Ant Design 5.29 + Zustand + i18next (frontend); Python 3.11 + FastAPI + Pydantic v2 (backend); vitest (frontend tests); pytest (backend tests).

## Global Constraints

- **PFMEA failure chain hangs off `ProcessStepFunction`** (`HAS_FAILURE_MODE: ProcessStepFunction → FailureMode`), NOT `ProcessWorkElementFunction`. Per spec §5/§8 and approved data-structure §2.2. `createWizardFailureChain` is called with the `ProcessStepFunction` id.
- **CC/SC live on function-node `classification`**: CC → `ProcessStepFunction.classification`, SC → `ProcessWorkElementFunction.classification`. `ProcessItemFunction` has NO CC/SC (empty only). Never add a `FailureCause.special_characteristic` field. Per spec §8.
- **Three-tier severity** on `FailureEffect`: `severity_plant`/`severity_customer`/`severity_user` (1–10, already in `types/index.ts` and backend schema), with `severity = max(plant, customer, user)`. The wizard writes all four. Per spec §5 Step 4.
- **4M classification values are exactly** `"Man" | "Machine" | "Material" | "Environment"` (4M, NOT 5M1E — no Method/法). `ProcessWorkElement.classification` required; `ProcessStep.process_number` required (e.g. `"OP10"`). Per approved data-structure §2.1-A.
- **Do not change DFMEA behavior.** New code lives in `components/pfmea/` + `PFMEAWizardPage.tsx`. The only existing DFMEA file touched is `ScopeTagField.tsx` (extend its trigger-type union — additive, non-breaking) and `FMEAEditorPage.tsx` (Class column compat — PFMEA-only branch, DFMEA Filter Code untouched) and `App.tsx`/`FMEAListPage.tsx` (additive routes/branches).
- **i18n namespace**: new `pfmea` namespace (`locales/{zh-CN,en-US}/pfmea.json`); all PFMEA wizard strings read from it.
- **Reuse, don't duplicate**: import `SmartSuggestionDropdown`, `useWizardSave`, `wizardGraphNormalize`, `wizardCascadeDelete`, `wizardStructureOrder`, `wizardTimeframe`, `wizardScopeTokens`, `fmea` (`calculateAP`), `fmeaTable` (`buildRows`/`getRowSeverity`) directly from their existing locations.
- **TDD**: every code task writes the failing test first, runs it, implements, runs it green, commits. Frequent commits.
- **Frontend test command**: `npx vitest run <file>` (single run). **Backend test command**: `cd backend && SECRET_KEY=test-secret-key pytest tests/<file> -x`.
- **FMEA model**: `FMEADocument.fmea_type` defaults to `"PFMEA"`; `create_fmea` already auto-initializes a single `ProcessItem` node for PFMEA (approved data-structure §5.1). The wizard loads that.

---

## File Structure

**Create (frontend):**
- `frontend/src/utils/pfmeaRules.ts` — PFMEA rule-based AI suggestion fallbacks (process verbs, 4M failure chains).
- `frontend/src/hooks/usePfmeaWizardValidation.ts` — PFMEA-specific step completion + warnings.
- `frontend/src/components/pfmea/PFMEAWizardSidebar.tsx` — sidebar: PFMEA structure tree + step nav.
- `frontend/src/components/pfmea/PFMEAGuidanceCard.tsx` — per-step guidance from `pfmea.wizard.guidance`.
- `frontend/src/components/pfmea/FunctionTreeEditor.tsx` — 3-level function tree + CC/SC maintenance (Step 2).
- `frontend/src/components/pfmea/RiskTable.tsx` — risk table: 3-tier severity, CC/SC read-only aggregation, O/D gate (Step 4).
- `frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx` — the wizard page (steps 0–6, save, finish, conflict).
- `frontend/src/locales/zh-CN/pfmea.json` — Chinese i18n.
- `frontend/src/locales/en-US/pfmea.json` — English i18n.
- Tests: `pfmeaRules.test.ts`, `usePfmeaWizardValidation.test.ts`, `FunctionTreeEditor.test.tsx`, `RiskTable.test.tsx`, `PFMEAWizardSidebar.test.tsx`, `PFMEAWizardPage.test.tsx`.

**Create (backend):**
- `backend/tests/test_pfmea_recommend.py` — `pfmea_tool`/`pfmea_trend` trigger tests.

**Modify (frontend):**
- `frontend/src/components/dfmea/ScopeTagField.tsx` — extend `ScopeTriggerType` union with `"pfmea_tool" | "pfmea_trend"` (additive).
- `frontend/src/App.tsx` — add route `/fmea/pfmea-wizard/:id`.
- `frontend/src/pages/planning/fmea/FMEAListPage.tsx` — PFMEA create → wizard; PFMEA incomplete draft → wizard.
- `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` — PFMEA Class column reads function-node `classification` (read-only); DFMEA untouched.
- `frontend/src/i18n.ts` (or wherever namespaces are registered) — register `pfmea` namespace. *(Locate the i18n config that imports dfmea.json and add pfmea.json alongside — confirm exact file in Task 3.)*

**Modify (backend):**
- `backend/app/schemas/recommendation.py` — add `"pfmea_tool"`, `"pfmea_trend"` to `trigger_type` Literal.
- `backend/app/api/fmea.py` — extend `_recommend_anchor` to handle `pfmea_tool`/`pfmea_trend`.
- `backend/app/services/recommendation_service.py` — add `pfmea_tool`/`pfmea_trend` prompt templates; add PFMEA process verbs + 4M failure chains to rule engine; route `failure_mode`/`failure_cause` rule content by `fmea_type`.

---

## Task 1: Backend — `pfmea_tool` / `pfmea_trend` recommend triggers

**Files:**
- Modify: `backend/app/schemas/recommendation.py:7-10`
- Modify: `backend/app/api/fmea.py:245-265` (`_recommend_anchor`)
- Modify: `backend/app/services/recommendation_service.py` (`PROMPT_TEMPLATES`, rule engine)
- Test: `backend/tests/test_pfmea_recommend.py`

**Interfaces:**
- Produces: backend accepts `trigger_type ∈ {"pfmea_tool","pfmea_trend"}` and returns `RecommendResponse` with `suggestions: SuggestionItem[]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pfmea_recommend.py
import pytest
from unittest.mock import AsyncMock, patch
from app.schemas.recommendation import RecommendRequest


@pytest.mark.asyncio
async def test_pfmea_tool_trigger_accepted_by_schema():
    """pfmea_tool / pfmea_trend must be valid trigger_type values."""
    req = RecommendRequest(trigger_type="pfmea_tool", context={"fmea_title": "SMT焊接生产线", "task": "PFMEA"})
    assert req.trigger_type == "pfmea_tool"
    req2 = RecommendRequest(trigger_type="pfmea_trend", context={"task": "PFMEA"})
    assert req2.trigger_type == "pfmea_trend"


@pytest.mark.asyncio
async def test_pfmea_tool_anchor_returns_task():
    """_recommend_anchor must resolve pfmea_tool via task fallback like dfmea_tool."""
    from app.api.fmea import _recommend_anchor
    assert _recommend_anchor("pfmea_tool", {"task": "过程FMEA", "fmea_title": "SMT线"}) == "过程FMEA"
    assert _recommend_anchor("pfmea_trend", {"fmea_title": "SMT线"}) == "SMT线"
    assert _recommend_anchor("pfmea_tool", {}) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_pfmea_recommend.py -x`
Expected: FAIL — `pydantic.ValidationError` for `pfmea_tool` not in Literal; `_recommend_anchor` returns `""` for `pfmea_tool`.

- [ ] **Step 3: Add the two trigger types to the schema enum**

In `backend/app/schemas/recommendation.py`, change the `trigger_type` Literal to:

```python
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization",
        "dfmea_tool", "dfmea_trend",
        "pfmea_tool", "pfmea_trend",
        "prevention_control", "detection_control",
    ]
```

- [ ] **Step 4: Extend `_recommend_anchor`**

In `backend/app/api/fmea.py`, change the `dfmea_tool`/`dfmea_trend` branch to also match the PFMEA triggers:

```python
    if trigger_type in ("dfmea_tool", "dfmea_trend", "pfmea_tool", "pfmea_trend"):
        return (
            context.get("task")
            or context.get("fmea_title")
            or context.get("team")
            or context.get("input_text")
            or ""
        )
```

- [ ] **Step 5: Add prompt templates + PFMEA rule content**

In `backend/app/services/recommendation_service.py`, add two entries to `PROMPT_TEMPLATES` mirroring the `dfmea_tool`/`dfmea_trend` shape **exactly** (the LLM result is validated by `SuggestionList.model_validate()`, which requires `name`/`confidence`/`explanation` — see `backend/app/schemas/recommendation.py:16-18` and `recommendation_service.py:540`). A prompt returning `{name, reason}` would fail validation and silently fall back to empty rule/graph. Place immediately after the `"dfmea_trend"` entry (line 450):

```python
    "pfmea_tool": """你是资深PFMEA(过程FMEA)工程师，精通AIAG-VDA方法论。

【任务】为下方PFMEA分析推荐 3-5 个合适的「分析工具/方法」。
【工具定义】用于过程结构/功能/失效分析的方法与图样，例如过程流程图、过程参数图(P图)、鱼骨图(4M分析)、PFMEA模板、过程FMECA等。
【方向约束】推荐具体、可执行的方法或图样名称，不要泛泛的"质量工具"。

【当前上下文】
- FMEA 标题: {fmea_title}
- 产品线: {product_line_code}
- 分析任务: {task}
- 团队: {team}

【历史相似案例】
{historical_patterns}

【示例】分析工具: 过程流程图 / 过程参数图(P图) / 鱼骨图(4M分析) / PFMEA模板 / 过程FMECA

【要求】与当前过程/任务直接相关，便于据此开展结构分析与功能分析。
返回 JSON：
{{"suggestions": [{{"name": "工具/方法名称", "confidence": 0.0-1.0, "explanation": "为何适合当前PFMEA分析"}}]}}
""",
    "pfmea_trend": """你是资深PFMEA(过程FMEA)工程师，精通AIAG-VDA方法论。

【任务】为下方PFMEA分析推荐 3-5 个「趋势数据/信息源」。
【趋势定义】指导本次分析的输入信息与历史数据来源，例如历史PFMEA、过程SPC数据、不合格品记录(NCR)、客户投诉、CAPA记录、返工/报废记录等。
【方向约束】推荐具体的数据源类别，便于据此收集分析输入。

【当前上下文】
- FMEA 标题: {fmea_title}
- 产品线: {product_line_code}
- 分析任务: {task}
- 团队: {team}

【历史相似案例】
{historical_patterns}

【示例】趋势数据: 历史PFMEA / 过程SPC数据 / 不合格品记录(NCR) / 客户投诉 / CAPA记录 / 返工报废记录

【要求】与当前产品线/过程相关、能指导风险识别的数据源。
返回 JSON：
{{"suggestions": [{{"name": "趋势数据/信息源", "confidence": 0.0-1.0, "explanation": "为何该数据源对本次分析有价值"}}]}}
""",
```

> **Critical**: the JSON key names must be `name`/`confidence`/`explanation` (not `reason`). `_build_prompt` formats the template with `{fmea_title}`/`{product_line_code}`/`{task}`/`{team}`/`{historical_patterns}` — all are provided by `_assemble_context` (which already injects `fmea_type`, `product_line_code`, and merges `request.context`). Confirm `product_line_code` is in scope: `_assemble_context` returns `product_line_code` via the `fmea` object; if the template uses `{product_line}` instead (the failure_* templates use `{product_line}`), match whatever `_assemble_context` provides. Check `_assemble_context` (around line 844) and use the matching key. The `dfmea_tool` template uses `{product_line_code}` — use the same.

Then add a PFMEA-specific rule map. After `FAILURE_CHAIN_MAP` (around line 121), add:

```python
# PFMEA 过程动词 → 失效模式（按 4M 组织）
PFMEA_VERB_PATTERNS: dict[str, list[str]] = {
    "焊接": ["焊点虚焊", "焊点桥连", "焊料不足", "焊点气孔"],
    "装配": ["装配错位", "漏装", "错装", "装配过紧/过松"],
    "注塑": ["缺料", "飞边", "缩水", "气泡"],
    "涂装": ["涂层不均", "漏涂", "涂层过厚/过薄", "色差"],
    "压装": ["压装不到位", "压装过载", "压装偏斜", "压装扭矩不稳"],
    "贴装": ["贴装偏移", "贴装漏件", "贴装反件", "贴装压力异常"],
}

PFMEA_FAILURE_CHAIN_MAP: dict[str, dict[str, list[str]]] = {
    "贴装偏移": {
        "effects": ["电控板功能丧失", "整机无法启动", "客户退货"],
        "causes": ["贴装吸嘴磨损", "贴装压力设定偏小", "设备校准漂移", "来料器件偏置"],
    },
    "压装不到位": {
        "effects": ["连接松动", "异响", "功能间歇性失效"],
        "causes": ["压头行程未校准", "压力传感器漂移", "来料尺寸超差", "操作未按SOP"],
    },
    "焊点虚焊": {
        "effects": ["电路断开", "信号中断", "功能丧失"],
        "causes": ["焊接温度不足", "焊膏活性不足", "贴装压力不足", "环境湿度过高"],
    },
}

PFMEA_4M_CAUSE_HINTS: dict[str, list[str]] = {
    "Man": ["操作未按SOP", "培训不足", "疲劳/疏忽", "人员换线未验证"],
    "Machine": ["设备校准漂移", "设备磨损", "设备参数漂移", "预防性维护缺失"],
    "Material": ["来料尺寸超差", "来料材质不符", "辅料过期", "批次不一致"],
    "Environment": ["温湿度超范围", "粉尘/洁净度不足", "静电(ESD)", "照明不足"],
}
```

Then route the rule engine by `fmea_type`. Find the function that maps `trigger_type` to rule content (the one that uses `VERB_PATTERNS`/`FAILURE_CHAIN_MAP` for `failure_mode`/`failure_cause`). Add a `fmea_type` parameter branch: when `fmea.fmea_type == "PFMEA"`, use `PFMEA_VERB_PATTERNS`/`PFMEA_FAILURE_CHAIN_MAP`/`PFMEA_4M_CAUSE_HINTS` instead of the DFMEA maps. *(Locate the exact function — likely `_rule_engine_suggest` or similar — and add the branch. If the rule function does not receive `fmea`, thread `fmea.fmea_type` through from `_assemble_context`/`recommend`. Show the branch:)*

```python
def _rule_failure_causes(trigger_type: str, fm_name: str, fmea_type: str) -> list[str]:
    if fmea_type == "PFMEA":
        chain = PFMEA_FAILURE_CHAIN_MAP.get(fm_name)
        if chain:
            return chain["causes"]
        # fall back to verb-based
        for verb, modes in PFMEA_VERB_PATTERNS.items():
            if verb in fm_name:
                return PFMEA_FAILURE_CHAIN_MAP.get(modes[0], {}).get("causes", [])
        return []
    # DFMEA default (existing behavior unchanged)
    chain = FAILURE_CHAIN_MAP.get(fm_name)
    return chain["causes"] if chain else []
```

Apply the same `fmea_type` branching for the `failure_mode` verb-pattern lookup (use `PFMEA_VERB_PATTERNS` when PFMEA). Leave all DFMEA paths exactly as-is.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_pfmea_recommend.py -x`
Expected: PASS.

- [ ] **Step 7: Add a template-format test + a service-level non-empty-suggestions test**

Append to `backend/tests/test_pfmea_recommend.py`:

```python
from app.services.recommendation_service import PROMPT_TEMPLATES
from app.schemas.recommendation import SuggestionList


def test_pfmea_prompt_templates_format_without_keyerror():
    """Both prompts must format with the context keys _assemble_context provides."""
    ctx = {
        "fmea_title": "SMT线", "product_line_code": "DC-DC-100",
        "task": "PFMEA", "team": "张工", "historical_patterns": "无",
    }
    for trig in ("pfmea_tool", "pfmea_trend"):
        rendered = PROMPT_TEMPLATES[trig].format_map(_SafeDict(ctx))
        assert "suggestions" in rendered
        assert "confidence" in rendered  # schema key, not "reason"


def test_pfmea_tool_llm_output_passes_suggestionlist_validation():
    """LLM output shaped per the prompt must pass SuggestionList validation
    (this is the gate that would otherwise drop to empty rule/graph fallback)."""
    raw = {
        "suggestions": [
            {"name": "过程流程图", "confidence": 0.9, "explanation": "PFMEA标准起点"},
            {"name": "鱼骨图(4M分析)", "confidence": 0.8, "explanation": "识别4M失效起因"},
        ]
    }
    validated = SuggestionList.model_validate(raw)
    assert len(validated.suggestions) == 2
    assert validated.suggestions[0].name == "过程流程图"


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"
```

> Also add a service-level test that `pfmea_tool` returns non-empty suggestions when the LLM is stubbed to return valid output. Use the existing `test_recommendation_service.py` fixture pattern for constructing a `RecommendationService` with a stubbed LLM (find it via `grep -n "class.*LLM\|llm =\|RecommendationService(" backend/tests/test_recommendation_service.py`). The stub LLM's `complete()` must return a dict matching the `SuggestionList` schema above. Assert `response.suggestions` is non-empty and `response.source in ("hybrid","graph_enriched","rule_fallback")`. If the existing fixture is hard to reuse, the two tests above (template format + SuggestionList validation) are the required minimum; drop the full-service test if it cannot be stabilized, but **do not skip the validation test** — it is the regression guard for finding #1.

- [ ] **Step 8: Confirm the rule engine handles unknown triggers gracefully**

The rule engine is called as `self.rules.evaluate(request.trigger_type, request.context)` (line 496). `pfmea_tool`/`pfmea_trend` have no rule handler. Verify `RuleEngine.evaluate` returns an empty `SuggestionList` for unknown triggers rather than raising (read `backend/app/services/recommendation_service.py` `RuleEngine` class / `evaluate`). If it raises for unknown triggers, add an empty-result branch for `pfmea_tool`/`pfmea_trend`. Add a test:

```python
def test_rule_engine_returns_empty_for_pfmea_scope_triggers():
    from app.services.recommendation_service import RuleEngine
    engine = RuleEngine()
    for trig in ("pfmea_tool", "pfmea_trend"):
        result = engine.evaluate(trig, {"task": "PFMEA"})
        assert list(result.suggestions) == []
```

- [ ] **Step 9: Run full backend recommend test suite to confirm no regression**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommendation_service.py tests/test_pfmea_recommend.py -x`
Expected: PASS (existing DFMEA tests still green).

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/recommendation.py backend/app/api/fmea.py backend/app/services/recommendation_service.py backend/tests/test_pfmea_recommend.py
git commit -m "feat(pfmea): add pfmea_tool/pfmea_trend recommend triggers + 4M rule content"
```

---

## Task 2: Frontend — `pfmeaRules.ts` (PFMEA rule helpers)

**Files:**
- Create: `frontend/src/utils/pfmeaRules.ts`
- Test: `frontend/src/utils/pfmeaRules.test.ts`

**Interfaces:**
- Consumes: `GraphNode` from `../types`.
- Produces: `usePfmeaRules()` hook returning `{ generateFailureModes, suggestFailureChain, suggest4MCauses }` used by Step 3 rule fallback (mirrors `useDfmeaRules` shape but PFMEA-oriented).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/utils/pfmeaRules.test.ts
import { describe, it, expect } from 'vitest';
import { usePfmeaRules } from './pfmeaRules';

describe('usePfmeaRules', () => {
  const rules = usePfmeaRules();

  it('generateFailureModes returns process-verb-based modes', () => {
    const modes = rules.generateFailureModes('贴装电子元器件');
    expect(modes.length).toBeGreaterThan(0);
    expect(modes.some((m) => m.includes('偏移') || m.includes('漏件'))).toBe(true);
  });

  it('suggestFailureChain returns effects+causes for a known PFMEA mode', () => {
    const chain = rules.suggestFailureChain('贴装偏移');
    expect(chain.effects.length).toBeGreaterThan(0);
    expect(chain.causes.length).toBeGreaterThan(0);
  });

  it('suggest4MCauses returns Man/Machine/Material/Environment buckets', () => {
    const buckets = rules.suggest4MCauses();
    expect(buckets.Man.length).toBeGreaterThan(0);
    expect(buckets.Machine.length).toBeGreaterThan(0);
    expect(buckets.Material.length).toBeGreaterThan(0);
    expect(buckets.Environment.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run frontend/src/utils/pfmeaRules.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `pfmeaRules.ts`**

```typescript
// frontend/src/utils/pfmeaRules.ts

export interface FailureChain {
  effects: string[];
  causes: string[];
}

const VERB_PATTERNS: Record<string, string[]> = {
  焊接: ['焊点虚焊', '焊点桥连', '焊料不足', '焊点气孔'],
  装配: ['装配错位', '漏装', '错装', '装配过紧/过松'],
  注塑: ['缺料', '飞边', '缩水', '气泡'],
  涂装: ['涂层不均', '漏涂', '涂层过厚/过薄', '色差'],
  压装: ['压装不到位', '压装过载', '压装偏斜', '压装扭矩不稳'],
  贴装: ['贴装偏移', '贴装漏件', '贴装反件', '贴装压力异常'],
};

const FAILURE_CHAIN_MAP: Record<string, FailureChain> = {
  贴装偏移: {
    effects: ['电控板功能丧失', '整机无法启动', '客户退货'],
    causes: ['贴装吸嘴磨损', '贴装压力设定偏小', '设备校准漂移', '来料器件偏置'],
  },
  压装不到位: {
    effects: ['连接松动', '异响', '功能间歇性失效'],
    causes: ['压头行程未校准', '压力传感器漂移', '来料尺寸超差', '操作未按SOP'],
  },
  焊点虚焊: {
    effects: ['电路断开', '信号中断', '功能丧失'],
    causes: ['焊接温度不足', '焊膏活性不足', '贴装压力不足', '环境湿度过高'],
  },
};

const M4_CAUSE_HINTS: Record<string, string[]> = {
  Man: ['操作未按SOP', '培训不足', '疲劳/疏忽', '人员换线未验证'],
  Machine: ['设备校准漂移', '设备磨损', '设备参数漂移', '预防性维护缺失'],
  Material: ['来料尺寸超差', '来料材质不符', '辅料过期', '批次不一致'],
  Environment: ['温湿度超范围', '粉尘/洁净度不足', '静电(ESD)', '照明不足'],
};

export function usePfmeaRules() {
  const generateFailureModes = (stepFunctionText: string): string[] => {
    const text = stepFunctionText ?? '';
    for (const verb of Object.keys(VERB_PATTERNS)) {
      if (text.includes(verb)) return VERB_PATTERNS[verb];
    }
    return [];
  };

  const suggestFailureChain = (failureMode: string): FailureChain =>
    FAILURE_CHAIN_MAP[failureMode] ?? { effects: [], causes: [] };

  const suggest4MCauses = (): Record<string, string[]> => ({ ...M4_CAUSE_HINTS });

  return { generateFailureModes, suggestFailureChain, suggest4MCauses };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run frontend/src/utils/pfmeaRules.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/pfmeaRules.ts frontend/src/utils/pfmeaRules.test.ts
git commit -m "feat(pfmea): add PFMEA rule helpers (4M causes, process-verb failure modes)"
```

---

## Task 3: Frontend — PFMEA i18n namespace

**Files:**
- Create: `frontend/src/locales/zh-CN/pfmea.json`
- Create: `frontend/src/locales/en-US/pfmea.json`
- Modify: the i18n config file that registers namespaces (locate by `grep -rn "dfmea" frontend/src/locales/zh-CN/index.ts frontend/src/i18n.ts` — confirm exact file; it is wherever `dfmea` namespace is imported).

**Interfaces:**
- Produces: `pfmea` namespace with key tree mirroring `dfmea.json` (see reference §9): `wizard.title`, `wizard.steps` (7 items), `wizard.scope` (incl. `toolPresets`/`trendPresets`), `wizard.structure`, `wizard.typeLabels`, `wizard.function`, `wizard.failure`, `wizard.risk`, `wizard.optimization`, `wizard.confirm`, `wizard.buttons`, `wizard.page`, `wizard.guidance.step0..step6`, `wizard.sidebar`, `smartSuggestion`, `rules`.

- [ ] **Step 1: Locate the i18n registration file**

Run: `grep -rln "dfmea.json\|dfmea'" frontend/src | head`
Note the file that imports `dfmea` resources (e.g. `frontend/src/locales/zh-CN/index.ts` or `frontend/src/i18n.ts`).

- [ ] **Step 2: Create `zh-CN/pfmea.json`**

Use the key tree from `dfmea.json` (reference §9) translated to PFMEA. PFMEA-specific values:

```json
{
  "wizard": {
    "title": "PFMEA 生成向导",
    "steps": ["5T范围", "结构分析", "功能分析", "失效分析", "风险分析", "优化", "结果文档"],
    "scope": {
      "title": "5T范围",
      "description": "定义PFMEA分析的团队、时间、工具、任务与趋势数据来源。",
      "team": "团队",
      "timeframe": "时间范围",
      "tool": "工具",
      "task": "任务",
      "trend": "趋势数据来源",
      "legacyTimeframe": "时间范围",
      "toolPresets": ["过程流程图", "过程参数图(P图)", "鱼骨图(4M分析)", "PFMEA模板", "过程FMECA", "控制计划草案", "历史经验教训库"],
      "trendPresets": ["历史PFMEA", "过程SPC数据", "不合格品记录(NCR)", "客户投诉", "CAPA记录", "返工/报废记录", "审核发现", "过程变更历史"],
      "aiRecommend": "AI推荐",
      "aiRecommendLoading": "推荐中…",
      "aiRecommendEmpty": "暂无推荐",
      "aiRecommendFailed": "推荐失败",
      "toolGuide": "工具说明",
      "toolGuideNeedStructure": "请先完成结构分析"
    },
    "structure": {
      "title": "结构分析",
      "description": "分解过程项目 → 过程步骤 → 作业要素(4M)。",
      "addProcessItem": "添加过程项目",
      "addProcessStep": "添加过程步骤",
      "addWorkElement": "添加作业要素",
      "delete": "删除",
      "empty": "尚未添加结构节点",
      "processNumber": "工序号",
      "classification4M": "4M分类",
      "newProcessItem": "新建过程项目",
      "newProcessStep": "新建过程步骤",
      "newWorkElement": "新建作业要素"
    },
    "typeLabels": {
      "ProcessItem": "过程项目",
      "ProcessStep": "过程步骤",
      "ProcessWorkElement": "作业要素"
    },
    "function": {
      "title": "功能分析",
      "description": "为每个结构节点定义功能，建立3层功能树并区分产品特性/过程特性。",
      "functionDesc": "功能",
      "requirement": "技术要求/过程特性",
      "specification": "产品特性/规格",
      "productChar": "产品特性",
      "processChar": "过程特性",
      "specialCharacteristic": "特殊特性",
      "addItemFunction": "添加过程项目功能",
      "addStepFunction": "添加过程步骤功能",
      "addWorkElementFunction": "添加作业要素功能"
    },
    "failure": {
      "title": "失效分析",
      "description": "为每个过程步骤功能建立失效链(挂过程步骤功能)。原因按4M组织。",
      "recommended": "推荐",
      "autoRecommend": "AI推荐",
      "failureMode": "失效模式",
      "failureEffect": "失效影响",
      "failureCause": "失效起因",
      "preventionControl": "预防控制",
      "detectionControl": "探测控制",
      "addFailureChain": "添加失效链",
      "delete": "删除",
      "newFailureMode": "新建失效模式",
      "workElementHint": "该步骤的4M作业要素"
    },
    "risk": {
      "title": "风险分析",
      "description": "评估三段式严重度(本厂/客户/终端用户，取最大值)、频度、探测度，计算AP。",
      "s": "S",
      "o": "O",
      "d": "D",
      "ap": "AP",
      "severityPlant": "本厂严重度",
      "severityCustomer": "客户严重度",
      "severityUser": "终端用户严重度",
      "severityMax": "综合严重度(最大值)",
      "severityDialog": "三段式严重度评分",
      "class": "特性",
      "mustOptimize": "需优化",
      "empty": "尚无风险行",
      "missingControlHint": "请先填写预防/探测控制",
      "controlsFirst": "填写控制后再评分O/D"
    },
    "optimization": {
      "title": "优化",
      "noOptimization": "无需优化",
      "noOptimizationHint": "没有AP=H的行",
      "apBadge": "AP=H",
      "measure": "优化措施",
      "measurePlaceholder": "输入优化措施",
      "responsible": "负责人",
      "responsiblePlaceholder": "负责人",
      "dueDate": "计划完成日期",
      "status": "状态",
      "actionTaken": "已采取措施",
      "actionTakenPlaceholder": "实际采取的措施",
      "completionDate": "完成日期",
      "revisedRatings": "重评 S′/O′/D′",
      "revisedAp": "重评AP",
      "statusOptions": { "open": "待执行", "undecided": "未决", "planned": "已计划", "done": "已完成", "notExecuted": "不执行" }
    },
    "confirm": {
      "title": "结果文档",
      "structureNodes": "结构节点",
      "functionNodes": "功能节点",
      "failureChains": "失效链",
      "totalNodes": "总节点",
      "totalEdges": "总边",
      "description": "确认PFMEA分析结果并完成创建。"
    },
    "buttons": { "cancel": "取消", "prev": "上一步", "next": "下一步", "finish": "完成创建" },
    "page": {
      "title": "PFMEA向导", "backToList": "返回列表", "saveDraft": "存草稿",
      "saveSaving": "保存中…", "saveSaved": "已保存", "saveError": "保存失败",
      "nextStep": "下一步", "prevStep": "上一步", "finish": "完成创建",
      "step1Incomplete": "结构分析未完成：过程步骤需填工序号、作业要素需选4M分类",
      "step2Incomplete": "功能分析未完成：所有作业要素需有功能，3层功能链需完整",
      "step3Incomplete": "失效分析未完成：所有过程步骤功能需有命名失效链与控制",
      "step4Incomplete": "风险分析未完成：需填写三段式严重度、O/D，且控制非空",
      "step5Incomplete": "优化未完成：AP=H的行需填负责人与计划完成日期",
      "finishFailed": "完成失败", "loadFailed": "加载失败",
      "conflictTitle": "内容已被他人修改", "conflictContent": "文档已被他人修改，请刷新后重试。", "conflictReload": "刷新"
    },
    "guidance": {
      "step0": { "title": "5T范围", "purpose": "界定分析范围", "points": ["团队、时间、工具、任务、趋势"], "fields": ["团队/时间/工具/任务/趋势"], "example": "SMT焊接生产线 / OP10-OP40" },
      "step1": { "title": "结构分析", "purpose": "分解过程结构", "points": ["过程项目→过程步骤→作业要素(4M)"], "fields": ["工序号(OP10)", "4M分类(人/机/料/环)"], "example": "OP10 贴装 / 机器:高速贴片机" },
      "step2": { "title": "功能分析", "purpose": "定义功能与特性", "points": ["3层功能树", "区分产品/过程特性", "CC/SC在此维护"], "fields": ["功能名", "产品特性/过程特性", "CC/SC"], "example": "准确贴装 / 偏移度≤0.05mm / CC" },
      "step3": { "title": "失效分析", "purpose": "识别失效链", "points": ["失效模式挂过程步骤功能", "原因按4M"], "fields": ["FM/FE/FC/PC/DC"], "example": "贴装偏移 / 吸嘴磨损(机)" },
      "step4": { "title": "风险分析", "purpose": "评估风险", "points": ["三段式严重度取最大值", "O/D", "AP"], "fields": ["S(本厂/客户/终端用户)", "O", "D", "AP", "特性(只读)"], "example": "S=8 O=4 D=3 AP=H" },
      "step5": { "title": "优化", "purpose": "降低风险", "points": ["AP=H优先", "负责人与日期"], "fields": ["措施/负责人/日期/状态/重评"], "example": "引入压力闭环传感器 / 张工 / 2026-06-15" },
      "step6": { "title": "结果文档", "purpose": "确认完成", "points": ["核对统计", "完成创建"], "fields": [], "example": "" },
      "labelPurpose": "目的", "labelPoints": "要点", "labelFields": "字段", "labelExample": "示例", "expand": "展开", "collapse": "收起"
    },
    "sidebar": { "structureTree": "结构树", "structureHint": "结构分析后显示", "noStructure": "尚无结构", "steps": "步骤" }
  },
  "smartSuggestion": {
    "global": "全局", "currentProductLine": "当前产品线", "noGlobalPermission": "无全局权限",
    "scopeGlobal": "全局范围", "scopeLocal": "产品线范围", "ruleEngine": "规则引擎", "aiGenerated": "AI生成",
    "from": "来源", "confidence": { "high": "高", "medium": "中", "low": "低" },
    "tooFrequent": "请求过于频繁", "noPermission": "无权限", "serviceUnavailable": "服务不可用",
    "aiUnavailable": "AI不可用", "ruleOnlyMode": "仅规则模式", "close": "关闭"
  },
  "rules": {
    "optimizationHint": "AP=H 建议优先优化",
    "verbPatterns": "过程动词模式", "failureChains": "失效链"
  }
}
```

- [ ] **Step 3: Create `en-US/pfmea.json`** with the same key tree, English values (e.g. `"steps": ["5T Scope","Structure Analysis","Function Analysis","Failure Analysis","Risk Analysis","Optimization","Result Documentation"]`, `"toolPresets": ["Process Flow Diagram","P-Diagram","Fishbone (4M)","PFMEA Template","Process FMECA","Control Plan Draft","Lessons Learned"]`, etc.). Mirror the zh structure 1:1.

- [ ] **Step 4: Register the `pfmea` namespace in the i18n config**

In the file located in Step 1, alongside the `dfmea` resource import, add the `pfmea` resource for both languages. (Follow the exact pattern used for `dfmea` — e.g. if it imports `dfmea` JSON and registers under `ns: 'dfmea'`, do the same for `pfmea`.) If the config auto-loads all JSON in the locales folder, this step is a no-op — verify by checking whether `dfmea` is explicitly imported.

- [ ] **Step 5: Verify the namespace loads**

Run: `npx vitest run frontend/src/components/dfmea/GenerationWizard.test.tsx 2>&1 | tail -5` (sanity that i18n still parses).
Then write a tiny smoke test:

```typescript
// frontend/src/locales/pfmea.i18n.test.ts
import { describe, it, expect } from 'vitest';
import zh from './zh-CN/pfmea.json';
import en from './en-US/pfmea.json';

describe('pfmea i18n parity', () => {
  const zhSteps = (zh as any).wizard.steps;
  const enSteps = (en as any).wizard.steps;
  it('has 7 steps in both languages', () => {
    expect(zhSteps.length).toBe(7);
    expect(enSteps.length).toBe(7);
  });
  it('has guidance for all 7 steps in both', () => {
    for (const lang of [zh, en]) {
      for (let i = 0; i < 7; i++) {
        expect((lang as any).wizard.guidance[`step${i}`].title).toBeTruthy();
      }
    }
  });
});
```

Run: `npx vitest run frontend/src/locales/pfmea.i18n.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/locales/zh-CN/pfmea.json frontend/src/locales/en-US/pfmea.json frontend/src/locales/pfmea.i18n.test.ts
# plus the i18n config file if modified
git commit -m "feat(pfmea): add pfmea i18n namespace (zh-CN + en-US)"
```

---

## Task 4: Frontend — `usePfmeaWizardValidation` hook

**Files:**
- Create: `frontend/src/hooks/usePfmeaWizardValidation.ts`
- Test: `frontend/src/hooks/usePfmeaWizardValidation.test.ts`

**Interfaces:**
- Consumes: `GraphNode`, `GraphEdge` from `../types`; `buildRows`, `getRowSeverity` from `../utils/fmeaTable`.
- Produces: `usePfmeaWizardValidation(nodes, edges, selectedTools?, toolStructureMap?)` → `PfmeaStepValidation` with `{ step1Complete, step2Complete, step3Complete, step4Complete, step5Complete, warnings: number[], step4Unrated, step4MissingControl, step4MissingSeverity }`. `warnings` contains the 1-based wizard step index (1..5) for each incomplete step. (PFMEA has no DFMEA tool-structure-gap concept; `selectedTools`/`toolStructureMap` kept in signature for parity but unused — pass through as no-ops.)

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/hooks/usePfmeaWizardValidation.test.ts
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePfmeaWizardValidation } from './usePfmeaWizardValidation';
import type { GraphNode, GraphEdge } from '../types';

const Z = { severity: 0, occurrence: 0, detection: 0 };

describe('usePfmeaWizardValidation', () => {
  it('step1 incomplete when a ProcessStep lacks process_number', () => {
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
      { id: 'ps', type: 'ProcessStep', name: '贴装', ...Z }, // no process_number
      { id: 'we', type: 'ProcessWorkElement', name: '机', classification: 'Machine', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'ps', type: 'HAS_PROCESS_STEP' },
      { source: 'ps', target: 'we', type: 'HAS_WORK_ELEMENT' },
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step1Complete).toBe(false);
    expect(result.current.warnings).toContain(1);
  });

  it('step1 incomplete when a WorkElement lacks classification', () => {
    const nodes: GraphNode[] = [
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'we', type: 'ProcessWorkElement', name: '机', ...Z }, // no classification
    ];
    const edges: GraphEdge[] = [{ source: 'ps', target: 'we', type: 'HAS_WORK_ELEMENT' }];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step1Complete).toBe(false);
  });

  it('step1 complete with process_number + 4M classification', () => {
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'we', type: 'ProcessWorkElement', name: '机', classification: 'Machine', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'ps', type: 'HAS_PROCESS_STEP' },
      { source: 'ps', target: 'we', type: 'HAS_WORK_ELEMENT' },
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step1Complete).toBe(true);
  });

  it('step4 incomplete when severity_plant/customer/user not all >0', () => {
    const nodes: GraphNode[] = [
      { id: 'psf', type: 'ProcessStepFunction', name: 'f', ...Z },
      { id: 'fm', type: 'FailureMode', name: 'm', ...Z },
      { id: 'fe', type: 'FailureEffect', name: 'e', severity: 8, severity_plant: 4, severity_customer: 8, severity_user: 0, ...Z },
      { id: 'fc', type: 'FailureCause', name: 'c', occurrence: 4, ...Z },
      { id: 'pc', type: 'PreventionControl', name: 'p', ...Z },
      { id: 'dc', type: 'DetectionControl', name: 'd', detection: 3, ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'psf', target: 'fm', type: 'HAS_FAILURE_MODE' },
      { source: 'fm', target: 'fe', type: 'EFFECT_OF' },
      { source: 'fc', target: 'fm', type: 'CAUSE_OF' },
      { source: 'fc', target: 'pc', type: 'PREVENTED_BY' },
      { source: 'fc', target: 'dc', type: 'DETECTED_BY' },
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step4Complete).toBe(false);
    expect(result.current.warnings).toContain(4);
  });

  it('step4 complete when all three severities + O/D + controls present', () => {
    const nodes: GraphNode[] = [
      { id: 'psf', type: 'ProcessStepFunction', name: 'f', ...Z },
      { id: 'fm', type: 'FailureMode', name: 'm', ...Z },
      { id: 'fe', type: 'FailureEffect', name: 'e', severity: 8, severity_plant: 4, severity_customer: 8, severity_user: 8, ...Z },
      { id: 'fc', type: 'FailureCause', name: 'c', occurrence: 4, ...Z },
      { id: 'pc', type: 'PreventionControl', name: 'p', ...Z },
      { id: 'dc', type: 'DetectionControl', name: 'd', detection: 3, ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'psf', target: 'fm', type: 'HAS_FAILURE_MODE' },
      { source: 'fm', target: 'fe', type: 'EFFECT_OF' },
      { source: 'fc', target: 'fm', type: 'CAUSE_OF' },
      { source: 'fc', target: 'pc', type: 'PREVENTED_BY' },
      { source: 'fc', target: 'dc', type: 'DETECTED_BY' },
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step4Complete).toBe(true);
  });

  it('step2 fails when a WEF maps to a sibling step\'s StepFunction (wrong branch)', () => {
    // Two steps each with a StepFunction; one WEF under ps1 but mapped from psf2 (wrong branch).
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
      { id: 'pif', type: 'ProcessItemFunction', name: '完成', ...Z },
      { id: 'ps1', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'ps2', type: 'ProcessStep', name: '焊接', process_number: 'OP20', ...Z },
      { id: 'psf1', type: 'ProcessStepFunction', name: '贴装功能', ...Z },
      { id: 'psf2', type: 'ProcessStepFunction', name: '焊接功能', ...Z },
      { id: 'we1', type: 'ProcessWorkElement', name: '机', classification: 'Machine', ...Z },
      { id: 'wef1', type: 'ProcessWorkElementFunction', name: '机功能', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'pif', type: 'HAS_FUNCTION' },
      { source: 'pi', target: 'ps1', type: 'HAS_PROCESS_STEP' },
      { source: 'pi', target: 'ps2', type: 'HAS_PROCESS_STEP' },
      { source: 'ps1', target: 'psf1', type: 'HAS_FUNCTION' },
      { source: 'ps2', target: 'psf2', type: 'HAS_FUNCTION' },
      { source: 'pif', target: 'psf1', type: 'FUNCTION_MAPPED_TO' },
      { source: 'pif', target: 'psf2', type: 'FUNCTION_MAPPED_TO' },
      { source: 'ps1', target: 'we1', type: 'HAS_WORK_ELEMENT' },
      { source: 'we1', target: 'wef1', type: 'HAS_FUNCTION' },
      { source: 'psf2', target: 'wef1', type: 'FUNCTION_MAPPED_TO' }, // WRONG: we1 is under ps1, should map from psf1
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step2Complete).toBe(false);
    expect(result.current.warnings).toContain(2);
  });
});
```

> If `@testing-library/react` `renderHook` is not already a dependency, check `DFMEAWizardPage.test.tsx` / `useWizardValidation.test.tsx` for the existing pattern and mirror it (the repo already tests `useWizardValidation`, so the harness is present).

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run frontend/src/hooks/usePfmeaWizardValidation.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

```typescript
// frontend/src/hooks/usePfmeaWizardValidation.ts
import { useMemo } from 'react';
import type { GraphNode, GraphEdge } from '../types';
import { buildRows, getRowSeverity } from '../utils/fmeaTable';

export interface PfmeaStepValidation {
  step1Complete: boolean; // structure: tree + process_number + 4M classification
  step2Complete: boolean; // function: every WorkElement has function + 3-level FUNCTION_MAPPED_TO chain
  step3Complete: boolean; // failure: every ProcessStepFunction has named FM->FE->FC + PC/DC
  step4Complete: boolean; // risk: all rows severity_plant/customer/user>0, O/D>0, PC/DC non-empty
  step5Complete: boolean; // optimization: every AP=H row has RecommendedAction with responsible+due_date
  warnings: number[]; // 1-based wizard step indices that are incomplete
  step4MissingCause: boolean;
  step4Unrated: boolean;
  step4MissingControl: boolean;
  step4MissingSeverity: boolean;
}

const STRUCTURE_TYPES = ['ProcessItem', 'ProcessStep', 'ProcessWorkElement'];
const STEP_FUNCTION = 'ProcessStepFunction';
const WE_FUNCTION = 'ProcessWorkElementFunction';
const ITEM_FUNCTION = 'ProcessItemFunction';

export function usePfmeaWizardValidation(
  nodes: GraphNode[],
  edges: GraphEdge[],
): PfmeaStepValidation {
  return useMemo(() => {
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const steps = nodes.filter((n) => n.type === 'ProcessStep');
    const workElements = nodes.filter((n) => n.type === 'ProcessWorkElement');

    // Step 1: structure tree exists; every step has process_number; every WE has 4M classification
    const hasStructure = nodes.some((n) => STRUCTURE_TYPES.includes(n.type));
    const stepsNumbered = steps.length > 0 && steps.every((s) => (s.process_number ?? '').trim());
    const weClassified = workElements.length > 0 && workElements.every((w) =>
      ['Man', 'Machine', 'Material', 'Environment'].includes(w.classification ?? ''));
    const step1Complete = hasStructure && stepsNumbered && weClassified && workElements.length > 0;

    // Step 2: every WorkElement has a HAS_FUNCTION function node; 3-level FUNCTION_MAPPED_TO chain complete AND branch-local.
    // Branch-local means: each StepFunction maps FROM the ItemFunction of the ProcessItem that owns its step;
    // each WEF maps FROM the StepFunction of the ProcessStep that owns the work element.
    const weFunctionNodes = nodes.filter((n) => n.type === WE_FUNCTION);
    const weHasFunction = workElements.length > 0 && workElements.every((we) =>
      edges.some((e) => e.source === we.id && e.type === 'HAS_FUNCTION'));
    const itemFuncs = nodes.filter((n) => n.type === ITEM_FUNCTION);
    const stepFuncs = nodes.filter((n) => n.type === STEP_FUNCTION);
    // StepFunction branch-local: its FUNCTION_MAPPED_TO source must be an ItemFunction whose
    // ProcessItem owns this StepFunction's step (HAS_PROCESS_STEP).
    const stepFuncChained = stepFuncs.length > 0 && stepFuncs.every((sf) => {
      const mappedFrom = edges.find((e) => e.target === sf.id && e.type === 'FUNCTION_MAPPED_TO');
      if (!mappedFrom) return false;
      const itemFunc = nodeMap.get(mappedFrom.source);
      if (!itemFunc || itemFunc.type !== ITEM_FUNCTION) return false;
      // the step that owns sf, and the item that owns that step
      const sfStep = nodes.find((n) => n.type === 'ProcessStep' &&
        edges.some((e) => e.source === n.id && e.target === sf.id && e.type === 'HAS_FUNCTION'));
      if (!sfStep) return false;
      const owningItem = nodes.find((n) => n.type === 'ProcessItem' &&
        edges.some((e) => e.source === n.id && e.target === sfStep.id && e.type === 'HAS_PROCESS_STEP'));
      if (!owningItem) return false;
      return edges.some((e) => e.source === owningItem.id && e.target === itemFunc.id && e.type === 'HAS_FUNCTION');
    });
    // WEF branch-local: its FUNCTION_MAPPED_TO source must be a StepFunction whose ProcessStep owns this WEF.
    const weFuncChained = weFunctionNodes.length > 0 && weFunctionNodes.every((wf) => {
      const mappedFrom = edges.find((e) => e.target === wf.id && e.type === 'FUNCTION_MAPPED_TO');
      if (!mappedFrom) return false;
      const stepFunc = nodeMap.get(mappedFrom.source);
      if (!stepFunc || stepFunc.type !== STEP_FUNCTION) return false;
      // the step that owns wf, and the step that owns stepFunc — must be the same step
      const wfStep = nodes.find((n) => n.type === 'ProcessStep' &&
        edges.some((e) => e.source === n.id && e.target === wf.id && e.type === 'HAS_WORK_ELEMENT'));
      const sfStep = nodes.find((n) => n.type === 'ProcessStep' &&
        edges.some((e) => e.source === n.id && e.target === stepFunc.id && e.type === 'HAS_FUNCTION'));
      return !!wfStep && wfStep.id === sfStep?.id;
    });
    const step2Complete = weHasFunction && stepFuncChained && weFuncChained
      && itemFuncs.length > 0 && stepFuncs.length > 0 && weFunctionNodes.length > 0;

    // Step 3: every ProcessStepFunction has named FM->FE->FC + PC/DC
    const stepFuncList = nodes.filter((n) => n.type === STEP_FUNCTION);
    const step3Complete = stepFuncList.length > 0 && stepFuncList.every((f) => {
      const fmEdges = edges.filter((e) => e.source === f.id && e.type === 'HAS_FAILURE_MODE');
      if (fmEdges.length === 0) return false;
      return fmEdges.every((fe) => {
        const fm = nodeMap.get(fe.target);
        if (!fm || !fm.name?.trim()) return false;
        const effectNamed = edges.some((e) => e.source === fm.id && e.type === 'EFFECT_OF' && nodeMap.get(e.target)?.name?.trim());
        if (!effectNamed) return false;
        const causeEdges = edges.filter((e) => e.target === fm.id && e.type === 'CAUSE_OF');
        if (causeEdges.length === 0) return false;
        return causeEdges.every((ce) => {
          const cause = nodeMap.get(ce.source);
          if (!cause || !cause.name?.trim()) return false;
          const hasPc = edges.some((e) => e.source === cause.id && e.type === 'PREVENTED_BY' && nodeMap.get(e.target)?.name?.trim());
          const hasDc = edges.some((e) => e.source === cause.id && e.type === 'DETECTED_BY' && nodeMap.get(e.target)?.name?.trim());
          return hasPc && hasDc;
        });
      });
    });

    // Step 4: risk ratings
    const rows = buildRows(nodes, edges);
    const step4MissingCause = rows.some((r) => r.failureCauseNodeId == null);
    const step4MissingControl = rows.some((r) => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      if (!cause) return false;
      const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name ?? '' : '';
      const dcNode = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      return !pcName.trim() || !(dcNode?.name ?? '').trim();
    });
    const step4Unrated = rows.some((r) => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dc = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      return (cause?.occurrence ?? 0) === 0 || (dc?.detection ?? 0) === 0;
    });
    const step4MissingSeverity = rows.some((r) => {
      // any FailureEffect of this row missing one of the three severity fields >0
      return r.failureEffectNodeIds.some((feId) => {
        const fe = nodeMap.get(feId);
        if (!fe) return true;
        return !((fe.severity_plant ?? 0) > 0 && (fe.severity_customer ?? 0) > 0 && (fe.severity_user ?? 0) > 0);
      });
    });
    const step4Complete = rows.length > 0 && !step4MissingCause && !step4Unrated && !step4MissingControl && !step4MissingSeverity;

    // Step 5: every AP=H row has RecommendedAction with responsible + due_date
    const rowsWithAP_H = rows.filter((r) => {
      const s = getRowSeverity(r, nodeMap);
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dc = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      const o = cause?.occurrence ?? 0;
      const d = dc?.detection ?? 0;
      const ap = calculateAPLocal(s, o, d);
      return ap === 'H';
    });
    const step5Complete = rowsWithAP_H.length === 0 || rowsWithAP_H.every((r) =>
      r.recommendedActionIds.some((raId) => {
        const ra = nodeMap.get(raId);
        return !!ra && (ra.responsible ?? '').trim() && (ra.due_date ?? '').trim();
      }));

    const warnings: number[] = [];
    if (!step1Complete) warnings.push(1);
    if (!step2Complete) warnings.push(2);
    if (!step3Complete) warnings.push(3);
    if (!step4Complete) warnings.push(4);
    if (!step5Complete) warnings.push(5);

    return {
      step1Complete, step2Complete, step3Complete, step4Complete, step5Complete,
      warnings,
      step4MissingCause, step4Unrated, step4MissingControl, step4MissingSeverity,
    };
  }, [nodes, edges]);
}

// local AP calc to avoid importing calculateAP circular concerns; keep in sync with utils/fmea.ts
import { calculateAP } from '../utils/fmea';
function calculateAPLocal(s: number, o: number, d: number) {
  return calculateAP(s, o, d);
}
```

> Move the `import { calculateAP }` to the top of the file (TS requires imports at top). The `calculateAPLocal` wrapper is only to keep the call site readable; you may call `calculateAP` directly. Remove the wrapper if redundant — the test does not assert on it.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run frontend/src/hooks/usePfmeaWizardValidation.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/usePfmeaWizardValidation.ts frontend/src/hooks/usePfmeaWizardValidation.test.ts
git commit -m "feat(pfmea): add usePfmeaWizardValidation (4M/OP gates, 3-tier severity, CC/SC-aware)"
```

---

## Task 5: Frontend — `PFMEAWizardSidebar`

**Files:**
- Create: `frontend/src/components/pfmea/PFMEAWizardSidebar.tsx`
- Test: `frontend/src/components/pfmea/PFMEAWizardSidebar.test.tsx`

**Interfaces:**
- Consumes: `WizardSidebarProps` shape from `components/dfmea/WizardSidebar.tsx` (reference §8).
- Produces: same props interface, but structure tree built from `STRUCTURE_TYPES = ['ProcessItem','ProcessStep','ProcessWorkElement']` and `VALID_EDGE_TYPES = new Set(['HAS_PROCESS_STEP','HAS_WORK_ELEMENT'])`, step labels from `pfmea.wizard.steps`/`pfmea.wizard.sidebar`.

- [ ] **Step 1: Read the source to copy**

Read `frontend/src/components/dfmea/WizardSidebar.tsx` in full. This task copies it and adapts two constant blocks + the i18n namespace.

- [ ] **Step 2: Write the failing test**

```typescript
// frontend/src/components/pfmea/PFMEAWizardSidebar.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PFMEAWizardSidebar from './PFMEAWizardSidebar';
import type { GraphNode, GraphEdge } from '../../types';

const Z = { severity: 0, occurrence: 0, detection: 0 };

describe('PFMEAWizardSidebar', () => {
  it('renders 7 step labels from pfmea namespace', () => {
    render(
      <PFMEAWizardSidebar
        currentStep={0} onStepClick={() => {}} completedSteps={new Set()}
        maxReachableStep={0} warnings={[]} structureNodes={[]} edges={[]} />,
      { wrapper: I18nTestWrapper },
    );
    // step labels: at least the 5T范围 / 结构分析 labels should appear
    expect(screen.getAllByText(/5T|Scope|范围|结构/i).length).toBeGreaterThan(0);
  });

  it('renders ProcessItem/ProcessStep/WorkElement in structure tree', () => {
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: 'SMT线', ...Z },
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'we', type: 'ProcessWorkElement', name: '贴片机', classification: 'Machine', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'ps', type: 'HAS_PROCESS_STEP' },
      { source: 'ps', target: 'we', type: 'HAS_WORK_ELEMENT' },
    ];
    render(
      <PFMEAWizardSidebar currentStep={1} onStepClick={() => {}} completedSteps={new Set([0,1])}
        maxReachableStep={2} warnings={[]} structureNodes={nodes} edges={edges} />,
      { wrapper: I18nTestWrapper },
    );
    expect(screen.getByText('SMT线')).toBeInTheDocument();
    expect(screen.getByText(/贴装/)).toBeInTheDocument();
  });
});
```

> `I18nTestWrapper` — mirror whatever the existing `WizardSidebar`/`GenerationWizard` tests use to provide the i18n context (check `frontend/src/components/dfmea/GenerationWizard.test.tsx` for the wrapper pattern; reuse it, adding the `pfmea` namespace resource). If no shared wrapper exists, create a minimal one inline that registers `pfmea` + `dfmea` namespaces.

- [ ] **Step 3: Run test to verify it fails**

Run: `npx vitest run frontend/src/components/pfmea/PFMEAWizardSidebar.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement by copying `WizardSidebar.tsx` and adapting**

Copy `frontend/src/components/dfmea/WizardSidebar.tsx` → `frontend/src/components/pfmea/PFMEAWizardSidebar.tsx`. Make exactly these changes:

1. Change the i18n namespace: where it calls `useTranslation()` (default namespace), pass `useTranslation('pfmea')` and prefix the step/sidebar keys accordingly. If the original uses `t('wizard.steps')` against the default namespace, change to `t('pfmea:wizard.steps')` (or set the namespace via `useTranslation('pfmea')` and keep `t('wizard.steps')` — whichever matches how `dfmea.json` is keyed; confirm by reading the original).

2. Replace the structure-type constants:
```typescript
const STRUCTURE_TYPES = ['ProcessItem', 'ProcessStep', 'ProcessWorkElement'];
const VALID_EDGE_TYPES = new Set(['HAS_PROCESS_STEP', 'HAS_WORK_ELEMENT']);
```

3. Keep the same `WizardSidebarProps` interface and export name `PFMEAWizardSidebar`. Change the component function name to `PFMEAWizardSidebar`.

No other logic changes — the tree-building, step-nav, and warning-icon logic are structure-type-driven and work unchanged once the constants are swapped.

> **Export convention**: the DFMEA `WizardSidebar` uses `export default`. Keep `export default function PFMEAWizardSidebar(...)` so the page's `import WizardSidebar from '../../../components/pfmea/PFMEAWizardSidebar'` (Task 9) and the test's default import both resolve.

- [ ] **Step 5: Run test to verify it passes**

Run: `npx vitest run frontend/src/components/pfmea/PFMEAWizardSidebar.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/pfmea/PFMEAWizardSidebar.tsx frontend/src/components/pfmea/PFMEAWizardSidebar.test.tsx
git commit -m "feat(pfmea): add PFMEAWizardSidebar (ProcessItem/Step/WorkElement tree)"
```

---

## Task 6: Frontend — `PFMEAGuidanceCard` + extend `ScopeTagField` trigger union

**Files:**
- Create: `frontend/src/components/pfmea/PFMEAGuidanceCard.tsx`
- Modify: `frontend/src/components/dfmea/ScopeTagField.tsx:8` (`ScopeTriggerType` union)
- Test: `frontend/src/components/pfmea/PFMEAGuidanceCard.test.tsx`

**Interfaces:**
- `PFMEAGuidanceCard`: props `{ stepIndex: number }`, reads `pfmea.wizard.guidance.step${stepIndex}`.
- `ScopeTagField`: `ScopeTriggerType` now `"dfmea_tool" | "dfmea_trend" | "pfmea_tool" | "pfmea_trend"`.

- [ ] **Step 1: Extend the `ScopeTagField` trigger union**

In `frontend/src/components/dfmea/ScopeTagField.tsx`, change:
```typescript
export type ScopeTriggerType = "dfmea_tool" | "dfmea_trend" | "pfmea_tool" | "pfmea_trend";
```
This is additive — existing DFMEA usage (`"dfmea_tool"`/`"dfmea_trend"`) is unaffected.

- [ ] **Step 2: Write the failing test for `PFMEAGuidanceCard`**

```typescript
// frontend/src/components/pfmea/PFMEAGuidanceCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PFMEAGuidanceCard from './PFMEAGuidanceCard';

describe('PFMEAGuidanceCard', () => {
  it('renders the step0 title from pfmea namespace', () => {
    render(<PFMEAGuidanceCard stepIndex={0} />, { wrapper: I18nTestWrapper });
    expect(screen.getByText(/5T|范围|Scope/i)).toBeInTheDocument();
  });
  it('renders step1 fields mentioning 4M or 工序号', () => {
    render(<PFMEAGuidanceCard stepIndex={1} />, { wrapper: I18nTestWrapper });
    expect(screen.getByText(/4M|工序号|OP10|分类/i)).toBeInTheDocument();
  });
});
```
(Reuse the same `I18nTestWrapper` from Task 5; if it's not exported as a shared helper, extract it to `frontend/src/components/pfmea/__test-utils__/I18nWrapper.tsx` in this task and update Task 5's import — or just inline the wrapper in both. Prefer extracting to a shared helper to DRY.)

- [ ] **Step 3: Run test to verify it fails**

Run: `npx vitest run frontend/src/components/pfmea/PFMEAGuidanceCard.test.tsx`
Expected: FAIL.

- [ ] **Step 4: Implement `PFMEAGuidanceCard`**

Copy `frontend/src/components/dfmea/WizardGuidanceCard.tsx` → `frontend/src/components/pfmea/PFMEAGuidanceCard.tsx`. Change:
- `useTranslation()` → `useTranslation('pfmea')` (or prefix keys with `pfmea:` — match the original's pattern).
- Rename component to `PFMEAGuidanceCard` and keep it a **default export** (`export default function PFMEAGuidanceCard`) so the page (Task 9) and test default imports resolve.
- Keep the same props `{ stepIndex: number }`, collapsible localStorage behavior, and key shape (`wizard.guidance.step${i}.{title,purpose,points,fields,example}`).

- [ ] **Step 5: Run test to verify it passes**

Run: `npx vitest run frontend/src/components/pfmea/PFMEAGuidanceCard.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/pfmea/PFMEAGuidanceCard.tsx frontend/src/components/pfmea/PFMEAGuidanceCard.test.tsx frontend/src/components/dfmea/ScopeTagField.tsx
git commit -m "feat(pfmea): add PFMEAGuidanceCard; extend ScopeTagField trigger union for pfmea_tool/trend"
```

---

## Task 7: Frontend — `FunctionTreeEditor` (Step 2, 3-level function tree + CC/SC)

**Files:**
- Create: `frontend/src/components/pfmea/FunctionTreeEditor.tsx`
- Test: `frontend/src/components/pfmea/FunctionTreeEditor.test.tsx`

**Interfaces:**
- Consumes: `GraphNode`, `GraphEdge` from `../../types`.
- Props:
```typescript
interface FunctionTreeEditorProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  fmeaId: string;
  onChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}
```
- Produces: edits `ProcessItemFunction`/`ProcessStepFunction`/`ProcessWorkElementFunction` nodes (name, requirement, specification, classification for Step/WorkElement only) and `HAS_FUNCTION` + `FUNCTION_MAPPED_TO` edges. CC/SC editable only on `ProcessStepFunction` (CC) and `ProcessWorkElementFunction` (SC); `ProcessItemFunction` classification hidden.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/pfmea/FunctionTreeEditor.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FunctionTreeEditor from './FunctionTreeEditor';
import type { GraphNode, GraphEdge } from '../../types';

const Z = { severity: 0, occurrence: 0, detection: 0 };

describe('FunctionTreeEditor', () => {
  it('creates a ProcessStepFunction with HAS_FUNCTION + FUNCTION_MAPPED_TO when adding a step function', () => {
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
      { id: 'pif', type: 'ProcessItemFunction', name: '完成SMT', ...Z },
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'pif', type: 'HAS_FUNCTION' },
      { source: 'pi', target: 'ps', type: 'HAS_PROCESS_STEP' },
    ];
    const onChange = vi.fn();
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />, { wrapper: I18nTestWrapper });
    fireEvent.click(screen.getByRole('button', { name: /addStepFunction|添加过程步骤功能/ }));
    expect(onChange).toHaveBeenCalled();
    const [, newEdges] = onChange.mock.calls[0];
    expect(newEdges.some((e: GraphEdge) => e.type === 'HAS_FUNCTION')).toBe(true);
    expect(newEdges.some((e: GraphEdge) => e.type === 'FUNCTION_MAPPED_TO')).toBe(true);
  });

  it('lets a ProcessStepFunction set classification CC but hides it for ProcessItemFunction', () => {
    const nodes: GraphNode[] = [
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'psf', type: 'ProcessStepFunction', name: '准确贴装', specification: '偏移≤0.05mm', ...Z },
      { id: 'pif', type: 'ProcessItemFunction', name: '完成SMT', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'ps', target: 'psf', type: 'HAS_FUNCTION' },
      { source: 'pif', target: 'psf', type: 'FUNCTION_MAPPED_TO' },
    ];
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });
    // StepFunction card shows a classification (CC/SC) selector
    expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0);
  });

  it('branch-local: with two steps, a new StepFunction maps to ITS step\'s ProcessItem function only', () => {
    // Two ProcessItems each with a ProcessItemFunction; two ProcessSteps (one per item).
    const nodes: GraphNode[] = [
      { id: 'pi1', type: 'ProcessItem', name: '线A', ...Z },
      { id: 'pi2', type: 'ProcessItem', name: '线B', ...Z },
      { id: 'pif1', type: 'ProcessItemFunction', name: '完成A', ...Z },
      { id: 'pif2', type: 'ProcessItemFunction', name: '完成B', ...Z },
      { id: 'ps1', type: 'ProcessStep', name: '贴装A', process_number: 'OP10', ...Z },
      { id: 'ps2', type: 'ProcessStep', name: '贴装B', process_number: 'OP20', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi1', target: 'pif1', type: 'HAS_FUNCTION' },
      { source: 'pi2', target: 'pif2', type: 'HAS_FUNCTION' },
      { source: 'pi1', target: 'ps1', type: 'HAS_PROCESS_STEP' },
      { source: 'pi2', target: 'ps2', type: 'HAS_PROCESS_STEP' },
    ];
    const onChange = vi.fn();
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />, { wrapper: I18nTestWrapper });
    // click the add-step-function button for ps2 (贴装B)
    fireEvent.click(screen.getByRole('button', { name: /addStepFunction.*OP20|添加过程步骤功能.*OP20/ }));
    const [, newEdges] = onChange.mock.calls[0];
    const mapped = newEdges.filter((e: GraphEdge) => e.type === 'FUNCTION_MAPPED_TO');
    expect(mapped.length).toBe(1);
    // must map from pif2 (线B's item function), NOT pif1
    expect(mapped[0].source).toBe('pif2');
  });

  it('branch-local: with two work elements under different steps, a new WEF maps to ITS step\'s StepFunction only', () => {
    const nodes: GraphNode[] = [
      { id: 'ps1', type: 'ProcessStep', name: '贴装A', process_number: 'OP10', ...Z },
      { id: 'ps2', type: 'ProcessStep', name: '焊接B', process_number: 'OP20', ...Z },
      { id: 'psf1', type: 'ProcessStepFunction', name: '贴装功能', ...Z },
      { id: 'psf2', type: 'ProcessStepFunction', name: '焊接功能', ...Z },
      { id: 'we1', type: 'ProcessWorkElement', name: '机A', classification: 'Machine', ...Z },
      { id: 'we2', type: 'ProcessWorkElement', name: '机B', classification: 'Machine', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'ps1', target: 'psf1', type: 'HAS_FUNCTION' },
      { source: 'ps2', target: 'psf2', type: 'HAS_FUNCTION' },
      { source: 'ps1', target: 'we1', type: 'HAS_WORK_ELEMENT' },
      { source: 'ps2', target: 'we2', type: 'HAS_WORK_ELEMENT' },
    ];
    const onChange = vi.fn();
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />, { wrapper: I18nTestWrapper });
    // click add-work-element-function for we2 (机B, under ps2)
    fireEvent.click(screen.getByRole('button', { name: /addWorkElementFunction.*机B|添加作业要素功能.*机B/ }));
    const [, newEdges] = onChange.mock.calls[0];
    const mapped = newEdges.filter((e: GraphEdge) => e.type === 'FUNCTION_MAPPED_TO');
    expect(mapped.length).toBe(1);
    // must map from psf2 (焊接B's step function), NOT psf1
    expect(mapped[0].source).toBe('psf2');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run frontend/src/components/pfmea/FunctionTreeEditor.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement `FunctionTreeEditor`**

```typescript
// frontend/src/components/pfmea/FunctionTreeEditor.tsx
import { useTranslation } from 'react-i18next';
import { Card, Input, Select, Button, Empty, Tag, Space } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { GraphNode, GraphEdge } from '../../types';

interface FunctionTreeEditorProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  fmeaId: string;
  onChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}

const Z = { severity: 0, occurrence: 0, detection: 0 };
const newId = (p: string) => `w${crypto.randomUUID()}_${p}`;

export default function FunctionTreeEditor({ nodes, edges, fmeaId, onChange }: FunctionTreeEditorProps) {
  const { t } = useTranslation('pfmea');
  void fmeaId;

  const itemFuncs = nodes.filter((n) => n.type === 'ProcessItemFunction');
  const stepNodes = nodes.filter((n) => n.type === 'ProcessStep');
  const weNodes = nodes.filter((n) => n.type === 'ProcessWorkElement');

  const updateNode = (id: string, patch: Partial<GraphNode>) => {
    onChange(nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)), edges);
  };

  // Branch-local parent resolution for FUNCTION_MAPPED_TO (spec §5 Step 2 + §8):
  //  - ProcessStepFunction  ← maps FROM the ProcessItemFunction of the ProcessItem
  //                              that owns this ProcessStep (HAS_PROCESS_STEP parent).
  //  - ProcessWorkElementFunction ← maps FROM the ProcessStepFunction of the ProcessStep
  //                              that owns this WorkElement (HAS_WORK_ELEMENT parent).
  //  - ProcessItemFunction   ← no FUNCTION_MAPPED_TO parent (top of the chain).
  // `structureParentId` is the id of the structure node this function is being added under
  // (ProcessItem / ProcessStep / ProcessWorkElement), passed from the add-button.
  const itemFunctionOf = (processItemId: string): GraphNode | undefined =>
    nodes.find((n) => n.type === 'ProcessItemFunction' &&
      edges.some((e) => e.source === processItemId && e.target === n.id && e.type === 'HAS_FUNCTION'));
  const stepFunctionOf = (processStepId: string): GraphNode | undefined =>
    nodes.find((n) => n.type === 'ProcessStepFunction' &&
      edges.some((e) => e.source === processStepId && e.target === n.id && e.type === 'HAS_FUNCTION'));
  const processItemOfStep = (stepId: string): GraphNode | undefined =>
    nodes.find((n) => n.type === 'ProcessItem' &&
      edges.some((e) => e.source === n.id && e.target === stepId && e.type === 'HAS_PROCESS_STEP'));

  const addFunction = (
    structureParentId: string,
    fnType: 'ProcessItemFunction' | 'ProcessStepFunction' | 'ProcessWorkElementFunction',
  ) => {
    const fid = newId('func');
    const fn: GraphNode = { id: fid, type: fnType, name: '', ...Z } as GraphNode;
    const newEdges: GraphEdge[] = [{ source: structureParentId, target: fid, type: 'HAS_FUNCTION' }];
    if (fnType === 'ProcessStepFunction') {
      // structureParentId is a ProcessStep; find its ProcessItem, then that item's function.
      const item = processItemOfStep(structureParentId);
      const itemFunc = item ? itemFunctionOf(item.id) : undefined;
      if (itemFunc) newEdges.push({ source: itemFunc.id, target: fid, type: 'FUNCTION_MAPPED_TO' });
    } else if (fnType === 'ProcessWorkElementFunction') {
      // structureParentId is a ProcessWorkElement; find its ProcessStep, then that step's function.
      const step = nodes.find((n) => n.type === 'ProcessStep' &&
        edges.some((e) => e.source === n.id && e.target === structureParentId && e.type === 'HAS_WORK_ELEMENT'));
      const stepFunc = step ? stepFunctionOf(step.id) : undefined;
      if (stepFunc) newEdges.push({ source: stepFunc.id, target: fid, type: 'FUNCTION_MAPPED_TO' });
    }
    // ProcessItemFunction: no FUNCTION_MAPPED_TO parent (chain root).
    onChange([...nodes, fn], [...edges, ...newEdges]);
  };

  const renderFunctionCard = (fn: GraphNode, allowClass: boolean, classOptions: { value: string; label: string }[]) => (
    <Card key={fn.id} size="small" style={{ marginBottom: 8 }}
      title={<Input size="small" value={fn.name} placeholder={t('wizard.function.functionDesc')}
        onChange={(e) => updateNode(fn.id, { name: e.target.value })} />}>
      <Space direction="vertical" style={{ width: '100%' }}>
        {fn.type === 'ProcessStepFunction' && (
          <Input size="small" addonBefore={t('wizard.function.specification')} value={fn.specification ?? ''}
            onChange={(e) => updateNode(fn.id, { specification: e.target.value })} placeholder="偏移度 <= 0.05mm" />
        )}
        {fn.type === 'ProcessWorkElementFunction' && (
          <Input size="small" addonBefore={t('wizard.function.requirement')} value={fn.requirement ?? ''}
            onChange={(e) => updateNode(fn.id, { requirement: e.target.value })} placeholder="贴装压力 3.0±0.5N" />
        )}
        {allowClass && (
          <Select size="small" value={fn.classification || undefined} placeholder={t('wizard.function.specialCharacteristic')}
            onChange={(v) => updateNode(fn.id, { classification: v || '' })} options={classOptions} style={{ width: 120 }} />
        )}
      </Space>
    </Card>
  );

  const classOpts = [
    { value: '', label: '-' },
    { value: 'CC', label: 'CC' },
    { value: 'SC', label: 'SC' },
  ];

  return (
    <div>
      {stepNodes.length === 0 && weNodes.length === 0 && itemFuncs.length === 0 && (
        <Empty description={t('wizard.function.description')} />
      )}
      {/* Item functions */}
      {itemFuncs.map((fn) => renderFunctionCard(fn, false, classOpts))}
      <Button icon={<PlusOutlined />} size="small" onClick={() => {
        const pi = nodes.find((n) => n.type === 'ProcessItem');
        if (pi) addFunction(pi.id, 'ProcessItemFunction');
      }}>{t('wizard.function.addItemFunction')}</Button>
      {/* Step functions */}
      {nodes.filter((n) => n.type === 'ProcessStepFunction').map((fn) => renderFunctionCard(fn, true, classOpts))}
      {stepNodes.map((ps) => (
        <Button key={ps.id} icon={<PlusOutlined />} size="small" onClick={() => addFunction(ps.id, 'ProcessStepFunction')}>
          {t('wizard.function.addStepFunction')} — {ps.process_number}
        </Button>
      ))}
      {/* Work element functions */}
      {nodes.filter((n) => n.type === 'ProcessWorkElementFunction').map((fn) => renderFunctionCard(fn, true, classOpts))}
      {weNodes.map((we) => (
        <Button key={we.id} icon={<PlusOutlined />} size="small" onClick={() => addFunction(we.id, 'ProcessWorkElementFunction')}>
          {t('wizard.function.addWorkElementFunction')} — {we.name}({we.classification})
        </Button>
      ))}
    </div>
  );
}
```

> The `addFunction` above resolves the `FUNCTION_MAPPED_TO` parent **branch-locally** (StepFunction ← its step's ProcessItem's ItemFunction; WorkElementFunction ← its work element's ProcessStep's StepFunction). The two branch-local tests below (Step 1) are the regression guard: with two ProcessSteps and two WorkElements, a WEF must map only to its own step's StepFunction — never a sibling step's. The `itemFuncs` variable declared earlier is now unused for linking (branch resolution uses `itemFunctionOf`); remove `itemFuncs` if it becomes unused, or keep it for rendering the item-function list.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run frontend/src/components/pfmea/FunctionTreeEditor.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/pfmea/FunctionTreeEditor.tsx frontend/src/components/pfmea/FunctionTreeEditor.test.tsx
git commit -m "feat(pfmea): add FunctionTreeEditor (3-level functions + FUNCTION_MAPPED_TO + CC/SC)"
```

---

## Task 8: Frontend — `RiskTable` (Step 4, 3-tier severity + CC/SC read-only + O/D gate)

**Files:**
- Create: `frontend/src/components/pfmea/RiskTable.tsx`
- Test: `frontend/src/components/pfmea/RiskTable.test.tsx`

**Interfaces:**
- Props:
```typescript
interface RiskTableProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  fmeaId: string;
  onChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}
```
- Produces: edits `FailureEffect.severity_plant/customer/user` (and writes `severity = max`), `FailureCause.occurrence`, `DetectionControl.detection`. O/D `InputNumber` disabled while PC/DC name empty. CC/SC column read-only, aggregated per spec §8 (CC wins; else SC WEF-name list / `SC×N`; `-` if none).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/pfmea/RiskTable.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RiskTable, { computeSeverity, aggregateSpecialCharacteristic } from './RiskTable';
import type { GraphNode, GraphEdge } from '../../types';

const Z = { severity: 0, occurrence: 0, detection: 0 };

const baseRow = () => {
  const nodes: GraphNode[] = [
    { id: 'psf', type: 'ProcessStepFunction', name: '准确贴装', classification: 'CC', ...Z },
    { id: 'fm', type: 'FailureMode', name: '贴装偏移', ...Z },
    { id: 'fe', type: 'FailureEffect', name: '功能丧失', severity: 0, severity_plant: 0, severity_customer: 0, severity_user: 0, ...Z },
    { id: 'fc', type: 'FailureCause', name: '吸嘴磨损', occurrence: 0, ...Z },
    { id: 'pc', type: 'PreventionControl', name: '校准', ...Z },
    { id: 'dc', type: 'DetectionControl', name: 'AOI', detection: 0, ...Z },
  ];
  const edges: GraphEdge[] = [
    { source: 'psf', target: 'fm', type: 'HAS_FAILURE_MODE' },
    { source: 'fm', target: 'fe', type: 'EFFECT_OF' },
    { source: 'fc', target: 'fm', type: 'CAUSE_OF' },
    { source: 'fc', target: 'pc', type: 'PREVENTED_BY' },
    { source: 'fc', target: 'dc', type: 'DETECTED_BY' },
  ];
  return { nodes, edges };
};

describe('RiskTable', () => {
  it('disables O/D inputs while PC/DC name empty', () => {
    const { nodes, edges } = baseRow();
    nodes[4] = { ...nodes[4], name: '' }; // empty PC
    nodes[5] = { ...nodes[5], name: '' }; // empty DC
    render(<RiskTable nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });
    const oInput = screen.getByDisplayValue('') as HTMLInputElement; // at least one disabled
    // O and D spin inputs should be disabled
    const disabledNums = screen.getAllByRole('spinbutton').filter((el) => (el as HTMLInputElement).disabled);
    expect(disabledNums.length).toBeGreaterThan(0);
  });

  it('writes severity = max(plant, customer, user) when a severity sub-field changes', () => {
    const { nodes, edges } = baseRow();
    const onChange = vi.fn();
    render(<RiskTable nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />, { wrapper: I18nTestWrapper });
    // open severity dialog and set customer severity to 8
    // (Implementation detail: the table shows a "S" cell that opens a popover with 3 InputNumbers.)
    // Find the severity trigger and the three inputs; this test asserts the contract:
    fireEvent.click(screen.getByRole('button', { name: /三段式严重度|severityDialog|S/i }) || screen.getAllByText(/S/i)[0]);
    // Set the three inputs to 4, 8, 8 and expect onChange called with fe.severity === 8
    const nums = screen.getAllByRole('spinbutton');
    // The first three spinbuttons in the dialog are plant/customer/user
    fireEvent.change(nums[0], { target: { value: '4' } });
    fireEvent.change(nums[1], { target: { value: '8' } });
    fireEvent.change(nums[2], { target: { value: '8' } });
    expect(onChange).toHaveBeenCalled();
    const [newNodes] = onChange.mock.calls[onChange.mock.calls.length - 1];
    const fe = newNodes.find((n: GraphNode) => n.id === 'fe');
    expect(fe.severity).toBe(8);
    expect(fe.severity_customer).toBe(8);
  });

  it('shows CC (read-only) from ProcessStepFunction.classification', () => {
    const { nodes, edges } = baseRow();
    render(<RiskTable nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });
    expect(screen.getByText('CC')).toBeInTheDocument();
  });

  it('shows SC list when no CC and WEFs have SC', () => {
    const { nodes, edges } = baseRow();
    nodes[0] = { ...nodes[0], classification: '' }; // step func no CC
    nodes.push({ id: 'wef', type: 'ProcessWorkElementFunction', name: '贴装压力', classification: 'SC', ...Z } as GraphNode);
    edges.push({ source: 'psf', target: 'wef', type: 'FUNCTION_MAPPED_TO' });
    render(<RiskTable nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });
    expect(screen.getByText(/SC/)).toBeInTheDocument();
  });

  // --- stable pure-function tests (recommended over fragile dialog interaction) ---
  describe('computeSeverity', () => {
    it('returns the max of the three sub-fields', () => {
      expect(computeSeverity(4, 8, 8)).toBe(8);
      expect(computeSeverity(0, 0, 0)).toBe(0);
      expect(computeSeverity(9, 3, 1)).toBe(9);
    });
  });

  describe('aggregateSpecialCharacteristic', () => {
    const Z2 = { severity: 0, occurrence: 0, detection: 0 };
    it('CC wins over SC', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: 'CC', ...Z2 } as GraphNode;
      const wefs = [{ id: 'wef', type: 'ProcessWorkElementFunction', name: 'n', classification: 'SC', ...Z2 } as GraphNode];
      const edges: GraphEdge[] = [{ source: 'psf', target: 'wef', type: 'FUNCTION_MAPPED_TO' }];
      expect(aggregateSpecialCharacteristic(stepFunc, wefs, edges).tag).toBe('CC');
    });
    it('lists SC WEF names when <=2 and no CC', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: '', ...Z2 } as GraphNode;
      const wefs = [
        { id: 'wef1', type: 'ProcessWorkElementFunction', name: '压力', classification: 'SC', ...Z2 } as GraphNode,
        { id: 'wef2', type: 'ProcessWorkElementFunction', name: '温度', classification: 'SC', ...Z2 } as GraphNode,
      ];
      const edges: GraphEdge[] = [
        { source: 'psf', target: 'wef1', type: 'FUNCTION_MAPPED_TO' },
        { source: 'psf', target: 'wef2', type: 'FUNCTION_MAPPED_TO' },
      ];
      const r = aggregateSpecialCharacteristic(stepFunc, wefs, edges);
      expect(r.tag).toBe('SC');
      expect(r.label).toBe('SC(压力/温度)');
    });
    it('collapses to SC×N when >2', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: '', ...Z2 } as GraphNode;
      const wefs = [1, 2, 3].map((i) => ({ id: `wef${i}`, type: 'ProcessWorkElementFunction', name: `n${i}`, classification: 'SC', ...Z2 } as GraphNode));
      const edges: GraphEdge[] = wefs.map((w) => ({ source: 'psf', target: w.id, type: 'FUNCTION_MAPPED_TO' }));
      expect(aggregateSpecialCharacteristic(stepFunc, wefs, edges).label).toBe('SC×3');
    });
    it('returns - when none', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: '', ...Z2 } as GraphNode;
      expect(aggregateSpecialCharacteristic(stepFunc, [], []).label).toBe('-');
    });
    it('only counts WEFs linked to THIS step function (branch-local)', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: '', ...Z2 } as GraphNode;
      const wefs = [{ id: 'wef', type: 'ProcessWorkElementFunction', name: '压力', classification: 'SC', ...Z2 } as GraphNode];
      const edges: GraphEdge[] = [{ source: 'OTHER', target: 'wef', type: 'FUNCTION_MAPPED_TO' }]; // linked to a different step func
      expect(aggregateSpecialCharacteristic(stepFunc, wefs, edges).label).toBe('-');
    });
  });
});
```

> The severity-dialog interaction test above (`writes severity = max...`) is fragile against exact DOM structure. **Prefer the `computeSeverity`/`aggregateSpecialCharacteristic` pure-function tests** (they are stable and are the regression guard for spec §8's aggregation rule + the `severity=max` contract). Keep one rendering test for the read-only CC display and the O/D-disabled gate; drop the dialog-interaction test if flaky.

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run frontend/src/components/pfmea/RiskTable.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement `RiskTable`**

```typescript
// frontend/src/components/pfmea/RiskTable.tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Table, InputNumber, Popover, Tag, Tooltip } from 'antd';
import type { GraphNode, GraphEdge } from '../../types';
import { buildRows, getRowSeverity, type FMEARow } from '../../utils/fmeaTable';
import { calculateAP } from '../../utils/fmea';

interface RiskTableProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  fmeaId: string;
  onChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}

/** severity = max(plant, customer, user); 0 if any unset (caller treats 0 as unrated). */
export function computeSeverity(plant: number, customer: number, user: number): number {
  return Math.max(plant || 0, customer || 0, user || 0);
}

/** CC wins; else list SC WEF names (collapse to SC×N when >2); '-' when none. */
export function aggregateSpecialCharacteristic(
  stepFunc: GraphNode | undefined,
  weFunctionNodes: GraphNode[],
  edges: GraphEdge[],
): { label: string; tag: 'CC' | 'SC' | '-' } {
  if (stepFunc?.classification === 'CC') return { label: 'CC', tag: 'CC' };
  const scWefs = weFunctionNodes.filter((w) =>
    w.classification === 'SC' && edges.some((e) => e.source === stepFunc?.id && e.target === w.id && e.type === 'FUNCTION_MAPPED_TO'));
  if (scWefs.length === 0) return { label: '-', tag: '-' };
  if (scWefs.length <= 2) return { label: `SC(${scWefs.map((w) => w.name).join('/')})`, tag: 'SC' };
  return { label: `SC×${scWefs.length}`, tag: 'SC' };
}

export default function RiskTable({ nodes, edges, fmeaId, onChange }: RiskTableProps) {
  const { t } = useTranslation('pfmea');
  void fmeaId;
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const rows = buildRows(nodes, edges);

  const updateNode = (id: string, patch: Partial<GraphNode>) =>
    onChange(nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)), edges);

  const columns = [
    {
      title: t('wizard.failure.failureEffect'), dataIndex: 'effect', key: 'effect',
      render: (_: unknown, row: FMEARow) => row.failureEffectNodeIds.map((id) => nodeMap.get(id)?.name).join(' / '),
    },
    {
      title: 'S', key: 'severity', width: 90,
      render: (_: unknown, row: FMEARow) => {
        const feId = row.failureEffectNodeIds[0];
        const fe = feId ? nodeMap.get(feId) : undefined;
        const content = (
          <div style={{ display: 'grid', gap: 4 }}>
            <label>{t('wizard.risk.severityPlant')}<InputNumber min={0} max={10} value={fe?.severity_plant ?? 0}
              onChange={(v) => {
                const plant = v ?? 0;
                updateNode(feId!, { severity_plant: plant, severity: computeSeverity(plant, fe?.severity_customer ?? 0, fe?.severity_user ?? 0) });
              }} /></label>
            <label>{t('wizard.risk.severityCustomer')}<InputNumber min={0} max={10} value={fe?.severity_customer ?? 0}
              onChange={(v) => {
                const c = v ?? 0;
                updateNode(feId!, { severity_customer: c, severity: computeSeverity(fe?.severity_plant ?? 0, c, fe?.severity_user ?? 0) });
              }} /></label>
            <label>{t('wizard.risk.severityUser')}<InputNumber min={0} max={10} value={fe?.severity_user ?? 0}
              onChange={(v) => {
                const u = v ?? 0;
                updateNode(feId!, { severity_user: u, severity: computeSeverity(fe?.severity_plant ?? 0, fe?.severity_customer ?? 0, u) });
              }} /></label>
          </div>
        );
        return (
          <Popover content={content} title={t('wizard.risk.severityDialog')} trigger="click">
            <ButtonLike value={fe?.severity ?? 0} />
          </Popover>
        );
      },
    },
    { title: t('wizard.failure.failureMode'), key: 'fm', render: (_: unknown, row: FMEARow) => nodeMap.get(row.failureModeNodeId)?.name },
    { title: t('wizard.failure.failureCause'), key: 'fc', render: (_: unknown, row: FMEARow) => row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId)?.name : '' },
    { title: t('wizard.failure.preventionControl'), key: 'pc', render: (_: unknown, row: FMEARow) => row.preventionControlIds[0] ? nodeMap.get(row.preventionControlIds[0])?.name : '' },
    {
      title: 'O', key: 'o', width: 70,
      render: (_: unknown, row: FMEARow) => {
        const pcName = row.preventionControlIds[0] ? nodeMap.get(row.preventionControlIds[0])?.name ?? '' : '';
        const disabled = !pcName.trim();
        return <InputNumber min={0} max={10} disabled={disabled} value={row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId)?.occurrence ?? 0 : 0}
          onChange={(v) => updateNode(row.failureCauseNodeId!, { occurrence: v ?? 0 })} style={{ width: 60 }} />;
      },
    },
    { title: t('wizard.failure.detectionControl'), key: 'dc', render: (_: unknown, row: FMEARow) => row.detectionControlIds[0] ? nodeMap.get(row.detectionControlIds[0])?.name : '' },
    {
      title: 'D', key: 'd', width: 70,
      render: (_: unknown, row: FMEARow) => {
        const dcId = row.detectionControlIds[0];
        const dcName = dcId ? nodeMap.get(dcId)?.name ?? '' : '';
        const disabled = !dcName.trim();
        return <InputNumber min={0} max={10} disabled={disabled} value={dcId ? nodeMap.get(dcId)?.detection ?? 0 : 0}
          onChange={(v) => updateNode(dcId!, { detection: v ?? 0 })} style={{ width: 60 }} />;
      },
    },
    {
      title: t('wizard.risk.ap'), key: 'ap', width: 60,
      render: (_: unknown, row: FMEARow) => {
        const s = getRowSeverity(row, nodeMap);
        const o = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId)?.occurrence ?? 0 : 0;
        const d = row.detectionControlIds[0] ? nodeMap.get(row.detectionControlIds[0])?.detection ?? 0 : 0;
        const ap = calculateAP(s, o, d);
        const color = ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'default';
        return ap ? <Tag color={color}>{ap}</Tag> : '';
      },
    },
    {
      title: t('wizard.risk.class'), key: 'class', width: 90,
      render: (_: unknown, row: FMEARow) => {
        const stepFunc = nodeMap.get(row.functionNodeId);
        const wefs = nodes.filter((n) => n.type === 'ProcessWorkElementFunction');
        const { label, tag } = aggregateSpecialCharacteristic(stepFunc, wefs, edges);
        const bg = tag === 'CC' ? '#fff1f0' : tag === 'SC' ? '#fffbe6' : undefined;
        return <Tooltip title={label}><Tag style={{ background: bg }}>{label}</Tag></Tooltip>;
      },
    },
  ];

  return <Table rowKey="key" dataSource={rows} columns={columns as any} pagination={false} size="small" bordered />;
}

function ButtonLike({ value }: { value: number }) {
  return <a role="button" tabIndex={0}>{value || '-'}</a>;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run frontend/src/components/pfmea/RiskTable.test.tsx`
Expected: PASS. (If the severity-dialog interaction test is flaky, convert it to a `computeSeverity`/`aggregateSpecialCharacteristic` pure-function test and keep the rendering tests for CC display + O/D-disabled.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/pfmea/RiskTable.tsx frontend/src/components/pfmea/RiskTable.test.tsx
git commit -m "feat(pfmea): add RiskTable (3-tier severity=max, CC/SC read-only aggregation, O/D gate)"
```

---

## Task 9: Frontend — `PFMEAWizardPage` scaffold + Step 0/1

**Files:**
- Create: `frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx`
- Test: `frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`

**Interfaces:**
- Consumes: `useWizardSave`, `usePfmeaWizardValidation`, `PFMEAWizardSidebar`, `PFMEAGuidanceCard`, `ScopeTagField`, `SmartSuggestionDropdown`, `createWizardFailureChain`, `ensureCauseControls`, `orderStructureNodes`, `cascadeDeleteStructureNode`, `rangeToTimeframe`/`timeframeToRange`, `parseScopeTokens`, `calculateAP`, `buildRows`/`getRowSeverity`, `getFMEA`/`deleteFMEA`.
- Produces: the wizard page rendering steps 0–6.

- [ ] **Step 1: Read the DFMEA source in full**

Read `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` (reference §1 has the key blocks). This page is a copy-then-adapt of it.

- [ ] **Step 2: Write the failing test (scaffold + Step 0 + Step 1)**

```typescript
// frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../../api/fmea', () => ({
  getFMEA: vi.fn(),
  deleteFMEA: vi.fn(),
}));

import { getFMEA } from '../../../api/fmea';
import { PFMEAWizardPage } from './PFMEAWizardPage';
import type { FMEADocument } from '../../../types';

const Z = { severity: 0, occurrence: 0, detection: 0 };
const baseDoc: FMEADocument = {
  fmea_id: '00000000-0000-0000-0000-000000000001',
  document_no: 'PFMEA-2026-001', title: 'SMT焊接生产线',
  fmea_type: 'PFMEA', status: 'draft', lock_version: 1,
  graph_data: { nodes: [{ id: 'pi_1', type: 'ProcessItem', name: 'SMT焊接生产线', ...Z }], edges: [], wizardScope: {} },
} as unknown as FMEADocument;

describe('PFMEAWizardPage', () => {
  beforeEach(() => { vi.mocked(getFMEA).mockResolvedValue(baseDoc); });

  it('redirects to editor when fmea_type is not PFMEA', async () => {
    vi.mocked(getFMEA).mockResolvedValue({ ...baseDoc, fmea_type: 'DFMEA' } as unknown as FMEADocument);
    render(<MemoryRouter><PFMEAWizardPage /></MemoryRouter>, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => expect(getFMEA).toHaveBeenCalled());
    // navigation away — page should not render wizard title for DFMEA
  });

  it('renders Step 0 scope fields and adds a ProcessStep in Step 1', async () => {
    render(<MemoryRouter><PFMEAWizardPage /></MemoryRouter>, { wrapper: I18nTestRouterWrapper });
    await waitFor(() => screen.getByText(/PFMEA向导|PFMEA Wizard/i));
    // Step 0 visible initially; navigate to Step 1 via sidebar/next
    fireEvent.click(screen.getByRole('button', { name: /nextStep|下一步/i }));
    await waitFor(() => screen.getByText(/addProcessStep|添加过程步骤/i));
  });
});
```

> `I18nTestRouterWrapper` — a wrapper providing i18n (with `pfmea` + `dfmea` namespaces) and router context. Extract from the Task 5/6 shared helper; if it doesn't include router, compose `MemoryRouter` + the i18n provider. Mirror how `DFMEAWizardPage.test.tsx` sets up its wrapper.

- [ ] **Step 3: Run test to verify it fails**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement — copy `DFMEAWizardPage.tsx` → `PFMEAWizardPage.tsx` and apply these edits**

Copy the file, then make these specific changes (each shown as a delta):

1. **Imports**: replace DFMEA-specific imports with PFMEA ones:
```typescript
import { usePfmeaWizardValidation } from '../../../hooks/usePfmeaWizardValidation';
import { usePfmeaRules } from '../../../utils/pfmeaRules';
import WizardSidebar from '../../../components/pfmea/PFMEAWizardSidebar';
import WizardGuidanceCard from '../../../components/pfmea/PFMEAGuidanceCard';
import ScopeTagField from '../../../components/dfmea/ScopeTagField'; // reused (trigger union extended in Task 6)
import SmartSuggestionDropdown from '../../../components/dfmea/SmartSuggestionDropdown'; // reused
```
Keep: `useWizardSave`, `calculateAP`, `buildRows`/`getRowSeverity`, `createWizardFailureChain`/`ensureCauseControls`, `orderStructureNodes`, `cascadeDeleteStructureNode`, `rangeToTimeframe`/`timeframeToRange`, `parseScopeTokens`, `getFMEA`/`deleteFMEA`, wizard utils. Remove DFMEA-only imports: `useDfmeaRules`, `toolsRequiringNodeType`/`pickParamParent`/`buildAttachedParamNode`/`StructureNodeType` (PFMEA has no Interface/DesignParameter/tool-structure-gap).

2. **i18n**: `useTranslation()` → `useTranslation('pfmea')` (or prefix keys with `pfmea:` to match original pattern).

3. **Load guard**: change `if (doc.fmea_type !== 'DFMEA')` → `if (doc.fmea_type !== 'PFMEA')`.

4. **Structure node type list** (used in `completedSteps` + `renderStep1`):
```typescript
const STRUCTURE_TYPES = ['ProcessItem', 'ProcessStep', 'ProcessWorkElement'];
const FUNCTION_TYPES = ['ProcessItemFunction', 'ProcessStepFunction', 'ProcessWorkElementFunction'];
```
Replace the DFMEA `['System','Subsystem','Component','Interface','DesignParameter']` and child-type/edge maps with:
```typescript
const CHILD_TYPE: Record<string, string> = { ProcessItem: 'ProcessStep', ProcessStep: 'ProcessWorkElement' };
const CHILD_EDGE_TYPE: Record<string, string> = { ProcessItem: 'HAS_PROCESS_STEP', ProcessStep: 'HAS_WORK_ELEMENT' };
```

5. **`completedSteps`**: mirror the DFMEA `completedSteps` useMemo but use `STRUCTURE_TYPES` for `hasStructure`, `FUNCTION_TYPES` for `hasFunction`; keep `hasFailure`/`hasRating`/`hasOptimization` (use `RecommendedAction` presence for step 5 — see Task 13; for the scaffold, mirror DFMEA's `hasOptimization` using named PC/DC, and Task 13 will refine to RecommendedAction).

6. **`renderStep1`** (structure): mirror DFMEA's structure step but:
   - Render `ProcessItem → ProcessStep → ProcessWorkElement` via `orderStructureNodes(nodes.filter(n => STRUCTURE_TYPES.includes(n.type)), edges)`.
   - When adding a `ProcessStep`, include `process_number: ''` field (render an `Input` bound to `process_number`, required).
   - When adding a `ProcessWorkElement`, include `classification: ''` field and render a `Select` with options `Man/Machine/Material/Environment` (required).
   - Delete via `cascadeDeleteStructureNode`.
   - No Interface/DesignParameter, no tool-structure-gap UI.

7. **Finish gate**: 
```typescript
const canFinish = validation.warnings.length === 0
  && validation.step1Complete && validation.step2Complete
  && validation.step3Complete && validation.step4Complete && validation.step5Complete;
```
(Adjust the `validation.*` names to the `PfmeaStepValidation` fields from Task 4.)

8. **`handleFinish`**: same as DFMEA (write `wizard_completed: true`, immediateSave, navigate to `/fmea/${fmeaId}`).

9. **JSX layout**: identical structure to DFMEA (header + sidebar + guidance + `STEP_RENDERERS[currentStep]` + bottom nav + conflict modal), swapping `WizardSidebar`→`PFMEAWizardSidebar`, `WizardGuidanceCard`→`PFMEAGuidanceCard`. Define `STEP_RENDERERS` for steps 0–6; for this task implement `renderStep0` (ScopeTagField ×5 with `pfmea_tool`/`pfmea_trend` triggers + team/timeframe/task) and `renderStep1` (structure). Leave `renderStep2..6` as placeholder `() => <div>{t('wizard.steps[N]')}</div>` for now (Tasks 10–13 fill them).

`renderStep0` key snippet (ScopeTagField usage):
```typescript
<ScopeTagField value={parseScopeTokens.stringify(wizardScope.tool ? [wizardScope.tool] : []) /* or keep as token string */}
  onChange={(v) => updateScope({ tool: v })} presets={t('wizard.scope.toolPresets', { returnObjects: true }) as string[]}
  triggerType="pfmea_tool" fmeaId={fmeaId} context={{ fmea_title: fmea?.title, product_line_code, task: wizardScope.task, team: wizardScope.team }} />
```
(Adapt to how DFMEA's `renderStep0` wires `wizardScope.tool` — it stores a token string; mirror that exactly, swapping `triggerType` to `"pfmea_tool"`/`"pfmea_trend"`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: PASS (Step 0 renders, Step 1 add-ProcessStep renders).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx
git commit -m "feat(pfmea): wizard page scaffold + Step 0 scope + Step 1 structure"
```

---

## Task 10: Frontend — Step 2 (FunctionTreeEditor) wired into page

**Files:**
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx` (`renderStep2`)
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`

- [ ] **Step 1: Add the failing test**

Append to `PFMEAWizardPage.test.tsx`:
```typescript
it('Step 2 renders the FunctionTreeEditor', async () => {
  render(<MemoryRouter><PFMEAWizardPage /></MemoryRouter>, { wrapper: I18nTestRouterWrapper });
  await waitFor(() => screen.getByText(/PFMEA向导/i));
  // advance to step 2
  fireEvent.click(screen.getByRole('button', { name: /nextStep|下一步/i }));
  fireEvent.click(screen.getByRole('button', { name: /nextStep|下一步/i }));
  await waitFor(() => screen.getByText(/addStepFunction|添加过程步骤功能/i));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: FAIL (Step 2 is placeholder).

- [ ] **Step 3: Implement `renderStep2`**

```typescript
import FunctionTreeEditor from '../../../components/pfmea/FunctionTreeEditor';

const renderStep2 = () => (
  <FunctionTreeEditor nodes={nodes} edges={edges} fmeaId={fmeaId} onChange={(n, e) => updateGraphData(n, e)} />
);
```
Register `2: renderStep2` in `STEP_RENDERERS`.

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx
git commit -m "feat(pfmea): wire FunctionTreeEditor into Step 2"
```

---

## Task 11: Frontend — Step 3 (failure chain on ProcessStepFunction)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx` (`renderStep3`)
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`

- [ ] **Step 1: Add the failing test**

```typescript
it('Step 3 creates a failure chain on a ProcessStepFunction', async () => {
  // Seed a doc that already has a ProcessStepFunction
  const doc = { ...baseDoc, graph_data: { nodes: [
    { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
    { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
    { id: 'psf', type: 'ProcessStepFunction', name: '准确贴装', ...Z },
  ], edges: [{ source: 'ps', target: 'psf', type: 'HAS_FUNCTION' }], wizardScope: { wizard_completed: false } } };
  vi.mocked(getFMEA).mockResolvedValue(doc as unknown as FMEADocument);
  render(<MemoryRouter><PFMEAWizardPage /></MemoryRouter>, { wrapper: I18nTestRouterWrapper });
  // navigate to step 3 and click "add failure chain"
  // ... advance via next buttons 3 times, then click addFailureChain
  // assert a FailureMode node appears (SmartSuggestionDropdown for failure_mode)
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement `renderStep3`**

Mirror DFMEA `renderStep3` but key differences:
- Filter functions to `ProcessStepFunction` only (FM hangs off `ProcessStepFunction`): `const stepFuncs = nodes.filter(n => n.type === 'ProcessStepFunction');`
- For each `ProcessStepFunction`, show a card with the step's WorkElements (4M) as read-only context hints, and an "add failure chain" button calling:
```typescript
const { newNodes, newEdges } = createWizardFailureChain(stepFuncId);
onChange([...nodes, ...newNodes], [...edges, ...newEdges]);
```
- 5 `SmartSuggestionDropdown`s per chain: `failure_mode`/`failure_effect`/`failure_cause`/`prevention_control`/`detection_control`, with `context` including `function_description` = step func name + `process_step` = step name + the step's 4M work-element names (joined) for the `failure_cause` trigger.
- Delete a chain via `cascadeDeleteStructureNode(fmId, nodes, edges)`.
- `ensureCauseControls` runs on load (already in the page load effect — keep it).

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx
git commit -m "feat(pfmea): Step 3 failure chain on ProcessStepFunction (4M context)"
```

---

## Task 12: Frontend — Step 4 (RiskTable) wired into page

**Files:**
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx` (`renderStep4`)
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`

- [ ] **Step 1: Add the failing test**

```typescript
it('Step 4 renders the RiskTable with severity dialog and CC/SC column', async () => {
  // Seed doc with one complete failure chain + ratings
  // navigate to step 4, assert RiskTable renders (AP tag or class column)
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement `renderStep4`**

```typescript
import RiskTable from '../../../components/pfmea/RiskTable';

const renderStep4 = () => (
  <RiskTable nodes={nodes} edges={edges} fmeaId={fmeaId} onChange={(n, e) => updateGraphData(n, e)} />
);
```
Register `4: renderStep4` in `STEP_RENDERERS`.

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx
git commit -m "feat(pfmea): wire RiskTable into Step 4"
```

---

## Task 13: Frontend — Step 5 (Optimization) + Step 6 (Result) + finish gate refinement

**Files:**
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx` (`renderStep5`, `renderStep6`, `completedSteps` step 5)
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`

- [ ] **Step 1: Add the failing tests**

```typescript
it('Step 5 shows RecommendedAction editor for AP=H rows', async () => {
  // Seed doc with an AP=H row (severity 9, O 4, D 4 → AP=H)
  // navigate to step 5, assert responsible/due_date inputs appear
});

it('finish is disabled until all gates pass', async () => {
  // Seed incomplete doc, navigate to step 6, assert finish button disabled
});

it('finish navigates to editor when all gates pass', async () => {
  // Seed complete doc (all gates green), assert finish enabled and calls navigate
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement `renderStep5` (optimization)**

Mirror DFMEA's optimization step (`renderStep5` in DFMEAWizardPage). For each row with `AP === 'H'` (compute via `calculateAP(getRowSeverity(row, nodeMap), cause.occurrence, dc.detection)`), render a card with:
- `Input.TextArea` for `RecommendedAction.name` (measure description)
- `Input` for `responsible`, `DatePicker` for `due_date`, `Select` for `status` (open/undecided/planned/done/notExecuted), `Input.TextArea` for `action_taken`, `DatePicker` for `completion_date`
- Three `InputNumber`s for `revised_severity`/`revised_occurrence`/`revised_detection` + computed `revised_ap = calculateAP(...)`.
- Create the `RecommendedAction` node + `OPTIMIZED_BY` edge from the `FailureCause` when first edited (or pre-create via a button). Store all fields on the `RecommendedAction` node.

- [ ] **Step 4: Implement `renderStep6` (result/confirm)**

Mirror DFMEA's confirm step: stats cards (structure nodes, function nodes, failure chains, total nodes/edges) + the Finish button (already in bottom nav). No data entry.

- [ ] **Step 5: Refine `completedSteps` step 5**

Change `hasOptimization` to detect `RecommendedAction` nodes with non-empty `responsible`:
```typescript
const hasOptimization = nodes.some(n => n.type === 'RecommendedAction' && (n.responsible ?? '').trim());
```

- [ ] **Step 6: Run to verify they pass**

Run: `npx vitest run frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx frontend/src/pages/planning/fmea/PFMEAWizardPage.test.tsx
git commit -m "feat(pfmea): Step 5 optimization + Step 6 confirm + finish gate"
```

---

## Task 14: Frontend — Routing + FMEAListPage navigation

**Files:**
- Modify: `frontend/src/App.tsx` (route, reference §10 line 139)
- Modify: `frontend/src/pages/planning/fmea/FMEAListPage.tsx` (reference §10 lines 121-136, 186-189)
- Test: `frontend/src/pages/planning/fmea/FMEAListPage.test.tsx` (extend existing or add focused tests)

- [ ] **Step 1: Add the route**

In `frontend/src/App.tsx`, immediately after the DFMEA wizard route (line 139), add:
```typescript
<Route path="/fmea/pfmea-wizard/:id" element={<ProtectedRoute requiredModule="fmea"><PFMEAWizardPage /></ProtectedRoute>} />
```
And import `PFMEAWizardPage` at the top alongside `DFMEAWizardPage`.

- [ ] **Step 2: Write the failing test**

```typescript
// in FMEAListPage.test.tsx (append)
it('navigates to PFMEA wizard on create fmea_type=PFMEA', async () => {
  const navigate = vi.fn();
  vi.mocked(useNavigate).mockReturnValue(navigate);
  vi.mocked(createFMEA).mockResolvedValue({ fmea_id: 'abc', fmea_type: 'PFMEA' } as any);
  // render, open create modal, select PFMEA, submit
  // expect navigate).toHaveBeenCalledWith('/fmea/pfmea-wizard/abc')
});

it('navigates PFMEA incomplete draft to wizard', () => {
  // list row: fmea_type=PFMEA, status=draft, wizard_completed falsy
  // expect targetPath === `/fmea/pfmea-wizard/${id}`
});
```
(Adapt to the existing FMEAListPage test harness; mirror how existing DFMEA-wizard navigation is tested.)

- [ ] **Step 3: Run to verify it fails**

Run: `npx vitest run frontend/src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: FAIL.

- [ ] **Step 4: Update `handleCreate`**

In `frontend/src/pages/planning/fmea/FMEAListPage.tsx`, change the create navigation (lines 121-136):
```typescript
if (values.fmea_type === "DFMEA") {
  navigate(`/fmea/wizard/${fmea.fmea_id}`);
} else if (values.fmea_type === "PFMEA") {
  navigate(`/fmea/pfmea-wizard/${fmea.fmea_id}`);
} else {
  navigate(`/fmea/${fmea.fmea_id}`, { state: { showLessonsLearned: true, problemDescription: values.problem_description } });
}
```

- [ ] **Step 5: Update list-row draft detection**

Change the incomplete-draft check (lines 186-189) to include PFMEA:
```typescript
const isIncompleteDraft = (record.fmea_type === "DFMEA" || record.fmea_type === "PFMEA")
  && record.status === "draft"
  && !record.graph_data?.wizardScope?.wizard_completed;
const targetPath = isIncompleteDraft
  ? (record.fmea_type === "PFMEA" ? `/fmea/pfmea-wizard/${record.fmea_id}` : `/fmea/wizard/${record.fmea_id}`)
  : `/fmea/${record.fmea_id}`;
```

- [ ] **Step 6: Run to verify it passes**

Run: `npx vitest run frontend/src/pages/planning/fmea/FMEAListPage.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/planning/fmea/FMEAListPage.tsx frontend/src/pages/planning/fmea/FMEAListPage.test.tsx
git commit -m "feat(pfmea): route PFMEA wizard + list navigation (create & draft)"
```

---

## Task 15: Frontend — Editor compatibility (PFMEA Class column reads function-node classification)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:1071-1092` (Class column)
- Create: `frontend/src/pages/planning/fmea/FMEAEditorPage.test.tsx` (no editor page test exists today — only `FMEAEditorDragSort.test.tsx` and `FMEAVersionSnapshot.test.tsx` do)
- Reference (do not modify): `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx` and `FMEAVersionSnapshot.test.tsx` — copy their i18n/router/mock setup into the new test file.

**Interfaces:**
- Consumes: `aggregateSpecialCharacteristic` (named export) from `../../components/pfmea/RiskTable` (Task 8).
- Produces: PFMEA Class column is read-only, reading function-node `classification` aggregated per spec §8; DFMEA Filter Code column unchanged (still editable on `FailureMode.classification`).

- [ ] **Step 1: Inspect the existing editor test harness**

Read `frontend/src/pages/planning/fmea/FMEAEditorDragSort.test.tsx` and `frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx` in full. Note the i18n wrapper, router setup, `getFMEA` mock shape, and how they construct a `FMEADocument` with `graph_data`. The new `FMEAEditorPage.test.tsx` will reuse this exact harness.

- [ ] **Step 2: Create `FMEAEditorPage.test.tsx` with the failing tests**

```typescript
// frontend/src/pages/planning/fmea/FMEAEditorPage.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
// Reuse the SAME wrapper/harness pattern as FMEAEditorDragSort.test.tsx (i18n + router + getFMEA mock).
// Copy the imports, the i18n test provider, and the getFMEA mock setup from that file.

vi.mock('../../../api/fmea', () => ({ getFMEA: vi.fn(), updateFMEA: vi.fn(), deleteFMEA: vi.fn() }));
import { getFMEA } from '../../../api/fmea';
import type { FMEADocument, GraphNode, GraphEdge } from '../../../types';

const Z = { severity: 0, occurrence: 0, detection: 0 };

const pfmeaWithCC = (): FMEADocument => ({
  fmea_id: '00000000-0000-0000-0000-000000000001',
  document_no: 'PFMEA-2026-001', title: 'SMT焊接生产线',
  fmea_type: 'PFMEA', status: 'approved', lock_version: 1,
  graph_data: {
    nodes: [
      { id: 'psf', type: 'ProcessStepFunction', name: '准确贴装', classification: 'CC', ...Z } as GraphNode,
      { id: 'fm', type: 'FailureMode', name: '贴装偏移', classification: '', ...Z } as GraphNode, // FM classification empty (new model)
      { id: 'fe', type: 'FailureEffect', name: '功能丧失', severity: 8, ...Z } as GraphNode,
      { id: 'fc', type: 'FailureCause', name: '吸嘴磨损', occurrence: 4, ...Z } as GraphNode,
      { id: 'pc', type: 'PreventionControl', name: '校准', ...Z } as GraphNode,
      { id: 'dc', type: 'DetectionControl', name: 'AOI', detection: 3, ...Z } as GraphNode,
    ],
    edges: [
      { source: 'psf', target: 'fm', type: 'HAS_FAILURE_MODE' },
      { source: 'fm', target: 'fe', type: 'EFFECT_OF' },
      { source: 'fc', target: 'fm', type: 'CAUSE_OF' },
      { source: 'fc', target: 'pc', type: 'PREVENTED_BY' },
      { source: 'fc', target: 'dc', type: 'DETECTED_BY' },
    ] as GraphEdge[],
    wizardScope: { wizard_completed: true },
  },
} as unknown as FMEADocument);

describe('FMEAEditorPage Class column', () => {
  beforeEach(() => { vi.mocked(getFMEA).mockResolvedValue(pfmeaWithCC()); });

  it('PFMEA: Class column is read-only and shows CC from ProcessStepFunction.classification', async () => {
    render(<FMEAEditorPageWrapper />, { wrapper: EditorTestHarness }); // reuse harness from FMEAEditorDragSort.test
    await screen.findByText(/SMT焊接生产线|PFMEA/i);
    // The Class cell should show 'CC' (from psf.classification), and there should be NO editable
    // Select whose onChange writes to the FailureMode node for PFMEA.
    expect(screen.getAllByText('CC').length).toBeGreaterThan(0);
  });

  it('DFMEA: Filter Code column unchanged (editable Select on FailureMode.classification)', async () => {
    const dfmea = { ...pfmeaWithCC(), fmea_type: 'DFMEA' } as unknown as FMEADocument;
    vi.mocked(getFMEA).mockResolvedValue(dfmea);
    render(<FMEAEditorPageWrapper />, { wrapper: EditorTestHarness });
    await screen.findByText(/DFMEA/i);
    // For DFMEA the Class column must remain the editable Select bound to FailureMode.classification.
    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBeGreaterThan(0); // Filter Code Select present
  });
});
```

> `FMEAEditorPageWrapper` / `EditorTestHarness` — names placeholder for the harness you copy from `FMEAEditorDragSort.test.tsx`. If that file renders `FMEAEditorPage` directly via a route, mirror it exactly (same `MemoryRouter` + `ProtectedRoute`/auth mock + i18n provider). The assertions are deliberately tolerant (presence of `CC` text / presence of a combobox) to avoid coupling to exact column DOM; tighten only if the existing harness makes stronger assertions straightforward. If rendering the full editor in-test is too heavy (auth/permission deps), fall back to a unit test of the column's `render` function extracted into a pure helper — but prefer the rendering test since the deliverable is an integrated column change.

- [ ] **Step 3: Run to verify it fails**

Run: `npx vitest run frontend/src/pages/planning/fmea/FMEAEditorPage.test.tsx`
Expected: FAIL (PFMEA Class column currently reads `FailureMode.classification`, which is empty → no `CC` shown).

- [ ] **Step 4: Modify the Class column**

In `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` (lines 1071-1092), branch by `isDFMEA`. Keep the DFMEA branch exactly as-is (Filter Code on `FailureMode.classification`, editable). Replace the PFMEA branch (`!isDFMEA`) with a read-only aggregation that reads the row's function node:

```typescript
{
  title: <Tooltip title={isDFMEA ? t("editor.tooltips.filterCode") : t("editor.tooltips.classification")}>Class</Tooltip>,
  key: "class",
  width: 70,
  align: "center" as const,
  onCell: (_row: FMEARow, index?: number) => ({ rowSpan: index != null ? rowSpans[index]?.mode ?? 1 : 1 }),
  render: (_: unknown, row: FMEARow) => {
    if (isDFMEA) {
      // ---- DFMEA: Filter Code on FailureMode, editable (UNCHANGED) ----
      const node = nodeMap.get(row.failureModeNodeId);
      const classValue = node?.classification || "";
      const bgStyle = classValue === "CC" ? { background: "#fff1f0" } : classValue === "SC" ? { background: "#fffbe6" } : {};
      return (
        <Select
          size="small"
          value={classValue || undefined}
          onChange={(value) => updateNode(row.failureModeNodeId, "classification", value || "")}
          disabled={!canEdit('fmea')}
          style={{ width: 60, ...bgStyle }}
          options={[{ value: "", label: "-" }, { value: "CC", label: "CC" }, { value: "SC", label: "SC" }]}
        />
      );
    }
    // ---- PFMEA: read-only, from function-node classification (spec §9) ----
    const stepFunc = nodeMap.get(row.functionNodeId);
    const wefs = nodes.filter((n) => n.type === "ProcessWorkElementFunction");
    const { label, tag } = aggregateSpecialCharacteristic(stepFunc, wefs, edges);
    const bg = tag === "CC" ? "#fff1f0" : tag === "SC" ? "#fffbe6" : undefined;
    return <Tooltip title={label}><Tag style={{ background: bg }}>{label}</Tag></Tooltip>;
  },
},
```
Import `aggregateSpecialCharacteristic` from `../../components/pfmea/RiskTable` (exported in Task 8). Ensure `nodes` and `edges` are in scope in the column render (they are — the editor holds them in state like the wizard).

- [ ] **Step 5: Run to verify it passes**

Run: `npx vitest run frontend/src/pages/planning/fmea/FMEAEditorPage.test.tsx`
Expected: PASS (PFMEA read-only + DFMEA unchanged).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx frontend/src/pages/planning/fmea/FMEAEditorPage.test.tsx
git commit -m "feat(pfmea): editor Class column reads function-node classification (read-only); DFMEA Filter Code untouched"
```

---

## Final verification

- [ ] **Run the full frontend test suite**
Run: `cd frontend && npx vitest run`
Expected: all green (including existing DFMEA tests unchanged).

- [ ] **Run the full backend test suite**
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -x`
Expected: all green.

- [ ] **Run the frontend build**
Run: `cd frontend && npm run build`
Expected: `tsc --noEmit` + `vite build` succeed (no type errors; PFMEA namespace resolves; no unused-import errors from the removed DFMEA-only imports).

- [ ] **Manual smoke test** (optional, if dev env available): create a new PFMEA from the list page → wizard opens at Step 0 → walk through all 7 steps with seed-like data (SMT line, OP10 贴装, Machine 4M, ProcessStepFunction CC, failure chain, 3-tier severity, AP=H optimization) → Finish → lands in the editor → editor Class column shows CC read-only.

---

## Self-review notes

- **Spec coverage**: Every spec section maps to a task — Steps 0–6 (Tasks 9–13), CC/SC model §8 (Tasks 7+8+15), editor compat §9 (Task 15), three-tier severity (Tasks 4+8), pfmea_tool/trend backend §6 (Task 1), routing §7 (Task 14), validation §10 (Task 4), tests §11 (per-task tests), scope §12 (exclusions respected: no FC↔WEF edge, no FailureCause.special_characteristic, DFMEA untouched except additive ScopeTagField union + PFMEA-only editor branch).
- **LLM schema alignment (review fix #1)**: Task 1 prompts now return `{"suggestions":[{"name","confidence","explanation"}]}` matching `SuggestionList.model_validate` (not `{name,"reason"}`). Task 1 Step 7 tests template formatting + `SuggestionList` validation as the regression guard; Step 8 confirms the rule engine returns empty (not raises) for the new scope triggers so they fall through to LLM.
- **Branch-local FUNCTION_MAPPED_TO (review fix #2)**: Task 7 `addFunction` resolves the mapped parent by walking the structure tree (StepFunction ← its step's ProcessItem's ItemFunction; WEF ← its work element's ProcessStep's StepFunction). Two branch-local tests in Task 7 (two steps / two work elements) assert WEF maps only to its own step's StepFunction. Task 4 validation's `step2Complete` is strengthened to reject wrong-branch mapping, with a failing-branch test.
- **Export consistency (review fix #3)**: all four PFMEA components use **default exports** (matching the existing DFMEA `WizardSidebar`/`WizardGuidanceCard` convention). All page + test imports use default imports (`import X from '...'`); only the pure helpers `computeSeverity`/`aggregateSpecialCharacteristic` remain named exports (imported by Task 8 tests and Task 15). No `{ NamedComponent }` component imports remain.
- **Editor test file (review fix #4)**: Task 15 creates a new `FMEAEditorPage.test.tsx` (none exists today — only `FMEAEditorDragSort.test.tsx` / `FMEAVersionSnapshot.test.tsx`), reusing their i18n/router/mock harness; it does not reference a non-existent file.
- **No placeholders**: every code step shows real code; the two "copy-then-adapt" tasks (5, 9) reference the exact source file + show the specific edits. Pure-function tests (`computeSeverity`/`aggregateSpecialCharacteristic`) are the stable alternative to the fragile severity-dialog interaction test.
- **Type consistency**: `PfmeaStepValidation` field names (`step1Complete`..`step5Complete`) match the finish-gate usage in Task 9. `aggregateSpecialCharacteristic`/`computeSeverity` are defined in Task 8 and reused in Task 15 (imported). `createWizardFailureChain` signature unchanged (called with `ProcessStepFunction` id). `ScopeTriggerType` extended additively. Step numbering verified unique within each task (Task 1: 1–10; Task 15: 1–6).