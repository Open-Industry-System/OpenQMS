# FMEA 智能推荐升级 — 设计文档

> **状态:** 已审阅  
> **日期:** 2026-06-01  
> **范围:** 后端推荐服务 + 前端智能建议下拉组件  
> **审查修订:** 2026-06-01 R1 — 修正缓存、权限、限流、前端接入、LLM Provider 边界  
> **审查修订:** 2026-06-01 R2 — 修正迁移编号冲突、PG partial index、权限依赖语义、模型类名、updateNode 签名、API client 路径  
> **审查修订:** 2026-06-01 R3 — 修正缓存过期记录唯一约束冲突、down_revision 指向当前 head、依赖安装策略明确化  
> **审查修订:** 2026-06-01 R4 — 缓存写入改为真正 upsert（ON CONFLICT DO UPDATE），响应示例补全 llm_available

---

## 1. 目标

将现有的前端规则引擎 (`dfmeaRules.ts`) 升级为后端编排的混合推荐系统：规则引擎快速评估 + LLM 精细化补充。用户在 FMEA 编辑器中输入时，自动触发推荐，以内联下拉菜单形式展示建议。

### 核心需求

- **触发方式:** 输入自动触发（防抖 500ms）
- **推荐范围:** 4 类推荐，5 种触发类型（效应+原因各一个触发）：
  1. 失败模式 (`failure_mode`)
  2. 失败效应 (`failure_effect`)
  3. 失败原因 (`failure_cause`)
  4. 预防/检测措施 (`measure`)
  5. 优化行动 (`optimization`)
- **智能来源:** 规则引擎优先 → LLM 补充（当规则结果为通用/模糊时）
- **LLM 提供商:** 可配置（Claude / OpenAI / 本地模型），默认仅规则引擎（LLM 为可选增强）
- **缓存:** 按结构化字段缓存，24 小时 TTL，支持按 fmea_id 主动失效
- **回退:** LLM 失败时回退到规则引擎 + 显示错误提示

---

## 2. 架构概览

```
用户输入 → 前端防抖(500ms) + 最小上下文过滤
  → POST /api/fmea/{id}/recommend
    → 权限检查: require_permission(Module.FMEA, PermissionLevel.EDIT)
    → 限流检查: 每用户+每FMEA 滑动窗口
    → RecommendationService
      → 1. 缓存查询 (按 fmea_id + trigger_type + context_hash)
      → 2. 命中 → 返回 cached=true
      → 3. 未命中 → 规则引擎评估
      → 4. 如果结果为 generic 且 LLM 已配置 → 调用 LLM
      → 5. LLM 输出 Pydantic 校验
      → 6. 写入缓存 + 返回
  → 前端显示内联下拉菜单
```

**LLM 未配置时的行为：** 系统默认以"纯规则引擎"模式运行。`LLM_PROVIDER` 环境变量未设置时，规则引擎结果直接返回（即使为 generic），不报错。这保证了零外部依赖的基本可用性。

---

## 3. 后端设计

### 3.1 新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/services/recommendation_service.py` | 推荐服务核心：规则引擎 + LLM 编排 + 缓存 |
| `backend/app/services/llm_provider.py` | LLM 多提供商抽象 + 工厂 |
| `backend/app/schemas/recommendation.py` | 请求/响应 Pydantic 模型 |
| `backend/alembic/versions/20260601_add_recommendation_cache.py` | 缓存表迁移（down_revision: `"028_permission_matrix"`，当前 head） |

### 3.2 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/api/fmea.py` | 实现 `/recommend` 端点（替换 501 stub） |
| `backend/requirements.txt` | 新增 `anthropic`、`openai`、`httpx` 依赖 |

### 3.3 新增依赖

```
# requirements.txt 新增（部署时统一安装，运行时按 LLM_PROVIDER 按需使用）
anthropic>=0.40.0       # Claude API
openai>=1.50.0          # OpenAI API
httpx>=0.27.0           # HTTP 客户端 (LocalProvider + 通用)
```

三个包在 `requirements.txt` 中统一安装，但运行时按 `LLM_PROVIDER` 按需初始化。`LLM_PROVIDER` 未设置时，这些包虽已安装但不会被导入，不影响启动和运行。这样避免了 extras dependency 的复杂性，同时保证部署环境一致性。

### 3.4 API 端点

```
POST /api/fmea/{fmea_id}/recommend
```

**权限:** 使用 `require_permission(Module.FMEA, PermissionLevel.EDIT)`（`core/permissions.py:62`）。注意：现有的 `require_engineer_or_admin` 检查的是 `PermissionLevel.CREATE`，不是 EDIT，因此这里使用精确的权限依赖。Viewer 调用返回 403。

**请求:**
```json
{
  "trigger_type": "failure_mode",
  "context": {
    "function_description": "密封腔体",
    "process_step": "OP30",
    "failure_mode": "密封失效",
    "severity": 8,
    "occurrence": 5,
    "detection": 6
  }
}
```

`context` 中的字段根据 `trigger_type` 不同而变化：

| trigger_type | 必填 context 字段 | 可选 context 字段 |
|---|---|---|
| `failure_mode` | `function_description` | `process_step` |
| `failure_effect` | `failure_mode` | `function_description` |
| `failure_cause` | `failure_mode` | `function_description`, `severity` |
| `measure` | `failure_mode`, `ap` | `severity`, `occurrence`, `detection` |
| `optimization` | `failure_mode`, `severity`, `occurrence`, `detection` | `ap` |

**响应:**
```json
{
  "suggestions": [
    {
      "name": "密封圈老化导致泄漏",
      "confidence": 0.85,
      "source": "llm",
      "explanation": "基于历史 FMEA 数据，DC-DC 产品线密封工序中 72% 的失效模式与此相关"
    }
  ],
  "source": "hybrid",
  "cached": false,
  "llm_available": true
}
```

### 3.5 RecommendationService 核心逻辑

```python
class RecommendationService:
    def __init__(self, db: AsyncSession, llm_provider: LLMProvider | None):
        self.db = db
        self.llm = llm_provider  # 可能为 None（纯规则模式）
        self.rules = RuleEngine()

    async def recommend(self, fmea_id: UUID, request: RecommendRequest) -> RecommendResponse:
        # 0. 获取 FMEA 文档（后续缓存查询和上下文组装都需要）
        fmea = await self._get_fmea_or_404(fmea_id)

        # 1. 检查缓存
        context_hash = self._compute_context_hash(request.context)
        cached = await self._get_cached(fmea_id, request.trigger_type, context_hash)
        if cached:
            return cached

        # 2. 规则引擎评估
        rule_result = self.rules.evaluate(request.trigger_type, request.context)

        # 3. 如果规则结果为 generic 且 LLM 已配置，调用 LLM
        if rule_result.quality == "generic" and self.llm is not None:
            try:
                llm_context = await self._assemble_context(fmea, request)
                llm_result = await asyncio.wait_for(
                    self.llm.complete(
                        prompt=self._build_prompt(request.trigger_type, llm_context),
                        response_schema=SUGGESTION_RESPONSE_SCHEMA
                    ),
                    timeout=settings.LLM_TIMEOUT
                )
                # Pydantic 校验 LLM 输出
                validated = SuggestionList.model_validate(llm_result)
                suggestions = self._merge_results(rule_result.suggestions, validated.suggestions)
                source = "hybrid"
            except (asyncio.TimeoutError, Exception) as e:
                # LLM 失败：回退到规则引擎
                suggestions = rule_result.suggestions
                source = "rule_fallback"
                logger.warning("LLM failed, falling back to rules: %s", e)
        else:
            suggestions = rule_result.suggestions
            source = "rule"

        # 4. 缓存结果
        response = RecommendResponse(
            suggestions=suggestions,
            source=source,
            cached=False,
            llm_available=self.llm is not None
        )
        await self._cache_result(fmea_id, request.trigger_type, context_hash, fmea, response)
        return response
```

### 3.6 规则引擎（从前端迁移）

将 `frontend/src/utils/dfmeaRules.ts` 的逻辑迁移到后端 `recommendation_service.py` 内部：

- `generate_failure_modes(function_desc)` — 中文动词模式匹配
- `suggest_failure_chain(failure_mode)` — 关键词映射
- `suggest_measures(failure_mode, ap)` — AP 等级 + 关键词匹配
- `analyze_risk(s, o, d)` — RPN + AP + 优化提示

每个方法返回 `RuleResult`，包含 `suggestions` 和 `quality`（`"specific"` 或 `"generic"`）。

**质量判定规则：**
- 返回的建议中包含通用占位符（如 "功能降级"、"零部件老化"）→ `generic`
- 所有建议都是具体的、上下文相关的 → `specific`

### 3.7 LLM Provider 抽象

```python
# backend/app/services/llm_provider.py
from typing import Protocol
from pydantic import BaseModel

class LLMProvider(Protocol):
    async def complete(self, prompt: str, response_schema: dict) -> dict: ...

class ClaudeProvider:
    """使用 Anthropic SDK。api_key 从环境变量读取。"""
    def __init__(self, api_key: str, model: str): ...

class OpenAIProvider:
    """使用 OpenAI SDK。api_key 从环境变量读取。"""
    def __init__(self, api_key: str, model: str): ...

class LocalProvider:
    """使用 httpx 调用本地 Ollama/vLLM。"""
    def __init__(self, base_url: str, model: str): ...

def create_llm_provider() -> LLMProvider | None:
    """工厂函数：根据环境变量创建 provider，未配置时返回 None。"""
    provider_name = settings.LLM_PROVIDER
    if not provider_name:
        return None  # 纯规则引擎模式

    api_key = settings.LLM_API_KEY
    if not api_key and provider_name != "local":
        raise ValueError(f"LLM_PROVIDER={provider_name} requires LLM_API_KEY")

    model = settings.LLM_MODEL
    if provider_name == "claude":
        return ClaudeProvider(api_key=api_key, model=model)
    elif provider_name == "openai":
        return OpenAIProvider(api_key=api_key, model=model)
    elif provider_name == "local":
        base_url = settings.LLM_BASE_URL
        if not base_url:
            raise ValueError("LLM_PROVIDER=local requires LLM_BASE_URL")
        return LocalProvider(base_url=base_url, model=model)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider_name}")
```

**启动时配置验证：** 在 FastAPI `lifespan` 中调用 `create_llm_provider()`。如果配置无效（如缺少 API key），记录警告日志并以 `provider=None` 启动（纯规则模式），不阻止服务启动。

**LLM 输出校验：** LLM 返回的 JSON 必须通过 Pydantic 校验：

```python
class SuggestionItem(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = ""

class SuggestionList(BaseModel):
    suggestions: list[SuggestionItem]
```

校验失败时视为 LLM 失败，回退到规则引擎。

**超长输出保护：** LLM 响应体限制 10KB，超出视为异常并回退。

### 3.8 Prompt 模板

```python
PROMPT_TEMPLATES = {
    "failure_mode": """
你是一位资深质量工程师，精通 AIAG-VDA FMEA 方法论。

当前上下文：
- FMEA 类型: {fmea_type}
- 产品线: {product_line}
- 工艺步骤: {process_step}
- 功能描述: {function_description}

历史相似 FMEA 中的失败模式：
{historical_patterns}

请根据以上信息，推荐 3-5 个可能的失败模式。
要求：
1. 具体、可操作，不要泛泛而谈
2. 与当前工艺/功能直接相关
3. 参考历史数据中的真实案例

返回 JSON 格式：
{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}
""",
    # failure_effect, failure_cause, measure, optimization 类似结构
}
```

### 3.9 上下文组装

```python
async def _assemble_context(self, fmea: FMEADocument, request: RecommendRequest) -> dict:
    # 1. 历史相似 FMEA
    historical = await get_similar_fmeas(
        self.db,
        current_fmea_id=fmea.fmea_id,
        fmea_type=fmea.fmea_type,
        product_line_code=fmea.product_line_code,
        limit=5
    )

    # 2. AIAG-VDA 标准知识（硬编码关键规则）
    aiag_rules = get_aiag_vda_rules()

    # 3. 行业知识库
    industry_kb = get_industry_knowledge(fmea.product_line_code)

    return {
        "fmea_type": fmea.fmea_type,
        "product_line": fmea.product_line_code,
        "current_context": request.context,
        "historical_patterns": extract_patterns(historical),
        "aiag_rules": aiag_rules,
        "industry_kb": industry_kb,
    }
```

**`get_similar_fmeas` 查询逻辑：**
```python
async def get_similar_fmeas(
    session: AsyncSession,
    *,
    current_fmea_id: UUID,
    fmea_type: str,
    product_line_code: str,
    limit: int = 5
) -> list["FMEADocument"]:
    """查找同产品线、已批准的 FMEA，按更新时间排序。
    后续可扩展为基于功能描述的向量相似度搜索。"""
    from app.models.fmea import FMEADocument

    stmt = (
        select(FMEADocument)
        .where(FMEADocument.fmea_type == fmea_type)
        .where(FMEADocument.product_line_code == product_line_code)
        .where(FMEADocument.status == "approved")
        .where(FMEADocument.fmea_id != current_fmea_id)
        .order_by(FMEADocument.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

**`extract_patterns` 逻辑：**
从历史 FMEA 的 graph_data 中提取失败模式模式：
```python
def extract_patterns(fmeas: list) -> list[dict]:
    """从历史 FMEA 中提取失败模式、效应、原因的模式。"""
    patterns = []
    for fmea in fmeas:
        nodes = fmea.graph_data.get("nodes", [])
        edges = fmea.graph_data.get("edges", [])
        for node in nodes:
            if node["type"] == "FailureMode":
                effects = [n for n in nodes if n["type"] == "FailureEffect"
                          and any(e["source"] == node["id"] and e["target"] == n["id"]
                                 for e in edges if e["type"] == "EFFECT_OF")]
                causes = [n for n in nodes if n["type"] == "FailureCause"
                         and any(e["source"] == n["id"] and e["target"] == node["id"]
                                for e in edges if e["type"] == "CAUSE_OF")]
                patterns.append({
                    "failure_mode": node["name"],
                    "effects": [e["name"] for e in effects],
                    "causes": [c["name"] for c in causes],
                    "source_doc": fmea.document_no
                })
    return patterns
```

### 3.10 缓存表

```sql
CREATE TABLE recommendation_cache (
    cache_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fmea_id            UUID NOT NULL REFERENCES fmea_documents(fmea_id) ON DELETE CASCADE,
    trigger_type       VARCHAR(20) NOT NULL,
    context_hash       VARCHAR(64) NOT NULL,
    product_line_code  VARCHAR(20) NOT NULL,
    fmea_type          VARCHAR(20) NOT NULL,
    suggestions        JSONB NOT NULL,
    source             VARCHAR(15) NOT NULL,  -- rule | hybrid | rule_fallback
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '24 hours',

    UNIQUE (fmea_id, trigger_type, context_hash)
);

CREATE INDEX ix_recommendation_cache_lookup
    ON recommendation_cache (fmea_id, trigger_type, context_hash, expires_at);
CREATE INDEX ix_recommendation_cache_expires
    ON recommendation_cache (expires_at);
```

**缓存查询：**
```python
async def _get_cached(
    self, fmea_id: UUID, trigger_type: str, context_hash: str
) -> RecommendResponse | None:
    stmt = (
        select(RecommendationCache)
        .where(RecommendationCache.fmea_id == fmea_id)
        .where(RecommendationCache.trigger_type == trigger_type)
        .where(RecommendationCache.context_hash == context_hash)
        .where(RecommendationCache.expires_at > func.now())
    )
    result = await self.db.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
        return RecommendResponse(
            suggestions=row.suggestions,
            source=row.source,
            cached=True,
            llm_available=self.llm is not None
        )
    return None
```

**缓存写入：**

使用 PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`（upsert）处理并发和过期记录冲突。两个并发请求同时未命中缓存时，第二个会更新第一个的写入而非报错。

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def _cache_result(
    self, fmea_id: UUID, trigger_type: str, context_hash: str,
    fmea: "FMEADocument", response: RecommendResponse
) -> None:
    stmt = (
        pg_insert(RecommendationCache)
        .values(
            fmea_id=fmea_id,
            trigger_type=trigger_type,
            context_hash=context_hash,
            product_line_code=fmea.product_line_code,
            fmea_type=fmea.fmea_type,
            suggestions=[s.model_dump() for s in response.suggestions],
            source=response.source,
        )
        .on_conflict_do_update(
            index_elements=["fmea_id", "trigger_type", "context_hash"],
            set_={
                "suggestions": [s.model_dump() for s in response.suggestions],
                "source": response.source,
                "product_line_code": fmea.product_line_code,
                "fmea_type": fmea.fmea_type,
                "created_at": func.now(),
                "expires_at": func.now() + text("INTERVAL '24 hours'"),
            },
        )
    )
    await self.db.execute(stmt)
```

**缓存失效逻辑：**
- **自然过期：** 查询时过滤 `WHERE expires_at > now()`，过期条目不返回
- **主动失效：** FMEA 文档更新时，按 `fmea_id` 删除所有缓存
  ```python
  async def invalidate_cache_for_fmea(self, fmea_id: UUID):
      await self.db.execute(
          delete(RecommendationCache)
          .where(RecommendationCache.fmea_id == fmea_id)
      )
  ```
  调用点：`fmea_service.update_fmea()` 中 `graph_data` 变更后调用
- **级联删除：** 外键 `ON DELETE CASCADE`，FMEA 文档删除时缓存自动清除

### 3.11 限流

**策略：** 滑动窗口限流，基于内存计数器（生产环境可升级为 Redis）。

```python
# 每用户每秒最多 5 次推荐请求
# 每 FMEA 文档每秒最多 20 次推荐请求（防止单文档刷屏）
RATE_LIMITS = {
    "per_user": {"max_requests": 5, "window_seconds": 1},
    "per_fmea": {"max_requests": 20, "window_seconds": 1},
}
```

限流超限返回 429 Too Many Requests。

**前端配合：**
- 防抖 500ms（减少无效请求）
- 仅对有效字段触发（输入 >= 2 字符）
- 仅发送最小必要 context（不同 trigger_type 只发对应必填字段）
- 输入变化时取消前一个未完成的请求（AbortController）

---

## 4. 前端设计

### 4.1 新增文件

| 文件 | 职责 |
|------|------|
| `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx` | 智能建议下拉组件 |
| `frontend/src/api/recommendation.ts` | 前端 API 调用函数 |

注意：放在 `components/dfmea/` 而非 `components/fmea/`，与现有组件目录一致。

### 4.2 SmartSuggestionDropdown 组件

**功能：**
- 挂载在 FMEA 编辑器的可推荐单元格上
- 用户输入停止 500ms 后自动触发 API 调用
- 加载状态：单元格右侧显示小型 spinner
- 下拉菜单：最多 5 个建议，每个带有置信度标签（高/中/低）
- 键盘支持：↑↓ 选择，Enter 应用，Esc 关闭
- 来源标记：规则引擎（齿轮图标）/ LLM（星星图标）
- 回退提示：使用规则引擎回退时显示黄色提示条
- 无 LLM 提示：`llm_available=false` 时显示"仅规则引擎"灰色标签

**Props：**
```typescript
interface SmartSuggestionDropdownProps {
  triggerType: 'failure_mode' | 'failure_effect' | 'failure_cause' | 'measure' | 'optimization';
  context: Record<string, unknown>;  // 当前行的上下文数据
  fmeaId: string;
  onSelect: (suggestion: Suggestion) => void;  // 用户选择建议后的回调
  disabled?: boolean;  // viewer 角色禁用
}
```

### 4.3 逐列接入方案

FMEA 编辑器位于 `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`。现有表格使用 Ant Design `Table` 组件，每列通过 `render` 函数自定义渲染。

**接入方式：** 在可推荐列的 `render` 函数中，将 `SmartSuggestionDropdown` 包裹在 `Input` 外层。

**具体列映射：**

| 列 | trigger_type | context 来源 | 目标节点 | 目标属性 |
|---|---|---|---|---|
| 失败模式 | `failure_mode` | `functionName`, `processNumber` | `FailureMode` | `name` |
| 失败效应 | `failure_effect` | `failureModeName`, `functionName` | `FailureEffect` | `name` |
| 失败原因 | `failure_cause` | `failureModeName`, `functionName` | `FailureCause` | `name` |
| 预防措施 | `measure` | `failureModeName`, `ap` | `PreventionControl` | `name` |
| 检测措施 | `measure` | `failureModeName`, `ap` | `DetectionControl` | `name` |
| 优化行动 | `optimization` | `failureModeName`, S/O/D | `RecommendedAction` | `name` |

**集成示例（失败模式列）：**
```tsx
// 在 FMEAEditorPage.tsx 的 columns 定义中
{
  title: '失效模式',
  dataIndex: 'failureMode',
  render: (_, row) => (
    <SmartSuggestionDropdown
      triggerType="failure_mode"
      context={{
        function_description: row.functionName,
        process_step: row.processNumber,
      }}
      fmeaId={fmeaId}
      onSelect={(s) => {
        // 使用现有的 updateNode(nodeId, field, value) 三参数签名
        updateNode(row.failureModeNodeId, "name", s.name);
      }}
      disabled={isViewer}
    />
  ),
}
```

**`updateNode` 函数（现有签名，位于 FMEAEditorPage.tsx:233）：**
```typescript
const updateNode = useCallback((nodeId: string, field: string, value: unknown) => {
  setNodes((prev) => prev.map((n) => (n.id === nodeId ? { ...n, [field]: value } : n)));
}, []);
```

`SmartSuggestionDropdown` 内部包裹一个 `Input` + 下拉 popover，用户选择建议后调用 `onSelect`，由父组件通过 `updateNode(nodeId, field, value)` 更新 graph 数据。

### 4.4 与现有组件的关系

- `SmartSuggestionDropdown` 替代 `InlineRecommendations`（位于 `frontend/src/components/dfmea/InlineRecommendations.tsx`）
- `InlineRecommendations` 标记为 `@deprecated`，但保留直到新组件稳定
- `dfmeaRules.ts` 标记为 `@deprecated`，后端规则引擎成熟后移除
- `GenerationWizard` 中的推荐调用暂不修改（后续迭代）

### 4.5 API 调用

```typescript
// frontend/src/api/recommendation.ts
import client from "./client";

export interface Suggestion {
  name: string;
  confidence: number;
  source: 'rule' | 'llm';
  explanation: string;
}

export interface RecommendRequest {
  trigger_type: string;
  context: Record<string, unknown>;
}

export interface RecommendResponse {
  suggestions: Suggestion[];
  source: 'rule' | 'hybrid' | 'rule_fallback';
  cached: boolean;
  llm_available: boolean;
}

export async function getRecommendations(
  fmeaId: string,
  request: RecommendRequest,
  signal?: AbortSignal
): Promise<RecommendResponse> {
  const { data } = await client.post(`/fmea/${fmeaId}/recommend`, request, { signal });
  return data;
}
```

---

## 5. 权限

使用现有的权限模型（`core/permissions.py` 中 `Module.FMEA` + `PermissionLevel`）：

| 操作 | 所需权限 | 对应依赖 |
|------|---------|---------|
| 调用推荐接口 | FMEA EDIT | `require_permission(Module.FMEA, PermissionLevel.EDIT)` |
| 查看推荐结果 | 无独立"查看"接口，结果随 POST 返回 | — |

**明确说明：** 当前设计只有一个 `POST /recommend` 端点，不存在独立的"查看"路径。Viewer 调用此端点返回 403，这意味着 Viewer 无法使用智能推荐功能。如果后续需要 Viewer 查看推荐，需新增 `GET /recommend/cached` 端点（只读缓存，不触发 LLM）。

推荐结果不写入审计日志（仅为辅助建议，非数据变更）。

---

## 6. 错误处理

| 场景 | HTTP 状态 | 响应 | 前端行为 |
|------|----------|------|---------|
| LLM 超时 (>LLM_TIMEOUT 秒) | 200 | `source: "rule_fallback"` | 黄色提示条"AI 建议暂不可用，已使用规则引擎" |
| LLM API 错误 | 200 | `source: "rule_fallback"` | 同上 |
| LLM 输出校验失败 | 200 | `source: "rule_fallback"` | 同上 |
| 缓存命中 | 200 | `cached: true` | 无特殊提示 |
| 规则引擎无结果 + 无 LLM | 200 | `suggestions: []` | 显示"暂无建议" |
| 输入太短 (<2 字符) | — | 不发请求 | 无下拉 |
| 权限不足 (viewer) | 403 | 错误信息 | 不触发（前端 disabled） |
| 限流超限 | 429 | 错误信息 | 短暂禁用触发，3 秒后重试 |
| FMEA 不存在 | 404 | 错误信息 | 无下拉 |

---

## 7. 环境变量

```env
# LLM 配置（可选，未设置则以纯规则引擎模式运行）
LLM_PROVIDER=          # claude | openai | local | 留空=纯规则
LLM_API_KEY=           # API key（claude/openai 必填）
LLM_MODEL=             # 模型名称（各 provider 有内部默认值）
LLM_BASE_URL=          # 本地模型 URL（仅 local 模式）
LLM_TIMEOUT=5          # 超时秒数（默认 5）
```

**默认值（代码内部）：**
- `claude` → `claude-sonnet-4-6-20250514`
- `openai` → `gpt-4o`
- `local` → 无默认值，必须指定 `LLM_MODEL`

启动时验证：如果 `LLM_PROVIDER` 有值但配置不完整（如 `claude` 无 `LLM_API_KEY`），记录 `WARNING` 日志并以 `provider=None` 启动。

---

## 8. 未来扩展

以下不在本次实现范围内，但设计时预留了扩展点：

1. **向量相似度搜索：** 历史 FMEA 查询从关键词匹配升级为嵌入向量相似度
2. **批量分析：** 用户点击按钮一次性分析整个文档的所有空行
3. **用户反馈循环：** 记录用户是否采纳建议，用于优化推荐质量
4. **Redis 缓存：** 当前使用 PostgreSQL 缓存，后续可切换到 Redis
5. **流式响应：** LLM 结果逐步返回，减少用户等待感
6. **Viewer 只读推荐：** 新增 `GET /recommend/cached` 端点
