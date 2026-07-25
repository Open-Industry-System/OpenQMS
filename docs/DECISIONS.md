# 决策日志 (Architecture Decision Records)

本文档记录 OpenQMS 关键设计决策、做出决策时的背景以及随之带来的影响。
仅记录会**长期约束**代码或团队的决策；可逆的实现细节、临时 hack 不进入此文件。

## 格式约定

每条决策使用轻量 ADR 格式：

- **编号**：`ADR-NNNN`，单调递增，落定后不再复用
- **日期**：决策落定日 (`YYYY-MM-DD`)
- **状态**：`Accepted` / `Superseded by ADR-XXXX` / `Deprecated`
- **背景**：当时的问题、约束、备选方案
- **决策**：选择了什么，**没**选什么
- **影响**：对代码、运维、团队的正负面后果

新决策追加在文件末尾。**已落定的决策不要原地改写**——若被推翻，新增一条 ADR 并把旧条目状态改为 `Superseded by ADR-XXXX`。

---

## ADR-0001 — 主键统一使用 Python 端生成的 UUID v4

- **日期**：2025-08-15
- **状态**：Accepted
- **背景**：多工厂、多租户场景下需要跨库去重、离线生成 ID、避免自增 ID 暴露业务量级。备选：PG `bigserial`、PG 端 `gen_random_uuid()`、Python 端 `uuid4()`。
- **决策**：所有业务表主键统一为 `UUID v4`，由 Python 端 (`uuid.uuid4()`) 生成；ORM 层定义 `default=uuid.uuid4`，DB 列类型为 `UUID(as_uuid=True)`。
- **影响**：
  - ✅ 跨工厂/租户 ID 不冲突，便于未来集团合并、外部系统对接
  - ✅ Service 层能在 `flush` 前拿到 ID，方便组装关联对象
  - ⚠️ 索引体积大于 `bigint`；分页/排序时不要按主键排序，统一用 `created_at DESC`
  - ⚠️ Alembic 迁移文件必须显式声明 `UUID(as_uuid=True)`，否则 PG 会回落到 `VARCHAR(36)`

## ADR-0002 — FMEA 用 JSONB 图模型，不做关系表拆分

- **日期**：2025-09-10
- **状态**：Accepted
- **背景**：AIAG-VDA 7 步法 PFMEA/DFMEA 节点关系是动态图（System→Subsystem→…→FailureMode→Effect/Cause→Controls），节点种类多且常新增。备选：完全关系化（≥ 12 张关联表）、文档型（MongoDB）、JSONB 图。
- **决策**：`fmea_documents.graph_data` JSONB 列存 `{nodes: [...], edges: [...]}`，节点/边类型用枚举字符串约束；前端 `fmeaTable.ts` 双向转换为 20+ 列的电子表格行。
- **影响**：
  - ✅ 节点类型增删不需要 schema 迁移；DFMEA/PFMEA 共用同一份代码
  - ✅ 整图一次性读写，无 N+1
  - ⚠️ 跨 FMEA 查询（"这个零件出现在哪些 FMEA 中？"）必须 `jsonb_array_elements()`，不能走索引——为此引入了 Neo4j + JSONB 双 Repository（见 ADR-0010）
  - ⚠️ 共享节点（控制措施、行动）的删除必须做引用计数：`fmeaTable.ts` 行删除时检查"是否还有其他行引用"，否则会误删
  - ⚠️ Dashboard RPN 聚合用原始 SQL + `jsonb_array_elements()`（见 ADR-0007）

## ADR-0003 — 多工厂数据隔离用 `factory_id` 行级过滤，不用 schema-per-tenant（同一部署内）

- **日期**：2025-10-02
- **状态**：Accepted（SaaS 多租户层另见 ADR-0012）
- **背景**：客户内部多工厂部署需要让"工厂 A 的工程师看不到工厂 B 的数据"，但同一份代码、同一个 DB。备选：每工厂独立 schema、每工厂独立 DB、行级 `factory_id`。
- **决策**：所有业务表带 `factory_id NOT NULL`；`core/factory_scope.py` 提供 `check_factory_access(entity, scope)`；`core/deps.py` 的 `RequestScope` 在每个请求注入"用户可见工厂集合"。Users 表 `factory_id` 允许 NULL，表示集团管理员。
- **影响**：
  - ✅ 部署/迁移简单，跨工厂报表/集团审计无需联邦查询
  - ✅ 行级权限与 RBAC 解耦：角色管"能做什么"，scope 管"能看哪些行"
  - ⚠️ **每个新模块的 Service 方法都必须显式调 `check_factory_access`**——漏掉就是越权漏洞，CI 没法静态检查
  - ⚠️ 跨工厂统计接口（Group Admin Dashboard）要单独标注豁免，否则会被 scope 过滤成空

## ADR-0004 — Service 层手写 AuditLog，不用 SQLAlchemy event hook 自动审计

- **日期**：2025-10-18
- **状态**：Accepted
- **背景**：合规（IATF 16949 / ISO 9001）要求所有质量记录可追溯。备选：SQLAlchemy `event.listens_for(Session, "after_flush")` 自动审计、AOP 装饰器、Service 层手动写入。
- **决策**：所有 CRUD 在 Service 方法里**手工**创建 `AuditLog` 行，字段含 `actor_id / module / action / entity_id / before / after / reason`。
- **影响**：
  - ✅ 业务上下文显式（"为什么改"，自动 hook 拿不到）；可写入业务字段，比如 8D 阶段、FMEA 修订号
  - ✅ 测试可断言"调一次 update → 写一条 audit"，事件钩子很难测
  - ⚠️ **新 Service 方法漏写 AuditLog 是最常见 bug**——code review checklist 必查
  - ⚠️ `enqueue_embedding()` 必须在 `await db.commit()` **之前**调用，否则 outbox 行会丢（与 audit 同 transaction）

## ADR-0005 — JWT HS256 + 120 min 过期，不用 OAuth2 第三方/refresh token

- **日期**：2025-09-25
- **状态**：Accepted
- **背景**：内部部署为主，没有第三方 IdP；用户接受 2 小时后重新登录。备选：JWT RS256（需要密钥分发）、Session + Redis、OAuth2 + refresh token。
- **决策**：HS256 单 secret，`SECRET_KEY` 环境变量；token `sub=user_id`，120 min `exp`；前端 `ProtectedRoute` 本地校验过期；过期则 axios 拦截器清 token → `/login`。无 refresh token。
- **影响**：
  - ✅ 实现简单，无后端 session 存储
  - ⚠️ 无主动登出/撤销机制——修改密码后旧 token 仍可用最长 2 小时
  - ⚠️ `SECRET_KEY` 必须在部署/测试两侧一致；测试用 `SECRET_KEY=test-secret-key`
  - ⚠️ 登录无速率限制（见 `PROGRESS.md` Known Gaps），后续需引入

## ADR-0006 — 权限矩阵 = 7 角色 × 25 模块 × 5 级，不做 ACL/策略引擎

- **日期**：2025-10-12
- **状态**：Accepted
- **背景**：质量管理领域职责清晰（admin / manager / quality_engineer / viewer + group_admin / supplier_manager / customer_manager），不需要任意主体-对象-动作的策略系统。备选：Casbin、OPA、内置 RBAC 矩阵。
- **决策**：`role_definitions` × `permissions` 表存矩阵；`core/permissions.py` 定义 `Module` / `PermissionLevel` 枚举；API 层用 `require_permission(Module.X, PermissionLevel.Y)` 装饰；前端 `usePermission` hook 镜像逻辑用于菜单过滤。状态机审批权限（FMEA 审批、8D D7/D8 closure）在 Service 层硬编码 role check，不进矩阵。
- **影响**：
  - ✅ 矩阵可视化、易审计；新角色只需在 seed 里追加
  - ✅ 前后端权限一致性靠同一个 `Module` 枚举常量（前端从 `types/index.ts` 镜像）
  - ⚠️ 业务级"只能审批同工厂"等横切规则不在矩阵里，散落在 Service——引入 `core/factory_scope.py` 收口（见 ADR-0003）
  - ⚠️ 完整矩阵见 `docs/permissions.md`，修改时**必须**同步更新该文档

## ADR-0007 — Dashboard 聚合用原始 SQL + JSONB 函数，不用 ORM

- **日期**：2025-11-04
- **状态**：Accepted
- **背景**：Dashboard 要把 FMEA `graph_data` JSONB 里的所有 FailureMode 节点摊平统计 RPN，SQLAlchemy ORM 无法表达。备选：ORM relation hack、应用层 Python 聚合、原始 SQL `text()`。
- **决策**：`services/dashboard_service.py` 用 `db.execute(text(...))`，配合 `jsonb_array_elements(graph_data->'nodes')` 摊平后 `GROUP BY`、`AVG`、`COUNT`。SQL 字符串中所有用户输入走绑定参数 (`:name`)。
- **影响**：
  - ✅ 单查询完成，避免拉 1000 个 FMEA 文档到 Python
  - ⚠️ SQL 与 PG 绑定，跨 DB 不可移植——可接受
  - ⚠️ JSONB 路径变化（节点 schema 改字段名）会让 dashboard 静默返回 0；schema 演进时需同步检查这里

## ADR-0008 — 前端只用 Zustand 管 auth + product line + factory，业务数据用 `useState`

- **日期**：2025-09-30
- **状态**：Accepted
- **背景**：React 18 + Vite + Ant Design 已成型，需要决定状态管理方案。备选：Redux Toolkit、Zustand 全局、纯 `useState` + props。
- **决策**：Zustand 只承载跨页全局：`useAuthStore`、`useProductLineStore`、`useFactoryStore`。每个页面的列表/筛选/表单状态用本地 `useState`；分页数据按 `PaginatedResponse<T>` 泛型规范返回。
- **影响**：
  - ✅ 学习成本低，页面文件自包含
  - ✅ 无 selector 重渲染玄学
  - ⚠️ 跨页缓存（"刷新列表后跳详情再回来"）丢失——可接受
  - ⚠️ 未引入 React Query / SWR：所有 axios 调用手写 loading/error，重复样板较多

## ADR-0009 — FMEA 编辑器不引入第三方表格库，自建 Ant `Input`+`Select` 电子表格

- **日期**：2025-10-22
- **状态**：Accepted
- **背景**：20+ 列、单元格类型差异大（下拉、级联、长文本、数字）、行间数据相互联动（S/O/D → AP 自动查表）。备选：AG Grid、Handsontable、ant-table-edit、原生表格。
- **决策**：用 Ant Design `Input`、`Select`、`InputNumber` 组合手写表格；`utils/fmea.ts` 提供 AIAG-VDA Action Priority 查表；`utils/fmeaTable.ts` 处理 JSONB graph ↔ 行模型双向转换。
- **影响**：
  - ✅ 无授权费 / bundle 增量；与现有 Ant Design 样式天然一致
  - ✅ 完全可控（行 fanout 按 cause × effect、多 Effect、共享节点引用计数都自定义）
  - ⚠️ 性能上限：单文档 > 500 行会卡，目前未触发
  - ⚠️ 复制粘贴 / 多选 / 撤销 等 spreadsheet 习惯功能要自己实现

## ADR-0010 — 知识图谱用 Neo4j + JSONB 双 Repository，不是迁移到 Neo4j

- **日期**：2025-12-08
- **状态**：Accepted
- **背景**：跨 FMEA 检索（相似失效模式、变更影响 BFS）在 PG JSONB 上不可索引，但完全迁移 Neo4j 会丢掉事务和 Alembic 迁移。备选：纯 PG + 物化视图、纯 Neo4j、双源同步。
- **决策**：PG JSONB 是**真源** (source of truth)；FMEA 保存时异步同步到 Neo4j（`graph/` 模块）；查询时按场景路由——CRUD 走 JSONB Repository、相似/BFS 走 Neo4j Repository。Neo4j 数据丢失时可从 PG 重建。
- **影响**：
  - ✅ 事务/审计仍在 PG，Neo4j 故障不影响主流程
  - ✅ 推荐/影响分析可享受图遍历性能
  - ⚠️ 双写一致性：依赖 outbox + 重试，未做强校验脚本
  - ⚠️ 部署多一个服务（docker-compose 已含）

## ADR-0011 — Agent 框架不用 pydantic-ai，自研轻量 harness 直接调 openai/anthropic SDK

- **日期**：2026-06-15
- **状态**：Accepted
- **背景**：P0 AI Agent Base 需要工具调用 + HITL 审批 + 三层记忆 + guardrails。pydantic-ai 是首选，但其依赖 pydantic ≥ 2.10，而项目锁定 pydantic 2.9.2（FastAPI 0.115 + 大量已写 schema 不能升）。备选：升级 pydantic 全栈、用 LangChain、自研 harness。
- **决策**：在 `app/agent/` 自研 harness——三态网关 (5-tuple 白名单) + HITL 审批 + 3 层 memory + guardrails，工具调用直接走 openai/anthropic 官方 SDK。
- **影响**：
  - ✅ 不破坏 pydantic 2.9.2 锁定
  - ✅ 6 张 `agent_*` 表 + 82 单测，行为可控
  - ⚠️ 自己维护工具调用 loop；多工具并发、anthropic `tool_result` shaping 是 P2 follow-up
  - ⚠️ 详细 root cause 见 memory `ai-driven-qms-p0-agent-base.md`

## ADR-0012 — SaaS 多租户用 schema-per-tenant + JWT 域隔离，不在 row 上再加 `tenant_id`

- **日期**：2026-01-20
- **状态**：Accepted
- **背景**：SaaS 客户要求"我的数据物理隔离"，但同一份代码服务多客户。备选：所有表加 `tenant_id`（在 `factory_id` 之上再叠一层）、schema-per-tenant、DB-per-tenant。
- **决策**：每租户独立 PG schema（`tenant_xxx`）；JWT 域名 (`acme.openqms.com`) 路由到对应 schema；schema 内沿用 ADR-0003 的 `factory_id` 行级隔离。新租户通过模板 schema clone。
- **影响**：
  - ✅ 物理隔离合规友好；导出/迁移单租户只需 `pg_dump --schema`
  - ✅ 现有业务代码无需再加 `tenant_id`
  - ⚠️ Alembic 迁移需对每个 schema 跑一遍——封装在部署脚本
  - ⚠️ 跨租户集团报表不可行（设计上即如此）

## ADR-0013 — Alembic 迁移手写，不用 autogenerate

- **日期**：2025-08-20
- **状态**：Accepted
- **背景**：autogenerate 对 JSONB、enum、约束改名、复合索引识别不稳定，且生产数据迁移常需自定义 SQL（数据回填、分批 UPDATE）。备选：纯 autogenerate、autogenerate + 手工校对、纯手写。
- **决策**：所有迁移文件**手写** `op.create_table / op.add_column / op.execute(...)`；命名 `NNNN_<动词>_<对象>.py`，复杂数据迁移在 `upgrade()` 里用 `op.execute(text(...))`。
- **影响**：
  - ✅ 数据迁移和 schema 迁移在同一文件，回滚明确
  - ✅ JSONB 字段、check constraint 行为可控
  - ⚠️ 编号偶发冲突（多分支并行开发时）——`PROGRESS.md` Known Gaps 已标注，需规范
  - ⚠️ 新开发者上手成本略高，参考已有迁移文件模仿

---

## 何时写新 ADR

下列任一即写：

1. 选了一项会**长期约束**代码走向的技术或模式（库、协议、数据模型）
2. **拒绝**了一个看起来合理的方案（"为什么不用 X" 的预防性记录）
3. 因外部约束（合规、性能、依赖锁定）让代码偏离常规做法

下列**不**写：

- 单文件实现细节、bug 修复、变量改名
- 临时绕过（应该写 `# TODO` 或 `PROGRESS.md`）
- 单模块内部选择，对其他模块无影响

---

> 历史背景：本文件 2026-06-30 创建，前 13 条 ADR 是对项目已有决策的**回溯整理**，日期取自最相关的代码合入日。之后的决策按落定日实时记录。
