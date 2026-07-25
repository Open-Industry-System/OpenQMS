---
name: verify-fmea-lifecycle-version-snapshot-cp-sync
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.18（版本快照 + CP 联动；FMEAVersion.snapshot/major_no/minor_no/sha256_hash/change_type + PFMEA APPROVED 时 CP sync_pending 置位）end-to-end — e.g. "验收 02.18" / "走查 FMEA 版本快照 CP 联动" / "verify version-snapshot-cp-sync". Symptoms include needing to confirm 提交/审批各生成快照、CP sync 是 durable outbox（非直接两阶段调用）、幂等键 (fmea_id, fmea_version_id, cp.sync_pending_set)、CP 审计 changed_fields 仅 sync_pending + trigger_fmea_version_id。
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.18-version-snapshot-cp-sync.md
> 故事版本：定稿 v4（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-version-snapshot-cp-sync

## Overview

本子 skill 走查 US-E2E-02.18：FMEA 提交（DRAFT/REWORK→IN_REVIEW）与审批（IN_REVIEW→APPROVED）两个时机生成 `FMEAVersion` 快照；PFMEA APPROVED 时触发关联 CP `sync_pending=true`（仅 PFMEA，DFMEA 不触发）。

核心验收点：

1. **版本快照**：`FMEAVersion` 字段齐：`snapshot`（JSONB 完整 graph_data）+ `major_no`/`minor_no` + `sha256_hash` + `change_type`（submit/approve）+ `created_by`/`created_at`。
2. **差异对比**：编辑器内版本历史（`[data-e2e="fmea-version-snapshot"]` tab）支持节点级 diff 高亮。
3. **CP sync = Durable outbox**（**目标语义，当前未实现 → FAIL**）：
   - **审批事务**（原子提交）：FMEA status=APPROVED + `FMEAVersion` + FMEA TRANSITION AuditLog（1 条）+ `fmea_versions/CREATE` AuditLog（1 条）+ CP outbox 记录（`event_type=cp.sync_pending_set`）。**此事务不写 `control_plans/UPDATE` 审计**。
   - **Worker 事务**（独立，原子提交）：对每个非 pending→pending 翻转的关联 CP：CP.sync_pending=true + `control_plans/UPDATE` AuditLog + outbox `status=completed/processed_at`。
   - **幂等**：outbox 事件键 = `(fmea_id, fmea_version_id, event_type=cp.sync_pending_set)`；worker 处理键 = `(outbox_id, cp_id)`；已 pending 的 CP 不重复审计。
   - **当前实现（FAIL 预期）**：`fmea_service.transition_fmea` 在 `:378` commit 后 `:381-383` **直接调用** `mark_cp_sync_pending_on_fmea_approve`，后者 `control_plan_service.py:665` 再 commit——**直接两阶段调用，非 durable outbox**；无 CP outbox 表 / worker / 幂等键；CP sync_pending 置位**未写**独立 `control_plans/UPDATE` 审计。
4. **CP 审计 changed_fields**：仅 `sync_pending: false→true` + `trigger_fmea_version_id`；**不得**含 `source_fmea_version_id`（该字段仅在实际应用同步时更新，`version_service.py:829`）。
5. **不得复用 `GraphSyncOutbox`/`graph_sync_worker`**——那是 Neo4j 图投影通道（`aggregate_type="fmea"`, event_type=fmea.approved），与 CP 业务事件无关；若实现走 GraphSyncOutbox → FAIL。
6. **审计总量** = **2 + affected_cp_count** 条 AuditLog（非固定三条）。

## When to Use

**用**：用户说「验收 02.18」「走查版本快照 CP 联动」「verify version-snapshot-cp-sync」等。
**不用**：审批流程本身（02.19）；CP 同步内容更新（另立）；版本 diff 算法深度。

## 前置

1. **epic 级前置**：见 `.claude/skills/verify-fmea-lifecycle/SKILL.md`「前置」节。
2. **无需 LLM 凭证**（AI_REQUIRED=false）。
3. **关联 CP 就绪**：种子数据中已有 PFMEA（如 `PFMEA-E2E-001`）关联 ≥1 个 ControlPlan（`sync_pending=false`），且另有 DFMEA（如 `DFMEA-E2E-001`）作为对照。
4. **manager + engineer 账号**：从 `/api/e2e/seed-state` 拿密码。
5. **可直接调 API**：用 admin token 走 `POST /api/fmea/{id}/transition`，绕过前端验证后端契约。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 提交评审（EDIT） |
| manager | manager (L3-L4) | 审批（APPROVE） |
| admin | admin (L5) | API 直调 + 审计查询 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| `[data-e2e="fmea-version-snapshot"]` | 点击 | 编辑器版本历史 tab（`FMEAEditorPage.tsx:2011`） |
| 版本历史抽屉内 diff 选项 | 按钮文本（i18n） | 选两个版本对比 |
| 「提交评审」 | 按钮文本 | 编辑器顶部 |
| CP 列表「待同步」标识 | Ant Tag/Badge，无 data-e2e | CP 列表/详情行 |

## 走查剧本

### A. 启动 + 提交快照（change_type="submit"）

1. **做**：engineer 登录 → 打开 PFMEA draft（向导已完成）→ 编辑器内点「提交评审」；或 admin token 直调 `POST http://localhost:8001/api/fmea/{pfmea_id}/transition` body `{"target_status": "in_review"}`。
   - **期望**：FMEA status → IN_REVIEW；生成版本快照。
   - **断言**：
     - `GET /api/fmea/{id}` 回读 `status == "in_review"`；
     - `GET /api/fmea/{id}/versions`（或 equivalent endpoint；若无 → MISSING）回读至少 1 条 FMEAVersion：
       - `change_type == "submit"`；
       - `major_no`/`minor_no` 数值合理；
       - `snapshot` 为完整 graph_data JSONB（含 nodes/edges/wizardScope）；
       - `sha256_hash` 非空且可对 snapshot 重算验证；
       - `created_by` == engineer 用户 ID。
   - **落库**：审计 `GET /api/admin/logs/audit?table_name=fmea_documents&record_id=<id>&start=<走查开始ISO>` 含 1 条 `action=TRANSITION`（old_status=draft → new_status=in_review）；`GET /api/admin/logs/audit?table_name=fmea_versions&record_id=<version_id>` 含 1 条 `action=CREATE`，`changed_fields.change_type == "submit"`。

### B. 审批快照（change_type="approve"）+ PFMEA CP sync

2. **做**：manager 登录 → FMEA 列表找该 IN_REVIEW 文档 → 审批通过；或 admin token 直调 `POST /api/fmea/{id}/transition` body `{"target_status": "approved"}`。
   - **期望**：status → APPROVED；生成 approve 快照；触发 CP sync_pending。
   - **断言（版本快照）**：
     - 新增 1 条 FMEAVersion，`change_type == "approve"`，字段齐（同 A）。
   - **断言（CP sync，关键）**：
     - **目标语义（FAIL 预期）**：
       - 审批事务提交后，立即查 CP outbox 表（`cp_sync_outbox` 或类似名）：存在 `(fmea_id, fmea_version_id, event_type="cp.sync_pending_set")` 记录，status=pending；**审批事务内无 `control_plans/UPDATE` 审计**。
       - 等 worker 消费（轮询 ≤ 30s）→ outbox `status=completed` + `processed_at` 非空；
       - 每个关联 CP：`GET /api/control-plans/{cp_id}` 回读 `sync_pending == true`；
       - `GET /api/admin/logs/audit?table_name=control_plans&record_id=<cp_id>` 含 1 条 `action=UPDATE`，`changed_fields` 仅 `sync_pending: false→true` + `trigger_fmea_version_id == <approve 版本 ID>`，**不含 `source_fmea_version_id`**；
       - 审计总量 = 2（审批事务）+ affected_cp_count（worker）。
     - **当前实现（实际预期 FAIL）**：
       - 无 CP outbox 表 / worker → 上面 outbox 断言全 MISSING；
       - `mark_cp_sync_pending_on_fmea_approve` 直接两阶段调用 → CP.sync_pending 可能已置 true（功能可达），但无独立 CP AuditLog（缺审计）；
       - 判 **FAIL**：spec 已定为 durable outbox，现状非 durable。
   - **落库**：
     - FMEA 侧：1 TRANSITION + 1 fmea_versions/CREATE 审计；
     - CP 侧：affected_cp_count 条 control_plans/UPDATE（**当前 0 条 → FAIL**）。

### C. DFMEA 不触发 CP sync（对照）

3. **做**：对 DFMEA（`DFMEA-E2E-001`，已向导完成）重复 A→B 流程，审批通过。
   - **期望**：DFMEA 仅生成 submit + approve 快照；**不**触发 CP sync_pending。
   - **断言**：
     - DFMEA 的 FMEAVersion 数 == 2（submit + approve）；
     - CP outbox 表无该 DFMEA 的 `cp.sync_pending_set` 事件；
     - 关联 CP（若有）`sync_pending` 仍 false；
     - `control_plans` 表无 UPDATE 审计新增。
   - **若 DFMEA 误触发 CP** → FAIL。

### D. 幂等性（APPROVED→REWORK→重新审批）

4. **做**：manager 把已 APPROVED 的 PFMEA 转回 REWORK（`POST /api/fmea/{id}/transition` body `{"target_status": "rework"}`）；engineer 再次提交 → manager 再次审批。
   - **期望**：每次审批产生**新的** FMEAVersion 与**新的** CP outbox 事件（幂等键 `(fmea_id, fmea_version_id, cp.sync_pending_set)` 允许同一 fmea 多次触发，只要 version_id 不同）。
   - **断言**：
     - FMEAVersion 数 +2（再次 submit + approve）；
     - CP outbox 含 ≥2 条该 fmea 的事件（不同 fmea_version_id）；
     - 已 `sync_pending=true` 的 CP 不重复写 UPDATE 审计（仅对"非 pending → pending"实际翻转的 CP 写）；
     - worker 处理键 `(outbox_id, cp_id)` 幂等——worker 重试不产生重复 CP 审计。
   - **当前预期**：FAIL（无 outbox/worker，幂等键不存在）。

### E. 差异对比（编辑器版本历史）

5. **做**：engineer 打开编辑器 → 点 `[data-e2e="fmea-version-snapshot"]` tab → 在版本历史抽屉里选 submit 与 approve 两个版本 → 点「对比」。
   - **期望**：差异视图渲染，新增/删除/修改的节点按颜色高亮。
   - **断言**：版本历史 tab 可见；选中两版本后 diff 视图非空；高亮 class/颜色区分 add/remove/change。
   - **若 tab/对比功能不存在** → MISSING。

### F. CP 列表可见「待同步」

6. **做**：进 CP 列表页 → 找步骤 B 中受影响的 CP。
   - **期望**：行内显示「待同步」Tag/Badge。
   - **断言**：UI 可见标识；`GET /api/control-plans/{cp_id}` 回读 `sync_pending == true`。
   - **若 sync_pending=true 但 UI 无标识** → MISSING（前端展示缺口）。

### G. 收尾

7. **做**：把测试用 FMEA 恢复 DRAFT；受影响的 CP `sync_pending` 重置 false（admin 直改或调种子重置）。
   - **落库**：恢复产生的审计单独记录，不计入本故事判定。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 提交快照 | submit FMEAVersion 字段齐 | PASS |
| 审批快照 | approve FMEAVersion 字段齐 | PASS |
| 差异对比 | 节点级 diff 高亮可用 | PASS（若 tab/对比缺 → MISSING） |
| CP sync = Durable outbox | outbox 表 + worker + 幂等键 + 审批事务不写 CP 审计 | **FAIL**（直接两阶段调用） |
| CP 审计 changed_fields | 仅 sync_pending + trigger_fmea_version_id，不含 source_fmea_version_id | **FAIL**（无 CP 审计落库） |
| 审计总量 | 2 + affected_cp_count | **FAIL**（缺 CP 侧） |
| DFMEA 不触发 CP | 无 CP outbox 事件，无 CP 审计 | PASS |
| 幂等 | APPROVED→REWORK→重审批再触发；已 pending 不重复审计 | **FAIL**（无幂等键） |
| 不用 GraphSyncOutbox | CP 事件独立 outbox 表 | **FAIL**（无 CP outbox 表） |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 快照 + CP sync 全符合 spec |
| **PASS-NOTE** | 通过但有备注 |
| **FAIL** | CP sync 非 durable outbox；审批事务提前写 CP 审计；幂等键误用 (fmea_id, event_type)；CP 审计 changed_fields 含 source_fmea_version_id；误用 GraphSyncOutbox；DFMEA 误触发 CP；审计实体/action 写错 |
| **MISSING** | 版本历史 tab 不存在；CP outbox 表/worker 不存在；快照字段缺（sha256_hash 等） |
| **BLOCKED** | —（AI_REQUIRED=false） |

## 报告片段

```markdown
### 02.18 版本快照 + CP 联动 — <PASS|PASS-NOTE|FAIL|MISSING>

- submit 快照字段齐（snapshot/major_no/minor_no/sha256_hash/change_type/created_by）：<OK|FAIL>
- approve 快照字段齐：<OK|FAIL>
- 差异对比可用：<OK|MISSING>
- PFMEA APPROVED 触发 CP sync_pending：<OK|FAIL>
- CP sync = Durable outbox：<OK|FAIL 直接两阶段调用>
- CP 审计 changed_fields 正确：<OK|FAIL|MISSING>
- 审计总量 = 2 + affected_cp_count：<OK|FAIL>
- 幂等（重审批再触发，已 pending 不重复审计）：<OK|FAIL>
- DFMEA 不触发 CP：<OK|FAIL>
- 截图：screenshots/02.18-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v4（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.18-version-snapshot-cp-sync.md` 顶部「状态: 定稿 vX（日期）」。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
