# OpenQMS 产品文档与 README 编写设计

## 目标

为 OpenQMS 项目编写一份结构化的 README 与产品文档，面向三类受众：

1. **最终用户**：了解系统有哪些模块、自己能做什么、典型业务流程如何操作。
2. **管理员/部署人员**：完成 Docker 或本地部署、迁移数据库、配置环境变量、理解账号与权限。
3. **开发者**：理解前后端架构、权限模型、模块边界与数据流，便于二次开发。

## 当前项目状态（基于代码库实际结构）

### 已实现的前端路由（`frontend/src/App.tsx`）

| 功能域 | 路由 | 依赖模块 |
|---|---|---|
| 仪表盘 | `/dashboard` | dashboard |
| FMEA | `/fmea`, `/fmea/:id` | fmea |
| CAPA/8D | `/capa`, `/capa/:id` | capa |
| 控制计划 | `/control-plans`, `/control-plans/:id` | planning |
| 质量目标 | `/quality-goals` | quality_goal |
| 内部审核 | `/internal-audits`, `/internal-audits/:id` | audit |
| 客户审核 | `/customer-audits`, `/customer-audits/:id` | customer_audit |
| SPC | `/spc`, `/spc/:id` | spc |
| 供应商 | `/suppliers`, `/suppliers/:id`, `/suppliers/quality` | supplier |
| 供应商风险 | `/supplier-risk`, `/supplier-risk/config` | supplier_risk |
| 供应链风险地图 | `/supply-chain-risk-map` | supply_chain_risk_map |
| MSA | `/msa/gauges`, `/msa/gauges/:id`, `/msa/studies` | msa |
| 特殊特性 | `/special-characteristics`, `/special-characteristics/matrix`, `/special-characteristics/traceability`, `/special-characteristics/:id` | special_characteristic |
| 管理评审 | `/management-reviews`, `/management-reviews/:id` | management_review |
| IQC | `/iqc/inspections`, `/iqc/inspections/:id`, `/iqc/materials`, `/iqc/aql-optimization`, `/iqc/aql-optimization/profiles`, `/iqc/aql-optimization/config` | iqc |
| SCAR | `/scars`, `/scars/:id` | scar |
| APQP | `/apqp`, `/apqp/:id` | planning |
| PPAP | `/ppap`, `/ppap/:id` | ppap |
| 客户质量 | `/customer-quality`, `/customer-quality/complaints/:id`, `/customer-quality/rma/:id` | customer_quality |
| 知识图谱 | `/knowledge-graph` | knowledge_graph |
| 变更影响 | `/change-impact` | — |
| MES | `/mes/dashboard`, `/mes/connections`, `/mes/orders`, `/mes/scrap` | mes |
| PLM | `/plm/dashboard`, `/plm/connections`, `/plm/parts`, `/plm/change-orders` | plm |
| ERP | `/erp`, `/erp/connections`, `/erp/master-data`, `/erp/supply-chain`, `/erp/commercial`, `/erp/traceability` | erp |
| 集团管理 | `/group/dashboard`, `/group/factories`, `/group/comparison`, `/group/suppliers`, `/group/audits` | group |

### 权限模型（`backend/app/core/permissions.py` + `frontend/src/hooks/usePermission.ts`）

- **权限维度**：角色（role_key）+ 模块（ModuleKey）+ 等级（PermissionLevel）+ 工厂/产品线范围。
- **PermissionLevel**：`NONE=0 < VIEW=1 < CREATE=2 < EDIT=3 < APPROVE=4 < ADMIN=5`。
- **角色定义**（`backend/alembic/versions/028_permission_matrix.py`）：
  - `admin`：系统管理员
  - `manager`：质量经理
  - `viewer`：只读用户
  - `customer_qe`：客户质量工程师
  - `supplier_qe`：供应商质量工程师
  - `field_qe`：现场质量工程师（演示账号 `engineer` 对应该角色）
  - `planning_qe`：前期策划质量工程师
- **种子默认账号**（`backend/app/seed.py`）：
  - `admin` / `Admin@2026`
  - `engineer` / `Engineer@2026`（role_key=`field_qe`）
  - `manager` / `Manager@2026`
  - `viewer` / `Viewer@2026`
  - `groupadmin` / `GroupAdmin@2026`

### 默认权限矩阵（简化版）

| 模块 | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|---|---|---|---|---|---|---|---|
| fmea | ADMIN | APPROVE | EDIT | EDIT | VIEW | VIEW | VIEW |
| capa | ADMIN | APPROVE | EDIT | VIEW | EDIT | EDIT | VIEW |
| planning | ADMIN | APPROVE | VIEW | EDIT | VIEW | VIEW | VIEW |
| ppap | ADMIN | APPROVE | NONE | EDIT | EDIT | NONE | VIEW |
| iqc | ADMIN | APPROVE | VIEW | VIEW | EDIT | NONE | VIEW |
| supplier | ADMIN | APPROVE | VIEW | VIEW | EDIT | VIEW | VIEW |
| supplier_risk | ADMIN | APPROVE | — | — | — | — | — |
| supply_chain_risk_map | ADMIN | APPROVE | — | — | — | — | — |
| customer_quality | ADMIN | APPROVE | VIEW | VIEW | NONE | EDIT | VIEW |
| customer_audit | ADMIN | APPROVE | VIEW | VIEW | NONE | EDIT | VIEW |
| scar | ADMIN | APPROVE | VIEW | VIEW | EDIT | VIEW | VIEW |
| spc | ADMIN | APPROVE | EDIT | VIEW | VIEW | VIEW | VIEW |
| msa | ADMIN | APPROVE | EDIT | NONE | NONE | NONE | VIEW |
| special_characteristic | ADMIN | APPROVE | NONE | EDIT | NONE | NONE | VIEW |
| quality_goal | ADMIN | APPROVE | NONE | NONE | NONE | NONE | VIEW |
| audit | ADMIN | APPROVE | VIEW | VIEW | VIEW | VIEW | VIEW |
| management_review | ADMIN | APPROVE | VIEW | VIEW | NONE | NONE | VIEW |
| mes | ADMIN | APPROVE | — | — | — | — | — |
| plm | ADMIN | APPROVE | — | — | — | — | — |
| erp | ADMIN | APPROVE | — | — | — | — | — |
| knowledge_graph | ADMIN | APPROVE | — | — | — | — | — |
| group | ADMIN | EDIT | — | — | — | — | — |
| user_mgmt | ADMIN | VIEW | NONE | NONE | NONE | NONE | NONE |
| permission_mgmt | ADMIN | NONE | NONE | NONE | NONE | NONE | NONE |
| dashboard | ADMIN | APPROVE | VIEW | VIEW | VIEW | VIEW | VIEW |

> 注：`—` 表示该角色在种子数据中未单独配置，实际以管理员在“权限管理”页面设定为准。

## 文档范围

### 1. 最终用户文档

- **README.md**（项目根目录）：
  - 顶部 2-3 句英文简介
  - 项目简介、核心能力、适用场景
  - 技术栈徽章/列表
  - 5 分钟 Docker 快速启动（可验证命令）
  - 默认账号与登录入口
  - 模块支持状态矩阵（已完善 / 开发中 / 规划中）
  - 文档目录链接
- **docs/user-guide.md**：
  - 登录与首页导航
  - 工厂/产品线切换（如已上线）
  - 列表页通用操作（搜索、分页、导出）
  - 审批/状态流转通用说明
  - 个人设置与消息通知
- **docs/modules/*.md**（按功能域合并，避免文件过多）：
  - `planning.md`：FMEA、控制计划、APQP、PPAP、特殊特性
  - `capa.md`：8D / CAPA
  - `iqc-supplier.md`：IQC、供应商、供应商风险、供应链风险地图
  - `spc-msa.md`：SPC、MSA、量具管理
  - `customer-quality.md`：客诉、RMA、客户审核、SCAR、出货/保修
  - `management-review.md`：管理评审、质量目标、看板
  - `erp-mes-plm.md`：ERP / MES / PLM 集成
  - `knowledge-graph.md`：知识图谱、变更影响分析
  - `group.md`：集团/多工厂管理

### 2. 管理员/部署文档

- **docs/deployment.md**：
  - Docker Compose 部署（推荐）
  - 本地开发环境搭建
  - 环境变量说明（`.env.example`）
  - 数据库迁移命令
  - 种子数据命令
  - 常见问题排查
- **docs/admin-guide.md**（新增）：
  - 用户管理
  - 角色与权限配置
  - 工厂/产品线分配
  - 审计日志查看
  - 备份与恢复建议

### 3. 开发者文档

- **docs/architecture.md**：
  - 前后端技术栈与目录结构
  - 请求处理流程（API → Service → Model）
  - 权限校验流程（JWT + RolePermission + Factory/ProductLine 范围）
  - 数据模型概览（核心表关系）
  - 模块间数据流（FMEA → SC → CP → IQC → SPC 等）
  - 如何访问 FastAPI 自动生成的 API 文档（`/docs`、`/redoc`）
- **docs/permissions.md**（更新现有）：
  - 权限模型详解
  - ModuleKey 列表
  - PermissionLevel 含义
  - 默认角色与权限矩阵
  - 工厂/产品线范围说明
- **docs/development.md**（新增）：
  - 后端开发约定（Service 层、手动 AuditLog、ValueError → HTTPException）
  - 前端开发约定（路由注册、权限钩子、API 客户端）
  - 如何添加新模块
  - 测试与提交规范

## 文档风格

- 以中文为主，技术术语保留英文缩写（FMEA、CAPA、SPC、MSA、IQC 等）。
- 每个模块文档包含：功能概述、适用角色、关键概念、前置条件、操作步骤、字段说明、常见问题。
- 使用 Markdown 表格展示路由、权限矩阵和关键字段。
- 截图占位说明：初版以文字描述为主，后续可补充实际界面截图。

## 关键信息来源

- `CLAUDE.md` 与 `AGENTS.md`：项目架构与约定。
- `docs/ROADMAP.md`：已实现模块与路线图。
- `docs/permissions.md`：现有权限模型说明。
- `backend/app/core/permissions.py`：权限等级与模块枚举。
- `backend/alembic/versions/028_permission_matrix.py`：默认角色与权限矩阵。
- `backend/app/seed.py`：默认账号、角色、演示数据。
- `frontend/src/App.tsx`：前端路由与页面清单。
- `frontend/src/hooks/usePermission.ts`：前端模块键与权限等级。
- `backend/app/api/` 与 `backend/app/services/`：模块接口与业务能力。
- `docker-compose.yml` 与 `.env.example`：部署配置。

## 成功标准（可验证）

1. **README 快速启动可复现**：
   - 执行 `docker compose up -d` 后，所有服务健康。
   - 执行 `docker compose exec backend alembic upgrade head` 成功。
   - 执行 `docker compose exec backend python -m app.seed` 成功。
   - 浏览器访问 `http://localhost:5173` 显示登录页。
   - 使用 `admin` / `Admin@2026` 登录成功并进入 `/dashboard`。
2. **每个已上线前端路由对应的模块在文档中有说明**：至少说明入口路径、查看权限、主要操作。
3. **权限矩阵准确**：与 `backend/alembic/versions/028_permission_matrix.py` 中的 `PERMISSION_MATRIX` 一致。
4. **默认账号信息准确**：与 `backend/app/seed.py` 第 966 行输出一致。
5. **文档内部链接有效**：README 中指向 docs/ 各文件的相对链接可正常跳转。

## 文档维护机制

- 新增数据库迁移、API 路由或前端页面时，开发者应同步更新对应模块文档与模块状态矩阵。
- 权限变更需同步更新 `docs/permissions.md`、`docs/admin-guide.md` 与 `docs/architecture.md` 中的权限矩阵。
- 每季度由维护者检查一次文档与代码的一致性，重点核对：
  - 模块状态矩阵
  - 默认账号/密码
  - 环境变量列表
  - 部署命令

## 实现计划

1. **模块清单梳理（Workflow 并行分析）**
   - 输入：`frontend/src/App.tsx`、`backend/app/api/*.py`、`backend/app/core/permissions.py`、`backend/alembic/versions/028_permission_matrix.py`。
   - 输出：模块清单表，字段包括：功能域、路由、依赖 ModuleKey、后端 API 文件、Service 文件、前端页面文件、默认权限等级、文档文件归属、实现状态。
2. **样板文档先行**
   - 优先完成 `README.md`、`docs/deployment.md`、`docs/architecture.md`。
   - 选择 2 个核心模块（建议 `iqc-supplier.md` 与 `customer-quality.md`）写成样板，确认风格与深度。
3. **批量生成模块文档**
   - 基于模块清单表，使用 Workflow 并行生成其余 `docs/modules/*.md`。
4. **权限与管理员文档**
   - 更新 `docs/permissions.md`。
   - 新增 `docs/admin-guide.md`。
5. **验证与提交**
   - 检查 Markdown 链接、表格格式、代码块语言标签。
   - 核对权限矩阵与种子数据。
   - 提交所有变更。
