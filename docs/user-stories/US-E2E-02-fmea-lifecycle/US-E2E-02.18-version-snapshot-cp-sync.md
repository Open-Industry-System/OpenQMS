# 子故事 US-E2E-02.18：版本快照 + CP 联动

**状态**: 定稿 v6（2026-11-03），批准快照逐特性导入与保守同步契约
**所属 epic**: US-E2E-02（README.md v4）
**关联 skill**: `verify-fmea-lifecycle-version-snapshot-cp-sync`（已同步；运行结果另见验收证据）
**前置**: 02.15（编辑器保存已就绪）
**AI_REQUIRED**: false

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师，**我想** 在 FMEA 提交评审或审批通过时自动生成版本快照（`FMEAVersion.snapshot`），可查看版本历史与差异对比；当 PFMEA 审批通过时自动标记关联控制计划为"待同步"（sync_pending），
**以便** FMEA 变更有版本可追溯，PFMEA→控制计划变更联动可感知，避免 CP 与已批准 PFMEA 脱节。

## 背景 / 前置条件

- 后端 `fmea_service.transition_fmea` 在 IN_REVIEW/APPROVED 时创建版本快照（`FMEAVersion`）。
- 后端批准事务入独立 CPSyncOutbox，cp_sync_worker 调用 control_plan_service.apply_cp_sync_pending 置 CP.sync_pending=true（**仅 PFMEA 关联时**）。
- 前端 `FMEAVersionSnapshot` 组件支持版本历史 + 差异对比。

## 主流程

1. **版本快照**：
   - FMEA DRAFT/REWORK→IN_REVIEW（提交评审，02.19）→ 创建版本快照（change_type="submit"）。
   - FMEA IN_REVIEW→APPROVED（审批通过，02.19）→ 创建版本快照（change_type="approve"）。
2. **版本查看**：
   - 编辑器内打开版本历史抽屉，查看各版本快照（`FMEAVersion.snapshot` JSONB）。
   - 选择两个版本做差异对比（高亮新增/删除/修改的节点）。
3. **CP 联动（仅 PFMEA）**：
   - PFMEA APPROVED → `CPSyncOutbox(fmea_id, fmea_version_id)` → worker `apply_cp_sync_pending` → 关联 CP 的 `sync_pending=true`。
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
- **交付语义 = Durable outbox**（已实现，仍需回归证明）：

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

  **当前实现**：`CPSyncOutbox` 与 `cp_sync_worker.process_cp_sync_outbox_batch` 已独立实现，审批事务入队，worker 置 pending 并审计；浏览器若关闭 lifespan，须只启动独立 CP worker，不启动 AI／Neo4j worker。

  **outbox 表/worker 选型（计划阶段注意，勿误用）**：
  - **不得复用 `GraphSyncOutbox` / `graph_sync_worker`**——它面向 Neo4j 图投影（`aggregate_type="fmea"`, `event_type=fmea.approved/fmea.updated`，由 `GraphProjectionService` 消费到 Neo4j），与 CP 业务事件无关。
  - 已使用独立 CP outbox 表/模型（如 `CPSyncOutbox`，承载 `cp.sync_pending_set`）+ 独立 CP outbox worker（轮询、幂等、重试、置 CP.sync_pending + 写审计 + 标记 processed）。

  - E2E 验收：APPROVED 提交后立即查 CP outbox 记录存在（且审批事务内**无** `control_plans/UPDATE` 审计）；worker 消费后每个受影响 CP.sync_pending 最终为 true + 各出现 1 条 `control_plans/UPDATE` 审计（允许短暂延迟，需轮询/等待 worker）；worker 重复消费不产生重复审计；APPROVED→REWORK→重新审批产生新的 outbox 事件并可再次触发同步。

### 审计（跨两个事务，共 2 + affected_cp_count 条 AuditLog）

一个 FMEA 可关联多个 CP（`apply_cp_sync_pending` 遍历全部关联 CP）。审计总量 = **审批事务固定 2 条 + worker 事务受影响 CP 数条**（非固定三条）。

| 操作 | 所在事务 | 数量 | `table_name` | `action` | Outbox `event_type` | `changed_fields` |
|---|---|---|---|---|---|---|
| FMEA 状态流转（提交/审批） | 审批事务 | 1 | `fmea_documents` | `TRANSITION` | `fmea.submitted` / `fmea.approved` | old_status / new_status |
| FMEA 版本创建 | 审批事务 | 1 | `fmea_versions` | `CREATE` | `fmea.version_created` | fmea_id / version / change_type / change_summary |
| CP sync_pending 置位 | **worker 事务** | **affected_cp_count**（每个非 pending→pending 翻转的 CP 各 1 条） | `control_plans` | `UPDATE` | `cp.sync_pending_set` | `sync_pending: false→true`；`trigger_fmea_version_id: <批准版本 ID>`（上下文，**不声称修改 CP 字段**） |

- **CP 审计 `changed_fields` 只记录真实字段变化**：pending 标记只改 `sync_pending`（`control_plan_service.py:663`），**不改 `source_fmea_version_id`**——该字段表示 CP 已同步到的 FMEA 版本，仅在真正应用同步时更新（`version_service.py:829`）。因此审计记 `sync_pending: false→true` + `trigger_fmea_version_id`（上下文，从 outbox payload 读取的批准版本 ID），不得把 `source_fmea_version_id` 写入 changed_fields。
- 本次结果须分别记录审批、worker、导入与同步证据；不复用历史缺口结论。

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
| 失败条件（FAILED） | 快照未生成或字段缺失（如缺 snapshot/major_no/minor_no/sha256_hash）；差异对比不可用；PFMEA APPROVED 未触发 CP sync；DFMEA APPROVED 误触发 CP；sync_pending 置位但 CP 不可见；CP sync 非 durable outbox；审批事务提前写 control_plans/UPDATE 审计；worker 不原子/不重试/不幂等（重复审计）；幂等键误用 (fmea_id, event_type) 导致重新审批后无法再同步；已 pending 的 CP 重复写审计；CP 审计 changed_fields 误含 source_fmea_version_id（声称修改了未修改字段）；误用 GraphSyncOutbox/graph_sync_worker 承载 CP 事件；审计实体/action 写错（如版本创建写 TRANSITION 或 CP sync 未写独立 AuditLog）；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 审批闭环本身（提交/审批/驳回流程，见 02.19）。
- 已批准 CP 的新返工流程、全量 CSR/PPAP 合规认证不在本次范围；现有 approved 写入保护仍须保留。
- 版本对比的逐字段 diff 算法深度（现有实现，本子故事只验可用）。

## 后续

- 版本快照为 02.19 审批闭环提供版本可追溯；CP sync_pending 驱动 CP 侧后续更新。

## 2026-11-03 结构化特性补充验收

- `characteristics` 缺失/null 是 legacy，只提示参考，不自动转换、保存不补空数组；显式 `[]` 是确认无特性，禁止回退旧功能字段。
- 每项独立 UUID、kind、名称、规范、单位、可选特殊分类、依据；改名不换 UUID，名称不能为空。按真实唯一 `HAS_FUNCTION` 所属及 FMEA 类型判断 kind；缺失／歧义须复核，不猜测。
- PFMEA 同一工序步骤功能录入 **2 产品**，其工作要素功能录入 **3 过程**；过程只能关联同工序产品 UUID。保存刷新核对集合、规范与分类分离。DFMEA 共享功能类型仍全部为 product。
- 编辑器行级 CRUD／wizardScope、标准表头／结构边不变；approved 写保护和历史快照只读，不迁移历史批准数据。
- 本次特性专项浏览器及完整检查结果见 [纠偏验收证据](../../development/characteristic-correction-acceptance.md)，并非整个子故事（含 AI 等）重新全量认证。

### CP 导入和同步

选择真正 `change_type=approve` 的版本快照，预览／确认携带 `source_fmea_version_id`、`expected_lock_version`、`preview_digest`、`selected_candidate_keys`。五项特性生成五条独立 CP 行，不做产品×过程笛卡尔积；来源元数据只读。实际逐行 `source_characteristic_ref.accepted_source_version_id` 表示接受基线，文档来源跟踪只在全部处理完成时推进。

合法返工、改两项名称、重新审批后：实际陈旧锁返回 409，旧预览失效且不自动重试；用户重新预览，部分接受仍 pending，显式新预览并处理剩余项。核对行 UUID、逐行接受版本与手工评价／频次／方法／反应计划保留。活动 CAPA／执行关联／SC 等受保护行不自动删除；冲突和旧混合行保留 pending，不放宽已批准 CP 门禁。

## 2026-11-03 v6：单位恰好一次与晚到事件

- CP 标准列不变；specification_tolerance 从该对象的 specification＋unit 投影。明确单位恰好一次；原文本已带该单位不重复追加。specification 为 None/空白时，只有 unit 不成为有效控制准则；不做未授权的量值换算。新自动 SC spec_requirement 共用同一小格式化函数，submitted/approved 安全材料仍只提示复核，不能自动改写。
- 单独修改 unit 也必须出现在 import/sync/stale-check 的同源投影中，沿实际接受快照三方比较，保留明确清空；实际 CP API 与 UI 都回读单位，不仅检查 FMEA 输入。旧测试记录与不可变快照不批量修复或冒充手工覆盖。
- 独立 worker 采用 scope→CP parent 的既有有序互斥协议，等待后重读 CP。晚到事件若该 CP 已完整接受同一或更新的、hash/工厂/来源有效的批准基线，不再恢复 pending，也不重复审计；不能只凭文档 source_fmea_version_id 判断完成（部分首次导入也可能有它）。逐行实际接受快照、源身份及覆盖必须有效；未变行可保留旧接受版本。
- 真正更新/未处理/部分接受/未知基线仍保守提示 needs-update；worker 不清除已有 pending，不改源指针、项目或业务字段，仅真实 false→true 写 sync_pending＋trigger_fmea_version_id 审计，outbox 同事务完成。
- 验收必须同时覆盖 worker-first 和 late delivery：暂停且验证仅属本次实例的 worker，真实批准→新 CP 创建/UI 导入→释放后仍不 pending；保留真实部分待办，暂停 worker→合法源返工/单位修改/新批准→UI 完整同步→释放后仍不 pending。按确切版本查只读 outbox completed 是交付后的断言，不能是唯一避免应用顺序缺陷的前置条件。真实独立事务回归另覆盖旧事件在新基线后到达、部分/未知基线及实际锁等待后 fresh-row 重读。
- 新运行使用唯一 CHARACTERISTIC_RUN_TAG，manifest/evidence/PNG/test-results 独立路径；不得覆盖 404b462f 等先前证据。CHARACTERISTIC_WORKER_PID 需指向本次自己启动且命令/cwd 已核对的独立 CP worker；失败时恢复该 worker，不停其他服务。只读原测试解释器、owned endpoint、权限与业务保护要求不变。
