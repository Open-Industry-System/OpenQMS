import client from "./client";
import type { FMEADocument, FMEAListResponse, GraphData } from "../types";

export async function listFMEAs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  product_line?: string;
  high_rpn?: boolean;
  fmea_type?: "PFMEA" | "DFMEA";
  search?: string;
}): Promise<FMEAListResponse> {
  const resp = await client.get("/fmea", { params });
  return resp.data;
}

export async function getFMEA(id: string): Promise<FMEADocument> {
  const resp = await client.get(`/fmea/${id}`);
  return resp.data;
}

export async function createFMEA(data: {
  title: string;
  document_no: string;
  fmea_type: string;
}): Promise<FMEADocument> {
  const resp = await client.post("/fmea", data);
  return resp.data;
}

export async function updateFMEA(
  id: string,
  data: {
    title?: string;
    graph_data?: GraphData;
    lock_version?: number;
    confirmed_latest_lock_version?: number;
  }
): Promise<FMEADocument> {
  const resp = await client.put(`/fmea/${id}`, data);
  return resp.data;
}

export async function transitionFMEA(
  id: string,
  target_status: string
): Promise<FMEADocument> {
  const resp = await client.post(`/fmea/${id}/transition`, { target_status });
  return resp.data;
}

export async function deleteFMEA(id: string): Promise<void> {
  await client.delete(`/fmea/${id}`);
}
