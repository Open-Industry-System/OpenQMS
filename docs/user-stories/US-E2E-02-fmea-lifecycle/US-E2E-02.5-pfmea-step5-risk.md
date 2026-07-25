# 子故事 US-E2E-02.5：PFMEA Step5 风险分析

**状态**: 定稿 v2（2026-07-25），经代码评审修订
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step5-risk`（待生成）
**前置**: 02.4（Step4 失效链已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.5（过程 FMEA 步骤五：风险分析）
**AI_REQUIRED**: true（PC/DC 措施推荐）

## 故事

**作为** 前期策划质量工程师，**我想** 在向导 Step5 评分：三段式严重度 S（本厂 severity_plant / 客户 severity_customer / 终端用户 severity_user，取最大值）+ 频度 O（FailureCause.occurrence）+ 探测度 D（DetectionControl.detection），系统自动查 AIAG-VDA AP 表得出 AP（H/M/L），并维护 CC/SC 特殊特性，
**以便** 量化每个失效链的风险等级，识别高优先级项，为优化（Step6）提供排序依据。

## 背景 / 前置条件

- Step4 失效链已落库（FE/FC/PC/DC 节点就绪）。

## 主流程

1. `planning_qe` 在 Step5 为每行评分：
   - FE 三段式 S：`severity_plant`/`severity_customer`/`severity_user`（1-10），`severity = max(三者)`
   - FC 频度 O：`occurrence`（1-10）
   - DC 探测度 D：`detection`（1-10）
2. 系统自动查 AIAG-VDA AP 表得出 AP（**查表结果，非 S×O×D 乘积**；`utils/fmea.ts calculateAP` 查 AP 表）。
3. CC/SC 写入函数节点 `classification`（PFMEA 专有列）。
4. PC/DC 措施可触发 AI 推荐（`prevention_control`/`detection_control` trigger）。
5. 保存草稿。
6. 推进到 Step6。

## 业务规则 / 验收标准

### 结构完整性
- 三段式 S 字段均 >0（门禁要求三字段均 >0，避免退化为单 S）。
- `severity = max(severity_plant, severity_customer, severity_user)`。
- AP 为 S/O/D 组合的**查表结果**（1000 种组合查 AIAG-VDA AP 表，非乘积映射；`utils/fmea.ts` 的 `calculateAP`）。
- CC/SC 写入 `ProcessStepFunction`/`ProcessWorkElementFunction.classification`（PFMEA 专有，DFMEA 无）。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `prevention_control`/`detection_control` 推荐时，后端必须查询 4 来源，通过 `source_executions[]` 可观测（同 02.4）。

- **缺口处理**：现状仅接图(keyword)+结构+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step5 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | PFMEA 定义 |
|---|---|
| 落库实体 | `FailureEffect`（更新 severity_*）、`FailureCause`（更新 occurrence）、`DetectionControl`（更新 detection） |
| 关键字段 | FE.severity_plant/customer/user；FE.severity = max(三者)；FC.occurrence；DC.detection；AP（查表，非乘积） |
| 边类型 | 无新增（更新现有节点） |
| AI 触发器 | `prevention_control`、`detection_control` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.4 失效链 |
| 通过条件 | 三段式 S 均>0 + AP 查表正确 + CC/SC 写 classification + AI 查全 4 来源（source_executions 可观测）+ 采纳留痕 + 审计 |
| 失败条件（FAILED） | 三段式 S 任一为 0；AP 写成乘积或计算错误；CC/SC 写错字段；AI 未查 #2/#3；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（AI_REQUIRED=true） |

## 不在本子故事范围

- Step6 优化（RecommendedAction，见 02.6）。
- AP 表的逐格校验（现有 `utils/fmea.ts`，本子故事只验计算触发）。

## 后续

- 高 AP 行驱动 Step6 优化行动。
