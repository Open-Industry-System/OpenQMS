# 前端 UX 综合优化设计

**日期：** 2026-05-29
**状态：** 已批准（已修正）

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

将现有 22 个平铺菜单重组为 5 个业务分组。使用 Ant Design `Menu` 的 `SubMenu`（`children` 嵌套）作为业务分组容器，而非 `type: 'group'`。`SubMenu` 支持折叠态 hover 弹出子菜单、展开/收起动画、`openKeys` 受控，更符合需求。

### 分组方案

| 分组 key | 图标 | 菜单项 |
|----------|------|--------|
| `/dashboard` | DashboardOutlined | 仪表盘（独立顶层项，不分组） |
| `grp:planning` | ExperimentOutlined | FMEA 管理、控制计划、APQP 质量策划、PPAP、特殊特性 |
| `grp:shopfloor` | ToolOutlined | SPC 控制图、MSA 分析、质量目标、内部审核、管理评审 |
| `grp:customer` | CustomerServiceOutlined | 客户质量(客诉/RMA)、客户审核、8D/CAPA |
| `grp:supplier` | ShopOutlined | 供应商管理、供货质量看板、SCAR 管理、来料检验(IQC) |

### selectedKeys / openKeys 映射

当前 `AppLayout.tsx:79` 用 `"/" + location.pathname.split("/")[1]` 算选中项。分组后需要维护一个路由→分组映射表：

```typescript
// 路由前缀 → 所属分组 key
const ROUTE_GROUP_MAP: Record<string, string> = {
  "/fmea": "grp:planning",
  "/control-plans": "grp:planning",
  "/apqp": "grp:planning",
  "/ppap": "grp:planning",
  "/special-characteristics": "grp:planning",
  "/spc": "grp:shopfloor",
  "/msa": "grp:shopfloor",
  "/quality-goals": "grp:shopfloor",
  "/internal-audits": "grp:shopfloor",
  "/management-reviews": "grp:shopfloor",
  "/customer-quality": "grp:customer",
  "/customer-audits": "grp:customer",
  "/capa": "grp:customer",
  "/suppliers": "grp:supplier",
  "/iqc": "grp:supplier",
  "/scars": "grp:supplier",
};
```

- `selectedKeys`：保持现有逻辑 `"/" + pathname.split("/")[1]`
- `openKeys`：通过 `ROUTE_GROUP_MAP[selectedKey]` 自动展开当前分组
- 折叠态（`collapsed=true`）：SubMenu 自动变成 popup 子菜单，hover 展开

### 交互细节

- 侧边栏展开时：分组标题可点击展开/收起，子菜单项平铺
- 侧边栏折叠时：分组图标 hover 弹出子菜单浮层（SubMenu 默认行为）
- 当前页面所属分组通过 `openKeys` 自动展开
- IQC 的子菜单（检验单、物料管理）保持现有二级结构，挂在"供应商质量"分组下

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
- **超期 CAPA**：超过 `due_date` 且未关闭的 CAPA，显示编号、超期天数
- **PPM 超标供应商**：PPM>阈值的供应商，显示供应商名称、PPM 值

### 底部区域

- **最近操作**：当前用户最近写操作的 5 个文档（从现有 `audit_logs` 表查询 `user_id` 匹配的记录，按 `created_at` 降序）。注意：audit_logs 记录的是写操作（创建/编辑/审批），不是页面访问。UI 文案用"最近操作"准确，不需要新增 access log
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
    overdue_tasks: number;      // 超期任务数（按 due_date 判断）
    high_risk_items: number;    // 高风险项数（RPN≥100）
    month_trend: number;        // 本月 vs 上月创建量变化
  };
  alerts: {
    high_rpn_fmeas: Array<{
      fmea_id: string;          // 对应 fmea_documents.fmea_id
      document_no: string;      // 对应 fmea_documents.document_no
      node_name: string;        // graph node name
      rpn: number;
    }>;
    overdue_capas: Array<{
      report_id: string;        // 对应 capa_eightd.report_id
      document_no: string;      // 对应 capa_eightd.document_no
      overdue_days: number;     // CURRENT_DATE - due_date
    }>;
    high_ppm_suppliers: Array<{
      supplier_id: string;      // 对应 suppliers.supplier_id
      supplier_name: string;
      ppm: number;
    }>;
  };
  recent_actions: Array<{       // 从 audit_logs 查询
    entity_id: string;          // 操作对象 ID
    entity_type: string;        // 'fmea' | 'capa' | 'control_plan' | ...
    entity_no: string;          // 文档编号
    action: string;             // 'create' | 'update' | 'approve' | ...
    created_at: string;         // ISO datetime
  }>;
}
```

字段命名与现有后端模型保持一致：`fmea_id`、`report_id`、`document_no`、`due_date`。不引入新命名。

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

#### 现有外键（已存在，直接复用）

| 表 | 字段 | 关联 | 说明 |
|----|------|------|------|
| `capa_eightd` | `fmea_ref_id` | → `fmea_documents.fmea_id` | CAPA→FMEA 文档级关联（已存在） |
| `customer_complaints` | `capa_ref_id` | → `capa_eightd.report_id` | 客诉→CAPA 关联（已存在） |
| `customer_complaints` | `fmea_ref_id` | → `fmea_documents.fmea_id` | 客诉→FMEA 关联（已存在） |
| `customer_complaints` | `supplier_responsibility` | boolean | 是否供应商责任（已存在） |
| `customer_complaints` | `scar_ref_id` | UUID | 关联 SCAR（已存在） |

#### 需要升级的关联

1. **CAPA→FMEA：从文档级升级到失效模式节点级**
   - 现有 `capa_eightd.fmea_ref_id` 关联到整个 FMEA 文档
   - 需求是关联到具体的失效模式 graph node
   - **方案：** 在 `capa_eightd` 表新增 `fmea_node_id` (String, nullable)，存储 graph node ID
   - 前端 CAPA 详情页展示关联时，通过 `fmea_ref_id` 找到文档 + `fmea_node_id` 定位到具体行
   - **不需要新增关联表**，扩展现有字段即可

2. **客诉→供应商：新增外键**
   - 现有 `customer_complaints` 有 `supplier_responsibility` (boolean) 但没有 `supplier_id`
   - **新增字段：** `supplier_id` UUID (nullable, FK → `suppliers.supplier_id`)
   - 当 `supplier_responsibility=true` 时，可选择关联具体供应商

#### 新增关联表

3. **`special_characteristic_links` 关联表**
   - `sc_id` UUID (FK → `special_characteristics.id`)
   - `source_type` VARCHAR ('fmea' | 'control_plan')
   - `source_id` UUID (文档 ID)
   - `node_id` VARCHAR (graph node ID，仅 FMEA 需要)
   - 复合唯一约束：(`sc_id`, `source_type`, `source_id`)

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
│   ├── planning/                       # 前期质量策划
│   │   ├── fmea/
│   │   │   ├── FMEAListPage.tsx        ← pages/fmea/FMEAListPage.tsx
│   │   │   └── FMEAEditorPage.tsx      ← pages/fmea/FMEAEditorPage.tsx
│   │   ├── control-plan/
│   │   │   ├── ControlPlanListPage.tsx  ← pages/control-plan/ControlPlanListPage.tsx
│   │   │   └── ControlPlanEditorPage.tsx
│   │   ├── apqp/
│   │   │   ├── APQPListPage.tsx         ← pages/apqp/APQPListPage.tsx
│   │   │   └── APQPDetailPage.tsx
│   │   ├── ppap/
│   │   │   ├── PPAPListPage.tsx         ← pages/ppap/PPAPListPage.tsx
│   │   │   └── PPAPDetailPage.tsx
│   │   └── special-characteristic/
│   │       ├── SCListPage.tsx           ← pages/special-characteristic/SCListPage.tsx
│   │       ├── SCDetailPage.tsx
│   │       ├── SCMatrixPage.tsx
│   │       └── TraceabilityPage.tsx
│   ├── shopfloor/                      # 现场质量管理
│   │   ├── spc/
│   │   │   ├── SPCListPage.tsx         ← pages/spc/SPCListPage.tsx
│   │   │   ├── SPCDetailPage.tsx
│   │   │   └── VersionPanel.tsx
│   │   ├── msa/
│   │   │   ├── GaugeListPage.tsx       ← pages/msa/GaugeListPage.tsx
│   │   │   ├── GaugeDetailPage.tsx
│   │   │   ├── MsaStudyListPage.tsx
│   │   │   └── StudyDetailPage.tsx
│   │   ├── quality-goal/
│   │   │   └── QualityGoalListPage.tsx ← pages/qualityGoal/QualityGoalListPage.tsx
│   │   ├── internal-audit/
│   │   │   ├── InternalAuditListPage.tsx
│   │   │   └── InternalAuditDetailPage.tsx
│   │   └── management-review/
│   │       ├── ManagementReviewListPage.tsx
│   │       └── ManagementReviewDetailPage.tsx
│   ├── customer/                       # 客户质量
│   │   ├── quality/
│   │   │   ├── CustomerQualityPage.tsx ← pages/customerQuality/CustomerQualityPage.tsx
│   │   │   ├── ComplaintDetailPage.tsx
│   │   │   └── RMADetailPage.tsx
│   │   ├── audit/
│   │   │   ├── CustomerAuditListPage.tsx ← pages/customerAudit/CustomerAuditListPage.tsx
│   │   │   └── CustomerAuditDetailPage.tsx
│   │   └── capa/
│   │       ├── CAPAListPage.tsx        ← pages/capa/CAPAListPage.tsx
│   │       └── CAPADetailPage.tsx
│   └── supplier/                       # 供应商质量
│       ├── management/
│       │   ├── SupplierListPage.tsx    ← pages/supplier/SupplierListPage.tsx
│       │   └── SupplierDetailPage.tsx
│       ├── dashboard/
│       │   └── SupplierQualityPage.tsx ← pages/supplier/SupplierQualityPage.tsx
│       ├── scar/
│       │   ├── SCARListPage.tsx        ← pages/scar/SCARListPage.tsx
│       │   └── SCARDetailPage.tsx
│       └── iqc/
│           ├── IqcInspectionListPage.tsx   ← pages/iqc/IqcInspectionListPage.tsx
│           ├── IqcInspectionDetailPage.tsx
│           └── IqcMaterialListPage.tsx
├── components/
│   ├── layout/
│   │   └── AppLayout.tsx               # 侧边栏分组重构
│   ├── shared/
│   │   ├── KPICard.tsx
│   │   └── ImportExcelDialog.tsx
│   ├── cross-links/                    # 新增
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

所有 `←` 标记表示从现有位置迁移。页面文件全部已存在，无遗漏。

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

| 阶段 | 内容 | 预估工作量 | 说明 |
|------|------|-----------|------|
| P1 | 侧边栏分组重构 | 0.5 天 | Menu SubMenu + selectedKeys/openKeys 映射 |
| P2 | 仪表盘重设计（前端+后端 API） | 2 天 | 新增 summary/alerts/recent_actions API + 前端三层布局 |
| P3 | 跨模块关联 — 数据库 + API | 3 天 | Alembic 迁移（fmea_node_id、supplier_id、sc_links 表）、服务层、schemas |
| P4 | 跨模块关联 — 前端组件 + 集成 | 4 天 | cross-links 组件、各详情页集成、FMEA graph node 定位跳转 |
| P5 | 目录重构（逐模块迁移） | 1 天 | 纯机械移动文件 + 更新 import，最后执行避免与 P3/P4 冲突 |

**总计约 10.5 天**。

**执行顺序：P1→P2→P3→P4→P5**

P5 放最后的原因：目录迁移产生大量 import diff，如果在 P3/P4 之前做，后续功能开发的 PR 会和迁移 PR 产生合并冲突。先完成所有功能改动，最后做纯机械的文件移动。

---

## 6. 技术难点：FMEA Graph Node 定位

FMEA 数据以 JSONB graph 存储（`graph_data` 列），失效模式是 graph 中的一个 node（`type: 'FailureMode'`），不是独立的表行。CAPA 关联到失效模式节点级时：

- **存储：** `capa_eightd.fmea_node_id` 存储 node UUID（graph 内部 ID）
- **前端跳转：** CAPA 详情页点击"查看关联 FMEA"时，需要：
  1. 跳转到 `/fmea/:fmea_id`
  2. URL 携带 `?node=<fmea_node_id>` 参数
  3. FMEA 编辑器解析参数，自动展开 graph→table 对应行，高亮该失效模式
- **graph→table 转换：** 复用现有 `fmeaTable.ts` 的 `graphToRows()` 逻辑，找到 node 所在行索引，调用 `scrollToRow()`
- **多 CAPA 关联：** 一个失效模式节点可被多个 CAPA 引用（一对多），不需要关联表，`fmea_node_id` 在 CAPA 侧存储即可

这个跳转逻辑是 P4 中最复杂的部分，需要 FMEA 编辑器支持 URL 参数定位。

---

## 7. 技术约束

- UI 语言保持中文（zh_CN）
- 不引入新的第三方 UI 库，使用现有 Ant Design 5.x 组件
- 前端路由路径不变，保持向后兼容
- 产品线筛选器逻辑不变
- 角色权限模型不变（4 级 RBAC）
