# 自定义拖拽看板设计文档

**日期**: 2026-06-08
**状态**: 待实现
**方案**: A（react-grid-layout 自由网格）

---

## 1. 背景与目标

当前 `/dashboard` 页面为硬编码布局（4 个 KPI 卡片 + 3 个 Alert 卡片 + 最近操作 + 快速入口），所有用户看到相同界面。

**目标**: 实现用户级可拖拽自定义看板，支持：
- 组件级（widget）拖拽调整位置、调整大小
- 从组件库添加/删除 widget
- 布局保存到后端，按用户持久化
- 扩展到其他模块 KPI（SPC、MSA、IQC、MES 等）

---

## 2. 架构概述

```
前端 (React 18)
├── DashboardPage — 模式切换、数据获取、保存/取消逻辑
├── DashboardGrid — react-grid-layout 包装层
├── WidgetLibraryPanel — 左侧面板，分类展示可添加 widget
├── WidgetWrapper — widget 外壳（标题栏、删除按钮、状态处理）
└── *Widget (14 个) — 具体 widget 渲染组件

后端 (FastAPI)
├── /api/dashboard/layout — GET/PUT 用户布局配置
├── /api/dashboard/widgets — GET 统一 widget 数据接口
├── dashboard_service.get_widgets_data() — 聚合多模块数据
└── user_dashboard_layouts 表 — 存储 JSONB 布局配置
```

---

## 3. 数据库设计

### 3.1 新增表 `user_dashboard_layouts`

| 字段 | 类型 | 约束 | 说明 |
|:---|:---|:---|:---|
| `layout_id` | UUID | PK, `gen_random_uuid()` | 主键 |
| `user_id` | UUID | FK → users.user_id, UNIQUE, ON DELETE CASCADE | 所属用户 |
| `layout_config` | JSONB | NOT NULL | 布局配置 |
| `created_at` | timestamptz | `server_default=now()` | 创建时间 |
| `updated_at` | timestamptz | `server_default=now(), onupdate=now()` | 更新时间 |

### 3.2 `layout_config` JSONB 结构

```json
{
  "lg": [
    { "i": "kpi-pending", "type": "kpi_pending_actions", "x": 0, "y": 0, "w": 3, "h": 2 },
    { "i": "kpi-overdue", "type": "kpi_overdue_tasks", "x": 3, "y": 0, "w": 3, "h": 2 }
  ]
}
```

**响应式持久化策略**：
- 只持久化 **桌面端（`lg` 断点，≥1200px）** 的布局
- `md/sm/xs` 断点由前端根据 `lg` 布局自动计算（等比压缩 + 单列 fallback），不单独存储
- 编辑模式仅在 `lg` / `md` 断点可用；移动端（`sm/xs`）为只读自适应视图

字段说明：
- `i`: 唯一实例 ID，使用 `crypto.randomUUID()` 生成
- `type`: widget 类型标识
- `x`, `y`: 网格坐标
- `w`, `h`: 网格宽高（react-grid-layout 的 grid units）

### 3.3 默认布局

新用户无记录时，后端根据用户**模块权限过滤后**返回默认布局：

```json
{
  "lg": [
    { "i": "kpi-pending", "type": "kpi_pending_actions", "x": 0, "y": 0, "w": 3, "h": 2 },
    { "i": "kpi-overdue", "type": "kpi_overdue_tasks", "x": 3, "y": 0, "w": 3, "h": 2 },
    { "i": "kpi-risk", "type": "kpi_high_risk_items", "x": 6, "y": 0, "w": 3, "h": 2 },
    { "i": "kpi-trend", "type": "kpi_month_trend", "x": 9, "y": 0, "w": 3, "h": 2 },
    { "i": "alert-fmea", "type": "alert_high_rpn_fmea", "x": 0, "y": 2, "w": 4, "h": 4 },
    { "i": "alert-capa", "type": "alert_overdue_capa", "x": 4, "y": 2, "w": 4, "h": 4 },
    { "i": "alert-ppm", "type": "alert_high_ppm_suppliers", "x": 8, "y": 2, "w": 4, "h": 4 },
    { "i": "recent-actions", "type": "recent_actions", "x": 0, "y": 6, "w": 12, "h": 3 }
  ]
}
```

**权限过滤规则**：
- 后端返回默认布局前，先过滤掉用户无权限模块的 widget
- 例如：用户无 `fmea` 权限，则默认布局中不包含 `alert_high_rpn_fmea`
- 前端不做"暂无权限"占位，直接不渲染（后端已保证返回的 widget 均可访问）

---

## 4. 后端 API 设计

### 4.1 GET /api/dashboard/layout

获取当前用户布局配置。

**权限**: `Module.DASHBOARD, PermissionLevel.VIEW`

**响应**（已有记录）:
```json
{
  "layout_id": "uuid",
  "user_id": "uuid",
  "layout_config": { "lg": [...] },
  "created_at": "2026-06-08T10:00:00Z",
  "updated_at": "2026-06-08T10:00:00Z"
}
```

**响应**（无记录，返回默认）:
```json
{
  "layout_id": null,
  "user_id": "uuid",
  "layout_config": { "lg": [...] },
  "created_at": null,
  "updated_at": null
}
```

### 4.2 PUT /api/dashboard/layout

保存当前用户布局配置。

**权限**: `Module.DASHBOARD, PermissionLevel.EDIT`

**请求**:
```json
{
  "layout_config": {
    "lg": [
      { "i": "kpi-pending", "type": "kpi_pending_actions", "x": 0, "y": 0, "w": 3, "h": 2 }
    ]
  }
}
```

**校验规则**:
- `lg` 数组长度 ≤ 20
- 每个 widget 必须包含 `i`, `type`, `x`, `y`, `w`, `h`
- `type` 必须在白名单内（14 个合法类型，见第 6 节）
- `w`, `h` 必须 ≥ 该 widget 的 `minSize`
- **`i` 唯一性**：所有 widget 的 `i` 字段必须互不相同
- **坐标非负**：`x >= 0`, `y >= 0`
- **宽度边界**：`w >= minSize.w` 且 `w <= 12`（总列数）
- **高度边界**：`h >= minSize.h` 且 `h <= 50`
- **水平不越界**：`x + w <= 12`
- **类型过滤**：后端再次校验所有 `type` 对应模块是否在用户权限范围内

**响应**:
```json
{
  "layout_id": "uuid",
  "user_id": "uuid",
  "layout_config": { "lg": [...] },
  "updated_at": "2026-06-08T10:00:00Z"
}
```

### 4.3 GET /api/dashboard/widgets

统一数据接口，按需返回 widget 数据。**只查询用户看板上实际存在的 widget 类型**，避免无用查询。

**权限**: `Module.DASHBOARD, PermissionLevel.VIEW`

**查询参数**:
- `product_line?: string` — 产品线过滤
- `types: string` — **必填**，逗号分隔的 widget type 列表，如 `types=kpi_pending_actions,alert_overdue_capa,spc_abnormal_count`

**边界处理**:
- `types` 缺失或空字符串 → `400 Bad Request`，`{"detail": "types parameter is required"}`
- `types` 包含非法 type → `400 Bad Request`，`{"detail": "unknown widget type: xxx"}`
- `types` 包含重复 type → 自动去重，只查一次
- `types` 包含用户无权限模块的 type → 该 type 被静默忽略，不返回对应模块数据

**响应结构**:
```json
{
  "kpi": {
    "pending_actions": 12,
    "overdue_tasks": 3,
    "high_risk_items": 7,
    "month_trend": 5
  },
  "alerts": {
    "high_rpn_fmeas": [...],
    "overdue_capas": [...],
    "high_ppm_suppliers": [...]
  },
  "recent_actions": [...],
  "spc": {
    "abnormal_count": 2,
    "capability_summary": { "cpk_avg": 1.33, "count": 15 }
  },
  "msa": {
    "gauges_expiring_30d": 4
  },
  "iqc": {
    "pending_inspections": 8
  },
  "mes": {
    "equipment_running": 12,
    "equipment_down": 1,
    "equipment_idle": 3
  },
  "supplier": {
    "ppm_trend": [...]
  }
}
```

**数据聚合逻辑**:
后端根据 `types` 参数，按模块**顺序查询**所需数据（同一 AsyncSession 不适合并发，MVP 采用顺序查询保证稳定性）：
1. 解析 `types` 参数，去重，映射到对应数据模块
2. 按模块顺序执行查询：
   - `kpi` 相关 types → `get_summary()` + `get_dashboard()`
   - `alert` 相关 types → `get_alerts()`
   - `recent_actions` → `get_recent_actions()`
   - `spc_*` → `spc_service` 查询（带 `product_line_codes` 过滤）
   - `msa_*` → `gauge` 表查询（带 `product_line_codes` 过滤）
   - `iqc_*` → `iqc_inspections` 查询（带 `product_line_codes` 过滤）
   - `mes_*` → `mes_equipment_status` 查询（带 `product_line_codes` 过滤）
   - `supplier_*` → `iqc_inspections` 分组查询（带 `product_line_codes` 过滤）

**权限过滤**（双层）：
1. **模块级过滤**：后端根据用户模块权限，跳过无权限模块的查询
2. **行级过滤 (RLS)**：所有查询通过 `get_user_product_line_codes()` 获取用户授权产线，SQL 层做 `product_line_code.in_(codes)` 物理过滤

**容错与错误报告**：
单个模块查询失败（如 MES 表被锁定）不影响其他模块。响应结构增加 `errors` 字段：
```json
{
  "kpi": { "pending_actions": 12, ... },
  "spc": { "abnormal_count": 2, ... },
  "mes": {},
  "errors": {
    "mes": "equipment_status query timeout"
  }
}
```
- 失败模块返回空对象 `{}`
- `errors` 记录失败原因（仅包含失败模块）
- 前端 `WidgetWrapper` 检测到对应模块在 `errors` 中时，显示 error state + retry 按钮
- `errors` 为空对象时前端正常渲染

---

## 5. 前端设计

### 5.1 新增依赖

```bash
npm install react-grid-layout
npm install -D @types/react-grid-layout
```

**CSS 导入**（在 `DashboardPage.tsx` 或全局入口导入）：
```typescript
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
```

### 5.2 Widget 元数据结构

```typescript
// frontend/src/components/dashboard/widgets/types.ts
export type WidgetCategory = "kpi" | "alert" | "chart" | "list" | "shortcut";

export interface WidgetMeta {
  type: string;
  name: string;
  category: WidgetCategory;
  defaultSize: { w: number; h: number };
  minSize: { w: number; h: number };
  module: ModuleKey;
}

export interface WidgetLayoutItem {
  i: string;
  type: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardLayoutConfig {
  lg: WidgetLayoutItem[];
}

export interface WidgetProps {
  data: DashboardWidgetsData;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}
```

### 5.3 Widget 注册表

```typescript
// frontend/src/components/dashboard/widgets/registry.ts
import KpiPendingWidget from "./KpiPendingWidget";
import AlertHighRpnWidget from "./AlertHighRpnWidget";
// ... 其他 widget

export const widgetRegistry: Record<string, WidgetMeta & { component: React.FC<WidgetProps> }> = {
  kpi_pending_actions: {
    type: "kpi_pending_actions",
    name: "待办事项",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiPendingWidget,
  },
  // ... 全部 14 个 widget
};

export function getWidgetMeta(type: string): WidgetMeta | undefined {
  return widgetRegistry[type];
}

export function getWidgetComponent(type: string): React.FC<WidgetProps> | undefined {
  return widgetRegistry[type]?.component;
}
```

### 5.4 页面组件结构

```
DashboardPage
├── 顶部工具栏
│   ├── 标题 "质量仪表盘"
│   ├── [编辑布局] 按钮（仅 canEdit dashboard）
│   └── [刷新] 按钮
│
├── 查看模式
│   └── DashboardGrid (react-grid-layout, isDraggable=false, isResizable=false)
│       └── WidgetWrapper × N
│           └── *Widget 组件
│
└── 编辑模式
    ├── 编辑工具栏
    │   ├── [完成] [取消] [恢复默认]
    │   └── 未保存提示
    ├── 左侧面板: WidgetLibraryPanel
    │   ├── 搜索框
    │   └── 按分类折叠面板 (KPI / Alert / 扩展)
    │       └── WidgetLibraryItem × N（点击添加到画布）
    └── 右侧画布: DashboardGrid (react-grid-layout, isDraggable=true, isResizable=true)
        └── WidgetWrapper × N（带删除按钮）
```

### 5.5 WidgetWrapper 设计

**ResizeObserver + 图表自适应**:
```typescript
// WidgetWrapper.tsx 内部
const containerRef = useRef<HTMLDivElement>(null);
useEffect(() => {
  const el = containerRef.current;
  if (!el) return;
  const ro = new ResizeObserver(
    debounce((entries) => {
      const { width, height } = entries[0].contentRect;
      onResize?.({ width, height });
    }, 200)
  );
  ro.observe(el);
  return () => ro.disconnect();
}, []);
```

- 子图表组件（ECharts / Ant Design Charts）通过 `onResize` 回调触发 `.resize()`
- 防抖 200ms，避免拖拽过程中频繁重绘

**废弃 Widget 防御**:
```typescript
// DashboardPage 加载 layout 时
const validWidgets = layoutConfig.lg.filter(
  item => widgetRegistry[item.type] !== undefined
);
```
- 当后端 JSONB 中存在已废弃/改名的 widget type 时，前端静默过滤，不渲染报错

### 5.6 react-grid-layout 配置

```typescript
const GRID_CONFIG = {
  cols: 12,              // 12 列网格
  rowHeight: 40,         // 每行 40px
  margin: [16, 16],      // widget 间距
  containerPadding: [0, 0],
  breakpoints: { lg: 1200, md: 996, sm: 768, xs: 480 },
  cols: { lg: 12, md: 10, sm: 6, xs: 4 },
};
```

**响应式布局规则**:

react-grid-layout 通过 `layouts` prop 接收各断点布局：
```typescript
<ResponsiveGridLayout
  layouts={{
    lg: layoutConfig.lg,           // 桌面端：用户保存的布局
    md: computeMdLayout(layoutConfig.lg),  // 平板端：自动计算
    sm: computeMobileLayout(layoutConfig.lg), // 移动端：线性排列
    xs: computeMobileLayout(layoutConfig.lg),
  }}
/>
```

**`md` 断点（996px-1200px，10 列）计算规则**:
1. 等比缩放：`w_md = round(w_lg * 10 / 12)`, `x_md = round(x_lg * 10 / 12)`
2. 最小宽度保护：`w_md >= minSize.w`
3. 水平越界修正：`x_md + w_md <= 10`
4. 垂直紧凑：使用 `compactType="vertical"` 自动消除空隙

**`sm/xs` 断点（<768px，6/4 列）计算规则**:
1. 所有 widget 强制 `w = cols`（占满整行）
2. 按 `y` 坐标升序排列，同 `y` 按 `x` 升序
3. 每个 widget 垂直堆叠，无重叠

**编辑模式可用性**:
- 编辑模式仅在 `lg` / `md` 断点可用
- `sm/xs` 断点隐藏「编辑布局」按钮，`isDraggable=false, isResizable=false`

### 5.7 编辑模式交互流程

1. **进入编辑**: 点击「编辑布局」→ 复制当前 layout 到 editState → 显示编辑 UI
2. **添加 widget**: 点击左侧面板 widget → 生成新 `i`（`crypto.randomUUID()`）→ 添加到 `lg` 数组末尾（右下角）
3. **拖拽/调整大小**: react-grid-layout 回调更新 `editState.layout`
4. **删除 widget**: 点击 widget 右上角 🗑️ → 从数组移除
5. **完成**: 调用 `PUT /api/dashboard/layout` → 成功后刷新页面数据 → 切换回查看模式
6. **取消**: 丢弃 `editState` → 恢复 `originalLayout` → 切换回查看模式
7. **恢复默认**: 重置为系统默认布局 → 调用 `PUT` 保存

---

## 6. Widget 清单（MVP：14 个）

### 6.1 现有 Dashboard 复用（8 个）

| # | type | 名称 | 类别 | defaultSize | minSize | 权限模块 |
|:---|:---|:---|:---|:---|:---|:---|
| 1 | `kpi_pending_actions` | 待办事项 | kpi | 3×2 | 2×2 | dashboard |
| 2 | `kpi_overdue_tasks` | 超期任务 | kpi | 3×2 | 2×2 | dashboard |
| 3 | `kpi_high_risk_items` | 高风险项 | kpi | 3×2 | 2×2 | dashboard |
| 4 | `kpi_month_trend` | 本月新增 FMEA | kpi | 3×2 | 2×2 | dashboard |
| 5 | `alert_high_rpn_fmea` | 高 RPN FMEA Top5 | alert | 4×4 | 3×3 | fmea |
| 6 | `alert_overdue_capa` | 超期 CAPA Top5 | alert | 4×4 | 3×3 | capa |
| 7 | `alert_high_ppm_suppliers` | PPM 超标供应商 Top5 | alert | 4×4 | 3×3 | supplier |
| 8 | `recent_actions` | 最近操作 | list | 12×3 | 6×2 | dashboard |

### 6.2 跨模块扩展（6 个）

| # | type | 名称 | 类别 | defaultSize | minSize | 权限模块 | 数据来源 |
|:---|:---|:---|:---|:---|:---|:---|:---|
| 9 | `spc_abnormal_count` | SPC 异常点数 | kpi | 3×2 | 2×2 | spc | spc_service 近7天异常点计数 |
| 10 | `spc_capability_summary` | 过程能力摘要 | chart | 4×4 | 3×3 | spc | CPK/PPK 趋势聚合 |
| 11 | `msa_gauge_expiry` | 量具到期提醒 | kpi | 3×2 | 2×2 | msa | Gauge 表 next_calibration_date |
| 12 | `iqc_pending_inspections` | IQC 待检批次 | kpi | 3×2 | 2×2 | iqc | IqcInspection 状态 pending |
| 13 | `mes_equipment_status` | 设备状态概览 | chart | 4×3 | 3×2 | mes | MESEquipmentStatus 聚合 |
| 14 | `supplier_ppm_trend` | 供应商 PPM 趋势 | chart | 4×4 | 3×3 | supplier | IqcInspection 按供应商分组 |

---

## 7. 权限模型

### 7.1 双层过滤

**前端过滤**（组件库面板）:
```typescript
const visibleWidgets = Object.values(widgetRegistry)
  .filter(w => canView(w.module));
```

**后端过滤**（GET /widgets 响应）:
```python
# 伪代码
if not can_view(user, Module.SPC):
    del data["spc"]
if not can_view(user, Module.MSA):
    del data["msa"]
# ...
```

### 7.2 编辑权限

统一使用 `canEdit("dashboard")` 判断，不按角色硬编码：

- `canEdit("dashboard") === false`：隐藏「编辑布局」按钮（Viewer 角色）
- `canEdit("dashboard") === true`：显示「编辑布局」按钮，可保存布局（Engineer / Manager / Admin）

### 7.3 布局权限清洗

**默认布局**：后端返回前按当前用户模块权限过滤，只包含用户有权限的 widget。

**已保存布局**：用户权限可能随时间变化（如从 Engineer 降级为 Viewer，或管理员撤销某模块权限）。GET / PUT 时后端按当前权限重新清洗：
- 过滤掉无权限模块的 widget
- 返回清洗后的 layout_config
- 前端始终信任后端返回的 widget 列表，不做二次权限判断

---

## 8. 文件清单

### 8.1 新增文件

```
backend/
├── alembic/versions/20260608_add_user_dashboard_layouts.py  # 迁移
├── app/
│   ├── models/user_dashboard_layout.py                       # ORM 模型
│   ├── schemas/dashboard_layout.py                           # Pydantic Schema
│   └── services/dashboard_service.py                         # 扩展：新增 get_widgets_data()

frontend/
├── src/
│   ├── api/dashboard.ts                                      # 扩展 layout API
│   ├── components/dashboard/
│   │   ├── DashboardGrid.tsx                                 # react-grid-layout 包装
│   │   ├── WidgetLibraryPanel.tsx                            # 组件库面板
│   │   ├── WidgetWrapper.tsx                                 # Widget 外壳
│   │   └── widgets/
│   │       ├── types.ts                                      # Widget 类型定义
│   │       ├── registry.ts                                   # Widget 注册表
│   │       ├── KpiPendingWidget.tsx                          # KPI 待办
│   │       ├── KpiOverdueWidget.tsx                          # KPI 超期
│   │       ├── KpiRiskWidget.tsx                             # KPI 高风险
│   │       ├── KpiTrendWidget.tsx                            # KPI 趋势
│   │       ├── AlertHighRpnWidget.tsx                        # Alert 高RPN
│   │       ├── AlertOverdueCapaWidget.tsx                    # Alert 超期CAPA
│   │       ├── AlertHighPpmWidget.tsx                        # Alert PPM
│   │       ├── RecentActionsWidget.tsx                       # 最近操作
│   │       ├── SpcAbnormalWidget.tsx                         # SPC 异常
│   │       ├── SpcCapabilityWidget.tsx                       # SPC 能力
│   │       ├── MsaGaugeExpiryWidget.tsx                      # MSA 量具到期
│   │       ├── IqcPendingWidget.tsx                          # IQC 待检
│   │       ├── MesEquipmentWidget.tsx                        # MES 设备
│   │       └── SupplierPpmWidget.tsx                         # 供应商PPM
│   └── pages/dashboard/
│       └── DashboardPage.tsx                                 # 重写（或大幅改造）
```

### 8.2 修改文件

```
backend/
├── app/
│   ├── api/dashboard.py                                      # 新增 layout/widgets 端点
│   ├── models/__init__.py                                    # 导出 UserDashboardLayout
│   ├── main.py                                               # 无需修改（路由已注册）
│   └── services/dashboard_service.py                         # 新增 get_widgets_data

frontend/
├── src/
│   ├── App.tsx                                               # 无需修改
│   ├── components/layout/AppLayout.tsx                       # 无需修改
│   ├── hooks/usePermission.ts                                # ModuleKey 补充 "mes"
│   └── types/index.ts                                        # 新增 DashboardWidgetsData 等类型
```

---

## 9. 验收标准

### 9.1 功能验收

- [ ] 有完整模块权限的新用户首次访问 `/dashboard` 看到与当前一致的默认布局；权限不足用户看到过滤后的默认布局
- [ ] 点击「编辑布局」进入编辑模式，显示左侧面板 + 可拖拽画布
- [ ] 可从左侧面板添加 widget 到画布
- [ ] 可拖拽 widget 调整位置
- [ ] 可拖拽 widget 边角调整大小（受 minSize 限制）
- [ ] 可删除画布上的 widget
- [ ] 点击「完成」保存布局，刷新页面后布局保持不变
- [ ] 点击「取消」放弃修改
- [ ] 点击「恢复默认」重置为初始布局
- [ ] Viewer 角色看不到「编辑布局」按钮
- [ ] 无权限模块的 widget 不出现在组件库面板

### 9.2 技术验收

- [ ] `npm run build` 通过（TypeScript 无错误）
- [ ] `npm run lint` 通过
- [ ] 后端新增 Alembic 迁移可正常升级/降级
- [ ] 后端 API 响应符合 Pydantic Schema
- [ ] react-grid-layout 响应式断点正常工作（大屏 12 列 → 小屏 4 列）
- [ ] **ResizeObserver**：widget 调整大小后内部图表自动自适应重绘
- [ ] **废弃 Widget 防御**：layout_config 中存在无效 type 时不报错，静默过滤
- [ ] **移动端降级**：屏幕 `< 768px` 时禁用编辑、强制线性布局
- [ ] **按需查询**：GET `/widgets?types=...` 只查询实际用到的 widget 数据
- [ ] **RLS 隔离**：所有跨模块查询均带 `product_line_codes` 过滤
- [ ] **顺序查询**：后端按模块顺序查询各 widget 数据（同一 AsyncSession 安全）
- [ ] **容错**：单个模块查询失败不影响其他 widget 渲染

---

## 10. 扩展点

后续可轻松扩展：
- **新增 Widget**: 在 `registry.ts` 注册 + 添加组件 + 在 `dashboard_service.py` 添加数据查询
- **预设模板**: 在 `layout_config` 中增加 `template_id` 字段，支持管理员配置多套模板
- **共享布局**: 增加 `is_shared` 字段，支持团队共享看板模板
