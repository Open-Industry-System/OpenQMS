# 子故事 US-E2E-02.13：DFMEA Step6 优化

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step6-optimization`
**前置**: 02.12（Step5 风险分析已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.6（设计 FMEA 步骤六：优化）
**AI_REQUIRED**: true（RecommendedAction 含 AI 推荐措施）

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step6 为高风险失效链（AP=H/M）创建优化行动（RecommendedAction），含负责人/截止日期/状态/措施描述/目标 S′O′D′AP′，其中措施由 AI 推荐（查询全部知识库后生成），
**以便** 明确降低设计风险的行动项与责任，可追踪执行状态。

## 背景 / 前置条件

- Step5 风险分析已落库，AP 已计算。

## 主流程

1. `planning_qe` 在 Step6 为高 AP 行创建 `RecommendedAction`（字段同 02.6）。
2. `OPTIMIZED_BY` 边连接失效链节点。
3. AI 推荐 `optimization` trigger。
4. 保存草稿。
5. 推进到 Step7。

## 业务规则 / 验收标准

### 结构完整性
- `RecommendedAction` 节点字段完整（同 02.6）。
- `OPTIMIZED_BY` 边指向失效链节点。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `optimization` 推荐时，后端必须查询 4 来源（同 02.4）。

- **缺口处理**：现状仅接图(keyword)+结构+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step6 保存写 AuditLog。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `RecommendedAction` + `OPTIMIZED_BY` 边 |
| 关键字段 | owner、due_date、status、action_text、target_severity/occurrence/detection/ap |
| 边类型 | `OPTIMIZED_BY` |
| AI 触发器 | `optimization` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT）；RecommendedAction.status ∈ {open, in_progress, completed} |
| 审计事件 | `fmea.updated`、`ADOPT_RECOMMENDATION` |
| E2E seed 前置 | 02.12 风险分析 |
| 通过条件 | 字段完整 + 边正确 + AI 查全 4 来源 + 采纳留痕 + 审计 |
| 失败条件（FAILED） | 字段缺失；边缺失；AI 未查 #2/#3；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- Step7 结果文件化（见 02.14）。

## 后续

- RecommendedAction 为 Step7 提供优化措施汇总。
