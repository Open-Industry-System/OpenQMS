import client from "./client";
import i18n from "../i18n";

export interface Suggestion {
  name: string;
  confidence: number;
  source: "rule" | "graph" | "semantic_search" | "lessons_learned" | "llm";
  explanation: string;
  recommendation_id?: string;
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
  scope?: "global" | "current_product_type" | "current_product_line";
  include_graph?: boolean;
}

export interface RecommendResponse {
  suggestions: Suggestion[];
  source: "rule" | "graph" | "hybrid" | "rule_fallback" | "graph_enriched";
  cached: boolean;
  llm_available: boolean;
  graph_match_count: number;
  effective_scope: "global" | "current_product_type" | "current_product_line";
}

export async function getRecommendations(
  fmeaId: string,
  request: RecommendRequest,
  signal?: AbortSignal
): Promise<RecommendResponse> {
  // The global axios client timeout is 10s, but the backend recommendation
  // pipeline's LLM leg is bounded by llm_timeout (clamped >=15s; real Ark call
  // ~9-15s). A 10s timeout aborts the request before the backend finishes, so
  // the caller's catch block fires ("AI recommend failed"). Override per-request
  // to wait long enough for the backend to self-bound. Must exceed the
  // configured llm_timeout (see /admin/ai-config); 45s covers 15-30s + buffer.
  // 携带当前 UI 语言（i18n.language, 如 en-US）到 context.language，后端据此
  // 追加英文输出指令，让 AI 建议名跟随界面语言（缺陷修复 #7）。
  const payload = {
    ...request,
    context: { ...request.context, language: i18n.language },
  };
  const { data } = await client.post(`/fmea/${fmeaId}/recommend`, payload, {
    signal,
    timeout: 45000,
  });
  return data;
}
