import { isDisabledAgentProbe, isDisabledAgentProbeConsole, unexpectedCharacteristicFailures, type HttpFailure } from "../../helpers/characteristic-diagnostics";
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

// Test-only account manifest, produced by the guarded bootstrap, not app.seed.
const tag = process.env.CHARACTERISTIC_RUN_TAG!;
const owned = JSON.parse(readFileSync(`e2e/.storage-state/characteristic-owned-${tag}.json`, 'utf8'));
const evidencePath = `e2e/.storage-state/characteristic-${tag}-${process.pid}-evidence.json`;
const evidence: Record<string, unknown> = { run: owned.run, factory: owned.factory_id, documents: [], screenshots: [], preconditions: 'API-created draft + declared complete simulated structure/failure chain; all five characteristics entered through real UI; wizard completion via UI; approvals via real API with distinct actors' };
const prefix = `E2E-T11-${owned.run}-${Date.now()}`;
const apiURL = process.env.CHARACTERISTIC_API_URL!;
const uiURL = process.env.CHARACTERISTIC_UI_URL!;
let editor: APIRequestContext;
let approver: APIRequestContext;
const docs: { kind: string; id: string }[] = [];

let workerPaused = false;
function workerSignal(signal: 'SIGSTOP' | 'SIGCONT') {
  const pid = Number(process.env.CHARACTERISTIC_WORKER_PID);
  expect(Number.isInteger(pid) && pid > 1).toBe(true);
  const command = execFileSync('/bin/ps', ['-p', String(pid), '-o', 'command='], { encoding: 'utf8' });
  expect(command).toContain('-m app.services.cp_sync_worker');
  const cwd = execFileSync('/usr/sbin/lsof', ['-a', '-p', String(pid), '-d', 'cwd', '-Fn'], { encoding: 'utf8' });
  expect(cwd).toContain(`n${resolve('../backend')}`);
  process.kill(pid, signal);
  workerPaused = signal === 'SIGSTOP';
}
async function delivered(fmeaId: string, versionId: string) {
  await expect.poll(() => execFileSync(process.env.CHARACTERISTIC_PYTHON!, ['-c', `
import os, sys, uuid
sys.path.insert(0, sys.argv[3])
from tests.e2e.characteristic_bootstrap import require_owned_database
url = require_owned_database(os.environ)
import psycopg
with psycopg.connect(url.replace('postgresql+asyncpg://', 'postgresql://')) as connection:
    connection.execute('SET TRANSACTION READ ONLY')
    row = connection.execute('SELECT status FROM cp_sync_outbox WHERE fmea_id=%s AND fmea_version_id=%s', (uuid.UUID(sys.argv[1]), uuid.UUID(sys.argv[2]))).fetchone()
    print(row[0] if row else 'missing')
`, fmeaId, versionId, resolve('../backend')], { encoding: 'utf8' }).trim(), { timeout: 15_000 }).toBe('completed');
}

async function json(response: Awaited<ReturnType<APIRequestContext['get']>>) {
  expect(response.ok(), `${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}
async function shot(page: Page, name: string) {
  const path = `e2e/.storage-state/${owned.run}-${tag}-${name}.png`;
  expect(existsSync(path), "Do not overwrite historical screenshots").toBe(false);
  await page.screenshot({ path, fullPage: true });
  (evidence.screenshots as string[]).push(path);
}
function graph(dfmea = false) {
  const node = (id: string, type: string, name: string, extra = {}) => ({ id, type, name, severity: 0, occurrence: 0, detection: 0, ...extra });
  const edge = (source: string, target: string, type: string) => ({ source, target, type });
  return {
    nodes: [
      node('item', dfmea ? 'System' : 'ProcessItem', 'SIMULATED DC-DC'),
      node('step', dfmea ? 'Subsystem' : 'ProcessStep', 'SMT贴装', { process_number: 'OP10' }),
      node('we', dfmea ? 'Component' : 'ProcessWorkElement', '贴片机', { classification: 'Machine' }),
      node('if', 'ProcessItemFunction', '提供电源'),
      node('sf', 'ProcessStepFunction', '精确贴装', { specification: 'legacy reference, not a characteristic' }),
      node('wf', 'ProcessWorkElementFunction', '稳定贴装动作'),
      node('fm', 'FailureMode', '位置偏移'),
      node('fe', 'FailureEffect', '装配不良', { severity: 2, severity_plant: 2, severity_customer: 2, severity_user: 2 }),
      node('fc', 'FailureCause', '定位磨损', { occurrence: 2 }),
      node('pc', 'PreventionControl', '定期维护'),
      node('dc', 'DetectionControl', 'AOI位置检测', { detection: 2 }),
    ],
    edges: [edge('item', 'step', 'HAS_PROCESS_STEP'), edge('step', 'we', 'HAS_WORK_ELEMENT'), edge('item', 'if', 'HAS_FUNCTION'), edge('step', 'sf', 'HAS_FUNCTION'), edge('we', 'wf', 'HAS_FUNCTION'), edge('if', 'sf', 'FUNCTION_MAPPED_TO'), edge('sf', 'wf', 'FUNCTION_MAPPED_TO'), edge('sf', 'fm', 'HAS_FAILURE_MODE'), edge('fm', 'fe', 'EFFECT_OF'), edge('fc', 'fm', 'CAUSE_OF'), edge('fc', 'pc', 'PREVENTED_BY'), edge('fc', 'dc', 'DETECTED_BY')],
    wizardScope: { team: 'SIMULATED Task11', task: 'Manual characteristic acceptance', wizard_completed: false },
  };
}
async function draft(type: string, label = type) {
  const doc = await json(await editor.post('/api/fmea', { data: { title: `${prefix}-${label}`, document_no: `${prefix}-${label}`, fmea_type: type, product_line_code: owned.product_line } }));
  docs.push({ kind: 'fmea', id: doc.fmea_id });
  const updated = await json(await editor.put(`/api/fmea/${doc.fmea_id}`, { data: { lock_version: doc.lock_version, graph_data: graph(type === 'DFMEA') } }));
  expect(updated.status).toBe('draft');
  return updated;
}
async function login(page: Page) {
  // Prevent only optional AI recommendation traffic; never fulfill core business requests.
  await page.route('**/api/fmea/*/recommend', route => route.abort());
  // Reuse a genuine API-issued test session rather than hammering login limits.
  const session = JSON.parse(readFileSync(`e2e/.storage-state/${owned.run}-${tag}-editor-api.json`, 'utf8'));
  await page.addInitScript(token => localStorage.setItem('access_token', token), session.access_token);
  await page.goto('/dashboard');
  await expect(page).not.toHaveURL(/\/login/);

}
async function functionStep(page: Page, id: string, dfmea = false) {
  await page.goto(`/fmea/${dfmea ? 'wizard' : 'pfmea-wizard'}/${id}`);
  await page.getByText(dfmea ? '功能分析 (第三步)' : '功能分析', { exact: true }).first().click();
  await expect(page.getByRole('button', { name: '新增产品特性' }).first()).toBeVisible();
}
async function add(page: Page, kind: '产品' | '过程', name: string, specification: string, unit: string) {
  await page.getByRole('button', { name: `新增${kind}特性` }).first().click();
  await page.getByRole('textbox', { name: '特性名称', exact: true }).last().fill(name);
  await page.getByRole('textbox', { name: '规范／公差', exact: true }).last().fill(specification);
  await page.getByRole('textbox', { name: '单位', exact: true }).last().fill(unit);
  if (kind === '过程') {
    const related = page.getByRole('combobox', { name: '关联产品特性', exact: true }).last();
    await related.click();
    await page.getByText('元器件贴装偏移量', { exact: true }).last().click();
    await page.getByText('焊盘覆盖率', { exact: true }).last().click();
    await related.press('Escape');
  }
  await page.getByRole('button', { name: '确认特性' }).click();
}
async function save(page: Page, id: string) {
  const response = page.waitForResponse(r => r.url().endsWith(`/api/fmea/${id}`) && r.request().method() === 'PUT');
  await page.getByRole('button', { name: /存草稿/ }).click();
  await json(await response);
}
// Actual wizard navigation/completion, never a direct wizard_completed write.
async function completeDraftWizard(page: Page, id: string) {
  await functionStep(page, id);
  for (let step = 3; step <= 6; step++) {
    await page.getByRole("button", { name: "下一步", exact: true }).click();
  }
  await page.getByRole("button", { name: /完成/ }).click();
  await expect(page).toHaveURL(new RegExp(`/fmea/${id}$`));
}
async function approve(id: string) {
  await json(await editor.post(`/api/fmea/${id}/transition`, { data: { target_status: 'in_review' } }));
  const approved = await json(await approver.post(`/api/fmea/${id}/transition`, { data: { target_status: 'approved' } }));
  expect(approved.approved_by).toBe(owned.accounts.approver.id);
  const versions = await json(await editor.get(`/api/fmea/${id}/versions`));
  const version = versions.items.find((v: any) => v.change_type === 'approve');
  expect(version).toBeTruthy();
  const verify = await json(await editor.post(`/api/fmea/${id}/versions/${version.major_no}/${version.minor_no}/verify`));
  expect(verify.is_valid).toBe(true);
  evidence[`verify-${version.major_no}`] = verify;
  return version;
}

test.beforeEach(async ({ page }, info) => {
  const observed = {
    test: info.title, pageErrors: [] as string[], consoleErrors: [] as string[],
    consoleErrorDetails: [] as { message: string; url: string }[],
    httpFailures: [] as HttpFailure[], unavailableAgentProbes: [] as HttpFailure[],
  };
  (evidence.browserDiagnostics ??= [] as unknown[]);
  (evidence.browserDiagnostics as unknown[]).push(observed);
  page.on('pageerror', error => observed.pageErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') {
      observed.consoleErrors.push(message.text());
      observed.consoleErrorDetails.push({ message: message.text(), url: message.location().url });
    }
  });
  page.on('response', response => {
    if (response.status() < 400) return;
    const failure = { method: response.request().method(), url: response.url(), status: response.status() };
    observed.httpFailures.push(failure);
    if (isDisabledAgentProbe(failure, uiURL)) observed.unavailableAgentProbes.push(failure);
  });
});

test.afterEach(async ({ page }, info) => {
  if (workerPaused) workerSignal('SIGCONT');
  const diagnostic = (evidence.browserDiagnostics as {
    test: string; pageErrors: string[]; consoleErrors: string[];
    consoleErrorDetails: { message: string; url: string }[];
    httpFailures: HttpFailure[]; unavailableAgentProbes: HttpFailure[];
  }[]).find(item => item.test === info.title)!;
  expect(diagnostic.pageErrors).toEqual([]);
  expect(unexpectedCharacteristicFailures(diagnostic.httpFailures, uiURL, info.title.startsWith('real PFMEA'))).toEqual([]);
  // Main deliberately hides this default-off capability; prove its actual
  // GET404 and unavailable UI, rather than ignoring arbitrary console404s.
  expect(diagnostic.unavailableAgentProbes.length).toBeGreaterThan(0);
  await expect(page.getByRole("button", { name: "Agent 任务", exact: true })).toHaveCount(0);
  const unexpected = diagnostic.consoleErrorDetails.filter(({ message, url }) =>
    !message.startsWith('Warning:')
    && !(info.title.startsWith('real PFMEA') && message.includes('status of 409 (Conflict)'))
    && !isDisabledAgentProbeConsole(message, url, diagnostic.httpFailures, uiURL));
  expect(unexpected).toEqual([]);
});

test.beforeAll(async ({ playwright }) => {
  for (const actor of ['editor', 'approver']) {
    const auth = await playwright.request.newContext({ baseURL: apiURL });
    const authPath = `e2e/.storage-state/${owned.run}-${tag}-${actor}-api.json`;
    const token = existsSync(authPath) ? JSON.parse(readFileSync(authPath, 'utf8')) : await json(await auth.post('/api/auth/login', { data: { username: owned.accounts[actor].username, password: owned.password } }));
    if (!existsSync(authPath)) writeFileSync(authPath, JSON.stringify(token), { mode: 0o600, flag: "wx" });
    const context = await playwright.request.newContext({ baseURL: apiURL, extraHTTPHeaders: { Authorization: `Bearer ${token.access_token}`, 'X-Factory-ID': owned.factory_id } });
    if (actor === 'editor') editor = context; else approver = context;
    await auth.dispose();
  }
});
test.afterAll(async () => {
  // Keep approved audit-bearing records: no force-delete or trigger bypass.
  evidence.documents = docs;
  evidence.cleanup = 'Retained explicitly tracked approval/version evidence; no force-delete. Accounts/factory remain because historical audit FKs reference them.';
  writeFileSync(evidencePath, JSON.stringify(evidence, null, 2), { flag: "wx" });
  await editor?.dispose(); await approver?.dispose();
});

test('real PFMEA 2 product + 3 process -> approved snapshot -> five CP rows -> stale/partial/fresh sync', async ({ page }) => {
  const doc = await draft('PFMEA');
  await login(page);
  await functionStep(page, doc.fmea_id);
  await expect(page.getByText('历史功能字段仅供参考，请确认后录入结构化特性。').first()).toBeVisible();
  const legacy = await json(await editor.get(`/api/fmea/${doc.fmea_id}`));
  expect(legacy.graph_data.nodes.find((n: any) => n.id === 'sf').characteristics).toBeUndefined();
  await shot(page, 'legacy');
  await add(page, '产品', '元器件贴装偏移量', '≤0.05', 'mm');
  await page.getByRole('combobox', { name: '特殊分类', exact: true }).first().click();
  await page.getByText('CC', { exact: true }).last().click();
  await add(page, '产品', '焊盘覆盖率', '≥95', '%');
  await add(page, '过程', '贴装力', '3.0±0.5', 'N');
  await add(page, '过程', '贴装速度', '20±2', 'mm/s');
  await add(page, '过程', '吸嘴真空度', '−60±5', 'kPa');
  await save(page, doc.fmea_id);
  await page.reload();
  await page.getByText('功能分析', { exact: true }).first().click();
  await expect(page.getByRole('textbox', { name: '特性名称', exact: true })).toHaveCount(5);
  let source = await json(await editor.get(`/api/fmea/${doc.fmea_id}`));
  const sf = source.graph_data.nodes.find((n: any) => n.id === 'sf');
  const wf = source.graph_data.nodes.find((n: any) => n.id === 'wf');
  expect(sf.characteristics.map((c: any) => c.kind)).toEqual(['product', 'product']);
  expect(wf.characteristics.map((c: any) => c.kind)).toEqual(['process', 'process', 'process']);
  expect(wf.characteristics.every((c: any) => c.related_product_characteristic_ids.length === 2)).toBe(true);
  expect(sf.characteristics.map((c: any) => c.classification)).toEqual(['CC', null]);
  expect(sf.characteristics[0].unit).toBe('mm');
  expect(wf.characteristics[0].unit).toBe('N');
  const characteristicIDs = [...sf.characteristics, ...wf.characteristics].map((c: any) => c.id);
  expect(new Set(characteristicIDs).size).toBe(5);
  await shot(page, 'five-characteristics');
  await page.getByRole('textbox', { name: '特性名称', exact: true }).nth(2).evaluate(element => element.scrollIntoView({ block: 'start' }));
  await shot(page, 'process-three');
  // Prepopulated simulated failure chain satisfies existing validation; finish is real UI.
  await page.getByRole('button', { name: '下一步', exact: true }).click();
  await page.getByRole('button', { name: '下一步', exact: true }).click();
  await page.getByRole('button', { name: '下一步', exact: true }).click();
  await page.getByRole('button', { name: '下一步', exact: true }).click();
  await page.getByRole('button', { name: /完成/ }).click();
  await expect(page).toHaveURL(new RegExp(`/fmea/${doc.fmea_id}$`));
  workerSignal('SIGSTOP');
  const v1 = await approve(doc.fmea_id);
  evidence.v1 = v1;
  const cp = await json(await editor.post('/api/control-plans', { data: { title: `${prefix}-CP`, document_no: `${prefix}-CP`, fmea_ref_id: doc.fmea_id, product_line_code: owned.product_line } }));
  docs.push({ kind: 'cp', id: cp.cp_id });
  await page.goto(`/control-plans/${cp.cp_id}`);
  await page.getByRole('button', { name: /从 PFMEA 导入/ }).click();
  const modal = page.getByRole('dialog');
  await modal.getByRole('combobox').nth(0).click();
  await page.getByText(`${doc.document_no} - ${doc.title}`, { exact: true }).click();
  await modal.getByRole('combobox').nth(1).click();
  await page.getByText(`v${v1.major_no}.${v1.minor_no}`, { exact: true }).last().click();
  const previewResponse = page.waitForResponse(r => r.url().includes('/import-from-fmea/preview'));
  await modal.getByRole('button', { name: '预览变更' }).click();
  const preview = await json(await previewResponse);
  expect(preview.items).toHaveLength(5);
  await expect(page.getByText('元器件贴装偏移量', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('贴装力', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('空载转速', { exact: true })).toHaveCount(0);
  await shot(page, 'import-preview');
  await modal.getByRole('button', { name: '确认导入' }).click();
  await expect(modal).not.toBeVisible();
  let current = await json(await editor.get(`/api/control-plans/${cp.cp_id}`));
  expect(current.items).toHaveLength(5);
  const rowIDs = current.items.map((i: any) => i.item_id).sort();
  expect(current.items.filter((i: any) => i.product_characteristic)).toHaveLength(2);
  expect(current.items.filter((i: any) => i.process_characteristic)).toHaveLength(3);
  expect(current.items.every((i: any) => i.source_characteristic_ref.accepted_source_version_id === v1.version_id)).toBe(true);
  const criteria = ['≤0.05 mm', '≥95 %', '3.0±0.5 N', '20±2 mm/s', '−60±5 kPa'];
  expect(current.items.map((i: any) => i.specification_tolerance)).toEqual(expect.arrayContaining(criteria));
  for (const criterion of criteria) await expect(page.locator(`input[value="${criterion}"]`)).toBeVisible();
  expect(current.sync_pending).toBe(false);
  await shot(page, 'late-import-before-delivery');
  // Ordinary permitted UI edit: unchanged source remains a nonblocking local
  // override, not an outstanding source change. Explicit ACK uses the real API
  // because a clean CP has no pending-only drawer entry point.
  const localCriterion = '≥96 % (SIMULATED LOCAL)';
  await page.locator('input[value="≥95 %"]').fill(localCriterion);
  await page.locator(`input[value="${localCriterion}"]`).blur();
  const savedOverride = page.waitForResponse(response => response.url().includes(`/api/control-plans/${cp.cp_id}`) && response.request().method() === 'PUT');
  await page.getByRole('button', { name: /保\s*存/ }).click();
  await json(await savedOverride);
  const overrideProof = (document: any) => ({
    marker: document.source_fmea_version_id,
    refs: Object.fromEntries(document.items.map((item: any) => [item.item_id, item.source_characteristic_ref])),
    criterion: document.items.find((item: any) => item.product_characteristic === '焊盘覆盖率').specification_tolerance,
  });
  const acknowledgeOverride = async (versionId: string) => {
    const beforeAck = await json(await editor.get(`/api/control-plans/${cp.cp_id}`));
    const noOp = await json(await editor.get(`/api/control-plans/${cp.cp_id}/sync-preview`, { params: { source_fmea_version_id: versionId } }));
    expect(noOp.items).toEqual([]);
    expect(noOp.issues.some((issue: any) => issue.code === 'local_source_override' && !issue.blocking)).toBe(true);
    await json(await editor.post(`/api/control-plans/${cp.cp_id}/sync-from-fmea`, { data: {
      source_fmea_version_id: noOp.source_fmea_version_id, expected_lock_version: noOp.expected_lock_version,
      preview_digest: noOp.preview_digest, selected_candidate_keys: [],
    } }));
    const acknowledged = await json(await editor.get(`/api/control-plans/${cp.cp_id}`));
    expect(acknowledged.sync_pending).toBe(false);
    expect(acknowledged.source_fmea_version_id).toBe(versionId);
    expect(overrideProof(acknowledged).refs).toEqual(overrideProof(beforeAck).refs);
    expect(acknowledged.items.find((item: any) => item.product_characteristic === '焊盘覆盖率').specification_tolerance).toBe(localCriterion);
    return acknowledged;
  };
  current = await acknowledgeOverride(v1.version_id);
  await shot(page, 'acknowledged-override-before-late-import');
  workerSignal('SIGCONT');
  await delivered(doc.fmea_id, v1.version_id); // postcondition, not a pre-sync gate
  const afterImportDelivery = await json(await editor.get(`/api/control-plans/${cp.cp_id}`));
  expect(afterImportDelivery.sync_pending).toBe(false);
  expect(overrideProof(afterImportDelivery)).toEqual(overrideProof(current));
  evidence.acknowledgedImportProof = overrideProof(afterImportDelivery);
  evidence.lateImport = { version: v1.version_id, pendingAfterDelivery: false, criteria, acknowledgedLocalCriterion: localCriterion };
  // Legal API manual fields are setup for preservation, not source/provenance forging.
  const editable = (item: any) => Object.fromEntries(Object.entries(item).filter(([key]) => key !== 'source_characteristic_ref'));
  const manualMethods = new Map(current.items.map((i: any) => [i.item_id,
    i.product_characteristic ? 'SIMULATED-AOI-position/coverage' : i.process_characteristic === '贴装力' ? 'SIMULATED-force-sensor' : i.process_characteristic === '贴装速度' ? 'SIMULATED-encoder' : 'SIMULATED-vacuum-sensor']));
  current = await json(await editor.put(`/api/control-plans/${cp.cp_id}`, { data: { lock_version: current.lock_version, items: current.items.map((i: any) => ({ ...editable(i), evaluation_method: manualMethods.get(i.item_id), sample_size: '5', sample_frequency: '每班', control_method: 'MANUAL-control', reaction_plan: 'MANUAL-stop' })) } }));
  await json(await approver.post(`/api/fmea/${doc.fmea_id}/transition`, { data: { target_status: 'rework', reason: 'SIMULATED characteristic revision' } }));
  await functionStep(page, doc.fmea_id);
  for (const [old, name] of [['元器件贴装偏移量', '元器件贴装位置偏差'], ['贴装力', '贴装作用力']]) {
    await page.locator(`input[value="${old}"]`).fill(name);
    await page.locator(`input[value="${name}"]`).blur();
  }
  const speedCard = page.locator('.ant-card').filter({ has: page.locator('input[value="贴装速度"]') }).last();
  await speedCard.getByRole('textbox', { name: '单位', exact: true }).fill('cm/s');
  await speedCard.getByRole('textbox', { name: '单位', exact: true }).blur();
  await save(page, doc.fmea_id);
  const v2 = await approve(doc.fmea_id);
  evidence.v2 = v2;
  // Worker delivers durable outbox normally; it does not mutate source approval.
  // A pending flag may belong to an earlier approval. Wait for this exact
  // immutable source-version event to be delivered, not an arbitrary sleep.
  await delivered(doc.fmea_id, v2.version_id);
  await expect.poll(async () => (await json(await editor.get(`/api/control-plans/${cp.cp_id}`))).sync_pending, { timeout: 15_000 }).toBe(true);
  await page.goto(`/control-plans/${cp.cp_id}`);
  for (const header of ['零件/过程编号', '过程名称/操作描述', '设备/工装/夹具', '特性编号', '产品特性', '过程特性', '特殊特性分类', '产品/过程/规格/公差', '评价/测量技术', '样本大小', '样本频次', '控制方法', '反应计划']) {
    await expect(page.getByRole('columnheader', { name: header, exact: true })).toHaveCount(1);
  }
  await page.getByRole('button', { name: '立即同步' }).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByRole('button', { name: '确认同步' })).toBeEnabled();
  // Real concurrent legal update, no interception of success or 409.
  current = await json(await editor.get(`/api/control-plans/${cp.cp_id}`));
  await json(await editor.put(`/api/control-plans/${cp.cp_id}`, { data: { lock_version: current.lock_version, title: `${prefix}-CP-concurrent` } }));
  const stale = page.waitForResponse(r => r.url().endsWith('/sync-from-fmea') && r.request().method() === 'POST');
  await drawer.getByRole('button', { name: '确认同步' }).click();
  expect((await stale).status()).toBe(409);
  await expect(drawer.getByText('预览已失效，请重新生成预览后再确认。')).toBeVisible();
  await shot(page, 'real-409');
  await drawer.getByRole('button', { name: '重新生成预览' }).click();
  await expect(drawer.getByRole('row').filter({ has: page.getByRole('checkbox') })).toHaveCount(4);
  // Two renamed objects plus the unit-only change: accept exactly one.
  await drawer.getByRole('checkbox').first().uncheck();
  await drawer.getByRole('row').filter({ hasText: '元器件贴装位置偏差' }).getByRole('checkbox').check();
  await drawer.getByRole('button', { name: '确认同步' }).click();
  await expect(drawer.getByText('仍有 2 项待同步。')).toBeVisible();
  current = await json(await editor.get(`/api/control-plans/${cp.cp_id}`));
  expect(current.sync_pending).toBe(true);
  expect(current.items.filter((i: any) => i.source_characteristic_ref.accepted_source_version_id === v2.version_id)).toHaveLength(1);
  evidence.partial = current;
  await shot(page, 'partial-pending');
  workerSignal('SIGSTOP');
  await json(await approver.post(`/api/fmea/${doc.fmea_id}/transition`, { data: { target_status: 'rework', reason: 'SIMULATED unit-only revision before delayed worker' } }));
  await functionStep(page, doc.fmea_id);
  const forceCard = page.locator('.ant-card').filter({ has: page.locator('input[value="贴装作用力"]') }).last();
  await forceCard.getByRole('textbox', { name: '单位', exact: true }).fill('kN');
  await forceCard.getByRole('textbox', { name: '单位', exact: true }).blur();
  await save(page, doc.fmea_id);
  const v3 = await approve(doc.fmea_id);
  evidence.v3 = v3;
  await page.goto(`/control-plans/${cp.cp_id}`);
  await page.getByRole('button', { name: '立即同步' }).click();
  await expect(page.getByRole('dialog').getByText('20±2 cm/s', { exact: false }).first()).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: '确认同步' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  const beforeLate = await acknowledgeOverride(v3.version_id);
  expect(beforeLate.sync_pending).toBe(false);
  await shot(page, 'late-sync-before-delivery');
  workerSignal('SIGCONT');
  await delivered(doc.fmea_id, v3.version_id); // only after actual UI sync completed
  await page.reload();
  current = await json(await editor.get(`/api/control-plans/${cp.cp_id}`));
  expect(current.sync_pending).toBe(false);
  expect(overrideProof(current)).toEqual(overrideProof(beforeLate));
  evidence.acknowledgedFinalProof = overrideProof(current);
  expect(current.items.map((i: any) => i.item_id).sort()).toEqual(rowIDs);
  // Unchanged characteristics retain their actual v1 per-row baseline (not falsely advanced).
  expect(current.items.filter((i: any) => i.source_characteristic_ref.accepted_source_version_id === v3.version_id)).toHaveLength(2);
  expect(current.items.filter((i: any) => i.source_characteristic_ref.accepted_source_version_id === v2.version_id)).toHaveLength(1);
  expect(current.items.map((i: any) => i.specification_tolerance)).toEqual(expect.arrayContaining(['20±2 cm/s', '3.0±0.5 kN']));
  await expect(page.locator('input[value="20±2 cm/s"]')).toBeVisible();
  await expect(page.locator('input[value="3.0±0.5 kN"]')).toBeVisible();
  evidence.lateSync = { version: v3.version_id, pendingAfterDelivery: current.sync_pending, acknowledgedLocalCriterion: localCriterion };
  expect(current.items.every((i: any) => i.evaluation_method === manualMethods.get(i.item_id) && i.sample_frequency === '每班' && i.control_method === 'MANUAL-control' && i.reaction_plan === 'MANUAL-stop')).toBe(true);
  expect(current.source_fmea_version_id).toBe(v3.version_id);
  expect(current.items.find((item: any) => item.product_characteristic === '焊盘覆盖率').specification_tolerance).toBe(localCriterion);
  const changedSource = await json(await editor.get(`/api/fmea/${doc.fmea_id}`));
  expect(changedSource.graph_data.nodes.flatMap((n: any) => n.characteristics ?? []).map((c: any) => c.id)).toEqual(characteristicIDs);
  const extracted = await json(await editor.post(`/api/special-characteristics/sync-from-fmea/${doc.fmea_id}`));
  expect(extracted.count).toBe(1);
  const catalog = await json(await editor.get('/api/special-characteristics/list', { params: { product_line: owned.product_line } }));
  const ordinary = catalog.items.find((sc: any) => sc.source_fmea_id === doc.fmea_id);
  expect(ordinary.is_safety_related).toBe(false);
  expect(ordinary.source_characteristic_id).toBe(characteristicIDs[0]);
  expect(ordinary.spec_requirement).toBe('≤0.05 mm');
  const chain = await json(await editor.get(`/api/special-characteristics/traceability/${ordinary.sc_id}`));
  expect(chain.control_plan_items.map((i: any) => i.item_id)).toEqual(current.items.filter((i: any) => i.source_characteristic_ref.characteristic_id === characteristicIDs[0]).map((i: any) => i.item_id));
  expect(chain.msa_status).toBe('PENDING');
  expect(chain.spc_characteristics).toEqual([]);
  evidence.ordinarySC = { id: ordinary.sc_id, chain };
  docs.push({ kind: 'sc', id: ordinary.sc_id });
  evidence.final = current;
  await shot(page, 'complete-stable-rows');
  // Actual version history snapshot viewing, not the live graph.
  await page.goto(`/fmea/${doc.fmea_id}`);
  await page.getByRole('tab', { name: /版本历史/ }).click();
  await page.getByRole('button', { name: /查看/ }).first().click();
  await page.getByRole('tab', { name: /编辑器|失效分析/ }).first().click();
  await expect(page.getByRole('textbox', { name: '特性名称', exact: true }).first()).toBeDisabled();
  await expect(page.getByRole('button', { name: '新增产品特性' })).toHaveCount(0);
  await shot(page, 'snapshot-readonly');

  // Final-review I1: the event is already consumed before this independent CP exists.
  await delivered(doc.fmea_id, v3.version_id);
  const partialCP = await json(await editor.post("/api/control-plans", { data: { title: `${prefix}-PARTIAL`, document_no: `${prefix}-PARTIAL`, fmea_ref_id: doc.fmea_id, product_line_code: owned.product_line } }));
  docs.push({ kind: "cp", id: partialCP.cp_id });
  await page.goto(`/control-plans/${partialCP.cp_id}`);
  await page.getByRole("button", { name: /从 PFMEA 导入/ }).click();
  const importDialog = page.getByRole("dialog");
  await importDialog.getByRole("combobox").nth(0).click();
  await page.getByText(`${doc.document_no} - ${doc.title}`, { exact: true }).click();
  await importDialog.getByRole("combobox").nth(1).click();
  await page.getByText(`v${v3.major_no}.${v3.minor_no}`, { exact: true }).last().click();
  await importDialog.getByRole("button", { name: "预览变更" }).click();
  const candidateTable = importDialog.getByRole("table").filter({
    has: page.getByRole("columnheader", { name: "产品特性", exact: true }),
  });
  const importRows = candidateTable.locator("tbody tr");
  await expect(importRows).toHaveCount(5);
  for (let i = 1; i < 5; i++) await importRows.nth(i).getByRole("checkbox").uncheck();
  await importDialog.getByRole("button", { name: "确认导入" }).click();
  await expect(importDialog.getByText("已部分导入，仍有 4 项待同步。")).toBeVisible();
  await importDialog.getByRole("button", { name: /取\s*消/ }).click();
  await expect(importDialog).not.toBeVisible();
  await page.reload();
  const partialReload = await json(await editor.get(`/api/control-plans/${partialCP.cp_id}`));
  expect(partialReload.items).toHaveLength(1);
  expect(partialReload.sync_pending).toBe(true);
  await expect(page.getByRole("button", { name: "立即同步" })).toBeVisible();
  await shot(page, "worker-first-partial-reload");
  await page.getByRole("button", { name: "立即同步" }).click();
  await expect(page.getByRole("dialog").locator("tbody tr")).toHaveCount(4);
  await page.getByRole("dialog").getByRole("button", { name: "确认同步" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.reload();
  const completedImport = await json(await editor.get(`/api/control-plans/${partialCP.cp_id}`));
  expect(completedImport.items).toHaveLength(5);
  expect(completedImport.sync_pending).toBe(false);
  expect(completedImport.items.every((i: any) => i.source_characteristic_ref.accepted_source_version_id === v3.version_id)).toBe(true);
  evidence.workerFirstPartial = { partialReload, completedImport };
  // I2: an unclassified, unexecuted control deletion is explicit, not disabled.
  await json(await approver.post(`/api/fmea/${doc.fmea_id}/transition`, { data: { target_status: "rework", reason: "SIMULATED final-review source deletion" } }));
  // Work-element characteristics are editable in the function wizard even
  // when that function has no failure-analysis row in the main editor.
  await functionStep(page, doc.fmea_id);
  const vacuum = page.locator(".ant-card").filter({ has: page.locator('input[value="吸嘴真空度"]') }).last();
  await vacuum.getByRole("button", { name: "删除过程特性" }).click();
  await save(page, doc.fmea_id);
  const v4 = await approve(doc.fmea_id);
  await delivered(doc.fmea_id, v4.version_id);
  await page.goto(`/control-plans/${partialCP.cp_id}`);
  await page.getByRole("button", { name: "立即同步" }).click();
  const deletion = page.getByRole("dialog").locator("tbody tr").filter({ hasText: "吸嘴真空度" });
  await expect(deletion).toHaveCount(1);
  await expect(deletion.getByRole("checkbox")).not.toBeChecked();
  await expect(deletion.getByRole("checkbox")).toBeEnabled();
  await deletion.getByRole("checkbox").check();
  await shot(page, "applicable-deletion-selected");
  await page.getByRole("dialog").getByRole("button", { name: "确认同步" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.reload();
  const afterDeletion = await json(await editor.get(`/api/control-plans/${partialCP.cp_id}`));
  expect(afterDeletion.items).toHaveLength(4);
  expect(afterDeletion.items.some((i: any) => i.process_characteristic === "吸嘴真空度")).toBe(false);
  expect(afterDeletion.sync_pending).toBe(false);
  evidence.applicableDeletion = afterDeletion;
  for (const row of afterDeletion.items) {
    const name = row.product_characteristic || row.process_characteristic;
    await expect(page.locator(`input[value="${name}"]`)).toBeVisible();
  }
  await shot(page, "applicable-deletion-reloaded");
});

test('DFMEA shared ProcessWorkElementFunction remains product through browser save/reload', async ({ page }) => {
  const doc = await draft('DFMEA');
  await login(page);
  await functionStep(page, doc.fmea_id, true);
  await expect(page.getByRole('button', { name: '新增过程特性' })).toHaveCount(0);
  await add(page, '产品', 'DFMEA结构绝缘间隙', '≥2', 'mm');
  await save(page, doc.fmea_id);
  await page.reload();
  await page.getByText('功能分析 (第三步)', { exact: true }).first().click();
  await expect(page.locator('input[value="DFMEA结构绝缘间隙"]')).toBeVisible();
  const saved = await json(await editor.get(`/api/fmea/${doc.fmea_id}`));
  const chars = saved.graph_data.nodes.flatMap((n: any) => n.characteristics ?? []);
  expect(chars).toHaveLength(1);
  expect(chars[0].kind).toBe('product');
  evidence.dfmea = saved;
  await shot(page, 'dfmea-product');
});


test("editor function deletion confirms surviving process references and persists reload", async ({ page }) => {
  const doc = await draft("PFMEA", "PFMEA-TREE");
  let source = await json(await editor.get(`/api/fmea/${doc.fmea_id}`));
  const productId = crypto.randomUUID();
  const processId = crypto.randomUUID();
  const char = (id: string, kind: string, name: string, links: string[] = []) => ({ id, kind, name, classification: null, related_product_characteristic_ids: links });
  source.graph_data.nodes.find((n: any) => n.id === "sf").characteristics = [char(productId, "product", "SIMULATED removed size")];
  source.graph_data.nodes.find((n: any) => n.id === "wf").characteristics = [char(processId, "process", "SIMULATED surviving force", [productId])];
  await json(await editor.put(`/api/fmea/${doc.fmea_id}`, { data: { lock_version: source.lock_version, graph_data: source.graph_data } }));
  await login(page);
  await completeDraftWizard(page, doc.fmea_id);
  const completed = await json(await editor.get(`/api/fmea/${doc.fmea_id}`));
  expect(completed.graph_data.wizardScope.wizard_completed).toBe(true);
  const row = page.getByTestId("fmea-structure-node-sf");
  await row.getByRole("button").filter({ has: page.locator(".anticon-delete") }).click();
  await page.getByRole("button", { name: /确\s*定/, exact: true }).click();
  await expect(page.getByText("以下过程特性将失去关联：SIMULATED surviving force。确认继续吗？")).toBeVisible();
  await expect(row).toBeVisible();
  await shot(page, "tree-deletion-impact-confirmation");
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(row).toHaveCount(0);
  const saved = page.waitForResponse(r => r.url().endsWith(`/api/fmea/${doc.fmea_id}`) && r.request().method() === "PUT");
  await page.getByRole("button", { name: /保\s*存/ }).click();
  await json(await saved);
  await page.reload();
  await expect(page.getByTestId("fmea-structure-node-sf")).toHaveCount(0);
  // Surviving wf has no failure row: inspect its real function-wizard UI,
  // not a nonexistent CharacteristicEditor created by selecting the tree node.
  await page.goto(`/fmea/pfmea-wizard/${doc.fmea_id}`);
  await page.getByText("功能分析", { exact: true }).first().click();
  await expect(page.locator('input[value="SIMULATED surviving force"]')).toBeVisible();
  source = await json(await editor.get(`/api/fmea/${doc.fmea_id}`));
  const survivor = source.graph_data.nodes.find((n: any) => n.id === "wf").characteristics[0];
  expect(survivor.id).toBe(processId);
  expect(survivor.related_product_characteristic_ids).toEqual([]);
  evidence.treeDeletion = source;
  await shot(page, "tree-deletion-save-reload");
});
