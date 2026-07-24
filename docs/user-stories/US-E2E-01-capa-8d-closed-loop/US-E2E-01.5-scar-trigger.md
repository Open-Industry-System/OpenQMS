# 子故事 US-E2E-01.5：8D → SCAR 触发与回写

**状态**: 定稿 v1（2026-07-08）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-scar-trigger`
**前置**: 01.1、01.3（8D 有 D3 遏制数据 + D4 根因，方有 SCAR 上下文）
**AI_REQUIRED**: false（无 AI 步骤；功能错误 → `FAILED`）

## 故事

**作为** 现场质量工程师，**我想** 来料不良的 8D 在 D3 遏制或 D4 根因阶段，
能一键发起 SCAR（Supplier Corrective Action Request），携带 8D 上下文，
SCAR 单号回写 8D，SCAR 状态变更同步回 8D，
**以便** 供应商纠正措施被正式触发、8D 与 SCAR 关联可追溯可审计。

## 背景 / 前置条件

- 系统已部署，8D 为来料不良场景（涉及供应商），已推进至 D3/D4（01.1/01.3 就绪）。
- 系统已有 SCAR 模块（`SupplierSCAR` 模型存在）。

## 联动关系

- **8D → SCAR**：从 8D 一键发起 SCAR，携带 8D 单号、不良描述、受影响批次等上下文。
- **SCAR → 8D**：SCAR 单号回写 8D，建立关联；SCAR 状态变更同步回 8D 可见。

## 主流程

1. field_qe 在来料不良 8D 的 D3 或 D4 阶段，触发【发起 SCAR】。
2. 系统创建 SCAR，携带 8D 上下文（8D 单号、不良描述、受影响批次）。
3. SCAR 单号回写到 8D，建立关联。
4. SCAR 状态变更（如创建/处理中/关闭）同步回 8D 可见。

## 业务规则 / 验收标准

- **SCAR 触发**：来料不良 8D 可一键发起 SCAR，携带上下文（8D 单号、不良描述、受影响批次）。
- **单号回写**：SCAR 单号回写到 8D，建立关联关系。
- **状态同步**：SCAR 状态变更同步回 8D 可见（至少创建/关闭两个状态）。
- **关联审计**：8D→SCAR 触发与状态同步写审计日志。
- **数据落库**：8D-SCAR 关联关系正确持久化，可追溯。
- **执行验证**：E2E 断言触发→回写→状态同步链路完整，只验结构/关联，不验内容。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `supplier_scars`（SCAR，已有模型）、`capa_eightd.scar_ref_id`（回写 SCAR 单号关联） |
| 关键字段 | scar.capa_id（关联 8D）、scar.status∈{open,in_progress,closed}、capa.scar_ref_id；同步事件含 scar_status |
| 状态枚举 | SCAR: open→in_progress→closed；同步回 8D 的状态可见 |
| 审计事件 | `SCAR_TRIGGERED`（含 capa_id、scar_id）、`SCAR_STATUS_SYNCED`（含 scar_status） |
| E2E seed 前置 | 来料不良 8D 推进到 D3/D4；涉及供应商 |
| 通过条件 | 一键发起 SCAR + 上下文携带 + 单号回写 8D + 状态同步可见 + 审计 |
| 失败条件（FAILED） | 无法触发；上下文缺失；单号未回写；状态未同步；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- SCAR 模块的完整业务流程（SCAR 本身的发起/跟踪/关闭由供应商模块负责，本子故事只管 8D 侧触发与回写）。
- 8D↔FMEA 双向追溯（见 01.4）、供应商风险（见 01.6）。

## 后续

- 8D 关闭自动触发 SCAR 关闭的联动为后续迭代。
