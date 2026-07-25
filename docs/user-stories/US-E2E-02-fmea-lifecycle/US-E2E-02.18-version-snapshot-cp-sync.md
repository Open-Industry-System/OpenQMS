# 子故事 US-E2E-02.18：版本快照 + CP 联动

**状态**: 定稿 v4（2026-07-25），经三轮代码评审修订（审计实体/action 收口 + CP sync = Durable outbox）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-version-snapshot-cp-sync`（待生成）
**前置**: 02.15（编辑器保存已就绪）
**AI_REQUIRED**: false

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师，**我想** 在 FMEA 提交评审或审批通过时自动生成版本快照（`FMEAVersion.snapshot`），可查看版本历史与差异对比；当 PFMEA 审批通过时自动标记关联控制计划为"待同步"（sync_pending），
**以便** FMEA 变更有版本可追溯，PFMEA→控制计划变更联动可感知，避免 CP 与已批准 PFMEA 脱节。

## 背景 / 前置条件

- 后端 `fmea_service.transition_fmea` 在 IN_REVIEW/APPROVED 时创建版本快照（`FMEAVersion`）。
- 后端 `control_plan_service.mark_cp_sync_pending_on_fmea_approve` 在 APPROVED 时置 CP.sync_pending=true（**仅 PFMEA 关联时**）。
- 前端 `FMEAVersionSnapshot` 组件支持版本历史 + 差异对比。

## 主流程

1. **版本快照**：
   - FMEA DRAFT/REWORK→IN_REVIEW（提交评审，02.19）→ 创建版本快照（change_type="submit"）。
   - FMEA IN_REVIEW→APPROVED（审批通过，02.19）→ 创建版本快照（change_type="approve"）。
2. **版本查看**：
   - 编辑器内打开版本历史抽屉，查看各版本快照（`FMEAVersion.snapshot` JSONB）。
   - 选择两个版本做差异对比（高亮新增/删除/修改的节点）。
3. **CP 联动（仅 PFMEA）**：
   - PFMEA APPROVED → `mark_cp_sync_pending_on_fmea_approve(fmea_id, version_id)` → 关联 CP 的 `sync_pending=true`。
   - DFMEA APPROVED → 只生成版本快照，**不要求 CP**。
   - CP 列表/详情显示"待同步"标识，提示用户基于新 PFMEA 版本更新控制计划。

## 业务规则 / 验收标准

### 版本快照
- 快照在 `transition_fmea` 内创建（提交/审批两个时机）。
- `FMEAVersion` 字段：`snapshot`（JSONB，完整 graph_data）+ `major_no`/`minor_no`（版本号）+ `sha256_hash`（完整性校验）+ `change_type`（submit/approve）+ `created_by`/`created_at`。
- 差异对比支持节点级高亮（新增/删除/修改）。

### CP 联动（仅 PFMEA）
- 仅 PFMEA APPROVED（非 IN_REVIEW，非 DFMEA）触发 CP sync_pending。
- sync_pending 置 true 后，CP 列表/详情可见"待同步"状态。
- **交付语义 = Durable outbox**（对齐现有两阶段实现，`fmea_service.py:378` 先 commit + `control_plan_service.py:665` 再 commit）：
  - 同事务只提交 APPROVED、版本快照、三条 AuditLog、**outbox 记录**（`event_type=cp.sync_pending_set`）。
  - CP sync_pending **最终一致**：outbox worker 消费该事件后重试、幂等、最终置 CP.sync_pending=true。
  - **不采用"同事务"**（需重构现有两阶段代码为单事务）——本 spec 验收 Durable outbox 语义。
  - E2E 验收：APPROVED 提交后立即查 outbox 记录存在；worker 消费后 CP.sync_pending 最终为 true（允许短暂延迟，需轮询/等待 worker）。

### 审计（三个独立 AuditLog 记录）

| 操作 | `table_name` | `action` | Outbox `event_type` | `changed_fields` |
|---|---|---|---|---|
| FMEA 状态流转（提交/审批） | `fmea_documents` | `TRANSITION` | `fmea.submitted` / `fmea.approved` | old_status / new_status |
| FMEA 版本创建 | `fmea_versions` | `CREATE` | `fmea.version_created` | fmea_id / version / change_type / change_summary |
| CP sync_pending 置位 | `control_plans` | `UPDATE` | `cp.sync_pending_set` | sync_pending / source_fmea_version_id |

- **当前实现缺口**：CP sync_pending 置位未写独立 AuditLog（`mark_cp_sync_pending_on_fmea_approve` 直接改 CP.sync_pending，未审计）——本子故事验收此契约为 `FAILED`（驱动补齐）。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `FMEAVersion`（版本快照）、`ControlPlan.sync_pending`（仅 PFMEA） |
| 关键字段 | FMEAVersion.{fmea_id, snapshot, major_no, minor_no, sha256_hash, change_type, created_by, created_at}；ControlPlan.sync_pending |
| 边类型 | 无 |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | 触发时机：IN_REVIEW（submit）/ APPROVED（approve） |
| 审计事件 | 三个独立 AuditLog：`fmea_documents`/`TRANSITION`（流转）+ `fmea_versions`/`CREATE`（快照）+ `control_plans`/`UPDATE`（CP sync，仅 PFMEA） |
| E2E seed 前置 | 02.15 编辑器 + 关联 CP（PFMEA） |
| 通过条件 | 提交/审批各生成快照（snapshot/major_no/minor_no/sha256_hash/change_type 完整）+ 差异对比可用 + PFMEA APPROVED 触发 CP sync_pending=true + CP 可见待同步 + DFMEA APPROVED 不触发 CP + CP sync = Durable outbox（同事务提交 outbox 记录，worker 重试/幂等/最终置位，非单事务同步）+ 三个独立 AuditLog 记录（fmea_documents/TRANSITION + fmea_versions/CREATE + control_plans/UPDATE） |
| 失败条件（FAILED） | 快照未生成或字段缺失（如缺 snapshot/major_no/minor_no/sha256_hash）；差异对比不可用；PFMEA APPROVED 未触发 CP sync；DFMEA APPROVED 误触发 CP；sync_pending 置位但 CP 不可见；CP sync 非 Durable outbox（要求单事务同步即偏离现有实现）或 worker 不重试/不幂等/不最终置位；审计实体/action 写错（如版本创建写 TRANSITION 或 CP sync 未写独立 AuditLog）；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 审批闭环本身（提交/审批/驳回流程，见 02.19）。
- CP 同步的实际内容更新（CP 编辑器侧，另立）。
- 版本对比的逐字段 diff 算法深度（现有实现，本子故事只验可用）。

## 后续

- 版本快照为 02.19 审批闭环提供版本可追溯；CP sync_pending 驱动 CP 侧后续更新。
