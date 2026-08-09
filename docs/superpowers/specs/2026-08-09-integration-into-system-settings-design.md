# 设计：将 MES/PLM/ERP 集成移入「系统设置」下的「系统集成」子组

**日期**：2026-08-09
**状态**：已批准（用户确认）
**范围**：仅前端侧边栏菜单重组 + i18n。**URL、路由、权限逻辑、页面文件、后端全部不变。**

## 背景

当前侧边栏有三个顶层集成组：MES 集成（`grp:mes`）、PLM 集成（`grp:plm`）、ERP 集成（`grp:erp`），均为一级菜单。需求是把它们收进「系统设置」（`grp:admin`，i18n 标签 `menu.admin` = "系统管理"）模块下，作为子模块。

## 决策（已与用户确认）

- **组织方式**：在系统设置下新建**单一「系统集成」子组**（`grp:integration`），内部再分 MES/PLM/ERP 三个三级组，各自挂原有页面。
- **URL 不变**：`/mes/*`、`/plm/*`、`/erp/*` 全部保留。因此 `App.tsx` 路由、`MENU_KEYS`、dashboard drill-down 链接（`dashboardDrilldown.ts`、`MesEquipmentWidget.tsx` 等）**均无需改动**。
- **权限**：**保留现有模块权限**（`module: "mes"|"plm"|"erp"` 的 `canView` 判断），不套 `adminOnly`。

## 目标菜单结构

```
系统设置 (grp:admin, menu.admin)
├─ AI 配置       /admin/ai-config       adminOnly
├─ 产品类型      /admin/product-types   adminOnly
├─ 产品线        /admin/product-lines   adminOnly
├─ 用户管理      /admin/users           adminOnly
├─ 日志管理      /admin/logs            adminOnly
├─ 审核技能      /admin/review-skills   adminOnly
└─ 系统集成 (grp:integration, menu.integration)   ← 新增子组，无 module/adminOnly
   ├─ MES 集成 (grp:mes, module:"mes")
   │   ├─ /mes/dashboard  MES 看板
   │   ├─ /mes/orders     工单列表
   │   ├─ /mes/scrap      报废/返工
   │   └─ /mes/connections 连接管理
   ├─ PLM 集成 (grp:plm, module:"plm")
   │   ├─ /plm/dashboard  PLM 看板
   │   ├─ /plm/parts      零件列表
   │   ├─ /plm/change-orders 变更单管理
   │   └─ /plm/connections  连接管理
   └─ ERP 集成 (grp:erp, module:"erp")
       ├─ /erp              ERP 看板
       ├─ /erp/connections  连接管理
       ├─ /erp/master-data  主数据
       ├─ /erp/supply-chain 供应链
       ├─ /erp/commercial   销售与成本
       └─ /erp/traceability 批次追溯
```

## 变更点

### 1. `frontend/src/components/layout/AppLayout.tsx`

- **删除**三个顶层组对象 `grp:mes`、`grp:plm`、`grp:erp`（连同其子项整体搬迁）。
- 在 `grp:admin` 的 `children` 末尾**新增** `grp:integration` 子组（无 `module`、无 `adminOnly`），其 `children` 为原 `grp:mes`/`grp:plm`/`grp:erp` 三个组对象（内容原样，仅缩进层级变化）。
- **`MENU_KEY_TO_OPEN_KEYS`**：14 个集成路由的 openKeys 由 `["grp:mes"]` 等改为 `["grp:admin", "grp:integration", "grp:mes"]` 等（前面补两级父组），保证选中时三级菜单正确展开。
- **`MENU_KEYS`**：不变（URL 未变）。

### 2. i18n

- `frontend/src/locales/zh-CN/layout.json`：`menu` 下新增 `"integration": "系统集成"`。
- `frontend/src/locales/en-US/layout.json`：`menu` 下新增 `"integration": "System Integration"`。
- 复用现有 `mesIntegration`/`plmIntegration`/`erpIntegration` 及各页面 key，**不新增其它键**。

## 权限行为说明

`filterMenuByPermission` 对「无 `module` 也无 `adminOnly`」的组直接放行、仅递归过滤子项：

- `grp:integration` 不带 `module`/`adminOnly`：三个子组按各自 `mes/plm/erp` 模块权限过滤；某用户三者皆无权限时子组为空 → 系统集成组自动隐藏。行为正确。
- `grp:admin` 本身也无 `module`/`adminOnly`：非 admin 但拥有任一集成模块权限的用户，会在系统设置下仅看到「系统集成」子组（其余 `adminOnly` 项被 `filterMenuByPermission` 隐藏）。这与现状一致（现状下 mes/plm/erp 本就顶层可见），符合「保留现有模块权限」的选择。

## 验证

- `cd frontend && npm run build`（含 `tsc --noEmit` + vite build）
- `cd frontend && npm run lint`
- 若存在 AppLayout 相关测试则 `npm test`

## 明确不做（YAGNI）

- 不改任何 URL / 路由 / 重定向。
- 不改后端、不改权限矩阵定义。
- 不移动/重命名 `pages/mes`、`pages/plm`、`pages/erp` 文件。
- 不改 dashboard drill-down 链接。
