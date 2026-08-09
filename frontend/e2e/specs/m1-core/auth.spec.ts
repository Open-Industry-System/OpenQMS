import { test, expect } from "@playwright/test";
import { getSeedState } from "../../fixtures/seed-state";

test.describe("auth + RBAC + factory isolation", () => {
  test("viewer sees FMEA/CAPA menus (VIEW) but cannot create FMEA or admin users", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/viewer.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    // Expand the relevant groups so the child menu items are rendered.
    await page.locator('[data-e2e="menu-grp:planning"]').click();
    await page.locator('[data-e2e="menu-grp:customer"]').click();
    // viewer has fmea=1 / capa=1 (VIEW) and can see the menu entries.
    await expect(page.locator('[data-e2e="menu-fmea"]')).toBeVisible();
    await expect(page.locator('[data-e2e="menu-capa"]')).toBeVisible();
    // viewer has user_mgmt=0 (NONE) and cannot see admin users menu.
    await expect(page.locator('[data-e2e="menu-admin-users"]')).toBeHidden();
    // On /fmea viewer sees the list but not the create button (create needs EDIT=3).
    await page.goto("/fmea");
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="fmea-create"]')).toBeHidden();
    await ctx.close();
  });

  test("engineer sees FMEA + CAPA menus and create button, but not admin user mgmt", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    // Expand the relevant groups so the child menu items are rendered.
    await page.locator('[data-e2e="menu-grp:planning"]').click();
    await page.locator('[data-e2e="menu-grp:customer"]').click();
    // engineer (field_qe) has fmea=3 / capa=3 (EDIT) and can see the menu entries.
    await expect(page.locator('[data-e2e="menu-fmea"]')).toBeVisible();
    await expect(page.locator('[data-e2e="menu-capa"]')).toBeVisible();
    // engineer has user_mgmt=0 (NONE) and cannot see admin users menu.
    await expect(page.locator('[data-e2e="menu-admin-users"]')).toBeHidden();
    // On /fmea engineer sees the create button.
    await page.goto("/fmea");
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="fmea-create"]')).toBeVisible();
    await ctx.close();
  });

  test("factory isolation: engineer sees only DC-FACT-E2E data", async ({ browser }) => {
    const s = await getSeedState();
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await page.goto("/fmea");
    await page.waitForLoadState("networkidle");

    // Engineer is scoped to a single factory; the factory switcher is not rendered.
    await expect(page.locator('[data-e2e="factory-switcher"]')).toBeHidden();

    // The SH factory name must not appear anywhere on the page.
    const sh = s.factories.find((f) => f.code === "SH-FACT-E2E");
    await expect(page.locator(`text=${sh!.name}`)).toHaveCount(0);
    await ctx.close();
  });

  test("groupadmin sees both factories", async ({ browser }) => {
    const s = await getSeedState();
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/groupadmin.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    const dc = s.factories.find((f) => f.code === "DC-FACT-E2E");
    const sh = s.factories.find((f) => f.code === "SH-FACT-E2E");

    // The factory switcher lists both factories for a cross-factory group admin.
    const switcher = page.locator('[data-e2e="factory-switcher"]');
    await expect(switcher).toBeVisible();
    await switcher.click();
    // Ant renders the dropdown in a portal. The visible items use internal classes,
    // but the portal also exposes role="option" elements keyed by the factory id.
    await expect(page.getByRole("option", { name: dc!.id })).toHaveCount(1);
    await expect(page.getByRole("option", { name: sh!.id })).toHaveCount(1);
    await ctx.close();
  });
});

test.describe("系统集成菜单（系统设置下）权限可见性", () => {
  // seed.py 中 viewer 角色 mes/plm/erp 均为 VIEW=1，故 viewer 应看到系统设置→系统集成
  // 下的三个集成组，但看不到 adminOnly 的管理项（用户管理等）。
  test("viewer 有集成 VIEW 权限：看到系统集成组，但看不到 adminOnly 管理项", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/viewer.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    // 逐级展开，再断言，避免“未展开”造成的假阳性
    await page.locator('[data-e2e="menu-grp:admin"]').click();
    await page.locator('[data-e2e="menu-grp:integration"]').click();
    await expect(page.locator('[data-e2e="menu-grp:mes"]')).toBeVisible();
    await expect(page.locator('[data-e2e="menu-grp:plm"]')).toBeVisible();
    await expect(page.locator('[data-e2e="menu-grp:erp"]')).toBeVisible();
    // adminOnly 项对非 admin 隐藏
    await expect(page.locator('[data-e2e="menu-admin-users"]')).toBeHidden();
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
