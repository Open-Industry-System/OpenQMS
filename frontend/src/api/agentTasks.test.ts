import { beforeEach, describe, expect, it, vi } from "vitest";
import client from "./client";
import { getTaskActivity, createTask, appendTaskMessage, controlTask, parseActivityPage } from "./agentTasks";
vi.mock("./client", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const id = "00000000-0000-4000-8000-000000000001";
const task = {
  task_id: id,
  target_capa_id: id,
  factory_id: id,
  preferred_installation_id: id,
  status: "ready",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z"
};
const page = {
  task_id: id,
  task_status: "ready",
  run_id: null,
  run_status: null,
  lease_epoch: null,
  window_end_sequence: 0,
  next_before_sequence: null,
  items: []
};
beforeEach(() => vi.clearAllMocks());
describe("user-only task wrapper", () => {
  it("forwards exact creation body and signal without authority fields", async () => {
    vi.mocked(client.post).mockResolvedValue({ data: task });
    const body = {
      report_id: id,
      installation_id: id,
      request_key: "key",
      initial_text: "text"
    };
    const signal = new AbortController().signal;
    expect(await createTask(body, signal)).toEqual(task);
    expect(client.post).toHaveBeenCalledWith("/agent/tasks", body, { signal });
  });
  it("forwards exact append and control idempotency bodies", async () => {
    vi.mocked(client.post).mockResolvedValueOnce({ data: { message_id: id, sequence: 1, state: "accepted" } }).mockResolvedValueOnce({
      data: {
        control_id: id,
        task_id: id,
        task_status: "paused",
        run_id: id,
        run_status: "paused",
        lease_epoch: 2
      }
    });
    const append = { content: "same", idempotency_key: "key" };
    await appendTaskMessage(id, append);
    expect(client.post).toHaveBeenNthCalledWith(1, `/agent/tasks/${id}/messages`, append, { signal: undefined });
    const control = {
      action: "pause" as const,
      run_id: id,
      expected_epoch: 1,
      idempotency_key: "key"
    };
    await controlTask(id, control);
    expect(client.post).toHaveBeenNthCalledWith(2, `/agent/tasks/${id}/control`, control, { signal: undefined });
  });
  it("strictly parses response JSON/shape and forwards stable bounded query", async () => {
    vi.mocked(client.get).mockResolvedValueOnce({ data: page }).mockResolvedValueOnce({ data: "{bad json" });
    const signal = new AbortController().signal;
    await getTaskActivity(id, { page_size: 50 }, signal);
    expect(client.get).toHaveBeenCalledWith(`/agent/tasks/${id}/activity`, { params: { page_size: 50 }, signal });
    await expect(getTaskActivity(id, { page_size: 50 }, signal)).rejects.toThrow();
  });
  it.each([{ ...page, items: Array(51).fill({}) }, { ...page, window_end_sequence: "0" }, { ...page, html: "<b>secret</b>" }, {
    ...page, items: [{
      sequence: 1,
      kind: "unknown",
      created_at: task.created_at,
      data: {}
    }]
  }, {
    ...page, items: [{
      sequence: 1,
      kind: "message",
      created_at: task.created_at,
      data: {
        message_id: id,
        sequence: 1,
        author_id: id,
        content: "x",
        data_class: "restricted",
        state: "accepted"
      }
    }]
  }])("rejects malformed/unknown page fields %j", bad => expect(() => parseActivityPage(bad)).toThrow());
});
