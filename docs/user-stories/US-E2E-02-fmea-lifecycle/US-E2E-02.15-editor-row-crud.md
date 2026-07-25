# 子故事 US-E2E-02.15：编辑器行级 CRUD + 图同步

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-editor-row-crud`
**前置**: 02.7 或 02.14（向导已完成，或已有 draft FMEA）
**AI_REQUIRED**: false（纯结构编辑，AI 推荐见 02.16）

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师，**我想** 在 FMEA 编辑器内对失效链表格做行级增删改：增删行（addRow/deleteRow）、多效应（addEffect/deleteEffect）、多原因（addCause/deleteMode），且表格与图结构双向同步（buildRows），
**以便** 在向导完成后继续细化失效链，灵活调整结构，且表格与图数据始终保持一致。

## 背景 / 前置条件

- 向导已完成（wizard_completed=true）或已有 draft FMEA 进入编辑器 `/fmea/{id}`。
- 编辑器基于 `utils/fmeaTable.ts` 的 `buildRows`/`createRowNodes` 实现图↔表格双向转换。

## 主流程

1. `planning_qe` 在编辑器内：
   - `addRow`：为选中功能节点新增失效链行（创建 FM/FE/FC/PC/DC 节点 + 边）。
   - `deleteRow`：删除行，共享控制/行动节点仅在无其他行引用时删除（`deleteRowHelpers.planCauseDeletion`）。
   - `addEffect`/`deleteEffect`：多效应扇出/收起。
   - `addCause`/`deleteMode`：多原因/失效模式调整。
2. 每次编辑触发 `buildRows` 重算表格（图→表格）。
3. 保存（`PUT /api/fmea/{id}` graph_data）触发 `rowsToGraph`（表格→图）。
4. lock_version 递增（见 02.17）。

## 业务规则 / 验收标准

### 结构完整性
- 表格行与图节点一一对应（`buildRows` 双向一致）。
- 多效应：1 FM × N FE → 表格扇出 N 行（行按 cause × effect 配对）。
- 共享节点删除规则：PC/DC/RecommendedAction 节点仅在被引用数为 0 时删除（避免误删共享控制）。

### 审计与落库
- 编辑器保存写 AuditLog（`UPDATE` graph_data）。
- 节点/边持久化到 graph_data。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `FailureMode`、`FailureEffect`、`FailureCause`、`PreventionControl`、`DetectionControl`、`RecommendedAction` |
| 关键字段 | 节点 name/id；边 source/target/type |
| 边类型 | `HAS_FAILURE_MODE`、`EFFECT_OF`、`CAUSE_OF`、`PREVENTED_BY`、`DETECTED_BY`、`OPTIMIZED_BY` |
| AI 触发器 | 无（AI_REQUIRED=false，AI 推荐见 02.16） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | `fmea.updated`（graph_data，含 lock_version 递增） |
| E2E seed 前置 | 02.7 或 02.14 完成的 draft FMEA |
| 通过条件 | 表格↔图双向一致 + 多效应扇出正确 + 共享节点删除规则正确 + 审计 |
| 失败条件（FAILED） | 表格与图不一致；多效应扇出错误；误删共享节点；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 编辑器内 AI 推荐下拉（见 02.16）。
- 协同编辑 + 冲突检测（见 02.17）。
- 版本快照（见 02.18）。

## 后续

- 行级编辑为 02.16 AI 推荐、02.17 协同、02.18 版本快照提供编辑载体。
