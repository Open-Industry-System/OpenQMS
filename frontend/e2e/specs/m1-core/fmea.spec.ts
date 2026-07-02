import { test, expect } from "@playwright/test";
import { cleanupByPrefix } from "../../helpers/api-client";
import { pfmeaWizardInputs } from "../../fixtures/input/pfmea-wizard-inputs";

test.describe("FMEA lifecycle", () => {
  test.afterAll(async () => { await cleanupByPrefix("E2E-M1-PFMEA"); });

  test("create PFMEA, see it in list, open editor, recommend button present", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await page.addInitScript(() => {
      localStorage.setItem("openqms_product_line", "DC-DC-100");
    });
    await page.goto("/fmea");
    await page.waitForLoadState("networkidle");
    await page.locator('[data-e2e="fmea-create"]').click();
    // Fill create form — FMEACreate requires document_no + title.
    await page.getByLabel(/文档编号|Document No\.|document no/i).fill(pfmeaWizardInputs.document_no);
    await page.getByLabel(/标题|Title/i).fill(pfmeaWizardInputs.title);
    await page.locator('[role="dialog"]').getByRole("button", { name: /创建|确定|Create|OK/i }).click();
    await page.waitForURL(/\/fmea/);
    // Creating a PFMEA navigates into the wizard; go back to the list to see the row.
    await page.goto("/fmea");
    await page.waitForLoadState("networkidle");
    // List shows the new doc
    await expect(page.locator('[data-e2e="row-E2E-M1-PFMEA-001"]')).toBeVisible({ timeout: 10000 });
    // Open editor via the list action button (incomplete PFMEA drafts redirect to the wizard)
    await page.locator('[data-e2e="row-E2E-M1-PFMEA-001"] [data-e2e="fmea-open"]').click();
    await page.waitForURL(/\/fmea\//);
    // Recommend button present (AI button visibility does not require LLM call)
    await expect(page.locator('[data-e2e="fmea-recommend"]').first()).toBeVisible({ timeout: 10000 });
    await ctx.close();
  });
});
