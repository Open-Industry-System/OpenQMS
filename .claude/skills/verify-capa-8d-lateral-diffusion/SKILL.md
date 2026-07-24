---
name: verify-capa-8d-lateral-diffusion
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D lateral diffusion alert (US-E2E-01.9). Symptoms include checking lateral modal after D8 close, decide API, or LATERAL_DIFFUSION_CHECKED audit.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.9-lateral-diffusion.md
> 故事版本：定稿 v2（2026-07-21）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-lateral-diffusion

## Overview

走查 US-E2E-01.9 横向扩散预警：D8 关闭后自动检查类似产品（4 依据并集：same_product_type / shared_fmea_mode / shared_control_plan / same_supplier_material）→ LLM 生成 suggestion_direction → Modal 弹出 → notify/skip 决策 → 通知记录落库 → 审计。

## When to Use

**用**：用户说「验收 01.9」「走查横向扩散」「验证 lateral diffusion」等。

## 前置

1. 故事版本一致（比对 `US-E2E-01.9-lateral-diffusion.md` 顶部：定稿 v2（2026-07-21））。
2. e2e 栈在跑（`:5174`）。
3. LLM 凭证齐（有命中时需 LLM；无凭证 → BLOCKED）。
4. seed-state 取 manager/admin 账号。
5. seed 中有 `8D-E2E-LATERAL-001`（notify）、`8D-E2E-LATERAL-002`（skip）、`8D-E2E-LATERAL-BLOCK`、`8D-E2E-LATERAL-EMPTY`（均 D8_APPROVAL_PENDING）。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="lateral-diffusion-modal"]` | 弹窗 |
| `[data-e2e="lateral-hit-<type>"]` | 每个命中产品类型块 |
| `[data-e2e="lateral-decide-notify"]` | 通知全部按钮 |
| `[data-e2e="lateral-decide-skip"]` | 不通知按钮（需理由） |
| `[data-e2e="lateral-skip-reason"]` | 不通知理由 textarea |
| `[data-e2e="lateral-diffusion-card"]` | 常驻卡片 |
| `[data-e2e="lateral-notifications"]` | 通知记录列表 |

## 走查剧本

> 所有 seed CAPA 均处于 `D8_APPROVAL_PENDING`。关闭 = manager 点 `[data-e2e="capa-approve"]`（`capa-advance` 在该状态下不渲染）。

### A. 001 关闭 → 四依据并集
- manager 登录 → 进 `8D-E2E-LATERAL-001` → 点 `[data-e2e="capa-approve"]` 关闭（`D8_APPROVAL_PENDING`→`D8_CLOSURE`）。
- 无 LLM → 422 `outcome=blocked`（fail-closed，关闭链阻断）。
- 有 LLM → 200，`lateral_diffusion` 投影存在，`status=done`。
- **断言**：`similar_products` 中 `hit_criteria` 并集含全部四值：`same_product_type`、`shared_fmea_mode`、`shared_control_plan`、`same_supplier_material`。
- **审计**：`GET /api/admin/logs/audit?table_name=capa_eightd&action=LATERAL_DIFFUSION_CHECKED&start={t0_iso}&page_size=200`，客户端按 `record_id == {capa_id}` 和 `operated_at >= t0` 过滤后 ≥ 1，`changed_fields.hit_criteria_union` 含四值。（API 不接收 `record_id` 参数。）

### B. 001 弹窗 + notify
- 关闭后前端自动弹出 `[data-e2e="lateral-diffusion-modal"]`（若 `decision=null`）。
- 点 `[data-e2e="lateral-decide-notify"]`。
- **断言**：`POST /api/capa/{id}/lateral-diffusion/decide` 200，`decision=notified`，`notifications` ≥ 1。
- 卡片 `[data-e2e="lateral-diffusion-card"]` 显示 notified 状态 + 通知列表。
- **审计**：`LATERAL_NOTIFICATION_SENT` ≥ 1。

### C. 002 skip + 理由
- 进 `8D-E2E-LATERAL-002` → 点 `[data-e2e="capa-approve"]` 关闭（有 LLM）→ 弹窗 → 填 `[data-e2e="lateral-skip-reason"]`「无需扩散」→ 点 `[data-e2e="lateral-decide-skip"]`。
- **断言**：`decision=skipped`；`LATERAL_NOTIFICATION_SKIPPED` 审计 `changed_fields.skip_reason` = 「无需扩散」。
- 无理由时 skip 按钮 disabled。

### D. EMPTY 空命中
- 进 `8D-E2E-LATERAL-EMPTY` → 点 `[data-e2e="capa-approve"]` 关闭（有 LLM）→ 无弹窗（无命中）。
- **断言**：`lateral_diffusion.status=empty`，`llm_status=skipped`，`similar_products=[]`。

### E. BLOCK 无凭证
- 无 LLM 环境：进 `8D-E2E-LATERAL-BLOCK` → 点 `[data-e2e="capa-approve"]` 关闭 → 422 `outcome=blocked`。
- **断言**：CAPA `status` 仍为 `D8_APPROVAL_PENDING`（回滚）；无 lateral check 行。

### F. rerun
- 进已关闭且未 decide 的 CAPA → 卡片点「重新检查」。
- **断言**：`POST /api/capa/{id}/lateral-diffusion/rerun` 200；投影刷新。

## 缺陷分类

PASS / FAIL / MISSING / BLOCKED（备注写说明；不用 PASS-NOTE）。UI 基线 + FAIL/MISSING 截图存 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.9/screenshots/`。

## UI 截图清单（强制）

遵循编排器「UI 截图验证契约」。工具：`browser_take_screenshot` → `REPORT_ROOT/01.9/screenshots/`。

| 步骤 | 界面 | 文件 | 必查 |
|---|---|---|---|
| A | 001 关闭后横向扩散 Modal | `A-modal-hits.png` | `lateral-diffusion-modal`；四依据命中块 |
| B | notify 后常驻卡片 + 通知列表 | `B-notified-card.png` | `lateral-diffusion-card` + notifications |
| C | 002 skip 填理由 | `C-skip-reason.png` | skip-reason textarea；skip 按钮 |
| C | skip 后卡片状态 | `C-skipped-card.png` | decision=skipped 展示 |
| D | EMPTY 无弹窗详情 | `D-empty.png` | 无 modal；卡片 empty/无命中 |
| F | rerun 后刷新 | `F-rerun.png` | 投影刷新反馈 |

每步 PASS 也截；视觉 FAIL 判据见编排器契约。子报告填「## UI 截图」表。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.9/report.md`，用编排器契约模板。UI 基线 + FAIL/MISSING 截图存 `screenshots/`；子报告须含「## UI 截图」表。

## 维护

每次跑前比对故事版本（v2 / 2026-07-21）；不一致 → 停下提示同步。
