import client from "./client";
import type {
  KnowledgeEntryDetail,
  KnowledgeEntryListResponse,
  KnowledgeEntrySummary,
} from "../types";

export async function listKnowledgeEntries(params: {
  page?: number;
  page_size?: number;
  product_line_code?: string;
  factory_id?: string;
  source_type?: string;
  q?: string;
}): Promise<KnowledgeEntryListResponse> {
  const resp = await client.get("/knowledge/entries", { params });
  return resp.data;
}

export async function getKnowledgeEntry(id: string): Promise<KnowledgeEntryDetail> {
  const resp = await client.get(`/knowledge/entries/${id}`);
  return resp.data;
}

/** Find the CAPA-sourced knowledge entry for a closed 8D, if any. */
export async function findCapaKnowledgeEntry(
  capaId: string,
  opts?: { document_no?: string; product_line_code?: string },
): Promise<KnowledgeEntrySummary | null> {
  const resp = await listKnowledgeEntries({
    source_type: "capa",
    product_line_code: opts?.product_line_code,
    q: opts?.document_no,
    page: 1,
    page_size: 50,
  });
  return resp.items.find((item) => item.source_id === capaId) ?? null;
}
