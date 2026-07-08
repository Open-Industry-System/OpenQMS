# 子故事 US-E2E-01.2：AI 推荐 12 源全接入（编排 DAG + provenance + 执行验证）

**状态**: 评审稿 v1（2026-07-08）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-recommendation-sources`
**前置**: 无（纯后端推荐管道，无外部系统依赖）
**AI_REQUIRED**: true（无 LLM 凭证 → `BLOCKED`）

## 故事

**作为** 现场质量工程师，**我想** 在 D4 根因分析、D5 永久措施触发 AI 推荐时，
看到完整的 12 阶段编排流程被真实执行（而非黑盒），每阶段带来源 provenance 标注，
关键阶段必须达 `done`、外部数据阶段无数据时 `skipped` 但注明原因、LLM 阶段不可降级，
**以便** AI 推荐可追溯、可解释、可审计，且编排过程对工程师和审查者透明。

## 背景 / 前置条件

- 系统已部署，「默认工厂」+ 产品线 `DC-DC-100-E2E`；该产品已有 FMEA、知识库、SPC 控制图、IQC 检验记录、MES 连接。
- AI 步骤必须配置 `.env.e2e` 的 LLM 凭证并完整执行；无凭证时本子故事验收视为 `BLOCKED`，不得降级跳过 AI 步骤。
- 现场发现一批来料螺栓尺寸超差，8D 已推进到 D4。

## AI 推荐流程编排（D4/D5，可视化 DAG）

触发 D4/D5 推荐后，UI 展示**流程编排可视化面板**，按以下 12 阶段执行；每阶段显示：名称 / 来源 / 状态（pending·running·done·skipped·error）/ 命中数·摘要。

1. 上下文采集（关联产品/产品线/失效现象）
2. 本产品 FMEA 检索（图相似：相似 FailureMode 的 Cause/控制措施）
3. 全局知识库 RAG 检索（pgvector 语义 + 全文 + RRF 融合，6 实体）
4. 同类型产品知识库检索（按 `product_types` 主数据聚合，跨工厂共享）
5. 经验教训库检索（历史 8D lessons）
6. SPC 异常关联检索（SPC 判异 → 关联失效模式）
7. MES 设备/过程数据检索（设备异常/参数漂移）
8. IQC 来料检验数据检索（本批及历史来料不良）
9. 供货历史检索（供应商评级/历史 PPM）
10. 规则启发（高 RPN 优先/重复根因加权/安全特性提级）
11. LLM 融合排序（去重/排序/自然语言解释）
12. 输出推荐列表（每条带**来源 provenance** 标签）

## 主流程

1. field_qe 在 D4 触发【AI 多源推荐】，流程编排面板出现，展示 12 阶段。
2. 工程师观察各阶段状态流转：1-10 并行/串行检索 → 11 LLM 融合 → 12 输出。
3. 每阶段显示来源标签 + 命中数 + 摘要；`skipped` 阶段注明原因（如"无 SPC 控制图关联"）。
4. 最终推荐列表非空，每条带来源 provenance 标签（标注命中哪些阶段）。
5. D5 永久措施触发同样流程，验收标准一致。

## 业务规则 / 验收标准

- **12 阶段全部接入**：阶段 1-10 各自作为独立推荐源接入编排；阶段 11 LLM 融合；阶段 12 输出。不允许任一阶段为"占位未实现"。
- **阶段状态**：
  - 阶段 2（本产品 FMEA）/ 3（全局知识库）/ 10（规则）/ 11（LLM）/ 12（输出）必须达 `done`；
  - 阶段 4（同类型产品）/ 5（经验教训）/ 6（SPC）/ 7（MES）/ 8（IQC）/ 9（供货历史）可在无对应数据时 `skipped`，但必须注明原因；
  - 阶段 1（上下文采集）必须 `done`（提供后续阶段的检索上下文）；
  - 任何阶段 `error` 视为 `FAILED`。
- **provenance 标注**：每条推荐标注命中的阶段集合；点击推荐项可展开看各来源的命中详情。
- **AP/S/O/D**：每条推荐带 `AP∈{H,M,L}`、`S/O/D∈1..10`（来自 FMEA 节点风险）。
- **LLM 不可降级**：无 LLM 凭证 → `BLOCKED`；LLM 阶段 `skipped`/`error` → `FAILED`。
- **执行验证**：E2E 断言**编排被执行**（面板各阶段状态符合预期，非黑盒），只验结构/状态/来源，不验精确文字。
- **审计**：推荐触发与采纳写审计日志（操作人、命中阶段集合、采纳记录）。
- **数据落库**：推荐结果（含每条的来源 provenance、AP/S/O/D、命中阶段）持久化，可回溯。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `recommendation_cache`（含 stage_runs[]、candidates[]）、`capa_ai_adoption`（采纳记录） |
| 关键字段 | stage_run.index∈1..12、status∈{pending,running,done,skipped,error}、skipped_reason；candidate.source_provenance[]∈stage_index 集合、AP∈{H,M,L}、S/O/D∈1..10 |
| 状态枚举 | 阶段状态见上；LLM 阶段不可 skipped |
| 审计事件 | `RECOMMENDATION_TRIGGERED`（含 stage 集合）、`RECOMMENDATION_ADOPTED` |
| E2E seed 前置 | 产品线 DC-DC-100-E2E 有 FMEA + 知识库 + SPC + IQC + MES + 供应商历史数据 |
| 通过条件 | 12 阶段全接入 + 关键阶段 done + skipped 注明原因 + 推荐非空带 provenance + AP/S/O/D 齐全 |
| 失败条件（FAILED） | 关键阶段非 done；可跳过阶段 skipped 但缺 skipped_reason；LLM 阶段 skipped/error；provenance 缺失；AP/S/O/D 缺失 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- D4 根因现场验证子流程（见 01.3）。
- D3 遏制措施的 AI 分析（见 01.1，D3 不走这 12 阶段 DAG，有独立的数据导入+分析流程）。
- D7 预防复发 AI 提示（见 01.3 的 D7 node-action 部分）。
- AI 推荐准确率评测（epic 范围外）。

## 后续

- 各推荐源的命中质量/召回率优化为后续迭代，不在本子故事验收范围。
- 01.8 的知识库沉淀条目会进入阶段 5（经验教训库）与阶段 3（全局知识库），形成"当前 8D → 知识库 → 未来 8D"闭环。
