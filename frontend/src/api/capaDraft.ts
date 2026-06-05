import client from "./client";
import type { DraftRequest, DraftResponse, DraftCapabilitiesResponse } from "../types";

export async function getDraftCapabilities(
  reportId: string
): Promise<DraftCapabilitiesResponse> {
  const resp = await client.get(`/capa/${reportId}/draft/capabilities`);
  return resp.data;
}

export async function generateDraft(
  reportId: string,
  step: string,
  data: DraftRequest
): Promise<DraftResponse> {
  const resp = await client.post(`/capa/${reportId}/draft/${step}`, data);
  return resp.data;
}
