/**
 * US-E2E-01.5 — 8D→SCAR 触发与状态回写故事级 spec。
 *
 * 依赖 seed_e2e：
 *  - 8D-E2E-SCAR-001（D3_INTERIM + current D3 impact report lot LOT-E2E-SCAR-001）
 *  - D3-SUP-E2E-001（D3 E2E 供应商）
 *
 * 无 LLM 凭证也必须全绿。IDs 按 document_no 运行时解析。
 *
 * 角色：
 *  - engineer（field_qe）：CAPA EDIT → UI 触发 SCAR
 *  - manager：SCAR APPROVE → start/respond/verify/close 推进
 *  - admin：审计日志断言
 */
import { test, expect } from "@playwright/test";
import { accountPassword } from "../../fixtures/seed-state";
import { loginForToken, authedApi } from "../../helpers/api-client";

const PRODUCT_LINE = "DC-DC-100-E2E";
const CAPA_DOC = "8D-E2E-SCAR-001";
const LOT = "LOT-E2E-SCAR-001";
const SUPPLIER_NO = "D3-SUP-E2E-001";

async function setProductLine(page: import("@playwright/test").Page, code: string) {
  await page.addInitScript((c) => {
    localStorage.setItem("openqms_product_line", c);
  }, code);
}

async function resolveSeedIds(): Promise<{ capaId: string; supplierId: string }> {
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
  const capa = capas.find((c) => c.document_no === CAPA_DOC);
  if (!capa) throw new Error(`Seed CAPA ${CAPA_DOC} not found — run seed_e2e`);

  const supRes = await ac.get("/suppliers", {
    params: { page: 1, page_size: 50, search: SUPPLIER_NO },
  });
  const suppliers = (supRes.data.items || supRes.data) as Array<{
    supplier_id: string;
    supplier_no: string;
  }>;
  const supplier = suppliers.find((s) => s.supplier_no === SUPPLIER_NO);
  if (!supplier) throw new Error(`Seed supplier ${SUPPLIER_NO} not found — run seed_e2e`);

  return { capaId: capa.report_id, supplierId: supplier.supplier_id };
}

async function closeScarViaApi(scarId: string) {
  // manager has scar APPROVE; engineer is VIEW-only on scar module.
  const mgrPw = await accountPassword("manager");
  const token = await loginForToken("manager", mgrPw);
  const ac = await authedApi(token);

  await ac.post(`/scars/${scarId}/transition`, { action: "start" });
  await ac.post(`/scars/${scarId}/transition`, {
    action: "respond",
    supplier_response: "E2E supplier response for SCAR trigger story",
  });
  await ac.post(`/scars/${scarId}/transition`, { action: "verify" });
  await ac.post(`/scars/${scarId}/transition`, {
    action: "close",
    resolution_summary: "E2E SCAR closed after verification",
  });
}

test.describe("US-E2E-01.5 8D→SCAR 触发", () => {
  // Audit asserts depend on the trigger+close story above.
  test.describe.configure({ mode: "serial" });

  test("8D→SCAR trigger + status sync", async ({ browser }) => {
    const { capaId, supplierId } = await resolveSeedIds();

    const ctx = await browser.newContext({
      storageState: "e2e/.storage-state/engineer.json",
    });
    const page = await ctx.newPage();
    await setProductLine(page, PRODUCT_LINE);

    await page.goto(`/capa/${capaId}`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="capa-trigger-scar"]')).toBeVisible({
      timeout: 15000,
    });

    await page.locator('[data-e2e="capa-trigger-scar"]').click();
    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Select D3 E2E supplier (search so it is not limited to first page of options)
    const supplierSelect = dialog.locator(".ant-select").first();
    await supplierSelect.locator(".ant-select-selector").click();
    await supplierSelect.locator("input").fill(SUPPLIER_NO);
    await page
      .locator(".ant-select-dropdown:visible .ant-select-item-option")
      .filter({ hasText: SUPPLIER_NO })
      .first()
      .click();

    await dialog.getByRole("button", { name: /发起 SCAR|Trigger SCAR|OK|确 定|确定/ }).click();

    const linked = page.locator('[data-e2e="capa-linked-scar"]');
    await expect(linked).toBeVisible({ timeout: 15000 });
    await expect(linked).toContainText(/SCAR-/);

    // Resolve scar via CAPA GET projection
    const engPw = await accountPassword("engineer");
    const engToken = await loginForToken("engineer", engPw);
    const engAc = await authedApi(engToken);
    const capaDetail = await engAc.get(`/capa/${capaId}`);
    const linkedScar = capaDetail.data.linked_scar as {
      scar_id: string;
      scar_no: string;
      status: string;
      supplier_id: string;
    } | null;
    expect(linkedScar, "linked_scar missing after trigger").toBeTruthy();
    expect(linkedScar!.supplier_id).toBe(supplierId);
    expect(linkedScar!.status).toBe("open");

    // SCAR description must include D3 lot (from affected_batches / D3 report)
    const mgrPw = await accountPassword("manager");
    const mgrToken = await loginForToken("manager", mgrPw);
    const mgrAc = await authedApi(mgrToken);
    const scarRes = await mgrAc.get(`/scars/${linkedScar!.scar_id}`);
    expect(scarRes.data.description || "").toContain(LOT);
    expect(scarRes.data.source_type).toBe("capa");
    expect(scarRes.data.capa_ref_id).toBe(capaId);

    await closeScarViaApi(linkedScar!.scar_id);

    // CAPA projection reflects closed status (no CAPA row mutation, read-time join)
    const capaAfter = await engAc.get(`/capa/${capaId}`);
    expect(capaAfter.data.linked_scar?.status).toBe("closed");
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="capa-linked-scar"]')).toContainText(/closed|CLOSED|已关闭/i);

    await ctx.close();
  });

  test("审计: SCAR_TRIGGERED + SCAR_STATUS_SYNCED", async () => {
    const { capaId } = await resolveSeedIds();
    const adminPw = await accountPassword("admin");
    const token = await loginForToken("admin", adminPw);
    const ac = await authedApi(token);

    const triggered = await ac.get("/admin/logs/audit", {
      params: {
        table_name: "capa_eightd",
        action: "SCAR_TRIGGERED",
        page: 1,
        page_size: 200,
      },
    });
    const triggeredItems = (triggered.data.items as any[]).filter(
      (l) => l.record_id === capaId,
    );
    expect(
      triggeredItems.length,
      `expected SCAR_TRIGGERED for ${capaId}`,
    ).toBeGreaterThan(0);

    const synced = await ac.get("/admin/logs/audit", {
      params: {
        table_name: "capa_eightd",
        action: "SCAR_STATUS_SYNCED",
        page: 1,
        page_size: 200,
      },
    });
    const syncedItems = (synced.data.items as any[]).filter(
      (l) => l.record_id === capaId,
    );
    // At least one status sync after close path (open→…→closed)
    expect(
      syncedItems.length,
      `expected SCAR_STATUS_SYNCED for ${capaId}`,
    ).toBeGreaterThan(0);
    const statuses = new Set(
      syncedItems
        .map((l) => l.changed_fields?.new_status as string | undefined)
        .filter((s): s is string => !!s),
    );
    expect(statuses.has("closed"), `missing closed sync; got ${[...statuses]}`).toBe(
      true,
    );
  });
});
