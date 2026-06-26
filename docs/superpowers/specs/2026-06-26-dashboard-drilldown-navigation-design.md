# 仪表盘下钻导航设计

**日期**: 2026-06-26
**分支**: `fix/dashboard-admin-pages`
**状态**: 待评审

## 背景

仪表盘上的指标卡（待办事项、超期事项、高风险项、月度趋势）只显示数字，无法跳转到具体问题；Top-5 预警列表（高RPN FMEA / 超期 CAPA / 高PPM 供应商）已展示单号但行不可点击；其他单模块计数卡（SPC 异常 / MSA 量具到期 / IQC 待检 / MES 设备）也无下钻入口。用户无法从仪表盘直接到达想看的具体条目。

## 目标

让仪表盘上每个有意义的指标都能下钻：
- KPI 数字卡片点击 → 跳转到**过滤后的列表页**（聚合卡片用下拉菜单选择分类）。
- Top-5 预警列表行点击 → 跳转到该条目**详情页**。
- 单模块计数卡点击 → 跳转到对应过滤列表。
- 月度趋势卡片为差值指标，**保持不可点**。
- 无模块查看权限的卡片/行**灰显禁用**，点击不响应（避免跳转后被 ProtectedRoute 挡 403）。

## 导航目标映射

### KPI 数字卡片

| 卡片 | 行为 | URL |
|---|---|---|
| 超期事项 `kpi_overdue_tasks` | 直接跳转 | `/capa?overdue=true` |
| 高风险项 `kpi_high_risk_items` | 直接跳转 | `/fmea?high_rpn=true` |
| 待办事项 `kpi_pending_actions` | **下拉菜单**，按分类显示计数后跳转 | `→ /fmea?pending=true`、`/capa?pending_action=true`、`/customer-quality?status=open` |
| 月度趋势 `kpi_month_trend` | **不可点**（差值指标，无明确下钻目标） | — |

待办事项菜单项示例：`▸ FMEA 待办 (3)` / `▸ CAPA 待办 (5)` / `▸ 客诉 待办 (4)`，计数来自后端 `pending_breakdown`。

### Top-5 预警列表（行点击 → 详情页）

| 预警 widget | 目标路由 | 实体ID来源 |
|---|---|---|
| `alert_high_rpn_fmea` | `/fmea/:fmea_id` | `item.fmea_id` |
| `alert_overdue_capa` | `/capa/:report_id` | `item.report_id` |
| `alert_high_ppm_suppliers` | `/suppliers/quality/:supplier_id` | `item.supplier_id` |

### 其他单模块计数卡

| 卡片 | URL |
|---|---|
| SPC 异常 `spc_abnormal_count` | `/spc?abnormal=true` |
| MSA 量具到期 `msa_gauge_expiry` | `/msa/gauges?expiring=30d` |
| IQC 待检 `iqc_pending_inspections` | `/iqc/inspections?status=pending` |
| MES 设备 `mes_equipment_status` | `/mes/dashboard` |

## 前端改动

### 新增 `dashboardDrilldown.ts`

集中维护 widget type → 目标路由/菜单 的映射，避免散落在各 widget。导出：
- `getKpiDrilldown(type, data, canView)` → 返回 `{ kind: 'link', url }` | `{ kind: 'menu', items: [{label, url, count, disabled}] }` | `null`（不可点）。
- `getAlertRowDrilldown(type, item, canView)` → 返回 `{ url }` | `null`。

### KPI widgets

- `KpiOverdueWidget` / `KpiRiskWidget` / `KpiPendingWidget` / `IqcPendingWidget` / `SpcAbnormalWidget` / `MsaGaugeExpiryWidget` / `MesEquipmentWidget`：用 `useNavigate` + `usePermission().canView(module)` 计算 drilldown，传给 `KPICard` 的 `onClick`（已存在）。
- 无权限时传 `disabled`（`KPICard` 已支持 `disabled`，灰显不响应）。
- `KpiPendingWidget`：用 antd `Dropdown` 包裹卡片，菜单项来自 `pending_breakdown`；分类计数为 0 的项仍显示但可点（跳到空列表）；无权限的分类项 `disabled`。
- `KpiTrendWidget`：不传 `onClick`，保持纯展示。

### 预警 widgets

`AlertHighRpnWidget` / `AlertOverdueCapaWidget` / `AlertHighPpmWidget`：
- `List.Item` 增加点击 → `navigate(url)`；hover 高亮、`cursor: pointer`、`tabIndex=0`、Enter/Space 触发（键盘可达）。
- 无该模块查看权限时整行灰显、不响应点击、`tabIndex=-1`。widget 已知 `module`（来自 registry），用 `canView` 守卫。

### 列表页读取 URL 过滤参数（缺失补上）

| 列表页 | 新增读取的参数 | 已支持 |
|---|---|---|
| `CAPAListPage` | — | `?overdue=true`、`?pending_action=true` ✅ |
| `FMEAListPage` | `?high_rpn=true`、`?pending=true`、`?created_this_month=true` | 否（需加 `useSearchParams`） |
| `IqcInspectionListPage` | `?status=pending` | 否（需加 `useSearchParams`） |
| `GaugeListPage` | `?expiring=30d` → 自动打开到期抽屉 | 否（已有到期抽屉状态，需触发） |
| `SPCListPage` | `?abnormal=true` | 否（需加 `useSearchParams`） |

列表页读取到参数后初始化本地 filter state 并触发查询，用户后续操作仍可改 filter。

## 后端改动（最小集）

### `dashboard_service.get_summary`

返回值增加 `pending_breakdown: {fmea, capa, complaint}`。三个计数已在该函数内分别算出（`fmea_pending_count` / `capa_pending_count` / `complaint_pending_count`），当前只返回三者之和 `pending_actions`，仅需补返回分项。

### FMEA 列表 `GET /api/fmea`

增加两个布尔查询参数（复用现有 `status`/`high_rpn` 之外）：
- `pending=true` → `status.in_(["draft", "in_review"])`（一次过滤，避免前端发两次 status 请求）。
- `created_this_month=true` → `created_at >=本月1日`。

`listFMEAs` 前端 API client 同步加这两个参数。

### SPC 列表 `GET /api/spc/inspection-characteristics`

增加 `abnormal=true` → 只返回近 7 天内有 `SPCAlarm.status == "open"` 关联的检验特性（复用 dashboard `get_widgets_data` 中 SPC 异常的判定逻辑）。

### IQC 列表 `GET /api/iqc/inspections`

确认 `status=pending` 过滤已支持；若未支持则补 `status` 查询参数。（预计已支持，实现时验证。）

### MSA 量具

`getExpiringGauges(days)` 后端已存在，无需改；`GaugeListPage` 读取 `?expiring=30d` 后打开到期抽屉并调用该接口。

## 权限处理

- widget 的 `module` 字段已在 `registry.ts` / 后端 `WIDGET_MODULE_MAP` 定义。
- 前端用 `usePermission().canView(module)` 判断：无权限的 KPI 卡传 `disabled`；无权限的预警行灰显。
- 详情页/列表页本身仍由 `ProtectedRoute requiredModule` 兜底。

## 测试

### 前端 (vitest)
- 新增 `dashboardDrilldown.test.ts`：映射函数各分支（link/menu/disabled/null）。
- KPI widget 测试：有权限→点击触发 navigate 正确 URL；无权限→disabled 不触发 navigate；待办菜单展开并按分类 navigate。
- 预警 widget 测试：行点击 navigate 到正确详情路由；无权限行不响应。
- 列表页测试：带 URL 参数挂载 → 初始 filter/查询参数正确（FMEA/IQC/Gauge/SPC 各一）。

### 后端 (pytest)
- `get_summary` 返回 `pending_breakdown` 三项计数正确。
- FMEA 列表 `?pending=true` / `?created_this_month=true` 过滤结果正确。
- SPC 列表 `?abnormal=true` 只返回异常特性。

## 不在范围内

- 不改仪表盘布局编辑/拖拽能力。
- 不新增 widget、不改 widget 数据结构（仅补 `pending_breakdown`）。
- 不为月度趋势卡片加下钻。
- 不改预警列表的 Top-5 数量与排序。