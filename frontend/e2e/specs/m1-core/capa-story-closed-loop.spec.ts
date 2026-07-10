import { test, expect } from "@playwright/test";
import { accountPassword } from "../../fixtures/seed-state";
import { cleanupByPrefix, loginForToken, authedApi, E2E_API_BASE_URL } from "../../helpers/api-client";

/**
 * US-E2E-01 — 8D 非 AI 闭环故事级 spec（Spec C / P2-11）。
 *
 * 覆盖故事主流程 10 步、7 条 TRANSITION 审计断言、viewer 只读。
 * 原混合 spec 中的 AI 推荐断言（D4 12 阶段 DAG / AI 采纳 provenance）已拆分至
 * capa-story-ai-recommend.spec.ts；本文件无 LLM 凭证也必须全绿。
 *
 * 与 m1-core/capa.spec.ts（D1→D2 冒烟）、capa-ai-draft.spec.ts（按钮可见性）、
 * capa-story-ai-recommend.spec.ts（AI D4 推荐）并行；用独立单号前缀
 * E2E-STORY-CAPA-，afterAll 清理不互斥。
 *
 * 设计取舍：
 * - 审计断言走 GET /api/admin/logs/audit?table_name=capa_eightd（admin token），按 record_id 客户端过滤。
 *   故事的 1 CREATE + 7 TRANSITION（D1→D2…D6→D7_PREVENTION 由 engineer、D7→D8 由 manager）在此回读。
 *   （PROGRESS 初稿写「/api/audit-logs?target_id」，但该端点不存在；实际 admin/logs/audit 无 record_id 过滤，
 *   客户端过滤等价且无需新增后端端点——Surgical Changes。）
 * - D4 验证子流程断言（method / conclusion / retry_count）在独立 test 中覆盖，使用与主故事相同的
 *   create→D4 初始化 helper，避免重复登录/seed 代码。
 */

const STORY_DOC_NO = "E2E-STORY-CAPA-001";
const D4_SUBFLOW_DOC_NO = "E2E-STORY-CAPA-D4-001";
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
  await page.locator('[data-e2e="capa-advance"]').click();
  // Step 5: D4 — 用验证卡 testid 作哨兵。
  await expect(page.locator('[data-e2e="d4-verification-card"]')).toBeVisible({ timeout: 10000 });

  return { page, context: ctx, capId };
}

test.describe("US-E2E-01 CAPA 8D closed-loop story", () => {
  test.afterAll(async () => {
    await cleanupByPrefix("E2E-STORY-CAPA");
  });

  test("10-step closed loop: create → D1..D7 (engineer) → D8 (manager) → viewer read-only + audit trail", async ({ browser }) => {
    test.setTimeout(240000); // 全故事驱动 7 次推进 + D7 处置 + 三角色，远超默认 30s。
    // 审计窗口起点（留 5s 抵消时钟漂移）。
    const auditStart = new Date(Date.now() - 5000).toISOString();

    // ── Engineer: create + D1..D7 ──────────────────────────────────────────
    const { page, context: engCtx, capId } = await createCapaAndAdvanceToD4(browser, STORY_DOC_NO);

    // D4 根因由工程师手动填写（AI 推荐断言已拆分至 capa-story-ai-recommend.spec.ts）。
    const d4Textarea = page.locator("textarea").first();
    await d4Textarea.fill("现场根因：螺栓孔径定位销磨损导致孔径偏大");
    await d4Textarea.evaluate((el: any) => el.blur());

    // D4 现场验证：method 选 measurement，填写 result，提交 passed，满足 D4→D5 闸口。
    await page.locator('[data-e2e="d4-verification-new"]').click();
    await page.locator('[data-e2e="verification-method"] .ant-select-selector').click();
    await page.locator('.ant-select-dropdown:visible .ant-select-item-option-content')
      .filter({ hasText: /测量|Measurement/i }).first().click();
    await page.locator('[data-e2e="verification-result"] textarea')
      .fill("孔径实测 8.12mm 超差，定位销磨损 0.07mm，根因验证通过");
    await page.locator('[data-e2e="verify-pass"]').click();
    await expect(page.locator('[data-e2e="verification-conclusion-0"]'))
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
    await page.locator('[data-e2e="capa-advance"]').click();
    await waitForStep(page, /^预防复发措施$|^Prevent Recurrence$/);

    // Step 8: D7 预防复发 — 工程师填写后无法推进（D7→D8 需审批权限）。
    const d7 = page.locator("textarea").first();
    await d7.fill("将定位销磨损检测纳入首件检验 + 周保养点检表。");
    await d7.evaluate((el: any) => el.blur());
    await expect(page.locator('[data-e2e="capa-advance"]')).toBeHidden();
    await engCtx.close();

    // ── Manager: D7→D8 关闭审批 ──────────────────────────────────────────
    const mgrCtx = await browser.newContext({ storageState: "e2e/.storage-state/manager.json" });
    const mPage = await mgrCtx.newPage();
    await setProductLine(mPage, PRODUCT_LINE);
    await mPage.goto(`/capa/${capId}`);
    await mPage.waitForLoadState("networkidle");
    await expect(mPage.getByText(/^预防复发措施$|^Prevent Recurrence$/)).toBeVisible({ timeout: 10000 });

    // D7 推荐（FMEA 节点）需逐一处置后方可推进 D7→D8。全部标记「无需更新」(skip)。
    const d7Items = mPage.locator('[data-e2e^="d7-node-action-"]');
    const d7Count = await d7Items.count();
    for (let i = 0; i < d7Count; i++) {
      await d7Items.nth(i).locator('[data-e2e="d7-skip"]').click();
      await expect(d7Items.nth(i).locator('[data-e2e="d7-action-status"]')).toBeVisible({ timeout: 10000 });
    }
    await expect(mPage.locator('[data-e2e="capa-advance"]')).toBeVisible();
    await mPage.locator('[data-e2e="capa-advance"]').click();
    await mPage.waitForLoadState("networkidle");
    // D8_CLOSURE 后无推进按钮。
    await expect(mPage.locator('[data-e2e="capa-advance"]')).toBeHidden();
    await mgrCtx.close();

    // ── Viewer: 只读断言 ─────────────────────────────────────────────────
    const viewCtx = await browser.newContext({ storageState: "e2e/.storage-state/viewer.json" });
    const vPage = await viewCtx.newPage();
    await setProductLine(vPage, PRODUCT_LINE);
    await vPage.goto("/capa");
    await vPage.waitForLoadState("networkidle");
    // 列表看到已关闭的故事 8D。
    await expect(vPage.locator(`[data-e2e="row-${STORY_DOC_NO}"]`)).toBeVisible({ timeout: 10000 });
    // 只读用户无创建入口。
    await expect(vPage.locator('[data-e2e="capa-create"]')).toBeHidden();
    // 打开详情，无推进按钮。
    await vPage.locator(`[data-e2e="row-${STORY_DOC_NO}"]`).getByRole("button", { name: /处理|Process/i }).click();
    await vPage.waitForURL(/\/capa\//);
    await expect(vPage.locator('[data-e2e="capa-advance"]')).toBeHidden();
    await viewCtx.close();

    // ── 审计轨迹断言：1 CREATE + 7 TRANSITION（操作人符合故事角色） ─────
    const logs = await fetchCapaAuditLogs(capId, auditStart);
    const creates = logs.filter((l) => l.action === "CREATE");
    const transitions = logs
      .filter((l) => l.action === "TRANSITION")
      .sort((a, b) => new Date(a.operated_at).getTime() - new Date(b.operated_at).getTime());
    expect(creates).toHaveLength(1);
    expect(creates[0].operated_by).toBe("engineer");
    expect(transitions).toHaveLength(7);
    const expectedTransitions: [string, string, string][] = [
      ["D1_TEAM", "D2_DESCRIPTION", "engineer"],
      ["D2_DESCRIPTION", "D3_INTERIM", "engineer"],
      ["D3_INTERIM", "D4_ROOT_CAUSE", "engineer"],
      ["D4_ROOT_CAUSE", "D5_CORRECTION", "engineer"],
      ["D5_CORRECTION", "D6_VERIFICATION", "engineer"],
      ["D6_VERIFICATION", "D7_PREVENTION", "engineer"],
      ["D7_PREVENTION", "D8_CLOSURE", "manager"],
    ];
    for (let i = 0; i < 7; i++) {
      expect(transitions[i].changed_fields.old_status).toBe(expectedTransitions[i][0]);
      expect(transitions[i].changed_fields.new_status).toBe(expectedTransitions[i][1]);
      expect(transitions[i].operated_by).toBe(expectedTransitions[i][2]);
    }
  });

  test("D4 verification subflow: method enum + conclusion + retry_count", async ({ browser, request }) => {
    test.setTimeout(180000);

    const { page, context, capId } = await createCapaAndAdvanceToD4(browser, D4_SUBFLOW_DOC_NO);

    // 用 request 登录 engineer，取得独立 token 用于 GET /api/capa/{id} 断言。
    const engineerPw = await accountPassword("engineer");
    const loginResp = await request.post(`${E2E_API_BASE_URL}/auth/login`, {
      data: { username: "engineer", password: engineerPw },
    });
    expect(loginResp.ok()).toBeTruthy();
    const token = ((await loginResp.json()) as any).access_token as string;
    const apiHeaders = { Authorization: `Bearer ${token}` };

    async function fetchCapa(id: string) {
      const r = await request.get(`${E2E_API_BASE_URL}/capa/${id}`, { headers: apiHeaders });
      expect(r.ok()).toBeTruthy();
      return r.json() as Promise<any>;
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

    async function saveDraft() {
      await page.locator('[data-e2e="verify-save-draft"]').click();
      await expect(page.locator('[data-e2e="verification-conclusion-0"]'))
        .toContainText(/草稿|Draft|Pending/i, { timeout: 10000 });
    }

    async function submitFail() {
      await page.locator('[data-e2e="verify-fail-0"]').click();
      await expect(page.locator('[data-e2e="verification-conclusion-0"]'))
        .toContainText(/不通过|Failed|未通过/i, { timeout: 10000 });
    }

    async function submitPass() {
      await page.locator('[data-e2e="verify-pass-0"]').click();
      await expect(page.locator('[data-e2e="verification-conclusion-0"]'))
        .toContainText(/通过|Passed/i, { timeout: 10000 });
    }

    // 根因 A：保存草稿 → retry_count 不递增。
    await setCurrentRootCause("根因 A：定位销磨损导致孔径偏大");
    await openVerificationForm();
    await fillVerificationDetail();
    await saveDraft();
    let capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(0);

    // 根因 A：提交 failed → retry_count = 1。
    await submitFail();
    capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(1);

    // 根因 B：failed → retry_count = 2。
    await setCurrentRootCause("根因 B：夹具重复定位误差");
    await openVerificationForm();
    await fillVerificationDetail();
    await saveDraft();
    await submitFail();
    capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(2);

    // 根因 C：failed → retry_count = 3（达到阈值）。
    await setCurrentRootCause("根因 C：切削液温度波动");
    await openVerificationForm();
    await fillVerificationDetail();
    await saveDraft();
    await submitFail();
    capa = await fetchCapa(capId);
    expect(capa.d4_retry_count).toBe(3);

    // 根因 D：passed → 不递增；随后 advance 触发 threshold 警告。
    await setCurrentRootCause("根因 D：刀具磨损补偿未生效");
    await openVerificationForm();
    await fillVerificationDetail();
    await saveDraft();
    await submitPass();

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
