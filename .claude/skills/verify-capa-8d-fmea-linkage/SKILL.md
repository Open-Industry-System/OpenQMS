---
name: verify-capa-8d-fmea-linkage
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D ↔ FMEA bidirectional traceability (US-E2E-01.4). Symptoms include checking FMEA link from CAPA header, reverse lookup from FMEA to linked CAPAs, or D7 node-action FMEA matching.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.4-fmea-linkage.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-fmea-linkage

## Overview

走查 US-E2E-01.4 8D ↔ FMEA 双向追溯：CAPA header 关联 FMEA（`fmea_ref_id`）→ FMEA 详情反查关联 CAPA 列表 → D7 node-action 按 `linked`/`keyword`/`rule` 匹配 FMEA 预防节点。

## When to Use

**用**：用户说「验收 01.4」「走查 FMEA 双向」「验证 CAPA 关联 FMEA」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. LLM 凭证齐（D7 auto-fill 需 LLM）。
4. seed-state 取 engineer 账号。
5. seed 中有 `PFMEA-E2E-FMEA-LINK-001`（含 `fm-1`/`cause-link`/`pc-link` 节点）。

## 走查剧本

### A. CAPA → FMEA（header link）
- engineer 登录 → 进 `8D-E2E-FMEA-LINK-001`（D4_ROOT_CAUSE）→ 点详情头部「关联FMEA」→ 选 `PFMEA-E2E-FMEA-LINK-001`。
- **断言**：`GET /api/capa/{id}` `fmea_ref_id` 非空；审计 `FMEA_LINKAGE_CREATED`（`source=header`）。

### B. FMEA → CAPA（reverse lookup）
- 进 FMEA 列表 → `PFMEA-E2E-FMEA-LINK-001` → 详情 → 关联 CAPA 面板。
- **断言**：面板列出 `8D-E2E-FMEA-LINK-001`（及 `8D-E2E-FMEA-LINK-002` 若已 link）。

### C. D7 node-action FMEA 匹配
- 推进到 D7_PREVENTION → D7RecPanel 渲染。
- **断言**：`GET /api/capa/{id}/d7-node-actions` 中 `linked` 项 `fmea_id` = `PFMEA-E2E-FMEA-LINK-001` 的 fmea_id，`failure_mode_node_id=fm-1`，`failure_cause_node_id=cause-link`。
- `keyword` 项有 `fmea_id` 但无 `failure_cause_node_id`。
- `rule` 兜底项 `fmea_id=null`。

### D. skip 项
- 进 `8D-E2E-FMEA-LINK-002` → D7 skip 一项 → 审计 `D7_SKIP_CONFIRMATION` 含理由。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
