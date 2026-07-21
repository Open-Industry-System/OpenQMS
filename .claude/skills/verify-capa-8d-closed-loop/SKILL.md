---
name: verify-capa-8d-closed-loop
description: Use when asked to verify / walk through / 验收 / 走查 the OpenQMS CAPA 8D closed-loop epic (US-E2E-01) end-to-end — e.g. "验收 US-E2E-01" / "walk through the 8D closed-loop" / "端到端走查 epic". Orchestrates 10 sub-skills covering all sub-stories 01.1–01.10.
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
| 01.7 D8 文档门禁 | 定稿 v1（2026-07-08） | `verify-capa-8d-doc-update-gate` | true |
| 01.8 知识库沉淀 | 定稿 v1（2026-07-08） | `verify-capa-8d-knowledge-sink` | true |
| 01.9 横向扩散 | 定稿 v2（2026-07-21） | `verify-capa-8d-lateral-diffusion` | true |
| 01.10 PPT 输出 | 定稿 v4（2026-07-09） | `verify-capa-8d-ppt-output` | false（审查需 LLM） |

## 前置（编排器级）

1. **Epic 版本一致**：读本 skill 顶部「Epic 版本」，与 `README.md` 顶部比对；不一致 → 停下，提示用户先同步。
2. **e2e 栈在跑**：`curl -sf http://localhost:5174`。不可达 → `make e2e-up && make e2e-seed`。
3. **LLM 凭证**：读 `.env.e2e`。缺 → 提示配置；AI_REQUIRED=true 的子故事无法验收，但 AI_REQUIRED=false 的子故事仍可跑。
4. **拿账号**：`GET /api/e2e/seed-state`。

## 执行顺序

按 8D 业务流程顺序执行，每个子 skill 独立输出子报告：

```
01.1 D3 遏制
  ↓
01.2 推荐 12 源（D4/D5）
  ↓
01.3 D4 验证 + D7 node-action + 审批壳
  ↓
01.4 FMEA 双向
  ↓
01.5 SCAR 触发
  ↓
01.6 供应商风险输入
  ↓
01.7 D8 文档门禁
  ↓
01.8 知识库沉淀
  ↓
01.9 横向扩散
  ↓
01.10 PPT 输出
```

**跳过策略**：若某子 skill 因前置不满足（如无 LLM 凭证）无法执行，在总报告中标记 `BLOCKED` 并说明原因，继续下一个子 skill，**不**整体终止。

## 报告汇总

每个子 skill 在其自己的 `docs/e2e/reports/US-E2E-01.<n>-<YYYY-MM-DD>/report.md` 输出子报告。编排器额外生成 epic 级总览：

```
docs/e2e/reports/US-E2E-01-epic-<YYYY-MM-DD>/
  report.md          ← epic 总览（汇总各子报告 PASS/FAIL/BLOCKED 计数）
  screenshots/       ← 各子 skill 截图的符号链接或汇总
```

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
- [01.1](../US-E2E-01.1-<date>/report.md)
- ...
```

## 维护（同步）

本编排器是 README 的单向派生。每次跑前：

1. 读 skill 顶部「Epic 版本」。
2. 读 `docs/user-stories/US-E2E-01-capa-8d-closed-loop/README.md` 顶部版本。
3. 一致 → 直接跑。
4. 不一致 → 停下，提示：「Epic README 已更新到 vX，编排器仍停在 vY，需同步后再跑。要我现在同步吗？」
   - 同步 = 重读 README → 核对子 skill 列表/版本 → 更新本文件 → 重跑。

各子 skill 的维护规则见其自身 SKILL.md（与对应子故事版本比对）。
