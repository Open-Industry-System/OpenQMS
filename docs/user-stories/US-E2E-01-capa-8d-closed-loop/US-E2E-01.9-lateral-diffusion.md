# 子故事 US-E2E-01.9：横向扩散预警与通知

**状态**: 评审稿 v1（2026-07-08）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-lateral-diffusion`
**前置**: 01.3、01.4、01.8（8D 根因/预防 + FMEA 关联 + 知识沉淀就绪，方有扩散判定依据）
**AI_REQUIRED**: true（类似产品判定/建议方向可能用 LLM；无 LLM 凭证 → `BLOCKED`）

## 故事

**作为** 现场质量工程师 / 8D 团队负责人，**我想** 在 8D 报告完成（D8 关闭）后，
系统自动检查是否有**类似产品**可能受同一根因/失效模式影响，有则提示是否**通知相关产品负责人更新**，
通知状态可追踪，
**以便** 同类风险能横向扩散预防、不重蹈覆辙、通知决策可审计。

## 背景 / 前置条件

- 系统已部署，8D 已完成 D8 关闭 + 知识沉淀（01.8 就绪）。
- 产品主数据含 `product_types`；FMEA 图、控制计划、供应商/物料数据可用。
- AI 步骤必须配置 `.env.e2e` 的 LLM 凭证。

## 横向扩散预警

D8 关闭后，系统自动检查是否有**类似产品**可能受同一根因/失效模式影响：

- **类似产品判定**（4 个依据，取并集）：
  1. 同 `product_type`（产品主数据）
  2. 共享相同 FMEA 失效模式/根因（FMEA 图有相同或相似 FailureMode/Cause）
  3. 共享相同控制计划特性/控制参数
  4. 同供应商 + 同物料（同一供应商供的同一物料用于多个产品）
- **预警输出**：类似产品清单 + 每项的命中依据 + 建议更新方向。
- **通知动作**：系统弹出提示，询问是否通知相关产品负责人去更新产品内容；
  - 确认通知 → 生成通知（含本 8D 摘要 + 命中依据 + 建议更新方向）→ 发送给相关产品负责人；
  - 不通知 → 记录"已评估、不通知"及理由（留痕，不跳过评估）；
  - 通知状态可追踪（已通知/待通知/已处理）。

## 主流程

1. 8D 完成 D8 关闭 + 知识沉淀（01.8）。
2. D8 关闭后系统自动触发横向扩散检查（4 判定依据取并集）。
3. 有类似产品 → 弹出提示，询问是否通知相关产品负责人。
4. 工程师/负责人确认通知 → 生成通知发送；不通知 → 记录理由。
5. 通知状态可追踪（已通知/待通知/已处理）。
6. 检查结果 + 通知决策写审计日志。

## 业务规则 / 验收标准

- **自动触发**：D8 关闭后自动触发类似产品检查，4 个判定依据取并集。
- **通知提示**：有类似产品时弹出提示询问是否通知；确认通知则发送含 8D 摘要+命中依据+建议方向的通知；不通知需记录理由（不跳过评估）。
- **通知状态可追踪**：通知记录有状态（已通知/待通知/已处理），可查询。
- **审计**：检查结果 + 通知决策（通知/不通知 + 理由）写审计日志。
- **数据落库**：横向扩散检查结果、通知记录（含状态）正确持久化。
- **执行验证**：E2E 断言类似产品识别（4 依据并集）+ 通知提示 + 通知/不通知留痕 + 通知状态可查。
- **LLM 不可降级**：无 LLM 凭证 → `BLOCKED`；LLM 阶段 `skipped`/`error` → `FAILED`。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `capa_lateral_diffusion_check`（检查结果）、`capa_lateral_notification`（通知记录） |
| 关键字段 | check.capa_id、check.similar_products[]（含 product_id、hit_criteria[]∈{same_product_type,shared_fmea_mode,shared_control_plan,same_supplier_material}）、check.suggestion_direction；notification.product_id、notification.recipient、notification.status∈{notified,pending,processed}、notification.decision∈{notified,skipped}、notification.skip_reason |
| 状态枚举 | notification.status∈{notified,pending,processed}；hit_criteria 4 值枚举 |
| 审计事件 | `LATERAL_DIFFUSION_CHECKED`（含 similar_products count）、`LATERAL_NOTIFICATION_SENT`、`LATERAL_NOTIFICATION_SKIPPED`（含 skip_reason） |
| E2E seed 前置 | 8D 完成 D8 关闭 + 知识沉淀；存在 ≥1 类似产品（同 product_type 或共享 FMEA 模式等） |
| 通过条件 | 4 依据并集检查 + 类似产品清单 + 通知提示 + 通知/不通知留痕 + 通知状态可查 + 审计 |
| 失败条件（FAILED） | 检查未触发；依据缺失；通知状态不可查；不通知未留痕；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- 通知发送的具体渠道（站内信/邮件/待办，本子故事只管生成通知记录，渠道为后续迭代）。
- 类似产品负责人的后续更新闭环跟踪（后续迭代）。
- 横向扩散的自动强制更新（本子故事只管提示+通知，不强制，更新由各产品负责人决定）。
- 知识库沉淀（见 01.8）、PPT 输出（见 01.10）。

## 后续

- 通知渠道（站内信/邮件/待办）为后续迭代。
- 类似产品负责人的更新闭环跟踪为后续迭代。
