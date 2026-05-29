# 前端 UX 综合优化设计

**日期：** 2026-05-29
**状态：** 已批准

## 背景

当前前端存在三个核心问题：
1. 侧边栏 22 个菜单项平铺，无分组，用户找不到模块
2. 仪表盘 14 个 KPI 卡片堆叠，信息密度高但没有层次，抓不住重点
3. 模块之间无交叉引用，CAPA、FMEA、客诉、供应商等各自孤立

## 目标

- 按业务流程重组导航结构
- 仪表盘成为"作战指挥中心"，一眼看到关键问题
- 建立模块间关联，支持从任一端跳转到另一端
- 物理目录重构，提升代码可维护性

---

## 1. 侧边栏导航重构

将现有 22 个平铺菜单重组为 5 个业务分组，使用 Ant Design `Menu` 的 `type: 'group'` + `children` 实现。

### 分组方案

| 分组 | 菜单项 |
|------|--------|
| **仪表盘** | 仪表盘（独立项，不分组） |
| **前期质量策划** | FMEA 管理、控制计划、APQP 质量策划、PPAP、特殊特性 |
| **现场质量管理** | SPC 控制图、MSA 分析、质量目标、内部审核、管理评审 |
| **客户质量** | 客户质量(客诉/RMA)、客户审核、8D/CAPA |
| **供应商质量** | 供应商管理、供货质量看板、SCAR 管理、来料检验(IQC) |

### 交互细节

- 侧边栏展开时：分组标题 + 子菜单项
- 侧边栏折叠时：只显示图标，hover 显示子菜单弹出层
- 当前页面所属分组自动展开
- IQC 的子菜单（检验单、物料管理）保持现有二级结构

---

## 2. 仪表盘重设计

从当前"统计数据堆叠"改为三层结构：待办 → 风险预警 → 快捷操作。

### 布局

```
┌─────────────────────────────────────────────────────┐
│                    质量仪表盘                         │
├─────────────────────────────────────────────────────┤
│  待办事项      超期任务      高风险项      本月趋势    │
│    12            3             5            +2       │
├─────────────────────────────────────────────────────┤
│ 风险预警区                                           │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │ 高 RPN FMEA  │ │ 超期 CAPA    │ │ PPM 超标供应商│ │
│ │              │ │              │ │              │ │
│ │ • PFMEA-001  │ │ • 8D-023     │ │ • 供应商A    │ │
│ │   RPN=180    │ │   超期5天     │ │   PPM=850    │ │
│ │ • DFMEA-003  │ │ • 8D-019     │ │ • 供应商B    │ │
│ │   RPN=150    │ │   超期2天     │ │   PPM=620    │ │
│ └──────────────┘ └──────────────┘ └──────────────┘ │
├─────────────────────────────────────────────────────┤
│ 最近操作                      │ 快速入口            │
│ • PFMEA-001 (2分钟前)        │ [新建 FMEA]         │
│ • 8D-023 (1小时前)           │ [新建 CAPA]         │
│ • 控制计划-CP005 (昨天)       │ [新建客诉]          │
└─────────────────────────────┴───────────────────────┘
```

### 顶部指标卡

4 个数字，每个可点击跳转到对应列表（带筛选条件）：

| 指标 | 点击跳转 |
|------|---------|
| 待办事项 | 跳转到各模块待办列表（待审批 FMEA + 待推进 CAPA + 未关闭客诉） |
| 超期任务 | 跳转到 CAPA 列表，筛选"超期" |
| 高风险项 | 跳转到 FMEA 列表，筛选"RPN≥100" |
| 本月趋势 | 显示本月 vs 上月数据变化量 |

### 风险预警区

3 个卡片，每个显示 top 5 高风险项，每项可点击跳转：

- **高 RPN FMEA**：RPN≥100 的 FMEA 节点，显示文档编号、节点名称、RPN 值
- **超期 CAPA**：超过 target_date 且未关闭的 CAPA，显示编号、超期天数
- **PPM 超标供应商**：PPM>阈值的供应商，显示供应商名称、PPM 值

### 底部区域

- **最近操作**：当前用户最近操作的 5 个文档（需后端记录操作日志或从 audit_logs 查询）
- **快速入口**：新建 FMEA / 新建 CAPA / 新建客诉 的快捷按钮

### 后端 API 扩展

扩展现有 `GET /api/dashboard` 响应，新增字段：

```typescript
interface DashboardData {
  // 现有 KPI 字段保留
  kpi: { ... };

  // 新增
  summary: {
    pending_actions: number;    // 待办总数
    overdue_tasks: number;      // 超期任务数
    high_risk_items: number;    // 高风险项数
    month_trend: number;        // 本月变化量
  };
  alerts: {
    high_rpn_fmeas: Array<{
      document_id: string;
      document_number: string;
      node_name: string;
      rpn: number;
    }>;
    overdue_capas: Array<{
      capa_id: string;
      capa_number: string;
      overdue_days: number;
    }>;
    high_ppm_suppliers: Array<{
      supplier_id: string;
      supplier_name: string;
      ppm: number;
    }>;
  };
  recent_documents: Array<{
    id: string;
    type: string;           // 'fmea' | 'capa' | 'control_plan' | ...
    number: string;
    title: string;
    last_accessed: string;  // ISO datetime
  }>;
}
```

---

## 3. 模块间交叉引用

### 关联矩阵

| 源模块 | 关联目标 | 展示位置 | 交互方式 |
|--------|---------|---------|---------|
| CAPA | FMEA 失效模式 | CAPA 详情页顶部"关联 FMEA"卡片 | 点击跳转 FMEA 编辑器，定位到对应失效模式行 |
| FMEA | CAPA | FMEA 编辑器新增"关联 CAPA"tab | 显示该失效模式发起的所有 CAPA，点击跳转 |
| 客诉 | 供应商 | 客诉详情页"关联供应商"字段 | 选择供应商后，客诉自动出现在供应商详情页 |
| 供应商 | 客诉/IQC/SCAR | 供应商详情页新增三个 tab | 聚合该供应商的所有客诉、IQC 不合格、SCAR |
| IQC | 供应商 | IQC 详情页显示供应商信息 | 点击跳转供应商详情 |
| SCAR | 供应商 | SCAR 详情页显示供应商信息 | 点击跳转供应商详情，SCAR 同时出现在供应商详情 tab |
| APQP | FMEA/控制计划/PPAP | APQP 详情页"子模块进度"卡片 | 每个子模块显示状态+链接，点击跳转 |
| 特殊特性 | FMEA/控制计划 | 特殊特性详情页"使用位置"tab | 显示哪些 FMEA 和控制计划引用了该特性 |
| FMEA/控制计划 | 特殊特性 | FMEA 编辑器列/控制计划列中特殊特性标记 | 点击标记跳转特殊特性详情 |
| CAPA | 客诉 | CAPA 详情页"来源"字段 | 显示从哪个客诉发起，点击跳转 |

### 数据库变更

大部分关联通过现有外键实现。需要新增：

1. **`capa_fmea_links` 关联表**
   - `capa_id` → capa_eightd.id
   - `fmea_document_id` → fmea_documents.id
   - `failure_node_id` (string, graph node ID)

2. **`special_characteristic_links` 关联表**
   - `special_characteristic_id` → special_characteristics.id
   - `source_type` ('fmea' | 'control_plan')
   - `source_id` (document UUID)
   - `node_id` (string, graph node ID)

3. **客诉表新增字段**
   - `supplier_id` UUID (nullable, FK → suppliers)

4. **CAPA 表新增字段**
   - `complaint_id` UUID (nullable, FK → customer_complaints)

### 通用关联组件

新增 `components/cross-links/` 目录，存放可复用的关联展示组件：

- `RelatedCAPAList` — 显示关联的 CAPA 列表，带跳转链接
- `RelatedFMEALink` — 显示关联的 FMEA 文档，带跳转链接
- `SupplierBadge` — 显示关联供应商信息，点击跳转
- `APQPProgressCard` — 显示 APQP 子模块进度，带各子模块链接
- `SpecialCharacteristicTag` — 特殊特性标记，点击跳转详情

---

## 4. 目录与路由重构

### 新目录结构

```
frontend/src/
├── pages/
│   ├── dashboard/
│   │   └── DashboardPage.tsx
│   ├── planning/                    # 前期质量策划
│   │   ├── fmea/
│   │   │   ├── FMEAListPage.tsx
│   │   │   └── FMEAEditorPage.tsx
│   │   ├── control-plan/
│   │   │   ├── ControlPlanListPage.tsx
│   │   │   └── ControlPlanEditorPage.tsx
│   │   ├── apqp/
│   │   │   └── APQPDetailPage.tsx
│   │   ├── ppap/
│   │   │   └── PPAPDetailPage.tsx
│   │   └── special-characteristic/
│   │       ├── SCListPage.tsx
│   │       ├── SCDetailPage.tsx
│   │       ├── SCMatrixPage.tsx
│   │       └── TraceabilityPage.tsx
│   ├── shopfloor/                   # 现场质量管理
│   │   ├── spc/
│   │   │   ├── SPCListPage.tsx
│   │   │   ├── SPCDetailPage.tsx
│   │   │   └── VersionPanel.tsx
│   │   ├── msa/
│   │   │   ├── GaugeListPage.tsx
│   │   │   ├── GaugeDetailPage.tsx
│   │   │   ├── MsaStudyListPage.tsx
│   │   │   └── StudyDetailPage.tsx
│   │   ├── quality-goal/
│   │   │   └── QualityGoalListPage.tsx
│   │   ├── internal-audit/
│   │   │   ├── InternalAuditListPage.tsx
│   │   │   └── InternalAuditDetailPage.tsx
│   │   └── management-review/
│   │       ├── ManagementReviewListPage.tsx
│   │       └── ManagementReviewDetailPage.tsx
│   ├── customer/                    # 客户质量
│   │   ├── quality/
│   │   │   ├── CustomerQualityPage.tsx
│   │   │   ├── ComplaintDetailPage.tsx
│   │   │   └── RMADetailPage.tsx
│   │   ├── audit/
│   │   │   └── CustomerAuditDetailPage.tsx
│   │   └── capa/
│   │       ├── CAPAListPage.tsx
│   │       └── CAPADetailPage.tsx
│   └── supplier/                    # 供应商质量
│       ├── management/
│       │   ├── SupplierListPage.tsx
│       │   └── SupplierDetailPage.tsx
│       ├── dashboard/
│       │   └── SupplierQualityPage.tsx
│       ├── scar/
│       │   └── SCARDetailPage.tsx
│       └── iqc/
│           ├── IqcInspectionListPage.tsx (新增，当前检查列表页不存在)
│           ├── IqcInspectionDetailPage.tsx
│           └── IqcMaterialListPage.tsx
├── components/
│   ├── layout/
│   │   └── AppLayout.tsx            # 侧边栏分组重构
│   ├── shared/
│   │   ├── KPICard.tsx
│   │   └── ImportExcelDialog.tsx
│   ├── cross-links/                 # 新增
│   │   ├── RelatedCAPAList.tsx
│   │   ├── RelatedFMEALink.tsx
│   │   ├── SupplierBadge.tsx
│   │   ├── APQPProgressCard.tsx
│   │   └── SpecialCharacteristicTag.tsx
│   ├── dfmea/
│   ├── control-plan/
│   ├── version/
│   └── supplier/
```

### 路由保持不变

所有 URL 路径不变（`/fmea`、`/capa`、`/suppliers` 等），只改文件物理位置和 import 路径。现有书签和链接不受影响。

### 迁移策略

逐模块迁移，每迁移一个模块：
1. 移动文件到新目录
2. 更新 App.tsx 中的 import 路径
3. 更新模块内部的相对 import
4. 运行 `npm run build` 验证编译通过
5. 手动验证页面功能正常

---

## 5. 实施优先级

| 阶段 | 内容 | 预估工作量 |
|------|------|-----------|
| P1 | 侧边栏分组重构 | 0.5 天 |
| P2 | 仪表盘重设计（前端+后端 API） | 1.5 天 |
| P3 | 目录重构（逐模块迁移） | 1 天 |
| P4 | 跨模块关联（数据库+API+前端组件） | 3 天 |
| P5 | 各页面集成关联组件 | 2 天 |

**总计约 8 天**，建议按 P1→P2→P3→P4→P5 顺序执行。

---

## 6. 技术约束

- UI 语言保持中文（zh_CN）
- 不引入新的第三方 UI 库，使用现有 Ant Design 5.x 组件
- 前端路由路径不变，保持向后兼容
- 产品线筛选器逻辑不变
- 角色权限模型不变（4 级 RBAC）
