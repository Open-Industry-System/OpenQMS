---
name: verify-capa-8d-knowledge-sink
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D knowledge sink (US-E2E-01.8). Symptoms include checking knowledge entry creation, embedding_status, recommend hit, or KNOWLEDGE_SUNK audit.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.8-knowledge-sink.md
> 故事版本：定稿 v2（2026-10-27）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-knowledge-sink

## Overview

走查 US-E2E-01.8 知识库沉淀：D8 关闭自动触发 sink → knowledge_entry 创建 → embedding 生命周期 → recommend 检索命中 → 手动 resink。

## When to Use

**用**：用户说「验收 01.8」「走查知识沉淀」「验证 embedding/recommend」等。

## 本轮实施契约与验收边界

版本/日期同步仅表明剧本对应已实现契约，不是走查 PASS。2026-10-27 正向真实 provider/浏览器、知识及横向扩散仍因本工作树缺少授权 `.env.e2e` 而 BLOCKED；不得借用环境/生产密钥、mock provider 或预造 passed gate。独立权限/终态保护可单列，不冒充整故事完成。操作解释见 `docs/development/capa-outcome-review.md`。

## 前置

1. 故事版本一致。
2. e2e 栈在跑。
3. LLM 凭证齐（沉淀摘要/embedding 需 LLM；无凭证 → close 422 blocked）。
4. seed-state 取 manager/engineer/admin 账号。
5. seed 中有 `8D-E2E-KNOW-001`（`D8_APPROVAL_PENDING`，D2–D8 字段齐全）。

## selector 表

| selector | 用途 |
|---|---|
| `[data-e2e="capa-advance"]` / `capa-approve` | manager 关闭（D8_APPROVAL_PENDING→D8_CLOSURE 用 approve） |
| `[data-e2e="capa-knowledge-card"]` | 知识卡片 |
| `[data-e2e="capa-knowledge-entry"]` | entry 摘要 |
| `[data-e2e="capa-knowledge-embedding-status"]` | embedding 状态 |
| `[data-e2e="capa-knowledge-resink"]` | 手动 resink |
| `[data-e2e="capa-knowledge-reload"]` | 重新加载 |
| `[data-e2e="capa-status"]` | 状态 |

## 知识回读契约（禁止捏造路径）

- **没有** `GET /api/knowledge/capa/{id}`。
- 列表：`GET /api/knowledge/entries?source_type=capa&q={document_no}&page_size=50`，再在客户端按 `item.source_id === capa_id` 过滤（与 `findCapaKnowledgeEntry` 一致）。
- 详情：`GET /api/knowledge/entries/{entry_id}`。
- 手动 resink：`POST /api/capa/{id}/sink-knowledge`。
- 审计写在 **`table_name=capa_eightd`**（不是 knowledge_entries）：`action=KNOWLEDGE_SUNK`，审计行的 `record_id={capa_id}`。

## 走查剧本

### A. 关闭触发 sink
- manager 登录 → 进 `8D-E2E-KNOW-001` → 完整读取并核对集中结果面板及必要来源，提交同次 revision/round → `[data-e2e="capa-approve"]`（`D8_APPROVAL_PENDING`→`D8_CLOSURE`）。
- **断言**：`GET /api/capa/{id}` `status=D8_CLOSURE`。
- **断言**：`GET /api/knowledge/entries?source_type=capa&q=8D-E2E-KNOW-001` 的 items 中存在 `source_id={capa_id}`，entry 含 `summary`/`tags`/`embedding_status` ∈ {pending, ready, failed}。
- 无 LLM → advance/approve 422 `detail.outcome=blocked`（fail-closed）。

### B. Embedding 生命周期
- 轮询 list/detail 直到 `embedding_status=ready`（≤ 60s）。
- **断言**：`embedding_status=ready`。`embedding_status=failed` → **FAIL**。超时未 ready（worker 未跑/未配置）→ **BLOCKED**（AI_REQUIRED=true 子故事）；在报告里记 BLOCKED 并说明 worker 未就绪，**不**记 PASS。
- **审计**：`GET /api/admin/logs/audit?table_name=capa_eightd&action=KNOWLEDGE_SUNK&start={t0_iso}&page_size=200`，客户端按 `record_id == {capa_id}` 和 `operated_at >= t0` 过滤后 ≥ 1。（API 不接收 `record_id` 参数；响应字段是 `operated_at`。）

### C. Recommend 检索命中
- engineer 登录 → 进另一 D4 CAPA → 触发 D4 推荐。
- **断言**：`GET /api/capa/{id}/d4-fmea-recommendations` 某条 `match_source`/`source_knowledge_entry_id` 命中该 entry（或 provenance 含 entry_id）。命中时审计可有 `action=KNOWLEDGE_RETRIEVED`。

### D. 手动 resink
- 在已关闭报告有 EDIT 时单独补写 d8_closure（明确未审补充），记录前后核心/revision/round/决定/source_versions 相同；不要以直接改库制造真实关闭证据。
- manager 进已关闭 CAPA → `[data-e2e="capa-knowledge-resink"]`。
- **断言**：`POST /api/capa/{id}/sink-knowledge` 200；entry 更新；新增 `KNOWLEDGE_SUNK` 审计。
- **v2 来源断言**：知识详情 fields.closure_review_scope 和列表 closure_review_scope 为 `unreviewed_supplement`；D8 lesson.tags 含且不重复 `review_scope:unreviewed_supplement`，D7 lesson 不获 approved 标记。知识/经验推荐文本保留“未审核补充”；不得把补充用作已审根因/已验证效果。
- 历史缺标记知识/经验读取只投影，不更新 fields/tags/embedding/数据库；无适用 UPDATE 审计时补充人/时间为 null。归档补充仍冻结400，混合核心 PUT 409；正式记录无候选7天清理。
- 本轮 Task7 缺授权测试配置，真实 sink/embedding/recommend 与横向扩散尚未执行成功。普通 provider double 测试只能说明逻辑回归，不能把这些步骤记 PASS。

## 缺陷分类

PASS / FAIL / MISSING / BLOCKED（备注写说明；不用 PASS-NOTE）。

## UI 截图清单（强制）

遵循编排器「UI 截图验证契约」。工具：`browser_take_screenshot` → `REPORT_ROOT/01.8/screenshots/`。

| 步骤 | 界面 | 文件 | 必查 |
|---|---|---|---|
| A | 关闭后知识卡片 | `A-knowledge-card.png` | `capa-knowledge-card` + entry 摘要 |
| B | embedding 状态 ready | `B-embedding-ready.png` | `capa-knowledge-embedding-status`=ready |
| C | D4 推荐命中 knowledge 源（若可展示） | `C-recommend-hit.png` | provenance/源标签（API-only 可 N/A） |
| D | 手动 resink 后卡片刷新 | `D-resink.png` | resink 按钮可用；卡片更新 |

每步 PASS 也截；视觉 FAIL 判据见编排器契约。子报告填「## UI 截图」表。

## 子报告输出

写到 `docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.8/report.md`，用编排器契约模板。UI 基线 + FAIL/MISSING 截图存 `screenshots/`；子报告须含「## UI 截图」表。

## 维护

每次跑前比对故事版本；不一致 → 停下提示同步。
