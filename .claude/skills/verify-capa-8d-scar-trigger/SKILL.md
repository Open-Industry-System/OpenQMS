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

走查 US-E2E-01.5 8D → SCAR 触发：CAPA 详情页触发 SCAR → 供应商选择 → D3 受影响批次关联 → SCAR 创建 → CAPA↔SCAR 双向链接 → SCAR 状态回写 CAPA。

## When to Use

**用**：用户说「验收 01.5」「走查 SCAR 触发」「验证 8D 转 SCAR」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. seed-state 取 engineer/manager 账号。
4. seed 中有 `8D-E2E-SCAR-001`（D3_INTERIM，含 D3 批次数据）。

## 走查剧本

### A. 触发 SCAR
- engineer 登录 → 进 `8D-E2E-SCAR-001` → 点 `[data-e2e="capa-trigger-scar"]` → 填供应商/描述/批次 → 提交。
- **断言**：`POST /api/capa/{id}/trigger-scar` 200；`GET /api/capa/{id}` `scar_ref_id` 非空、`linked_scar` 含 scar_no/status。

### B. 双向链接
- 进 SCAR 列表 → 找到新 SCAR → 详情 → 关联 CAPA 面板。
- **断言**：SCAR 详情含 `capa_ref_id` = 原 CAPA report_id；CAPA 详情 `linked_scar` 反向可见。

### C. D3 批次关联
- **断言**：SCAR 创建时 `affected_batches` 含 `LOT-E2E-SCAR-001`；`GET /api/capa/{id}/d3/affected-lots` 一致。

### D. 状态回写
- SCAR 状态变更（open → in_progress → closed）→ CAPA 详情 `linked_scar.status` 同步更新。
- **断言**：`GET /api/capa/{id}` `linked_scar.status` = SCAR 当前状态。

### E. 审计
- `GET /api/admin/logs/audit?table_name=supplier_scars&action=CREATE&record_id={scar_id}` ≥ 1；CAPA 侧 `scar_ref_id` 更新审计。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
