import client from "./client";
import type {
  CharacteristicImportPreview,
  ControlPlan,
  ControlPlanItem,
  ControlPlanListResponse,
  ImportFromFMEARequest,
} from "../types";

export type ControlPlanItemWrite = Omit<ControlPlanItem, "source_characteristic_ref">;

function toControlPlanItemWrite(item: ControlPlanItem): ControlPlanItemWrite {
  const {
    item_id,
    step_no,
    process_name,
    equipment,
    characteristic_no,
    product_characteristic,
    process_characteristic,
    special_class,
    specification_tolerance,
    evaluation_method,
    sample_size,
    sample_frequency,
    control_method,
    reaction_plan,
    source_fmea_node_id,
    sop_ref,
    spc_chart_id,
    gauge_id,
    sort_order,
  } = item;
  return {
    item_id,
    step_no,
    process_name,
    equipment,
    characteristic_no,
    product_characteristic,
    process_characteristic,
    special_class,
    specification_tolerance,
    evaluation_method,
    sample_size,
    sample_frequency,
    control_method,
    reaction_plan,
    source_fmea_node_id,
    sop_ref,
    spc_chart_id,
    gauge_id,
    sort_order,
  };
}

export async function listControlPlans(params: {
  page?: number;
  page_size?: number;
  product_line?: string;
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
    items?: ControlPlanItem[];
    lock_version?: number;
    confirmed_latest_lock_version?: number;
  }
): Promise<ControlPlan> {
  const payload = data.items
    ? { ...data, items: data.items.map(toControlPlanItemWrite) }
    : data;
  const resp = await client.put(`/control-plans/${id}`, payload);
  return resp.data;
}

export async function deleteControlPlan(id: string): Promise<{ message: string }> {
  const resp = await client.delete(`/control-plans/${id}`);
  return resp.data;
}

export async function previewImportFromFMEA(
  id: string,
  data: Pick<ImportFromFMEARequest, "fmea_id" | "source_fmea_version_id" | "expected_lock_version" | "step_ids">
): Promise<CharacteristicImportPreview> {
  const resp = await client.post(`/control-plans/${id}/import-from-fmea/preview`, data);
  return resp.data;
}

export async function applyImportFromFMEA(
  id: string,
  data: Required<Pick<ImportFromFMEARequest, "fmea_id" | "source_fmea_version_id" | "expected_lock_version" | "step_ids" | "preview_digest" | "selected_candidate_keys">>
): Promise<{ imported_count: number; items: ControlPlanItem[] }> {
  const resp = await client.post(`/control-plans/${id}/import-from-fmea`, data);
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

// ─── CSR Sync ───

export async function syncCSRToControlPlan(planId: string, customerIds: string[]): Promise<ControlPlan> {
  const resp = await client.post(`/control-plans/${planId}/sync-csr`, { customer_ids: customerIds });
  return resp.data;
}
