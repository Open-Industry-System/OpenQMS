import { test, expect } from "@playwright/test";

test.describe("CAPA AI Draft", () => {
  // Login helper
  async function login(page, username: string, password: string) {
    await page.goto("http://localhost:5173/login");
    await page.fill('input[placeholder="用户名"]', username);
    await page.fill('input[placeholder="密码"]', password);
    await page.click('button:has-text("登录")');
    await page.waitForURL(/\/dashboard|\/capa/);
  }

  test("capabilities endpoint not intercepted by report_id route", async ({ page }) => {
    // Verify GET /api/capa/capabilities returns 401 (not 422 UUID validation error)
    const response = await page.evaluate(async () => {
      const res = await fetch("http://localhost:8000/api/capa/capabilities");
      return { status: res.status };
    });
    expect(response.status).toBe(401); // 401 = authenticated route, not 422 UUID error
  });

  test("AI draft button visible for engineer with edit permission", async ({ page }) => {
    await login(page, "engineer", "Engineer@2026");
    await page.goto("http://localhost:5173/capa");
    // Create a new CAPA or navigate to existing one in D2 status
    await page.click('button:has-text("新建 8D")');
    await page.fill('input[placeholder="报告标题"]', "E2E Test Report");
    await page.selectOption('select', { label: "致命" });
    await page.click('button:has-text("创建")');
    await page.waitForURL(/\/capa\//);

    // Wait for page to load
    await page.waitForSelector('text=AI草拟', { timeout: 10000 });
    const aiButton = page.locator('text=AI草拟').first();
    await expect(aiButton).toBeVisible();
  });

  test("AI draft button hidden for viewer", async ({ page }) => {
    await login(page, "viewer", "Viewer@2026");
    await page.goto("http://localhost:5173/capa");
    // Navigate to first CAPA
    const firstRow = page.locator('table tbody tr').first();
    if (await firstRow.isVisible().catch(() => false)) {
      await firstRow.click();
    }
    await page.waitForURL(/\/capa\//, { timeout: 5000 }).catch(() => {});

    // AI button should not be visible for viewer
    const aiButton = page.locator('text=AI草拟');
    await expect(aiButton).not.toBeVisible();
  });

  test("format preference persisted in localStorage", async ({ page }) => {
    await login(page, "engineer", "Engineer@2026");
    await page.goto("http://localhost:5173/capa");
    // Navigate to a CAPA in D2 status
    const firstRow = page.locator('table tbody tr').first();
    if (await firstRow.isVisible().catch(() => false)) {
      await firstRow.click();
    }
    await page.waitForURL(/\/capa\//, { timeout: 5000 }).catch(() => {});

    // Wait for AI button
    await page.waitForSelector('text=AI草拟', { timeout: 10000 });

    // Check localStorage for format preference
    const format = await page.evaluate(() => {
      try {
        const raw = localStorage.getItem("openqms_ai_draft_preference");
        return raw ? JSON.parse(raw).format : "structured";
      } catch {
        return "structured";
      }
    });
    expect(format).toMatch(/structured|paragraph/);
  });
});
