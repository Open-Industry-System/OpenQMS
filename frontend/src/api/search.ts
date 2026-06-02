import client from "./client";

export interface SearchResultItem {
  entity_type: string;
  entity_id: string;
  node_id: string | null;
  entity_field: string;
  chunk_text: string;
  score: number;
  source: "vector" | "fulltext" | "hybrid";
  metadata: Record<string, unknown>;
  product_line_code: string | null;
}

export interface SemanticSearchResponse {
  results: SearchResultItem[];
  total: number;
  query_time_ms: number;
}

export interface QASource {
  entity_type: string;
  entity_id: string;
  document_no: string;
  chunk_text: string;
  relevance_score: number;
}

export interface QAResponse {
  answer: string;
  sources: QASource[];
  llm_available: boolean;
  query_time_ms: number;
}

export interface QARequest {
  question: string;
  product_line_code?: string;
  max_context_chunks?: number;
}

export async function semanticSearch(params: {
  q: string;
  entity_types?: string;
  product_line_code?: string;
  limit?: number;
}, signal?: AbortSignal): Promise<SemanticSearchResponse> {
  const { data } = await client.get("/search/semantic", { params, signal });
  return data;
}

export async function askQuestion(
  request: QARequest,
  signal?: AbortSignal,
): Promise<QAResponse> {
  const { data } = await client.post("/search/ask", request, { signal });
  return data;
}
