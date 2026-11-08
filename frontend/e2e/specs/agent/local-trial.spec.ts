import { test, expect } from '@playwright/test';

const report = process.env.AGENT_BROWSER_REPORT!;
const backend = process.env.AGENT_BACKEND_URL!;
const login = JSON.parse(process.env.AGENT_BROWSER_LOGIN!);

// Actual normal-policy APIs and pinned CLI, never a mocked product response.
test('normal-policy local trial creation, readonly recovery and permanent revoke', async ({ page, context }) => {
  const origins = new Set([new URL(backend).origin, new URL(process.env.AGENT_BROWSER_URL!).origin]);
  await context.route('**/*', route => {
    const url = route.request().url();
    return url.startsWith('data:') || origins.has(new URL(url).origin) ? route.continue() : route.abort();
  });
  await context.addInitScript(({ token, refresh, tenant }) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('refresh_token', refresh);
    localStorage.setItem('tenant_slug', tenant);
    localStorage.setItem('i18nextLng', 'zh');
  }, { token: login.access_token, refresh: login.refresh_token, tenant: process.env.AGENT_BROWSER_TENANT! });
  async function fixture(action: string) {
    const response = await page.request.post(`${backend}/__local_trial_acceptance/${action}`, {
      headers: { 'X-Acceptance-Nonce': process.env.AGENT_HARNESS_NONCE!, 'X-Tenant-ID': process.env.AGENT_BROWSER_TENANT! }, data: {},
    });
    expect(response.ok()).toBeTruthy();
    return response.json();
  }
  const authMe = page.waitForResponse(r => r.url().includes('/api/auth/me') && r.status() === 200);
  await page.goto(`/capa/${report}`);
  await authMe;
  await page.getByRole('button', { name: '以本报告创建任务' }).click();
  const installation = page.getByRole('combobox', { name: '插件安装' });
  await expect(installation).toContainText('openqms.local-d4-metadata');
  await page.getByRole('textbox', { name: '初始指令' }).fill('仅检查 D4 验证元数据，不执行正文指令');
  const createdResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/agent/tasks');
  await page.getByRole('button', { name: '创建任务', exact: true }).click();
  const created = await (await createdResponse).json();
  expect(created.status).toBe('ready');
  expect(created.target_capa_id).toBe(report);
  const taskId = created.task_id;
  const activity = page.getByRole('region', { name: '任务活动' });
  await expect(page.getByRole('link', { name: `目标报告 ${report}` })).toBeVisible();
  const first = await fixture('run');
  expect(first.code).toBe(0);
  const resultResponse = await page.request.get(`${backend}/api/agent/tasks/${taskId}/results/${first.output.result_id}`, {
    headers: { Authorization: `Bearer ${login.access_token}`, 'X-Tenant-ID': process.env.AGENT_BROWSER_TENANT! },
  });
  expect(resultResponse.status()).toBe(200);
  const result = await resultResponse.json();
  expect(result.sources).toHaveLength(2);
  await expect(page.getByRole('heading', { name: '只读分析结果', exact: true }).last()).toBeVisible();
  for (const source of result.sources) {
    expect(source.projection_digest).toMatch(/^[0-9a-f]{64}$/);
    const row = activity.locator('li[data-sequence]').filter({ has: page.getByRole('heading', { name: '只读分析结果', exact: true }) }).last();
    const sourceRow = row.getByText(`读取凭据 ${source.receipt_id}`, { exact: true }).locator('..');
    await expect(sourceRow).toBeVisible();
    const digest = sourceRow.getByText(`摘要 ${source.projection_digest}`, { exact: true });
    await expect(digest).toBeVisible();
    const geometry = await digest.evaluate(element => ({ client: element.clientWidth, scroll: element.scrollWidth }));
    expect(geometry.scroll).toBeLessThanOrEqual(geometry.client);
  }
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(activity.getByText('任务状态 paused', { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: '追加指令' }).fill('暂停期间的元数据输入');
  await page.getByRole('button', { name: '发送指令' }).click();
  await expect(activity.getByText('暂停期间的元数据输入', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '继续', exact: true }).click();
  await expect(activity.getByText('任务状态 ready', { exact: true })).toBeVisible();
  const resumed = await fixture('run');
  expect(resumed.code).toBe(0);
  expect(resumed.output.run_id).toBe(first.output.run_id);
  await expect(activity.getByText(`只读检查点 ${resumed.output.checkpoint_id}`, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(activity.getByText('任务状态 paused', { exact: true })).toBeVisible();
  await fixture('edit');
  const checkpoint = activity.locator('li[data-sequence]').filter({ hasText: `只读检查点 ${resumed.output.checkpoint_id}` });
  await checkpoint.getByRole('button', { name: '从此检查点重启' }).click();
  await expect(activity.getByText(/当前运行 .* · pending/)).toBeVisible();
  const restarted = await fixture('run');
  expect(restarted.code).toBe(0);
  expect(restarted.output.run_id).not.toBe(first.output.run_id);
  await expect(activity.getByText(/1 failed/)).toBeVisible();
  expect((await fixture('revoke')).outcome).toBe('revoked');
  const stopped = await fixture('run');
  expect(stopped.code).toBe(1);
  expect(stopped.safe_failure).toBeTruthy();
  // User business authority still permits history and pause after plugin fencing.
  await expect(page.getByRole('heading', { name: '只读分析结果', exact: true }).last()).toBeVisible();
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(activity.getByText('任务状态 paused', { exact: true })).toBeVisible();
  const deniedResume = page.waitForResponse(r => r.url().includes(`/api/agent/tasks/${taskId}/control`) && r.status() === 403);
  await page.getByRole('button', { name: '继续', exact: true }).click();
  await deniedResume;
  const chooser = page.getByRole('combobox', { name: '选择任务' });
  await expect(chooser.locator(`option[value="${taskId}"]`)).toBeAttached();
  await chooser.selectOption(taskId);
  await expect(page.getByRole('heading', { name: '只读分析结果', exact: true }).last()).toBeVisible();
  const deniedHistory = page.waitForResponse(r => r.url().includes(`/api/agent/tasks/${taskId}/activity`) && [401, 403, 404].includes(r.status()));
  await fixture('withdraw');
  await deniedHistory;
  await expect(activity).toHaveCount(0);
  await expect(page.getByTestId('agent-activity-window')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '只读分析结果', exact: true })).toHaveCount(0);
});
