import client from "./client";

export interface Suggestion {
  name: string;
  confidence: number;
  source: "rule" | "graph" | "llm";
  explanation: string;
  source_fmea_id?: string;
  source_document_no?: string;
  source_product_line_code?: string;
  source_product_line_name?: string;
  source_node_type?: string;
  source_node_id?: string;
  similarity_score?: number;
  match_reason?: string;
}

export interface RecommendRequest {
  trigger_type: string;
  context: Record<string, unknown>;
  scope?: "global" | "current_product_line";
  include_graph?: boolean;
}

export interface RecommendResponse {
  suggestions: Suggestion[];
  source: "rule" | "graph" | "hybrid" | "rule_fallback" | "graph_enriched";
  cached: boolean;
  llm_available: boolean;
  graph_match_count: number;
  effective_scope: "global" | "current_product_line";
}

export async function getRecommendations(
  fmeaId: string,
  request: RecommendRequest,
  signal?: AbortSignal
): Promise<RecommendResponse> {
  const { data } = await client.post(`/fmea/${fmeaId}/recommend`, request, { signal });
  return data;
}
