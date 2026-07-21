---
name: verify-capa-8d-supplier-risk-input
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D → supplier risk rating input (US-E2E-01.6). Symptoms include checking supplier risk input generation from CAPA close, repeat detection, risk level evaluation, or confirmation flow.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.6-supplier-risk-input.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-supplier-risk-input

## Overview

走查 US-E2E-01.6 8D → 供应商风险评级输入：CAPA 关闭后自动生成 supplier_risk_input → 重复检测（matched/not_matched）→ 风险等级评估 → CAPA 详情页确认/否认 → 审计。

## When to Use

**用**：用户说「验收 01.6」「走查供应商风险输入」「验证 CAPA 关闭后风险输入」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. seed-state 取 engineer/manager/admin 账号。
4. seed 中有 `8D-E2E-RISK-001`（D8_APPROVAL_PENDING，含 supplier_id + D7 action）和 `8D-E2E-RISK-HIST-001`（历史重复 CAPA）。

## 走查剧本

### A. 关闭触发风险输入
- manager 登录 → 进 `8D-E2E-RISK-001` → `[data-e2e="capa-advance"]` 推进 D8→D8_CLOSURE。
- **断言**：`GET /api/capa/{id}` `supplier_risk_input` 非空，`status` ∈ {pending, processing, processed}。

### B. 重复检测
- 等待 worker 处理（轮询 `supplier_risk_input.status=processed`，≤ 90s）。
- **断言**：`repeat_suggested=true`、`repeat_detection_status=matched`、`matched_capa_nos` 含 `8D-E2E-RISK-HIST-001`、`evaluated_risk_level` 非空、`evaluated_at` 非空。

### C. 确认/否认
- engineer 登录 → 进详情 → `[data-e2e="supplier-risk-input-card"]` → 点 `[data-e2e="supplier-risk-confirm-yes"]`（确认重复）或 `[data-e2e="supplier-risk-confirm-no"]`。
- **断言**：`POST /api/capa/{id}/confirm-repeat` 200；`GET /api/capa/{id}` `supplier_risk_input.repeat_confirmed` = true/false；风险重新评估（`evaluated_at` 更新）。

### D. 审计
- `GET /api/admin/logs/audit?table_name=capa_eightd&action=SUPPLIER_RISK_INPUT_SENT&record_id={id}` ≥ 1。
- 确认后 `SUPPLIER_RISK_CHANGED` 审计（若风险等级变化）。

### E. CAPA 产品线冻结
- **断言**：`8D-E2E-RISK-001` 的 `product_line_code` 在关闭后不可修改（update 尝试应 422/400）。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
