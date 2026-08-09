# 设计：将 MES/PLM/ERP 集成移入「系统设置」下的「系统集成」子组

**日期**：2026-08-09
**状态**：已批准，经评审修订（v2）
**范围**：前端侧边栏菜单重组 + 权限过滤修复 + i18n。**URL、路由、页面文件、后端全部不变。**

## 背景

当前侧边栏有三个顶层集成组：MES 集成（`grp:mes`）、PLM 集成（`grp:plm`）、ERP 集成（`grp:erp`），均为一级菜单。需求是把它们收进「系统设置」（`grp:admin`）模块下，作为子模块。

## 决策（已与用户确认）

- **组织方式**：在系统设置下新建**单一「系统集成」子组**（`grp:integration`），内部再分 MES/PLM/ERP 三个三级组，各自挂原有页面。
- **URL 不变**：`/mes/*`、`/plm/*`、`/erp/*` 全部保留。因此 `App.tsx` 路由、`MENU_KEYS`、dashboard drill-down 链接（`dashboardDrilldown.ts`、`MesEquipmentWidget.tsx` 等）**均无需改动**。
- **权限**：**保留现有模块权限**（`module: "mes"|"plm"|"erp"` 的 `canView` 判断），不套 `adminOnly`。
- **命名**：父组统一叫「**系统设置** / System Settings」。当前 `menu.admin` = "系统管理" / "System Admin"，本设计一并修改该 i18n 标签（zh + en），不改菜单 key。

## 目标菜单结构

```
系统设置 (grp:admin, menu.admin → "系统设置"/"System Settings")
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

### 1. 修复 `filterMenuByPermission`（**必须先做**，P1）

**问题**：现实现 `AppLayout.tsx:305` 对「无 `module` 且无 `adminOnly`」的组直接 `return item`，**递归过滤子树的逻辑（307–311）根本不会执行**。若只把集成组原样搬进 `grp:admin`，则 `grp:admin`/`grp:integration` 都直接放行整棵子树，MES/PLM/ERP 的 `module` 权限被绕过——无权限用户仍看到全部集成菜单，违反「保留现有模块权限」。

**修复**：调整判断顺序——先做当前节点的 `adminOnly`/`module` 校验，再递归过滤 `children`，子节点为空时隐藏父组：

```ts
function filterMenuByPermission(items, canViewFn, isAdmin): MenuItem[] {
  return items
    .map((item) => {
      if (item.adminOnly && !isAdmin) return null;        // 当前节点：adminOnly
      if (item.module && !canViewFn(item.module)) return null; // 当前节点：module 权限
      if (item.children) {                                // 通过当前校验后，递归过滤子树
        const filteredChildren = filterMenuByPermission(item.children, canViewFn, isAdmin);
        if (filteredChildren.length === 0) return null;   // 子树为空 → 隐藏父组
        return { ...item, children: filteredChildren };
      }
      return item;
    })
    .filter((item): item is MenuItem => item !== null);
}
```

关键差异：删除了 `if (!item.module && !item.adminOnly) return item;` 这条提前返回，让**所有带 `children` 的组都进入递归**。

**连带修复（明确列入范围）**：当前 `adminOnly` 子项未被真正过滤的既有问题——修复后 `grp:admin` 下各 `adminOnly` 子项对非 admin 正确隐藏，`grp:admin`/`grp:integration` 在子树全空时自动隐藏。这是同一算法的直接结果，纳入本次范围。

### 2. 菜单结构（`AppLayout.tsx`）

- **删除**三个顶层组对象 `grp:mes`、`grp:plm`、`grp:erp`（连同子项整体搬迁）。
- 在 `grp:admin` 的 `children` 末尾**新增** `grp:integration` 子组（无 `module`、无 `adminOnly`），其 `children` 为原 `grp:mes`/`grp:plm`/`grp:erp` 三个组对象（内容原样，仅缩进层级变化）。
- **`MENU_KEY_TO_OPEN_KEYS`**：14 个集成路由的 openKeys 由 `["grp:mes"]` 等改为 `["grp:admin", "grp:integration", "grp:mes"]` 等（前面补两级父组），保证选中时三级菜单正确展开。
- **`MENU_KEYS`**：不变（URL 未变）。

### 3. i18n

- `zh-CN/layout.json`：`menu` 下新增 `"integration": "系统集成"`；并将 `"admin"` 由 `"系统管理"` 改为 `"系统设置"`。
- `en-US/layout.json`：`menu` 下新增 `"integration": "System Integration"`；并将 `"admin"` 由 `"System Admin"` 改为 `"System Settings"`。
- 复用现有 `mesIntegration`/`plmIntegration`/`erpIntegration` 及各页面 key，**不新增其它键**。

## 权限行为（修复后）

- `grp:integration` 不带 `module`/`adminOnly`：三个子组按各自 `mes/plm/erp` 模块权限过滤；某用户三者皆无权限时子组为空 → 「系统集成」组自动隐藏。
- `grp:admin` 本身不带 `module`/`adminOnly`：其下 `adminOnly` 子项对非 admin 隐藏；非 admin 且无任一集成权限的用户，整个「系统设置」组子树为空 → 自动隐藏。非 admin 但拥有某集成权限的用户，只看到「系统设置 → 系统集成 → 对应组」。符合「保留现有模块权限」。

## 测试（**必须新增**，P2）

当前无 `AppLayout` 单元测试；既有 `e2e/specs/m1-core/auth.spec.ts` 未展开 `grp:admin`，"隐藏" 可能只是菜单未展开的假阳性。因此**必须新增测试**，且**必须先真正展开 `grp:admin`、`grp:integration` 再断言**。

**单元测试**（新建 `frontend/src/components/layout/AppLayout.test.tsx`，跑 `vitest`）：mock 不同 `permissions`，渲染菜单并断言可见性——
- 只有 `mes` 权限 → 仅显示 MES 组，PLM/ERP 隐藏。
- 只有 `plm`/`erp` 权限 → 仅显示对应组。
- 三者皆无权限 → 「系统集成」隐藏；非 admin 时整个「系统设置」组为空并隐藏。
- admin → 各 admin 项 + 其拥有权限的集成项正确显示。
- 访问 `/mes/*` 时 `grp:admin`、`grp:integration`、`grp:mes` 三个祖先 openKeys 都展开。

**E2E**：在 `e2e/specs/m1-core/auth.spec.ts` 增补场景，用 `[data-e2e="menu-grp:admin"]`、`[data-e2e="menu-grp:integration"]` 逐级展开后断言集成菜单的可见/隐藏。

## 验证

```bash
cd frontend
npm run build                                   # tsc -b && vite build
npm run lint
npm test -- --run                               # vitest 单元测试
npm run test:e2e -- e2e/specs/m1-core/auth.spec.ts
```

## 明确不做（YAGNI）

- 不改任何 URL / 路由 / 重定向。
- 不改后端、不改权限矩阵定义（仅前端菜单过滤）。
- 不移动/重命名 `pages/mes`、`pages/plm`、`pages/erp` 文件。
- 不改 dashboard drill-down 链接。
