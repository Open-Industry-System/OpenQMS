import client from "./client";
import { downloadExcel, uploadExcel, type ImportResult } from "../utils/excel";
import type {
  Supplier,
  SupplierListResponse,
  SupplierCertification,
  SupplierEvaluation,
  SupplierStats,
  SupplierExpiryAlert,
  QualityDashboardResponse,
  SupplierQualityDetailResponse,
  SupplierCompareResponse,
} from "../types";

export async function getSupplierStats(): Promise<SupplierStats> {
  const resp = await client.get("/suppliers/stats");
  return resp.data;
}

export async function getExpiryAlerts(days = 90): Promise<SupplierExpiryAlert[]> {
  const resp = await client.get("/suppliers/expiry-alerts", { params: { days } });
  return resp.data;
}

export async function listSuppliers(params?: Record<string, unknown>): Promise<SupplierListResponse> {
  const resp = await client.get("/suppliers", { params });
  return resp.data;
}

export async function createSupplier(
  data: Omit<Supplier, "supplier_id" | "supplier_no" | "created_at" | "updated_at" | "status" | "created_by" | "reject_reason">
): Promise<Supplier> {
  const resp = await client.post("/suppliers", data);
  return resp.data;
}

export async function getSupplier(id: string): Promise<Supplier> {
  const resp = await client.get(`/suppliers/${id}`);
  return resp.data;
}

export async function updateSupplier(id: string, data: Partial<Supplier>): Promise<Supplier> {
  const resp = await client.put(`/suppliers/${id}`, data);
  return resp.data;
}

export async function deleteSupplier(id: string): Promise<void> {
  await client.delete(`/suppliers/${id}`);
}

export async function approveSupplier(id: string): Promise<Supplier> {
  const resp = await client.post(`/suppliers/${id}/approve`);
  return resp.data;
}

export async function rejectSupplier(id: string, reason: string): Promise<Supplier> {
  const resp = await client.post(`/suppliers/${id}/reject`, null, { params: { reason } });
  return resp.data;
}

export async function confirmApproved(id: string): Promise<Supplier> {
  const resp = await client.post(`/suppliers/${id}/confirm-approved`);
  return resp.data;
}

export async function suspendSupplier(id: string, reason: string): Promise<Supplier> {
  const resp = await client.post(`/suppliers/${id}/suspend`, null, { params: { reason } });
  return resp.data;
}

export async function reinstateSupplier(id: string): Promise<Supplier> {
  const resp = await client.post(`/suppliers/${id}/reinstate`);
  return resp.data;
}

export async function listCertifications(supplierId: string): Promise<SupplierCertification[]> {
  const resp = await client.get(`/suppliers/${supplierId}/certifications`);
  return resp.data.items;
}

export async function createCertification(
  supplierId: string,
  data: Omit<SupplierCertification, "cert_id" | "supplier_id" | "created_at" | "file_url">
): Promise<SupplierCertification> {
  const resp = await client.post(`/suppliers/${supplierId}/certifications`, data);
  return resp.data;
}

export async function updateCertification(
  supplierId: string,
  certId: string,
  data: Partial<SupplierCertification>
): Promise<SupplierCertification> {
  const resp = await client.put(`/suppliers/${supplierId}/certifications/${certId}`, data);
  return resp.data;
}

export async function deleteCertification(supplierId: string, certId: string): Promise<void> {
  await client.delete(`/suppliers/${supplierId}/certifications/${certId}`);
}

export async function listEvaluations(supplierId: string): Promise<SupplierEvaluation[]> {
  const resp = await client.get(`/suppliers/${supplierId}/evaluations`);
  return resp.data.items;
}

export async function createEvaluation(
  supplierId: string,
  data: Omit<SupplierEvaluation, "eval_id" | "supplier_id" | "created_at" | "capa_penalty" | "finding_penalty" | "premium_freight_penalty" | "customer_disruption_penalty" | "total_score" | "grade" | "evaluated_by">
): Promise<SupplierEvaluation> {
  const resp = await client.post(`/suppliers/${supplierId}/evaluations`, data);
  return resp.data;
}

// ─── Quality Dashboard ───

export async function getQualityDashboard(params?: {
  start_date?: string;
  end_date?: string;
  product_line_code?: string;
}): Promise<QualityDashboardResponse> {
  const resp = await client.get("/suppliers/quality/dashboard", { params });
  return resp.data;
}

export async function getSupplierQualityDetail(
  supplierId: string,
  params?: { start_date?: string; end_date?: string }
): Promise<SupplierQualityDetailResponse> {
  const resp = await client.get(`/suppliers/quality/supplier/${supplierId}`, { params });
  return resp.data;
}

export async function getSupplierCompare(
  supplierIds: string[],
  params?: { start_date?: string; end_date?: string }
): Promise<SupplierCompareResponse> {
  const resp = await client.get("/suppliers/quality/compare", {
    params: { supplier_ids: supplierIds.join(","), ...params },
  });
  return resp.data;
}

export async function exportQualityDashboard(params?: {
  start_date?: string;
  end_date?: string;
  product_line_code?: string;
}): Promise<void> {
  const resp = await client.get("/suppliers/quality/export", {
    params,
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(new Blob([resp.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `supplier_quality_${new Date().toISOString().split("T")[0]}.xlsx`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function exportSuppliers(params?: Record<string, string | undefined>): Promise<void> {
  await downloadExcel("/suppliers/export", params || {}, `suppliers_${new Date().toISOString().split("T")[0]}.xlsx`);
}

export async function downloadSupplierImportTemplate(): Promise<void> {
  await downloadExcel("/suppliers/import-template", {}, "supplier_import_template.xlsx");
}

export async function importSuppliers(file: File): Promise<ImportResult> {
  return uploadExcel("/suppliers/import", file);
}
