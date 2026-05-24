import client from "./client";
import type { CAPAReport, CAPAListResponse } from "../types";

export async function listCAPAs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  product_line?: string;
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

export async function advanceCAPA(id: string): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/advance`);
  return resp.data;
}

export async function linkFMEA(id: string, fmea_id: string): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/link-fmea`, null, {
    params: { fmea_id },
  });
  return resp.data;
}
