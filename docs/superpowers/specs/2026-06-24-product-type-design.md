# 产品类型（Product Type）设计

**日期**: 2026-06-24
**分支**: fix/fmea-fixes
**状态**: 设计已确认，待写实现计划

## 背景与动机

当前 AI 推荐管线（FMEA 推荐、8D D4/D5 推荐、语义搜索/QA）召回历史时，过滤维度只有 `product_line_code` + `factory_id`，没有"产品类型"这一层。用户希望按产品类型做更精准的历史归类与推荐。

经梳理确认（见 `docs/superpowers/specs/` 同期对话）：

- 知识库载体：`document_embeddings`（pgvector 向量库）+ `fmea_documents.graph_data`（AIAG-VDA 图）。
- 现有分类维度：`product_line_code`（如 `DC-DC-100`）+ `factory_id`。**无 product_type 维度**。
- 推荐时按 scope 过滤召回：`global` / `current_product_line`，并有 KG VIEW 权限门控。

## 目标

引入"产品类型"作为**产品线的父级**分类（ProductType → ProductLine → FMEA/文档），并在 AI 推荐召回历史时新增「同类产品」范围（同类型下所有产品线的历史）。

## 非目标（YAGNI）

- 不在 `document_embeddings` 上反规范化 `product_type_code` 列（方案 A：scope 解析层展开 product_line_codes，embedding 写入路径不动，无向量回填）。
- 不做全局产品线选择器按类型分组（AppLayout 顶部选择器不变）。
- 不对同类型匹配做额外 +0.1 加权（保留现有同产品线 +0.1）。
- 不把 `product_lines.product_type_code` 设为 NOT NULL（本次保持 nullable，存量由管理员分配）。

## 关键决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 产品类型与产品线关系 | 产品类型是产品线的父级 | 用户明确：一个类型下挂多个产品线 |
| 产品类型租户范围 | 跨工厂共享（无 factory_id） | 用户明确：集团级分类法 |
| 推荐召回如何用类型 | 新增 `current_product_type` scope（同类）| 用户选择"新增同类范围"，三档并存 |
| 建模方式 | 新建 `product_types` 表 | 用户选择，独立主数据 + FK |
| 召回过滤实现 | scope 解析层展开 product_line_codes | 方案 A，复用现有按 product_line_code 过滤路径（向量源 `= ANY(...)`、图仓库 ORM `in_()`），最小改动 |
| 无 KG 权限用户的 scope 降级 | `global`/`current_product_type` → 降级 `current_product_line` | 最严档，保持现有"无权限不跨产品线"语义 |
| 语义搜索页类型过滤 | 纳入本次范围 | 用户确认 |
| 全局选择器分组 | 不做 | YAGNI |

## §1 数据模型

### 新表 `product_types`（跨工厂共享，无 factory_id）

| 列 | 类型 | 约束 |
|---|---|---|
| `code` | String(20) | PK，`^[A-Z0-9_-]+$` |
| `name` | String(100) | NOT NULL |
| `description` | Text | nullable |
| `is_active` | Boolean | default True |
| `created_at` | DateTime(tz) | server_default now() |
| `updated_at` | DateTime(tz) | server_default now(), onupdate now() |

### `product_lines` 加列

| 列 | 类型 | 约束 |
|---|---|---|
| `product_type_code` | String(20) | FK→`product_types.code` ON DELETE RESTRICT, **nullable=True** |

- nullable 初始保留，存量产品线由管理员后续分配。
- 推荐遇到无类型产品线时，`current_product_type` 降级为 `current_product_line`（见 §3）。
- 后续若全部已分配，可再发迁移设 NOT NULL——非本次必做。

### Pydantic schema + API

- `/api/product-types`：list / create / update / delete。仅 admin 可写，所有人可读。服务层手动写 `AuditLog`，沿用现有 CRUD 模式。
- `ProductLineCreate / ProductLineUpdate / ProductLineResponse` 增加 `product_type_code: str | None` 字段。

### seed

新增 `POWER / 电源类`，把 `DC-DC-100` 挂到其下。

### 删除语义（与 product_lines 一致：软停用）

`product_types` 带 `is_active`，DELETE 走**软停用**（`is_active=False`），与 `product_line_service.delete_product_line`（`product_line_service.py:49-79`，软停用 + 下游引用检查）模式一致，不做硬删。

- DELETE 前检查下游引用：是否有 `product_lines.product_type_code = code` 且 `is_active=True` 的产品线。若有 → 409/400 拒绝（"类型仍被活跃产品线引用，无法停用"）。
- 无引用 → 设 `is_active=False`。
- FK `ON DELETE RESTRICT` 仅作为数据库层兜底（防止误硬删），业务层不主动硬删。

## §2 迁移与回填

### Alembic 迁移（手写，含 downgrade）

1. 建 `product_types` 表。
2. `product_lines` 加 `product_type_code` 列（nullable，无 server_default，FK→`product_types.code` ON DELETE RESTRICT）。

### 回填

- 迁移内不自动回填业务含义（无法可靠推断）。
- seed 阶段把 `DC-DC-100` 挂到 `POWER / 电源类`。
- 存量产品线 `product_type_code` 留空，由管理员在产品线管理界面分配。

### 无 embedding 回填

方案 A 关键收益：`document_embeddings` 不动，没有向量重写。召回时若当前 FMEA 的产品线无类型，`current_product_type` scope 降级为 `current_product_line`，不报错。

## §3 推荐范围解析与权限

### Scope 取值变更

`backend/app/schemas/recommendation.py`：
```python
scope: Literal["global", "current_product_type", "current_product_line"] = "global"
```
前端 `RecommendRequest.scope` 同步。

### 新增解析函数

`resolve_product_line_codes(scope, current_product_line_code, db, request_scope, user) -> list[str] | None`（放新模块 `recommendation_scope.py`）：

**返回值语义**：业务 scope 解析结果 **∩ 用户可访问产品线 ∩ 可访问工厂的产品线**。

- `global` → `None`（不过滤，沿用现有 KG global 语义）。说明：FMEA 图推荐 global 路径 `find_similar_nodes_advanced` 只过滤 `status==approved`，**不**按工厂/产品线收敛（`jsonb_repository.py:235-238`）——即 KG VIEW 用户可全局跨工厂看历史。这是既有设计，本次沿用，不把 global 纳入工厂/产品线过滤。
- `current_product_line` → `[current_product_line_code]`（仍需落在用户可访问集合内，若不可访问则返回空列表）。
- `current_product_type`：
  - 查 `product_lines.product_type_code` where code = current_product_line_code。
  - 若为 NULL → 降级返回 `[current_product_line_code]`（等价 current_product_line）。
  - 若非空 → 查同类型下所有 `product_line_code`，得到业务集合。
- **权限交集**（所有非 global 档）：将上一步业务集合与 `request_scope.pl_scope`（用户可访问产品线）及 `request_scope.factory_scope`（可访问工厂下的产品线，复用 `product_line_service.list_product_lines(accessible_factory_ids=...)`）取交集。交集为空 → 返回空列表（召回不到，不报错）。

> 必须取交集的原因：`product_types` 跨工厂共享，同类型下可能含用户不可访问工厂的产品线；不取交集会让 KG VIEW 用户跨到不可访问工厂的历史。`product_lines` 本身带 `factory_id` 且 list 按 `accessible_factory_ids` 过滤（`product_line_service.py:17-18`），解析函数复用同一过滤路径。

### FMEA 推荐管线（`RecommendationService.recommend`）

- **服务签名变更**：`recommend(self, fmea_id, request, user)` → `recommend(self, fmea_id, request, user, request_scope: RequestScope)`。当前 service 只接收 user 拿不到工厂 scope（`recommendation_service.py:412`）；`api/fmea.py:274` 端点已有 `scope: RequestScope = Depends(get_request_scope)` 但未传给 service，本次由端点传入。
- `effective_scope` 解析扩展：现有只处理 global↔current_product_line 权限降级。新增 `current_product_type` 档：
  - 无 KG VIEW 权限 + 请求 `global`/`current_product_type` → 降级到 `current_product_line`（最严档）。
  - 有 KG VIEW 权限 → 三个 scope 都允许。
- `find_similar_nodes_advanced` 支持按一组 product_line_code 过滤：当前签名 `scope, product_line_code`（`jsonb_repository.py:224`），改为 `product_line_codes: list[str] | None`（None=不过滤）。当前实现是 ORM `FMEADocument.product_line_code == product_line_code`（非 SQL ANY），改为 `FMEADocument.product_line_code.in_(product_line_codes)`。**同步更新**：图仓库抽象基类 `repository.py`、Neo4j 实现 `neo4j_repository.py`（对应 `in_` 语义）、`/api/graph` 调试端点（`SimilarNodesRequest/Response`）。
- `_query_graph_similarity` 传解析出的 codes 集合（经权限交集后的）。
- 缓存键 `_compute_context_hash` 已含 `scope`，天然区分三档，无需改。
- **`scope` Literal 全量更新**：`RecommendRequest.scope`、`RecommendResponse.effective_scope`、`SimilarNodesRequest.scope`、`SimilarNodesResponse.effective_scope`、前端 `api/recommendation.ts` 的 `RecommendRequest/RecommendResponse` 类型、相关测试 fixture。

### 8D 管线（`HybridRecommendationPipeline`）

**现状**：8D D4/D5 推荐是 `GET /{report_id}/d4-fmea-recommendations` 与 `.../d5-...`（`api/capa.py:378/449`），**无 scope 参数**；`RecommendationContext` 只传 `user_product_lines=allowed_pls`（用户可访问产品线）与当前 CAPA 的 `product_line_code`。

**本次决策：8D 不暴露 scope 控件，移出本次 scope 目标。** 理由：8D 召回已由 `user_product_lines` 收敛到用户可访问产品线，且 D4/D5 是无参数 GET，加 scope 需改 API 契约与前端 8D 页面，超出"产品类型"主诉求。

- 不给 `RecommendationContext` 加 `product_line_codes`，不改 8D API 签名。
- 8D 仍按现有用户可访问产品线集合（`user_product_lines`）召回，**不提供同类型范围语义**。
- 若后续需在 8D 显式按类型召回，另立 spec。

### 语义搜索页（`SemanticSearchTab.tsx` + `/api/search`）

- 现有按 `product_line_code` 过滤。新增可选 `product_type_code` 过滤。
- 前端联动：选类型 → 产品线下拉收窄到该类型下的产品线；不选产品线只选类型时，后端按类型解析成同类型 product_line_codes 集合过滤。
- 后端 search 端点接受 `product_type_code`，解析成 codes 集合后复用现有 `= ANY(...)` 过滤。
- **QA 同步**：`ask()` 复用 `semantic_search(product_line_code=...)`（`search_service.py:185`），`QARequest` 已有 `product_line_code`（`schemas/search.py:42`）。本次给 `semantic_search` 与 `ask` 同时增加 `product_type_code` 参数，`QARequest` schema 加 `product_type_code: str | None`，`api/search.py` 的 semantic search GET query 参数加 `product_type_code`，前端 `api/search.ts` 参数类型同步，`SemanticSearchTab` 在 search 与 QA 两种模式下都传 `product_type_code`，避免 QA 模式下类型过滤不一致。

## §4 前端

### 关键事实

后端有完整 `product_lines` CRUD（`backend/app/api/product_line.py`：list/post/put/delete），但**前端无产品线管理页**（`App.tsx` 无路由，`pages/admin/` 仅 `AIConfigPage.tsx`）。AppLayout 顶部只有全局产品线选择器（`useProductLineStore`）。故本次需补前端管理入口。

### 1. 产品类型主数据管理页（新增）

- `pages/admin/ProductTypePage.tsx`：列表 + 新建/编辑/删除（code、name、description、is_active）。沿用现有 admin 页风格。
- 菜单项加权限过滤（admin）。
- API client `api/productType.ts`。

### 2. 产品线管理页（新增最小入口）

- 因前端无产品线管理页，本次顺带补 `pages/admin/ProductLinePage.tsx`：列表 + 编辑（含 `product_type_code` 下拉）。仅补"分配类型"所需的最小 CRUD 入口，不做超出范围的功能。
- 复用后端已有 product_lines API。

### 3. FMEA 推荐 scope 选择

- 推荐触发处（`SmartSuggestionDropdown` / `InlineRecommendations`），scope 选项从两档扩为三档，新增「同类产品」。
- `RecommendRequest.scope` 类型同步。

### 4. 语义搜索页类型过滤

- `SemanticSearchTab.tsx` 产品线下拉旁加「产品类型」下拉（可选）。联动：选类型→产品线选项过滤→仍按 product_line_code 传后端；只选类型时后端按类型解析。

### 5. i18n

zh-CN/en-US 双语补全（产品类型、同类产品、各字段名、菜单项）。

## §5 测试

### 后端 pytest

1. `product_types` CRUD（list/create/update/delete）+ 权限（非 admin 403）+ AuditLog 写入。
2. `product_types` DELETE 软停用：无活跃产品线引用 → `is_active=False`；有活跃产品线引用 → 拒绝（4xx）；FK RESTRICT 仅作 DB 兜底。
3. `product_lines` 带类型字段 create/update。
4. `resolve_product_line_codes` 解析（**含权限交集**）：
   - `global` → None
   - `current_product_line` → 单元素（在用户可访问集合内）；不可访问 → 空列表
   - `current_product_type` 有类型 → 同类型产品线 ∩ 用户可访问产品线 ∩ 可访问工厂产品线
   - `current_product_type` 无类型 → 降级单元素
   - 同类型含不可访问工厂的产品线 → 被交集剔除，不泄露
5. FMEA 推荐管线：`current_product_type` scope 召回跨产品线（同类型）历史；无 KG 权限用户请求 `current_product_type` 降级到 `current_product_line`。
6. `find_similar_nodes_advanced` 接受 codes 集合过滤（`in_` 语义；回归现有单产品线不破）；Neo4j repo 对应实现同步。
7. 语义搜索：按 `product_type_code` 过滤返回同类型 product_line 的结果；QA `ask()` 同样支持 `product_type_code`。
8. 现有推荐/语义搜索测试不回归（fixture 补 product_type 字段、scope Literal 三档）。

### 前端 vitest

1. 产品类型管理页 CRUD 交互（含软停用拒绝提示）。
2. 产品线管理页类型分配。
3. 推荐触发处 scope 三档可选。
4. 语义搜索页类型下拉联动产品线、传参正确（search 与 QA 两种模式）。

### 迁移/seed

- 迁移可正向 + 降级（手写 downgrade）。
- seed 后 `DC-DC-100` 挂到 `POWER`。

### 验证命令

`pytest tests/ -x`、`npm run build`、`npm run lint`。

## 涉及文件（预估）

**后端**：
- 新：`models/product_type.py`、`schemas/product_type.py`、`api/product_type.py`、`services/product_type_service.py`、`services/recommendation_scope.py`、alembic 迁移。
- 改：`models/product_line.py`、`schemas/product_line.py`、`api/product_line.py`、`services/recommendation_service.py`、`graph/jsonb_repository.py` + `graph/repository.py`（抽象基类）+ `graph/neo4j_repository.py`（Neo4j 实现 `in_` 对应）、`schemas/recommendation.py`（scope Literal 全量）、`api/graph.py`（调试端点 SimilarNodesRequest/Response）、`services/search_service.py`（semantic_search + ask 加 product_type_code）、`schemas/search.py`（QARequest 加 product_type_code）、`api/search.py`（semantic search GET query 参数）、`seed.py`。
- **不改**：`services/recommendation_types.py`（RecommendationContext，8D 不加字段）、`services/recommendation_sources.py`（8D 召回源，不动）、`api/capa.py`（8D API 签名不动）。

**前端**：
- 新：`pages/admin/ProductTypePage.tsx`、`pages/admin/ProductLinePage.tsx`、`api/productType.ts`。
- 改：`types/index.ts`、`api/recommendation.ts`（scope Literal 三档）、`api/productLine.ts`、`api/search.ts`（semantic search 参数 + QARequest 参数加 product_type_code）、`pages/graph/SemanticSearchTab.tsx`、推荐触发组件（`SmartSuggestionDropdown`/`InlineRecommendations`）、`App.tsx`（路由）、`components/layout/AppLayout.tsx`（菜单）、i18n 资源。

## 后续

spec 批准后，进入 writing-plans 生成实现计划。
