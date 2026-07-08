# Gap Analysis：US-E2E-01 v8.1 epic vs 现有实现

**日期**: 2026-07-08
**对照对象**: `docs/user-stories/US-E2E-01-capa-8d-closed-loop/`（epic 评审稿 v8.1 + 10 子故事，愿景态）
**方法**: 逐条验收标准对照现有实现（codegraph + 文件检索），标注 ✅已实现 / ⚠️部分实现 / ❌未实现
**范围**: 只标注 gap，不做实现方案设计

## 摘要

| 子故事 | AI_REQUIRED | 状态 | 主要 gap |
|---|---|---|---|
| 01.1 D3 遏制 | true | ❌ 基本未实现 | 无数据导入流程、无受影响范围分析、无 AI 遏制建议（仅 D3 文本草稿）；D3→D4 无闸口（advance_capa 不检查 d3_interim 非空）；ERP 数据模型可复用 |
| 01.2 12 源推荐 | true | ⚠️ 大部分已实现 | 12 阶段编排器 + 全源接入已就绪（Spec B 已交付）；但 LLM 未配置时静默放行（pc=None 返回 attempted=0，非 BLOCKED）、stage_runs 未结构化持久化（RecommendationCache 仅 suggestions JSONB）、前端面板/AP-S-O-D 待核 |
| 01.3 D4 验证+D7+审批壳 | true | ⚠️ 部分实现 | method 非枚举、无回退计数器、状态机未细化（D7_PREVENTION→D8_CLOSURE 直连，无 D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING/驳回）、node-action 无 status 字段（仅 action=confirmed/skipped，无 pending）、FMEA 反查基础已有但未覆盖 D7 Prevention 节点+审计缺失 |
| 01.4 8D↔FMEA 双向 | false | ⚠️ 部分实现 | 双向反查基础已有（GET /api/capa/by-fmea-node + get_capas_by_fmea_node + 前端 RelatedCAPAList），但只查 fmea_ref_id/fmea_node_id，需确认覆盖 D7 node-action Prevention 节点 + 审计 |
| 01.5 8D→SCAR 触发 | false | ❌ 未实现 | SupplierSCAR.capa_ref_id 外键已就绪；8D 侧触发入口+状态同步缺失 |
| 01.6 8D→供应商风险 | false | ❌ 未实现 | SupplierRiskAlert.linked_capa_id 外键已就绪；8D 触发写入入口缺失 |
| 01.7 D8 文档更新门禁 | true | ❌ 未实现 | 现有 D7→D8 闸口只查 node-action 完整性，无文档更新审核；CP/FMEA 版本模型可复用 |
| 01.8 知识库沉淀 | true | ⚠️ 部分实现 | D7/D8 lessons 抽取已有（capa_lessons_learned）；非结构化 8 字段沉淀、时机非 D8 关闭后全报告 |
| 01.9 横向扩散预警 | true | ❌ 未实现 | 同类产品 KB 检索有（recommendation_sources_extra）；横向扩散检查+通知完全缺失 |
| 01.10 PPT 输出 | false | ❌ 未实现 | 仅有 management_review 的 markdown 导出；无 PPT 生成 |

**结论**：
- **大部分已实现**：01.2（12 源编排器已就绪，但 LLM 降级/持久化有 gap）
- **部分实现**：01.3、01.4、01.8
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
| D3→D4 推进条件 | ❌ | 状态机允许 D3_INTERIM→D4_ROOT_CAUSE（eightd_state.py:19）；advance_capa 只对 D4→D5、D7→D8 加闸口，不检查 d3_interim 非空（capa_service.py:365） | gap：无 D3→D4 闸口，未验证遏制措施已填写即可推进 |
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
| LLM 不可降级 | ❌ | `llm_fusion_layer.py:34` — provider 未配置时 `pc is None` 返回 `LLMOutcome(attempted=0)`，静默放行（不报错、不 BLOCKED）；编排器继续产出 rule-only 结果 | gap：未配置时未按故事口径判 BLOCKED，而是静默降级；llm_available 字段仅记录状态不阻断 |
| 执行验证（编排被执行） | ⚠️ | 后端编排器有 stage 状态 | 前端面板可视化待核 |
| 审计 + 数据落库 | ⚠️ | RecommendationCache（recommendation_cache.py:50）仅 `suggestions` JSONB + `llm_available` bool，**无 stage_runs 字段**；API 返回 runtime stages（capa.py:425）但未结构化持久化 | gap：stage_runs 未落库，无法事后回溯编排执行过程；审计有但 stages 持久化位置待定 |

**01.2 gap**：12 阶段编排器 + 全源接入已就绪（Spec B 已交付）。但三个 gap：(1) LLM 未配置时静默降级（应按故事判 BLOCKED）；(2) stage_runs 未结构化持久化（RecommendationCache 仅 suggestions）；(3) 前端面板/AP-S-O-D 展示待核。

---

## 01.3 D4 现场验证 + D7 node-action + 审批壳（AI_REQUIRED=true）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 验证方法分类（measurement/observation/reproduction 枚举） | ❌ | `CapaRootCauseVerification.method` 是 `str \| None` 自由文本（schemas/capa_verification.py:23） | method 非枚举 |
| 验证记录落库 | ✅ | 模型字段齐全（method/result/evidence_attachments/verified_by/verified_at） | 无 |
| 未验证不能推进 D4→D5 | ✅ | capa_service.py:412 D4→D5 闸口绑定已验证 root_cause_text | 无 |
| 回退循环 + 计数器 | ❌ | 无 retry_count 字段、无回退循环计数 | 缺失 |
| 阈值提示"建议升级" | ❌ | 无 | 缺失 |
| D7 node-action 结构化落库（pending） | ❌ | `CapaD7NodeAction`（capa.py:76）只有 `action` 字段（schema: `Literal["confirmed","skipped"]`，capa_verification.py:62），**无 status 字段**（无 pending/已执行/已验证） | gap：无 status 字段，故事要求的 pending 状态不存在；需加 status 字段 + 迁移 |
| 8D D7 ↔ FMEA 双向追溯 | ⚠️ | node-action 有 fmea_id + fmea_node_id；FMEA 反查基础已有（见 01.4：by-fmea-node API + RelatedCAPAList），但未覆盖 D7 node-action Prevention 节点，反查审计缺失 | gap：反查未覆盖 Prevention 节点；反查审计缺失（见 01.4） |
| 审批壳（权限/待审批/审计/驳回） | ❌ | 状态机 D7_PREVENTION→D8_CLOSURE 直连（eightd_state.py:23），**无 D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING 中间状态**，无驳回回退（D7_PREVENTION 只能→D8_CLOSURE）；现有 _d7_to_d8_gate 只查 node-action 完整性 | gap：状态机未细化、无驳回回退；审批壳的"待审批状态"不存在 |
| 审批记录写审计 | ✅ | TRANSITION 审计 | 无 |

**01.3 gap**：部分实现。gap：(1) method 非枚举（自由文本）；(2) 无回退循环计数器；(3) 状态机未细化（D7_PREVENTION→D8_CLOSURE 直连，无 D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING，无驳回回退）；(4) node-action 无 status 字段（仅 action=confirmed/skipped，故事要求的 pending 不存在）；(5) FMEA 反查（依赖 01.4）。

---

## 01.4 8D ↔ FMEA 双向追溯（AI_REQUIRED=false）

| 验收标准 | 状态 | 现有实现 | gap |
|---|---|---|---|
| 8D→FMEA 根因关联（Cause 节点） | ⚠️ | `CAPAEightD.fmea_ref_id` + `fmea_node_id`（capa.py:36）；D4 根因关联 FMEA Cause 待核 | D4 根因→FMEA Cause 关联待核 |
| 8D→FMEA node-action 关联（Prevention 节点） | ✅ | `CapaD7NodeAction.fmea_id` + `failure_cause_node_id` + `prevention_control_node_id` | 无 |
| FMEA→8D 反查入口 | ⚠️ | 已有 `GET /api/capa/by-fmea-node/{fmea_id}`（capa.py:103）+ `get_capas_by_fmea_node()`（capa_service.py:796）+ 前端 `RelatedCAPAList.tsx` | gap：反查只查 `CAPAEightD.fmea_ref_id`/`fmea_node_id`，需确认是否覆盖 D7 node-action 的 Prevention 节点；反查审计待核 |
| 关联审计 | ⚠️ | node-action 创建有审计；FMEA 反查无审计 | FMEA 反查审计缺失 |

**01.4 gap**：双向反查基础已有（by-fmea-node API + RelatedCAPAList）。gap：反查只查 `fmea_ref_id`/`fmea_node_id`，需确认覆盖 D7 node-action 的 Prevention 节点（prevention_control_node_id）；反查审计缺失。工作量小。

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
| P0 | 01.2（12 源）收尾 | 编排器已就绪，但 LLM 未配置静默降级（应判 BLOCKED）+ stage_runs 未持久化是硬 gap；前端面板/AP-S-O-D 待核 |
| P0 | 01.3（D4 验证 + D7 + 审批壳）收尾 | method 枚举 + 回退计数器 + 状态机细化（D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING/驳回）+ node-action 加 status 字段 |
| P1 | 01.1（D3 遏制）新建 | 业务流程最靠前，完全缺失，含 D3→D4 闸口补齐；ERP 数据模型 + capa_draft 结构可复用 |
| P1 | 01.4（FMEA 双向）收尾 | 反查 API 已有，补 Prevention 节点覆盖 + 审计（工作量小） |
| P1 | 01.5（SCAR 触发）新建 | capa_ref_id 外键已就绪，只缺 8D 侧触发入口（工作量小） |
| P1 | 01.6（供应商风险）新建 | linked_capa_id 外键已就绪，只缺 8D 侧触发写入（工作量小） |
| P2 | 01.7（D8 文档门禁）新建 | 完全缺失，需扩展 D7→D8 闸口 + 新增 D8_GATE_PENDING 状态；版本模型可复用 |
| P2 | 01.8（知识沉淀）收尾 | lessons 已有，补结构化 8 字段 + 按产品检索入口 |
| P3 | 01.9（横向扩散）新建 | 完全缺失，同类型产品 KB 检索可复用 |
| P3 | 01.10（PPT）新建 | 完全缺失，需引入 PPT 生成依赖 |

## 意外发现

1. **01.2 编排器已实现但 LLM 降级有硬 gap**：Spec B 已交付 12 源全接入 + 编排器，但 `llm_fusion_layer.py:34` 在 provider 未配置时 `pc is None` 返回 `attempted=0` 静默放行（非故事要求的 BLOCKED），且 RecommendationCache 无 stage_runs 字段（编排执行过程未结构化持久化）。
2. **01.5/01.6 数据模型已就绪**：SupplierSCAR.capa_ref_id、SupplierRiskAlert.linked_capa_id 外键都在，只缺 8D 侧触发入口——工作量比预期小。
3. **01.4 反查基础已有**：GET /api/capa/by-fmea-node + RelatedCAPAList 已存在，只查 fmea_ref_id/fmea_node_id，需补 Prevention 节点覆盖 + 审计。
4. **01.3 node-action 无 status 字段**：CapaD7NodeAction 只有 action=confirmed/skipped，故事要求的 pending/已执行/已验证状态不存在，需加字段 + 迁移。
5. **01.3 状态机 D7→D8 直连**：eightd_state.py D7_PREVENTION→D8_CLOSURE 无中间状态、无驳回回退，故事要求的 D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING 全部缺失。
6. **01.1 D3→D4 无闸口**：advance_capa 只对 D4→D5、D7→D8 加闸口，D3→D4 不检查 d3_interim 非空。
7. **01.8 知识沉淀已有基础**：D7/D8 lessons 抽取 + embedding 已有，但非结构化 8 字段、时机非 D8 关闭后全报告。
8. **数据模型基础设施齐全**：ERP（库存/发货）、SCAR（capa_ref_id）、供应商风险（linked_capa_id）、控制计划版本、FMEA 版本、lessons 表均存在，新建子故事可复用，不需从零建表。
9. **01.3 method 是自由文本**：CapaRootCauseVerification.method 是 `str | None`，故事要求枚举（measurement/observation/reproduction），需改 schema + 可能迁移。
