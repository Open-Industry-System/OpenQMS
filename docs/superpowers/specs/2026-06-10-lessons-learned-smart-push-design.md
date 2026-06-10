# 经验教训智能推送 — 设计文档

**日期**: 2026-06-10
**模块**: Phase 4 P3 经验教训智能推送
**状态**: 设计中

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

## 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  创建流程                                                            │
│                                                                      │
│  FMEAListPage / CAPAListPage                                         │
│  ├─ 用户点击"创建" → 弹窗填写标题/编号/类型                            │
│  ├─ createFMEA() / createCAPA() 成功                                  │
│  ├─ ★ 弹出 LessonsLearnedModal（经验教训面板）                        │
│  │   ├─ "跳过，直接编辑" → 关闭面板，导航到编辑器                       │
│  │   └─ 查看经验 → 可选跳转来源文档（新标签页）                         │
│  └─ 关闭面板 → navigate 到编辑器                                       │
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
  confidence: number;              // 0.0-1.0
  match_reason: string;            // "相似工艺步骤" / "相同失效模式" / ...
  severity?: string;               // 严重等级（如有）
  root_cause?: string;             // 根因摘要
  action?: string;                 // 措施摘要
}
```

## 数据流

```
createFMEA / createCAPA 成功
       │
       ▼
前端调用 POST /api/{module}/{id}/lessons-learned
       │
       ▼
LessonsLearnedService.recommend()
       │
       ├─ 1. 加载新文档，提取上下文（标题 + fmea_type/severity + 产品线）
       ├─ 2. 多源并行召回
       │      ├─ KnowledgeGraphSource   → 图谱相似失效模式匹配
       │      ├─ SemanticSearchSource   → pgvector 语义搜索
       │      ├─ HistoricalCAPASource   → 已关闭 8D 根因匹配
       │      ├─ AuditFindingSource     → ★ 新增：审核发现项匹配
       │      └─ RuleEngineSource       → fallback
       ├─ 3. FusionEngine 去重 + 排序
       │      └─ 产品线 boost：同产品线 +0.10，跨产品线不加成
       ├─ 4. 分类：highlights (≥0.7) + 按 source_type 分组
       └─ 5. 返回 LessonsLearnedResponse
```

## 产品线策略

- **同产品线**：confidence + 0.10，排在前
- **跨产品线**：不加成，排在同产品线之后，标注来源产品线
- **兜底规则**：如果同产品线结果 < 3 条，自动补充跨产品线结果至至少 5 条

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
        # 1. 加载文档，提取上下文
        # 2. 多源并行召回
        # 3. FusionEngine 去重 + 产品线 boost
        # 4. 分类输出
```

### 新增 Source：AuditFindingSource

唯一需要新建的 Source。复用 `AuditFinding` 模型。

```python
class AuditFindingSource:
    """审核发现项召回源。"""
    name = "audit_finding"

    async def retrieve(self, context) -> list[RecommendationCandidate]:
        # 1. 从上下文提取关键词
        # 2. 查询 audit_findings 表（description ILIKE）
        # 3. 过滤产品线权限
        # 4. 转换为 RecommendationCandidate
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

- `FMEAListPage.tsx`：`handleCreate` 中 `createFMEA()` 成功后、`navigate` 前弹出
- `CAPAListPage.tsx`：`handleCreate` 中 `createCAPA()` 成功后、`navigate` 前弹出

### LessonsLearnedModal 交互

- Modal 宽度 720px
- loading 状态：显示 "正在检索相关经验教训..."
- 渲染面板（见下方布局）
- "跳过，直接编辑" 按钮 → 关闭面板，navigate 到编辑器
- "查看详情" → 新标签页打开来源文档
- viewer 角色不弹出（不能创建文档）
- 全部为空 → "未找到相关经验教训，开始创建吧！" + 自动导航到编辑器
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
│                                                              │
│  📋 FMEA 相关经验 (N 条)                          [展开/收起] │
│  🔧 8D 整改经验 (N 条)                            [展开/收起] │
│  ✅ 审核发现 (N 条)                                [展开/收起] │
└──────────────────────────────────────────────────────────────┘
```

## 权限

- POST 端点：`require_engineer_or_admin`（`get_current_user` 即可，engineer+ 角色才有创建入口）
- 产品线过滤：在查询时应用用户可访问的产品线列表
- 响应脱敏：跨产品线数据只显示文档编号和摘要，不暴露详细字段

## 测试策略

- 后端单元测试：每个 Source 独立测试 + FusionEngine 测试
- API 测试：POST 端点正常/空结果/权限拒绝
- 前端：面板渲染 + 跳过 + 空状态

## 不在范围内

- 编辑时推荐（已有系统处理）
- 用户反馈/评分机制（未来扩展）
- 推送历史记录持久化（未来扩展）
- LLM 摘要生成（未来扩展，当前只做结构化数据展示）
