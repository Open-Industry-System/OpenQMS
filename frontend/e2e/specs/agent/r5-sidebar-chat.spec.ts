import { expect, test } from '@playwright/test';

const employee: {
  username: string;
  password: string;
  installation: string;
  model: string;
  proposal: string;
  questions: [string, string];
  replies: [string, string];
} = JSON.parse(process.env.AGENT_BROWSER_LOGIN!);

test('employee starts a real R5 task and continues its dialogue on desktop and narrow screens', async ({ page, context }, testInfo) => {
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
  const reportPath = `/capa/${process.env.AGENT_BROWSER_REPORT}`;
  await page.goto(reportPath);

  await page.getByRole('button', { name: '以本报告创建任务', exact: true }).click();
  const drawer = page.getByRole('dialog', { name: 'Agent 任务' });
  await drawer.getByLabel('插件安装', { exact: true }).selectOption(employee.installation);
  await drawer.getByLabel('新任务模型', { exact: true }).selectOption(employee.model);
  const creation = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/agent/tasks' && response.request().method() === 'POST');
  await drawer.getByRole('button', { name: '用 synthetic A · actual-agent 开始新任务（仅根据当前根因）', exact: true }).click();
  const created = await creation;
  expect(created.status()).toBe(201);
  const task = await created.json();
  expect(task.model_deployment.deployment_id).toBe(employee.model);
  expect(task.status).toBe('ready');

  const launch = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/agent/tasks/${task.task_id}/launch` && response.request().method() === 'POST');
  await drawer.getByRole('button', { name: '启动模型任务', exact: true }).click();
  const conversation = drawer.getByRole('region', { name: '任务对话', exact: true });
  const composer = drawer.getByRole('textbox', { name: '追加指令', exact: true });
  const send = drawer.getByRole('button', { name: '补充给 synthetic A', exact: true });
  const postedReply = () => page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/agent/tasks/${task.task_id}/messages` && response.request().method() === 'POST');
  const noExtraSources = '继续（无额外资料）';
  await expect(conversation).toBeVisible();
  await expect(conversation.getByText(employee.questions[0], { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(drawer.getByLabel('选择处理范围检查点', { exact: true })).toBeHidden();
  await expect(composer).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath('sidebar-desktop.png') });

  await drawer.getByRole('button', { name: '任务详情', exact: true }).click();
  await drawer.getByText('建议与检查点', { exact: true }).click();
  const continueTask = drawer.getByRole('button', { name: noExtraSources, exact: true });
  await expect(continueTask).toBeEnabled();
  const firstReply = postedReply();
  await continueTask.click();
  const firstAccepted = await firstReply;
  expect(firstAccepted.status()).toBe(202);
  expect(firstAccepted.request().postDataJSON().content).toBe(employee.replies[0]);
  await drawer.getByRole('button', { name: '返回对话', exact: true }).click();
  await expect(conversation.getByText(noExtraSources, { exact: true })).toBeVisible();
  await expect(conversation.getByText(employee.questions[1], { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(conversation.getByText(employee.proposal, { exact: true })).toBeVisible();
  await expect(conversation.getByRole('link', { name: '在 8D 报告中审阅建议' })).toHaveAttribute('href', reportPath);

  const reopened = await context.newPage();
  try {
    await reopened.goto(reportPath);
    await reopened.getByRole('button', { name: 'Agent 任务', exact: true }).click();
    await reopened.getByLabel('选择任务', { exact: true }).selectOption(task.task_id);
    const history = reopened.getByRole('region', { name: '任务对话', exact: true });
    await expect(history.getByText(employee.questions[0], { exact: true })).toBeVisible();
    await expect(history.getByText(employee.questions[1], { exact: true })).toBeVisible();
  } finally {
    await reopened.close();
  }

  await page.bringToFront();
  await page.setViewportSize({ width: 390, height: 780 });
  await expect.poll(() => drawer.evaluate(element => {
    const { left, right } = element.getBoundingClientRect();
    return left >= 0 && right <= window.innerWidth;
  })).toBe(true);
  const chooser = drawer.getByRole('combobox', { name: '选择任务', exact: true });
  await expect.poll(() => chooser.evaluate(element => {
    const panel = element.closest('[role="dialog"]');
    if (!panel) return false;
    const select = element.getBoundingClientRect();
    const bounds = panel.getBoundingClientRect();
    return select.left >= bounds.left && select.right <= bounds.right
      && select.top >= bounds.top && select.bottom <= bounds.bottom;
  })).toBe(true);
  await expect(composer).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath('sidebar-narrow.png') });
  await composer.fill(employee.replies[1]);
  await expect(send).toBeEnabled();
  const secondReply = postedReply();
  await send.click();
  const secondAccepted = await secondReply;
  expect(secondAccepted.status()).toBe(202);
  expect(secondAccepted.request().postDataJSON().content).toBe(employee.replies[1]);
  await expect(conversation.getByText(employee.replies[1], { exact: true })).toBeVisible();
  const launched = await launch;
  expect(launched.status()).toBe(200);
  expect((await launched.json()).status).toBe('executed');

  await page.reload();
  await page.getByRole('button', { name: 'Agent 任务', exact: true }).click();
  await drawer.getByLabel('选择任务', { exact: true }).selectOption(task.task_id);
  await expect(conversation.getByText(employee.replies[1], { exact: true })).toBeVisible();
  await expect(conversation.getByText(noExtraSources, { exact: true })).toBeVisible();
  await expect(conversation.getByText(employee.proposal, { exact: true })).toBeVisible();
});
