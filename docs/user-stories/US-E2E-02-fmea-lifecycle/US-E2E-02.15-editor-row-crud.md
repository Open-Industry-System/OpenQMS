# 子故事 US-E2E-02.15：编辑器行级 CRUD + 图同步

**状态**: 定稿 v2（2026-07-25），经代码评审修订
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-editor-row-crud`（待生成）
**前置**: 02.7 或 02.14（向导已完成，或已有 draft FMEA）
**AI_REQUIRED**: false（纯结构编辑，AI 推荐见 02.16）

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师，**我想** 在 FMEA 编辑器内对失效链表格做行级增删改：增删行（addRow/deleteRow）、多效应（addEffect/deleteEffect）、多原因（addCause/deleteMode），且表格与图结构双向同步（buildRows），编辑保存保留向导元数据（wizardScope），
**以便** 在向导完成后继续细化失效链，灵活调整结构，且表格与图数据始终保持一致，不丢失向导上下文。

## 背景 / 前置条件

- 向导已完成（wizardScope.wizard_completed=true）或已有 draft FMEA 进入编辑器 `/fmea/{id}`。
- 编辑器基于 `utils/fmeaTable.ts` 的 `buildRows`/`createRowNodes` 实现图↔表格双向转换。
- **当前实现缺口**：编辑器保存仅 `{nodes, edges}`（`FMEAEditorPage.tsx:568`），可能覆盖 `wizardScope`（含 wizard_completed）——本子故事验收保留向导元数据。

## 主流程

1. `planning_qe` 在编辑器内：
   - `addRow`：为选中功能节点新增失效链行（创建 FM/FE/FC/PC/DC 节点 + 边）。
   - `deleteRow`：删除行，共享控制/行动节点仅在无其他行引用时删除（`deleteRowHelpers.planCauseDeletion`）。
   - `addEffect`/`deleteEffect`：多效应（FM 级共享列表）增删，同一单元格内编辑，不增加行数。
   - `addCause`/`deleteMode`：多原因/失效模式调整。
2. 每次编辑触发 `buildRows` 重算表格（图→表格）。
3. 保存（`PUT /api/fmea/{id}` graph_data）触发 `rowsToGraph`（表格→图），**保留 wizardScope**（不覆盖非表格 metadata）。
4. lock_version 递增（见 02.17）。

## 业务规则 / 验收标准

### 结构完整性（对齐 `fmeaTable.buildRows` 稳定契约）
- **一行对应一个 FM×FC**；无 cause 时单行 placeholder（key 后缀 `_null`）。
- **多效应是 FM 级共享列表**（`failureEffectNodeIds: string[]`），跨该 FM 的所有 cause 行共享，同一单元格内编辑，**不增加行数**（非 cause × effect 笛卡尔积）。
- 表格行与图节点一一对应（`buildRows` 双向一致）。
- 共享节点删除规则：PC/DC/RecommendedAction 节点仅在被引用数为 0 时删除（避免误删共享控制）。

### 可编辑状态
- 仅 DRAFT、REWORK 可编辑图（编辑器 PUT）；IN_REVIEW、APPROVED、ARCHIVED 的 PUT 必须拒绝（见 02.19 权限矩阵）。

### 向导元数据保留
- 编辑器保存（普通保存 + 冲突覆盖）**保留 wizardScope**（含 wizard_completed），不覆盖非表格 graph metadata。

### 审计与落库
- 编辑器保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- 节点/边/wizardScope 持久化到 graph_data。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `FailureMode`、`FailureEffect`、`FailureCause`、`PreventionControl`、`DetectionControl`、`RecommendedAction` |
| 关键字段 | 节点 name/id；边 source/target/type；wizardScope（保留） |
| 边类型 | `HAS_FAILURE_MODE`（功能→FM）、`EFFECT_OF`（FM→FE）、`CAUSE_OF`（FC→FM）、`PREVENTED_BY`（FC→PC）、`DETECTED_BY`（FC/FM→DC）、`OPTIMIZED_BY`（FC/FM→RecommendedAction） |
| AI 触发器 | 无（AI_REQUIRED=false，AI 推荐见 02.16） |
| 状态枚举 | FMEAState ∈ {DRAFT, REWORK}（仅二者可编辑） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`） |
| E2E seed 前置 | 02.7 或 02.14 完成的 draft FMEA |
| 通过条件 | 表格↔图双向一致（一行=FM×FC）+ 多效应为 FM 级共享（不增加行数）+ 共享节点删除规则正确 + 保存保留 wizardScope + 仅 DRAFT/REWORK 可编辑 + 审计 |
| 失败条件（FAILED） | 表格与图不一致；多效应写成笛卡尔积（增加行数）；误删共享节点；保存覆盖 wizardScope（丢失 wizard_completed）；IN_REVIEW/APPROVED 可编辑；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 编辑器内 AI 推荐下拉（见 02.16）。
- 协同编辑 + 冲突检测（见 02.17）。
- 版本快照（见 02.18）。

## 后续

- 行级编辑为 02.16 AI 推荐、02.17 协同、02.18 版本快照提供编辑载体。
