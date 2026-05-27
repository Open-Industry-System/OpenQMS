import client from "./client";
import type {
  SCARListResponse,
  SupplierSCAR,
  SCARCreate,
  SCARUpdate,
  SCARTransitionRequest,
  SCARLinkCAPARequest,
} from "../types";

export async function listSCARs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  supplier_id?: string;
  source_type?: string;
}): Promise<SCARListResponse> {
  const res = await client.get("/scars", { params });
  return res.data;
}

export async function getSCAR(id: string): Promise<SupplierSCAR> {
  const res = await client.get(`/scars/${id}`);
  return res.data;
}

export async function createSCAR(data: SCARCreate): Promise<SupplierSCAR> {
  const res = await client.post("/scars", data);
  return res.data;
}

export async function updateSCAR(id: string, data: SCARUpdate): Promise<SupplierSCAR> {
  const res = await client.put(`/scars/${id}`, data);
  return res.data;
}

export async function transitionSCAR(id: string, data: SCARTransitionRequest): Promise<SupplierSCAR> {
  const res = await client.post(`/scars/${id}/transition`, data);
  return res.data;
}

export async function linkCAPA(id: string, data: SCARLinkCAPARequest): Promise<SupplierSCAR> {
  const res = await client.post(`/scars/${id}/link-capa`, data);
  return res.data;
}
