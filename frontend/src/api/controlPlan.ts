import client from "./client";
import type { ControlPlan, ControlPlanListResponse } from "../types";

export async function listControlPlans(params: {
  page?: number;
  page_size?: number;
}): Promise<ControlPlanListResponse> {
  const resp = await client.get("/control-plans", { params });
  return resp.data;
}

export async function getControlPlan(id: string): Promise<ControlPlan> {
  const resp = await client.get(`/control-plans/${id}`);
  return resp.data;
}

export async function createControlPlan(data: {
  title: string;
  document_no: string;
  fmea_ref_id?: string;
  product_line_code?: string;
  phase?: string;
  part_no?: string;
  part_name?: string;
  contact_info?: string;
  drawing_rev?: string;
  org_factory?: string;
  core_group?: string;
}): Promise<ControlPlan> {
  const resp = await client.post("/control-plans", data);
  return resp.data;
}

export async function updateControlPlan(
  id: string,
  data: {
    title?: string;
    fmea_ref_id?: string;
    product_line_code?: string;
    phase?: string;
    part_no?: string;
    part_name?: string;
    contact_info?: string;
    drawing_rev?: string;
    org_factory?: string;
    core_group?: string;
    items?: ControlPlan["items"];
  }
): Promise<ControlPlan> {
  const resp = await client.put(`/control-plans/${id}`, data);
  return resp.data;
}

export async function deleteControlPlan(id: string): Promise<{ message: string }> {
  const resp = await client.delete(`/control-plans/${id}`);
  return resp.data;
}

export async function importFromFMEA(
  id: string,
  fmeaId: string,
  stepNos?: string[]
): Promise<{ imported_count: number }> {
  const resp = await client.post(`/control-plans/${id}/import-from-fmea`, {
    fmea_id: fmeaId,
    step_nos: stepNos,
  });
  return resp.data;
}

export async function checkStaleItems(
  id: string
): Promise<{
  stale_items: Array<{
    item_id: string;
    step_no: string;
    status: string;
    diff_fields: string[];
  }>;
}> {
  const resp = await client.get(`/control-plans/${id}/stale-check`);
  return resp.data;
}

export async function approveControlPlan(id: string): Promise<ControlPlan> {
  const resp = await client.post(`/control-plans/${id}/approve`);
  return resp.data;
}
