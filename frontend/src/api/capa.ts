import client from "./client";
import type { CAPAReport, CAPAListResponse, D7RecommendationResponse } from "../types";

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
  skipReasons?: { d7_skip_reasons?: Array<{ fmea_id: string; node_id: string; reason: string }> }
): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/advance`, skipReasons ?? {});
  return resp.data;
}

export async function getD7Recommendations(id: string): Promise<D7RecommendationResponse> {
  const resp = await client.get(`/capa/${id}/d7-fmea-recommendations`);
  return resp.data;
}

export async function linkFMEA(id: string, fmea_id: string): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/link-fmea`, null, {
    params: { fmea_id },
  });
  return resp.data;
}
