---
name: verify-fmea-lifecycle-pfmea-step6-optimization
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.6（PFMEA Step6 优化：RecommendedAction + FailureCause 风险处置字段 + canonical 状态枚举 + OPTIMIZED_BY 边 + AI optimization trigger）end-to-end — e.g. "验收 02.6" / "走查 PFMEA Step6" / "verify pfmea-step6-optimization".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.6-pfmea-step6-optimization.md
> 故事版本：定稿 v4（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-pfmea-step6-optimization

## Overview

本子 skill 走查 US-E2E-02.6：在 PFMEA 向导 Step6 为高风险失效链创建优化行动（RecommendedAction）或记录风险处置理由（FailureCause 字段）。

核心验收点（含多个 spec 已定缺口 → FAIL 预期）：

1. **RecommendedAction 数据模型**：`name`（计划/推荐措施，AI 写入此处）/ `responsible` / `due_date` / `status` / `action_taken` / `completion_date` / `revised_severity` / `revised_occurrence` / `revised_detection` / `revised_ap`。
2. **Canonical 状态枚举**：`{open, in_progress, completed, not_executed}`（含第 4 态）；legacy 映射 `undecided→open, planned→in_progress, done→completed, notExecuted→not_executed, closed→completed`（**当前前端枚举为 `{undecided, planned, done, notExecuted}` 未迁移 → FAIL**）。
3. **FailureCause 风险处置字段**（**新增，需 schema 扩展 → MISSING 预期**）：`control_sufficiency_reason`（H 不行动）/ `risk_acceptance_reason`（M 不行动）/ `management_review_evidence`（S=9-10 且 AP=H/M 必须非空）。
4. **`OPTIMIZED_BY` 边**：FC/FM → RecommendedAction。
5. **状态门禁**：
   - `status=not_executed` → 必须 `FailureCause.control_sufficiency_reason` 或 `risk_acceptance_reason` 非空；
   - `status=completed` → 必须 `action_taken`/`completion_date`/`revised_occurrence`/`revised_detection`/`revised_ap` 非空（`revised_severity` 可留空若 S 不变）。
6. **AIAG-VDA Step6 行动触发**：H=行动或控制充分理由；M=行动或风险接受理由；L=行动可选；S=9-10 且 AP=H/M → `management_review_evidence` 非空（纳入 Step7 门禁）。
7. **AI 触发器**：`optimization`，写入 `name`（**不写入 action_taken**）；3 required_retrievers 可观测。

## When to Use

**用**：用户说「验收 02.6」「走查 PFMEA Step6」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **LLM 凭证齐**（AI_REQUIRED=true）：缺 → BLOCKED。
3. **02.5 已就绪**：风险分析已落库，AP 已计算。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入 RecommendedAction + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| Step6 视图 | `renderStep5`（`PFMEAWizardPage.tsx:538`） | 优化行动表 |
| 措施（name） TextArea | placeholder=`wizard.optimization.measurePlaceholder`（`PFMEAWizardPage.tsx:598`） | RecommendedAction.name |
| 责任人 Input | placeholder=`wizard.optimization.responsiblePlaceholder` | responsible |
| 计划完成日期 DatePicker | Ant DatePicker | due_date |
| 状态 Select | 选项 open/undecided/planned/done/notExecuted（**当前 legacy，预期 FAIL**） | status |
| 实际措施 TextArea | action_taken | — |
| 实际完成日期 DatePicker | completion_date | — |
| S'/O'/D' InputNumber | revised_* | — |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step6

1. **做**：engineer 登录 → 打开 02.5 已完成的 PFMEA → 向导 Step6。
   - **期望**：显示 AP=H 的高风险失效链列表（`highRiskRows`）；若无 AP=H 显示「无优化项」。
   - **断言**：UI 至少 1 条 AP=H 失效链。
   - **落库**：无。

### B. 创建 RecommendedAction + 字段断言

2. **做**：在某 AP=H 行录入：
   - 措施（name）=「增加 AOI 复检工位」（**计划/推荐措施**，AI 推荐或手工）；
   - 责任人 =「张工」；
   - 计划完成日期 = 下月末；
   - status = `open`（**canonical 枚举**；若 UI 选项是 `undecided`/`planned`/`done`/`notExecuted` → 现状为 legacy，FAIL）。
   - **期望**：UI 显示已填字段；状态 Select 含 canonical 4 态。
   - **断言**：
     - status 选项 ∈ {open, in_progress, completed, not_executed}；
     - **当前预期 FAIL**：UI 选项为 legacy {open, undecided, planned, done, notExecuted}（`PFMEAWizardPage.tsx:565-571`）。
   - **落库**：尚未保存。

### C. AI 触发（optimization）+ 写 name 非 action_taken

3. **做**：触发 AI `optimization` → 抓 `POST /api/fmea/{id}/recommend` 响应。
   - **期望**：3 required_retrievers + context_execution + generation_execution 可观测。
   - **断言**：同 02.4 §C。
   - **关键**：AI 推荐采纳后写入 `RecommendedAction.name`，**不写入 `action_taken`**。
     - 若写入 action_taken → FAIL。
   - **当前预期 FAIL/MISSING**：同 02.4。

### D. OPTIMIZED_BY 边断言

4. **做**：保存草稿 → `GET /api/fmea/{id}`。
   - **期望**：`graph_data.edges` 含 `<FC 或 FM> ─OPTIMIZED_BY→ RecommendedAction`。
   - **断言**：边方向正确（FC/FM 为 source，RecommendedAction 为 target）。
   - **落库**：1 条 UPDATE 审计。

### E. FailureCause 风险处置字段（MISSING 预期）

5. **做**：选另一条 AP=H 失效链，**不**创建 RecommendedAction，改在该 FC 上填 `control_sufficiency_reason` = 「现有 PC 已覆盖 H 级风险」。
   - **期望**：保存成功；`FailureCause.control_sufficiency_reason` 落库。
   - **断言**：`GET /api/fmea/{id}` 回读该 FC 节点 `control_sufficiency_reason` 非空。
     - **当前预期 MISSING**：schema 未扩展 FailureCause 三字段 → 字段无处存 → FAIL。
   - **同时验证 placeholder 行回退**：若该失效链无 FC（`_null` key 行），允许评估，则回退到 `FailureMode.control_sufficiency_reason`（同一规则）。

### F. 状态门禁（completed + not_executed）

6. **做**（completed）：把某 RecommendedAction status 设为 `completed`，但**留空** `action_taken`/`completion_date`/`revised_occurrence`/`revised_detection`/`revised_ap` 任一项 → 保存。
   - **期望**：门禁拦截或保存时校验失败。
   - **断言**：UI/后端任一拦截（`completed` 必须 5 字段齐，`revised_severity` 可留空）。
   - **若直接保存成功** → FAIL。

7. **做**（not_executed）：把某 RecommendedAction status 设为 `not_executed`，但**留空**对应 FC 的 `control_sufficiency_reason`/`risk_acceptance_reason` → 保存。
   - **期望**：门禁拦截（`not_executed` 必须对应理由非空）。
   - **若直接保存成功** → FAIL。

### G. S=9-10 且 AP=H/M → management_review_evidence 非空

8. **做**：选一条 S=9-10 且 AP=H/M 的失效链，无论选完成行动还是风险接受，期望 `FailureCause.management_review_evidence` 必须非空。
   - **期望**：留空时门禁拦截。
   - **若允许留空** → FAIL（纳入 Step7 门禁）。

### H. 推进 Step7

9. **做**：把 RecommendedAction 各字段填齐 → 保存 → 点「下一步」。
   - **期望**：跳到 Step7 结果文件化。
   - **落库**：1 条 UPDATE 审计。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| RecommendedAction 字段齐 | name/responsible/due_date/status/action_taken/completion_date/revised_* | PASS |
| Canonical 状态枚举 | {open, in_progress, completed, not_executed} | **FAIL**（legacy 未迁移） |
| OPTIMIZED_BY 边 | FC/FM → RA | PASS |
| FailureCause 风险处置字段 | 三字段落库 | **MISSING**（schema 未扩展） |
| completed 门禁 | 5 字段必填 | FAIL（若未拦截） |
| not_executed 门禁 | 理由必填 | FAIL（若未拦截） |
| S=9-10 + AP=H/M → management_review_evidence | 非空 | FAIL（若未拦截） |
| AI 3 required_retrievers | source_executions 可观测 | **FAIL/MISSING** |
| AI 写 name 非 action_taken | 字段正确 | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过条件满足 |
| **FAIL** | 状态用 legacy 未迁移；门禁未拦截；AI 写入 action_taken；OPTIMIZED_BY 边方向反；AI 未查 #2/#3 |
| **MISSING** | FailureCause 三字段不在 schema；canonical 状态枚举未迁移 |
| **BLOCKED** | LLM 凭证缺 |

## 报告片段

```markdown
### 02.6 PFMEA Step6 优化 — <PASS|PASS-NOTE|FAIL|MISSING>

- RecommendedAction 字段齐：<OK|FAIL>
- Canonical 状态枚举：<OK|FAIL legacy>
- OPTIMIZED_BY 边方向：<OK|FAIL>
- FailureCause 风险处置字段：<OK|MISSING>
- completed/not_executed 门禁：<OK|FAIL>
- S=9-10 management_review_evidence：<OK|FAIL>
- AI 3 required_retrievers：<OK|FAIL|MISSING>
- 截图：screenshots/02.6-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v4（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.6-pfmea-step6-optimization.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
