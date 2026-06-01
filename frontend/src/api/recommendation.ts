import client from "./client";

export interface Suggestion {
  name: string;
  confidence: number;
  source: "rule" | "llm";
  explanation: string;
}

export interface RecommendRequest {
  trigger_type: string;
  context: Record<string, unknown>;
}

export interface RecommendResponse {
  suggestions: Suggestion[];
  source: "rule" | "hybrid" | "rule_fallback";
  cached: boolean;
  llm_available: boolean;
}

export async function getRecommendations(
  fmeaId: string,
  request: RecommendRequest,
  signal?: AbortSignal
): Promise<RecommendResponse> {
  const { data } = await client.post(`/fmea/${fmeaId}/recommend`, request, { signal });
  return data;
}
