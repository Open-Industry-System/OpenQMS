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

| 决策 | 选择 | 理由 |
|---|---|---|
| 01.2 BLOCKED 语义 | 严格 BLOCKED | 故事契约 AI_REQUIRED=true 不可降级；改写 e2e 无凭证 D4/D5 步为 test.skip(BLOCKED)，非 AI 步照跑 |
| stage_runs 持久化落点 | 加列到 RecommendationCache（JSONB） | 与 suggestions 同行同生命周期，一次读出回放 DAG；迁移仅加一列 |
| method 枚举落地 | Text + CHECK + Pydantic Literal | 向后兼容现有 NULL 数据；避免 PG enum 加值需 ALTER TYPE 及脏数据迁移失败 |
| retry_count 落点 | 加在 capa_eightd（每 8D 一个计数器） | 语义对齐「选根因的回退尝试次数」而非「单根因验证次数」；D4 前缀避免与未来 D5/D7 计数器混淆 |

---

## 3. 架构与切片划分

两个独立切片，一份 spec，两轮 TDD plan。切片间无代码依赖（A 改 orchestrator/cache，B 改 verification/8D model），可并行，但建议 A 先（解锁 BLOCKED 语义给后续 01.7 门禁复用）。

```
切片 A（01.2 收尾）—— BLOCKED 语义 + stage_runs 持久化
  后端:
    RecommendationOrchestrator.run()         ← 顶部判 BLOCKED（pc is None）
    LLMFusionLayer.enrich()                   ← pc is None 分支保留 catch-all（不动）
    HybridRecommendationPipeline.recommend()  ← 透传 BLOCKED 信号（不写 cache/审计）
    api/capa.py D4/D5 endpoint                ← pc is None → HTTP 422 + blocked body
    models/recommendation_cache.py            ← 加 stage_runs JSONB 列
    services/recommendation_service._cache_result ← 写入 stage_runs
    schemas/recommendation_stage.py           ← StageRunSchema.status 扩展加 "blocked"（复用既有 schema，加枚举值）
  迁移: ALTER TABLE recommendation_cache ADD COLUMN stage_runs JSONB
  前端: D4/D5RecPanel ← 收到 422/blocked 时渲染 BLOCKED 提示（非崩溃）
  e2e: capa-story-closed-loop.spec.ts ← 无凭证 D4/D5 步改 test.skip(BLOCKED)

切片 B（01.3 收尾）—— method 枚举 + retry_count
  后端:
    models/capa.py CapaRootCauseVerification  ← method 保留 Text，DB 加 CHECK
    models/capa.py CAPAEightD                  ← 加 d4_retry_count int default 0
    schemas/capa_verification.py               ← method 改 Literal
    services/capa_verification_service         ← 验证失败递增 retry_count + 审计
    services/capa_service.advance_capa        ← D4→D5 时若 retry_count>=3 附 warning
  迁移: ALTER TABLE capa_root_cause_verification ADD CHECK;
        ALTER TABLE capa_eightd ADD COLUMN d4_retry_count
  前端: D4RecPanel 验证卡 ← method 改 Select 下拉
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

`RecommendationResult` 加 `blocked: bool = False` 字段。`_blocked_stages()` 构造 12 行：stage 1 `done`（上下文已知）、stage 11 `status="blocked"` reason="未配置 LLM 凭证"、stages 2-10 与 12 `skipped` reason="LLM 未配置，编排未执行"。

**StageRunSchema.status 枚举扩展（必须）**：现有 `Literal["pending","running","done","skipped","error"]` 不含 "blocked"。BLOCKED 是结果级裁决，现有枚举无法诚实表达——`skipped` 在故事语义里是「可接受降级」（LLM 阶段 skipped 反而判 FAILED），`error` 是 FAILED 不是 BLOCKED。故新增 `"blocked"` 值到 `StageRunSchema.status`（及 `StageRun` dataclass 的 status 字段，若为 Literal）。这是纯加法扩展（新枚举值），低风险，与 epic README 的 BLOCKED 裁决一致。

**为什么不动 LLMFusionLayer.enrich 的 pc=None 分支**：那行是 catch-all 防「provider 配置了但运行时失败」的真实降级，与「从未配置」语义不同。BLOCKED 只在 pc is None（从未配置）时触发，由 orchestrator 顶部单点判定，enrich 永远拿到非 None pc。

#### 4.1.2 HybridRecommendationPipeline.recommend — 透传，不写 cache/审计

```python
result = await self.orchestrator.run(...)
if not result.blocked:                          # BLOCKED 时跳过审计与 cache
    await self._maybe_write_llm_audit(...)
return result
```

BLOCKED 不写 `llm_recommend` 审计（无 LLM 调用，符合既有「attempted=0 不审计」规则），不写 RecommendationCache（无有效结果）。

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

#### 4.1.4 RecommendationCache — 加 stage_runs 列

```python
stage_runs: Mapped[list] = mapped_column(JSONB, nullable=True)  # 12 行 StageRun 序列化
```

`_cache_result` 写入时序列化 12 个 StageRun。读取侧（未来回溯）一次读出 suggestions + stage_runs 即可回放 DAG。BLOCKED 时不写 cache（无有效结果可回溯）。

#### 4.1.5 前端 D4RecPanel / D5RecPanel

Axios 拦截器对 422 + `detail.blocked===true` 不走「清 token→/login」逻辑，而是把 blocked body 投递给面板。面板渲染：「⚠️ AI 推荐不可用——未配置 LLM 凭证。联系管理员配置 /admin/ai-config」+ stage 11 显示 blocked 红色节点。

#### 4.1.6 e2e capa-story-closed-loop.spec.ts 改写

- D4/D5 推荐断言分两支：`hasLLMCreds()` → 断 200 + stage 11 done；无凭证 → 断 422 + `detail.blocked===true` + `test.skip`（AI 闭环 BLOCKED，记入报告）。
- D1→D3 / D7 审批 / D8 闘环等非 AI 步保持照跑（核心非 AI 闭环不受 LLM 影响）。

### 4.2 切片 B 组件

#### 4.2.1 CapaRootCauseVerification.method — 枚举化

列保留 Text（向后兼容），DB 加 CHECK：

```sql
ALTER TABLE capa_root_cause_verification
  ADD CONSTRAINT chk_verification_method
  CHECK (method IS NULL OR method IN ('measurement','observation','reproduction'));
```

Pydantic：

```python
class VerificationCreate(BaseModel):
    root_cause_text: str
    method: Literal["measurement","observation","reproduction"] | None = None
    ...
class VerificationUpdate(BaseModel):
    method: Literal["measurement","observation","reproduction"] | None = None
    ...
```

`VerificationResponse.method` 同步改 `Literal | None`。旧 NULL 值兼容；非 NULL 非枚举值由 CHECK 拒（迁移前若有脏数据需先清洗）。

#### 4.2.2 CAPAEightD.d4_retry_count — 回退计数器

```python
d4_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

**递增时机**：`capa_verification_service` 在创建/更新验证记录且 `is_verified=False`（验证不通过）时 `capa.d4_retry_count += 1`。语义 = 「选了根因去验证但未通过」的累计尝试次数。

注意区分：`is_verified=True`（通过）不递增——通过即确认根因，不是回退。`is_verified=False`（不通过→回退选另一条）才递增。

#### 4.2.3 advance_capa — D4→D5 阈值提示

```python
# D4_ROOT_CAUSE → D5_CORRECTION 闸口既有（验至少 1 条 is_verified=True），追加：
warning = None
if capa.d4_retry_count >= D4_RETRY_THRESHOLD:  # = 3
    warning = "建议升级处理（D4 验证已回退 {} 次）".format(capa.d4_retry_count)
# advance 响应 body 附 warning（不阻断）
```

故事明确「超过阈值提示但不硬性阻断」——warning 进响应 body，前端 toast 展示，不抛错、不挡推进。

#### 4.2.4 审计对齐

| 当前 | 故事契约 | 改动 |
|---|---|---|
| `RC_VERIFY` | `D4_VERIFICATION_PASSED` / `D4_VERIFICATION_FAILED` | 按 is_verified 拆两事件名，含 retry_count |

故事 01.3 实现注记已列「审计命名对齐（RC_VERIFY→D4_VERIFICATION_*）」为后续切片——本切片一并做掉。`D7_NODE_CONFIRMED`→`D7_NODE_ACTION_CREATED`、`TRANSITION`→`D8_APPROVAL_PENDING` 等其余命名对齐**不在本切片**（属 01.3 审计对齐的其余项，避免范围蔓延，留给后续或 verify skill 走查时补）。

#### 4.2.5 前端 D4RecPanel 验证卡

method 字段从文本 Input 改 Select：

```tsx
<Select data-e2e="verification-method" placeholder="选择验证方法">
  <Option value="measurement">测量验证</Option>
  <Option value="observation">观察验证</Option>
  <Option value="reproduction">复现实验</Option>
</Select>
```

i18n 补 `verification.method.*` 三项（zh-CN + en-US）。

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
  → pipeline: _maybe_write_llm_audit + _cache_result(stage_runs 落库)
  → endpoint: 200 + {stages, items}
  → D4RecPanel: 渲染 12 阶段 DAG + 推荐列表 + provenance
```

### 5.3 切片 A：stage_runs 持久化（正常路径）

```
orchestrator.run → RecommendationResult(stages=[12 StageRun], items=[...])
  → pipeline._maybe_write_llm_audit (既有)
  → recommendation_service._cache_result(...):
      RecommendationCache(
          suggestions=[候选序列化],
          stage_runs=[StageRunSchema(...).model_dump() for s in result.stages],  # 新
          llm_available=True,
          ...
      )
  → db.commit()
```

回溯读取：`SELECT suggestions, stage_runs FROM recommendation_cache WHERE report_id=... AND trigger_type=...` → 一次读出候选 + DAG 执行过程。

### 5.4 切片 B：D4 验证子流程

```
工程师选候选根因 → 创建验证记录（method=measurement, result="...", 证据）
  → POST /api/capa/{id}/verifications {method, result, is_verified:false}
  → capa_verification_service.create:
      验证记录入库
      if is_verified is False:                    # 验证不通过
          capa.d4_retry_count += 1
          写审计 D4_VERIFICATION_FAILED {retry_count, method, root_cause_text}
      db.commit()
      return verification

验证通过（is_verified=true）→ 确认根因
  → PATCH 验证记录 is_verified=true
  → service: 写审计 D4_VERIFICATION_PASSED {method, root_cause_text}  # 不递增
  → db.commit()

推进 D4→D5
  → advance_capa(D4_ROOT_CAUSE → D5_CORRECTION):
      闸口: 至少 1 条 is_verified=True  (既有)
      if capa.d4_retry_count >= 3:
          warning = "建议升级处理（D4 验证已回退 N 次）"
      写 TRANSITION 审计 (既有)
      db.commit()
      return {新状态, warning?}   # warning 进 body，不阻断
  → frontend: 收到 warning → toast 展示，不阻断推进
```

### 5.5 关键数据流边界

- **BLOCKED 不写 cache / 不写 llm 审计**：无 LLM 调用，符合既有「attempted=0 不审计」规则。
- **retry_count 只在 is_verified=False 递增**：通过不递增（通过=确认，非回退）。
- **warning 不阻断**：故事明确「超阈值提示但不硬性阻断」，warning 进 body 不抛错。
- **审计 retry_count 字段**：`D4_VERIFICATION_FAILED` 的 metadata 含 retry_count，供回溯。
- **BLOCKED 与验证闸口不耦合**：BLOCKED 只影响 D4 推荐请求，不影响 D4 验证记录创建（验证是本地操作，不依赖 LLM）。即「无 LLM 凭证时，工程师仍可手动选根因 + 创建验证记录 + 推进 D4→D5」——符合故事 BLOCKED 语义只锁 AI 步、不锁非 AI 步。
- **retry_count warning 不影响推荐请求**：推荐与验证是独立请求，retry_count 只在 advance_capa 时读。

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
- 处理：`_cache_result` 写 stage_runs 时 try/except，失败则 stage_runs=NULL 但 suggestions 正常写（cache 主体不因 stage_runs 序列化失败而整体丢）。
- 取舍：suggestions（候选）比 stage_runs（DAG 回溯）更重要，前者优先保证。

**4. 既有缓存读取（未来回溯路径）**
- 触发：回溯读 cache 时 stage_runs 为 NULL（本切片前的旧 cache 行）。
- 处理：读取侧判 `stage_runs is NULL` → 回溯面板显示「DAG 执行记录不可用（旧缓存）」，不报错。

### 6.2 切片 B 错误处理

**1. method 非法值 — 双层拦截**
- API 层：Pydantic Literal 拒非枚举值 → 422 校验错误（既有 FastAPI 行为，不特判）。
- DB 层：CHECK 约束兜底（防绕过 API 直写）→ IntegrityError → service 层转 ValueError → API 层 HTTPException(400)。
- 既有自由文本脏数据（迁移前）：CHECK 添加前若存在非枚举非 NULL 值会迁移失败——核验现有 method 基本为 NULL，迁移安全；迁移脚本加前置断言 `SELECT count(*) WHERE method IS NOT NULL AND method NOT IN (...)` 非零则中止并报脏数据。

**2. retry_count 并发递增 — FOR UPDATE 串行化**
- 触发：两个并发验证失败请求同时递增同一 8D 的 d4_retry_count。
- 处理：递增前 `SELECT ... FOR UPDATE` 锁 capa 行（既有 advance_capa 已用此模式），保证计数不丢。
- 取舍：验证是低频操作，行锁开销可接受。

**3. 阈值提示 — 非错误，不阻断**
- 触发：`d4_retry_count >= 3` 时 advance。
- 处理：warning 进响应 body，不抛错、不阻断推进。前端 toast 展示。
- 边界：阈值=3（故事「如 3 次」），不硬上限（故事「不设硬性上限」）。

**4. 迁移兼容 — 既有 d4_retry_count 无值**
- 既有 8D 行：迁移加列 `default 0`，旧行自动填 0。
- 既有 verification 行：method 既有 NULL/自由文本，CHECK 放行 NULL，非枚举值由前置断言拦。

---

## 7. 测试策略

### 7.1 切片 A 测试

**后端单测（pytest）**

`test_recommendation_orchestrator.py`（扩展）：
- `test_run_blocked_when_pc_none` — pc=None → `result.blocked=True`、items=[]、stages 12 行结构正确（stage 1 done、stage 11 blocked、其余 skipped）。
- `test_blocked_stages_carry_reason` — stage 11 的 status/reason 字段断言。
- `test_run_normal_when_pc_present`（回归）— pc 非 None → blocked=False，既有 12 阶段编排不破。

`test_hybrid_recommendation_pipeline.py`（扩展）：
- `test_blocked_skips_audit_and_cache` — blocked=True 时 `_maybe_write_llm_audit` 不调用、`_cache_result` 不调用（mock 验证调用计数）。
- `test_normal_writes_audit_and_cache`（回归）— blocked=False 时两者照调。

`test_cache_result.py`（新增/扩展）：
- `test_cache_result_persists_stage_runs` — 正常路径 cache 行 stage_runs 非 NULL、含 12 行、字段齐全。
- `test_cache_result_stage_runs_serialize_failure_degrades` — stage_runs 序列化抛错时 stage_runs=NULL 但 suggestions 正常写。

`test_capa_api_d4_d5.py`（扩展）：
- `test_d4_endpoint_returns_422_blocked_when_no_llm` — pc=None → 422 + `detail.blocked===true` + stages 非空。
- `test_d5_endpoint_returns_422_blocked_when_no_llm` — 同上对 D5。
- `test_d4_endpoint_normal_200`（回归）— pc 非 None → 200 + stages + items。

**前端单测（vitest）**
- `D4RecPanel` / `D5RecPanel`：收到 422+blocked → 渲染 BLOCKED 提示（testid `rec-blocked-banner`）+ stage 11 红色节点；不崩。

**e2e（Playwright）— 改写 capa-story-closed-loop.spec.ts**
- 无凭证分支：D4/D5 推荐 → 断 422 + `detail.blocked===true` → `test.skip(true, "BLOCKED: no LLM creds")`，记入报告。
- 有凭证分支：断 200 + stage 11 done。
- 非 AI 步（D1-D3 / D7 审批 / D8 闭环）两分支都照跑——验证核心非 AI 闭环不受 LLM 影响。
- `ai-credentials.guard.spec.ts` 不动（既有 smoke 守卫）。

### 7.2 切片 B 测试

**后端单测（pytest）**

`test_capa_verification_method_enum.py`（新增）：
- `test_create_verification_with_valid_method` — method=measurement/observation/reproduction 三值各创建成功。
- `test_create_verification_with_invalid_method_rejected` — method="guess" → 422（Pydantic 拒）。
- `test_db_check_rejects_invalid_method` — 绕过 API 直写非法值 → IntegrityError（CHECK 生效）。
- `test_create_verification_method_null_allowed` — method=None 创建成功（既有行为不破）。

`test_d4_retry_count.py`（新增）：
- `test_verification_failed_increments_retry_count` — 创建 is_verified=False → capa.d4_retry_count +=1。
- `test_verification_passed_does_not_increment` — is_verified=True → 不递增。
- `test_concurrent_verification_failures_serialize` — 两个并发失败请求 → retry_count 精确+2（FOR UPDATE 生效，不丢）。
- `test_advance_d4_to_d5_warns_at_threshold` — d4_retry_count=3 → advance 响应 body 含 warning。
- `test_advance_d4_to_d5_no_warning_below_threshold`（回归）— d4_retry_count<3 → 无 warning。
- `test_advance_not_blocked_by_warning` — 阈值超限仍推进成功（warning 不阻断）。

`test_d4_verification_audit.py`（新增）：
- `test_failed_verification_writes_audit_with_retry_count` — `D4_VERIFICATION_FAILED` 审计 metadata 含 retry_count/method。
- `test_passed_verification_writes_audit` — `D4_VERIFICATION_PASSED` 审计。

**迁移测试**
- `test_migration_method_check_constraint` — upgrade 后 CHECK 存在；downgrade 移除。
- `test_migration_d4_retry_count_column` — upgrade 后列存在 default 0；downgrade 移除。
- `test_migration_aborts_on_dirty_method_data` — 前置断言：有非枚举非 NULL method 值时迁移中止。

**前端单测（vitest）**
- `D4RecPanel` 验证卡：method 渲染 Select（testid `verification-method`）+ 三选项；非法值不出现在选项。

**e2e（Playwright）— 扩展 capa-story-closed-loop.spec.ts**
- D4 验证子流程：选根因 → 选 method（枚举 Select）→ 填 result → 上传证据 → 结论不通过 → 断 retry_count 递增（回读）→ 重选另一条 → 验证通过 → 推进 D4→D5。
- 推进时若 retry_count>=3 → 断 toast 含「建议升级处理」。

### 7.3 测试边界

- **不测**：LLM 推荐内容质量（epic 范围外）、阈值升级处理流程动作（本切片只提示）、PG enum（已选 CHECK）。
- **回归保护**：既有 orchestrator 12 阶段编排测试、既有验证闸口测试、既有 advance_capa 测试全跑——确保 BLOCKED 与 retry_count 不破现有绿。

### 7.4 验收命令

- 后端：`cd backend && pytest tests/ -x --tb=short`（含新测 + 回归）
- 前端：`cd frontend && npm run build`（tsc --noEmit + vite build）+ vitest 新测
- e2e：`make e2e`（手动，不接入 CI；无凭证分支 skip-with-warning）
- 整体：`make check`

---

## 8. 验收契约对齐

本设计交付后，gap analysis 中 01.2 / 01.3 的以下 gap 将闭合：

| Gap | 来源 | 本设计闭合方式 |
|---|---|---|
| 01.2 LLM 未配置静默降级 | gap analysis 01.2 行 + 意外发现 #1 | §4.1.1 orchestrator 顶部判 BLOCKED + §4.1.3 API 422 |
| 01.2 stage_runs 未持久化 | gap analysis 01.2 行 + 意外发现 #1 | §4.1.4 RecommendationCache 加 stage_runs JSONB |
| 01.3 method 非枚举 | gap analysis 01.3 行 + 意外发现 #9 | §4.2.1 Text + CHECK + Literal |
| 01.3 无回退计数器 | gap analysis 01.3 行 | §4.2.2 d4_retry_count + §4.2.3 阈值提示 |
| 01.3 审计命名 RC_VERIFY→D4_VERIFICATION_* | 故事 01.3 实现注记 #145 | §4.2.4 本切片一并做掉 |

仍未闭合（不在本设计范围，留后续）：
- 01.3 FMEA 反查覆盖 Prevention 节点 + 反查审计（依赖 01.4 切片）
- 01.3 `D7_NODE_CONFIRMED`→`D7_NODE_ACTION_CREATED` 等其余审计命名对齐
- 01.1 / 01.4 / 01.5 / 01.6 / 01.7 / 01.8 / 01.9 / 01.10 子故事

---

## 9. 不在本设计范围

- 01.2 前端面板可视化与 AP/S/O/D 展示的最终核验（Spec B 已交付，gap analysis 标 ⚠️ 待核——属走查验收，非新开发，由 verify skill 走查确认）。
- 01.3 状态机细化切片（已交付，本设计在其基础上收尾 method + retry_count）。
- 其余 8 个子故事（01.1/01.4-01.10）的实现。
- verify skill 重定义为编排器 + 10 子 skill（配套任务，非本设计）。
- LLM 推荐准确率评测（epic 范围外）。
- 8D 团队负责人作为独立 RBAC 角色（epic 范围外，当前用 manager 账号代表）。
