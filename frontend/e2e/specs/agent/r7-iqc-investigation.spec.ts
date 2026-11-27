import { expect, test, type Browser } from '@playwright/test';

const tenant = process.env.AGENT_BROWSER_TENANT!;
const inspection = process.env.AGENT_BROWSER_REPORT!;
const backend = process.env.AGENT_BACKEND_URL!;
const input = JSON.parse(process.env.AGENT_BROWSER_LOGIN!);
const base = `/api/iqc/inspections/${inspection}`;
const origins = new Set([new URL(backend).origin, new URL(process.env.AGENT_BROWSER_URL!).origin]);

async function openIqc(browser: Browser, username: string) {
  const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
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
  await page.goto(`/iqc/inspections/${inspection}`);
  await page.getByRole('button', { name: '调查建议', exact: true }).click();
  return { context, page, drawer: page.getByRole('dialog', { name: '调查建议' }) };
}

test('IQC 调查建议由员工发起并按当前读者显示关联', async ({ browser, request }) => {
  const fixtureStep = async (name: string) => {
    const response = await request.post(`${backend}/__iqc_browser/${name}`, {
      headers: { 'X-Acceptance-Nonce': input.nonce, 'X-Tenant-ID': tenant },
    });
    expect(response.status(), await response.text()).toBe(200);
  };
  const employee = await openIqc(browser, 'trial-executor');
  const prepared = employee.page.waitForResponse(response =>
    new URL(response.url()).pathname === `${base}/investigations` && response.request().method() === 'POST');
  const opened = employee.page.waitForResponse(response =>
    new URL(response.url()).pathname.startsWith(`${base}/investigations/`) &&
    new URL(response.url()).pathname.includes('/results/'), { timeout: 90000 });
  await employee.drawer.getByRole('button', { name: '准备调查', exact: true }).click();
  const created = await prepared;
  expect(created.status()).toBe(201);
  const { task_id } = await created.json();
  const originalResponse = await opened;
  expect(originalResponse.status()).toBe(200);
  const visibleOriginal = await originalResponse.json();
  expect(visibleOriginal.task_id).toBe(task_id);
  const initialCard = employee.drawer.getByRole('region', { name: '调查建议卡' });
  await expect(initialCard).toContainText('外观黑点');
  await expect(initialCard).toContainText('抽样量未记录');
  await initialCard.getByRole('button', { name: '复制 D2 草稿', exact: true }).click();
  await expect(initialCard.getByRole('status')).toContainText('已复制 D2 草稿');
  await expect.poll(() => employee.page.evaluate(() => navigator.clipboard.readText())).toContain('外观黑点');

  const samePath = `${base}/investigations/${task_id}/results/${visibleOriginal.result_id}`;
  await fixtureStep('link');
  const admin = await openIqc(browser, input.admin);
  const wideRead = admin.page.waitForResponse(response => new URL(response.url()).pathname === samePath);
  await admin.drawer.getByRole('button', { name: '查看建议', exact: true }).click();
  const widerResult = await (await wideRead).json();
  expect(widerResult.result_id).toBe(visibleOriginal.result_id);
  expect(widerResult.card).toEqual(visibleOriginal.card);
  await expect(admin.drawer.getByRole('link', { name: '8D · 8D-IQC-BROWSER' })).toBeVisible();
  const sharedCard = admin.drawer.getByRole('region', { name: '调查建议卡' });
  await sharedCard.getByRole('button', { name: '复制 D2 草稿', exact: true }).click();
  await expect(sharedCard.getByRole('status')).toContainText('已复制 D2 草稿');
  await expect.poll(() => admin.page.evaluate(() => navigator.clipboard.readText())).toBe(visibleOriginal.card.d2);
  await expect(initialCard.getByRole('link', { name: '8D · 8D-IQC-BROWSER' })).toHaveCount(0);
  await expect(initialCard).toContainText('已核范围内可考虑新建调查。');

  await fixtureStep('revoke');
  await expect(initialCard).toHaveCount(0, { timeout: 15000 });
  await expect(employee.drawer.getByRole('button', { name: '查看建议', exact: true })).toHaveCount(0, { timeout: 15000 });
  await expect(employee.drawer).not.toContainText('外观黑点');
  await employee.context.close();
  await admin.context.close();
});
