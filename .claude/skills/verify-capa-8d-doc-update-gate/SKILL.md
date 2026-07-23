---
name: verify-capa-8d-doc-update-gate
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D D8 document update gate (US-E2E-01.7). Symptoms include checking D8_GATE_PENDING transition, doc-gate panel, impact analysis, or audit coverage.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.7-doc-update-gate.md
> 故事版本：定稿 v2（2026-07-23）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-doc-update-gate

## Overview

走查 US-E2E-01.7 D8 文档更新审核门禁：`D7_COMPLETED` → `D8_GATE_PENDING` → AI 影响分析 → 自动审核（**仅 FMEA/CP**，设计 C1）→ decision（passed/blocked/deferred）→ `D8_APPROVAL_PENDING`。

## When to Use

**用**：用户说「验收 01.7」「走查文档门禁」「验证 D8 gate」等。

## 前置

1. 故事版本一致（比对 `US-E2E-01.7-doc-update-gate.md` 顶部：定稿 **v2（2026-07-23）**）。
2. e2e 栈在跑。
3. LLM 凭证齐（AI_REQUIRED=true；影响分析需 LLM）。**无 LLM → 01.7 整体 `BLOCKED`**（影响分析路径不可降级为 skip；门禁无影响分析即无法 passed→advance）。
4. seed-state 取 engineer/manager 账号。
5. seed 中有 `8D-E2E-DOCGATE-001`（`D8_GATE_PENDING`）和 `PFMEA-E2E-DOCGATE-001` + `CP-E2E-DOCGATE-001`。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="doc-gate-panel"]` | 门禁面板 |
| `[data-e2e="doc-gate-generate"]` | 触发影响分析（POST impact） |
| `[data-e2e="doc-gate-regenerate"]` | 重新生成 |
| `[data-e2e="doc-gate-status"]` | analysis 状态 Tag |
| `[data-e2e="doc-gate-affected-list"]` | 受影响文档列表 |
| `[data-e2e="doc-gate-confirm-empty"]` | 空清单确认无影响 |
| `[data-e2e="doc-gate-run-audit"]` | 触发自动审核 |
| `[data-e2e="doc-gate-audit-zone"]` / `doc-gate-audit-table` | 审核区 |
| `[data-e2e="doc-gate-decision"]` | 当前 decision |
| `[data-e2e="doc-gate-advance"]` | 门禁通过后推进 |
| `[data-e2e="doc-gate-defer-btn"]` | 打开延期 Modal |
| `[data-e2e="doc-gate-defer-modal"]` | 延期弹窗 |
| `[data-e2e="doc-gate-defer-reason"]` / `doc-gate-defer-owner` / `doc-gate-defer-deadline` | 延期字段 |
| `[data-e2e="capa-status"]` | 状态文案 |
| `[data-e2e="capa-advance"]` | 在 D8_GATE_PENDING **应隐藏**（全局推进排除） |

## 走查剧本

> **假 PASS 防护**：走查前记录 `t0`。reseed 会清理此 CAPA 的全部审计，但仍按 `start=t0` 过滤审计断言，仅认可本轮新写的审计。
>
> **审计 API 用法**（重要）：`GET /api/admin/logs/audit` 只接收 `table_name`/`action`/`operated_by`/`start`/`end`，**不接收 `record_id`**（拼 `record_id={id}` 会被忽略，可能命中其他 CAPA 的同名审计）。响应字段是 `operated_at`（不是 `created_at`），每条含 `record_id`。正确做法：`GET /api/admin/logs/audit?table_name=capa_eightd&action=DOC_IMPACT_ANALYZED&start={t0_iso}&page_size=200`，再在**客户端**按 `item.record_id == {capa_id}` 和 `item.operated_at >= t0` 过滤。

### A. 门禁入口
- engineer 登录 → 进 `8D-E2E-DOCGATE-001`。
- **断言**：`[data-e2e="capa-status"]` = `D8_GATE_PENDING`；`[data-e2e="doc-gate-panel"]` 可见；`[data-e2e="capa-advance"]` **隐藏**；`[data-e2e="doc-gate-generate"]` 可见。

### B. 影响分析（验收范围 = CP + FMEA，故事 v2 / 设计 C1）
- 点 `[data-e2e="doc-gate-generate"]` → 等待 done。
- **断言**：`GET /api/capa/{id}/doc-gate/impact` `status=done`；`affected_docs` 非空，**含 `control_plan` 与 `fmea` 两类**（seed 已在同产品线 `E2E_PRODUCT_LINE` 建 `CP-E2E-DOCGATE-001` + `PFMEA-E2E-DOCGATE-001`）。每条含 `doc_type`、`doc_id`、`doc_name`、`baseline_version_id`、`baseline_version`。
- **通过条件（v2）**：`affected_docs` 的 `doc_type` 并集 ⊇ {`control_plan`, `fmea`} → 本步可 **PASS**。**不**要求 SOP / inspection_sop / other；allowlist 与 prompt 仅 CP+FMEA 是契约而非缺口。
- **缺类 = FAIL**：只有一类或零类（seed 有 CP+FMEA 仍分析不出）→ **FAIL**。
- **空清单 = FAIL**：`affected_docs=[]` 是实现缺陷；`confirm-no-affected` 仅在「无受影响」合法时使用。
- **审计**：`GET /api/admin/logs/audit?table_name=capa_eightd&action=DOC_IMPACT_ANALYZED&start={t0_iso}&page_size=200`，客户端按 `record_id == {capa_id}` 和 `operated_at >= t0` 过滤后 ≥ 1。

### C. 自动审核（passed 路径：版本 bump + 可写字段覆盖）
- `[data-e2e="doc-gate-run-audit"]` → `POST /api/capa/{id}/doc-gate/audit` → 每文档 `status` ∈ {passed, pending_update, incomplete}；`decision` ∈ {passed, blocked}。
- **passed 的前置条件**：单文档 `status=passed` 当且仅当 (a) 存在 `created_at > capa.created_at` 的版本（`version_bump=true`），(b) baseline sha256 ≠ latest sha256，(c) 该文档全部 `key_points` 被 diff 覆盖。否则 `incomplete`（有 bump 覆盖不全）或 `pending_update`（无 bump）。
- **可写字段陷阱（重要，产品限制 — 按 action 区分）**：FMEA `allowed_fields` = [`prevention_control`, `detection_control`, `name`]，但 `GraphNodeSchema` **没有** `prevention_control`/`detection_control`（只有 `name` 及 severity/occurrence/detection 等）。`PUT /api/fmea/{id}` 经 Pydantic 会丢弃前两个字段。对 audit 覆盖的影响：
  - **`modify` + field ∈ {prevention_control, detection_control}**：diff 永远盖不到 → 该 key_point **incomplete**（产品 bug）。
  - **`modify` + field=`name`**：可改 node `name` → 可 covered。
  - **`delete`**：`_match_key_point` **只比 node id / item_id，忽略 field** → 删除目标节点/项即可 covered，与 field 无关。
  - **`add` + field ∈ {prevention_control, detection_control}**：匹配要求新节点上该 field **非空**，但 API 写不进去 → incomplete（产品 bug）。
  - **`add` + field=`name`**：新节点 `name=business_key` 且 field 非空即可。
  - CP 的 `allowed_fields`（`control_method`/`reaction_plan`/`special_class`/`sample_size`/`sample_frequency`/`product_characteristic`/`process_characteristic`）均可写，CP 各 action 稳定可走。
- **走查 passed 路径的步骤**（版本 bump 必须显式创建，PUT 只更新不建版本）：
  1. **先完成 B 步 impact**，`GET /api/capa/{id}/doc-gate/impact` 读出每个 `affected_doc` 的 **全部** `key_points`（每项：`target_kind` / `expected_action` / `field` / `target_key` 或 `add_anchor`）。同产品线还可能出现 **无 baseline** 的文档（如 seed 的 `PFMEA-E2E-001` 无 version 行）→ LLM 可产出 `target_kind=document` + `expected_action=add`。
  2. **禁止硬编码只改某一字段**。`run_audit` → `_match_key_point` 按 action 分支严格匹配（见下）。漏改任何一个 key_point → 该 doc `incomplete`，整单无法 `passed`。必须对 **impact 返回的全部 key_points 逐条执行**。
  3. **按 key_point 落库**（同 doc 可合并一次 PUT，但每条匹配条件都必须满足）：

     | target_kind | action | 角色 | 落库要点（`_match_key_point` 真源） |
     |---|---|---|---|
     | `document` | `add` | engineer（FMEA）/ manager（CP） | **仅允许 baseline=NULL**；**不得**带 `target_key`/`add_anchor`。audit 对 document 直接 `return action=="add"`——只需为该文档创建 **首个** 版本（`POST .../versions` + JSON body）。无需先改内容。seed 常见：`PFMEA-E2E-001`（`DC-DC-100-E2E`，无 baseline）。 |
     | `cp_item` | `modify` | **manager** | seed `CP-E2E-DOCGATE-001` 为 **`draft`**（approved 会 400）。body **完整 `items` + 保留原 `item_id`（=target_key）**；该 `field` 值须与 baseline **不同**。engineer PLANNING=VIEW → PUT CP **403**。 |
     | `cp_item` | `delete` | manager | 完整 items 数组中 **去掉** `item_id==target_key` 的项后 PUT（field 被校验但匹配时忽略）。 |
     | `cp_item` | `add` | manager | 在完整 items 中 **追加** 一项，且必须同时满足：`source_fmea_node_id == add_anchor.parent_node_id`；`product_characteristic` **或** `process_characteristic` 等于 `add_anchor.business_key`（trim+小写比较）；`field` 指定字段 **非空**。`node_type` 仅校验 allowlist，匹配不看它。新 item 可用 `temp-*` 或省略 item_id（服务端建 UUID）。 |
     | `fmea_node` | `modify` | engineer | **`PUT /api/fmea/{id}` 是整图替换**（`fmea_service` 写整个 `graph_data`，不是 patch）。必须先 `GET /api/fmea/{id}` 取完整 `graph_data`，在内存改目标 node 后 **原样带回全部 nodes/edges**（含未改节点）；只提交目标节点会删掉其余图。field=`name` 可写；prevention/detection_control → incomplete。target_key = node `id`。 |
     | `fmea_node` | `delete` | engineer | 同上：**GET 全图 → 删掉 `id==target_key` 的 node 及悬空边 → PUT 完整 graph_data**。field 不参与匹配。 |
     | `fmea_node` | `add` | engineer | 同上：**GET 全图 → append node + edge → PUT 完整 graph_data**。新 node：`id` 新 UUID、`type == add_anchor.node_type`、`name`（trim+小写）== `business_key`；边三字段齐全 `{"source","target","type"}`（缺 type → **422**）。**先判 anchor 是否合法，再决定是否落库**（见下「add_anchor 合法性」）。仅 **canonical 父子** 才可写边；**任何非 canonical anchor 一律 incomplete，不得落库**（写非法边可让 matcher 假 PASS）；若存在此类 key_point → **passed 路径 FAIL（产品缺陷）**。field 非空；prevention/detection_control 写不进 → incomplete。 |

  4. **FMEA `add_anchor` 合法性（产品缺陷 — 必须先过滤再落库）**：
     - **实现现状**：`_cand_from_fmea` 对 **每个** 已有 node × `{FailureMode, FailureEffect, FailureCause}` 笛卡尔积生成 `add_anchors`（`capa_doc_gate_service.py`）；`_match_key_point` 只查 parent 是否为边的 source、new.type/name/field，**不校验 edge.type、不校验 parent 节点 type**。
     - **canonical 父子（`seed.py` 真源，仅这些允许落库）**：

       | new `node_type` | parent type 必须是 | 标准边 direction + type | 与 matcher parent→new |
       |---|---|---|---|
       | `FailureMode` | `Function`（含 ProcessStepFunction 等 function 类） | parent→new `HAS_FAILURE_MODE` | ✓ 一致 |
       | `FailureEffect` | `FailureMode` | parent→new `EFFECT_OF` | ✓ 一致 |
       | `FailureCause` | `FailureMode`（语义上 cause 挂在 FM 下） | **new→parent** `CAUSE_OF`（Cause→FM） | ✗ 与 matcher 要求 parent→new **冲突** |

     - **一律 incomplete、不得落库** 的例子（matcher 仍可能假 PASS；不得用 PASS-NOTE 软化）：
       - parent type ∉ 上表（如 seed docgate baseline 仅 `ProcessStep` `node-1` → 全部 3 种 anchor 都非法：ProcessStep→FM/FE/FC）；
       - parent=FM + new=FailureCause：标准边是 Cause→FM，写 parent→new + `CAUSE_OF` = **反向边** 假 PASS；
       - 任意写错 type 但仍 parent→new 的边（matcher 不看 type）。
     - **走查规则**：**不得**为通过 gate 而写语义错误边。对非法 / 方向冲突的 key_point **一律 incomplete**（不得记 PASS-NOTE）；若 impact 含此类 key_point 且无法合法覆盖 → 该 doc 无法 `status=passed` → **passed 路径记 FAIL（产品缺陷：add_anchor 笛卡尔积 + matcher 不验父子/边 type）**，子报告单列；**不得**只特判 CAUSE_OF——ProcessStep 父等同样禁止。
  5. **每个被改的文档（含 document-add）显式建版本**（PUT 不建版本）：
     - CP：`POST /api/control-plans/{cp_id}/versions`（鉴权 `Module.FMEA >= CREATE`）
     - FMEA：`POST /api/fmea/{fmea_id}/versions`
     - **必须带 JSON body**（`req: ManualVersionCreate`；裸 POST → **422**）。发 `{}` 或 `{"change_summary":"01.7 doc-gate update"}`。`Content-Type: application/json`。
     - `document` add：仅此 POST 即可（version_bump：latest 存在且 created_at > capa.created_at，baseline 为 null 时 sha 不等自然成立）。
  6. `run-audit`。期望：每个被更新 doc 的 `coverage` 全部 `covered=true` → `status=passed`；否则按漏改/不可写字段/非法 add_anchor 记 `incomplete`。
- **blocked 路径（无须 bump）**：直接 `run-audit`（无新版本）→ `status=pending_update` → `decision=blocked` → advance 400 阻断。
- **审计**：`action=DOC_UPDATE_AUDITED`（含 status）；通过时另有 `DOC_GATE_PASSED`；阻断时 `DOC_GATE_BLOCKED`。

### D. Decision + 推进
- **passed**：`GET /api/capa/{id}/doc-gate/decision` `decision=passed` → `[data-e2e="doc-gate-advance"]` 或 `POST /api/capa/{id}/advance` `target_state=D8_APPROVAL_PENDING` → status=`D8_APPROVAL_PENDING`。
- **blocked**：不能推进到 D8_APPROVAL_PENDING（advance 400）。
- **deferred**：`[data-e2e="doc-gate-defer-btn"]` → 填 reason/owner/deadline → 审计 `action=DOC_GATE_DEFERRED`（defer 仍阻断推进）。

### E. 版本新鲜度（input hash 不含 latest version）
- **断言**：`analysis_input_hash`（C9）= capa 语义输入 + 候选身份集（doc_type/doc_id/baseline）+ contract_version，**明确不含 latest version**（`_compute_input_hash` 注释 MUST NOT include latest version）。
- **因此**：分析后创建新版本（passed 的必要步骤）**不会**使 input hash 失效或触发 freshness 阻断。freshness 只在 CAPA 语义输入（d4/d5/d7/severity/fmea_ref 等）或候选 baseline 变化时使旧分析 stale（须重生成 impact），不在新建版本时阻断。走查「分析后 bump 版本」是正确做法，不记 FAIL。

## 缺陷分类

步骤级：PASS / FAIL / MISSING / BLOCKED。**整单总体结论**（编排器读）：仅 `PASS` / `FAIL` / `BLOCKED`（与编排器契约一致；**不得**用 PASS-NOTE 作为总体结论）。

- 非法 add_anchor / 不可写 field 等产品缺陷：key_point → **incomplete**；若导致无法 `decision=passed` → 整单 **FAIL（产品缺陷）**，备注写清根因。
- 无 LLM → 整体 `BLOCKED`（不记 PASS/FAIL）。

## FAIL / BLOCKED 后 01.3 衔接（编排器读此节）

01.7 **不再**因「缺 SOP 第三类」必然 FAIL（故事 v2）。若 01.7 仍 FAIL/BLOCKED（LLM 失败、产品 bug、无 LLM 等）：
- **不要**为「给 01.3 留 D8_APPROVAL_PENDING」而人为制造 `passed` decision。
- 01.3 post-gate **审批路径 (c)** 依赖 `8D-E2E-DOCGATE-001` 到达 `D8_APPROVAL_PENDING`。若 01.7 未推进到该状态，则 01.3 **(c) 审批** 标 `BLOCKED（前置 01.7 未通过）`；**权限 (a) 与驳回 (b)** 在 `8D-E2E-APPROVAL-001` 上**不依赖 01.7**，须继续验收。
- 产品 bug（FMEA 不可写 prevention/detection_control；add_anchor 笛卡尔积/matcher 不验 canonical 父子与边 type）若导致无法 `decision=passed` → 整单仍 **FAIL（产品缺陷）**，与 SOP 无关。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.7/report.md`，用编排器契约模板。FAIL/MISSING 截图存 `screenshots/`。明确写出：验收范围 = CP+FMEA（v2）；FMEA 产品限制的 **action 范围**（modify/add 的 prevention|detection_control 不可写；delete 不受影响）；**add_anchor 笛卡尔积 + matcher 不验父子/边 type**（含 ProcessStep 父、CAUSE_OF 方向冲突等——不得写非法边换假 PASS）。

## 维护

每次跑前比对故事版本（v2 / 2026-07-23）；不一致 → 停下提示同步。
