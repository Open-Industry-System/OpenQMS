---
name: verify-fmea-lifecycle-dfmea-step6-optimization
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.13（DFMEA Step6 优化：RecommendedAction + FailureCause 风险处置字段 + canonical 状态枚举 + OPTIMIZED_BY 边 + AI optimization trigger）end-to-end — e.g. "验收 02.13" / "走查 DFMEA Step6" / "verify dfmea-step6-optimization".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.13-dfmea-step6-optimization.md
> 故事版本：定稿 v4（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-dfmea-step6-optimization

## Overview

本子 skill 走查 US-E2E-02.13：在 DFMEA 向导 Step6 为高风险失效链创建优化行动（RecommendedAction）或记录风险处置理由（FailureCause 字段）。**与 02.6 PFMEA 完全同契约**，仅 fmea_type 不同。

核心验收点：

1. **RecommendedAction 数据模型**：`name`/`responsible`/`due_date`/`status`/`action_taken`/`completion_date`/`revised_*`。
2. **Canonical 状态枚举**：`{open, in_progress, completed, not_executed}`；legacy 映射 `undecided→open, planned→in_progress, done→completed, notExecuted→not_executed, closed→completed`（**当前前端枚举未迁移 → FAIL**）。
3. **FailureCause 风险处置字段**（新增，**MISSING 预期**）：`control_sufficiency_reason`/`risk_acceptance_reason`/`management_review_evidence`。
4. **`OPTIMIZED_BY` 边**：FC/FM → RecommendedAction。
5. **状态门禁**：completed 必填 5 字段；not_executed 必填理由；S=9-10 且 AP=H/M 必填 management_review_evidence。
6. **AI 触发器**：`optimization`，写入 name；3 required_retrievers 可观测。

## When to Use

**用**：用户说「验收 02.13」「走查 DFMEA Step6」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **LLM 凭证齐**（AI_REQUIRED=true）：缺 → BLOCKED。
3. **02.12 已就绪**：风险分析已落库。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入 RecommendedAction + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| Step6 视图 | `renderStep5`（`DFMEAWizardPage.tsx`） | 优化行动表 |
| 措施（name） TextArea | placeholder=`wizard.optimization.measurePlaceholder`（`DFMEAWizardPage.tsx`） | RecommendedAction.name |
| 责任人 Input | placeholder=`wizard.optimization.responsiblePlaceholder` | responsible |
| 计划完成日期 DatePicker | Ant DatePicker | due_date |
| 状态 Select | 选项 open/undecided/planned/done/notExecuted（**当前 legacy，预期 FAIL**） | status |
| 实际措施 TextArea | action_taken | — |
| 实际完成日期 DatePicker | completion_date | — |
| S'/O'/D' InputNumber | revised_* | — |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step6

1. **做**：engineer 登录 → 打开 02.12 已完成的 DFMEA → 向导 Step6。
   - **期望**：AP=H 失效链列表渲染。
   - **落库**：无。

### B. 创建 RecommendedAction + 状态枚举断言

2. **做**：录入措施/责任人/计划完成日期；status 选 `open`。
   - **断言**：status 选项 ∈ {open, in_progress, completed, not_executed}（**canonical**）。
   - **当前预期 FAIL**：UI 选项为 legacy {open, undecided, planned, done, notExecuted}。

### C. AI 触发（optimization）+ 写 name 非 action_taken

3. **做**：触发 AI `optimization` → 抓 `POST /api/fmea/{id}/recommend` 响应。
   - **期望**：响应含 `suggestions` + `source_executions` + `context_execution` + `generation_execution`。
   - **断言（AI 契约，关键）**：
     - `source_executions` 含 3 条目：`graph` / `semantic_search` / `lessons_learned`（required_retrievers；`rule` **不是** required_retriever），每条 `status ∈ {success, empty, unavailable, error}`；健康环境 E2E 下每条必须为 `success | empty`，否则 FAIL；
     - `context_execution.current_product_structure ∈ {assembled, unavailable}`；
     - `generation_execution.llm ∈ {success, unavailable, error}`；
     - 每条 suggestion 的 `source ∈ {rule, graph, semantic_search, lessons_learned, llm}`；
     - 上述任一字段缺失 → FAIL/MISSING。
   - **关键**：AI 推荐采纳后写入 `RecommendedAction.name`，**不写入 `action_taken`**。
     - 若写入 action_taken → FAIL。
   - **当前预期 FAIL/MISSING**：RecommendResponse 未扩展 `source_executions`/`context_execution`/`generation_execution`；RecommendationService 未接 semantic_search/lessons_learned；SuggestionItem 未扩展 `source`/`recommendation_id`。

### D. OPTIMIZED_BY 边 + FailureCause 风险处置字段

4. **做**：保存 → `GET /api/fmea/{id}`。
   - **断言**：
     - `graph_data.edges` 含 `<FC/FM> ─OPTIMIZED_BY→ RecommendedAction`；
     - FailureCause 三字段（control_sufficiency_reason/risk_acceptance_reason/management_review_evidence）落库（**当前预期 MISSING**）；
     - 若无 FC 的 placeholder 行，回退到 `FailureMode.*_reason`。
   - **落库**：1 条 UPDATE 审计。

### E. 状态门禁

5. **做**：completed 留空 5 字段任一 → 保存期望拦截；not_executed 留空理由 → 保存期望拦截；S=9-10 且 AP=H/M 留空 management_review_evidence → 期望拦截。
   - **当前预期**：FAIL（若未拦截）。

### F. 推进 Step7

6. **做**：补齐字段 → 点「下一步」。
   - **落库**：1 条 UPDATE 审计。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| RecommendedAction 字段齐 | 全字段 | PASS |
| Canonical 状态枚举 | 4 态 | **FAIL**（legacy） |
| OPTIMIZED_BY 边 | FC/FM → RA | PASS |
| FailureCause 风险处置字段 | 三字段落库 | **MISSING** |
| completed/not_executed 门禁 | 拦截 | FAIL（若未拦截） |
| S=9-10 management_review_evidence | 非空 | FAIL（若未拦截） |
| AI 3 required_retrievers | 可观测 | **FAIL/MISSING** |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过 |
| **FAIL** | legacy 枚举未迁移；门禁未拦截；AI 写入 action_taken；OPTIMIZED_BY 边反 |
| **MISSING** | FailureCause 三字段不在 schema |
| **BLOCKED** | LLM 凭证缺 |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.13 DFMEA Step6 优化 — <PASS|PASS-NOTE|FAIL|MISSING>

- RecommendedAction 字段齐：<OK|FAIL>
- Canonical 状态枚举：<OK|FAIL legacy>
- OPTIMIZED_BY 边：<OK|FAIL>
- FailureCause 风险处置字段：<OK|MISSING>
- 状态门禁：<OK|FAIL>
- AI 3 required_retrievers：<OK|FAIL|MISSING>
- 截图：screenshots/02.13-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v4（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.13-dfmea-step6-optimization.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
