# 子故事 US-E2E-02.9：DFMEA Step2 结构分析

**状态**: 定稿 v2（2026-07-25），经代码评审修订
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step2-structure`（待生成）
**前置**: 02.8（Step1 5T 范围已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.2（设计 FMEA 步骤二：结构分析）
**AI_REQUIRED**: false

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step2 定义系统结构树：系统(System) → 子系统(Subsystem) → 零部件(Component)，含方块图/边界图/接口分析的可视化辅助，
**以便** 建立 DFMEA 的设计结构骨架，为功能分析（Step3）与失效分析（Step4）提供结构载体。

## 背景 / 前置条件

- Step1 已完成，向导已注入初始 System 节点。

## 主流程

1. `planning_qe` 在 Step2 录入系统结构：
   - `System`（顶层）
   - `Subsystem`（`HAS_PROCESS_STEP` 边，语义/UI 映射为 hasSubsystem，见 README "图结构契约" 节）
   - `Component`（`HAS_WORK_ELEMENT` 边，语义/UI 映射为 hasComponent）
2. 结构树左侧面板实时展示层级。
3. 保存草稿。
4. 推进到 Step3。

## 业务规则 / 验收标准

### 结构完整性
- `System` → `Subsystem`（`HAS_PROCESS_STEP` 边）→ `Component`（`HAS_WORK_ELEMENT` 边）层级正确（**共享 Process* 边词汇，不新增 HAS_SUBSYSTEM/HAS_COMPONENT**，见 README "图结构契约" 节）。
- DFMEA 的 System/Subsystem/Component 为语义/UI 名称（`graphPresentation.ts:239-240` 映射）。

### 门禁
- 推进 Step3 前：至少 1 个 Subsystem + 1 个 Component。

### 审计与落库
- Step2 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- 节点/边持久化到 graph_data。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `System`、`Subsystem`、`Component`（语义/UI 名称） |
| 关键字段 | name（各层） |
| 边类型 | `HAS_PROCESS_STEP`（System→Subsystem）、`HAS_WORK_ELEMENT`（Subsystem→Component） |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`） |
| E2E seed 前置 | 02.8 DFMEA draft + wizardScope |
| 通过条件 | 结构树 3 层齐全 + 边正确（共享 Process* 边）+ 审计 |
| 失败条件（FAILED） | 用了不存在的 HAS_SUBSYSTEM/HAS_COMPONENT 边；层级断裂；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- Step3 功能分析（见 02.10）。
- 方块图/边界图/接口矩阵的深度可视化（现有 `dfmea-wizard-tool-structure-guidance`，本子故事只验结构树）。
- 全图 schema migration（若需将 DFMEA 边改为 HAS_SUBSYSTEM/HAS_COMPONENT，另立改造；本 epic 保持共享 Process* 边）。

## 后续

- 结构树为 Step3 功能分析提供挂载点。
