import { act, renderHook, cleanup } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../store/authStore";
import { useAgentTaskActivity, readAgentIdentity } from "./useAgentTaskActivity";
import type { ActivityPage } from "../../types/agentTask";
import { getTaskActivity } from "../../api/agentTasks";
vi.mock("../../api/agentTasks", async () => ({ ...await vi.importActual("../../api/agentTasks"), getTaskActivity: vi.fn() }));
const task = "00000000-0000-4000-8000-000000000001";
const run = "00000000-0000-4000-8000-000000000002";
const page = (lo: number, hi: number, cursor: number | null = null, w = hi): ActivityPage => ({
  task_id: task,
  task_status: "ready",
  run_id: run,
  run_status: "active",
  lease_epoch: 1,
  window_end_sequence: w,
  next_before_sequence: cursor,
  items: Array.from({ length: Math.max(0, hi - lo + 1) }, (_, i) => ({
    sequence: lo + i,
    kind: "ack",
    created_at: "2026-10-01T00:00:00Z",
    data: { batch_id: run, state: "received" }
  }))
});
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}
const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};
const setup = () => renderHook((props) => useAgentTaskActivity(props), {
  initialProps: {
    taskId: task,
    identity: readAgentIdentity(),
    credential: "jwt",
    open: true,
    requestEpoch: 0
  }
});
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(getTaskActivity).mockReset();
  localStorage.clear();
  localStorage.setItem("access_token", "jwt");
  useAuthStore.setState({ user: { user_id: "user1" } as any, token: "jwt" });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
describe("fresh bounded whole activity cycle", () => {
  it("atomically replaces both pages using THIS latest cursor and W; retains 51–60", async () => {
    const history = deferred<any>();
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(51, 100, 51)).mockResolvedValueOnce(page(1, 50, null, 100)).mockResolvedValueOnce(page(61, 110, 61)).mockReturnValueOnce(history.promise);
    const { result } = setup();
    await flush();
    expect(result.current.page?.items).toHaveLength(100);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.page?.items[0].sequence).toBe(1); // no visible partial first page
    expect(getTaskActivity).toHaveBeenLastCalledWith(task, { page_size: 50, before_sequence: 61, window_end_sequence: 110 }, expect.any(AbortSignal));
    history.resolve(page(11, 60, null, 110));
    await flush();
    expect(result.current.page?.items.map(i => i.sequence)).toEqual(Array.from({ length: 100 }, (_, i) => i + 11));
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(62, 111, 62)).mockResolvedValueOnce(page(12, 61, null, 111));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.page?.items[result.current.page.items.length - 1]?.sequence).toBe(111);
  });
  it("reauthorizes both pages even when no new sequence; empty history is valid", async () => {
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(1, 3, 1)).mockResolvedValueOnce(page(1, 0, null, 3)).mockResolvedValueOnce(page(1, 3, 1)).mockResolvedValueOnce(page(1, 0, null, 3));
    const { result } = setup();
    await flush();
    expect(result.current.page?.items).toHaveLength(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(getTaskActivity).toHaveBeenCalledTimes(4);
  });
  it.each([403, 401, 404])("second-page %s immediately withdraws ALL content and never publishes staged data", async (status) => {
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(1, 2)).mockResolvedValueOnce(page(2, 3, 2)).mockRejectedValueOnce({ response: { status } });
    const { result } = setup();
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.page).toBeNull();
    expect(result.current.status).toBe("denied");
  });
  it.each(["network", "parse"])("second-page %s failure discards old and staged content; retries from new latest", async () => {
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(1, 2)).mockResolvedValueOnce(page(2, 3, 2)).mockRejectedValueOnce(new Error("invalid/network"));
    const { result } = setup();
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.page).toBeNull();
    expect(result.current.status).toBe("interrupted");
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(4, 5));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(getTaskActivity).toHaveBeenLastCalledWith(task, { page_size: 50 }, expect.any(AbortSignal));
    expect(result.current.page?.window_end_sequence).toBe(5);
  });
  it("one request cycle in flight; closed late history ignored; reopen latest new W", async () => {
    const history = deferred<any>();
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(2, 3, 2)).mockReturnValueOnce(history.promise);
    const { result, rerender } = setup();
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(getTaskActivity).toHaveBeenCalledTimes(2);
    const signal = vi.mocked(getTaskActivity).mock.calls[1][2];
    rerender({
      taskId: task,
      identity: readAgentIdentity(),
      credential: "jwt",
      open: false,
      requestEpoch: 0
    });
    expect(signal?.aborted).toBe(true);
    history.resolve(page(1, 1, null, 3));
    await flush();
    expect(result.current.page).toBeNull();
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(4, 5));
    rerender({
      taskId: task,
      identity: readAgentIdentity(),
      credential: "jwt",
      open: true,
      requestEpoch: 0
    });
    await flush();
    expect(getTaskActivity).toHaveBeenLastCalledWith(task, { page_size: 50 }, expect.any(AbortSignal));
  });
  it("hidden document aborts whole cycle and late first page cannot repopulate", async () => {
    const pending = deferred<any>();
    vi.mocked(getTaskActivity).mockReturnValueOnce(pending.promise);
    const { result } = setup();
    const signal = vi.mocked(getTaskActivity).mock.calls[0][2];
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(signal?.aborted).toBe(true);
    pending.resolve(page(1, 2));
    await flush();
    expect(result.current.page).toBeNull();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
  });
  it.each([page(1, 1, null, 2), {
    ...page(1, 1, null, 3), items: [{
      sequence: 1,
      kind: "ack",
      created_at: "2026-10-01T00:00:00Z",
      data: { batch_id: run, state: "received", html: "unsafe" }
    }]
  }])("rejects malformed second page or mismatched W and hides all content", async (bad) => {
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(1, 2)).mockResolvedValueOnce(page(2, 3, 2)).mockResolvedValueOnce(bad as ActivityPage);
    const { result } = setup();
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.page).toBeNull();
    expect(result.current.status).toBe("interrupted");
  });
  it("rejects latest cursor gaps", async () => {
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(3, 4, 2)).mockResolvedValueOnce(page(1, 1, null, 4));
    const { result } = setup();
    await flush();
    expect(result.current.page).toBeNull();
    expect(result.current.status).toBe("interrupted");
  });
  it("uses freshly authorized second-page current run metadata for controls", async () => {
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(2, 3, 2)).mockResolvedValueOnce({
      ...page(1, 1, null, 3),
      task_status: "paused",
      run_status: "paused",
      lease_epoch: 5
    });
    const { result } = setup();
    await flush();
    expect(result.current.page?.lease_epoch).toBe(5);
    expect(result.current.page?.task_status).toBe("paused");
  });
  it("hide then reopen within one event batch cannot revive old cycle", async () => {
    const old = deferred<any>();
    const fresh = deferred<any>();
    vi.mocked(getTaskActivity).mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
    const { result } = setup();
    const signal = vi.mocked(getTaskActivity).mock.calls[0][2];
    act(() => {
      Object.defineProperty(document, "hidden", { configurable: true, value: true });
      document.dispatchEvent(new Event("visibilitychange"));
      Object.defineProperty(document, "hidden", { configurable: true, value: false });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(signal?.aborted).toBe(true);
    old.resolve(page(1, 2));
    await flush();
    expect(result.current.page).toBeNull();
    fresh.resolve(page(4, 5));
    await flush();
    expect(result.current.page?.window_end_sequence).toBe(5);
  });
  it("never renders retained content during same-batch hidden-to-visible reopen", async () => {
    const pending = deferred<ActivityPage>();
    vi.mocked(getTaskActivity).mockResolvedValueOnce(page(1, 2)).mockReturnValueOnce(pending.promise);
    const renders: Array<ActivityPage | null> = [];
    renderHook(() => {
      const state = useAgentTaskActivity({
        taskId: task,
        identity: readAgentIdentity(),
        credential: "jwt",
        open: true,
        requestEpoch: 0
      });
      renders.push(state.page);
      return state;
    });
    await flush();
    expect(renders.some(p => p !== null)).toBe(true);
    renders.length = 0;
    act(() => {
      Object.defineProperty(document, "hidden", { configurable: true, value: true });
      document.dispatchEvent(new Event("visibilitychange"));
      Object.defineProperty(document, "hidden", { configurable: true, value: false });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(renders.every(p => p === null)).toBe(true);
  });
  it("old task and tenant responses cannot replace current content", async () => {
    const old = deferred<any>();
    vi.mocked(getTaskActivity).mockReturnValueOnce(old.promise).mockResolvedValueOnce({ ...page(4, 5), task_id: run });
    const { result, rerender } = setup();
    rerender({
      taskId: run,
      identity: readAgentIdentity(),
      credential: "jwt",
      open: true,
      requestEpoch: 0
    });
    await flush();
    old.resolve(page(1, 2));
    await flush();
    expect(result.current.page?.task_id).toBe(run);
    const tenant = deferred<any>();
    vi.mocked(getTaskActivity).mockReturnValueOnce(tenant.promise);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    localStorage.setItem("tenant_slug", "other");
    tenant.resolve({ ...page(6, 7), task_id: run });
    await flush();
    expect(result.current.page).toBeNull();
  });
});
