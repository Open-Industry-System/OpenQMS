import { test, expect, type Page, type BrowserContext } from '@playwright/test';

const backend = process.env.AGENT_BACKEND_URL!;
const tenant = process.env.AGENT_BROWSER_TENANT!;
const editor = JSON.parse(process.env.OUTCOME_EDITOR_LOGIN!);
const approver = JSON.parse(process.env.OUTCOME_APPROVER_LOGIN!);

async function initialize(page: Page, context: BrowserContext) {
  const origins = new Set([new URL(backend).origin, new URL(process.env.AGENT_BROWSER_URL!).origin]);
  await context.route('**/*', route => {
    const url = route.request().url();
    return url.startsWith('data:') || origins.has(new URL(url).origin) ? route.continue() : route.abort();
  });
  // Tenant selection and language only. Tokens/roles come from normal login.
  await context.addInitScript(value => {
    localStorage.setItem('tenant_slug', value);
    localStorage.setItem('openqms_locale', 'zh-CN');
  }, tenant);
  await page.goto('/login');
  await page.locator('#username').fill(approver.username);
  await page.locator('#password').fill(approver.password);
  const login = page.waitForResponse(r => new URL(r.url()).pathname === '/api/auth/login' && r.request().method() === 'POST');
  await page.locator('button[type=submit]').click();
  expect((await login).status()).toBe(200);
  await expect(page).toHaveURL(/dashboard/);
}

async function command(page: Page, action: string) {
  const response = await page.request.post(`${backend}/__outcome_acceptance/${action}`, {
    headers: { 'X-Acceptance-Nonce': process.env.AGENT_HARNESS_NONCE!, 'X-Tenant-ID': tenant }, data: {},
  });
  expect(response.status()).toBe(200);
  return response.json();
}

async function business(page: Page, report: string, method: string, suffix: string, data?: object) {
  return page.evaluate(async ({ report, method, suffix, data }) => {
    const response = await fetch(`/api/capa/${report}${suffix}`, {
      method, headers: { 'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('access_token')}`, 'X-Tenant-ID': localStorage.getItem('tenant_slug')! },
      ...(data ? { body: JSON.stringify(data) } : {}),
    });
    return { status: response.status, body: await response.json() };
  }, { report, method, suffix, data });
}

async function sameDocumentLogin(page: Page, credentials: { username: string; password: string }) {
  // Exercise the real application login action, not setState or forged authority.
  // This deliberately keeps the same mounted document/report and outstanding read.
  const before = page.url();
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/auth/login' && r.request().method() === 'POST');
  await page.evaluate(async credentials => {
    const modulePath = '/src/store/authStore.ts';
    const { useAuthStore } = await import(modulePath);
    await useAuthStore.getState().login(credentials.username, credentials.password);
  }, credentials);
  expect((await response).status()).toBe(200);
  expect(page.url()).toBe(before);
}

function outcomeResponse(page: Page, report: string) {
  return page.waitForResponse(r => new URL(r.url()).pathname === `/api/capa/${report}/outcome-review`
    && r.request().method() === 'GET' && r.status() === 200);
}

async function reload(page: Page, report: string) {
  const response = outcomeResponse(page, report);
  await page.getByRole('button', { name: '重新加载审核材料', exact: true }).click();
  return (await response).json();
}

async function denyTerminalWrites(page: Page, report: string) {
  const before = await command(page, 'snapshot');
  for (const [method, suffix, data] of [
    ['PUT', '', { d6_verification: 'forbidden' }],
    ['POST', '/adopt-recommendation', { d_step: 'd4', adopted_text: 'forbidden', source: 'rule' }],
    ['POST', '/root-cause-verifications', { root_cause_text: 'forbidden' }],
  ] as const) {
    const result = await business(page, report, method, suffix, data);
    expect(result.status).toBe(409);
    expect(result.body).toEqual({ detail: 'CAPA_REVIEWED_CONTENT_LOCKED' });
    expect(await command(page, 'snapshot')).toEqual(before);
  }
}

test('terminal protection: actual employee login, same document identity, legacy material and source denial', async ({ page, context }) => {
  await initialize(page, context);
  const report = process.env.OUTCOME_TERMINAL_REPORT!;
  const response = outcomeResponse(page, report);
  await page.goto(`/capa/${report}`);
  const seen = await (await response).json();
  expect(seen.binding_status).toBe('legacy_unversioned');
  await expect(page.getByTestId('capa-outcome-core')).toContainText('实施后复测合格');
  await expect(page.getByTestId('capa-outcome-core')).toHaveAttribute('data-readonly', 'true');
  await expect(page.getByTestId('capa-outcome-approve')).toHaveCount(0);
  await denyTerminalWrites(page, report);
  await command(page, 'arm-read');
  await page.getByRole('button', { name: '重新加载审核材料', exact: true }).click();
  await command(page, 'wait-read');
  const cancelled = page.waitForEvent('requestfailed', request => new URL(request.url()).pathname === `/api/capa/${report}/outcome-review`);
  try {
    const supplement = await business(page, report, 'PUT', '', { d8_closure: '换班后的未审补充材料' });
    expect(supplement.status).toBe(200);
    const current = outcomeResponse(page, report);
    await sameDocumentLogin(page, editor);
    await current;
    await cancelled;
    await expect(page.locator('[data-e2e=capa-outcome-supplement]')).toContainText('换班后的未审补充材料');
  } finally {
    await command(page, 'release-read');
  }
  await expect(page.getByTestId('capa-outcome-approve')).toHaveCount(0);
  await expect(page.getByTestId('capa-outcome-core')).not.toContainText('换班后的未审补充材料');
  await expect(page.locator('[data-e2e=capa-outcome-supplement]')).toContainText('结案后补充，未纳入本次审核');
  // Legacy source binding cannot be reconstructed: 409 is honest, not a fake receipt.
  // Current source withdrawal must still return a complete denial before any source body.
  await sameDocumentLogin(page, approver);
  await command(page, 'withdraw-source');
  const denied = await business(page, process.env.OUTCOME_SOURCE_REPORT!, 'GET', '/outcome-review');
  expect(denied.status).toBe(403);
  expect(denied.body).toEqual({ detail: 'CAPA_OUTCOME_REVIEW_ACCESS_DENIED' });
  await command(page, 'restore-source');
  expect((await reload(page, report)).core).toEqual(seen.core);
});

test('live implemented outcomes: actual displayed revision, real approval, supplement and archive', async ({ page, context }) => {
  await initialize(page, context);
  const reportId = process.env.AGENT_BROWSER_REPORT!;
  const first = outcomeResponse(page, reportId);
  await page.goto(`/capa/${reportId}`);
  await first;
  await page.getByTestId('capa-outcome-core').waitFor();
  await expect(page.getByTestId('capa-outcome-core')).toContainText('实施后复测合格');
  await expect(page.getByTestId('capa-outcome-approve')).toBeEnabled();

  // Hold actual authorized bytes, change actual material, then login as EDIT in
  // the same mounted document. No delayed route.fulfill, synthetic DTO or sleep.
  await command(page, 'arm-read');
  await page.getByRole('button', { name: '重新加载审核材料', exact: true }).click();
  await command(page, 'wait-read');
  const cancelled = page.waitForEvent('requestfailed', request => new URL(request.url()).pathname === `/api/capa/${reportId}/outcome-review`);
  try {
    expect((await business(page, reportId, 'PUT', '', { d6_verification: '换班后新增合成复测结果' })).status).toBe(200);
    const current = outcomeResponse(page, reportId);
    await sameDocumentLogin(page, editor);
    await current; await cancelled;
    await expect(page.getByTestId('capa-outcome-core')).toContainText('换班后新增合成复测结果');
    await expect(page.getByTestId('capa-outcome-approve')).toHaveCount(0);
  } finally {
    await command(page, 'release-read');
  }
  expect((await business(page, reportId, 'PUT', '', { d6_verification: '实施后复测合格' })).status).toBe(200);
  const current = outcomeResponse(page, reportId);
  await sameDocumentLogin(page, approver);
  const displayed = await (await current).json();
  await expect(page.getByText(`材料版本: ${displayed.revision}`, { exact: false })).toBeVisible();
  await expect(page.getByText(`审核轮次: ${displayed.review_round_id}`, { exact: false })).toBeVisible();
  const closed = page.waitForResponse(r =>
    r.url().endsWith(`/capa/${reportId}/advance`) && r.request().method() === 'POST');
  await page.getByTestId('capa-outcome-approve').click();
  const approved = await closed;
  expect(approved.status()).toBe(200);
  expect(approved.request().postDataJSON()).toEqual({ target_state: 'D8_CLOSURE',
    expected_outcome_revision: displayed.revision, expected_review_round_id: displayed.review_round_id });
  await expect(page.getByTestId('capa-status')).toHaveText('D8_CLOSURE');
  await expect(page.getByTestId('capa-outcome-core')).toHaveAttribute('data-readonly', 'true');
  await denyTerminalWrites(page, reportId);
  const seen = await reload(page, reportId);
  expect((await business(page, reportId, 'PUT', '', { d8_closure: '合成结案后未审补充' })).status).toBe(200);
  const supplement = await reload(page, reportId);
  expect(supplement.revision).toBe(seen.revision);
  expect(supplement.core).toEqual(seen.core);
  expect(supplement.binding_status).toBe('verified');
  await expect(page.getByTestId('capa-outcome-core')).not.toContainText('合成结案后未审补充');
  await expect(page.locator('[data-e2e=capa-outcome-supplement]')).toContainText('合成结案后未审补充');
  const archived = page.waitForResponse(r => new URL(r.url()).pathname === `/api/capa/${reportId}/advance` && r.request().method() === 'POST');
  await page.locator('[data-e2e=capa-archive]').click();
  expect((await archived).status()).toBe(200);
  await expect(page.getByTestId('capa-status')).toHaveText('ARCHIVED');
  await expect(page.getByTestId('capa-outcome-core')).toHaveAttribute('data-readonly', 'true');
  const before = await command(page, 'snapshot');
  expect((await business(page, reportId, 'PUT', '', { d8_closure: 'forbidden' })).status).toBe(400);
  expect((await business(page, reportId, 'PUT', '', { d6_verification: 'forbidden' })).status).toBe(409);
  expect(await command(page, 'snapshot')).toEqual(before);
  await expect(page.locator('[data-e2e=capa-outcome-supplement-edit]')).toHaveCount(0);
});
