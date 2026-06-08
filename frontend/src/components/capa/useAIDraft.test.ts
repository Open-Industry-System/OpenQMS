import { renderHook, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { useAIDraft } from "./useAIDraft";
import * as api from "../../api/capaDraft";

vi.mock("../../api/capaDraft");

const mockGenerateDraft = vi.mocked(api.generateDraft);

describe("useAIDraft", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("starts with idle state", () => {
    const { result } = renderHook(() => useAIDraft());
    expect(result.current.loading).toBe(false);
    expect(result.current.draft).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.tempUnavailable).toBe(false);
  });

  it("sets loading and clears error on generate", async () => {
    mockGenerateDraft.mockImplementation(
      () => new Promise(() => {}) // never resolves
    );
    const { result } = renderHook(() => useAIDraft());

    act(() => {
      result.current.generate("report-1", "d2", "structured");
    });

    expect(result.current.loading).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("stores draft on success", async () => {
    const fakeResp = {
      content: "问题陈述：测试",
      structured_data: { problem_statement: "测试" },
      request_id: "abc",
      step: "d2",
    };
    mockGenerateDraft.mockResolvedValue(fakeResp);

    const { result } = renderHook(() => useAIDraft());

    await act(async () => {
      result.current.generate("report-1", "d2", "structured");
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.draft).toEqual(fakeResp);
    expect(result.current.error).toBeNull();
  });

  it("handles 409 as warning", async () => {
    mockGenerateDraft.mockRejectedValue({
      response: { status: 409, data: { detail: "需先完成前置步骤" } },
    });

    const { result } = renderHook(() => useAIDraft());

    await act(async () => {
      result.current.generate("report-1", "d3", "structured");
    });

    expect(result.current.error).toBe("需先完成前置步骤");
    expect(result.current.errorLevel).toBe("warning");
  });

  it("handles 503 as tempUnavailable", async () => {
    mockGenerateDraft.mockRejectedValue({
      response: { status: 503, data: { detail: "unavailable" } },
    });

    const { result } = renderHook(() => useAIDraft());

    await act(async () => {
      result.current.generate("report-1", "d2", "structured");
    });

    expect(result.current.tempUnavailable).toBe(true);
    expect(result.current.errorLevel).toBe("error");
  });

  it("clear resets all state", async () => {
    mockGenerateDraft.mockResolvedValue({
      content: "test",
      structured_data: null,
      request_id: "abc",
      step: "d2",
    });

    const { result } = renderHook(() => useAIDraft());

    await act(async () => {
      result.current.generate("report-1", "d2", "structured");
    });
    expect(result.current.draft).not.toBeNull();

    act(() => {
      result.current.clear();
    });
    expect(result.current.draft).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.tempUnavailable).toBe(false);
  });

  it("undo saves and restores snapshots", () => {
    const { result } = renderHook(() => useAIDraft());

    expect(result.current.canUndo("d2_description")).toBe(false);

    act(() => {
      result.current.saveUndo("d2_description", "original content");
    });
    expect(result.current.canUndo("d2_description")).toBe(true);

    let restored: string | undefined;
    act(() => {
      restored = result.current.undo("d2_description");
    });
    expect(restored).toBe("original content");
    expect(result.current.canUndo("d2_description")).toBe(false);
  });

  it("undo returns undefined when no snapshot", () => {
    const { result } = renderHook(() => useAIDraft());

    let restored: string | undefined;
    act(() => {
      restored = result.current.undo("d2_description");
    });
    expect(restored).toBeUndefined();
  });
});
