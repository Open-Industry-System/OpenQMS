/**
 * US-E2E-01.4 — 8D ↔ FMEA 双向追溯故事级 spec。
 *
 * 依赖 seed_e2e：
 *  - PFMEA-E2E-FMEA-LINK-001（fm-1 / cause-link / pc-link）
 *  - 8D-E2E-FMEA-LINK-001（header + D4 source_ref + D7 confirmed）
 *  - 8D-E2E-FMEA-LINK-002（D7 skipped 对照，反查不出现）
 *
 * 无 LLM 凭证也必须全绿。IDs 按 document_no 运行时解析，不依赖 process.env。
 */
import { test, expect } from "@playwright/test";
import { accountPassword } from "../../fixtures/seed-state";
import { loginForToken, authedApi } from "../../helpers/api-client";

const PRODUCT_LINE = "DC-DC-100-E2E";
const FMEA_DOC_NO = "PFMEA-E2E-FMEA-LINK-001";
const CAPA_DOC_NO = "8D-E2E-FMEA-LINK-001";
const CAPA_SKIPPED_DOC_NO = "8D-E2E-FMEA-LINK-002";
const CAUSE_NODE = "cause-link";

async function setProductLine(page: import("@playwright/test").Page, code: string) {
  await page.addInitScript((c) => {
    localStorage.setItem("openqms_product_line", c);
  }, code);
}

async function resolveSeedIds(): Promise<{ capaId: string; fmeaId: string }> {
  const engPw = await accountPassword("engineer");
  const token = await loginForToken("engineer", engPw);
  const ac = await authedApi(token);

  const capaRes = await ac.get("/capa", {
    params: { page: 1, page_size: 100, product_line: PRODUCT_LINE },
  });
  const capas = (capaRes.data.items || capaRes.data) as Array<{
    report_id: string;
    document_no: string;
  }>;
  const capa = capas.find((c) => c.document_no === CAPA_DOC_NO);
  if (!capa) throw new Error(`Seed CAPA ${CAPA_DOC_NO} not found — run seed_e2e`);

  const fmeaRes = await ac.get("/fmea", {
    params: { page: 1, page_size: 100, product_line: PRODUCT_LINE },
  });
  const fmeas = (fmeaRes.data.items || fmeaRes.data) as Array<{
    fmea_id: string;
    document_no: string;
  }>;
  const fmea = fmeas.find((f) => f.document_no === FMEA_DOC_NO);
  if (!fmea) throw new Error(`Seed FMEA ${FMEA_DOC_NO} not found — run seed_e2e`);

  return { capaId: capa.report_id, fmeaId: fmea.fmea_id };
}

test.describe("US-E2E-01.4 FMEA 双向追溯", () => {
  test("8D→FMEA: Cause 节点深链高亮", async ({ browser }) => {
    const { capaId } = await resolveSeedIds();
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await setProductLine(page, PRODUCT_LINE);

    await page.goto(`/capa/${capaId}`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="capa-status"]')).toHaveText("D4_ROOT_CAUSE");
    await expect(page.locator('[data-e2e="d4-verification-card"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-e2e="d4-cause-link"]')).toBeVisible({ timeout: 10000 });

    await page.locator('[data-e2e="d4-cause-link"]').click();
    await expect(page).toHaveURL(new RegExp(`tab=graph.*highlightNode=${CAUSE_NODE}|highlightNode=${CAUSE_NODE}.*tab=graph`));
    // Graph tab active + highlight applied (G6 canvas has no per-node DOM testid)
    await expect(page.locator('[data-e2e="fmea-highlight-active"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-e2e="fmea-highlight-active"]')).toHaveAttribute(
      "data-highlight-node",
      CAUSE_NODE,
    );

    await ctx.close();
  });

  test("FMEA→8D: related-capa 含该 8D + sources", async ({ browser }) => {
    const { fmeaId } = await resolveSeedIds();
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await setProductLine(page, PRODUCT_LINE);

    await page.goto(`/fmea/${fmeaId}?tab=related-capa`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="related-capa-list"]')).toBeVisible({ timeout: 10000 });
    const item = page.locator('[data-e2e="related-capa-item"]').filter({ hasText: CAPA_DOC_NO });
    await expect(item).toBeVisible({ timeout: 10000 });
    await expect(item.locator('[data-e2e="related-capa-source-header"]')).toBeVisible();
    await expect(item.locator('[data-e2e="related-capa-source-d4_cause"]')).toBeVisible();
    await expect(item.locator('[data-e2e="related-capa-source-d7_prevention"]')).toBeVisible();

    await ctx.close();
  });

  test("FMEA→8D: skipped 对照不出现", async ({ browser }) => {
    const { fmeaId } = await resolveSeedIds();
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await setProductLine(page, PRODUCT_LINE);

    await page.goto(`/fmea/${fmeaId}?tab=related-capa`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="related-capa-list"]')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(CAPA_SKIPPED_DOC_NO)).toHaveCount(0);
    // Positive control: linked CAPA still present
    await expect(page.locator('[data-e2e="related-capa-item"]').filter({ hasText: CAPA_DOC_NO })).toBeVisible();

    await ctx.close();
  });

  test("审计: header / d4_cause / d7_prevention 的 FMEA_LINKAGE_CREATED", async () => {
    const { capaId } = await resolveSeedIds();
    const adminPw = await accountPassword("admin");
    const token = await loginForToken("admin", adminPw);
    const ac = await authedApi(token);

    const r = await ac.get("/admin/logs/audit", {
      params: {
        table_name: "capa_eightd",
        action: "FMEA_LINKAGE_CREATED",
        page: 1,
        page_size: 200,
      },
    });
    const items = (r.data.items as any[]).filter((l) => l.record_id === capaId);
    const sources = new Set(
      items
        .map((l) => l.changed_fields?.source as string | undefined)
        .filter((s): s is string => !!s),
    );
    expect(sources.has("header"), `missing header; got ${[...sources]}`).toBe(true);
    expect(sources.has("d4_cause"), `missing d4_cause; got ${[...sources]}`).toBe(true);
    expect(sources.has("d7_prevention"), `missing d7_prevention; got ${[...sources]}`).toBe(true);
  });
});
