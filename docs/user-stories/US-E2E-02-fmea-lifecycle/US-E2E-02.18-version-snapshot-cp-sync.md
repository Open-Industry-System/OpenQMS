# 子故事 US-E2E-02.18：版本快照 + CP 联动

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-version-snapshot-cp-sync`
**前置**: 02.15（编辑器保存已就绪）
**AI_REQUIRED**: false

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师，**我想** 在 FMEA 提交评审或审批通过时自动生成版本快照，可查看版本历史与差异对比；当 FMEA 审批通过时自动标记关联控制计划为"待同步"（sync_pending），
**以便** FMEA 变更有版本可追溯，FMEA→控制计划变更联动可感知，避免 CP 与已批准 FMEA 脱节。

## 背景 / 前置条件

- 后端 `fmea_service.transition_fmea` 在 IN_REVIEW/APPROVED 时创建版本快照。
- 后端 `control_plan_service.mark_cp_sync_pending_on_fmea_approve` 在 APPROVED 时置 CP.sync_pending=true。
- 前端 `FMEAVersionSnapshot` 组件支持版本历史 + 差异对比。

## 主流程

1. **版本快照**：
   - FMEA DRAFT→IN_REVIEW（提交评审，02.19）→ 创建版本快照（change_type="submit"）。
   - FMEA IN_REVIEW→APPROVED（审批通过，02.19）→ 创建版本快照（change_type="approve"）。
2. **版本查看**：
   - 编辑器内打开版本历史抽屉，查看各版本快照。
   - 选择两个版本做差异对比（高亮新增/删除/修改的节点）。
3. **CP 联动**：
   - FMEA APPROVED → `mark_cp_sync_pending_on_fmea_approve(fmea_id, version_id)` → 关联 CP 的 `sync_pending=true`。
   - CP 列表/详情显示"待同步"标识，提示用户基于新 FMEA 版本更新控制计划。

## 业务规则 / 验收标准

### 版本快照
- 快照在 `transition_fmea` 内创建（提交/审批两个时机）。
- 快照含完整 graph_data + change_type（submit/approve）+ version_id + 创建时间。
- 差异对比支持节点级高亮（新增/删除/修改）。

### CP 联动
- 仅 APPROVED（非 IN_REVIEW）触发 CP sync_pending。
- sync_pending 置 true 后，CP 列表/详情可见"待同步"状态。

### 审计与落库
- 版本快照创建写 AuditLog。
- CP sync_pending 置位写 AuditLog。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `FMEAVersion`（版本快照）、`ControlPlan.sync_pending` |
| 关键字段 | FMEAVersion.{fmea_id, graph_data, change_type, version_id, created_at}；ControlPlan.sync_pending |
| 边类型 | 无 |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | 触发时机：IN_REVIEW（submit）/ APPROVED（approve） |
| 审计事件 | `fmea.version_created`、`cp.sync_pending_set` |
| E2E seed 前置 | 02.15 编辑器 + 关联 CP |
| 通过条件 | 提交/审批各生成快照 + 差异对比可用 + APPROVED 触发 CP sync_pending=true + CP 可见待同步 + 审计 |
| 失败条件（FAILED） | 快照未生成；差异对比不可用；APPROVED 未触发 CP sync；sync_pending 置位但 CP 不可见；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 审批闭环本身（提交/审批/驳回流程，见 02.19）。
- CP 同步的实际内容更新（CP 编辑器侧，另立）。
- 版本对比的逐字段 diff 算法深度（现有实现，本子故事只验可用）。

## 后续

- 版本快照为 02.19 审批闭环提供版本可追溯；CP sync_pending 驱动 CP 侧后续更新。
