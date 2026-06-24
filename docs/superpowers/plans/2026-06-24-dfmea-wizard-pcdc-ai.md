# DFMEA 向导第 4 步 PC/DC AI 推荐实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DFMEA 向导第 4 步（失效分析）的预防措施(PC)/探测措施(DC)输入框接入 AI 推荐，与 FM/FE/FC 字段效果一致；后端新增 `prevention_control` / `detection_control` 两个 trigger 拆分混合 measure 列表。

**Architecture:** 后端 `recommendation_service.py` 抽 `_measure_lists` 共享 helper，新增两个 rule handler + 两个 LLM 提示模板 + 两个图谱增强分支；schema 加两个 Literal。前端把 `renderStep3` 的两个 PC/DC `<Input>` 换成 `SmartSuggestionDropdown`，`triggerType` 对应，`SmartSuggestionDropdown` 的联合类型扩两个值。

**Tech Stack:** Python 3.11 + FastAPI + Pydantic v2（后端）| React 18 + TypeScript 5.6 + Ant Design 5.29 + Vitest（前端）。后端工作目录 `backend/`，前端 `frontend/`。

## Global Constraints

- 不改主 FMEA 编辑器（`FMEAEditorPage`）的 PC/DC；不删旧 `"measure"` trigger（保留，内部重构为共享 helper，对外行为一致）；不动第 5 步。
- 后端 trigger_type 字符串大小写敏感：`prevention_control` / `detection_control`（下划线）。
- 边类型：`PREVENTED_BY`（cause→PreventionControl）、`DETECTED_BY`（cause→DetectionControl）。
- `RuleSuggestion`/`RuleResult` 已在 `recommendation_service.py` 定义；`RuleResult(suggestions, quality)`，`quality: Literal["specific","generic"]`。
- LLM 提示模板放 `PROMPT_TEMPLATES` dict（`recommendation_service.py:248`），`_build_prompt` 用 `PROMPT_TEMPLATES.get(trigger_type, "")` 取模板 → 新 key 自动生效。
- `_recommend_anchor`（`api/fmea.py:245`）默认分支已返回 `failure_mode` anchor → 新 trigger 无需改 anchor。
- 前端 `SmartSuggestionDropdown` 已在 `DFMEAWizardPage.tsx:16` import；`processStep`、`fmeaId`、`handleUpdateControl(causeId, type, value: string)` 已在 `renderStep3` 作用域。
- `handleUpdateControl` 签名不变——`onSelect` 传 `s.name`、`onChange` 传 `val`，均为字符串。
- 后端测试用 `pytest`，pattern 参照 `backend/tests/test_recommendation_service.py`（`SECRET_KEY=test-secret-key` 已在文件顶部 `os.environ.setdefault`；`RuleEngine()` 直接 `evaluate(trigger, context)`）。
- 每个后端 task 结束 `python -m pytest` 须过；每个前端 tsx task 结束 `npx tsc --noEmit` 须过（项目 `.claude/settings.json` PostToolUse hook 自动对 tsx 触发 tsc）。
- worktree 已隔离于 `worktree-dfmea-wizard-pcdc-ai`，基于 `fix/fmea-fixes` @ 836ceed。

---

### Task 1: 后端 schema + 规则引擎 — 新增两个 trigger 的 rule handler + 测试

**Files:**
- Modify: `backend/app/schemas/recommendation.py:6-10`
- Modify: `backend/app/services/recommendation_service.py:130-218`（`dispatch` + `_suggest_measures` 重构 + 两个新 handler）
- Test: `backend/tests/test_recommendation_service.py`（追加用例）

**Interfaces:**
- Produces: `RuleEngine.evaluate("prevention_control", context)` 与 `RuleEngine.evaluate("detection_control", context)` 返回 `RuleResult`，前者只含预防项（explanation "预防措施"），后者只含探测项（explanation "检测措施"）。`measure` trigger 行为不变（仍混合）。
- Consumes: 无（首个 task）。

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_recommendation_service.py` (after `test_rule_engine_generic_fallback`, ~line 114):

```python
def test_rule_engine_prevention_control_returns_only_prevention():
    """prevention_control trigger 必须只返回预防项，不混入探测项。"""
    engine = RuleEngine()
    result = engine.evaluate("prevention_control", {"failure_mode": "采集数据失效", "ap": "H"})
    assert len(result.suggestions) > 0
    # 预防项 explanation 标注「预防措施」；不得出现检测专属词
    for s in result.suggestions:
        assert "预防" in s.explanation
    detection_only_keywords = ["在线实时监测", "自诊断功能", "出厂100%功能测试", "传感器信号校验", "气密性测试", "接触电阻测试"]
    names = [s.name for s in result.suggestions]
    for kw in detection_only_keywords:
        assert kw not in names, f"探测项 {kw} 不应出现在 prevention_control 结果中"


def test_rule_engine_detection_control_returns_only_detection():
    """detection_control trigger 必须只返回探测项。"""
    engine = RuleEngine()
    result = engine.evaluate("detection_control", {"failure_mode": "采集数据失效", "ap": "H"})
    assert len(result.suggestions) > 0
    for s in result.suggestions:
        assert "检测" in s.explanation or "探测" in s.explanation
    prevention_only_keywords = ["冗余设计", "降额设计", "失效安全设计", "传感器冗余布置", "信号滤波设计", "双重密封结构", "防松结构设计"]
    names = [s.name for s in result.suggestions]
    for kw in prevention_only_keywords:
        assert kw not in names, f"预防项 {kw} 不应出现在 detection_control 结果中"


def test_rule_engine_measure_still_returns_mixed():
    """旧 measure trigger 行为不变：仍返回预防+探测混合。"""
    engine = RuleEngine()
    result = engine.evaluate("measure", {"failure_mode": "采集数据失效", "ap": "H"})
    assert len(result.suggestions) > 0
    explanations = " ".join(s.explanation for s in result.suggestions)
    assert "预防" in explanations
    assert "检测" in explanations
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_recommendation_service.py::test_rule_engine_prevention_control_returns_only_prevention tests/test_recommendation_service.py::test_rule_engine_detection_control_returns_only_detection -v`
Expected: FAIL — `RuleEngine.evaluate` 对新 trigger 返回空（`dispatch.get` 未命中 → `RuleResult(suggestions=[], quality="generic")`），`len > 0` 断言失败。

- [ ] **Step 3: Add the two trigger types to the schema**

In `backend/app/schemas/recommendation.py`, replace the `trigger_type` Literal (lines 7-10):

```python
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization",
        "dfmea_tool", "dfmea_trend",
        "prevention_control", "detection_control",
    ]
```

- [ ] **Step 4: Refactor `_suggest_measures` + add two handlers + wire dispatch**

In `backend/app/services/recommendation_service.py`, replace the `_suggest_measures` method (lines 187-218) and the `dispatch` dict (lines 131-137).

Replace `_suggest_measures` with a shared helper + three thin handlers:

```python
    def _measure_lists(self, context: dict) -> tuple[list[str], list[str], Literal["specific", "generic"]]:
        """按 AP/关键词生成 (prevention, detection, quality) 两列表。
        供 measure / prevention_control / detection_control 三个 trigger 共享。"""
        fm = context.get("failure_mode", "")
        ap = context.get("ap", "L")
        prevention: list[str] = []
        detection: list[str] = []

        if ap == "H":
            prevention.extend(["冗余设计（双通道/备份）", "选用更高可靠性等级元器件", "降额设计", "失效安全设计"])
            detection.extend(["在线实时监测", "自诊断功能", "出厂100%功能测试"])
        elif ap == "M":
            prevention.extend(["优化设计参数", "增加防错结构", "选用成熟工艺"])
            detection.extend(["定期功能测试", "过程巡检", "来料检验"])
        else:
            prevention.extend(["标准化设计", "选用合格供应商物料"])
            detection.extend(["常规检验", "用户反馈跟踪"])

        if re.search(r"采集|检测|监测|识别", fm):
            prevention.extend(["传感器冗余布置", "信号滤波设计"])
            detection.extend(["传感器信号校验", "标定周期缩短"])
        if re.search(r"密封|封闭|泄漏", fm):
            prevention.extend(["双重密封结构", "密封槽优化设计"])
            detection.extend(["气密性测试", "泄漏监测"])
        if re.search(r"连接|接合|固定|接触", fm):
            prevention.extend(["防松结构设计", "镀金/镀银处理"])
            detection.extend(["接触电阻测试", "振动试验验证"])

        quality: Literal["specific", "generic"] = "specific" if (fm and any(kw in fm for kw in ["采集", "密封", "连接"])) else "generic"
        return prevention, detection, quality

    def _suggest_measures(self, context: dict) -> RuleResult:
        prevention, detection, quality = self._measure_lists(context)
        suggestions = (
            [RuleSuggestion(name=p, confidence=0.6, explanation="预防措施") for p in prevention]
            + [RuleSuggestion(name=d, confidence=0.6, explanation="检测措施") for d in detection]
        )
        return RuleResult(suggestions=suggestions, quality=quality)

    def _suggest_prevention_control(self, context: dict) -> RuleResult:
        prevention, _detection, quality = self._measure_lists(context)
        suggestions = [RuleSuggestion(name=p, confidence=0.6, explanation="预防措施") for p in prevention]
        return RuleResult(suggestions=suggestions, quality=quality)

    def _suggest_detection_control(self, context: dict) -> RuleResult:
        _prevention, detection, quality = self._measure_lists(context)
        suggestions = [RuleSuggestion(name=d, confidence=0.6, explanation="检测措施") for d in detection]
        return RuleResult(suggestions=suggestions, quality=quality)
```

Then replace the `dispatch` dict (lines 131-137) to add the two new triggers:

```python
        dispatch = {
            "failure_mode": self._generate_failure_modes,
            "failure_effect": self._suggest_failure_effect,
            "failure_cause": self._suggest_failure_cause,
            "measure": self._suggest_measures,
            "optimization": self._suggest_optimization,
            "prevention_control": self._suggest_prevention_control,
            "detection_control": self._suggest_detection_control,
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_recommendation_service.py -v -k "prevention_control or detection_control or measure_still"`
Expected: PASS (3 new tests green).

- [ ] **Step 6: Run full recommendation test file (regression)**

Run: `cd backend && python -m pytest tests/test_recommendation_service.py -v`
Expected: all pass (existing tests unaffected — `measure` behavior unchanged).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/recommendation.py backend/app/services/recommendation_service.py backend/tests/test_recommendation_service.py
git commit -m "feat(dfmea): add prevention_control/detection_control rule triggers (split measure)"
```

---

### Task 2: 后端 LLM 提示模板 + 图谱增强分支

**Files:**
- Modify: `backend/app/services/recommendation_service.py` — `PROMPT_TEMPLATES` dict (~line 248+, after the `"measure"` template ~line 333) + `_extract_neighbors_from_match` (~line 556-609).

**Interfaces:**
- Produces: `PROMPT_TEMPLATES["prevention_control"]` / `["detection_control"]` 两个模板；`_extract_neighbors_from_match` 对两个新 trigger 返回对应类型的控制邻居节点。
- Consumes: Task 1 的两个 trigger 已在 schema + dispatch。

- [ ] **Step 1: Add the two LLM prompt templates**

In `backend/app/services/recommendation_service.py`, in the `PROMPT_TEMPLATES` dict, after the `"measure"` template (which ends around line 333 with the closing `""",`), add two new entries. First locate the exact end of the `"measure"` template — it is the block starting `    "measure": """你是资深质量工程师...` and ending with `""",`. Insert immediately after it:

```python
    "prevention_control": """你是资深质量工程师，精通 AIAG-VDA FMEA 方法论。

【任务】为下方失效模式推荐 3-5 个「预防控制(P)」。
【预防控制(P)】阻止失效模式或失效原因发生的设计/工艺手段（防止"发生"或"起因"）。
【方向约束】措施必须可执行、可验证，与该失效模式直接相关；只给预防控制，不要给探测控制。

【当前上下文】
- FMEA 类型: {fmea_type}
- 工艺步骤/结构要素: {process_step}
- 失效模式: {failure_mode}
- AP(行动优先级): {ap}

【示例（失效模式=焊缝气孔, AP=H）】
焊接参数(电流/气流量)在线监控与闭环 / 焊前母材清洁度自动检验

【要求】name 为纯措施描述，不加前缀；explanation 说明为何针对该失效及为何属预防。
返回 JSON：
{{"suggestions": [{{"name": "措施描述", "confidence": 0.0-1.0, "explanation": "为何针对该失效模式及为何属预防控制"}}]}}
""",
    "detection_control": """你是资深质量工程师，精通 AIAG-VDA FMEA 方法论。

【任务】为下方失效模式推荐 3-5 个「探测控制(D)」。
【探测控制(D)】在交付前探测失效模式或失效原因的检验/测试手段（探测"已发生"或"已起因"）。
【方向约束】措施必须可执行、可验证，与该失效模式直接相关；只给探测控制，不要给预防控制。

【当前上下文】
- FMEA 类型: {fmea_type}
- 工艺步骤/结构要素: {process_step}
- 失效模式: {failure_mode}
- AP(行动优先级): {ap}

【示例（失效模式=焊缝气孔, AP=H）】
焊后100% X射线探伤 / 焊缝气密性在线检测

【要求】name 为纯措施描述，不加前缀；explanation 说明为何针对该失效及为何属探测。
返回 JSON：
{{"suggestions": [{{"name": "措施描述", "confidence": 0.0-1.0, "explanation": "为何针对该失效模式及为何属探测控制"}}]}}
""",
```

- [ ] **Step 2: Add the two graph-enrichment branches**

In `_extract_neighbors_from_match` (lines 556-609), the `elif trigger_type == "optimization":` block ends around line 607, followed by `return []` at line 609. Insert two new `elif` branches **before** the final `return []`. Replace:

```python
        elif trigger_type == "optimization":
            opt_ids = set()
            for e in edges:
                if e.get("type") == "OPTIMIZED_BY" and e.get("source") == fm_id:
                    opt_ids.add(e.get("target"))
            cause_ids = {
                e.get("source") for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            }
            for e in edges:
                if e.get("type") == "OPTIMIZED_BY" and e.get("source") in cause_ids:
                    opt_ids.add(e.get("target"))
            return [node_map[oid] for oid in opt_ids if oid in node_map]

        return []
```

with:

```python
        elif trigger_type == "optimization":
            opt_ids = set()
            for e in edges:
                if e.get("type") == "OPTIMIZED_BY" and e.get("source") == fm_id:
                    opt_ids.add(e.get("target"))
            cause_ids = {
                e.get("source") for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            }
            for e in edges:
                if e.get("type") == "OPTIMIZED_BY" and e.get("source") in cause_ids:
                    opt_ids.add(e.get("target"))
            return [node_map[oid] for oid in opt_ids if oid in node_map]

        elif trigger_type == "prevention_control":
            ctrl_ids = set()
            for e in edges:
                if e.get("type") == "PREVENTED_BY" and e.get("source") == fm_id:
                    ctrl_ids.add(e.get("target"))
            cause_ids = {
                e.get("source") for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            }
            for e in edges:
                if e.get("type") == "PREVENTED_BY" and e.get("source") in cause_ids:
                    ctrl_ids.add(e.get("target"))
            return [node_map[cid] for cid in ctrl_ids if cid in node_map]

        elif trigger_type == "detection_control":
            ctrl_ids = set()
            for e in edges:
                if e.get("type") == "DETECTED_BY" and e.get("source") == fm_id:
                    ctrl_ids.add(e.get("target"))
            cause_ids = {
                e.get("source") for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            }
            for e in edges:
                if e.get("type") == "DETECTED_BY" and e.get("source") in cause_ids:
                    ctrl_ids.add(e.get("target"))
            return [node_map[cid] for cid in ctrl_ids if cid in node_map]

        return []
```

- [ ] **Step 3: Add a test for the graph-enrichment branches**

Append to `backend/tests/test_recommendation_service.py`:

```python
def test_extract_neighbors_prevention_control_only_prevented_by():
    """prevention_control 图谱增强只取 PREVENTED_BY 邻居，不含 DETECTED_BY。"""
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    match = {
        "node_id": "fm1", "fmea_id": str(uuid.uuid4()),
    }
    # StubGraphRepo 不提供 graph_data；直接测 _extract_neighbors_from_match 的边逻辑
    # 需要注入 graph_data。改用最小桩：覆写 _get_graph_data_by_fmea_id。
    async def fake_graph_data(_fmea_id):
        return {
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "m"},
                {"id": "fc1", "type": "FailureCause", "name": "c"},
                {"id": "pc1", "type": "PreventionControl", "name": "预防A"},
                {"id": "dc1", "type": "DetectionControl", "name": "探测B"},
            ],
            "edges": [
                {"source": "fc1", "target": "fm1", "type": "CAUSE_OF"},
                {"source": "fc1", "target": "pc1", "type": "PREVENTED_BY"},
                {"source": "fc1", "target": "dc1", "type": "DETECTED_BY"},
            ],
        }
    svc._get_graph_data_by_fmea_id = fake_graph_data  # type: ignore[method-assign]

    import asyncio
    nodes = asyncio.get_event_loop().run_until_complete(
        svc._extract_neighbors_from_match(match, "prevention_control")
    )
    names = [n["name"] for n in nodes]
    assert "预防A" in names
    assert "探测B" not in names


def test_extract_neighbors_detection_control_only_detected_by():
    """detection_control 图谱增强只取 DETECTED_BY 邻居。"""
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    match = {"node_id": "fm1", "fmea_id": str(uuid.uuid4())}
    async def fake_graph_data(_fmea_id):
        return {
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "m"},
                {"id": "fc1", "type": "FailureCause", "name": "c"},
                {"id": "pc1", "type": "PreventionControl", "name": "预防A"},
                {"id": "dc1", "type": "DetectionControl", "name": "探测B"},
            ],
            "edges": [
                {"source": "fc1", "target": "fm1", "type": "CAUSE_OF"},
                {"source": "fc1", "target": "pc1", "type": "PREVENTED_BY"},
                {"source": "fc1", "target": "dc1", "type": "DETECTED_BY"},
            ],
        }
    svc._get_graph_data_by_fmea_id = fake_graph_data  # type: ignore[method-assign]

    import asyncio
    nodes = asyncio.get_event_loop().run_until_complete(
        svc._extract_neighbors_from_match(match, "detection_control")
    )
    names = [n["name"] for n in nodes]
    assert "探测B" in names
    assert "预防A" not in names
```

- [ ] **Step 4: Run the new tests**

Run: `cd backend && python -m pytest tests/test_recommendation_service.py -v -k "extract_neighbors"`
Expected: PASS (2 new tests).

- [ ] **Step 5: Run full recommendation test file**

Run: `cd backend && python -m pytest tests/test_recommendation_service.py -v`
Expected: all pass.

- [ ] **Step 6: Verify Python syntax / import**

Run: `cd backend && python -c "from app.services.recommendation_service import PROMPT_TEMPLATES, RuleEngine; assert 'prevention_control' in PROMPT_TEMPLATES; assert 'detection_control' in PROMPT_TEMPLATES; RuleEngine().evaluate('prevention_control', {'failure_mode':'x'}); print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_recommendation_service.py
git commit -m "feat(dfmea): LLM prompts + graph enrichment for prevention/detection_control triggers"
```

---

### Task 3: 后端 API 层 — 确认 anchor + 注释（验证性，最小改动）

**Files:**
- Inspect/verify: `backend/app/api/fmea.py:245-260`（`_recommend_anchor`）、`:300-313`（anchor 注释）。
- Modify (optional, doc-only): `backend/app/api/fmea.py` 注释补新 trigger 名。

**Interfaces:**
- Produces: 确认 `/fmea/{id}/recommend` 对新 trigger 正常路由（anchor 走默认 failure_mode 分支）。
- Consumes: Task 1/2 的 schema + service。

- [ ] **Step 1: Verify anchor routing with a focused test**

Append to `backend/tests/test_recommendation_service.py` (or a new test) — actually the anchor lives in `api/fmea.py` which is harder to unit-test in isolation. Instead verify via the service-level: confirm a RecommendRequest with the new trigger produces a non-empty response when failure_mode is a usable anchor. Append:

```python
def test_recommend_request_accepts_new_triggers():
    """RecommendRequest schema 接受新 trigger_type；service 不抛未路由错误。"""
    req = RecommendRequest(trigger_type="prevention_control", context={"failure_mode": "采集数据失效", "ap": "H"})
    assert req.trigger_type == "prevention_control"
    engine = RuleEngine()
    result = engine.evaluate(req.trigger_type, req.context)
    assert len(result.suggestions) > 0
```

- [ ] **Step 2: Run the test**

Run: `cd backend && python -m pytest tests/test_recommendation_service.py::test_recommend_request_accepts_new_triggers -v`
Expected: PASS（schema 接受 + rule 返回非空）。若 FAIL 在 `RecommendRequest(trigger_type=...)` 验证错误，说明 Task 1 的 schema 改动未生效，回查。

- [ ] **Step 3: (Optional doc) Update the anchor comment in api/fmea.py**

In `backend/app/api/fmea.py`, around line 306, the comment says `effect/cause/measure/optimization`. Optionally extend to mention the new triggers. Only if it reads naturally — this is doc-only, skip if it would be a churn edit. If skipping, leave a one-line note in the commit message.

- [ ] **Step 4: Run the broader recommend-related test suite (regression)**

Run: `cd backend && python -m pytest tests/ -k "recommend or fmea" -x --tb=short`
Expected: all pass（含 test_recommendation_service / test_dfmea_tool_trend_recommendation 等）。

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_recommendation_service.py
git commit -m "test(dfmea): verify RecommendRequest accepts prevention/detection_control triggers"
```

---

### Task 4: 前端 SmartSuggestionDropdown — 扩 triggerType 联合类型

**Files:**
- Modify: `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx:13`（`triggerType` 类型）+ `:12-21`（interface）。

**Interfaces:**
- Produces: `SmartSuggestionDropdown` 的 `triggerType` 接受 `"prevention_control" | "detection_control"`。
- Consumes: 无（首个前端 task）。

- [ ] **Step 1: Extend the triggerType union**

In `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`, replace the `triggerType` line in the `SmartSuggestionDropdownProps` interface (line 13):

```ts
  triggerType: "failure_mode" | "failure_effect" | "failure_cause" | "measure" | "optimization" | "prevention_control" | "detection_control";
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dfmea/SmartSuggestionDropdown.tsx
git commit -m "feat(dfmea): SmartSuggestionDropdown accepts prevention/detection_control triggers"
```

---

### Task 5: 前端 renderStep3 — PC/DC 改用 SmartSuggestionDropdown

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx:576-581`（PC/DC 两个 `<Input>` 块）。

**Interfaces:**
- Consumes: Task 4 的 `triggerType` 扩展；既有 `handleUpdateControl(causeId, type, value: string)`、`SmartSuggestionDropdown`、`processStep`、`fmeaId`、`fmNode.name`、`func.name`。
- Produces: 第 4 步 PC/DC 输入框具备 AI 推荐。

- [ ] **Step 1: Replace the PC/DC Input block with SmartSuggestionDropdown**

In `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`, replace the PC/DC block (lines 576-581):

```tsx
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.preventionControl')}</div>
                            <Input size="small" value={pcName} placeholder={t('wizard.optimization.preventionPlaceholder')}
                              onChange={e => handleUpdateControl(causeNode.id, 'prevention', e.target.value)} />
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.detectionControl')}</div>
                            <Input size="small" value={dcName} placeholder={t('wizard.optimization.detectionPlaceholder')}
                              onChange={e => handleUpdateControl(causeNode.id, 'detection', e.target.value)} />
```

with:

```tsx
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.preventionControl')}</div>
                            <SmartSuggestionDropdown
                              triggerType="prevention_control"
                              context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
                              fmeaId={fmeaId!}
                              value={pcName}
                              onChange={(val) => handleUpdateControl(causeNode.id, 'prevention', val)}
                              onSelect={(s) => handleUpdateControl(causeNode.id, 'prevention', s.name)}
                            />
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.detectionControl')}</div>
                            <SmartSuggestionDropdown
                              triggerType="detection_control"
                              context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
                              fmeaId={fmeaId!}
                              value={dcName}
                              onChange={(val) => handleUpdateControl(causeNode.id, 'detection', val)}
                              onSelect={(s) => handleUpdateControl(causeNode.id, 'detection', s.name)}
                            />
```

> `handleUpdateControl(causeId, type, value: string)` 签名不变——`onSelect` 传 `s.name`、`onChange` 传 `val`，均为字符串。`Input` 不再用于 PC/DC；若 `Input` 在文件其他位置仍被使用（FM/FE/FC 已是 SmartSuggestionDropdown，结构树/其他步骤仍用 Input），无需动 import。

- [ ] **Step 2: Typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors（29 个既有 warning 不变）。

- [ ] **Step 3: Run the wizard Step 3 AI-wiring test (regression)**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/DFMEAWizardPage.test.tsx`
Expected: PASS。该测试往 `inputs[0..2]`（FM/FE/FC）打字；PC/DC 下拉是 `SmartSuggestionDropdown`（内部 `Input.TextArea`），插在 FC 之后。**若测试按 `inputs` 顺序索引且 PC/DC textarea 改变了 inputs 数组顺序/数量导致索引错位，需检查**——先跑确认。`SmartSuggestionDropdown` 渲染 `Input.TextArea`，原 PC/DC 是 `Input`（单行），改后 textarea 数量 +2。若测试用 `getAllByRole('textbox')` 取前 3 个，FM/FE/FC 仍在前 3（它们也是 textarea），PC/DC 在后，索引不变。

- [ ] **Step 4: Run full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: all pass（既有 267 测试）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea): wire Step 4 PC/DC to AI recommend (prevention/detection_control triggers)"
```

---

### Task 6: 全量验证 + 手动 HMR 清单

**Files:** 无代码改动。

- [ ] **Step 1: Backend full recommend test suite**

Run: `cd backend && python -m pytest tests/ -k "recommend" --tb=short`
Expected: all pass.

- [ ] **Step 2: Frontend full lint + build + tests**

Run: `cd frontend && npm run lint && npm run build && npx vitest run`
Expected: lint 0 error、build 绿、tests 全绿。

- [ ] **Step 3: Manual verification (Docker HMR)**

If Docker running (`docker compose up`), open a DFMEA wizard at an existing DFMEA doc, go to Step 4 (失效分析), and verify:
1. 每条 cause 下有「预防措施」「探测措施」两个带 💡 灯泡图标的输入框（与 FM/FE/FC 一致）。
2. 在 PC 输入框打 ≥2 字（且该行 failure_mode 已填）→ 下拉只见预防类措施（如「冗余设计」「降额设计」），不见探测类。
3. 在 DC 输入框打 ≥2 字 → 下拉只见探测类措施（如「在线实时监测」「气密性测试」），不见预防类。
4. 选中一项 → 写入对应 PC/DC 节点 name；第 5 步（风险分析）表格的 PC/DC 列显示该文本，O/D 解锁可打分。
5. scope 切换（全局/当前产品线）、限流提示、AI 不可用回退——与 FM/FE/FC 行为一致。
6. failure_mode 为空时 PC/DC 不下拉（后端 anchor<2 early return）。

- [ ] **Step 4: Final commit (if any fixups)**

若手动验证发现需微调，修正后提交。否则无 commit。

---

## Self-Review

**1. Spec coverage:**
- §1a schema 加 Literal → Task 1 Step 3。✓
- §1b 规则引擎抽 `_measure_lists` + 两个 handler + dispatch → Task 1 Step 4。✓
- §1c LLM 两个模板 → Task 2 Step 1。✓
- §1d `_recommend_anchor` 无需改 → Task 3 验证（test_recommend_request_accepts_new_triggers 间接覆盖）。✓
- §1e `_extract_neighbors_from_match` 两个分支 → Task 2 Step 2。✓
- §2a `SmartSuggestionDropdown` triggerType 扩展 → Task 4。✓
- §2b `renderStep3` PC/DC 换 SmartSuggestionDropdown → Task 5。✓
- §3 context `{failure_mode, function_description, process_step}` → Task 5 代码块。✓
- 测试：后端 rule handler（Task 1）、graph 增强（Task 2）、schema 接受（Task 3）；前端 tsc/lint/vitest（Task 4/5/6）。✓
- 验证：后端 pytest、前端 build、手动 HMR → Task 6。✓

**2. Placeholder scan:** 无 TBD/TODO；每个代码 step 含完整代码块。✓

**3. Type consistency:**
- `_measure_lists` 返回 `tuple[list[str], list[str], Literal["specific","generic"]]`（Task 1 定义，Task 1 三个 handler 消费）。✓
- trigger 字符串 `prevention_control` / `detection_control` 全文一致（schema、dispatch、PROMPT_TEMPLATES、_extract_neighbors、前端 triggerType、renderStep3）。✓
- `handleUpdateControl(causeId, type, value: string)` 签名一致（既有，Task 5 消费，不变）。✓
- `SmartSuggestionDropdown` props：`triggerType` / `context` / `fmeaId` / `value` / `onChange(val)` / `onSelect(s)` 与既有 FM/FE/FC 用法一致（Task 5 对照 :568-575 既有 failure_cause 用法）。✓

无遗漏。
