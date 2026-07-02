import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import path from "path";
import { cleanupByPrefix } from "../../helpers/api-client";
import { capaFormInputs } from "../../fixtures/input/capa-form-inputs";

function hasLLMCreds(): boolean {
  const envPath = path.resolve(process.cwd(), "e2e/.storage-state/e2e-env.json");
  try {
    const env = JSON.parse(readFileSync(envPath, "utf-8"));
    return env.hasLLM === true;
  } catch {
    return false;
  }
}

test.describe("CAPA 8D lifecycle", () => {
  test.afterAll(async () => { await cleanupByPrefix("E2E-M1-CAPA"); });

  test("create 8D, advance D-states, AI draft visible for engineer", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await page.addInitScript(() => {
      localStorage.setItem("openqms_product_line", "DC-DC-100-E2E");
    });
    await page.goto("/capa");
    await page.waitForLoadState("networkidle");
    await page.locator('[data-e2e="capa-create"]').click();
    // Create form fields (CAPAListPage modal): document_no (报告编号, required), title, severity.
    await page.getByLabel(/报告编号|document no|report no/i).fill(capaFormInputs.document_no);
    await page.getByLabel(/标题|title/i).fill(capaFormInputs.title);
    await page.locator('[role="dialog"]').getByRole("button", { name: /创建|确定|Create|OK/i }).click();
    await page.waitForURL(/\/capa\//, { timeout: 10000 });
    // Creating a CAPA opens the Lessons Learned modal; dismiss it to reach the detail page.
    await page.getByRole("button", { name: /跳过，直接编辑|Skip, edit directly/i }).click();
    // Detail page: advance button present (D-state transition)
    await expect(page.locator('[data-e2e="capa-advance"]')).toBeVisible();
    await page.locator('[data-e2e="capa-advance"]').click();
    // AI draft button visible for engineer only when LLM is configured.
    if (hasLLMCreds()) {
      await expect(page.locator('[data-e2e="capa-ai-draft"]')).toBeVisible({ timeout: 10000 });
    }
    await ctx.close();
  });
});
