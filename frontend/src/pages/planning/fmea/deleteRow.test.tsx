import { describe, it, expect } from "vitest";
// deleteRow is an inline useCallback; test via the exported page is heavy.
// Instead, extract the deletion plan into a pure helper tested here.
import { planCauseDeletion } from "./deleteRowHelpers";

describe("planCauseDeletion", () => {
  it("deletes only the cause + private controls + CAUSE_OF, keeps mode and effects", () => {
    const row = {
      key: "row_fn1_fm1_fc1",
      functionNodeId: "fn1",
      failureModeNodeId: "fm1",
      failureEffectNodeIds: ["fe1", "fe2"],
      failureCauseNodeId: "fc1",
      preventionControlIds: ["pc1"],
      detectionControlIds: ["dc1"],
      recommendedActionIds: ["ra1"],
    };
    const allRows = [
      { ...row, key: "row_fn1_fm1_fc1" },
      { ...row, key: "row_fn1_fm1_fc2", failureCauseNodeId: "fc2", preventionControlIds: ["pc2"], detectionControlIds: ["dc2"], recommendedActionIds: [] },
    ];
    const result = planCauseDeletion(row, allRows);
    expect(result.nodeIdsToDelete).toEqual(new Set(["fc1", "pc1", "dc1", "ra1"]));
    expect(result.nodeIdsToDelete).not.toContain("fm1");
    expect(result.nodeIdsToDelete).not.toContain("fe1");
    expect(result.nodeIdsToDelete).not.toContain("fe2");
  });

  it("deletes private controls even when last cause (mode still kept)", () => {
    const row = {
      key: "row_fn1_fm1_fc1",
      functionNodeId: "fn1",
      failureModeNodeId: "fm1",
      failureEffectNodeIds: ["fe1"],
      failureCauseNodeId: "fc1",
      preventionControlIds: ["pc1"],
      detectionControlIds: ["dc1"],
      recommendedActionIds: [],
    };
    const result = planCauseDeletion(row, [row]);
    expect(result.nodeIdsToDelete).toEqual(new Set(["fc1", "pc1", "dc1"]));
    expect(result.nodeIdsToDelete).not.toContain("fm1");
  });
});
