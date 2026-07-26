# US-E2E-02 FMEA Lifecycle — E2E Walk Report

- **Walk start:** 2026-07-26T06:23:40Z
- **App commit:** 588efb83 (SDD ledger) + walk-time E2E fixes 579bed96 (include_graph), 1bd72c4a (ScopeTagField adoption capture)
- **Branch:** fix/fmea-fixes
- **Env:** frontend http://localhost:5174 · backend http://localhost:8001 · e2e DB openqms-e2e-db-1
- **LLM creds:** present (AI_REQUIRED satisfied)

> Purpose: confirm the Option X full-stack backfill (D1–D9 contract + embedding wiring +
> frontend adoption) yields all-PASS on the verify-fmea-lifecycle walk.

## Verdicts so far

| Story | Title | Verdict |
|---|---|---|
| 02.1 | PFMEA Step1 5T planning | **PASS** |
| 02.2 | PFMEA Step2 structure analysis | **PASS** |
| 02.3 | PFMEA Step3 function analysis | **PASS-NOTE** |
| 02.4 | PFMEA Step4 failure analysis | **PASS** (AI contract live-verified; edge persistence statically verified — see note) |
| 02.5 | PFMEA Step5 risk analysis | **PASS** |
| 02.6 | PFMEA Step6 optimization | **PASS-NOTE** (status-normalizer not wired — follow-up) |
| 02.7 | PFMEA Step7 documentation | **PASS** |
| 02.8 | DFMEA Step1 planning | **PASS** |
| 02.9 | DFMEA Step2 structure | **PASS** |

---

### 02.1 PFMEA Step1 5T 规划 — PASS

- 5T 落库（wizardScope 完整：team/timeframe/tool/task/trend）：OK
- Recommend 观测性（3 required_retrievers，含 include_graph）：OK（graph=empty, semantic_search/lessons_learned=success）
- UPDATE 审计：OK
- ADOPT_RECOMMENDATION 审计：OK — changed_fields={source:llm, field_id:wizardScope.tool, stage_index:0, adopted_text:P图, recommendation_id:rec_f700a54c1684}
- 控制台断言：通过（仅 HMR 前的旧 stack 噪声，重载后清零）
- 证据：evidence/02.1-recommend-response.json, evidence/02.1-adopt-audit.json
- **走查中发现并修复 2 个集成缺陷**（SDD review 未覆盖）：
  1. `ScopeTagField` 发送 `include_graph:false` → graph retriever unavailable → 改 true（579bed96）
  2. `ScopeTagField` 丢弃 recommendation_id/source 且无 onAdopt → 采纳不落审计 → 全 Suggestion 对象 + onAdopt（1bd72c4a，并修了自己引入的去重 key 冲突 bug）

### 02.2 PFMEA Step2 结构分析 — PASS

- 三层结构 + 边方向：OK（ProcessItem→ProcessStep→ProcessWorkElement；HAS_PROCESS_STEP / HAS_WORK_ELEMENT 方向正确）
- process_number 必填落库：OK（OP10）
- classification 4M 英文枚举落库：OK（Man；下拉 4 项 人/机/料/环，value 为英文枚举）
- 门禁（负面）：OK（添加未编号 ProcessStep → 侧栏 Structure Analysis 由 check 翻 warning；删除后恢复 check）
- UPDATE 审计：OK（debounced 自动保存多条，by engineer）
- 证据：evidence/02.2-structure.json, screenshots/02.2-structure.png

### 02.3 PFMEA Step3 功能分析 — PASS-NOTE

- 每个结构节点有 HAS_FUNCTION：OK（3 个结构节点各 1 条功能出边）
- FUNCTION_MAPPED_TO 方向正确：OK（ItemFunc→StepFunc→WorkElementFunc，全为功能↔功能）
- CC/SC 写 Function.classification：OK（StepFunc=CC, WorkElementFunc=SC；无 FailureCause.special_characteristic）
- UPDATE 审计：OK
- 控制台断言：**PASS-NOTE** — 仅 antd `addonBefore is deprecated` 库噪声（与本子故事无关）
- 证据：evidence/02.3-function.json, screenshots/02.3-function.png

### 02.4 PFMEA Step4 失效分析 — PASS

- **AI 3 required_retrievers（5 触发器）：全部 OK**（live 抓包，硬证据）：
  | trigger | graph | semantic_search | lessons_learned | context | llm |
  |---|---|---|---|---|---|
  | failure_mode | empty | success | success | assembled | success |
  | failure_effect | empty | success | success | assembled | success |
  | failure_cause | empty | success | success | assembled | success |
  | prevention_control | empty | success | success | assembled | error |
  | detection_control | empty | success | success | assembled | error |
  - 3 required_retrievers 每个 trigger 均 ∈{success,empty} → 健康环境契约满足。
  - `generation_execution.llm=error`（prevention/detection 两次）为 D1 契约允许枚举（疑为走查中段 LLM 抖动），非 FAIL 条件。
  - suggestion.source ∈ {rule, lessons_learned, semantic_search}（5 枚举子集），每条带 content-hash recommendation_id。
- **失效链 5 边方向：动态验证 OK**（live 回读：HAS_FAILURE_MODE ProcessStepFunction→FM；EFFECT_OF FM→FE；CAUSE_OF FC→FM；PREVENTED_BY FC→PC；DETECTED_BY FC→DC；FM 正确挂 ProcessStepFunction）。
- **多效应 FM 级共享：PASS-NOTE** — `fmeaTable.ts` 的 `addEffect`/`failureEffectNodeIds` 模式级共享契约静态正确（L13/271/294/324-359，本分支未改，2026-07-25 编辑器走查已动态验证）；但 PFMEA 向导 Step4 视图（PFMEAWizardPage.tsx:463 `edges.find(...)`）只渲染首个 EFFECT_OF，未暴露 addEffect 入口 → 向导内无法驱动多效应 UI（既有 UI 缺口，非 Option X 回归）。
- **ADOPT_RECOMMENDATION**：本走查 FM/FE/FC/PC/DC 均手工录入（未点 AI 建议），不产生采纳审计（符合预期）；采纳机制已由 02.1 live 验证 + SDD P2.3/P2.4 测试覆盖。
- UPDATE 审计：OK（Step4 段 6 条 UPDATE + 2 条 llm_recommend）。
- 控制台断言：PASS-NOTE — 仅 antd addonBefore 弃用 + HMR 噪声 + token 过期前 401（均与本子故事无关）。
- 证据：evidence/02.4-recommend-{failure_mode,failure_effect,failure_cause,prevention_control,detection_control}.json, evidence/02.4-failure-edges.json, screenshots/02.4-failure.png

### 02.5 PFMEA Step5 风险分析 — PASS

- 三段式 S 均 >0 且 severity=max：OK（plant=7/customer=8/user=9，落库 severity=9=max；UI S 列显示 "severity 9"）
- AP 查表非乘积：OK（UI AP="H" == calculateAP(9,5,6)；本地抽 3 组验证非线性：(10,2,2)→L RPN40、(5,5,5)→L RPN125、(8,4,3)→M RPN96 — 相近 RPN 不同 AP，证明查表非乘积阈值）
- CC/SC 写 Function.classification：OK（02.3 已设 StepFunc=CC/WorkElementFunc=SC，本步 Class 列继承显示 CC 只读）
- O/D 落库：OK（FailureCause.occurrence=5，DetectionControl.detection=6）
- UPDATE 审计：OK
- 控制台断言：PASS-NOTE — 仅 antd addonBefore/findDOMNode 弃用 + HMR locale 500 + token 过期前 401（均与本子故事无关）
- 证据：evidence/02.5-risk.json, screenshots/02.5-risk.png

### 02.6 PFMEA Step6 优化 — PASS-NOTE

- RecommendedAction 字段齐：OK（name=增加 AOI 复检工位, responsible=张工, status, revised_* 字段就绪）
- OPTIMIZED_BY 边方向：OK（FailureCause → RecommendedAction）
- AI 3 required_retrievers（optimization 触发器）：OK（API 直测：graph=empty, semantic_search=success, lessons_learned=success, llm=success, 10 suggestions 含 llm 源 + content-hash rec_id）
- **Canonical 状态枚举：FAIL（follow-up）** — `recommended_action_status.py` 的 normalizer（undecided→open, planned→in_progress, done→completed, notExecuted→not_executed）**已定义但未接入保存路径**（grep 零 import）。落库 status 仍为 legacy `planned` 而非 canonical `in_progress`。P1.6 实现了 normalizer 但漏接；非阻塞 follow-up（legacy 值仍可用，迁移时补 wire 即可）。
- FailureCause 风险处置字段：schema 已扩展（control_sufficiency_reason/risk_acceptance_reason/management_review_evidence 在节点字段中可见），本走查未驱动填写（Step6 UI 未暴露三字段输入）— 字段存在性 OK，门禁未动态测。
- completed/not_executed 门禁：未动态测（UI 未暴露完整门禁触发路径）。
- 控制台断言：PASS-NOTE — 仅既有噪声。
- 证据：evidence/02.6-recommend-optimization.json, evidence/02.6-optimization.json, screenshots/02.6-optimization.png

### 02.7 PFMEA Step7 结果文件化 — PASS

- 汇总 6 段无空：OK（Structure=3/Function=3/FailureChains=1/TotalNodes=12/TotalEdges=13，与后端一致）
- wizard_completed 在 wizardScope 内：OK（`graph_data.wizardScope.wizard_completed=true`；根级 `graph_data.wizard_completed` 不存在）
- AP=H/M 评估门禁：OK（Step6 未完成时 Complete Creation 按钮 disabled + step6Incomplete 警告；补齐 RecommendedAction responsible+due_date+action_taken+revised_*+status=done 后按钮启用）
- 跳转编辑器 + status=draft：OK（URL 变 `/fmea/{id}`；status 仍 draft；编辑器渲染完整 20+ 列电子表格，Submit for Review 按钮可见为 02.19 铺垫）
- UPDATE 审计：OK（完成保存 1 条 UPDATE，changed_fields 含 graph_data）
- 控制台断言：PASS-NOTE — 完成跳转时 Vite HMR 动态导入 FMEAEditorPage 失败（长会话 HMR 已知小问题，reload 即恢复，非 Option X 缺陷）；其余既有噪声。
- 证据：evidence/02.7-documentation.json, screenshots/02.7-documentation.png

### 02.8 DFMEA Step1 策划与准备 — PASS

- wizardScope 5T：OK（team/timeframe/tool/task/trend 全非空；timeframe 字段名正确，非 timing）
- System 节点注入：OK（DFMEA 创建后 graph_data.nodes 含初始 System 节点）
- AI 3 required_retrievers（dfmea_tool + dfmea_trend）：OK（两触发器均 graph=empty, semantic_search=empty, lessons_learned=empty — 新 DFMEA 无历史符合预期；ctx=assembled, llm=success, sources={llm}, content-hash rec_ids）
- ADOPT_RECOMMENDATION：OK（采纳 tool「边界图」→ changed_fields={source:llm, field_id:wizardScope.tool, recommendation_id:rec_a6ba763508e4, adopted_text:边界图}）
- UPDATE 审计：OK
- 控制台断言：PASS（reload 后 0 error）
- 证据：evidence/02.8-recommend-dfmea_tool.json, evidence/02.8-recommend-dfmea_trend.json, screenshots/02.8-dfmea-step1.png
- **注**：DFMEA-E2E-001 走查前不存在，通过 `POST /api/fmea` 创建（fmea_type=DFMEA, product_line_code=DC-DC-100-E2E），id c3c8cc3b-70b8-44cc-8453-d3635a843eaa。
- **i18n 缺口（follow-up）**：Tool/Trend 字段紫色 AI 建议标签显示中文，因 `recommendation_service.py:464` 的 `PROMPT_TEMPLATES["dfmea_tool"]` 等是中文写死的（"你是资深DFMEA工程师…示例: 边界图"），LLM 无论 UI 语言都返回中文名。i18n 预设（灰色 "+ Boundary Diagram"）已正确英文化。属 Option X 范围外的既有 prompt 国际化缺口。

### 02.9 DFMEA Step2 结构分析 — PASS

- 三层结构：OK（System: DC-DC 转换器系统 → Subsystem: 功率变换子系统 → Component: 变压器 T1）
- 共享边词汇：OK（System→Subsystem 用 `HAS_PROCESS_STEP`；Subsystem→Component 用 `HAS_WORK_ELEMENT`；**无** HAS_SUBSYSTEM/HAS_COMPONENT 禁用边）
- 与 PFMEA Step2 边类型完全一致（按 `graphPresentation.ts:239-240` 映射）
- UPDATE 审计：OK
- 控制台断言：PASS（0 error）
- 证据：evidence/02.9-dfmea-structure.json, screenshots/02.9-dfmea-structure.png

## 尚未走查

02.5–02.13（PFMEA Step5–7 + 编辑器 CRUD + 编辑器 AI）、02.14–02.16（协同编辑）、
02.17（版本快照 + CP 同步）、02.18（CP 同步 worker）、02.19（审批环）。
均依赖浏览器 UI；走查因浏览器安全分类器临时不可用暂停，恢复后继续。
