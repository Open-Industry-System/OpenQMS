---
name: verify-capa-8d-d4-d7-audit
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D D4 verification + D7 node-action + approval shell (US-E2E-01.3). Symptoms include checking root cause verification flow, D7 FMEA node-actions, D8 approval gate, or rejection rollback.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.3-d4-verification-d7-node-action.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-d4-d7-audit

## Overview

走查 US-E2E-01.3：D4 根因现场验证（method/result/evidence + pass/fail/draft）→ D4→D5 闸口 → D7 node-action（confirm/skip）→ D7→D8 壳状态推进与审批边界。

## When to Use

**用**：用户说「验收 01.3」「走查 D4 验证」「验证 D7 node-action」「检查审批壳」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. LLM 凭证齐（AI_REQUIRED=true；D7 auto-fill 需 LLM）。**无 LLM → 整个 01.3 标 `BLOCKED`，不软跳过 auto-fill**。auto-fill 子断言缺失即 FAIL。
4. seed-state 取 engineer/manager 账号。
5. seed 用三条独立 CAPA（pre-gate / post-gate 审批 / post-gate 驳回各一个，互不污染）：
   - **pre-gate**：`8D-E2E-D4-001`（`_seed_d4_audit` 产出，`D4_ROOT_CAUSE`，挂 FMEA `PFMEA-E2E-FMEA-LINK-001`；无预存 D4 验证/D7 动作，01.3 新鲜创建）——在它上推进 D4 验证 → D7 node-action → `D7_COMPLETED` → `D8_GATE_PENDING`。
   - **post-gate 审批**：`8D-E2E-DOCGATE-001`（`_seed_doc_gate_capa` 产出，`D8_GATE_PENDING`）——01.7 负责推进到 `D8_APPROVAL_PENDING`；01.3 随后 `capa-approve` → `D8_CLOSURE`。
   - **post-gate 驳回**：`8D-E2E-APPROVAL-001`（`_seed_d4_audit` 产出，`D8_APPROVAL_PENDING`）——01.3 `capa-reject` → `D7_PREVENTION`。此 CAPA 不被其他子 story 消费。
   - 三条 CAPA 各自独立：pre-gate 不复用 01.4 的 seed；审批与驳回在不同 CAPA 上操作（避免状态冲突）。

## 状态机与角色（必读，勿写反）

| 边 | 操作者 | 权限 | UI |
|---|---|---|---|
| D4_ROOT_CAUSE → D5_CORRECTION … → D7_PREVENTION | engineer | capa EDIT | `[data-e2e="capa-advance"]` |
| D7_PREVENTION → D7_COMPLETED | engineer | capa EDIT | `[data-e2e="capa-advance"]`（可带 d7_skip_reasons） |
| D7_COMPLETED → D8_GATE_PENDING | engineer | capa EDIT | `[data-e2e="capa-advance"]` |
| D8_GATE_PENDING → D8_APPROVAL_PENDING | engineer | capa EDIT + 文档门禁 decision=passed | DocGate 区 `[data-e2e="doc-gate-advance"]`（01.7） |
| D8_APPROVAL_PENDING → D8_CLOSURE | **manager** | capa **APPROVE** | `[data-e2e="capa-approve"]`（不是 capa-advance） |
| D8_APPROVAL_PENDING → D7_PREVENTION（驳回） | **manager** | capa **APPROVE** | `[data-e2e="capa-reject"]` + `[data-e2e="capa-reject-reason"]` |

**禁止错误叙述**：「engineer 不能推进 D7」「manager 推进 D7→D8 门禁」。engineer 推进到门禁/待审批；manager 只做关闭审批与驳回。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="d4-verification-new"]` | 新建验证入口 |
| `[data-e2e="d4-verification-card"]` | 验证卡片 |
| `[data-e2e="verification-method"]` | 验证方法 |
| `[data-e2e="verification-result"]` | 结果 |
| `[data-e2e="verification-evidence"]` | 证据 |
| `[data-e2e="verify-pass"]` / `verify-fail` / `verify-save-draft` | 结论提交（新建） |
| 已有记录行 | `verify-pass-{i}` / `verify-fail-{i}`（实现为索引后缀，断言时用前缀） |
| `[data-e2e="d7-auto-fill"]` | AI 填充预防 |
| `[data-e2e="d7-confirm"]` | 确认预防项 |
| `[data-e2e="d7-skip"]` | 跳过（需理由） |
| `[data-e2e="capa-advance"]` | 线性/壳推进（非审批） |
| `[data-e2e="capa-approve"]` | manager 批准关闭 |
| `[data-e2e="capa-reject"]` | manager 驳回 |
| `[data-e2e="capa-reject-reason"]` | 驳回理由 |

## 走查剧本

> 本子故事按 pre-gate / post-gate 分两段。pre-gate 在 01.7 之前跑（推进到 `D8_GATE_PENDING` 停）；post-gate 在 01.7 之后跑（审批壳）。无 LLM → 两段都 BLOCKED。

### A. D4 现场验证（pre-gate）
- engineer 登录 → 进 `8D-E2E-D4-001`（`D4_ROOT_CAUSE`，FMEA 已挂）。
- **(a) 闸口阻断（先做）**：无 D4 验证记录时点 `[data-e2e="capa-advance"]` → 断言 `status` 仍为 `D4_ROOT_CAUSE`（阻断通过）。
- **(b) 提交验证**：`[data-e2e="d4-verification-new"]` → 填 method/result/evidence → 点 `[data-e2e="verify-pass"]`。
- **(c) 闸口放行**：`GET /api/capa/{id}/root-cause-verifications` 含该记录，`conclusion=passed`。`[data-e2e="capa-advance"]` → `status=D5_CORRECTION`。

### B. D7 node-action（pre-gate）
- engineer 推进到 `D7_PREVENTION` → D7RecPanel 渲染（linked/keyword/rule 分组）。
- 对项：`d7-auto-fill`（需 LLM/FMEA）/ `d7-confirm` / `d7-skip`（填理由）。**无 LLM → 整个 01.3 标 `BLOCKED`**（auto-fill 不可降级为 skip）。有 LLM 但 auto-fill 缺失/失败 → **FAIL**（实现缺陷）。
- **断言**：`GET /api/capa/{id}/d7-node-actions` ≥ 1；skip 有理由。rule 兜底项（`fmea_id=null`）仅在无 linked/keyword 推荐时生成，当前 seed 有全文匹配命中，不预期 rule 项——断言 rule 存在会误 FAIL。
- engineer 点 `[data-e2e="capa-advance"]` → `D7_COMPLETED`（全部 confirm 或带 skip reasons）。
- 再 advance → `D8_GATE_PENDING`。**pre-gate 到此为止，不推进到 `D8_APPROVAL_PENDING`**（那是 01.7 的职责；01.7 在 `8D-E2E-DOCGATE-001` 上做）。

### C. 审批壳（post-gate）

路径拆分（与编排器一致；**不得**因 01.7 非通过而整段跳过 post-gate）：

| 子路径 | CAPA | 依赖 01.7？ | 01.7 BLOCKED（无 LLM） | 01.7 FAIL（LLM/产品缺陷等，未到 `D8_APPROVAL_PENDING`） |
|---|---|---|---|---|
| **(a) 权限** | `8D-E2E-APPROVAL-001` | **否**（seed 已是 `D8_APPROVAL_PENDING`） | 仍可跑 | **仍可跑** |
| **(b) 驳回** | `8D-E2E-APPROVAL-001` | **否** | 仍可跑 | **仍可跑** |
| **(c) 审批** | `8D-E2E-DOCGATE-001` | **是**（须 01.7 推到 `D8_APPROVAL_PENDING`） | 该子路径 `BLOCKED` | 该子路径 `BLOCKED（前置 01.7 未通过）` |

- **(a) 权限（先做）**：**engineer** → 进 `8D-E2E-APPROVAL-001` → `[data-e2e="capa-approve"]` **不可见**。须在 manager 改状态前。
- **(b) 驳回**：manager → `8D-E2E-APPROVAL-001` → `[data-e2e="capa-reject"]` + reason → `status=D7_PREVENTION`；审计 `D8_REJECTED`。
- **(c) 审批**：仅当 01.7 已使 `8D-E2E-DOCGATE-001` 为 `D8_APPROVAL_PENDING` 时：manager → approve → `D8_CLOSURE`（`D8_APPROVED`）。否则本子路径 `BLOCKED`，**不**把 (a)(b) 一并 BLOCKED。

**禁止**：01.7 FAIL 后把整个 post-gate（含权限/驳回）标 BLOCKED。

### D. 审计
- `TRANSITION`（D4→D5 等 engineer 边）；`D7_SKIP_CONFIRMATION`（若 skip）；`D8_APPROVED` / `D8_REJECTED`（manager）；`ADOPT_RECOMMENDATION`（若 D4 采纳）。

## UI 截图清单（强制）

遵循编排器「UI 截图验证契约」。工具：`browser_take_screenshot` → `REPORT_ROOT/01.3/screenshots/`。

| 步骤 | 界面 | 文件 | 必查 |
|---|---|---|---|
| A | D4 验证新建表单 | `A-d4-verify-form.png` | method/result/evidence 控件可见 |
| A | 验证通过后卡片 | `A-d4-verify-card.png` | conclusion=passed 展示 |
| B | D7RecPanel（confirm/skip/auto-fill） | `B-d7-panel.png` | 推荐分组渲染；`d7-confirm`/`d7-skip` 可见 |
| B | 推进到 `D8_GATE_PENDING` | `B-gate-pending.png` | 状态 Tag 正确 |
| C-a | engineer 在 APPROVAL CAPA（无 approve 按钮） | `C-eng-no-approve.png` | `capa-approve` **不可见** |
| C-b | 驳回后 `D7_PREVENTION` | `C-reject.png` | 状态回退；reject 反馈 |
| C-c | 审批后 `D8_CLOSURE`（若 01.7 通过） | `C-approve-closed.png` | 状态 Tag=关闭；否则本行 BLOCKED |

每步 PASS 也截；视觉 FAIL 判据见编排器契约。子报告填「## UI 截图」表。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.3/report.md`，用编排器契约模板。pre-gate / post-gate 分开列表；post-gate 内 (a)(b)(c) 分行，标注 (c) 是否因 01.7 BLOCKED/FAIL 而 BLOCKED。UI 基线 + FAIL/MISSING 截图存 `screenshots/`；子报告须含「## UI 截图」表。

## 缺陷分类

步骤级：`PASS` / `FAIL` / `MISSING` / `BLOCKED`（备注写说明；**不用** PASS-NOTE）。整单总体结论：`PASS` / `FAIL` / `BLOCKED`。

- pre-gate / post-gate 分开记。
- post-gate **(c)** 因 01.7 BLOCKED 或 FAIL → `BLOCKED`（不是 FAIL）。
- post-gate **(a)(b)** 在 01.7 FAIL 时仍可 `PASS`/`FAIL`（独立 seed）。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
