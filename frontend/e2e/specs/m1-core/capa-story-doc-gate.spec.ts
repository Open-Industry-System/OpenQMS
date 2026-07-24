/**
 * US-E2E-01.7 — D8 文档更新审核门禁故事级 spec。
 *
 * 非 LLM 路径（无凭证也必须绿）：
 *  - seed CAPA `8D-E2E-DOCGATE-001` 位于 D8_GATE_PENDING
 *  - 全局推进按钮隐藏；DocGatePanel 可见
 *  - 无 current analysis 时 advance → 400
 *
 * AI 路径（需 LLM）：生成影响分析 → 审核/空清单确认 → 推进到 D8_APPROVAL_PENDING
 *  无凭证时 skip。
 */
import { test, expect } from "@playwright/test";
import { accountPassword } from "../../fixtures/seed-state";
import { loginForToken, authedApi } from "../../helpers/api-client";
import { noLlmCreds } from "../../fixtures/d3-containment";

const DOCGATE_DOC_NO = "8D-E2E-DOCGATE-001";
const PRODUCT_LINE = "DC-DC-100-E2E";

async function setProductLine(page: import("@playwright/test").Page, code: string) {
  await page.addInitScript((c) => {
    localStorage.setItem("openqms_product_line", c);
  }, code);
}

async function resolveDocGateCapaId(): Promise<string> {
  const engPw = await accountPassword("engineer");
  const token = await loginForToken("engineer", engPw);
  const ac = await authedApi(token);
  const r = await ac.get("/capa", {
    params: { page: 1, page_size: 100, product_line: PRODUCT_LINE },
  });
  const items = (r.data.items || r.data) as Array<{ report_id: string; document_no: string; status: string }>;
  const hit = items.find((c) => c.document_no === DOCGATE_DOC_NO);
  if (!hit) throw new Error(`Seed CAPA ${DOCGATE_DOC_NO} not found — run seed_e2e`);
  return hit.report_id;
}

test.describe("doc-gate D8 document update gate", () => {
  test("blocks advance without analysis (non-LLM)", async ({ browser }) => {
    const capaId = await resolveDocGateCapaId();

    // API: advance without analysis → 400
    const engPw = await accountPassword("engineer");
    const token = await loginForToken("engineer", engPw);
    const ac = await authedApi(token);
    const adv = await ac.post(`/capa/${capaId}/advance`, {
      target_state: "D8_APPROVAL_PENDING",
    }, { validateStatus: () => true });
    expect(adv.status).toBe(400);
    expect(String(adv.data?.detail || "")).toMatch(/影响分析/);

    // UI: panel visible, global advance hidden
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await setProductLine(page, PRODUCT_LINE);
    await page.goto(`/capa/${capaId}`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="capa-status"]')).toHaveText("D8_GATE_PENDING");
    await expect(page.locator('[data-e2e="doc-gate-panel"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-e2e="capa-advance"]')).toBeHidden();
    await expect(page.locator('[data-e2e="doc-gate-generate"]')).toBeVisible();
    await ctx.close();
  });

  test("empty-list confirm path (API, non-LLM via seed analysis optional)", async () => {
    // Without LLM we cannot generate a done/empty analysis via API.
    // Verify confirm-no-affected rejects when no analysis (400/404 path).
    const capaId = await resolveDocGateCapaId();
    const engPw = await accountPassword("engineer");
    const token = await loginForToken("engineer", engPw);
    const ac = await authedApi(token);
    const conf = await ac.post(`/capa/${capaId}/doc-gate/confirm-no-affected`, {}, {
      validateStatus: () => true,
    });
    expect([400, 422]).toContain(conf.status);
  });

  test("AI impact → audit/confirm → advance (LLM required)", async ({ browser }) => {
    test.skip(noLlmCreds(), "No AI credentials — skip LLM doc-gate path");
    test.setTimeout(180000);

    const capaId = await resolveDocGateCapaId();
    const engPw = await accountPassword("engineer");
    const token = await loginForToken("engineer", engPw);
    const ac = await authedApi(token);
    const ok = { validateStatus: () => true };

    // Generate impact analysis
    const impact = await ac.post(`/capa/${capaId}/doc-gate/impact`, {}, ok);
    // 422 blocked should not happen when LLM creds exist
    expect(impact.status).not.toBe(422);
    expect([200, 201]).toContain(impact.status);
    const impactBody = impact.data;
    // May be done / failed / running — wait for terminal if running
    if (impactBody.status === "running") {
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const g = await ac.get(`/capa/${capaId}/doc-gate/impact`, ok);
        if (g.data?.status !== "running") {
          Object.assign(impactBody, g.data);
          break;
        }
      }
    }
    expect(["done", "failed"]).toContain(impactBody.status);

    if (impactBody.status !== "done") {
      // Distinguish expected skips from real regressions (review test-quality #2):
      // - "LLM 未配置" / "BLOCKED" = no LLM creds in this env → expected skip.
      // - Any other failure (LLM returned garbage, validate error, input_changed)
      //   is a real product defect → surface as a test failure, not a silent skip.
      const err = String(impactBody.error || "");
      const noCreds = err.includes("LLM 未配置") || err.includes("BLOCKED");
      if (noCreds) {
        test.skip(true, `Impact analysis skipped (no LLM credentials): ${err}`);
        return;
      }
      throw new Error(
        `Impact analysis failed unexpectedly (not a no-creds skip): ${err || "unknown"}`
      );
    }

    const affected = impactBody.affected_docs || [];
    if (affected.length === 0) {
      const conf = await ac.post(`/capa/${capaId}/doc-gate/confirm-no-affected`, {}, ok);
      expect(conf.status).toBe(200);
      expect(conf.data.decision).toBe("passed");
    } else {
      const audit = await ac.post(`/capa/${capaId}/doc-gate/audit`, {}, ok);
      expect(audit.status).toBe(200);
      expect(["passed", "blocked"]).toContain(audit.data.decision);
      if (audit.data.decision !== "passed") {
        const blocked = await ac.post(`/capa/${capaId}/advance`, {
          target_state: "D8_APPROVAL_PENDING",
        }, ok);
        expect(blocked.status).toBe(400);
        return;
      }
    }

    const adv = await ac.post(`/capa/${capaId}/advance`, {
      target_state: "D8_APPROVAL_PENDING",
    }, ok);
    expect(adv.status).toBe(200);
    expect(adv.data.capa.status).toBe("D8_APPROVAL_PENDING");

    // UI reflects status
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await setProductLine(page, PRODUCT_LINE);
    await page.goto(`/capa/${capaId}`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="capa-status"]')).toHaveText("D8_APPROVAL_PENDING");
    await ctx.close();
  });
});
