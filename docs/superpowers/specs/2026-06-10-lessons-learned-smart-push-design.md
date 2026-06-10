# 经验教训智能推送 — 设计文档

**日期**: 2026-06-10
**模块**: Phase 4 P3 经验教训智能推送
**状态**: 设计定稿（v2 — 整合 review 反馈）

---

## 目标

新建 FMEA 或 8D/CAPA 时，主动推送历史经验教训，帮助质量工程师避免重复错误、借鉴历史方案。

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据来源 | 已批准 FMEA + 已关闭 CAPA + 审核发现 | 全量覆盖，不遗漏任何教训 |
| 触发时机 | 仅创建时推送（编辑时沿用现有推荐系统） | 不侵入编辑器，新增模块只负责"创建时推送" |
| UI 形态 | 混合面板：高匹配卡片 + 分类列表 | 重要教训突出、其余分类可查阅 |
| 匹配策略 | 全混合管道（方案 B） | 复用现有基础设施，匹配准确 |
| 产品线策略 | 当前产品线优先 + 跨产品线降权 | 精准 + 兜底，避免遗漏相似工艺教训 |
| 编辑时推荐 | 不改动，沿用 SmartSuggestionDropdown / D4/D5 推荐 / D7 推荐 | 各系统职责清晰 |
| 产品线权限 | 全局检索 + 动态脱敏（非 DB 级过滤） | 跨产品线教训可见但受控，最大化知识库价值 |
| 缓存策略 | `hash(title + product_line + doc_type)` 作为 cache key | 新文档 ID 无意义，基于内容 hash 可命中缓存 |
| 面板宿主 | 编辑器页面内弹出（navigate 后 state 驱动） | 避免列表页停留卡死，用户已到正确 URL |

## 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  创建流程                                                            │
│                                                                      │
│  FMEAListPage / CAPAListPage                                         │
│  ├─ 用户点击"创建" → 弹窗填写标题/编号/类型                            │
│  ├─ createFMEA() / createCAPA() 成功                                  │
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

## API 设计

### 端点

```
POST /api/fmea/{fmea_id}/lessons-learned
POST /api/capa/{report_id}/lessons-learned
```

请求体为空（从文档 ID 加载上下文）。

### 响应结构

```typescript
interface LessonsLearnedResponse {
  highlights: LessonCard[];        // 1-2 条高匹配（置信度 ≥ 0.7），顶部突出展示
  categories: {
    fmea: LessonCard[];            // 来源：已批准 FMEA 的失效模式+原因+控制
    capa: LessonCard[];            // 来源：已关闭 8D 的根因+措施
    audit: LessonCard[];           // 来源：审核发现项
  };
  source: "hybrid" | "rule_fallback";
  cached: boolean;
}

interface LessonCard {
  id: string;                      // 唯一标识
  title: string;                   // 问题摘要（如 "焊接温度不足导致焊点虚焊"）
  summary: string;                 // 简短描述
  source_type: "fmea" | "capa" | "audit";
  source_document_no: string;      // PFMEA-2026-001 / 8D-2026-003
  source_id: string;               // 可跳转的 UUID
  source_product_line: string;     // 来源产品线
  same_product_line: boolean;      // 是否同产品线
  confidence: number;              // 0.0-1.0
  match_reason: string;            // "相似工艺步骤" / "相同失效模式" / ...
  severity?: string;               // 严重等级（如有，跨 PL 未授权时为 null）
  root_cause?: string;             // 根因摘要（跨 PL 未授权时为 null）
  action?: string;                 // 措施摘要（跨 PL 未授权时为 null）
  can_view_detail: boolean;        // 是否有权限查看来源文档详情
}
```

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
       ├─ 1. 加载新文档，提取上下文
       │      ├─ FMEA: title + fmea_type + product_line_code
       │      └─ CAPA: title + severity + product_line_code（d2_description 此时可能为空）
       ├─ 2. 多源并行召回
       │      ├─ KnowledgeGraphSource   → 图谱相似失效模式匹配
       │      ├─ SemanticSearchSource   → pgvector 语义搜索
       │      ├─ HistoricalCAPASource   → 已关闭 8D 根因匹配
       │      ├─ AuditFindingSource     → ★ 新增：审核发现项 pgvector 匹配
       │      └─ RuleEngineSource       → fallback
       ├─ 3. FusionEngine 去重 + 排序
       │      └─ 产品线 boost：同产品线 +0.10，跨产品线不加成
       ├─ 4. 动态脱敏：跨产品线未授权条目隐藏 severity/root_cause/action
       ├─ 5. 分类：highlights (≥0.7) + 按 source_type 分组
       └─ 6. 返回 LessonsLearnedResponse
```

## 产品线策略

### 权限与脱敏

采用 **全局检索 + 动态脱敏** 策略，而非 DB 级产品线过滤：

1. **检索阶段**：pgvector 相似度搜索不限制产品线，最大化召回
2. **后处理阶段**：`LessonsLearnedService` 对比每条候选的 `product_line_code` 与用户可访问列表
   - **同产品线**：confidence + 0.10，返回完整字段
   - **跨产品线已授权**：confidence + 0.10，返回完整字段
   - **跨产品线未授权**：confidence 不加成，隐藏 `severity`、`root_cause`、`action`（设为 null），`can_view_detail = false`
3. **排序**：同产品线 → 已授权跨产品线 → 未授权跨产品线

### 前端脱敏展示

- 未授权条目显示占位文本："您没有访问该产品线文档的权限"
- "查看详情" 按钮对 `can_view_detail = false` 的条目禁用，tooltip 提示权限不足

### 兜底规则

如果同产品线结果 < 3 条，自动补充已授权跨产品线结果至至少 5 条。

## 缓存策略

### 缓存表迁移

`recommendation_cache` 表的 `fmea_id` 是非空外键。为支持 CAPA：

```sql
ALTER TABLE recommendation_cache ALTER COLUMN fmea_id DROP NOT NULL;
ALTER TABLE recommendation_cache ADD COLUMN report_id UUID
    REFERENCES capa_eightd(report_id) ON DELETE CASCADE;
```

### Cache Key 设计

新文档创建时，文档 ID 是全新的，用 ID 做 key 会导致 100% miss。

- **key 计算**：`hash(title + product_line_code + doc_type + fmea_type/severity)`
- **查询逻辑**：先查 `context_hash` 命中缓存，miss 时走完整召回管道
- **有效期**：24 小时（与现有 `recommendation_cache` 一致）

## 后端新增文件

```
backend/app/
├── schemas/
│   └── lessons_learned.py          # 请求/响应 Pydantic v2 schema
├── services/
│   └── lessons_learned_service.py  # LessonsLearnedService + AuditFindingSource
└── api/
    └── fmea.py                     # 新增 POST /fmea/{id}/lessons-learned
    └── capa.py                     # 新增 POST /capa/{id}/lessons-learned
```

### 迁移文件

```
backend/alembic/
└── 032_lessons_learned_cache.py    # 使 fmea_id 可空 + 添加 report_id
```

### 服务层：LessonsLearnedService

```python
class LessonsLearnedService:
    """创建时经验教训智能推送服务。"""

    def __init__(self, db, llm_provider, embedding_provider, graph_repo):
        # 复用已有 Source
        self.sources = [
            KnowledgeGraphSource(),
            SemanticSearchSource(),
            HistoricalCAPASource(),
            AuditFindingSource(),   # ★ 新增
            RuleEngineSource(),
        ]
        self.fusion = FusionEngine()

    async def recommend(self, doc_id, doc_type, user) -> LessonsLearnedResponse:
        # 1. 加载文档，构建 LessonsLearnedContext
        # 2. 多源并行召回
        # 3. FusionEngine 去重 + 产品线 boost
        # 4. 动态脱敏
        # 5. 分类输出
```

### 上下文构建

```python
@dataclass
class LessonsLearnedContext:
    """经验教训推送上下文。"""
    doc_type: Literal["fmea", "capa"]
    doc_id: uuid.UUID
    query_text: str                 # FMEA: title; CAPA: d2_description or title
    fmea_type: str | None           # 仅 FMEA
    severity: str | None            # 仅 CAPA
    product_line_code: str
    user_product_lines: list[str]   # 用户可访问的产品线列表
    fmea_ref_id: uuid.UUID | None   # CAPA 关联的 FMEA（如有）
    graph_data: dict | None         # FMEA 图数据（如有）
```

query_text 提取逻辑：
- **FMEA**：`title`（创建时唯一有文本内容的字段）
- **CAPA**：优先 `d2_description`，fallback `title`（创建时 d2_description 可能为空）

### 新增 Source：AuditFindingSource

使用 pgvector 语义搜索（非 ILIKE），复用现有 `document_embeddings` 基础设施。

```python
class AuditFindingSource:
    """审核发现项召回源。使用 pgvector 语义搜索。"""
    name = "audit_finding"

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        # 1. 使用 context.query_text 生成 embedding
        # 2. 查询 document_embeddings WHERE entity_type = 'audit_finding'
        #    JOIN audit_findings af ON af.finding_id = entity_id
        #    JOIN audit_plans ap ON af.audit_id = ap.audit_id
        # 3. 按 pgvector 余弦相似度排序
        # 4. 取 ap.product_line_code 和 ap.plan_no 作为来源字段
        # 5. 转换为 RecommendationCandidate
```

注意：
- `audit_findings` 表无 `product_line_code`，需 JOIN `audit_plans` 获取
- `plan_no` 作为 `source_document_no`
- `embedding_sync_worker.py` 已支持 `entity_type = 'audit_finding'`，无需新建同步逻辑

### FusionEngine 扩展

在 `FusionEngine.SOURCE_PRIORITY` 中新增：
```python
"audit_finding": 0.6,
```

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

- `FMEAListPage.tsx`：`handleCreate` 成功后 `navigate(`/fmea/${fmea.fmea_id}`, { state: { showLessonsLearned: true } })`
- `CAPAListPage.tsx`：`handleCreate` 成功后 `navigate(`/capa/${capa.report_id}`, { state: { showLessonsLearned: true } })`
- `FMEAEditorPage.tsx`：检测 `location.state?.showLessonsLearned` → 弹出 Modal
- `CAPADetailPage.tsx`：同上

### LessonsLearnedModal 交互

- Modal 宽度 720px
- loading 状态：显示 "正在检索相关经验教训..."，**3 秒超时**自动关闭并提示 "检索超时，请在编辑过程中使用推荐功能"
- 渲染面板（见下方布局）
- "跳过，直接编辑" 按钮 → 关闭面板
- "查看详情" → 对 `can_view_detail = true` 的条目，新标签页打开来源文档；对 `can_view_detail = false` 的条目，按钮禁用 + tooltip 提示权限不足
- viewer 角色不弹出（不能创建文档）
- 全部为空 → "未找到相关经验教训，开始创建吧！" + 自动关闭面板
- 不持久化偏好，每次都弹出

### 面板布局

```
┌──────────────────────────────────────────────────────────────┐
│  💡 历史经验教训                               [跳过，直接编辑] │
│  基于当前文档，我们找到了以下相关经验，供您参考                    │
├──────────────────────────────────────────────────────────────┤
│  ⚠️ 推荐关注                                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 🔴 标题                                    置信度: XX%  │  │
│  │ 来源 · 产品线 · 严重等级                                  │  │
│  │ 根因: ... | 措施: ...                    [查看详情 →]   │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 🟡 标题                                    置信度: XX%  │  │
│  │ 来源 · 其他产品线 · —                    [权限不足]      │  │
│  │ 根因: 您没有访问该产品线文档的权限                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                              │
│  📋 FMEA 相关经验 (N 条)                          [展开/收起] │
│  🔧 8D 整改经验 (N 条)                            [展开/收起] │
│  ✅ 审核发现 (N 条)                                [展开/收起] │
└──────────────────────────────────────────────────────────────┘
```

## 权限

- POST 端点：`get_current_user`（engineer+ 角色才有创建入口，viewer 角色无法触发）
- 产品线过滤：全局检索 → 后处理阶段动态脱敏
- 跨产品线未授权：隐藏 `severity`、`root_cause`、`action`，`can_view_detail = false`

## 测试策略

- 后端单元测试：每个 Source 独立测试 + FusionEngine 测试 + 动态脱敏测试
- API 测试：POST 端点正常/空结果/权限拒绝/跨产品线脱敏
- 前端：面板渲染 + 跳过 + 空状态 + 超时 + 未授权条目展示

## 不在范围内

- 编辑时推荐（已有系统处理）
- 用户反馈/评分机制（未来扩展）
- 推送历史记录持久化（未来扩展）
- LLM 摘要生成（未来扩展，当前只做结构化数据展示）

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1 | 2026-06-10 | 初稿 |
| v2 | 2026-06-10 | 整合 review 反馈：通用化上下文、AuditFindingSource 用 pgvector、全局检索+动态脱敏、缓存迁移、编辑器内弹出、超时处理、权限控制 |
