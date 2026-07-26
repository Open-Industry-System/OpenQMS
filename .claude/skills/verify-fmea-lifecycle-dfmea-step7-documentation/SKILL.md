---
name: verify-fmea-lifecycle-dfmea-step7-documentation
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.14（DFMEA Step7 结果文件化：汇总评审 + 完成 + wizardScope.wizard_completed=true + 跳转编辑器）end-to-end — e.g. "验收 02.14" / "走查 DFMEA Step7" / "verify dfmea-step7-documentation".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.14-dfmea-step7-documentation.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-dfmea-step7-documentation

## Overview

本子 skill 走查 US-E2E-02.14：DFMEA 向导 Step7 汇总评审 + 完成 + 跳编辑器。**与 02.7 PFMEA 完全同契约**，仅 fmea_type 不同。

核心验收点：

1. **`wizard_completed` 落库位置**：`graph_data.wizardScope.wizard_completed = true`（**在 wizardScope 内**）。
2. **汇总视图无空段**：5T 范围 / 结构树 / 功能树 / 失效链 / 风险表 / 优化行动 6 段均非空。
3. **Step7 门禁 = 所有 AP=H/M 已评估**：
   - 所有 AP=H/M 的行，要么有 RecommendedAction（status=completed），要么有 `FailureCause.control_sufficiency_reason`（H）或 `risk_acceptance_reason`（M）非空；
   - **S=9-10 且 AP=H/M 时**：`FailureCause.management_review_evidence` 必须非空。
4. **审计**：UPDATE（含 wizard_completed=true）。
5. **跳转编辑器**：URL 变 `/fmea/{id}`，状态仍 DRAFT。

## When to Use

**用**：用户说「验收 02.14」「走查 DFMEA Step7」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **AI_REQUIRED=false**。
3. **02.8–02.13 全部就绪**。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 评审汇总 + 点完成 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| Step7 汇总 Card | `renderStep6`（`DFMEAWizardPage.tsx`） | 显示 structCount/funcCount/fmCount/nodes/edges |
| 「完成」按钮 | `t('wizard.page.finish')`（`DFMEAWizardPage.tsx`） | 触发 wizard_completed=true + 跳转 |
| 「上一步」 | `t('wizard.page.prevStep')` | 返回 Step6 |
| completionWarning | `t('wizard.page.completionWarning')` | 各 Step 未完成警告 |

## 走查剧本

### A. 进入 Step7

1. **做**：engineer 登录 → 打开 02.8–02.13 已完成的 DFMEA → 向导 Step7。
   - **期望**：汇总 Card 渲染，显示 structCount/funcCount/fmCount/totalNodes/totalEdges。
   - **断言**：各计数 > 0。
   - **落库**：无。

### B. 各段非空 + 与后端一致

2. **做**：核对 UI 各计数 == `GET /api/fmea/{id}` 回读的 `graph_data.nodes.length` / `edges.length`。
   - **若某段为 0 但仍可完成** → FAIL。

### C. AP=H/M 评估门禁 + S=9-10 management_review_evidence

3. **做**：留一条 AP=H 未评估 → 尝试完成，期望拦截；留 S=9-10 且 AP=H/M 的 management_review_evidence 空 → 期望拦截。
   - **若可完成** → FAIL。
   - **清理**：补齐后再继续。

### D. 点完成 + wizard_completed 落库（关键）

4. **做**：点「完成」。
   - **期望**：跳 `/fmea/{id}`；状态 DRAFT。
   - **断言**：`GET /api/fmea/{id}`：
     - `graph_data.wizardScope.wizard_completed == true`；
     - **不**在 `graph_data.wizard_completed`（根级）写；
     - `status == "draft"`。
   - **落库**：1 条 UPDATE 审计（含 wizard_completed=true）。

## 判定汇总

| 检查点 | 通过条件 |
|---|---|
| 汇总 6 段无空 | 各计数 > 0 |
| wizard_completed 在 wizardScope 内 | 不在根级 |
| AP=H/M 评估门禁 | 拦截 |
| S=9-10 management_review_evidence 门禁 | 拦截 |
| 跳转编辑器 + status=draft | URL 正确 |
| UPDATE 审计 | 含 wizard_completed |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过 |
| **FAIL** | wizard_completed 写根级；空段未拦截；AP 未评估可完成；S=9-10 留空可完成；未审计 |
| **MISSING** | 汇总 Card 不渲染 |
| **BLOCKED** | — |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.14 DFMEA Step7 结果文件化 — <PASS|PASS-NOTE|FAIL|MISSING>

- 汇总 6 段无空：<OK|FAIL>
- wizard_completed 在 wizardScope 内：<OK|FAIL>
- AP=H/M 评估门禁：<OK|FAIL>
- S=9-10 management_review_evidence 门禁：<OK|FAIL>
- 跳转编辑器 + status=draft：<OK|FAIL>
- UPDATE 审计：<OK|FAIL>
- 截图：screenshots/02.14-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.14-dfmea-step7-documentation.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
