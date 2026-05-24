# 管理评审模块设计文档

**日期**: 2026-05-24
**状态**: 已批准 (审查修订版)
**优先级**: P1 (Phase 1 收尾)

---

## 1. 概述

支撑 ISO 9001:2015 §9.3 和 IATF 16949:2016 §9.3.1.1 管理评审要求。自动汇总已上线 6 个模块数据形成评审输入包，记录评审会议纪要和输出措施跟踪闭环（含效果验证）。

---

## 2. 数据模型

### 2.1 management_reviews (主表)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| review_id | UUID | PK, default uuid4 | |
| doc_no | VARCHAR(50) | UNIQUE, NOT NULL | MR-YYYY-NNN |
| title | VARCHAR(200) | NOT NULL | 评审主题 |
| review_date | DATE | NOT NULL | 计划评审日期 |
| actual_date | DATE | nullable | 实际评审日期 |
| status | VARCHAR(20) | NOT NULL, default 'draft' | 状态机: draft → data_collected → in_review → closed |
| product_line_code | VARCHAR(20) | FK → product_lines.code, nullable | 产品线编码; NULL=全厂级评审 |
| location | VARCHAR(100) | nullable | 评审地点 |
| chair_person_id | UUID | FK → users | 主持人 |
| participants | JSONB | nullable | `[{user_id, name, role, department}]` |
| meeting_minutes | TEXT | nullable | 评审会议纪要 |
| data_package | JSONB | nullable | 自动汇总数据快照 |
| manual_inputs | JSONB | nullable | 手动输入项 (见 §4.3) |
| attachments | JSONB | nullable | `[{file_name, file_url, uploaded_at, uploaded_by}]` |
| created_by | UUID | FK → users | |
| updated_by | UUID | FK → users, nullable | |
| created_at | TIMESTAMP(tz) | default now() | |
| updated_at | TIMESTAMP(tz) | default now() | |

索引:
- ix_mgmt_reviews_status ON (status)
- ix_mgmt_reviews_product_line ON (product_line_code)

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
| status | VARCHAR(20) | NOT NULL, default 'pending' | pending → in_progress → completed → verified |
| completion_notes | TEXT | nullable | 完成说明 |
| verified_by | UUID | FK → users, nullable | 效果验证人 |
| verified_at | DATE | nullable | 验证日期 |
| verification_notes | TEXT | nullable | 验证结论与效果评估 |
| created_at | TIMESTAMP(tz) | default now() | |
| updated_at | TIMESTAMP(tz) | default now() | |

CHECK 约束: category IN ('improvement_opportunity', 'system_change', 'resource_need')
CHECK 约束: status IN ('pending', 'in_progress', 'completed', 'verified')

---

## 3. 状态机

```
draft ──→ data_collected ──→ in_review ──→ closed
  │              │                │            │
  │              │                │            └─ admin/manager 可有条件重新打开
  │              │                └─ 填写纪要 + 添加输出项, manager/admin 关闭
  │              └─ 生成数据包快照, 可刷新
  └─ 编辑基本信息
```

转换规则:
- `draft → data_collected`: 必填 title, review_date, chair_person_id; 自动生成数据包快照
- `data_collected → draft`: 回退, 重新编辑
- `data_collected → in_review`: engineer+ 可触发开始评审
- `in_review → closed`: manager/admin 权限; 必须至少有 1 条 output 或 meeting_minutes
- `closed → in_review`: 仅 admin/manager; 自动记录 AuditLog (操作人+理由)
- `closed`: 主表只读; 关联的 output 措施项仍可更新 status/completion_notes/verification 字段

措施项状态机:
- `pending → in_progress`: 责任人开始执行
- `in_progress → completed`: 责任人完成执行, 填写 completion_notes
- `completed → verified`: manager/admin 效果验证, 填写 verified_by/verified_at/verification_notes

评审关闭后的措施项字段级锁:
- **锁定(只读)**: category, description, responsible_id, due_date
- **可更新**: status, completion_notes, verified_by, verified_at, verification_notes

角色权限:
- quality_engineer: 创建/编辑 draft, 触发 collect-data/back-to-draft/start-review, 更新自己负责的 output
- manager/admin: 所有权限 + close/reopen + 效果验证(verified)

---

## 4. 自动数据包

### 4.1 数据源映射

| # | ISO 9001 §9.3.2 要求 | 数据来源 | 类型 | 聚合逻辑 |
|---|----------------------|---------|------|---------|
| 1 | 以往管理评审措施落实 | review_outputs | 自动 | 历史评审 output 完成率/验证率统计 |
| 2 | 质量目标实现程度 | quality_goals | 自动 | active 目标达成率, 按级别汇总 |
| 3 | 审核结果 | audit_programs/plans/findings | 自动 | 最近周期审核发现项统计, 闭环率 |
| 4 | 不合格与纠正措施 | capa_eightd | 自动 | open/in_progress/completed 计数, 平均闭环天数 |
| 5 | FMEA 风险分析 | fmea_documents | 自动 | AP=H 数量, 状态分布 |
| 6 | SPC 过程能力 | inspection_characteristics/sample_batches/spc_alarms | 自动 | Cpk 分布, 异常事件计数 |
| 7 | 外部供方绩效 | suppliers/supplier_evaluations | 自动 | 评级分布(A/B/C/D), 交付得分 |
| 8 | 内外部因素变化 | manual_inputs.external_factors | 手动文本 | 文本输入 + 可上传附件 |
| 9 | 资源充分性 | manual_inputs.resource_adequacy | 手动文本 | 文本输入 + 可上传附件 |
| 10 | 顾客满意与反馈 | manual_inputs.customer_satisfaction | 手动录入 | 文本摘要 + 上传附件 (Excel/PPT 报告) |
| 11 | 监视测量结果(设备) | manual_inputs.equipment_monitoring | 手动录入 | 文本摘要 + 上传附件 |
| 12 | 不良质量成本 | manual_inputs.copq | 手动录入 | 文本摘要 + 上传附件 |
| 13 | 制造可行性评估 | manual_inputs.manufacturing_feasibility | 手动录入 | 文本摘要 + 上传附件 |

### 4.2 产品线隔离

数据包聚合根据评审的 `product_line_code` 过滤:
- **product_line_code 有值** (如 `DC-DC-100`): 各模块查询追加 `where(product_line_code == review.product_line_code)` 过滤
- **product_line_code 为 NULL** (全厂级评审): 不过滤, 返回全局统计数据

手动输入项(8-13)不受产品线过滤影响。

### 4.3 数据包 JSONB 结构

```json
{
  "generated_at": "2026-05-24T10:00:00Z",
  "generated_by": "uuid",
  "product_line_code": "DC-DC-100",
  "quality_goals": {
    "total": 15,
    "achieved": 10,
    "on_track": 3,
    "behind": 2
  },
  "internal_audits": {
    "total_programs": 4,
    "total_findings": 23,
    "closed_findings": 18,
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
    "avg_delivery_score": 85.5
  },
  "previous_review_actions": {
    "total_outputs": 15,
    "completed": 10,
    "verified": 8,
    "overdue": 2,
    "in_progress": 3,
    "completion_rate": 0.667
  }
}
```

### 4.4 手动输入结构 (manual_inputs JSONB)

```json
{
  "external_factors": "文本内容...",
  "resource_adequacy": "文本内容...",
  "customer_satisfaction": { "summary": "文本摘要", "attachments": [...] },
  "equipment_monitoring": { "summary": "文本摘要", "attachments": [...] },
  "copq": { "summary": "文本摘要", "attachments": [...] },
  "manufacturing_feasibility": { "summary": "文本摘要", "attachments": [...] }
}
```

未上线模块 (10-13) 提供文本摘要 + 附件上传, 待对应模块上线后切换为自动聚合。

---

## 5. API 设计

### 5.1 评审记录 CRUD

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/management-reviews | 列表(分页+筛选) | 已登录 |
| POST | /api/management-reviews | 创建 | engineer+ |
| GET | /api/management-reviews/{id} | 详情(含 outputs) | 已登录 |
| PUT | /api/management-reviews/{id} | 更新基本信息 | engineer+ (draft/data_collected) |
| DELETE | /api/management-reviews/{id} | 删除 | admin (仅 draft) |

### 5.2 状态转换

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /api/management-reviews/{id}/collect-data | draft → data_collected, 生成数据包 | engineer+ |
| POST | /api/management-reviews/{id}/refresh-data | 刷新数据包(仅 data_collected) | engineer+ |
| POST | /api/management-reviews/{id}/back-to-draft | data_collected → draft | engineer+ |
| POST | /api/management-reviews/{id}/start-review | data_collected → in_review | engineer+ |
| POST | /api/management-reviews/{id}/close | in_review → closed | manager+ |
| POST | /api/management-reviews/{id}/reopen | closed → in_review | admin/manager |

### 5.3 评审输出 CRUD

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/management-reviews/{id}/outputs | 措施列表 | 已登录 |
| POST | /api/management-reviews/{id}/outputs | 添加措施 | engineer+ (in_review 状态) |
| PUT | /api/management-reviews/{id}/outputs/{output_id} | 更新措施 | engineer+ |
| DELETE | /api/management-reviews/{id}/outputs/{output_id} | 删除措施 | admin (in_review 状态) |
| POST | /api/management-reviews/{id}/outputs/{output_id}/verify | 效果验证 completed → verified | manager+ |

关闭后措施更新: PUT 仅允许 status, completion_notes, verification 字段变更; category/description/responsible_id/due_date 锁定为只读。

### 5.4 附件上传

通过 PUT /api/management-reviews/{id} 更新 attachments JSONB 字段。文件上传复用现有上传机制。

---

## 6. 前端设计

### 6.1 ManagementReviewListPage

- 评审记录列表, 列: doc_no, title, review_date, status, product_line, chair_person, 措施完成率
- 筛选: status, product_line, date range
- 操作: 创建评审, 查看详情
- 状态标签颜色: draft=蓝, data_collected=青, in_review=橙, closed=绿

### 6.2 ManagementReviewDetailPage

布局分区:
1. **基本信息**: 标题, 日期, 主持人, 参会人员, 产品线, 地点, 附件上传区 + 状态操作按钮
2. **数据包区域** (data_collected 及之后显示):
   - 13 个可折叠卡片, 每个对应一个输入源
   - 自动数据源(#1-7): 展示聚合统计 (数字 + 简要图表)
   - 手动文本源(#8-9): 文本编辑区
   - 手动录入源(#10-13): 文本摘要 + 附件上传 (标签提示"手动录入, 待模块上线后自动切换")
   - 刷新按钮 (仅 data_collected)
3. **会议纪要**: 文本编辑区 (in_review 及之后可编辑)
4. **措施跟踪表**: 输出项表格, 支持 CRUD + 状态切换, 列: 类别/描述/责任人/截止日期/状态/验证状态
   - 验证操作: manager/admin 点击"效果验证"按钮, 弹窗填写验证结论

### 6.3 导航

- 侧边栏: "管理评审" 菜单项, 图标 TeamOutlined
- 路由: /management-reviews, /management-reviews/:id

---

## 7. 仪表盘扩展

新增 KPI 卡片:
- 管理评审措施完成率: (verified outputs / total outputs) × 100%
- 待验证措施数量: completed (待验证) 的 output 计数

---

## 8. 文件清单

### 后端
- `backend/app/models/management_review.py` — 2 个 ORM 模型
- `backend/app/schemas/management_review.py` — Pydantic schemas
- `backend/app/services/management_review_service.py` — 业务逻辑 + 数据包聚合
- `backend/app/api/management_review.py` — FastAPI 路由
- `backend/alembic/versions/013_add_management_review.py` — 数据库迁移

### 前端
- `frontend/src/types/index.ts` — 新增管理评审相关 TypeScript 接口 (追加到现有文件)
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

---

## 附录 A: 审查修订记录

| # | 审查发现 | 修订内容 |
|---|---------|---------|
| 2.1 | product_line PK 类型不匹配 | `product_line_id UUID` → `product_line_code VARCHAR(20) FK → product_lines.code` |
| 2.2 | 缺少附件支持 | 新增 `attachments JSONB` 字段 |
| 2.3 | 措施缺少效果验证 | 新增 verified_by/verified_at/verification_notes; 状态增加 `verified` |
| 2.4 | 占位模块不可录入 | #10-13 改为手动录入 (文本摘要 + 附件上传), 标注待模块上线后切换 |
| 3.1 | 数据包产品线隔离 | §4.2 明确聚合查询按 product_line_code 过滤逻辑 |
| 3.2 | closed 状态不可逆 | 新增 `closed → in_review` 有条件重新打开 (admin/manager) |
| 3.3 | start-review 权限过严 | `data_collected → in_review` 放开至 engineer+ |
| 4.1 | 前端类型文件位置 | 类型写入 `types/index.ts` 而非独立文件 |
| 4.2 | 关闭后措施字段锁定 | §3 明确关闭后锁定 category/description/responsible_id/due_date |
| 4.3 | doc_no 长度不足 | VARCHAR(20) → VARCHAR(50) |
