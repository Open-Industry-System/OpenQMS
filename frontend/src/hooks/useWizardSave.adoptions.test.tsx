import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWizardSave } from "./useWizardSave";
import * as fmeaApi from "../api/fmea";

vi.mock("../api/fmea", () => ({
  updateFMEA: vi.fn(async (_id: string, _data: unknown) => ({ lock_version: 2, version: 2 })),
}));

const graph = { nodes: [], edges: [] } as never;

describe("useWizardSave adoptions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("forwards adoptions to updateFMEA", async () => {
    const { result } = renderHook(() => useWizardSave({ fmeaId: "f1" }));
    const adoptions = [{
      field_id: "fm1", recommendation_id: "rec_1", source: "graph",
      stage_index: 0, adopted_text: "焊接电流不足",
    }];
    await act(async () => {
      await result.current.immediateSave(graph, "t", "h", adoptions);
    });
    expect(fmeaApi.updateFMEA).toHaveBeenCalledWith(
      "f1",
      expect.objectContaining({ adoptions }),
    );
  });

  it("omits adoptions key when not provided", async () => {
    const { result } = renderHook(() => useWizardSave({ fmeaId: "f1" }));
    await act(async () => {
      await result.current.immediateSave(graph, "t", "h");
    });
    const data = (fmeaApi.updateFMEA as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect("adoptions" in data).toBe(false);
  });
});
