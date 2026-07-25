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
- **交付语义 = Durable outbox**（**目标语义，需新增实现**；现状是直接两阶段调用，见下"当前实现"）：

  **审批事务（`transition_fmea`，单事务原子提交）**：
  - FMEA status=APPROVED + 版本快照（`FMEAVersion`）+ FMEA transition/version 审计（2 条 AuditLog）+ **CP outbox 记录**（`event_type=cp.sync_pending_set`）。
  - **此事务不写 `control_plans/UPDATE` 审计**——worker 尚未改 CP，不能提前审计。

  **Worker 事务（消费 CP outbox，独立事务原子提交）**：
  - 对**每个**实际从非 pending 变为 pending 的关联 CP：CP.sync_pending=true + 该 CP 的 `control_plans/UPDATE` 审计；最后 outbox `status=completed/processed_at`——**同一事务原子提交**。
  - **幂等**：
    - **Outbox 事件键 = `(fmea_id, fmea_version_id, event_type=cp.sync_pending_set)`**——每次批准版本恰好产生一个 outbox 事件；**不能只用 `(fmea_id, event_type)`**（会阻止 APPROVED→REWORK→重新审批后的再次同步，见 02.19）。
    - **Worker 处理键 = `(outbox_id, cp_id)`**——保证每个 CP 对该 outbox 事件只处理、审计一次；worker 重试不产生重复 CP 审计。
    - **已 `sync_pending=true` 的 CP 不重复写 UPDATE 审计**（仅对"非 pending → pending"实际翻转的 CP 写审计）。
  - **重试**：outbox 行带 `attempt_count`/`next_attempt_at`/指数退避，失败重试最终置位（最终一致）。

  **当前实现（与目标语义的差距，验收标 `FAILED` 驱动补齐）**：
  - 现状 `fmea_service.transition_fmea` 在 `:378` commit 审批事务后，`:381-383` **直接调用** `mark_cp_sync_pending_on_fmea_approve`，后者在 `control_plan_service.py:665` 再次 commit——这是**直接两阶段调用，不是 durable outbox**。
  - 现状 `mark_cp_sync_pending_on_fmea_approve` **未写** `control_plans/UPDATE` 审计、**未走** outbox/worker、无幂等键。

  **outbox 表/worker 选型（计划阶段注意，勿误用）**：
  - **不得复用 `GraphSyncOutbox` / `graph_sync_worker`**——它面向 Neo4j 图投影（`aggregate_type="fmea"`, `event_type=fmea.approved/fmea.updated`，由 `GraphProjectionService` 消费到 Neo4j），与 CP 业务事件无关。
  - 需新增独立 CP outbox 表/模型（如 `CPSyncOutbox`，承载 `cp.sync_pending_set`）+ 独立 CP outbox worker（轮询、幂等、重试、置 CP.sync_pending + 写审计 + 标记 processed）。

  - E2E 验收：APPROVED 提交后立即查 CP outbox 记录存在（且审批事务内**无** `control_plans/UPDATE` 审计）；worker 消费后每个受影响 CP.sync_pending 最终为 true + 各出现 1 条 `control_plans/UPDATE` 审计（允许短暂延迟，需轮询/等待 worker）；worker 重复消费不产生重复审计；APPROVED→REWORK→重新审批产生新的 outbox 事件并可再次触发同步。

### 审计（跨两个事务，共 2 + affected_cp_count 条 AuditLog）

一个 FMEA 可关联多个 CP（`mark_cp_sync_pending_on_fmea_approve` 遍历全部关联 CP）。审计总量 = **审批事务固定 2 条 + worker 事务受影响 CP 数条**（非固定三条）。

| 操作 | 所在事务 | 数量 | `table_name` | `action` | Outbox `event_type` | `changed_fields` |
|---|---|---|---|---|---|---|
| FMEA 状态流转（提交/审批） | 审批事务 | 1 | `fmea_documents` | `TRANSITION` | `fmea.submitted` / `fmea.approved` | old_status / new_status |
| FMEA 版本创建 | 审批事务 | 1 | `fmea_versions` | `CREATE` | `fmea.version_created` | fmea_id / version / change_type / change_summary |
| CP sync_pending 置位 | **worker 事务** | **affected_cp_count**（每个非 pending→pending 翻转的 CP 各 1 条） | `control_plans` | `UPDATE` | `cp.sync_pending_set` | `sync_pending: false→true`；`trigger_fmea_version_id: <批准版本 ID>`（上下文，**不声称修改 CP 字段**） |

- **CP 审计 `changed_fields` 只记录真实字段变化**：pending 标记只改 `sync_pending`（`control_plan_service.py:663`），**不改 `source_fmea_version_id`**——该字段表示 CP 已同步到的 FMEA 版本，仅在真正应用同步时更新（`version_service.py:829`）。因此审计记 `sync_pending: false→true` + `trigger_fmea_version_id`（上下文，从 outbox payload 读取的批准版本 ID），不得把 `source_fmea_version_id` 写入 changed_fields。
- **当前实现缺口**：① CP sync 非 durable outbox（直接两阶段调用）；② CP sync_pending 置位未写独立 `control_plans/UPDATE` 审计；③ 无 CP outbox 表/worker/幂等键——本子故事验收此契约为 `FAILED`（驱动补齐）。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `FMEAVersion`（版本快照）、`ControlPlan.sync_pending`（仅 PFMEA） |
| 关键字段 | FMEAVersion.{fmea_id, snapshot, major_no, minor_no, sha256_hash, change_type, created_by, created_at}；ControlPlan.sync_pending |
| 边类型 | 无 |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | 触发时机：IN_REVIEW（submit）/ APPROVED（approve） |
| 审计事件 | 跨两个事务，共 **2 + affected_cp_count** 条 AuditLog：审批事务固定 2 条（fmea_documents/TRANSITION + fmea_versions/CREATE）+ worker 事务受影响 CP 数条（control_plans/UPDATE，仅 PFMEA，每个非 pending→pending 翻转的 CP 各 1 条） |
| E2E seed 前置 | 02.15 编辑器 + 关联 CP（PFMEA） |
| 通过条件 | 提交/审批各生成快照（snapshot/major_no/minor_no/sha256_hash/change_type 完整）+ 差异对比可用 + PFMEA APPROVED 触发 CP sync_pending=true + CP 可见待同步 + DFMEA APPROVED 不触发 CP + CP sync = Durable outbox（审批事务提交 CP outbox 记录且不写 CP 审计；worker 事务原子置位各受影响 CP.sync_pending + 各写 control_plans/UPDATE 审计 + 标记 processed）+ 幂等（outbox 事件键 = (fmea_id, fmea_version_id, cp.sync_pending_set)；worker 处理键 = (outbox_id, cp_id)；已 pending 的 CP 不重复审计；APPROVED→REWORK→重新审批可再次触发）+ CP 审计 changed_fields 仅 sync_pending: false→true + trigger_fmea_version_id（不写 source_fmea_version_id）+ 审计总量 = 2 + affected_cp_count + 使用独立 CP outbox 表/worker（非 GraphSyncOutbox/graph_sync_worker） |
| 失败条件（FAILED） | 快照未生成或字段缺失（如缺 snapshot/major_no/minor_no/sha256_hash）；差异对比不可用；PFMEA APPROVED 未触发 CP sync；DFMEA APPROVED 误触发 CP；sync_pending 置位但 CP 不可见；CP sync 非 durable outbox（现状直接两阶段调用）；审批事务提前写 control_plans/UPDATE 审计；worker 不原子/不重试/不幂等（重复审计）；幂等键误用 (fmea_id, event_type) 导致重新审批后无法再同步；已 pending 的 CP 重复写审计；CP 审计 changed_fields 误含 source_fmea_version_id（声称修改了未修改字段）；误用 GraphSyncOutbox/graph_sync_worker 承载 CP 事件；审计实体/action 写错（如版本创建写 TRANSITION 或 CP sync 未写独立 AuditLog）；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 审批闭环本身（提交/审批/驳回流程，见 02.19）。
- CP 同步的实际内容更新（CP 编辑器侧，另立）。
- 版本对比的逐字段 diff 算法深度（现有实现，本子故事只验可用）。

## 后续

- 版本快照为 02.19 审批闭环提供版本可追溯；CP sync_pending 驱动 CP 侧后续更新。
