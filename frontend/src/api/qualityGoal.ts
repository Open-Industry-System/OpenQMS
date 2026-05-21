import client from "./client";
import type { QualityGoal, QualityGoalListResponse } from "../types";

export async function listQualityGoals(params: {
  page?: number;
  page_size?: number;
  level?: number;
  product_line?: string;
  status?: string;
  period?: string;
}): Promise<QualityGoalListResponse> {
  const resp = await client.get("/quality-goals", { params });
  return resp.data;
}

export async function getQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.get(`/quality-goals/${id}`);
  return resp.data;
}

export async function createQualityGoal(data: {
  parent_id?: string | null;
  level: number;
  product_line?: string | null;
  name: string;
  target_value: string;
  unit: string;
  period: string;
  owner_id: string;
  description?: string | null;
}): Promise<QualityGoal> {
  const resp = await client.post("/quality-goals", data);
  return resp.data;
}

export async function updateQualityGoal(
  id: string,
  data: {
    name?: string;
    target_value?: string;
    actual_value?: string;
    unit?: string;
    period?: string;
    owner_id?: string;
    description?: string | null;
  }
): Promise<QualityGoal> {
  const resp = await client.put(`/quality-goals/${id}`, data);
  return resp.data;
}

export async function deleteQualityGoal(id: string): Promise<void> {
  await client.delete(`/quality-goals/${id}`);
}

export async function submitQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/submit`);
  return resp.data;
}

export async function withdrawQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/withdraw`);
  return resp.data;
}

export async function approveQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/approve`);
  return resp.data;
}

export async function rejectQualityGoal(id: string, reject_reason: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/reject`, { reject_reason });
  return resp.data;
}

export async function archiveQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/archive`);
  return resp.data;
}

export async function updateActualValue(id: string, actual_value: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/actual-value`, { actual_value });
  return resp.data;
}
