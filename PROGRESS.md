# OpenQMS 开发进度

**更新日期**: 2026-07-21
**当前分支**: `feature/us-e2e-01-spec-a`
**最近提交**: 01.9 横向扩散预警与通知已落地（migration/ORM/match/LLM close hook/decide-rerun/FE/E2E）；下一步 01.10 或 verify skill 同步

> **2026-07-08 更新**：US-E2E-01 已从单文件 v7 升级为 **epic 合集 v8.1 定稿**（`docs/user-stories/US-E2E-01-capa-8d-closed-loop/`，README + 10 子故事，经 3 轮评审修订）。配套 gap analysis 已完成（`docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`）。原 v6 缺口清单（11 项已完成）对应 v7 范围，v8.1 扩展为 10 子故事后的待办见文末「US-E2E-01 v8.1 待办任务」。

详细路线图见 `docs/ROADMAP.md`，本文件为当前阶段的快速看板。

---

## 系统级 E2E 测试套件（M0+M1，已落地）

浏览器全栈 E2E（Playwright + 专用 docker-compose e2e profile），手动 `make e2e`，**不接入 CI**。

- **M0 基建**：`docker-compose.e2e.yml`（独立库 qms_e2e + 卷 pgdata_e2e + 端口 5433/8001/5174，redis 不暴露，AI 服务 `profiles:["ai-infra"]`，`!override` 端口）；`E2E_MODE` config + 生产门控条件路由；确定性幂等 `seed_e2e`（2 工厂/产品线含 DC-DC-100 默认/5 账号 + UserProductLine/已知 PFMEA-E2E-001 + 8D-E2E-001）；`/api/e2e/seed-state` 只读（账号密码单一来源）+ `/api/e2e/cleanup` 白名单 FK 逆序单事务删（禁用 version 触发器）；`make e2e*` 目标（先 db/redis→migrate→backend/frontend）；`tsconfig.e2e.json` + `@types/node`；helpers/fixtures/global.setup（5 角色 UI 登录→storageState）+ guards。
- **M1 流程**（3/4，④原延后现可解封）：①登录+RBAC+工厂隔离 ②FMEA 生命周期 ③CAPA 8D 生命周期。④看板下钻此前仅实现一半（`KPICard` onClick + 列表页 query param 已有；widget→navigate 接线 + `dashboardDrilldown.ts` 缺失），**本轮已补齐**（见下文「仪表盘下钻」）；E2E Task 13 下钻 spec 可据此解封（follow-up）。
- **生产代码**：仅 `data-e2e` testid（`CAPAListPage` 的 `product_line_code` 为已批准的 bug 修复例外）。
- **验证**：M1 套件 9 passed / 1 skipped（无 LLM 凭证时 AI spec skip-with-warning）；backend e2e 端点测试 2 passed；`make check` + e2e tsc 干净；生产门控 `[]`（TENANT_MODE=production 时 `/api/e2e/*` 不载入）。
- **已知摩擦**：backend 登录限流（`auth.py` 10 次/5min 内存）在反复跑 Playwright 时可能让 `global.setup` 超时——重启 e2e backend 即恢复（未改生产代码）。
- spec: `docs/superpowers/specs/2026-07-01-system-e2e-test-suite-design.md`；plan: `docs/superpowers/plans/2026-07-01-system-e2e-test-suite.md`；指南: `docs/e2e.md`。

---

## US-E2E-01 8D 全程闭环 — 特性缺口清单（2026-07-03 审计）

对照 `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（v6，定稿）逐条审计当前系统实现的结果。**结论：故事结构上无法端到端通过**，需先补齐以下产品实现，再写故事级 spec `capa-story-closed-loop.spec.ts`。审计口径：代码路径（models/api/services/state_machines + frontend components/e2e），未跑运行时。

**进度**：11 项全部完成（P0-1~P0-4 / P1-5~P1-10 / P2-11 全部落地）

### 已完成 ✅（约 50%）

- [x] **CAPA 8D 状态机 D1→D2→…→D8_CLOSURE 严格顺序** —— `backend/app/state_machines/eightd_state.py`
- [x] **权限模型**：D1-D6 需编辑权限、D7→D8 需 `canApprove('capa')` —— `backend/app/api/capa.py:189 advance_capa`
- [x] **建单 + D 步字段 + 状态转换审计** —— `CAPAEightD` 模型 `models/capa.py:11-40`；服务层每次 advance 写 `AuditLog`
- [x] **D2 AI 草拟按钮** —— `AIDraftButton.tsx` + `useAIDraft.ts`
- [x] **D4/D5/D7 推荐 API + 面板骨架** —— `api/capa.py:276-461`；`D4RecPanel.tsx` / `D5RecPanel.tsx` / `D7RecPanel.tsx`（⚠️ 有骨架但缺阶段/来源丰富度，见"待补 P0-2/P0-3"）
- [x] **3 类推荐源实现** —— `FMEAGraphSource`、`SemanticSearchSource`（pgvector + FTS RRF）、`HistoricalCAPASource`（已关闭 8D D2→D2 语义匹配）、`RuleEngineSource` + LLM 融合（`match_source: "llm"`）

### 待补（P0 — 补齐后故事才能落地）

1. [x] **P0-1 D4 现场根因验证子流程** — 故事验收：「根因必须经现场验证才可确认；验证记录（方法/结果/证据）落库且可追溯；未验证的根因不能推进 D4→D5」
   - 当前 `d4_root_cause` 只是单个 `Text` 列，**无** 方法/结果/证据字段，**无** 附件表关联，**无** D4→D5 阻断校验
   - **交付物**：新表 `capa_root_cause_verification`（`capa_id, root_cause_text, method, result, evidence_attachments(JSONB), verified_by, verified_at, is_verified`）+ API（create/list/update） + `D4RecPanel` 增加「候选根因 → 验证卡」子面板（method 输入 / result 选择 / 证据附件上传）+ `advance_capa` 在 `D4_ROOT_CAUSE → D5_CORRECTION` 时校验至少 1 条 `is_verified=true` 记录 (Spec A 已落地，commit 见 git log)
2. [x] **P0-2 AI 推荐 12 阶段可视化 DAG 面板** — 故事验收：「触发 D4/D5 推荐后，流程编排面板出现，展示 12 阶段（名称/来源/状态 pending·running·done·skipped·error/命中数·摘要）」
   - 当前 `D4RecPanel.tsx` 仅按 `match_source` 分组（5 组），无 stage/status 概念；后端也无 stage 事件流
   - **交付物**：新服务 `RecommendationOrchestrator` 把现有 sources 组织成 12 阶段执行图，返回 `{stages: [{name, source, status, hit_count, summary, error?}], items: [...]}`；`D4/D5RecPanel` 增加 `<RecommendationDAG>` 组件（12 节点 + 状态色 + 命中数徽标）；无 LLM 凭证时相关阶段 `status="skipped"` 且带 reason (Spec B 已落地，commit 见 git log)
3. [x] **P0-3 AI 推荐来源 provenance 落地到 UI + testid** — 故事验收：「最终推荐列表非空、**每条带来源标签**」
   - 后端已有 `match_source`（linked/keyword/rule/llm/historical_capa/semantic_search/fmea_graph）但 UI 层无 `data-e2e` 钩子
   - **交付物**：`<RecItem>` 渲染 `<Tag data-e2e="rec-source-{source}">` + 阶段命中位置徽标；每条推荐 payload 增加 `stage_index` 便于 UI 关联到 DAG 节点 (Spec B 已落地，commit 见 git log)
4. [x] **P0-4 AI 采纳审计留痕** — 故事验收：「AI 推荐采纳 + 根因验证记录留痕（含来源）」
   - `grep "adopt_recommendation|recommendation_audit"` = 0 命中；当前采纳只把文本追加到 `d4_root_cause`/`d5_correction`，未记录 which item / from which source / at what stage
   - **交付物**：新表 `capa_ai_adoption`（`capa_id, d_step, adopted_text, source, stage_index, item_ref, adopted_by, adopted_at`）；D4/D5/D7 采纳按钮点击时 insert 记录并写 `AuditLog(action='ADOPT_RECOMMENDATION', metadata={source, stage})` (Spec A 已落地，commit 见 git log)

### 待补（P1 — 4 类推荐源接入）

5. [x] **P1-5 SPC 异常关联推荐源**（故事阶段 6）— 已有 SPC 判异算法（`spc_service.py`），需新增 `SPCAnomalySource` 类：查询该产品线近 30 天判异记录 → 关联到候选失效模式 → 输出到 D4 推荐；无 SPC 数据时 `status="skipped"` reason="产品线暂无 SPC 图" (Spec B 已落地，commit 见 git log)
6. [x] **P1-6 IQC 来料检验推荐源**（故事阶段 8）— 已有 IQC 模型（`iqc_materials`），新增 `IQCSource`：本批 + 历史来料不良趋势 → D4 推荐；这两个（5、6）由于底层数据已在系统内，接入成本最低，建议先做 (Spec B 已落地，commit 见 git log)
7. [x] **P1-7 供货历史推荐源**（故事阶段 9）— 已有 `supplier_quality_service`，新增 `SupplierHistorySource`：供应商评级/历史 PPM/SCAR 状态 → D4 推荐 (Spec B 已落地，commit 见 git log)
8. [x] **P1-8 MES 设备/过程数据推荐源**（故事阶段 7）— `mes_connector.py` 存在但仅为连接骨架；需评估：先做 mock 数据源接入 vs 等真实 MES 集成 (Spec B 已落地，commit 见 git log)
9. [x] **P1-9 同类型产品 KB 检索**（故事阶段 4）— 需按 `product_types` 主数据聚合跨工厂共享 KB，扩展 `SemanticSearchSource` 增加 `product_type` 过滤维度或新增 `SameTypeProductKBSource` (Spec B 已落地，commit 见 git log)
10. [x] **P1-10 经验教训库结构化**（故事阶段 5）— 当前 `HistoricalCAPASource` 只做 D2 语义匹配；建议新增 `capa_lessons_learned` 表（`capa_id, lesson_text, category, tags`）或从 D7/D8 抽取字段，让 lessons 检索更精准 (Spec B 已落地，commit 见 git log)

### 待补（P2 — 故事级 E2E）

11. [x] **P2-11 `capa-story-closed-loop.spec.ts`** — 用 `E2E-STORY-CAPA-001` 前缀（故事主角单号），覆盖 10 步主流程 + 12 阶段 DAG 结构断言（`data-e2e="rec-stage-{n}"` 状态属性）+ 7 条 TRANSITION 审计断言（`GET /api/audit-logs?target_id=...` 断 1 CREATE + 7 TRANSITION，D1-D7 operator=engineer、D7-D8 operator=manager）+ AI 采纳留痕断言（`capa_ai_adoption` 表通过 seed-state 端点回读）+ viewer 只读断言（`/capa` 列表看到关闭 8D、详情打开、`capa-create`/`capa-advance` 隐藏）
    - LLM 无凭证时 AI 断言 `test.skip` + 核心闭环照跑（沿用 `_guards/ai-credentials.guard.spec.ts` 模式）
    - 前置：现有 `capa.spec.ts` / `capa-ai-draft.spec.ts` 保持不变（M1 冒烟），故事 spec 与之并行
    - 落地（`frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts`）：单测覆盖 10 步闭环（engineer D1..D7 → manager D7→D8 → viewer 只读）。**实现取舍**：审计回读走 `GET /api/admin/logs/audit?table_name=capa_eightd`（admin token）按 `record_id` + 时间窗客户端过滤（原 PROGRESS 写的 `/api/audit-logs?target_id` 端点不存在，`admin/logs/audit` 无 `record_id` 过滤参数，客户端过滤等价且无需新增后端端点）；AI 采纳留痕同样从审计日志回读（`ADOPT_RECOMMENDATION` 的 `changed_fields` 含 `source` + `stage_index`），不另建 seed-state adoptions 端点。DAG 断言用实际 testid `rec-dag-stage-{n}` + `data-status`（非 `rec-stage-{n}`）。viewer 只读：D4 推荐恒非空（`RuleEngineSource` 默认候选兜底），无需关联 FMEA 即可断言 provenance + 采纳；`CAPAListPage` 新增 `canEdit('capa')` 门控隐藏 `capa-create`（viewer 真正只读）

### 补齐建议顺序

`[x] P0-1 (D4 验证) → [x] P0-4 (采纳审计) → [x] P0-2 (DAG 面板) → [x] P0-3 (provenance UI) → [x] P1-5/6 (SPC/IQC 源) → [ ] P2-11 (故事 spec) → [x] P1-7~10 (MES/供货/同类型/lessons，视实际 ROI 决定)`

理由：D4 验证 + 采纳审计是**数据模型缺口**，先落表结构；DAG + provenance 是**观测层缺口**，依赖 orchestrator；4 类源里 SPC/IQC 数据已在库最优先；MES/供货/同类型/lessons 优先级由业务实际数据密度决定。

### 参考

- 故事：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`
- 现有 E2E 覆盖度：`frontend/e2e/specs/m1-core/capa.spec.ts`（~10%，仅 D1→D2）+ `capa-ai-draft.spec.ts`（~5%，仅按钮可见性）
- 相关既有代码：`backend/app/services/{capa_service,capa_recommendation_service,recommendation_sources}.py`、`frontend/src/components/capa/{D4,D5,D7}RecPanel.tsx`

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
2. **仪表盘下钻**（设计 2026-06-26；**2026-07-03 补齐实现**）
   - 注：此前 PROGRESS 误记为已落地（`b82967c` 实为 customer-quality 的 searchParams 修复，非下钻），实际仅 `KPICard` onClick + 列表页 query param 就绪，widget→navigate 接线 + `dashboardDrilldown.ts` 缺失；本轮补齐。
   - KPI 卡片 → 过滤列表/详情页、Alert 行可点击、Pending 聚合 → 类别菜单
   - 后端：`pending_breakdown` 分项计数 / FMEA `pending` 过滤 / SPC `abnormal` 过滤（近 7 天 open 告警的 IC 子查询）
   - 前端：`dashboardDrilldown.ts` 权限映射 + `useDashboardDrilldown` hook、`KpiPendingWidget` 受控 Dropdown、IQC/SPC/MSA/MES drilldown、`AlertRow` a11y（hover/键盘/灰显）、无目标模块权限时灰显禁用
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
6. **P1-D：剩余 4 个 LLM 消费者迁移到 Agent 基座**（2026-07-01，5 任务 TDD 全部落地）
   - **8D D4/D5 混合推荐**：`LLMFusionLayer.enrich()` 返回 `LLMOutcome`（attempted/succeeded/failed 两阶段计数）；`HybridRecommendationPipeline` 迁到 `(db, pc, embedding_provider)`，写入 3 态审计 `llm_recommend`（`success`/`partial`/`llm_failed`）；D4/D5 路由 `build_client` 解析 `pc` + 透传 audit ctx + `await db.commit()`；LLM 未配置静默降级，不 503
   - **RAG 语义搜索问答**：`SearchService.ask()` 顶部解析 `pc`（no-results 早返回 `llm_available=pc is not None`），`complete_json` + 2 态审计 `llm_rag_qa`（哨兵 `record_id=uuid5` + `table_name="rag_qa"` + sort/dedup `correlation_id`）；路由改 503 守卫为 embedding-only + commit；hybrid 200 sources-only 保留
   - **管理评审报告**：`_enrich_with_llm`/`_generate_executive_summary` 改返回 outcome（`section_attempted`/`section_failed_keys`/`summary_failed`）；`generate_report` 重算 `llm_enriched` + `pc.model` 空值保护 + 2 态审计（与 CRUD 审计并存，骑乘 service L264 commit，路由无 commit）
   - **CAPA draft D2-D8**：仅换 `complete_json`（`llm_model_name` 空值保护，503 保留），**保留现有 `AI_DRAFT` 审计**不引入 `write_audit_raw`；`capa_capabilities`（`:112`）改 `build_client` 探测，`draft_capabilities`（`:480`）不动
   - 全消费者 timeout 来源不变（D4/D5 2s / mgmt `REPORT_LLM_TIMEOUT` / RAG httpx 30s / CAPA draft `CAPA_DRAFT_LLM_TIMEOUT`）；`LLMProvider` 类保留给 `ai_config_service` 自检
   - 经 3 轮 spec + 3 轮 plan 评审（11+7 findings 全闭合）+ 4 任务子代理逐任务评审 + opus 全分支评审；948 backend 测试绿 + frontend build 绿
7. 杂项：`a178b5d` 清理 5 个 Finder 复制的 ' 2.*' 文档文件；`e91b1ad`/`97cf6d3` Makefile 用 venv 绝对路径跑 pytest；`f80c27a` SCAR 测试改 `SCAR-TEST-*` 避免种子碰撞

---

## 二、还没有开发（已规划，待启动或进行中）

### 紧邻待启动
- **P1 LLM 迁移收尾**（P1-D 后剩余项）
  - P1-B + P1-C + P1-D 全部落地：4 个 LLM 消费者（8D D4/D5 / RAG 搜索 / 管理评审报告 / CAPA draft）已迁到 `provider_adapter.complete_json` + `write_audit_raw`
  - 经核实 **SPC-FMEA 异常关联 / D7 预防复发 / 经验教训推送均无 LLM 调用**（纯规则/图匹配），早先 PROGRESS 列入"剩余 LLM 调用点"有误
  - 仅剩 `ai_config_service` 自检仍用旧 `LLMProvider`（诊断用途，单独处理，不迁）
  - 后续可选：旧 `LLMProvider` 类在 `ai_config` 自检也切基座后删除；P0 follow-up（embedding worker / 多工具 LLM 循环 / Anthropic shaping）排期
- **系统级端到端（E2E）测试套件**（2026-06-30 新增需求）
  - 目标：对所有代码更改进行系统级端到端测试，覆盖每次合并/发版前的回归
  - 已落地（TDD 计划 14 任务）：
    - Task 3 `seed_e2e` / `seed-state` endpoint / `backend/tests/test_e2e_endpoints.py`：确定性 E2E 种子（2 工厂 / 1 产品线 / 5 账号 / 1 PFMEA / 1 CAPA）+ `GET /api/e2e/seed-state`
  - 待 brainstorm 的范围：模块覆盖（FMEA / CAPA / IQC / SPC / MSA / 客户质量 / 供应商质量 / Admin / Agent Base）、层次（API 契约 + 浏览器 UI 流 + RBAC 角色矩阵 + 多工厂 `factory_id` 隔离）、运行方式（docker-compose 整栈 vs in-process）
  - 候选工具：后端 pytest + httpx；前端 Playwright（仓库已有 `mcp__plugin_playwright`）；位置建议 `backend/tests/e2e/` + `frontend/e2e/`，或新增顶层 `e2e/`
  - 与现有 `make check`（单元层）分离为独立 target，避免 CI 时长爆炸
  - 下一步：Task 4 cleanup endpoint + 后续 E2E spec 任务

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
| P1-D 剩余 LLM 消费者迁移 | ✅ 已落地（5 任务 TDD：D4/D5 + RAG + 管理评审 + CAPA draft，948 测试绿） | `fix/dashboard-admin-pages` |
| Admin 用户/日志/工厂编辑 | ✅ 已落地（`cfde81c` 等） | `fix/dashboard-admin-pages` |
| 仪表盘下钻 | ✅ 已落地（本轮补齐 widget→navigate 接线 + `dashboardDrilldown.ts`；`b82967c` 实为 customer-quality 修复，非下钻） | `fix/dashboard-admin-pages` |
| `fix/dashboard-admin-pages` → `main` 合并 | 🟡 待统一回归 + PR 评审（已领先 125 commit） | — |
| US-E2E-01 epic v8.1 定稿 + gap analysis | ✅ 已落地（README + 10 子故事转定稿 + gap 报告，3 轮评审修订） | `feature/us-e2e-01-spec-a` |
| US-E2E-01 v8.1 实现（10 子故事） | 🟡 进行中（01.1–01.9 已落地；待 01.10 PPT） | — |
| US-E2E-01 verify skill 同步 | 🟡 待同步（总 skill 重定义为编排器 + 10 子 skill） | — |
| 01.10 PPT 输出 | ✅ 已落地（PPT generator + sub-agent 3-round review + admin review-skill management + frontend） | `feature/us-e2e-01-spec-a` |

---

## US-E2E-01 v8.1 待办任务（2026-07-08 录入）

US-E2E-01 已升级为 epic 合集 v8.1 定稿（`docs/user-stories/US-E2E-01-capa-8d-closed-loop/`，README + 10 子故事）。配套 gap analysis：`docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`。以下为按 gap 分析结论排定的实现任务，按优先级 + 交付顺序。

### P0 — 收尾（编排器已就绪，补硬 gap）

- [x] **01.2 12 源推荐收尾** — LLM 未配置严格 `BLOCKED`（orchestrator 顶部 pc=None→`RecommendationResult(blocked=True)` + D4/D5 endpoint 422+`detail.blocked` + 前端 `rec-blocked-banner`）；`RecommendationCache.stage_runs` JSONB 列 + 新增 CAPA 专属 `_cache_capa_result` write-only 写入路径（report_id 键 + uq_cache_capa upsert）+ `_serialize_capa_suggestions`（D5 单次遍历互斥）；e2e 拆 `capa-story-ai-recommend.spec.ts`（AI，无凭证 skip 整测）+ `capa-story-closed-loop.spec.ts`（非 AI 始终照跑）。切片 A（A1-A7）全部 review-clean。
  → **A3 已完成**：`RecommendationCache.stage_runs` JSONB 列 + Alembic 迁移 `20260709_capa_cache_stage_runs` + `backend/tests/migrations/` PG 迁移测试基础设施（`mig_db_url` fixture + `_cfg` helper），B1 可复用。
- [x] **01.3 D4 验证 + D7 + 审批壳状态机细化切片** — 新增 `D7_COMPLETED`/`D8_GATE_PENDING`/`D8_APPROVAL_PENDING` 3 状态 + 驳回回退边 + `capa_d7_node_action.status=pending` + edge 权限 + `update_capa` 冻结守卫；9 任务已落地，backend 测试绿
- [x] **01.3 D4 验证 method 枚举 + 回退计数器切片** — `CapaRootCauseVerification.method` 自由文本→枚举（measurement/observation/reproduction）+ CHECK 约束 + 迁移测试；`conclusion`（pending/passed/failed）+ `d4_retry_count` 回退计数器 + 双行锁递增 + 审计 `D4_VERIFICATION_PASSED`/`D4_VERIFICATION_FAILED`；服务层 `create_verification`/`update_verification` 结论驱动，`is_verified` 派生；同记录并发仅 +1，跨记录并发 +2（commit `8ccb29c5`）
### P1 — 新建/收尾

- [x] **01.1 D3 遏制全链路新建** — 4 类数据导入（在途/库存、发货/物流、IQC、SPC 判异）+ 受影响范围分析报告（5 项）+ AI 遏制建议（带 provenance）；ERP 数据模型（`ERPInventoryBalance`/`ERPShipment`）+ `capa_draft` 的 containment_actions 可复用；补 D3→D4 闸口（`advance_capa` 当前不检查 d3_interim 非空）。**实现态 v4（2026-07-12）**
  - **Task 12 E2E seed 扩展** ✅：D3 源数据 7 表 upsert + 7 独立 CAPA + 幂等 + E2E_MODE 守卫测试（`backend/app/seed_e2e.py` / `seed_e2e_constants.py` / `tests/e2e/test_seed_e2e_d3.py`）；附 `shipment_records.factory_id` 迁移补齐 schema drift
- [x] **01.4 8D↔FMEA 双向收尾** — 三源反查（header / D4 `source_ref` / D7 confirmed|auto_filled，含 Prevention）+ 同厂同 PL 写不变量 + factory/effective 过滤 + FMEA 可见性 404 + D4 Cause 选择器 + D7 Prevention 持久化/fingerprint + `FMEA_LINKAGE_CREATED` + deep-link/`activeRelatedNodeId` + reverse-lookup indexes + E2E `capa-story-fmea-linkage`（4/4）。spec: `docs/superpowers/specs/2026-07-14-us-e2e-01.4-fmea-linkage-design.md`；plan: `docs/superpowers/plans/2026-07-15-us-e2e-01.4-fmea-linkage.md`
  - **Deploy note 01.4**: D7 `recommendation_hash` now includes prevention fields; in-flight D7 CAPAs with pre-change hashes may need re-confirm/skip before D7 completion gate passes.
- [x] **01.5 8D→SCAR 触发新建** — 1:1 CAPA↔SCAR（`capa.scar_ref_id` + `scar.capa_ref_id` 双边 partial unique）+ `POST /capa/{id}/trigger-scar`（body `supplier_id` 必填，D3+ 非 ARCHIVED，同厂同 PL，FOR UPDATE + IntegrityError→400）+ GET `linked_scar`/`d3_affected_lots` 投影 + `SCAR_STATUS_SYNCED` 审计（CAPA 行不写状态）+ link-capa 硬化（SCAR CREATE + CAPA EDIT）+ FE CAPADetail 触发 Modal + seed `8D-E2E-SCAR-001` + E2E `capa-story-scar-trigger`。spec: `docs/superpowers/specs/2026-07-15-us-e2e-01.5-scar-trigger-design.md`；plan: `docs/superpowers/plans/2026-07-16-us-e2e-01.5-scar-trigger.md`（worktree commits `98f7e539`..`c5f4e970`）
- [x] **01.6 8D→供应商风险新建** — D7_COMPLETED 写 `supplier_risk_capa_inputs` outbox（severity/disposition/repeat 检测）+ 30s worker `evaluate_supplier_risk_in_tx` + `SUPPLIER_RISK_INPUT_SENT`；`POST /capa/{id}/confirm-repeat`（CAPA EDIT ∧ SUPPLIER_RISK EDIT）+ `SUPPLIER_RISK_CHANGED`；GET 投影 `supplier_risk_input`；FE `SupplierRiskInputCard`；E2E seed `8D-E2E-RISK-001`/`8D-E2E-RISK-HIST-001` + `capa-story-supplier-risk-input`。
  - **Deploy note 01.6**: (1) R11 须经 `seed_supplier_risk_configs`（e2e seed 已调；生产/新厂 seed 后确认 R11 存在）；(2) backend lifespan 启动 risk input worker loop（30s）— 进程不跑 loop 则 outbox 永挂 pending；(3) `capa.supplier_id` 生命周期：D7+ 锁定更换；create API 可带 `supplier_id` 但历史 create 路径未必设置，须在 D7 前通过 update/ORM 写入，否则 advance 不写 outbox。

### P2 — 新建/收尾

- [x] **01.7 D8 文档更新门禁新建** — 3 表 `capa_docg_*` + `generate_impact_analysis` 三阶段（BLOCKED/stale/CAS/C9）+ `run_audit`（diff_engine 版本间 diff + 关键点覆盖 + 空清单守卫）+ `record_defer`/`confirm_no_affected` + `_d8_doc_gate_gate`（C8/C9，defer 仍阻断）+ 7 路由 + `DocGatePanel`（全局推进排除 D8_GATE_PENDING）+ E2E seed `8D-E2E-DOCGATE-001` + `capa-story-doc-gate.spec.ts`；窄范围只审 CP/FMEA（C1）。plan: `docs/superpowers/plans/2026-07-13-us-e2e-01.7-doc-update-gate.md`。**终审第七轮修复**（3 P0 + 5 P1）：drop full UQ 允许重试、field 级覆盖判定、None baseline 不崩、CP item_id+完整 snapshot、空清单→done→confirm、phase3 refresh+rebuild candidates、defer owner 工厂校验、审计事件链补全；+10 回归测试 + advance-flow/TOCTOU gate 接入修复。**终审第 20–24 轮**：历史 hash 双算法 + backfill 全量 demote C9；preflight 可执行处置 + `make deploy-check` 强制入口；**structured waiver**（`waiver_items` 绑定 analysis/audit_run/doc_id/target_key/field + latest_version_id/hash；仅 server-confirmed blocked_modify；C8 仍核验非豁免文档；preflight 仅 latest decision 精确匹配；TOCTOU FOR UPDATE）；CHECK `chk_docg_waiver_items`；fixture `capa_with_cp_blocked_modify`。**第 24 轮**：residual completeness（同批次全部未覆盖 keypoint 须被 items 覆盖；不可豁免 FMEA/pending_update/incomplete 拒整单）；C8 version_snapshot 保留全部文档并绑定 latest_version_id/sha256，gate 重比版本+target_key 仍缺；preflight waived_keys 绑定版本，CP 漂移即复报；`20260715_waiver_items` 迁移先 UPDATE 失效遗留 reason-only waiver 再加 CHECK；`make deploy-release` 强制 migrate->check+preflight->再放行 app；+5 回归测试（partial/FMEA residual/version bump/stale waiver/legacy migration）。444 capa 绿。
- [x] **01.8 知识库沉淀收尾** — `knowledge_entries`（结构化 fields + document_no 50 + embedding_*）+ outbox `content_hash` + worker stale/dead_letter；`sink_capa_on_close` 挂 D8 close fail-closed（blocked/failed）+ 手动 resink；list/detail factory 403/404；stage-5 `KnowledgeEntrySource` + `KNOWLEDGE_SUNK`/`KNOWLEDGE_RETRIEVED`；FE CAPA knowledge card + outcome UX；E2E seed `8D-E2E-KNOW-001` + `capa-story-knowledge-sink.spec.ts`。spec: `docs/superpowers/specs/2026-07-16-us-e2e-01.8-knowledge-sink-design.md` v5；plan: `docs/superpowers/plans/2026-07-16-us-e2e-01.8-knowledge-sink.md`（worktree commits `5493d331`..本 task）
  - 与 `capa_lessons_learned` 写路径共存（未改 lessons）。
  - E2E：无 LLM → close 422 `outcome=blocked`；有 LLM → close + list/card + audit SUNK；embedding ready / recommend 命中依赖 embedding worker（可选，软断言）。

### P3 — 新建

- [x] **01.9 横向扩散预警新建** — 4 依据并集类似产品检查（同 product_type/共享 FMEA 模式/共享控制计划/同供应商+物料）+ 通知提示 + 状态追踪；D8 关闭 fail-closed 钩子；decide/rerun；FE Modal/Card；E2E seed+spec
- [x] **01.10 PPT 输出新建** — D8 关闭后一键生成 8D 报告 PPT（D1-D8 + 封面 + 联动附录）；前端 `generatePpt` API + 生成按钮（`canCreate('capa')` L2 门控，D8_CLOSURE/ARCHIVED 可见）+ 审核报告 Modal + admin ReviewSkillsPage 已落地（commit `c78d774d`）

### 配套（非子故事）

- [ ] **verify skill 同步** — `verify-capa-8d-closed-loop` 重定义为编排器（依据 README v8.1），端到端走查逻辑拆进 10 个子 skill（`verify-capa-8d-d3-containment` / `-recommendation-sources` / `-d4-d7-audit` / `-fmea-linkage` / `-scar-trigger` / `-supplier-risk-input` / `-doc-update-gate` / `-knowledge-sink` / `-lateral-diffusion` / `-ppt-output`），各顶部声明依据的子故事版本
- [ ] **gap analysis 维护** — 实现推进中若发现新 gap，回写 `docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`

### 关键约束

- **交付顺序**：01.1→01.2→01.3→01.7→01.4→01.5→01.6→01.8→01.9→01.10（D 步业务流程；01.4/01.5/01.6 可并行）
- **状态机**：实现时须先把 `eightd_state.py` 细化为 D7_PREVENTION→D7_COMPLETED→D8_GATE_PENDING→D8_APPROVAL_PENDING→D8_CLOSURE（含驳回回退），01.3/01.7 依赖此细化
- **AI_REQUIRED**：01.1/01.2/01.3/01.7/01.8/01.9 为 true（无 LLM 凭证→BLOCKED）；01.4/01.5/01.6/01.10 为 false

---

## 参考资料

- 详细路线图：`docs/ROADMAP.md`
- AI-QMS 总体设计：`docs/superpowers/specs/2026-06-29-ai-driven-qms-overview-design.md`
- P0 Agent Base 设计：`docs/superpowers/specs/2026-06-29-ai-qms-p0-agent-base-design.md`
- P0 Agent Base 实施计划：`docs/superpowers/plans/2026-06-29-ai-qms-p0-agent-base-plan.md`（13 任务 / 4 验收）
- P1-B 质量趋势迁移：`docs/superpowers/specs/2026-06-30-ai-qms-p1b-quality-trend-migration-design.md` + `docs/superpowers/plans/2026-06-30-ai-qms-p1b-quality-trend-migration.md`（5 TDD 任务）
- P1-C FMEA 推荐迁移：`docs/superpowers/specs/2026-06-30-ai-qms-p1c-fmea-recommend-migration-design.md` + `docs/superpowers/plans/2026-06-30-ai-qms-p1c-fmea-recommend-migration.md`（6 TDD 任务，4 轮评审）
- P1-D 剩余 LLM 消费者迁移：`docs/superpowers/specs/2026-07-01-ai-qms-p1d-remaining-llm-migration-design.md` + `docs/superpowers/plans/2026-07-01-ai-qms-p1d-remaining-llm-migration.md`（5 TDD 任务，3 轮 spec + 3 轮 plan 评审）
- 权限矩阵：`docs/permissions.md`
- 各模块详细文档：`docs/modules/`
