import client from "./client";
import type {
  PLMConnection,
  PLMConnectionCreate,
  PLMConnectionUpdate,
  PLMConnectionListResponse,
  PLMPart,
  PLMBOM,
  PLMBOMTreeResponse,
  PLMChangeOrder,
  PLMChangeImpactTask,
  PLMDashboard,
} from "../types/plm";

// ─── Connections ───

export const createPLMConnection = (data: PLMConnectionCreate) =>
  client.post<PLMConnection>("/plm/connections", data).then((r) => r.data);

export const getPLMConnections = (page = 1, page_size = 20) =>
  client.get<PLMConnectionListResponse>("/plm/connections", { params: { page, page_size } }).then((r) => r.data);

export const getPLMConnection = (id: string) =>
  client.get<PLMConnection>(`/plm/connections/${id}`).then((r) => r.data);

export const updatePLMConnection = (id: string, data: PLMConnectionUpdate) =>
  client.put<PLMConnection>(`/plm/connections/${id}`, data).then((r) => r.data);

export const deletePLMConnection = (id: string) =>
  client.delete(`/plm/connections/${id}`).then((r) => r.data);

export const testPLMConnection = (id: string) =>
  client.post<{ success: boolean }>(`/plm/connections/${id}/test`).then((r) => r.data);

export const syncPLMConnection = (id: string) =>
  client.post<{ synced_jobs: number }>(`/plm/connections/${id}/sync`).then((r) => r.data);

// ─── Parts ───

export const getPLMParts = (params?: { connection_id?: string; page?: number; page_size?: number }) =>
  client.get<{ items: PLMPart[]; total: number; page: number; page_size: number }>("/plm/parts", { params }).then((r) => r.data);

export const getPLMPart = (id: string) =>
  client.get<PLMPart>(`/plm/parts/${id}`).then((r) => r.data);

// ─── BOMs ───

export const getPLMBOMs = (params?: { connection_id?: string; page?: number; page_size?: number }) =>
  client.get<{ items: PLMBOM[]; total: number; page: number; page_size: number }>("/plm/boms", { params }).then((r) => r.data);

export const getPLMBOMTree = (
  connectionId: string,
  partNumber: string,
) =>
  client.get<PLMBOMTreeResponse>(`/plm/connections/${connectionId}/boms/tree/${encodeURIComponent(partNumber)}`).then((r) => r.data);

// ─── Change Orders ───

export const getPLMChangeOrders = (params?: { connection_id?: string; page?: number; page_size?: number }) =>
  client.get<{ items: PLMChangeOrder[]; total: number; page: number; page_size: number }>("/plm/change-orders", { params }).then((r) => r.data);

export const getPLMChangeOrder = (id: string) =>
  client.get<PLMChangeOrder>(`/plm/change-orders/${id}`).then((r) => r.data);

// ─── Dashboard ───

export const getPLMDashboard = () =>
  client.get<PLMDashboard>("/plm/dashboard").then((r) => r.data);

// ─── Impact Analysis ───

export const triggerImpactAnalysis = (changeId: string) =>
  client.post<PLMChangeImpactTask>(`/plm/change-orders/${changeId}/impact-analysis`).then((r) => r.data);

// ─── Import BOM to FMEA ───

export const importBOMToFMEA = (
  connectionId: string,
  partNumber: string,
  body: { fmea_id: string; overwrite?: boolean },
) =>
  client.post<{ imported_nodes: number; imported_edges: number; root: string; fmea_id: string }>(
    `/plm/connections/${connectionId}/boms/${encodeURIComponent(partNumber)}/import-to-fmea`,
    body,
  ).then((r) => r.data);
