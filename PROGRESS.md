# OpenQMS 开发进度

**更新日期**: 2026-07-01
**当前分支**: `fix/dashboard-admin-pages`（领先 `main` 108 个 commit，尚未合并）
**最近合并**: `4102de5` P1-B 质量趋势迁移；P1-C FMEA 推荐迁移（6 任务 TDD 已落地，41 推荐测试绿）

详细路线图见 `docs/ROADMAP.md`，本文件为当前阶段的快速看板。

---

## 一、已经开发完成

### Phase 1 — 基础平台 + 核心模块 ✅
- MVP 闭环：JWT + 7 角色 RBAC、产品线 JSONB 图、PFMEA/DFMEA 编辑器、8D/CAPA 工作流、仪表盘、审计日志
- 控制计划编辑器（与 FMEA 双向联动）
- SPC 控制图（X-bar R / I-MR / 直方图 / P/NP/C/U + 8 大判异规则 + Cp/Cpk）
- MSA 测量系统分析（GR&R、偏倚、线性、稳定性、计数型 Kappa）
- 特殊特性（CC/SC）贯穿管理、产品安全特性管理、质量目标、内部审核、管理评审、FMEA/CP 版本管理

### Phase 2 — 供应商 / 客户质量 ✅
- 供应商档案 + 准入审批 + A/B/C/D 评级
- IQC（AQL/ISO 2859-1 抽样引擎，含克隆重检）
- 供货质量看板（PPM / 批次合格率 / 准时率 / 排名）
- SCAR 5 态生命周期 + 8D 闭环
- 客诉、RMA、客户质量看板（含 0 公里 PPM、保修费用、满意度、客户审核摘要）
- 客户审核、APQP（5 阶段门）、PPAP（AIAG 18 要素 + 5 态）
- 产品线选择器、CSR/VOC → 控制计划同步、Excel 导入导出

### Phase 3 — AI + 知识图谱 ✅
- Neo4j 基础设施 + JSONB 双 Repository
- G6 v5 图谱可视化（FMEA 嵌入 tab + `/knowledge-graph` 全局页）
- 全局知识库（跨 FMEA 统计 + 相似节点搜索 + 响应白名单脱敏）
- LLM RAG 语义搜索（pgvector + 全文 + RRF 融合，6 实体）
- FMEA 编辑智能推荐（混合规则 + 图相似 + LLM，多 Provider）
- 8D D4/D5 全混合推荐管道（4 D4 源 + 3 D5 源 + FusionEngine + LLMFusionLayer）
- 变更影响分析（BFS + AP 预测 + 影响评分）
- SPC-FMEA 异常关联推荐、D7 预防复发提示
- 多人协同编辑（乐观锁 + 短轮询在线状态 + 三方 diff）

### Phase 4 — 高级分析 + 生态集成 ✅
- MES / PLM / ERP 三大连接器（Mock + REST，Outbox 可靠推送，凭证 Fernet 加密）
- 8D 报告 AI 草拟、质量趋势 AI 解读
- 经验教训智能推送（5 源融合）
- 控制计划智能校验（4 规则引擎）
- IQC 抽样方案智能优化（10 规则 + 多级审批）
- 供应商风险智能预警（10 规则 + 4 级 + 邮件/Webhook + SCAR/CAPA 闭环）
- 管理评审报告自动生成、供应链风险地图（热力图 + 时间线 + 对比）
- 自定义拖拽看板（react-grid-layout + 18 widget）
- 多工厂部署（factory_id 行级隔离 + 三层 Scope）
- SaaS 多租户（schema-per-tenant + JWT 域隔离）

### Phase 4+ — FMEA 体验优化（已合并到 main） ✅
- PFMEA 七步法生成向导（Step 0 范围 → Step 6 确认）
- DFMEA 向导增强（5T 工具/趋势 AI 推荐 + PC/DC AI 推荐 + 工具结构引导）
- FMEA 版本快照只读查看器、安全删除（draft/rework）
- 产品类型主数据（`product_types` 表，跨工厂共享）
- 图谱布局清晰度（边色/方向切换/PNG 导出背景合成）
- 结构树拖拽迁移 `@dnd-kit`、推荐缓存与作用域修复

### 当前分支 `fix/dashboard-admin-pages` 已落地（未合 main）
1. **管理后台增强**（2026-06-26 起）
   - 用户管理页（创建 + 列表 + 启停 + 删除 + 工厂访问/角色/密码编辑）
   - 日志管理页（audit / login / system 三 tab 分页）
   - `system_logs` 表 + DBLogHandler（异步队列 + 每租户 drain）
   - `login_audit_logs` 表 + 登录成功/失败捕获
2. **仪表盘下钻**（2026-06-26 ~ 06-27）
   - KPI 卡片 → 过滤列表/详情页、Alert 行可点击、Pending 聚合 → 类别菜单
   - 后端：pending_breakdown / pending-filter / SPC-distinct-ic_id / abnormal-filter 端点
   - 前端：`dashboardDrilldown.ts` 权限映射、KpiPendingWidget 下拉、IQC/SPC/MSA/MES drilldown、a11y 改造
3. **P0 Agent Base — AI-driven QMS 基座**（2026-06-29 ~ 06-30，合并 `178487b`）
   - 6 张 `agent_*` 表 + `audit_logs` 扩 `factory_id/tenant_schema/correlation_id`
   - `@agent_tool` 注册表 + 三级权限网关（readonly / draft / commit）
   - 5 元组白名单（user × tool × module × min_level × max_scope）+ HITL 待办审批 + 状态机（approve/reject/modify）
   - 三层记忆（Redis 短期 + `task_state` JSONB + `agent_memory` 入队）
   - Guardrails（输入注入启发式 + 输出脱敏/清洗）
   - 自研 tool-calling 主循环（基于 openai/anthropic SDK，**未引入 pydantic-ai** — 与 pinned pydantic 2.9.2 冲突）
   - API 路由：sessions / messages / actions / whitelist（含 factory_id + `check_factory_access`）
   - 82 个测试（含 4 个 P0 验收用例：readonly 隔离 / draft 不落库 / commit 三态 / guardrails）
4. **P1-B：质量趋势解读迁移到 Agent 基座**（2026-06-30，合并 `4102de5`）
   - `quality_trend_service` LLM 调用切到 `provider_adapter.complete_json` + `audit.write_audit_raw`
   - config-check 前置于 cache（修回归）、严格 provider 白名单、每调用本地 httpx、路由测试 assert kwargs
   - 5 个 TDD 任务，全分支回归绿
5. **P1-C：FMEA 智能推荐迁移到 Agent 基座**（2026-07-01，6 任务 TDD 已落地）
   - `RecommendationService.recommend()` 的 LLM 调用从旧 `LLMProvider.complete()` 迁到 `provider_adapter.complete_json`
   - 新增两态审计 `_write_recommend_audit`（`success` / `llm_failed`），仅覆盖 `need_llm=True` 路径
   - 抽 `_tenant_schema` 到共享 `core/tenant.py`（dashboard + fmea 路由共用）；`build_client` 前置于 cache 检查
   - 丢 `llm_provider` ctor 参数 + `self.llm`；`llm_available` 穿透 `_get_cached`/`_cache_result`
   - 混合 rule-fallback UX、缓存行为、5 态 `source` 状态机**不变**；未配置 LLM 静默 rule 降级（200，不审计，不 503）
   - 经 4 轮 spec/plan 对抗评审（17+ 修复合并入计划），零中间红 commit；41 推荐测试绿
6. 杂项：`a178b5d` 清理 5 个 Finder 复制的 ' 2.*' 文档文件；`e91b1ad`/`97cf6d3` Makefile 用 venv 绝对路径跑 pytest；`f80c27a` SCAR 测试改 `SCAR-TEST-*` 避免种子碰撞

---

## 二、还没有开发（已规划，待启动或进行中）

### 紧邻待启动
- **P1 后续：剩余 LLM 调用点迁移到 Agent 基座（D 阶段及以后）**
  - P1-B（质量趋势）+ P1-C（FMEA 推荐 / 5T 工具趋势）已完成，agent 基座 `provider_adapter.complete_json` + `write_audit_raw` 已就位
  - 仍未迁移的旧 LLM 调用点：8D D4/D5 混合推荐管道、SPC-FMEA 异常关联、D7 预防复发、经验教训推送等（Phase 3 功能里的 LLM 直连）
  - 目标：旧调用点删除，用户无感，可观测性统一（base 审计覆盖）
- **系统级端到端（E2E）测试套件**（2026-06-30 新增需求）
  - 目标：对所有代码更改进行系统级端到端测试，覆盖每次合并/发版前的回归
  - 待 brainstorm 的范围：模块覆盖（FMEA / CAPA / IQC / SPC / MSA / 客户质量 / 供应商质量 / Admin / Agent Base）、层次（API 契约 + 浏览器 UI 流 + RBAC 角色矩阵 + 多工厂 `factory_id` 隔离）、运行方式（docker-compose 整栈 vs in-process）
  - 候选工具：后端 pytest + httpx；前端 Playwright（仓库已有 `mcp__plugin_playwright`）；位置建议 `backend/tests/e2e/` + `frontend/e2e/`，或新增顶层 `e2e/`
  - 与现有 `make check`（单元层）分离为独立 target，避免 CI 时长爆炸
  - 下一步：走 `superpowers:brainstorming` → spec → plan → TDD

### P2 — Copilot（对话式助手）
- 前端 UI 侧栏（`ProtectedRoute` 接入待做）
- Readonly tools 扩展：查 FMEA / SPC / 客诉 / 8D / 供应商
- Draft tools 扩展：8D 草稿生成 + PFMEA 行建议
- 验收：工程师可用自然语言查数 + 生成草稿落入编辑器

### P3 — 流程自动化（客诉 → 8D 端到端）
- 任务队列 / worker
- Agent 拆解 D1–D8 起草 → 待办审批 → 落库
- 一条客诉全流程 agent 产出草稿、人审批后入库、全程可审计

### 从 P0 拆出的独立后续任务
1. **embedding worker 支持 `agent_memory`**
   - 当前 worker 用固定 `table_field_map`，**不认识 `agent_memory`**
   - P0 仅验收 queued 入队 + 非向量 fallback 检索；向量检索待 worker 增强
   - 需把 `agent_memory` 加入 worker，upsert `document_embeddings` 后置 `ready/failed`
2. **既有随机 `record_id` 写审计调用点的兼容修复**
   - 如 `quality_trend_service` 等
   - P0 只保证新增 agent 审计使用可追溯主键 + `factory_id/correlation_id`，**未触碰旧调用点**
3. **真正的多工具 LLM 循环**
   - P0 harness 主循环目前是骨架，需补完多轮 tool-call 调度
4. **Anthropic tool_result 完整 shaping**
   - 当前 provider_adapter 偏 OpenAI 形态，Anthropic 侧的 tool_result 结构需补齐
5. `fix/dashboard-admin-pages` 分支整体合并回 `main`（含 Admin 增强 + 仪表盘下钻 + P0 Agent Base）

### ROADMAP 之外的已知缺口（来自 CLAUDE.md）
- 测试套件仍在补齐，部分历史模块缺 `factory_id` fixture 回填
- 登录无速率限制
- Redis 已配置但**未实现缓存逻辑**
- 前端 bundle 5.5MB，需代码分割
- 部分 Alembic 迁移号重叠，需规整

---

## 三、当前阻塞 / 风险点

### 设计/技术决策已规避的"曾经阻塞"
- ~~引入 pydantic-ai 做 agent 基座~~ — 与项目 pinned **pydantic 2.9.2 冲突**，已切换到**自研 tool-calling 循环 + 现有 openai/anthropic SDK**（spec `f57fcff` 记录决策）
- ~~LLM 推荐"AI 建议暂不可用"误导~~ — 三因叠加（Docker 镜像缺 SDK / OpenAIProvider 忽略 `llm_base_url` / 硬编码 `response_format=json_object` 被 Ark/DeepSeek 拒绝），已诊断；`llm_timeout=5s` < Ark 实际 ~9s 导致静默 rule_fallback，需把 `/admin/ai-config` 默认值上调到 15–30s
- ~~Worktree 执行 superpowers 计划~~ — `worktree.baseRef=fresh` 缺已 commit 的 plan + 当前代码状态，已改为 `baseRef=head`；backend 测试需 `SECRET_KEY=test-secret-key`；worktree frontend 需 `npm install`

### 当前实际待解（需要决策/手动操作）
1. **P1 后续迁移排期**：P1-B + P1-C 已落地，剩余旧 LLM 调用点（8D D4/D5 / SPC-FMEA / D7 / 经验教训推送）未排迁移顺序
2. **P0 follow-up 优先级未排期**：embedding worker / 随机 record_id 修复 / 多工具循环 / Anthropic shaping 四项已识别但未挑顺序
3. **`fix/dashboard-admin-pages` 合 main 时机**：分支已领先 108 个 commit，含 P0 Agent Base 大变更（6 新表 + audit_logs schema 扩展）+ P1-B/C 迁移，合并前需：
   - 完整运行 backend `pytest` + frontend `npm run lint` + `tsc --noEmit`
   - 在干净 DB 上跑 `alembic upgrade head` 验证迁移
   - 评审者过 P0 Agent Base 整体（已逐 commit review，但 PR 级总览未做）
4. **LLM Provider 兼容性**：Anthropic 的 `tool_result` 结构与 OpenAI 不一致，provider_adapter 当前仅 OpenAI 形态完善，切到 Claude provider 会跑不通（P1-B/C 都走 OpenAI 形态 `complete_json`，未触碰此缺口）
5. **数据库基线**：CLAUDE.md 已标注"部分 Alembic 迁移号重叠，需规整"——P0 加了 6 表 + audit_logs 扩展，迁移线越来越长，建议在合 main 前做一次 squash

### 非阻塞但需关注
- 前端 5.5MB bundle，代码分割工作未排期
- Redis 配置在但缓存层为空（agent harness 短期记忆是首次实际用上 Redis 的地方）
- 测试套件 `factory_id` fixture 仍在按模块回填，跨模块测试偶发因 fixture 缺失失败

---

## 四、当前在做

| 项目 | 状态 | 位置 |
|---|---|---|
| P0 Agent Base | ✅ 已合并 `178487b`，82 测试通过 | `fix/dashboard-admin-pages` |
| P1-B 质量趋势迁移 | ✅ 已落地（`4102de5`） | `fix/dashboard-admin-pages` |
| P1-C FMEA 推荐迁移 | ✅ 已落地（6 任务 TDD，41 推荐测试绿） | `fix/dashboard-admin-pages` |
| Admin 用户/日志/工厂编辑 | ✅ 已落地（`cfde81c` 等） | `fix/dashboard-admin-pages` |
| 仪表盘下钻 | ✅ 已落地（`b82967c`） | `fix/dashboard-admin-pages` |
| `fix/dashboard-admin-pages` → `main` 合并 | 🟡 待统一回归 + PR 评审（已领先 108 commit） | — |

---

## 参考资料

- 详细路线图：`docs/ROADMAP.md`
- AI-QMS 总体设计：`docs/superpowers/specs/2026-06-29-ai-driven-qms-overview-design.md`
- P0 Agent Base 设计：`docs/superpowers/specs/2026-06-29-ai-qms-p0-agent-base-design.md`
- P0 Agent Base 实施计划：`docs/superpowers/plans/2026-06-29-ai-qms-p0-agent-base-plan.md`（13 任务 / 4 验收）
- P1-B 质量趋势迁移：`docs/superpowers/specs/2026-06-30-ai-qms-p1b-quality-trend-migration-design.md` + `docs/superpowers/plans/2026-06-30-ai-qms-p1b-quality-trend-migration.md`（5 TDD 任务）
- P1-C FMEA 推荐迁移：`docs/superpowers/specs/2026-06-30-ai-qms-p1c-fmea-recommend-migration-design.md` + `docs/superpowers/plans/2026-06-30-ai-qms-p1c-fmea-recommend-migration.md`（6 TDD 任务，4 轮评审）
- 权限矩阵：`docs/permissions.md`
- 各模块详细文档：`docs/modules/`
