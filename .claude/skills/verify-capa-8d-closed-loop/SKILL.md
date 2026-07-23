---
name: verify-capa-8d-closed-loop
description: Use when asked to verify / walk through / 验收 / 走查 the OpenQMS CAPA 8D closed-loop epic (US-E2E-01) end-to-end — e.g. "验收 US-E2E-01" / "walk through the 8D closed-loop" / "端到端走查 epic".
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/README.md
> Epic 版本：v8.1（2026-07-08）
> 子故事版本表：见下表
> 同步规则：当 README 版本号变更，本编排器必须重新核对并同步（见「维护」）。

# verify-capa-8d-closed-loop（编排器）

## Overview

US-E2E-01 已升级为 epic 合集 v8.1（10 个子故事）。本 skill 是**编排器**，不直接执行走查步骤，而是按顺序调用 10 个子 skill，汇总各子 skill 的验收报告，输出 epic 级总览。

这是 acceptance walk（人可读验收报告），不是 Playwright spec——spec 写在 `frontend/e2e/specs/`。

## When to Use

**用**：用户说「验收 US-E2E-01」「走查 8D 闭环 epic」「端到端走查全部子故事」等。
**不用**：只验收单个子故事（直接调用对应子 skill）；写/改 Playwright spec；AI 推荐准确率评测。

## 子故事 × 子 skill 映射

| 子故事 | 状态 | 子 skill | AI_REQUIRED |
|---|---|---|---|
| 01.1 D3 遏制 | 实现态 v4（2026-07-12） | `verify-capa-8d-d3-containment` | true |
| 01.2 推荐 12 源 | 定稿 v1（2026-07-08） | `verify-capa-8d-recommendation-sources` | true |
| 01.3 D4 验证 + D7 node-action + 审批壳 | 定稿 v1（2026-07-08） | `verify-capa-8d-d4-d7-audit` | true |
| 01.4 8D↔FMEA 双向 | 定稿 v1（2026-07-08） | `verify-capa-8d-fmea-linkage` | false |
| 01.5 8D→SCAR 触发 | 定稿 v1（2026-07-08） | `verify-capa-8d-scar-trigger` | false |
| 01.6 供应商风险输入 | 定稿 v1（2026-07-08） | `verify-capa-8d-supplier-risk-input` | false |
| 01.7 D8 文档门禁 | 定稿 v2（2026-07-23） | `verify-capa-8d-doc-update-gate` | true |
| 01.8 知识库沉淀 | 定稿 v1（2026-07-08） | `verify-capa-8d-knowledge-sink` | true |
| 01.9 横向扩散 | 定稿 v2（2026-07-21） | `verify-capa-8d-lateral-diffusion` | true |
| 01.10 PPT 输出 | 定稿 v4（2026-07-09） | `verify-capa-8d-ppt-output` | false（审查需 LLM） |

## 前置（编排器级）

1. **Epic 版本一致**：读本 skill 顶部「Epic 版本」，与 `README.md` 顶部比对；不一致 → 停下，提示用户先同步。
2. **e2e 栈在跑**：`curl -sf http://localhost:5174`。不可达 → `make e2e-up && make e2e-seed`。
   **必须 reseed**：**每次**开始整套验收前执行 `make e2e-seed`（无论栈是否已在跑），确保所有 seed CAPA 恢复起始状态。重复验收若跳过 reseed，之前 walk 改变的状态会造成误 FAIL。
3. **LLM 凭证**：**有效运行配置优先来自 DB `system_settings`，缺值才回退 `.env.e2e`**——不能只读 `.env.e2e`（DB 配置可覆盖 env）。用 `GET /api/admin/ai-config`（读有效配置）或 `POST /api/admin/ai-config/test`（连通性测试）校验。按 provider 判断必需项（`anthropic`/`claude` 需 `LLM_API_KEY`；`openai`/`deepseek`/`ark` 需 `LLM_API_KEY`；`local`/`ollama` 需 `LLM_BASE_URL`+`LLM_MODEL`——**不**要求四项全非空）。缺 → AI_REQUIRED=true 的子故事（01.1/01.2/01.3/01.7/01.8/01.9）在该子 skill 内标记 `BLOCKED`（不是「无法验收」的软跳过）；AI_REQUIRED=false 的子故事仍可跑。
4. **拿账号**：`GET /api/e2e/seed-state`。

## 执行顺序

按 8D 业务流程顺序执行，每个子 skill 独立输出子报告：

```
01.1 D3 遏制
  ↓
01.2 推荐 12 源（D4/D5）
  ↓
01.3 pre  D4 验证 + D7 node-action → D8_GATE_PENDING（停）
  ↓
01.4 FMEA 双向
  ↓
01.5 SCAR 触发
  ↓
01.6 供应商风险输入
  ↓
01.7 D8 文档门禁 → D8_APPROVAL_PENDING
  ↓
01.3 post  审批壳（审批/驳回/权限）← 依赖 01.7 产出
  ↓
01.8 知识库沉淀
  ↓
01.9 横向扩散
  ↓
01.10 PPT 输出
```

**01.3 的前/后门禁拆分**：01.3 用三条独立 seed CAPA：

- **01.3 pre-gate**（在 01.7 之前跑）：在 `8D-E2E-D4-001`（`_seed_d4_audit` 产出，`D4_ROOT_CAUSE`，挂 FMEA）上做 D4 验证 → D7 node-action → `D7_COMPLETED` → `D8_GATE_PENDING`。**不**断言 `D8_APPROVAL_PENDING`。
- **01.7** 在 `8D-E2E-DOCGATE-001`（D8_GATE_PENDING）上跑门禁 → `D8_APPROVAL_PENDING`。
- **01.3 post-gate**（在 01.7 之后跑）：驳回在 `8D-E2E-APPROVAL-001`（`_seed_d4_audit` 产出，`D8_APPROVAL_PENDING`）；审批在 `8D-E2E-DOCGATE-001`（01.7 产出）。两条 CAPA 互不污染（避免审批后无法驳回的状态冲突）。若 01.7 因无 LLM BLOCKED，则 post-gate 两路径均标 `BLOCKED`，**不**软跳过。**若 01.7 FAIL**（LLM/产品缺陷等，未推进到 `D8_APPROVAL_PENDING`；**不再**因缺 SOP 必然 FAIL——故事 v2 验收范围 = CP+FMEA），则 01.3 审批路径标 `BLOCKED（前置 01.7 未通过）`；驳回路径不依赖 01.7，照常验收。

**跳过/传播策略**：
- 子 skill 因前置不满足（如无 LLM 凭证）无法执行 → 总报告标 `BLOCKED`，继续下一个，**不**整体终止；AI_REQUIRED=true 子故事 BLOCKED 时记 `BLOCKED`，**不**记 PASS 伪装通过。
- 子 skill **FAIL**（发现实现缺陷，如 LLM 失败、FMEA 不可写字段导致无法 passed）→ 总报告记 `FAIL` 并汇总缺陷；其后依赖该子 skill 产出的步骤若前置状态未达成，按上面规则标 `BLOCKED` 或如实记录可独立验收的部分。FAIL **不**自动阻断无依赖的后续子 skill。
- 任何情况下，**不**为让后续步骤「有状态可测」而人为制造本不应存在的成功状态（如 01.7 不该强行 passed）。

## 报告汇总（一次走查 = 一个日期文件夹）

**禁止**为每个子故事各建顶层日期目录。整 epic 或单子故事，同一天同一轮走查的全部产出都落在：

```
docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/
  report.md                 ← epic 总览（仅编排器整跑时写；单子故事走查可省略）
  01.1/report.md            ← 子报告（相对路径 screenshots/ 指向同级目录）
  01.1/screenshots/         ← 该子故事 FAIL/MISSING 截图
  01.2/report.md
  01.2/screenshots/
  …
  01.10/report.md
  01.10/screenshots/
  evidence/                 ← 可选：跨子故事共享证据（现场附件等）
```

编排器开跑时**先**创建 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/`，并把该绝对路径作为本轮 `REPORT_ROOT` 传给每个子 skill（口头约定即可：子 skill 写 `REPORT_ROOT/01.<n>/report.md`）。单子故事单独验收时，也创建同一 `REPORT_ROOT`，只写自己的 `01.<n>/`。

同日二次整跑：若 `REPORT_ROOT` 已存在且含 `report.md`，新建 `US-E2E-01-<YYYY-MM-DD>-2/`（再跑递增 `-3`…），**不**覆盖上一轮。

总览模板：

```markdown
# US-E2E-01 Epic 验收总览 — <date>

- Epic 版本：v8.1（2026-07-08）
- 走查时间：<开始> ~ <结束>
- LLM 凭证：齐全 / 缺

| 子故事 | 子 skill | 状态 | PASS | FAIL | MISSING | BLOCKED |
|---|---|---|---|---|---|---|
| 01.1 | d3-containment | PASS | N | 0 | 0 | — |
| ... |

## 总体结论
- 全部 PASS / 有缺陷 / BLOCKED（缺 LLM）

## 缺陷汇总
（各子 skill FAIL/MISSING 条目汇总）

## 各子报告链接
- [01.1](01.1/report.md)
- [01.2](01.2/report.md)
- ...
```

## 子报告契约（所有子 skill 必须遵守）

每个 `verify-capa-8d-*` 子 skill 在其 SKILL.md 末尾必须有「## 子报告输出」节，按此模板产出 `REPORT_ROOT/01.<n>/report.md`：

```markdown
# US-E2E-01.<n> <子故事名> 验收报告 — <YYYY-MM-DD>

- 故事版本：< vX（日期） >
- 走查时间：<开始> ~ <结束>
- LLM 凭证：齐全 / 缺
- AI_REQUIRED：true / false

| 步骤 | 断言 | 结果 | 备注 |
|---|---|---|---|
| A. ... | ... | PASS/FAIL/MISSING/BLOCKED | ... |

## 总体结论
PASS / FAIL / BLOCKED

## 缺陷清单
- [FAIL] <步骤>：<期望> vs <实际>（截图：screenshots/xxx.png）
```

**结果枚举**：

| 层级 | 允许值 | 说明 |
|---|---|---|
| 步骤「结果」列 | `PASS` / `FAIL` / `MISSING` / `BLOCKED` | **禁止** `PASS-NOTE`。说明性限制（seed 预置、审查因无 LLM 跳过等）写在 **备注** 列；步骤结果仍用四态之一（断言成立→`PASS`+备注；前置缺→`BLOCKED`；实现缺→`FAIL`）。 |
| 总体结论 | `PASS` / `FAIL` / `BLOCKED` | 任一步 FAIL → 总体 FAIL；仅有 BLOCKED 无 FAIL → BLOCKED；全 PASS → PASS。 |

子 skill 没写「## 子报告输出」节 = 契约缺失，编排器聚合时会报 `MISSING`。

本编排器是 README 的单向派生。每次跑前：

1. 读 skill 顶部「Epic 版本」。
2. 读 `docs/user-stories/US-E2E-01-capa-8d-closed-loop/README.md` 顶部版本。
3. 一致 → 直接跑。
4. 不一致 → 停下，提示：「Epic README 已更新到 vX，编排器仍停在 vY，需同步后再跑。要我现在同步吗？」
   - 同步 = 重读 README → 核对子 skill 列表/版本 → 更新本文件 → 重跑。

各子 skill 的维护规则见其自身 SKILL.md（与对应子故事版本比对）。
