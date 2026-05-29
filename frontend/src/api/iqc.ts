import client from "./client";
import { downloadExcel, uploadExcel, type ImportResult } from "../utils/excel";
import type {
  IqcMaterial,
  IqcInspectionTemplate,
  IqcInspection,
  AqlPlan,
  IqcStats,
} from "../types";

// ─── Materials ───

export async function listMaterials(params?: Record<string, unknown>): Promise<{
  items: IqcMaterial[];
  total: number;
  page: number;
  page_size: number;
}> {
  const resp = await client.get("/iqc/materials", { params });
  return resp.data;
}

export async function createMaterial(data: {
  part_no: string;
  part_name: string;
  part_spec?: string | null;
  material_type?: string;
  default_aql?: number | null;
  default_inspection_level?: string | null;
  unit?: string | null;
  product_line_code?: string;
}): Promise<IqcMaterial> {
  const resp = await client.post("/iqc/materials", data);
  return resp.data;
}

export async function getMaterial(id: string): Promise<IqcMaterial> {
  const resp = await client.get(`/iqc/materials/${id}`);
  return resp.data;
}

export async function updateMaterial(
  id: string,
  data: Partial<IqcMaterial>
): Promise<IqcMaterial> {
  const resp = await client.put(`/iqc/materials/${id}`, data);
  return resp.data;
}

export async function deleteMaterial(id: string): Promise<void> {
  await client.delete(`/iqc/materials/${id}`);
}

// ─── Templates ───

export async function listTemplates(params?: Record<string, unknown>): Promise<{
  items: IqcInspectionTemplate[];
  total: number;
  page: number;
  page_size: number;
}> {
  const resp = await client.get("/iqc/templates", { params });
  return resp.data;
}

export async function createTemplate(data: {
  template_name: string;
  material_id: string;
  items: Record<string, unknown>[];
}): Promise<IqcInspectionTemplate> {
  const resp = await client.post("/iqc/templates", data);
  return resp.data;
}

export async function getTemplate(id: string): Promise<IqcInspectionTemplate> {
  const resp = await client.get(`/iqc/templates/${id}`);
  return resp.data;
}

export async function updateTemplate(
  id: string,
  data: { template_name: string; items: Record<string, unknown>[] }
): Promise<IqcInspectionTemplate> {
  const resp = await client.put(`/iqc/templates/${id}`, data);
  return resp.data;
}

export async function deleteTemplate(id: string): Promise<void> {
  await client.delete(`/iqc/templates/${id}`);
}

// ─── Inspections ───

export async function listInspections(params?: Record<string, unknown>): Promise<{
  items: IqcInspection[];
  total: number;
  page: number;
  page_size: number;
}> {
  const resp = await client.get("/iqc/inspections", { params });
  return resp.data;
}

export async function createInspection(data: Record<string, unknown>): Promise<IqcInspection> {
  const resp = await client.post("/iqc/inspections", data);
  return resp.data;
}

export async function getInspection(id: string): Promise<IqcInspection> {
  const resp = await client.get(`/iqc/inspections/${id}`);
  return resp.data;
}

export async function updateInspection(
  id: string,
  data: Partial<IqcInspection>
): Promise<IqcInspection> {
  const resp = await client.put(`/iqc/inspections/${id}`, data);
  return resp.data;
}

export async function deleteInspection(id: string): Promise<void> {
  await client.delete(`/iqc/inspections/${id}`);
}

export async function startInspection(id: string): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/start`);
  return resp.data;
}

export async function updateInspectionItems(
  id: string,
  items: Record<string, unknown>[]
): Promise<IqcInspection> {
  const resp = await client.put(`/iqc/inspections/${id}/items`, { items });
  return resp.data;
}

export async function judgeInspection(
  id: string,
  data: {
    inspection_result: string;
    defect_qty: number;
    defect_description?: string | null;
    sample_qty?: number | null;
  }
): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/judge`, data);
  return resp.data;
}

export async function requestReinspect(id: string): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/request-reinspect`);
  return resp.data;
}

export async function approveConcession(
  id: string,
  reason: string
): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/concession`, { reason });
  return resp.data;
}

export async function closeInspection(id: string): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/close`);
  return resp.data;
}

export async function triggerScar(id: string): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/trigger-scar`);
  return resp.data;
}

// ─── AQL ───

export async function calculateAql(data: {
  lot_qty: number;
  aql_level: number;
  inspection_level?: string;
}): Promise<AqlPlan> {
  const resp = await client.post("/iqc/calculate-aql", data);
  return resp.data;
}

// ─── Stats ───

export async function getIqcStats(params?: Record<string, unknown>): Promise<IqcStats> {
  const resp = await client.get("/iqc/stats", { params });
  return resp.data;
}

// ─── Import / Export ───

export async function downloadMaterialImportTemplate(): Promise<void> {
  await downloadExcel("/iqc/materials/import-template", {}, "iqc_material_import_template.xlsx");
}

export async function importMaterials(file: File, productLineCode?: string): Promise<ImportResult> {
  return uploadExcel("/iqc/materials/import", file, productLineCode ? { product_line_code: productLineCode } : {});
}
