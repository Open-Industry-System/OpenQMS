---
name: verify-capa-8d-supplier-risk-input
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D → supplier risk rating input (US-E2E-01.6). Symptoms include checking risk input generation after D7 complete, repeat detection, or confirmation flow.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.6-supplier-risk-input.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-supplier-risk-input

## Overview

走查 US-E2E-01.6 8D → 供应商风险评级输入：`D7_PREVENTION`→`D7_COMPLETED` 时写 outbox → worker 处理（重复检测 + 风险等级）→ CAPA 详情确认/否认 → 审计。

## When to Use

**用**：用户说「验收 01.6」「走查供应商风险输入」「验证 CAPA D7 完成后风险输入」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑（backend lifespan 启动 30s risk input worker；进程不跑 loop 则 outbox 永挂 pending）。
3. seed-state 取 engineer/manager/admin 账号。
4. seed 中有：
   - `8D-E2E-RISK-001`：**`D7_PREVENTION`**（含 `supplier_id` + D7 action）——**不是** D8_APPROVAL_PENDING
   - `8D-E2E-RISK-HIST-001`：历史重复 CAPA

## 角色边界（禁止写反）

| 动作 | 角色 | 权限 |
|---|---|---|
| advance `D7_PREVENTION`→`D7_COMPLETED` | **engineer** | capa EDIT |
| `POST /confirm-repeat` | **manager**（或兼有 supplier_risk EDIT 的账号） | capa EDIT **∧** supplier_risk EDIT |
| engineer 对 supplier_risk | VIEW only | **403** 若调 confirm-repeat |

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="capa-advance"]` | engineer 推进 D7_COMPLETED |
| `[data-e2e="supplier-risk-input-card"]` | 风险输入卡片 |
| `[data-e2e="supplier-risk-input-status"]` | 状态 Tag |
| `[data-e2e="supplier-risk-input-prompt"]` | 待确认提示 |
| `[data-e2e="supplier-risk-confirm-yes"]` / `confirm-no` | 确认/否认重复 |
| `[data-e2e="supplier-risk-input-confirmed"]` | 已确认文案 |

## 走查剧本

### A. D7 完成触发风险输入
- engineer 登录 → 进 `8D-E2E-RISK-001`（断言 seed status=`D7_PREVENTION`，`supplier_id` 非空）。
- 点 `[data-e2e="capa-advance"]` 或 `POST /api/capa/{id}/advance` `target_state=D7_COMPLETED`。
- **断言**：status=`D7_COMPLETED`；`GET /api/capa/{id}` `supplier_risk_input` 非空，`status` ∈ {pending, processing, processed}。
- 中间审计可有 `action=SUPPLIER_RISK_INPUT_QUEUED`（outbox 入队）。

### B. Worker 处理 + 重复检测
- 轮询 `supplier_risk_input.status=processed`（≤ 90s）。
- **断言**：`repeat_suggested=true`、`repeat_detection_status=matched`、`matched_capa_nos` 含 `8D-E2E-RISK-HIST-001`、`evaluated_risk_level`/`evaluated_at` 非空。
- **审计**：`GET /api/admin/logs/audit?table_name=capa_eightd&action=SUPPLIER_RISK_INPUT_SENT&start={t0_iso}&page_size=200`，客户端按 `record_id == {capa_id}` 和 `operated_at >= t0` 过滤后 ≥ 1（`changed_fields` 含 disposition/severity/risk_level）。（API 不接收 `record_id` 参数。）

### C. 确认/否认（manager）
- **manager** 登录 → 进详情 → `[data-e2e="supplier-risk-input-card"]` → `[data-e2e="supplier-risk-confirm-yes"]` 或 `confirm-no`。
- **断言**：`POST /api/capa/{id}/confirm-repeat` body `{repeat_confirmed: true|false}` 200；投影 `repeat_confirmed` 对应；`evaluated_at` 更新。
- engineer 调 confirm-repeat → **403**（supplier_risk 仅 VIEW）。
- **审计**：`action=SUPPLIER_RISK_CHANGED`（`old_level`/`new_level`/`repeat_confirmed` 字段存在）。

### D. CAPA 产品线冻结
- **断言**：`product_line_code` 在 D7+ 后不可随意修改（update 422/400，按实现冻结守卫）。

## 缺陷分类

PASS / FAIL / MISSING / BLOCKED（备注写说明；不用 PASS-NOTE）。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.6/report.md`，用编排器契约模板。FAIL/MISSING 截图存 `screenshots/`。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
