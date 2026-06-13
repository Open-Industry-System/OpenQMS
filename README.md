# OpenQMS

> OpenQMS is a full-stack quality management platform for Chinese manufacturing, covering FMEA (AIAG-VDA 7-step), 8D/CAPA, SPC, MSA, IQC, supplier management, and more — built for IATF 16949 compliance.

开箱即用的质量管理体系平台，面向中国制造业，覆盖 AIAG-VDA PFMEA/DFMEA、8D/CAPA、SPC、MSA、IQC、供应商管理等核心模块，助力 IATF 16949 合规。

**[English documentation →](README_EN.md)**

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **FMEA** | AIAG-VDA 七步法 PFMEA/DFMEA，图模型编辑，RPN/AP 自动计算，审批流转 |
| **8D / CAPA** | D1–D8 步骤推进，团队组建，FMEA 关联，审批闭环 |
| **控制计划** | PFMEA 一键生成控制计划，双向同步，版本管理 |
| **特殊特性** | CC/SC 标识，覆盖矩阵，FMEA→CP 联动，追溯视图 |
| **SPC** | X̄-R / I-MR / P/NP/C/U 控制图，8 大判异规则，Cp/Cpk 计算 |
| **MSA** | GR&R、偏倚、线性、稳定性、计数型 Kappa 分析 |
| **IQC** | AQL 抽样方案，检验批管理，AQL 优化配置 |
| **供应商管理** | 供应商档案、绩效评价、供应商风险配置 |
| **SCAR** | 供应商纠正措施要求，5 态生命周期 |
| **客诉 / RMA** | 客诉接单、RMA 退货、CAPA/FMEA 联动 |
| **APQP** | 五阶段门管理，甘特图，交付物检查表 |
| **PPAP** | AIAG 18 要素，5 态生命周期，Level 1–5 必填映射 |
| **管理评审** | ISO 9001 §9.3 数据包自动汇总，措施跟踪闭环 |
| **内部审核** | 体系/过程/产品审核，检查表，发现项跟踪 |
| **客户审核** | 审核日程，发现项追踪，整改闭环 |
| **质量目标** | 三级目标树，审批流，仪表盘 KPI |
| **ERP / MES / PLM** | 外部系统集成看板与数据同步 |
| **知识图谱** | FMEA/CP 知识关联与可视化 |
| **集团管理** | 多工厂看板，工厂对比，集团供应商与审核 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11 / FastAPI 0.115 (async) / SQLAlchemy 2.0 (async) / PostgreSQL 15 / Redis 7 |
| 前端 | React 18 / TypeScript 5.6 / Vite 5.4 / Ant Design 5.21 |
| 基础设施 | Docker Compose / Alembic (迁移) / Neo4j 5 (知识图谱) / Ollama (AI 推荐) |

---

## 快速开始

### 前提条件

- [Docker](https://www.docker.com/get-started) 与 Docker Compose
- 4 GB+ 可用内存（Neo4j + Ollama 各占 256–512 MB）

### 1. 启动服务

```bash
git clone https://github.com/your-org/OpenQMS.git
cd OpenQMS
docker compose up -d
```

等待所有容器健康（约 30 秒）：

```bash
docker compose ps   # 确认 db/redis/neo4j 为 healthy，backend/frontend 为 running
```

### 2. 初始化数据库

```bash
docker compose exec backend alembic upgrade head
```

### 3. 导入演示数据

```bash
docker compose exec backend python -m app.seed
```

输出 `Seed data created successfully!` 即成功。

### 4. 访问系统

浏览器打开 **http://localhost:5173**，使用以下账号登录：

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| `admin` | `Admin@2026` | 系统管理员 | 全部权限，可管理用户与权限 |
| `engineer` | `Engineer@2026` | 现场质量工程师 | FMEA/SPC/MSA 编辑，CAPA 编辑 |
| `manager` | `Manager@2026` | 质量经理 | 审批权限，可关闭 CAPA |
| `viewer` | `Viewer@2026` | 只读用户 | 所有模块只读 |
| `groupadmin` | `GroupAdmin@2026` | 系统管理员（集团） | 多工厂管理权限 |

> ⚠️ 演示密码仅用于开发环境，生产环境请务必修改。

### 5. API 文档

- Swagger UI：**http://localhost:8000/docs**
- ReDoc：**http://localhost:8000/redoc**

---

## 模块支持状态

| 状态 | 说明 |
|------|------|
| ✅ 已完善 | 前后端功能完整，含演示数据 |
| 🔧 开发中 | 后端 API 已就绪，前端部分功能实现 |
| 📋 规划中 | 仅有设计文档，尚未开发 |

| 模块 | 状态 | 说明 |
|------|:----:|------|
| FMEA | ✅ | PFMEA/DFMEA 编辑器，审批流转 |
| 8D / CAPA | ✅ | D1–D8 步骤推进，FMEA 关联 |
| 控制计划 | ✅ | PFMEA 一键生成，版本管理 |
| 特殊特性 | ✅ | CC/SC 标识，覆盖矩阵，追溯 |
| SPC | ✅ | 控制图 + 判异 + 过程能力 |
| MSA | ✅ | GR&R / 偏倚 / 线性 / 稳定性 / Kappa |
| IQC | ✅ | AQL 抽样，检验批，AQL 优化 |
| 供应商 | ✅ | 档案 + 绩效 + 风险配置 |
| SCAR | ✅ | 5 态生命周期 |
| 客诉 / RMA | ✅ | 客诉 + 退货 + CAPA 联动 |
| APQP | ✅ | 五阶段门 + 甘特图 |
| PPAP | ✅ | 18 要素，Level 1–5 |
| 管理评审 | ✅ | 数据包汇总 + 措施跟踪 |
| 内部审核 | ✅ | 三类审核 + 发现项 |
| 客户审核 | ✅ | 审核日程 + 整改闭环 |
| 质量目标 | ✅ | 三级目标树 + KPI |
| 供应商风险 | ✅ | 风险规则配置 + 风险看板 |
| 供应链风险地图 | ✅ | 多维风险热力图 |
| 集团管理 | ✅ | 多工厂看板 + 对比 + 集团供应商 |
| ERP 集成 | ✅ | 看板 + 连接配置 + 数据同步 |
| MES 集成 | ✅ | 看板 + 连接配置 + 生产/报废数据 |
| PLM 集成 | ✅ | 零件/BOM/变更单 + Mock 连接器 |
| 知识图谱 | ✅ | Neo4j 可视化 + FMEA/CP 关联 |
| 变更影响 | ✅ | 影响分析 + 风险评分 |

---

## 文档目录

| 文档 | 说明 |
|------|------|
| [部署指南](docs/deployment.md) | Docker / 本地开发环境搭建 |
| [架构概览](docs/architecture.md) | 前后端架构、权限模型、数据流 |
| [用户指南](docs/user-guide.md) | 登录、导航、通用操作 |
| [管理员指南](docs/admin-guide.md) | 用户管理、权限配置、工厂分配 |
| [权限参考](docs/permissions.md) | 完整权限矩阵 |
| [开发指南](docs/development.md) | 开发约定、添加新模块 |
| [路线图](docs/ROADMAP.md) | 开发计划与进度 |

### 模块手册

| 手册 | 覆盖模块 |
|------|----------|
| [策划与 FMEA](docs/modules/planning.md) | FMEA、控制计划、APQP、PPAP、特殊特性 |
| [CAPA / 8D](docs/modules/capa.md) | 8D 步骤推进、审批流转 |
| [IQC 与供应商](docs/modules/iqc-supplier.md) | 来料检验、供应商管理、供应商风险、供应链风险地图 |
| [SPC 与 MSA](docs/modules/spc-msa.md) | 统计过程控制、测量系统分析 |
| [客户质量](docs/modules/customer-quality.md) | 客诉、RMA、客户审核、SCAR |
| [管理评审与质量目标](docs/modules/management-review.md) | 管理评审、质量目标、仪表盘 |
| [ERP / MES / PLM](docs/modules/erp-mes-plm.md) | 外部系统集成 |
| [知识图谱与变更影响](docs/modules/knowledge-graph.md) | 知识图谱可视化、变更影响分析 |
| [集团管理](docs/modules/group.md) | 多工厂、集团供应商、集团审核 |

---

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。