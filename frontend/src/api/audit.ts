import client from "./client";
import type { AuditProgram, AuditPlan, AuditFinding, AuditProgramListResponse, AuditPlanListResponse, AuditFindingListResponse, AuditStats, AuditChecklistItem, User, CustomerAuditStats, CustomerConfirmationRequest, FindingTransitionRequest } from "../types";

export async function listAuditPrograms(params?: Record<string, unknown>): Promise<AuditProgramListResponse> {
  const resp = await client.get("/audit-programs/list", { params });
  return resp.data;
}

export async function createAuditProgram(data: Omit<AuditProgram, "program_id" | "program_no" | "created_at" | "status" | "created_by">): Promise<AuditProgram> {
  const resp = await client.post("/audit-programs", data);
  return resp.data;
}

export async function getAuditProgram(id: string): Promise<AuditProgram> {
  const resp = await client.get(`/audit-programs/${id}`);
  return resp.data;
}

export async function updateAuditProgram(id: string, data: Partial<AuditProgram>): Promise<AuditProgram> {
  const resp = await client.put(`/audit-programs/${id}`, data);
  return resp.data;
}

export async function deleteAuditProgram(id: string): Promise<void> {
  await client.delete(`/audit-programs/${id}`);
}

export async function listAuditPlans(params?: Record<string, unknown>): Promise<AuditPlanListResponse> {
  const resp = await client.get("/audit-plans", { params });
  return resp.data;
}

export async function createAuditPlan(data: Omit<AuditPlan, "audit_id" | "plan_no" | "created_at" | "status" | "created_by">): Promise<AuditPlan> {
  const resp = await client.post("/audit-plans", data);
  return resp.data;
}

export async function getAuditPlan(id: string): Promise<AuditPlan> {
  const resp = await client.get(`/audit-plans/${id}`);
  return resp.data;
}

export async function updateAuditPlan(id: string, data: Partial<AuditPlan>): Promise<AuditPlan> {
  const resp = await client.put(`/audit-plans/${id}`, data);
  return resp.data;
}

export async function deleteAuditPlan(id: string): Promise<void> {
  await client.delete(`/audit-plans/${id}`);
}

export async function startAuditPlan(id: string): Promise<AuditPlan> {
  const resp = await client.post(`/audit-plans/${id}/start`);
  return resp.data;
}

export async function completeAuditPlan(id: string): Promise<AuditPlan> {
  const resp = await client.post(`/audit-plans/${id}/complete`);
  return resp.data;
}

export async function cancelAuditPlan(id: string): Promise<AuditPlan> {
  const resp = await client.post(`/audit-plans/${id}/cancel`);
  return resp.data;
}

export async function listAuditFindings(params?: Record<string, unknown>): Promise<AuditFindingListResponse> {
  const resp = await client.get("/audit-findings", { params });
  return resp.data;
}

export async function createAuditFinding(data: Omit<AuditFinding, "finding_id" | "created_at" | "status" | "closed_at" | "created_by" | "capa_ref_id">): Promise<AuditFinding> {
  const resp = await client.post("/audit-findings", data);
  return resp.data;
}

export async function updateAuditFinding(id: string, data: Partial<AuditFinding>): Promise<AuditFinding> {
  const resp = await client.put(`/audit-findings/${id}`, data);
  return resp.data;
}

export async function closeAuditFinding(id: string): Promise<AuditFinding> {
  const resp = await client.post(`/audit-findings/${id}/close`);
  return resp.data;
}

export async function createCAPAFromFinding(id: string): Promise<{ capa_id: string; document_no: string }> {
  const resp = await client.post(`/audit-findings/${id}/create-capa`);
  return resp.data;
}

export async function getAuditStats(): Promise<AuditStats> {
  const resp = await client.get("/audit-programs");
  return resp.data;
}

export async function getChecklistTemplates(): Promise<{ audit_type: string; name: string; items: AuditChecklistItem[] }[]> {
  const resp = await client.get("/audit-plans/checklist-templates");
  return resp.data;
}

export async function listAuditors(): Promise<User[]> {
  const resp = await client.get("/auditors");
  return resp.data;
}

export async function updateAuditorInfo(userId: string, data: { is_auditor: boolean; qualifications: string[]; last_qualification_date?: string }): Promise<User> {
  const resp = await client.put(`/auditors/${userId}/auditor-info`, data);
  return resp.data;
}

// -- Customer Audit API --

export async function getCustomerAuditStats(params?: { product_line_code?: string }): Promise<CustomerAuditStats> {
  const resp = await client.get("/audit-plans/customer-stats", { params });
  return resp.data;
}

export async function listCustomerAudits(params?: Record<string, unknown>): Promise<AuditPlanListResponse> {
  const resp = await client.get("/audit-plans", { params: { audit_category: "customer", ...params } });
  return resp.data;
}

export async function createCustomerAudit(data: {
  audit_scope: string;
  audit_criteria: string;
  planned_date: string;
  customer_name: string;
  customer_type: string;
  audit_mode?: string;
  lead_auditor?: string;
  team_members?: { user_id: string; username: string }[];
  checklist?: AuditChecklistItem[];
  product_line_code?: string;
}): Promise<AuditPlan> {
  const resp = await client.post("/audit-plans", { audit_category: "customer", ...data });
  return resp.data;
}

export async function updateCustomerAudit(id: string, data: Partial<AuditPlan>): Promise<AuditPlan> {
  const resp = await client.put(`/audit-plans/${id}`, data);
  return resp.data;
}

export async function confirmCustomerAudit(
  id: string,
  data: CustomerConfirmationRequest
): Promise<AuditPlan> {
  const resp = await client.put(`/audit-plans/${id}/customer-confirm`, data);
  return resp.data;
}

export async function transitionFinding(
  id: string,
  data: FindingTransitionRequest
): Promise<AuditFinding> {
  const resp = await client.post(`/audit-findings/${id}/transition`, data);
  return resp.data;
}

export async function confirmCustomerFinding(
  id: string,
  data: CustomerConfirmationRequest
): Promise<AuditFinding> {
  const resp = await client.post(`/audit-findings/${id}/customer-confirm`, data);
  return resp.data;
}
