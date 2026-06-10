# 经验教训智能推送 — 设计文档

**日期**: 2026-06-10
**模块**: Phase 4 P3 经验教训智能推送
**状态**: 设计定稿（v6 — 整合第五轮 review）

---

## 目标

新建 FMEA 或 8D/CAPA 时，主动推送历史经验教训，帮助质量工程师避免重复错误、借鉴历史方案。

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据来源 | 已批准 FMEA + 已关闭 CAPA + 审核发现 | 全量覆盖，不遗漏任何教训 |
| 触发时机 | 创建弹窗收集最小上下文 → 提交后立即推送 | 解决请求体为空导致推荐上下文不足的问题 |
| UI 形态 | 混合面板：高匹配卡片 + 分类列表 | 重要教训突出、其余分类可查阅 |
| 匹配策略 | lessons 专用 context + source adapter 层 | 复用 embedding/candidate 结构和 FusionEngine 思路，不复用现有 Source 类 |
| 产品线策略 | 用户可访问产品线范围内，当前产品线优先 | 不跨权限边界，避免需要额外授权模型 |
| 编辑时推荐 | 不改动，沿用 SmartSuggestionDropdown / D4/D5 推荐 / D7 推荐 | 各系统职责清晰 |
| 缓存策略 | content hash key 包含 allowed_pls_hash + 24h TTL，按用户可访问产品线集隔离 | 缓存 key 包含产品线集合 hash，避免不同权限用户共享缓存导致越权 |
| 面板宿主 | 编辑器页面内弹出（navigate 后 state 驱动） | 避免列表页停留卡死，用户已到正确 URL |

## 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  创建流程                                                            │
│                                                                      │
│  FMEAListPage / CAPAListPage                                         │
│  ├─ 用户点击"创建" → 弹窗填写标题/编号/类型 + 最小上下文              │
│  │      ├─ FMEA: title, document_no, fmea_type, problem_description │
│  │      └─ CAPA: title, document_no, severity, problem_description  │
│  ├─ createFMEA(values) / createCAPA(values) 成功                     │
│  ├─ navigate 到编辑器（携带 state: { showLessonsLearned: true,       │
│  │                       problemDescription }）                      │
│  │                                                                    │
│  ▼                                                                    │
│  FMEAEditorPage / CAPADetailPage（编辑器页面）                        │
│  ├─ 检测 location.state.showLessonsLearned                            │
│  ├─ ★ 弹出 LessonsLearnedModal（经验教训面板）                        │
│  │   ├─ "跳过，直接编辑" → 关闭面板                                   │
│  │   └─ 查看经验 → 可选跳转来源文档（新标签页）                         │
│  └─ 关闭面板，用户正常编辑                                             │
│                                                                      │
│  编辑时（不改动）                                                      │
│  ├─ SmartSuggestionDropdown（FMEA 内联推荐）                           │
│  ├─ D4/D5 推荐面板（8D）                                              │
│  └─ D7 预防复发推荐（8D）                                             │
└─────────────────────────────────────────────────────────────────────┘
```

### 创建弹窗新增字段

现有弹窗只收集标题/编号/类型。为提供足够推荐上下文，在创建弹窗中新增一个可选字段：

**FMEA 创建弹窗**：
```
标题: [________]
编号: [________]
类型: [PFMEA ▼]
问题描述（可选）: [____________]   ← 新增：简述工艺步骤或关注点，用于推荐
```

**CAPA 创建弹窗**：
```
标题: [________]
编号: [________]
严重等级: [严重 ▼]
期限: [________]
问题描述（可选）: [____________]   ← 新增：简述问题现象，用于推荐
```

`problem_description` 是可选的。如果为空，后端 fallback 到 `title`。

## API 设计

### 端点

```
POST /api/fmea/{fmea_id}/lessons-learned
POST /api/capa/{report_id}/lessons-learned
```

### 请求体

```json
{
  "problem_description": "焊接温度异常导致 BMS 模块失效"
}
```

可选字段。为空时后端从文档 title fallback。

### 响应结构

```typescript
interface LessonsLearnedResponse {
  highlights: LessonCard[];        // 1-2 条高匹配（置信度 ≥ 0.7），顶部突出展示
  categories: {
    fmea: LessonCard[];            // 来源：已批准 FMEA 的失效模式+原因+控制
    capa: LessonCard[];            // 来源：已关闭 8D 的根因+措施
    audit: LessonCard[];           // 来源：审核发现项
  };
  source: string;                  // 详细列出参与召回的 source 名称，用 " + " 连接
                                   // 如 "historical_fmea + semantic_search + historical_capa"
  cached: boolean;
}

interface LessonCard {
  id: string;                      // 唯一标识
  title: string;                   // 问题摘要
  summary: string;                 // 简短描述
  source_type: "fmea" | "capa" | "audit";
  source_document_no: string;      // PFMEA-2026-001 / 8D-2026-003
  source_id: string;               // 可跳转的 UUID
  source_product_line: string;     // 来源产品线
  same_product_line: boolean;      // 是否同产品线
  confidence: number;              // 0.0-1.0
  match_reason: string;            // "相似工艺步骤" / "相同失效模式" / ...
  root_cause?: string;             // 根因摘要
  action?: string;                 // 措施摘要
  severity?: string;               // 严重等级
}
```

`source` 字段为详细字符串，列出参与召回的 source 名称（用 ` + ` 连接），便于前端解释推荐依据。

## 数据流

```
createFMEA / createCAPA 成功
       │
       ▼
navigate 到编辑器（state: { showLessonsLearned: true, problemDescription }）
       │
       ▼
编辑器页面检测 state → 调用 POST /api/{module}/{id}/lessons-learned
       │
       ▼
LessonsLearnedService.recommend()
       │
       ├─ 1. 加载新文档 + 请求体 problem_description
       │      构建 LessonsLearnedContext（独立于 RecommendationContext）
       ├─ 2. 多源并行召回（lessons 专用 source adapter）
       │      ├─ HistoricalFMEASource   → 已批准 FMEA 失效模式匹配
       │      ├─ LessonsSemanticSource  → pgvector 语义搜索（lessons adapter）
       │      ├─ LessonsCAPASource      → 已关闭 8D 根因匹配（lessons adapter）
       │      ├─ AuditFindingSource     → 审核发现项 pgvector 匹配
       │      └─ LessonsRuleSource      → 关键词 fallback
       ├─ 3. LessonsFusionEngine 去重 + 排序
       │      └─ 同产品线 +0.10（lessons 专用，不改现有 FusionEngine 的 +0.05）
       ├─ 4. 分类：highlights (≥0.7) + 按 source_type 分组
       └─ 5. 返回 LessonsLearnedResponse
```

## 产品线策略

### 核心原则：不跨权限边界

- **检索范围**：仅在用户可访问的产品线内检索（与现有 recommendation_sources 行为一致）
- **"跨产品线"定义**：指用户有权限访问的其他产品线，不是跨越权限边界
- **同产品线**：confidence + 0.10，排在前
- **其他已授权产品线**：不加成，排在后，标注来源产品线
- **兜底规则**：如果同产品线结果 < 3 条，补充用户有权限的其他产品线结果至至少 5 条

不实施跨权限边界的检索。不返回用户无权访问的产品线数据（即使脱敏后也不返回）。

## 缓存策略

### 缓存表迁移

`recommendation_cache` 表的 `fmea_id` 是非空外键。为支持 CAPA，需要改动表结构。

**PostgreSQL NULL + UNIQUE 陷阱**：当 `fmea_id` 设为可空后，PostgreSQL 多列唯一约束在任一列为 NULL 时不视为冲突。这会导致 `on_conflict_do_update`（UPSERT）无法命中 CAPA 记录，不断插入重复数据。

**同步更新 ORM 模型**：

迁移文件外，还需同步修改 `backend/app/models/recommendation_cache.py`：
- `fmea_id`: `nullable=False` → `nullable=True`
- `fmea_type`: `nullable=False` → `nullable=True`
- `source`: `String(15)` → `String(100)`
- 新增 `report_id: Mapped[uuid.UUID | None]`（nullable，FK capa_eightd）
- 新增 `doc_type: Mapped[str]`（存储目标文档类型 "fmea" | "capa"，NOT NULL，default='fmea'）
  - lessons global cache 也用这个字段标记目标文档类型（fmea 或 capa），不额外使用 "lesson" 值；是否为 lessons cache 由 `trigger_type = "lessons_learned"` 表达
- 删除 `__table_args__` 中的 `UniqueConstraint`（旧约束已删除，由部分唯一索引替代）

**现有 FMEA 推荐缓存的 UPSERT 同步更新**：

`backend/app/services/recommendation_service.py` 中 `_cache_result()` 使用 `on_conflict_do_update(index_elements=["fmea_id", "trigger_type", "context_hash"])`。部分唯一索引需要额外指定 `index_where`，否则 UPSERT 会报 "no unique constraint matching"。

修改后的 `_cache_result()` 需根据 cache 类型指定不同的 `index_elements` 和 `index_where`：
- **FMEA cache**：`index_elements=["fmea_id", "trigger_type", "context_hash"]`，`index_where=RecommendationCache.fmea_id.isnot(None)`
- **CAPA cache**：`index_elements=["report_id", "trigger_type", "context_hash"]`，`index_where=RecommendationCache.report_id.isnot(None)`
- **Lessons global cache**：`index_elements=["trigger_type", "context_hash"]`，`index_where=RecommendationCache.fmea_id.is_(None) & RecommendationCache.report_id.is_(None)`

**解决方案：部分唯一索引（Partial Unique Indexes）**

```sql
-- 032_lessons_learned_cache.py

-- 1. 使 fmea_id 可空
ALTER TABLE recommendation_cache ALTER COLUMN fmea_id DROP NOT NULL;

-- 2. 添加 report_id 列
ALTER TABLE recommendation_cache ADD COLUMN report_id UUID
    REFERENCES capa_eightd(report_id) ON DELETE CASCADE;

-- 3. 删除旧的唯一约束
ALTER TABLE recommendation_cache DROP CONSTRAINT IF EXISTS uq_recommendation_cache_lookup;

-- 4. 扩展 source 列长度
ALTER TABLE recommendation_cache ALTER COLUMN source TYPE VARCHAR(100);

-- 5. 使 fmea_type 可空（CAPA/global cache 无 fmea_type）
ALTER TABLE recommendation_cache ALTER COLUMN fmea_type DROP NOT NULL;

-- 6. 新增 doc_type 列，存储目标文档类型 "fmea" | "capa"
ALTER TABLE recommendation_cache ADD COLUMN doc_type VARCHAR(20) DEFAULT 'fmea';
UPDATE recommendation_cache SET doc_type = 'fmea' WHERE doc_type IS NULL;
ALTER TABLE recommendation_cache ALTER COLUMN doc_type SET NOT NULL;

-- 7. 创建三个部分唯一索引，分别覆盖不同场景
-- FMEA 内联推荐场景：fmea_id 非空时，(fmea_id, trigger_type, context_hash) 唯一
CREATE UNIQUE INDEX uq_cache_fmea
    ON recommendation_cache (fmea_id, trigger_type, context_hash)
    WHERE fmea_id IS NOT NULL;

-- CAPA D4/D5 推荐场景：report_id 非空时，(report_id, trigger_type, context_hash) 唯一
CREATE UNIQUE INDEX uq_cache_capa
    ON recommendation_cache (report_id, trigger_type, context_hash)
    WHERE report_id IS NOT NULL;

-- Lessons 全局缓存场景：fmea_id IS NULL AND report_id IS NULL 时，(trigger_type, context_hash) 唯一
-- lessons 按内容 hash 共享缓存（不按文档 ID），trigger_type 固定为 "lessons_learned"
CREATE UNIQUE INDEX uq_cache_global
    ON recommendation_cache (trigger_type, context_hash)
    WHERE fmea_id IS NULL AND report_id IS NULL;
```

### Cache Key

- **key**：`context_hash = SHA256(problem_description + product_line_code + doc_type + fmea_type/severity + sorted(user_product_lines_or_sentinel))`
- `sorted(user_product_lines)` 确保相同产品线集合产生相同 hash，避免顺序差异导致 miss
- **admin 处理**：admin（bypass RLS，user_product_lines 为 None）使用固定 sentinel `"__ALL_PRODUCT_LINES__"`，与有权限列表的用户隔离
- **查询**：先查 `context_hash` 命中缓存，miss 时走完整召回
- **写入**：lessons 缓存写入 `fmea_id IS NULL AND report_id IS NULL` 的行（全局缓存，不按文档 ID 隔离），`trigger_type` 固定为 `"lessons_learned"`
- **TTL**：24 小时（与现有 `recommendation_cache` 一致）
- **隔离规则**：cache key 包含用户可访问产品线集合的 hash。不同产品线权限的用户不会命中同一缓存条目，避免越权。同角色用户如果可访问的产品线集合相同，可以共享缓存。
- **失效**：新 FMEA/CAPA 审批状态变更时，不清除此缓存（lessons 是创建时快照，不需要实时更新）

## 后端架构

### 模块划分

```
backend/app/
├── schemas/
│   └── lessons_learned.py              # 请求/响应 Pydantic v2 schema
├── services/
│   └── lessons_learned/
│       ├── __init__.py
│       ├── context.py                  # LessonsLearnedContext
│       ├── service.py                  # LessonsLearnedService
│       ├── sources/
│       │   ├── __init__.py
│       │   ├── base.py                 # LessonsSource ABC
│       │   ├── historical_fmea.py      # HistoricalFMEASource
│       │   ├── historical_capa.py      # LessonsCAPASource
│       │   ├── audit_finding.py        # AuditFindingSource
│       │   ├── semantic.py             # LessonsSemanticSource
│       │   └── rule_engine.py          # LessonsRuleSource
│       └── fusion.py                   # LessonsFusionEngine
└── api/
    └── fmea.py                         # 新增 POST /fmea/{id}/lessons-learned
    └── capa.py                         # 新增 POST /capa/{id}/lessons-learned
```

### LessonsLearnedContext

```python
@dataclass
class LessonsLearnedContext:
    """经验教训推送上下文 — 独立于 RecommendationContext（后者是 CAPA D4/D5 专用）。"""
    doc_type: Literal["fmea", "capa"]
    doc_id: uuid.UUID
    query_text: str                 # problem_description 或 title（fallback）
    fmea_type: str | None           # 仅 FMEA
    severity: str | None            # 仅 CAPA
    product_line_code: str
    user_product_lines: list[str] | None   # 用户可访问的产品线（None = admin 全权限）
    fmea_ref_id: uuid.UUID | None   # CAPA 关联的 FMEA（如有）
```

独立于 `RecommendationContext`（后者 stage 只允许 "d4" | "d5"，capa_data 依赖 d2_description/d4_root_cause）。

### LessonsSource ABC

```python
class LessonsSource(ABC):
    """经验教训召回源基类。"""
    name: str

    @abstractmethod
    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        ...
```

复用 `RecommendationCandidate` 数据结构（已定义在 `recommendation_types.py`），但不复用现有 Source 类（现有 Source 依赖 `RecommendationContext` 和 CAPA D4/D5 字段）。

### HistoricalFMEASource

新建。从历史已批准 FMEA 的 graph_data 中召回匹配的失效模式+原因+控制。

```python
class HistoricalFMEASource:
    """历史 FMEA 失效模式召回源。"""
    name = "historical_fmea"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 查询已批准 FMEA（status='approved'，product_line_code IN context.user_product_lines）
        # 2. 遍历 graph_data 中的 FailureMode 节点
        # 3. 关键词匹配 context.query_text against FailureMode.name / description
        # 4. 提取关联的 FailureCause、PreventionControl、DetectionControl
        # 5. 同产品线 confidence 0.7，其他已授权产品线 confidence 0.5
        # 6. 转换为 RecommendationCandidate
```

### LessonsCAPASource

新建。从已关闭/已归档 CAPA 中召回匹配的根因+措施。

```python
class LessonsCAPASource:
    """历史 CAPA 召回源。"""
    name = "historical_capa"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 查询已关闭/已归档 CAPA（status IN ('D8_CLOSURE', 'ARCHIVED')）
        #    product_line_code IN context.user_product_lines
        # 2. pgvector 语义搜索 d2_description（entity_type='capa', entity_field='d2_description'）
        # 3. 提取 d4_root_cause 作为 root_cause，d5_correction 作为 action
        # 4. 转换为 RecommendationCandidate
```

### AuditFindingSource

新建。审核发现项召回，使用 pgvector 语义搜索。

```python
class AuditFindingSource:
    """审核发现项召回源。pgvector 语义搜索。"""
    name = "audit_finding"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. pgvector 查询 document_embeddings WHERE entity_type = 'audit_finding'
        # 2. JOIN audit_findings af ON af.finding_id = de.entity_id
        # 3. JOIN audit_plans ap ON af.audit_id = ap.audit_id
        # 4. 过滤：ap.product_line_code IN context.user_product_lines
        # 5. 过滤：只召回 af.corrective_action IS NOT NULL 的已确认/已关闭发现项
        # 6. 按 pgvector 余弦相似度排序
        # 7. 取 ap.product_line_code、ap.plan_no 作为来源字段
        # 8. 转换为 RecommendationCandidate
```

注意：
- `audit_findings` 表无 `product_line_code`，需 JOIN `audit_plans` 获取
- `plan_no` 作为 `source_document_no`
- `embedding_sync_worker.py` 已支持 `entity_type = 'audit_finding'`，无需新建同步逻辑

### LessonsSemanticSource

lessons 专用语义搜索 adapter。复用 pgvector 基础设施，但适配 LessonsLearnedContext。

```python
class LessonsSemanticSearchSource:
    """lessons 专用语义搜索 adapter。"""
    name = "semantic_search"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 使用 context.query_text 生成 embedding
        # 2. 查询 document_embeddings（entity_type IN ('fmea_node', 'capa')）
        #    注意：FMEA embedding 的 entity_type 是 'fmea_node'（不是 'fmea'）
        # 3. 过滤产品线权限
        # 4. FMEA 结果需从 metadata.node_type 或 node_id 回溯 graph_data 组装 LessonCard
        # 5. 转换为 RecommendationCandidate
```

### LessonsRuleSource

lessons 专用规则引擎 adapter。复用 `RuleEngine`（`recommendation_service.py`），适配 LessonsLearnedContext。

```python
class LessonsRuleSource:
    """lessons 专用规则引擎 fallback。"""
    name = "rule_engine"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 使用 RuleEngine.evaluate("failure_mode", {"input_text": context.query_text})
        # 2. 转换为 RecommendationCandidate
```

### LessonsFusionEngine

lessons 专用去重排序引擎。复用 FusionEngine 思路，但独立实现。

```python
class LessonsFusionEngine:
    """lessons 专用去重排序引擎。"""

    SOURCE_PRIORITY = {
        "historical_fmea": 1.0,
        "historical_capa": 0.9,
        "semantic_search": 0.7,
        "audit_finding": 0.6,
        "rule_engine": 0.5,
    }

    PL_BOOST = 0.10  # 同产品线加成（lessons 专用）
    # 注意：现有 FusionEngine 使用 +0.05，不修改

    def merge(self, candidates: list[RecommendationCandidate],
              product_line_code: str) -> list[RecommendationCandidate]:
        # 1. 来源优先级归一化 + 同产品线 bonus
        # 2. 去重（归一化文本匹配）
        # 3. 截断 Top 10
```

### 权限

FMEA lessons endpoint：
```python
@router.post("/{fmea_id}/lessons-learned")
async def get_fmea_lessons(
    fmea_id: UUID,
    body: LessonsLearnedRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
) -> LessonsLearnedResponse:
    ...
```

CAPA lessons endpoint：
```python
@router.post("/{report_id}/lessons-learned")
async def get_capa_lessons(
    report_id: UUID,
    body: LessonsLearnedRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
) -> LessonsLearnedResponse:
    ...
```

若 endpoint 引用 FMEA 历史数据（FMEA source 参与召回），还需额外检查 `Module.FMEA VIEW` 权限。

## 前端新增文件

```
frontend/src/
├── components/
│   └── lessons/
│       └── LessonsLearnedModal.tsx   # 模态框面板
├── types/
│   └── index.ts                      # 新增 LessonsLearnedResponse 等类型
└── api/
    └── lessonsLearned.ts             # getFMEALessons / getCAPALessons
```

### 触发点

- `FMEAListPage.tsx`：`handleCreate` 成功后 `navigate(`/fmea/${fmea.fmea_id}`, { state: { showLessonsLearned: true, problemDescription } })`
- `CAPAListPage.tsx`：`handleCreate` 成功后 `navigate(`/capa/${capa.report_id}`, { state: { showLessonsLearned: true, problemDescription } })`
- `FMEAEditorPage.tsx`：检测 `location.state?.showLessonsLearned` → 弹出 Modal
- `CAPADetailPage.tsx`：同上

### 创建弹窗变更

FMEA 创建弹窗新增可选字段 `problem_description`（Ant Design Input.TextArea，2 行，placeholder="简述工艺步骤或关注点（可选，用于智能推荐）"）。

CAPA 创建弹窗同理。

### LessonsLearnedModal 交互

- Modal 宽度 720px
- loading 状态：显示 "正在检索相关经验教训..."，**10 秒超时**自动关闭并提示 "检索超时，请稍后在编辑过程中使用推荐功能"
  - embedding/pgvector/多源并行在冷启动或本地环境可能较慢，3 秒过于激进
- 渲染面板（见下方布局）
- "跳过，直接编辑" → 关闭面板
- "查看详情" → 新标签页打开来源文档（所有条目均在权限范围内，无需禁用）
- viewer 角色不弹出
- 全部为空 → "未找到相关经验教训，开始创建吧！" + 自动关闭面板
- **注意**：弹窗状态通过 `location.state` 传递，页面刷新后 state 丢失，弹窗不会恢复。这是可接受的行为——创建后的一次性提醒，刷新后不再重复弹出。

### 面板布局

```
┌──────────────────────────────────────────────────────────────┐
│  💡 历史经验教训                               [跳过，直接编辑] │
│  基于当前文档，我们找到了以下相关经验，供您参考                    │
├──────────────────────────────────────────────────────────────┤
│  ⚠️ 推荐关注                                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 🔴 标题                                    置信度: XX%  │  │
│  │ PFMEA-2026-005 · DC-DC-100 · 致命                       │  │
│  │ 根因: ... | 措施: ...                    [查看详情 →]   │  │
│  │ 推荐依据: 相似工艺 + 相同产品线                           │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 🟡 标题                                    置信度: XX%  │  │
│  │ 8D-2026-012 · DC-DC-100 · 严重                          │  │
│  │ 根因: ... | 措施: ...                    [查看详情 →]   │  │
│  │ 推荐依据: 语义搜索 + 相同产品线                           │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                              │
│  📋 FMEA 相关经验 (N 条)                          [展开/收起] │
│  🔧 8D 整改经验 (N 条)                            [展开/收起] │
│  ✅ 审核发现 (N 条)                                [展开/收起] │
└──────────────────────────────────────────────────────────────┘
```

每张卡片显示 `match_reason`，便于前端解释推荐依据。

## 测试策略

- 后端单元测试：每个 Source 独立测试 + LessonsFusionEngine 测试 + 缓存测试
- API 测试：POST 端点正常/空结果/权限拒绝/缓存命中
- 前端：面板渲染 + 跳过 + 空状态 + 超时 + 创建弹窗新字段

## 不在范围内

- 编辑时推荐（已有系统处理）
- 用户反馈/评分机制（未来扩展）
- 推送历史记录持久化（未来扩展）
- LLM 摘要生成（未来扩展）

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1 | 2026-06-10 | 初稿 |
| v2 | 2026-06-10 | 整合第一轮 review：通用化上下文、AuditFindingSource 用 pgvector、全局检索+动态脱敏、缓存迁移、编辑器内弹出、超时、权限控制 |
| v3 | 2026-06-10 | 整合第二轮 review：lessons 专用 context/source adapter 层；创建弹窗新增 problem_description；产品线不跨权限边界；权限用 require_permission；FusionEngine lessons 专用（+0.10 不改现有）；source 字段详细化；缓存按内容 hash 不按用户隔离 |
| v4 | 2026-06-10 | 整合第三轮 review：修正请求体空问题（problem_description 可选 + title fallback）；明确 HistoricalFMEASource 独立于 FMEAGraphSource；明确 lessons 专用 source adapter 不复用现有 Source 类；产品线策略明确"不跨权限边界"=不返回无权数据；AuditFindingSource 明确 JOIN + 只召回有 corrective_action 的发现项；缓存策略补充 TTL/用户隔离说明；FusionEngine +0.10 与现有 +0.05 并存；source 字段详细列出参与的 source 名称 |
| v5 | 2026-06-10 | 整合第四轮 review：cache key 加入 sorted(user_product_lines) 防止缓存越权；统一缓存隔离规则为"按可访问产品线集合隔离"；HistoricalFMEASource name 改为 historical_fmea（不与 FMEAGraphSource 的 fmea_graph 冲突）；LessonsSemanticSource entity_type 改为 ('fmea_node', 'capa')；超时从 3s 改为 10s；明确刷新页面后弹窗不恢复 |
| v6 | 2026-06-10 | 整合第五轮 review：修正旧约束名 uq_recommendation_cache_lookup；lessons 缓存使用全局模式（fmea_id IS NULL + report_id IS NULL），与旧 FMEA/CAPA 缓存分离；source 列扩为 VARCHAR(100)；fmea_type 改为可空 + 新增 doc_type 列；user_product_lines 改为 list[str] | None，admin sentinel "__ALL_PRODUCT_LINES__" |
