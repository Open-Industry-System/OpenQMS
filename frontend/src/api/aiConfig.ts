import client from "./client";

export interface AIConfig {
  llm_provider: string;
  llm_api_key: string;
  llm_model: string;
  llm_base_url: string;
  llm_timeout: number;
  capa_draft_llm_timeout: number;
  report_llm_timeout: number;
  embedding_provider: string;
  embedding_api_key: string;
  embedding_model: string;
  embedding_base_url: string;
  embedding_dimensions: number;
  search_vector_weight: number;
  search_fulltext_weight: number;
}

export async function getAIConfig(): Promise<AIConfig> {
  const { data } = await client.get("/admin/ai-config");
  return data;
}

export async function updateAIConfig(config: AIConfig): Promise<AIConfig> {
  const { data } = await client.put("/admin/ai-config", config);
  return data;
}

export interface ProviderTestResult {
  ok: boolean;
  latency_ms: number | null;
  detail: string | null;
}

export interface AIConfigTestResult {
  llm: ProviderTestResult;
  embedding: ProviderTestResult;
}

export async function testAIConfig(config: AIConfig): Promise<AIConfigTestResult> {
  const { data } = await client.post("/admin/ai-config/test", config);
  return data;
}
