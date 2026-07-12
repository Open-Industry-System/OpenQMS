# 子故事 US-E2E-01.1：D3 临时/遏制措施（数据导入 + 受影响范围分析 + AI 遏制建议）

**状态**: 实现态 v4（实现于 2026-07-12）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-d3-containment`
**前置**: 无（D3 是业务流程最靠前的 AI 步骤，独立交付，不依赖推荐源抽象）
**AI_REQUIRED**: true（无 LLM 凭证 → `BLOCKED`）

> **v4 变更**（基于 spec 第五轮审查 1 P0 + 2 P1 + 4 一致性修订）：
> 1. execution 模型修正（P0）：`report_id` NOT NULL（业务归属，manual/adopted 都有）+ `generation_id` nullable（仅 adopted）+ `advice_id` nullable + CHECK 区分 manual/adopted。**从未生成 AI 建议也能建 manual execution**（v3 把 generation_id 设 NOT NULL 导致 manual 无法建模）。
> 2. 闸口按 `report_id` 查 execution：manual 无 generation 也算有效；adopted 须属当前 advice_generation。
> 3. batches[] 数量契约：加 `qty_by_status{inventory,in_transit,shipped:{qty,unit}}`；**只 inventory/shipment 贡献数量，IQC/SPC 仅证据**；按源主键去重；不同单位不混加；impact_qty 从 qty_by_status 汇总。
> 4. advice generation 先 running 非 current，LLM 成功才原子切 current；失败旧代保持 current + 落 failed 行 + 200 status=failed（非 422 回滚）。
> 5. 审计事件补 `D3_EXECUTION_UPDATED`（v3 已补，v4 确认）。
>
> **v3 变更**（基于 spec 第四轮审查 4 P1 + 4 次要修订）：
> 1. 落库实体新增 `capa_d3_advice_generation`（建议代，不可变 generation 覆盖到 advice 层）。
> 2. 闸口 adopted execution 须属当前 advice_generation；建议重生成后旧 adopted execution 失效。
> 3. 删冗余 report_id 避免双真源：advice 只 generation_id、adoption 只 advice_id（**execution 除外**，v4 恢复 report_id 归属）。
> 4. 全链 ON DELETE RESTRICT + CAPA 软删除（归档不物理删）；存在 D3 审计实体禁止物理删除。
> 5. batch_key = `hash(normalized_material + normalized_lot)`（跨来源合并），lot 缺失退化；batches[].source_refs 保留原始 provenance。
> 6. record_key 永不为空，只有 snapshot_id 可空。
> 7. 建议生成先检查 LLM 凭证再建 generation（blocked 不破坏旧可用 generation）。
> 8. 审计事件补 `D3_EXECUTION_UPDATED`。
>
> **v2 变更**（基于 spec 对抗性审查 8 findings 修订）：
> 1. D3→D4 闸口加严：由「interim OR adoption」改为「当前导入代快照≥1 AND 当前代报告 status=done AND 有效执行记录（manual 或 adopted advice）」。AI 仍是辅助，但工程师须先导入数据+生成报告+记录执行结果方可推进（**对 v1「全人工也能推进」的修订**）。
> 2. 新增 D3 execution 实体：承载结构化执行记录（措施文本/执行结果状态/证据附件引用/来源 manual 或 adopted/对应 advice），取代仅靠 `d3_interim` 自由文本承载执行结果。
> 3. 报告 5 项的事实部分（批追溯/影响数量/客户映射/时间窗口）改由**确定性代码**计算，LLM 只做风险解释 + 建议文本；provenance = `snapshot_id + record key`，非 LLM 自报。
> 4. 不可变 generation：每次 import→report→advice 为新一代，旧代保留 + `is_current` 控制闸口/UI；审计实体不级联删。
> 5. import_run 语义：导入按 run 分代，run 内 (snapshot_type) 唯一，报告绑定一个完成的 import_run，防重复计数。
> 6. decision 单一当前值：UQ(advice_id) + UPDATE 写审计，禁止同建议同时 adopted+rejected。
> 7. IQC 数据源改查 `iqc_inspections`（非 `iqc_materials` 主数据）。
> 8. 客户名脱敏：送 LLM prompt 阶段代号化（`customer_01`），落库前还原真实客户名（报告对客户可见）。

## 故事

**作为** 现场质量工程师，**我想** 在 D3 填写临时/遏制措施时，导入在途/库存、发货/物流、IQC、SPC 判异数据，
系统生成**受影响范围分析报告**（批追溯、影响数量、客户影响、风险分级、时间窗口），
再由 AI 基于报告输出**遏制措施建议**（召回/隔离/通知客户/加严检验等），
工程师参考选定并执行后记录结果，
**以便** 缺陷品被有效遏制不再流入客户，遏制决策有数据支撑且可审计。

> **与 D4 根因推荐的区别**：D4 的 12 阶段 DAG 是"找根因"；D3 是"先止损"——遏制措施在根因明确前就要执行，
> 关注的是受影响批次的物理流转（在途/库存/已发货），数据来源和编排逻辑与 D4 不同，故独立为子故事。

## 背景 / 前置条件

- 系统已部署，「默认工厂」+ 产品线 `DC-DC-100-E2E`；该产品已有 SPC 控制图、IQC 检验记录、MES 连接。
- 现场发现一批来料螺栓尺寸超差，8D 已推进到 D3。
- AI 步骤必须配置 `.env.e2e` 的 LLM 凭证；无凭证时本子故事验收视为 `BLOCKED`，不得降级跳过 AI 步骤。
- 物流/库存/发货数据：E2E 环境通过可重复的 seed 或导入文件提供样本数据（真实 WMS/MES 对接为后续迭代）。

## 数据导入（4 类）

工程师在 D3 触发【遏制数据导入】，选择以下数据源导入（一次导入为一个 **import_run**，run 内每类最多一份快照）：

1. **在途/库存批次**：在途批次号、库位、数量；库存批次号、库位、数量。来源 `ERPInventoryBalance`（按产品线+工厂过滤）。
2. **发货/物流记录**：已发货批次、发货日期、物流单号、客户信息、到货状态。来源 `ERPShipment` + `ShipmentRecord`（到货状态字段缺失时记 `arrival_status='unknown'`，**不得由 LLM 推断**）。
3. **IQC 检验记录**：本批及历史同供应商/同物料不良记录、不良分布。来源 `iqc_inspections`（非 `iqc_materials` 主数据），按 supplier_id/part_no/时间窗过滤。
4. **SPC 控制图判异**：判异结果、异常发生时间窗口、受影响生产批次。来源 `SPCAlarm` JOIN `InspectionCharacteristic`（30 天判异口径）。

导入后系统**自动**生成受影响范围分析报告（无需人工触发报告按钮）。

## 受影响范围分析报告

导入完成后，系统**自动**生成受影响范围分析报告。报告 5 项中，**事实部分由确定性代码计算**（不交 LLM），LLM 仅负责风险分级推导与风险解释文本：

- **批追溯**：由快照 payload 按物料/批次 join 聚合，确定性计算受影响批次清单。
- **影响数量**：确定性按状态聚合（在途 N / 库存 M / 已发货 K），后端校验 = 明细求和。
- **客户影响**：由发货记录确定性 join `customers`，产出客户清单 + 数量 + 到货状态（真名，对客户可见）。
- **风险分级**：LLM 基于上述确定性事实 + capa.severity + 客户关键性（Customer.segment）推导 high/medium/low。
- **时间窗口**：由 SPC 判异 alarm 时间确定性取最早~最晚。

> **provenance**：每条 AI 建议的来源 = 命中的数据源 `snapshot_id` + 记录 key + 分析阶段，由后端确定性标注，**不接受 LLM 自报来源作为审计证据**。

## AI 遏制措施建议

基于受影响范围分析报告的确定性事实，AI 输出**遏制措施建议**（仅建议文本 + 风险解释，不重算批次/数量），每条带来源 provenance 标注：

- 召回建议（针对在途/已发货高风险批次）
- 隔离建议（针对库存受影响批次 → 库位隔离指令）
- 通知客户建议（针对已签收批次 → 客户沟通模板）
- 加严检验建议（针对后续来料 → IQC 加严方案）
- 临时替代方案建议（如适用）

> **客户名脱敏**：送 LLM prompt 阶段客户名代号化（`customer_01`），LLM 输出后落库前还原真实客户名（报告对客户可见为真名）。

## 主流程

1. field_qe 在 D3 触发【遏制数据导入】，导入 4 类数据（在途/库存、发货/物流、IQC、SPC 判异），系统**自动**生成受影响范围分析报告。
2. 系统展示报告内容（批追溯/影响数量/客户影响/风险分级/时间窗口）。
3. 工程师确认报告，触发【AI 遏制建议】，AI 基于报告输出遏制措施建议列表（带来源 provenance）。
4. 工程师参考选定措施，**填写结构化执行记录**（措施文本 + 执行结果状态 + 证据附件引用；来源 manual 或 adopted advice + 对应 advice）。
5. 保存 D3（含导入快照、分析报告、AI 建议列表含 provenance、采纳记录、执行记录，按不可变 generation 保留历史）。

## 业务规则 / 验收标准

- **数据导入**：4 类数据源均可导入；导入数据落库为快照（与 8D + import_run 关联），后续分析基于快照，不依赖外部系统实时状态；import_run 内每类唯一，防重复计数。
- **受影响范围分析报告**：报告必须包含批追溯/影响数量/客户影响/风险分级/时间窗口 5 项；事实部分确定性计算（不交 LLM），LLM 仅做风险分级 + 解释；报告落库且可追溯（不可变 generation，旧代保留）。
- **AI 遏制建议**：
  - 触发后 AI 基于报告输出建议列表，非空，每条带来源 provenance 标注（`snapshot_id` + 记录 key + 分析阶段，**后端确定性标注，非 LLM 自报**）；
  - 建议类型覆盖召回/隔离/通知客户/加严检验等；
  - 无 LLM 凭证 → `BLOCKED`；LLM 阶段 `skipped`/`error` → `FAILED`。
- **AI 辅助定位**：AI 遏制建议是辅助参考，不强制采纳；工程师可全部自填人工措施、不采纳任何 AI 建议也能推进 D3→D4（**但须先导入数据 + 生成报告 + 记录执行结果**，见状态机）。采纳与不采纳均留痕。
- **provenance 标注**：每条 AI 建议标注命中的数据源与分析阶段；点击可展开看来源详情（snapshot_id + record key）。
- **采纳留痕**：工程师采纳/拒绝 AI 建议写 `capa_d3_advice_adoption`（单一当前决策，UQ(advice_id)，改决策 UPDATE + 写审计）；未采纳的建议也留存。
- **执行记录**：实际执行的遏制措施 + 执行结果 + 证据附件落 `capa_d3_execution`（结构化，非自由文本）；来源 manual 或 adopted advice + 对应 advice_id。
- **数据落库**：import_run、导入快照、分析报告、AI 建议列表（含 provenance）、采纳记录、执行记录均正确持久化；不可变 generation，旧代保留 + `is_current` 控制。
- **客户名脱敏**：送 LLM prompt 代号化，落库还原真名；报告对客户可见为真名。
- **执行验证**：E2E 断言导入 → 报告生成 → AI 建议 → 采纳执行的链路完整，只验结构/状态/来源，不验精确文字。
- **状态机**：D3 推进至 D4 需满足：当前导入代 4 类快照齐全（任一类 record_count 可为 0 但须导入）AND 当前代报告 status=done AND 存在有效执行记录（manual 或 adopted advice）。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `capa_d3_import_run`（导入代，run 状态+完成时间）、`capa_d3_containment_snapshot`（快照，绑 run_id，run 内 type 唯一）、`capa_d3_impact_report`（报告，绑 run_id，不可变 generation + is_current）、`capa_d3_advice_generation`（建议代，绑 report_id，不可变 generation + is_current）、`capa_d3_ai_advice`（建议含 provenance，绑 generation_id）、`capa_d3_advice_adoption`（采纳/拒绝，UQ(advice_id) 单一当前决策）、`capa_d3_execution`（执行记录，report_id NOT NULL 归属 + generation_id nullable 仅 adopted，source manual 或 adopted） |
| 关键字段 | snapshot_type∈{inventory, shipment, iqc, spc}；report 含 batches[](batch_key+qty_by_status+source_refs)/impact_qty/customer_impact[]/risk_level∈{high,medium,low}/time_window/status∈{done,failed}；advice 含 source_provenance[](snapshot_id+record_key+source_type+stage，record_key 永不为空)、advice_type∈{recall,isolate,notify_customer,strict_inspection,alternative}；batch_key=hash(material+lot)；qty_by_status 只 inventory/shipment 贡献数量，IQC/SPC 仅证据；execution 含 measure_text/result_status/evidence_refs/source∈{manual,adopted}/advice_ref(仅adopted)/executed_by/executed_at |
| 状态枚举 | D3→D4 推进条件：当前 run 4 类快照齐全 AND 当前代报告 status=done AND 存在有效 execution（manual 或 adopted 且属当前 advice_generation；从未生成 AI 建议时纯 manual 也算） |
| 审计事件 | `D3_DATA_IMPORTED`、`D3_REPORT_GENERATED`、`D3_AI_ADVICE_GENERATED`、`D3_ADVICE_ADOPTED`、`D3_ADVICE_REJECTED`、`D3_ADVICE_DECISION_CHANGED`、`D3_EXECUTION_RECORDED`、`D3_EXECUTION_UPDATED` |
| E2E seed 前置 | 产品线 DC-DC-100-E2E 有 SPC 控制图 + iqc_inspections 记录 + ERPInventoryBalance/ERPShipment 样本（mock ERPConnection）+ Customer.segment='key' |
| 通过条件 | 当前 run 4 类导入成功 + 报告 5 项齐全(确定性事实+LLM风险) + AI 建议非空带 provenance + 执行记录有效 + D3→D4 可推进 |
| 失败条件（FAILED） | LLM 阶段 skipped/error；provenance 缺失；采纳/执行未留痕；报告事实与快照明细不一致（后端校验失败） |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（报告生成自动跟在导入后，无凭证则报告端点 BLOCKED，闸口报告 done 条件不满足） |

## 不在本子故事范围

- 真实 WMS/MES/TMS 系统对接（E2E 用 seed/导入文件模拟，真实对接为后续迭代）。
- D3 推进至 D4 后的 D4 根因分析（见 01.2/01.3）。
- AI 建议准确率评测（epic 范围外）。
- 遏制措施的成本/工时估算（后续迭代）。

## 后续

- 真实物流/库存/发货系统的对接为后续迭代（需与 WMS/MES/TMS 集成）。
- 受影响范围分析报告可导出为独立文档供跨部门协同（后续迭代）。
