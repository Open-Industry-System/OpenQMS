# 子故事 US-E2E-02.3：PFMEA Step3 功能分析

**状态**: 定稿 v2（2026-07-25），经代码评审修订
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step3-function`（待生成）
**前置**: 02.2（Step2 结构树已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.3（过程 FMEA 步骤三：功能分析）
**AI_REQUIRED**: false（功能树由结构推导，无独立 AI 触发器）

## 故事

**作为** 前期策划质量工程师，**我想** 在向导 Step3 为每个结构节点定义功能树（过程项功能 / 过程步骤功能 / 工作要素功能），区分产品特性与过程特性，并维护 CC/SC 特殊特性标识，
**以便** 明确每个结构节点的功能与特性要求，为失效分析（Step4）的"功能否定→失效模式"推导提供基础。

## 背景 / 前置条件

- Step2 结构树已落库（ProcessItem/ProcessStep/ProcessWorkElement）。

## 主流程

1. `planning_qe` 在 Step3 为每个结构节点录入功能：
   - `ProcessItemFunction`（产品特性）
   - `ProcessStepFunction`（产品特性，CC/SC 可设）
   - `ProcessWorkElementFunction`（过程特性，CC/SC 可设）
2. `HAS_FUNCTION` 边：结构节点 → 功能节点。
3. `FUNCTION_MAPPED_TO` 边：不同层级功能之间的功能关系（**非功能→结构**，见 README "图结构契约" 节）。
4. CC/SC 写入函数节点 `classification` 字段（复用现有字段，不新增）。
5. 保存草稿。
6. 推进到 Step4。

## 业务规则 / 验收标准

### 结构完整性
- **每个纳入分析范围的结构节点都有功能节点**（`HAS_FUNCTION` 边），非仅"至少一个功能"（见 README "评审决议" 节）。
- `FUNCTION_MAPPED_TO` 边连接不同层级功能（如 ProcessItemFunction → ProcessStepFunction）。
- CC/SC 写入 `ProcessStepFunction`/`ProcessWorkElementFunction` 的 `classification` 字段（非 FailureCause.special_characteristic）。

### 门禁
- 推进 Step4 前：每个结构节点都有功能节点（HAS_FUNCTION 边齐全）。

### 审计与落库
- Step3 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- 节点/边持久化到 graph_data。

## 验收契约（字段级）

| 项 | PFMEA 定义 |
|---|---|
| 落库实体 | `ProcessItemFunction`、`ProcessStepFunction`、`ProcessWorkElementFunction` |
| 关键字段 | Function.name；Function.classification（CC/SC） |
| 边类型 | `HAS_FUNCTION`（结构→功能）、`FUNCTION_MAPPED_TO`（功能↔功能） |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`） |
| E2E seed 前置 | 02.2 结构树 |
| 通过条件 | 每个结构节点都有功能节点 + FUNCTION_MAPPED_TO 边连接层级功能 + CC/SC 写 classification 字段 + 审计 |
| 失败条件（FAILED） | 结构节点缺功能节点；CC/SC 写错字段；FUNCTION_MAPPED_TO 误连功能→结构；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- Step4 失效分析（见 02.4）。
- 功能树的自动推导算法深度（现有由结构推导，本子故事只验结果）。

## 后续

- 功能树为 Step4 失效分析提供 FM 挂载点（FM 挂 ProcessStepFunction）。
