# US-E2E-01 P0 收尾设计 — 01.2 BLOCKED 语义 + stage_runs 持久化 + 01.3 method 枚举 + retry_count

**日期**: 2026-07-09
**状态**: 设计稿（待评审）
**关联故事**: `docs/user-stories/US-E2E-01-capa-8d-closed-loop/`（epic v8.1）
  - 子故事 01.2 `US-E2E-01.2-recommendation-12-sources.md`（定稿 v1）
  - 子故事 01.3 `US-E2E-01.3-d4-verification-d7-node-action.md`（定稿 v1，状态机切片已交付）
**依据 gap analysis**: `docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`
**范围**: P0 收尾的两个硬 gap——01.2 的 LLM BLOCKED 语义 + stage_runs 持久化；01.3 的 method 枚举 + retry_count 回退计数器。不含 01.4/01.7 等其余子故事。

---

## 1. 背景与问题

### 1.1 01.2 的两个硬 gap

gap analysis 指出 01.2「12 源推荐」编排器已就绪（Spec B 已交付 12 阶段 + 6 新源 + DAG 面板 + provenance + AP/S/O/D 展示），但有两个硬 gap：

**Gap A1 — LLM 未配置时静默降级（应判 BLOCKED）**

故事 01.2 + epic README 明确 `AI_REQUIRED=true`，验收契约写「阻塞条件（BLOCKED）：无 LLM 凭证」「LLM 不可降级：无 LLM 凭证 → BLOCKED」。

但当前代码 `backend/app/services/llm_fusion_layer.py:35-36`：

```python
if self.pc is None:
    return LLMOutcome(candidates=list(candidates) if candidates else [], attempted=0)
```

pc=None 时返回 `attempted=0`，编排继续 → stage 11 实际为 skipped/done → 返回 rule-only 结果。这是**静默降级**，与故事契约的 BLOCKED 相反。

且现有 e2e 故事 spec `frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts:23` 明确写：

> 无 LLM 凭证时：stage 11（LLM 融合）断言 skipped，核心闭环照跑；有凭证时断言 done。

这与故事契约直接矛盾——现有 e2e 把「无凭证静默降级」当通过，故事要求「无凭证 BLOCKED」。

**Gap A2 — stage_runs 未结构化持久化**

故事 01.2 验收契约写「落库实体：`recommendation_cache`（含 stage_runs[]、candidates[]）」「数据落库：推荐结果（含每条的来源 provenance、AP/S/O/D、命中阶段）持久化，可回溯」。

但 `backend/app/models/recommendation_cache.py` 的 `RecommendationCache` 模型只有 `suggestions`（候选 JSONB）+ `llm_available`（bool），**无 `stage_runs` 字段**。API 返回 runtime stages（`capa.py:446`/`544`），但未持久化——DAG 执行过程请求结束即丢失，无法事后回溯。

### 1.2 01.3 的两个硬 gap

01.3 状态机细化切片已交付（D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING + 驳回 + node-action.status + edge 权限 + 冻结守卫）。仍待后续切片（故事 01.3 实现注记第 142-145 行）：

**Gap B1 — method 非枚举**

故事 01.3 验收契约写 `verification.method∈{measurement,observation,reproduction}`。但 `backend/app/models/capa.py:51` `CapaRootCauseVerification.method` 是 `Text` 自由文本，`schemas/capa_verification.py` 的 `VerificationCreate.method` 是 `str | None`，无枚举约束。

**Gap B2 — 无回退计数器**

故事 01.3 写「回退循环计数器记录尝试次数（供审计，不设硬性上限，但超过阈值时提示"建议升级处理"）」「尝试次数超过阈值（如 3 次）时提示"建议升级处理"，但不硬性阻断」。验收契约关键字段含 `retry_count`，审计事件含 `D4_VERIFICATION_FAILED`（含 retry_count）。

当前无 retry_count 字段、无回退循环计数、无阈值提示。

---

## 2. 设计决策（已与用户确认）

### 2.1 原决策（brainstorm 阶段）

| 决策 | 选择 | 理由 |
|---|---|---|
| 01.2 BLOCKED 语义 | 严格 BLOCKED | 故事契约 AI_REQUIRED=true 不可降级；无凭证 D4/D5 推荐步走独立 guarded spec（见 §2.2），非 AI 步照跑 |
| stage_runs 持久化落点 | 加列到 RecommendationCache（JSONB） | report_id 键 + 既有 uq_cache_capa 部分索引；迁移仅加一列 |
| method 枚举落地 | Text + CHECK + Pydantic Literal + CheckConstraint 进 metadata | 向后兼容现有 NULL 数据；CHECK 同时写 Alembic 与模型 __table_args__（Base.metadata.create_all 测试路径一致） |
| retry_count 落点 | 加在 capa_eightd（每 8D 一个计数器） | 语义对齐「选根因的回退尝试次数」；D4 前缀避免与未来 D5/D7 计数器混淆 |

### 2.2 评审修订决策（Codex 对抗评审后，4 P0 + 3 P1 全部接受）

| 评审项 | 修订决策 | 理由 |
|---|---|---|
| P0-1 CAPA 缓存写入口 | **新增 CAPA 专属缓存写入路径**（write-only），不复用 FMEA 的 `_cache_result` | CAPA D4/D5 路径当前**完全无缓存写入**；既有 `recommendation_service._cache_result` 是 FMEA 键（fmea_id/FMEADocument/`fmea_id IS NOT NULL` 冲突键），不适用 CAPA。新增 `_cache_capa_result` 写 RecommendationCache（report_id 键 + uq_cache_capa upsert）。**只写不读**：D4/D5 端点仍每次重算，缓存行供审计/verify skill 回溯（故事要求「可回溯」，不要求性能缓存）；避免陈旧缓存风险与额外读路径测试 |
| P0-2 warning 响应契约 | **新增 `CAPAAdvanceResponse { capa: CAPAResponse, warning: str \| None }`** | `advance_capa() -> CAPAEightD` + API `response_model=CAPAResponse` 会过滤额外字段；局部 warning 变量进不了响应。新模型局部化到 advance 端点，不污染 CAPAResponse；同步前端类型与调用方 |
| P0-3 is_verified=False 不可靠 | **新增 `conclusion` 枚举字段（pending/passed/failed）**，retry_count 仅在 conclusion 跃迁到 failed 时递增 | `is_verified` 默认 False，草稿与未填结论的记录也读 False → 误计回退。conclusion=pending 时不计；显式提交 conclusion=failed 才计一次；true→false 转换计一次。既有 D4→D5 闸口仍读 `is_verified`（= conclusion=="passed" 派生同步），不破坏既有逻辑 |
| P0-4 test.skip 终止整测 | **拆为两个 spec**：`capa-story-ai-recommend.spec.ts`（AI D4/D5 推荐，无凭证 skip 整测）+ `capa-story-closed-loop.spec.ts`（非 AI D1-D3/D7/D8 闭环，始终照跑） | `test.skip()` 终止当前测试，与「非 AI 步照跑」矛盾。拆分后 AI 步的 BLOCKED 与非 AI 闭环解耦；与既有 `capa-ai-draft.spec.ts` + `ai-credentials.guard.spec.ts` 模式一致 |
| P1 reason 字段 | **复用 `summary`，不新增 reason** | StageRunSchema 既有 summary（skipped 阶段已用 summary 承载原因，如「D5 无 FMEA cause...跳过」）；新增 reason 属 YAGNI。stage 11 blocked 的原因写进 summary |
| P1 retry_count 默认值 | 迁移 `server_default='0'` NOT NULL + 模型 `server_default="0"` | `mapped_column(default=0)` 仅 ORM 侧默认；旧行与绕过 ORM 的 INSERT 需 DB 层默认 |
| P1 CHECK 进 metadata | `CapaRootCauseVerification.__table_args__` 加 `CheckConstraint`，与 Alembic 双声明 | 既有 RecommendationCache.__table_args__ 注释证明 Base.metadata.create_all 测试路径需模型内声明约束；否则测试库与生产库约束不一致 |

---

## 3. 架构与切片划分

两个独立切片，一份 spec，两轮 TDD plan。切片间无代码依赖（A 改 orchestrator/cache，B 改 verification/8D model），可并行，但建议 A 先（解锁 BLOCKED 语义给后续 01.7 门禁复用）。

```
切片 A（01.2 收尾）—— BLOCKED 语义 + stage_runs 持久化
  后端:
    RecommendationOrchestrator.run()         ← 顶部判 BLOCKED（pc is None）
    LLMFusionLayer.enrich()                   ← pc is None 分支保留 catch-all（不动）
    HybridRecommendationPipeline.recommend()  ← 透传 BLOCKED 信号（不写 cache/审计）
    HybridRecommendationPipeline._cache_capa_result ← 【新增】CAPA 专属缓存写入（write-only，不复用 FMEA _cache_result）
    api/capa.py D4/D5 endpoint                ← pc is None → HTTP 422 + blocked body；正常路径写缓存
    models/recommendation_cache.py            ← 加 stage_runs JSONB 列
    schemas/recommendation_stage.py           ← StageRunSchema.status 扩展加 "blocked"（复用 summary 承载原因，不加 reason）
  迁移: ALTER TABLE recommendation_cache ADD COLUMN stage_runs JSONB
  前端: D4/D5RecPanel ← 收到 422/blocked 时渲染 BLOCKED 提示（非崩溃）
  e2e: 拆为 capa-story-ai-recommend.spec.ts（无凭证 skip 整测）+ capa-story-closed-loop.spec.ts（非 AI 闭环始终照跑）

切片 B（01.3 收尾）—— method 枚举 + retry_count
  后端:
    models/capa.py CapaRootCauseVerification  ← method 保留 Text；加 conclusion 枚举列；__table_args__ 加 CheckConstraint(method)
    models/capa.py CAPAEightD                  ← 加 d4_retry_count int NOT NULL server_default 0
    schemas/capa_verification.py               ← method 改 Literal；加 conclusion Literal；is_verified 派生自 conclusion
    schemas/capa.py                             ← 新增 CAPAAdvanceResponse { capa, warning }
    services/capa_verification_service         ← conclusion→failed 跃迁递增 retry_count + 审计
    services/capa_service.advance_capa        ← 返回 (capa, warning)；D4→D5 时若 retry_count>=3 附 warning
    api/capa.py advance endpoint              ← response_model=CAPAAdvanceResponse
  迁移: ALTER TABLE capa_root_cause_verification ADD COLUMN conclusion VARCHAR(20) NOT NULL DEFAULT 'pending'
        + ADD CONSTRAINT chk_verification_method + 同步 __table_args__；
        ALTER TABLE capa_eightd ADD COLUMN d4_retry_count INTEGER NOT NULL DEFAULT 0
  前端: D4RecPanel 验证卡 ← method 改 Select + conclusion 选择；advance 调用方适配 CAPAAdvanceResponse
```

---

## 4. 组件细节

### 4.1 切片 A 组件

#### 4.1.1 RecommendationOrchestrator.run — 顶部 BLOCKED 判定

```python
async def run(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
    # 顶部 BLOCKED 判定（AI_REQUIRED=true，故事契约不可降级）
    if self.pc is None:
        blocked_stages = self._blocked_stages(context)  # 12 行结构化
        return RecommendationResult(items=[], stages=blocked_stages, blocked=True)
    # 正常编排（既有逻辑不变）
    ...
```

`RecommendationResult` 加 `blocked: bool = False` 字段。`_blocked_stages()` 构造 12 行：stage 1 `done`（上下文已知）、stage 11 `status="blocked"` summary="未配置 LLM 凭证"、stages 2-10 与 12 `skipped` summary="LLM 未配置，编排未执行"。

**StageRunSchema.status 枚举扩展（必须）**：现有 `Literal["pending","running","done","skipped","error"]` 不含 "blocked"。BLOCKED 是结果级裁决，现有枚举无法诚实表达——`skipped` 在故事语义里是「可接受降级」（LLM 阶段 skipped 反而判 FAILED），`error` 是 FAILED 不是 BLOCKED。故新增 `"blocked"` 值到 `StageRunSchema.status`（及 `StageRun` dataclass 的 status 字段，若为 Literal）。这是纯加法扩展（新枚举值），低风险，与 epic README 的 BLOCKED 裁决一致。

**不新增 reason 字段**：StageRunSchema 既有 `summary`，既有 skipped 阶段已用 summary 承载原因（如「D5 无 FMEA cause...跳过控制扩展」）。BLOCKED 的原因同样写进 summary，复用既有字段（YAGNI）。

**为什么不动 LLMFusionLayer.enrich 的 pc=None 分支**：那行是 catch-all 防「provider 配置了但运行时失败」的真实降级，与「从未配置」语义不同。BLOCKED 只在 pc is None（从未配置）时触发，由 orchestrator 顶部单点判定，enrich 永远拿到非 None pc。

#### 4.1.2 HybridRecommendationPipeline.recommend — 透传 BLOCKED，正常路径写缓存

```python
result = await self.orchestrator.run(...)
if not result.blocked:                          # BLOCKED 时跳过审计与 cache 写入
    await self._maybe_write_llm_audit(...)
    await self._cache_capa_result(report_id, context, result)  # 【新增】CAPA 缓存写入（write-only）
return result
```

BLOCKED 不写 `llm_recommend` 审计（无 LLM 调用，符合既有「attempted=0 不审计」规则），不写 RecommendationCache（无有效结果可回溯）。正常路径写缓存供审计/verify skill 回溯（故事「可回溯」）。

#### 4.1.3 API 层 — D4/D5 endpoint

```python
result = await pipeline.recommend(context, ...)
await db.commit()
if result.blocked:
    raise HTTPException(
        status_code=422,
        detail={"blocked": True, "reason": "LLM credentials not configured",
                "stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages]},
    )
return {"stages": [...], "items": [...]}
```

422（非 503）：503=服务故障，422=业务前置不满足（无 LLM 凭证是配置前置，不是服务挂）。body 带 stages 让前端面板渲染 BLOCKED 状态而非空白。

#### 4.1.4 RecommendationCache — 加 stage_runs 列 + 新增 CAPA 专属写入路径

模型加列：

```python
stage_runs: Mapped[list] = mapped_column(JSONB, nullable=True)  # 12 行 StageRun 序列化
```

**【新增】`_cache_capa_result`（CAPA 专属缓存写入，write-only，不复用 FMEA 的 `_cache_result`）**

现状核验：CAPA D4/D5 路径当前**完全无缓存写入**——`HybridRecommendationPipeline`/`capa.py` 从不调用 `_cache_result`/`RecommendationCache(`。既有 `recommendation_service._cache_result` 是 FMEA 键（`fmea_id`/`FMEADocument`/冲突键 `fmea_id IS NOT NULL`），不适用 CAPA。但 `RecommendationCache` 已有 `report_id` FK + `uq_cache_capa` 部分索引（`report_id, trigger_type, context_hash WHERE report_id IS NOT NULL`），CAPA 缓存键基础设施已就绪但未接线。本设计补齐这一接线。

```python
async def _cache_capa_result(self, report_id, context, result: RecommendationResult) -> None:
    context_hash = hashlib.sha256(
        json.dumps({
            "d2": context.capa_data.get("d2_description"),
            "d3": context.capa_data.get("d3_interim"),
            "d4": context.capa_data.get("d4_root_cause"),
            "fmea_ref_id": str(context.capa_data.get("fmea_ref_id")) if context.capa_data.get("fmea_ref_id") else None,
            "fmea_node_id": context.capa_data.get("fmea_node_id"),
            "product_line_code": context.capa_data.get("product_line_code"),
        }, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    trigger_type = context.stage  # "d4" / "d5"
    suggestions = self._serialize_capa_suggestions(context.stage, result.items)
    stage_runs = [StageRunSchema(**s.__dict__).model_dump() for s in result.stages]
    source = "hybrid"  # 编排融合后的聚合来源
    stmt = (
        pg_insert(RecommendationCache)
        .values(
            report_id=report_id,
            trigger_type=trigger_type,
            context_hash=context_hash,
            product_line_code=context.capa_data.get("product_line_code") or "",
            factory_id=context.factory_id,
            doc_type="capa",
            suggestions=suggestions,
            stage_runs=stage_runs,
            source=source,
            llm_available=(self.pc is not None),
            expires_at=func.now() + text("INTERVAL '24 hours'"),
        )
        .on_conflict_do_update(
            index_elements=["report_id", "trigger_type", "context_hash"],
            index_where=text("report_id IS NOT NULL"),
            set_={
                "suggestions": suggestions,
                "stage_runs": stage_runs,
                "source": source,
                "llm_available": (self.pc is not None),
                "created_at": func.now(),
                "expires_at": func.now() + text("INTERVAL '24 hours'"),
            },
        )
    )
    await self.db.execute(stmt)
```

**关键点**：
- 缓存键 = `report_id + trigger_type(d4/d5) + context_hash`，复用既有 `uq_cache_capa` 部分索引做 upsert。
- `context_hash` 捕获所有影响推荐的输入（d2/d3/d4/fmea_ref_id/fmea_node_id/product_line_code）——本设计为 write-only，不读缓存，故 context_hash 仅作去重键与回溯定位，无陈旧缓存风险（陈旧风险只在读缓存时才存在）。
- `doc_type="capa"` 区分 FMEA（`doc_type="fmea"`）行，便于回溯查询过滤。
- `_serialize_capa_suggestions(stage, items)`：D4 → `[c.to_d4_schema().model_dump() for c in items]`；D5 → `{"existing_controls": [...], "general_suggestions": [...]}` 按 D5 响应结构序列化（trigger_type 区分两种结构，回溯时按 trigger_type 解析）。
- **write-only**：D4/D5 端点不查缓存，仍每次重算编排；缓存行仅供审计/verify skill 回溯（故事要求「可回溯」，不要求性能缓存）。回溯查询：`SELECT suggestions, stage_runs, llm_available FROM recommendation_cache WHERE report_id=... AND trigger_type='d4' ORDER BY created_at DESC LIMIT 1`。
- BLOCKED 时不写 cache（pipeline 在 `if not result.blocked` 内调用）。
- stage_runs 序列化失败时防御性降级（见 §6.1-3）：try/except 包裹 stage_runs 写入，失败则 stage_runs=NULL 但 suggestions 正常写。

#### 4.1.5 前端 D4RecPanel / D5RecPanel

Axios 拦截器对 422 + `detail.blocked===true` 不走「清 token→/login」逻辑，而是把 blocked body 投递给面板。面板渲染：「⚠️ AI 推荐不可用——未配置 LLM 凭证。联系管理员配置 /admin/ai-config」+ stage 11 显示 blocked 红色节点。

#### 4.1.6 e2e 拆分为两个 spec（评审修订）

现有 `capa-story-closed-loop.spec.ts` 单测用 `test.skip()` 处理无凭证，会终止整测——与「非 AI 步照跑」矛盾。修订拆为：

- **`capa-story-ai-recommend.spec.ts`（新增）**：AI D4/D5 推荐 + 12 阶段 DAG 断言。`hasLLMCreds()` → 断 200 + stage 11 done + provenance；无凭证 → `test.skip(true, "BLOCKED: no LLM creds")`（整测 skip，记入报告）。此 spec 整体是 AI 条件步，skip 整测合理。
- **`capa-story-closed-loop.spec.ts`（改写）**：非 AI 闭环（D1-D3 / D7 审批 / D8_APPROVAL_PENDING→D8_CLOSURE / viewer 只读）始终照跑，不再含 D4/D5 AI 推荐断言。无凭证也全绿——核心非 AI 闭环不受 LLM 影响。
- `ai-credentials.guard.spec.ts` 不动（既有 smoke 守卫）。
- D4 验证子流程（method/conclusion/retry_count）属切片 B，放在 `capa-story-closed-loop.spec.ts`（非 AI 步，因验证是本地操作不依赖 LLM）。

### 4.2 切片 B 组件

#### 4.2.1 CapaRootCauseVerification — method 枚举化 + conclusion 枚举 + CHECK 进 metadata

**method**：列保留 Text（向后兼容），DB 加 CHECK + 模型 `__table_args__` 同步声明 CheckConstraint（评审修订：Base.metadata.create_all 测试路径需模型内约束，否则测试库与生产库不一致，同既有 RecommendationCache.__table_args__ 模式）：

```python
# models/capa.py
from sqlalchemy import CheckConstraint

class CapaRootCauseVerification(Base):
    __tablename__ = "capa_root_cause_verification"
    __table_args__ = (
        CheckConstraint(
            "method IS NULL OR method IN ('measurement','observation','reproduction')",
            name="chk_verification_method",
        ),
    )
    # ... 既有字段 ...
    method: Mapped[str | None] = mapped_column(Text)  # 类型不变，约束在 __table_args__ + Alembic 双声明
    # 【新增】验证结论枚举（评审修订 P0-3：is_verified 默认 False 无法区分草稿/失败）
    conclusion: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
```

```sql
-- Alembic 迁移（与 __table_args__ 双声明，保证测试库 create_all 与迁移后生产库一致）
ALTER TABLE capa_root_cause_verification
  ADD COLUMN conclusion VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE capa_root_cause_verification
  ADD CONSTRAINT chk_verification_method
  CHECK (method IS NULL OR method IN ('measurement','observation','reproduction'));
```

**conclusion 枚举**（`pending | passed | failed`）：评审修订 P0-3——`is_verified` 默认 False，草稿与未填结论的记录都读 False，无法可靠表示「一次验证失败」。新增 conclusion：
- `pending`：新建记录默认（草稿，工程师尚未给结论）——**不计 retry_count**。
- `passed`：验证通过——同步 `is_verified=True`，不计 retry_count。
- `failed`：验证不通过——同步 `is_verified=False`，**仅 conclusion 跃迁到 failed 时计 retry_count 一次**。

`is_verified` 列保留（既有 D4→D5 闸口读它），由 conclusion 派生同步：conclusion=passed → is_verified=True；其余 → is_verified=False。这样既有闸口逻辑不破坏。

Pydantic：

```python
class VerificationCreate(BaseModel):
    root_cause_text: str
    method: Literal["measurement","observation","reproduction"] | None = None
    conclusion: Literal["pending","passed","failed"] = "pending"  # 显式提交结论，默认 pending 不误计
    ...
class VerificationUpdate(BaseModel):
    method: Literal["measurement","observation","reproduction"] | None = None
    conclusion: Literal["pending","passed","failed"] | None = None
    ...
```

`VerificationResponse` 加 `conclusion: Literal["pending","passed","failed"]`，`method` 改 `Literal | None`。旧 NULL method 值兼容；非 NULL 非枚举值由 CHECK 拒（迁移前若有脏数据需先清洗，迁移脚本加前置断言，见 §6.2-1）。

#### 4.2.2 CAPAEightD.d4_retry_count — 回退计数器（server_default + conclusion 驱动递增）

```python
# models/capa.py
d4_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
```

```sql
-- Alembic 迁移：server_default 保证旧行与绕过 ORM 的 INSERT 填 0
ALTER TABLE capa_eightd ADD COLUMN d4_retry_count INTEGER NOT NULL DEFAULT 0;
```

评审修订 P1：`mapped_column(default=0)` 仅 ORM 侧默认，旧行与绕过 ORM 的 INSERT 不受保护；迁移 `DEFAULT 0` NOT NULL + 模型 `server_default="0"` 双保险。

**递增时机（conclusion 驱动，评审修订 P0-3）**：`capa_verification_service` 在 conclusion **跃迁到 `failed`** 时 `capa.d4_retry_count += 1`（FOR UPDATE 锁 capa 行，见 §6.2-2）：
- 新建记录 conclusion=pending → **不递增**（草稿不计回退）。
- 显式提交 conclusion=failed（pending→failed）→ 递增 1。
- 已 failed 记录改 method/result 但 conclusion 仍 failed（无跃迁）→ **不递增**（避免编辑重复计数）。
- conclusion true→false 不存在（conclusion 是三态，passed→failed 跃迁计 1，符合「回退选另一条」语义）。

语义 = 「选了根因去验证但结论不通过」的累计尝试次数，对齐故事「回退循环计数器记录尝试次数」。conclusion=passed 不递增（通过=确认根因，非回退）。

#### 4.2.3 advance_capa — D4→D5 阈值提示 + 新响应契约（评审修订 P0-2）

评审修订 P0-2：`advance_capa() -> CAPAEightD` + API `response_model=CAPAResponse` 会过滤额外字段，局部 warning 变量进不了响应。修订采用新响应模型：

```python
# schemas/capa.py（新增）
class CAPAAdvanceResponse(BaseModel):
    capa: CAPAResponse
    warning: str | None = None
    model_config = ConfigDict(from_attributes=True)
```

```python
# services/capa_service.advance_capa
async def advance_capa(...) -> tuple[CAPAEightD, str | None]:
    # ... 既有 D4→D5 闸口（验至少 1 条 is_verified=True，不变）...
    warning = None
    if capa.d4_retry_count >= D4_RETRY_THRESHOLD:  # = 3
        warning = "建议升级处理（D4 验证已回退 {} 次）".format(capa.d4_retry_count)
    # ... 写 TRANSITION 审计（既有）...
    return capa, warning
```

```python
# api/capa.py advance endpoint（response_model 改）
@router.post("/{report_id}/advance", response_model=CAPAAdvanceResponse)
async def advance_capa(...):
    capa, warning = await capa_service.advance_capa(...)
    await db.commit()
    return CAPAAdvanceResponse(capa=CAPAResponse.model_validate(capa), warning=warning)
```

故事明确「超过阈值提示但不硬性阻断」——warning 进响应 body，前端 toast 展示，不抛错、不挡推进。前端 advance 调用方适配新 `{ capa, warning }` 结构（取 `capa` 更新状态，`warning` 展示 toast）。其他 advance 调用方（若前端有多个）同步适配。

#### 4.2.4 审计对齐

| 当前 | 故事契约 | 改动 |
|---|---|---|
| `RC_VERIFY` | `D4_VERIFICATION_PASSED` / `D4_VERIFICATION_FAILED` | 按 conclusion 拆两事件名，含 retry_count |

评审修订：审计事件按 **conclusion** 而非 is_verified 触发——`conclusion=passed` 写 `D4_VERIFICATION_PASSED`（含 method/root_cause_text）；`conclusion=failed` 写 `D4_VERIFICATION_FAILED`（含 retry_count/method/root_cause_text）；`conclusion=pending` 不写验证结论审计（草稿不计）。retry_count 字段进 `D4_VERIFICATION_FAILED` 的 metadata 供回溯。

故事 01.3 实现注记已列「审计命名对齐（RC_VERIFY→D4_VERIFICATION_*）」为后续切片——本切片一并做掉。`D7_NODE_CONFIRMED`→`D7_NODE_ACTION_CREATED`、`TRANSITION`→`D8_APPROVAL_PENDING` 等其余命名对齐**不在本切片**（属 01.3 审计对齐的其余项，避免范围蔓延，留给后续或 verify skill 走查时补）。

#### 4.2.5 前端 D4RecPanel 验证卡

method 字段从文本 Input 改 Select；新增 conclusion 选择（通过/不通过，pending 为草稿态默认不展示为选项，由「保存草稿」vs「提交结论」动作区分）：

```tsx
<Select data-e2e="verification-method" placeholder="选择验证方法">
  <Option value="measurement">测量验证</Option>
  <Option value="observation">观察验证</Option>
  <Option value="reproduction">复现实验</Option>
</Select>
{/* 提交结论按钮：通过/不通过 → conclusion=passed/failed；保存草稿 → conclusion=pending */}
<Button data-e2e="verify-pass" onClick={() => submit({ conclusion: "passed" })}>验证通过</Button>
<Button data-e2e="verify-fail" onClick={() => submit({ conclusion: "failed" })}>验证不通过</Button>
```

i18n 补 `verification.method.*` 三项 + `verification.conclusion.*` 三项（zh-CN + en-US）。advance 调用方适配 `CAPAAdvanceResponse { capa, warning }`——warning 非 null 时 toast 展示「建议升级处理」。

#### 4.2.6 不在本切片

- 阈值升级处理流程（故事「后续细化」）——本切片只提示，不实现升级动作。
- `D7_NODE_CONFIRMED`→`D7_NODE_ACTION_CREATED` 等其余审计命名对齐（避免范围蔓延）。
- method 的 PG enum（已选 CHECK，不动）。

---

## 5. 数据流

### 5.1 切片 A：D4 推荐请求（无 LLM 凭证）

```
工程师点【AI 多源推荐】
  → frontend D4RecPanel → GET /api/capa/{id}/d4-fmea-recommendations
  → capa.py endpoint:
      pc = build_client(db)  → ProviderNotConfiguredError → pc=None
      pipeline = HybridRecommendationPipeline(db, None, embedding_provider)
      result = pipeline.recommend(context)
        → orchestrator.run(context):
            if self.pc is None:                      # BLOCKED 单点
                return RecommendationResult(items=[], stages=_blocked_stages(), blocked=True)
        → pipeline: result.blocked=True → 跳过 _maybe_write_llm_audit + 不写 cache
      if result.blocked:
        raise HTTPException(422, detail={blocked, reason, stages})
  → frontend axios 拦截器: 422 + detail.blocked → 不清 token，投递给面板
  → D4RecPanel: 渲染 BLOCKED 提示 + DAG stage 11 红色 blocked 节点
```

### 5.2 切片 A：D4 推荐请求（有 LLM 凭证）

```
  → orchestrator.run → 12 阶段全执行 → stage 11 done
  → pipeline: _maybe_write_llm_audit + _cache_capa_result(stage_runs + suggestions 落库 RecommendationCache，report_id 键)
  → endpoint: 200 + {stages, items}
  → D4RecPanel: 渲染 12 阶段 DAG + 推荐列表 + provenance
```

### 5.3 切片 A：stage_runs 持久化（正常路径，write-only）

```
orchestrator.run → RecommendationResult(stages=[12 StageRun], items=[...])
  → pipeline._maybe_write_llm_audit (既有)
  → pipeline._cache_capa_result(report_id, context, result):  # 【新增】CAPA 专属写入
      计算 context_hash (d2/d3/d4/fmea_ref_id/fmea_node_id/product_line_code)
      suggestions = _serialize_capa_suggestions(stage, items)  # D4 list / D5 {existing_controls,general_suggestions}
      stage_runs = [StageRunSchema(...).model_dump() for s in result.stages]
      pg_insert(RecommendationCache).values(report_id, trigger_type, context_hash,
          doc_type="capa", suggestions, stage_runs, source="hybrid",
          llm_available=True, expires_at=now+24h)
        .on_conflict_do_update(index=uq_cache_capa, set_={suggestions, stage_runs, ...})
  → db.commit()
```

回溯读取（审计/verify skill，非应用路径）：`SELECT suggestions, stage_runs, llm_available FROM recommendation_cache WHERE report_id=... AND trigger_type='d4' ORDER BY created_at DESC LIMIT 1` → 一次读出候选 + DAG 执行过程。应用路径不读缓存（write-only，D4/D5 端点仍每次重算）。

### 5.4 切片 B：D4 验证子流程（conclusion 驱动）

```
工程师选候选根因 → 创建验证记录（method=measurement, result="...", 证据）
  → POST /api/capa/{id}/verifications {method, result, conclusion:"pending"}   # 默认 pending，草稿不计回退
  → capa_verification_service.create:
      验证记录入库（conclusion=pending, is_verified=False）
      # pending 不递增 retry_count，不写验证结论审计
      db.commit()
      return verification

工程师提交结论（不通过）
  → PATCH {conclusion:"failed"}   # pending→failed 跃迁
  → service:
      SELECT capa FOR UPDATE                        # 锁行防并发丢计数
      capa.d4_retry_count += 1                      # 仅跃迁到 failed 递增 1
      is_verified 同步为 False
      写审计 D4_VERIFICATION_FAILED {retry_count, method, root_cause_text}
      db.commit()

工程师提交结论（通过）
  → PATCH {conclusion:"passed"}   # pending→passed 跃迁
  → service:
      is_verified 同步为 True                        # 既有 D4→D5 闸口读 is_verified 不破
      写审计 D4_VERIFICATION_PASSED {method, root_cause_text}   # 不递增
      db.commit()

推进 D4→D5
  → advance_capa(D4_ROOT_CAUSE → D5_CORRECTION):
      闸口: 至少 1 条 is_verified=True  (既有，conclusion=passed 派生)
      if capa.d4_retry_count >= 3:
          warning = "建议升级处理（D4 验证已回退 N 次）"
      写 TRANSITION 审计 (既有)
      db.commit()
      return (capa, warning)   # 新契约 CAPAAdvanceResponse {capa, warning}，不阻断
  → frontend: 收到 warning → toast 展示，不阻断推进；取 capa 更新状态
```

### 5.5 关键数据流边界

- **BLOCKED 不写 cache / 不写 llm 审计**：无 LLM 调用，符合既有「attempted=0 不审计」规则。
- **retry_count 仅在 conclusion 跃迁到 failed 递增**（评审修订 P0-3）：草稿（pending）不计；编辑 method/result 但 conclusion 不变不重复计；passed 不计。
- **warning 不阻断**：故事明确「超阈值提示但不硬性阻断」，warning 进 CAPAAdvanceResponse body 不抛错。
- **审计 retry_count 字段**：`D4_VERIFICATION_FAILED` 的 metadata 含 retry_count，供回溯。
- **BLOCKED 与验证闸口不耦合**：BLOCKED 只影响 D4 推荐请求，不影响 D4 验证记录创建（验证是本地操作，不依赖 LLM）。即「无 LLM 凭证时，工程师仍可手动选根因 + 创建验证记录（pending）+ 提交结论 + 推进 D4→D5」——符合故事 BLOCKED 语义只锁 AI 步、不锁非 AI 步。
- **retry_count warning 不影响推荐请求**：推荐与验证是独立请求，retry_count 只在 advance_capa 时读。
- **is_verified 由 conclusion 派生同步**：既有 D4→D5 闸口读 is_verified 不破坏；conclusion 是真相源，is_verified 是派生投影。

---

## 6. 错误处理

### 6.1 切片 A 错误处理

**1. BLOCKED（无 LLM 凭证）— 预期路径，非错误**
- 触发：`build_client` 抛 `ProviderNotConfiguredError` → pc=None → orchestrator 顶部判 BLOCKED。
- 处理：HTTP 422 + `detail.blocked=true` + stages。不写审计、不写 cache、不记 error 日志（这是配置前置，不是故障）。
- 前端：422 + `detail.blocked` 走专用分支（不清 token、不报 500），渲染 BLOCKED 提示。

**2. LLM 调用失败（provider 配置了但运行时失败）— 既有逻辑不动**
- 触发：`enrich` 内 `complete_json` 超时/异常。
- 处理：`enrich` catch-all → `LLMOutcome(attempted>0, succeeded=0, failed=attempted)` → stage 11 `status="error"` → DAG 显红 + `_maybe_write_llm_audit` 写 `llm_failed` 审计。
- 这是 FAILED 不是 BLOCKED：provider 配置了但调用失败 = 编排执行了但 LLM 阶段 error，符合故事「LLM 阶段 error → FAILED」。本切片不改这条路径。

**3. stage_runs 序列化失败 — 防御性降级**
- 触发：`StageRun` 含不可序列化字段（理论上不会，但兜底）。
- 处理：`_cache_capa_result` 写 stage_runs 时 try/except，失败则 stage_runs=NULL 但 suggestions 正常写（cache 主体不因 stage_runs 序列化失败而整体丢）。
- 取舍：suggestions（候选）比 stage_runs（DAG 回溯）更重要，前者优先保证。

**4. 既有缓存读取（未来回溯路径，write-only 故无应用读取）**
- 触发：审计/verify skill 回溯读 cache 时 stage_runs 为 NULL（本切片前的旧 cache 行，或序列化降级）。
- 处理：读取侧判 `stage_runs is NULL` → 显示「DAG 执行记录不可用（旧缓存/降级）」，不报错。本设计 write-only，应用路径不读缓存，故此场景仅限审计/回溯工具。

### 6.2 切片 B 错误处理

**1. method 非法值 — 双层拦截（API + DB CHECK，metadata 双声明）**
- API 层：Pydantic Literal 拒非枚举值 → 422 校验错误（既有 FastAPI 行为，不特判）。
- DB 层：CHECK 约束兜底（防绕过 API 直写）→ IntegrityError → service 层转 ValueError → API 层 HTTPException(400)。CHECK 同时在 Alembic 与 `CapaRootCauseVerification.__table_args__` 声明（评审修订 P1），保证 Base.metadata.create_all 测试库与迁移后生产库一致。
- 既有自由文本脏数据（迁移前）：CHECK 添加前若存在非枚举非 NULL 值会迁移失败——核验现有 method 基本为 NULL，迁移安全；迁移脚本加前置断言 `SELECT count(*) WHERE method IS NOT NULL AND method NOT IN ('measurement','observation','reproduction')` 非零则中止并报脏数据。

**2. retry_count 并发递增 — FOR UPDATE 串行化（conclusion 跃迁触发）**
- 触发：两个并发 conclusion=failed 跃迁同时递增同一 8D 的 d4_retry_count。
- 处理：递增前 `SELECT ... FOR UPDATE` 锁 capa 行（既有 advance_capa 已用此模式），保证计数不丢。
- 取舍：验证是低频操作，行锁开销可接受。

**3. conclusion 非法值 — Literal + 可选 DB CHECK**
- API 层：Pydantic Literal["pending","passed","failed"] 拒非法值 → 422。
- conclusion 列 NOT NULL server_default 'pending'，既有 verification 行迁移后自动填 pending（评审修订 P0-3：旧行 conclusion=pending 不误计回退）。

**4. 阈值提示 — 非错误，不阻断**
- 触发：`d4_retry_count >= 3` 时 advance。
- 处理：warning 进 `CAPAAdvanceResponse` body，不抛错、不阻断推进。前端 toast 展示。
- 边界：阈值=3（故事「如 3 次」），不硬上限（故事「不设硬性上限」）。

**5. 迁移兼容 — 既有行默认值**
- 既有 8D 行：迁移加列 `d4_retry_count INTEGER NOT NULL DEFAULT 0`，旧行自动填 0（评审修订 P1：server_default 双保险）。
- 既有 verification 行：迁移加列 `conclusion VARCHAR(20) NOT NULL DEFAULT 'pending'`，旧行填 pending（不计回退）；method 既有 NULL/自由文本，CHECK 放行 NULL，非枚举值由前置断言拦。

---

## 7. 测试策略

### 7.1 切片 A 测试

**后端单测（pytest）**

`test_recommendation_orchestrator.py`（扩展）：
- `test_run_blocked_when_pc_none` — pc=None → `result.blocked=True`、items=[]、stages 12 行结构正确（stage 1 done、stage 11 blocked、其余 skipped）。
- `test_blocked_stages_carry_summary` — stage 11 的 status=blocked + summary 含「未配置 LLM 凭证」断言。
- `test_run_normal_when_pc_present`（回归）— pc 非 None → blocked=False，既有 12 阶段编排不破。

`test_hybrid_recommendation_pipeline.py`（扩展）：
- `test_blocked_skips_audit_and_cache` — blocked=True 时 `_maybe_write_llm_audit` 不调用、`_cache_capa_result` 不调用（mock 验证调用计数）。
- `test_normal_writes_audit_and_cache`（回归）— blocked=False 时两者照调。

`test_cache_capa_result.py`（新增）：
- `test_cache_capa_result_persists_stage_runs` — 正常路径 cache 行 stage_runs 非 NULL、含 12 行、字段齐全；report_id 键 + doc_type="capa"。
- `test_cache_capa_result_upsert_on_conflict` — 同 report_id+trigger_type+context_hash 二次写 upsert 更新而非插入。
- `test_cache_capa_result_d4_d5_suggestions_shape` — D4 suggestions=list、D5 suggestions={existing_controls,general_suggestions} 结构断言。
- `test_cache_capa_result_stage_runs_serialize_failure_degrades` — stage_runs 序列化抛错时 stage_runs=NULL 但 suggestions 正常写。
- `test_blocked_does_not_write_cache` — blocked=True 时 RecommendationCache 无新行。
- `test_cache_capa_result_uses_uq_cache_capa_index` — 验证冲突键走 report_id IS NOT NULL 部分索引（不与 FMEA fmea_id 键冲突）。

`test_capa_api_d4_d5.py`（扩展）：
- `test_d4_endpoint_returns_422_blocked_when_no_llm` — pc=None → 422 + `detail.blocked===true` + stages 非空。
- `test_d5_endpoint_returns_422_blocked_when_no_llm` — 同上对 D5。
- `test_d4_endpoint_normal_200`（回归）— pc 非 None → 200 + stages + items。

**前端单测（vitest）**
- `D4RecPanel` / `D5RecPanel`：收到 422+blocked → 渲染 BLOCKED 提示（testid `rec-blocked-banner`）+ stage 11 红色节点；不崩。

**e2e（Playwright）— 拆分两 spec（评审修订 P0-4）**
- `capa-story-ai-recommend.spec.ts`（新增）：`hasLLMCreds()` → 断 200 + stage 11 done + provenance；无凭证 → `test.skip(true, "BLOCKED: no LLM creds")`（整测 skip 记入报告）。
- `capa-story-closed-loop.spec.ts`（改写）：非 AI 闭环（D1-D3 / D7 审批 / D8_APPROVAL_PENDING→D8_CLOSURE / viewer 只读）始终照跑，无凭证也全绿。
- `ai-credentials.guard.spec.ts` 不动（既有 smoke 守卫）。

### 7.2 切片 B 测试

**后端单测（pytest）**

`test_capa_verification_method_enum.py`（新增）：
- `test_create_verification_with_valid_method` — method=measurement/observation/reproduction 三值各创建成功。
- `test_create_verification_with_invalid_method_rejected` — method="guess" → 422（Pydantic 拒）。
- `test_db_check_rejects_invalid_method` — 绕过 API 直写非法值 → IntegrityError（CHECK 生效，含 metadata.create_all 路径）。
- `test_create_verification_method_null_allowed` — method=None 创建成功（既有行为不破）。
- `test_metadata_create_all_has_check_constraint` — Base.metadata.create_all 建库后 CHECK 存在（评审修订 P1：验证 __table_args__ 双声明）。

`test_capa_verification_conclusion.py`（新增，评审修订 P0-3）：
- `test_create_verification_default_pending` — 新建 conclusion=pending，is_verified=False，**不递增 retry_count**。
- `test_conclusion_failed_increments_retry_count` — pending→failed 跃迁 → retry_count +=1，is_verified 同步 False。
- `test_conclusion_passed_does_not_increment` — pending→passed 跃迁 → retry_count 不变，is_verified 同步 True。
- `test_conclusion_failed_no_transition_no_double_count` — 已 failed 记录改 method/result（conclusion 不变）→ retry_count 不再递增（防重复计数）。
- `test_concurrent_failed_transitions_serialize` — 两个并发 pending→failed 跃迁 → retry_count 精确+2（FOR UPDATE 生效）。

`test_d4_retry_count.py`（新增）：
- `test_advance_d4_to_d5_warns_at_threshold` — d4_retry_count=3 → advance 响应 `CAPAAdvanceResponse.warning` 含「建议升级处理」。
- `test_advance_d4_to_d5_no_warning_below_threshold`（回归）— d4_retry_count<3 → warning=None。
- `test_advance_not_blocked_by_warning` — 阈值超限仍推进成功（warning 不阻断）。
- `test_advance_response_contract` — advance 端点返回 `{capa, warning}` 结构，response_model=CAPAAdvanceResponse（评审修订 P0-2）。

`test_d4_verification_audit.py`（新增）：
- `test_failed_verification_writes_audit_with_retry_count` — `D4_VERIFICATION_FAILED` 审计 metadata 含 retry_count/method/root_cause_text。
- `test_passed_verification_writes_audit` — `D4_VERIFICATION_PASSED` 审计含 method/root_cause_text。
- `test_pending_does_not_write_conclusion_audit` — conclusion=pending 不写验证结论审计。

**迁移测试**
- `test_migration_method_check_constraint` — upgrade 后 CHECK 存在；downgrade 移除。
- `test_migration_d4_retry_count_column` — upgrade 后列存在 NOT NULL DEFAULT 0；downgrade 移除。
- `test_migration_conclusion_column` — upgrade 后 conclusion 列存在 NOT NULL DEFAULT 'pending'，旧行填 pending；downgrade 移除。
- `test_migration_aborts_on_dirty_method_data` — 前置断言：有非枚举非 NULL method 值时迁移中止。

**前端单测（vitest）**
- `D4RecPanel` 验证卡：method 渲染 Select（testid `verification-method`）+ 三选项；conclusion 按钮（testid `verify-pass`/`verify-fail`）；非法值不出现在选项。
- advance 调用方：收到 `CAPAAdvanceResponse { capa, warning }` → warning 非 null 时 toast 展示。

**e2e（Playwright）— 扩展 capa-story-closed-loop.spec.ts（非 AI，始终照跑）**
- D4 验证子流程：选根因 → 选 method（枚举 Select）→ 填 result → 上传证据 → 提交结论不通过（testid `verify-fail`）→ 断 retry_count 递增（回读）→ 重选另一条 → 提交结论通过（testid `verify-pass`）→ 推进 D4→D5。
- 推进时若 retry_count>=3 → 断 toast 含「建议升级处理」。
- 此流程不依赖 LLM，无凭证也照跑（属非 AI 步）。

### 7.3 测试边界

- **不测**：LLM 推荐内容质量（epic 范围外）、阈值升级处理流程动作（本切片只提示）、PG enum（已选 CHECK）、CAPA 缓存读取（write-only，无应用读路径）。
- **回归保护**：既有 orchestrator 12 阶段编排测试、既有验证闸口测试（读 is_verified，conclusion 派生同步）、既有 advance_capa 测试全跑——确保 BLOCKED 与 retry_count 不破现有绿。

### 7.4 验收命令

- 后端：`cd backend && pytest tests/ -x --tb=short`（含新测 + 回归）
- 前端：`cd frontend && npm run build`（tsc --noEmit + vite build）+ vitest 新测
- e2e：`make e2e`（手动，不接入 CI；`capa-story-ai-recommend.spec.ts` 无凭证 skip，`capa-story-closed-loop.spec.ts` 始终照跑）
- 整体：`make check`

---

## 8. 验收契约对齐

本设计交付后，gap analysis 中 01.2 / 01.3 的以下 gap 将闭合：

| Gap | 来源 | 本设计闭合方式 |
|---|---|---|
| 01.2 LLM 未配置静默降级 | gap analysis 01.2 行 + 意外发现 #1 | §4.1.1 orchestrator 顶部判 BLOCKED + §4.1.3 API 422 |
| 01.2 stage_runs 未持久化 | gap analysis 01.2 行 + 意外发现 #1 | §4.1.4 RecommendationCache 加 stage_runs JSONB + §4.1.2 新增 `_cache_capa_result` CAPA 写入路径 |
| 01.3 method 非枚举 | gap analysis 01.3 行 + 意外发现 #9 | §4.2.1 Text + CHECK + Literal + CheckConstraint 进 metadata |
| 01.3 无回退计数器 | gap analysis 01.3 行 | §4.2.2 d4_retry_count（server_default）+ §4.2.1 conclusion 枚举驱动递增 + §4.2.3 阈值提示 |
| 01.3 审计命名 RC_VERIFY→D4_VERIFICATION_* | 故事 01.3 实现注记 #145 | §4.2.4 本切片一并做掉 |

仍未闭合（不在本设计范围，留后续）：
- 01.3 FMEA 反查覆盖 Prevention 节点 + 反查审计（依赖 01.4 切片）
- 01.3 `D7_NODE_CONFIRMED`→`D7_NODE_ACTION_CREATED` 等其余审计命名对齐
- 01.1 / 01.4 / 01.5 / 01.6 / 01.7 / 01.8 / 01.9 / 01.10 子故事

---

## 9. 不在本设计范围

- 01.2 前端面板可视化与 AP/S/O/D 展示的最终核验（Spec B 已交付，gap analysis 标 ⚠️ 待核——属走查验收，非新开发，由 verify skill 走查确认）。
- 01.3 状态机细化切片（已交付，本设计在其基础上收尾 method + retry_count）。
- CAPA 推荐缓存读取路径（本设计 write-only；性能缓存/陈旧缓存处理留后续，若 D4/D5 延迟成问题再评估）。
- conclusion 的 PG enum 化（本设计用 String(20) + Literal + 可选 CHECK，不引入 PG enum）。
- 其余 8 个子故事（01.1/01.4-01.10）的实现。
- verify skill 重定义为编排器 + 10 子 skill（配套任务，非本设计）。
- LLM 推荐准确率评测（epic 范围外）。
- 8D 团队负责人作为独立 RBAC 角色（epic 范围外，当前用 manager 账号代表）。

---

## 10. 评审修订记录（Codex 对抗评审，2026-07-09）

初稿经 Codex 对抗评审（run 2，分支 diff 范围）+ 用户人工评审，识别 4 P0 + 3 P1，全部接受并修订：

| 评审项 | 级别 | 初稿缺陷 | 修订 |
|---|---|---|---|
| CAPA 缓存写入口 | P0 | 误称 `recommendation_service._cache_result` 写 stage_runs——该方法是 FMEA 键，CAPA 路径根本无缓存写入 | §4.1.2/§4.1.4 新增 `_cache_capa_result`（report_id 键 + uq_cache_capa upsert + write-only），不复用 FMEA 方法 |
| warning 响应契约 | P0 | 局部 warning 变量无法穿透 `response_model=CAPAResponse` 过滤 | §4.2.3 新增 `CAPAAdvanceResponse {capa, warning}`，advance service 返回 tuple，端点 response_model 改 |
| is_verified=False 不可靠 | P0 | is_verified 默认 False，草稿与未填结论都读 False，误计回退 | §4.2.1 新增 `conclusion` 枚举（pending/passed/failed），retry_count 仅 conclusion→failed 跃迁递增 |
| test.skip 终止整测 | P0 | `test.skip()` 终止当前测试，与「非 AI 步照跑」矛盾 | §4.1.6 拆为 `capa-story-ai-recommend.spec.ts`（AI，无凭证 skip 整测）+ `capa-story-closed-loop.spec.ts`（非 AI，始终照跑） |
| reason 字段缺失 | P1 | spec 用 reason 但 StageRunSchema 无此字段 | §4.1.1 复用 `summary` 承载原因（YAGNI），不新增 reason |
| retry_count 默认值 | P1 | `mapped_column(default=0)` 仅 ORM 侧 | §4.2.2 迁移 `DEFAULT 0 NOT NULL` + 模型 `server_default="0"` 双保险 |
| CHECK 进 metadata | P1 | CHECK 仅写 Alembic，Base.metadata.create_all 测试库不一致 | §4.2.1 `__table_args__` 加 CheckConstraint + Alembic 双声明 |

修订后所有评审项闭合；BLOCKED/FAILED 区分、Text+CHECK+Literal、行锁并发计数三项原判断保留。
