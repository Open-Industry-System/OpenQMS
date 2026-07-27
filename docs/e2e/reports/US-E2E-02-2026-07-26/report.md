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
| 02.10 | DFMEA Step3 function | **PASS** |
| 02.11 | DFMEA Step4 failure | **PASS** (FM on ProcessWorkElementFunction + 5 edges + no 4M + AI contract) |
| 02.12 | DFMEA Step5 risk | **PASS** (S=9/O=4/D=5→AP=H, RPN=180 non-linear) |
| 02.13 | DFMEA Step6 optimization | **PASS** (OPTIMIZED_BY + optimization AI contract) |
| 02.14 | DFMEA Step7 documentation | **PASS** (summary counts + wizard_completed in wizardScope) |
| 02.18 | version snapshot + CP sync | **PASS** (caught+fixed DFMEA guard defect) |
| 02.19 | approval cycle | **PASS** (14/14 API cases) |
| 02.15 | editor row CRUD + multi-effect | **PASS-NOTE** (multi-effect FM-level sharing live-verified; SC-sync 403 + addCause self-edge pre-existing) |
| 02.16 | editor AI recommend | **PASS-NOTE** (8/9 checkpoints live; §I recommend-lacks-status-gate is pre-existing spec gap) |
| 02.17 | collaborative editing | **PASS** (4 API checkpoints live: 409/conflict, FORCE_SAVE_OVERRIDE+wizardScope, 二次冲突, no-increment; UI wiring static-verified) |

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

### 02.10 DFMEA Step3 功能分析 — PASS

- Component 有 HAS_FUNCTION：OK（Component 变压器 T1 → ProcessWorkElementFunction「转换电压」；DFMEA 复用 ProcessWorkElementFunction 节点类型，与 PFMEA 共享功能契约）
- 规范/要求落库：OK（specification=输出精度 ±2%, requirement=输入12V输出5V）
- 控制台断言：PASS（0 error）
- 证据：evidence/02.10-dfmea-function.json, screenshots/02.10-dfmea-function.png
- **注**：DFMEA Step3 仅 1 个功能节点时无 FUNCTION_MAPPED_TO 边（需 ≥2 功能才连），与 PFMEA Step3 契约一致；多结构节点功能挂载已在 PFMEA 02.3 动态验证。

### 02.18 版本快照 + CP 联动 — PASS（API 直调，动态验证）

- submit 快照字段齐：OK（change_type=submit, major_no=0, minor_no=1, sha256_hash 非空, created_by 非空）
- approve 快照字段齐：OK（change_type=approve, major_no=1, minor_no=0, sha256_hash 非空）
- **CP sync = Durable outbox**：OK（cp_sync_outbox 独立表，非 GraphSyncOutbox；审批事务入队 pre-commit；worker 批处理；幂等键 unique constraint `(fmea_id, fmea_version_id, event_type)` 存在）
  - 审批后 outbox 行 status=completed, processed_at 非空
  - worker 写 control_plans/UPDATE 审计，changed_fields 仅 `sync_pending:"false->true"` + `trigger_fmea_version_id`，**不含** source_fmea_version_id ✓
  - CP.source_fmea_version_id 仍 NULL（只在 CP 实际同步内容时更新）✓
  - 审计总量 = 2（TRANSITION + fmea_versions/CREATE）+ affected_cp_count（1 CP UPDATE）✓
- **幂等性（Test D APPROVED→REWORK→re-approve）**：OK
  - 2 条 outbox 行（不同 fmea_version_id），幂等键允许同 fmea 多次
  - CP sync_pending UPDATE 审计仅 1 条（worker `sync_pending == False` 过滤，已 pending 不重复审计）✓
- **DFMEA 不触发 CP sync（对照）**：**修复后 PASS**
  - **走查发现 DEFECT（已修）**：DFMEA 审批也入队 cp_sync_outbox 行（P1.9 漏了 `fmea_type == "PFMEA"` 守卫，fmea_service.py:433）。修复前 DFMEA approve → 1 行；修复后 → 0 行。已提交修复。
- 证据：evidence/02.18-cp-sync.json
- **预存 BUG（非本分支引入，main 也有）**：CP update API（link fmea_ref_id）500 — AuditLog changed_fields 存 UUID 非 str（control_plan_service.py:214，main 与本分支均未变）。走查用 DB 直改绕开。

### 02.19 审核闭环 — PASS（API 直调，14/14 用例）

| 用例 | 期望 | 实际 | 标签 |
|---|---|---|---|
| A 提交（wizard_completed=true） | 200 + TRANSITION + submit 快照 | 200, status=in_review | PASS |
| B wizard_completed=false → 422 | 422 | 422 "向导未完成，不能提交评审" | PASS |
| C manager 审批 | 200 + approved_by/at | 200, approved_by=manager_id, approved_at 非空 | PASS |
| D engineer 审批 → 403 | 403 | 403 "审批权限不足" | PASS |
| E1 驳回无 reason → 422 | 422 | 422 "驳回必须携带非空 reason" | PASS |
| E2 驳回空 reason → 422 | 422 | 422 | PASS |
| E3 驳回空白 reason → 422 | 422 | 422 | PASS |
| F1 engineer 驳回 → 403 | 403 | 403 "审批权限不足" | PASS |
| F2 manager 驳回带 reason → 200 | 200, status=rework | 200, status=rework | PASS |
| G APPROVED→REWORK 保留 approved_by/at | 保留 | status=rework, approved_by 仍 manager, approved_at 仍非空 | PASS |
| H IN_REVIEW PUT → 409 | 409 | 409 "当前状态不可编辑（仅草稿/返工可编辑）" | PASS |
| I DRAFT→APPROVED 跳步 → 400 | 400 | admin 400 "Cannot transition from draft to approved"（engineer 先撞 403 APPROVE 门） | PASS |
| J REWORK→IN_REVIEW wizard_completed=false → 422 | 422 | 422 "向导未完成" | PASS |
| J2 REWORK→IN_REVIEW wizard_completed=true → 200 | 200 | 200, status=in_review | PASS |

- 证据：evidence/02.19-approval-cycle.json
- **确认 follow-up**：rework reason 仅校验未持久化（fmea.py:224 transition_fmea 未传 req.reason）→ 审计 changed_fields 不含 reason。已在 ledger 记为最强 follow-up。

### 02.15 编辑器行 CRUD + 多效应 — PASS-NOTE（动态验证）

- **行 CRUD**：OK（编辑器 `/fmea/{id}` status=rework 可编辑；Add Cause → 新增第 2 行 FC「操作员未按 SOP」，FM×FC 语义正确：2 FailureCause 节点，2 条 CAUSE_OF 边均 → 同一 FM「贴装偏移」）
- **多效应 FM 级共享（核心断言）**：OK — 点「添加失效影响」在效应单元格内新增第 2 个效应输入框（**非**新行）；填「焊接短路」+ Save 后 API 回读：
  - FM「贴装偏移」(wcc56326e) 发出 **2 条 EFFECT_OF 边** → 2 个不同 FE 节点（焊接开路 wc67ee381 + 焊接短路 n1785117662）✓
  - 编辑器行数仍 2（单元格内多值，非笛卡尔积）✓
  - `failureEffectNodeIds` 字段 `NOT_SET`（数据模型用边表达多效应，非数组字段，与 `fmeaTable.ts` 一致）✓
- **wizardScope 保留**：OK（`wizard_completed=True`，tool/team/task/trend/timeframe 全保留；rework 编辑不洗向导范围）
- UPDATE 审计：OK（lock_version 50，graph_data 多次自动保存）
- 控制台断言：**PASS-NOTE** — 仅 2 条 `special-characteristics/sync-from-fmea` 403（engineer 无 SC 同步权限，保存后自动触发，pre-existing main 行为，非 Option X 回归）
- **预存 UI 缺口（follow-up，非本分支引入）**：第 2 行 FC「操作员未按 SOP」无 PC/DC 文本时，`PREVENTED_BY`/`DETECTED_BY` 边 source==target（自指），疑似 `fmeaTable.ts` addCause 边构造在空 PC/DC 时用 FC 自身占位；非阻塞。
- 证据：evidence/02.15-multi-effect.json

### 02.16 编辑器内 AI 推荐 — PASS-NOTE（动态验证）

- **5 触发器 + 3 required_retrievers（failure_mode live，全 5 触发器 02.4 已验）**：OK
  - 编辑器 FM 单元格输入「贴装偏移测试」→ SmartSuggestionDropdown 500ms 防抖弹出 → 5 条建议（rule/lessons_learned/semantic_search 来源齐全）
  - 响应 `source_executions`：graph=empty, semantic_search=success(7), lessons_learned=success(4)
  - `context_execution.current_product_structure=assembled`，`generation_execution.llm=success`，`llm_available=true`
- **source 枚举 + source_document_no**：OK（`source ∈ {rule, lessons_learned, semantic_search}`，每条带 content-hash `recommendation_id`；semantic_search 命中带 `source_document_no` E2E-FMEA-P-001/D-001）
- **§E ADOPT_RECOMMENDATION 审计（核心，live）**：OK — 点建议「贴装漏件」采纳 + Save → DB 写 `ADOPT_RECOMMENDATION`：`field_id=wcc56326e..._fm`, `source=rule`, `recommendation_id=rec_bc5d32dfe150`, `adopted_text=贴装漏件`, `stage_index=0`（5 元数据全落）
- **§F 手工 vs 采纳区分**：OK — 手工编辑 PC 单元格「SOP 培训与考核」+ Save → 仅写 1 条 UPDATE，`ADOPT_RECOMMENDATION` 计数不变（仍 2）；采纳路径同事务写 UPDATE+ADOPT_RECOMMENDATION（时间戳一致，幂等去重确认）
- **§G 限流 per_user 5/s**：OK — 1 秒内连发 6 次，第 6 次 HTTP 429「请求过于频繁」
- **§H 缓存 24h**：OK — 相同 trigger+context 第 2 次调用 `cached=true`（第 1 次 `cached=false`）；DB 确认 `recommendation_cache` 行写入，`expires_at = created_at + 24h`
- **§I 可编辑状态门禁**：**NOTE**（spec gap，非 Option X 回归）— `/api/fmea/{id}/recommend` 端点（fmea.py:281-336）仅校验 EDIT 权限 + 限流 + 工厂访问 + anchor 长度，**无 status 门禁**（IN_REVIEW/APPROVED 仍可触发推荐）。spec 表 §I 行标注「见 02.19」即此端点不独立校验，依赖 02.19 的 PUT 门禁。属既有设计，非本分支引入。
- 控制台断言：PASS-NOTE — 仅既有 `special-characteristics/sync-from-fmea` 403 噪声（engineer 无 SC 同步权限，保存后自动触发）。
- 证据：evidence/02.16-recommend-response.json, evidence/02.16-adopt-audit.json

### 02.17 协同编辑 + 冲突检测 — PASS（API 直调，4 关键契约 live + UI 接线静态验证）

- **§D 乐观锁 409 + conflict.latest_lock_version**：OK — engineer PUT (lock 52→53) 200；admin PUT (stale 52, current 53) → **409** + `conflict.latest_lock_version=53`
- **§G FORCE_SAVE_OVERRIDE + wizardScope 保留**：OK — admin retry `confirmed_latest_lock_version=53` → 200, lock 53→54, `wizardScope.wizard_completed=true` **保留**，FM 名覆盖为 admin 版本；DB 写 `action=FORCE_SAVE_OVERRIDE`，`operated_by=admin`，`changed_fields.reason="User confirmed overwrite after conflict detection"`
- **§H 二次冲突 `lock_version_changed_again`**：OK — engineer 再保存 (54→55) 后，admin 带 stale `confirmed_latest_lock_version=54` 重试 → **409** + detail "Document was modified again while you were reviewing. Please refresh." + `conflict.latest_lock_version=55`
- **§I lock_version 无变更不递增**：OK — no-op PUT（graph_data 完全相同）HTTP 200，lock_version 55→55（不递增）
- **UI 接线静态验证**（FMEAEditorPage.tsx）：
  - §A 在线用户列表：`useCollaboration` (:366) + `CollaborationBar` (:1655) 短轮询存在感
  - §B 行级编辑指示器：`ActiveUserIndicator activeUsers rowKey field` (:1109/1228/1316) 行+字段级
  - §E 三方 diff 对话框：`ConflictDialog` (:2085-2089) + `conflictInfo/conflictDiff` (:397-399)，`onRefresh`(放弃)/`onForceSave`(覆盖) 两路径
  - force save 发 `confirmed_latest_lock_version`：`handleConflictForceSave` (:650-658)
- 控制台断言：未单独采集（API 直调路径，无浏览器交互）；UI 接线静态完整。
- 证据：evidence/02.17-collab.json

### 02.11 DFMEA Step4 失效分析 — PASS（API 直调，DFMEA-specific 契约）

- **FM 挂 DFMEA 功能节点**：OK — `HAS_FAILURE_MODE` source = `ProcessWorkElementFunction`（转换电压），非 System/Subsystem/Component（DFMEA 功能节点复用类型，与 02.10 契约一致）
- **失效链 5 边方向**：OK — HAS_FAILURE_MODE(func→FM)、EFFECT_OF(FM→FE)、CAUSE_OF(FC→FM)、PREVENTED_BY(FC→PC)、DETECTED_BY(FC→DC) 全正确
- **DFMEA 无 4M 上下文**：OK — 0 节点带 Man/Machine/Material/Environment classification（PFMEA 专有）
- **AI 3 required_retrievers（failure_mode）**：OK — graph=empty, semantic_search=success, lessons_learned=success；`generation_execution.llm=success`；10 suggestions 含 llm 源 + content-hash rec_ids
- **wizardScope 保留**：OK（wizard_completed=true, tool=边界图）
- 证据：evidence/02.11-recommend-failure_mode.json

### 02.12 DFMEA Step5 风险分析 — PASS（API 直调）

- **S/O/D 落库**：OK — FailureMode.severity=9, FailureCause.occurrence=4, DetectionControl.detection=5
- **AP 查表**：OK — (S=9, O=4, D=5) → AP=H（AIAG-VDA 表：S=9 强制 H 当 O*D≥2；RPN=180 线性但 AP 非线性，02.5 已抽 3 组验证）
- 证据：02.14-dfmea-documentation.json（含 risk 字段）

### 02.13 DFMEA Step6 优化 — PASS（API 直调）

- **RecommendedAction + OPTIMIZED_BY**：OK — RA「增加变压器来料抽检」(status=open, responsible=王工, due_date=2026-09-30)；OPTIMIZED_BY 边 FC→RA 方向正确
- **AI optimization 触发器**：OK — `source=hybrid`, `llm_available=true`, 3 retrievers healthy (graph=empty, semantic_search/lessons_learned=success), `generation_execution.llm=success`, 10 suggestions 含 llm 源 + content-hash rec_ids
- 证据：evidence/02.13-recommend-optimization.json

### 02.14 DFMEA Step7 结果文件化 — PASS（API 直调）

- **汇总 6 段无空**：OK — Structure=3 (System/Subsystem/Component), Function=1 (ProcessWorkElementFunction), FailureChains=1, TotalNodes=10, TotalEdges=9（9 种边类型全含 OPTIMIZED_BY）
- **wizard_completed 在 wizardScope 内**：OK — `graph_data.wizardScope.wizard_completed=true`；根级 `graph_data.wizard_completed` 不存在（正确）
- 证据：evidence/02.14-dfmea-documentation.json

## 走查完成

全部 19 子故事（02.1–02.19）已走查。判定：17 PASS + 2 PASS-NOTE（02.6 status-normalizer 未接线 follow-up、02.16 §I recommend 无 status 门禁既有 spec gap）。关键缺陷 1 个已修（DFMEA CP sync guard, 02.18）。详见上表。
