# 经验教训智能推送 — 设计文档

**日期**: 2026-06-10
**模块**: Phase 4 P3 经验教训智能推送
**状态**: 设计定稿（v3 — 整合第二轮 review）

---

## 目标

新建 FMEA 或 8D/CAPA 时，主动推送历史经验教训，帮助质量工程师避免重复错误、借鉴历史方案。

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据来源 | 已批准 FMEA + 已关闭 CAPA + 审核发现 | 全量覆盖，不遗漏任何教训 |
| 触发时机 | 创建弹窗收集最小上下文 → 提交后立即推送 | 解决请求体为空导致推荐上下文不足的问题 |
| UI 形态 | 混合面板：高匹配卡片 + 分类列表 | 重要教训突出、其余分类可查阅 |
| 匹配策略 | 全混合管道 — lessons 专用 source adapter 层 | 复用 embedding/FusionEngine 思路，不直接套 8D D4/D5 pipeline |
| 产品线策略 | 用户可访问产品线范围内，当前产品线优先 | 不跨权限边界，避免需要额外授权模型 |
| 编辑时推荐 | 不改动，沿用 SmartSuggestionDropdown / D4/D5 推荐 / D7 推荐 | 各系统职责清晰 |
| 缓存策略 | `hash(title + problem_desc + product_line + doc_type)` 作为 cache key，24h TTL，按用户权限隔离（同角色共享） | 新文档 ID 无意义，基于内容 hash 可命中缓存 |
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
│  ├─ navigate 到编辑器（携带 state: { showLessonsLearned: true }）     │
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
  source: string;                  // "fmea_graph + semantic_search + historical_capa + audit_finding + rule"
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

`source` 字段改为详细字符串，列出参与召回的 source 名称（用 `+` 连接），便于前端解释推荐依据。

## 数据流

```
createFMEA / createCAPA 成功
       │
       ▼
navigate 到编辑器（state: { showLessonsLearned: true }）
       │
       ▼
编辑器页面检测 state → 调用 POST /api/{module}/{id}/lessons-learned
       │
       ▼
LessonsLearnedService.recommend()
       │
       ├─ 1. 加载新文档 + 请求体 problem_description
       │      构建 LessonsLearnedContext
       ├─ 2. 多源并行召回（lessons 专用 source adapter）
       │      ├─ HistoricalFMEASource   → 已批准 FMEA 失效模式匹配 ★ 新增
       │      ├─ SemanticSearchSource   → pgvector 语义搜索（通用 adapter）
       │      ├─ HistoricalCAPASource   → 已关闭 8D 根因匹配 ★ 新增
       │      ├─ AuditFindingSource     → 审核发现项 pgvector 匹配 ★ 新增
       │      └─ RuleEngineSource       → 关键词 fallback
       ├─ 3. LessonsFusionEngine 去重 + 排序
       │      └─ 同产品线 +0.10（lessons 专用，不改现有 FusionEngine）
       ├─ 4. 分类：highlights (≥0.7) + 按 source_type 分组
       └─ 5. 返回 LessonsLearnedResponse
```

## 产品线策略

### 核心原则：不跨权限边界

- **检索范围**：仅在用户可访问的产品线内检索（与现有 recommendation_sources 行为一致）
- **同产品线**：confidence + 0.10，排在前
- **其他已授权产品线**：不加成，排在后，标注来源产品线
- **兜底规则**：如果同产品线结果 < 3 条，补充用户有权限的其他产品线结果至至少 5 条

不实施跨权限边界的检索，避免需要额外的授权模型。

## 缓存策略

### 缓存表迁移

`recommendation_cache` 表的 `fmea_id` 是非空外键。为支持 CAPA：

```sql
-- 032_lessons_learned_cache.py
ALTER TABLE recommendation_cache ALTER COLUMN fmea_id DROP NOT NULL;
ALTER TABLE recommendation_cache ADD COLUMN report_id UUID
    REFERENCES capa_eightd(report_id) ON DELETE CASCADE;
-- 新增 lesson context hash 列（可选，复用 context_hash 即可）
```

### Cache Key

- **key**：`context_hash = SHA256(problem_description + product_line_code + doc_type + fmea_type/severity)`
- **查询**：先查 `context_hash` 命中缓存，miss 时走完整召回
- **TTL**：24 小时
- **用户隔离**：不按用户隔离（同产品线、同问题描述的推荐结果一致）。权限过滤在 source 层已保证不返回越权数据。
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
│       │   ├── historical_capa.py      # HistoricalCAPASource
│       │   ├── audit_finding.py        # AuditFindingSource
│       │   ├── semantic.py             # SemanticSearchSource (lessons adapter)
│       │   └── rule_engine.py          # RuleEngineSource (lessons adapter)
│       └── fusion.py                   # LessonsFusionEngine
└── api/
    └── fmea.py                         # 新增 POST /fmea/{id}/lessons-learned
    └── capa.py                         # 新增 POST /capa/{id}/lessons-learned
```

### LessonsLearnedContext

```python
@dataclass
class LessonsLearnedContext:
    """经验教训推送上下文 — 独立于 RecommendationContext。"""
    doc_type: Literal["fmea", "capa"]
    doc_id: uuid.UUID
    query_text: str                 # problem_description 或 title
    fmea_type: str | None           # 仅 FMEA
    severity: str | None            # 仅 CAPA
    product_line_code: str
    user_product_lines: list[str]   # 用户可访问的产品线（用于权限过滤）
    fmea_ref_id: uuid.UUID | None   # CAPA 关联的 FMEA（如有）
```

独立于 `RecommendationContext`（后者是 CAPA D4/D5 专用，stage 只允许 "d4" | "d5"）。

### LessonsSource ABC

```python
class LessonsSource(ABC):
    """经验教训召回源基类。"""
    name: str

    @abstractmethod
    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        ...
```

复用 `RecommendationCandidate` 数据结构（已定义在 `recommendation_types.py`），但不复用现有 Source 类。

### HistoricalFMEASource

新建，处理"新建 FMEA 时从历史已批准 FMEA 全局召回"。

```python
class HistoricalFMEASource:
    """历史 FMEA 失效模式召回源。"""
    name = "fmea_graph"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 查询已批准 FMEA（同产品线优先，补充其他已授权产品线）
        # 2. 遍历 graph_data 中的 FailureMode 节点
        # 3. 关键词匹配 query_text against FailureMode.name / description
        # 4. 提取关联的 FailureCause、PreventionControl、DetectionControl
        # 5. 转换为 RecommendationCandidate
```

### HistoricalCAPASource

新建，处理"已关闭 8D 的根因+措施匹配"。

```python
class HistoricalCAPASource:
    """历史 CAPA 召回源。"""
    name = "historical_capa"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 查询已关闭/已归档 CAPA（status IN D8_CLOSURE, ARCHIVED）
        # 2. 关键词匹配 query_text against d2_description + d4_root_cause
        # 3. 提取 d5_correction 作为 action
        # 4. 转换为 RecommendationCandidate
```

### AuditFindingSource

新建，审核发现项召回。

```python
class AuditFindingSource:
    """审核发现项召回源。pgvector 语义搜索。"""
    name = "audit_finding"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 查询 document_embeddings WHERE entity_type = 'audit_finding'
        #    JOIN audit_findings af ON af.finding_id = entity_id
        #    JOIN audit_plans ap ON af.audit_id = ap.audit_id
        # 2. 过滤：ap.product_line_code IN context.user_product_lines
        # 3. 过滤：只召回有 corrective_action 的已确认/已关闭发现项
        # 4. 按 pgvector 余弦相似度排序
        # 5. 取 ap.product_line_code、ap.plan_no 作为来源字段
        # 6. 转换为 RecommendationCandidate
```

### SemanticSearchSource（lessons adapter）

复用 pgvector 基础设施，但适配 LessonsLearnedContext。

```python
class LessonsSemanticSearchSource:
    """lessons 专用语义搜索 adapter。"""
    name = "semantic_search"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 使用 context.query_text 生成 embedding
        # 2. 查询 document_embeddings（entity_type IN fmea, capa）
        # 3. 过滤产品线权限
        # 4. 转换为 RecommendationCandidate
```

### RuleEngineSource（lessons adapter）

复用 `RuleEngine` 规则引擎（`recommendation_service.py` 中已有），适配 LessonsLearnedContext。

### LessonsFusionEngine

复用 FusionEngine 思路，但 lessons 专用：

```python
class LessonsFusionEngine:
    """lessons 专用去重排序引擎。"""

    SOURCE_PRIORITY = {
        "fmea_graph": 1.0,
        "historical_capa": 0.9,
        "semantic_search": 0.7,
        "audit_finding": 0.6,
        "rule_engine": 0.5,
    }

    PL_BOOST = 0.10  # 同产品线加成（lessons 专用，不改现有 FusionEngine 的 +0.05）
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
- loading 状态：显示 "正在检索相关经验教训..."，**3 秒超时**自动关闭并提示
- 渲染面板（见下方布局）
- "跳过，直接编辑" → 关闭面板
- "查看详情" → 新标签页打开来源文档（所有条目均在权限范围内，无需禁用）
- viewer 角色不弹出
- 全部为空 → "未找到相关经验教训，开始创建吧！" + 自动关闭面板

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
| v3 | 2026-06-10 | 整合第二轮 review：lessons 专用 context/source adapter 层（不直接套 8D pipeline）；创建弹窗新增 problem_description；产品线不跨权限边界；权限用 require_permission；FusionEngine lessons 专用（+0.10 不改现有）；source 字段详细化；缓存按内容 hash 不按用户隔离 |
