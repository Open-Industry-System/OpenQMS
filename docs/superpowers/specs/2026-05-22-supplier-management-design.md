# 供应商管理模块设计文档

**日期**: 2026-05-22  
**状态**: 已批准，待实施  
**方案**: A — 三表扁平结构

---

## 范围

供应商全生命周期管理，涵盖三个子功能：
1. **供应商档案** — 基本信息、资质证书台账、到期预警
2. **准入管理** — 申请→审批→审核联动→批准的状态机流转
3. **绩效评价** — 混合指标（手动打分 + 系统自动拉取）生成百分制得分与字母评级

---

## 数据模型

### `suppliers` 主表

| 字段 | 类型 | 说明 |
|------|------|------|
| supplier_id | UUID PK | |
| supplier_no | VARCHAR | 自动编号 `SUP-YYYY-NNN` |
| name | VARCHAR | 供应商全称 |
| short_name | VARCHAR | 简称（列表显示用） |
| contact_name | VARCHAR | 联系人姓名 |
| contact_phone | VARCHAR | |
| contact_email | VARCHAR | |
| address | VARCHAR | |
| product_scope | TEXT | 供货范围描述 |
| status | ENUM | `pending_review` \| `audit_required` \| `approved` \| `rejected` \| `suspended` |
| audit_plan_id | UUID FK | 关联的产品审核计划（准入审核） |
| reject_reason | TEXT | 拒绝或暂停原因 |
| created_by | UUID FK | 非空 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### `supplier_certifications` 证书台账

| 字段 | 类型 | 说明 |
|------|------|------|
| cert_id | UUID PK | |
| supplier_id | UUID FK | |
| cert_type | VARCHAR | 如 ISO 9001、IATF 16949、RoHS |
| cert_no | VARCHAR | 证书编号 |
| issued_by | VARCHAR | 颁证机构 |
| issue_date | DATE | |
| expiry_date | DATE | 到期预警依据此字段 |
| file_url | VARCHAR | 预留，当前不实现文件上传 |
| created_at | TIMESTAMP | |

### `supplier_evaluations` 绩效评价

| 字段 | 类型 | 说明 |
|------|------|------|
| eval_id | UUID PK | |
| supplier_id | UUID FK | |
| eval_period | VARCHAR | 如 `2026-Q1`、`2026-A` |
| eval_type | ENUM | `quarterly` \| `annual` |
| quality_score | FLOAT | 来料合格率得分（手动，0-100） |
| delivery_score | FLOAT | 交期达成率得分（手动，0-100） |
| service_score | FLOAT | 服务响应得分（手动，0-100） |
| capa_count | INT | 评价期内关联 CAPA 数（快照） |
| finding_count | INT | 评价期内内审发现项数（快照） |
| capa_penalty | FLOAT | CAPA 数对应扣分（快照） |
| finding_penalty | FLOAT | 发现项对应扣分（快照） |
| total_score | FLOAT | 加权总分（0-100） |
| grade | ENUM | `A` \| `B` \| `C` \| `D` |
| notes | TEXT | |
| evaluated_by | UUID FK | 非空 |
| created_at | TIMESTAMP | |

**评分公式**：
- 基础分 = 质量×35% + 交期×30% + 服务×15%（小计最高80分）
- 扣分 = CAPA数×2分 + 发现项数×3分（上限20分）
- 总分 = max(0, 基础分×(80/80×100%) - 扣分) → 映射到0-100区间，实际为：`基础分 - 扣分`（基础分满分80，扣分上限20，总分满分100）

> 精确公式：`total_score = max(0, quality_score×0.35 + delivery_score×0.30 + service_score×0.15 - capa_penalty - finding_penalty)`，满分 = 100×0.80 = 80 + 20（无扣分时）= 100

**评级映射**：≥90→A，75-89→B，60-74→C，<60→D

**扣分规则**：
- 每个 CAPA 扣 2 分，上限 10 分
- 每个内审发现项扣 3 分，上限 10 分
- 总扣分上限 20 分

---

## 状态机

```
pending_review
  ├─[manager/admin 批准]──► audit_required
  └─[manager/admin 拒绝]──► rejected

audit_required
  ├─[关联审核完成，manager/admin 确认]──► approved
  └─[manager/admin 拒绝]──► rejected

approved
  └─[manager/admin 暂停]──► suspended

suspended
  └─[manager/admin 恢复]──► approved
```

- quality_engineer 创建供应商（初始状态 `pending_review`）
- 所有状态流转由 manager/admin 执行
- `audit_required` 状态下，manager 需关联一个已有的 `product` 类型内部审核计划；该审核计划完成后，manager/admin 手动确认批准

---

## API 路由

路由前缀：`/api/suppliers`

### 供应商 CRUD

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/` | 所有已登录用户 | 列表（分页、状态筛选、评级筛选、名称搜索） |
| POST | `/` | engineer+ | 创建供应商档案 |
| GET | `/{id}` | 所有已登录用户 | 档案详情 |
| PUT | `/{id}` | engineer+ | 更新基本信息 |
| GET | `/stats` | 所有已登录用户 | 统计数据 |
| GET | `/expiry-alerts` | 所有已登录用户 | 30/60/90 天内到期证书 |

### 状态流转

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/{id}/approve` | manager/admin | pending_review → audit_required |
| POST | `/{id}/reject` | manager/admin | → rejected（需提供 reason） |
| POST | `/{id}/confirm-approved` | manager/admin | audit_required → approved |
| POST | `/{id}/suspend` | manager/admin | approved → suspended（需提供 reason） |
| POST | `/{id}/reinstate` | manager/admin | suspended → approved |

### 证书台账

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/{id}/certifications` | 所有已登录用户 | 证书列表 |
| POST | `/{id}/certifications` | engineer+ | 添加证书 |
| PUT | `/{id}/certifications/{cid}` | engineer+ | 更新证书 |
| DELETE | `/{id}/certifications/{cid}` | engineer+ | 删除证书 |

### 绩效评价

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/{id}/evaluations` | 所有已登录用户 | 评价历史列表 |
| POST | `/{id}/evaluations` | engineer+ | 新建评价 |
| GET | `/{id}/evaluations/{eid}` | 所有已登录用户 | 评价详情 |

评价记录创建后不可修改（作为历史存档）。

---

## 前端页面

### SupplierListPage (`/suppliers`)

**顶部统计卡片（4张）**：供应商总数 / 待审核数 / 已批准数 / 证书30天内到期数

**筛选栏**：状态下拉 + 最新评级下拉 + 名称/简称搜索框

**主表格**：
- 列：编号 | 简称 | 供货范围（ellipsis） | 状态 Tag | 最新评级 Badge | 证书预警图标 | 操作
- 操作列：查看详情按钮 + 快捷流转按钮（根据状态和角色显示）

**右上角**：新建供应商按钮（engineer+）+ 证书预警抽屉按钮

### SupplierDetailPage (`/suppliers/:id`)

**顶部**：返回按钮 + 供应商名称 + 状态 Tag + 操作按钮组

**Tab 1 — 基本信息**：
- 联系人/地址/供货范围展示/编辑
- 准入进度：显示当前状态流转节点（Steps 组件）
- 若状态为 `audit_required`：显示关联审核计划选择框（从已有 product 类型审核计划中选），或"跳转新建审核"快捷入口

**Tab 2 — 资质证书**：
- 可编辑表格：证书类型/编号/颁证机构/签发日期/到期日期
- 到期日距今 ≤ 30 天：行高亮红色 + 到期日标红

**Tab 3 — 绩效评价**：
- 左侧：历史评价卡片列表（期次 + 总分 + 评级 + 日期）
- 右侧：新建评价表单
  - 评价期次输入（季度/年度）
  - 三项手动分数输入（0-100 滑块+数字输入）
  - 系统自动拉取：评价期内 CAPA 数 + 内审发现项数（只读展示）
  - 实时计算总分预览 + 评级预测
  - 提交按钮

---

## 编号规则

`SUP-YYYY-NNN`，如 `SUP-2026-001`，服务层按年度序号自增（与现有 AP-/PL- 模式一致）。

---

## 已知简化与扩展点

### 当前简化
- 供应商与 CAPA 的关联通过 CAPA `product_line_code` 间接匹配，无强外键——评价时按时间范围统计全局 CAPA 数作为扣分参考，不区分具体供应商归因
- `file_url` 字段预留但不实现文件上传，证书只录元数据
- 绩效评价创建后不可修改（如需更正，新建评价记录即可）

---

## PPAP 生产件批准模块

PPAP（Production Part Approval Process）满足 IATF 16949 §8.3.4.4 要求，记录供应商提交的 18 个 PPAP 元素的批准状态。

### 数据模型

#### `supplier_ppap_submissions`

| 字段 | 类型 | 说明 |
|------|------|------|
| submission_id | UUID PK | |
| supplier_id | UUID FK → suppliers | |
| part_no | VARCHAR(100) | 零件编号 |
| part_name | VARCHAR(200) | 零件名称 |
| submission_level | INT | 提交等级 1-5 |
| submission_date | DATE | 提交日期 |
| status | VARCHAR(20) | draft / submitted / approved / rejected |
| approved_by | UUID FK → users | 批准人 |
| approved_at | TIMESTAMP | |
| notes | TEXT | |
| created_by / created_at / updated_at | | 审计字段 |

#### `supplier_ppap_elements`

| 字段 | 类型 | 说明 |
|------|------|------|
| element_id | UUID PK | |
| submission_id | UUID FK → supplier_ppap_submissions | |
| element_no | INT | 元素编号 1-18 |
| element_name | VARCHAR(200) | 元素名称（如 1.设计记录、2.工程变更文件...） |
| status | VARCHAR(20) | pending / submitted / approved / rejected |
| notes | TEXT | |
| sort_order | INT | |

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/suppliers/{id}/ppap-submissions | PPAP 提交列表 |
| POST | /api/suppliers/{id}/ppap-submissions | 创建 PPAP 提交 |
| GET | /api/suppliers/{id}/ppap-submissions/{sid} | PPAP 详情（含 18 元素） |
| PUT | /api/suppliers/{id}/ppap-submissions/{sid} | 更新 PPAP 提交 |
| POST | /api/suppliers/{id}/ppap-submissions/{sid}/approve | 批准 PPAP |

---

## IQC 来料检验模块

### 数据模型

#### `iqc_inspections`

| 字段 | 类型 | 说明 |
|------|------|------|
| inspection_id | UUID PK | |
| inspection_no | VARCHAR(50) UNIQUE | 编号 `IQC-YYYY-NNN` |
| supplier_id | UUID FK → suppliers | |
| part_no / part_name | VARCHAR | 零件信息 |
| lot_no | VARCHAR(50) | 批次号 |
| lot_qty | INTEGER | 批次数量 |
| sample_qty | INTEGER | 抽样数量 |
| inspection_result | VARCHAR(20) | pending / accepted / rejected / concession |
| defect_qty | INTEGER | 不合格品数 |
| defect_description | TEXT | 不合格描述 |
| linked_capa_id | UUID FK → capa_eightd, nullable | 不合格处置关联的 8D |
| inspection_date | DATE | |
| inspected_by | UUID FK → users | |
| created_at / updated_at | | |

---

## SCAR 供应商纠正措施要求

### 数据模型

#### `supplier_scars`

| 字段 | 类型 | 说明 |
|------|------|------|
| scar_id | UUID PK | |
| scar_no | VARCHAR(50) UNIQUE | 编号 `SCAR-YYYY-NNN` |
| supplier_id | UUID FK → suppliers | |
| source_type | VARCHAR(20) | iqc_reject / audit_finding / customer_complaint / other |
| source_id | UUID, nullable | 关联源单据 ID（IQC inspection / audit finding） |
| description | TEXT | 问题描述 |
| requested_action | TEXT | 要求供应商采取的纠正措施 |
| supplier_response | TEXT | 供应商回复 |
| status | VARCHAR(20) | open / supplier_responded / closed |
| issued_by | UUID FK → users | |
| issued_date | DATE | |
| due_date | DATE | |
| closed_date | DATE | |
| created_at / updated_at | | |

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/suppliers/{id}/scars | SCAR 列表 |
| POST | /api/suppliers/{id}/scars | 创建 SCAR |
| GET | /api/suppliers/{id}/scars/{scar_id} | SCAR 详情 |
| PUT | /api/suppliers/{id}/scars/{scar_id} | 更新 SCAR（含供应商回复） |
| POST | /api/suppliers/{id}/scars/{scar_id}/close | 关闭 SCAR |

---

## 文件结构（更新）

```
backend/
  alembic/versions/016_add_ppap_iqc_scar.py
  app/
    models/
      supplier.py              — Supplier + Certification + Evaluation + PPAP + IQC + SCAR
      iqc_inspection.py        — IqcInspection
    schemas/supplier.py        — 扩展 PPAP / IQC / SCAR schemas
    services/supplier_service.py — 扩展 PPAP / IQC / SCAR 业务逻辑
    api/
      supplier.py              — 扩展路由
      iqc.py                   — IQC 路由
frontend/
  src/
    types/index.ts             — 追加 PPAP / IQC / SCAR 接口
    api/supplier.ts            — 扩展 API 函数
    pages/supplier/
      SupplierDetailPage.tsx   — 新增 PPAP / SCAR Tab
