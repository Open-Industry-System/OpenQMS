# 子故事 US-E2E-02.4：PFMEA Step4 失效分析

**状态**: 定稿 v2（2026-07-25），经代码评审修订
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step4-failure`（待生成）
**前置**: 02.3（Step3 功能树已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.4（过程 FMEA 步骤四：失效分析）
**AI_REQUIRED**: true（FM/FE/FC + PC/DC 含 AI 推荐）

## 故事

**作为** 前期策划质量工程师，**我想** 在向导 Step4 定义失效链：失效模式(FM) → 失效效应(FE) / 失效原因(FC) + 预防控制(PC) + 探测控制(DC)，其中 FM/FE/FC 由 AI 推荐（查询全部知识库后生成），
**以便** 完整描述"功能怎么坏了 → 后果是什么 → 为什么坏"，并挂载控制措施，为风险分析（Step5）提供 S/O/D 评分对象。

## 背景 / 前置条件

- Step3 功能树已落库，FM 挂 `ProcessStepFunction`（`HAS_FAILURE_MODE` 边）。

## 主流程

1. `planning_qe` 在 Step4 为每个功能节点录入失效链：
   - `FailureMode`（挂 `ProcessStepFunction`，`HAS_FAILURE_MODE` 边）
   - `FailureEffect`（`EFFECT_OF` 边：FM → FE）
   - `FailureCause`（`CAUSE_OF` 边：FC → FM，4M 上下文以工作要素为录入提示）
   - `PreventionControl`（`PREVENTED_BY` 边：FC → PC）
   - `DetectionControl`（`DETECTED_BY` 边：FC/FM → DC）
2. FM/FE/FC 字段触发 AI 推荐（`failure_mode`/`failure_effect`/`failure_cause` trigger），查询全知识库后下拉展示。
3. PC/DC 字段可触发 AI 推荐（`prevention_control`/`detection_control` trigger）。
4. 采纳推荐或手工录入。
5. 保存草稿。
6. 推进到 Step5。

## 业务规则 / 验收标准

### 结构完整性
- 失效链边方向正确（见 README "图结构契约" 节）：
  - `<function node> ─HAS_FAILURE_MODE→ FM`
  - `FM ─EFFECT_OF→ FE`
  - `FC ─CAUSE_OF→ FM`
  - `FC ─PREVENTED_BY→ PC`
  - `FC/FM ─DETECTED_BY→ DC`
- FM 挂 `ProcessStepFunction`（不挂 ProcessWorkElementFunction，对齐 2026-05-20 数据结构文档 §2.2）。
- 多效应：1 FM × N FE → FM 级共享列表（`failureEffectNodeIds`），跨该 FM 的所有 cause 行共享（非 cause × effect 笛卡尔积，见 README "编辑器行模型" 节）。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `failure_mode`/`failure_effect`/`failure_cause`/`prevention_control`/`detection_control` 推荐时，后端必须查询 4 来源，通过 `source_executions[]` 可观测（见 README "AI 推荐知识库查询契约" 节）。

- **缺口处理**：现状仅接 #1(keyword)+#4+LLM，**#2/#3 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step4 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`（`action="ADOPT_RECOMMENDATION"`，changed_fields 含 field_id/source/stage_index/adopted_text；当前无采纳元数据 API，见 README "AI 采纳审计契约" 节）。

## 验收契约（字段级）

| 项 | PFMEA 定义 |
|---|---|
| 落库实体 | `FailureMode`、`FailureEffect`、`FailureCause`、`PreventionControl`、`DetectionControl` |
| 关键字段 | FM.name；FE.name；FC.name；PC.name；DC.name |
| 边类型 | `HAS_FAILURE_MODE`（功能→FM）、`EFFECT_OF`（FM→FE）、`CAUSE_OF`（FC→FM）、`PREVENTED_BY`（FC→PC）、`DETECTED_BY`（FC/FM→DC） |
| AI 触发器 | `failure_mode`、`failure_effect`、`failure_cause`、`prevention_control`、`detection_control` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.3 功能树 |
| 通过条件 | 失效链边方向正确 + FM 挂 ProcessStepFunction + 多效应为 FM 级共享 + AI 查全 4 来源（source_executions 可观测）+ 采纳留痕 + 审计 |
| 失败条件（FAILED） | 失效链边方向反了；FM 挂错层级；多效应写成笛卡尔积；AI 未查 #2/#3（source_executions 缺）；推荐无 source；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（AI_REQUIRED=true） |

## 不在本子故事范围

- Step5 风险分析（S/O/D/AP 评分，见 02.5）。
- 失效链的自动推导算法深度（现有规则 + AI，本子故事只验结果与来源）。

## 后续

- 失效链节点为 Step5 风险分析提供 S/FE、O/FC、D/DC 评分对象。
