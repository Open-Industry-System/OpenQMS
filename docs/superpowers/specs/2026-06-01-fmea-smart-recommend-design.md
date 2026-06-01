# FMEA 智能推荐升级 — 设计文档

> **状态:** 草稿  
> **日期:** 2026-06-01  
> **范围:** 后端推荐服务 + 前端智能建议下拉组件

---

## 1. 目标

将现有的前端规则引擎 (`dfmeaRules.ts`) 升级为后端编排的混合推荐系统：规则引擎快速评估 + LLM 精细化补充。用户在 FMEA 编辑器中输入时，自动触发推荐，以内联下拉菜单形式展示建议。

### 核心需求

- **触发方式:** 输入自动触发（防抖 500ms）
- **推荐范围:** 失败模式、效应+原因、预防/检测措施、优化行动（全部 4 类）
- **智能来源:** 规则引擎优先 → LLM 补充（当规则结果为通用/模糊时）
- **LLM 提供商:** 可配置（Claude / OpenAI / 本地模型）
- **缓存:** 按输入哈希缓存，24 小时 TTL
- **回退:** LLM 失败时回退到规则引擎 + 显示错误提示

---

## 2. 架构概览

```
用户输入 → 前端防抖(500ms) → POST /api/fmea/{id}/recommend
  → RecommendationService (后端)
    → 1. 规则引擎评估 (快速，无 API 成本)
    → 2. 如果结果为 generic → 调用 LLM
    → 3. 缓存结果 (按输入哈希)
    → 返回结构化建议
  → 前端显示内联下拉菜单
```

---

## 3. 后端设计

### 3.1 新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/services/recommendation_service.py` | 推荐服务核心：规则引擎 + LLM 编排 + 缓存 |
| `backend/app/schemas/recommendation.py` | 请求/响应 Pydantic 模型 |
| `backend/alembic/versions/018_add_recommendation_cache.py` | 缓存表迁移 |

### 3.2 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/api/fmea.py` | 实现 `/recommend` 端点（替换 501 stub） |

### 3.3 API 端点

```
POST /api/fmea/{fmea_id}/recommend
```

**请求:**
```json
{
  "trigger_type": "failure_mode | failure_effect | failure_cause | measure | optimization",
  "context": {
    "function_description": "密封腔体",
    "failure_mode": "密封失效",
    "severity": 8,
    "occurrence": 5,
    "detection": 6,
    "process_step": "OP30"
  }
}
```

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
  "cached": false
}
```

### 3.4 RecommendationService 核心逻辑

```python
class RecommendationService:
    def __init__(self, db: AsyncSession, llm_provider: LLMProvider):
        self.db = db
        self.llm = llm_provider
        self.rules = RuleEngine()

    async def recommend(self, fmea_id: UUID, request: RecommendRequest) -> RecommendResponse:
        # 1. 检查缓存
        cache_key = self._compute_hash(request)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        # 2. 规则引擎评估
        rule_result = self.rules.evaluate(request.trigger_type, request.context)

        # 3. 如果规则结果为 generic，调用 LLM
        if rule_result.quality == "generic":
            context = await self._assemble_context(fmea_id, request)
            llm_result = await self.llm.complete(
                prompt=self._build_prompt(request.trigger_type, context),
                response_schema=SUGGESTION_SCHEMA
            )
            suggestions = self._merge_results(rule_result.suggestions, llm_result.suggestions)
            source = "hybrid"
        else:
            suggestions = rule_result.suggestions
            source = "rule"

        # 4. 缓存结果
        response = RecommendResponse(suggestions=suggestions, source=source, cached=False)
        await self._cache_result(cache_key, response)
        return response
```

### 3.5 规则引擎（从前端迁移）

将 `frontend/src/utils/dfmeaRules.ts` 的逻辑迁移到后端 `recommendation_service.py` 内部：

- `generate_failure_modes(function_desc)` — 中文动词模式匹配
- `suggest_failure_chain(failure_mode)` — 关键词映射
- `suggest_measures(failure_mode, ap)` — AP 等级 + 关键词匹配
- `analyze_risk(s, o, d)` — RPN + AP + 优化提示

每个方法返回 `RuleResult`，包含 `suggestions` 和 `quality`（`"specific"` 或 `"generic"`）。

**质量判定规则：**
- 返回的建议中包含通用占位符（如 "功能降级"、"零部件老化"）→ `generic`
- 所有建议都是具体的、上下文相关的 → `specific`

### 3.6 LLM Provider 抽象

```python
from typing import Protocol

class LLMProvider(Protocol):
    async def complete(self, prompt: str, response_schema: dict) -> dict: ...

class ClaudeProvider:
    """使用 Anthropic SDK"""
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"): ...

class OpenAIProvider:
    """使用 OpenAI SDK"""
    def __init__(self, api_key: str, model: str = "gpt-4o"): ...

class LocalProvider:
    """使用 httpx 调用本地 Ollama/vLLM"""
    def __init__(self, base_url: str, model: str): ...
```

通过环境变量切换：
```env
LLM_PROVIDER=claude          # claude | openai | local
LLM_API_KEY=sk-...
LLM_MODEL=claude-sonnet-4-6  # 可选，有默认值
LLM_BASE_URL=                # 仅 local 模式需要
```

### 3.7 Prompt 模板

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

### 3.8 上下文组装

```python
async def _assemble_context(self, fmea_id: UUID, request: RecommendRequest) -> dict:
    # 1. 当前文档数据
    fmea = await get_fmea(self.db, fmea_id)

    # 2. 历史相似 FMEA
    historical = await get_similar_fmeas(
        self.db,
        fmea_type=fmea.fmea_type,
        product_line_code=fmea.product_line_code,
        limit=5
    )

    # 3. AIAG-VDA 标准知识（硬编码关键规则）
    aiag_rules = get_aiag_vda_rules()

    # 4. 行业知识库
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
    fmea_type: str,
    product_line_code: str,
    limit: int = 5
) -> list[FmeaDocument]:
    """查找同产品线、已批准的 FMEA，按更新时间排序。
    后续可扩展为基于功能描述的向量相似度搜索。"""
    stmt = (
        select(FmeaDocument)
        .where(FmeaDocument.fmea_type == fmea_type)
        .where(FmeaDocument.product_line_code == product_line_code)
        .where(FmeaDocument.status == "approved")
        .where(FmeaDocument.fmea_id != current_fmea_id)  # 排除自身
        .order_by(FmeaDocument.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
```

**`extract_patterns` 逻辑：**
从历史 FMEA 的 graph_data 中提取失败模式模式：
```python
def extract_patterns(fmeas: list[FmeaDocument]) -> list[dict]:
    """从历史 FMEA 中提取失败模式、效应、原因的模式。"""
    patterns = []
    for fmea in fmeas:
        nodes = fmea.graph_data.get("nodes", [])
        edges = fmea.graph_data.get("edges", [])
        for node in nodes:
            if node["type"] == "FailureMode":
                # 找到关联的效应和原因
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

### 3.9 缓存表

```sql
CREATE TABLE recommendation_cache (
    cache_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    input_hash     VARCHAR(64) UNIQUE NOT NULL,
    trigger_type   VARCHAR(20) NOT NULL,
    suggestions    JSONB NOT NULL,
    source         VARCHAR(10) NOT NULL,  -- rule | llm | hybrid
    fmea_type      VARCHAR(20) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '24 hours'
);

CREATE INDEX ix_recommendation_cache_hash ON recommendation_cache (input_hash);
CREATE INDEX ix_recommendation_cache_expires ON recommendation_cache (expires_at);
```

**缓存失效逻辑：**
- **自然过期：** `expires_at` 到期后自动失效（查询时过滤 `WHERE expires_at > now()`）
- **主动失效：** 当 FMEA 文档更新时，删除该文档相关的所有缓存条目
  ```python
  async def invalidate_cache_for_fmea(self, fmea_id: UUID):
      """FMEA 更新时，删除该文档相关的缓存。"""
      await self.db.execute(
          delete(RecommendationCache)
          .where(RecommendationCache.input_hash.contains(str(fmea_id)))
      )
  ```
- **定期清理：** 后台定时任务删除过期条目（可选，PostgreSQL 查询时自然过滤即可）

---

## 4. 前端设计

### 4.1 新增文件

| 文件 | 职责 |
|------|------|
| `frontend/src/components/fmea/SmartSuggestionDropdown.tsx` | 智能建议下拉组件 |
| `frontend/src/api/recommendation.ts` | 前端 API 调用函数 |

### 4.2 SmartSuggestionDropdown 组件

**功能：**
- 挂载在 FMEA 编辑器的可推荐单元格上（失败模式、效应、原因、措施列）
- 用户输入停止 500ms 后自动触发 API 调用
- 加载状态：单元格右侧显示小型 spinner
- 下拉菜单：最多 5 个建议，每个带有置信度标签（高/中/低）
- 键盘支持：↑↓ 选择，Enter 应用，Esc 关闭
- 来源标记：规则引擎（齿轮图标）/ LLM（星星图标）
- 回退提示：使用规则引擎回退时显示黄色提示条

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

**使用示例：**
```tsx
<SmartSuggestionDropdown
  triggerType="failure_mode"
  context={{ function_description: row.functionName, process_step: row.processNumber }}
  fmeaId={fmeaId}
  onSelect={(s) => updateNode(row.failureModeNodeId, { name: s.name })}
  disabled={isViewer}
/>
```

### 4.3 与现有组件的关系

- `SmartSuggestionDropdown` 替代现有的 `InlineRecommendations` 组件
- `dfmeaRules.ts` 标记为 `@deprecated`，后端规则引擎成熟后移除
- `GenerationWizard` 中的推荐调用暂不修改（后续迭代）

### 4.4 API 调用

```typescript
// frontend/src/api/recommendation.ts
export async function getRecommendations(
  fmeaId: string,
  request: RecommendRequest
): Promise<RecommendResponse> {
  const { data } = await api.post(`/fmea/${fmeaId}/recommend`, request);
  return data;
}
```

---

## 5. 权限

- 所有已认证用户（包括 viewer）可以**查看**推荐
- 只有 `quality_engineer` 及以上角色可以**触发**推荐（viewer 触发时返回 403）
- 推荐结果不写入审计日志（仅为辅助建议，非数据变更）

---

## 6. 错误处理

| 场景 | 行为 |
|------|------|
| LLM 超时 (>5s) | 回退到规则引擎结果 + 黄色提示 |
| LLM API 错误 | 回退到规则引擎结果 + 黄色提示 |
| 缓存命中 | 直接返回缓存结果，`cached: true` |
| 规则引擎无结果 | 调用 LLM（跳过规则质量检查） |
| 输入太短 (<2字符) | 不触发推荐，返回空列表 |
| 频率限制 | 前端防抖(500ms) + 后端缓存天然限流；如需更严格限制，可在 Nginx/API Gateway 层配置 |

---

## 7. 环境变量

```env
# LLM 配置
LLM_PROVIDER=claude          # claude | openai | local
LLM_API_KEY=sk-...           # API key
LLM_MODEL=claude-sonnet-4-6  # 模型名称（可选）
LLM_BASE_URL=                # 本地模型 URL（仅 local 模式）
LLM_TIMEOUT=5                # 超时秒数（默认 5）
```

---

## 8. 未来扩展

以下不在本次实现范围内，但设计时预留了扩展点：

1. **向量相似度搜索：** 历史 FMEA 查询从关键词匹配升级为嵌入向量相似度
2. **批量分析：** 用户点击按钮一次性分析整个文档的所有空行
3. **用户反馈循环：** 记录用户是否采纳建议，用于优化推荐质量
4. **Redis 缓存：** 当前使用 PostgreSQL 缓存，后续可切换到 Redis
5. **流式响应：** LLM 结果逐步返回，减少用户等待感
