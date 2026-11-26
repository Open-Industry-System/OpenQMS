import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { copyFile, mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const authorization = 'Bearer workspace-fixture-token';
const tenant = 'workspace-fixture-tenant';
const tools = ['summarize_capa', 'find_fmea'].map(name => ({
  name,
  description: name,
  parameters: {
    type: 'object',
    properties: { key: { type: 'string' } },
    required: ['key'],
    additionalProperties: false,
  },
}));

function infer(turn, tool_calls = []) {
  return {
    path: 'infer',
    body: { turn },
    response: { content: 'Private model text', tool_calls },
  };
}

function tool(call_id, status = 200) {
  return {
    path: 'tools',
    body: { call_id },
    response: { evidence: 'Private tool result' },
    status,
  };
}

function call(id, name, args = { key: 'private model argument' }) {
  return { id, name, arguments: args };
}

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
      body: JSON.parse(Buffer.concat(chunks).toString('utf8')),
    });
    res.writeHead(step?.status ?? (step ? 200 : 500), { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(step?.response ?? {}));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise((resolve, reject) => {
    server.close(error => error ? reject(error) : resolve());
    server.closeAllConnections();
  }));

  const directory = await mkdtemp(join(tmpdir(), 'openqms-workspace-worker-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const worker = join(directory, 'worker.mjs');
  await copyFile(new URL('./dist/workspace-worker.mjs', import.meta.url), worker);
  const child = spawn(process.execPath, [worker], {
    cwd: directory,
    env: { LANG: 'C', LC_ALL: 'C' },
    stdio: ['pipe', 'pipe', 'pipe'],
    timeout: 5_000,
  });
  let stdout = '';
  let stderr = '';
  child.stdout.setEncoding('utf8').on('data', chunk => { stdout += chunk; });
  child.stderr.setEncoding('utf8').on('data', chunk => { stderr += chunk; });
  child.stdin.end(JSON.stringify({
    api_origin: origin ?? `http://127.0.0.1:${server.address().port}`,
    token: authorization.slice('Bearer '.length),
    tenant_slug: tenant,
    content: 'Private employee prompt',
    tools,
  }));

  assert.deepEqual(await once(child, 'close'), [exit, null]);
  assert.equal(stdout, exit === 0 ? '{"kind":"completed"}\n' : '');
  assert.equal(stderr, '');
  assert.deepEqual(observed, steps.map(step => ({
    method: 'POST',
    url: `/api/agent/workspace/runtime/${step.path}`,
    authorization,
    tenant,
    body: step.body,
  })));
}

test('Pi runs broker-selected tools in order across model turns and returns a completion marker', async t => {
  await exercise(t, [
    infer(0, [call('capa', 'summarize_capa')]),
    tool('capa'),
    infer(1, [call('fmea', 'find_fmea')]),
    tool('fmea'),
    infer(2),
  ]);
});

test('a tool-free response can complete on the first turn', async t => {
  await exercise(t, [infer(0)]);
});

test('Pi rejects malformed tool arguments before calling the broker', async t => {
  await exercise(t, [infer(0, [call('capa', 'summarize_capa', { unknown: 'private' })])], { exit: 1 });
});

test('an unregistered tool rejects its whole inference batch', async t => {
  await exercise(t, [
    infer(0, [call('capa', 'summarize_capa'), call('confirm', 'confirm_write')]),
  ], { exit: 1 });
});

test('a duplicate call ID from a later turn is rejected', async t => {
  await exercise(t, [
    infer(0, [call('duplicate', 'summarize_capa')]),
    tool('duplicate'),
    infer(1, [call('duplicate', 'find_fmea')]),
  ], { exit: 1 });
});

test('the worker rejects tool calls beyond the round limit', async t => {
  await exercise(t, [
    infer(0, Array.from({ length: 9 }, (_, index) => call(`call-${index}`, 'summarize_capa'))),
  ], { exit: 1 });
});

test('an authorization failure stops before sibling tools and subsequent rounds', async t => {
  await exercise(t, [
    infer(0, [call('capa', 'summarize_capa'), call('fmea', 'find_fmea')]),
    tool('capa', 403),
  ], { exit: 1 });
});

test('the worker rejects an origin with a non-root path', async t => {
  await exercise(t, [], { exit: 1, origin: 'http://127.0.0.1:8000/other' });
});
