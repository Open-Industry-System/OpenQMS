import { afterEach, it, expect, vi } from "vitest";
import client from "./client";
const adapter = client.defaults.adapter;
afterEach(() => {
  client.defaults.adapter = adapter;
  localStorage.clear();
});
it("Agent user GET excludes factory scope while business GET retains factory injection", async () => {
  localStorage.setItem("access_token", "user-only");
  localStorage.setItem("current_factory_id", "factory-A");
  const seen: any[] = [];
  client.defaults.adapter = vi.fn(async (config) => {
    seen.push(config);
    return {
      data: {},
      status: 200,
      statusText: "OK",
      headers: {},
      config
    };
  });
  await client.get("/agent/tasks/availability");
  await client.get("/agent/tasks/task/activity", { params: { page_size: 50 } });
  await client.get("/capa");
  expect(seen[0].params?.factory_id).toBeUndefined();
  expect(seen[1].params).toEqual({ page_size: 50 });
  expect(seen[0].headers.Authorization).toBe("Bearer user-only");
  expect(seen[2].params.factory_id).toBe("factory-A");
});
it.each([401, 403])("Agent %s is rejected immediately so restricted visible content can be withdrawn", async (status) => {
  const seen: string[] = [];
  client.defaults.adapter = vi.fn(async (config) => {
    seen.push(config.url!);
    throw { config, response: { status, data: {} }, message: "denied" };
  });
  await expect(client.get("/agent/tasks/task/activity")).rejects.toMatchObject({ response: { status } });
  expect(seen).toEqual(["/agent/tasks/task/activity"]);
});

it('D4 text preview GET rejects UI factory injection without changing other CAPA reads', async () => {
  localStorage.setItem('current_factory_id', 'factory-A');
  const seen: any[] = [];
  client.defaults.adapter = async config => {
    seen.push(config);
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
  };
  await client.get('/capa/report/d4-text-preview/availability');
  await client.get('/capa/report/d4-text-preview/version');
  await client.get('/capa/report/root-cause-verifications');
  expect(seen.slice(0, 2).every(config => config.params?.factory_id === undefined)).toBe(true);
  expect(seen[2].params.factory_id).toBe('factory-A');
});

it.each([401, 403])('D4 text preview %s rejects immediately without refresh or body retry', async status => {
  const seen: string[] = [];
  client.defaults.adapter = async config => {
    seen.push(config.url!);
    throw { config, response: { status, data: {} } };
  };
  await expect(client.post('/capa/report/d4-text-preview', { replacement_terms: ['private'] }))
    .rejects.toMatchObject({ response: { status } });
  expect(seen).toEqual(['/capa/report/d4-text-preview']);
});


it.each([401, 403])('outcome reads and exact decision POST fail immediately on %s without refresh/replay', async status => {
  const seen: string[] = [];
  client.defaults.adapter = async config => {
    seen.push(config.url!);
    throw { config, response: { status, data: {} } };
  };
  await expect(client.get('/capa/report/outcome-review')).rejects.toMatchObject({ response: { status } });
  await expect(client.post('/capa/report/advance', { target_state: 'D8_CLOSURE' })).rejects.toMatchObject({ response: { status } });
  expect(seen).toEqual(['/capa/report/outcome-review', '/capa/report/advance']);
});
