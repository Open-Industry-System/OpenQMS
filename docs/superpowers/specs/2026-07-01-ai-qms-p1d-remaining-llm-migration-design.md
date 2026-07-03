# P1-D — 剩余 LLM 消费者迁移到 Agent 基座 详细设计

- **日期**: 2026-07-01
- **作者**: Sam Wang (与 Claude 协作)
- **状态**: 已定稿，待写实现 plan
- **类型**: 期级实现 spec（P1-D）
- **上游**: [2026-06-29-ai-driven-qms-overview-design.md](./2026-06-29-ai-driven-qms-overview-design.md) · [2026-06-29-ai-qms-p0-agent-base-design.md](./2026-06-29-ai-qms-p0-agent-base-design.md) · [2026-06-30-ai-qms-p1b-quality-trend-migration-design.md](./2026-06-30-ai-qms-p1b-quality-trend-migration-design.md) · [2026-06-30-ai-qms-p1c-fmea-recommend-migration-design.md](./2026-06-30-ai-qms-p1c-fmea-recommend-migration-design.md)

## 1. 范围与目标

把 4 个仍在用旧 `LLMProvider.complete()` 的消费者迁移到 P0 基座 `provider_adapter.complete_json`；其中 3 个补基座审计 `audit.write_audit_raw`，CAPA draft 保留其现有 `AI_DRAFT` 审计只换 provider 调用。**薄迁移**：不包 agent tool、不走 harness、不建 agent_session；各消费者 hybrid 降级语义全部保留；旧 `LLMProvider` 类不删（`ai_config_service` 自检仍用）。

P1-D 是 P1（迁移现有 LLM 调用）的第三/第四个消费者批次，沿用 P1-B/P1-C 验证过的"LLM 调用统一到基座 provider_adapter + 审计统一到基座 audit（write_audit_raw）"迁移模板。本 spec 一次覆盖 4 个消费者（全包），按消费者拆 TDD 任务、风险递增顺序执行。

### 4 个消费者总览

| # | 模块 | 文件 | LLM 调用点 | 降级语义 | 现有审计 | P1-D 审计动作 |
|---|---|---|---|---|---|---|
| 1 | 8D D4/D5 全混合推荐 | `llm_fusion_layer.py`（经 `hybrid_recommendation_pipeline.py` 包装） | `enrich()` L33 + `_generate_fallback()` L137 | hybrid 静默降级（`if not self.llm: return candidates`） | 无 | 新增 `write_audit_raw`（LLMOutcome 三态） |
| 2 | RAG 语义搜索问答 | `search_service.py` | `ask()` L277 | hybrid 200 sources-only（`if not self.llm` 返回搜索结果 + "未配置 LLM"） | 无 | 新增 `write_audit_raw`（两态） |
| 3 | 管理评审报告生成 | `management_review_report_service.py` | `_enrich_with_llm()` L152 + `_generate_executive_summary()` L191 | hybrid fallback（`_fallback_executive_summary`） | CRUD `_write_audit`（`REPORT_GENERATE` 等，`db.add`） | 新增 `write_audit_raw`（LLM 拆出）；CRUD 审计保留 |
| 4 | 8D 报告 AI 草拟 D2-D8 | `capa_draft_service.py` | `generate_draft()` L408 | **纯 LLM 503**（`if llm_provider is None: 503`） | 自有 `AuditLog`（`AI_DRAFT`，独立 session 自提交，覆盖 success/fail/503） | **保留现有审计**，只换 provider 调用 |

> **范围修正说明**：PROGRESS.md 早先列的"剩余 4 个旧 LLM 调用点"含 SPC-FMEA 异常关联 / D7 预防复发 / 经验教训推送 —— 经 grep 核实这三者**均无 LLM 调用**（SPC-FMEA 与 D7 是纯规则/图匹配；`lessons_learned/service.py` 仅 `llm_available=False` 硬编码）。真实剩余消费者与 P1-C spec 排除清单一致（"管理评审 / 搜索 / CAPA draft / LLMFusionLayer"）。

### 与 P1-B/P1-C 的关键差异

- **P1-B**（质量趋势）：纯 LLM 特性，未配置 → 503 + 审计 `llm_not_configured`。
- **P1-C**（FMEA 推荐）：hybrid，未配置 → 静默规则降级 200、**不审计**；LLM 尝试两态 `success`/`llm_failed`。
- **P1-D**：4 个消费者降级语义**各自保留现状** —— 3 个 hybrid（D4/D5、RAG、管理评审，未配置不审计，P1-C 模式）+ 1 个纯 LLM（CAPA draft 503，P1-B 模式，且保留其自有审计不重写）。审计粒度：D4/D5 用结构化 `LLMOutcome` 三态（因 enrich 两阶段调 LLM —— fusion + fallback，单 bool 聚合有歧义）；其余两态。

## 2. 共享改动

### 2.0 `core/tenant.py` 复用（无新代码）

P1-C 已抽 `backend/app/core/tenant.py`（`tenant_schema(request) -> str`，取 `request.state.tenant.schema_name`，缺省 `"public"`）。P1-D 4 个路由直接 `from app.core.tenant import tenant_schema` 使用，**无新共享 util**。

### 2.1 provider 解析模式（4 消费者统一）

每个消费者在 LLM 调用前解析基座 provider client：
```python
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderNotConfiguredError
try:
    pc = await provider_adapter.build_client(db)
except ProviderNotConfiguredError:
    pc = None
```
`pc is None` 即"LLM 未配置"，等价于旧 `self.llm is None` / `llm_provider is None`。**解析时机**：在消费者进入 LLM 分支前；CAPA draft 在 503 判定前；D4/D5 在构造 `HybridRecommendationPipeline` 前（pipeline 需要把 `pc` 透传给 `LLMFusionLayer`）。

## 3. 各消费者改动

### 3.1 8D D4/D5 — `llm_fusion_layer.py` + `hybrid_recommendation_pipeline.py` + `api/capa.py`

**`api/capa.py`** D4 端点（L374 区域）+ D5 端点（L445 区域）：
- 删 `llm_provider = request.app.state.llm_provider`。
- `pc = await provider_adapter.build_client(db)`（`try/except ProviderNotConfiguredError → pc=None`）。
- `HybridRecommendationPipeline(db, pc, embedding_provider)`（构造签名 `llm_provider` → `pc`）。
- 末尾新增 `await db.commit()`（D4/D5 recommend 路由当前只读无 commit；审计行需落库，镜像 P1-C `fmea.py:325` 路由层统一提交）。
  > **GET + commit 语义说明**：D4/D5 是 `@router.get` 端点，加 `db.commit()` 使其在读推荐结果外**额外写一行审计**。这是有意行为（audit-on-AI-call 是 P1-D 目标），非 bug；会话内仅 SELECT + 审计 flush，无其他脏状态会被意外落库。REST 读纯度让位于 AI 调用可观测性。
- 传 `tenant_schema=tenant_schema(request)` 给 pipeline.recommend（见下）。

**`hybrid_recommendation_pipeline.py`**：
- `__init__(self, db, llm_provider, embedding_provider)` → `__init__(self, db, pc, embedding_provider)`；`self.llm = llm_provider` → `self.pc = pc`。
- `LLMFusionLayer(llm_provider)`（L49）→ `LLMFusionLayer(pc)`。
- `recommend()`（或 D4/D5 入口方法）签名新增 `tenant_schema: str` + `user: User` + `report_id: uuid.UUID` + `factory_id`（来自 `capa.factory_id`，NOT NULL）—— 用于写审计。
- 调 `self.llm_layer.enrich(fused, context)`（L87）后，据返回的 `LLMOutcome` 写一条 `write_audit_raw`（见审计语义）。

**`llm_fusion_layer.py`**：
- `__init__(self, llm_provider, timeout=2.0)` → `__init__(self, pc, timeout=2.0)`；`self.llm = llm_provider` → `self.pc = pc`。
- `if not self.llm`（L24）→ `if self.pc is None`（返回原候选，hybrid 静默降级，**不审计** —— 由 pipeline 据 `LLMOutcome.attempted==0` 判定）。
- `self.llm.complete(prompt, {})`（L33 阶段1 批量 fusion + L137 阶段2 `_generate_fallback`）→ `provider_adapter.complete_json(self.pc, prompt, {})`。
- **`enrich()` 返回值升级为结构化 `LLMOutcome`**（核心修正）：
  ```python
  @dataclass
  class LLMOutcome:
      candidates: list[RecommendationCandidate]   # 融合后候选（与原返回值等价）
      attempted: int    # 实际发起的 LLM 调用次数（阶段1 fusion + 阶段2 fallback，最多 2）
      succeeded: int    # 成功次数
      failed: int       # 失败次数（吞异常降级的）
  ```
  enrich 内部**两阶段**（非按候选循环）：阶段1 一次批量 fusion 调用（L32-35，给所有候选生成理由）；阶段2 仅当 `len(enriched) < 3` 时一次 `_generate_fallback`（L45-47）。每阶段一次 `complete_json` try 成功 `succeeded+=1`，except `failed+=1`。`self.pc is None` 时 `attempted=succeeded=failed=0`（直接返回原候选）。
- 调用方（pipeline L87）解包：`outcome = await self.llm_layer.enrich(fused, context); enriched = outcome.candidates`。

**审计语义（pipeline 写一条 `write_audit_raw`，三态；状态写 `new_values`）**：
- `attempted == 0`（`pc is None` 未配置）→ **不审计**（hybrid 静默降级，P1-C 模式）。
- `attempted > 0 and failed == 0` → `new_values={"status": "success", "trigger": "d4"/"d5", "attempted": N, "succeeded": N}`。
- `attempted > 0 and 0 < failed < attempted` → `new_values={"status": "partial", "attempted": N, "succeeded": N, "failed": N}`（fusion/fallback **两阶段中部分失败**，如 fusion 成功但 fallback 失败）。
- `attempted > 0 and failed == attempted` → `new_values={"status": "llm_failed", "attempted": N, "failed": N}`（两阶段全失败；候选降级返回）。
- `record_id = report_id`（`capa_eightd` 稳定主键，满足 P0 follow-up #2）；`correlation_id = uuid5(NAMESPACE_URL, f"d4_recommend:{report_id}:{context_hash}")`（D5 用 `d5_recommend` 前缀）；`factory_id = capa.factory_id`；`tenant_schema = tenant_schema(request)`；`action = "llm_recommend"`；`table_name = "capa_eightd"`；`changed_fields` 计数与 `new_values.status` 一致（计数放 `new_values`，`changed_fields` 留空或冗余写 —— 与 P1-C `audit_context` 写 `new_values` 对齐）。
- `write_audit_raw` 只 flush 不 commit；提交由 D4/D5 路由末尾 `await db.commit()` 统一完成。

> **为什么三态而非 P1-C 两态**：`enrich` 是两阶段 LLM 调用（fusion + fallback），每阶段独立 try/except 吞异常降级。单 bool 聚合会失真（"任一成功"掩盖部分失败 / "任一失败"过度上报）。结构化 `LLMOutcome` 保留按阶段粒度，`partial` 态 + 计数让审计忠实反映"fusion 成功但 fallback 失败"这类部分失败。P1-C 的 `recommend()` 是单次 LLM 调用，两态足够；D4/D5 最多 2 次，需三态。`write_audit_raw` 无 `status` 参数（`audit.py:11-16`），状态写 `new_values={"status": ...}`，与 P1-C 一致。

### 3.2 RAG 搜索 — `search_service.py` + `api/search.py`

**`search_service.py`**：
- `SearchService.__init__(self, db, llm_provider=None, embedding_provider=None)` → 去掉 `llm_provider`；`self.llm = llm_provider` 删除。
- `ask()` 内 `pc = await provider_adapter.build_client(db)`（`except → pc=None`）。
- L223 `llm_available=self.llm is not None` → `pc is not None`。
- L237 `if not self.llm` → `if pc is None`（返回 sources-only + "未配置 LLM"，200，**不审计** —— 未配置 hybrid 降级）。
- L269-281 try 块：`self.llm.complete(prompt=prompt, response_schema=rag_schema)` → `provider_adapter.complete_json(pc, prompt, rag_schema)`；包 `write_audit_raw` 两态：成功 → `new_values={"status": "success", "model": pc.model}`，`except` → `new_values={"status": "llm_failed", "error": str(e), "model": pc.model}`（**保留** L281 现状把错误塞进 answer 仍 200 返回）。`write_audit_raw` 无 `status` 参数（`audit.py:11-16`），状态写 `new_values`。
- `ask()` 签名新增 `user: User` + `tenant_schema: str`（路由传入，用于审计）。

**审计语义（`write_audit_raw` 两态，RAG 特殊主键）**：
- `pc is None`（未配置）→ 不审计。
- LLM 尝试 → `new_values={"status": "success"/"llm_failed", ...}` 两态。
- **`record_id`**：`audit_logs.record_id` 是 `nullable=False`（`models/audit.py:18`），**不能用 None**。RAG 跨实体无单一业务主键 —— 用**稳定哨兵 UUID** `record_id = uuid5(NAMESPACE_URL, f"rag_qa:{query_hash}")`，同查询→同 record_id→可聚合，且非随机（满足 P0 follow-up #2）。
- **`table_name = "rag_qa"`**（虚拟表名；`table_name` 是 `String(100)` 不要求真实表，标识"跨实体 QA 审计"类别）。
- **`factory_id = None`**（`audit_logs.factory_id` 可空，P0 迁移 `c0b6287b3d61:122` 未指定 `nullable=False`）。RAG 跨工厂搜索，强塞单工厂失真；`None` 诚实表达 + 靠 `correlation_id`/`changed_fields` 记 query 上下文。
  > **可见性风险（已接受）**：工厂级 manager 按 `factory_id` 过滤审计日志会漏掉 RAG 行。RAG 本就跨工厂，这是诚实归因；如未来需工厂级 RAG 审计归因，再拆。
- **`correlation_id = uuid5(NAMESPACE_URL, f"rag_qa:{query_hash}:{source_ids_hash}")`** —— `source_ids_hash` 必须 **sort + dedup** source entity_ids 后再哈希（P1-C `scope_hash` 模式），否则同查询因来源顺序不同算不同 correlation_id，聚合失效。
- `action = "llm_rag_qa"`；`user_id = user.user_id`。

**`api/search.py`** `ask_question`（L55）：
- `SearchService(db=db, llm_provider=llm_provider, embedding_provider=embedding_provider)`（L25，由依赖构造）→ 去 `llm_provider`。
- `service.ask(...)` 传 `scope.user` + `tenant_schema(request)`。
- 末尾新增 `await db.commit()`（`ask_question` 当前只读无 commit；审计行落库）。
- `semantic_search`（L28，纯向量+全文搜索无 LLM）**不动**。

### 3.3 管理评审报告 — `management_review_report_service.py` + `api/management_review.py`

**`management_review_report_service.py`**：
- `generate_report(..., llm_provider: "LLMProvider | None" = None, use_llm: bool = True, ...)` → 去掉 `llm_provider` 参数；内部 `pc = await provider_adapter.build_client(db)`（`except → pc=None`）。
- L236/242 `if use_llm and llm_provider is not None:` → `if use_llm and pc is not None:`。
- `_enrich_with_llm(... llm_provider ...)`（L137）+ `_generate_executive_summary(... llm_provider ...)`（L180）：去 `llm_provider` 参数，改用闭包/传入的 `pc`；L143/186 `if llm_provider is None:` → `if pc is None:`（走 `_fallback_executive_summary`，hybrid 降级）。
- L152 `llm_provider.complete(prompt, LLM_SECTION_SCHEMA)` → `provider_adapter.complete_json(pc, prompt, LLM_SECTION_SCHEMA)`。
- L191 `llm_provider.complete(...)` → `provider_adapter.complete_json(pc, prompt, ...)`。
- **关键：helper 必须向 `generate_report` 回传 LLM 失败信号**（现状吞异常，generate_report 拿不到失败）。真实结构：`_enrich_with_llm` 对 `REPORT_SECTIONS`（13 段）**循环**调 LLM、按段 `except` 吞异常降级，现返回 `(sections, llm_enriched: bool)`；`_generate_executive_summary` 吞异常返回 `(summary, recs)` 无失败信号。改为：
  - `_enrich_with_llm` 返回 `(sections, section_attempted: int, section_failed_keys: list[str])` —— `section_attempted` = 实际尝试 LLM 的段数（13，若 pc 非None），`section_failed_keys` = 抛异常的段 key 列表。
  - `_generate_executive_summary` 返回 `(summary, recs, summary_failed: bool)` —— `summary_failed=True` 当 LLM 抛异常走 fallback。
  - `generate_report` 据这些写审计（见下）。**保留各 helper 现有 fallback 行为不变**（按段降级 / `_fallback_executive_summary`），只追加 outcome 回传，不重构 fallback。
- `model_name`（L249）`getattr(llm_provider, "model", None)` → `(pc.model if pc else None) or settings.LLM_MODEL or "rule-only"`（`ProviderClient.model` 真实存在，`provider_adapter.py:26`；**`pc` 可能为 None**（未配置 / `use_llm=False` 路径仍算 `model_name`），需 `if pc else None` 空值保护，再 `settings.LLM_MODEL` 兜底）。
- **保留**现有 CRUD `_write_audit(db, review_id, user_id, action, changed_fields)`（L372，`REPORT_GENERATE/SAVE_DRAFT/FINALIZE/REOPEN`）**原样不动** —— LLM 审计与 CRUD 审计分离，不复用、不删除。

**审计语义（新增 `write_audit_raw` 两态，与 CRUD 审计并存；状态写 `new_values`）**：
- `pc is None` 或 `use_llm=False` → 不审计（`section_attempted=0`、`summary` 走 fallback）。
- LLM 尝试（`pc is not None and use_llm`）→ 据 helper outcome 聚合**两态**：
  - `section_failed_keys == [] and not summary_failed` → `new_values={"status": "success", "model": (pc.model if pc else None) or settings.LLM_MODEL, "section_attempted": N, "summary_failed": false}`。
  - `section_failed_keys` 非空 **或** `summary_failed` → `new_values={"status": "llm_failed", "model": ..., "section_attempted": N, "section_failed_keys": [...], "summary_failed": bool}`（部分段失败也算 `llm_failed`，但 failed_keys 记录细节，**fallback 行为不变**——失败段降级、summary 走 fallback）。
  - > **不用 D4/D5 的三态**：管理评审 13 段 + 1 summary 是固定编排、按段降级后仍出报告；两态（success / llm_failed-with-detail）足够，`section_failed_keys` 承载粒度。`partial` 态的"部分失败但仍可用"语义这里等同于 `llm_failed` + 非空 `section_failed_keys`，不另设状态。
- `record_id = review.review_id`；`table_name = "management_reviews"`；`correlation_id = uuid5(NAMESPACE_URL, f"mgmt_review:{review_id}:{sections_hash}")`；`factory_id = review.factory_id`；`action = "llm_report_generate"`；`tenant_schema` 由路由传 `generate_report`。
- `write_audit_raw` 只 flush；**提交骑乘 service 内 `generate_report` 现有 `await db.commit()`（`management_review_report_service.py:264`），不是路由**——路由 `management_review.py` generate 端点**无 commit**（L411-439 无 `db.commit`），现有 CRUD `_write_audit`（L261）已靠 service L264 commit 落库。新增 LLM `write_audit_raw` 的 flush 必须在 service L264 commit **之前**完成（与 CRUD `_write_audit` 一并由 L264 提交）。**plan 勿在路由加 commit、勿删 service L264 commit**。

**`api/management_review.py`** generate 路由（L426 区域）：
- 删 `llm_provider = getattr(request.app.state, "llm_provider", None)`。
- `report_service.generate_report(..., llm_provider=llm_provider, use_llm=req.use_llm, ...)` → 去 `llm_provider`，加 `tenant_schema=tenant_schema(request)`。
- 路由**无 commit**（L411-439 无 `db.commit`）；提交由 service `generate_report` 内 `await db.commit()`（L264）完成 —— **路由不加 commit**。

### 3.4 CAPA draft — `capa_draft_service.py` + `api/capa.py`

**`capa_draft_service.py`** `generate_draft()`：
- L239 `llm_provider = getattr(request.app.state, "llm_provider", None)` → `pc = await provider_adapter.build_client(db)`（`try/except ProviderNotConfiguredError → pc=None`）。
- L240 `llm_model_name = getattr(llm_provider, "model", None) or settings.LLM_MODEL or "unknown"` → `(pc.model if pc else None) or settings.LLM_MODEL or "unknown"`（`ProviderClient.model` 真实存在，`provider_adapter.py:26`；**L240 在 L387 503 检查之前执行，`pc` 可能为 None**，需 `if pc else None` 空值保护，再 `settings.LLM_MODEL` 兜底；503 审计行的 `model` 字段仍能正确落 "unknown"）。
- L387 `if llm_provider is None: raise HTTPException(503, "AI 服务未配置")` → `if pc is None: ...`（**保留纯 LLM 503 语义**，P1-B 模式）。
- L408 `llm_provider.complete(prompt, response_schema)` → `provider_adapter.complete_json(pc, prompt, response_schema)`（包在现有 `asyncio.wait_for(..., timeout=capa_draft_llm_timeout)` 内不变）。
- L411-418 的 `TimeoutError`/`ConnectionError`/`Exception` 分支保留（`complete_json` 异常向上冒泡，现有 except 仍捕获；`complete_json` 内部 `response_format=json_object` 被拒重试对调用方透明）。
- **现有 `_write_audit()`（L261-288，`AI_DRAFT`，独立 `get_tenant_aware_session()` 自提交，覆盖 success/fail/503）原样保留** —— 只换 provider 调用，不重写审计。`audit_success`/`audit_error`/`audit_status_code`/`model` 仍写入 `changed_fields`（`model` 用上面的 `llm_model_name = (pc.model if pc else None) or settings.LLM_MODEL or "unknown"`，**含 503 未配置路径的空值保护**）。503 路径（`pc is None`）仍经现有 `_write_audit` 审计 `status_code=503`。
- **不新增 `write_audit_raw`**（策略 B：CAPA draft 已有完整 success/fail/503 审计，重写收益低、独立 session 自提交语义重构风险高）。

**`api/capa.py`** draft 端点 + 全局能力探测端点：
- `draft_capa_step`（L516）：现调 `generate_draft(db, report_id, step, req, scope.user, request)` —— `generate_draft` 内部自己取 `request.app.state.llm_provider`，路由层无显式 llm_provider 传参。**路由层无需改 llm_provider**（`generate_draft` 内部解析 pc）。`generate_draft` 已有 `db: AsyncSession` 参数（L230），`build_client(db)` 可用，无需新参。
- **全局能力探测端点 `capa_capabilities`（`capa.py:112` `GET /capabilities`，非 `:480` 的 `/{report_id}/draft/capabilities`）**：L122-125 现读 `app.state.llm_provider` 返回 `ai_draft_enabled` + `llm_provider` model。改为探测 `await provider_adapter.build_client(db)`：不抛 `ProviderNotConfiguredError` → `ai_draft_enabled=True`、`llm_provider=pc.model or settings.LLM_MODEL or None`；抛 → `ai_draft_enabled=False`、`llm_provider=None`。**与 `generate_draft` 用同一来源**（`build_client`），避免 `ai_draft_enabled` 与实际 `generate_draft` 可用性不一致。
  > **⚠ 端点别改错**：`capa.py:480` `/{report_id}/draft/capabilities`（`draft_capabilities`）返回 `available_steps`/`current_step`，**不读 `app.state.llm_provider`**，P1-D **不动它**。要改的是 `:112` `/capabilities`（`capa_capabilities`）。

## 4. 数据流

```
§3.1 D4/D5:
api/capa.py  GET /{report_id}/d4-fmea-recommendations | d5-...
  └─ pc = provider_adapter.build_client(db)  (except → None)
  └─ HybridRecommendationPipeline(db, pc, embedding_provider)
       recommend(..., user, report_id, factory_id, tenant_schema)
        ├─ rules + graph match (不变)
        └─ llm_layer.enrich(fused, context) → LLMOutcome(candidates, attempted, succeeded, failed)
            pc is None → attempted=0 → 不审计, 返回原候选
            attempted>0 → pipeline 写 write_audit_raw(success/partial/llm_failed)
  └─ await db.commit()  (新增：审计行落库)

§3.2 RAG:
api/search.py  POST /ask
  └─ SearchService(db, embedding_provider).ask(question, user, tenant_schema)
        ├─ vector+fulltext search (不变, 总跑)
        ├─ pc = build_client(db) (except → None)
        ├─ pc is None → 200 sources-only, 不审计
        └─ complete_json(pc, prompt, rag_schema) → success → audit success
                                          except → audit llm_failed, answer 写错误串, 200
  └─ await db.commit()  (新增：审计行落库)

§3.3 管理评审:
api/management_review.py  generate
  └─ report_service.generate_report(..., use_llm, user, tenant_schema)
        ├─ pc = build_client(db) (except → None)
        ├─ use_llm and pc is None → fallback, 不审计
        └─ use_llm and pc: _enrich_with_llm + _generate_executive_summary
              complete_json (13 段 enrich + 1 summary) → success (no failures) → write_audit_raw(success)
                                       except (any section/summary) → fallback + write_audit_raw(llm_failed, section_failed_keys/summary_failed)
        └─ CRUD _write_audit(REPORT_GENERATE)  (保留, 不动)
        └─ service 内 await db.commit()  (L264, LLM 审计 flush + CRUD 审计 一并落库)
  └─ 路由无 commit  (management_review.py generate 端点不 commit)

§3.4 CAPA draft:
api/capa.py  POST /{report_id}/draft/{step}
  └─ generate_draft(db, report_id, step, req, user, request)
        ├─ pc = build_client(db) (except → None)
        ├─ pc is None → 503, 现有 _write_audit(AI_DRAFT, status_code=503)
        └─ complete_json(pc, prompt, response_schema) → success → 现有 _write_audit(success)
                                              except → 现有 _write_audit(fail, status_code=503/504/422)
        (独立 session 自提交, 不新增 write_audit_raw)
```

## 5. 错误处理

各消费者降级语义**全部保留现状**：
- D4/D5：`pc is None` → 原候选返回（hybrid 静默）；LLM 失败 → 候选降级 + 审计 `partial`/`llm_failed`。
- RAG：`pc is None` → 200 sources-only；LLM 失败 → answer 写错误串仍 200 + 审计 `llm_failed`。
- 管理评审：`pc is None` → `_fallback_executive_summary`；LLM 失败 → fallback + 审计 `llm_failed`。
- CAPA draft：`pc is None` → 503；LLM 超时 → 504；连接错误 → 503；JSON 解析失败 → 422（现有 except 分支不变）。

`complete_json` 的 `response_format=json_object` 被 Ark/DeepSeek 拒绝时的降级重试对调用方透明，不改变各消费者降级状态机。`ProviderNotConfiguredError` → `pc=None` → 各 hybrid 走降级 / CAPA draft 走 503。**各消费者 timeout 来源保留现状，不统一**：
- D4/D5：`LLMFusionLayer(timeout=2.0)` 默认 2s（`capa.py:376/447` 构造 `HybridRecommendationPipeline` 未传 timeout，沿用 2s 默认）—— **保留 2s，不强制 15s**。
- 管理评审：`report_llm_timeout or settings.REPORT_LLM_TIMEOUT`（路由 `management_review.py:427` 取 `app.state.report_llm_timeout` 传入 `generate_report`，helper L146/188 用）—— 保留。
- RAG 搜索：`search_service` 无 `wait_for`，走 `complete_json` 内部 `httpx.AsyncClient(timeout=30)`（`provider_adapter.py:179`）—— 保留。
- CAPA draft：`capa_draft_llm_timeout`（`settings.CAPA_DRAFT_LLM_TIMEOUT`，`generate_draft` L248-252 解析）—— 保留。

> **⚠ plan 勿把 timeout 统一成 `settings.LLM_TIMEOUT` 15s**：D4/D5 现行 2s 是 fusion 层刻意短超时（候选已就绪、LLM 只 enrich，超时即降级）；统一到 15s 会改变 D4/D5 响应特性。P1-C 的 15s 下限只作用于 FMEA `recommend()`，不外推到 P1-D。

基座不 import 业务层异常。

## 6. 测试

全程 stub SDK，不调真实 LLM。每消费者覆盖：

**§3.1 D4/D5**：
- `success`：`complete_json` 全成功（fusion + 可能的 fallback）→ `LLMOutcome(attempted>0, failed=0)` → 审计 `new_values.status="success"`，`record_id/correlation_id/factory_id/tenant_schema` 落库
- `partial`：fusion/fallback **两阶段中部分失败**（如 fusion 成功、fallback 抛异常）→ `0<failed<attempted` → 审计 `new_values.status="partial"` + 计数，候选仍降级返回
- `llm_failed`：两阶段 `complete_json` 全抛异常 → `failed==attempted` → 审计 `new_values.status="llm_failed"`
- `pc is None`：`build_client` 抛 `ProviderNotConfiguredError` → `attempted=0` → 不审计，原候选返回
- D4/D5 路由 `await db.commit()` 验证（审计行落库）
- `enrich()` 返回类型变更：所有 enrich 调用方/测试解包 `LLMOutcome`

**§3.2 RAG**：
- `success`：`complete_json` 返回 `{answer: ...}` → 审计 `success`
- `llm_failed`：`complete_json` 抛异常 → answer 写错误串 + 审计 `llm_failed` + 200
- `pc is None`：sources-only 200 + "未配置 LLM" + 不审计
- `record_id` 哨兵稳定：同 query → 同 `uuid5`；`table_name="rag_qa"`
- `correlation_id` 稳定：source_ids 顺序乱序 → 同 correlation_id（验证 sort/dedup）
- `ask_question` 路由 `await db.commit()` 验证

**§3.3 管理评审**：
- `success`：13 段 `complete_json` + summary 全成功 → `section_failed_keys=[]`、`summary_failed=False` → 审计 `new_values.status="success"`
- `llm_failed`：部分段 `complete_json` 抛异常 **或** summary 抛异常 → fallback（按段降级 / `_fallback_executive_summary`）+ 审计 `new_values.status="llm_failed"` + `section_failed_keys`/`summary_failed` 记细节
- helper outcome 回传：`_enrich_with_llm` 返回 `(sections, section_attempted, section_failed_keys)`；`_generate_executive_summary` 返回 `(summary, recs, summary_failed)` —— 验证 generate_report 能拿到失败信号（现状吞异常拿不到）
- `pc is None` / `use_llm=False` → fallback + 不审计
- `model_name` 空值保护：`pc=None` 路径 `(pc.model if pc else None) or settings.LLM_MODEL or "rule-only"` 不 AttributeError
- **CRUD `_write_audit(REPORT_GENERATE)` 仍写**（验证 LLM 审计与 CRUD 审计并存，不互相覆盖）
- **service L264 `await db.commit()` 落库 LLM 审计 + CRUD 审计**（路由无 commit，验证路由未加 commit、service commit 未被删）

**§3.4 CAPA draft**：
- `success`：`complete_json` 成功 → 现有 `_write_audit(AI_DRAFT, success=True)` 仍写
- `pc is None` → 503 + 现有 `_write_audit(status_code=503)`
- 超时 → 504 + 现有审计；JSON 解析失败 → 422 + 现有审计
- **不新增 `write_audit_raw`**（验证基座审计不被引入）
- `capa_capabilities`（`capa.py:112` `GET /capabilities`）`ai_draft_enabled` 探测 `build_client` 不抛异常、`llm_provider=pc.model`；**`draft_capabilities`（`:480`）不动**

**回归**：backend `pytest`（recommendation/capa/search/management_review 路由 + 4 服务 + 现有审计测试）+ frontend `tsc --noEmit`（本变更不碰前端，但 `make check` 跑全量）。

## 7. 显式排除（YAGNI）

- 不包 agent tool / 不走 harness / 不建 agent_session
- 不删旧 `LLMProvider` 类（`ai_config_service` 自检仍用）
- 不重写 CAPA draft 现有 `AI_DRAFT` 审计（只换 provider 调用）
- 不动管理评审 CRUD `_write_audit`（只加 LLM `write_audit_raw`，与之并存）
- 不改各消费者降级语义 / 超时默认值
- 不迁移 `ai_config_service` 自检（诊断用途，单独处理）
- 不改 `audit_logs` schema（`record_id` 保持 `nullable=False`；RAG 用哨兵 UUID 而非放宽约束）
- 不在 `complete_json` 强制 `response_schema` 校验（留 P2+）
- 不加 `app_state.provider_client` 缓存（需要时再统一加）
- 不迁 SPC-FMEA / D7 / 经验教训推送（经核实无 LLM 调用，PROGRESS.md 早先列表有误）

## 8. plan 衔接

进 writing-plans，按消费者拆 TDD 任务，风险递增顺序：
1. **8D D4/D5 LLMFusionLayer**（P1-C 自然延伸）：`LLMOutcome` dataclass + `enrich()` 返回升级 + 调用方解包；`pc` 透传；pipeline `write_audit_raw` 三态；`capa.py` D4/D5 路由 `build_client` + `await db.commit()` + `tenant_schema`
2. **RAG 搜索**：`SearchService.__init__` 去 `llm_provider`；`ask()` 内 `build_client` + `complete_json` + 两态 `write_audit_raw`（哨兵 `record_id` + sort/dedup `correlation_id`）；`search.py` `ask_question` 路由 `await db.commit()` + `tenant_schema`
3. **管理评审报告**：`generate_report` 去 `llm_provider` 参数 + 内部 `build_client`；`_enrich_with_llm`/`_generate_executive_summary` 切 `complete_json` 且**改返回 outcome**（`(sections, section_attempted, section_failed_keys)` / `(summary, recs, summary_failed)`，保留各自 fallback）；`model_name` 用 `(pc.model if pc else None) or settings.LLM_MODEL or "rule-only"`；timeout 保留 `report_llm_timeout or settings.REPORT_LLM_TIMEOUT`；新增 LLM `write_audit_raw` 两态（`new_values.status` + `section_failed_keys`/`summary_failed`，CRUD 审计保留）；LLM flush 置于 service L264 commit **之前**；`management_review.py` 路由去 `app.state.llm_provider` + 传 `tenant_schema`（**路由不加 commit、不删 service L264 commit**）
4. **CAPA draft**：`generate_draft` 内 `build_client` 替 `app.state.llm_provider`；`complete_json` 替 `.complete()`；`llm_model_name` 用 `(pc.model if pc else None) or settings.LLM_MODEL or "unknown"`（503 未配置路径空值保护）；`capa_capabilities`（`capa.py:112`）探测适配（`draft_capabilities:480` 不动）；现有 `AI_DRAFT` 审计保留不动
5. 全量回归 + `make check`（backend pytest + frontend tsc）

> **回归测试必含**：(a) D4/D5 `LLMOutcome` 三态（success/partial/llm_failed，partial = fusion/fallback 两阶段中部分失败）+ 路由 commit + **2s timeout 保留**；(b) RAG 哨兵 `record_id` 稳定 + `correlation_id` sort/dedup + 路由 commit；(c) 管理评审 helper 回传 outcome（`section_attempted`/`section_failed_keys`/`summary_failed`）+ LLM 审计（`new_values.status` + failed 细节）与 CRUD 审计并存 + service L264 commit 落库 + 路由无 commit + `pc=None` 路径 `model_name` 空值保护不 AttributeError；(d) CAPA draft 现有 `AI_DRAFT` 审计 success/503/504/422 不变（`model` 用 `(pc.model if pc else None) or settings.LLM_MODEL`，503 路径不 AttributeError）+ 不引入 `write_audit_raw` + `capa_capabilities:112` 探测 `build_client`、`draft_capabilities:480` 不动；(e) 所有审计状态写 `new_values={"status":...}`（`write_audit_raw` 无 status 参数）；(f) `LLMProvider` 类仍被 `ai_config_service` 引用（未删）；(g) **各消费者 timeout 来源未统一**（D4/D5 2s / mgmt `REPORT_LLM_TIMEOUT` / RAG httpx 30s / CAPA draft `CAPA_DRAFT_LLM_TIMEOUT`）。