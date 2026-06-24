# DFMEA 向导第 4 步 PC/DC AI 推荐设计

- 日期：2026-06-24
- 分支：`worktree-dfmea-wizard-pcdc-ai`（基于 `fix/fmea-fixes` @ 836ceed）
- 涉及文件：
  - 后端：`backend/app/schemas/recommendation.py`、`backend/app/services/recommendation_service.py`、`backend/app/api/fmea.py`（仅注释，可选）
  - 前端：`frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`、`frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`
- 测试：后端 `backend/tests/`（推荐服务测试）、前端 `npx tsc --noEmit` + `npm run lint` + 既有测试

## 背景

DFMEA 向导第 4 步（失效分析，`renderStep3`）已为 失效模式(FM)/失效影响(FE)/失效原因(FC) 接入 AI 推荐（`SmartSuggestionDropdown`，commit 9c669aa）。但同步骤的 **预防措施(PC)/探测措施(DC)** 仍是普通 `<Input>`，无 AI 提示——与"和其他输入框的提示效果一致"的要求不符。

后端已有 `"measure"` trigger（`recommendation_service.py:187` `_suggest_measures`），但它返回 **P+D 混合列表**（用 `explanation` "预防措施"/"检测措施" 区分，LLM 模板要求 name 加 `P:`/`D:` 前缀）。PC/DC 是两个独立输入框，各需只看自己类型的推荐，混合列表不适用。

## 目标

- 第 4 步 PC/DC 输入框与 FM/FE/FC 一样具备 AI 推荐（`SmartSuggestionDropdown`）。
- PC 下拉只见预防措施，DC 下拉只见探测措施——按类型拆分，不混合。
- 复用既有 `SmartSuggestionDropdown` 组件与推荐管线（graph/LLM/rule 三源、scope 切换、限流），不改组件行为。

## 非目标（范围外）

- 不改主 FMEA 编辑器（`FMEAEditorPage`）的 PC/DC 单元格——编辑器有自己的推荐接线。
- 不删旧 `"measure"` trigger——保留（前端目前无消费者，但避免 schema 破坏性删除；内部重构为共享 helper，对外行为一致）。
- 不动第 5 步（风险分析）——PC/DC 在那里是只读展示。
- 不改 `SmartSuggestionDropdown` 的 UI/交互逻辑——只扩 `triggerType` 联合类型。

## 设计

### 1. 后端：新增两个 trigger

#### 1a. `schemas/recommendation.py`
`trigger_type` Literal 追加 `"prevention_control"`, `"detection_control"`：
```python
trigger_type: Literal[
    "failure_mode", "failure_effect", "failure_cause", "measure", "optimization",
    "dfmea_tool", "dfmea_trend",
    "prevention_control", "detection_control",
]
```

#### 1b. `services/recommendation_service.py` — 规则引擎
- 把 `_suggest_measures` 内部「按 AP/关键词生成 prevention/detection 两列表 + quality」的逻辑抽成共享 `_measure_lists(self, context) -> tuple[list[str], list[str], Literal["specific","generic"]]`。现有 `_suggest_measures` 改为调用它并合并返回（行为不变）。
- 新增 `_suggest_prevention_control(self, context) -> RuleResult`：调用 `_measure_lists`，只取 prevention 半，`[RuleSuggestion(name=p, confidence=0.6, explanation="预防措施") for p in prevention]`，quality 同 `_measure_lists`。
- 新增 `_suggest_detection_control(self, context) -> RuleResult`：同理只取 detection 半，explanation "检测措施"。
- `dispatch` 字典加 `"prevention_control": self._suggest_prevention_control`、`"detection_control": self._suggest_detection_control`。

#### 1c. `services/recommendation_service.py` — LLM 提示模板
`PROMPT_TEMPLATES` 新增两个聚焦模板（`measure` 模板的拆分版，只问一种类型，**不要求** `P:`/`D:` 前缀）：

- `"prevention_control"`：任务=为失效模式推荐 3-5 个「预防控制(P)」；定义=阻止失效模式/原因发生的设计或工艺手段；上下文同 measure（fmea_type/process_step/failure_mode/ap）；返回 JSON `{"suggestions":[{"name","confidence","explanation"}]}`，name 为纯措施描述无前缀。
- `"detection_control"`：任务=推荐「探测控制(D)」；定义=交付前探测失效模式/原因的检验/测试手段；其余同上。

> 提示模板的填充与选择逻辑在 `recommendation_service.py` 既有流程里按 `trigger_type` 取 `PROMPT_TEMPLATES[trigger_type]`——新 key 自动生效，无需改路由。

#### 1d. `api/fmea.py` `_recommend_anchor`
新 trigger 以 `failure_mode` 为 anchor（与 effect/cause/measure 一致），已落到默认分支 `return context.get("failure_mode") or context.get("input_text") or ""`，**无需改动**。:306 附近注释提及 "effect/cause/measure/optimization"，可顺带补上 prevention_control/detection_control（文档性，可选）。

#### 1e. `services/recommendation_service.py` — 图谱增强（`_extract_neighbors_from_match`）
该函数（:556-609）按 trigger_type 分支从相似 FMEA 的图里抽邻居节点做图谱增强；新 trigger 当前会落到 `return []`（:609）——无增强。为与 FM/FE/FC/measure 一致（"提示效果一致"），补两个分支，复用 `measure` 分支（:581）的「fm_id + 其 causes 的控制边」逻辑但只取一种边类型：

```python
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
    # 同上，边类型换 DETECTED_BY
```

> 注：`measure` 分支收集 fm_id 及其 causes 的 PREVENTED_BY+DETECTED_BY 邻居；新分支是它的单类型子集。图谱匹配本身（`find_similar_nodes` 按 failure_mode 语义检索）trigger 无关，不受影响。

### 2. 前端：PC/DC 改用 SmartSuggestionDropdown

#### 2a. `SmartSuggestionDropdown.tsx`
`triggerType` 联合类型追加 `"prevention_control" | "detection_control"`：
```ts
triggerType: "failure_mode" | "failure_effect" | "failure_cause" | "measure" | "optimization" | "prevention_control" | "detection_control";
```
组件其余逻辑 trigger 无关，不动。

#### 2b. `DFMEAWizardPage.tsx` `renderStep3`
当前 PC/DC 是两个 `<Input size="small">`（在 `causeNodes.map` 块内，`handleUpdateControl` 回调）。替换为 `SmartSuggestionDropdown`，结构与同块的 FM/FE/FC 下拉一致（label `<div>` + 下拉）：

```tsx
// PC
<div>
  <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.preventionControl')}</div>
  <SmartSuggestionDropdown
    triggerType="prevention_control"
    context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
    fmeaId={fmeaId!}
    value={pcName}
    onChange={(val) => handleUpdateControl(causeNode.id, 'prevention', val)}
    onSelect={(s) => handleUpdateControl(causeNode.id, 'prevention', s.name)}
  />
</div>
// DC 同理，triggerType="detection_control"，'detection'
```

`handleUpdateControl(causeId, type, value: string)` 签名不变——`onSelect` 传 `s.name`、`onChange` 传 `val`，均为字符串。`SmartSuggestionDropdown` 已在文件顶部 import（9c669aa）。`processStep`/`fmeaId` 已在 `renderStep3` 作用域内。

### 3. 传给新 trigger 的 context
`{ failure_mode, function_description, process_step }`——与向导现有 `failure_cause` 下拉一致。规则/LLM 以 `failure_mode` 为 anchor。

## 测试

### 后端
- 若 `backend/tests/` 存在推荐服务测试（如 `test_recommendation_service.py` 或 `test_recommend_*`），补两个用例：
  - `_suggest_prevention_control` 只返回预防项（explanation 含"预防"，name 不含 `D:`/检测关键词列表里的检测项）。
  - `_suggest_detection_control` 只返回探测项。
  - 既有 `measure` 用例仍通过（行为不变）。
- 若无现成测试文件：新建 `backend/tests/test_recommendation_service_pcdc.py`，聚焦测两个新 handler 的返回类型拆分 + `measure` 仍混合。
- 运行：`cd backend && python -m pytest tests/ -x --tb=short -k recommend`（或既有推荐测试命令）。

### 前端
- `cd frontend && npx tsc --noEmit && npm run lint`——clean。
- `npx vitest run`——既有 267 测试仍绿。`DFMEAWizardPage.test.tsx` 往 FM/FE/FC 前三个输入框打字——PC/DC 下拉是新增输入，不影响该测试对前三个的断言（确认 `inputs[0..2]` 索引仍指向 FM/FE/FC；若 PC/DC 下拉插在 cause 块内、位于 FC 之后，索引不变）。
- Docker HMR 手动：第 4 步 PC 字段输入≥2字→下拉只见预防项；DC 字段→只见探测项；选中写入对应节点 name；空 failure_mode 时不下拉（anchor<2 守卫）。

## 验证

- 后端：`pytest` 推荐测试通过。
- 前端：`npm run lint` 0 error、`npm run build` 绿、`vitest` 全绿。
- 手动 HMR 走查上述场景。

## 风险与备注

- `SmartSuggestionDropdown` 的 `onChange` 在每次按键触发（500ms 防抖后 fetch），PC/DC 编辑会触发推荐请求——与 FM/FE/FC 一致，符合"提示效果一致"要求。限流由后端 per-user/per-fmea 守卫。
- 旧 `measure` trigger 保留但前端无消费者；若后续确认无任何外部消费者，可另行清理（本次不做）。
- LLM 模板新增两个 key 会使 `PROMPT_TEMPLATES[trigger_type]` 对新 trigger 命中；若某 trigger 无模板，既有流程回退规则——新 trigger 已配模板，不触发回退。
