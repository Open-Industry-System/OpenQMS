# Gap Analysis：US-E2E-01 v8.1 epic vs 现有实现

**日期**: 2026-07-08
**对照对象**: `docs/user-stories/US-E2E-01-capa-8d-closed-loop/`（epic 评审稿 v8.1 + 10 子故事，愿景态）
**方法**: 逐条验收标准对照现有实现（codegraph + 文件检索），标注 ✅已实现 / ⚠️部分实现 / ❌未实现
**范围**: 只标注 gap，不做实现方案设计

## 摘要

| 子故事 | AI_REQUIRED | 状态 | 主要 gap |
|---|---|---|---|
| 01.1 D3 遏制 | true | ❌ 基本未实现 | 无数据导入流程、无受影响范围分析、无 AI 遏制建议（仅 D3 文本草稿）；ERP 数据模型可复用 |
| 01.2 12 源推荐 | true | ✅ 基本已实现 | 12 阶段编排器 + 全源接入已就绪（Spec B 已交付）；仅前端面板/AP-S-O-D 展示待核 |
| 01.3 D4 验证+D7+审批壳 | true | ⚠️ 大部分已实现 | 验证 method 非枚举、无回退计数器、FMEA 反查入口；审批壳+node-action(pending) 已有 |
| 01.4 8D↔FMEA 双向 | false | ⚠️ 部分实现 | 8D→FMEA 关联点有（fmea_ref_id/node_id）；FMEA→8D 反查入口缺失 |
| 01.5 8D→SCAR 触发 | false | ❌ 未实现 | SupplierSCAR.capa_ref_id 外键已就绪；8D 侧触发入口+状态同步缺失 |
| 01.6 8D→供应商风险 | false | ❌ 未实现 | SupplierRiskAlert.linked_capa_id 外键已就绪；8D 触发写入入口缺失 |
| 01.7 D8 文档更新门禁 | true | ❌ 未实现 | 现有 D7→D8 闸口只查 node-action 完整性，无文档更新审核；CP/FMEA 版本模型可复用 |
| 01.8 知识库沉淀 | true | ⚠️ 部分实现 | D7/D8 lessons 抽取已有（capa_lessons_learned）；非结构化 8 字段沉淀、时机非 D8 关闭后全报告 |
| 01.9 横向扩散预警 | true | ❌ 未实现 | 同类产品 KB 检索有（recommendation_sources_extra）；横向扩散检查+通知完全缺失 |
| 01.10 PPT 输出 | false | ❌ 未实现 | 仅有 management_review 的 markdown 导出；无 PPT 生成 |

**结论**：
- **已就绪**：01.2（12 源编排器，最大惊喜）
- **大部分就绪**：01.3、01.4、01.8（补字段/入口即可）
- **数据模型就绪、链路缺失**：01.5（SCAR.capa_ref_id）、01.6（RiskAlert.linked_capa_id）——外键都在，只缺 8D 侧触发
- **完全缺失**：01.1（D3 遏制全链路）、01.7（文档门禁）、01.9（横向扩散）、01.10（PPT）

**数据模型基础设施齐全**：ERP（库存/发货）、SCAR（capa_ref_id）、供应商风险（linked_capa_id）、控制计划版本、FMEA 版本、lessons 表均存在，新建子故事可复用，不需从零建表。

---

## 01.1 D3 遏制措施（AI_REQUIRED=true）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 4 类数据源导入（在途/库存、发货/物流、IQC、SPC 判异） | ❌ | `ERPInventoryBalance`/`ERPShipment`/`ShipmentRecord` 模型存在（erp.py）；`capa_draft_service.py` 有 D3 AI 文本草稿（含 containment_actions 结构） | 数据模型有基础设施，但无 D3 导入入口、无与 8D 关联的快照 |
| 受影响范围分析报告（5 项） | ❌ | 无批追溯/影响数量/客户影响/风险分级/时间窗口分析逻辑 | 完全缺失 |
| AI 遏制建议（带 provenance） | ❌ | D3 草稿是 AI 生成文本，非"基于分析报告的遏制建议" | 仅有文本草稿，无基于数据的建议 |
| AI 辅助定位（不强制采纳） | ✅ | 现有 D3 草稿本就是辅助 | — |
| 采纳留痕 + 数据落库 | ⚠️ | D3 现仅 `d3_interim` 文本字段 | 无结构化采纳记录 |
| D3→D4 推进条件 | ⚠️ | 状态机允许 D3→D4 | 待核是否要求"遏制措施已填写" |
| 验收契约落库实体 | ❌ | 无 capa_d3_containment_snapshot/impact_report/ai_advice/adoption 表 | 完全缺失 |

**01.1 gap**：D3 当前只是文本字段 + AI 文本草稿。故事要求的"数据导入→分析报告→AI 遏制建议"链路完全缺失。ERP 数据模型 + capa_draft 的 containment_actions 结构可复用。

---

## 01.2 AI 推荐 12 源全接入（AI_REQUIRED=true）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 12 阶段全部接入 | ✅ | `recommendation_orchestrator.py` STAGE_PLAN 全 12 阶段；`_build_sources` 接入全 12 源（含 spc_anomaly/mes/iqc/supplier_history/same_type_product_kb/lessons_learned 6 新源） | 无 |
| 阶段状态（done/skipped/error） | ✅ | StageRun 有状态；skipped 注明原因（should_skip 协议） | 无 |
| provenance 标注 | ✅ | Spec B 含 provenance（每条推荐带命中阶段） | 前端 UI 展示待核 |
| AP/S/O/D | ⚠️ | 走查报告（2026-07-07）显示已加 ap/severity/occurrence/detection 到 D4/D5 schema + RiskTags 组件 | 已修，待最终核 |
| LLM 不可降级 | ✅ | LLMFusionLayer + 失败审计 | 无 |
| 执行验证（编排被执行） | ⚠️ | 后端编排器有 stage 状态 | 前端面板可视化待核 |
| 审计 + 数据落库 | ✅ | RecommendationCache + 审计 | 无 |

**01.2 gap**：基本已实现（Spec B 已交付）。仅前端编排面板可视化 + AP/S/O/D 展示需最终核对。

---

## 01.3 D4 现场验证 + D7 node-action + 审批壳（AI_REQUIRED=true）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 验证方法分类（measurement/observation/reproduction 枚举） | ❌ | `CapaRootCauseVerification.method` 是 `str \| None` 自由文本（schemas/capa_verification.py:23） | method 非枚举 |
| 验证记录落库 | ✅ | 模型字段齐全（method/result/evidence_attachments/verified_by/verified_at） | 无 |
| 未验证不能推进 D4→D5 | ✅ | capa_service.py:412 D4→D5 闸口绑定已验证 root_cause_text | 无 |
| 回退循环 + 计数器 | ❌ | 无 retry_count 字段、无回退循环计数 | 缺失 |
| 阈值提示"建议升级" | ❌ | 无 | 缺失 |
| D7 node-action 结构化落库（pending） | ✅ | `CapaD7NodeAction` 模型（prevention_control_node_id/action_type/来源/状态/关联8D）；status 默认值待核是否 pending | status 默认值待核 |
| 8D D7 ↔ FMEA 双向追溯 | ⚠️ | node-action 有 fmea_id + fmea_node_id；FMEA 侧反查入口缺失（见 01.4） | FMEA 侧反查待 01.4 |
| 审批壳（权限/待审批/审计/驳回） | ⚠️ | D7→D8 闸口存在（_d7_to_d8_gate）；审批权限 + manager 账号 + 驳回回退待核走查 | 走查待执行；状态机需细化（D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING） |
| 审批记录写审计 | ✅ | TRANSITION 审计 | 无 |

**01.3 gap**：大部分已实现。gap：method 枚举化、回退循环计数器、状态机细化（D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING）、node-action status 默认 pending 核实、FMEA 反查（依赖 01.4）。

---

## 01.4 8D ↔ FMEA 双向追溯（AI_REQUIRED=false）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 8D→FMEA 根因关联（Cause 节点） | ⚠️ | `CAPAEightD.fmea_ref_id` + `fmea_node_id`（capa.py:36）；D4 根因关联 FMEA Cause 待核 | D4 根因→FMEA Cause 关联待核 |
| 8D→FMEA node-action 关联（Prevention 节点） | ✅ | `CapaD7NodeAction.fmea_id` + `failure_cause_node_id` + `prevention_control_node_id` | 无 |
| FMEA→8D 反查入口 | ❌ | fmea_service.py:334 仅删除时 null-out fmea_ref_id，无反查 API/入口 | 缺失 |
| 关联审计 | ⚠️ | node-action 创建有审计；FMEA 反查无审计 | FMEA 反查审计缺失 |

**01.4 gap**：8D→FMEA 方向关联点已有（node-action + capa.fmea_ref_id）；FMEA→8D 反查入口完全缺失。需在 FMEA 模块侧加反查 API + 展示。

---

## 01.5 8D → SCAR 触发与回写（AI_REQUIRED=false）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 一键发起 SCAR（携带 8D 上下文） | ❌ | `SupplierSCAR` 模型已有 `capa_ref_id` 外键（supplier.py，指向 capa_eightd）、`source_type`/`source_id` | 8D 侧无触发入口 |
| SCAR 单号回写 8D | ❌ | capa_ref_id 已就绪（SCAR 侧指向 8D），但 8D 侧无 scar_ref_id 反向字段或读取 | 8D 侧读取 SCAR 关联缺失 |
| SCAR 状态变更同步 8D | ❌ | 无同步机制 | 缺失 |
| 关联审计 | ❌ | 无 | 缺失 |

**01.5 gap**：数据模型已就绪（SupplierSCAR.capa_ref_id 外键）。8D 侧触发入口 + 单号回写读取 + 状态同步完全缺失。

---

## 01.6 8D → 供应商风险评级输入（AI_REQUIRED=false）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 8D 输入传递（严重度+处置+重复） | ❌ | `SupplierRiskAlert` 已有 `linked_capa_id` 外键（supplier_risk.py:32）+ `source_type`/`source_id`；supplier_risk/service.py:382 有 alert 创建 | 8D 侧无触发写入入口（severity/disposition/repeat 未传递） |
| 评级变化回显 8D | ❌ | 8D 侧无读取 risk_alert 的入口 | 缺失 |
| 关联审计 | ❌ | 无 | 缺失 |

**01.6 gap**：数据模型已就绪（SupplierRiskAlert.linked_capa_id 外键 + alert 创建逻辑存在）。8D 侧触发写入 + 评级变化回显完全缺失。

---

## 01.7 D8 关闭前文档更新审核（AI_REQUIRED=true）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 文档影响分析（识别受影响文档清单） | ❌ | 无 | 缺失 |
| 受影响文档类型（CP/FMEA/SOP） | ⚠️ | `control_plan` + `control_plan_version`、`fmea_version` 版本模型存在；SOP 模型待核 | 版本数据模型有基础，无影响分析逻辑 |
| 文档更新审核（版本 bump + 覆盖） | ❌ | 无 | 缺失 |
| D8 门禁阻断（未通过不可关闭） | ❌ | 现有 D7→D8 闸口（capa_service.py:388 `_d7_to_d8_gate`）只查 node-action 完整性 + recommendation_hash，无文档审核 | 缺失（需扩展闸口或新增门禁阶段） |
| 延期处理（记录待办但阻断） | ❌ | 无 | 缺失 |
| 审核报告 | ❌ | 无 | 缺失 |

**01.7 gap**：完全未实现。现有 D7→D8 闸口需扩展为"node-action 完整性 + 文档更新审核"两段，或新增 D8_GATE_PENDING 状态承载门禁。版本数据模型（control_plan_version/fmea_version）可复用。

---

## 01.8 8D 知识库沉淀（AI_REQUIRED=true）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| D8 关闭自动触发沉淀 | ⚠️ | D7→D8 时抽 d7 lessons（capa_service.py:397 `_extract_lessons(db,capa,"d7")`）；D8 保存时抽 d8 lessons（capa_lessons_service.py:71） | 时机是 D7→D8/D8 保存，非"D8 关闭后全报告沉淀" |
| 结构化知识条目（8 字段） | ⚠️ | `capa_lessons_learned` 表有 lesson_text/category/source_d_step/tags，非故事要求的 8 字段结构 | 字段不全（非结构化 8 字段） |
| 沉淀可被推荐源检索命中 | ⚠️ | lessons_learned source 已接入编排器 stage 5；有 enqueue_embedding | 闭环链路待核（新 8D 推荐命中本条沉淀） |
| 按产品检索历史 8D | ❌ | 无按产品检索 8D 经验入口 | 缺失 |
| 审计 | ✅ | LESSON_EXTRACTED 审计 | 无 |

**01.8 gap**：知识沉淀部分有（D7/D8 lessons 抽取 + embedding）。gap：沉淀字段非结构化 8 字段、时机非 D8 关闭后全报告、按产品检索入口缺失。

---

## 01.9 横向扩散预警与通知（AI_REQUIRED=true）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 类似产品检查（4 依据并集） | ❌ | `recommendation_sources_extra.py` 有同类型产品 KB 检索（同 factory+product_type 跨 product_line）；但非"横向扩散检查"用途 | 检索逻辑可复用，但横向扩散检查+4 依据并集缺失 |
| 通知提示 + 询问是否通知 | ❌ | 无 | 缺失 |
| 通知状态可追踪 | ❌ | 无 | 缺失 |
| 审计 | ❌ | 无 | 缺失 |

**01.9 gap**：完全未实现。同类型产品 KB 检索逻辑（recommendation_sources_extra）可复用作 4 依据之一，但横向扩散检查 + 通知 + 状态追踪完全缺失。

---

## 01.10 8D 报告 PPT 输出（AI_REQUIRED=false）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 一键生成 PPT（D8 关闭后） | ❌ | 仅有 management_review 的 markdown 导出（export_report_markdown）；无 PPT 生成 | 缺失 |
| PPT 结构（D1-D8 + 封面 + 附录） | ❌ | 无 | 缺失 |
| 可重复生成 | ❌ | 无 | 缺失 |
| 审计 | ❌ | 无 | 缺失 |

**01.10 gap**：完全未实现。无 python-pptx 依赖、无 PPT 生成逻辑。management_review 的 markdown 导出可作部分参考但不直接复用。

---

## 优先级建议（按交付顺序 + 完成度）

| 优先级 | 子故事 | 理由 |
|---|---|---|
| P0 | 01.2（12 源）收尾 | 已基本就绪，仅前端面板 + AP/S/O/D 展示待核，工作量小 |
| P0 | 01.3（D4 验证 + D7 + 审批壳）收尾 | 大部分就绪，补 method 枚举 + 回退计数器 + 状态机细化 + node-action pending 核实 |
| P1 | 01.1（D3 遏制）新建 | 业务流程最靠前，完全缺失，ERP 数据模型 + capa_draft 结构可复用 |
| P1 | 01.4（FMEA 双向）收尾 | 8D→FMEA 已有，补 FMEA→8D 反查入口（工作量小） |
| P1 | 01.5（SCAR 触发）新建 | capa_ref_id 外键已就绪，只缺 8D 侧触发入口（工作量小） |
| P1 | 01.6（供应商风险）新建 | linked_capa_id 外键已就绪，只缺 8D 侧触发写入（工作量小） |
| P2 | 01.7（D8 文档门禁）新建 | 完全缺失，需扩展 D7→D8 闸口 + 新增 D8_GATE_PENDING 状态；版本模型可复用 |
| P2 | 01.8（知识沉淀）收尾 | lessons 已有，补结构化 8 字段 + 按产品检索入口 |
| P3 | 01.9（横向扩散）新建 | 完全缺失，同类型产品 KB 检索可复用 |
| P3 | 01.10（PPT）新建 | 完全缺失，需引入 PPT 生成依赖 |

## 意外发现

1. **01.2 已基本实现**：之前以为只接了 5 源，实际 Spec B 已交付 12 源全接入 + 编排器。
2. **01.5/01.6 数据模型已就绪**：SupplierSCAR.capa_ref_id、SupplierRiskAlert.linked_capa_id 外键都在，只缺 8D 侧触发入口——工作量比预期小。
3. **01.8 知识沉淀已有基础**：D7/D8 lessons 抽取 + embedding 已有，但非结构化 8 字段、时机非 D8 关闭后全报告。
4. **数据模型基础设施齐全**：ERP（库存/发货）、SCAR（capa_ref_id）、供应商风险（linked_capa_id）、控制计划版本、FMEA 版本、lessons 表均存在，新建子故事可复用，不需从零建表。
5. **01.3 method 是自由文本**：CapaRootCauseVerification.method 是 `str | None`，故事要求枚举（measurement/observation/reproduction），需改 schema + 可能迁移。
