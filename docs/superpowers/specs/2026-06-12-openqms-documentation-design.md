# OpenQMS 产品文档与 README 编写设计

## 目标

为 OpenQMS 项目编写一份面向最终用户的完整 README 与产品文档，降低新用户上手成本，明确各质量模块的使用方式与权限要求。

## 文档范围

- **README.md**（项目根目录）：项目简介、核心能力、技术栈、快速启动、默认账号、目录指引。
- **docs/user-guide.md**：全局使用指南，包括登录、工厂/产品线切换、列表页通用操作、审批流程。
- **docs/deployment.md**：Docker 与本地开发环境部署、数据库迁移、环境变量说明。
- **docs/architecture.md**：前后端架构、权限模型、数据模型概览、模块间数据流。
- **docs/permissions.md**：更新现有权限说明，补充新模块权限点。
- **docs/modules/*.md**：按功能域划分的模块用户手册：
  - `fmea-capq.md`：FMEA / 控制计划 / 特殊特性
  - `capa.md`：8D / CAPA
  - `iqc-supplier.md`：来料检验、供应商管理、供应商风险、供应链风险地图
  - `spc-msa.md`：SPC、MSA、量具管理
  - `customer-quality.md`：客诉、客户审核、SCAR、出货
  - `management-review.md`：管理评审、质量目标、看板
  - `apqp-ppap.md`：APQP、PPAP
  - `erp-mes-plm.md`：ERP / MES / PLM 集成
  - `change-impact.md`：变更影响分析
  - `knowledge-base.md`：知识库与智能推荐（如已实现前端入口）

## 文档风格

- 以中文为主，技术术语保留英文缩写（FMEA、CAPA、SPC 等）。
- 每个模块包含：功能概述、适用角色、关键概念、操作步骤、字段说明、常见问题。
- 使用 Markdown 表格展示角色权限和关键字段。
- 配图占位说明：后续可补充截图，初版以文字描述为主。

## 关键信息来源

- `CLAUDE.md` 与 `AGENTS.md`：项目架构与约定。
- `docs/ROADMAP.md`：已实现模块与路线图。
- `docs/permissions.md`：现有权限模型。
- `backend/app/api/` 与 `backend/app/services/`：模块接口与业务能力。
- `frontend/src/pages/`：已实现前端页面。
- `docker-compose.yml` 与 `backend/seed.py`：部署与演示数据。

## 成功标准

1. 新用户仅通过 README 即可在 10 分钟内完成 Docker 启动并登录系统。
2. 每个已上线模块都有对应用户手册，说明入口、操作路径和权限限制。
3. 权限矩阵覆盖 admin / manager / quality_engineer / viewer 四个角色在各模块的能力。
4. 文档结构清晰，README 中提供到各文档的链接。

## 实现计划

1. 使用 Workflow 并行分析后端 API、服务、模型、前端页面与现有文档。
2. 汇总模块清单与功能要点。
3. 按上述结构撰写 README.md 与 docs/ 下各文档。
4. 本地验证 Markdown 链接与结构，提交变更。
