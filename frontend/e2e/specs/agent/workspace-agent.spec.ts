import { expect, test } from '@playwright/test';

const employee: {
  username: string;
  password: string;
  existing_no: string;
  draft_title: string;
  draft_no: string;
} = JSON.parse(process.env.AGENT_BROWSER_LOGIN!);

test('employee queries related PFMEAs and confirms one draft through Pi', async ({ page, context }, testInfo) => {
  const allowedOrigins = new Set([
    new URL(process.env.AGENT_BACKEND_URL!).origin,
    new URL(process.env.AGENT_BROWSER_URL!).origin,
  ]);
  await context.route('**/*', route => {
    const url = route.request().url();
    return url.startsWith('data:') || allowedOrigins.has(new URL(url).origin) ? route.continue() : route.abort();
  });
  await context.addInitScript(tenant => {
    localStorage.setItem('tenant_slug', tenant);
    localStorage.setItem('openqms_locale', 'zh-CN');
  }, process.env.AGENT_BROWSER_TENANT!);
  await page.goto('/login');
  await page.locator('#username').fill(employee.username);
  await page.locator('#password').fill(employee.password);
  await page.locator('button[type=submit]').click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`/capa/${process.env.AGENT_BROWSER_REPORT}`);

  await expect(page.getByRole('button', { name: '以本报告创建任务', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '工作区助手', exact: true }).click();
  const drawer = page.getByRole('dialog', { name: '工作区助手', exact: true });
  const composer = drawer.getByRole('textbox', { name: '向 Pi 提问', exact: true });
  const send = drawer.getByRole('button', { name: '发送', exact: true });
  await composer.fill('帮我查一下当前 8D 同产品线有哪些 PFMEA？');
  await send.click();

  const list = drawer.getByRole('region', { name: '同产品线 PFMEA', exact: true });
  const existing = list.getByRole('link', { name: employee.existing_no });
  await expect(existing).toHaveAttribute('href', /^\/fmea\/[0-9a-f-]{36}$/, { timeout: 30_000 });
  await existing.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('workspace-desktop.png') });

  await page.setViewportSize({ width: 390, height: 780 });
  await expect.poll(() => drawer.evaluate(element => {
    const { left, right } = element.getBoundingClientRect();
    return left >= 0 && right <= window.innerWidth;
  })).toBe(true);
  await expect(composer).toBeInViewport();
  await expect(send).toBeInViewport();
  await composer.fill(`为这条线创建 PFMEA 草稿，标题「${employee.draft_title}」，单号 ${employee.draft_no}`);
  await send.click();

  const preview = drawer.getByRole('region', { name: 'PFMEA 草稿预览', exact: true });
  await expect(preview.getByText(employee.draft_title, { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(preview.getByText(employee.draft_no, { exact: true })).toBeVisible();
  await expect(preview.getByText('待确认', { exact: true })).toBeVisible();
  const confirm = preview.getByRole('button', { name: '确认创建', exact: true });
  await expect(confirm).toBeEnabled();
  await preview.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('workspace-390px.png') });

  const confirmation = page.waitForResponse(response =>
    /^\/api\/agent\/workspace\/actions\/[^/]+\/confirm$/.test(new URL(response.url()).pathname)
      && response.request().method() === 'POST');
  await confirm.click();
  const confirmed = await confirmation;
  expect(confirmed.status()).toBe(200);
  const receipt = await confirmed.json();
  expect(receipt).toMatchObject({
    status: 'applied',
    draft: { document_no: employee.draft_no, title: employee.draft_title },
  });
  await expect(preview.getByRole('status')).toContainText('已创建草稿');
  await expect(preview.getByRole('link', { name: `${employee.draft_no} · ${employee.draft_title}` }))
    .toHaveAttribute('href', `/fmea/${receipt.draft.id}`);

  const retry = await page.evaluate(async ({ url, body }) => {
    const token = localStorage.getItem('access_token');
    const tenant = localStorage.getItem('tenant_slug');
    if (!token || !tenant) throw new Error('Employee session unavailable');
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Tenant-ID': tenant,
        'Content-Type': 'application/json',
      },
      body,
    });
    return { status: response.status, receipt: await response.json() };
  }, { url: confirmed.url(), body: confirmed.request().postData() });
  expect(retry.status).toBe(200);
  expect(retry.receipt).toEqual(receipt);
});
