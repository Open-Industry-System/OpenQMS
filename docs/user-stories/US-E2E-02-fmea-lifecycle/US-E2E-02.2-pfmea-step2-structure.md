# 子故事 US-E2E-02.2：PFMEA Step2 结构分析

**状态**: 定稿 v2（2026-07-25），经代码评审修订
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step2-structure`（待生成）
**前置**: 02.1（Step1 5T 范围已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.2（过程 FMEA 步骤二：结构分析）
**AI_REQUIRED**: false（纯手工录入，无 AI 触发器）

## 故事

**作为** 前期策划质量工程师，**我想** 在向导 Step2 定义过程结构树：过程项 → 过程步骤(OP10/OP20) → 工作要素(4M：Man/Machine/Material/Environment)，
**以便** 建立 PFMEA 的过程结构骨架，为功能分析（Step3）与失效分析（Step4）提供结构载体。

## 背景 / 前置条件

- Step1 已完成，`wizardScope` 已落库。
- 向导已注入初始 ProcessItem 节点。

## 主流程

1. `planning_qe` 在 Step2 录入过程结构：
   - `ProcessItem`（如"DC-DC 转换器装配"）
   - `ProcessStep`，含 `process_number` OP10/OP20，必填
   - `ProcessWorkElement`，`classification` ∈ 4M（Man/Machine/Material/Environment），必填
2. 结构树左侧面板实时展示层级。
3. 保存草稿（graph_data + `HAS_PROCESS_STEP`/`HAS_WORK_ELEMENT` 边）。
4. 推进到 Step3。

## 业务规则 / 验收标准

### 结构完整性
- `ProcessItem` → `ProcessStep`（`HAS_PROCESS_STEP` 边）→ `ProcessWorkElement`（`HAS_WORK_ELEMENT` 边）层级正确（共享边词汇，见 README "图结构契约" 节）。
- `ProcessStep.process_number` 非空（OP10/OP20 格式）。
- `ProcessWorkElement.classification` ∈ {Man, Machine, Material, Environment}（4M 存储枚举，中文仅为 UI 标签），必填。

### 门禁
- 推进 Step3 前：至少 1 个 ProcessStep + 1 个 ProcessWorkElement，且 process_number/classification 非空。

### 审计与落库
- Step2 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- 节点/边持久化到 `graph_data.nodes`/`edges` JSONB。

## 验收契约（字段级）

| 项 | PFMEA 定义 |
|---|---|
| 落库实体 | `ProcessItem`、`ProcessStep`、`ProcessWorkElement` |
| 关键字段 | ProcessStep.process_number；ProcessWorkElement.classification ∈ {Man, Machine, Material, Environment} |
| 边类型 | `HAS_PROCESS_STEP`、`HAS_WORK_ELEMENT` |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`） |
| E2E seed 前置 | 02.1 PFMEA draft + wizardScope |
| 通过条件 | 结构树 3 层齐全 + process_number/classification 必填 + 边正确 + 审计 |
| 失败条件（FAILED） | 层级断裂；process_number 缺失；classification 非 4M 存储枚举；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- Step3 功能分析（见 02.3）。
- 结构树的拖拽排序（现有 `pfmea-tree-drag-sort`，不在本子故事验收）。

## 后续

- 结构树为 Step3 功能分析提供挂载点（3 层功能节点）。
