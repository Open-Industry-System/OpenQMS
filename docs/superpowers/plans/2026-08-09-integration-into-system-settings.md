# 集成菜单移入系统设置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把侧边栏 MES/PLM/ERP 三个顶层集成组收进「系统设置」下的「系统集成」子组，并修复菜单权限过滤算法，使无权限用户看不到集成菜单。

**Architecture:** 纯前端改动。先修复 `filterMenuByPermission`（让所有带 `children` 的组进入递归过滤、子树为空时隐藏父组），再把三个集成组搬迁为 `grp:admin → grp:integration` 的三级子组，更新 `MENU_KEY_TO_OPEN_KEYS` 三级祖先，最后改 i18n。URL / 路由 / 后端 / 页面文件全部不变。

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5 Menu + react-i18next + vitest + @testing-library/react。

## Global Constraints

- URL 不变：`/mes/*`、`/plm/*`、`/erp/*` 保留；不改 `App.tsx` 路由、`MENU_KEYS`、dashboard drill-down。
- 权限保留现有模块判断：`module: "mes"|"plm"|"erp"` 的 `canView`，不套 `adminOnly`。
- 命名：父组标签统一为「系统设置 / System Settings」；新增 `menu.integration` = 「系统集成 / System Integration」。
- 验证：`cd frontend && npm run build`（`tsc -b && vite build`）、`npm run lint`、`npm test -- --run`、`npm run test:e2e -- e2e/specs/m1-core/auth.spec.ts`。
- 复用现有 i18n 键 `mesIntegration`/`plmIntegration`/`erpIntegration` 及各页面键，不为集成页新增其它键。

---

### Task 1: 修复 `filterMenuByPermission` 递归过滤

**Files:**
- Modify: `frontend/src/components/layout/AppLayout.tsx:294-315`（`filterMenuByPermission` 函数体）
- Test: `frontend/src/components/layout/filterMenuByPermission.test.ts`（新建）

**Interfaces:**
- Consumes: `MenuItem`（`AppLayout.tsx:119-127`）、`ModuleKey`（`hooks/usePermission.ts`）。
- Produces: 修正后的 `filterMenuByPermission(items, canViewFn, isAdmin): MenuItem[]`。所有带 `children` 的组都递归过滤；子树为空返回该组为 `null`。后续 Task 2 的菜单结构依赖此行为。为可单测，把该函数（及 `MenuItem` 接口）从 `AppLayout.tsx` 导出。

当前实现（`AppLayout.tsx:294-315`）：

```ts
function filterMenuByPermission(
  items: MenuItem[],
  canViewFn: (m: ModuleKey) => boolean,
  isAdmin: boolean,
): MenuItem[] {
  return items
    .map((item) => {
      if (item.adminOnly && !isAdmin) return null;
      if (!item.module && !item.adminOnly) return item;   // ← 问题所在：组直接放行，子树不过滤
      if (item.module && !canViewFn(item.module)) return null;
      if (item.children) {
        const filteredChildren = filterMenuByPermission(item.children, canViewFn, isAdmin);
        if (filteredChildren.length === 0) return null;
        return { ...item, children: filteredChildren };
      }
      return item;
    })
    .filter((item): item is MenuItem => item !== null);
}
```

- [ ] **Step 1: 写失败测试**

新建 `frontend/src/components/layout/filterMenuByPermission.test.ts`：

```ts
import { describe, it, expect } from "vitest";
import { filterMenuByPermission, type MenuItem } from "./AppLayout";
import type { ModuleKey } from "../../hooks/usePermission";

const canViewNone = (_m: ModuleKey) => false;
const canViewOnly = (...mods: ModuleKey[]) => (m: ModuleKey) => mods.includes(m);

describe("filterMenuByPermission", () => {
  it("无 module/adminOnly 的组会递归过滤其子项", () => {
    const items: MenuItem[] = [
      {
        key: "grp:admin",
        label: "系统设置",
        children: [
          { key: "/admin/users", label: "用户管理", adminOnly: true },
          {
            key: "grp:integration",
            label: "系统集成",
            children: [
              { key: "grp:mes", label: "MES", module: "mes", children: [
                { key: "/mes/dashboard", label: "MES 看板", module: "mes" },
              ]},
            ],
          },
        ],
      },
    ];
    // 非 admin、无任何模块权限 → 子树全空，整组隐藏
    expect(filterMenuByPermission(items, canViewNone, false)).toEqual([]);
  });

  it("只保留有权限的集成子组，隐藏无权限的", () => {
    const items: MenuItem[] = [
      {
        key: "grp:integration",
        label: "系统集成",
        children: [
          { key: "grp:mes", label: "MES", module: "mes", children: [
            { key: "/mes/dashboard", label: "MES 看板", module: "mes" },
          ]},
          { key: "grp:plm", label: "PLM", module: "plm", children: [
            { key: "/plm/dashboard", label: "PLM 看板", module: "plm" },
          ]},
        ],
      },
    ];
    const out = filterMenuByPermission(items, canViewOnly("mes"), false);
    expect(out).toHaveLength(1);
    expect(out[0].children?.map((c) => c.key)).toEqual(["grp:mes"]);
  });

  it("adminOnly 子项对非 admin 隐藏，对 admin 显示", () => {
    const items: MenuItem[] = [
      { key: "grp:admin", label: "系统设置", children: [
        { key: "/admin/users", label: "用户管理", adminOnly: true },
      ]},
    ];
    expect(filterMenuByPermission(items, canViewNone, false)).toEqual([]); // 非 admin：唯一子项被滤，父组空 → 隐藏
    const out = filterMenuByPermission(items, canViewNone, true);           // admin：保留
    expect(out[0].children?.map((c) => c.key)).toEqual(["/admin/users"]);
  });

  it("无 children 的叶子项不受递归影响", () => {
    const items: MenuItem[] = [{ key: "/dashboard", label: "看板" }];
    expect(filterMenuByPermission(items, canViewNone, false)).toHaveLength(1);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/components/layout/filterMenuByPermission.test.ts`
Expected: FAIL —— `filterMenuByPermission` 未导出（`AppLayout.tsx` 仅 `export default`），且现有算法在无 module/adminOnly 组上直接放行。

- [ ] **Step 3: 导出符号并修复算法**

在 `AppLayout.tsx`：把 `interface MenuItem` 改为 `export interface MenuItem`，把 `function filterMenuByPermission` 改为 `export function filterMenuByPermission`，并把函数体改为（删除提前返回，统一走递归）：

```ts
export function filterMenuByPermission(
  items: MenuItem[],
  canViewFn: (m: ModuleKey) => boolean,
  isAdmin: boolean,
): MenuItem[] {
  return items
    .map((item) => {
      // Admin-only items are hidden from non-admins; the backend enforces
      // require_admin regardless, but we hide the link so it doesn't 403.
      if (item.adminOnly && !isAdmin) return null;
      if (item.module && !canViewFn(item.module)) return null;
      if (item.children) {
        const filteredChildren = filterMenuByPermission(item.children, canViewFn, isAdmin);
        if (filteredChildren.length === 0) return null;
        return { ...item, children: filteredChildren };
      }
      return item;
    })
    .filter((item): item is MenuItem => item !== null);
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/components/layout/filterMenuByPermission.test.ts`
Expected: PASS（4 个用例全绿）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/AppLayout.tsx frontend/src/components/layout/filterMenuByPermission.test.ts
git commit -m "fix(menu): filterMenuByPermission 递归过滤子树，子树为空隐藏父组"
```

---

### Task 2: 菜单结构搬迁 + openKeys 三级祖先

**Files:**
- Modify: `frontend/src/components/layout/AppLayout.tsx`（`useMenuItems` 删除三个顶层组、`grp:admin` 下新增 `grp:integration`；`MENU_KEY_TO_OPEN_KEYS` 改 14 条；渲染处给 `grp:integration` 加图标）

**Interfaces:**
- Consumes: Task 1 修正后的 `filterMenuByPermission`（保证 `grp:integration`/`grp:mes/plm/erp` 正确过滤）。
- Produces: 新菜单树；`MENU_KEY_TO_OPEN_KEYS` 中集成路由 openKeys 前缀为 `["grp:admin", "grp:integration", ...]`。Task 3 的 e2e 依赖这些 `grp:` key。

- [ ] **Step 1: 在 `grp:admin` 下新增 `grp:integration` 并搬入三个集成组**

在 `useMenuItems` 中：
1. **删除**顶层数组里的 `grp:mes`、`grp:plm`、`grp:erp` 三个组对象（`AppLayout.tsx:225-262`）。
2. 在 `grp:admin`（`AppLayout.tsx:276-288`）的 `children` 末尾追加 `grp:integration` 子组，其 `children` 为刚删除的三个组对象（内容原样，仅缩进层级变化）：

```ts
      {
        key: "grp:admin",
        icon: <SettingOutlined />,
        label: t("menu.admin"),
        children: [
          { key: "/admin/ai-config", icon: <SettingOutlined />, label: t("menu.aiConfig"), adminOnly: true },
          { key: "/admin/product-types", icon: <AppstoreOutlined />, label: t("menu.productTypes"), adminOnly: true },
          { key: "/admin/product-lines", icon: <ProfileOutlined />, label: t("menu.productLines"), adminOnly: true },
          { key: "/admin/users", icon: <UserOutlined />, label: t("menu.users"), adminOnly: true },
          { key: "/admin/logs", icon: <FileTextOutlined />, label: t("menu.logs"), adminOnly: true },
          { key: "/admin/review-skills", icon: <AuditOutlined />, label: t("menu.reviewSkills"), adminOnly: true },
          {
            key: "grp:integration",
            icon: <ShareAltOutlined />,
            label: t("menu.integration"),
            children: [
              {
                key: "grp:mes",
                icon: <ToolOutlined />,
                label: t("menu.mesIntegration"),
                module: "mes",
                children: [
                  { key: "/mes/dashboard", label: t("menu.mesDashboard"), module: "mes" },
                  { key: "/mes/orders", label: t("menu.workOrders"), module: "mes" },
                  { key: "/mes/scrap", label: t("menu.scrapRework"), module: "mes" },
                  { key: "/mes/connections", label: t("menu.mesConnections"), module: "mes" },
                ],
              },
              {
                key: "grp:plm",
                icon: <BuildOutlined />,
                label: t("menu.plmIntegration"),
                module: "plm",
                children: [
                  { key: "/plm/dashboard", label: t("menu.plmDashboard"), module: "plm" },
                  { key: "/plm/parts", label: t("menu.partList"), module: "plm" },
                  { key: "/plm/change-orders", label: t("menu.changeOrderManagement"), module: "plm" },
                  { key: "/plm/connections", label: t("menu.plmConnections"), module: "plm" },
                ],
              },
              {
                key: "grp:erp",
                icon: <SettingOutlined />,
                label: t("menu.erpIntegration"),
                module: "erp",
                children: [
                  { key: "/erp", label: t("menu.erpDashboard"), module: "erp" },
                  { key: "/erp/connections", label: t("menu.erpConnections"), module: "erp" },
                  { key: "/erp/master-data", label: t("menu.masterData"), module: "erp" },
                  { key: "/erp/supply-chain", label: t("menu.supplyChain"), module: "erp" },
                  { key: "/erp/commercial", label: t("menu.salesCost"), module: "erp" },
                  { key: "/erp/traceability", label: t("menu.batchTraceability"), module: "erp" },
                ],
              },
            ],
          },
        ],
      },
```

- [ ] **Step 2: 更新 `MENU_KEY_TO_OPEN_KEYS` 的 14 条集成路由**

把 `AppLayout.tsx:92-105` 的集成段改为（前缀补 `grp:admin`、`grp:integration`）：

```ts
  "/mes/dashboard": ["grp:admin", "grp:integration", "grp:mes"],
  "/mes/orders": ["grp:admin", "grp:integration", "grp:mes"],
  "/mes/scrap": ["grp:admin", "grp:integration", "grp:mes"],
  "/mes/connections": ["grp:admin", "grp:integration", "grp:mes"],
  "/plm/dashboard": ["grp:admin", "grp:integration", "grp:plm"],
  "/plm/connections": ["grp:admin", "grp:integration", "grp:plm"],
  "/plm/parts": ["grp:admin", "grp:integration", "grp:plm"],
  "/plm/change-orders": ["grp:admin", "grp:integration", "grp:plm"],
  "/erp": ["grp:admin", "grp:integration", "grp:erp"],
  "/erp/connections": ["grp:admin", "grp:integration", "grp:erp"],
  "/erp/master-data": ["grp:admin", "grp:integration", "grp:erp"],
  "/erp/supply-chain": ["grp:admin", "grp:integration", "grp:erp"],
  "/erp/commercial": ["grp:admin", "grp:integration", "grp:erp"],
  "/erp/traceability": ["grp:admin", "grp:integration", "grp:erp"],
```

`MENU_KEYS`（`AppLayout.tsx:46-62`）不动。`grp:mes`/`grp:plm`/`grp:erp` 三个组的 icon/import 已在文件中（`ToolOutlined`/`BuildOutlined`/`SettingOutlined`），无需新增 import。

- [ ] **Step 3: 类型检查 + lint**

Run: `cd frontend && npx tsc -b && npm run lint`
Expected: 无新增 type/lint 错误。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(menu): MES/PLM/ERP 集成移入系统设置-系统集成子组"
```

---

### Task 3: i18n 标签（integration + admin 改名）

**Files:**
- Modify: `frontend/src/locales/zh-CN/layout.json`（`menu` 节点）
- Modify: `frontend/src/locales/en-US/layout.json`（`menu` 节点）
- Test: `frontend/src/components/layout/filterMenuByPermission.test.ts`（无需改）；由 Task 4 的 e2e 兜底

**Interfaces:**
- Consumes: Task 2 引用的 `t("menu.integration")`、`t("menu.admin")`。
- Produces: `menu.integration`、`menu.admin` 两个键的中英文案。

- [ ] **Step 1: zh-CN**

在 `frontend/src/locales/zh-CN/layout.json` 的 `menu` 对象中：
- 把 `"admin": "系统管理"` 改为 `"admin": "系统设置"`；
- 在 `admin` 键附近新增 `"integration": "系统集成",`。

- [ ] **Step 2: en-US**

在 `frontend/src/locales/en-US/layout.json` 的 `menu` 对象中：
- 把 `"admin": "System Admin"` 改为 `"admin": "System Settings"`；
- 新增 `"integration": "System Integration",`。

- [ ] **Step 3: 校验 JSON 合法 + 键被解析**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/layout.json','utf8')); JSON.parse(require('fs').readFileSync('src/locales/en-US/layout.json','utf8')); console.log('ok')"`
Expected: 输出 `ok`。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/zh-CN/layout.json frontend/src/locales/en-US/layout.json
git commit -m "feat(i18n): 新增系统集成菜单键，系统管理更名系统设置"
```

---

### Task 4: e2e 权限场景（逐级展开再断言）

**Files:**
- Modify: `frontend/e2e/specs/m1-core/auth.spec.ts`（追加一个 `test.describe` 块）

**Interfaces:**
- Consumes: Task 2 的菜单 key（`grp:admin`、`grp:integration`、`grp:mes/plm/erp`）与 `stripModuleField` 生成的 `data-e2e="menu-<key>"`（key 中 `/`→`-`，`grp:xxx` 保留冒号）。
- Produces: 覆盖 spec 权限场景的 e2e 断言。依赖 e2e seed 角色权限（见下）。

**前置确认（执行时先核对，必要时改用真实存在的角色）**：本块假设 seed 里 `viewer` 无任何集成模块权限、`admin` 有全部权限。`engineer` 的 mes/plm/erp 权限需查 `backend/app/seed.py` 的权限矩阵；若 engineer 也无集成权限，则「只显示 MES」场景改用 admin 登录断言全部可见 + viewer 断言全部隐藏，并在断言前先逐级展开。e2e 为手动运行（不在 CI），需 `.env.e2e`。

- [ ] **Step 1: 追加 e2e 场景**

在 `frontend/e2e/specs/m1-core/auth.spec.ts` 文件末尾追加：

```ts
test.describe("系统集成菜单（系统设置下）权限可见性", () => {
  test("viewer 无集成权限：展开系统设置后系统集成组隐藏", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/viewer.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    // viewer 无任何 mes/plm/erp 权限且无 admin 权限 → 整个系统设置组隐藏
    await expect(page.locator('[data-e2e="menu-grp:admin"]')).toBeHidden();
    await ctx.close();
  });

  test("admin：展开系统设置→系统集成后三个集成组均可见", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/admin.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    // 逐级展开，再断言，避免“未展开”造成的假阳性
    await page.locator('[data-e2e="menu-grp:admin"]').click();
    await page.locator('[data-e2e="menu-grp:integration"]').click();
    await expect(page.locator('[data-e2e="menu-grp:mes"]')).toBeVisible();
    await expect(page.locator('[data-e2e="menu-grp:plm"]')).toBeVisible();
    await expect(page.locator('[data-e2e="menu-grp:erp"]')).toBeVisible();
    // 展开 MES 组，子页面可见
    await page.locator('[data-e2e="menu-grp:mes"]').click();
    await expect(page.locator('[data-e2e="menu-mes-dashboard"]')).toBeVisible();
    await ctx.close();
  });
});
```

- [ ] **Step 2: 运行 e2e（手动，需 `.env.e2e` 与已启动栈）**

Run: `make e2e TEST_ARGS="--grep 系统集成"` 或 `cd frontend && npm run test:e2e -- e2e/specs/m1-core/auth.spec.ts`
Expected: 新增 2 个用例通过；既有 auth 用例不回归。
若环境未就绪：明确记录“e2e 未在本地跑，需在 e2e 环境执行”，不得声称已通过。

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/specs/m1-core/auth.spec.ts
git commit -m "test(e2e): 系统集成菜单在系统设置下的权限可见性"
```

---

### Task 5: 全量验证 + 文档同步

**Files:**
- Modify: `docs/DECISIONS.md` 或 `PROGRESS.md`（按 CLAUDE.md 文档同步规则；若无需更新则在 PR 上加 `docs-not-needed` 说明）

**Interfaces:**
- Consumes: Task 1–4 全部产物。
- Produces: 绿 `make check` / 前端构建；文档与代码一致。

- [ ] **Step 1: 全量前端验证**

Run:
```bash
cd frontend
npm run build
npm run lint
npm test -- --run
```
Expected: 构建成功、无 lint 错误、vitest 全绿。

- [ ] **Step 2: 文档同步检查（CLAUDE.md 第 5 条）**

本次改动触及 `frontend/src/`。检查 `docs/permissions.md`、`CLAUDE.md`、相关模块 README 是否描述了侧边栏菜单分组（如「MES/PLM/ERP 顶层菜单」）。若有，更新为「系统设置 → 系统集成」；若无，则在 PR 加 `docs-not-needed` 并写一句理由。

- [ ] **Step 3: 最终 Commit（如有文档改动）**

```bash
git add docs/
git commit -m "docs: 同步侧边栏集成菜单归位说明"
```
