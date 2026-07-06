# US-E2E-01 8D 全程闭环 — Spec B：12 阶段推荐编排器 + DAG 可视化 + provenance + 6 类新推荐源

**状态**：设计稿（待评审）
**日期**：2026-07-06
**关联**：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（v6 定稿）、`PROGRESS.md` 特性缺口清单 P0-2 / P0-3 / P1-5~10、Spec A 设计 `2026-07-03-us-e2e-01-spec-a-d4-verification-adoption-design.md`（已落地）
**分支**：`worktree-us-e2e-01-8d-closed-loop`（从 Spec A head 续做）

## 背景与范围

US-E2E-01 故事要求：触发 D4/D5 推荐后，UI 展示**12 阶段流程编排可视化面板**（每阶段：名称 / 来源 / 状态 pending·running·done·skipped·error / 命中数 / 摘要）；最终推荐列表非空、**每条带来源 provenance 标签**；关键阶段达 `done`（或合理 `skipped` 并注明原因，如无 SPC 数据）；E2E 断言**编排被执行**（面板各阶段状态符合预期，非黑盒），只验结构/状态/来源，不验精确文字。

Spec A 已落地数据模型缺口（P0-1 D4 验证、P0-4 采纳/动作审计），其中 `capa_ai_adoption.stage_index` 建为**可空列**，Spec A 决策 1 明确"编排器上线后在推荐响应里返回 `stage_index`，前端采纳时回传，服务层透传——届时只改服务层一处"。Spec B 即补齐这个编排器 + DAG + provenance 观测层，并接入 6 类新推荐源（SPC / IQC / MES / 供货历史 / 同类型产品 KB / 经验教训结构化）。

### 现状（已查证）

当前 D4/D5 推荐走 `HybridRecommendationPipeline.recommend()`（`backend/app/services/hybrid_recommendation_pipeline.py`），它是 **5 阶段扁平循环**，无 per-stage status/hit_count/summary 暴露：

```
Stage 1 召回: for source in d4_sources/d5_sources: candidates += source.retrieve(context)  # 异常仅 log.warning
Stage 2 (D5 only) FMEAControlExpander.expand(cause_candidates, fmea_docs)
Stage 3 FusionEngine.merge(all_candidates, context)   # 优先级归一化 + PL/severity bonus + 去重 + Top10
Stage 4 LLMFusionLayer.enrich(fused, context) → LLMOutcome(attempted/succeeded/failed)
Stage 5 llm_recommend 审计（attempted>0 时）
返回 RecommendationResult(items=outcome.candidates)
```

- D4 sources（4）：`FMEAGraphSource` / `SemanticSearchSource` / `HistoricalCAPASource` / `RuleEngineSource`
- D5 sources（3 + expander）：`SemanticSearchSource` / `HistoricalCAPAMeasureSource` / `RuleEngineMeasureSource` / `FMEAControlExpander`
- Source 接口：`async retrieve(context: RecommendationContext) -> list[RecommendationCandidate]`；构造器 `(db, embedding_provider=None)`（`FMEAGraphSource`/`RuleEngineSource` 无 `__init__`）
- `RecommendationCandidate`：`source / content / category / confidence / match_reason / metadata`；`to_d4_schema()` / `to_d5_control_schema()` / `to_d5_suggestion_schema()` 输出 API 字典，已有 `match_source`，**无 `stage_index`**
- D7 推荐走独立的纯函数 `capa_service.get_d7_recommendations()`（图节点匹配，非 12 阶段管线）——**Spec B 不改 D7 管线**，12 阶段 DAG 仅用于 D4/D5
- API：`GET /api/capa/{id}/d4-fmea-recommendations` → `{items: [...]}`；`GET /api/capa/{id}/d5-fmea-recommendations` → `{existing_controls, general_suggestions}`（`backend/app/api/capa.py:342/425`）
- 前端 `D4RecPanel.tsx` / `D5RecPanel.tsx`（Spec A 后）按 `match_source` 分组渲染，采纳走统一端点；**无 DAG 面板、无 per-item provenance testid**

### 本 spec 交付

1. **P0-2 12 阶段推荐编排器** — 新 `RecommendationOrchestrator` 把现有 sources + 6 类新源组织成 12 阶段执行图，返回 `{stages: [...], items: [...]}`，每阶段带 `status/hit_count/summary/error`。
2. **P0-2 DAG 可视化面板** — 前端新 `<RecommendationDAG>` 组件，12 节点 + 状态色 + 命中数徽标 + `data-e2e="rec-dag-stage-{index}"`。
3. **P0-3 provenance UI + testid** — 每条推荐 `<Tag data-e2e="rec-source-{source}">` + 阶段命中徽标；payload 加 `stage_index`。
4. **P1-5~10 六类新推荐源** — `SPCAnomalySource` / `IQCSource` / `SupplierHistorySource` / `MESSource` / `SameTypeProductKBSource` / 结构化 `LessonsLearnedSource`（含新表 `capa_lessons_learned`）。
5. **采纳 `stage_index` 透传闭环** — Spec A 留的口子：编排器返回 `stage_index` → 前端采纳回传 → `AdoptRequest` 扩字段 → `adopt_recommendation` 透传入库。

### 不在本 spec 范围

- 故事级 E2E spec `capa-story-closed-loop.spec.ts`（P2-11，Spec C）—— 但本 spec 的 `data-e2e="rec-dag-stage-{index}"` / `rec-item-stage-{index}` / `rec-source-{source}` 选择器是 Spec C 断言的依赖
- D7 推荐管线改造（D7 走独立纯函数，非 12 阶段；D7 的 confirm/skip/auto-fill 审计已在 Spec A 落地）
- AI 推荐准确率/排序质量评测（故事明确排除）
- 真实 MES 集成（本 spec 用已持久化的 mock MES 数据；真实连接器已有，数据写入路径已通）

## 关键决策

1. **编排器包装而非重写管线**：`RecommendationOrchestrator` 内部仍调现有 `FMEAGraphSource` / `SemanticSearchSource` / `HistoricalCAPASource` / `RuleEngineSource` / `FusionEngine` / `LLMFusionLayer`，但把它们映射到 12 个命名阶段，每阶段执行前后更新 `StageRun(status, hit_count, summary, error)`。`HybridRecommendationPipeline` 保留为薄壳（旧调用方/测试不破），内部委托 orchestrator；`recommend()` 返回类型从 `RecommendationResult(items)` 扩为 `RecommendationResult(stages, items)`（`items` 不变，加 `stages` 字段）。

2. **12 阶段映射固定，D4/D5 共用同一编排**：故事定义的 12 阶段对 D4/D5 都适用，差异仅在每阶段背后挂的 source。编排器持 `STAGE_PLAN: list[StageSpec]`，每个 `StageSpec` 声明 `index/name/source_kind/stage_filter`（`stage_filter` 指明该阶段对 d4/d5/both 生效）。无对应 source 的阶段（如 D5 的 FMEAGraphSource 阶段）显式 `skipped` reason="D5 不召回根因节点"。阶段定义见下「12 阶段编排模型」。

3. **`stage_index` 写入 candidate metadata，schema 透传**：编排器在 stage N 执行后，给该 stage 产出的每个 `RecommendationCandidate` 的 `metadata["stage_index"] = N`。`to_d4_schema` / `to_d5_control_schema` / `to_d5_suggestion_schema` 各加一行 `"stage_index": self.metadata.get("stage_index")`。Spec A 的 `capa_ai_adoption.stage_index` 列从此有值。

4. **`AdoptRequest` 扩 `stage_index`（Spec A 决策 1 兑现）**：`AdoptRequest` 加 `stage_index: int | None = None`；前端 D4/D5 RecPanel 采纳时从 item 取 `stage_index` 回传；`adopt_recommendation` 服务层把 `req.stage_index` 透传到 `CapaAIAdoption.stage_index`（替换 Spec A 硬写的 `None`）。历史采纳记录不回填。单点改动，Spec A plan 已预留。

5. **skipped / error 语义明确，便于 E2E 断言**：
   - `done`：source 执行成功，`hit_count` = 返回候选数（可为 0，仍 done）
   - `skipped`：source 前置条件不满足（无 embedding provider / 无 SPC 数据 / 无 MES 连接 / D5 阶段不适用），`hit_count=0`，`summary` 注明原因（如 "产品线暂无 SPC 控制图"）—— 故事验收"合理 skipped 并注明原因"
   - `error`：source 抛异常，`error` 字段存异常摘要（脱敏），`hit_count=0`，不阻断后续阶段
   - `running`：编排器执行中瞬时态（同步执行下 API 响应里不会出现 running，但 DAG 组件预留该态用于未来流式 SSE）
   - `pending`：未执行（同上，API 响应里所有阶段终态为 done/skipped/error）

6. **6 类新源遵循现有 Source 接口 + 强制 async `should_skip`（R3+R6-修复合约一致性）**：`async retrieve(context) -> list[RecommendationCandidate]`，构造器 `(db, embedding_provider=None)`，`name` 类属性 = 内部 source 标识。`match_source` 外部值按下表与内部 `source` 映射（`to_d4_schema` 已有 `rule_engine→rule` 映射模式，新源沿用）。**6 类新源 MUST 实现 `async def should_skip(context) -> str | None`**（R6-修复：async，因需 `await db.execute(...)` 查底层数据存在性，如 SPC 查 `spc_alarms` count、IQC 查 `iqc_inspections` 不良 count）：返回 reason → 编排器标 `skipped`（无数据）；返回 None → `retrieve`，`[]` 即 `done(0)`（有数据 0 命中），非空即 `done(N)`。编排器 `await should_skip(context)`（同步调用会返回 coroutine 被误判 truthy → 误 skipped）。**唯一 skip/done(0) 规则**（R3-修复）：不再"返回 [] 据 summary 判 skipped"。既有源（FMEAGraphSource/SemanticSearchSource/HistoricalCAPASource/RuleEngineSource）的**结构性前置条件**（embedding None / linked_fmea None / pc None / D5 不适用）由编排器 `_stage_precondition` 集中处理（R3-修复），不要求既有源新增 should_skip。

7. **新源 `match_source` 外部值表**（扩展 Spec A 采纳映射表）：

| 阶段 | 内部 `source` | 外部 `match_source` | `item_ref` 关键字段 |
|---|---|---|---|
| 2 本产品 FMEA | `fmea_graph` | `fmea_graph` | `{failure_cause_node_id, fmea_id, failure_mode_node_id}` |
| 3 全局 KB RAG | `semantic_search` | `semantic_search` | `{failure_cause_node_id, fmea_id}` |
| 4 同类型产品 KB | `same_type_product_kb` | `same_type_product_kb` | `{failure_cause_node_id, fmea_id, product_type_code}` |
| 5 经验教训 | `lessons_learned` | `lessons_learned` | `{source_capa_id, lesson_id, category}` |
| 6 SPC 异常 | `spc_anomaly` | `spc_anomaly` | `{spc_chart_id, alarm_id, failure_mode_node_id?}` |
| 7 MES 设备/过程 | `mes` | `mes` | `{equipment_id?, scrap_record_id?, shift?}` |
| 8 IQC 来料 | `iqc` | `iqc` | `{supplier_id, part_no, inspection_id?, defect_qty}` |
| 9 供货历史 | `supplier_history` | `supplier_history` | `{supplier_id, grade, ppm}` |
| 10 规则启发 | `rule_engine` | `rule` | `{}` |
| 11 LLM 融合 | `llm` | `llm` | `{}` |

8. **DAG 组件独立、D4/D5 共用**：`<RecommendationDAG stages={stages} />` 放在 `D4RecPanel` / `D5RecPanel` 的 `<Card>` 顶部（推荐列表上方）。12 节点用 Ant `Steps`（垂直方向，`size="small"`）或自定义 grid 渲染；每节点：名称 + 来源 Tag + 状态色（done=green/skipped=orange/error=red/running=blue/pending=default）+ 命中数 Badge。`data-e2e="rec-dag-stage-{index}"` + `data-status="{status}"` 供 Spec C E2E 断言。无 LLM 凭证时阶段 11 `skipped`。

9. **provenance Tag per item**：D4/D5 RecPanel 的每个推荐项加 `<Tag data-e2e="rec-source-{match_source}">{来源标签}</Tag>` + `<Tag data-e2e="rec-item-stage-{stage_index}">阶段{stage_index}</Tag>`。D4 现有按 `match_source` 分组保留（分组标题 + 每项 provenance Tag 并存）。`rec-source-*` 与 `rec-item-stage-*`（项徽标）/ `rec-dag-stage-*`（DAG 节点）是 Spec C 故事 spec 的断言钩子（R2-修复：前缀区分 DAG 节点 vs 项徽标）。

10. **P1-10 经验教训结构化 = 新表 + 按生命周期拆分抽取（R2-修复 D8 lessons 丢失）**：新表 `capa_lessons_learned`（`lesson_id, capa_id, factory_id, lesson_text, category, tags(JSONB), source_d_step, created_at`）。**抽取按生命周期点拆分**（Codex R2 发现：D7→D8 转换是**进入** D8 而非完成 D8，此时 `d8_closure` 为空/未填，单点抽取会永久丢失 D8 闭环 lessons）：
   - **D7 prevention lessons**：在 `advance_capa` D7→D8_CLOSURE 转换时从 `d7_prevention` 抽取（`source_d_step='d7'`）——d7_prevention 在 D7 已定稿。
   - **D8 closure lessons**：在 `d8_closure` 字段更新时抽取（`source_d_step='d8'`）——D8_CLOSURE 是终态（无 D9 转换），d8_closure 在 D8 期间可编辑。**用 delete-and-rebuild 语义（R3-修复 stale lessons）**：每次保存先 `DELETE FROM capa_lessons_learned WHERE capa_id=X AND source_d_step='d8'`，再重新切句插入。删改/移除的句子对应旧 lesson 被删除，不留在 KB 污染检索。d7 lessons 用 upsert（d7_prevention 在 D7 定稿后不变，重试幂等即可，无需 delete-and-rebuild）。
   `LessonsLearnedSource`（阶段 5）用 pgvector 语义匹配 `lesson_text` 而非裸 D2→D2（`HistoricalCAPASource` 仍保留作 fallback，阶段 5 优先 lessons，无结果时 orchestrator 不降级到 historical，保持阶段边界清晰）。两处抽取均复用 `advance_capa`/`update_capa` 既有事务，单 commit，幂等（决策 17）。

11. **P1-9 同类型产品 KB = 新 Source，不改 SemanticSearchSource**：`SemanticSearchSource` 按 `user_product_lines` 过滤（行级权限语义），改它加 `product_type` 维度会混淆两种 scope。新 `SameTypeProductKBSource` 查 `document_embeddings` JOIN `product_lines` ON `de.product_line_code = pl.code` WHERE `pl.product_type_code = (当前 CAPA 产品线的 product_type)` AND `de.product_line_code != 当前 PL`（跨工厂同类型，排除本产品线避免与阶段 2/3 重复），仍受 `user_product_lines` 行级权限收口（admin 全权限；非 admin 仅在用户可见产品线内匹配同类型）。依赖 `product_lines.product_type_code` 列（实施时确认列名）。

12. **P1-8 MESSource 查已持久化数据，不等真实集成**：`mes_scrap_records` / `mes_equipment_status` / `mes_measurement_ingestions` 表已存在，mock 连接器 ingest 路径已通（`mes_connector.py` + `mes_service.py`）。`MESSource` 直接查这些表（产品线近 30 天 scrap 缺陷模式 + equipment 停机原因），映射到候选根因。无 MES 数据 → `skipped` reason="产品线暂无 MES 数据"。真实 MES 接入后数据源不变，仅数据量增加。

13. **D4/D5 API 响应加 `stages`，向后兼容**：D4 → `{stages: [...], items: [...]}`；D5 → `{stages: [...], existing_controls: [...], general_suggestions: [...]}`。`items`/controls/suggestions 每项加 `stage_index`。旧前端忽略 `stages` 仍可工作（但本 spec 前端同步落地 DAG，无旧前端兼容负担）。

14. **编排器不引入 SSE/流式**：本 spec 同步执行 12 阶段，API 一次返回全部终态。`running`/`pending` 状态在 DAG 组件预留但 API 响应不出现。流式 SSE 留后续（故事不要求）。

15. **显示顺序 ≠ 执行顺序（R1-修复 D5 stage 2 依赖 + R10-修复不只依赖 semantic）**：12 阶段的 `index` 是**显示顺序**（DAG 节点编号 + `rec-dag-stage-{index}` testid 契约），不是执行顺序。`FMEAControlExpander`（D5 stage 2）是**派生阶段**——它消费 **stage 3/4 召回的 FailureCause 候选 ∪ linked FMEA 按 D4 关键词直查的 FailureCause**（R10-修复：`_lookup_linked_fmea_causes`，不依赖 embedding，embedding 不可用/semantic 0 命中时仍能扩展 FMEA 控制措施，与既有纯函数 `_match_existing_controls` 一致）扩展出 Control。编排器分两遍执行：①**召回遍**跑独立 retrieve 阶段（1/2 D4/3/4/5/6-9 D4/10/11）；②**派生遍**跑 stage 2 D5（合并 semantic+直查 causes 去重后 expand）。每个 `StageRun` 仍按 `index` 报告。D5 stage 2 **skip 条件**：semantic 无 cause 且 linked FMEA 直查无 cause（或无 linked FMEA）→ skipped；有 linked FMEA 且直查命中 → 即使 embedding 不可用也 done。**回归测试**：D5 embedding 不可用 + linked FMEA 有 D4 关键词匹配的 cause → stage 2 done 扩展出 control（不 skipped）；D5 无 linked FMEA 且 semantic 无 cause → stage 2 skipped。

16. **stage 12 终态单次发射（R1-修复重复 output stage）**：`STAGE_PLAN` 含 12 项，但 stage 12（输出推荐列表）标记 `terminal=True`，**编排器主循环跳过 terminal 阶段**——它在 FusionEngine merge 之后单次发射。主循环只处理 stage 1-11（stage 1 internal 上下文、stage 2-10 sources、stage 11 LLM）。主循环结束后：`fused = fusion.merge(all_candidates, context)` → 追加**唯一一个** `StageRun(12, "输出推荐列表", "internal", "done", hit_count=len(fused))`。**禁止**在主循环的 `internal` 分支处理 stage 12 + 循环后再 append（那会产生 13 行/重复 index 12）。**回归测试**：响应 `stages` 恰好 12 行、`index` 集合 = {1..12} 无重复。

17. **lesson 抽取幂等（R1-修复 lesson 重复）**：`capa_lessons_learned.lesson_id` 用**确定性** `uuid5(NAMESPACE_URL, f"capa_lesson:{capa_id}:{source_d_step}:{normalized_lesson_text}")`（非随机 uuid4），同一 CAPA 同一原文反复抽取产生相同 `lesson_id`。抽取用 `pg_insert.on_conflict_do_update(index_elements=["lesson_id"], set_={category/tags/updated_at})` upsert，重试/双击/并发 advance 不会产生重复行、不会重复入队 embedding（同 `entity_id` 幂等）。`advance_capa` D7→D8 转换开头 `SELECT capa ... FOR UPDATE` 串行化并发 advance（状态机本身也拒绝 D8→D8 再转，FOR UPDATE 兜底不确定提交后的重试）。`LESSON_EXTRACTED` 审计带 `correlation_id = uuid5(capa_id, "lesson_extract")`，重试产生相同 correlation_id 便于去重查询；审计 append-only 可接受（它是转换日志，不喂 KB）。**回归测试**：同一 CAPA 两次触发抽取 → lessons 行数不变（upsert）、embedding 入队不重复、audit correlation_id 相同。

18. **D7→D8 闭环闸口（R2-修复 D7 旁路，Codex 评审发现）**：Spec A 落地了 `CapaD7NodeAction` 持久化（confirm/skip/auto-fill），但 `advance_capa` D7_PREVENTION → D8_CLOSURE **未强制**每条 D7 推荐都已处置——直接 `POST /api/capa/{id}/advance`（body 可空）可绕过 UI 弹窗关闭 D7，闭环审计可被旁路。Spec B 在同一次 `advance_capa` D7→D8 改动里（决策 17 lessons 钩子同处）补**服务端闸口**：转换前重算当前 D7 推荐（复用纯函数 `capa_service.get_d7_recommendations(capa_data, fmea_docs, allowed_pls)`，按 recommend 端点同样方式预加载 fmea_docs + `_resolve_allowed_pls`），取每条推荐 key `(fmea_id, failure_mode_node_id, failure_cause_node_id)`，要求每个 key 在 `capa_d7_node_action` 表里有**当前 CAPA 限定**且**`recommendation_hash` 匹配**的一条 `confirmed`/`skipped`/`auto_filled` 记录——查询 `WHERE capa_id = capa.report_id AND fmea_id = ... AND failure_mode_node_id = ... AND COALESCE(failure_cause_node_id,'') = ... AND recommendation_hash = :current_hash`（R8-修复：按当前 `capa_id` 限定，防他 CAPA 同 key 动作误满足；**R10+R11-修复：`recommendation_hash` 防 stale 处置**——`current_hash = recommendation_fingerprint(fmea_id=..., failure_mode_node_id=..., failure_cause_node_id=..., failure_mode_name=..., failure_cause_name=..., match_reason=...)`，与 D7 端点 record 路径用**同一 canonical helper**（稳定 ID + 内容指纹 + 固定 `|` delimiter），FMEA 节点改名/推荐内容变 → hash 变 → 旧动作 stale → 闸口阻断，强制重新处置；既有 Spec A 动作 hash NULL → 视为 stale）；存在未处置/stale key → `ValueError("D7 有 N 条推荐未处置或已 stale（FMEA 变更），不可关闭")` → API 400。**completeness 健康检查（R7+R8+R9-修复，生成前跑，不只在空集）**：重算前独立查 canonical scope FMEA count（`SELECT count(*) FROM fmea_documents WHERE factory_id=capa.factory_id AND product_line_code=capa.product_line_code`）与加载的 fmea_docs 数对比——**任何不一致（partial preload / 关联 FMEA 缺失 / PL 有 FMEA 但 preload 空）→ fail-closed 400 "D7 推荐重算异常：FMEA 预加载不完整"**（R9-修复：partial preload 也拦截，避免只验证已加载子集漏未加载 FMEA 的推荐）；count=0 且无 fmea_ref_id → 真无推荐，闸口平凡通过。`failure_cause_node_id` 为 NULL 的推荐 key 用 `COALESCE(...,'')` 收口匹配（与 `ix_capa_d7_node_unique` 一致）。闸口校验在 `SELECT FOR UPDATE` 之后、状态写入之前、lessons 抽取之前——闸口不通过则不抽取 lessons、不推进、不审计 TRANSITION（早返回 400）。**canonical scope（R2+R5-修复 over-block）**：重算 D7 推荐用**授权无关但 CAPA 相关**的 scope——`capa.factory_id` + `capa.product_line_code`（CAPA 自己的产品线），fmea_docs 按 `capa.factory_id AND product_line_code = capa.product_line_code` 加载，`allowed_pls = [capa.product_line_code]`。**不**用整工厂 scope（避免无关产品线的推荐阻塞本 CAPA 关闭），**不**用推进用户的 `allowed_pls`（避免用户 PL 窄而误放行）。重算异常 → fail-closed 400。**回归测试**：CAPA 属 PL-A，工厂另有 PL-B 的 D7 推荐 → 闸口只看 PL-A 推荐，PL-B 未处置不阻塞 PL-A CAPA 关闭。**权限**：D7→D8 本就需 `canApprove('capa')`（既有），闸口不改变权限模型，只补闭环完整性。

## 12 阶段编排模型

`STAGE_PLAN`（D4/D5 共用，`stage_filter` 控制差异）：

| # | 阶段名 | source_kind | stage_filter | skipped 条件 | 命中语义 |
|---|---|---|---|---|---|
| 1 | 上下文采集 | `ContextSource`（internal） | both | 永不 | hit_count=0，summary="上下文已采集（D2/D4 + 关联 FMEA + 产品线）" |
| 2 | 本产品 FMEA 检索 | `FMEAGraphSource`（D4）/ `FMEAControlExpander`（D5，**派生**） | both | 无关联 FMEA → skipped "未关联 FMEA" | D4: 候选根因数；D5: 候选控制数（派生遍产出） |
| 3 | 全局知识库 RAG 检索 | `SemanticSearchSource` | both | 无 embedding_provider → skipped "未配置 embedding" | 语义命中数 |
| 4 | 同类型产品 KB 检索 | `SameTypeProductKBSource`（NEW） | both | 无 `product_lines.product_type_code` / 无同类型数据 → skipped | 跨产品线同类型命中数 |
| 5 | 经验教训库检索 | `LessonsLearnedSource`（NEW） | both | 无 embedding / 无 lessons 数据 → skipped | lessons 命中数 |
| 6 | SPC 异常关联检索 | `SPCAnomalySource`（NEW） | d4 | 无 SPC 图/无判异记录 → skipped "产品线暂无 SPC 数据" | SPC 关联失效模式数 |
| 7 | MES 设备/过程数据检索 | `MESSource`（NEW） | d4 | 无 MES 连接/无数据 → skipped | MES 异常关联数 |
| 8 | IQC 来料检验数据检索 | `IQCSource`（NEW） | d4 | 无 IQC 不良记录 → skipped | IQC 不良趋势命中数 |
| 9 | 供货历史检索 | `SupplierHistorySource`（NEW） | d4 | 无关联供应商/无评级数据 → skipped | 供货风险命中数 |
| 10 | 规则启发 | `RuleEngineSource`（D4）/ `RuleEngineMeasureSource`（D5） | both | 永不（兜底） | 规则建议数 |
| 11 | LLM 融合排序 | `LLMFusionLayer`（既有） | both | 无 `pc`（LLM 未配置）→ skipped "未配置 LLM" | 增强后候选数（attempted/succeeded/failed 入 summary） |
| 12 | 输出推荐列表 | `ProvenanceTagger`（internal，**terminal**） | both | 永不 | hit_count=最终去重后 items 数，summary="输出 N 条带来源推荐" |

注：阶段 6-9 仅 D4（D5 是措施推荐，SPC/MES/IQC/供货是根因线索，D5 用不上）；D5 时这些阶段 `skipped` reason="D5 阶段不适用"。阶段 2 D5 用 `FMEAControlExpander`（基于 stage 3/4 召回 cause ∪ linked FMEA 按 D4 关键词直查 cause 扩展控制，R10-修复不依赖 embedding），是**派生阶段**（决策 15）：召回遍先跑 stage 3/4，派生遍合并 semantic+直查 causes 去重后跑 stage 2，`StageRun` 仍按 index=2 报告。阶段 12 是 **terminal**（决策 16）：主循环跳过，FusionEngine merge 后单次发射。`index` 是显示顺序（DAG 节点 + `rec-dag-stage-{index}` 契约），非执行顺序。

## 数据模型

### 新表 `capa_lessons_learned`（P1-10）

```python
class CapaLessonLearned(Base):
    __tablename__ = "capa_lessons_learned"
    # lesson_id 确定性：uuid5(NAMESPACE_URL, f"capa_lesson:{capa_id}:{source_d_step}:{normalized_lesson_text}")
    # 同一 CAPA 同一原文反复抽取 → 相同 lesson_id → upsert 幂等（决策 17）。无 default=uuid4。
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    lesson_text: Mapped[str] = mapped_column(Text, nullable=False)
    lesson_text_normalized: Mapped[str] = mapped_column(Text, nullable=False)   # 去空白/小写，用于 uuid5 + 唯一索引
    category: Mapped[str] = mapped_column(String(40), nullable=False)   # "prevention" | "detection" | "systemic" | "process"
    source_d_step: Mapped[str] = mapped_column(String(8), nullable=False)  # "d7" | "d8"
    tags: Mapped[list] = mapped_column(JSONB, default=lambda: [])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # 索引：ix_capa_lessons_capa (capa_id), ix_capa_lessons_pl (product_line_code)
    # 唯一索引（决策 17 防重复，表达式索引收口 normalized 文本）：
    #   CREATE UNIQUE INDEX ix_capa_lessons_unique ON capa_lessons_learned (capa_id, source_d_step, md5(lesson_text_normalized))
    # embedding 复用 document_embeddings（entity_type='capa_lesson', entity_id=lesson_id, entity_field='lesson_text'）—— enqueue_embedding 入队
```

- `lesson_id` 由应用层 `_extract_lessons` 用 `uuid5` 确定性生成（非随机），同一 (capa, source_d_step, normalized_text) → 同一 `lesson_id`。PK 即去重键。
- **按生命周期拆分抽取（R2+R7-修复，单源合约）**：① D7→D8_CLOSURE 转换时**仅从 `capa.d7_prevention` 抽取**（`source_d_step='d7'`）——d7_prevention 在 D7 已定稿，d8_closure 此时为空**不抽取**；② `d8_closure` 字段在 D8 期间更新时**才抽取**（`source_d_step='d8'`，delete-and-rebuild，见 `update_capa` 钩子）。抽取规则：按句号/换行切分，过滤空句，**按 `normalized_text` 去重**，`category` 启发式判定（含"预防/防呆/poka"→prevention；含"检测/探测/检验"→detection；含"体系/流程/制度"→systemic；余 →process）。`source_d_step` 标来源。`lesson_text_normalized = "".join(text.lower().split())`。
- **d7 upsert + d8 delete-and-rebuild（R7-修复）**：d7 用 `pg_insert(...).on_conflict_do_update(index_elements=["lesson_id"], set_={category, tags, updated_at})` upsert（d7_prevention 定稿不变，重试幂等）；d8 用 savepoint 内 `DELETE WHERE capa_id+source_d_step='d8'` + 重插（编辑后旧行删除，见钩子）。**任一抽取失败 → fail-closed 阻断转换/保存（400），KB==CAPA**（R7-修复，不残留 stale，无 dirty 标记）。
- `enqueue_embedding(db, "capa_lesson", lesson.lesson_id, lesson.product_line_code, lesson.factory_id)` 入队，embedding worker 把 `capa_lessons_learned` 加入 `table_field_map`（P0 follow-up 已识别 worker 不认识 `agent_memory`，本 spec 同理需加 `capa_lesson`）。**d8 delete-and-rebuild 时同步清理孤儿 embedding（R8-修复）**：savepoint 内 `DELETE FROM document_embeddings WHERE entity_type='capa_lesson' AND entity_id IN (被删 d8 lesson_id)` + 取消对应 pending outbox 行，避免删改 lesson 文本残留 embedding。
- **依赖**：embedding worker 扩展 `capa_lesson` 实体类型（如 worker 未扩，`LessonsLearnedSource` 降级为 FTS 匹配 `lesson_text`，仍可用，命中质量略降）。

### `RecommendationResult` 扩展（`recommendation_types.py`）

```python
@dataclass
class StageRun:
    index: int
    name: str
    source: str          # 外部 match_source 值（与 candidate.match_source 对齐）
    status: Literal["pending", "running", "done", "skipped", "error"]
    hit_count: int = 0
    summary: str = ""
    error: str | None = None
    # R4-修复：LLM stage 结构化审计字段（非 LLM stage 为 None）。薄壳 _maybe_write_llm_audit 读此，
    # 不解析 summary 字符串——避免 status='error' 时 summary 无计数导致审计层抛错破坏响应
    llm_attempted: int | None = None
    llm_succeeded: int | None = None
    llm_failed: int | None = None

@dataclass
class RecommendationResult:
    items: list[RecommendationCandidate]
    stages: list[StageRun] = field(default_factory=list)
```

### `RecommendationCandidate.metadata` 约定

编排器在 stage N 产出的 candidate 的 `metadata["stage_index"] = N`。`to_d4_schema` / `to_d5_control_schema` / `to_d5_suggestion_schema` 各加：
```python
"stage_index": self.metadata.get("stage_index"),
```

### 迁移

`backend/alembic/versions/20260706_add_capa_lessons_learned.py`，`down_revision` 取 Spec A head（`20260703_capa_verif` 或其后继，实施时 `alembic heads` 确认），手写：① `op.create_table("capa_lessons_learned")` + 普通索引（`capa_id` / `product_line_code`）+ **唯一表达式索引** `CREATE UNIQUE INDEX ix_capa_lessons_unique ON capa_lessons_learned (capa_id, source_d_step, md5(lesson_text_normalized))`（决策 17 防重复，PK 确定性 uuid5 已是第一道防线，此索引为并发兜底）；② **`op.add_column("capa_d7_node_action", sa.Column("recommendation_hash", sa.String(16), nullable=True))`**（R10-修复：Spec A 表扩展，存动作创建时的推荐内容 hash `sha256(failure_mode_name+failure_cause_name+match_reason)` 截 16 位；nullable 让既有行兼容，新动作必填；D7 闸口据此防 FMEA 改名后 stale 处置误满足）。遵循 ADR-0013/0001/0003。（R7-修复：不引入 `lessons_dirty` 列——lessons 抽取 fail-closed，无需 dirty 标记/重试。）

## API

D4/D5 recommend 端点响应加 `stages`，handler 改用 orchestrator 返回的 `stages` 透传。

| 方法 | 路径 | 改动 |
|---|---|---|
| GET | `/api/capa/{report_id}/d4-fmea-recommendations` | 响应从 `{items}` → `{stages, items}`；`items[]` 每项加 `stage_index` |
| GET | `/api/capa/{report_id}/d5-fmea-recommendations` | 响应从 `{existing_controls, general_suggestions}` → `{stages, existing_controls, general_suggestions}`；两项各加 `stage_index` |
| POST | `/api/capa/{report_id}/adopt-recommendation`（Spec A） | `AdoptRequest` 加 `stage_index: int \| None`（决策 4） |

### Schemas（`backend/app/schemas/capa.py` 扩展）

```python
class StageRunSchema(BaseModel):
    index: int
    name: str
    source: str
    status: Literal["pending", "running", "done", "skipped", "error"]
    hit_count: int
    summary: str
    error: str | None = None

# D4Recommendation / D5ExistingControl / D5GeneralSuggestion 各加：
#   stage_index: int | None = None

# D4RecommendationResponse 加：
#   stages: list[StageRunSchema] = []
# D5RecommendationResponse 加：
#   stages: list[StageRunSchema] = []

# AdoptRequest（capa_verification.py）加：
#   stage_index: int | None = None
```

handler 改动（`api/capa.py:414/497`，R9-修复 D4/D5 返回合约分开）：
- **D4**（`get_d4_fmea_recommendations`）：`result = await pipeline.recommend(...)` 后 `return {"stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages], "items": [c.to_d4_schema() for c in result.items]}`。
- **D5**（`get_d5_fmea_recommendations`）：`result = await pipeline.recommend(...)` 后**保留既有 D5 形状**——`existing_controls = [c.to_d5_control_schema() for c in result.items if c.to_d5_control_schema()]`、`general_suggestions = [c.to_d5_suggestion_schema() for c in result.items if not c.to_d5_control_schema()]`（沿用既有 `capa.py:506-513` 分流逻辑），`return {"stages": [...], "existing_controls": existing_controls, "general_suggestions": general_suggestions}`。**不用 `to_d4_schema()` 序列化 D5**（R9-修复：避免 D5 形状被 D4 覆盖、控制/建议分流丢失）。
- GET 推荐端点**不**做 lessons 重试/修复（R7-修复：无 dirty 标记，lessons 抽取 fail-closed 在写路径保证 KB==CAPA，GET 只读无副作用）。

## 服务层

### `backend/app/services/recommendation_orchestrator.py`（新建）

```python
@dataclass
class StageSpec:
    index: int
    name: str
    source_kind: str            # 'fmea_graph' | 'semantic_search' | ... | 'internal' | 'llm'
    stage_filter: Literal["d4", "d5", "both"]
    skipped_reason: str | None = None   # 静态 skipped（如 D5 不适用）
    derived: bool = False               # 派生阶段：消费已召回候选，非独立 retrieve（决策 15，D5 stage 2）
    terminal: bool = False              # 终态阶段：主循环跳过，fusion 后单次发射（决策 16，stage 12）

STAGE_PLAN: list[StageSpec] = [
    StageSpec(1,  "上下文采集",        "internal",        "both"),
    StageSpec(2,  "本产品 FMEA 检索",   "fmea_graph",      "both"),   # D5: derived（下方 executes_after）
    StageSpec(3,  "全局知识库 RAG 检索", "semantic_search", "both"),
    StageSpec(4,  "同类型产品 KB 检索",  "same_type_product_kb", "both"),
    StageSpec(5,  "经验教训库检索",     "lessons_learned", "both"),
    StageSpec(6,  "SPC 异常关联检索",   "spc_anomaly",     "d4"),
    StageSpec(7,  "MES 设备/过程检索",  "mes",             "d4"),
    StageSpec(8,  "IQC 来料检索",       "iqc",             "d4"),
    StageSpec(9,  "供货历史检索",       "supplier_history","d4"),
    StageSpec(10, "规则启发",           "rule_engine",     "both"),
    StageSpec(11, "LLM 融合排序",       "llm",             "both"),
    StageSpec(12, "输出推荐列表",       "internal",        "both", terminal=True),
]
# D5 stage 2 标派生（决策 15）：FMEAControlExpander 消费 stage 3/4 召回的 cause
_D5_DERIVED = {2: "FMEAControlExpander"}   # index -> 派生处理器

class RecommendationOrchestrator:
    def __init__(self, db, pc, embedding_provider):
        self.db = db; self.pc = pc; self.embedding = embedding_provider
        self.fusion = FusionEngine(); self.llm_layer = LLMFusionLayer(pc)
        self.d5_control_expander = FMEAControlExpander()   # D5 stage 2 派生处理器（决策 15）
        self._sources = self._build_sources()   # source_kind -> instance（D5 stage 2 不在此列，派生）
        # R10-修复：不在构造时 fail-fast 校验协议——避免单源配置错误导致所有 D4/D5 请求硬失败（含 D4-only 源本应 skipped 的 D5 请求）。
        # 协议校验改为 per-stage 运行时（_exec_recall_stage 内，违规 → 该 stage error，其余 stage + 12 阶段响应照常）。
        # 启动/CI 应另跑 `validate_all_new_sources()` lint（见下）提前发现配置错误。

    NEW_SOURCE_KINDS = frozenset({"spc_anomaly", "iqc", "supplier_history", "mes", "same_type_product_kb", "lessons_learned"})

    def _check_source_protocol(self, spec, source) -> str | None:
        # R10-修复：per-stage 运行时协议校验（不阻断构造/整请求）。新源 should_skip 必须存在、可调用、async。
        # 违规 → 返回 error reason（该 stage 标 error，其余 stage + 12 阶段响应照常）；合规 → None
        import inspect
        if spec.source_kind not in self.NEW_SOURCE_KINDS:
            return None   # 既有源无 should_skip 协议要求
        if source is None:
            return f"source {spec.source_kind} 未注册"
        if not callable(getattr(source, "should_skip", None)):
            return f"source {spec.source_kind} should_skip 不可调用"
        if not inspect.iscoroutinefunction(source.should_skip):
            return f"source {spec.source_kind} should_skip 非 async"
        return None

    def validate_all_new_sources(self) -> list[str]:
        # R10-修复：启动/CI lint（非请求路径），返回违规列表供提前发现配置错误；不 raise
        violations = []
        for spec in STAGE_PLAN:
            if spec.source_kind in self.NEW_SOURCE_KINDS:
                v = self._check_source_protocol(spec, self._sources.get(spec.source_kind))
                if v: violations.append(f"stage {spec.index} {spec.name}: {v}")
        return violations

    async def run(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
        stages: list[StageRun] = []
        all_candidates: list[RecommendationCandidate] = []

        # ── 召回遍：stage 1-10（跳过 11 LLM、12 terminal、D5 stage 2 derived）──
        # 顺序合约（R2-修复 LLM/融合顺序）：recall → fusion → LLM，与既有管线一致——LLM 吃 fused 集，不吃 raw
        for spec in STAGE_PLAN:
            if spec.terminal or spec.source_kind == "llm":
                continue   # stage 12 terminal 留末尾；stage 11 LLM 留 fusion 之后
            if context.stage == "d5" and spec.index in _D5_DERIVED:
                continue   # D5 stage 2 派生留派生遍
            stages.append(await self._exec_recall_stage(spec, context, all_candidates))

        # ── 派生遍：D5 stage 2 FMEAControlExpander over stage 3/4 召回 causes + linked FMEA 直查 causes（决策 15 + R3 边界 + R4 guard + R10-修复）──
        if context.stage == "d5":
            spec = next(s for s in STAGE_PLAN if s.index == 2)
            semantic_causes = [c for c in all_candidates
                               if c.metadata.get("failure_cause_node_id") and c.metadata.get("stage_index") in (3, 4)]   # R3-修复：仅 stage 3/4 召回的 cause
            # R10-修复：D5 stage 2 不只依赖 semantic（embedding 不可用 / semantic 0 命中时仍能扩展 FMEA 控制措施）——
            # 直接从 linked FMEA 按 D4 根因关键词查 FailureCause（与既有纯函数 _match_existing_controls 一致，不依赖 embedding）
            direct_causes = await self._lookup_linked_fmea_causes(context)
            # 合并 + 按 (fmea_id, failure_cause_node_id) 去重
            seen: set = set(); cause_cands = []
            for c in semantic_causes + direct_causes:
                k = (c.metadata.get("fmea_id"), c.metadata.get("failure_cause_node_id"))
                if k not in seen:
                    seen.add(k); cause_cands.append(c)
            if not cause_cands:
                # R4-修复：无 FMEA cause（semantic + linked FMEA 直查均空）→ skipped，不调 expand 误报 done(0)
                stages.append(StageRun(2, spec.name, "fmea_graph", "skipped",
                                       summary="D5 无 FMEA cause（semantic + linked FMEA 直查均空），跳过控制扩展"))
            else:
                try:
                    controls = await self.d5_control_expander.expand(cause_cands, context.fmea_docs or [])
                    for c in controls:
                        c.metadata["stage_index"] = 2
                    all_candidates.extend(controls)
                    stages.append(StageRun(2, spec.name, "fmea_graph", "done",
                                           hit_count=len(controls), summary=f"扩展 {len(controls)} 条 FMEA 控制措施"))
                except Exception as e:
                    logger.warning(f"D5 stage 2 FMEAControlExpander failed: {e}")
                    stages.append(StageRun(2, spec.name, "fmea_graph", "error", error=str(e)[:200]))

        # ── Fusion（既有序：fusion 在 LLM 之前，R2-修复顺序）──
        fused = self.fusion.merge(all_candidates, context)

        # ── Stage 11 LLM enrich over FUSED（不是 raw，保既有合约，R2-修复）──
        spec11 = next(s for s in STAGE_PLAN if s.index == 11)
        stage11, enriched = await self._exec_llm_stage(spec11, fused, context)
        stages.append(stage11)
        fused = enriched   # LLM 增强后的 fused 集

        # ── Stage 12 terminal 单次发射（决策 16）──
        stages.append(StageRun(12, "输出推荐列表", "internal", "done",
                               hit_count=len(fused), summary=f"输出 {len(fused)} 条带来源推荐"))

        # 按 index 排序，保证显示顺序 1..12
        stages.sort(key=lambda s: s.index)
        return RecommendationResult(items=fused, stages=stages)

    async def _exec_recall_stage(self, spec, context, all_candidates) -> StageRun:
        # 1. stage_filter 不匹配 → skipped
        if spec.stage_filter != "both" and spec.stage_filter != context.stage:
            return StageRun(spec.index, spec.name, spec.source_kind, "skipped",
                            summary=f"{context.stage.upper()} 阶段不适用")
        # 2. internal（stage 1 上下文）
        if spec.source_kind == "internal":
            return StageRun(spec.index, spec.name, "internal", "done",
                            summary="上下文已采集（D2/D4 + 关联 FMEA + 产品线）")
        # 3. 普通 source（LLM stage 11 不在此，由 _exec_llm_stage 处理）
        source = self._sources.get(spec.source_kind)
        try:
            # R10-修复：per-stage 协议校验（违规 → 该 stage error，不阻断构造/整请求；其余 stage + 12 阶段响应照常）
            proto_violation = self._check_source_protocol(spec, source)
            if proto_violation:
                return StageRun(spec.index, spec.name, spec.source_kind, "error",
                                error=proto_violation, summary=f"source 协议违规: {proto_violation}")
            # 唯一 skip/done(0) 规则（R3-修复合约一致性 + R6-修复 async）：
            # ① 编排器 _stage_precondition 查结构性前置（既有源：linked_fmea None / embedding None）
            # ② 新源 async should_skip 查底层数据存在性（强制，R6-修复：async + await）
            # 返回 reason → skipped；None → retrieve，[] 即 done(0)，非空即 done(N)
            pre = self._stage_precondition(spec, context)
            if pre is None and hasattr(source, "should_skip"):
                pre = await source.should_skip(context)   # R6-修复：should_skip 是 async，必须 await（否则返回 coroutine 被误判 truthy → 误 skipped）
            if pre:
                return StageRun(spec.index, spec.name, spec.source_kind, "skipped", summary=pre)
            candidates = await source.retrieve(context)
            for c in candidates:
                c.metadata["stage_index"] = spec.index
            all_candidates.extend(candidates)
            return StageRun(spec.index, spec.name, spec.source_kind, "done", hit_count=len(candidates),
                            summary=source.summary(candidates) if hasattr(source, "summary") else "")
        except Exception as e:
            logger.warning(f"Stage {spec.index} {spec.name} failed: {e}")
            return StageRun(spec.index, spec.name, spec.source_kind, "error", error=str(e)[:200])

    def _stage_precondition(self, spec, context) -> str | None:
        # R3-修复：集中既有源 + 新源共用的结构性前置条件（不要求既有源新增 should_skip）
        if spec.source_kind == "fmea_graph" and context.stage == "d4" and not context.linked_fmea:
            return "未关联 FMEA"
        if spec.source_kind in ("semantic_search", "same_type_product_kb", "lessons_learned") and self.embedding is None:
            return "未配置 embedding"
        return None

    async def _lookup_linked_fmea_causes(self, context) -> list[RecommendationCandidate]:
        # R10-修复：D5 stage 2 直查 linked FMEA 的 FailureCause（按 D4 根因关键词），不依赖 embedding。
        # embedding 不可用 / semantic 0 命中时仍能扩展 FMEA 控制措施（与既有纯函数 _match_existing_controls 一致）。
        from app.utils.text import extract_keywords
        linked = context.linked_fmea
        if not linked or not linked.get("graph_data"):
            return []
        d4 = context.capa_data.get("d4_root_cause", "") or context.capa_data.get("d2_description", "")
        keywords = extract_keywords(d4)
        if not keywords:
            return []
        graph = linked["graph_data"]; node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])
        forward: dict[str, list] = {}
        for e in edges:
            forward.setdefault(e["source"], []).append((e["target"], e["type"]))
        cands: list[RecommendationCandidate] = []
        for node in graph.get("nodes", []):
            if node.get("type") != "FailureCause":
                continue
            name = node.get("name", ""); desc = node.get("description", "")
            if not any(kw in name or kw in desc for kw in keywords):
                continue
            fm_id = fm_name = None
            for tgt, etype in forward.get(node["id"], []):
                if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                    fm_id = tgt; fm_name = node_map[tgt].get("name"); break
            cands.append(RecommendationCandidate(
                source="fmea_graph", content=name, category=None, confidence=0.5,
                match_reason="关联 FMEA 失效原因（D4 关键词直查）",
                metadata={"failure_cause_node_id": node["id"], "failure_cause_desc": desc or None,
                          "failure_mode_node_id": fm_id, "failure_mode_name": fm_name,
                          "fmea_id": str(linked["fmea_id"]), "fmea_document_no": linked.get("document_no"),
                          "product_line_code": linked.get("product_line_code"), "stage_index": 2}))
        return cands

    async def _exec_llm_stage(self, spec, fused, context) -> tuple[StageRun, list[RecommendationCandidate]]:
        # LLM enrich over FUSED 集（保既有 fusion→LLM 顺序，R2-修复）；返回 (StageRun, 增强后候选)
        if self.pc is None:
            return StageRun(spec.index, spec.name, "llm", "skipped", summary="未配置 LLM",
                            llm_attempted=0, llm_succeeded=0, llm_failed=0), fused
        try:
            outcome = await self.llm_layer.enrich(fused, context)
            for c in outcome.candidates:
                c.metadata.setdefault("stage_index", spec.index)
            # R6+R11-修复：全失败（attempted>0 且 succeeded=0）→ status='error'（不绿，DAG 显红），
            # **返回原 fused 候选（非 outcome.candidates——后者可能为空，会丢确定性 fused 推荐，R11-修复）**
            # + 写 llm_failed audit（attempted>0）；部分失败 → done（summary 记 failed 计数），返回 outcome.candidates
            status = "error" if (outcome.attempted > 0 and outcome.succeeded == 0) else "done"
            returned_cands = fused if status == "error" else outcome.candidates
            if status == "done":
                for c in returned_cands:
                    c.metadata.setdefault("stage_index", spec.index)
            return StageRun(spec.index, spec.name, "llm", status,
                            hit_count=len(returned_cands),
                            summary=f"attempted={outcome.attempted} succeeded={outcome.succeeded} failed={outcome.failed}",
                            llm_attempted=outcome.attempted, llm_succeeded=outcome.succeeded, llm_failed=outcome.failed), returned_cands
        except Exception as e:
            # R3+R4+R5-修复：LLMFusionLayer.enrich 已硬化为 catch-all（见下），正常不会抛——此 except 仅兜底
            # 意外的非 LLM 调用错误（如 prompt 构造 bug），此时无 provider 调用完成，attempted=0 诚实，不审计。
            # enrich 内部全失败（provider 调用 attempted>0 全 failed）→ 不抛，返回 LLMOutcome(attempted>0, succeeded=0, failed=attempted)
            # → stage 11 error（R6-修复：全失败显 error 不绿）+ llm_attempted>0 → _maybe_write_llm_audit 写 status="llm_failed"（全失败也审计，R5-修复）
            logger.warning(f"Stage 11 LLM enrich unexpected error: {e}")
            for c in fused:
                c.metadata.setdefault("stage_index", spec.index)
            return StageRun(spec.index, spec.name, "llm", "error", error=str(e)[:200],
                            summary="LLM 增强失败，保留 fused 候选",
                            llm_attempted=0, llm_succeeded=0, llm_failed=0), fused
```

**关键不变量**（实施时测试断言）：① `stages` 恰好 12 行，`index` 集合 = {1..12} 无重复（决策 16）；② D5 stage 2 的 `StageRun` 在 stage 3/4 召回 cause 后才产出（决策 15）；③ stage 12 只出现一次（terminal）；④ **执行顺序 recall → fusion → LLM（LLM 吃 fused 不吃 raw），与既有 `HybridRecommendationPipeline` 合约一致（R2-修复）**——测试断言 `LLMFusionLayer.enrich` 收到的候选数 == `FusionEngine.merge` 输出数（非 raw 召回数）；⑤ no-data 源 → skipped（should_skip 返回 reason），0-match → done(0)（should_skip None + retrieve []），测试覆盖两条路径（R2-修复）；⑥ **LLM 失败隔离 + 审计结构化 + 全失败显 error + 全失败保留 fused（R3+R4+R5+R6+R11-修复）**：`LLMFusionLayer.enrich` 硬化为 catch-all（内部 catch 所有异常 → 返回 `LLMOutcome(attempted, succeeded, failed)`，不抛）——provider 调用全失败 → `attempted>0, succeeded=0` → stage 11 **`error`（不绿，DAG 显红，R6-修复）** + `llm_attempted>0` → `_maybe_write_llm_audit` 写 `status="llm_failed"`（**全失败也审计，R5-修复**，不隐藏 LLM 用量），**`_exec_llm_stage` 返回原 `fused` 候选（非 `outcome.candidates`——后者可能为空会丢确定性 fused 推荐，R11-修复）**，stage 12 发射 fused（非空）；enrich 仅意外非 LLM 错误才抛 → `_exec_llm_stage` except → stage 11 `error` + `llm_attempted=0`（诚实）+ 未修改 fused，stage 12 照常发射，`run()` 不抛；`_maybe_write_llm_audit` 读结构化字段（不解析 summary）→ attempted=0 不写 audit，审计层 try/except 兜底，**审计不破坏响应**——测试断言 enrich 抛错后响应仍 12 阶段 + items 非空 + 无 500，**enrich 全失败（candidates=[]）→ stage 12 仍发射原 fused（非空，R11-修复）**，enrich 全失败 → audit 记 `llm_failed`；⑦ **D5 stage 2 输入边界 + 直查（R3+R4+R10-修复）**：`cause_cands` = semantic（stage 3/4）∪ linked FMEA 直查（`_lookup_linked_fmea_causes`，不依赖 embedding）；先算合并去重再分支——空则 skipped（不调 expand 误报 done(0)），非 stage 3/4 且非直查的 cause（lessons/rule/SPC 等）不触发；**embedding 不可用但 linked FMEA 直查命中 → stage 2 仍 done（R10-修复，不丢 FMEA 控制措施）**；⑧ **should_skip 强制 + async + per-stage 校验（R4+R6+R10-修复）**：6 新源 `should_skip` 必须存在、可调用、`iscoroutinefunction`（async）；编排器 `await source.should_skip(context)`（R6-修复：async DB 查存在性，不误判 coroutine truthy）；**协议校验 per-stage 运行时（R10-修复）**——`_exec_recall_stage` 调 `_check_source_protocol`，违规 → 该 stage `error`（不阻断构造/整请求，其余 stage + 12 阶段响应照常）；启动/CI 另跑 `validate_all_new_sources()` lint 提前发现配置错误（不 raise 在请求路径）；⑨ **LLM 审计结构化（R4-修复）**：`llm_recommend` 审计从 stage 11 `StageRun.llm_attempted/succeeded/failed` 取值，不解析 summary 字符串；⑩ **lessons 抽取 fail-closed（R7-修复）**：d7/d8 lesson 抽取失败 → 阻断转换/保存（400），KB==CAPA 保证，**无 dirty marker / 读路径副作用 / JSONB list 并发丢状态风险**；抽取是 DB 事务一部分（`db.add`+`enqueue_embedding`+audit 全 DB 写），失败即事务失败，与转换/保存同命运，fail-closed 无额外 UX 代价。

注：`should_skip(context) -> str | None` 是**新 Source 强制协议方法**（R2-修复）：6 类新源各须实现，查底层数据是否存在（如 SPC 查 `spc_alarms` count、IQC 查 `iqc_inspections` 不良 count）。返回非 None → skipped reason；返回 None → retrieve。既有 `FMEAGraphSource`/`SemanticSearchSource`/`HistoricalCAPASource`/`RuleEngineSource` 无此方法，编排器据 `context.linked_fmea is None` / `self.embedding is None` 等上下文判 skipped（既有源不新增 should_skip，避免改既有源）。

### `HybridRecommendationPipeline` 改为薄壳

```python
class HybridRecommendationPipeline:
    def __init__(self, db, pc, embedding_provider):
        self.orchestrator = RecommendationOrchestrator(db, pc, embedding_provider)

    async def recommend(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
        result = await self.orchestrator.run(context, user=user, report_id=report_id,
                                              factory_id=factory_id, tenant_schema=tenant_schema)
        # R4-修复：审计读 stage 11 结构化字段（llm_attempted/succeeded/failed），不解析 summary；
        # status=error/skipped 时 llm_attempted=0 → 不写 audit。审计层异常不破坏响应（_maybe_write_llm_audit 内部 try/except）
        self._maybe_write_llm_audit(result, context, user, report_id, factory_id, tenant_schema)
        return result

    def _maybe_write_llm_audit(self, result, context, user, report_id, factory_id, tenant_schema):
        # R4-修复：从 stage 11 StageRun 结构化字段取计数（非 summary 字符串），避免 error 时审计层抛错
        stage11 = next((s for s in result.stages if s.index == 11), None)
        if stage11 is None or stage11.llm_attempted is None or stage11.llm_attempted == 0:
            return   # skipped（无 pc）/ error（attempted=0）→ 无 LLM 尝试，不写 llm_recommend audit
        if stage11.llm_failed == 0:
            status = "success"
        elif stage11.llm_failed < stage11.llm_attempted:
            status = "partial"
        else:
            status = "llm_failed"
        capa_hash = hashlib.sha256(json.dumps(context.capa_data, sort_keys=True, default=str).encode()).hexdigest()[:16]
        correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{context.stage}_recommend:{report_id}:{capa_hash}")
        try:
            audit_mod.write_audit_raw(self.db, user_id=user.user_id, factory_id=factory_id,
                tenant_schema=tenant_schema, table_name="capa_eightd", record_id=report_id,
                action="llm_recommend", correlation_id=correlation_id,
                new_values={"status": status, "trigger": context.stage,
                            "attempted": stage11.llm_attempted, "succeeded": stage11.llm_succeeded,
                            "failed": stage11.llm_failed})
        except Exception as e:
            logger.warning(f"llm_recommend audit write failed (non-blocking): {e}")   # 审计失败不破坏响应
```

### 6 类新 Source（`backend/app/services/recommendation_sources.py` 追加）

所有新源遵循：`name` 类属性、`__init__(self, db, embedding_provider=None)`、`async retrieve(context) -> list[RecommendationCandidate]`、**`async def should_skip(context) -> str | None`（强制 + async，R3+R6-修复）**、可选 `summary(candidates) -> str`。返回的 candidate `source` = 内部标识（见决策 7 表），`metadata` 含 `item_ref` 关键字段 + `product_line_code` + `severity`（供 FusionEngine bonus）。

**1. `SPCAnomalySource`（name=`spc_anomaly`，阶段 6，D4 only）**
- 复用既有 `spc_service.match_fmea_for_alarm(db, alarm)`（`spc_service.py:379`，已实现 SPC 告警→FMEA 失效模式映射，写入 `alarm.fmea_recommendations`）。查 `spc_alarms`（`models/spc.py:81`，`ic_id`→`inspection_characteristics`，`InspectionCharacteristic.product_line`）近 30 天该产品线的告警记录，逐条调 `match_fmea_for_alarm` 取关联失效模式。
- 候选根因："SPC 判异：{rule} 规则触发，关联失效模式 {fm_name}"（判异算法 = `evaluate_western_electric`，`spc_service.py:995`）。
- `should_skip`：产品线无 SPC 图 / 近 30 天无 `spc_alarms` 记录 → "产品线暂无 SPC 数据"。
- `match_source=spc_anomaly`，`item_ref={spc_chart_id=ic_id, alarm_id, failure_mode_node_id?}`。

**2. `IQCSource`（name=`iqc`，阶段 8，D4 only）**
- 查 `iqc_inspections`（`backend/app/models/iqc_inspection.py`）该产品线 + 关联供应商近 30 天 `inspection_result` 不良 / `defect_qty > 0` 的记录，聚合 `defect_description` 高频词。
- 候选根因："来料不良：{part_name} 缺陷 {defect_description}（{defect_qty} 件，{inspection_no}）"。
- `should_skip`：无不良记录 → "产品线暂无 IQC 不良数据"。
- `match_source=iqc`，`item_ref={supplier_id, part_no, inspection_id, defect_qty}`。

**3. `SupplierHistorySource`（name=`supplier_history`，阶段 9，D4 only）**
- 从 `iqc_inspections.supplier_id`（该产品线近期不良的供应商）或关联 SCAR（`SupplierSCAR.capa_ref_id`）取供应商，调 `supplier_quality_service.get_supplier_quality_detail(db, supplier_id, start, end, factory_id)` 取 grade/ppm/batch_acceptance/scar_count。
- 候选根因："供应商 {supplier_name} 评级 {grade}，PPM={ppm}，历史 SCAR {scar_count} 条"。
- `should_skip`：无关联供应商 / 供应商无评级 → "无关联供应商评级数据"。
- `match_source=supplier_history`，`item_ref={supplier_id, grade, ppm}`。
- 注：`capa_eightd` 无 `supplier_id` 列（已查证），供应商来源 = IQC 不良的 supplier_id 或 SCAR.capa_ref_id。

**4. `MESSource`（name=`mes`，阶段 7，D4 only）**
- 查 `mes_scrap_records`（报废缺陷模式）+ `mes_equipment_status`（设备停机）该产品线近 30 天，聚合 scrap 缺陷描述 + equipment downtime 原因。
- 候选根因："MES 报废：{scrap_reason}（{qty} 件）" / "设备停机：{equipment} {downtime_reason}"。
- `should_skip`：产品线无 MES 连接 / 无 scrap+equipment 数据 → "产品线暂无 MES 数据"。
- `match_source=mes`，`item_ref={equipment_id?, scrap_record_id?}`。

**5. `SameTypeProductKBSource`（name=`same_type_product_kb`，阶段 4，both）**
- 解析当前 CAPA 产品线的 `product_type_code`：JOIN `product_lines`（`models/product_line.py:20`，`product_type_code` FK→`product_types.code`，已确认存在）ON `product_lines.code = capa.product_line_code`。
- pgvector 语义查 `document_embeddings` JOIN `product_lines` ON `de.product_line_code = pl.code` WHERE `pl.product_type_code = :pt` AND `de.product_line_code != :current_pl` AND `de.entity_type='fmea_node'` AND node_type in (FailureCause, FailureMode)，受 `user_product_lines` 收口（非 admin 限定可见产品线）。
- 候选同阶段 3（FailureCause/FailureMode 结构回溯），`metadata.product_type_code` 标同类型来源。
- `should_skip`：当前产品线 `product_type_code` 为 NULL / 无同类型数据 → "无同类型产品 KB"。

**6. `LessonsLearnedSource`（name=`lessons_learned`，阶段 5，both）**
- pgvector 语义查 `document_embeddings de` JOIN `capa_lessons_learned lesson` ON `de.entity_id = lesson.lesson_id` WHERE `de.entity_type='capa_lesson'` AND `de.entity_field='lesson_text'` AND `lesson.lesson_id IS NOT NULL`（**R3-修复：排除 delete-and-rebuild 后的孤儿 embedding**，不再裸查 `document_embeddings`），受 `user_product_lines` 收口，匹配 `context.capa_data.d2_description`（D4）或 `d4_root_cause`（D5）。
- 候选："经验教训：{lesson_text}（来自 {source_capa_document_no}，类别 {category}）"。
- `should_skip`：无 embedding / 无 lessons 数据 → "暂无结构化经验教训"。
- `match_source=lessons_learned`，`item_ref={source_capa_id, lesson_id, category}`。
- 依赖：embedding worker 支持 `capa_lesson` 实体（决策 10 依赖）；未支持时降级 FTS `lesson_text`。

### `advance_capa` D7→D8 改动（P1-10 lessons 钩子 + 决策 17 幂等 + 决策 18 闸口）

`backend/app/services/capa_service.py:advance_capa` 在 `D7_PREVENTION → D8_CLOSURE` 转换时：
1. **开头 `SELECT capa ... FOR UPDATE`**（行锁，串行化并发 advance；状态机本身也拒 D8→D8 再转，FOR UPDATE 兜底不确定提交后的重试）。
2. **D7 闭环闸口（决策 18，转换前，R2+R5+R7+R8+R9-修复）**，按序：
   a. **canonical completeness check（R9-修复，生成前跑，不只在空集）**：独立查 `SELECT count(*) FROM fmea_documents WHERE factory_id=capa.factory_id AND product_line_code=capa.product_line_code`（canonical count），与加载的 fmea_docs 数对比——**任何不一致（partial preload：加载部分 FMEA）→ fail-closed `ValueError("D7 推荐重算异常：FMEA 预加载不完整")` → 400**（R9-修复：不只在推荐为空时检查，partial preload 也拦截，避免只验证已加载子集而漏未加载 FMEA 的推荐）；`capa.fmea_ref_id` 非空但 fmea_docs 未含该 FMEA → fail-closed 400 "关联 FMEA 未加载"。
   b. **重算 D7 推荐**（canonical CAPA 相关 scope：fmea_docs 按 `capa.factory_id AND product_line_code=capa.product_line_code` 加载，`allowed_pls=[capa.product_line_code]`；不用整工厂避免无关 PL 阻塞，不用用户 allowed_pls 避免 PL 窄误放行）。重算异常 → fail-closed `ValueError("D7 推荐重算失败，不可关闭")` → 400。
   c. **处置校验**：取每条推荐 key `(fmea_id, failure_mode_node_id, COALESCE(failure_cause_node_id,''))` + **当前推荐 fingerprint**（`current_hash = recommendation_fingerprint(fmea_id=..., failure_mode_node_id=..., failure_cause_node_id=..., failure_mode_name=..., failure_cause_name=..., match_reason=...)`，与 D7 端点 record 路径用同一 canonical helper，R11-修复），查 `capa_d7_node_action` 表是否每个 key 都有 `confirmed`/`skipped`/`auto_filled` 记录——**查询显式 `WHERE capa_id = capa.report_id AND recommendation_hash = :current_hash`（R8+R10+R11-修复：按当前 CAPA 限定 + hash 匹配，防他 CAPA 同 key 动作 + 防 FMEA 改名后旧动作 stale + record/gate 单源一致）**；存在未处置/stale key → `ValueError("D7 有 N 条推荐未处置或已 stale（FMEA 变更），不可关闭")` → API 400，**早返回**（不写 TRANSITION audit、不抽 lessons、不推进状态）。
   d. **D7 推荐为空 + completeness 通过**（a 步 count=0 或 loaded==canonical）→ 真无推荐，闸口平凡通过。
3. **状态转换**（既有）：`capa.status = next_state.value` + 写 TRANSITION audit（D7→D8）。
4. **D7 lessons 抽取（决策 10/17，转换后 commit 前，R2+R7-修复 fail-closed）**：调 `_extract_lessons(capa, source_d_step="d7")`：**仅从 `d7_prevention` 切句**（d7_prevention 在 D7 已定稿；`d8_closure` 此时为空，**不在此抽取**——见下方 d8_closure 更新钩子），逐句构造 `CapaLessonLearned`（`lesson_id = uuid5(NAMESPACE_URL, f"capa_lesson:{capa_id}:d7:{normalized_text}")`），用 `pg_insert(...).on_conflict_do_update(index_elements=["lesson_id"], set_={category, tags, updated_at})` upsert，`enqueue_embedding(db, "capa_lesson", lesson_id, ...)` 入队。**抽取异常 → 阻断转换**：`ValueError("D7 lessons 抽取失败，不可关闭，请重试")` → API 400，D8 **不推进**（KB==CAPA 保证，无 dirty/读路径副作用，R7-修复）。
5. **审计 `LESSON_EXTRACTED`**（≤20 字符）记 d7 lesson 数，`correlation_id = uuid5(capa_id, "lesson_extract_d7")`（重试产生相同 correlation_id 便于去重查询；audit append-only 可接受，它是转换日志不喂 KB）。
6. **fail-closed（R7-修复）**：lesson 抽取异常 → 阻断 D7→D8（400），不推进、不写 TRANSITION audit。抽取是 DB 事务一部分（`db.add`+`enqueue_embedding`+audit 全是 DB 写），失败即事务失败，与转换本身同命运，fail-closed 无额外 UX 代价。注：闸口（步骤 2）失败**阻断**（400）；lessons 抽取（步骤 4）失败**也阻断**（R7：fail-closed 保证 KB==CAPA，无 dirty marker / 读路径重试的并发与副作用风险）。

**幂等保证**：同一 CAPA 重试/双击/并发 advance → `SELECT FOR UPDATE` 串行化 + 状态机拒 D8→D8；d7 lessons 相同 `lesson_id` 命中 upsert（不新增行）、相同 `entity_id` 重复入队 embedding 幂等、相同 `correlation_id` audit 可识别。

**闸口不变量**：D7→D8 推进成功 ⇒ canonical scope 下所有当前 D7 推荐键均有 `CapaD7NodeAction`（闭环可审计，不可旁路，不受推进用户 PL 范围影响）。直接 `POST /advance` 无 D7 动作 → 400。重算失败 → 400（fail-closed，不误放行）。

### `update_capa` d8_closure 更新钩子（P1-10，R2+R3+R4+R7-修复 atomic + fail-closed）

D8_CLOSURE 是终态（无 D9 转换），`d8_closure` 文本在 D8 期间可编辑。`backend/app/services/capa_service.py:update_capa`（或 CAPA 字段保存路径）在检测到 `d8_closure` 字段变更且 `capa.status == D8_CLOSURE` 时，调 `_extract_lessons(capa, source_d_step="d8")`，**delete-and-rebuild + savepoint + fail-closed（R3 stale + R4 atomic + R7 防并发/读路径副作用）**：
1. 开 savepoint（SQLAlchemy `async with db.begin_nested()`）。
2. `DELETE FROM capa_lessons_learned WHERE capa_id=X AND source_d_step='d8'`；**同步清理孤儿 embedding + claim-safe（R8+R9-修复）**：先 `UPDATE embedding_outbox SET status='cancelled' WHERE entity_type='capa_lesson' AND entity_id IN (被删 d8 lesson_id) AND status='pending'`（锁掉未认领的 pending 行，防 worker 认领后写 stale），再 `DELETE FROM document_embeddings WHERE entity_type='capa_lesson' AND entity_id IN (被删 d8 lesson_id)`；**已认领/in-flight 的 outbox 行由 worker 兜底**：embedding worker upsert `document_embeddings` 前**重查 `capa_lessons_learned` 行存在**（`SELECT 1 FROM capa_lessons_learned WHERE lesson_id=:id`），行已删 → 丢弃该 job 不写 embedding（R9-修复：防 in-flight worker 在 cleanup 后写 stale embedding）。删改 lesson 文本不残留 embedding。
3. 从 `d8_closure` 切句，**按 `normalized_text` 去重**（同句重复只保留 1 行，避免 `lesson_id` uuid5 碰撞），构造 `CapaLessonLearned`（`lesson_id = uuid5(NAMESPACE_URL, f"capa_lesson:{capa_id}:d8:{normalized_text}")`），`db.add` + `enqueue_embedding(db, "capa_lesson", lesson_id, ...)`。
4. 审计 `LESSON_EXTRACTED`（`correlation_id = uuid5(capa_id, "lesson_extract_d8")`）。
5. **任一步异常 → ROLLBACK TO SAVEPOINT + 阻断保存**：`ValueError("D8 lessons 抽取失败，无法保存闭环总结，请重试")` → API 400，d8_closure **不保存**（KB==CAPA 保证，不残留 stale）。savepoint 成功则 release，随外层事务 commit。

**为何 fail-closed 无额外 UX 代价（R7-修复）**：lesson 抽取 = `db.add` + `enqueue_embedding`（DB outbox 写）+ audit（DB 写），全在保存事务内；抽取失败即 DB 事务失败，与 d8_closure 保存本身同命运——fail-closed 不比"保存失败"多阻拦任何场景。**不**用 dirty marker / 读路径重试（R7-修复：避免 JSONB list 并发丢状态 + GET 副作用 + 永久 stale 风险）。

**回归测试（R3+R4+R7+R8）**：CAPA 进 D8 后填 `d8_closure`（2 句）保存 → 2 行 d8 lesson；改 `d8_closure`（删 1 句、改 1 句、加 1 句）保存 → 行数 = 新句子数，旧句 lesson 已 delete；同文本再保存 → 行数不变（幂等）；**d8_closure 含重复句** → 去重后 1 行（不碰撞 lesson_id）；**抽取中异常（mock `enqueue_embedding` 抛错）→ savepoint 回滚 + 保存 400（d8_closure 未保存，KB 未变）**；**用户重试保存 → 重新抽取 → 成功则保存 + KB 一致**；**删改 d8_closure 后，被删句的 `document_embeddings`（entity_type='capa_lesson'）行已清理（R8-修复），不残留**——`LessonsLearnedSource` 检索不到旧文本；**in-flight race（R9-修复）**：模拟 worker 已认领旧 lesson_id 的 outbox job（status='claimed'），cleanup 后 worker 完成 job 时**重查 `capa_lessons_learned` 行不存在 → 丢弃，不写 stale embedding**（断言 `document_embeddings` 无该 entity_id）。

### `adopt_recommendation` 透传 `stage_index`（Spec A 决策 1 兑现）

`capa_verification_service.adopt_recommendation`（Spec A）把 `CapaAIAdoption(..., stage_index=None, ...)` 改为 `stage_index=req.stage_index`。`AdoptRequest` 加字段（决策 4）。单点改动。

### D7 端点 populate `recommendation_hash` + canonical fingerprint（R10+R11-修复防 stale 处置）

**单一 canonical helper（R11-修复：record + gate 用同一函数，避免 delimiter/字段不一致导致 closure deadlock）**——`backend/app/services/capa_d7_action_service.py` 暴露：
```python
import hashlib
def recommendation_fingerprint(*, fmea_id, failure_mode_node_id, failure_cause_node_id,
                               failure_mode_name, failure_cause_name, match_reason) -> str:
    # 稳定 ID + 内容指纹：node_id 稳定（同节点改名 → 内容部分变 → hash 变 → stale 检测）；
    # delimiter 固定 "|"，record 与 gate 调同一函数 → byte-identical 输入
    raw = f"{fmea_id}|{failure_mode_node_id}|{failure_cause_node_id or ''}|{failure_mode_name}|{failure_cause_name or ''}|{match_reason}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```
Spec A 的 `record_d7_action` / `auto_fill_d7` 在 insert/升级 `CapaD7NodeAction` 时调 `recommendation_fingerprint(...)`（从当前 D7 推荐取字段），存入 `recommendation_hash`。D7 闸口（决策 18）重算当前推荐时调**同一** `recommendation_fingerprint(...)` 生成 `current_hash`，要求动作 `recommendation_hash == current_hash`——FMEA 节点改名/推荐内容变 → hash 变 → 旧动作 stale → 闸口阻断。既有 Spec A 动作行（hash NULL）→ 视为 stale。**测试**：record + gate 用 byte-identical 输入 → hash 相等；改名任一 name 字段 → hash 变。

## 前端

### 新组件 `frontend/src/components/capa/RecommendationDAG.tsx`

- Props: `stages: StageRun[]`。
- 渲染：Ant `Steps direction="vertical" size="small"`，每步 `title={阶段名}` + `description={<Space><Tag>{来源}</Tag><Badge count={hit_count} /><Text type="secondary">{summary}</Text></Space>}`，`status` 映射：done→`finish`/skipped→`wait`+灰/error→`error`。或自定义 grid（3 列 × 4 行）更紧凑——实施时择优。
- 每节点 `data-e2e="rec-dag-stage-{index}"`（index=1..12）+ `data-status="{status}"`。
- 空状态：无 stages → 不渲染（兼容旧响应）。

### `D4RecPanel.tsx` / `D5RecPanel.tsx` 改造

- `getD4Recommendations` / `getD5Recommendations` 返回值取 `res.stages`，传给 `<RecommendationDAG stages={stages} />`，放 `<Card>` 顶部。
- 每个推荐项加 `<Tag data-e2e="rec-source-{item.match_source}">{来源标签}</Tag>` + `<Tag data-e2e="rec-item-stage-{item.stage_index}">阶段{stage_index}</Tag>`（`rec-item-stage-*` 区别于 DAG 节点的 `rec-dag-stage-*`，R2-修复冲突）。D4 现有分组（linked/semantic/...）保留，分组内每项加 provenance Tag。
- 采纳按钮 `adoptRecommendation` 调用时 payload 加 `stage_index: item.stage_index`（决策 4）。
- 来源标签 i18n：`d4.sources.{match_source}` / `d5.sources.{match_source}`（zh-CN/en-US 追加）。

### `api/capa.ts` 类型扩展

`D4Recommendation` / `D5ExistingControl` / `D5GeneralSuggestion` 加 `stage_index?: number | null`；新增 `StageRun` 类型；`D4RecommendationResponse` / `D5RecommendationResponse` 加 `stages: StageRun[]`；`AdoptRequest` 加 `stage_index?: number | null`。

### data-e2e 钩子（Spec C 依赖）

| 元素 | testid |
|---|---|
| DAG 阶段节点 | `rec-dag-stage-{index}`（index=1..12，1-indexed 与 `StageRun.index` 对齐）+ `data-status="{status}"` |
| 推荐来源标签 | `rec-source-{match_source}` |
| 推荐项阶段徽标 | `rec-item-stage-{stage_index}`（index=1..12，与 `StageRun.index` 对齐；**区别于 DAG 节点的 `rec-dag-stage-*`**） |
| DAG 容器 | `recommendation-dag` |

**选择器合约（R2-修复冲突）**：DAG 节点用 `rec-dag-stage-{index}`，推荐项阶段徽标用 `rec-item-stage-{index}`——两者前缀不同，避免 Spec C E2E 误选。`index` 统一 1..12（与后端 `StageRun.index` 一致，非 0-indexed）。

## E2E / 测试兼容

### 现有 E2E 影响评估

- D4/D5 recommend 端点响应加 `stages` 字段，现有 `capa.spec.ts`（M1 冒烟）不断言响应结构，向后兼容。
- D7 recommend 不变。
- 新源无数据时 skipped，现有 E2E 不触发新源断言。

### 后端 pytest（TDD，新建）

- `backend/tests/recommendation/test_orchestrator.py`：
  - **12 唯一阶段索引（R1-决策 16）**：响应 `stages` 恰好 12 行，`{s.index for s in stages} == {1..12}` 无重复，stage 12 只出现一次。
  - **D5 stage 2 派生依赖（R1-决策 15）**：D5 上下文 + semantic 召回产 1 cause（stage 3 done hit_count=1）→ stage 2 FMEAControlExpander 扩展出 control（hit_count≥1，control 的 `stage_index=2`）；若 stage 3 无 cause → stage 2 skipped "D5 无召回 cause"。断言 stage 2 的 `StageRun` 在 stage 3 之后产出（`stages` 排序后 index 仍为 2，但执行序 stage 3 先于 stage 2）。
  - 12 阶段全执行：D4 上下文 → 12 个 StageRun，阶段 1/12 done，阶段 6-9 据数据 done/skipped，阶段 11 据 pc done/skipped。
  - `stage_index` 写入：每个 candidate 的 `metadata.stage_index` == 其产出阶段 index；`to_d4_schema()` 输出含 `stage_index`。
  - skipped 语义：无 embedding → 阶段 3/4/5 skipped；无 SPC 数据 → 阶段 6 skipped reason 含 "SPC"；D5 → 阶段 6-9 skipped reason "D5 阶段不适用"。
  - error 隔离：某 source 抛异常 → 该阶段 error，后续阶段继续，items 不含该阶段候选。
  - LLM 未配置（pc=None）→ 阶段 11 skipped "未配置 LLM"，不审计 `llm_recommend`（attempted=0）。
  - **fusion→LLM 顺序（R2-修复）**：spy `LLMFusionLayer.enrich` + `FusionEngine.merge`，断言 `enrich` 收到的候选数 == `merge` 输出数（fused），**不等于** raw 召回候选数（all_candidates）；即 LLM 吃 fused 不吃 raw，保既有合约。
  - **no-data vs done(0)（R2-修复）**：SPC 有告警但无 FMEA 匹配 → `should_skip` 返回 None + `retrieve` 返回 [] → stage 6 **done(0)**（有数据 0 命中）；SPC 无告警 → `should_skip` 返回 reason → stage 6 **skipped**。两路径分别断言 status。新源（SPC/IQC/MES/...）各测 should_skip 返回 reason 的无数据场景。
  - **LLM 失败隔离（R3-修复）**：`LLMFusionLayer.enrich` 抛异常（mock timeout/provider error）→ stage 11 `error` + 返回未修改 fused，stage 12 照常发射 done，`run()` 不抛，响应仍是 12 阶段 + items 非空（fused 候选保留）。
  - **D5 stage 2 输入边界 + guard + 直查（R3+R4+R10-修复）**：D5 上下文，stage 5 lesson 候选带 `failure_cause_node_id` 但 `stage_index=5` → **不**进 stage 2（仅 semantic 3/4 + linked FMEA 直查触发）；且 stage 2 标 `skipped`（非 done(0)），不调 expand。**R10-修复**：D5 embedding 不可用（stage 3 skipped）+ linked FMEA 有 D4 关键词匹配的 FailureCause → stage 2 **done**（`_lookup_linked_fmea_causes` 命中，扩展出 control，不因 semantic skip 丢 FMEA 控制措施）；D5 无 linked FMEA 且 semantic 无 cause → stage 2 skipped。
  - **LLM 审计结构化 + 失败隔离 + 全失败也审计 + 全失败显 error + 全失败保留 fused（R3+R4+R5+R6+R7+R11-修复）**：mock `LLMFusionLayer.enrich` 抛错 → stage 11 `error` + `llm_attempted=0` → `_maybe_write_llm_audit` 不写 `llm_recommend` audit，响应 12 阶段 + items 非空 + 无 500；mock enrich 成功 → audit 读结构化 `llm_attempted/succeeded/failed`（不解析 summary 字符串）；mock `_maybe_write_llm_audit` 内部异常 → 仍不破坏响应（try/except 兜底）；**mock enrich 全失败（`LLMOutcome(attempted=2, succeeded=0, failed=2, candidates=[])`，不抛）→ stage 11 `error`（不绿，R6）+ audit 写 `status="llm_failed"`（R5）+ **stage 12 发射原 fused（非空，R11-修复：不因 outcome.candidates 空丢确定性推荐）**。
  - **should_skip 强制 + callable + async + per-stage（R4+R5+R6+R10-修复）**：mock 某新源缺 should_skip / 非 callable（设成属性）/ 非 async → 该 stage `error`（不阻断整请求，其余 stage + 12 阶段响应照常，**不**在构造时 raise）；`validate_all_new_sources()` lint 返回违规列表（启动/CI 用，非请求路径）。
- `backend/tests/recommendation/test_sources_spc.py` / `test_sources_iqc.py` / `test_sources_supplier.py` / `test_sources_mes.py` / `test_sources_same_type.py` / `test_sources_lessons.py`：每源 `retrieve` 返回结构 + `should_skip`（无数据返 reason、有数据返 None）+ factory_id 隔离 + 空 vs 有数据。
- `backend/tests/recommendation/test_lessons_extraction.py`：
  - `advance_capa` D7→D8 抽取 **d7_prevention** lessons（`source_d_step='d7'`）+ enqueue_embedding + `LESSON_EXTRACTED` audit（`correlation_id=uuid5(capa_id,"lesson_extract_d7")`）；**抽取异常 → fail-closed 阻断转换 400（D8 不推进、状态仍 D7、无 TRANSITION audit），重试 advance 重新抽取后再推进（R7+R9-修复，单源合约）**。
  - **d8_closure 更新钩子（R2+R3+R4+R7-修复 atomic+fail-closed）**：CAPA 进 D8 后填 `d8_closure`（2 句）保存 → 2 行 `source_d_step='d8'` lesson；改 `d8_closure`（删 1 句、改 1 句、加 1 句）保存 → 行数 = 新句子数，旧句 lesson 已 delete；同文本再保存 → 行数不变（幂等）；**d8_closure 含重复句** → 去重后 1 行（不碰撞 lesson_id）；**抽取中异常（mock `enqueue_embedding` 抛错）→ savepoint 回滚 + 保存 400（d8_closure 未保存，KB 未变）**；**用户重试保存 → 重新抽取 → 成功则保存 + KB 一致**。
  - **D7 lessons fail-closed（R7-修复）**：D7→D8 转换时 d7 抽取异常（mock）→ 阻断转换 400（D8 不推进、不写 TRANSITION audit、不抽 lessons）；重试 advance → 重新抽取 → 成功则推进 D8 + d7 lessons 入库。
  - **D7→D8 不抽 d8_closure（R2-修复）**：D7→D8 转换时 `d8_closure` 为空，断言此时**不产生** `source_d_step='d8'` 行（只产 d7）。
  - **幂等（R1-决策 17）**：同一 CAPA 两次触发 `_extract_lessons`（同 source_d_step）→ 行数不变（upsert 同 `lesson_id`）、embedding 不重复、audit `correlation_id` 相同。
  - **并发（R1-决策 17）**：并发 advance D7→D8 → 仅一个推进，lessons 不重复。
  - **确定性 lesson_id**：同 (capa, source_d_step, normalized_text) → 相同 `lesson_id`（uuid5）。
- `backend/tests/capa/test_capa_d7_gate.py`（R2-决策 18）：
  - D7 有 2 条推荐、0 处置 → `advance_capa` 抛 `ValueError`（API 400），未写 TRANSITION audit、未抽 lessons、状态仍 D7_PREVENTION。
  - 处置 1 条（剩 1 条未处置）→ 仍 400。
  - 2 条全处置（confirmed/skipped/auto_filled 任一）→ 200 推进 D8_CLOSURE + 抽 d7 lessons + 写 TRANSITION audit。
  - D7 无推荐（canonical scope 下真无：无关联 FMEA 且 PL 无 FMEA）→ 闸口平凡通过，200 推进。
  - **degraded-empty 健康检查（R7+R8-修复）**：① CAPA 有 `fmea_ref_id` 但 fmea_docs preload 降级未含该 FMEA → fail-closed 400 "关联 FMEA 未加载"；② **CAPA 无 `fmea_ref_id`，PL 有 FMEA（canonical count>0），但 preload 返回空（降级）→ fail-closed 400 "PL FMEA 未加载"（R8-修复：D7 推荐可来自 PL keyword 匹配，不仅 linked fmea_ref_id）**；③ PL 真 0 FMEA + 无 fmea_ref_id → 真无推荐，200 通过。
  - **capa_id 限定（R8-修复）**：CAPA-A 与 CAPA-B 共用同 FMEA key（fmea_id+fm+cause），CAPA-B 有该 key 的 `CapaD7NodeAction`，CAPA-A 无 → CAPA-A 闸口**仍 400**（查询 `WHERE capa_id=CAPA-A.report_id`，他 CAPA 动作不满足本 CAPA 闸口）。
  - **partial preload（R9-修复）**：PL 有 3 个 FMEA（canonical count=3），但 fmea_docs 只加载 2 个（partial preload），D7 重算返回 2 条推荐（已加载子集）→ 闸口 **completeness check 在生成前跑**：loaded(2) ≠ canonical(3) → fail-closed 400 "FMEA 预加载不完整"（不验证已加载 2 条子集而漏第 3 个 FMEA 的未处置推荐）。
  - **stale 处置（R10-修复）**：CAPA 有 D7 推荐 key K（fm_name="虚焊"），用户 confirmed（动作存 `recommendation_hash=hash("虚焊|...|...")`）；之后 FMEA 节点改名 fm_name="虚焊2" → 闸口重算当前推荐 hash ≠ 动作 hash → key K 视为 stale/未处置 → 400 "已 stale（FMEA 变更）"，强制重新处置；既有 Spec A 动作（hash NULL）→ 视为 stale → 需重新处置。
  - `failure_cause_node_id` 为 NULL 的推荐 key 与 `capa_d7_node_action` 同 NULL key 匹配（COALESCE 收口）。
  - 直接 `POST /api/capa/{id}/advance`（空 body）无 D7 动作 → 400（不可绕过 UI）。
  - **canonical scope（R2+R5-修复 over-block）**：CAPA 属 PL-A，工厂另有 PL-B 的 D7 推荐 → 闸口只看 PL-A 推荐（`capa.factory_id AND product_line_code=PL-A`），**PL-B 未处置不阻塞 PL-A CAPA 关闭**；推进用户 `allowed_pls` 窄于 PL-A 时（用户只能看 PL-A 的子集）闸口仍看 PL-A 全部 D7 推荐，未处置 → 400。两 PL 测试断言无关 PL 不阻塞。
  - **fail-closed（R2-修复 subset）**：重算 D7 推荐异常（fmea_docs load 失败 / `get_d7_recommendations` 抛错）→ `ValueError("D7 推荐重算失败")` → 400（不误判"无推荐"放行）。
- `backend/tests/recommendation/test_adopt_stage_index.py`：`adopt_recommendation` 透传 `stage_index` 到 `capa_ai_adoption`（Spec A 列非 None）。
- 既有 `test_capa_recommendation.py` / `test_d7_recommendations.py` / `test_hybrid_recommendation_pipeline.py`：响应加 `stages` 字段后断言不破（既有断言查 `items`/`existing_controls`，不拒新字段）；**新增 D5 形状断言（R9-修复）**：D5 响应仍是 `{stages, existing_controls, general_suggestions}`（非 `{stages, items}`），`existing_controls` 用 `to_d5_control_schema`、`general_suggestions` 用 `to_d5_suggestion_schema`（不被 `to_d4_schema` 覆盖），各含 `stage_index`。

### 前端 vitest

- `RecommendationDAG.test.tsx`：12 节点渲染 + 状态色 + `data-e2e="rec-dag-stage-{index}"`（index=1..12）+ `data-status`。
- `D4RecPanel.test.tsx` / `D5RecPanel.test.tsx`（既有扩展）：DAG 渲染（`rec-dag-stage-*`）、每项 provenance Tag `rec-source-*` / `rec-item-stage-*`（区别于 DAG 节点）、采纳 payload 含 `stage_index`。

### Spec C 依赖就绪

本 spec 落地后，Spec C 故事 spec 可断言：`data-e2e="rec-dag-stage-{index}"` 的 `data-status`（关键阶段 done/skipped）、`rec-source-{source}` 标签存在、`rec-item-stage-{index}` 项阶段徽标、采纳留痕 `capa_ai_adoption.stage_index` 非 None。

## 验收

- `RecommendationOrchestrator` 把现有 4 D4 源 + 3 D5 源 + 6 新源组织成 12 阶段，返回 `{stages, items}`；每阶段 `status/hit_count/summary/error` 正确；skipped 注明原因；error 不阻断后续（R-决策 5）。
- **响应 `stages` 恰好 12 行、`index` 集合 = {1..12} 无重复，stage 12 单次发射**（R1-决策 16）；**D5 stage 2 FMEAControlExpander 消费 stage 3/4 semantic ∪ linked FMEA 直查 causes（R10-修复：embedding 不可用时仍扩展 FMEA 控制措施），control 的 `stage_index=2`**（R1-决策 15）。
- D4/D5 API 响应含 `stages`，`items`/controls/suggestions 每项含 `stage_index`（R-决策 3）。
- `AdoptRequest` 加 `stage_index`，`adopt_recommendation` 透传入库（Spec A 决策 1 兑现，R-决策 4）。
- 6 新源各 `retrieve` 返回 `RecommendationCandidate`，`match_source` 按决策 7 表；无数据 `should_skip` 返回 reason，编排器标 skipped（R-决策 6）。
- `capa_lessons_learned` 表通过 Alembic 迁移建出（含 `ix_capa_lessons_unique` 唯一索引）；**D7→D8 抽 d7_prevention lessons，d8_closure 更新时抽 d8 lessons**（R2-修复按生命周期拆分）；enqueue_embedding + audit；**抽取异常 fail-closed 阻断转换/保存 400（KB==CAPA，R7+R9-修复，不残留 stale）**（R-决策 10）。
- **lesson 抽取幂等：d7 lessons 用确定性 uuid5 upsert（同 CAPA 重试/双击/并发 advance → 不新增行、不重复入队 embedding、audit `correlation_id` 相同；`SELECT FOR UPDATE` 串行化并发 advance）；d8 lessons 用 delete-and-rebuild（编辑后旧行删除，不残留）**（R1-决策 17 + R3-修复 stale）。
- **D7→D8 闭环闸口：转换前用 canonical CAPA 相关 scope（`capa.factory_id` + `capa.product_line_code`）重算 D7 推荐，要求每个 key 有**当前 `capa_id` 限定 + `recommendation_hash` 匹配**的 `CapaD7NodeAction`（R8+R10-修复：防他 CAPA 同 key 动作 + 防 FMEA 改名 stale 处置）；未处置/stale → 400 早返回；重算异常 → fail-closed 400；**completeness-before-generation（R9-修复）：partial preload / 关联 FMEA 缺失 / PL 有 FMEA 但 preload 空 → fail-closed 400**；直接 `POST /advance` 不可绕过；真无推荐（PL 0 FMEA + 无 linked）平凡通过**（R2+R5+R7+R8+R9+R10-决策 18）。
- **执行顺序 recall → fusion → LLM（LLM 吃 fused 不吃 raw），与既有 `HybridRecommendationPipeline` 合约一致**（R2-修复）；`LLMFusionLayer.enrich` 收到 `FusionEngine.merge` 输出，非 raw 召回集。
- **no-data vs done(0) 区分：新源 `should_skip` 返回 reason → skipped；`should_skip` None + retrieve [] → done(0)；测试覆盖两路径**（R2-修复）。
- **选择器合约：DAG 节点 `rec-dag-stage-{index}`、项徽标 `rec-item-stage-{index}`，index 1..12 与 `StageRun.index` 对齐**（R2-修复冲突）。
- **lessons 抽取 fail-closed + savepoint 原子 + embedding 清理 + in-flight 防race（R3+R4+R7+R8+R9-修复）**：D7→D8 仅抽 d7_prevention（upsert），d8_closure 更新时 delete-and-rebuild（savepoint）；**任一抽取失败 → 阻断转换/保存 400（KB==CAPA，无 dirty/读路径副作用）**；d8 delete-and-rebuild **同步清理孤儿 `document_embeddings` + claim-safe 取消 pending outbox（R8+R9）**；**embedding worker upsert 前重查 lesson 行存在，in-flight job 行已删则丢弃（R9-修复防 stale 写入）**；重复 normalized_text 去重；`LessonsLearnedSource` JOIN 双保险。
- **LLM 失败隔离 + 审计结构化 + 全失败也审计 + 全失败显 error + 全失败保留 fused（R3+R4+R5+R6+R11-修复）**：`LLMFusionLayer.enrich` 硬化 catch-all 不抛——provider 全失败 → `attempted>0, succeeded=0` → stage 11 **`error`（不绿，DAG 显红，R6-修复）** + audit 写 `status="llm_failed"`（**全失败也审计，不隐藏 LLM 用量，R5-修复**），**`_exec_llm_stage` 返回原 fused（非空，R11-修复：不因 `outcome.candidates` 空丢确定性推荐）**，stage 12 发射 fused；仅意外非 LLM 错误才抛 → stage 11 `error` + `llm_attempted=0` + 未修改 fused，stage 12 照常发射，`run()` 不抛；审计读结构化字段（不解析 summary），审计层 try/except 兜底，**审计不破坏响应**。
- **D5 stage 2 输入边界 + guard（R3+R4-修复）**：先算 `cause_cands`（stage_index in {3,4}）再分支——空则 `skipped`（不调 expand 误报 done(0)），非 stage 3/4 的 cause 不触发。
- **should_skip 强制 + callable + async + per-stage（R4+R5+R6+R10-修复）**：6 新源 `should_skip` 必须存在、可调用、`iscoroutinefunction`（async）；**协议校验 per-stage 运行时**——`_exec_recall_stage` 调 `_check_source_protocol`，违规 → 该 stage `error`（不阻断构造/整请求，其余 stage + 12 阶段响应照常）；启动/CI 跑 `validate_all_new_sources()` lint；编排器 `await should_skip(context)`（async DB 查存在性，不误判 coroutine truthy）。
- **skip/done(0) 合约一致（R3-修复）**：6 新源强制 `should_skip`（数据存在性），既有源结构性前置（embedding/linked_fmea/pc None）由编排器 `_stage_precondition` 集中，唯一规则——`should_skip`/`_stage_precondition` 返回 reason → skipped；None + retrieve [] → done(0)；非空 → done(N)。
- `SameTypeProductKBSource` 跨工厂同类型检索受 `user_product_lines` 收口；`capa_eightd` 无 supplier_id 时 `SupplierHistorySource` 经 IQC/SCAR 取供应商（R-决策 11/13）。
- `<RecommendationDAG>` 12 节点 + 状态色 + 命中数 + `data-e2e="rec-dag-stage-{index}"` + `data-status`；D4/D5 RecPanel 每项 `rec-source-{source}` + `rec-item-stage-{index}` Tag（R-决策 8/9）。
- 无 LLM 凭证时阶段 11 skipped + 核心闭环照跑（故事验收"无 LLM 凭证时 AI 步骤跳过+告警"）。
- 后端新增 pytest 全绿（含 R1~R9 各项 + R10 三项回归：D5 stage 2 linked-FMEA 直查不依赖 embedding / 源协议 per-stage error 不阻断整请求 / D7 闸口 recommendation_hash 防 stale 处置）；既有推荐/D7/capa 测试不退化；前端 vitest + `tsc --noEmit` + `npm run build` 绿；`make check` 绿。
- `docs/` 同步：本 spec + `PROGRESS.md` 缺口清单 P0-2/P0-3/P1-5~10 勾选。

## 参考

- 故事：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（12 阶段编排见「AI 推荐流程编排」节）
- Spec A：`docs/superpowers/specs/2026-07-03-us-e2e-01-spec-a-d4-verification-adoption-design.md`（`stage_index` 预留决策 1、采纳映射表）
- 现有代码：`backend/app/services/{hybrid_recommendation_pipeline,fusion_engine,llm_fusion_layer,recommendation_sources,recommendation_types}.py`、`backend/app/services/lessons_learned/service.py`、`backend/app/api/capa.py:342/425`、`frontend/src/components/capa/{D4,D5,D7}RecPanel.tsx`
- 数据层：`backend/app/services/{spc_service,iqc_inspection_service,supplier_quality_service,mes_service,mes_connector}.py`、`backend/app/models/{iqc_inspection,mes,capa}.py`
- 相关 ADR：ADR-0001（UUID v4）、ADR-0003（factory_id 行级隔离）、ADR-0004（手写 AuditLog）、ADR-0013（手写 Alembic）
- 依赖：embedding worker 扩 `capa_lesson` 实体（P0 follow-up 同类）；`product_lines.product_type_code` 已确认存在（`product_line.py:20`）；SPC 复用 `match_fmea_for_alarm`（`spc_service.py:379`）
- 后续 spec：Spec C（故事级 E2E `capa-story-closed-loop.spec.ts`，依赖本 spec 的 `rec-dag-stage-*` / `rec-item-stage-*` / `rec-source-*` 选择器与 `stage_index` 留痕）
