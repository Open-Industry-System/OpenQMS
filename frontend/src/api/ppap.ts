import client from "./client";
import type {
  PPAPListResponse,
  PPAPSubmission,
  PPAPCreate,
  PPAPElement,
  PPAPElementUpdate,
  PPAPTransitionRequest,
} from "../types";

export async function listPPAPs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  supplier_id?: string;
}): Promise<PPAPListResponse> {
  const res = await client.get("/ppap", { params });
  return res.data;
}

export async function getPPAP(id: string): Promise<PPAPSubmission> {
  const res = await client.get(`/ppap/${id}`);
  return res.data;
}

export async function createPPAP(data: PPAPCreate): Promise<PPAPSubmission> {
  const res = await client.post("/ppap", data);
  return res.data;
}

export async function updatePPAP(id: string, data: Partial<PPAPCreate>): Promise<PPAPSubmission> {
  const res = await client.put(`/ppap/${id}`, data);
  return res.data;
}

export async function updatePPAPElement(
  submissionId: string,
  elementId: string,
  data: PPAPElementUpdate,
): Promise<PPAPElement> {
  const res = await client.put(`/ppap/${submissionId}/elements/${elementId}`, data);
  return res.data;
}

export async function transitionPPAP(id: string, data: PPAPTransitionRequest): Promise<PPAPSubmission> {
  const res = await client.post(`/ppap/${id}/transition`, data);
  return res.data;
}

export async function deletePPAP(id: string): Promise<void> {
  await client.delete(`/ppap/${id}`);
}
