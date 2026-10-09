import { test, expect } from '@playwright/test';
const report = process.env.AGENT_BROWSER_REPORT!;
const backend = process.env.AGENT_BACKEND_URL!;
const login = JSON.parse(process.env.AGENT_BROWSER_LOGIN!);

test('actual employee restricted D4 candidate and source/version uncertainty withdrawal', async ({ page, context }) => {
  const origins = new Set([new URL(backend).origin, new URL(process.env.AGENT_BROWSER_URL!).origin]);
  await context.route('**/*', route => {
    const url = route.request().url();
    return url.startsWith('data:') || origins.has(new URL(url).origin) ? route.continue() : route.abort();
  });
  await context.addInitScript(({ token, refresh, tenant }) => {
    localStorage.setItem('access_token', token); localStorage.setItem('refresh_token', refresh);
    localStorage.setItem('tenant_slug', tenant); localStorage.setItem('i18nextLng', 'zh');
  }, { token: login.access_token, refresh: login.refresh_token, tenant: process.env.AGENT_BROWSER_TENANT! });
  async function fixture(action: string) {
    const response = await page.request.post(`${backend}/__d4_preview_acceptance/${action}`, {
      headers: { 'X-Acceptance-Nonce': process.env.AGENT_HARNESS_NONCE!, 'X-Tenant-ID': process.env.AGENT_BROWSER_TENANT! }, data: {},
    });
    expect(response.status()).toBe(200);
  }
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('d4-text-preview')) requests.push(request.method()+':'+new URL(request.url()).pathname); });
  await page.goto(`/capa/${report}`);
  const trigger = page.getByRole('button', { name: '正文脱敏候选预览', exact: true });
  await expect(trigger).toBeVisible();
  expect(requests.every(value => value.includes('/availability'))).toBeTruthy();
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'D4 正文脱敏候选预览' });
  await dialog.getByRole('textbox', { name: '显式替换词' }).fill('机密客户\nACME');
  const generated = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/d4-text-preview'));
  await dialog.getByRole('button', { name: '生成受限候选' }).click();
  const response = await generated;
  expect(response.status()).toBe(200);
  const first = await response.json();
  expect(first.data_class).toBe('restricted'); expect(first.external_delivery_allowed).toBe(false);
  expect(first.fields.some((value: {source_status:string}) => value.source_status === 'validated_reference')).toBeTruthy();
  const region = dialog.getByRole('region', { name: '受限正文预览' });
  await expect(region).toBeVisible();
  await expect(region.getByText(/扭矩10N·m/)).toBeVisible();
  const text = await region.innerText();
  for (const marker of ['机密客户','ACME','sam@example.test','13800138000','NEVER LOAD SOURCE TITLE','NEVER LOAD FMEA BODY']) {
    expect(text).not.toContain(marker);
  }
  expect(await dialog.getByRole('button', { name: /保存|替换原文|采纳/ }).count()).toBe(0);
  await fixture('change');
  await expect(region).toHaveCount(0);
  const changed = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/d4-text-preview') && r.status() === 200);
  await dialog.getByRole('button', { name: '生成受限候选' }).click();
  const second = await (await changed).json();
  expect(second.source_version).not.toBe(first.source_version);
  await expect(region.getByText(/扭矩12N·m/)).toBeVisible();
  await fixture('withdraw');
  await expect(region).toHaveCount(0);
  const denied = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/d4-text-preview') && r.status() === 403);
  await dialog.getByRole('button', { name: '生成受限候选' }).click();
  expect(await (await denied).json()).toEqual({ detail: 'PREVIEW_ACCESS_DENIED' });
  await expect(region).toHaveCount(0);
  await fixture('restore');
  await dialog.getByRole('button', { name: '生成受限候选' }).click();
  await expect(region).toBeVisible();
  await page.route(`**/api/capa/${report}/d4-text-preview/version`, route => route.abort('failed'));
  await expect(region).toHaveCount(0);
  await page.unroute(`**/api/capa/${report}/d4-text-preview/version`);
  await dialog.getByRole('button', { name: '关闭预览' }).click();
  await expect(dialog).toHaveCount(0);
  await trigger.click();
  await expect(dialog.getByRole('textbox', { name: '显式替换词' })).toHaveValue('');
  await dialog.getByRole('button', { name: '生成受限候选' }).click();
  await expect(region).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(dialog).toHaveCount(0);
  const count = requests.length;
  await page.waitForTimeout(2100);
  expect(requests).toHaveLength(count);
});
