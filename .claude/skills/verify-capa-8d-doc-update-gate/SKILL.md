---
name: verify-capa-8d-doc-update-gate
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D D8 document update gate (US-E2E-01.7) — AI impact analysis, automated audit, waiver/defer, version freshness. Symptoms include checking D8_GATE_PENDING → D8_APPROVAL_PENDING transition, doc-gate panel, or audit coverage.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.7-doc-update-gate.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-doc-update-gate

## Overview

走查 US-E2E-01.7 D8 文档更新审核门禁：D7_COMPLETED → D8_GATE_PENDING → AI 文档影响分析 → 自动化审核（FMEA/CP/SOP 覆盖率）→ decision（passed/blocked/deferred）→ D8_APPROVAL_PENDING。

## When to Use

**用**：用户说「验收 01.7」「走查文档门禁」「验证 D8 gate」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. LLM 凭证齐（影响分析需 LLM）。
4. seed-state 取 engineer/manager 账号。
5. seed 中有 `8D-E2E-DOCGATE-001`（D8_GATE_PENDING）和 `PFMEA-E2E-DOCGATE-001`（approved FMEA）。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="doc-gate-panel"]` | 门禁面板 |
| `[data-e2e="doc-gate-impact"]` | 触发影响分析 |
| `[data-e2e="doc-gate-audit"]` | 触发自动审核 |
| `[data-e2e="doc-gate-confirm"]` | 确认无影响 |
| `[data-e2e="doc-gate-defer"]` | 延期（需 owner/deadline/reason） |

## 走查剧本

### A. 影响分析
- engineer 登录 → 进 `8D-E2E-DOCGATE-001` → `[data-e2e="doc-gate-impact"]` → 等待 `status=done`。
- **断言**：`GET /api/capa/{id}/doc-gate/impact` 返回 `affected_docs` ≥ 1（FMEA/CP），每条含 `doc_type`/`doc_id`/`doc_name`/`version_before`。

### B. 自动审核
- `[data-e2e="doc-gate-audit"]` → 等待审核完成。
- **断言**：`GET /api/capa/{id}/doc-gate/audit` 每条含 `status` ∈ {passed, pending_update, incomplete}、`coverage`、`covered_count`/`total_count`。

### C. Decision
- **passed**：全部审核通过 → `[data-e2e="doc-gate-confirm"]` → `decision=passed` → 推进到 D8_APPROVAL_PENDING。
- **blocked**：有 pending_update → `decision=blocked`，不能推进。
- **deferred**：`[data-e2e="doc-gate-defer"]` → 填 owner/deadline/reason → `decision=deferred` → 审计 `DOC_GATE_DEFERRED`。

### D. 版本新鲜度
- **断言**：`analysis_input_hash` 与当前 FMEA/CP version 一致；若文档在分析后更新，审核应 `incomplete`（freshness 检查）。

### E. 审计
- `GET /api/admin/logs/audit?table_name=capa_docg_analysis&record_id={analysis_id}` 含 `DOC_GATE_ANALYSIS_DONE`/`DOC_GATE_AUDIT_RUN`/`DOC_GATE_DECISION`。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
