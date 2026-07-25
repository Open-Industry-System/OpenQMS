# 子故事 US-E2E-02.9：DFMEA Step2 结构分析

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step2-structure`
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
   - `Subsystem`（`HAS_SUBSYSTEM` 边）
   - `Component`（`HAS_COMPONENT` 边，挂 Subsystem）
2. 结构树左侧面板实时展示层级。
3. 保存草稿。
4. 推进到 Step3。

## 业务规则 / 验收标准

### 结构完整性
- `System` → `Subsystem`（`HAS_SUBSYSTEM` 边）→ `Component`（`HAS_COMPONENT` 边）层级正确。

### 门禁
- 推进 Step3 前：至少 1 个 Subsystem + 1 个 Component。

### 审计与落库
- Step2 保存写 AuditLog。
- 节点/边持久化到 graph_data。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `System`、`Subsystem`、`Component` |
| 关键字段 | name（各层） |
| 边类型 | `HAS_SUBSYSTEM`、`HAS_COMPONENT` |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | `fmea.updated` |
| E2E seed 前置 | 02.8 DFMEA draft + wizardScope |
| 通过条件 | 结构树 3 层齐全 + 边正确 + 审计 |
| 失败条件（FAILED） | 层级断裂；边缺失；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- Step3 功能分析（见 02.10）。
- 方块图/边界图/接口矩阵的深度可视化（现有 `dfmea-wizard-tool-structure-guidance`，本子故事只验结构树）。

## 后续

- 结构树为 Step3 功能分析提供挂载点。
