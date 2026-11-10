# 子故事 US-E2E-02.10：DFMEA Step3 功能分析

**状态**: 定稿 v3（2026-11-03），结构化特性契约同步
**所属 epic**: US-E2E-02（README.md v4）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step3-function`（已同步；运行结果另见验收证据）
**前置**: 02.9（Step2 结构树已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.3（设计 FMEA 步骤三：功能分析）
**AI_REQUIRED**: false

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step3 为每个结构节点定义功能树（系统功能 / 子系统功能 / 零部件功能），含参数图(P图)辅助，区分要求与功能，
**以便** 明确每个结构节点的功能与要求，为失效分析（Step4）的"功能否定→失效模式"推导提供基础。

## 背景 / 前置条件

- Step2 结构树已落库（System/Subsystem/Component）。

## 主流程

1. `planning_qe` 在 Step3 为每个结构节点录入功能：
   - `ProcessItemFunction` / `ProcessStepFunction` / `ProcessWorkElementFunction`（**DFMEA 复用 Process*Function 类型，无独立 SystemFunction 类型**，见 `schemas/fmea.py:6-9` 注释与 README "图结构契约" 节）。
2. `HAS_FUNCTION` 边：结构节点 → 功能节点。
3. `FUNCTION_MAPPED_TO` 边：不同层级功能之间的功能关系（**非功能→结构**）。
4. 保存草稿。
5. 推进到 Step4。

## 业务规则 / 验收标准

### 结构完整性
- **每个纳入分析范围的结构节点都有功能节点**（`HAS_FUNCTION` 边），非仅"至少一个功能"。
- `FUNCTION_MAPPED_TO` 边连接不同层级功能（如 SystemFunction 语义 → SubsystemFunction 语义，实际复用 Process*Function 类型）。
- DFMEA 标准风险表不新增 CC/SC 列；结构化特性的可选 classification 是独立内部数据，不代表标准新增要求。System/Subsystem/Component 的真实 HAS_FUNCTION 所属决定 kind=product，不能按复用 Process*Function 名称误判为过程。

### 门禁
- 推进 Step4 前：每个结构节点都有功能节点（HAS_FUNCTION 边齐全）。

### 审计与落库
- Step3 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `ProcessItemFunction`、`ProcessStepFunction`、`ProcessWorkElementFunction`（复用，非独立 SystemFunction） |
| 关键字段 | Function.name；characteristics[]（所有 DFMEA 特性 kind=product） |
| 边类型 | `HAS_FUNCTION`（结构→功能）、`FUNCTION_MAPPED_TO`（功能↔功能） |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`） |
| E2E seed 前置 | 02.9 结构树 |
| 通过条件 | 每个结构节点都有功能节点 + FUNCTION_MAPPED_TO 边连接层级功能 + 审计 |
| 失败条件（FAILED） | 用了不存在的 SystemFunction 类型；结构节点缺功能节点；FUNCTION_MAPPED_TO 误连功能→结构；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- Step4 失效分析（见 02.11）。
- 参数图(P图)的深度可视化（现有 `dfmea-wizard-pcdc-ai`，本子故事只验功能树）。

## 后续

- 功能树为 Step4 失效分析提供 FM 挂载点。

## 2026-11-03 结构化特性补充验收

- `characteristics` 缺失/null 是 legacy，只提示参考，不自动转换、保存不补空数组；显式 `[]` 是确认无特性，禁止回退旧功能字段。
- 每项独立 UUID、kind、名称、规范、单位、可选特殊分类、依据；改名不换 UUID，名称不能为空。按真实唯一 `HAS_FUNCTION` 所属及 FMEA 类型判断 kind；缺失／歧义须复核，不猜测。
- PFMEA 同一工序步骤功能录入 **2 产品**，其工作要素功能录入 **3 过程**；过程只能关联同工序产品 UUID。保存刷新核对集合、规范与分类分离。DFMEA 共享功能类型仍全部为 product。
- 编辑器行级 CRUD／wizardScope、标准表头／结构边不变；approved 写保护和历史快照只读，不迁移历史批准数据。
- 本次特性专项浏览器及完整检查结果见 [纠偏验收证据](../../development/characteristic-correction-acceptance.md)，并非整个子故事（含 AI 等）重新全量认证。
