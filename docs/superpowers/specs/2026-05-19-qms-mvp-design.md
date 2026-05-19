# QMS MVP 设计文档

**日期**: 2026-05-19  
**版本**: 1.0  
**状态**: 已批准  

---

## 1. 产品概述

### 1.1 产品愿景

打造以"知识库 + 智能推荐"为核心差异化的新一代智能质量管理平台，实现质量管理的知识驱动与智能化升级。

### 1.2 MVP 范围

基于 PRD v1.2，MVP 聚焦核心闭环：**PFMEA 编辑器 + 8D/CAPA 基础流程 + 仪表盘**，以单产品线可跑通 PFMEA→8D 闭环为验收标准。

| 模块 | 功能 | 优先级 |
|------|------|--------|
| 用户认证 | JWT 用户名密码认证，RBAC 角色（admin/quality_engineer/viewer） | P0 |
| PFMEA 编辑器 | 工序流编辑、FMEA 表格、RPN 计算、状态流转 | P0 |
| 8D/CAPA | D1-D8 步骤流、阶段推进、FMEA 关联 | P0 |
| 仪表盘 | KPI 卡片、趋势图、预警列表 | P0 |

### 1.3 技术栈

| 层级 | 选型 |
|------|------|
| 前端 | React 18 + Vite + Ant Design 5.x + Zustand + TypeScript |
| 后端 | FastAPI + SQLAlchemy + Pydantic + Python 3.11+ |
| 数据库 | PostgreSQL 15+（含 JSONB 图结构） |
| 缓存 | Redis 7+ |
| 部署 | Docker Compose 本地开发环境 |

### 1.4 约束

- 单产品线（硬编码 `DC-DC-100`）
- 简单 JWT 认证，无 SSO/OIDC
- MVP 阶段跳过 Neo4j，用 PostgreSQL JSONB 存储 FMEA 图结构

---

## 2. 数据模型设计

### 2.1 核心表结构

```sql
-- 用户表
CREATE TABLE users (
    user_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(50) UNIQUE NOT NULL,
    display_name   VARCHAR(100),
    email          VARCHAR(100),
    password_hash  VARCHAR(255) NOT NULL,
    role           VARCHAR(20) CHECK (role IN ('admin', 'quality_engineer', 'viewer')),
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FMEA 文档表
CREATE TABLE fmea_documents (
    fmea_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_no      VARCHAR(50) UNIQUE NOT NULL,
    title            VARCHAR(200) NOT NULL,
    fmea_type        VARCHAR(20) CHECK (fmea_type IN ('PFMEA', 'DFMEA')),
    product_line_code VARCHAR(20) DEFAULT 'DC-DC-100',
    status           VARCHAR(20) DEFAULT 'draft',
    version          INTEGER DEFAULT 1,
    graph_data       JSONB DEFAULT '{}',  -- 存储工序→功能→失效→原因→措施树
    created_by       UUID REFERENCES users(user_id),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by      UUID REFERENCES users(user_id),
    approved_at      TIMESTAMP
);

-- 8D 报告表
CREATE TABLE capa_eightd (
    report_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_no      VARCHAR(50) UNIQUE NOT NULL,
    title            VARCHAR(200) NOT NULL,
    product_line_code VARCHAR(20) DEFAULT 'DC-DC-100',
    status           VARCHAR(20) DEFAULT 'd1_team',
    d1_team          JSONB DEFAULT '[]',
    d2_description   TEXT,
    d3_interim       TEXT,
    d4_root_cause    TEXT,
    d5_correction    TEXT,
    d6_verification  TEXT,
    d7_prevention    TEXT,
    d8_closure       TEXT,
    fmea_ref_id      UUID REFERENCES fmea_documents(fmea_id),
    severity         VARCHAR(20),
    due_date         DATE,
    created_by       UUID REFERENCES users(user_id),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 审计日志表
CREATE TABLE audit_logs (
    log_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name       VARCHAR(100) NOT NULL,
    record_id        UUID NOT NULL,
    action           VARCHAR(20) NOT NULL,
    changed_fields   JSONB,
    operated_by      UUID REFERENCES users(user_id),
    operated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_fmea_status ON fmea_documents(status);
CREATE INDEX idx_fmea_pl ON fmea_documents(product_line_code);
CREATE INDEX idx_capa_status ON capa_eightd(status);
CREATE INDEX idx_capa_pl ON capa_eightd(product_line_code);
CREATE INDEX idx_audit_table ON audit_logs(table_name, record_id);
CREATE INDEX idx_audit_time ON audit_logs(operated_at);
```

### 2.2 graph_data JSONB 结构

```json
{
  "nodes": [
    {
      "id": "n1",
      "type": "Process",
      "name": "SMT 贴装",
      "process_number": "OP10"
    },
    {
      "id": "n2",
      "type": "Function",
      "name": "元件贴装"
    },
    {
      "id": "n3",
      "type": "FailureMode",
      "name": "元件偏移",
      "severity": 7,
      "occurrence": 4,
      "detection": 3
    },
    {
      "id": "n4",
      "type": "FailureCause",
      "name": "贴装压力不足"
    },
    {
      "id": "n5",
      "type": "ControlMeasure",
      "name": "定期校准贴片机"
    }
  ],
  "edges": [
    {"source": "n1", "target": "n2", "type": "HAS_FUNCTION"},
    {"source": "n2", "target": "n3", "type": "HAS_FAILURE_MODE"},
    {"source": "n3", "target": "n4", "type": "HAS_CAUSE"},
    {"source": "n4", "target": "n5", "type": "CONTROLLED_BY"}
  ]
}
```

---

## 3. API 设计

### 3.1 认证模块

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/auth/login | 登录，返回 JWT |
| POST | /api/auth/register | 注册（仅 admin） |
| GET | /api/auth/me | 当前用户信息 |

### 3.2 FMEA 模块

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/fmea | FMEA 列表（分页 + 筛选） |
| POST | /api/fmea | 创建 FMEA 文档 |
| GET | /api/fmea/:id | FMEA 详情（含 graph_data） |
| PUT | /api/fmea/:id | 更新 FMEA |
| POST | /api/fmea/:id/transition | 状态流转 |
| GET | /api/fmea/:id/graph | 获取图谱数据 |

### 3.3 8D/CAPA 模块

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/capa | 8D 报告列表 |
| POST | /api/capa | 创建 8D 报告 |
| GET | /api/capa/:id | 8D 报告详情 |
| PUT | /api/capa/:id | 更新 8D 报告 |
| POST | /api/capa/:id/advance | 推进到下一 D 阶段 |
| POST | /api/capa/:id/link-fmea | 关联 FMEA |

### 3.4 仪表盘模块

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/dashboard | 仪表盘聚合数据 |
| GET | /api/dashboard/kpi | KPI 卡片数据 |
| GET | /api/dashboard/trends | 趋势图数据 |
| GET | /api/dashboard/alerts | 预警列表 |

---

## 4. 前端设计

### 4.1 路由设计

```
/                          → 重定向到 /dashboard
/login                     → 登录页
/dashboard                 → 仪表盘主页

/fmea                      → PFMEA 列表页
/fmea/:id                  → PFMEA 编辑器
/fmea/:id?tab=graph        → PFMEA 图谱视图

/capa                      → 8D 报告列表页
/capa/:id                  → 8D 报告详情
/capa/:id?step=d4          → 8D 指定步骤
```

### 4.2 组件树

```
App
├── AuthLayout
│   └── LoginPage
└── AppLayout
    ├── Sidebar
    ├── Header
    └── Content
        ├── DashboardPage
        │   ├── KPICards
        │   ├── TrendChart
        │   └── AlertList
        ├── FMEAListPage
        │   └── FMEATable
        ├── FMEAEditorPage
        │   ├── ProcessFlowPanel
        │   ├── FMEATableEditor
        │   ├── GraphPreviewPanel
        │   └── TransitionBar
        ├── CAPAListPage
        │   └── CAPATable
        └── CAPADetailPage
            ├── StepStepper
            ├── StepForm
            └── FMEALinkPanel
```

---

## 5. 关键交互流程

### 5.1 PFMEA 编辑 → 审批闭环

1. 质量工程师进入 /fmea 列表，点击"新建 PFMEA"
2. 进入编辑器，左侧添加工序 OP10/OP20/...
3. 点击工序，右侧表格逐级添加：功能 → 失效模式 → 失效原因 → 控制措施
4. 填写 S/O/D 评分，RPN 自动计算（S×O×D），AP 自动判定
5. 底部图谱面板实时更新节点 - 关系图
6. 保存 → 状态=DRAFT
7. 点击"提交审核" → 状态=IN_REVIEW
8. 质量经理审批通过 → 状态=APPROVED（或打回 → REWORK）

### 5.2 8D 问题解决流程

1. 工程师进入 /capa 列表，点击"新建 8D"
2. D1: 录入团队信息 → 推进到 D2
3. D2: 填写 5W2H 问题描述，可选关联 FMEA 失效模式 → 推进到 D3
4. D3: 定义临时遏制措施 → 推进到 D4
5. D4: 根因分析（5Why/鱼骨图），系统推荐关联 FMEA 原因 → 推进到 D5
6. D5: 永久纠正措施 → 推进到 D6
7. D6: 验证结果 → 推进到 D7
8. D7: 预防复发措施，自动提示需更新的 FMEA 条目 → 推进到 D8
9. D8: 关闭确认 → 状态=CLOSED

---

## 6. 项目文件结构

```
OpenQMS/
├── docker-compose.yml
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       ├── pages/
│       ├── components/
│       ├── store/
│       └── types/
├── backend/
│   ├── requirements.txt
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models/
│       ├── schemas/
│       ├── api/
│       ├── services/
│       ├── core/
│       └── state_machines/
└── prototypes/
```

---

## 7. 状态机设计

### 7.1 FMEA 状态机

```
DRAFT → IN_REVIEW → APPROVED
                 ↘ REWORK → IN_REVIEW
DRAFT → ARCHIVED
APPROVED → ARCHIVED
```

### 7.2 8D 状态机

```
D1_TEAM → D2_DESCRIPTION → D3_INTERIM → D4_ROOT_CAUSE 
→ D5_CORRECTION → D6_VERIFICATION → D7_PREVENTION 
→ D8_CLOSURE → ARCHIVED
```

状态转换规则复用原型 `prototypes/qms_state_prototype/models.py` 中的定义。

---

## 8. 非功能性需求

| 指标 | 目标值 |
|------|--------|
| 页面加载时间 | ≤ 2s (P95) |
| API 响应时间 | ≤ 500ms (P95) |
| 并发用户数 | 50 人（MVP） |
| 数据隔离 | 单产品线（MVP） |

---

## 9. 验收标准

1. **用户认证**: 可注册/登录，JWT 认证通过，角色权限生效
2. **PFMEA 编辑器**: 可创建 PFMEA，编辑工序流和 FMEA 表格，RPN 自动计算，状态流转正常
3. **8D/CAPA**: 可创建 8D 报告，D1-D8 逐步推进，可关联 FMEA
4. **仪表盘**: 显示 KPI 卡片（FMEA 数/8D 数/RPN 均值/超期数），趋势图正常
5. **数据持久化**: 所有数据可正确保存到 PostgreSQL，重启后不丢失

---

## 10. 后续演进

- Phase 1 扩展：DFMEA 编辑器、控制计划、SPC 控制图、特殊特性管理
- Phase 2: 供应商质量管理、客户质量管理、Neo4j 图数据库迁移
- Phase 3: AI 推荐引擎、知识图谱可视化、变更影响分析
