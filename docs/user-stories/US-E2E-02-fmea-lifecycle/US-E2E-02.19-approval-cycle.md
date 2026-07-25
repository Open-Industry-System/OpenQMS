# 子故事 US-E2E-02.19：审核闭环（提交 + 审批 + 驳回）

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-approval-cycle`
**前置**: 02.7 或 02.14（向导完成，可提交评审）
**AI_REQUIRED**: false

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师（提交方）与 manager（审批方），**我想** 在编辑器内提交 FMEA 评审（DRAFT→IN_REVIEW），由 manager 审批通过（IN_REVIEW→APPROVED，触发版本快照 + CP 同步）或驳回返工（IN_REVIEW→REWORK），返工后可重提，
**以便** FMEA 经审批方可生效，审批闭环可审计，驳回可返工修正。

## 背景 / 前置条件

- 向导已完成（wizard_completed=true），FMEA 处于 DRAFT。
- 后端 `POST /api/fmea/{id}/transition` 支持 DRAFT→IN_REVIEW、IN_REVIEW→APPROVED、IN_REVIEW→REWORK、REWORK→IN_REVIEW。
- 审批（IN_REVIEW→APPROVED）需 `canApprove('fmea')` 权限（manager，planning_qe 不可）。

## 主流程

1. **提交评审**：`planning_qe` 在编辑器点击"提交评审" → DRAFT→IN_REVIEW。
   - 生成版本快照（change_type="submit"，见 02.18）。
   - 写 AuditLog（`fmea.submitted`）。
2. **审批通过**：`manager` 在 FMEA 列表/详情审批 → IN_REVIEW→APPROVED。
   - 需 `canApprove('fmea')` 权限校验（`require_approve_permission` 依赖）。
   - 置 `approved_by`/`approved_at`。
   - 生成版本快照（change_type="approve"，见 02.18）。
   - 触发 CP sync_pending（见 02.18）。
   - 写 AuditLog（`fmea.approved`）。
3. **驳回返工**：`manager` 驳回 → IN_REVIEW→REWORK。
   - 写 AuditLog（`fmea.rejected`，含驳回理由）。
   - FMEA 回到可编辑状态（REWORK→IN_REVIEW 可重提）。
4. **重提**：`planning_qe` 修改后重新提交 → REWORK→IN_REVIEW。

## 业务规则 / 验收标准

### 状态机流转
- DRAFT → IN_REVIEW（提交，planning_qe 可）。
- IN_REVIEW → APPROVED（审批，manager 可，planning_qe 不可 → 403）。
- IN_REVIEW → REWORK（驳回，manager 可）。
- REWORK → IN_REVIEW（重提，planning_qe 可）。
- APPROVED → REWORK（已批准后返工，manager 可）。
- 不可跳步（DRAFT 不可直接 APPROVED）。

### 权限
- 提交/重提：需「编辑」权限（planning_qe）。
- 审批/驳回：需「审批」权限（manager）。
- 只读用户：不可提交/审批/驳回。

### 联动
- 提交（DRAFT→IN_REVIEW）：生成 submit 快照（02.18）。
- 审批（IN_REVIEW→APPROVED）：生成 approve 快照 + 置 approved_by/at + 触发 CP sync_pending（02.18）。

### 审计与落库
- 每次流转写 AuditLog（`fmea.submitted`/`fmea.approved`/`fmea.rejected`）。
- approved_by/approved_at 持久化。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `FMEADocument.{status, approved_by, approved_at}`、`FMEAVersion`（快照）、`ControlPlan.sync_pending` |
| 关键字段 | status（FMEAState）、approved_by、approved_at |
| 边类型 | 无 |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState ∈ {DRAFT, IN_REVIEW, APPROVED, REWORK, ARCHIVED} |
| 审计事件 | `fmea.submitted`、`fmea.approved`、`fmea.rejected` |
| E2E seed 前置 | 02.7 或 02.14 完成的 draft FMEA + manager 账号 |
| 通过条件 | 状态机流转正确 + 权限校验（planning_qe 不可审批→403）+ 提交/审批各生成快照 + APPROVED 触发 CP sync_pending + 置 approved_by/at + 驳回可返工重提 + 审计 |
| 失败条件（FAILED） | 状态跳步；权限校验失效（planning_qe 可审批）；快照未生成；CP sync 未触发；approved_by/at 未置；驳回不可返工；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 版本快照/CP 联动的字段级细节（见 02.18）。
- APPROVED 后的归档（ARCHIVED）与二次审批深度（另立）。
- 「设计负责人」作为独立 RBAC 角色（另立；当前用 manager 代表）。

## 后续

- 审批闭环为 FMEA 生命周期终点；APPROVED 后 CP 待同步（02.18）驱动控制计划侧更新。
