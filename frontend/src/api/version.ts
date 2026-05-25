import client from "./client";
import type {
  FMEAVersion,
  CPVersion,
  VersionListResponse,
  FMEACompareResponse,
  CPCompareResponse,
  VerifyResponse,
  SyncPreviewResponse,
} from "../types";

// --- FMEA Version APIs ---

export async function listFMEAVersions(
  fmeaId: string,
  params?: {
    major_only?: boolean;
    page?: number;
    page_size?: number;
  }
): Promise<VersionListResponse<FMEAVersion>> {
  const resp = await client.get(`/fmea/${fmeaId}/versions`, { params });
  return resp.data;
}

export async function getFMEAVersion(
  fmeaId: string,
  major: number,
  minor: number
): Promise<FMEAVersion> {
  const resp = await client.get(
    `/fmea/${fmeaId}/versions/${major}/${minor}`
  );
  return resp.data;
}

export async function createFMEAVersion(
  fmeaId: string,
  data: {
    change_summary: string;
    is_major?: boolean;
  }
): Promise<FMEAVersion> {
  const resp = await client.post(`/fmea/${fmeaId}/versions`, data);
  return resp.data;
}

export async function rollbackFMEAVersion(
  fmeaId: string,
  major: number,
  minor: number,
  data: { reason: string }
): Promise<FMEAVersion> {
  const resp = await client.post(
    `/fmea/${fmeaId}/versions/${major}/${minor}/rollback`,
    data
  );
  return resp.data;
}

export async function compareFMEAVersions(
  fmeaId: string,
  major1: number,
  minor1: number,
  major2: number,
  minor2: number
): Promise<FMEACompareResponse> {
  const resp = await client.get(`/fmea/${fmeaId}/versions/compare`, {
    params: { major1, minor1, major2, minor2 },
  });
  return resp.data;
}

export async function verifyFMEAVersion(
  fmeaId: string,
  major: number,
  minor: number
): Promise<VerifyResponse> {
  const resp = await client.post(
    `/fmea/${fmeaId}/versions/${major}/${minor}/verify`
  );
  return resp.data;
}

// --- CP Version APIs ---

export async function listCPVersions(
  cpId: string,
  params?: {
    major_only?: boolean;
    page?: number;
    page_size?: number;
  }
): Promise<VersionListResponse<CPVersion>> {
  const resp = await client.get(`/control-plans/${cpId}/versions`, { params });
  return resp.data;
}

export async function getCPVersion(
  cpId: string,
  major: number,
  minor: number
): Promise<CPVersion> {
  const resp = await client.get(
    `/control-plans/${cpId}/versions/${major}/${minor}`
  );
  return resp.data;
}

export async function createCPVersion(
  cpId: string,
  data: {
    change_summary: string;
    is_major?: boolean;
  }
): Promise<CPVersion> {
  const resp = await client.post(`/control-plans/${cpId}/versions`, data);
  return resp.data;
}

export async function rollbackCPVersion(
  cpId: string,
  major: number,
  minor: number,
  data: { reason: string }
): Promise<CPVersion> {
  const resp = await client.post(
    `/control-plans/${cpId}/versions/${major}/${minor}/rollback`,
    data
  );
  return resp.data;
}

export async function compareCPVersions(
  cpId: string,
  major1: number,
  minor1: number,
  major2: number,
  minor2: number
): Promise<CPCompareResponse> {
  const resp = await client.get(`/control-plans/${cpId}/versions/compare`, {
    params: { major1, minor1, major2, minor2 },
  });
  return resp.data;
}

export async function verifyCPVersion(
  cpId: string,
  major: number,
  minor: number
): Promise<VerifyResponse> {
  const resp = await client.post(
    `/control-plans/${cpId}/versions/${major}/${minor}/verify`
  );
  return resp.data;
}

// --- FMEA-CP Sync APIs ---

export async function getSyncPreview(
  cpId: string
): Promise<SyncPreviewResponse> {
  const resp = await client.get(
    `/control-plans/${cpId}/sync-preview`
  );
  return resp.data;
}

export async function applySyncFromFMEA(
  cpId: string,
  data: {
    selected_item_ids: string[];
  }
): Promise<{ synced_count: number }> {
  const resp = await client.post(
    `/control-plans/${cpId}/sync-from-fmea`,
    data
  );
  return resp.data;
}
