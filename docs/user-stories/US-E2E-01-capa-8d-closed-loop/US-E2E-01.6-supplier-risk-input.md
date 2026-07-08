# 子故事 US-E2E-01.6：8D → 供应商风险评级输入

**状态**: 定稿 v1（2026-07-08）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-supplier-risk-input`
**前置**: 01.1、01.3（8D 有严重度 + 处置结果 + D4 根因，方有风险输入）
**AI_REQUIRED**: false（无 AI 步骤；功能错误 → `FAILED`）

## 故事

**作为** 现场质量工程师 / 供应商质量管理者，**我想** 涉及供应商的来料不良 8D，
其严重度 + 处置结果 + 是否重复发生，作为供应商风险评级的输入传递给供应商风险模块，
供应商风险评级变化时关联的 8D 可见，
**以便** 8D 问题影响供应商评级、风险联动可追溯。

## 背景 / 前置条件

- 系统已部署，8D 为来料不良场景（涉及供应商），已推进至 D4/D7（01.1/01.3 就绪）。
- 系统已有供应商风险模块（`supplier_risk` 模型：SupplierRiskAlert/Config 等）。

## 联动关系

- **8D → 供应商风险**：8D 的严重度 + 处置结果 + 是否重复发生，作为供应商风险评级的输入。
- **供应商风险 → 8D**：供应商风险评级变化时，关联的 8D 可见该影响。

## 主流程

1. field_qe 推进来料不良 8D，D4 根因 + D7 处置结果落库（01.1/01.3）。
2. 供应商风险评级系统读取本 8D 的严重度 + 处置结果 + 是否重复发生，作为评级输入。
3. 供应商风险评级变化时，关联的 8D 可见该影响。

## 业务规则 / 验收标准

- **8D → 供应商风险**：涉及供应商的 8D，其严重度 + 处置结果 + 是否重复发生作为供应商风险评级输入传递。
- **供应商风险 → 8D**：供应商风险评级变化关联到 8D 可见（8D 详情可见风险影响记录）。
- **联动审计**：8D→供应商风险输入传递 + 评级变化写审计日志。
- **数据落库**：8D-供应商风险关联关系正确持久化，可追溯。
- **执行验证**：E2E 断言输入传递 + 评级变化回显链路完整，只验结构/关联，不验评级算法。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `supplier_risk_alerts`（风险告警，已有模型）、`capa_eightd`（severity、d4_root_cause、d7_prevention 作为输入） |
| 关键字段 | risk_alert.supplier_id、risk_alert.source_capa_id（关联 8D）、risk_alert.risk_level∈{high,medium,low}、risk_alert.input_fields{severity,disposition,repeat}；capa 可读 risk_alert 列表 |
| 状态枚举 | risk_level∈{high,medium,low} |
| 审计事件 | `SUPPLIER_RISK_INPUT_SENT`（含 capa_id、supplier_id、input_fields）、`SUPPLIER_RISK_CHANGED`（含 risk_level） |
| E2E seed 前置 | 来料不良 8D 涉及供应商；供应商风险模块可用 |
| 通过条件 | 输入字段传递 + 评级变化回显 8D + 审计 |
| 失败条件（FAILED） | 输入未传递；评级变化 8D 不可见；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- 供应商风险评级算法的完整定义（本子故事只管 8D 作为输入的传递，评级算法由供应商模块负责）。
- SCAR 触发（见 01.5）、FMEA 双向追溯（见 01.4）。

## 后续

- 供应商风险评级算法的细化与校准为后续迭代。
