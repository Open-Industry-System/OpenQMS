---
name: verify-capa-8d-d4-d7-audit
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D D4 verification + D7 node-action + approval shell (US-E2E-01.3). Symptoms include checking root cause verification flow, D7 FMEA node-actions, D7→D8 approval gate, or rejection rollback.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.3-d4-verification-d7-node-action.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-d4-d7-audit

## Overview

走查 US-E2E-01.3：D4 根因现场验证（method/result/evidence/verified）→ D4→D5 闸口（已验证 root_cause_text 一致）→ D7 node-action（linked/keyword/rule 三类，confirm/skip 落库）→ D7→D8 审批壳（manager 可，engineer 不可，驳回回退 D7）。

## When to Use

**用**：用户说「验收 01.3」「走查 D4 验证」「验证 D7 node-action」「检查审批壳」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. LLM 凭证齐。
4. seed-state 取 engineer/manager 账号。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="d4-verification-new"]` | 新建验证表单 |
| `[data-e2e="verification-method"]` | 验证方法 input |
| `[data-e2e="verification-result"]` | 结果 textarea |
| `[data-e2e="verification-evidence"]` | 证据上传 |
| `[data-e2e="verification-form-is-verified"]` | 新建表单已验证 Switch |
| `[data-e2e="verification-submit"]` | 提交 |
| `[data-e2e="d7-auto-fill"]` | AI 填充预防 |
| `[data-e2e="d7-confirm"]` | 确认预防项 |
| `[data-e2e="d7-skip"]` | 跳过（需理由） |
| `[data-e2e="capa-advance"]` | 推进 |

## 走查剧本

### A. D4 现场验证
- engineer 登录 → 进 D4 CAPA → 点 `[data-e2e="d4-verification-new"]` → 填 method/result → 上传证据 → 勾 form-is-verified → submit。
- **断言**：`GET /api/capa/{id}/root-cause-verifications` 含该记录，`is_verified=true`。
- **闸口**：未验证时 D4→D5 阻断；验证后推进成功，`status=D5_CORRECTION`。

### B. D7 node-action
- 推进到 D7_PREVENTION → D7RecPanel 渲染（linked/keyword/rule 分组）。
- 对每项：`d7-auto-fill`（FMEA 命中）/ `d7-confirm` / `d7-skip`（填理由）。
- **断言**：`GET /api/capa/{id}/d7-node-actions` ≥ 1 条；rule 兜底项 `fmea_id=null`；skip 项有理由。

### C. 审批壳
- engineer 此时不能推进 D7→D8（`capa-advance` 禁用/不可见）。
- manager 登录 → 进详情 → `[data-e2e="capa-advance"]` 推进 → `status=D8_GATE_PENDING`（或直接 D8_APPROVAL_PENDING，视 01.7 门禁）。
- **驳回**：manager 点驳回 → 填理由 → `status=D7_PREVENTION`；审计含 `D7_SKIP_CONFIRMATION`（若跳过）+ TRANSITION。

### D. 审计
- TRANSITION D4→D5（engineer）、D7→D8（manager）；`ADOPT_RECOMMENDATION`（若 D4 采纳）。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
