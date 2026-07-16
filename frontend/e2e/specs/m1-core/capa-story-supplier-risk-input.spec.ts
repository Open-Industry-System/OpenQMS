/**
 * US-E2E-01.6 — 8D→供应商风险输入故事级 spec。
 *
 * 依赖 seed_e2e：
 *  - 8D-E2E-RISK-001（D7_PREVENTION + supplier_id + FMEA + D7 confirmed action）
 *  - 8D-E2E-RISK-HIST-001（ARCHIVED，同 supplier + PL + fmea_node → matched repeat）
 *  - D3-SUP-E2E-001 + R11 supplier risk configs
 *
 * 无 LLM 凭证也必须全绿。IDs 按 document_no 运行时解析。
 *
 * 角色：
 *  - engineer（field_qe）：CAPA EDIT → advance D7_PREVENTION→D7_COMPLETED
 *  - manager：CAPA EDIT + supplier_risk EDIT → confirm-repeat
 *  - admin：审计日志断言
 *
 * 注意：engineer 的 supplier_risk=VIEW only，不能 confirm-repeat。
 */
import { test, expect } from "@playwright/test";
import { accountPassword } from "../../fixtures/seed-state";
import { loginForToken, authedApi } from "../../helpers/api-client";

const PRODUCT_LINE = "DC-DC-100-E2E";
const CAPA_DOC = "8D-E2E-RISK-001";
const HIST_CAPA_DOC = "8D-E2E-RISK-HIST-001";
const SUPPLIER_NO = "D3-SUP-E2E-001";

type SupplierRiskProjection = {
  status: string;
  repeat_suggested: boolean | null;
  repeat_detection_status: string;
  matched_capa_nos: string[];
  evaluated_risk_level: string | null;
  evaluated_risk_score: number | null;
  repeat_confirmed: boolean | null;
};

async function resolveCapaId(): Promise<string> {
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
  return capa.report_id;
}

async function waitForProcessed(
  ac: Awaited<ReturnType<typeof authedApi>>,
  capaId: string,
  timeoutMs = 90_000,
): Promise<SupplierRiskProjection> {
  const deadline = Date.now() + timeoutMs;
  let last: SupplierRiskProjection | null = null;
  while (Date.now() < deadline) {
    const r = await ac.get(`/capa/${capaId}`);
    const proj = r.data.supplier_risk_input as SupplierRiskProjection | null;
    last = proj;
    if (proj?.status === "processed") return proj;
    if (proj?.status === "error") {
      throw new Error(
        `supplier_risk_input entered error state before processed: ${JSON.stringify(proj)}`,
      );
    }
    await new Promise((res) => setTimeout(res, 3000));
  }
  throw new Error(
    `supplier_risk_input not processed within ${timeoutMs}ms; last=${JSON.stringify(last)}`,
  );
}

test.describe("US-E2E-01.6 8D→供应商风险输入", () => {
  test.describe.configure({ mode: "serial" });

  test("advance D7 → worker processes risk input → confirm-repeat", async () => {
    const capaId = await resolveCapaId();

    // engineer advances D7_PREVENTION → D7_COMPLETED (capa EDIT; not APPROVE edge)
    const engPw = await accountPassword("engineer");
    const engToken = await loginForToken("engineer", engPw);
    const engAc = await authedApi(engToken);

    const before = await engAc.get(`/capa/${capaId}`);
    expect(before.data.status).toBe("D7_PREVENTION");
    expect(before.data.supplier_id, "seed must set capa.supplier_id").toBeTruthy();

    const adv = await engAc.post(`/capa/${capaId}/advance`, {
      target_state: "D7_COMPLETED",
    });
    expect(adv.status).toBeLessThan(300);
    expect(adv.data.capa?.status || adv.data.status).toBe("D7_COMPLETED");

    // Poll GET until worker marks input processed (loop every 30s; allow ~90s)
    const projection = await waitForProcessed(engAc, capaId, 90_000);
    expect(projection.status).toBe("processed");
    expect(projection.repeat_suggested).toBe(true);
    expect(projection.repeat_detection_status).toBe("matched");
    expect(projection.matched_capa_nos.length).toBeGreaterThan(0);
    expect(projection.matched_capa_nos).toContain(HIST_CAPA_DOC);
    expect(projection.evaluated_risk_level).not.toBeNull();

    // admin audit: SUPPLIER_RISK_INPUT_SENT
    const adminPw = await accountPassword("admin");
    const adminToken = await loginForToken("admin", adminPw);
    const adminAc = await authedApi(adminToken);
    const sentLogs = await adminAc.get("/admin/logs/audit", {
      params: {
        table_name: "capa_eightd",
        action: "SUPPLIER_RISK_INPUT_SENT",
        page: 1,
        page_size: 200,
      },
    });
    const sentItems = (sentLogs.data.items as any[]).filter(
      (l) => l.record_id === capaId,
    );
    expect(
      sentItems.length,
      `expected SUPPLIER_RISK_INPUT_SENT for ${capaId}`,
    ).toBeGreaterThan(0);
    const sent = sentItems[0];
    expect(sent.changed_fields?.disposition).toBeDefined();
    expect(sent.changed_fields?.risk_level).toBe(projection.evaluated_risk_level);

    // manager confirm-repeat (needs CAPA EDIT + SUPPLIER_RISK EDIT; engineer is VIEW-only on risk)
    const mgrPw = await accountPassword("manager");
    const mgrToken = await loginForToken("manager", mgrPw);
    const mgrAc = await authedApi(mgrToken);
    const confirm = await mgrAc.post(`/capa/${capaId}/confirm-repeat`, {
      repeat_confirmed: true,
    });
    expect(confirm.status).toBeLessThan(300);
    const after = confirm.data.supplier_risk_input as SupplierRiskProjection;
    expect(after.repeat_confirmed).toBe(true);

    // SUPPLIER_RISK_CHANGED audit — fields present; do NOT assert old_level != new_level
    const changedLogs = await adminAc.get("/admin/logs/audit", {
      params: {
        table_name: "capa_eightd",
        action: "SUPPLIER_RISK_CHANGED",
        page: 1,
        page_size: 200,
      },
    });
    const changedItems = (changedLogs.data.items as any[]).filter(
      (l) => l.record_id === capaId,
    );
    expect(
      changedItems.length,
      `expected SUPPLIER_RISK_CHANGED for ${capaId}`,
    ).toBeGreaterThan(0);
    const changed = changedItems[0];
    expect(changed.changed_fields).toHaveProperty("old_level");
    expect(changed.changed_fields).toHaveProperty("new_level");
    expect(changed.changed_fields.repeat_confirmed).toBe(true);

    // silence unused import risk if tree-shaken — keep supplier no for seed docs
    expect(SUPPLIER_NO).toBeTruthy();
  });
});
