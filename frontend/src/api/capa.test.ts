import { describe, it, expect, vi, beforeEach } from "vitest";
import client from "./client";

vi.mock("./client", () => ({
  default: { post: vi.fn(), get: vi.fn(), patch: vi.fn() },
}));

import {
  adoptRecommendation, listVerifications, createVerification, updateVerification,
  recordD7Action, listD7Actions, autoFillD7,
} from "./capa";

beforeEach(() => vi.clearAllMocks());

describe("capa verification/d7 api", () => {
  it("adoptRecommendation posts to adopt-recommendation", async () => {
    (client.post as any).mockResolvedValue({ data: { adoption_id: "a1", d_step: "d4", field_value: "x" } });
    const r = await adoptRecommendation("c1", { d_step: "d4", adopted_text: "x", source: "fmea_graph" });
    expect(client.post).toHaveBeenCalledWith("/capa/c1/adopt-recommendation",
      { d_step: "d4", adopted_text: "x", source: "fmea_graph" });
    expect(r.field_value).toBe("x");
  });

  it("createVerification posts and returns record", async () => {
    (client.post as any).mockResolvedValue({ data: { verification_id: "v1", is_verified: true } });
    const r = await createVerification("c1", { root_cause_text: "rc", is_verified: true });
    expect(client.post).toHaveBeenCalledWith("/capa/c1/root-cause-verifications",
      { root_cause_text: "rc", is_verified: true });
    expect(r.verification_id).toBe("v1");
  });

  it("autoFillD7 posts to d7-auto-fill", async () => {
    (client.post as any).mockResolvedValue({ data: { action_id: "a1", prevention_control_node_id: "ctrl", prevention_control_name_after: "监控", is_new_control: true } });
    const r = await autoFillD7("c1", { fmea_id: "f1", failure_mode_node_id: "fm", failure_cause_node_id: "c", match_source: "linked" });
    expect(client.post).toHaveBeenCalledWith("/capa/c1/d7-auto-fill",
      { fmea_id: "f1", failure_mode_node_id: "fm", failure_cause_node_id: "c", match_source: "linked" });
    expect(r.is_new_control).toBe(true);
  });
});
