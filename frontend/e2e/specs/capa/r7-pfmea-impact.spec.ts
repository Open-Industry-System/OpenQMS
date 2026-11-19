import { expect, test, type Browser, type Page } from '@playwright/test';

const tenant = process.env.AGENT_BROWSER_TENANT!;
const report = process.env.AGENT_BROWSER_REPORT!;
const backend = process.env.AGENT_BACKEND_URL!;
const input = JSON.parse(process.env.AGENT_BROWSER_LOGIN!);
const path = `/api/capa/${report}/pfmea-impact`;
const origins = new Set([new URL(backend).origin, new URL(process.env.AGENT_BROWSER_URL!).origin]);

async function signIn(browser: Browser, username: string) {
  const context = await browser.newContext();
  await context.route('**/*', route => {
    const url = route.request().url();
    return url.startsWith('data:') || origins.has(new URL(url).origin) ? route.continue() : route.abort();
  });
  await context.addInitScript(slug => {
    localStorage.setItem('tenant_slug', slug);
    localStorage.setItem('openqms_locale', 'zh-CN');
  }, tenant);
  const page = await context.newPage();
  await page.goto('/login');
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(input.password);
  await page.locator('button[type=submit]').click();
  await expect(page).toHaveURL(/dashboard/);
  return { context, page };
}

async function openReport(page: Page) {
  await page.goto(`/capa/${report}`);
  await page.getByRole('button', { name: '以本报告创建任务', exact: true }).click();
  const panel = page.getByRole('region', { name: '评估对 PFMEA 的影响', exact: true });
  await expect(panel).toBeVisible();
  return panel;
}

async function runImpact(page: Page, previous?: string) {
  const panel = page.getByRole('region', { name: '评估对 PFMEA 的影响', exact: true });
  await panel.getByLabel('目标 PFMEA', { exact: true }).selectOption({
    label: `PFMEA-R7-NATIVE · Final assembly PFMEA · ${input.approvedLabel}`,
  });
  await expect(panel).toContainText('已有未批准修订');
  await expect(panel.getByRole('button', { name: '开始评估', exact: true })).toBeDisabled();
  await panel.getByLabel('批准的模型部署', { exact: true })
    .selectOption({ label: 'Synthetic R7 model · r7-native · 本地' });
  const creation = page.waitForResponse(r =>
    new URL(r.url()).pathname === `${path}/tasks` && r.request().method() === 'POST');
  await panel.getByRole('button', { name: '开始评估', exact: true }).click();
  const create = await creation;
  expect(create.status()).toBe(201);
  expect(create.request().postDataJSON()).toMatchObject({
    fmea_id: input.binding.fmea_id, approved_version_id: input.binding.approved_version_id,
    installation_id: input.binding.installation_id, model_deployment_id: input.binding.model_deployment_id,
    ...(previous ? { previous_result_id: previous } : {}),
  });
  const requestKey = create.request().postDataJSON().request_key;
  const { taskId } = await create.json();
  const launch = page.waitForResponse(r =>
    new URL(r.url()).pathname === `${path}/tasks/${taskId}/launch`, { timeout: 120000 });
  await panel.getByRole('button', { name: '运行评估', exact: true }).click();
  const finished = await launch;
  expect(finished.status()).toBe(200);
  const completed = await finished.json();
  expect(completed).toMatchObject({ taskId, status: 'completed' });
  const result = panel.getByRole('region', { name: 'PFMEA 影响评估建议', exact: true });
  await expect(result.getByRole('article')).toHaveCount(2);
  await expect(result).toContainText('employee measure 1');
  await expect(result).toContainText('employee measure 2');
  await expect(result).toContainText('有明确影响');
  await expect(result).toContainText('证据不足');
  await expect(result).toContainText('Add an independent torque recipe check at OP40.');
  await expect(result).toContainText('No station applicability evidence for this measure.');
  const evidence = page.waitForResponse(r => new URL(r.url()).pathname.includes(
    `${path}/tasks/${taskId}/results/${completed.resultId}/sources/`));
  await result.getByRole('button', { name: `PFMEA ${input.approvedLabel} · control-a`, exact: true }).click();
  const source = await evidence;
  expect(source.status()).toBe(200);
  await expect(result.getByText('Verify program', { exact: true })).toBeVisible();
  return { taskId, resultId: completed.resultId as string, sourcePath: new URL(source.url()).pathname, requestKey };
}

test('R7 employee generation, archived reevaluation, and reviewer source revocation', async ({ browser, request }) => {
  test.setTimeout(220000);
  const advanceFixture = async (action: string) => {
    const response = await request.post(`${backend}/__r7_browser/${action}`, {
      headers: { 'X-Acceptance-Nonce': input.nonce, 'X-Tenant-ID': tenant },
    });
    expect(response.status(), `Fixture ${action}: ${await response.text()}`).toBe(200);
  };
  const employee = await signIn(browser, 'trial-executor');
  const initial = await openReport(employee.page);
  const original = await runImpact(employee.page);
  await advanceFixture('archive');
  await initial.getByRole('button', { name: '重新评估', exact: true }).click();
  const archived = await runImpact(employee.page, original.resultId);
  expect(archived.taskId).not.toBe(original.taskId);
  expect(archived.requestKey).not.toBe(original.requestKey);
  await advanceFixture('archive-reviewed');
  await employee.context.close();

  const reviewer = await signIn(browser, 'r7-reviewer');
  const panel = await openReport(reviewer.page);
  await expect(panel.getByRole('button', { name: '开始评估', exact: true })).toHaveCount(0);
  const detailPath = `${path}/tasks/${archived.taskId}/results/${archived.resultId}`;
  const selected = reviewer.page.waitForResponse(r => new URL(r.url()).pathname === detailPath);
  await panel.getByRole('combobox', { name: '历史评估', exact: true })
    .selectOption(`${archived.taskId}/${archived.resultId}`);
  const response = await selected;
  expect(response.status()).toBe(200);
  const authorization = (await response.request().allHeaders()).authorization;
  expect(authorization).toBeTruthy();
  await expect(panel.getByRole('region', { name: 'PFMEA 影响评估建议', exact: true })).toBeVisible();
  await advanceFixture('revoke-source');
  // Either the history list or the detail poll can discover the withdrawal first.
  await expect(panel.getByRole('region', { name: 'PFMEA 影响评估建议', exact: true })).toHaveCount(0, { timeout: 15000 });
  for (const url of [detailPath, archived.sourcePath]) {
    const denied = await reviewer.context.request.get(`${backend}${url}`, {
      headers: { Authorization: authorization, 'X-Tenant-ID': tenant },
    });
    expect(denied.status()).toBe(404);
    expect(await denied.json()).toEqual({ detail: 'Impact assessment unavailable' });
  }
  const target = await reviewer.context.request.get(`${backend}/api/fmea/${input.binding.fmea_id}`, {
    headers: { Authorization: authorization, 'X-Tenant-ID': tenant },
  });
  expect(target.status()).toBe(200);
  expect(await target.json()).toMatchObject({ fmea_id: input.binding.fmea_id });
  await reviewer.context.close();
});
