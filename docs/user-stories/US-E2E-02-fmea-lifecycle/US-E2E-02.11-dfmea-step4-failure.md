# 子故事 US-E2E-02.11：DFMEA Step4 失效分析

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step4-failure`
**前置**: 02.10（Step3 功能树已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.4（设计 FMEA 步骤四：失效分析）
**AI_REQUIRED**: true（FM/FE/FC + PC/DC 含 AI 推荐）

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step4 定义失效链：失效模式(FM) → 失效效应(FE) / 失效原因(FC) + 预防控制(PC) + 探测控制(DC)，其中 FM/FE/FC 由 AI 推荐（查询全部知识库后生成），
**以便** 完整描述设计失效链，为风险分析（Step5）提供评分对象。

## 背景 / 前置条件

- Step3 功能树已落库。

## 主流程

1. `planning_qe` 在 Step4 为每个功能节点录入失效链：
   - `FailureMode`（挂 `ComponentFunction`/`SubsystemFunction`，`HAS_FAILURE_MODE` 边）
   - `FailureEffect`（`EFFECT_OF` 边）
   - `FailureCause`（`CAUSE_OF` 边）
   - `PreventionControl`（`PREVENTED_BY` 边）
   - `DetectionControl`（`DETECTED_BY` 边）
2. FM/FE/FC 字段触发 AI 推荐（`failure_mode`/`failure_effect`/`failure_cause` trigger）。
3. 采纳或手工录入。
4. 保存草稿。
5. 推进到 Step5。

## 业务规则 / 验收标准

### 结构完整性
- 失效链边齐全（同 02.4）。
- FM 挂 DFMEA 功能节点（ComponentFunction/SubsystemFunction）。
- DFMEA 无 4M 上下文（PFMEA 专有）。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `failure_mode`/`failure_effect`/`failure_cause`/`prevention_control`/`detection_control` 推荐时，后端必须查询 4 来源（同 02.4）。

- **缺口处理**：现状仅接图(keyword)+结构+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step4 保存写 AuditLog。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `FailureMode`、`FailureEffect`、`FailureCause`、`PreventionControl`、`DetectionControl` |
| 关键字段 | FM.name；FE.name；FC.name；PC.name；DC.name |
| 边类型 | `HAS_FAILURE_MODE`、`EFFECT_OF`、`CAUSE_OF`、`PREVENTED_BY`、`DETECTED_BY` |
| AI 触发器 | `failure_mode`、`failure_effect`、`failure_cause`、`prevention_control`、`detection_control` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | `fmea.updated`、`ADOPT_RECOMMENDATION` |
| E2E seed 前置 | 02.10 功能树 |
| 通过条件 | 失效链边齐全 + FM 挂 DFMEA 功能节点 + AI 查全 4 来源 + 采纳留痕 + 审计 |
| 失败条件（FAILED） | 失效链断裂；FM 挂错层级；AI 未查 #2/#3；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- Step5 风险分析（见 02.12）。

## 后续

- 失效链节点为 Step5 提供 S/O/D 评分对象。
