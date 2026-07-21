---
name: verify-capa-8d-ppt-output
description: Use when asked to verify / walk through / 验收 the OpenQMS CAPA 8D PPT export (US-E2E-01.10) — one-click generation, sub-agent review loop, admin review-skill management. Symptoms include checking PPT download, review report modal, or needs_review flag.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop/US-E2E-01.10-ppt-output.md
> 故事版本：定稿 v4（2026-07-09）
> 所属 epic：US-E2E-01（README.md v8.1）
> 同步规则：当子故事版本号或日期变更，本剧本必须重新核对并同步。

# verify-capa-8d-ppt-output

## Overview

走查 US-E2E-01.10 8D 报告 PPT 输出：D8_CLOSURE/ARCHIVED 后一键生成 PPT（D1-D8 + 封面 + 附录）→ sub-agent 3 轮审查（LLM 校正 → needs_review；纯 DB-faithful → passed）→ 审查报告 Modal → admin ReviewSkillsPage 配置审查标准。

## When to Use

**用**：用户说「验收 01.10」「走查 PPT 输出」「验证 8D 报告导出」等。

## 前置

1. 故事版本一致（比对 `US-E2E-01.10-ppt-output.md` 顶部：定稿 v4（2026-07-09））。
2. e2e 栈在跑。
3. LLM 凭证齐（sub-agent 审查需 LLM；无凭证 → 跳过审查 + 提示「大模型未配置」，PPT 仍可生成）。
4. seed-state 取 engineer/admin 账号。
5. 有一个 D8_CLOSURE 或 ARCHIVED 的 CAPA（如 `8D-E2E-KNOW-001` 关闭后）。

## 走查剧本

### A. 生成 PPT
- engineer 登录 → 进 D8_CLOSURE CAPA → 点 `[data-e2e="capa-generate-ppt"]`（或对应按钮）。
- **断言**：`POST /api/capa/{id}/ppt` 200，返回 PPT 文件流（`Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation`）或生成任务 ID。
- 无 LLM → PPT 仍生成，审查跳过，提示「大模型未配置」。

### B. Sub-agent 审查
- 有 LLM → 生成后自动触发审查（3 轮上限）。
- **断言**：`GET /api/capa/{id}/ppt-review` 返回审查报告，`status` ∈ {passed, needs_review, failed}。
- 首轮即通过（无校正，内容 DB-faithful）→ `passed`。
- LLM 校正采用的内容 → `needs_review` + 标注「需人工复核确认未编造数据」。

### C. 审查报告 Modal
- 前端弹出审查报告 Modal（或页面展示）。
- **断言**：Modal 含各页/section 审查结果；`needs_review` 项高亮提示。

### D. Admin ReviewSkillsPage
- admin 登录 → 进 Review Skills 管理页。
- **断言**：可创建/编辑/删除审查 skill（按租户隔离）；`GET /api/admin/review-skills` 返回列表。

### E. 内容忠实性
- **断言**：PPT 内容（D1-D8 各字段）与 `GET /api/capa/{id}` 回读一致；无编造数据（结构校验 + 人工抽检）。

### F. 审计
- `GET /api/admin/logs/audit?table_name=capa_ppt_export&record_id={export_id}` 含 `PPT_EXPORT_GENERATED`（及 `PPT_REVIEW_DONE` 若审查运行）。

## 缺陷分类

PASS / PASS-NOTE / FAIL / MISSING。

## 维护

每次跑前比对故事版本（v4 / 2026-07-09）；不一致 → 停下提示同步。
