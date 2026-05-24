# 管理评审模块设计文档

**日期**: 2026-05-24
**状态**: 已批准
**优先级**: P1 (Phase 1 收尾)

---

## 1. 概述

支撑 ISO 9001:2015 §9.3 和 IATF 16949:2016 §9.3.1.1 管理评审要求。自动汇总已上线 6 个模块数据形成评审输入包，记录评审会议纪要和输出措施跟踪闭环。

---

## 2. 数据模型

### 2.1 management_reviews (主表)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| review_id | UUID | PK, default uuid4 | |
| doc_no | VARCHAR(20) | UNIQUE, NOT NULL | MR-YYYY-NNN |
| title | VARCHAR(200) | NOT NULL | 评审主题 |
| review_date | DATE | NOT NULL | 计划评审日期 |
| actual_date | DATE | nullable | 实际评审日期 |
| status | VARCHAR(20) | NOT NULL, default 'draft' | 状态机: draft → data_collected → in_review → closed |
| product_line_id | UUID | FK → product_lines | 产品线 |
| location | VARCHAR(100) | nullable | 评审地点 |
| chair_person_id | UUID | FK → users | 主持人 |
| participants | JSONB | nullable | `[{user_id, name, role, department}]` |
| meeting_minutes | TEXT | nullable | 评审会议纪要 |
| data_package | JSONB | nullable | 自动汇总数据快照 |
| manual_inputs | JSONB | nullable | `{external_factors, resource_adequacy}` |
| created_by | UUID | FK → users | |
| updated_by | UUID | FK → users, nullable | |
| created_at | TIMESTAMP(tz) | default now() | |
| updated_at | TIMESTAMP(tz) | default now() | |

索引:
- ix_mgmt_reviews_status ON (status)
- ix_mgmt_reviews_product_line ON (product_line_id)

CHECK 约束: status IN ('draft', 'data_collected', 'in_review', 'closed')

### 2.2 review_outputs (评审输出/措施跟踪)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| output_id | UUID | PK, default uuid4 | |
| review_id | UUID | FK → management_reviews, NOT NULL | 关联评审 |
| category | VARCHAR(30) | NOT NULL | improvement_opportunity / system_change / resource_need |
| description | TEXT | NOT NULL | 措施描述 |
| responsible_id | UUID | FK → users, nullable | 责任人 |
| due_date | DATE | nullable | 截止日期 |
| status | VARCHAR(20) | NOT NULL, default 'pending' | pending → in_progress → completed |
| completion_notes | TEXT | nullable | 完成说明 |
| created_at | TIMESTAMP(tz) | default now() | |
| updated_at | TIMESTAMP(tz) | default now() | |

CHECK 约束: category IN ('improvement_opportunity', 'system_change', 'resource_need')
CHECK 约束: status IN ('pending', 'in_progress', 'completed')

---

## 3. 状态机

```
draft ──→ data_collected ──→ in_review ──→ closed
  │              │                │
  │              │                └─ 填写纪要 + 添加输出项, Manager/Admin 关闭
  │              └─ 生成数据包快照, 可刷新
  └─ 编辑基本信息
```

转换规则:
- `draft → data_collected`: 必填 title, review_date, chair_person_id; 自动生成数据包快照
- `data_collected → draft`: 回退, 重新编辑
- `data_collected → in_review`: 开始评审
- `in_review → closed`: Manager/Admin 权限; 必须至少有 1 条 output 或 meeting_minutes
- `closed`: 只读; 关联的 output 措施项仍可单独更新状态

角色权限:
- quality_engineer: 创建/编辑 draft
- manager/admin: 所有状态转换 + 关闭

---

## 4. 自动数据包

### 4.1 数据源映射

| # | ISO 9001 §9.3.2 要求 | 数据来源 | 类型 | 聚合逻辑 |
|---|----------------------|---------|------|---------|
| 1 | 以往管理评审措施落实 | review_outputs | 自动 | 历史评审 output 完成率统计 |
| 2 | 质量目标实现程度 | quality_goals | 自动 | active 目标达成率, 按级别汇总 |
| 3 | 审核结果 | audit_programs/plans/findings | 自动 | 最近周期审核发现项统计, 闭环率 |
| 4 | 不合格与纠正措施 | capa_eightd | 自动 | open/in_progress/completed 计数, 平均闭环天数 |
| 5 | FMEA 风险分析 | fmea_documents | 自动 | AP=H 数量, 状态分布 |
| 6 | SPC 过程能力 | SPC 控制图数据 | 自动 | Cpk 分布, 异常事件计数 |
| 7 | 外部供方绩效 | suppliers | 自动 | 评级分布(A/B/C/D), 准交率 |
| 8 | 内外部因素变化 | manual_inputs.external_factors | 手动 | 文本输入 |
| 9 | 资源充分性 | manual_inputs.resource_adequacy | 手动 | 文本输入 |
| 10 | 顾客满意与反馈 | — | 占位 | 模块未上线 |
| 11 | 监视测量结果(设备) | — | 占位 | 模块未上线 |
| 12 | 不良质量成本 | — | 占位 | 模块未上线 |
| 13 | 制造可行性评估 | — | 占位 | 模块未上线 |

### 4.2 数据包 JSONB 结构

```json
{
  "generated_at": "2026-05-24T10:00:00Z",
  "generated_by": "uuid",
  "quality_goals": {
    "total": 15,
    "achieved": 10,
    "on_track": 3,
    "behind": 2,
    "details": [...]
  },
  "internal_audits": {
    "total_programs": 4,
    "total_findings": 23,
    "closed_findings": 18,
    "open_findings": 5,
    "closure_rate": 0.783
  },
  "capa_stats": {
    "total": 30,
    "open": 8,
    "in_progress": 5,
    "closed": 17,
    "avg_closure_days": 12.5
  },
  "fmea_risks": {
    "total_documents": 10,
    "high_ap_count": 3,
    "status_distribution": {"draft": 2, "active": 6, "completed": 2}
  },
  "spc_capability": {
    "total_control_charts": 8,
    "cpk_distribution": {"excellent": 3, "acceptable": 3, "marginal": 1, "poor": 1},
    "out_of_control_events": 5
  },
  "supplier_performance": {
    "total_suppliers": 12,
    "rating_distribution": {"A": 5, "B": 4, "C": 2, "D": 1},
    "on_time_delivery_rate": 0.92
  },
  "previous_review_actions": {
    "total_outputs": 15,
    "completed": 10,
    "overdue": 2,
    "in_progress": 3,
    "completion_rate": 0.667
  }
}
```

### 4.3 手动输入结构

```json
{
  "external_factors": "文本内容...",
  "resource_adequacy": "文本内容..."
}
```

---

## 5. API 设计

### 5.1 评审记录 CRUD

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/management-reviews | 列表(分页+筛选) | 已登录 |
| POST | /api/management-reviews | 创建 | engineer+ |
| GET | /api/management-reviews/{id} | 详情 | 已登录 |
| PUT | /api/management-reviews/{id} | 更新 | engineer+ (draft/data_collected) |
| DELETE | /api/management-reviews/{id} | 删除 | admin (仅 draft) |

### 5.2 状态转换

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /api/management-reviews/{id}/collect-data | draft → data_collected, 生成数据包 | engineer+ |
| POST | /api/management-reviews/{id}/refresh-data | 刷新数据包(仅 data_collected) | engineer+ |
| POST | /api/management-reviews/{id}/back-to-draft | data_collected → draft | engineer+ |
| POST | /api/management-reviews/{id}/start-review | data_collected → in_review | manager+ |
| POST | /api/management-reviews/{id}/close | in_review → closed | manager+ |

### 5.3 评审输出 CRUD

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/management-reviews/{id}/outputs | 措施列表 | 已登录 |
| POST | /api/management-reviews/{id}/outputs | 添加措施 | engineer+ (in_review 状态) |
| PUT | /api/management-reviews/{id}/outputs/{output_id} | 更新措施 | engineer+ |
| DELETE | /api/management-reviews/{id}/outputs/{output_id} | 删除措施 | admin |

### 5.4 手动输入

通过 PUT /api/management-reviews/{id} 更新 manual_inputs 字段。

---

## 6. 前端设计

### 6.1 ManagementReviewListPage

- 评审记录列表, 列: doc_no, title, review_date, status, product_line, chair_person, 措施完成率
- 筛选: status, product_line, date range
- 操作: 创建评审, 查看详情
- 状态标签颜色: draft=蓝, data_collected=青, in_review=橙, closed=绿

### 6.2 ManagementReviewDetailPage

布局分区:
1. **基本信息**: 标题, 日期, 主持人, 参会人员, 产品线, 地点 + 状态操作按钮
2. **数据包区域** (data_collected 及之后显示):
   - 13 个可折叠卡片, 每个对应一个输入源
   - 自动数据源: 展示聚合统计 (数字 + 简要图表)
   - 手动输入源: 文本编辑区
   - 占位数据源: 灰色"模块待开发"提示
   - 刷新按钮 (仅 data_collected)
3. **会议纪要**: 文本编辑区 (in_review 及之后可编辑)
4. **措施跟踪表**: 输出项表格, 支持 CRUD + 状态切换, 列: 类别/描述/责任人/截止日期/状态

### 6.3 导航

- 侧边栏: "管理评审" 菜单项, 图标 TeamOutlined
- 路由: /management-reviews, /management-reviews/:id

---

## 7. 仪表盘扩展

新增 KPI 卡片:
- 管理评审措施完成率: (completed outputs / total outputs) × 100%
- 待关闭措施数量: pending + in_progress 的 output 计数

---

## 8. 文件清单

### 后端
- `backend/app/models/management_review.py` — 2 个 ORM 模型
- `backend/app/schemas/management_review.py` — Pydantic schemas
- `backend/app/services/management_review_service.py` — 业务逻辑 + 数据包聚合
- `backend/app/api/management_review.py` — FastAPI 路由
- `backend/alembic/versions/013_add_management_review.py` — 数据库迁移

### 前端
- `frontend/src/types/managementReview.ts` — TypeScript 接口
- `frontend/src/api/managementReview.ts` — API 调用函数
- `frontend/src/pages/managementReview/ManagementReviewListPage.tsx` — 列表页
- `frontend/src/pages/managementReview/ManagementReviewDetailPage.tsx` — 详情页

### 注册
- `backend/app/models/__init__.py` — 导出模型
- `backend/app/schemas/__init__.py` — 导出 schema
- `backend/app/main.py` — 注册路由
- `frontend/src/App.tsx` — 添加路由
- `frontend/src/components/layout/AppLayout.tsx` — 侧边栏菜单

---

## 9. 文档编号

格式: `MR-{YYYY}-{NNN}`, 自增序列, 示例: MR-2026-001
