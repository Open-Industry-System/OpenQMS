# P1-C — FMEA 推荐 LLM 调用迁移到 Agent 基座 详细设计

- **日期**: 2026-06-30
- **作者**: Sam Wang (与 Claude 协作)
- **状态**: 已定稿，待写实现 plan
- **类型**: 期级实现 spec（P1-C）
- **上游**: [2026-06-29-ai-driven-qms-overview-design.md](./2026-06-29-ai-driven-qms-overview-design.md) · [2026-06-29-ai-qms-p0-agent-base-design.md](./2026-06-29-ai-qms-p0-agent-base-design.md) · [2026-06-30-ai-qms-p1b-quality-trend-migration-design.md](./2026-06-30-ai-qms-p1b-quality-trend-migration-design.md)

## 1. 范围与目标

把 `RecommendationService.recommend()` 的 LLM 调用层从旧 `LLMProvider.complete()` 迁到 P0 基座 `provider_adapter.complete_json`，并为 LLM 调用补基座审计 `audit.write_audit_raw`。**薄迁移**：不包成 agent tool、不走 harness、不创建 agent_session；缓存 / 速率限制 / 规则引擎 / 图谱相似 / `_need_llm` / 超时下限 / 5 状态 source 全部原样保留。

P1-C 是 P1（迁移现有 LLM 调用）的第二个消费者，沿用 P1-B 验证过的"LLM 调用统一到基座 provider_adapter + 审计统一到基座 audit"迁移模板。

覆盖全部 trigger type：`failure_mode` / `failure_effect` / `failure_cause` / `prevention_control` / `detection_control` / `optimization` 以及 5T 的 `dfmea_tool` / `dfmea_trend` / `pfmea_tool` / `pfmea_trend`——全部走同一个 `recommend()`，同一个 `.complete()` 调用点（`recommendation_service.py` 当前行 641）。**一个调用点，一处迁移。**

**不在 P1-C**：包成 readonly agent tool（留 P2 Copilot）；管理评审报告 / 搜索 / CAPA 草稿 / LLMFusionLayer 等消费者（P1-D/E）；`ai_config_service` 自检调用（诊断用途，单独处理）；旧 `LLMProvider` 类删除（P1 全部消费者迁完后）。

### 与 P1-B 的关键差异

P1-B 的 `quality_trend` 是纯 LLM 特性——LLM 未配置时返回 503（`llm_not_configured` → `LLMNotConfiguredError`）。FMEA `recommend()` 是**混合**推荐（规则 + 图谱 + LLM），LLM 未配置时现行 UX 是**规则降级 200 + "AI 建议暂不可用"**。P1-C 保留这个 hybrid 语义：`build_client` 抛 `ProviderNotConfiguredError` 时 `recommend()` 捕获后走纯规则降级返回 200，**不抛 503**。

## 2. 改动点（4 处）

### 2.1 `backend/app/services/recommendation_service.py` — 换 provider + 补审计

**构造函数**：
- 去掉 `llm_provider` 参数，签名改为 `__init__(self, db: AsyncSession, graph_repo: FMEAGraphRepository, llm_timeout: int | None = None)`。
- 删 `self.llm`、删 `from app.services.llm_provider import LLMProvider` 导入。
- `self.llm_timeout = max(llm_timeout or settings.LLM_TIMEOUT, 15)` 保留（15s 下限不动）。
- **`_cache_result` 内两处 `self.llm is not None`**（当前 line 919 / 925，写 `RecommendationCache.llm_available`）改为引用 `recommend()` 局部 `pc is not None`——需把 `llm_available` 值作为参数传入 `_cache_result`（或在 `recommend()` 内构造好后传入），避免 `_cache_result` 再访问已删除的 `self.llm`。`_get_cached` 不引用 `self.llm`，不动。

**`recommend()` 签名**：新增 `tenant_schema: str` 参数（由路由传入，与 P1-B 一致）。`factory_id` 从 `fmea.factory_id` 取（NOT NULL，无需新参）。保留 `request: RecommendRequest` / `user: User` / `request_scope: RequestScope`。

**provider 解析（缓存 miss 后、规则引擎前）**：
```python
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderNotConfiguredError
try:
    pc = await provider_adapter.build_client(self.db)
except ProviderNotConfiguredError:
    pc = None
```
`pc is None` 即"LLM 未配置"，等价于旧 `self.llm is None`。

**`_need_llm` 调用**：`llm_available=pc is not None`（其余参数不变）。

**`need_llm` 分支**（原 `self.llm.complete` 调用点，当前行 630–657）：
- `pc is None` → 审计 `llm_not_configured`；`source = "graph" if graph_suggestions else "rule_fallback"`（与旧 `self.llm is None` 路径等价，仅新增审计）。
- `pc is not None` →
  - `raw = await asyncio.wait_for(provider_adapter.complete_json(pc, prompt, {}), timeout=self.llm_timeout)`（`response_schema={}` 与旧 `self.llm.complete(prompt, {})` 一致；解析校验 `SuggestionList.model_validate(raw)` 不变）。
  - 成功 → 审计 `success`，`source` 同现状（`graph_enriched` / `hybrid`）。
  - 异常（含超时）→ 审计 `llm_failed`，`source = "graph" if graph_suggestions else "rule_fallback"`，`logger.warning` 保留（与现状 `except Exception` 一致）。
- `need_llm=False` 分支不变（纯规则 / 纯图谱，不审计）。

**审计入口**（新增私有方法 `_write_recommend_audit`，调 `audit.write_audit_raw`）：
- `db` / `user_id=user.id` / `factory_id=fmea.factory_id` / `tenant_schema=tenant_schema`
- `table_name="fmea_documents"` / `record_id=fmea_id`（稳定主键，满足 P0 follow-up #2"避免随机 record_id"）
- `correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"fmea_recommend:{fmea_id}:{request.trigger_type}:{context_hash}")`——同一 (fmea, trigger, context) 多次推荐可按 correlation_id 聚合（镜像 P1-B 的 `scope_hash` → `uuid5` 模式，复用已有 `context_hash`）
- `action="llm_recommend"`；状态写入 `new_values`（`{"status": ..., "trigger_type": ..., "source": ..., "suggestion_count": ...}`，与 P1-B 的 `audit_context` 写 `new_values` 一致）
- `write_audit_raw` 只 flush 不 commit。**`recommend()` 全路径（含 `_cache_result`、`_get_cached`）都不显式 commit**，统一由 FastAPI 请求依赖在请求结束时提交（OpenQMS 标准模式，与 P1-B `_write_interpret_audit` 独立 commit 的差异见下）。审计行与缓存行在同一请求事务内一并提交。

> **commit 语义差异说明**：P1-B 的 `interpret_quality_trend` 走 dashboard 路由、`_write_interpret_audit` 独立 `await db.commit()`（P1-B §2.3 原文）。P1-C 的 `recommend()` 现行代码**不显式 commit**（`_cache_result`/`_get_cached` 只 `execute`，依赖请求依赖收尾提交）。为最小改动，P1-C 沿用 `recommend()` 现状——`_write_recommend_audit` 不显式 commit，与 `_cache_result` 同事务由请求依赖提交。两路径行为各自自洽，不强制对齐。

**审计范围（有意收窄）**：审计只覆盖 `need_llm=True` 的 LLM 尝试路径，三态 `success` / `llm_failed` / `llm_not_configured`。**缓存命中、`need_llm=False` 纯规则路径不审计**——对齐"审计 LLM 调用"语义，避免每次缓存读都写审计。这是与 P1-B（每次解读都写审计）的差异，因 recommend 有缓存且高频。

### 2.2 `backend/app/api/fmea.py` — 调用面适配

`POST /{fmea_id}/recommend` 路由（`recommend` handler）：
- 删 `llm = getattr(fastapi_request.app.state, "llm_provider", None)`（当前行 320）。
- `RecommendationService(db=db, graph_repo=graph_repo, llm_timeout=llm_timeout)`（不传 llm_provider）。
- `service.recommend(fmea_id, request, scope.user, scope, tenant_schema=_tenant_schema(fastapi_request))`。
- 其余请求参数、`_check_rate_limit`、`_recommend_anchor` 不变。

### 2.3 `_tenant_schema` 抽共享 util

P1-B 在 `backend/app/api/dashboard.py` 加了私有 `_tenant_schema(request) -> str` helper（`getattr(request.state, "tenant", None)` 取 `schema_name`，缺省 `"public"`，与 `backend/app/api/agent/sessions.py:17` 一致）。现 2 个消费者，抽共享：

- 新建 `backend/app/core/tenant.py`：
  ```python
  def tenant_schema(request) -> str:
      """从 request.state.tenant 取 schema_name，缺省 'public'。"""
      tenant = getattr(request.state, "tenant", None)
      return getattr(tenant, "schema_name", None) or "public"
  ```
- `dashboard.py` 删本地 `_tenant_schema`，改为 `from app.core.tenant import tenant_schema`，调用点改 `tenant_schema(request)`（行为不变，纯 DRY）。
- `api/fmea.py` 同样导入并使用。

### 2.4 测试适配

- **`recommendation_service` 测试**：stub `provider_adapter.build_client` / `complete_json` 替换旧 `llm_provider` 注入；覆盖：
  - `success`：`complete_json` 返回合法 dict → `source=hybrid/graph_enriched`，审计 `success`，`factory_id`/`tenant_schema`/`correlation_id` 落库
  - `llm_failed`：`complete_json` 抛异常 / 超时 → `source=rule_fallback`，审计 `llm_failed`，`logger.warning` 保留
  - `llm_not_configured`：`build_client` 抛 `ProviderNotConfiguredError` → `pc=None`，规则降级 200，审计 `llm_not_configured`
  - 缓存命中：不审计（验证 `_write_recommend_audit` 不被调）
  - `need_llm=False` 纯规则：不审计
  - `correlation_id` 对同一 (fmea, trigger, context) 稳定
- **`api/fmea.py` `/recommend` 路由测试**：不传 `app.state.llm_provider`，验证 service 用 `tenant_schema` 构造；现有路由测试适配。
- **`dashboard.py` 路由测试**：验证改用共享 `tenant_schema` 后行为不变（P1-B 既有测试应仍绿）。
- **`core/tenant.py` 单测**：`request.state.tenant.schema_name` 存在 → 返回之；缺省 → `"public"`。

## 3. 数据流

```
api/fmea.py  POST /{fmea_id}/recommend
  └─ RequestScope → user, scope;  tenant_schema(request) → tenant_schema
  └─ RecommendationService(db, graph_repo, llm_timeout)
       recommend(fmea_id, request, user, scope, tenant_schema)
        ├─ _get_fmea_or_404 → fmea.factory_id
        ├─ cache 检查（命中即返回，不审计）            ← 不变
        ├─ try: pc = provider_adapter.build_client(db)   ← 新：基座 provider
        │   except ProviderNotConfiguredError: pc = None
        ├─ rules + graph similarity                       ← 不变
        ├─ _need_llm(llm_available=pc is not None)        ← 不变
        └─ need_llm 分支:
            pc is None → audit llm_not_configured → source=rule_fallback
            pc ok:
              complete_json(pc, prompt, {}) → success → audit success
                                       → except  → audit llm_failed → rule_fallback
```

## 4. 错误处理

5 状态 source 全部保留：`rule` / `graph` / `hybrid` / `graph_enriched` / `rule_fallback`。`complete_json` 的降级重试（`response_format=json_object` 被 Ark/DeepSeek 拒绝时去掉重试）对调用方透明，不改变 source 状态机。

`ProviderNotConfiguredError` → `recommend()` 捕获 → `pc=None` → 规则降级 200（**不**抛 503，与 P1-B 不同，对齐 hybrid 现状 UX）。`LLM_TIMEOUT` 15s 下限保留。基座不 import 业务层异常。

## 5. 测试

详见 §2.4。全程 stub SDK，不调真实 LLM。回归：backend `pytest`（含 recommendation + fmea 路由 + dashboard + tenant 单测）+ frontend `tsc --noEmit`（本变更不碰前端，但 `make check` 跑全量）。

## 6. 显式排除（YAGNI）

- 不包 agent tool / 不走 harness / 不建 agent_session
- 不删旧 `LLMProvider` 类（管理评审 / 搜索 / CAPA draft / LLMFusionLayer 等消费者仍用）
- 不动 `chat_with_tools`、`_need_llm`、规则引擎、图谱管线、缓存逻辑、`_compute_context_hash`
- 不迁移其他消费者（管理评审 / 搜索 / CAPA draft / LLMFusionLayer / ai_config 自检）
- 不在 `complete_json` 强制 `response_schema` 校验（留 P2+）
- 不改超时默认值（已 15s 下限）
- 缓存命中 / `need_llm=False` 纯规则路径不审计
- 不加 `app_state.provider_client` 缓存（需要时再统一加）

## 7. plan 衔接

进 writing-plans，拆 TDD 任务：
1. `core/tenant.py` 共享 util + 单测 → `dashboard.py` 切换导入（P1-B 测试应仍绿）
2. `recommendation_service.__init__` 去 `llm_provider` 参数 + `recommend()` 加 `tenant_schema` 参数（先 stub build_client/complete_json 让现有测试适配新签名）
3. `_write_recommend_audit`（调 `write_audit_raw`，含 correlation_id/factory_id/tenant_schema）+ `need_llm` 分支三态审计接线
4. `api/fmea.py` 调用面切换（去 `app.state.llm_provider`、传 `tenant_schema`）
5. 全量回归 + `make check`
