import { readFileSync } from 'node:fs';
import { request as httpRequest } from 'node:http';
import { setTimeout as delay } from 'node:timers/promises';
import { runAgentLoop } from '@earendil-works/pi-agent-core';
import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';

const MAX_TOOLS = 8;
const ROUND_MS = 120_000;
const RESPONSE_LIMIT = 1024 * 1024;
const TOOL_STATUSES = {
  read_d4: ['read', 'missing_basis'],
  query_source: ['read', 'missing_basis'],
  request_supplement: ['accepted'],
  save_proposal: ['saved'],
};
const MODEL = {
  api: 'openqms-broker',
  provider: 'openqms',
  id: 'platform-managed',
};
const ZERO_USAGE = {
  input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
};

class RetryOriginal extends Error {}

function brokerClient({ api_origin, token, tenant_slug }) {
  const origin = new URL(api_origin);
  if (origin.protocol !== 'http:' || origin.hostname !== '127.0.0.1' ||
      origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash ||
      typeof token !== 'string' || !token || typeof tenant_slug !== 'string' || !tenant_slug) {
    throw new Error('Invalid broker configuration');
  }
  const deadline = performance.now() + ROUND_MS;
  const headers = {
    Authorization: `Bearer ${token}`,
    'X-Tenant-ID': tenant_slug,
    'Content-Type': 'application/json',
  };

  return async function post(path, body) {
    const remaining = Math.ceil(deadline - performance.now());
    if (remaining <= 0) {
      throw new Error('Round expired');
    }
    const data = JSON.stringify(body);
    const response = await new Promise((resolve, reject) => {
      const outgoing = httpRequest(origin, {
        agent: false,
        method: 'POST',
        path: `/api/agent/runtime/${path}`,
        headers: { ...headers, 'Content-Length': Buffer.byteLength(data) },
        signal: AbortSignal.timeout(Math.min(30_000, remaining)),
      }, resolve);
      outgoing.once('error', () => reject(new RetryOriginal('Broker connection lost')));
      outgoing.end(data);
    });

    if (response.statusCode !== 200) {
      response.destroy();
      if (response.statusCode === 409) {
        throw new RetryOriginal('Broker requested original call');
      }
      throw new Error('Broker request rejected');
    }

    const chunks = [];
    let size = 0;
    try {
      for await (const chunk of response) {
        size += chunk.length;
        if (size > RESPONSE_LIMIT) {
          throw new Error('Broker response too large');
        }
        chunks.push(chunk);
      }
    } catch (error) {
      if (size <= RESPONSE_LIMIT) {
        throw new RetryOriginal('Broker response interrupted');
      }
      throw error;
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  };
}

async function executeTool(post, callId, name, signal) {
  let retried = false;
  for (;;) {
    signal.throwIfAborted();
    let result;
    try {
      result = await post('model/tools', { call_id: callId });
    } catch (error) {
      if (retried || !(error instanceof RetryOriginal)) {
        throw error;
      }
      retried = true;
      continue;
    }
    if (name === 'request_supplement' && result?.status === 'waiting') {
      await delay(100, undefined, { signal });
      continue;
    }
    if (!TOOL_STATUSES[name].includes(result?.status)) {
      throw new Error('Broker tool failed');
    }
    // The broker keeps evidence, conversation history and tool results.
    return { content: [{ type: 'text', text: result.status }], details: {} };
  }
}

async function run(post) {
  const batch = await post('messages/claim', { limit: 20 });
  if (batch.messages.length) {
    await post('messages/ack', {
      batch_id: batch.batch_id,
      through_sequence: batch.messages.at(-1).sequence,
    });
  }

  const controller = new AbortController();
  const tools = Object.keys(TOOL_STATUSES).map(name => ({
    name,
    label: name,
    description: `Execute a broker-issued ${name} call.`,
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    execute: (callId, _arguments, signal) => executeTool(post, callId, name, signal),
  }));

  let turn = 0;
  let terminalResponse = false;
  const issued = new Set();
  const streamFn = async () => {
    controller.signal.throwIfAborted();
    if (turn > MAX_TOOLS) {
      throw new Error('Round exhausted');
    }
    const response = await post('model/infer', { operation: 'workflow', turn: turn++ });
    if (typeof response?.content !== 'string' || !Array.isArray(response.tool_calls) ||
        response.tool_calls.length + issued.size > MAX_TOOLS) {
      throw new Error('Invalid broker response');
    }
    const content = response.content ? [{ type: 'text', text: response.content }] : [];
    for (const call of response.tool_calls) {
      if (!call || typeof call.id !== 'string' || !call.id.length || call.id.length > 100 ||
          issued.has(call.id) || typeof call.name !== 'string' || !Object.hasOwn(TOOL_STATUSES, call.name)) {
        throw new Error('Invalid broker tool call');
      }
      issued.add(call.id);
      content.push({ type: 'toolCall', id: call.id, name: call.name, arguments: {} });
    }
    terminalResponse = response.tool_calls.length === 0;
    const message = {
      role: 'assistant',
      content,
      api: MODEL.api,
      provider: MODEL.provider,
      model: MODEL.id,
      usage: ZERO_USAGE,
      stopReason: terminalResponse ? 'stop' : 'toolUse',
      timestamp: Date.now(),
    };
    const stream = createAssistantMessageEventStream();
    stream.push({ type: 'done', reason: message.stopReason, message });
    return stream;
  };

  await runAgentLoop(
    [{ role: 'user', content: 'Process the active broker workflow.', timestamp: Date.now() }],
    { systemPrompt: '', messages: [], tools },
    {
      model: MODEL,
      toolExecution: 'sequential',
      convertToLlm: () => [],
      shouldStopAfterTurn: () => controller.signal.aborted,
    },
    event => {
      // Pi can recover from a tool error by default. An R5 round must halt.
      if (event.type === 'tool_execution_end' && event.isError) {
        controller.abort();
      }
    },
    controller.signal,
    streamFn,
  );

  controller.signal.throwIfAborted();
  if (!terminalResponse) {
    throw new Error('Round did not complete');
  }
  await post('finish', { status: 'completed' });
}

try {
  await run(brokerClient(JSON.parse(readFileSync(0, 'utf8'))));
} catch {
  // The launcher needs only an exit status. Keep broker payloads off both streams.
  process.exitCode = 1;
}
