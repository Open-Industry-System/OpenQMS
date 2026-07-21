/**
 * US-E2E-01.9 lateral diffusion story spec.
 *
 * Deterministic assertions. Tests FAIL when the story contract is broken.
 * Only the no-LLM close path is environment-gated (design: blocked, not failed).
 *
 * Seed: 8D-E2E-LATERAL-001/002/BLOCK/EMPTY at D8_APPROVAL_PENDING.
 */
import { test, expect } from "@playwright/test";
import { accountPassword } from "../../fixtures/seed-state";
import { noLlmCreds } from "../../fixtures/d3-containment";
import { loginForToken, authedApi } from "../../helpers/api-client";

const CAPA_001 = "8D-E2E-LATERAL-001";
const CAPA_002 = "8D-E2E-LATERAL-002";
const CAPA_BLOCK = "8D-E2E-LATERAL-BLOCK";
const CAPA_EMPTY = "8D-E2E-LATERAL-EMPTY";

async function findCapa(ac: any, docNo: string) {
  const r = await ac.get("/capa", { params: { page: 1, page_size: 100 } });
  const item = (r.data.items || []).find((c: any) => c.document_no === docNo);
  if (!item) throw new Error(`seed CAPA ${docNo} not found — run seed_e2e`);
  return item;
}

async function closeCapa(ac: any, reportId: string) {
  return ac.post(`/capa/${reportId}/advance`, { target_state: "D8_CLOSURE" });
}

test.describe("capa-story-lateral-diffusion", () => {
  let managerAc: any;
  let adminAc: any;
  const llmMissing = noLlmCreds();

  test.beforeAll(async () => {
    const managerPw = await accountPassword("manager");
    const managerToken = await loginForToken("manager", managerPw);
    managerAc = await authedApi(managerToken);
    const adminPw = await accountPassword("admin");
    const adminToken = await loginForToken("admin", adminPw);
    adminAc = await authedApi(adminToken);
  });

  test("001 close yields all four hit criteria union", async () => {
    const capa = await findCapa(managerAc, CAPA_001);

    let detail: any;
    if (capa.status === "D8_APPROVAL_PENDING") {
      if (llmMissing) {
        // Design: no-LLM close must be 422 blocked (not failed, not 200)
        const err = await closeCapa(managerAc, capa.report_id).catch((e: any) => e);
        expect(err.response?.status, "no-LLM close must be 422").toBe(422);
        const body = err.response?.data?.detail;
        expect(body?.outcome, "no-LLM must be blocked, not failed").toBe("blocked");
        return;
      }
      const adv = await closeCapa(managerAc, capa.report_id);
      expect(adv.status).toBe(200);
      detail = adv.data.capa || adv.data;
    } else {
      const r = await managerAc.get(`/capa/${capa.report_id}`);
      detail = r.data;
    }

    const lat = detail.lateral_diffusion;
    expect(lat, "lateral_diffusion projection must exist").toBeTruthy();
    expect(lat.status).toBe("done");

    const union = new Set<string>();
    for (const sp of lat.similar_products || []) {
      for (const c of sp.hit_criteria || []) union.add(c);
    }
    for (const need of [
      "same_product_type",
      "shared_fmea_mode",
      "shared_control_plan",
      "same_supplier_material",
    ]) {
      expect(union.has(need), `missing criterion ${need}`).toBeTruthy();
    }
  });

  test("001 decide notify writes notifications + SENT audit", async () => {
    const capa = await findCapa(managerAc, CAPA_001);
    const r = await managerAc.get(`/capa/${capa.report_id}`);
    const lat = r.data.lateral_diffusion;

    if (llmMissing && capa.status === "D8_APPROVAL_PENDING") {
      // Cannot close without LLM; notify path unreachable
      return;
    }
    if (!lat || lat.status !== "done") {
      throw new Error("001 must have a done lateral check");
    }
    if (lat.decision === "skipped") {
      throw new Error("001 was previously skipped — notify test invalid");
    }
    if (lat.decision === "notified") {
      // Already decided in prior run: verify audit exists
      const logs = await adminAc.get("/admin/logs/audit", {
        params: { table_name: "capa_eightd", action: "LATERAL_NOTIFICATION_SENT", page: 1, page_size: 200 },
      });
      const items = (logs.data.items || []).filter((l: any) => l.record_id === capa.report_id);
      expect(items.length, "SENT audit must exist for decided 001").toBeGreaterThan(0);
      return;
    }

    const d = await managerAc.post(`/capa/${capa.report_id}/lateral-diffusion/decide`, {
      decision: "notify",
    });
    expect(d.status).toBe(200);
    expect(d.data.decision).toBe("notified");
    expect((d.data.notifications || []).length).toBeGreaterThan(0);

    // SENT audit
    const logs = await adminAc.get("/admin/logs/audit", {
      params: { table_name: "capa_eightd", action: "LATERAL_NOTIFICATION_SENT", page: 1, page_size: 200 },
    });
    const items = (logs.data.items || []).filter((l: any) => l.record_id === capa.report_id);
    expect(items.length, "LATERAL_NOTIFICATION_SENT audit required").toBeGreaterThan(0);
  });

  test("002 decide skip writes SKIPPED with skip_reason + audit", async () => {
    const capa = await findCapa(managerAc, CAPA_002);

    if (capa.status === "D8_APPROVAL_PENDING") {
      if (llmMissing) {
        const err = await closeCapa(managerAc, capa.report_id).catch((e: any) => e);
        expect(err.response?.status).toBe(422);
        expect(err.response?.data?.detail?.outcome).toBe("blocked");
        return;
      }
      const adv = await closeCapa(managerAc, capa.report_id);
      expect(adv.status).toBe(200);
    }

    const r = await managerAc.get(`/capa/${capa.report_id}`);
    const lat = r.data.lateral_diffusion;
    if (!lat || lat.status !== "done") {
      throw new Error("002 must have a done lateral check");
    }
    if (lat.decision === "notified") {
      throw new Error("002 was previously notified — skip test invalid");
    }
    if (lat.decision === "skipped") {
      // Verify audit from prior run
      const logs = await adminAc.get("/admin/logs/audit", {
        params: { table_name: "capa_eightd", action: "LATERAL_NOTIFICATION_SKIPPED", page: 1, page_size: 200 },
      });
      const items = (logs.data.items || []).filter((l: any) => l.record_id === capa.report_id);
      expect(items.length, "SKIPPED audit must exist for decided 002").toBeGreaterThan(0);
      expect(items[0].changed_fields?.skip_reason).toBeTruthy();
      return;
    }

    const d = await managerAc.post(`/capa/${capa.report_id}/lateral-diffusion/decide`, {
      decision: "skip",
      skip_reason: "E2E 不通知",
    });
    expect(d.status).toBe(200);
    expect(d.data.decision).toBe("skipped");

    // SKIPPED audit with skip_reason
    const logs = await adminAc.get("/admin/logs/audit", {
      params: { table_name: "capa_eightd", action: "LATERAL_NOTIFICATION_SKIPPED", page: 1, page_size: 200 },
    });
    const items = (logs.data.items || []).filter((l: any) => l.record_id === capa.report_id);
    expect(items.length, "LATERAL_NOTIFICATION_SKIPPED audit required").toBeGreaterThan(0);
    expect(items[0].changed_fields?.skip_reason).toBe("E2E 不通知");
  });

  test("EMPTY closes and reports empty lateral status", async () => {
    const capa = await findCapa(managerAc, CAPA_EMPTY);

    if (capa.status !== "D8_APPROVAL_PENDING") {
      // Already closed: projection MUST exist and be empty
      const r = await managerAc.get(`/capa/${capa.report_id}`);
      const lat = r.data.lateral_diffusion;
      expect(lat, "EMPTY CAPA must have lateral projection").toBeTruthy();
      expect(lat.status).toBe("empty");
      expect(lat.llm_status).toBe("skipped");
      return;
    }

    if (llmMissing) {
      // 01.8 sink may block without LLM; design says blocked
      const err = await closeCapa(managerAc, capa.report_id).catch((e: any) => e);
      expect(err.response?.status).toBe(422);
      expect(err.response?.data?.detail?.outcome).toBe("blocked");
      return;
    }

    const adv = await closeCapa(managerAc, capa.report_id);
    expect(adv.status).toBe(200);
    const body = adv.data.capa || adv.data;
    expect(body.lateral_diffusion, "EMPTY CAPA must have lateral projection").toBeTruthy();
    expect(body.lateral_diffusion.status).toBe("empty");
    expect(body.lateral_diffusion.llm_status).toBe("skipped");
  });

  test("BLOCK without LLM is 422 blocked; with LLM closes", async () => {
    const capa = await findCapa(managerAc, CAPA_BLOCK);

    if (capa.status !== "D8_APPROVAL_PENDING") {
      // Already closed: only valid if LLM was available
      if (llmMissing) {
        throw new Error("BLOCK CAPA closed without LLM — close-chain gate is broken");
      }
      const r = await managerAc.get(`/capa/${capa.report_id}`);
      expect(r.status).toBe(200);
      return;
    }

    const result = await closeCapa(managerAc, capa.report_id).catch((e: any) => e);
    if (llmMissing) {
      expect(result.response?.status, "no-LLM close must be 422").toBe(422);
      const body = result.response?.data?.detail;
      expect(body?.outcome).toBe("blocked");
      expect(body?.message).toBeTruthy();
    } else {
      expect(result.status).toBe(200);
      const body = result.data.capa || result.data;
      expect(body.status).toBe("D8_CLOSURE");
    }
  });
});
