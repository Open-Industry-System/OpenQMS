import client from "./client";
import type {
  PLMConnection,
  PLMConnectionCreate,
  PLMConnectionUpdate,
  PLMConnectionListResponse,
  PLMConnectionTestResponse,
  PLMPart,
  PLMPartListResponse,
  PLMBOMListResponse,
  PLMBOMTreeResponse,
  PLMChangeOrder,
  PLMChangeOrderListResponse,
  PLMChangeImpactTask,
  PLMDashboard,
  PLMPartConfirmSCRequest,
  PLMPartConfirmSCResponse,
  PLMBOMImportResponse,
} from "../types/plm";

// ─── Connections ───

export async function createPLMConnection(
  data: PLMConnectionCreate,
): Promise<PLMConnection> {
  const resp = await client.post<PLMConnection>("/plm/connections", data);
  return resp.data;
}

export async function getPLMConnections(
  page = 1,
  page_size = 20,
): Promise<PLMConnectionListResponse> {
  const resp = await client.get<PLMConnectionListResponse>(
    "/plm/connections",
    { params: { page, page_size } },
  );
  return resp.data;
}

export async function getPLMConnection(id: string): Promise<PLMConnection> {
  const resp = await client.get<PLMConnection>(`/plm/connections/${id}`);
  return resp.data;
}

export async function updatePLMConnection(
  id: string,
  data: PLMConnectionUpdate,
): Promise<PLMConnection> {
  const resp = await client.put<PLMConnection>(
    `/plm/connections/${id}`,
    data,
  );
  return resp.data;
}

export async function deletePLMConnection(id: string): Promise<void> {
  await client.delete(`/plm/connections/${id}`);
}

export async function testPLMConnection(
  id: string,
): Promise<PLMConnectionTestResponse> {
  const resp = await client.post<PLMConnectionTestResponse>(
    `/plm/connections/${id}/test`,
  );
  return resp.data;
}

export async function syncPLMConnection(
  id: string,
): Promise<{ synced_jobs: number }> {
  const resp = await client.post<{ synced_jobs: number }>(
    `/plm/connections/${id}/sync`,
  );
  return resp.data;
}

// ─── Parts ───

export async function getPLMParts(params?: {
  connection_id?: string;
  search?: string;
  product_line_code?: string;
  page?: number;
  page_size?: number;
}): Promise<PLMPartListResponse> {
  const resp = await client.get<PLMPartListResponse>("/plm/parts", {
    params,
  });
  return resp.data;
}

export async function getPLMPart(id: string): Promise<PLMPart> {
  const resp = await client.get<PLMPart>(`/plm/parts/${id}`);
  return resp.data;
}

// ─── BOMs ───

export async function getPLMBOMs(params?: {
  connection_id?: string;
  page?: number;
  page_size?: number;
}): Promise<PLMBOMListResponse> {
  const resp = await client.get<PLMBOMListResponse>("/plm/boms", { params });
  return resp.data;
}

export async function getPLMBOMTree(
  connectionId: string,
  partNumber: string,
  params?: { revision?: string; bom_revision?: string },
): Promise<PLMBOMTreeResponse> {
  const resp = await client.get<PLMBOMTreeResponse>(
    `/plm/connections/${connectionId}/boms/tree/${encodeURIComponent(partNumber)}`,
    { params },
  );
  return resp.data;
}

// ─── Change Orders ───

export async function getPLMChangeOrders(params?: {
  connection_id?: string;
  product_line_code?: string;
  page?: number;
  page_size?: number;
}): Promise<PLMChangeOrderListResponse> {
  const resp = await client.get<PLMChangeOrderListResponse>(
    "/plm/change-orders",
    { params },
  );
  return resp.data;
}

export async function getPLMChangeOrder(id: string): Promise<PLMChangeOrder> {
  const resp = await client.get<PLMChangeOrder>(`/plm/change-orders/${id}`);
  return resp.data;
}

// ─── Dashboard ───

export async function getPLMDashboard(params?: {
  product_line_code?: string;
}): Promise<PLMDashboard> {
  const resp = await client.get<PLMDashboard>("/plm/dashboard", { params });
  return resp.data;
}

// ─── Impact Analysis ───

export async function triggerImpactAnalysis(
  changeId: string,
): Promise<PLMChangeImpactTask> {
  const resp = await client.post<PLMChangeImpactTask>(
    `/plm/change-orders/${changeId}/impact-analysis`,
  );
  return resp.data;
}

// ─── Import BOM to FMEA ───

export async function importBOMToFMEA(
  connectionId: string,
  partNumber: string,
  body: { fmea_id: string; overwrite?: boolean },
  params?: { revision?: string; bom_revision?: string },
): Promise<PLMBOMImportResponse> {
  const resp = await client.post<PLMBOMImportResponse>(
    `/plm/connections/${connectionId}/boms/${encodeURIComponent(partNumber)}/import-to-fmea`,
    body,
    { params },
  );
  return resp.data;
}

export async function confirmPLMPartSC(
  partId: string,
  body: PLMPartConfirmSCRequest,
): Promise<PLMPartConfirmSCResponse> {
  const resp = await client.post<PLMPartConfirmSCResponse>(
    `/plm/parts/${partId}/confirm-sc`,
    body,
  );
  return resp.data;
}
