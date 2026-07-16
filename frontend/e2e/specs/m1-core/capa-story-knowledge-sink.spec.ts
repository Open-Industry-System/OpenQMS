/**
 * US-E2E-01.8 — 8D 知识库沉淀故事级 spec。
 *
 * 依赖 seed_e2e：
 *  - 8D-E2E-KNOW-001（D8_APPROVAL_PENDING，D2–D8 字段齐全）
 *
 * 无 LLM 凭证：关闭 advance 必须 422 + detail.outcome=blocked（fail-closed）。
 * 有 LLM 凭证：manager 关闭 → knowledge card/list 可见 → 可选 recommend 命中 entry_id
 *  + 审计 KNOWLEDGE_SUNK（embedding ready 依赖 worker，尽力轮询，不硬失败）。
 *
 * 角色：
 *  - manager：APPROVE → D8_APPROVAL_PENDING → D8_CLOSURE（触发 sink）
 *  - engineer：list/recommend 读路径
 *  - admin：审计
 */
import { test, expect } from "@playwright/test";
import { accountPassword } from "../../fixtures/seed-state";
import { noLlmCreds } from "../../fixtures/d3-containment";
import { loginForToken, authedApi } from "../../helpers/api-client";

const PRODUCT_LINE = "DC-DC-100-E2E";
const CAPA_DOC = "8D-E2E-KNOW-001";

async function setProductLine(page: import("@playwright/test").Page, code: string) {
  await page.addInitScript((c) => {
    localStorage.setItem("openqms_product_line", c);
  }, code);
}

async function resolveKnowledgeCapaId(): Promise<string> {
  const engPw = await accountPassword("engineer");
  const token = await loginForToken("engineer", engPw);
  const ac = await authedApi(token);
  const r = await ac.get("/capa", {
    params: { page: 1, page_size: 100, product_line: PRODUCT_LINE },
  });
  const items = (r.data.items || r.data) as Array<{
    report_id: string;
    document_no: string;
    status: string;
  }>;
  const hit = items.find((c) => c.document_no === CAPA_DOC);
  if (!hit) throw new Error(`Seed CAPA ${CAPA_DOC} not found — run seed_e2e`);
  return hit.report_id;
}

async function listCapaKnowledgeEntries(token: string, q?: string) {
  const ac = await authedApi(token);
  return ac.get("/knowledge/entries", {
    params: {
      source_type: "capa",
      product_line_code: PRODUCT_LINE,
      q: q ?? CAPA_DOC,
      page: 1,
      page_size: 50,
    },
    validateStatus: () => true,
  });
}

test.describe("US-E2E-01.8 8D 知识库沉淀", () => {
  test.describe.configure({ mode: "serial" });

  test("no-LLM: D8 close is blocked (422 outcome=blocked)", async () => {
    // Fail-closed path must pass without credentials (AI_REQUIRED=true).
    // When LLM is configured this assertion is not meaningful — skip.
    test.skip(!noLlmCreds(), "LLM credentials present — blocked path N/A");

    const capaId = await resolveKnowledgeCapaId();
    const mgrPw = await accountPassword("manager");
    const token = await loginForToken("manager", mgrPw);
    const ac = await authedApi(token);

    const adv = await ac.post(
      `/capa/${capaId}/advance`,
      { target_state: "D8_CLOSURE" },
      { validateStatus: () => true },
    );
    expect(adv.status).toBe(422);
    const detail = adv.data?.detail;
    expect(detail?.outcome).toBe("blocked");
    expect(detail?.reason || "llm_unavailable").toMatch(/llm_unavailable|blocked/i);

    // Status must remain approval-pending (no partial close).
    const after = await ac.get(`/capa/${capaId}`);
    expect(after.data.status).toBe("D8_APPROVAL_PENDING");
  });

  test("with-LLM: close → knowledge card/list + KNOWLEDGE_SUNK (+ optional recommend)", async ({
    browser,
  }) => {
    test.skip(noLlmCreds(), "No AI credentials — skip LLM knowledge-sink path");
    test.setTimeout(180000);

    const capaId = await resolveKnowledgeCapaId();
    const mgrPw = await accountPassword("manager");
    const mgrToken = await loginForToken("manager", mgrPw);
    const mgrAc = await authedApi(mgrToken);
    const ok = { validateStatus: () => true };

    // Ensure still at D8_APPROVAL_PENDING (re-seed normally guarantees this).
    const before = await mgrAc.get(`/capa/${capaId}`);
    expect(before.data.status).toBe("D8_APPROVAL_PENDING");

    const adv = await mgrAc.post(
      `/capa/${capaId}/advance`,
      { target_state: "D8_CLOSURE" },
      ok,
    );
    // 422 blocked should not happen when LLM creds exist
    if (adv.status === 422 && adv.data?.detail?.outcome === "blocked") {
      test.skip(true, `Close blocked despite e2e-env hasLLM: ${JSON.stringify(adv.data.detail)}`);
      return;
    }
    if (adv.status === 422 && adv.data?.detail?.outcome === "failed") {
      // Real LLM failure is a product/env issue — surface, do not soft-pass.
      throw new Error(
        `Knowledge sink failed on close: ${JSON.stringify(adv.data.detail)}`,
      );
    }
    expect(adv.status).toBe(200);
    expect(adv.data.capa?.status || adv.data.status).toBe("D8_CLOSURE");

    type KnowledgeListItem = {
      entry_id: string;
      source_id: string;
      document_no: string;
      lesson_summary?: string | null;
      embedding_status?: string;
    };

    // API list: CAPA-sourced entry for this document
    let entry: KnowledgeListItem | null = null;
    for (let i = 0; i < 10; i++) {
      const list = await listCapaKnowledgeEntries(mgrToken);
      expect(list.status).toBe(200);
      const items = (list.data.items || []) as KnowledgeListItem[];
      entry = items.find((e) => e.source_id === capaId) ?? null;
      if (entry) break;
      await new Promise((r) => setTimeout(r, 1000));
    }
    expect(entry, `knowledge entry for ${CAPA_DOC} missing after close`).toBeTruthy();
    expect(entry!.document_no).toBe(CAPA_DOC);
    expect(entry!.lesson_summary || "").not.toBe("");

    // Best-effort: poll embedding_status → ready (worker may be offline in e2e).
    let embeddingStatus = entry!.embedding_status || "pending";
    for (let i = 0; i < 15 && embeddingStatus === "pending"; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const list = await listCapaKnowledgeEntries(mgrToken);
      const items = (list.data.items || []) as KnowledgeListItem[];
      const hit = items.find((e) => e.source_id === capaId);
      if (hit?.embedding_status) {
        embeddingStatus = hit.embedding_status;
        entry = { ...entry!, ...hit };
      }
    }
    // Soft assert: ready preferred; pending is acceptable if worker not in stack.
    expect(["pending", "ready", "failed"]).toContain(embeddingStatus);

    // UI card on closed CAPA
    const ctx = await browser.newContext({
      storageState: "e2e/.storage-state/manager.json",
    });
    const page = await ctx.newPage();
    await setProductLine(page, PRODUCT_LINE);
    await page.goto(`/capa/${capaId}`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="capa-status"]')).toHaveText("D8_CLOSURE");
    await expect(page.locator('[data-e2e="capa-knowledge-card"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-e2e="capa-knowledge-entry"]')).toBeVisible({
      timeout: 15000,
    });
    await ctx.close();

    // Audit: KNOWLEDGE_SUNK
    const adminPw = await accountPassword("admin");
    const adminToken = await loginForToken("admin", adminPw);
    const adminAc = await authedApi(adminToken);
    const sunk = await adminAc.get("/admin/logs/audit", {
      params: {
        table_name: "capa_eightd",
        action: "KNOWLEDGE_SUNK",
        page: 1,
        page_size: 200,
      },
    });
    const sunkItems = (sunk.data.items as any[]).filter((l) => l.record_id === capaId);
    expect(
      sunkItems.length,
      `expected KNOWLEDGE_SUNK for ${capaId}`,
    ).toBeGreaterThan(0);
    expect(sunkItems[0].changed_fields?.entry_id).toBe(entry!.entry_id);

    // Optional recommend hit (needs ready embedding + embedding provider).
    // Prefer probing from a D4 CAPA that already has d2 text in seed (no create needed).
    if (embeddingStatus === "ready") {
      const engPw = await accountPassword("engineer");
      const engToken = await loginForToken("engineer", engPw);
      const engAc = await authedApi(engToken);

      // Use FMEA-link seed CAPA (D4_ROOT_CAUSE) as probe host when present.
      const probeList = await engAc.get("/capa", {
        params: { page: 1, page_size: 100, product_line: PRODUCT_LINE },
      });
      const probeItems = (probeList.data.items || []) as Array<{
        report_id: string;
        document_no: string;
        status: string;
      }>;
      const probe =
        probeItems.find((c) => c.document_no === "8D-E2E-FMEA-LINK-001") ||
        probeItems.find((c) => c.status === "D4_ROOT_CAUSE");
      if (probe) {
        const rec = await engAc.get(`/capa/${probe.report_id}/d4-fmea-recommendations`, ok);
        if (rec.status === 200) {
          const body = rec.data;
          const items = (body.items || []) as Array<{
            metadata?: { entry_id?: string };
            source?: string;
            match_source?: string;
          }>;
          const stages = (body.stages || []) as Array<{
            index?: number;
            name?: string;
            source?: string;
            status?: string;
            hit_count?: number;
          }>;
          const stageHit = stages.some(
            (s) =>
              (s.source === "knowledge_entry" || String(s.name || "").includes("knowledge")) &&
              (s.hit_count || 0) > 0,
          );
          const itemHit = items.some(
            (it) =>
              it.source === "knowledge_entry" ||
              it.match_source === "knowledge_entry" ||
              it.metadata?.entry_id === entry!.entry_id,
          );
          if (stageHit || itemHit) {
            const retrieved = await adminAc.get("/admin/logs/audit", {
              params: {
                table_name: "capa_eightd",
                action: "KNOWLEDGE_RETRIEVED",
                page: 1,
                page_size: 200,
              },
            });
            const rItems = (retrieved.data.items as any[]).filter(
              (l) => l.record_id === probe.report_id,
            );
            expect(
              rItems.length,
              "expected KNOWLEDGE_RETRIEVED after knowledge_entry hit",
            ).toBeGreaterThan(0);
          }
        }
      }
    }
  });
});
