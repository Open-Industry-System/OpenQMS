---
name: verify-fmea-lifecycle-pfmea-step7-documentation
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.7（PFMEA Step7 结果文件化：汇总评审 + 点完成 + wizardScope.wizard_completed=true 落库 + 跳转编辑器）end-to-end — e.g. "验收 02.7" / "走查 PFMEA Step7" / "verify pfmea-step7-documentation".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.7-pfmea-step7-documentation.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-pfmea-step7-documentation

## Overview

本子 skill 走查 US-E2E-02.7：PFMEA 向导 Step7 汇总评审全部 6 步内容，确认所有 AP=H/M 已评估后点「完成」，写 `wizardScope.wizard_completed=true`，跳转编辑器。

核心验收点：

1. **`wizard_completed` 落库位置**：`graph_data.wizardScope.wizard_completed = true`（**在 wizardScope 内，非 graph_data 根级**，`PFMEAWizardPage.tsx:160`）。
2. **汇总视图无空段**：5T 范围 / 结构树 / 功能树 / 失效链 / 风险表 / 优化行动 6 段均有内容。
3. **Step7 门禁 = 所有 AP=H/M 已评估**：
   - 所有 AP=H/M 的行，要么有 RecommendedAction（status=completed，且 action_taken/completion_date/revised_* 非空），要么有 `FailureCause.control_sufficiency_reason`（H）或 `risk_acceptance_reason`（M）非空；
   - **S=9-10 且 AP=H/M 时**：`FailureCause.management_review_evidence` 必须非空。
4. **审计**：保存写 `action=UPDATE`（Outbox `fmea.updated`，含 wizardScope.wizard_completed=true）。
5. **跳转编辑器**：完成后前端跳 `/fmea/{id}`，状态仍 DRAFT。

## When to Use

**用**：用户说「验收 02.7」「走查 PFMEA Step7」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **AI_REQUIRED=false**。
3. **02.1–02.6 全部就绪**：Step1-Step6 数据已落库。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 评审汇总 + 点完成 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| Step7 汇总 Card | `renderStep6`（`PFMEAWizardPage.tsx:656-669`） | 显示 structCount/funcCount/fmCount/nodes/edges |
| 「完成」按钮 | `t('wizard.page.finish')`（`PFMEAWizardPage.tsx:733`） | 触发 wizard_completed=true + 跳转 |
| 「上一步」 | `t('wizard.page.prevStep')` | 返回 Step6 |
| completionWarning | `t('wizard.page.completionWarning')` | 各 Step 未完成警告 |

## 走查剧本

### A. 进入 Step7

1. **做**：engineer 登录 → 打开 02.1–02.6 已完成的 PFMEA → 向导 Step7。
   - **期望**：汇总 Card 渲染，显示 6 项统计（结构节点数 / 功能节点数 / 失效链数 / 总节点数 / 总边数）。
   - **断言**：UI 各计数 > 0（无空段）。
   - **落库**：无。

### B. 各段非空断言

2. **做**：逐项核对汇总 Card 显示：
   - 结构节点数 ≥ 3（ProcessItem/ProcessStep/ProcessWorkElement）；
   - 功能节点数 ≥ 3（每个结构节点 1 个功能）；
   - 失效链数 ≥ 1；
   - 总节点数、总边数 与 `GET /api/fmea/{id}` 回读的 `graph_data.nodes.length` / `edges.length` 一致。
   - **期望**：所有计数与后端一致；无 0 段。
   - **若某段为 0 但「完成」按钮仍可点** → FAIL（前序空段未拦截）。

### C. AP=H/M 评估门禁

3. **做**：在 Step6 留一条 AP=H 失效链**未评估**（无 RecommendedAction、无 control_sufficiency_reason）→ 跳到 Step7 → 尝试点「完成」。
   - **期望**：「完成」按钮 disabled（`canFinish == false`，`PFMEAWizardPage.tsx:203-208`），或点后校验拦截。
   - **断言**：完成按钮不可点 / 点击后向导警告可见。
   - **若仍可完成** → FAIL（Step7 门禁未实现）。
   - **清理**：回 Step6 把该行评估补全（RecommendedAction completed 或 control_sufficiency_reason 非空）。

### D. S=9-10 且 AP=H/M → management_review_evidence

4. **做**：选一条 S=9-10 且 AP=H/M 失效链，评估已做（如 RecommendedAction completed），但 `management_review_evidence` 留空 → 跳 Step7 点完成。
   - **期望**：门禁拦截（management_review_evidence 必填）。
   - **若可完成** → FAIL。
   - **清理**：补 `management_review_evidence` 非空。

### E. 点完成 + wizard_completed 落库（关键）

5. **做**：所有评估补齐后，点「完成」。
   - **期望**：前端跳转 `/fmea/{id}` 编辑器；状态仍 DRAFT。
   - **断言（回读，关键）**：`GET /api/fmea/{id}`：
     - `graph_data.wizardScope.wizard_completed == true`；
     - **不**在 `graph_data.wizard_completed`（根级）写——若在根级 → FAIL（字段位置错）；
     - `status == "draft"`；
     - URL 已跳编辑器。
   - **落库（审计）**：1 条 `action=UPDATE`，`operated_by=engineer`，`changed_fields` 含 wizardScope.wizard_completed=true；Outbox `fmea.updated`。

### F. 提交评审入口可用

6. **做**：编辑器内查「提交评审」按钮是否可见（为 02.19 铺垫）。
   - **期望**：按钮可见可点（wizard_completed=true 满足后端门禁）。
   - **断言**：按钮存在。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 汇总 6 段无空 | 各计数 > 0 | PASS |
| 与后端一致 | UI 计数 == 后端 nodes/edges.length | PASS |
| wizard_completed 在 wizardScope 内 | 不在 graph_data 根级 | PASS |
| AP=H/M 评估门禁 | 未评估不可完成 | PASS（若可完成 → FAIL） |
| S=9-10 management_review_evidence | 留空不可完成 | PASS（若可完成 → FAIL） |
| 跳转编辑器 | URL 变 /fmea/{id}，status=draft | PASS |
| UPDATE 审计 | 含 wizard_completed=true | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过条件满足 |
| **FAIL** | wizard_completed 写在 graph_data 根级；前序空段未拦截；AP 未评估即可通过；S=9-10 management_review_evidence 为空可完成；未审计 |
| **MISSING** | 汇总 Card 不渲染；「完成」按钮不存在 |
| **BLOCKED** | — |

## 报告片段

```markdown
### 02.7 PFMEA Step7 结果文件化 — <PASS|PASS-NOTE|FAIL|MISSING>

- 汇总 6 段无空：<OK|FAIL>
- wizard_completed 在 wizardScope 内：<OK|FAIL>
- AP=H/M 评估门禁：<OK|FAIL>
- S=9-10 management_review_evidence 门禁：<OK|FAIL>
- 跳转编辑器 + status=draft：<OK|FAIL>
- UPDATE 审计：<OK|FAIL>
- 截图：screenshots/02.7-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.7-pfmea-step7-documentation.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
