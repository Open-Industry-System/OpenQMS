import { describe, it, expect } from "vitest";
import type { Suggestion } from "../recommendation";
import type { RecommendationAdoption } from "../fmea";

describe("adoption types", () => {
  it("Suggestion supports the 5 sources + recommendation_id", () => {
    const s: Suggestion = {
      name: "焊接电流不足",
      confidence: 0.8,
      source: "semantic_search",
      explanation: "",
      recommendation_id: "rec_abc123",
    };
    expect(s.recommendation_id).toBe("rec_abc123");
    expect(s.source).toBe("semantic_search");
  });

  it("RecommendationAdoption shape", () => {
    const a: RecommendationAdoption = {
      field_id: "fm_node_1",
      recommendation_id: "rec_abc123",
      source: "graph",
      stage_index: 0,
      adopted_text: "焊接电流不足",
    };
    expect(a.field_id).toBe("fm_node_1");
  });
});
