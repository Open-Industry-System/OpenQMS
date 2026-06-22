import { describe, it, expect, vi, beforeEach } from "vitest";
import { getRecommendations } from "./recommendation";

vi.mock("./client", () => ({
  default: { post: vi.fn() },
}));

import client from "./client";

const mockedPost = vi.mocked(client.post);

const RESPONSE = {
  suggestions: [],
  source: "rule" as const,
  cached: false,
  llm_available: false,
  graph_match_count: 0,
  effective_scope: "current_product_line" as const,
};

describe("getRecommendations timeout", () => {
  beforeEach(() => mockedPost.mockReset());

  it("passes a per-request timeout that comfortably exceeds the backend LLM leg (>=30s)", async () => {
    // The global axios client timeout is 10s, but the backend recommendation
    // pipeline's LLM leg is bounded by llm_timeout (clamped >=15s; real Ark call
    // ~9-15s). A 10s frontend timeout aborts the request before the backend
    // finishes -> the caller's catch block fires ("AI recommend failed"). The
    // recommend call must wait long enough for the backend to self-bound.
    mockedPost.mockResolvedValueOnce({ data: RESPONSE });
    await getRecommendations("fmea-1", { trigger_type: "dfmea_tool", context: {} });
    const cfg = mockedPost.mock.calls[0][2] as { timeout?: number } | undefined;
    expect(cfg?.timeout).toBeGreaterThanOrEqual(30000);
  });
});