---
name: verify-capa-8d-fmea-linkage
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D ↔ FMEA bidirectional traceability (US-E2E-01.4). Symptoms include checking FMEA link from CAPA header, reverse lookup from FMEA to linked CAPAs, or D7 node-action FMEA matching.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.4-fmea-linkage.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-fmea-linkage

## Overview

走查 US-E2E-01.4 8D ↔ FMEA 双向追溯：CAPA header 关联 FMEA（`fmea_ref_id`）→ FMEA 详情反查关联 CAPA 列表 → D7 node-action 按 `linked`/`keyword`/`rule` 匹配 FMEA 预防节点。

## When to Use

**用**：用户说「验收 01.4」「走查 FMEA 双向」「验证 CAPA 关联 FMEA」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. LLM 凭证（AI_REQUIRED=false，本子故事不依赖 LLM）。
4. seed-state 取 engineer 账号。
5. seed 中有 `PFMEA-E2E-FMEA-LINK-001`（含 `fm-1`/`cause-link`/`pc-link` 节点）。

## 走查剧本

> **假 PASS 防护**：seed 预置 `8D-E2E-FMEA-LINK-001` 的 `fmea_ref_id` + `FMEA_LINKAGE_CREATED` 审计。验收前记录走查开始时间 `t0`，所有审计断言按 `operated_at >= t0` 过滤（API 响应字段是 `operated_at`，不是 `created_at`），仅认可本轮新写的审计——否则旧 seed 审计会让断言空走也 PASS。
>
> **审计 API 用法**（重要）：`GET /api/admin/logs/audit` 只接收 `table_name`/`action`/`operated_by`/`start`/`end`，**不接收 `record_id`**（`record_id` 查询参数会被忽略）。响应字段是 `operated_at`（不是 `created_at`），每条含 `record_id`。正确做法：`GET /api/admin/logs/audit?table_name=capa_eightd&action=FMEA_LINKAGE_CREATED&start={t0_iso}&page_size=200`，然后在**客户端**按 `item.record_id == {capa_id}` 和 `item.operated_at >= t0` 过滤。直接拼 `record_id={id}` 是无效的。

### A. CAPA → FMEA（header link 回读 + 审计隔离）
- engineer 登录 → 进 `8D-E2E-FMEA-LINK-001`（D4_ROOT_CAUSE）。
- seed 已预关联 `PFMEA-E2E-FMEA-LINK-001`（`fmea_ref_id` 非空），且 seed 预置了 `FMEA_LINKAGE_CREATED`（`source=header`）审计。**无法解绑后重关联**——不存在清空 `fmea_ref_id` 的 PATCH 路由，PUT 也跳过 `None` 值。因此 header-link 的「新建关联」动作不可走查，只能做回读断言。
- **断言（回读）**：`GET /api/capa/{id}` `fmea_ref_id` = `PFMEA-E2E-FMEA-LINK-001` 的 fmea_id。
- **审计（按 `start=t0` + 客户端 `record_id`/`operated_at` 过滤）**：本轮**不产生**新 `FMEA_LINKAGE_CREATED`（无新建关联动作）→ 步骤 `PASS`，**备注**写明「header-link 审计依赖 seed 预置，未走查新建路径」。若需验证「新建 header-link 审计」，须用一条初始未关联 FMEA 的新 CAPA（当前 seed 无此 CAPA）。

### B. FMEA → CAPA（reverse lookup）
- 进 FMEA 列表 → `PFMEA-E2E-FMEA-LINK-001` → 详情 → 关联 CAPA 面板。
- **断言**：面板列出 `8D-E2E-FMEA-LINK-001`（`8D-E2E-FMEA-LINK-002` 若已 link 才出现）。

### C. D7 node-action FMEA 匹配
- 推进到 D7_PREVENTION → D7RecPanel 渲染。
- **断言**：`GET /api/capa/{id}/d7-node-actions`（已持久化的动作行）中 `linked` 项 `fmea_id` = `PFMEA-E2E-FMEA-LINK-001` 的 fmea_id，`failure_mode_node_id=fm-1`，`failure_cause_node_id=cause-link`。
- **注意区分 API**：`keyword`/`rule` 项来自**推荐 API**（`GET /api/capa/{id}/d4-fmea-recommendations` 或 D7 推荐计算），不是 `d7-node-actions`。seed 仅预置一条 `linked` 动作；未执行 confirm/skip 前 `d7-node-actions` 不会有 `keyword` 项。断言 `d7-node-actions` 含 keyword 会误 FAIL——如需验证 keyword，先在 D7RecPanel 对一条 keyword 推荐点 `d7-confirm`，再查 `d7-node-actions` 出现该 keyword 行。
- **注意**：`rule` 兜底项（`fmea_id=null`）仅在无 linked/keyword 推荐时生成；当前 seed 有 linked 命中，不预期出现 rule 项。断言 rule 存在会误 FAIL。

### D. skip 项 + 推进审计
- **seed 预置**：`8D-E2E-FMEA-LINK-002` 已有一条 `action=skipped` 的 D7 node-action（见 `_seed_fmea_linkage`）。因此：
  - 再次点 `d7-skip`（同 reason）→ **幂等返回，不写新审计**。
  - 点 `d7-skip` 带不同 reason → 写 `D7_ACTION_CHANGED`（old_action=skipped, new_action=skipped, reason 变化），**不写** `D7_NODE_SKIPPED`。
  - **无法在本 seed 产生新 `D7_NODE_SKIPPED`**——该审计仅在新建（不存在既有行时）skip 动作时写。
- **走查断言（调整）**：
  - 验证既有 skipped 行：`GET /api/capa/{id}/d7-node-actions` 含 `action=skipped` 行（步骤 `PASS`；备注：seed 预置，非本轮产生）。
  - 验证 `D7_ACTION_CHANGED`：点 `d7-skip` 带新 reason → 审计 `D7_ACTION_CHANGED`（`start=t0` + 客户端 `record_id`/`operated_at` 过滤）。
  - 验证 `D7_SKIP_CONFIRMATION`（须直调 API）：`POST /api/capa/{id}/advance` body `{target_state:"D7_COMPLETED", d7_skip_reasons:[{fmea_id, node_id, reason}]}` → 写 `D7_SKIP_CONFIRMATION`。UI 在已全 skip 时不开 skip-reason 对话框（`allD7Confirmed=true`），故须直调 advance API。

## 缺陷分类

PASS / FAIL / MISSING / BLOCKED（备注写说明；不用 PASS-NOTE）。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.4/report.md`，用编排器契约模板。FAIL/MISSING 截图存 `screenshots/`。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
