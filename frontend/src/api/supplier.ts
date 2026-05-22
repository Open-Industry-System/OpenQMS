import client from "./client";
import type {
  Supplier,
  SupplierListResponse,
  SupplierCertification,
  SupplierEvaluation,
  SupplierStats,
  SupplierExpiryAlert,
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
  data: Omit<SupplierEvaluation, "eval_id" | "supplier_id" | "created_at" | "capa_penalty" | "finding_penalty" | "total_score" | "grade" | "evaluated_by">
): Promise<SupplierEvaluation> {
  const resp = await client.post(`/suppliers/${supplierId}/evaluations`, data);
  return resp.data;
}
