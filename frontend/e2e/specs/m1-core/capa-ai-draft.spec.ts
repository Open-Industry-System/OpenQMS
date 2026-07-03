import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import path from "path";
import { loginAs } from "../../fixtures/auth";
import { cleanupByPrefix } from "../../helpers/api-client";

function hasLLMCreds(): boolean {
  const envPath = path.resolve(process.cwd(), "e2e/.storage-state/e2e-env.json");
  try {
    const env = JSON.parse(readFileSync(envPath, "utf-8"));
    return env.hasLLM === true;
  } catch {
    return false;
  }
}

test.describe("CAPA AI Draft", () => {
  // Distinct prefix from Task 12 (E2E-M1-CAPA-*) so the two specs never collide on the
  // unique document_no, and each cleans up its own records.
  test.afterAll(async () => { await cleanupByPrefix("E2E-AI-CAPA"); });

  test("capabilities endpoint returns 401 not 422", async ({ page }) => {
    await page.goto("/login");
    const res = await page.evaluate(async () => {
      const r = await fetch("/api/capa/capabilities");
      return { status: r.status };
    });
    expect(res.status).toBe(401);
  });

  test("AI draft button visible for engineer", async ({ page }) => {
    test.skip(!hasLLMCreds(), "LLM creds not configured — AI draft button hidden w/o LLM");
    await page.evaluate(() => {
      localStorage.setItem("openqms_product_line", "DC-DC-100-E2E");
    });
    await page.goto("/capa");
    await page.getByRole("button", { name: /Create 8D|新建 8D/ }).click();
    await page.getByLabel(/报告编号|document no|report no/i).fill("E2E-AI-CAPA-001");
    await page.getByLabel(/标题|title/i).fill("E2E AI draft visibility");
    await page.locator('[role="dialog"]').getByRole("button", { name: /^确定|OK$/i }).click();
    await page.waitForURL(/\/capa\//);
    await expect(page.getByText(/AI草拟|AI draft/i).first()).toBeVisible({ timeout: 10000 });
  });
});
