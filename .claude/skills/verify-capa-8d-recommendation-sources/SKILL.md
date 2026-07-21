---
name: verify-capa-8d-recommendation-sources
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D AI recommendation 12-source orchestration (US-E2E-01.2) — DAG stages, provenance, execution verification. Symptoms include checking D4/D5 recommendation pipeline, 12-stage DAG, source labels, or recommendation adoption.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.2-recommendation-12-sources.md
> 故事版本：定稿 v1（2026-07-08）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-recommendation-sources

## Overview

走查 US-E2E-01.2 AI 推荐 12 源全接入：D4/D5 触发推荐 → 12 阶段 DAG 真实执行 → 每阶段 provenance 标注 → LLM 融合 → 推荐列表 → 采纳留痕。

## When to Use

**用**：用户说「验收 01.2」「走查推荐 DAG」「验证 12 源推荐」等。
**不用**：其他子故事；推荐准确率评测。

## 前置

1. 故事版本一致（比对 `US-E2E-01.2-recommendation-12-sources.md` 顶部）。
2. e2e 栈在跑（`:5174`）。
3. LLM 凭证齐（`.env.e2e` 四项）。
4. `GET /api/e2e/seed-state` 取账号。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="rec-dag-stage-<i>"]` | 第 i 阶段节点（读 `data-status` + 节点文本） |
| `[data-e2e^="rec-source-"]` | 每条推荐来源 provenance 标签 |
| `[data-e2e^="rec-item-stage-"]` | 每条推荐命中阶段索引 |
| `[data-e2e="d4-adopt"]` | D4 采纳根因 |
| `[data-e2e="d5-adopt-suggestion"]` | D5 采纳措施 |

## 走查剧本

### A. D4 推荐
- engineer 登录 → 进 CAPA（D4_ROOT_CAUSE 状态，如 `8D-E2E-001`）→ D4RecPanel 触发推荐。
- 对 `i=1..12` 查 `[data-e2e="rec-dag-stage-<i>"]`：

| i | 阶段 | 期望 |
|---|---|---|
| 1 | 上下文采集 | done |
| 2 | 本产品 FMEA 检索 | done |
| 3 | 全局知识库 RAG | done |
| 4 | 同类型产品知识库 | done/skipped（注明） |
| 5 | 经验教训库 | done/skipped |
| 6 | SPC 异常关联 | done/skipped |
| 7 | MES 设备/过程 | done/skipped |
| 8 | IQC 来料检验 | done |
| 9 | 供货历史 | done |
| 10 | 规则启发 | done |
| 11 | LLM 融合排序 | done |
| 12 | 输出推荐列表 | done |

- **断言**：推荐列表非空；每条有 `rec-source-*` 和 `rec-item-stage-*`；`GET /api/capa/{id}/d4-fmea-recommendations` 每条含 `match_source`/`confidence`/`stage_index`。

### B. D5 推荐
- 推进到 D5_CORRECTION → D5RecPanel 触发 → 同 12 阶段断言 → `GET /api/capa/{id}/d5-fmea-recommendations`。

### C. 采纳留痕
- D4 点 `[data-e2e="d4-adopt"]` 采纳一条 → `GET /api/admin/logs/audit?action=ADOPT_RECOMMENDATION&record_id={id}` 含 `source`/`stage_index`/`operated_by`。
- D5 同理。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING。截图存 `docs/e2e/reports/US-E2E-01.2-<YYYY-MM-DD>/screenshots/`。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
