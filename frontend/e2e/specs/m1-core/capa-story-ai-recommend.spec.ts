import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import path from "path";
import { accountPassword } from "../../fixtures/seed-state";
import { cleanupByPrefix, loginForToken } from "../../helpers/api-client";

/**
 * US-E2E-01 — AI D4 推荐路径故事级 spec。
 *
 * 从 capa-story-closed-loop.spec.ts 拆分出来：原混合 spec 用 test.skip() 在测试内
 * 终止整条故事，评审列为 P0-4 设计缺陷。本文件只覆盖 AI 推荐分支，无 LLM 凭证时
 * 整条 test 跳过；非 AI 闭环保留在 capa-story-closed-loop.spec.ts 并始终运行。
 *
 * 前置：8D 已推进到 D4（与闭环 spec 相同的 UI 推进方式，避免新增 API 直接构造）。
 * 验证点：后端 A5 已落地 422 + detail.blocked；本 spec 断言阶段 11（LLM 融合）
 * 在两种凭证状态下的表现。
 */

const AI_DOC_NO = "E2E-AI-REC-CAPA-001";
const PRODUCT_LINE = "DC-DC-100-E2E";

function hasLLMCreds(): boolean {
  const envPath = path.resolve(process.cwd(), "e2e/.storage-state/e2e-env.json");
  try {
    const env = JSON.parse(readFileSync(envPath, "utf-8"));
    return env.hasLLM === true;
  } catch {
    return false;
  }
}

async function setProductLine(page: import("@playwright/test").Page, code: string) {
  await page.addInitScript((c) => {
    localStorage.setItem("openqms_product_line", c);
  }, code);
}

/** 等待某 D 步表单标签出现（renderLabelWithDraft 把 i18n 标签渲染为可见文本）。 */
async function waitForStep(page: import("@playwright/test").Page, label: RegExp) {
  await expect(page.getByText(label)).toBeVisible({ timeout: 10000 });
}

test.describe("US-E2E-01 CAPA AI D4 recommendation", () => {
  test.afterAll(async () => {
    await cleanupByPrefix("E2E-AI-REC-CAPA");
  });

  test("AI D4 recommendation DAG (200 done | 422 BLOCKED)", async ({ browser, request }) => {
    test.setTimeout(120000);
    const llm = hasLLMCreds();

    // ── Engineer: create 8D and advance to D4 ─────────────────────────────
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await setProductLine(page, PRODUCT_LINE);
    await page.goto("/capa");
    await page.waitForLoadState("networkidle");

    await page.locator('[data-e2e="capa-create"]').click();
    await page.getByLabel(/报告编号|document no|report no/i).fill(AI_DOC_NO);
    await page.getByLabel(/标题|title/i).fill("AI D4 recommendation test");
    // 严重度「致命」：Ant Select 虚拟滚动，首项被滚出视口，用键盘从默认项上移两次。
    await page.locator('[role="dialog"] .ant-select-selector').first().click();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Enter");
    await page.locator('[role="dialog"]').getByRole("button", { name: /创建|确定|Create|OK/i }).click();
    await page.waitForURL(/\/capa\//, { timeout: 10000 });
    const capaId = page.url().split("/capa/")[1];
    expect(capaId).toBeTruthy();

    await page.getByRole("button", { name: /跳过，直接编辑|Skip, edit directly/i }).click();

    // D1 团队组建
    await page.getByPlaceholder(/成员姓名|Member name/i).first().fill("张工");
    await page.getByRole("button", { name: /添加成员|Add Member/i }).click();
    await page.locator('[data-e2e="capa-advance"]').click();
    await waitForStep(page, /^5W2H 问题描述$|^5W2H Problem Description$/);

    // D2 问题描述
    const d2 = page.locator("textarea").first();
    await d2.fill("现场抽检一批 DC-DC-100-E2E 来料螺栓，发现 M8 螺栓孔径超差，实测 8.12mm（上限 8.05mm）。");
    await d2.evaluate((el: any) => el.blur());
    await page.locator('[data-e2e="capa-advance"]').click();
    await waitForStep(page, /^临时遏制措施$|^Interim Containment$/);

    // D3 临时措施
    const d3 = page.locator("textarea").first();
    await d3.fill("对该批螺栓 100% 复检隔离，超差件判退供应商。");
    await d3.evaluate((el: any) => el.blur());
    await page.locator('[data-e2e="capa-advance"]').click();
    await expect(page.locator('[data-e2e="d4-verification-card"]')).toBeVisible({ timeout: 10000 });

    await ctx.close();

    // ── Call D4 recommendation endpoint directly ────────────────────────────
    const password = await accountPassword("engineer");
    const token = await loginForToken("engineer", password);
    const r = await request.get(`/api/capa/${capaId}/d4-fmea-recommendations`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (llm) {
      expect(r.status()).toBe(200);
      const body = await r.json();
      const s11 = body.stages.find((s: any) => s.index === 11);
      expect(s11).toBeTruthy();
      expect(s11.status).toBe("done");
    } else {
      expect(r.status()).toBe(422);
      const body = await r.json();
      expect(body.detail.blocked).toBe(true);
      test.skip(true, "BLOCKED: no LLM creds");
    }
  });
});
