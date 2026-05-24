import client from "./client";
import type {
  SpecialCharacteristic,
  SCListResponse,
  MatrixResponse,
  CPSyncStatusResponse,
  SeverityWarning,
} from "../types";

export async function listSCs(params?: {
  sc_type?: string;
  product_line?: string;
  source_type?: string;
  page?: number;
  page_size?: number;
  safety_related_only?: boolean;
  approval_status?: string;
  suggested_only?: boolean;
}): Promise<SCListResponse> {
  const resp = await client.get("/special-characteristics/list", { params });
  return resp.data;
}

export async function getSC(scId: string): Promise<SpecialCharacteristic> {
  const resp = await client.get(`/special-characteristics/${scId}`);
  return resp.data;
}

export async function createSC(
  data: Partial<SpecialCharacteristic>
): Promise<SpecialCharacteristic> {
  const resp = await client.post("/special-characteristics/create", data);
  return resp.data;
}

export async function updateSC(
  scId: string,
  data: Partial<SpecialCharacteristic>
): Promise<SpecialCharacteristic> {
  const resp = await client.put(`/special-characteristics/${scId}`, data);
  return resp.data;
}

export async function deleteSC(scId: string): Promise<void> {
  await client.delete(`/special-characteristics/${scId}`);
}

export async function getMatrix(
  productLine?: string
): Promise<MatrixResponse> {
  const resp = await client.get("/special-characteristics/matrix", {
    params: { product_line: productLine },
  });
  return resp.data;
}

export async function syncFromFMEA(
  fmeaId: string
): Promise<{ detail: string; count: number }> {
  const resp = await client.post(
    `/special-characteristics/sync-from-fmea/${fmeaId}`
  );
  return resp.data;
}

export async function syncToCP(
  cpId: string
): Promise<{ detail: string; updated_count: number }> {
  const resp = await client.post(
    `/special-characteristics/sync-to-cp/${cpId}`
  );
  return resp.data;
}

export async function getCPSyncStatus(
  cpId: string
): Promise<CPSyncStatusResponse> {
  const resp = await client.get(
    `/special-characteristics/cp-sync-status/${cpId}`
  );
  return resp.data;
}

export async function msaCallback(
  scId: string,
  grrPercent: number
): Promise<SpecialCharacteristic> {
  const resp = await client.post(
    `/special-characteristics/msa-callback/${scId}`,
    null,
    { params: { grr_percent: grrPercent } }
  );
  return resp.data;
}

export async function getSeverityWarnings(
  fmeaId: string
): Promise<SeverityWarning[]> {
  const resp = await client.get(`/fmea/${fmeaId}/severity-warnings`);
  return resp.data;
}

export async function safetySubmit(
  scId: string,
  data: { safety_regulation_ref: string; safety_verification_method: string }
): Promise<SpecialCharacteristic> {
  const resp = await client.post(`/special-characteristics/${scId}/safety-submit`, data);
  return resp.data;
}

export async function safetyApprove(
  scId: string,
  comment?: string
): Promise<SpecialCharacteristic> {
  const resp = await client.post(`/special-characteristics/${scId}/safety-approve`, { comment });
  return resp.data;
}

export async function safetyReject(
  scId: string,
  comment: string
): Promise<SpecialCharacteristic> {
  const resp = await client.post(`/special-characteristics/${scId}/safety-reject`, { comment });
  return resp.data;
}

export async function safetyConfirm(scId: string): Promise<SpecialCharacteristic> {
  const resp = await client.post(`/special-characteristics/${scId}/safety-confirm`);
  return resp.data;
}

export async function safetyDismiss(scId: string): Promise<SpecialCharacteristic> {
  const resp = await client.post(`/special-characteristics/${scId}/safety-dismiss`);
  return resp.data;
}

export async function safetyCancel(scId: string): Promise<SpecialCharacteristic> {
  const resp = await client.post(`/special-characteristics/${scId}/safety-cancel`);
  return resp.data;
}

export async function markAuditLogRead(logId: string): Promise<{ detail: string; log_id: string }> {
  const resp = await client.post(`/special-characteristics/audit-logs/${logId}/read`);
  return resp.data;
}
