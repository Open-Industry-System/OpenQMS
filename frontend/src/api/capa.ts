import client from "./client";
import type { CAPAReport, CAPAListResponse, D7RecommendationResponse, D4RecommendationResponse, D5RecommendationResponse, AdoptRequest, AdoptResponse, Verification, VerificationCreate, VerificationUpdate, D7NodeAction, D7NodeActionCreate, D7AutoFillRequest, D7AutoFillResponse } from "../types";

export async function listCAPAs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  product_line?: string;
  overdue?: boolean;
  pending_action?: boolean;
}): Promise<CAPAListResponse> {
  const resp = await client.get("/capa", { params });
  return resp.data;
}

export async function getCAPA(id: string): Promise<CAPAReport> {
  const resp = await client.get(`/capa/${id}`);
  return resp.data;
}

export async function createCAPA(data: {
  title: string;
  document_no: string;
  severity: string;
  due_date?: string;
  product_line_code?: string;
}): Promise<CAPAReport> {
  const resp = await client.post("/capa", data);
  return resp.data;
}

export async function updateCAPA(
  id: string,
  data: Record<string, unknown>
): Promise<CAPAReport> {
  const resp = await client.put(`/capa/${id}`, data);
  return resp.data;
}

export async function advanceCAPA(
  id: string,
  skipReasons?: { d7_skip_reasons?: Array<{ fmea_id: string | null; node_id: string; reason: string }> }
): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/advance`, skipReasons ?? {});
  return resp.data;
}

export async function getD7Recommendations(id: string): Promise<D7RecommendationResponse> {
  const resp = await client.get(`/capa/${id}/d7-fmea-recommendations`);
  return resp.data;
}

export async function getD4Recommendations(id: string): Promise<D4RecommendationResponse> {
  const resp = await client.get(`/capa/${id}/d4-fmea-recommendations`);
  return resp.data;
}

export async function getD5Recommendations(id: string): Promise<D5RecommendationResponse> {
  const resp = await client.get(`/capa/${id}/d5-fmea-recommendations`);
  return resp.data;
}

export async function linkFMEA(id: string, fmea_id: string): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/link-fmea`, null, {
    params: { fmea_id },
  });
  return resp.data;
}

export async function adoptRecommendation(capaId: string, req: AdoptRequest): Promise<AdoptResponse> {
  const resp = await client.post(`/capa/${capaId}/adopt-recommendation`, req);
  return resp.data;
}
export async function listVerifications(capaId: string): Promise<Verification[]> {
  const resp = await client.get(`/capa/${capaId}/root-cause-verifications`);
  return resp.data;
}
export async function createVerification(capaId: string, req: VerificationCreate): Promise<Verification> {
  const resp = await client.post(`/capa/${capaId}/root-cause-verifications`, req);
  return resp.data;
}
export async function updateVerification(capaId: string, vid: string, req: VerificationUpdate): Promise<Verification> {
  const resp = await client.patch(`/capa/${capaId}/root-cause-verifications/${vid}`, req);
  return resp.data;
}
export async function recordD7Action(capaId: string, req: D7NodeActionCreate): Promise<D7NodeAction> {
  const resp = await client.post(`/capa/${capaId}/d7-node-actions`, req);
  return resp.data;
}
export async function listD7Actions(capaId: string): Promise<D7NodeAction[]> {
  const resp = await client.get(`/capa/${capaId}/d7-node-actions`);
  return resp.data;
}
export async function autoFillD7(capaId: string, req: D7AutoFillRequest): Promise<D7AutoFillResponse> {
  const resp = await client.post(`/capa/${capaId}/d7-auto-fill`, req);
  return resp.data;
}
