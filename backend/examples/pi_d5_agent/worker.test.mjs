import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { copyFile, mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const bundle = new URL('./dist/worker.mjs', import.meta.url);
const auth = 'Bearer fixture-runtime-token';
const tenant = 'fixture-tenant';
const emptyInbox = [{ path: 'messages/claim', body: { limit: 20 }, result: { messages: [] } }];

function infer(turn, tool_calls = []) {
  return {
    path: 'model/infer',
    body: { operation: 'workflow', turn },
    result: { content: 'Private model response', tool_calls },
  };
}

function execute(call_id, result, status = 200) {
  return { path: 'model/tools', body: { call_id }, result, status };
}

const finish = { path: 'finish', body: { status: 'completed' }, result: {} };

async function exercise(t, steps, { exit = 0, origin } = {}) {
  const observed = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) {
      chunks.push(chunk);
    }
    const step = steps[observed.length];
    observed.push({
      method: req.method,
      url: req.url,
      authorization: req.headers.authorization,
      tenant: req.headers['x-tenant-id'],
      body: JSON.parse(Buffer.concat(chunks).toString()),
    });
    if (step?.status === 'disconnect') {
      res.destroy();
      return;
    }
    res.writeHead(step?.status ?? (step ? 200 : 500), { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(step?.result ?? {}));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(async () => {
    await new Promise((resolve, reject) => {
      server.close(error => error ? reject(error) : resolve());
      server.closeAllConnections();
    });
  });

  const directory = await mkdtemp(join(tmpdir(), 'openqms-pi-worker-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const worker = join(directory, 'worker.mjs');
  await copyFile(bundle, worker);

  const child = spawn(process.execPath, [worker], {
    cwd: directory,
    env: { LANG: 'C', LC_ALL: 'C' },
    stdio: ['pipe', 'pipe', 'pipe'],
    timeout: 5_000,
  });
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', chunk => { stdout += chunk; });
  child.stderr.on('data', chunk => { stderr += chunk; });
  child.stdin.end(JSON.stringify({
    api_origin: origin ?? `http://127.0.0.1:${server.address().port}`,
    token: auth.slice('Bearer '.length),
    task_id: 'sample-task',
    deployment_id: 'sample-deployment',
    tenant_slug: tenant,
  }));

  assert.deepEqual(await once(child, 'close'), [exit, null]);
  assert.equal(stdout, '');
  assert.equal(stderr, '');
  assert.deepEqual(observed, steps.map(step => ({
    method: 'POST',
    url: `/api/agent/runtime/${step.path}`,
    authorization: auth,
    tenant,
    body: step.body,
  })));
}

test('claims and ACKs once, executes four tools in order, and completes after the terminal turn', async t => {
  await exercise(t, [
    {
      path: 'messages/claim', body: { limit: 20 },
      result: { batch_id: 'broker-batch', messages: [{ sequence: 4 }, { sequence: 7 }] },
    },
    { path: 'messages/ack', body: { batch_id: 'broker-batch', through_sequence: 7 }, result: {} },
    infer(0, [{ id: 'read', name: 'read_d4' }, { id: 'query', name: 'query_source' }]),
    execute('read', { status: 'read', context: { private: 'D4 evidence' } }),
    execute('query', { status: 'read', context: { private: 'source evidence' } }),
    infer(1, [
      { id: 'supplement', name: 'request_supplement' },
      { id: 'save', name: 'save_proposal', arguments: { text: 'untrusted text' } },
    ]),
    execute('supplement', { status: 'waiting' }),
    execute('supplement', { status: 'accepted', accepted_sequence: 8 }),
    execute('save', { status: 'saved', proposal_id: 'broker-proposal' }),
    infer(2),
    finish,
  ]);
});

test('continues the platform-authorized chat when a read reports missing basis', async t => {
  await exercise(t, [
    ...emptyInbox,
    infer(0, [{ id: 'read', name: 'read_d4' }]),
    execute('read', { status: 'missing_basis' }),
    infer(1),
    finish,
  ]);
});

for (const status of [409, 'disconnect']) {
  test(`a ${status} at tool execution retries only the original ID`, async t => {
    await exercise(t, [
      ...emptyInbox,
      infer(0, [{ id: 'first', name: 'save_proposal' }, { id: 'second', name: 'query_source' }]),
      execute('first', {}, status),
      execute('first', { status: 'saved' }),
      execute('second', { status: 'read' }),
      infer(1),
      finish,
    ]);
  });
}

for (const scenario of [
  { label: 'authorization rejection', result: { detail: 'Restricted reason' }, status: 403 },
  { label: 'HTTP error', result: { detail: 'Restricted failure' }, status: 500 },
  { label: 'unexpected tool status', result: { status: 'failed', detail: 'Restricted failure' } },
]) {
  test(`${scenario.label} stops before sibling tools, inference, or finish`, async t => {
    await exercise(t, [
      ...emptyInbox,
      infer(0, [{ id: 'first', name: 'read_d4' }, { id: 'sibling', name: 'save_proposal' }]),
      execute('first', scenario.result, scenario.status),
    ], { exit: 1 });
  });
}

test('a second uncertain response stops the run after the same-ID retry', async t => {
  await exercise(t, [
    ...emptyInbox,
    infer(0, [{ id: 'save', name: 'save_proposal' }, { id: 'sibling', name: 'query_source' }]),
    execute('save', {}, 'disconnect'),
    execute('save', {}, 409),
  ], { exit: 1 });
});

test('an unregistered tool causes the broker turn to fail before side effects', async t => {
  await exercise(t, [
    ...emptyInbox,
    infer(0, [{ id: 'first', name: 'save_proposal' }, { id: 'foreign', name: 'shell' }]),
  ], { exit: 1 });
});

test('broker rejection during inference stops the run without finish', async t => {
  await exercise(t, [
    ...emptyInbox,
    { ...infer(0), status: 403, result: { detail: 'Restricted denial' } },
  ], { exit: 1 });
});

test('the worker rejects an unapproved HTTPS origin before making requests', async t => {
  await exercise(t, [], { exit: 1, origin: 'https://127.0.0.1' });
});
