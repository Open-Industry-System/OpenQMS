# P1-B — 质量趋势 AI 解读迁移到 Agent 基座 详细设计

- **日期**: 2026-06-30
- **作者**: Sam Wang (与 Claude 协作)
- **状态**: 已定稿，待写实现 plan
- **类型**: 期级实现 spec（P1-B）
- **上游**: [2026-06-29-ai-driven-qms-overview-design.md](./2026-06-29-ai-driven-qms-overview-design.md) · [2026-06-29-ai-qms-p0-agent-base-design.md](./2026-06-29-ai-qms-p0-agent-base-design.md)

## 1. 范围与目标

把 `quality_trend_service.interpret_quality_trend` 的 LLM 调用层从旧 `LLMProvider.complete()` 迁到 P0 基座 `provider_adapter`，并把审计入口统一到基座 `audit` helper。**薄迁移**：不包成 agent tool、不走 harness、不创建 agent_session；缓存 / rate limit / 解析校验 / 7 状态机原样保留。

P1-B 是 P1（迁移现有 LLM 调用）的第一个消费者，目的是验证"LLM 调用统一到基座 provider_adapter + 审计统一到基座 audit"这条迁移模板，跑通后套到 P1-C/D/E。

**不在 P1-B**：包成 readonly agent tool（留 P2 Copilot）；FMEA 推荐 / 管理评审 / 图谱混合推荐（P1-C/D/E）；旧 `LLMProvider` 类删除（P1 全部消费者迁完后）。

## 2. 改动点（4 处）

### 2.1 `backend/app/services/agent/provider_adapter.py` — 新增 `complete_json`

对等旧 `LLMProvider.complete()` 的成熟逻辑，搬入基座：

```python
async def complete_json(pc: ProviderClient, prompt: str, response_schema: dict) -> dict:
    """单次 JSON LLM 调用：prompt -> dict。对等旧 LLMProvider.complete。
    - openai 路径：response_format=json_object + Ark/DeepSeek 拒绝时降级重试 + _extract_json + 大小上限。
    - anthropic 路径：messages.create + json.loads + 大小上限。"""
```

- 复用 `_extract_json`：**抽到共享 util**（`backend/app/services/agent/llm_json.py` 或类似），`provider_adapter.complete_json` 与旧 `llm_provider._extract_json` 都从该 util 导入。**不直接移动** `llm_provider._extract_json`——旧 `OpenAIProvider.complete()` 仍依赖它（P1-B 不迁移 FMEA/管理评审/图谱等消费者，旧 `LLMProvider` 类保留），`llm_provider.py` 改为从共享 util 导入并保留兼容包装。
- `MAX_RESPONSE_BYTES = 10_240`：同样抽到共享 util（或 `provider_adapter` 模块常量），`llm_provider.py` 保留导入兼容。
- openai 降级重试保留：`chat.completions.create(response_format={"type": "json_object"})` 报 `"json_object"`/`"response_format"` 时去掉 `response_format` 重试
- `chat_with_tools`（tool-calling）不动；`complete_json` 服务单次 JSON 消费者
- `response_schema` 参数保留（与旧 `complete` 签名一致；P1-B 不强制 schema 校验，留作 P2+ 模型级 schema 强制时用）
- **未配置 LLM 边界**：`provider_adapter` 定义自己的 `ProviderNotConfiguredError`（基座异常，不 import 业务层 `LLMNotConfiguredError`）。`build_client` 在 `cfg.llm_api_key` 为空 或 `cfg.llm_model` 为空时抛 `ProviderNotConfiguredError`（不再默认 `gpt-4o`/`claude-sonnet-...` 静默构造）。`interpret_quality_trend` 捕获 `ProviderNotConfiguredError` → 写 `llm_not_configured` 审计 → 抛业务层 `LLMNotConfiguredError`（保持对 dashboard 路由的 503 语义不变）。

### 2.2 `backend/app/services/agent/audit.py` — 新增 `write_audit_raw`

不依赖 `AgentContext` 的基座审计入口，供非 agent 会话消费者用：

```python
async def write_audit_raw(
    db: AsyncSession, *, user_id: uuid.UUID, factory_id: uuid.UUID | None,
    tenant_schema: str, table_name: str, record_id: uuid.UUID, action: str,
    correlation_id: uuid.UUID | None = None, changed_fields: dict | None = None,
    old_values: dict | None = None, new_values: dict | None = None,
) -> AuditLog:
```

- 与 `write_audit(ctx, ...)` 行为一致（写 `audit_logs` 含 `factory_id`/`tenant_schema`/`correlation_id`），只是 scope 从参数取而非 ctx
- `write_audit(ctx, ...)` 重构为 `write_audit_raw` 的薄包装（从 ctx 取 `user_id`/`factory_id`/`tenant_schema` 转调）以 DRY
- `write_audit_raw` 只 `flush` 不 `commit`（与 `write_audit` 一致）；commit 时机由调用方决定

### 2.3 `backend/app/services/quality_trend_service.py` — 换 provider + 换审计

- `interpret_quality_trend` 签名：**去掉 `llm_provider` 参数**，新增 `factory_id: uuid.UUID | None` + `tenant_schema: str`（由调用方从 `RequestScope` 解析传入）。`factory_id` 允许 `None`——与 `RequestScope.effective_factory_id: UUID | None` 及 dashboard 现有"None=全局范围"语义一致；`AuditLog.factory_id` 本就 nullable，`write_audit_raw` 接受 `factory_id: uuid.UUID | None`。
- 内部：
  - `pc = await provider_adapter.build_client(db)`（读 raw ai-config，基座 provider）
  - `raw = await asyncio.wait_for(provider_adapter.complete_json(pc, prompt, _interpret_response_schema()), timeout=LLM_TIMEOUT)`
- `_write_interpret_audit` 改用 `audit.write_audit_raw`：
  - 传 `factory_id`（可 None）/`tenant_schema`/`user_id`
  - `correlation_id` = 由 `scope_hash` 派生的稳定 UUID（`uuid.uuid5(uuid.NAMESPACE_URL, f"quality_trend:{scope_hash}")`）—— 同一 scope 多次解读可按 correlation_id 聚合
  - 7 状态 + `audit_context` 原样保留（写入 `new_values`）
  - 保留现有 `await db.commit()`（`_write_interpret_audit` 本就独立提交；`write_audit_raw` flush 后由 `_write_interpret_audit` commit）
- 缓存 / rate limit / `_parse_interpretation` / `evidence_refs` 校验 / 5 种错误状态 全部不动

### 2.4 `backend/app/api/dashboard.py` — 调用面适配

`POST /widgets/quality-trend/interpret` 路由（`interpret_quality_trend` handler）：
- 不再传 `app_state.llm_provider`
- 从 `RequestScope` 解析 `factory_id`（`scope.effective_factory_id`，可为 None）传入
- `tenant_schema`：在 dashboard 路由模块加同名小 helper `_tenant_schema(request) -> str`（与 `backend/app/api/agent/sessions.py:17` 一致：`getattr(request.state, "tenant", None)` 取 `schema_name`，缺省 `"public"`），避免 `request.state.tenant` 缺属性时踩空，并与 P0 agent API 保持一致
- 其余请求参数不变

## 3. 数据流

```
dashboard.py 路由
  └─ RequestScope → factory_id (effective_factory_id) + tenant_schema
  └─ interpret_quality_trend(db, user_id, factory_id, tenant_schema, filter_codes, ...)
       ├─ _enforce_rate_limit / 缓存检查（不变）
       ├─ pc = provider_adapter.build_client(db)        ← 新：基座 provider
       ├─ raw = complete_json(pc, prompt, schema)       ← 新：基座 complete_json
       ├─ _parse_interpretation(raw, ...)               ← 不变
       └─ _write_interpret_audit → audit.write_audit_raw ← 新：基座审计入口
```

## 4. 错误处理

7 状态全部保留并经 `write_audit_raw` 写入：`rate_limited` / `insufficient_data` / `llm_not_configured` / `llm_failed`(超时+异常) / `parse_failed` / `cache_hit` / `success`。`LLM_TIMEOUT=30s` 保留。`complete_json` 的降级重试对调用方透明（不改变错误状态机）。

`llm_not_configured` 语义闭合（见 §2.1）：`build_client` 缺 key/model → 抛基座 `ProviderNotConfiguredError` → `interpret_quality_trend` 捕获 → 写 `llm_not_configured` 审计 → 抛业务层 `LLMNotConfiguredError`（dashboard 路由仍返回 503，语义不变）。基座不 import 业务层异常。

## 5. 测试

- `provider_adapter.complete_json`：
  - openai 路径：`response_format=json_object` 成功 → 返回 dict；SDK 拒绝 `response_format` → 降级重试成功；返回非 JSON 包裹 ```json fence → `_extract_json` 解析；超 `MAX_RESPONSE_BYTES` → 抛 `ValueError`
  - anthropic 路径：`messages.create` → `json.loads` 成功；超限抛错
  - `build_client` 缺 key/model → 抛 `ProviderNotConfiguredError`
  - 全程 stub SDK（monkeypatch `pc.client`），不调真实 LLM
- `audit.write_audit_raw`：写入 `audit_logs` 含 `factory_id`（含 None 用例）/`tenant_schema`/`correlation_id`；`write_audit(ctx)` 仍工作（薄包装不破坏 P0 测试）
- `interpret_quality_trend` 迁移后：
  - 7 状态审计经 `write_audit_raw`、`factory_id`/`correlation_id` 落库
  - 缓存命中/rate limit/`evidence_refs` 校验行为不变（现有测试适配新签名：去 `llm_provider`、加 `factory_id`/`tenant_schema`）
  - `complete_json` stub 后跑通 success 路径
- `dashboard.py` 路由：传 `factory_id`/`tenant_schema`、不再传 `llm_provider`；现有路由测试适配

## 6. 显式排除（YAGNI）

- 不包 agent tool / 不走 harness / 不建 agent_session
- 不删旧 `LLMProvider` 类（P1 全迁完后删）
- 不加 `app_state.provider_client` 缓存（需要时再统一加）
- 不动 `chat_with_tools`
- 不迁移其他消费者（FMEA 推荐 / 管理评审 / 图谱）
- 不在 `complete_json` 强制 `response_schema` 校验（留 P2+）

## 7. plan 衔接

进 writing-plans，拆 TDD 任务：`complete_json` → `write_audit_raw`（+ `write_audit` 重构为包装）→ `interpret_quality_trend` 改造 → `dashboard.py` 调用面 → 测试适配 → 全量回归。
