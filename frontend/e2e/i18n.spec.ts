import { test, expect } from "@playwright/test";

test.describe("i18n language switcher", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
  });

  test("login page can switch between Chinese and English", async ({ page }) => {
    // Switch to Chinese first (browser default might be English)
    await page.click('.ant-segmented-item:has-text("中文")');
    await page.waitForTimeout(500);

    // Chinese labels (Ant Design button text may contain extra spaces)
    await expect(page.locator('button[type="submit"]')).toContainText(/登\s*录/);
    await expect(page.locator('input[placeholder="请输入用户名"]')).toBeVisible();
    await expect(page.locator('input[placeholder="请输入密码"]')).toBeVisible();
    await expect(page.locator('text=智能质量管理平台')).toBeVisible();

    // Switch to English
    await page.click('.ant-segmented-item:has-text("English")');
    await page.waitForTimeout(500);

    await expect(page.locator('button[type="submit"]')).toContainText("Login");
    await expect(page.locator('input[placeholder="Please enter username"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Please enter password"]')).toBeVisible();
    await expect(page.locator('text=Intelligent Quality Management Platform')).toBeVisible();

    // Language preference persisted in localStorage
    const locale = await page.evaluate(() => localStorage.getItem("openqms_locale"));
    expect(locale).toBe("en-US");

    // Switch back to Chinese
    await page.click('.ant-segmented-item:has-text("中文")');
    await page.waitForTimeout(500);
    await expect(page.locator('button[type="submit"]')).toContainText(/登\s*录/);
  });

  test("login page loads English when localStorage already en-US", async ({ page }) => {
    await page.evaluate(() => {
      localStorage.setItem("openqms_locale", "en-US");
    });
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.locator('button[type="submit"]')).toContainText("Login");
  });
});
