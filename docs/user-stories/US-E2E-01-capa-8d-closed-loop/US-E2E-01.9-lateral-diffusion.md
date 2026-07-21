# 子故事 US-E2E-01.9：横向扩散预警与通知

**状态**: 定稿 v2（2026-07-21）  
**所属 epic**: US-E2E-01（README.md v8.1）  
**关联 skill**: `verify-capa-8d-lateral-diffusion`  
**前置**: 01.3、01.4、01.8（8D 根因/预防 + FMEA 关联 + 知识沉淀就绪，方有扩散判定依据）  
**AI_REQUIRED**: true（有类似产品命中时：无 LLM 凭证 → `BLOCKED`；LLM 阶段失败 → `FAILED`。无类似产品命中时不调 LLM，关闭可成功）  
**设计**: `docs/superpowers/specs/2026-07-19-us-e2e-01.9-lateral-diffusion-design.md`（定稿 v3）

> v2 修订（与 design v3 对齐）：  
> - 阻塞条件细化：有命中才强制 LLM；空命中允许无 LLM 关闭。  
> - 产品粒度说明：系统以 `product_type` 聚合（故事原 `product_id` 映射为 `product_type_code`）。  
> - 审计 `LATERAL_NOTIFICATION_SKIPPED` 明确含 `skip_reason`。  
> - E2E 要求一次关闭路径可见四依据并集。

## 故事

**作为** 现场质量工程师 / 8D 团队负责人，**我想** 在 8D 报告完成（D8 关闭）后，
系统自动检查是否有**类似产品**可能受同一根因/失效模式影响，有则提示是否**通知相关产品负责人更新**，
通知状态可追踪，
**以便** 同类风险能横向扩散预防、不重蹈覆辙、通知决策可审计。

## 背景 / 前置条件

- 系统已部署，8D 已完成 D8 关闭路径上的知识沉淀（01.8 就绪；关闭同事务先 01.8 后 01.9）。
- 产品主数据含 `product_types` / `product_lines`；FMEA 图、控制计划、供应商/物料数据可用。
- 有类似产品命中时的 AI 步骤必须配置 LLM 凭证（`.env.e2e` 或运行环境）。

## 横向扩散预警

D8 关闭后，系统自动检查是否有**类似产品**可能受同一根因/失效模式影响：

- **类似产品判定**（4 个依据，取并集；确定性匹配）：
  1. 同 `product_type`（产品主数据）
  2. 共享相同 FMEA 失效模式/根因（approved FMEA 图中 FailureMode/Cause 名称规范化精确匹配）
  3. 共享相同控制计划特性键（approved CP items）
  4. 同供应商 + 同物料（源物料来自 D3 impact `batches[].material_code`；目标经 IQC 检验/物料主数据绑定）
- **聚合粒度**：按 `product_type_code` 聚合（系统无独立 products 表；故事字段 `product_id` ≡ `product_type_code`），并展开相关 `product_lines`（可跨同租户工厂）。
- **预警输出**：类似产品（type）清单 + 每项的命中依据 + 建议更新方向（LLM 生成）。
- **通知动作**：系统弹出提示，询问是否通知相关产品负责人去更新产品内容；
  - 确认通知 → 生成通知记录（含本 8D 摘要 + 命中依据 + 建议更新方向）→ 解析收件人落库（渠道发送为后续迭代）；
  - 不通知 → 记录「已评估、不通知」及理由（留痕，不跳过评估）；
  - 通知状态可追踪（已通知/待通知/已处理）。
- **决策范围**：一次决定覆盖本次检查全部命中 type（不可只决策子集）。

## 主流程

1. 8D 完成 D8 审批关闭路径（含 01.8 知识沉淀成功）。
2. 同事务自动触发横向扩散检查（4 判定依据取并集）。
3. 有类似产品 → 弹出提示，询问是否通知相关产品负责人。
4. 工程师/负责人确认通知 → 生成通知记录；不通知 → 记录理由。
5. 通知状态可追踪（已通知/待通知/已处理）。
6. 检查结果 + 通知决策写审计日志。

## 业务规则 / 验收标准

- **自动触发**：D8 关闭后自动触发类似产品检查，4 个判定依据取并集。
- **通知提示**：有类似产品时弹出提示询问是否通知；确认通知则生成含 8D 摘要+命中依据+建议方向的通知记录；不通知需记录理由（不跳过评估）。
- **通知状态可追踪**：通知记录有状态（已通知/待通知/已处理），可查询。
- **审计**：检查结果 + 通知决策（通知/不通知 + 理由）写审计日志；`LATERAL_NOTIFICATION_SKIPPED` 必须含 `skip_reason`。
- **数据落库**：横向扩散检查结果、通知记录（含状态）正确持久化。
- **执行验证**：E2E 至少一次关闭路径断言类似产品识别的 **4 依据并集均出现** + 通知提示 + 通知/不通知留痕 + 通知状态可查。
- **LLM 契约**：
  - 有类似产品命中 + 无 LLM 凭证 → `BLOCKED`（阻断关闭）；
  - 有类似产品命中 + LLM 失败 / 不可用 → `FAILED`（阻断关闭）；
  - 无类似产品命中 → 不调 LLM，关闭成功（检查 `status=empty`）。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `capa_lateral_diffusion_checks`（检查结果）、`capa_lateral_notifications`（通知记录） |
| 关键字段 | check.capa_id、check.similar_products[]（含 product_type_code、hit_criteria[]∈{same_product_type,shared_fmea_mode,shared_control_plan,same_supplier_material}、suggestion_direction、product_lines[]）；notification.product_type_code、notification.recipient_user_id/label、notification.status∈{notified,pending,processed}、notification.decision∈{notified,skipped}、notification.skip_reason |
| 状态枚举 | notification.status∈{notified,pending,processed}；hit_criteria 4 值枚举 |
| 审计事件 | `LATERAL_DIFFUSION_CHECKED`（含 similar_products count / hit_criteria_union）、`LATERAL_NOTIFICATION_SENT`、`LATERAL_NOTIFICATION_SKIPPED`（**含 skip_reason**） |
| E2E seed 前置 | 8D 可走完 D8 关闭 + 知识沉淀；主 seed 同时具备四依据可命中数据；另有空命中 seed |
| 通过条件 | 4 依据并集检查（E2E 关闭路径可见四值）+ 类似产品清单 + 通知提示 + 通知/不通知留痕 + 通知状态可查 + 审计 |
| 失败条件（FAILED） | 检查未触发；依据实现缺失导致并集不全；通知状态不可查；不通知未留痕；未审计；有命中时 LLM 失败 |
| 阻塞条件（BLOCKED） | **有类似产品命中**且无 LLM 凭证 |

## 不在本子故事范围

- 通知发送的具体渠道（站内信/邮件/待办，本子故事只管生成通知记录，渠道为后续迭代）。
- 类似产品负责人的后续更新闭环跟踪（后续迭代）。
- 横向扩散的自动强制更新（本子故事只管提示+通知，不强制，更新由各产品负责人决定）。
- 知识库沉淀（见 01.8）、PPT 输出（见 01.10）。
- 语义/向量相似度匹配（本子故事依据 2 为规范化精确匹配）。

## 后续

- 通知渠道（站内信/邮件/待办）为后续迭代。
- 类似产品负责人的更新闭环跟踪为后续迭代。
