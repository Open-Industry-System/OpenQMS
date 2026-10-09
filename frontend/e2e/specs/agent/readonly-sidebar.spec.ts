import { test, expect, type Page, type Locator } from '@playwright/test';

const scenario = process.env.AGENT_BROWSER_SCENARIO!;
const report = process.env.AGENT_BROWSER_REPORT!;
const reportB = process.env.AGENT_BROWSER_REPORT_B!;
const taskId = process.env.AGENT_BROWSER_TASK!;
const backend = process.env.AGENT_BACKEND_URL!;
const nonce = process.env.AGENT_HARNESS_NONCE!;
const login = JSON.parse(process.env.AGENT_BROWSER_LOGIN!);

async function fixture(page: Page, action: string, body: object = {}) {
  const response = await page.request.post(`${backend}/__agent_acceptance/${action}`, {
    headers: { 'X-Acceptance-Nonce': nonce, 'X-Tenant-ID': process.env.AGENT_BROWSER_TENANT! }, data: body,
  });
  expect(response.ok(), `owned fixture ${action}`).toBeTruthy();
  return response.json();
}
async function open(page: Page) {
  await page.getByRole('button', { name: 'Agent 任务', exact: true }).click();
  await expect(page.getByRole('combobox', { name: '选择任务' })).toBeVisible();
}
async function selectA(page: Page) {
  await open(page);
  const chooser = page.getByRole('combobox', { name: '选择任务' });
  await expect(chooser.locator(`option[value="${taskId}"]`)).toBeAttached();
  await chooser.selectOption(taskId);
  await expect(page.getByRole('link', { name: `目标报告 ${report}` })).toBeVisible();
}
async function sequences(page: Page) {
  return page.getByTestId('agent-activity-window').locator(':scope > li').evaluateAll(
    rows => rows.map(row => Number(row.getAttribute('data-sequence'))));
}
const range = (first: number, last: number) => Array.from({ length: last - first + 1 }, (_, i) => i + first);

async function sourceGeometry(row: Locator, activity: Locator, sources: { receipt_id: string; projection_digest: string }[], label: string) {
  expect(sources).toHaveLength(2);
  for (const source of sources) {
    expect(source.projection_digest).toMatch(/^[0-9a-f]{64}$/);
    const sourceRow = row.getByText(`读取凭据 ${source.receipt_id}`, { exact: true }).locator('..');
    const digest = sourceRow.getByText(`摘要 ${source.projection_digest}`, { exact: true });
    await expect(digest).toBeVisible();
    const size = await digest.evaluate(element => ({ client: element.clientWidth, scroll: element.scrollWidth }));
    console.log(`${label} digest geometry ${JSON.stringify(size)}`);
    expect.soft(size.scroll, `${label} full source digest fits its available width`).toBeLessThanOrEqual(size.client);
  }
  const size = await activity.evaluate(element => ({ client: element.clientWidth, scroll: element.scrollWidth }));
  console.log(`${label} activity geometry ${JSON.stringify(size)}`);
  expect.soft(size.scroll, `${label} activity fits its available width`).toBeLessThanOrEqual(size.client);
}

// One parametrized pytest invocation = one actual browser test; no skipped
// scenarios, shared global setup or mocked product responses.
test(`actual readonly sidebar ${scenario}`, async ({ page, context }) => {
  const origins = new Set([new URL(backend).origin, new URL(process.env.AGENT_BROWSER_URL!).origin]);
  await context.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith('data:') || origins.has(new URL(url).origin)) return route.continue();
    return route.abort(); // no external sites, model or provider calls
  });
  await context.addInitScript(({ token, refresh, tenant }) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('refresh_token', refresh);
    localStorage.setItem('tenant_slug', tenant);
    localStorage.setItem('i18nextLng', 'zh');
  }, { token: login.access_token, refresh: login.refresh_token, tenant: process.env.AGENT_BROWSER_TENANT! });
  const authMe = page.waitForResponse(r => r.url().includes('/api/auth/me') && r.status() === 200);
  await page.goto(`/capa/${report}`);
  await authMe; // real frontend AuthMe + current permissions after actual login
  await selectA(page);
  const activity = page.getByRole('region', { name: '任务活动' });

  if (scenario.startsWith('race-')) {
    const winner = scenario.slice('race-'.length);
    const outcome = await fixture(page, 'race', { winner });
    expect(outcome.task_status).toBe(winner === 'append' ? 'ready' : 'completed');
    await expect(activity.getByText(`任务状态 ${outcome.task_status}`, { exact: true })).toBeVisible();
    if (winner === 'append') {
      await expect(activity.getByText('real racing new instruction', { exact: true })).toBeVisible();
      await expect(activity.getByText('排队中', { exact: true })).toBeVisible();
      await expect(activity.getByText(/当前运行 .* · active/)).toBeVisible();
    } else {
      await expect(activity.getByText('real racing new instruction', { exact: true })).toHaveCount(0);
      await expect(activity.getByText(/当前运行 .* · completed/)).toBeVisible();
    }
    return;
  }
  if (scenario.startsWith('authority-')) {
    await expect(page.getByRole('heading', { name: '只读分析结果' })).toBeVisible();
    await expect(activity.getByText(/D4 verification metadata/)).toBeVisible();
    const denied = page.waitForResponse(r => r.url().includes(`/api/agent/tasks/${taskId}/activity`)
      && [401,403,404].includes(r.status()));
    await fixture(page, 'withdraw', { change: scenario.slice('authority-'.length) });
    await denied;
    await expect(activity).toHaveCount(0);
    await expect(page.getByTestId('agent-activity-window')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '只读分析结果' })).toHaveCount(0);
    await expect(page.getByText(/D4 verification metadata/)).toHaveCount(0);
    return;
  }
  if (scenario === 'window') {
    await expect.poll(() => sequences(page)).toEqual(range(1,100));
    let secondReached!: () => void;
    const secondPending = new Promise<void>(resolve => { secondReached = resolve; });
    let releaseSecond!: () => void;
    const released = new Promise<void>(resolve => { releaseSecond = resolve; });
    const observed: { watermark: number; sequences: number[]; history: boolean }[] = [];
    let cycle = 0;
    await fixture(page, 'seed', { target: 110 });
    await page.route(`**/api/agent/tasks/${taskId}/activity?**`, async route => {
      const url = new URL(route.request().url());
      const history = url.searchParams.has('before_sequence');
      const response = await route.fetch(); // actual authenticated backend read
      const body = await response.json();
      observed.push({ watermark: body.window_end_sequence, sequences: body.items.map((i: {sequence:number}) => i.sequence), history });
      if (!history && cycle === 0) {
        cycle = 1;
        expect(body.window_end_sequence).toBe(110);
        expect(body.items.map((i: {sequence:number}) => i.sequence)).toEqual(range(61,110));
        await fixture(page, 'seed', { target: 111 }); // interpage actual commit
      } else if (history && cycle === 1) {
        expect(url.searchParams.get('window_end_sequence')).toBe('110');
        expect(body.window_end_sequence).toBe(110);
        expect(body.items.map((i: {sequence:number}) => i.sequence)).toEqual(range(11,60));
        secondReached();
        await released;
        cycle = 2;
      }
      await route.fulfill({ response });
    });
    await secondPending;
    await expect.poll(() => sequences(page)).toEqual(range(1,100)); // no partial latest publication
    releaseSecond();
    await expect.poll(() => sequences(page)).toEqual(range(11,110));
    expect((await sequences(page)).filter(n => n>=51 && n<=60)).toEqual(range(51,60));
    await page.unroute(`**/api/agent/tasks/${taskId}/activity?**`);
    let failedSecond!: () => void;
    const failed = new Promise<void>(resolve => { failedSecond = resolve; });
    let failureTime = 0;
    let retriedLatestTime = 0;
    let abortOnce = true;
    await page.route(`**/api/agent/tasks/${taskId}/activity?**`, async route => {
      const url = new URL(route.request().url());
      const response = await route.fetch();
      if (url.searchParams.has('before_sequence') && abortOnce) {
        abortOnce = false;
        failureTime = Date.now();
        await route.abort('failed'); // fail only after a real successful second read
        failedSecond();
      } else {
        if (!url.searchParams.has('before_sequence') && failureTime) retriedLatestTime = Date.now();
        await route.fulfill({ response });
      }
    });
    await failed;
    await expect(page.getByText('连接中断，重试中')).toBeVisible();
    await expect(page.getByTestId('agent-activity-window')).toHaveCount(0); // old body withdrawn too
    await expect.poll(() => sequences(page), { timeout: 10000 }).toEqual(range(12,111));
    expect(retriedLatestTime - failureTime).toBeGreaterThanOrEqual(4900);
    expect(observed.some(r => r.history && r.watermark===110)).toBeTruthy();
    return;
  }

  // Closing the UI does not stop the actual independent OS plugin process.
  await fixture(page, 'start', { hold: true, checkpoint: true });
  await page.getByRole('button', { name: '关闭任务侧栏' }).click();
  await expect(page.getByTestId('agent-activity-window')).toHaveCount(0);
  await fixture(page, 'release');
  const first = await fixture(page, 'join');
  expect(first.code).toBe(0);
  expect(first.contexts).toEqual([200,200]);
  await open(page);
  await expect(page.getByRole('heading', { name: '只读分析结果' })).toBeVisible();
  // Lifespan-off recommendation features are outside this acceptance scope.
  // Wait for real background notices to expire; never fabricate/hide responses.
  await expect(page.locator('.ant-message-notice')).toHaveCount(0, { timeout: 10000 });
  // Measure real source values returned by the authenticated product APIs.
  const headers = { Authorization: `Bearer ${login.access_token}`, 'X-Tenant-ID': process.env.AGENT_BROWSER_TENANT! };
  const resultResponse = await page.request.get(`${backend}/api/agent/tasks/${taskId}/results/${first.output.result_id}`, { headers });
  const checkpointResponse = await page.request.get(`${backend}/api/agent/tasks/${taskId}/checkpoints/${first.output.checkpoint_id}`, { headers });
  expect(resultResponse.status()).toBe(200);
  expect(checkpointResponse.status()).toBe(200);
  const resultRow = activity.locator('li[data-sequence]').filter({ has: page.getByRole('heading', { name: '只读分析结果', exact: true }) });
  const checkpointRow = activity.locator('li[data-sequence]').filter({ has: page.getByRole('heading', { name: `只读检查点 ${first.output.checkpoint_id}`, exact: true }) });
  await sourceGeometry(resultRow, activity, (await resultResponse.json()).sources, 'result');
  await sourceGeometry(checkpointRow, activity, (await checkpointResponse.json()).sources, 'checkpoint');
  await page.getByRole('heading', { name: '只读分析结果' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: '/tmp/openqms_r3_sidebar_verified.png' });
  await page.getByRole('heading', { name: `只读检查点 ${first.output.checkpoint_id}` }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: '/tmp/openqms_r3_sidebar_checkpoint_verified.png' });
  await page.getByRole('link', { name: `目标报告 ${report}` }).click();
  await expect(page).toHaveURL(new RegExp(`/capa/${report}$`));
  await page.getByRole('button', { name: '关闭任务侧栏' }).click();
  // Real SPA navigation and real factory/product-line selectors retain Task A.
  await page.locator('[data-e2e="factory-switcher"]').click();
  await page.locator('.ant-select-item-option').filter({ hasText: '浏览器第二工厂' }).click();
  await page.locator('.ant-layout-header .ant-select').nth(1).click();
  await page.locator('.ant-select-item-option').filter({ hasText: '浏览器第二产品线' }).click();
  await page.locator('[data-e2e="menu-capa"]').click();
  await page.locator('[data-e2e="row-8D-BROWSER-B"]').getByRole('button').click();
  await expect(page).toHaveURL(new RegExp(`/capa/${reportB}$`));
  await open(page);
  await expect(page.getByRole('combobox', { name: '选择任务' })).toHaveValue(taskId);
  await expect(page.getByRole('link', { name: `目标报告 ${report}` })).toBeVisible();
  expect((await fixture(page, 'state')).tasks).toHaveLength(1);
  await page.getByRole('button', { name: '关闭任务侧栏' }).click();
  await page.getByRole('button', { name: '以本报告创建任务' }).click();
  await page.getByRole('textbox', { name: '初始指令' }).fill('显式为报告 B 创建任务');
  const create = page.waitForResponse(r => r.request().method()==='POST' && new URL(r.url()).pathname==='/api/agent/tasks');
  await page.getByRole('button', { name: '创建任务', exact: true }).click();
  const created = await (await create).json();
  expect(created.target_capa_id).toBe(reportB);
  expect(created.task_id).not.toBe(taskId);
  expect((await fixture(page, 'state')).tasks).toHaveLength(2);
  await expect(activity.getByText('任务状态 ready', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '取消任务' }).click();
  await expect(activity.getByText('任务状态 cancelled', { exact: true })).toBeVisible();
  await expect(activity.getByText('排队中：终止时未确认接收（不代表已处理）', { exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: '选择任务' }).selectOption(taskId);
  await expect(page.getByRole('button', { name: '暂停', exact: true })).toBeEnabled();
  // Lost response retry uses the exact original body/key and server single op.
  const controlBodies: string[] = [];
  let lose = true;
  await page.route(`**/api/agent/tasks/${taskId}/control`, async route => {
    controlBodies.push(route.request().postData()!);
    const response = await route.fetch();
    if (lose) { lose = false; await route.abort('failed'); }
    else await route.fulfill({ response });
  });
  await page.getByRole('button', { name: '暂停', exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  await expect(page.getByRole('button', { name: '重试原控制操作' })).toBeVisible();
  await page.getByRole('button', { name: '重试原控制操作' }).click();
  await expect(activity.getByText('任务状态 paused', { exact: true })).toBeVisible();
  expect(controlBodies).toHaveLength(2);
  expect(controlBodies[1]).toBe(controlBodies[0]);
  expect((await fixture(page, 'state')).controls).toBe(1);
  expect((await fixture(page, 'state')).pause_audits).toBe(1);
  await page.unroute(`**/api/agent/tasks/${taskId}/control`);
  await page.getByRole('textbox', { name: '追加指令' }).fill('暂停期间追加的新指令');
  await page.getByRole('button', { name: '发送指令' }).click();
  await expect(activity.getByText('暂停期间追加的新指令', { exact: true })).toBeVisible();
  await expect(activity.getByText('排队中', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '继续', exact: true }).click();
  await expect(activity.getByText('任务状态 ready', { exact: true })).toBeVisible();
  await fixture(page, 'start', { hold: true });
  await expect(activity.getByText(`当前运行 ${first.output.run_id} · active`, { exact: true })).toBeVisible();
  // Pause after real first report receipt, before its dependent metadata query.
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(activity.getByText('任务状态 paused', { exact: true })).toBeVisible();
  await fixture(page, 'release');
  const interrupted = await fixture(page, 'join');
  expect(interrupted.code).toBe(1);
  expect(interrupted.safe_failure).toBeTruthy();
  expect(interrupted.contexts).toEqual([200,401]);
  expect(interrupted.history).toEqual([[1,2]]);
  await page.getByRole('button', { name: '继续', exact: true }).click();
  await expect(activity.getByText('任务状态 ready', { exact: true })).toBeVisible();
  await fixture(page, 'start', { checkpoint: true });
  const resumed = await fixture(page, 'join');
  expect(resumed.code).toBe(0);
  expect(resumed.history).toEqual([[1,2,3]]);
  expect(resumed.output.run_id).toBe(first.output.run_id);
  await expect(activity.getByText(`只读检查点 ${resumed.output.checkpoint_id}`, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(activity.getByText('任务状态 paused', { exact: true })).toBeVisible();
  await fixture(page, 'edit');
  await page.getByRole('textbox', { name: '追加指令' }).fill('检查点后新增指令');
  await page.getByRole('button', { name: '发送指令' }).click();
  const latestCheckpoint = activity.locator('li[data-sequence]').filter({ hasText: `只读检查点 ${resumed.output.checkpoint_id}` });
  await latestCheckpoint.getByRole('button', { name: '从此检查点重启' }).click();
  await expect(activity.getByText(/当前运行 .* · pending/)).toBeVisible();
  await fixture(page, 'start', { finish: true });
  const restarted = await fixture(page, 'join');
  expect(restarted.code).toBe(0);
  expect(restarted.output.run_id).not.toBe(first.output.run_id);
  expect(restarted.history).toEqual([[1,2,3]]);
  await expect(activity.getByText('任务状态 completed', { exact: true })).toBeVisible();
  await expect(activity.getByText(/1 failed/)).toBeVisible();
});
