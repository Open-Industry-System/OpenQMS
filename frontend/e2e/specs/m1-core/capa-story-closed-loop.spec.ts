import { test, expect } from "@playwright/test";
import { accountPassword } from "../../fixtures/seed-state";
import { cleanupByPrefix, completeD3Gate, loginForToken, authedApi } from "../../helpers/api-client";

/**
 * US-E2E-01 — 8D credentialed closed-loop story spec（Spec C / P2-11）。
 *
 * 覆盖故事核心链至 D8 文档门禁交接、8 条 TRANSITION 审计断言、viewer 只读。D3 gate
 * 必须生成 AI report 并记录手工执行后才能进入 D4；D4 AI 推荐断言另拆分至
 * capa-story-ai-recommend.spec.ts。
 *
 * 与 m1-core/capa.spec.ts（D1→D2 冒烟）、capa-ai-draft.spec.ts（按钮可见性）、
 * capa-story-ai-recommend.spec.ts（AI D4 推荐）并行；用独立单号前缀
 * E2E-STORY-CAPA-，afterAll 清理不互斥。
 *
 * 设计取舍：
 * - 审计断言走 GET /api/admin/logs/audit?table_name=capa_eightd（admin token），按 record_id 客户端过滤。
 *   故事的 1 CREATE + 8 TRANSITION（D1→D2…D6→D7_PREVENTION、D7_PREVENTION→D7_COMPLETED 由 engineer、
 *   D7_COMPLETED→D8_GATE_PENDING 由 manager）在此回读。
 *   （PROGRESS 初稿写「/api/audit-logs?target_id」，但该端点不存在；实际 admin/logs/audit 无 record_id 过滤，
 *   客户端过滤等价且无需新增后端端点——Surgical Changes。）
 * - D4 验证子流程断言（method / conclusion / retry_count）在独立 test 中覆盖，使用与主故事相同的
 *   create→D4 初始化 helper，避免重复登录/seed 代码。
 */

const STORY_DOC_NO = "E2E-STORY-CAPA-001";
const D4_SUBFLOW_DOC_NO = "E2E-STORY-CAPA-D4-001";
const D4_BASE_DOC_NO = "E2E-STORY-CAPA-D4-BASE-001";
const PRODUCT_LINE = "DC-DC-100-E2E";

async function setProductLine(page: import("@playwright/test").Page, code: string) {
  await page.addInitScript((c) => {
    localStorage.setItem("openqms_product_line", c);
  }, code);
}

/** 回读某 CAPA 的审计日志（admin token），按 record_id 客户端过滤。
 *  传 start（ISO）限定窗口，避免跨运行累积的 capa 审计日志溢出 200 行分页上限。 */
async function fetchCapaAuditLogs(capaId: string, start?: string) {
  const adminPw = await accountPassword("admin");
  const token = await loginForToken("admin", adminPw);
  const ac = await authedApi(token);
  const r = await ac.get("/admin/logs/audit", {
    params: { table_name: "capa_eightd", page: 1, page_size: 200, ...(start ? { start } : {}) },
  });
  return (r.data.items as any[]).filter((l) => l.record_id === capaId);
}

/** 等待某 D 步表单标签出现（renderLabelWithDraft 把 i18n 标签渲染为可见文本）。 */
async function waitForStep(page: import("@playwright/test").Page, label: RegExp) {
  await expect(page.getByText(label)).toBeVisible({ timeout: 10000 });
}

/** 创建 8D 并推进到 D4（engineer）。返回 page/context/capId，调用方负责关闭 context。 */
async function createCapaAndAdvanceToD4(
  browser: import("@playwright/test").Browser,
  docNo: string,
) {
  const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
  const page = await ctx.newPage();
  await setProductLine(page, PRODUCT_LINE);
  await page.goto("/capa");
  await page.waitForLoadState("networkidle");

  // Step 1: create 8D
  await page.locator('[data-e2e="capa-create"]').click();
  await page.getByLabel(/报告编号|document no|report no/i).fill(docNo);
  await page.getByLabel(/标题|title/i).fill("来料螺栓尺寸超差");
  // 严重度「致命」。Ant Select 虚拟滚动会滚到已选项（默认「一般」），首项「致命」被滚出视口且不在 DOM，
  // 故用键盘从「一般」上移两次到「致命」再回车（虚拟列表跟随活跃项渲染）。
  await page.locator('[role="dialog"] .ant-select-selector').first().click();
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");
  await page.locator('[role="dialog"]').getByRole("button", { name: /创建|确定|Create|OK/i }).click();
  await page.waitForURL(/\/capa\//, { timeout: 10000 });
  const capId = page.url().split("/capa/")[1];
  expect(capId).toBeTruthy();

  // 创建后弹出经验教训弹窗，跳过进入编辑。
  await expect(page.getByRole("button", { name: /跳过，直接编辑|Skip, edit directly/i })).toBeVisible({ timeout: 8000 });
  await page.getByRole("button", { name: /跳过，直接编辑|Skip, edit directly/i }).click();

  // Step 2: D1 团队组建
  await page.getByPlaceholder(/成员姓名|Member name/i).first().fill("张工");
  await page.getByRole("button", { name: /添加成员|Add Member/i }).click();
  await page.locator('[data-e2e="capa-advance"]').click();
  await waitForStep(page, /^5W2H 问题描述$|^5W2H Problem Description$/);

  // Step 3: D2 问题描述
  const d2 = page.locator("textarea").first();
  await d2.fill("现场抽检一批 DC-DC-100-E2E 来料螺栓，发现 M8 螺栓孔径超差，实测 8.12mm（上限 8.05mm）。");
  await d2.evaluate((el: any) => el.blur());
  await page.locator('[data-e2e="capa-advance"]').click();
  await waitForStep(page, /^临时遏制措施$|^Interim Containment$/);

  // Step 4: D3 临时措施
  const d3 = page.locator("textarea").first();
  await d3.fill("对该批螺栓 100% 复检隔离，超差件判退供应商。");
  await d3.evaluate((el: any) => el.blur());
  await completeD3Gate(capId);
  await page.locator('[data-e2e="capa-advance"]').click();
  // Step 5: D4 — 用验证卡 testid 作哨兵。
  await expect(page.locator('[data-e2e="d4-verification-card"]')).toBeVisible({ timeout: 10000 });

  return { page, context: ctx, capId };
}

test.describe("US-E2E-01 CAPA 8D closed-loop story", () => {
  test.afterAll(async () => {
    await cleanupByPrefix("E2E-STORY-CAPA");
  });

  test("core chain: create → D1..D7 → D8 gate handoff + viewer read-only + audit trail", async ({ browser }) => {
    test.setTimeout(240000); // 全故事驱动 8 次推进 + D7 处置 + 三角色，远超默认 30s。
    // 审计窗口起点（留 5s 抵消时钟漂移）。
    const auditStart = new Date(Date.now() - 5000).toISOString();

    // ── Engineer: create + D1..D7 ──────────────────────────────────────────
    const { page, context: engCtx, capId } = await createCapaAndAdvanceToD4(browser, STORY_DOC_NO);

    // D4 根因由工程师手动填写（AI 推荐断言已拆分至 capa-story-ai-recommend.spec.ts）。
    const aggregateRootCause = "现场根因：螺栓孔径定位销磨损导致孔径偏大";
    const d4Textarea = page.locator("textarea").first();
    await d4Textarea.fill(aggregateRootCause);
    await d4Textarea.evaluate((el: any) => el.blur());

    // D4 现场验证：method 选 measurement，填写 result，提交 passed，满足 D4→D5 闸口。
    await page.locator('[data-e2e="d4-verification-new"]').click();
    await page.locator('[data-e2e="verification-method"] .ant-select-selector').click();
    await page.locator('.ant-select-dropdown:visible .ant-select-item-option-content')
      .filter({ hasText: /测量|Measurement/i }).first().click();
    await page.locator('[data-e2e="verification-result"] textarea')
      .fill("孔径实测 8.12mm 超差，定位销磨损 0.07mm，根因验证通过");
    await page.locator('[data-e2e="verify-pass"]').click();
    const aggregateVerification = page
      .locator('[data-e2e^="verification-item-"]')
      .filter({ hasText: aggregateRootCause });
    await expect(aggregateVerification.locator('[data-e2e^="verification-conclusion-"]'))
      .toContainText(/通过|Passed/i, { timeout: 10000 });

    // D4→D5 闸口要求当前根因已验证，推进。
    await page.locator('[data-e2e="capa-advance"]').click();
    await waitForStep(page, /^永久纠正措施$|^Permanent Corrective Action$/);

    // Step 6: D5 永久措施
    const d5 = page.locator("textarea").first();
    await d5.fill("更换定位销并建立定期磨损检测周期，校准孔径加工夹具。");
    await d5.evaluate((el: any) => el.blur());
    await page.locator('[data-e2e="capa-advance"]').click();
    await waitForStep(page, /^效果验证$|^Effect Verification$/);

    // Step 7: D6 实施验证
    const d6 = page.locator("textarea").first();
    await d6.fill("更换后连续 3 批抽检孔径均合格，CPK 1.67。");
    await d6.evaluate((el: any) => el.blur());
    const d7RecommendationsResponsePromise = page.waitForResponse(
      (res) => res.url().includes(`/api/capa/${capId}/d7-fmea-recommendations`) && res.request().method() === "GET"
    );
    await page.locator('[data-e2e="capa-advance"]').click();
    await waitForStep(page, /^预防复发措施$|^Prevent Recurrence$/);
    const d7RecommendationsResponse = await d7RecommendationsResponsePromise;
    expect(d7RecommendationsResponse.ok()).toBeTruthy();

    // Step 8: D7 预防复发 — engineer 完成 D7，进入 manager 审批边。
    const d7 = page.locator("textarea").first();
    await d7.fill("将定位销磨损检测纳入首件检验 + 周保养点检表。");
    await d7.evaluate((el: any) => el.blur());
    // D7 推荐（FMEA 节点）须由 engineer 在 D7_PREVENTION 逐一处置后才可完成 D7。全部标记「无需更新」(skip)。
    const d7Items = page.locator('[data-e2e^="d7-node-action-"]');
    await expect(d7Items.first()).toBeVisible({ timeout: 10000 });
    const d7Count = await d7Items.count();
    expect(d7Count).toBeGreaterThan(0);
    for (let i = 0; i < d7Count; i++) {
      await d7Items.nth(i).locator('[data-e2e="d7-skip"]').click();
      await expect(d7Items.nth(i).locator('[data-e2e="d7-action-status"]')).toBeVisible({ timeout: 10000 });
    }
    await expect(page.locator('[data-e2e="capa-advance"]')).toBeVisible();
    await page.locator('[data-e2e="capa-advance"]').click();
    await expect(page.locator('[data-e2e="capa-status"]')).toHaveText("D7_COMPLETED");
    await engCtx.close();

    // ── Manager: D7_COMPLETED→D8_GATE_PENDING 文档门禁交接 ───────────────
    const mgrCtx = await browser.newContext({ storageState: "e2e/.storage-state/manager.json" });
    const mPage = await mgrCtx.newPage();
    await setProductLine(mPage, PRODUCT_LINE);
    await mPage.goto(`/capa/${capId}`);
    await mPage.waitForLoadState("networkidle");
    await expect(mPage.locator('[data-e2e="capa-status"]')).toHaveText("D7_COMPLETED");

    // Manager 仅执行 D7_COMPLETED→D8_GATE_PENDING 审批边。
    await expect(mPage.locator('[data-e2e="capa-advance"]')).toBeVisible();
    await mPage.locator('[data-e2e="capa-advance"]').click();
    await mPage.waitForLoadState("networkidle");
    await expect(mPage.locator('[data-e2e="capa-status"]')).toHaveText("D8_GATE_PENDING");
    await expect(mPage.locator('[data-e2e="doc-gate-panel"]')).toBeVisible({ timeout: 10000 });
    await expect(mPage.locator('[data-e2e="capa-advance"]')).toBeHidden();
    await mgrCtx.close();

    // ── Viewer: 只读断言 ─────────────────────────────────────────────────
    const viewCtx = await browser.newContext({ storageState: "e2e/.storage-state/viewer.json" });
    const vPage = await viewCtx.newPage();
    await setProductLine(vPage, PRODUCT_LINE);
    await vPage.goto("/capa");
    await vPage.waitForLoadState("networkidle");
    // 列表看到处于文档门禁的故事 8D。
    await expect(vPage.locator(`[data-e2e="row-${STORY_DOC_NO}"]`)).toBeVisible({ timeout: 10000 });
    // 只读用户无创建入口。
    await expect(vPage.locator('[data-e2e="capa-create"]')).toBeHidden();
    // 打开详情，文档门禁与全局推进按钮对 viewer 均为只读。
    await vPage.locator(`[data-e2e="row-${STORY_DOC_NO}"]`).getByRole("button", { name: /处理|Process/i }).click();
    await vPage.waitForURL(/\/capa\//);
    await expect(vPage.locator('[data-e2e="capa-status"]')).toHaveText("D8_GATE_PENDING");
    await expect(vPage.locator('[data-e2e="doc-gate-panel"]')).toBeVisible({ timeout: 10000 });
    await expect(vPage.locator('[data-e2e="capa-advance"]')).toBeHidden();
    await viewCtx.close();

    // ── 审计轨迹断言：1 CREATE + 8 TRANSITION（操作人符合故事角色） ─────
    const logs = await fetchCapaAuditLogs(capId, auditStart);
    const creates = logs.filter((l) => l.action === "CREATE");
    const transitions = logs
      .filter((l) => l.action === "TRANSITION")
      .sort((a, b) => new Date(a.operated_at).getTime() - new Date(b.operated_at).getTime());
    expect(creates).toHaveLength(1);
    expect(creates[0].operated_by).toBe("engineer");
    expect(transitions).toHaveLength(8);
    const expectedTransitions: [string, string, string][] = [
      ["D1_TEAM", "D2_DESCRIPTION", "engineer"],
      ["D2_DESCRIPTION", "D3_INTERIM", "engineer"],
      ["D3_INTERIM", "D4_ROOT_CAUSE", "engineer"],
      ["D4_ROOT_CAUSE", "D5_CORRECTION", "engineer"],
      ["D5_CORRECTION", "D6_VERIFICATION", "engineer"],
      ["D6_VERIFICATION", "D7_PREVENTION", "engineer"],
      ["D7_PREVENTION", "D7_COMPLETED", "engineer"],
      ["D7_COMPLETED", "D8_GATE_PENDING", "manager"],
    ];
    for (let i = 0; i < 8; i++) {
      expect(transitions[i].changed_fields.old_status).toBe(expectedTransitions[i][0]);
      expect(transitions[i].changed_fields.new_status).toBe(expectedTransitions[i][1]);
      expect(transitions[i].operated_by).toBe(expectedTransitions[i][2]);
    }
  });

  test("D4 verification subflow: passed does not increment retry_count (base case)", async ({ browser }) => {
    test.setTimeout(180000);

    const { page, context, capId } = await createCapaAndAdvanceToD4(browser, D4_BASE_DOC_NO);

    const engineerPw = await accountPassword("engineer");
    const token = await loginForToken("engineer", engineerPw);
    const api = await authedApi(token);

    async function fetchCapa(id: string) {
      const r = await api.get(`/capa/${id}`);
      expect(r.status).toBe(200);
      return r.data as any;
    }

    async function setCurrentRootCause(text: string) {
      const d4 = page.locator("textarea").first();
      await d4.fill(text);
      await d4.evaluate((el: any) => el.blur());
    }

    async function openVerificationForm() {
      await page.locator('[data-e2e="d4-verification-new"]').click();
    }

    async function fillVerificationDetail() {
      await page.locator('[data-e2e="verification-method"] .ant-select-selector').click();
      await page.locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: /测量|Measurement/i }).first().click();
      await page.locator('[data-e2e="verification-result"] textarea')
        .fill("实测孔径 8.12mm 超差，定位销磨损 0.07mm");
    }

    function verificationItems(rootCause: string) {
      return page.locator('[data-e2e^="verification-item-"]').filter({ hasText: rootCause });
    }

    async function saveDraft(rootCause: string) {
      await page.locator('[data-e2e="verify-save-draft"]').click();
      const item = verificationItems(rootCause);
      await expect(item).toHaveCount(1);
      await expect(item.locator('[data-e2e^="verification-conclusion-"]'))
        .toContainText(/草稿|Draft|Pending/i, { timeout: 10000 });
    }

    async function submitFail(rootCause: string) {
      const pendingItem = verificationItems(rootCause).filter({ has: page.locator('[data-e2e^="verify-fail-"]') });
      await expect(pendingItem).toHaveCount(1);
      await pendingItem.locator('[data-e2e^="verify-fail-"]').click();
      const failedItem = verificationItems(rootCause).filter({ hasText: /不通过|Failed|未通过/i });
      await expect(failedItem).toHaveCount(1);
      await expect(failedItem.locator('[data-e2e^="verify-pass-"]')).toHaveCount(0);
    }

    async function submitPass(rootCause: string) {
      await page.locator('[data-e2e="verify-pass"]').click();
      const passedItem = verificationItems(rootCause)
        .filter({ hasText: /通过|Passed/i })
        .filter({ hasNotText: /不通过|Failed|未通过/i });
      await expect(passedItem).toHaveCount(1);
    }

    // 根因 A：保存草稿 → retry_count 不递增。
    const rootCauseA = "根因 A：定位销磨损导致孔径偏大";
    await setCurrentRootCause(rootCauseA);
    await openVerificationForm();
    await fillVerificationDetail();
    await saveDraft(rootCauseA);
    let capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(0);

    // 根因 A：提交 failed → retry_count = 1；failed 记录不可再改为 passed。
    await submitFail(rootCauseA);
    capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(1);

    // 根因 A：追加一条 passed 验证 → retry_count 仍为 1（passed 不递增）。
    await openVerificationForm();
    await fillVerificationDetail();
    await submitPass(rootCauseA);
    await expect(verificationItems(rootCauseA)).toHaveCount(2);
    capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(1);

    // 推进到 D5：无阈值警告（retry_count < 3）。
    const advanceResponsePromise = page.waitForResponse(
      (res) => res.url().includes(`/api/capa/${capId}/advance`) && res.request().method() === "POST"
    );
    await page.locator('[data-e2e="capa-advance"]').click();
    const advanceRes = await advanceResponsePromise;
    expect(advanceRes.ok()).toBeTruthy();
    const advanceBody = await advanceRes.json();
    expect(advanceBody.capa.status).toBe("D5_CORRECTION");
    expect(advanceBody.capa.d4_retry_count).toBe(1);
    expect(advanceBody.warning).toBeNull();

    await context.close();
  });

  test("D4 verification subflow: threshold warning at retry_count >= 3", async ({ browser }) => {
    test.setTimeout(180000);

    const { page, context, capId } = await createCapaAndAdvanceToD4(browser, D4_SUBFLOW_DOC_NO);

    const engineerPw = await accountPassword("engineer");
    const token = await loginForToken("engineer", engineerPw);
    const api = await authedApi(token);

    async function fetchCapa(id: string) {
      const r = await api.get(`/capa/${id}`);
      expect(r.status).toBe(200);
      return r.data as any;
    }

    async function setCurrentRootCause(text: string) {
      const d4 = page.locator("textarea").first();
      await d4.fill(text);
      await d4.evaluate((el: any) => el.blur());
    }

    async function openVerificationForm() {
      await page.locator('[data-e2e="d4-verification-new"]').click();
    }

    async function fillVerificationDetail() {
      await page.locator('[data-e2e="verification-method"] .ant-select-selector').click();
      await page.locator('.ant-select-dropdown:visible .ant-select-item-option-content')
        .filter({ hasText: /测量|Measurement/i }).first().click();
      await page.locator('[data-e2e="verification-result"] textarea')
        .fill("实测孔径 8.12mm 超差，定位销磨损 0.07mm");
    }

    function verificationItems(rootCause: string) {
      return page.locator('[data-e2e^="verification-item-"]').filter({ hasText: rootCause });
    }

    async function saveDraft(rootCause: string) {
      await page.locator('[data-e2e="verify-save-draft"]').click();
      const item = verificationItems(rootCause);
      await expect(item).toHaveCount(1);
      await expect(item.locator('[data-e2e^="verification-conclusion-"]'))
        .toContainText(/草稿|Draft|Pending/i, { timeout: 10000 });
    }

    async function submitFail(rootCause: string) {
      const pendingItem = verificationItems(rootCause).filter({ has: page.locator('[data-e2e^="verify-fail-"]') });
      await expect(pendingItem).toHaveCount(1);
      await pendingItem.locator('[data-e2e^="verify-fail-"]').click();
      const failedItem = verificationItems(rootCause).filter({ hasText: /不通过|Failed|未通过/i });
      await expect(failedItem).toHaveCount(1);
      await expect(failedItem.locator('[data-e2e^="verify-pass-"]')).toHaveCount(0);
    }

    async function submitPass(rootCause: string) {
      await page.locator('[data-e2e="verify-pass"]').click();
      const passedItem = verificationItems(rootCause)
        .filter({ hasText: /通过|Passed/i })
        .filter({ hasNotText: /不通过|Failed|未通过/i });
      await expect(passedItem).toHaveCount(1);
    }

    // 阈值根因 A：提交 failed → retry_count = 1。
    const rootCauseA = "阈值根因 A：定位销磨损导致孔径偏大";
    await setCurrentRootCause(rootCauseA);
    await openVerificationForm();
    await fillVerificationDetail();
    await saveDraft(rootCauseA);
    let capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(0);

    await submitFail(rootCauseA);
    capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(1);

    // 阈值根因 B：failed 行 → retry_count = 2。
    const rootCauseB = "阈值根因 B：夹具重复定位误差";
    await setCurrentRootCause(rootCauseB);
    await openVerificationForm();
    await fillVerificationDetail();
    await saveDraft(rootCauseB);
    await submitFail(rootCauseB);
    capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(2);

    // 阈值根因 C：failed 行 → retry_count = 3（达到阈值）。
    const rootCauseC = "阈值根因 C：切削液温度波动";
    await setCurrentRootCause(rootCauseC);
    await openVerificationForm();
    await fillVerificationDetail();
    await saveDraft(rootCauseC);
    await submitFail(rootCauseC);
    capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(3);

    // 阈值根因 D：直接 passed → 不递增；随后 advance 触发 threshold 警告。
    const rootCauseD = "阈值根因 D：刀具磨损补偿未生效";
    await setCurrentRootCause(rootCauseD);
    await openVerificationForm();
    await fillVerificationDetail();
    await submitPass(rootCauseD);

    const advanceResponsePromise = page.waitForResponse(
      (res) => res.url().includes(`/api/capa/${capId}/advance`) && res.request().method() === "POST"
    );
    await page.locator('[data-e2e="capa-advance"]').click();
    const advanceRes = await advanceResponsePromise;
    expect(advanceRes.ok()).toBeTruthy();
    const advanceBody = await advanceRes.json();
    expect(advanceBody.capa.status).toBe("D5_CORRECTION");
    expect(advanceBody.capa.d4_retry_count).toBe(3);
    expect(advanceBody.warning).toContain("建议升级处理");

    // UI 侧 advanceCAPA() 把 warning 展示为 message.warning。
    await expect(page.locator(".ant-message").getByText("建议升级处理")).toBeVisible({ timeout: 5000 });

    await context.close();
  });
});
