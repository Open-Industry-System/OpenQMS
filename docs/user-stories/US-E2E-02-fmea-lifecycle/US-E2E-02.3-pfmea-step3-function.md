# 子故事 US-E2E-02.3：PFMEA Step3 功能分析

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step3-function`
**前置**: 02.2（Step2 结构树已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.3（过程 FMEA 步骤三：功能分析）
**AI_REQUIRED**: false（功能树由结构推导，无独立 AI 触发器）

## 故事

**作为** 前期策划质量工程师，**我想** 在向导 Step3 定义 3 层功能树（过程项功能 / 过程步骤功能 / 工作要素功能），区分产品特性与过程特性，并维护 CC/SC 特殊特性标识，
**以便** 明确每个结构节点的功能与特性要求，为失效分析（Step4）的"功能否定→失效模式"推导提供基础。

## 背景 / 前置条件

- Step2 结构树已落库（ProcessItem/ProcessStep/ProcessWorkElement）。

## 主流程

1. `planning_qe` 在 Step3 为每个结构节点录入功能：
   - `ProcessItemFunction`（产品特性）
   - `ProcessStepFunction`（产品特性，CC/SC 可设）
   - `ProcessWorkElementFunction`（过程特性，CC/SC 可设）
2. `FUNCTION_MAPPED_TO` 边连接功能与对应结构节点。
3. CC/SC 写入函数节点 `classification` 字段（复用现有字段，不新增）。
4. 保存草稿。
5. 推进到 Step4。

## 业务规则 / 验收标准

### 结构完整性
- 3 层功能节点齐全，`HAS_FUNCTION` 边挂载到对应结构节点。
- `FUNCTION_MAPPED_TO` 边区分产品特性/过程特性。
- CC/SC 写入 `ProcessStepFunction`/`ProcessWorkElementFunction` 的 `classification` 字段（非 FailureCause.special_characteristic）。

### 门禁
- 推进 Step4 前：至少 1 个功能节点，且有 `FUNCTION_MAPPED_TO` 边。

### 审计与落库
- Step3 保存写 AuditLog。
- 节点/边持久化到 graph_data。

## 验收契约（字段级）

| 项 | PFMEA 定义 |
|---|---|
| 落库实体 | `ProcessItemFunction`、`ProcessStepFunction`、`ProcessWorkElementFunction` |
| 关键字段 | Function.name；Function.classification（CC/SC） |
| 边类型 | `HAS_FUNCTION`、`FUNCTION_MAPPED_TO` |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | `fmea.updated`（graph_data） |
| E2E seed 前置 | 02.2 结构树 |
| 通过条件 | 3 层功能树齐全 + FUNCTION_MAPPED_TO 边正确 + CC/SC 写 classification 字段 + 审计 |
| 失败条件（FAILED） | 功能树断层；CC/SC 写错字段；边缺失；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- Step4 失效分析（见 02.4）。
- 功能树的自动推导算法深度（现有由结构推导，本子故事只验结果）。

## 后续

- 功能树为 Step4 失效分析提供 FM 挂载点（FM 挂 ProcessStepFunction）。
