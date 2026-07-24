---
name: verify-capa-8d-scar-trigger
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D → SCAR trigger and write-back (US-E2E-01.5). Symptoms include checking SCAR creation from CAPA, bidirectional link, D3 lot association, or SCAR status write-back.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.5-scar-trigger.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-scar-trigger

## Overview

走查 US-E2E-01.5 8D → SCAR 触发：CAPA 详情页触发 SCAR → 供应商选择 → D3 受影响批次关联 → SCAR 创建 → CAPA↔SCAR 双向链接 → SCAR 状态回写。

## When to Use

**用**：用户说「验收 01.5」「走查 SCAR 触发」「验证 8D 转 SCAR」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. seed-state 取 engineer/manager 账号。
4. seed 中有 `8D-E2E-SCAR-001`（D3_INTERIM+，含 D3 批次数据）。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="capa-trigger-scar"]` | 触发 SCAR |
| `[data-e2e="capa-linked-scar"]` | 已关联 SCAR 展示 |

## 走查剧本

### A. 触发 SCAR
- engineer 登录 → 进 `8D-E2E-SCAR-001` → 点 `[data-e2e="capa-trigger-scar"]` → 填供应商/描述 → 提交。
- **断言**：`POST /api/capa/{id}/trigger-scar` 200；`GET /api/capa/{id}` `scar_ref_id` 非空、`linked_scar` 含 scar_no/status。

### B. 双向链接
- 进 SCAR 详情 → 关联 CAPA。
- **断言**：SCAR `capa_ref_id` = 原 CAPA report_id；CAPA 侧 `[data-e2e="capa-linked-scar"]` 可见。

### C. D3 批次关联
- **断言**：SCAR `affected_batches` 含 seed 批次（如 `LOT-E2E-SCAR-001`）；CAPA GET 投影字段 `d3_affected_lots` 一致。
- **注意**：批次在 `GET /api/capa/{id}` 的 `d3_affected_lots` 投影中，无独立 lots 子路由。

### D. 状态回写
- SCAR 状态变更 → CAPA 详情 `linked_scar.status` 同步。
- **断言**：`GET /api/capa/{id}` `linked_scar.status` = SCAR 当前状态。

### E. 审计
- `GET /api/admin/logs/audit?table_name=capa_eightd&action=SCAR_TRIGGERED&start={t0_iso}&page_size=200`，客户端按 `record_id == {capa_id}` 和 `operated_at >= t0` 过滤后 ≥ 1。（API 不接收 `record_id` 参数。）
- 状态回写：`action=SCAR_STATUS_SYNCED`。

## 缺陷分类

PASS / FAIL / MISSING / BLOCKED（备注写说明；不用 PASS-NOTE）。

## UI 截图清单（强制）

遵循编排器「UI 截图验证契约」。工具：`browser_take_screenshot` → `REPORT_ROOT/01.5/screenshots/`。

| 步骤 | 界面 | 文件 | 必查 |
|---|---|---|---|
| A | CAPA 触发 SCAR 入口/表单 | `A-trigger-form.png` | `capa-trigger-scar` 可见；表单可填 |
| A | 触发成功后 CAPA 侧链接 | `A-linked-scar.png` | `capa-linked-scar` 展示 scar_no/status |
| B | SCAR 详情双向 CAPA 链接 | `B-scar-detail.png` | capa_ref 可见 |
| D | 状态回写后 CAPA `linked_scar` | `D-status-sync.png` | status 与 SCAR 一致 |

每步 PASS 也截；视觉 FAIL 判据见编排器契约。子报告填「## UI 截图」表。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.5/report.md`，用编排器契约模板。UI 基线 + FAIL/MISSING 截图存 `screenshots/`；子报告须含「## UI 截图」表。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
