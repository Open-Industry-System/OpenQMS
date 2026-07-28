# 子故事 US-E2E-02.19：审核闭环（提交 + 审批 + 驳回）

**状态**: 定稿 v3（2026-07-25），经代码评审修订（权限矩阵收口 + wizard_completed 后端门禁）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-approval-cycle`（待生成）
**前置**: 02.7 或 02.14（向导完成，可提交评审）
**AI_REQUIRED**: false

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师（提交方）与 manager（审批方），**我想** 在编辑器内提交 FMEA 评审（DRAFT/REWORK→IN_REVIEW，后端强制校验 wizard_completed），由 manager 审批通过（IN_REVIEW→APPROVED，触发版本快照 + PFMEA CP 同步）或驳回返工（IN_REVIEW→REWORK，必须携带非空 reason），返工后可重提，已批准 FMEA 也可返工（APPROVED→REWORK），
**以便** FMEA 经审批方可生效，审批闭环可审计，驳回可返工修正，状态机不可跳步，提交门禁不可绕过。

## 背景 / 前置条件

- 向导已完成（wizardScope.wizard_completed=true），FMEA 处于 DRAFT 或 REWORK。
- 后端 `POST /api/fmea/{id}/transition` 支持 DRAFT→IN_REVIEW、IN_REVIEW→APPROVED、IN_REVIEW→REWORK、REWORK→IN_REVIEW、APPROVED→REWORK（状态机 `fmea_state.py` 已支持全部 5 态流转）。
- **状态机支持情况**：APPROVED→REWORK **已支持**（`fmea_state.py:20`）；DRAFT→APPROVED **已阻止**（`fmea_state.py:18`）。
- **真正缺的实现缺口**：① 权限校验（`require_approve_permission` 仅对 `target_status=="approved"` 检查 APPROVE，见 `api/fmea.py:192`）；② 非空 reason 校验（驳回时）；③ 可编辑状态门禁（IN_REVIEW/APPROVED 拒绝 PUT）；④ wizard_completed 后端强制校验（提交/重提时）。

## 主流程

1. **提交评审**：`planning_qe` 在编辑器点击"提交评审" → DRAFT/REWORK→IN_REVIEW。
   - 需「编辑」权限（EDIT）。
   - **后端强制校验** `wizardScope.wizard_completed=true`（前端仅用于提前提示，可绕过 API 调用）；缺失或 false 返回 **422**（如 "向导未完成，不能提交评审"）。
   - 生成版本快照（change_type="submit"，见 02.18）。
   - 写 AuditLog（`fmea_documents`/`TRANSITION`，Outbox `fmea.submitted`）。
2. **审批通过**：`manager` 在 FMEA 列表/详情审批 → IN_REVIEW→APPROVED。
   - 需 `canApprove('fmea')` 权限（APPROVE，`require_approve_permission` 依赖）。
   - 置 `approved_by`/`approved_at`。
   - 生成版本快照（change_type="approve"，见 02.18）。
   - 触发 PFMEA CP sync_pending（见 02.18；DFMEA 不触发）。
   - 写 AuditLog（`fmea_documents`/`TRANSITION`，Outbox `fmea.approved`）。
3. **驳回返工**：`manager` 驳回 → IN_REVIEW→REWORK。
   - 需 `canApprove('fmea')` 权限（APPROVE；**当前仅对 approved 检查，REWORK 未检查 → 缺口**）。
   - **必须携带非空 reason**。
   - 写 AuditLog（`fmea_documents`/`TRANSITION`，Outbox `fmea.rejected`，含驳回理由）。
   - FMEA 回到可编辑状态（REWORK→IN_REVIEW 可重提）。
4. **重提**：`planning_qe` 修改后重新提交 → REWORK→IN_REVIEW。
   - 需「编辑」权限（EDIT）。
   - **后端强制校验** `wizardScope.wizard_completed=true`（同提交）。
5. **已批准返工**：`manager` 对已批准 FMEA 驳回 → APPROVED→REWORK。
   - 需 `canApprove('fmea')` 权限（APPROVE；**当前仅对 approved 检查，REWORK 未检查 → 缺口**）。
   - **approved_by/approved_at 保留历史**（不清空，便于追溯）。

## 业务规则 / 验收标准

### 审批权限矩阵（后端契约，当前部分未实现 → FAILED 驱动补齐）

| 流转 | 权限 | 说明 | 当前实现 |
|---|---|---|---|
| DRAFT/REWORK → IN_REVIEW | EDIT | 提交评审；后端强制校验 wizardScope.wizard_completed=true | 状态机已支持；权限未显式校验 EDIT；wizard_completed 未校验 → 缺口 |
| IN_REVIEW → APPROVED | APPROVE | 审批通过；置 approved_by/at + 生成 approve 快照 + PFMEA CP sync | ✅ 已实现（`require_approve_permission`） |
| IN_REVIEW → REWORK | APPROVE | 驳回；必须携带非空 reason | 仅对 approved 检查，REWORK 未检查 APPROVE；reason 未校验 → 缺口 |
| REWORK → IN_REVIEW | EDIT | 重提；后端强制校验 wizard_completed | 状态机已支持；权限未显式校验 EDIT；wizard_completed 未校验 → 缺口 |
| APPROVED → REWORK | APPROVE | 已批准后返工 | 状态机已支持；仅对 approved 检查，REWORK 未检查 APPROVE → 缺口 |
| 不可跳步 | — | DRAFT 不可直接 APPROVED | ✅ 状态机已阻止（`fmea_state.py:18`） |
| 可编辑图 | EDIT | 仅 DRAFT、REWORK；IN_REVIEW/APPROVED/ARCHIVED 的 PUT 必须拒绝 | 未实现可编辑状态校验 → 缺口 |

### wizard_completed 门禁契约
- 后端在 `DRAFT/REWORK→IN_REVIEW` 时强制校验 `wizardScope.wizard_completed=true`；缺失或 false 返回 **422**（带明确 detail）。
- E2E 直接调用 `POST /api/fmea/{id}/transition` 验证无法绕过前端。

### 联动
- 提交（DRAFT/REWORK→IN_REVIEW）：生成 submit 快照（02.18）。
- 审批（IN_REVIEW→APPROVED）：生成 approve 快照 + 置 approved_by/at + 触发 PFMEA CP sync_pending（02.18）。

### 审计与落库
- 每次流转写 AuditLog（`fmea_documents`/`TRANSITION`，Outbox `fmea.submitted`/`fmea.approved`/`fmea.rejected`）。
- approved_by/approved_at 持久化；APPROVED→REWORK 后保留历史。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `FMEADocument.{status, approved_by, approved_at}`、`FMEAVersion`（快照）、`ControlPlan.sync_pending`（仅 PFMEA） |
| 关键字段 | status（FMEAState）、approved_by、approved_at |
| 边类型 | 无 |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState ∈ {DRAFT, IN_REVIEW, APPROVED, REWORK, ARCHIVED} |
| 审计事件 | AuditLog `fmea_documents`/`TRANSITION`（Outbox `fmea.submitted`、`fmea.approved`、`fmea.rejected`） |
| E2E seed 前置 | 02.7 或 02.14 完成的 draft FMEA + manager 账号 |
| 通过条件 | 审批权限矩阵全部正确（含 REWORK 检查 APPROVE + EDIT 检查 + 可编辑状态校验）+ wizard_completed 后端强制校验（422，E2E 直接 API 验证）+ 驳回必须非空 reason + 提交/审批各生成快照 + PFMEA APPROVED 触发 CP sync_pending + DFMEA APPROVED 不触发 + 置 approved_by/at + APPROVED→REWORK 保留 approved_by/at + 不可跳步（状态机已阻止）+ 审计 |
| 失败条件（FAILED） | 权限矩阵缺任一项（如 REWORK 未检查 APPROVE；IN_REVIEW/APPROVED 可编辑；wizard_completed 后端未校验或返回非 422；reason 可空）；状态跳步（状态机已阻止，此项预期 PASS）；快照未生成；CP sync 误触发/未触发；approved_by/at 未置或 APPROVED→REWORK 后清空；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 版本快照/CP 联动的字段级细节（见 02.18）。
- APPROVED 后的归档（ARCHIVED）与二次审批深度（另立）。
- 「设计负责人」作为独立 RBAC 角色（另立；当前用 manager 代表）。

## 后续

- 审批闭环为 FMEA 生命周期终点；PFMEA APPROVED 后 CP 待同步（02.18）驱动控制计划侧更新。
