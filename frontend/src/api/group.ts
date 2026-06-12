import client from "./client";

// ── Factory CRUD ──

export interface Factory {
  id: string;
  code: string;
  name: string;
  location?: string;
  is_active: boolean;
}

export interface FactoryListResponse {
  items: Factory[];
  total: number;
}

export const listFactories = (isActive?: boolean) =>
  client.get<FactoryListResponse>("/group/factories", {
    params: { is_active: isActive },
  });

export const createFactory = (data: {
  code: string;
  name: string;
  location?: string;
}) => client.post<Factory>("/group/factories", data);

export const updateFactory = (
  factoryId: string,
  data: { name?: string; location?: string; is_active?: boolean }
) => client.put<Factory>(`/group/factories/${factoryId}`, data);

export const deactivateFactory = (factoryId: string) =>
  client.delete<void>(`/group/factories/${factoryId}`);

// ── Group Dashboard ──

export interface FactoryKPI {
  factory_id: string;
  factory_code: string;
  factory_name: string;
  open_fmea_count: number;
  open_capa_count: number;
  overdue_capa_count: number;
  active_spc_alarms: number;
  pending_iqc_inspections: number;
  open_scars: number;
  open_supplier_risk_alerts: number;
  recent_audit_findings: number;
}

export interface GroupDashboardResponse {
  factories: FactoryKPI[];
  totals: FactoryKPI;
  snapshot_date: string | null;
}

export const getGroupDashboard = () =>
  client.get<GroupDashboardResponse>("/group/dashboard");

// ── Factory Comparison ──

export interface FactoryComparisonItem {
  factory_id: string;
  factory_code: string;
  factory_name: string;
  metrics: Record<string, number>;
}

export interface FactoryComparisonResponse {
  factories: FactoryComparisonItem[];
  metric_names: string[];
}

export const getFactoryComparison = (metricNames?: string[]) =>
  client.get<FactoryComparisonResponse>("/group/comparison", {
    params: metricNames ? { metric_names: metricNames.join(",") } : undefined,
  });

// ── Shared Suppliers ──

export interface SharedSupplierResponse {
  shared_profile_id: string | null;
  unified_credit_code: string | null;
  name: string;
  short_name: string | null;
  industry: string | null;
  factory_evaluations: {
    factory_id: string;
    factory_code: string;
    grade: string;
    total_score: number;
  }[];
}

export const getSharedSuppliers = () =>
  client.get<SharedSupplierResponse[]>("/group/suppliers");

export const mergeSuppliers = (data: {
  supplier_ids: string[];
  shared_profile_id?: string;
}) => client.post("/group/suppliers/merge", data);

// ── Cross-Factory Audits ──

export interface CrossFactoryAuditResponse {
  program_id: string;
  program_no: string;
  audit_type: string;
  status: string;
  target_factory_ids: string[];
  target_factory_codes: string[];
  finding_count: number;
}

export const getCrossFactoryAudits = () =>
  client.get<CrossFactoryAuditResponse[]>("/group/audits");

export const getAuditProgramFactories = (programId: string) =>
  client.get<{ factory_id: string; factory_code: string }[]>(
    `/group/audits/${programId}/factories`
  );

export const addFactoryToAuditProgram = (
  programId: string,
  factoryId: string
) =>
  client.post(`/group/audits/${programId}/factories`, { factory_id: factoryId });

export const removeFactoryFromAuditProgram = (
  programId: string,
  factoryId: string
) => client.delete(`/group/audits/${programId}/factories/${factoryId}`);