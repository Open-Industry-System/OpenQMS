---
name: verify-fmea-lifecycle-approval-cycle
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.19（审核闭环：提交 + 审批 + 驳回 + 返工 + 已批准返工；含 wizard_completed 后端 422 门禁、非空 reason 422、可编辑状态 409、APPROVED→REWORK 保留 approved_by/at）end-to-end — e.g. "验收 02.19" / "走查 FMEA 审批闭环" / "verify approval-cycle". Symptoms include needing to confirm 审批权限矩阵（EDIT vs APPROVE）、DRAFT 不可直接 APPROVED、驳回必须带 reason、可编辑状态门禁。
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.19-approval-cycle.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-approval-cycle

## Overview

本子 skill 走查 US-E2E-02.19：FMEA 审批闭环——engineer 提交评审（DRAFT/REWORK→IN_REVIEW），manager 审批通过（IN_REVIEW→APPROVED）或驳回（IN_REVIEW→REWORK，必须带非空 reason），engineer 重提（REWORK→IN_REVIEW），manager 已批准返工（APPROVED→REWORK）。

核心验收点（**多项为已知实现缺口 → FAIL 预期**）：

| 流转 | 权限 | 说明 | 当前实现 |
|---|---|---|---|
| DRAFT/REWORK → IN_REVIEW | EDIT | 提交评审；**后端强制校验** `wizardScope.wizard_completed=true`，缺失/false → **422** | 状态机已支持；**权限未显式校验 EDIT；wizard_completed 未校验 → FAIL** |
| IN_REVIEW → APPROVED | APPROVE | 置 approved_by/at + approve 快照 + PFMEA CP sync | **PASS**（`require_approve_permission` 已查 `target_status=="approved"`） |
| IN_REVIEW → REWORK | APPROVE | **必须携带非空 reason**，否则 **422** | **权限未检查 APPROVE；reason 未校验 → FAIL** |
| REWORK → IN_REVIEW | EDIT | 重提；后端强制校验 wizard_completed → **422** | **EDIT 未校验；wizard_completed 未校验 → FAIL** |
| APPROVED → REWORK | APPROVE | 已批准返工；**approved_by/approved_at 保留历史** | **APPROVE 未校验 → FAIL**；保留语义需验证 |
| 不可跳步 | — | DRAFT 不可直接 APPROVED | **PASS**（状态机 `fmea_state.py:18` 已阻止） |
| 可编辑图 | EDIT | 仅 DRAFT、REWORK；IN_REVIEW/APPROVED 的 PUT 必须 **409** | **未实现 → FAIL** |

E2E 必须**直接调用** `POST /api/fmea/{id}/transition`（绕过前端）验证 422/409 门禁在后端强制执行。

## When to Use

**用**：用户说「验收 02.19」「走查 FMEA 审批闭环」「verify approval-cycle」等。
**不用**：版本快照/CP 联动字段级（02.18）；APPROVED 后的归档/二次审批深度（另立）。

## 前置

1. **epic 级前置**：见 `.claude/skills/verify-fmea-lifecycle/SKILL.md`「前置」节。
2. **无需 LLM 凭证**（AI_REQUIRED=false）。
3. **多个 FMEA 就绪**（避免顺序耦合，每个用例独立文档）：
   - `PFMEA-E2E-APPROVE-001`：向导完成（wizard_completed=true），DRAFT。
   - `PFMEA-E2E-INCOMPLETE-001`：向导未完成（wizard_completed=false 或缺失），DRAFT。
   - `PFMEA-E2E-REJECT-001`：向导完成，DRAFT。
   - `PFMEA-E2E-REWORK-001`：向导完成，DRAFT。
4. **engineer + manager + admin 账号**：从 `/api/e2e/seed-state` 拿密码；准备好三组 token。

## 账号 × 权限

| 账号 | 角色 | 能 | 不能 |
|---|---|---|---|
| engineer | quality_engineer (L2) | DRAFT/REWORK→IN_REVIEW（EDIT） | IN_REVIEW→APPROVED / IN_REVIEW→REWORK / APPROVED→REWORK |
| manager | manager (L3-L4) | IN_REVIEW→APPROVED、IN_REVIEW→REWORK、APPROVED→REWORK（APPROVE）；DRAFT/REWORK→IN_REVIEW（EDIT） | — |
| admin | admin (L5) | 全部 | — |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| 「提交评审」 | 按钮文本（i18n） | 编辑器顶部 |
| 「审批通过」/「驳回」 | 按钮文本 | 审批对话框 |
| 驳回 reason 输入 | Ant TextArea，无 data-e2e | 审批对话框内 |

后端契约断言以 API 直调为主（admin token 调 `POST /api/fmea/{id}/transition`）；UI 仅作辅助。

## 走查剧本

### A. 提交评审（wizard_completed=true → 通过）

1. **做**：engineer token 直调 `POST http://localhost:8001/api/fmea/{PFMEA-E2E-APPROVE-001}/transition` body `{"target_status": "in_review"}`。
   - **期望**：200，status → IN_REVIEW。
   - **断言**：
     - 响应 `status == "in_review"`；
     - `GET /api/fmea/{id}` 回读 status 一致；
     - 审计 `action=TRANSITION`，`old_status=draft`，`new_status=in_review`，`operated_by=engineer`；
     - 生成 `change_type="submit"` FMEAVersion（详见 02.18，本故事仅核审计存在）。
   - **落库**：1 TRANSITION + 1 fmea_versions/CREATE。

### B. wizard_completed=false → 422（关键，FAIL 预期）

2. **做**：engineer token 直调 `POST /api/fmea/{PFMEA-E2E-INCOMPLETE-001}/transition` body `{"target_status": "in_review"}`（该文档 `wizardScope.wizard_completed` 为 false 或缺失）。
   - **期望**：**422 Unprocessable Entity**，detail 含「向导未完成，不能提交评审」或类似明确文案。
   - **断言**：响应 status_code == 422；detail 非空且指向 wizard_completed。
     - **当前预期 FAIL**：`api/fmea.py` 未实现 wizard_completed 校验 → 返回 200 或 400 → 判 FAIL。
   - **落库**：失败请求不应写 TRANSITION 审计（若写了 → 额外 FAIL）。

### C. 审批通过（manager，APPROVE 权限 PASS 路径）

3. **做**：manager token 直调 `POST /api/fmea/{PFMEA-E2E-APPROVE-001}/transition` body `{"target_status": "approved"}`。
   - **期望**：200，status → APPROVED；approved_by=manager user_id；approved_at 非空。
   - **断言**：
     - `GET /api/fmea/{id}` 回读 `status == "approved"`、`approved_by == manager_user_id`、`approved_at` 时间戳合理；
     - 审计 `action=TRANSITION`，`new_status=approved`，`operated_by=manager`；
     - 生成 `change_type="approve"` FMEAVersion；
     - PFMEA 触发 CP sync_pending（详见 02.18，本故事仅核 FMEA 状态）。
   - **落库**：1 TRANSITION + 1 fmea_versions/CREATE + CP 侧（见 02.18）。

### D. engineer 试图审批 → 应被拒（权限矩阵）

4. **做**：另起一文档到 IN_REVIEW；engineer token 直调 `POST /api/fmea/{id}/transition` body `{"target_status": "approved"}`。
   - **期望**：403 Forbidden（engineer 无 APPROVE 权限）。
   - **断言**：status_code == 403。
   - **当前预期**：PASS（`require_approve_permission` 已对 `target_status=="approved"` 检查）。

### E. 驳回必须带非空 reason（FAIL 预期）

5. **做**：manager token 直调 `POST /api/fmea/{PFMEA-E2E-REJECT-001}/transition`（先 engineer 提交）→ manager 驳回，body `{"target_status": "rework"}`，**不传 reason**。
   - **期望**：**422 Unprocessable Entity**，detail 含「驳回必须携带理由」。
   - **断言**：status_code == 422。
     - **当前预期 FAIL**：`TransitionRequest` schema 未强制 reason；后端未校验 → 返回 200 → 判 FAIL。
   - 再用 `{"target_status": "rework", "reason": ""}` 与 `{"target_status": "rework", "reason": "   "}`（空白）重试，期望均 422。

### F. 驳回（带 reason）→ REWORK；engineer 无 APPROVE 权限

6. **做**：manager 用 `{"target_status": "rework", "reason": "失效链不完整，需补 FC"}` 驳回。
   - **期望**：200，status → REWORK；审计 `changed_fields` 含 reason。
   - **断言**：
     - `GET /api/fmea/{id}` 回读 `status == "rework"`；
     - 审计 1 条 TRANSITION，`new_status=rework`，`operated_by=manager`，`changed_fields.reason` 非空。
   - **再做**：engineer token 直调 `POST /api/fmea/{id}/transition` body `{"target_status": "rework", "reason": "x"}`（engineer 试图驳回）。
   - **期望**：**403**（engineer 无 APPROVE）。
   - **当前预期 FAIL**：`require_approve_permission` 仅查 `target_status=="approved"`，engineer 可驳回 → 判 FAIL。

### G. APPROVED→REWORK 保留 approved_by/at（FAIL 预期）

7. **做**：在已 APPROVED 的 `PFMEA-E2E-APPROVE-001` 上，manager 直调 `POST /api/fmea/{id}/transition` body `{"target_status": "rework", "reason": "客户反馈需补充特殊特性"}`。
   - **期望**：200，status → REWORK；**`approved_by`/`approved_at` 保留历史**（不清空）。
   - **断言**：`GET /api/fmea/{id}` 回读 `status == "rework"` 且 `approved_by` 仍为 manager、`approved_at` 仍非空。
     - 若被清空 → FAIL。
   - **再做**：engineer 试图 `POST .../transition` `{"target_status": "rework", "reason": "x"}` → 期望 **403**（engineer 无 APPROVE）。
   - **当前预期 FAIL**：APPROVE 权限未对 REWORK 检查。

### H. 可编辑状态门禁（409，FAIL 预期）

8. **做**：把文档推到 IN_REVIEW；engineer token 直调 `PUT /api/fmea/{id}` body 含新 `graph_data`。
   - **期望**：**409 Conflict**（IN_REVIEW 不可编辑）。
   - **断言**：status_code == 409。
   - 再把文档推到 APPROVED，重复 PUT → 期望 409。
   - **当前预期 FAIL**：`update_fmea` 未做状态校验 → 返回 200 → 判 FAIL。

### I. 不可跳步（PASS 路径）

9. **做**：engineer token 直调 `POST /api/fmea/{PFMEA-E2E-REWORK-001}/transition` body `{"target_status": "approved"}`（DRAFT → APPROVED 直跳）。
   - **期望**：**400 Bad Request**（状态机拒绝）。
   - **断言**：status_code == 400；detail 提示非法流转。
   - **当前预期**：PASS（`fmea_state.py:18` `DRAFT: [IN_REVIEW, ARCHIVED]` 已阻止）。

### J. 重提（REWORK→IN_REVIEW 同样校验 wizard_completed）

10. **做**：在 REWORK 状态文档（`wizard_completed=false`）上 engineer 直调 `POST .../transition` `{"target_status": "in_review"}`。
    - **期望**：**422**（同 B）。
    - **当前预期 FAIL**：wizard_completed 未校验。
    - 把 `wizard_completed` 置 true 后重提 → 期望 200。

### K. 收尾

11. **做**：admin 把测试文档恢复 DRAFT；登出。
    - **落库**：恢复产生的审计单独记录。

## 判定汇总

| 用例 | 期望 | 当前预期 |
|---|---|---|
| A. 提交（wizard_completed=true） | 200 + TRANSITION + submit 快照 | PASS |
| B. wizard_completed=false → 422 | 422 + 明确 detail | **FAIL** |
| C. manager 审批 | 200 + approved_by/at + approve 快照 | PASS |
| D. engineer 审批 → 403 | 403 | PASS |
| E. 驳回无 reason → 422 | 422（空/空白也 422） | **FAIL** |
| F. engineer 驳回 → 403 | 403 | **FAIL** |
| G. APPROVED→REWORK 保留 approved_by/at | 字段不清空 | **FAIL**（保留语义）+ **FAIL**（权限） |
| H. IN_REVIEW/APPROVED PUT → 409 | 409 | **FAIL** |
| I. DRAFT→APPROVED 跳步 | 400 | PASS |
| J. REWORK→IN_REVIEW wizard_completed=false → 422 | 422 | **FAIL** |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 权限矩阵 + wizard_completed + reason + 409 全满足 |
| **PASS-NOTE** | 通过但有备注 |
| **FAIL** | 权限矩阵缺任一项；wizard_completed 后端未校验或返回非 422；reason 可空；IN_REVIEW/APPROVED 可编辑；APPROVED→REWORK 清空 approved_by/at；状态跳步 |
| **MISSING** | 提交评审按钮不存在；审批对话框不存在 |
| **BLOCKED** | —（AI_REQUIRED=false） |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.19 审核闭环 — <PASS|PASS-NOTE|FAIL|MISSING>

| 用例 | 期望 | 实际 | 标签 |
|---|---|---|---|
| A 提交（wizard_completed=true） | 200 + TRANSITION | <...> | <PASS|FAIL> |
| B wizard_completed=false → 422 | 422 | <...> | <PASS|FAIL> |
| C manager 审批 | 200 + approved_by/at | <...> | <PASS|FAIL> |
| D engineer 审批 → 403 | 403 | <...> | <PASS|FAIL> |
| E 驳回无 reason → 422 | 422 | <...> | <PASS|FAIL> |
| F engineer 驳回 → 403 | 403 | <...> | <PASS|FAIL> |
| G APPROVED→REWORK 保留 approved_by/at | 保留 | <...> | <PASS|FAIL> |
| H IN_REVIEW/APPROVED PUT → 409 | 409 | <...> | <PASS|FAIL> |
| I DRAFT→APPROVED 跳步 → 400 | 400 | <...> | <PASS|FAIL> |
| J REWORK→IN_REVIEW wizard_completed=false → 422 | 422 | <...> | <PASS|FAIL> |

- 截图：screenshots/02.19-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.19-approval-cycle.md` 顶部「状态: 定稿 vX（日期）」。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
