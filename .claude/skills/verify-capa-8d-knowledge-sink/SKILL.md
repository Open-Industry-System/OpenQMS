---
name: verify-capa-8d-knowledge-sink
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D knowledge sink (US-E2E-01.8) — auto-sink on D8 close, embedding lifecycle, recommend retrieval, resink. Symptoms include checking knowledge entry creation, embedding_status, recommend hit, or KNOWLEDGE_SUNK audit.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.8-knowledge-sink.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-knowledge-sink

## Overview

走查 US-E2E-01.8 知识库沉淀：D8 关闭自动触发 sink → knowledge_entry 创建（summary/tags/llm_status）→ embedding 生成（pending → ready/failed）→ recommend 检索命中 → 手动 resink。

## When to Use

**用**：用户说「验收 01.8」「走查知识沉淀」「验证 embedding/recommend」等。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. LLM 凭证齐（沉淀摘要/embedding 需 LLM；无凭证 → BLOCKED）。
4. seed-state 取 manager/engineer/admin 账号。
5. seed 中有 `8D-E2E-KNOW-001`（D8_APPROVAL_PENDING，D2–D8 字段齐全）。

## 走查剧本

### A. 关闭触发 sink
- manager 登录 → 进 `8D-E2E-KNOW-001` → `[data-e2e="capa-advance"]` 推进 D8→D8_CLOSURE。
- **断言**：`GET /api/capa/{id}` `status=D8_CLOSURE`；`GET /api/knowledge/capa/{id}` 返回 entry 含 `summary`/`tags`/`llm_status=done`/`embedding_status` ∈ {pending, ready}。
- 无 LLM → 422 `outcome=blocked`（fail-closed）。

### B. Embedding 生命周期
- 轮询 `GET /api/knowledge/capa/{id}` 直到 `embedding_status=ready`（≤ 60s）。
- **断言**：`embedding_id` 非空；`GET /api/admin/logs/audit?table_name=knowledge_entries&action=KNOWLEDGE_SUNK&record_id={entry_id}` ≥ 1。

### C. Recommend 检索命中
- engineer 登录 → 进另一 CAPA（D4_ROOT_CAUSE）→ 触发 D4 推荐。
- **断言**：推荐 DAG 第 3 阶段（全局知识库 RAG）`status=done`、`hit_count` ≥ 1；`GET /api/capa/{id}/d4-fmea-recommendations` 某条 `match_source=knowledge_base` 或 provenance 含该 entry_id。

### D. 手动 resink
- manager 进已关闭 CAPA → 知识卡片 `[data-e2e="knowledge-resink"]` → 点击。
- **断言**：`POST /api/capa/{id}/sink-knowledge` 200；entry 更新（`updated_at` 变化）；`KNOWLEDGE_SUNK` 审计新增。

### E. 审计
- `KNOWLEDGE_SUNK`（首次 + resink）；`KNOWLEDGE_RETRIEVED`（recommend 命中时）。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
