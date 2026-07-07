import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import path from "path";
import { accountPassword } from "../../fixtures/seed-state";
import { cleanupByPrefix, loginForToken, authedApi } from "../../helpers/api-client";

/**
 * US-E2E-01 — 8D 全程闭环故事级 spec（Spec C / P2-11）。
 *
 * 覆盖故事主流程 10 步、12 阶段推荐编排 DAG 结构断言、7 条 TRANSITION 审计断言、
 * AI 采纳 provenance 留痕、viewer 只读。
 *
 * 与 m1-core/capa.spec.ts（D1→D2 冒烟）、capa-ai-draft.spec.ts（按钮可见性）并行；
 * 用独立单号前缀 E2E-STORY-CAPA-，afterAll 清理不互斥。
 *
 * 设计取舍：
 * - 审计断言走 GET /api/admin/logs/audit?table_name=capa_eightd（admin token），按 record_id 客户端过滤。
 *   故事的 1 CREATE + 7 TRANSITION（D1→D2…D6→D7 由 engineer、D7→D8 由 manager）在此回读。
 *   （PROGRESS 初稿写「/api/audit-logs?target_id」，但该端点不存在；实际 admin/logs/audit 无 record_id 过滤，
 *   客户端过滤等价且无需新增后端端点——Surgical Changes。）
 * - AI 采纳留痕同样从审计日志回读（action=ADOPT_RECOMMENDATION，changed_fields 含 source + stage_index），
 *   不另建 seed-state adoptions 回读端点；审计日志由 adopt_recommendation 服务同事务写入，证明全链路。
 * - 无 LLM 凭证时：stage 11（LLM 融合）断言 skipped，核心闭环照跑；有凭证时断言 done。
 *   D4 推荐即使无 LLM 也由 FMEA 图 / 规则等源产出，provenance + 采纳断言仍可执行。
 */

const STORY_DOC_NO = "E2E-STORY-CAPA-001";
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

test.describe("US-E2E-01 CAPA 8D closed-loop story", () => {
  test.afterAll(async () => {
    await cleanupByPrefix("E2E-STORY-CAPA");
  });

  test("10-step closed loop: create → D1..D7 (engineer) → D8 (manager) → viewer read-only + audit trail", async ({ browser }) => {
    test.setTimeout(240000); // 全故事驱动 7 次推进 + D4 推荐 + D7 处置 + 三角色，远超默认 30s。
    const llm = hasLLMCreds();
    // 审计窗口起点（留 5s 抵消时钟漂移）。
    const auditStart = new Date(Date.now() - 5000).toISOString();

    // ── Engineer: create + D1..D7 ──────────────────────────────────────────
    const engCtx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await engCtx.newPage();
    await setProductLine(page, PRODUCT_LINE);
    await page.goto("/capa");
    await page.waitForLoadState("networkidle");

    // Step 1: create 8D
    await page.locator('[data-e2e="capa-create"]').click();
    await page.getByLabel(/报告编号|document no|report no/i).fill(STORY_DOC_NO);
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

    // Step 2: D1 团队组建 — 添加一名成员（8D 团队负责人由后续 manager 账号审批 D7→D8 代表）。
    await page.getByPlaceholder(/成员姓名|Member name/i).first().fill("张工");
    await page.getByRole("button", { name: /添加成员|Add Member/i }).click();
    await page.locator('[data-e2e="capa-advance"]').click();
    await waitForStep(page, /^5W2H 问题描述$|^5W2H Problem Description$/);

    // Step 3: D2 问题描述 — AI 草拟按钮可见性（LLM 凭证齐时），填写描述后推进。
    if (llm) {
      await expect(page.locator('[data-e2e="capa-ai-draft"]')).toBeVisible({ timeout: 10000 });
    }
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
    // Step 5: D4 — 用验证卡 testid 作哨兵（D4 字段标签含括号，比文本匹配更稳）。
    await expect(page.locator('[data-e2e="d4-verification-card"]')).toBeVisible({ timeout: 10000 });

    // 12 阶段 DAG 结构断言（rec-dag-stage-{index} + data-status）。
    await expect(page.locator('[data-e2e="rec-dag-stage-1"]')).toBeVisible({ timeout: 20000 });
    for (let i = 1; i <= 12; i++) {
      const stage = page.locator(`[data-e2e="rec-dag-stage-${i}"]`);
      await expect(stage).toBeVisible();
      const status = await stage.getAttribute("data-status");
      expect(["pending", "running", "done", "skipped", "error"]).toContain(status);
    }
    // 输出阶段恒为 done；LLM 融合阶段随凭证状态。
    await expect(page.locator('[data-e2e="rec-dag-stage-12"]')).toHaveAttribute("data-status", "done");
    await expect(page.locator('[data-e2e="rec-dag-stage-11"]')).toHaveAttribute(
      "data-status",
      llm ? "done" : "skipped",
    );

    // provenance + AI 采纳（推荐非空时采纳首条，留痕含来源）。
    const recSourceCount = await page.locator('[data-e2e^="rec-source-"]').count();
    let adopted = false;
    const d4Textarea = page.locator("textarea").first();
    if (recSourceCount > 0) {
      await page.locator('[data-e2e="d4-adopt"]').first().click();
      // 采纳后 d4_root_cause 被服务端追加并 refresh，textarea 反映非空即采纳成功。
      await expect(d4Textarea).not.toHaveValue("", { timeout: 10000 });
      adopted = true;
    } else {
      await d4Textarea.fill("现场根因：螺栓孔径定位销磨损导致孔径偏大");
      await d4Textarea.evaluate((el: any) => el.blur());
    }

    // 现场验证卡：记录方法/结果/证据，标记已验证（root_cause_text 预填当前 d4_root_cause）。
    await page.locator('[data-e2e="d4-verification-new"]').click();
    await page.locator('[data-e2e="verification-method"] input').fill("三坐标测量机复测孔径 + 定位销磨损量");
    await page.locator('[data-e2e="verification-result"] textarea').fill("孔径实测 8.12mm 超差，定位销磨损 0.07mm，根因验证通过");
    await page.locator('[data-e2e="verification-form-is-verified"]').click();
    await page.locator('[data-e2e="verification-submit"]').click();
    await expect(page.locator('[data-e2e="verification-status"]')).toBeVisible({ timeout: 10000 });

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

    // AI 采纳留痕（含来源 + 阶段）。
    const adopts = logs.filter((l) => l.action === "ADOPT_RECOMMENDATION");
    if (adopted) {
      expect(adopts.length).toBeGreaterThanOrEqual(1);
      const a = adopts[0];
      expect(a.changed_fields.source).toBeTruthy();
      expect(typeof a.changed_fields.stage_index).toBe("number");
      expect(a.operated_by).toBe("engineer");
    } else {
      // 无推荐可采纳（环境异常）——记录但不阻断核心闭环。
      console.warn("[capa-story] no D4 recommendation to adopt; ADOPT_RECOMMENDATION assertion skipped");
    }
  });
});