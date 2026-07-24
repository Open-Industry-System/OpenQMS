import { describe, it, expect, vi, beforeEach } from "vitest";
import client from "./client";
import type { StageRun, D4RecommendationResponse, AdoptRequest } from "../types";

vi.mock("./client", () => ({
  default: { post: vi.fn(), get: vi.fn(), patch: vi.fn() },
}));

import {
  adoptRecommendation, listVerifications, createVerification, updateVerification,
  recordD7Action, listD7Actions, autoFillD7, advanceCAPA, sinkKnowledge,
  parseKnowledgeSinkError, formatCapaAdvanceError,
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
    (client.post as any).mockResolvedValue({ data: { verification_id: "v1", conclusion: "passed" } });
    const r = await createVerification("c1", { root_cause_text: "rc", conclusion: "passed" });
    expect(client.post).toHaveBeenCalledWith("/capa/c1/root-cause-verifications",
      { root_cause_text: "rc", conclusion: "passed" });
    expect(r.verification_id).toBe("v1");
  });

  it("advanceCAPA adapts { capa, warning } and returns capa", async () => {
    const capa = { capa_id: "c1", document_no: "8D-2026-001" } as any;
    (client.post as any).mockResolvedValue({ data: { capa, warning: "D7 skipped" } });
    const r = await advanceCAPA("c1");
    expect(client.post).toHaveBeenCalledWith("/capa/c1/advance", {});
    expect(r.document_no).toBe("8D-2026-001");
  });

  it("autoFillD7 posts to d7-auto-fill", async () => {
    (client.post as any).mockResolvedValue({ data: { action_id: "a1", prevention_control_node_id: "ctrl", prevention_control_name_after: "监控", is_new_control: true } });
    const r = await autoFillD7("c1", { fmea_id: "f1", failure_mode_node_id: "fm", failure_cause_node_id: "c", match_source: "linked" });
    expect(client.post).toHaveBeenCalledWith("/capa/c1/d7-auto-fill",
      { fmea_id: "f1", failure_mode_node_id: "fm", failure_cause_node_id: "c", match_source: "linked" });
    expect(r.is_new_control).toBe(true);
  });
});

describe("capa knowledge sink api", () => {
  it("sinkKnowledge posts to sink-knowledge", async () => {
    (client.post as any).mockResolvedValue({
      data: {
        entry_id: "e1",
        source_type: "capa",
        source_id: "c1",
        document_no: "8D-2026-001",
        title: "t",
        embedding_status: "pending",
      },
    });
    const r = await sinkKnowledge("c1");
    expect(client.post).toHaveBeenCalledWith("/capa/c1/sink-knowledge");
    expect(r.embedding_status).toBe("pending");
  });

  it("parseKnowledgeSinkError maps blocked vs failed 422 detail.outcome", () => {
    const blocked = parseKnowledgeSinkError({
      response: {
        status: 422,
        data: { detail: { outcome: "blocked", reason: "llm_unavailable", message: "no llm" } },
      },
    });
    expect(blocked?.outcome).toBe("blocked");
    expect(blocked?.message).toBe("no llm");

    const failed = parseKnowledgeSinkError({
      response: {
        status: 422,
        data: { detail: { outcome: "failed", reason: "llm_failed", message: "timeout" } },
      },
    });
    expect(failed?.outcome).toBe("failed");

    expect(parseKnowledgeSinkError({ response: { data: { detail: "plain" } } })).toBeNull();
  });

  it("formatCapaAdvanceError uses outcome-specific labels", () => {
    const blockedMsg = formatCapaAdvanceError(
      { response: { data: { detail: { outcome: "blocked", message: "x" } } } },
      "fallback",
      { blocked: "BLOCKED", failed: "FAILED" },
    );
    expect(blockedMsg).toContain("BLOCKED");
    expect(blockedMsg).toContain("x");

    const failedMsg = formatCapaAdvanceError(
      { response: { data: { detail: { outcome: "failed", message: "y" } } } },
      "fallback",
      { blocked: "BLOCKED", failed: "FAILED" },
    );
    expect(failedMsg).toContain("FAILED");
    expect(failedMsg).toContain("y");
  });
});

describe("capa recommendation stages (Spec B)", () => {
  it("accepts a D4 response with stages and per-item stage_index", () => {
    const stages: StageRun[] = Array.from({ length: 12 }, (_, i) => ({
      index: i,
      name: `stage-${i}`,
      source: i % 2 === 0 ? "fmea_graph" : "llm",
      status: i < 10 ? "done" : "pending",
      hit_count: i * 2,
      summary: `summary ${i}`,
    }));
    const resp: D4RecommendationResponse = {
      stages,
      items: stages.map((s) => ({
        failure_cause_node_id: `cause-${s.index}`,
        failure_cause_name: "cause",
        failure_cause_desc: null,
        failure_mode_node_id: null,
        failure_mode_name: null,
        fmea_document_no: null,
        fmea_id: null,
        match_source: "fmea_graph",
        match_reason: "reason",
        related_d2_keywords: [],
        confidence: 0.5,
        source_capa_id: null,
        source_capa_document_no: null,
        source_product_line_code: null,
        stage_index: s.index,
      })),
    };
    expect(resp.stages).toHaveLength(12);
    expect(resp.items[0].stage_index).toBe(0);
    expect(resp.stages[11].status).toBe("pending");
  });

  it("adoptRecommendation sends stage_index in the POST body", async () => {
    (client.post as any).mockResolvedValue({ data: { adoption_id: "a1", d_step: "d5", field_value: "x" } });
    const req: AdoptRequest = { d_step: "d5", adopted_text: "control-x", source: "existing_control", stage_index: 2 };
    const r = await adoptRecommendation("c1", req);
    expect(client.post).toHaveBeenCalledWith(
      "/capa/c1/adopt-recommendation",
      expect.objectContaining({ stage_index: 2 }),
    );
    expect(r.d_step).toBe("d5");
  });
});
