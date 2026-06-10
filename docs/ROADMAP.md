# OpenQMS 开发路线图

**更新日期**: 2026-06-10
**当前版本**: v0.1.0 (MVP)
**目标版本**: v3.0 (全功能发布)

---

## 总览

```
Phase 1 (M1-M4)          Phase 2 (M5-M8)          Phase 3 (M9-M12)         Phase 4 (M13-M16)
基础平台 + 核心模块        供应商/客户质量           AI + 知识图谱增强         高级分析 + 生态集成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
██████████████████████████ █████████████████████████ █████████████████████████ ░░░░░░░░░░░░░░░░░░░░░░░░
      已完成                  已完成                      已完成                    进行中
```

---

## Phase 1: 基础平台 + 核心模块 (Month 1-4)

### MVP (M1-M2): 核心闭环 ✅ 已完成

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| Docker Compose 开发环境 | P0 | ✅ 完成 | PostgreSQL + Redis + 前后端容器化 |
| 用户认证 (JWT + RBAC) | P0 | ✅ 完成 | 登录/注册/角色权限（admin/engineer/viewer） |
| 产品线数据架构 | P0 | ✅ 完成 | JSONB 图结构存储，单产品线 DC-DC-100 |
| PFMEA 编辑器 | P0 | ✅ 完成 | 工序流面板 + 节点/边表格编辑 + RPN 计算 + 状态流转 |
| 8D/CAPA 工作流 | P0 | ✅ 完成 | D1-D8 步骤推进 + 阶段表单 + FMEA 关联 |
| 仪表盘 | P0 | ✅ 完成 | 7 个 KPI 卡片 + 数据概览表 |
| 基础审计日志 | P0 | ✅ 完成 | AuditLog 模型已建表 |

### MVP 缺陷修复与体验优化 ✅ 已完成 (2026-05)

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| 业务级 RBAC 控制限制 | P0 | ✅ 完成 | 仅限 Admin / Manager 批准 FMEA/CAPA，只读用户界面置灰 |
| 输入框高频写库防抖 | P0 | ✅ 完成 | 8D/FMEA 文本输入防抖与失焦保存，消除并发写库竞态 |
| 8D D1 团队组建表单化 | P1 | ✅ 完成 | 替代 JSON TextArea 文本域，提供表格动态增删团队人员 |
| 审计日志自动写入 | P1 | ✅ 完成 | FMEA 与 CAPA 增删改、状态流转自动生成真实 AuditLog 记录 |

### M3-M4: 核心扩展 🔲 待开发

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| DFMEA 编辑器 | P0 | ✅ 完成 | 系统→子系统→零部件展开 + 设计参数矩阵 |
| DFMEA 生成规则引擎 | P0 | ✅ 完成 | 基于 AIAG-VDA 七步法设计引导式规则：①范围定义(5T)→②结构分析(方块图/边界图/结构树)→③功能分析(功能树/参数图)→④失效分析(失效链 FE-FM-FC)→⑤风险分析(S/O/D+AP)→⑥优化(预防/探测措施)→⑦结果文件化。核心规则：结构层级自动推导下级功能、功能否定生成失效模式、失效链自动关联、AP 表自动判定 H/M/L 并提示优化方向
| 控制计划编辑器 + FMEA 联动 | P0 | ✅ 完成 | PFMEA 一键生成控制计划，双向同步 |
| SPC 控制图 (v1.0+v1.1) | P0 | ✅ 完成 | X-bar R / I-MR / 直方图 / P/NP/C/U / 8大判异规则 / 手动+批量+API三源录入 / 过程能力Cp/Cpk/Pp/Ppk / 异常分级预警→8D / 控制限多版本管理 |
| SPC 计数值控制图 (v1.1) | P1 | ✅ 完成 | P图 / NP图 / C图 / U图 |
| SPC 控制限多版本 (v1.1) | P1 | ✅ 完成 | 自动版本号 + Drawer 切换 |
| 特殊特性贯穿管理 | P0 | ✅ 完成 | CC/SC 标识 + FMEA→CP 联动 + 覆盖矩阵 + 手动创建 + 严重度预警 + MSA 回调 + 动态产品线 |
| 产品安全特性管理 | P0 | ✅ 完成 | 安全特性识别 + 特殊批准流程 + FMEA 自动建议 + 会签通知 + 审批状态机 + 仪表盘 KPI |
| 质量目标管理 | P1 | ✅ 完成 | 三级目标树（公司→产品线→过程）+ 审批流 + 仪表盘 |
| 内部审核管理 | P0 | ✅ 完成 | 体系审核/过程审核/产品审核 + 检查表 + 发现项 + CAPA联动 |
| FMEA/CP 版本管理 | P1 | ✅ 完成 | 版本历史 + 变更对比 + 差异高亮 |
| 管理评审模块 | P1 | ✅ 完成 | ISO 9001 §9.3 管理评审数据包自动汇总 + 措施跟踪闭环(含效果验证) + 手动输入项 |
| MSA 测量系统分析 | P1 | ✅ 完成 | 量具管理与校验 + GR&R (均值极差法) + 偏倚 + 线性 + 稳定性 + 计数型 (Kappa) 分析，包含计算引擎、API 与可视化界面，完整测试覆盖 |

**验收标准**: 所有核心模块上线，内部 Beta 可用

---

## Phase 2: 供应商/客户质量 (Month 5-8) ✅ 基本完成

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| 供应商档案管理 | P0 | ✅ 完成 | 供应商主数据 + 资质证书 + 批准状态 + 准入审批流 + 绩效评价（混合指标 + A/B/C/D评级）；扩展点：Phase 2 IQC 阶段追加 supplier_audit_links 多对多关联表支持多次复审历史 |
| IQC 来料检验 | P0 | ✅ 完成 | AQL 抽样方案 + 检验批管理 + 判定 (基于 ISO 2859-1 的 AQL 抽样引擎，支持克隆重检与检验明细) |
| 供货质量看板 | P0 | ✅ 完成 | 供应商 PPM / 批次合格率 / 交付准时率 / 评级分布 / 供应商排名 / 对比分析 / Excel 导出 |
| SCAR 管理 + 8D 关联 | P1 | ✅ 完成 | IQC 拒收触发 SCAR → 8D 闭环；5态生命周期 + 独立路由 + 列表/详情页 |
| 客诉管理 | P0 | ✅ 完成 | 客诉接单 + 分类/严重等级 + 批次追溯 + 处理人 + 附件元数据 + 超期预警 + CAPA/FMEA 联动；SCAR 接口预留 |
| RMA 退货管理 | P0 | ✅ 完成 | 退货登记 + 批次/序列号 + 物流单号 + 不良分析 + 责任判定 + CAPA/FMEA 联动；SCAR 接口预留 |
| 客户质量看板 | P0 | ✅ 完成 | 投诉数、退货量、风险灯号、PPM 估算；0 公里 PPM（发运记录表）、SPC CPK、保修费用、客户满意度、客户审核摘要 |
| 供应商审核与绩效评价 | P1 | ✅ 合并至供应商档案管理 | 已整合进供应商管理模块 |
| 客户审核管理 | P1 | ✅ 完成 | 审核日程 + 发现项追踪 + 整改闭环（复用 audit_plan/audit_finding 路由，前端列表/详情页 + 客户确认流程） |
| 批量导入/导出 (Excel) | P2 | ✅ 完成 | xls/xlsx 标准格式兼容（backend utils/excel.py 通用工具 + frontend ImportExcelDialog 组件，已应用于供应商/SPC/IQC 模块） |
| APQP 项目质量策划 | P1 | ✅ 完成 | 五阶段门管理 + 五大工具串联 + 甘特图 + 阶段交付物检查表 |
| PPAP 管理 | P1 | ✅ 完成 | AIAG 18 要素提交与审批，5 态生命周期（draft/under_review/approved/rejected/resubmit），Level 1-5 必填元素映射，元素状态流转，前端列表/详情页 |
| 产品线选择器 | P0 | ✅ 完成 | product_lines 表 + 全局选择器 + 所有模块统一过滤 + service 层校验 |
| SCAR 接入 scar_ref_id | P1 | ✅ 完成 | 供应商责任客诉/RMA 一键创建 SCAR，双向关联，savepoint 事务安全 |
| 0 公里 PPM 发运记录 | P1 | ✅ 完成 | shipment_records 表 + CRUD + PPM fallback 链（参数→发运记录SUM→年发运量） |
| CSR/VOC → 控制计划同步 | P1 | ✅ 完成 | 客户特殊要求一键同步到控制计划 customer_requirements 字段，保留手动条目 |
| 高级客户质量看板 | P2 | ✅ 完成 | SPC CPK/PPK、保修费用、客户满意度、客户审核摘要；按客户/产品线过滤 |

**客户质量增强 (2026-05-30 已完成)**:
1. ~~SCAR 管理接入 `scar_ref_id`~~ ✅ 供应商责任客诉/RMA 一键创建 SCAR
2. ~~客户审核管理~~ ✅ 已在 Phase 2 前期完成
3. ~~CSR/VOC 同步控制计划~~ ✅ 一键同步客户特殊要求到控制计划
4. ~~0 公里 PPM 发运记录~~ ✅ shipment_records 表 + PPM fallback 链
5. ~~高级客户质量看板~~ ✅ SPC CPK、保修、满意度、审核摘要

**深色工业仪表盘 (2026-06-01 已完成)**:
1. ~~ConfigProvider 暗色主题~~ ✅ darkAlgorithm + 自定义 Token（单一来源）
2. ~~仪表盘重写~~ ✅ KPI 卡片（状态矩阵）+ 待处置事项（行动词）+ 最近操作（相对时间）+ 快速入口（viewer 隐藏）
3. ~~响应式设计~~ ✅ 小屏 P2/P3 自动折叠 + ARIA 地标 + 键盘导航（Enter + Space）
4. ~~可访问性~~ ✅ prefers-reduced-motion 响应 + 对比度 WCAG AA + screen reader 支持
5. ~~AppLayout 清理~~ ✅ 移除硬编码颜色，依赖 ConfigProvider Token

**验收标准**: GA v1.0 发布 — 供应商/客户模块上线

---

## Phase 3: AI + 知识图谱增强 (Month 9-12) ✅ 已完成

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| Neo4j 知识图谱基础设施 | P1 | ✅ 完成 | Neo4j Docker 服务 + Repository 抽象（Neo4j/JSONB 双实现）+ API 路由 |
| 知识图谱可视化 (G6 v5) | P1 | ✅ 完成 | FMEA 嵌入"图谱" tab（力导向/层次布局 + 节点点击/双击/右键菜单 + 影响/原因追溯高亮）+ 独立全局页面 `/knowledge-graph`（风险地图 + 跨 FMEA 统计 + 历史关键词搜索 + 节点跳转联动） |
| 全局知识库 | P1 | ✅ 完成 | 跨 FMEA 节点统计（AP 分布 / 高 AP 节点 / 平均 RPN / Top 失效模式）+ 相似节点关键词搜索 + Pydantic 响应白名单脱敏 + `/knowledge-graph` 全局页面 |
| LLM RAG 语义搜索 | P2 | ✅ 完成 | pgvector 向量存储 + 混合搜索（向量余弦 + tsvector 全文）+ RRF 融合 + RAG 问答（LLM + 来源引用）+ 6 实体类型覆盖（FMEA/CAPA/审核/客诉/SCAR/RMA）+ 产品线隔离 + 模块权限预过滤 + 异步 embedding worker + 回填命令 + KnowledgeGraph 第三 Tab |
| FMEA 编辑时智能推荐 | P2 | ✅ 完成 | 混合推荐系统（规则引擎 + 知识图谱相似度匹配 + 可选 LLM）+ PostgreSQL 缓存 + 前端 SmartSuggestionDropdown 内联下拉（5 种触发类型 × 6 列自动触发 + 500ms 防抖 + 键盘导航 + 回退提示）+ 产品线访问控制 + 限流；LLM 支持 Claude/OpenAI/Local 多提供商可配置 + 来源文档标注 |
| 8D 根因+措施推荐 | P2 | ✅ 完成 | D4/D5 全混合推荐管道（HybridRecommendationPipeline）：D4 四源（FMEA 图匹配 + RAG 语义搜索 + 历史 CAPA 匹配 + 规则引擎），D5 三源 + 控制措施扩展器；FusionEngine 去重排序 + LLMFusionLayer 增强；推荐面板（采纳/跳过）+ 只读权限控制 |
| 变更影响分析（图遍历）| P2 | ✅ 完成 | 设计参数变更 → 自动追溯影响范围；Neo4j/JSONB 双实现 BFS + AP 预测 + 影响评分 + 审计日志 + 前端报告/图谱联动 |
| SPC-FMEA 异常关联推荐 | P2 | ✅ 完成 | 控制图异常 → 识别关联 FMEA → 推荐 8D 方案；双路径匹配（控制计划桥接 + 名称模糊匹配）+ enrichment（RPN/AP/path/cause/control_count）+ 推荐弹窗面板 + CAPA 自动关联 |
| D7 预防复发提示 | P2 | ✅ 完成 | D7 步骤自动推荐关联 FMEA 失效模式（图结构匹配 + 关键词搜索）+ 一键跳转 + D5 措施自动填充 + D8 推进软门禁（未确认项弹窗 + 跳过理由写入审计日志）；产品线隔离 + CAPA/FMEA 双权限校验 |
| 多人协同编辑 | P2 | ✅ 完成 | 乐观锁 + 短轮询在线状态：FMEA/Control Plan 顶部在线用户列表 + 行级编辑指示器 + 409 冲突检测 + 三方 diff 预览 + 安全覆盖保存；CAPA/APQP 等仅接入在线状态 |

**Phase 3 已完成 (2026-05-31)**:
1. ~~Neo4j 知识图谱基础设施~~ ✅ Docker Compose + Neo4jRepository/JSONBRepository 双实现
2. ~~知识图谱可视化 (G6 v5)~~ ✅ GraphCanvas + GraphToolbar + NodeDetailDrawer + FMEA 嵌入 tab + /knowledge-graph 全局页
3. ~~全局知识库（基础）~~ ✅ 跨 FMEA 统计 + 相似节点搜索

**Phase 3 已完成 (2026-06-01)**:
4. ~~D7 预防复发提示~~ ✅ 图结构匹配 + 关键词搜索 + 自动填充 + 软门禁 + 审计日志
5. ~~FMEA 智能推荐升级~~ ✅ 后端混合推荐系统 + PostgreSQL 缓存 + 前端 SmartSuggestionDropdown 内联下拉 + 多 LLM 提供商支持

**Phase 3 已完成 (2026-06-02)**:
6. ~~8D 根因+措施推荐~~ ✅ D4 根因推荐（3 策略匹配）+ D5 措施推荐（3 路径控制措施 + 通用建议）+ 推荐面板 + 权限控制
7. ~~LLM RAG 语义搜索~~ ✅ pgvector + 混合搜索（向量+全文）+ RRF 融合 + RAG 问答 + 6 实体类型 + 产品线隔离 + 权限预过滤 + 异步 Worker + 回填命令 + 前端语义搜索 Tab + 17 个单元测试
8. ~~变更影响分析（图遍历）~~ ✅ Neo4j/JSONB 双 Repository BFS 遍历 + 方向控制 + AP 预测 + 影响评分 + 审计日志 + 产品线权限 + 前端报告面板 + FMEA 编辑器集成 + 知识图谱联动
9. ~~多人协同编辑~~ ✅ 乐观锁 + 短轮询在线状态（15s/8s/30s 动态间隔）
   - 后端：collaboration_sessions 表 + 心跳 API + lifespan 清理协程 + FMEA/Control Plan 原子乐观锁（SELECT FOR UPDATE + populate_existing）
   - 前端：useCollaboration Hook + CollaborationBar + ActiveUserIndicator + ConflictResolutionModal + 三方 graph diff + Control Plan items diff
   - 覆盖：FMEA/Control Plan 完整协同（在线状态 + 冲突提示），CAPA/APQP 等仅在线状态

**验收标准**: GA v2.0 发布 — AI + 知识图谱上线

---

## Phase 4: 高级分析 + 生态集成 (Month 13-16) 🔄 进行中

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| MES 集成连接器 | P2 | ✅ 完成 | Mock + REST 双连接器；9 张数据表；Outbox 可靠推送；3 类数据接入（生产订单/设备状态/报废记录）；SPC 告警推送；API Key 认证；凭证加密；4 页前端；Dashboard 实时聚合；产品线隔离；并发测试 33 条 |
| PLM 集成连接器 | P2 | ✅ 完成 (2026-06-09) | PLM BOM 树查询/导入 FMEA + Part→SC 特殊特性确认；Mock 连接器；9 张 PLM 表；前端 4 页（Dashboard/Connections/Parts/ChangeOrders）；双权限校验；46 后端回归测试 + 11 前端权限测试 |
| ERP 集成连接器 | P2 | ✅ 完成 (2026-06-10) | 商务与供应链事实源集成；9+1 同步对象；12 张数据表；Mock + REST 连接器；4 阶段 DAG 同步；双写关联（suppliers/shipments）；COQ 四类成本；字段级脱敏；双向批次追溯；6 页前端；5 轮代码审查 |
| 8D 报告 AI 草拟 | P3 | ✅ 完成 | LLM 辅助填充 D2-D8 步骤；结构化/段落双格式；localStorage 格式偏好；预览确认（替换/追加/取消）；撤销；权限控制（仅当前步骤可草拟）；独立审计日志；限流；FMEA 上下文关联；产品线隔离 |
| 质量趋势 AI 解读 | P3 | ✅ 完成 | 自定义仪表盘 Widget：规则摘要 + 按需 LLM 深度解读；SPC/CAPA/FMEA 三源聚合；模块级权限过滤；证据 hash 缓存；限流 + 审计日志；前端 stale 检测 |
| 经验教训智能推送 | P3 | 🔲 待开发 | 新建 FMEA/8D 时主动推送历史经验 |
| 控制计划智能校验 | P3 | 🔲 待开发 | AI 校验 CP 与 PFMEA 一致性 |
| IQC 抽样方案智能优化 | P3 | 🔲 待开发 | 基于历史质量动态调整 AQL |
| 供应商风险智能预警 | P3 | 🔲 待开发 | PPM + 交付 + SCAR 综合风险评估 |
| 管理评审报告自动生成 | P3 | 🔲 待开发 | 汇总输入数据 → 生成报告初稿 |
| 供应链风险地图 | P3 | 🔲 待开发 | 多维度供应风险热力图 |
| 自定义看板（拖拽式）| P3 | ✅ 完成 | react-grid-layout 拖拽布局，widget 库面板（18 种 widget），用户级 layout 存储，产品线过滤，权限控制 |
| 多工厂部署支持 | P3 | 🔲 待开发 | 每工厂独立实例 + 集团汇总 |
| SaaS 多租户架构 | P3 | 🔲 待开发 | Schema 级别隔离 + 弹性资源 |

**Phase 4 MES 集成已完成 (2026-06-05)**:
1. ~~数据库迁移~~ ✅ 9 张 MES 表 + CHECK 约束 + 权限种子（alembic/030）
2. ~~ORM 模型~~ ✅ MESConnection / MESSyncJob / MESProductionOrder / MESEquipmentStatus / MESScrapRecord / MESPushOutbox 等 9 个模型
3. ~~Schema 层~~ ✅ RESTConfig 校验 + Pydantic v2 请求/响应 + 分页包装 + Dashboard 聚合
4. ~~连接器适配层~~ ✅ MESConnector ABC + MockMESConnector + RESTMESConnector（分页/重试/auth/字段映射）
5. ~~凭证安全~~ ✅ SHA-256 API Key hash + Fernet 加密出站凭证 + sanitize_config 脱敏
6. ~~数据接入服务~~ ✅ MESIngestionService（4 类数据 ingest + 测量→SPC IC 联动 + 去重）
7. ~~同步调度~~ ✅ MESSyncService（manual/auto + SKIP LOCKED claim + claim_token UUID）
8. ~~Outbox 推送~~ ✅ MESPushService（3 阶段短事务 + at-least-once + event_id 幂等）
9. ~~生命周期管理~~ ✅ MESLifecycleService（7 天归档 + 失效 claim + 延迟清理）
10. ~~API 路由~~ ✅ 13 端点（connections CRUD + test/sync + ingest + 3 类列表 + dashboard）
11. ~~前端页面~~ ✅ 4 页（Connections + Dashboard + Production Orders + Scrap Records）+ 产品线联动
12. ~~并发测试~~ ✅ 33 条 pytest（SKIP LOCKED / claim_token / 幂等 / Outbox 3 阶段 / 归档）

**Phase 4 PLM 集成已完成 (2026-06-09)**:
1. ~~数据库迁移~~ ✅ 9 张 PLM 表 + CHECK 约束（alembic/031）
2. ~~ORM 模型~~ ✅ PLMConnection / PLMPart / PLMBOM / PLMChangeOrder / PLMSyncJob / PLMPushOutbox 等 9 个模型
3. ~~Schema 层~~ ✅ RESTConfig 校验 + Pydantic v2 请求/响应 + BOM 树结构 + Part 特殊特性确认
4. ~~连接器适配层~~ ✅ PLMConnector ABC + MockPLMConnector（分页/重试/auth/字段映射）
5. ~~凭证安全~~ ✅ SHA-256 API Key hash + Fernet 加密出站凭证
6. ~~数据接入服务~~ ✅ PLMIngestionService（BOM 导入 FMEA + Part→SC 特殊特性确认）
7. ~~同步调度~~ ✅ PLMSyncService（manual/auto + SKIP LOCKED claim）
8. ~~Outbox 推送~~ ✅ PLMPushService（3 阶段短事务 + at-least-once + event_id 幂等）
9. ~~API 路由~~ ✅ 13 端点（connections CRUD + test/sync + ingest + BOM + parts + change orders）
10. ~~前端页面~~ ✅ 4 页（Dashboard + Connections + Parts + ChangeOrders）+ 产品线联动
11. ~~测试覆盖~~ ✅ 46 条后端回归测试 + 11 条前端权限测试

**Phase 4 ERP 集成已完成 (2026-06-10)**:
1. ~~权限注册~~ ✅ Module.ERP 枚举 + product_line_filter 映射
2. ~~数据库迁移~~ ✅ 12 张 ERP 表 + 8 个 CHECK 约束 + 权限种子（alembic/032）
3. ~~ORM 模型~~ ✅ ERPConnection / ERPSyncJob / ERPPushOutbox / ERPSupplier / ERPCustomer / ERPMaterial / ERPLocation / ERPPurchaseOrder / ERPSalesOrder / ERPInventoryBalance / ERPShipment / ERPCostRecord
4. ~~Pydantic Schemas~~ ✅ RESTConfig 校验 + 分页 + Traceability + Dashboard 聚合
5. ~~凭证安全~~ ✅ SHA-256 API Key + Fernet 加密（ERP_ENCRYPTION_KEY）
6. ~~连接器~~ ✅ ERPConnector ABC + MockERPConnector（9 类数据）+ RESTERPConnector
7. ~~服务层~~ ✅ ERPIngestionService（9 类 push + 日期强制转换 + 自动关联）+ ERPSyncService（4 阶段 DAG 依赖门控）+ ERPTraceabilityService（双向多记录追溯）
8. ~~API 路由~~ ✅ 20+ 端点（CRUD + ingest + 列表 + link/unlink + dashboard + traceability）
9. ~~字段脱敏~~ ✅ bank_info/tax_id 基于 permission_level < 4 动态脱敏
10. ~~前端页面~~ ✅ 6 页（Dashboard + Connections + Master Data + Supply Chain + Sales & Cost + Traceability）
11. ~~测试覆盖~~ ✅ Mock 连接器 + 数据摄取 + 追溯 + 脱敏 + 日期强制转换 + DAG 门控
12. ~~5 轮代码审查~~ ✅ Alembic head 修正 + 事务提交/回滚 + 过滤器签名 + 角色键修正 + 脱敏完善 + 多记录追溯 + product_line_code 补全

**Phase 4 自定义拖拽看板已完成 (2026-06-09)**:
1. ~~后端模型~~ ✅ user_dashboard_layouts 表（JSONB 布局配置 + 用户级隔离）
2. ~~后端 API~~ ✅ DashboardPage 路由：GET/PUT 布局配置 + 产品线过滤 + 权限校验
3. ~~前端组件~~ ✅ WidgetLibraryPanel（分类面板）+ WidgetWrapper（拖拽容器）+ 18 种 widget
4. ~~拖拽引擎~~ ✅ react-grid-layout：resize + drag + 自动持久化 + 响应式断点
5. ~~Widget 库~~ ✅ KPI 卡片（6 种）+ 告警（4 种）+ SPC/MES/MSA/IQC/质量趋势 AI 等
6. ~~产品线过滤~~ ✅ 所有 widget 统一 product_line 过滤 + service 层校验
7. ~~权限控制~~ ✅ viewer 角色隐藏编辑按钮 + 后端 403 拦截

**验收标准**: GA v3.0 发布 — 全功能发布

---

## 项目统计 (截至 2026-06-10)

| 指标 | 数量 |
|------|------|
| Git 提交 | 1,021 次 |
| 后端 Python 文件 | 198 个 |
| 前端 TS/TSX 文件 | 181 个 |
| API 路由模块 | 34 个 (auth/fmea/capa/dashboard/iqc/scar/supplier/customer/spc/msa/ppap/apqp/audit/management_review/erp/...) |
| 前端页面 | 64 个 TSX 页面 |
| 数据库表 | 98 张 (含 ERP 12 张 + 多对多关联表) |
| 状态机 | 2 个 (FMEA 5-state + 8D 9-state) |
| 种子数据 | 4 用户 + 多模块演示数据 |

---

## 里程碑时间线

```
2026 M2  ──── ✅ MVP 完成 (FMEA + 8D + Dashboard)
2026 M4  ──── ✅ 核心模块上线 (内部 Beta)
2026 M5  ──── ✅ 供应商/客户模块完成 (含增强功能)
2026 M5  ──── ✅ 知识图谱基础设施 + 可视化上线
2026 M6  ──── ✅ Phase 3 AI + 知识图谱增强全部完成
2026 M6  ──── 🔲 Phase 4 高级分析 + 生态集成启动
2026 M12 ──── 🔲 GA v2.0 发布
2027 M4  ──── 🔲 全功能发布 (GA v3.0)
```

---

## MVP 技术资产

| 类别 | 内容 |
|------|------|
| 提交数 | 1,021 次 |
| 后端文件 | 198 个 Python 文件 |
| 前端文件 | 181 个 TS/TSX 文件 |
| API 端点 | 33 个路由模块 (auth/fmea/capa/dashboard/iqc/scar/supplier/customer/spc/msa/ppap/apqp/audit/management_review/...) |
| 前端页面 | 58 个 TSX 页面 |
| 数据库表 | 86 张 (含多对多关联表) |
| 状态机 | 2 个 (FMEA 5-state + 8D 9-state) |
| 种子数据 | 4 用户 + 3 FMEA + 6 CAPA + 多模块演示数据 |

---

## 下一步行动

**已完成 (2026-05-31)**:
- [x] Neo4j 知识图谱基础设施 (Docker Compose + 双 Repository 实现 + API 路由)
- [x] 知识图谱可视化前端 (G6 v5: GraphCanvas + 嵌入 FMEA tab + /knowledge-graph 全局页 + 5 场景交互)
- [x] 全局知识库基础 (跨 FMEA 统计 + 相似节点搜索 + Pydantic 响应白名单脱敏)

**已完成 (2026-06-01)**:
- [x] 深色工业仪表盘 (ConfigProvider 暗色主题 + 仪表盘重写 + 响应式折叠 + 可访问性)
- [x] AppLayout 清理 (移除硬编码颜色，依赖 ConfigProvider Token)
- [x] D7 预防复发提示 (图结构匹配 + 关键词搜索 + 自动填充 + 软门禁 + 审计日志)

**立即**:
- Phase 3 全部完成，准备进入 Phase 4
- 选择 Phase 4 首个开发模块

**已完成 (2026-06-02)**:
- [x] 8D 根因+措施推荐 (D4/D5 智能推荐：FMEA 图匹配 + 规则引擎 + 推荐面板)

**Phase 3 已完成 (2026-06-03)**:
10. ~~FMEA 智能推荐接入知识图谱~~ ✅ `_query_graph_similarity` 图谱相似度匹配 + 来源文档标注
11. ~~8D D4/D5 全混合管道升级~~ ✅ HybridRecommendationPipeline（4 D4 源 + 3 D5 源 + FusionEngine + LLMFusionLayer）

**Phase 3 剩余 (待排期)**:
- [x] FMEA 智能推荐 — 接入知识图谱相似度匹配 + 来源文档标注 — ✅ 已完成 (2026-06-03)
- [x] 8D D4/D5 全混合管道升级 (历史 CAPA 匹配 + LLM 增强 + RAG 语义搜索替代关键词子串匹配) — ✅ 已完成 (2026-06-03)
- [x] 变更影响分析 (设计参数变更 → 自动追溯影响范围) — ✅ 已完成 (2026-06-02)
- [x] SPC-FMEA 异常关联推荐 (控制图异常 → 关联 FMEA → 推荐 8D) — ✅ 已完成 (2026-06-02)
- [x] 多人协同编辑 (乐观锁 + 短轮询在线状态) — ✅ 已完成 (2026-06-02)
- [x] 全局知识库脱敏 (跨产品线数据聚合时的敏感信息处理) — ✅ 已完成 (2026-06-02)

**Phase 4 质量趋势 AI 解读已完成 (2026-06-10)**:
1. ~~后端服务~~ ✅ QualityTrendService（规则摘要 + 按需 LLM 深度解读）
2. ~~数据聚合~~ ✅ SPC/CAPA/FMEA 三源聚合 + 模块级权限过滤 + 产品线隔离
3. ~~证据缓存~~ ✅ scope_hash 规范化（列表排序/去重）+ description hash + LLM 超时处理
4. ~~审计日志~~ ✅ ai_interpretation 类型 + 模块过滤 + 限流
5. ~~前端 Widget~~ ✅ QualityTrendAIWidget + AI 分类面板 + stale 检测 + 手动触发
6. ~~API 端点~~ ✅ POST /dashboard/quality-trend/interpret（手动解读）
7. ~~Dashboard 集成~~ ✅ Widget 注册 + 布局持久化 + 前端类型定义

**Phase 4 已完成汇总 (截至 2026-06-10)**:
- [x] MES 集成连接器 — 9 张表 + Mock/REST 双连接器 + Outbox 推送 + 33 并发测试
- [x] PLM 集成连接器 — BOM 查询/导入 FMEA + Part→SC 特殊特性确认；9 张表；4 页前端；46 + 11 测试
- [x] 8D 报告 AI 草拟 — LLM 辅助填充 D2-D8；结构化/段落双格式；限流 + 审计日志
- [x] 质量趋势 AI 解读 — SPC/CAPA/FMEA 三源聚合 + 规则摘要 + 按需 LLM 深度解读 + Widget 集成
- [x] 自定义看板（拖拽式）— react-grid-layout + 18 种 widget + 用户级 layout 存储 + 产品线过滤

**Phase 4 剩余 (待开发)**:
- [ ] SaaS 多租户架构 — Schema 级别隔离 + 弹性资源
- [ ] 供应商风险智能预警
- [ ] 经验教训智能推送
- [ ] 控制计划智能校验
- [ ] IQC 抽样方案智能优化
- [ ] 管理评审报告自动生成
- [ ] 供应链风险地图
