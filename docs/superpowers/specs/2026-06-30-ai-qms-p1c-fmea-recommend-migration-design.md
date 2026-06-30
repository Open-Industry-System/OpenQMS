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
- **替换全部 `self.llm is not None` / `self.llm.complete` 引用**（共 5 处业务引用，分布在 `recommend()` 与缓存 helper）：
  - line 592（`_get_cached` 命中后的 fall-through gate）：`if self.llm is not None and not cached_with_llm:` —— 见下方"缓存 gate 顺序"特殊处理
  - line 624（`_need_llm` 调用入参 `llm_available=self.llm is not None`）：改为 `llm_available=pc is not None`
  - line 641（`self.llm.complete(prompt, {})`）：改为 `provider_adapter.complete_json(pc, prompt, {})`（见 §`need_llm` 分支）
  - line 663 / 902 / 925 / 933（`RecommendResponse.llm_available` 与 `RecommendationCache.llm_available` 写入）：改为 `pc is not None`。`_cache_result`（line 902/925/933）与响应构造（line 663）需把 `llm_available` 值从 `recommend()` 局部 `pc is not None` 传入（`_cache_result` 加 `llm_available: bool` 参数），不再访问已删除的 `self.llm`。
  - line 557（`self.llm = llm_provider`）随构造函数删除一并去掉。
- `self.llm_timeout`（line 562/642）**保留**（这是超时字段，不是 provider 引用）。

**`recommend()` 签名**：新增 `tenant_schema: str` 参数（由路由传入，与 P1-B 一致）。`factory_id` 从 `fmea.factory_id` 取（NOT NULL，无需新参）。保留 `request: RecommendRequest` / `user: User` / `request_scope: RequestScope`。

**provider 解析（缓存检查之前）**——**顺序关键**：
```python
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderNotConfiguredError
try:
    pc = await provider_adapter.build_client(self.db)
except ProviderNotConfiguredError:
    pc = None
```
`pc is None` 即"LLM 未配置"，等价于旧 `self.llm is None`。

> **⚠ 必须在缓存检查之前解析 `pc`**，否则有行为回归：现有 line 590–595 的缓存 gate 是 `if self.llm is not None and not cached_with_llm: pass  # fall through to re-evaluate with LLM`——即"缓存是无 LLM 生成的、而现在 LLM 已可用"时**穿透缓存重新评估**。若按"缓存 miss 后才 build provider"实现，`pc` 在缓存命中时尚未解析，这个 fall-through gate 永远走 `else: return cached`，导致规则模式缓存在 LLM 配好后继续命中 24 小时、AI 增强不触发。因此 `pc` 必须先于缓存检查解析，缓存 gate 的 `self.llm is not None`（line 592）改为 `pc is not None`，`_need_llm` 的 `llm_available`（line 624）同样用 `pc is not None`。

**`_need_llm` 调用**：`llm_available=pc is not None`（其余参数不变）。

**`need_llm` 分支**（原 `self.llm.complete` 调用点，当前行 630–657）：
- `pc is None` → 审计 `llm_not_configured`；`source = "graph" if graph_suggestions else "rule_fallback"`（与旧 `self.llm is None` 路径等价，仅新增审计）。
- `pc is not None` →
  - `raw = await asyncio.wait_for(provider_adapter.complete_json(pc, prompt, {}), timeout=self.llm_timeout)`（`response_schema={}` 与旧 `self.llm.complete(prompt, {})` 一致；解析校验 `SuggestionList.model_validate(raw)` 不变）。
  - 成功 → 审计 `success`，`source` 同现状（`graph_enriched` / `hybrid`）。
  - 异常（含超时）→ 审计 `llm_failed`，`source = "graph" if graph_suggestions else "rule_fallback"`，`logger.warning` 保留（与现状 `except Exception` 一致）。
- `need_llm=False` 分支不变（纯规则 / 纯图谱，不审计）。

**审计入口**（新增私有方法 `_write_recommend_audit`，调 `audit.write_audit_raw`）：
- `db` / `user_id=user.user_id`（`User` 模型主键字段是 `user_id`，非 `id`——`backend/app/models/user.py:14`）/ `factory_id=fmea.factory_id` / `tenant_schema=tenant_schema`
- `table_name="fmea_documents"` / `record_id=fmea_id`（稳定主键，满足 P0 follow-up #2"避免随机 record_id"）
- `correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"fmea_recommend:{fmea_id}:{request.trigger_type}:{context_hash}")`——同一 (fmea, trigger, context) 多次推荐可按 correlation_id 聚合（镜像 P1-B 的 `scope_hash` → `uuid5` 模式，复用已有 `context_hash`）
- `action="llm_recommend"`；状态写入 `new_values`（`{"status": ..., "trigger_type": ..., "source": ..., "suggestion_count": ...}`，与 P1-B 的 `audit_context` 写 `new_values` 一致）
- `write_audit_raw` 只 flush 不 commit。**`recommend()` 全路径（含 `_write_recommend_audit`、`_cache_result`、`_get_cached`）都不显式 commit**——沿用 `recommend()` 现状（现行代码 `_cache_result`/`_get_cached` 只 `execute`，无 commit）。提交由 **`POST /{fmea_id}/recommend` 路由保留现有的 `await db.commit()`**（`backend/app/api/fmea.py:325`）统一完成，审计行与缓存行在该 commit 一并落库。

> **⚠ 不要写成"FastAPI 请求依赖自动提交"**——`backend/app/database.py:39` 的 `get_db` 依赖在 `finally` 里**只 `rollback`、从不 `commit`**（`if session.in_transaction(): await session.rollback()`）。OpenQMS 的提交约定是**路由层显式 `await db.commit()`**，`/recommend` 路由当前就有（line 325），P1-C 保留它即可。这与 P1-B 的 `_write_interpret_audit` 内部独立 `await db.commit()` 不同（P1-B 走 dashboard 路由、helper 自提交）；P1-C 选择沿用 `recommend()` 的"路由层统一提交"现状，不强制对齐 P1-B。两种模式各自自洽，但**文档不得描述为依赖自动提交**。

**审计范围（有意收窄）**：审计只覆盖 `need_llm=True` 的 LLM 尝试路径，三态 `success` / `llm_failed` / `llm_not_configured`。**缓存命中、`need_llm=False` 纯规则路径不审计**——对齐"审计 LLM 调用"语义，避免每次缓存读都写审计。这是与 P1-B（每次解读都写审计）的差异，因 recommend 有缓存且高频。

### 2.2 `backend/app/api/fmea.py` — 调用面适配

`POST /{fmea_id}/recommend` 路由（`recommend` handler）：
- 删 `llm = getattr(fastapi_request.app.state, "llm_provider", None)`（当前行 320）。
- `RecommendationService(db=db, graph_repo=graph_repo, llm_timeout=llm_timeout)`（不传 llm_provider）。
- `service.recommend(fmea_id, request, scope.user, scope, tenant_schema=_tenant_schema(fastapi_request))`。
- **保留路由末尾的 `await db.commit()`**（`fmea.py:325`）——这是 `recommend()` 全路径（含新增审计行、缓存写入）的唯一提交点（见 §2.1 commit 语义说明）。
- 其余请求参数、`_check_rate_limit`、`_recommend_anchor` 不变。

**另一个构造点 — `backend/app/services/fmea_service.py:266`**：`update_fmea` 在 `graph_data`/`product_line_code` 变更时构造 `RecommendationService(db=db, llm_provider=None, graph_repo=_NullGraphRepo())` 调 `invalidate_cache_for_fmea`。构造函数去掉 `llm_provider` 参数后，此调用点必须同步改为 `RecommendationService(db=db, graph_repo=_NullGraphRepo())`，否则会 `TypeError`。该路径只做缓存失效、不调 `recommend()`，无需 `tenant_schema`，但**构造签名改动必须覆盖此处**。

### 2.3 `_tenant_schema` 抽共享 util

P1-B 在 `backend/app/api/dashboard.py` 加了私有 `_tenant_schema(request) -> str` helper（`getattr(request.state, "tenant", None)` 取 `schema_name`，缺省 `"public"`，与 `backend/app/api/agent/sessions.py:17` 一致）。现 2 个消费者，抽共享：

- 新建 `backend/app/core/tenant.py`（**与现有 `dashboard._tenant_schema` 实现完全一致**，仅提取为共享 + 加 `Request` 类型注解）：
  ```python
  from starlette.requests import Request

  def tenant_schema(request: Request) -> str:
      """从 request.state.tenant 取 schema_name，缺省 'public'。

      与 backend/app/api/dashboard.py 现有 _tenant_schema 等价，
      与 backend/app/api/agent/sessions.py:17 的取法一致。
      """
      tenant = getattr(request.state, "tenant", None)
      return tenant.schema_name if tenant else "public"
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
  - **缓存 gate 顺序回归**：先以 `pc=None`（未配 LLM）请求生成规则模式缓存 → 配好 LLM（`build_client` 返回 pc）再请求同 context → fall-through 重新评估、`source` 含 LLM 增强（验证 §2.1 顺序修复，防止 24h 陈旧规则缓存）
- **`api/fmea.py` `/recommend` 路由测试**：不传 `app.state.llm_provider`，验证 service 用 `tenant_schema` 构造；现有路由测试适配；验证路由仍 `await db.commit()`（审计行 + 缓存行落库）。
- **`fmea_service.update_fmea` 测试**：`graph_data`/`product_line_code` 变更触发缓存失效路径不 `TypeError`（验证构造函数签名改动覆盖此调用点）。
- **`dashboard.py` 路由测试**：验证改用共享 `tenant_schema` 后行为不变（P1-B 既有测试应仍绿）。
- **`core/tenant.py` 单测**：`request.state.tenant.schema_name` 存在 → 返回之；`request.state.tenant` 缺省 → `"public"`。

## 3. 数据流

```
api/fmea.py  POST /{fmea_id}/recommend
  └─ RequestScope → user, scope;  tenant_schema(request) → tenant_schema
  └─ RecommendationService(db, graph_repo, llm_timeout)
       recommend(fmea_id, request, user, scope, tenant_schema)
        ├─ _get_fmea_or_404 → fmea.factory_id
        ├─ try: pc = provider_adapter.build_client(db)   ← 新：基座 provider（必须在缓存检查前！）
        │   except ProviderNotConfiguredError: pc = None
        ├─ cache 检查（命中且无需 fall-through 即返回，不审计）
        │     · gate: if pc is not None and not cached_with_llm → fall through 重新评估
        ├─ rules + graph similarity                       ← 不变
        ├─ _need_llm(llm_available=pc is not None)        ← 入参改 pc
        └─ need_llm 分支:
            pc is None → audit llm_not_configured → source=rule_fallback
            pc ok:
              complete_json(pc, prompt, {}) → success → audit success
                                       → except  → audit llm_failed → rule_fallback
        └─ 路由层 await db.commit()（审计行 + 缓存行一并提交）  ← 保留 fmea.py:325
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
2. `recommendation_service.__init__` 去 `llm_provider` 参数；**同步改 `fmea_service.update_fmea:266` 的构造调用**（去 `llm_provider=None`）+ `recommend()` 加 `tenant_schema` 参数；替换全部 `self.llm` 引用（line 557/592/624/641/663/902/925/933，`self.llm_timeout` 保留）
3. **`pc` 解析置于缓存检查之前**（避免缓存 gate 回归），缓存 gate `pc is not None` 替换 line 592，`_need_llm` 入参 `pc is not None` 替换 line 624，`_cache_result` 加 `llm_available: bool` 参数替换 line 902/925/933
4. `_write_recommend_audit`（调 `write_audit_raw`，含 `user_id=user.user_id` / correlation_id / factory_id / tenant_schema）+ `need_llm` 分支三态审计接线；**不 commit**（路由层 `await db.commit()` 统一提交）
5. `api/fmea.py` `/recommend` 调用面切换（去 `app.state.llm_provider`、传 `tenant_schema`、保留 `await db.commit()`）
6. 全量回归 + `make check`（backend pytest + frontend tsc）

> **回归测试必含**：(a) `fmea_service.update_fmea` 缓存失效路径不 `TypeError`；(b) 规则模式缓存命中后、配好 LLM 再请求，fall-through 重新评估（验证 §2.1 缓存 gate 顺序修复）；(c) `await db.commit()` 仍在 `/recommend` 路由（审计行 + 缓存行落库）。
