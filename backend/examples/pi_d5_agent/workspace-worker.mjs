import { readFileSync } from 'node:fs';
import { request } from 'node:http';
import { runAgentLoop } from '@earendil-works/pi-agent-core';
import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';

const ROUND_MS = 120_000;
const MAX_TOOLS = 8;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const INFER_PATH = '/api/agent/workspace/runtime/infer';
const TOOL_PATH = '/api/agent/workspace/runtime/tools';
const MODEL = {
  api: 'openqms-broker',
  provider: 'openqms',
  id: 'platform-managed',
};
const ZERO_USAGE = {
  input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
};

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function brokerClient({ api_origin, token, tenant_slug }, signal) {
  if (typeof api_origin !== 'string' || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/?$/.test(api_origin) ||
      typeof token !== 'string' || !token || typeof tenant_slug !== 'string' || !tenant_slug) {
    throw new Error('Invalid workspace broker configuration');
  }
  const origin = new URL(api_origin);
  const headers = {
    Authorization: `Bearer ${token}`,
    'X-Tenant-ID': tenant_slug,
    'Content-Type': 'application/json',
  };

  return async function post(path, body) {
    signal.throwIfAborted();
    const data = JSON.stringify(body);
    const response = await new Promise((resolve, reject) => {
      const outgoing = request(origin, {
        agent: false,
        method: 'POST',
        path,
        headers: { ...headers, 'Content-Length': Buffer.byteLength(data) },
        signal,
      }, resolve);
      outgoing.once('error', reject);
      outgoing.end(data);
    });
    if (response.statusCode !== 200) {
      response.destroy();
      throw new Error('Workspace broker rejected the request');
    }

    let size = 0;
    const chunks = [];
    for await (const chunk of response) {
      size += chunk.length;
      if (size > MAX_RESPONSE_BYTES) {
        throw new Error('Workspace broker response too large');
      }
      chunks.push(chunk);
    }
    const result = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (!isObject(result)) {
      throw new Error('Invalid workspace broker response');
    }
    return result;
  };
}

function registerTools(catalog, post) {
  if (!Array.isArray(catalog)) {
    throw new Error('Invalid workspace tool catalog');
  }
  const tools = new Map();
  for (const entry of catalog) {
    if (!isObject(entry) || typeof entry.name !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(entry.name) ||
        tools.has(entry.name) || typeof entry.description !== 'string' ||
        !isObject(entry.parameters) || entry.parameters.type !== 'object') {
      throw new Error('Invalid workspace tool definition');
    }
    const { name, description, parameters } = entry;
    tools.set(name, {
      name,
      label: name,
      description,
      parameters,
      async execute(callId) {
        // Pi validates the arguments. The broker executes the original authorized call.
        await post(TOOL_PATH, { call_id: callId });
        return { content: [{ type: 'text', text: 'Tool result recorded by the broker.' }], details: {} };
      },
    });
  }
  return tools;
}

async function run(input) {
  if (!isObject(input) || typeof input.content !== 'string') {
    throw new Error('Invalid workspace prompt');
  }
  const controller = new AbortController();
  const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(ROUND_MS)]);
  const post = brokerClient(input, signal);
  const tools = registerTools(input.tools, post);
  let turn = 0;
  let terminalResponse = false;
  const issued = new Set();

  const streamFn = async () => {
    if (turn > MAX_TOOLS) {
      throw new Error('Workspace round exhausted');
    }
    const response = await post(INFER_PATH, { turn: turn++ });
    if (typeof response.content !== 'string' || !Array.isArray(response.tool_calls) ||
        response.tool_calls.length + issued.size > MAX_TOOLS) {
      throw new Error('Invalid workspace inference response');
    }
    const content = response.content ? [{ type: 'text', text: response.content }] : [];
    for (const call of response.tool_calls) {
      if (!isObject(call) || typeof call.id !== 'string' || !call.id.length || call.id.length > 100 ||
          issued.has(call.id) || !tools.has(call.name) || !isObject(call.arguments)) {
        throw new Error('Invalid workspace tool call');
      }
      issued.add(call.id);
      content.push({ type: 'toolCall', id: call.id, name: call.name, arguments: call.arguments });
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
    [{ role: 'user', content: input.content, timestamp: Date.now() }],
    { systemPrompt: '', messages: [], tools: [...tools.values()] },
    {
      model: MODEL,
      toolExecution: 'sequential',
      // The broker retains the authorized prompt, model messages and tool results.
      convertToLlm: () => [],
      shouldStopAfterTurn: () => signal.aborted,
    },
    event => {
      if (event.type === 'tool_execution_end' && event.isError) {
        controller.abort();
      }
    },
    signal,
    streamFn,
  );

  signal.throwIfAborted();
  if (!terminalResponse) {
    throw new Error('Workspace round did not complete');
  }
}

try {
  await run(JSON.parse(readFileSync(0, 'utf8')));
  process.stdout.write('{"kind":"completed"}\n');
} catch {
  // Keep capabilities, tool arguments and model responses out of worker output.
  process.exitCode = 1;
}
