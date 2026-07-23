# 子故事 US-E2E-01.7：D8 关闭前文档更新审核（影响分析 + 自动化审核门禁）

**状态**: 定稿 v2（2026-07-23）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-doc-update-gate`
**前置**: 01.2、01.3（8D 根因+预防 node-action 数据就绪，方可知哪些文档受影响）
**AI_REQUIRED**: true（文档影响分析用 LLM；无 LLM 凭证 → `BLOCKED`）

> **责任边界（评审修订）**：本子故事负责**门禁逻辑**——文档影响分析 + 自动审核 + 阻断/放行。审批壳归 01.3，本子故事不验审批，只通过状态机衔接（D7_COMPLETED→D8_GATE_PENDING→审核通过→D8_APPROVAL_PENDING）。
>
> **范围修订（v2 / 设计 C1）**：门禁**只审有版本表的文档**：控制计划（Control Plan）与 FMEA（PFMEA/DFMEA）。`doc_type` 枚举可保留 `sop` / `inspection_sop` / `other` 供前向兼容，但本切片**不产出、不验收** SOP 类。SOP/作业指导书实体与版本管理另立故事；不得为凑「≥3 类」伪造第三类。

## 故事

**作为** 8D 团队负责人 / 现场质量工程师，**我想** 在 8D 报告完成、D8 关闭审批前，
系统自动分析 8D 报告识别需更新的相关受控文档（本切片：**控制计划、FMEA**），
并自动化审核这些文档的更新情况（是否已更新、更新是否到位），
D8 关闭审批前必须通过此审核门禁，
**以便** 8D 发现的改进真正落到受控文档、文档与实际不脱节、关闭审批有据可依。

## 背景 / 前置条件

- 系统已部署，8D 已推进至 D7（根因 + D7 node-action 已落库，01.2/01.3 就绪）。
- 对应产品已有控制计划、FMEA 受控文档（含版本快照）。
- AI 步骤必须配置有效 LLM 凭证（文档影响分析用 LLM；优先 DB `system_settings`，回退 `.env.e2e`）。

## 能力 A：文档影响分析

8D 报告完成后（D7 填写后），系统自动分析 8D 报告，识别需更新的相关受控文档：

- **本切片受影响文档类型（验收）**：控制计划（Control Plan）、FMEA（PFMEA/DFMEA）。
- **枚举保留、本切片不验收**：作业指导书（SOP）、检验作业指导书、其他受控文档——无版本化实体，不进入 allowlist / 影响清单产出。
- **影响分析依据**：8D 的根因、D5 永久措施、D7 预防 node-action、严重度。
- **输出**：受影响文档清单 + 每项更新建议（哪些章节/节点需更新、更新方向）。
- **AI 辅助**：AI 基于 8D 报告内容分析受影响文档范围 + 更新建议（辅助，工程师确认）。

## 能力 B：文档更新自动化审核（D8 关闭门禁）

D8 关闭审批前，系统自动化审核相关文档的更新情况：

- **审核内容**（每项受影响文档，仅 CP / FMEA）：
  - 是否已更新（版本号 bump、更新时间在 8D 发起之后）；
  - 更新是否到位（关键更新点是否覆盖——控制计划是否新增/修改对应控制特性、FMEA 节点是否更新）；
  - 审核状态（通过 / 待更新 / 更新不完整）。
- **门禁规则**：
  - D8 关闭审批前，文档更新审核必须通过（所有受影响文档状态 = 通过）；
  - 未通过时，D8_GATE_PENDING 不可推进到 D8_APPROVAL_PENDING（门禁阻断）；
  - **延期处理规则**：延期 = 记录待办（理由+责任人+期限）但**仍阻断关闭**，8D 不可关闭直至文档更新审核通过；不设旁路。
- **审核报告**：生成文档更新审核报告，含每项受影响文档的审核状态 + 证据（版本号、更新点）。

## 主流程

1. field_qe 完成 D7（含 node-action），8D 报告数据就绪 → D7_COMPLETED。
2. 系统自动进入 D8_GATE_PENDING，触发文档影响分析：识别受影响文档清单 + 更新建议（CP/FMEA）。
3. 工程师按建议更新相关文档（在 FMEA/控制计划模块操作）。
4. 系统自动触发文档更新审核。
5. 审核通过 → D8_GATE_PENDING→D8_APPROVAL_PENDING（可审批）；未通过 → 门禁阻断；延期处理 → 记录待办但仍阻断。
6. 审核报告 + 门禁决策写审计日志。

## 业务规则 / 验收标准

- **文档影响分析**：8D 报告完成后触发，识别受影响文档清单（**至少覆盖控制计划 + FMEA 两类**，且仅此两类进入本切片验收）；每项带更新建议；清单落库可追溯。
- **文档更新审核门禁**：
  - D8_GATE_PENDING 自动审核，每项受影响文档有审核状态；
  - 未全部通过时不可推进到 D8_APPROVAL_PENDING；
  - 延期仍阻断关闭；
  - 审核依据 = 文档版本号 bump + 更新时间 + 关键更新点覆盖。
- **审核报告 / 审计 / 落库 / 执行验证 / 与 01.3 衔接**：同 v1 语义（门禁只管到 D8_APPROVAL_PENDING，不验审批）。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `capa_docg_analysis` / `capa_docg_audit` / `capa_docg_decision`（实现表名；故事旧称 impact/audit/gate 映射到此） |
| 关键字段 | impact.doc_type **验收产出** ∈ {control_plan, fmea}（枚举可含 sop/inspection_sop/other 但不产出）；audit.status∈{passed,pending_update,incomplete}；gate.decision∈{passed,blocked,deferred} |
| 状态枚举 | D7_COMPLETED→D8_GATE_PENDING→（门禁通过）→D8_APPROVAL_PENDING；延期仍停留 D8_GATE_PENDING |
| 审计事件 | `DOC_IMPACT_ANALYZED`、`DOC_UPDATE_AUDITED`、`DOC_GATE_BLOCKED`、`DOC_GATE_PASSED`、`DOC_GATE_DEFERRED` |
| E2E seed 前置 | 8D 在 D8_GATE_PENDING；同产品线有控制计划+FMEA（含版本，如 `CP-E2E-DOCGATE-001` + `PFMEA-E2E-DOCGATE-001`） |
| 通过条件 | 影响分析识别 **≥2 类文档（control_plan + fmea）** + 审核每项有状态 + 门禁阻断/放行/延期路径可验 + 审计 |
| 失败条件（FAILED） | 影响分析缺 CP 或 FMEA 类；审核状态缺失；门禁未阻断；延期允许关闭；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- **SOP / 检验 SOP / 其他受控文档**的实体、版本管理与门禁审核（系统无版本表；设计 C1；另立故事）。
- 受影响文档本身的更新操作（在 FMEA/控制计划模块完成）。
- 文档更新内容的质量审核、完整版本工作流。
- 审批壳（见 01.3）。
- 延期到期跟踪闭环（后续迭代）。

## 后续

- SOP 实体 + 版本表接入后，可扩展 allowlist 与验收类数（不改变本 v2 通过条件直至故事再升版）。
- 延期处理的到期跟踪与升级为后续迭代。
- 文档更新内容的质量自动评审为后续迭代。

---

## 实现注记（2026-07-14；v2 对齐 2026-07-23）

**设计 / 计划**：
- Spec：`docs/superpowers/specs/2026-07-13-us-e2e-01.7-doc-update-gate-design.md`（**C1 窄范围：只审 control_plan + fmea**）
- Plan：`docs/superpowers/plans/2026-07-13-us-e2e-01.7-doc-update-gate.md`

**落地摘要**：
- 3 表 `capa_docg_{analysis,audit,decision}` + 迁移 `20260713_doc_gate`
- 服务 `capa_doc_gate_service.py`：`_build_allowlist` 仅 CP+FMEA
- `advance_capa` 边 `D8_GATE_PENDING→D8_APPROVAL_PENDING` 接入文档门禁
- 7 路由 `/api/capa/{id}/doc-gate/*`；无 LLM → 422 blocked
- 前端 `DocGatePanel`；E2E seed `8D-E2E-DOCGATE-001`

**v2 相对 v1**：验收「≥3 类含 SOP」→「≥2 类 CP+FMEA」；SOP 从通过条件移出到「不在范围 / 前向兼容枚举」。
