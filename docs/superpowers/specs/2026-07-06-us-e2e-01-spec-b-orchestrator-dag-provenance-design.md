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

## 12 阶段编排模型

`STAGE_PLAN`（D4/D5 共用，`stage_filter` 控制差异）：

| # | 阶段名 | source_kind | stage_filter | skipped 条件 | 命中语义 |
|---|---|---|---|---|---|
| 1 | 上下文采集 | `ContextSource`（internal） | both | 永不 | hit_count=0，summary="上下文已采集（D2/D4 + 关联 FMEA + 产品线）" |
| 2 | 本产品 FMEA 检索 | `FMEAGraphSource`（D4）/ `FMEAControlExpander`（D5） | both | 无关联 FMEA → skipped "未关联 FMEA" | D4: 候选根因数；D5: 候选控制数 |
| 3 | 全局知识库 RAG 检索 | `SemanticSearchSource` | both | 无 embedding_provider → skipped "未配置 embedding" | 语义命中数 |
| 4 | 同类型产品 KB 检索 | `SameTypeProductKBSource`（NEW） | both | 无 `product_lines.product_type_code` / 无同类型数据 → skipped | 跨产品线同类型命中数 |
| 5 | 经验教训库检索 | `LessonsLearnedSource`（NEW） | both | 无 embedding / 无 lessons 数据 → skipped | lessons 命中数 |
| 6 | SPC 异常关联检索 | `SPCAnomalySource`（NEW） | d4 | 无 SPC 图/无判异记录 → skipped "产品线暂无 SPC 数据" | SPC 关联失效模式数 |
| 7 | MES 设备/过程数据检索 | `MESSource`（NEW） | d4 | 无 MES 连接/无数据 → skipped | MES 异常关联数 |
| 8 | IQC 来料检验数据检索 | `IQCSource`（NEW） | d4 | 无 IQC 不良记录 → skipped | IQC 不良趋势命中数 |
| 9 | 供货历史检索 | `SupplierHistorySource`（NEW） | d4 | 无关联供应商/无评级数据 → skipped | 供货风险命中数 |
| 10 | 规则启发 | `RuleEngineSource`（D4）/ `RuleEngineMeasureSource`（D5） | both | 永不（兜底） | 规则建议数 |
| 11 | LLM 融合排序 | `LLMFusionLayer`（既有） | both | 无 `pc`（LLM 未配置）→ skipped "未配置 LLM" | 增强后候选数（attempted/succeeded/failed 入 summary） |
| 12 | 输出推荐列表 | `ProvenanceTagger`（internal） | both | 永不 | hit_count=最终去重后 items 数，summary="输出 N 条带来源推荐" |

注：阶段 6-9 仅 D4（D5 是措施推荐，SPC/MES/IQC/供货是根因线索，D5 用不上）；D5 时这些阶段 `skipped` reason="D5 阶段不适用"。阶段 2 D5 用 `FMEAControlExpander`（基于阶段 3 召回的 cause 扩展控制），非独立 retrieve，编排器在 D5 时把阶段 2 标 done + hit_count=控制数，source_kind 标 `fmea_graph`（与 D4 一致外部值）。

## 数据模型

### 新表 `capa_lessons_learned`（P1-10）

```python
class CapaLessonLearned(Base):
    __tablename__ = "capa_lessons_learned"
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    lesson_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)   # "prevention" | "detection" | "systemic" | "process"
    source_d_step: Mapped[str] = mapped_column(String(8), nullable=False)  # "d7" | "d8"
    tags: Mapped[list] = mapped_column(JSONB, default=lambda: [])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 索引：ix_capa_lessons_capa (capa_id), ix_capa_lessons_pl (product_line_code)
    # embedding 复用 document_embeddings（entity_type='capa_lesson', entity_id=lesson_id, entity_field='lesson_text'）—— enqueue_embedding 入队
```

- 在 `advance_capa` D7→D8_CLOSURE 转换时，从 `capa.d7_prevention`（预防措施文本）+ `capa.d8_closure`（闭环总结）抽取：每个预防措施/经验点 → 1 行 lesson。抽取规则：按句号/换行切分，过滤空句，`category` 启发式判定（含"预防/防呆/poka"→prevention；含"检测/探测/检验"→detection；含"体系/流程/制度"→systemic；余 →process）。`source_d_step` 标来源。
- `enqueue_embedding(db, "capa_lesson", lesson.lesson_id, lesson.product_line_code, lesson.factory_id)` 入队，embedding worker 把 `capa_lessons_learned` 加入 `table_field_map`（P0 follow-up 已识别 worker 不认识 `agent_memory`，本 spec 同理需加 `capa_lesson`）。
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

`backend/alembic/versions/20260706_add_capa_lessons_learned.py`，`down_revision` 取 Spec A head（`20260703_capa_verif` 或其后继，实施时 `alembic heads` 确认），手写 `op.create_table("capa_lessons_learned")` + 普通索引（`capa_id` / `product_line_code`）。遵循 ADR-0013/0001/0003。

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
    source_kind: str            # 'fmea_graph' | 'semantic_search' | ... | 'internal'
    stage_filter: Literal["d4", "d5", "both"]
    skipped_reason: str | None = None   # 静态 skipped（如 D5 不适用）

STAGE_PLAN: list[StageSpec] = [ ... 12 项 ... ]

class RecommendationOrchestrator:
    def __init__(self, db, pc, embedding_provider):
        self.db = db; self.pc = pc; self.embedding = embedding_provider
        # source 实例按 stage_filter + stage 构造
        self._sources = self._build_sources()

    async def run(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
        stages: list[StageRun] = []
        all_candidates: list[RecommendationCandidate] = []
        for spec in STAGE_PLAN:
            # 1. stage_filter 不匹配 → skipped
            if spec.stage_filter != "both" and spec.stage_filter != context.stage:
                stages.append(StageRun(spec.index, spec.name, spec.source_kind, "skipped",
                                       summary=f"{context.stage.upper()} 阶段不适用")); continue
            # 2. internal stage（1 上下文 / 12 输出）
            if spec.source_kind == "internal":
                stages.append(self._run_internal(spec, context, all_candidates)); continue
            # 3. LLM stage（11）走 LLMFusionLayer
            if spec.source_kind == "llm":
                stage_run, enriched = await self._run_llm_stage(spec, all_candidates, context)
                stages.append(stage_run)
                all_candidates = enriched; continue
            # 4. 普通 source
            source = self._sources.get(spec.source_kind)
            run = StageRun(spec.index, spec.name, spec.source_kind, "running")
            try:
                # skipped 前置检查（无 embedding / 无数据等）由 source.retrieve 内部返回 []，
                # orchestrator 据 context + source.skipped_reason(context) 判 skipped vs done-with-0
                pre_skipped = source.should_skip(context) if hasattr(source, "should_skip") else None
                if pre_skipped:
                    stages.append(StageRun(spec.index, spec.name, spec.source_kind, "skipped",
                                           summary=pre_skipped)); continue
                candidates = await source.retrieve(context)
                for c in candidates:
                    c.metadata["stage_index"] = spec.index
                all_candidates.extend(candidates)
                stages.append(StageRun(spec.index, spec.name, spec.source_kind, "done",
                                       hit_count=len(candidates),
                                       summary=source.summary(candidates) if hasattr(source, "summary") else ""))
            except Exception as e:
                logger.warning(f"Stage {spec.index} {spec.name} failed: {e}")
                stages.append(StageRun(spec.index, spec.name, spec.source_kind, "error",
                                       error=str(e)[:200]))
        # FusionEngine 在 stage 10 后、stage 11 前去重排序（既有逻辑，编排器内联）
        fused = self.fusion.merge(all_candidates, context)
        # stage 11 LLM 已在循环内处理；stage 12 provenance tagging
        stages.append(StageRun(12, "输出推荐列表", "internal", "done",
                               hit_count=len(fused), summary=f"输出 {len(fused)} 条带来源推荐"))
        return RecommendationResult(items=fused, stages=stages)
```

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

### `advance_capa` 闭合钩子（P1-10）

`backend/app/services/capa_service.py:advance_capa` 在 `D7_PREVENTION → D8_CLOSURE` 转换成功后、commit 前，调用新 `_extract_lessons(capa) -> list[CapaLessonLearned]`，逐行 `db.add` + `enqueue_embedding(db, "capa_lesson", lesson_id, ...)`。审计 action `LESSON_EXTRACTED`（≤20 字符）记 lesson 数。失败不阻断闭合（lesson 抽取异常 → log warning + skip，D8 仍推进）。

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
  - 12 阶段全执行：D4 上下文 → 12 个 StageRun，阶段 1/12 done，阶段 6-9 据数据 done/skipped，阶段 11 据 pc done/skipped。
  - `stage_index` 写入：每个 candidate 的 `metadata.stage_index` == 其产出阶段 index；`to_d4_schema()` 输出含 `stage_index`。
  - skipped 语义：无 embedding → 阶段 3/4/5 skipped；无 SPC 数据 → 阶段 6 skipped reason 含 "SPC"；D5 → 阶段 6-9 skipped reason "D5 阶段不适用"。
  - error 隔离：某 source 抛异常 → 该阶段 error，后续阶段继续，items 不含该阶段候选。
  - LLM 未配置（pc=None）→ 阶段 11 skipped "未配置 LLM"，不审计 `llm_recommend`（attempted=0）。
- `backend/tests/recommendation/test_sources_spc.py` / `test_sources_iqc.py` / `test_sources_supplier.py` / `test_sources_mes.py` / `test_sources_same_type.py` / `test_sources_lessons.py`：每源 `retrieve` 返回结构 + `should_skip` + factory_id 隔离 + 空 vs 有数据。
- `backend/tests/recommendation/test_lessons_extraction.py`：`advance_capa` D7→D8 抽取 lessons 行 + enqueue_embedding + `LESSON_EXTRACTED` audit；抽取异常不阻断闭合。
- `backend/tests/recommendation/test_adopt_stage_index.py`：`adopt_recommendation` 透传 `stage_index` 到 `capa_ai_adoption`（Spec A 列非 None）。
- 既有 `test_capa_recommendation.py` / `test_d7_recommendations.py` / `test_hybrid_recommendation_pipeline.py`：响应加 `stages` 字段后断言不破（既有断言查 `items`/`existing_controls`，不拒新字段）。

### 前端 vitest

- `RecommendationDAG.test.tsx`：12 节点渲染 + 状态色 + `data-e2e="rec-stage-{n}"` + `data-status`。
- `D4RecPanel.test.tsx` / `D5RecPanel.test.tsx`（既有扩展）：DAG 渲染、每项 provenance Tag `rec-source-*` / `rec-stage-*`、采纳 payload 含 `stage_index`。

### Spec C 依赖就绪

本 spec 落地后，Spec C 故事 spec 可断言：`data-e2e="rec-stage-{n}"` 的 `data-status`（关键阶段 done/skipped）、`rec-source-{source}` 标签存在、采纳留痕 `capa_ai_adoption.stage_index` 非 None。

## 验收

- `RecommendationOrchestrator` 把现有 4 D4 源 + 3 D5 源 + 6 新源组织成 12 阶段，返回 `{stages, items}`；每阶段 `status/hit_count/summary/error` 正确；skipped 注明原因；error 不阻断后续（R-决策 5）。
- D4/D5 API 响应含 `stages`，`items`/controls/suggestions 每项含 `stage_index`（R-决策 3）。
- `AdoptRequest` 加 `stage_index`，`adopt_recommendation` 透传入库（Spec A 决策 1 兑现，R-决策 4）。
- 6 新源各 `retrieve` 返回 `RecommendationCandidate`，`match_source` 按决策 7 表；无数据 `should_skip` 返回 reason，编排器标 skipped（R-决策 6）。
- `capa_lessons_learned` 表通过 Alembic 迁移建出；`advance_capa` D7→D8 抽取 lessons + enqueue_embedding + audit；抽取异常不阻断闭合（R-决策 10）。
- `SameTypeProductKBSource` 跨工厂同类型检索受 `user_product_lines` 收口；`capa_eightd` 无 supplier_id 时 `SupplierHistorySource` 经 IQC/SCAR 取供应商（R-决策 11/13）。
- `<RecommendationDAG>` 12 节点 + 状态色 + 命中数 + `data-e2e="rec-stage-{n}"` + `data-status`；D4/D5 RecPanel 每项 `rec-source-{source}` + `rec-stage-{index}` Tag（R-决策 8/9）。
- 无 LLM 凭证时阶段 11 skipped + 核心闭环照跑（故事验收"无 LLM 凭证时 AI 步骤跳过+告警"）。
- 后端新增 pytest 全绿；既有推荐/D7/capa 测试不退化；前端 vitest + `tsc --noEmit` + `npm run build` 绿；`make check` 绿。
- `docs/` 同步：本 spec + `PROGRESS.md` 缺口清单 P0-2/P0-3/P1-5~10 勾选。

## 参考

- 故事：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（12 阶段编排见「AI 推荐流程编排」节）
- Spec A：`docs/superpowers/specs/2026-07-03-us-e2e-01-spec-a-d4-verification-adoption-design.md`（`stage_index` 预留决策 1、采纳映射表）
- 现有代码：`backend/app/services/{hybrid_recommendation_pipeline,fusion_engine,llm_fusion_layer,recommendation_sources,recommendation_types}.py`、`backend/app/services/lessons_learned/service.py`、`backend/app/api/capa.py:342/425`、`frontend/src/components/capa/{D4,D5,D7}RecPanel.tsx`
- 数据层：`backend/app/services/{spc_service,iqc_inspection_service,supplier_quality_service,mes_service,mes_connector}.py`、`backend/app/models/{iqc_inspection,mes,capa}.py`
- 相关 ADR：ADR-0001（UUID v4）、ADR-0003（factory_id 行级隔离）、ADR-0004（手写 AuditLog）、ADR-0013（手写 Alembic）
- 依赖：embedding worker 扩 `capa_lesson` 实体（P0 follow-up 同类）；`product_lines.product_type_code` 已确认存在（`product_line.py:20`）；SPC 复用 `match_fmea_for_alarm`（`spc_service.py:379`）
- 后续 spec：Spec C（故事级 E2E `capa-story-closed-loop.spec.ts`，依赖本 spec 的 `rec-stage-*` / `rec-source-*` 选择器与 `stage_index` 留痕）
