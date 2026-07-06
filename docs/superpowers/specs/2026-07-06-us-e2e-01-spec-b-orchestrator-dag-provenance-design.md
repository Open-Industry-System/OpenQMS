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
2. **P0-2 DAG 可视化面板** — 前端新 `<RecommendationDAG>` 组件，12 节点 + 状态色 + 命中数徽标 + `data-e2e="rec-stage-{n}"`。
3. **P0-3 provenance UI + testid** — 每条推荐 `<Tag data-e2e="rec-source-{source}">` + 阶段命中徽标；payload 加 `stage_index`。
4. **P1-5~10 六类新推荐源** — `SPCAnomalySource` / `IQCSource` / `SupplierHistorySource` / `MESSource` / `SameTypeProductKBSource` / 结构化 `LessonsLearnedSource`（含新表 `capa_lessons_learned`）。
5. **采纳 `stage_index` 透传闭环** — Spec A 留的口子：编排器返回 `stage_index` → 前端采纳回传 → `AdoptRequest` 扩字段 → `adopt_recommendation` 透传入库。

### 不在本 spec 范围

- 故事级 E2E spec `capa-story-closed-loop.spec.ts`（P2-11，Spec C）—— 但本 spec 的 `data-e2e="rec-stage-{n}"` / `rec-source-{source}` 选择器是 Spec C 断言的依赖
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

6. **6 类新源遵循现有 Source 接口**：`async retrieve(context) -> list[RecommendationCandidate]`，构造器 `(db, embedding_provider=None)`，`name` 类属性 = 内部 source 标识。`match_source` 外部值按下表与内部 `source` 映射（`to_d4_schema` 已有 `rule_engine→rule` 映射模式，新源沿用）。无数据时返回 `[]`，编排器据 `summary` 判 skipped。

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

8. **DAG 组件独立、D4/D5 共用**：`<RecommendationDAG stages={stages} />` 放在 `D4RecPanel` / `D5RecPanel` 的 `<Card>` 顶部（推荐列表上方）。12 节点用 Ant `Steps`（垂直方向，`size="small"`）或自定义 grid 渲染；每节点：名称 + 来源 Tag + 状态色（done=green/skipped=orange/error=red/running=blue/pending=default）+ 命中数 Badge。`data-e2e="rec-stage-{n}"` + `data-status="{status}"` 供 Spec C E2E 断言。无 LLM 凭证时阶段 11 `skipped`。

9. **provenance Tag per item**：D4/D5 RecPanel 的每个推荐项加 `<Tag data-e2e="rec-source-{match_source}">{来源标签}</Tag>` + `<Tag data-e2e="rec-stage-{stage_index}">阶段{stage_index}</Tag>`。D4 现有按 `match_source` 分组保留（分组标题 + 每项 provenance Tag 并存）。`rec-source-*` 与 `rec-stage-*` 是 Spec C 故事 spec 的断言钩子。

10. **P1-10 经验教训结构化 = 新表 + 闭合钩子**：新表 `capa_lessons_learned`（`lesson_id, capa_id, factory_id, lesson_text, category, tags(JSONB), source_d_step, created_at`），在 `advance_capa` D7→D8_CLOSURE 转换时从 `d7_prevention` / `d8_closure` 抽取结构化 lesson 行（一句预防/一条经验 → 一行）。`LessonsLearnedSource`（阶段 5）用 pgvector 语义匹配 `lesson_text` 而非裸 D2→D2（`HistoricalCAPASource` 仍保留作 fallback，阶段 5 优先 lessons，无结果时 orchestrator 不降级到 historical，保持阶段边界清晰）。闭合钩子复用 `advance_capa` 既有事务，单 commit。

11. **P1-9 同类型产品 KB = 新 Source，不改 SemanticSearchSource**：`SemanticSearchSource` 按 `user_product_lines` 过滤（行级权限语义），改它加 `product_type` 维度会混淆两种 scope。新 `SameTypeProductKBSource` 查 `document_embeddings` JOIN `product_lines` ON `de.product_line_code = pl.code` WHERE `pl.product_type_code = (当前 CAPA 产品线的 product_type)` AND `de.product_line_code != 当前 PL`（跨工厂同类型，排除本产品线避免与阶段 2/3 重复），仍受 `user_product_lines` 行级权限收口（admin 全权限；非 admin 仅在用户可见产品线内匹配同类型）。依赖 `product_lines.product_type_code` 列（实施时确认列名）。

12. **P1-8 MESSource 查已持久化数据，不等真实集成**：`mes_scrap_records` / `mes_equipment_status` / `mes_measurement_ingestions` 表已存在，mock 连接器 ingest 路径已通（`mes_connector.py` + `mes_service.py`）。`MESSource` 直接查这些表（产品线近 30 天 scrap 缺陷模式 + equipment 停机原因），映射到候选根因。无 MES 数据 → `skipped` reason="产品线暂无 MES 数据"。真实 MES 接入后数据源不变，仅数据量增加。

13. **D4/D5 API 响应加 `stages`，向后兼容**：D4 → `{stages: [...], items: [...]}`；D5 → `{stages: [...], existing_controls: [...], general_suggestions: [...]}`。`items`/controls/suggestions 每项加 `stage_index`。旧前端忽略 `stages` 仍可工作（但本 spec 前端同步落地 DAG，无旧前端兼容负担）。

14. **编排器不引入 SSE/流式**：本 spec 同步执行 12 阶段，API 一次返回全部终态。`running`/`pending` 状态在 DAG 组件预留但 API 响应不出现。流式 SSE 留后续（故事不要求）。

15. **显示顺序 ≠ 执行顺序（R1-修复 D5 stage 2 依赖）**：12 阶段的 `index` 是**显示顺序**（DAG 节点编号 + `rec-stage-{n}` testid 契约），不是执行顺序。`FMEAControlExpander`（D5 stage 2）是**派生阶段**——它不独立 retrieve，而是消费 stage 3（semantic）/ stage 4（same-type）召回的 FailureCause 候选扩展出 Control。编排器分两遍执行：①**召回遍**跑所有独立 retrieve 阶段（1 上下文 / 2 D4=FMEAGraphSource / 3 / 4 / 5 / 6-9 D4 / 10 规则 / 11 LLM），把 cause 候选收入 `all_candidates`；②**派生遍**跑 stage 2 D5（FMEAControlExpander over 已召回 causes），产出 control 候选。每个 `StageRun` 仍按其 `index` 报告（D5 stage 2 的 `StageRun` 在派生遍产出，显示位置不变）。D4 无派生阶段，stage 2 = FMEAGraphSource 在召回遍即完成。**回归测试**：D5 语义召回产 1 cause → stage 2 FMEAControlExpander 扩展出 control，hit_count≥1，control 的 `stage_index=2`。

16. **stage 12 终态单次发射（R1-修复重复 output stage）**：`STAGE_PLAN` 含 12 项，但 stage 12（输出推荐列表）标记 `terminal=True`，**编排器主循环跳过 terminal 阶段**——它在 FusionEngine merge 之后单次发射。主循环只处理 stage 1-11（stage 1 internal 上下文、stage 2-10 sources、stage 11 LLM）。主循环结束后：`fused = fusion.merge(all_candidates, context)` → 追加**唯一一个** `StageRun(12, "输出推荐列表", "internal", "done", hit_count=len(fused))`。**禁止**在主循环的 `internal` 分支处理 stage 12 + 循环后再 append（那会产生 13 行/重复 index 12）。**回归测试**：响应 `stages` 恰好 12 行、`index` 集合 = {1..12} 无重复。

17. **lesson 抽取幂等（R1-修复 lesson 重复）**：`capa_lessons_learned.lesson_id` 用**确定性** `uuid5(NAMESPACE_URL, f"capa_lesson:{capa_id}:{source_d_step}:{normalized_lesson_text}")`（非随机 uuid4），同一 CAPA 同一原文反复抽取产生相同 `lesson_id`。抽取用 `pg_insert.on_conflict_do_update(index_elements=["lesson_id"], set_={category/tags/updated_at})` upsert，重试/双击/并发 advance 不会产生重复行、不会重复入队 embedding（同 `entity_id` 幂等）。`advance_capa` D7→D8 转换开头 `SELECT capa ... FOR UPDATE` 串行化并发 advance（状态机本身也拒绝 D8→D8 再转，FOR UPDATE 兜底不确定提交后的重试）。`LESSON_EXTRACTED` 审计带 `correlation_id = uuid5(capa_id, "lesson_extract")`，重试产生相同 correlation_id 便于去重查询；审计 append-only 可接受（它是转换日志，不喂 KB）。**回归测试**：同一 CAPA 两次触发抽取 → lessons 行数不变（upsert）、embedding 入队不重复、audit correlation_id 相同。

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

注：阶段 6-9 仅 D4（D5 是措施推荐，SPC/MES/IQC/供货是根因线索，D5 用不上）；D5 时这些阶段 `skipped` reason="D5 阶段不适用"。阶段 2 D5 用 `FMEAControlExpander`（基于阶段 3/4 召回的 cause 扩展控制），是**派生阶段**（决策 15）：主循环召回遍先跑 stage 3/4 收 cause，派生遍再跑 stage 2 扩展 control，`StageRun` 仍按 index=2 报告。阶段 12 是 **terminal**（决策 16）：主循环跳过，FusionEngine merge 后单次发射。`index` 是显示顺序（DAG 节点 + `rec-stage-{n}` 契约），非执行顺序。

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

- `lesson_id` 由应用层 `_extract_lessons` 用 `uuid5` 确定性生成（非随机），同一 (capa, source_d_step, normalized_text) → 同一 `lesson_id`。PK 即去重键，upsert 命中同 PK 不新增行。
- 在 `advance_capa` D7→D8_CLOSURE 转换时，从 `capa.d7_prevention`（预防措施文本）+ `capa.d8_closure`（闭环总结）抽取：每个预防措施/经验点 → 1 行 lesson。抽取规则：按句号/换行切分，过滤空句，`category` 启发式判定（含"预防/防呆/poka"→prevention；含"检测/探测/检验"→detection；含"体系/流程/制度"→systemic；余 →process）。`source_d_step` 标来源。`lesson_text_normalized = "".join(text.lower().split())`。
- 抽取用 `pg_insert(CapaLessonLearned).values(...).on_conflict_do_update(index_elements=["lesson_id"], set_={"category":..., "tags":..., "updated_at": func.now()})` upsert（决策 17）。重试/双击/并发 advance → 同 `lesson_id` 命中 upsert，不新增行、不重复入队 embedding（同 `entity_id` 幂等）。
- `enqueue_embedding(db, "capa_lesson", lesson.lesson_id, lesson.product_line_code, lesson.factory_id)` 入队，embedding worker 把 `capa_lessons_learned` 加入 `table_field_map`（P0 follow-up 已识别 worker 不认识 `agent_memory`，本 spec 同理需加 `capa_lesson`）。upsert 下同 `lesson_id` 重复入队是幂等的（worker 按 `entity_id` upsert `document_embeddings`）。
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

`backend/alembic/versions/20260706_add_capa_lessons_learned.py`，`down_revision` 取 Spec A head（`20260703_capa_verif` 或其后继，实施时 `alembic heads` 确认），手写 `op.create_table("capa_lessons_learned")` + 普通索引（`capa_id` / `product_line_code`）+ **唯一表达式索引** `CREATE UNIQUE INDEX ix_capa_lessons_unique ON capa_lessons_learned (capa_id, source_d_step, md5(lesson_text_normalized))`（决策 17 防重复，PK 确定性 uuid5 已是第一道防线，此索引为并发兜底）。遵循 ADR-0013/0001/0003。

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

handler 改动（`api/capa.py:414/497`）：`result = await pipeline.recommend(...)` 后，`return {"stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages], "items": [c.to_d4_schema() for c in result.items]}`。

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

    async def run(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
        stages: list[StageRun] = []
        all_candidates: list[RecommendationCandidate] = []

        # ── 召回遍：跑所有非 terminal、非 derived 阶段（stage 1, 3-11，及 D4 的 stage 2）──
        for spec in STAGE_PLAN:
            if spec.terminal or spec.derived:
                continue   # stage 12 terminal 暂留；D5 stage 2 derived 留派生遍
            # D5 时 stage 2 是派生（_D5_DERIVED），跳过召回遍；D4 时 stage 2 = FMEAGraphSource 正常跑
            if context.stage == "d5" and spec.index in _D5_DERIVED:
                continue
            run = await self._exec_recall_stage(spec, context, all_candidates)
            stages.append(run)
            # _exec_recall_stage 内部把 candidate.metadata["stage_index"] = spec.index 后 extend all_candidates

        # ── 派生遍：D5 stage 2 FMEAControlExpander over 已召回 causes（决策 15）──
        if context.stage == "d5" and any(c.metadata.get("failure_cause_node_id") for c in all_candidates):
            spec = next(s for s in STAGE_PLAN if s.index == 2)
            cause_cands = [c for c in all_candidates if c.metadata.get("failure_cause_node_id")]
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
        elif context.stage == "d5":
            stages.append(StageRun(2, "本产品 FMEA 检索", "fmea_graph", "skipped",
                                   summary="D5 无召回 cause，跳过控制扩展"))

        # ── Fusion + terminal stage 12 单次发射（决策 16）──
        fused = self.fusion.merge(all_candidates, context)
        stages.append(StageRun(12, "输出推荐列表", "internal", "done",
                               hit_count=len(fused), summary=f"输出 {len(fused)} 条带来源推荐"))

        # 按 index 排序，保证显示顺序 1..12（派生遍/召回遍交错不影响最终序）
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
        # 3. LLM（stage 11）—— enrich 当前候选，attempted/succeeded/failed 入 summary
        if spec.source_kind == "llm":
            if self.pc is None:
                return StageRun(spec.index, spec.name, "llm", "skipped", summary="未配置 LLM")
            outcome = await self.llm_layer.enrich(all_candidates, context)
            all_candidates.clear(); all_candidates.extend(outcome.candidates)
            for c in all_candidates:
                c.metadata.setdefault("stage_index", spec.index)
            return StageRun(spec.index, spec.name, "llm", "done",
                            hit_count=len(outcome.candidates),
                            summary=f"attempted={outcome.attempted} succeeded={outcome.succeeded} failed={outcome.failed}")
        # 4. 普通 source
        source = self._sources.get(spec.source_kind)
        try:
            pre_skipped = source.should_skip(context) if hasattr(source, "should_skip") else None
            if pre_skipped:
                return StageRun(spec.index, spec.name, spec.source_kind, "skipped", summary=pre_skipped)
            candidates = await source.retrieve(context)
            for c in candidates:
                c.metadata["stage_index"] = spec.index
            all_candidates.extend(candidates)
            return StageRun(spec.index, spec.name, spec.source_kind, "done", hit_count=len(candidates),
                            summary=source.summary(candidates) if hasattr(source, "summary") else "")
        except Exception as e:
            logger.warning(f"Stage {spec.index} {spec.name} failed: {e}")
            return StageRun(spec.index, spec.name, spec.source_kind, "error", error=str(e)[:200])
```

**关键不变量**（实施时测试断言）：① `stages` 恰好 12 行，`index` 集合 = {1..12} 无重复（决策 16）；② D5 stage 2 的 `StageRun` 在 stage 3/4 召回 cause 后才产出（决策 15），`hit_count` 反映扩展出的 control 数；③ stage 12 只出现一次（terminal，主循环跳过）。`llm_recommend` 审计从 stage 11 summary 的 attempted/succeeded/failed 取值（`HybridRecommendationPipeline` 薄壳在 `run()` 后调 `write_audit_raw`，逻辑保留）。

注：`should_skip(context) -> str | None` 是新 Source 可选协议方法，返回非 None 即 skipped reason（避免"无数据"与"执行成功 0 命中"混淆——前者 skipped，后者 done）。既有 `FMEAGraphSource` 等无此方法，编排器据 `context.linked_fmea is None` 等上下文判 skipped。

### `HybridRecommendationPipeline` 改为薄壳

```python
class HybridRecommendationPipeline:
    def __init__(self, db, pc, embedding_provider):
        self.orchestrator = RecommendationOrchestrator(db, pc, embedding_provider)

    async def recommend(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
        result = await self.orchestrator.run(context, user=user, report_id=report_id,
                                              factory_id=factory_id, tenant_schema=tenant_schema)
        # llm_recommend 审计逻辑保留（attempted/succeeded/failed 从 stage 11 summary 或 LLMOutcome 取）
        self._maybe_write_llm_audit(result, context, user, report_id, factory_id, tenant_schema)
        return result
```

### 6 类新 Source（`backend/app/services/recommendation_sources.py` 追加）

所有新源遵循：`name` 类属性、`__init__(self, db, embedding_provider=None)`、`async retrieve(context) -> list[RecommendationCandidate]`、可选 `should_skip(context) -> str | None`、可选 `summary(candidates) -> str`。返回的 candidate `source` = 内部标识（见决策 7 表），`metadata` 含 `item_ref` 关键字段 + `product_line_code` + `severity`（供 FusionEngine bonus）。

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
- pgvector 语义查 `document_embeddings` WHERE `entity_type='capa_lesson'` AND `entity_field='lesson_text'`，受 `user_product_lines` 收口，匹配 `context.capa_data.d2_description`（D4）或 `d4_root_cause`（D5）。
- 候选："经验教训：{lesson_text}（来自 {source_capa_document_no}，类别 {category}）"。
- `should_skip`：无 embedding / 无 lessons 数据 → "暂无结构化经验教训"。
- `match_source=lessons_learned`，`item_ref={source_capa_id, lesson_id, category}`。
- 依赖：embedding worker 支持 `capa_lesson` 实体（决策 10 依赖）；未支持时降级 FTS `lesson_text`。

### `advance_capa` 闭合钩子（P1-10，决策 17 幂等）

`backend/app/services/capa_service.py:advance_capa` 在 `D7_PREVENTION → D8_CLOSURE` 转换时：
1. **开头 `SELECT capa ... FOR UPDATE`**（行锁，串行化并发 advance；状态机本身也拒 D8→D8 再转，FOR UPDATE 兜底不确定提交后的重试）。
2. 转换成功后、commit 前，调 `_extract_lessons(capa) -> list[CapaLessonLearned]`：从 `d7_prevention` / `d8_closure` 切句，逐句构造 `CapaLessonLearned`（`lesson_id = uuid5(NAMESPACE_URL, f"capa_lesson:{capa_id}:{source_d_step}:{normalized_text}")`），用 `pg_insert(...).on_conflict_do_update(index_elements=["lesson_id"], set_={category, tags, updated_at})` upsert，`enqueue_embedding(db, "capa_lesson", lesson_id, ...)` 入队。
3. 审计 `LESSON_EXTRACTED`（≤20 字符）记 lesson 数，`correlation_id = uuid5(capa_id, "lesson_extract")`（重试产生相同 correlation_id 便于去重查询；audit append-only 可接受，它是转换日志不喂 KB）。
4. 失败不阻断闭合（lesson 抽取异常 → log warning + skip，D8 仍推进）。

**幂等保证**：同一 CAPA 重试/双击/并发 advance → 相同 `lesson_id` 命中 upsert（不新增行）、相同 `entity_id` 重复入队 embedding 幂等、相同 `correlation_id` audit 可识别。

### `adopt_recommendation` 透传 `stage_index`（Spec A 决策 1 兑现）

`capa_verification_service.adopt_recommendation`（Spec A）把 `CapaAIAdoption(..., stage_index=None, ...)` 改为 `stage_index=req.stage_index`。`AdoptRequest` 加字段（决策 4）。单点改动。

## 前端

### 新组件 `frontend/src/components/capa/RecommendationDAG.tsx`

- Props: `stages: StageRun[]`。
- 渲染：Ant `Steps direction="vertical" size="small"`，每步 `title={阶段名}` + `description={<Space><Tag>{来源}</Tag><Badge count={hit_count} /><Text type="secondary">{summary}</Text></Space>}`，`status` 映射：done→`finish`/skipped→`wait`+灰/error→`error`。或自定义 grid（3 列 × 4 行）更紧凑——实施时择优。
- 每节点 `data-e2e="rec-stage-{index}"` + `data-status="{status}"`。
- 空状态：无 stages → 不渲染（兼容旧响应）。

### `D4RecPanel.tsx` / `D5RecPanel.tsx` 改造

- `getD4Recommendations` / `getD5Recommendations` 返回值取 `res.stages`，传给 `<RecommendationDAG stages={stages} />`，放 `<Card>` 顶部。
- 每个推荐项加 `<Tag data-e2e="rec-source-{item.match_source}">{来源标签}</Tag>` + `<Tag data-e2e="rec-stage-{item.stage_index}">阶段{stage_index}</Tag>`。D4 现有分组（linked/semantic/...）保留，分组内每项加 provenance Tag。
- 采纳按钮 `adoptRecommendation` 调用时 payload 加 `stage_index: item.stage_index`（决策 4）。
- 来源标签 i18n：`d4.sources.{match_source}` / `d5.sources.{match_source}`（zh-CN/en-US 追加）。

### `api/capa.ts` 类型扩展

`D4Recommendation` / `D5ExistingControl` / `D5GeneralSuggestion` 加 `stage_index?: number | null`；新增 `StageRun` 类型；`D4RecommendationResponse` / `D5RecommendationResponse` 加 `stages: StageRun[]`；`AdoptRequest` 加 `stage_index?: number | null`。

### data-e2e 钩子（Spec C 依赖）

| 元素 | testid |
|---|---|
| DAG 阶段节点 | `rec-stage-{n}`（n=0..11，0-indexed）+ `data-status` |
| 推荐来源标签 | `rec-source-{match_source}` |
| 推荐阶段徽标 | `rec-stage-{stage_index}` |
| DAG 容器 | `recommendation-dag` |

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
- `backend/tests/recommendation/test_sources_spc.py` / `test_sources_iqc.py` / `test_sources_supplier.py` / `test_sources_mes.py` / `test_sources_same_type.py` / `test_sources_lessons.py`：每源 `retrieve` 返回结构 + `should_skip` + factory_id 隔离 + 空 vs 有数据。
- `backend/tests/recommendation/test_lessons_extraction.py`：
  - `advance_capa` D7→D8 抽取 lessons 行 + enqueue_embedding + `LESSON_EXTRACTED` audit；抽取异常不阻断闭合。
  - **幂等（R1-决策 17）**：同一 CAPA 两次触发 `_extract_lessons`（模拟重试/双击）→ `capa_lessons_learned` 行数不变（upsert 同 `lesson_id`）、`enqueue_embedding` 对同 `lesson_id` 不重复入队（或入队幂等）、`LESSON_EXTRACTED` audit `correlation_id` 两次相同。
  - **并发（R1-决策 17）**：并发 advance D7→D8（两协程）→ 仅一个成功推进（`SELECT FOR UPDATE` 串行化 + 状态机拒 D8→D8），lessons 不重复。
  - **确定性 lesson_id**：同 (capa, source_d_step, normalized_text) → 相同 `lesson_id`（uuid5）。
- `backend/tests/recommendation/test_adopt_stage_index.py`：`adopt_recommendation` 透传 `stage_index` 到 `capa_ai_adoption`（Spec A 列非 None）。
- 既有 `test_capa_recommendation.py` / `test_d7_recommendations.py` / `test_hybrid_recommendation_pipeline.py`：响应加 `stages` 字段后断言不破（既有断言查 `items`/`existing_controls`，不拒新字段）。

### 前端 vitest

- `RecommendationDAG.test.tsx`：12 节点渲染 + 状态色 + `data-e2e="rec-stage-{n}"` + `data-status`。
- `D4RecPanel.test.tsx` / `D5RecPanel.test.tsx`（既有扩展）：DAG 渲染、每项 provenance Tag `rec-source-*` / `rec-stage-*`、采纳 payload 含 `stage_index`。

### Spec C 依赖就绪

本 spec 落地后，Spec C 故事 spec 可断言：`data-e2e="rec-stage-{n}"` 的 `data-status`（关键阶段 done/skipped）、`rec-source-{source}` 标签存在、采纳留痕 `capa_ai_adoption.stage_index` 非 None。

## 验收

- `RecommendationOrchestrator` 把现有 4 D4 源 + 3 D5 源 + 6 新源组织成 12 阶段，返回 `{stages, items}`；每阶段 `status/hit_count/summary/error` 正确；skipped 注明原因；error 不阻断后续（R-决策 5）。
- **响应 `stages` 恰好 12 行、`index` 集合 = {1..12} 无重复，stage 12 单次发射**（R1-决策 16）；**D5 stage 2 FMEAControlExpander 在 stage 3/4 召回 cause 后派生产出，control 的 `stage_index=2`，不再因执行序丢失 D5 控制**（R1-决策 15）。
- D4/D5 API 响应含 `stages`，`items`/controls/suggestions 每项含 `stage_index`（R-决策 3）。
- `AdoptRequest` 加 `stage_index`，`adopt_recommendation` 透传入库（Spec A 决策 1 兑现，R-决策 4）。
- 6 新源各 `retrieve` 返回 `RecommendationCandidate`，`match_source` 按决策 7 表；无数据 `should_skip` 返回 reason，编排器标 skipped（R-决策 6）。
- `capa_lessons_learned` 表通过 Alembic 迁移建出（含 `ix_capa_lessons_unique` 唯一索引）；`advance_capa` D7→D8 抽取 lessons + enqueue_embedding + audit；抽取异常不阻断闭合（R-决策 10）。
- **lesson 抽取幂等：同 CAPA 重试/双击/并发 advance → `lesson_id` 确定性 uuid5 命中 upsert，不新增行、不重复入队 embedding、audit `correlation_id` 相同；`SELECT FOR UPDATE` 串行化并发 advance**（R1-决策 17）。
- `SameTypeProductKBSource` 跨工厂同类型检索受 `user_product_lines` 收口；`capa_eightd` 无 supplier_id 时 `SupplierHistorySource` 经 IQC/SCAR 取供应商（R-决策 11/13）。
- `<RecommendationDAG>` 12 节点 + 状态色 + 命中数 + `data-e2e="rec-stage-{n}"` + `data-status`；D4/D5 RecPanel 每项 `rec-source-{source}` + `rec-stage-{index}` Tag（R-决策 8/9）。
- 无 LLM 凭证时阶段 11 skipped + 核心闭环照跑（故事验收"无 LLM 凭证时 AI 步骤跳过+告警"）。
- 后端新增 pytest 全绿（含 R1 三项回归：12 唯一索引 / D5 派生依赖 / lesson 幂等）；既有推荐/D7/capa 测试不退化；前端 vitest + `tsc --noEmit` + `npm run build` 绿；`make check` 绿。
- `docs/` 同步：本 spec + `PROGRESS.md` 缺口清单 P0-2/P0-3/P1-5~10 勾选。

## 参考

- 故事：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（12 阶段编排见「AI 推荐流程编排」节）
- Spec A：`docs/superpowers/specs/2026-07-03-us-e2e-01-spec-a-d4-verification-adoption-design.md`（`stage_index` 预留决策 1、采纳映射表）
- 现有代码：`backend/app/services/{hybrid_recommendation_pipeline,fusion_engine,llm_fusion_layer,recommendation_sources,recommendation_types}.py`、`backend/app/services/lessons_learned/service.py`、`backend/app/api/capa.py:342/425`、`frontend/src/components/capa/{D4,D5,D7}RecPanel.tsx`
- 数据层：`backend/app/services/{spc_service,iqc_inspection_service,supplier_quality_service,mes_service,mes_connector}.py`、`backend/app/models/{iqc_inspection,mes,capa}.py`
- 相关 ADR：ADR-0001（UUID v4）、ADR-0003（factory_id 行级隔离）、ADR-0004（手写 AuditLog）、ADR-0013（手写 Alembic）
- 依赖：embedding worker 扩 `capa_lesson` 实体（P0 follow-up 同类）；`product_lines.product_type_code` 已确认存在（`product_line.py:20`）；SPC 复用 `match_fmea_for_alarm`（`spc_service.py:379`）
- 后续 spec：Spec C（故事级 E2E `capa-story-closed-loop.spec.ts`，依赖本 spec 的 `rec-stage-*` / `rec-source-*` 选择器与 `stage_index` 留痕）
