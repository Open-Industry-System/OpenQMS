# 子故事 US-E2E-01.4：8D ↔ FMEA 双向追溯

**状态**: 定稿 v1（2026-07-08）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-fmea-linkage`
**前置**: 01.2、01.3（D4 根因 + D7 node-action 数据就绪，方有 FMEA 关联点）
**AI_REQUIRED**: false（无 AI 步骤；功能错误 → `FAILED`）

## 故事

**作为** 现场质量工程师 / 8D 团队负责人，**我想** 在 8D 闭环过程中，
8D 的 D4 根因与 D7 预防 node-action 能关联到 FMEA 图的 Cause/Prevention 节点，
且从 FMEA 节点能反查关联的 8D 记录，
**以便** 8D 与 FMEA 双向追溯、问题与改进不孤立、关联可审计。

## 背景 / 前置条件

- 系统已部署，8D 已推进至 D4 根因确认 + D7 node-action 创建（01.2/01.3 就绪）。
- 对应产品已有 FMEA 图。

## 联动关系

- **8D → FMEA**：D4 根因关联 FMEA 图 Cause 节点；D7 node-action 关联 FMEA Prevention 控制节点（01.3 已落库关联点，本子故事补全 FMEA 侧反查入口与展示）。
- **FMEA → 8D**：从 FMEA 节点可反查关联的 8D 记录列表（FMEA 模块侧入口与展示）。

## 主流程

1. field_qe 在 D4 确认根因后，根因关联到 FMEA 图的 Cause 节点（8D → FMEA）。
2. D7 预防节点落库为 node-action（01.3），关联 FMEA Prevention 节点（8D → FMEA）。
3. 从 FMEA 模块的节点详情页，可反查关联本 8D 的记录列表（FMEA → 8D）。
4. 双向跳转可追溯。

## 业务规则 / 验收标准

- **8D → FMEA**：D4 根因可关联 FMEA Cause 节点；D7 node-action 关联 FMEA Prevention 节点（01.3 已要求落库，本子故事验收关联点存在且正确）。
- **FMEA → 8D**：从 FMEA 节点详情页有反查入口，可看到关联的 8D 记录列表。
- **关联审计**：8D ↔ FMEA 关联建立写审计日志。
- **数据落库**：关联关系（8D-FMEA 节点）正确持久化，可追溯。
- **执行验证**：E2E 断言双向追溯链路完整（8D→FMEA 跳转 + FMEA→8D 反查），只验结构/关联，不验内容。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `capa_d7_node_action`（已含 fmea_id+fmea_node_id，01.3）、`capa_root_cause_verification`（root_cause 关联 FMEA Cause）、FMEA 侧反查入口（读上述关联） |
| 关键字段 | node_action.fmea_id、node_action.fmea_node_id、node_action.capa_id；FMEA 反查返回 8D 列表 |
| 状态枚举 | 无（关联点存在即通过） |
| 审计事件 | `FMEA_LINKAGE_CREATED`（含 capa_id、fmea_id、node_id、方向） |
| E2E seed 前置 | 8D 有 D4 根因 + D7 node-action；产品有 FMEA 图 |
| 通过条件 | 8D→FMEA 跳转可达 + FMEA→8D 反查返回正确列表 + 关联审计 |
| 失败条件（FAILED） | 关联点缺失；FMEA 侧无反查入口；反查列表错误；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- FMEA 图的自动更新逻辑（FMEA 图更新由 FMEA 模块负责，本子故事只管关联与反查）。
- D7 node-action 创建（见 01.3，本子故事假定 node-action 已落库）。
- SCAR 触发（见 01.5）、供应商风险（见 01.6）。

## 后续

- FMEA 图根据 node-action 自动更新的闭环为后续迭代。
