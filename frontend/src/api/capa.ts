import client from "./client";
import { message } from "antd";
import type { CAPAReport, CAPAListResponse, D7RecommendationResponse, D4RecommendationResponse, D5RecommendationResponse, AdoptRequest, AdoptResponse, Verification, VerificationCreate, VerificationUpdate, D7NodeAction, D7NodeActionCreate, D7AutoFillRequest, D7AutoFillResponse, StageRun } from "../types";

export class RecommendationBlockedError extends Error {
  detail: { blocked: true; reason: string; stages: StageRun[] };
  constructor(detail: { blocked: true; reason: string; stages: StageRun[] }) {
    super(detail.reason);
    this.detail = detail;
  }
}

export async function listCAPAs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  product_line?: string;
  overdue?: boolean;
  pending_action?: boolean;
}): Promise<CAPAListResponse> {
  const resp = await client.get("/capa", { params });
  return resp.data;
}

export async function getCAPA(id: string): Promise<CAPAReport> {
  const resp = await client.get(`/capa/${id}`);
  return resp.data;
}

export async function createCAPA(data: {
  title: string;
  document_no: string;
  severity: string;
  due_date?: string;
  product_line_code?: string;
}): Promise<CAPAReport> {
  const resp = await client.post("/capa", data);
  return resp.data;
}

export async function updateCAPA(
  id: string,
  data: Record<string, unknown>
): Promise<CAPAReport> {
  const resp = await client.put(`/capa/${id}`, data);
  return resp.data;
}

export interface AdvanceRequest {
  target_state?: string;
  reject_reason?: string;
  d7_skip_reasons?: Array<{ fmea_id: string | null; node_id: string; reason: string }>;
}

export interface CAPAAdvanceResponse { capa: CAPAReport; warning: string | null }

export async function advanceCAPA(id: string, req: AdvanceRequest = {}): Promise<CAPAReport> {
  const r = (await client.post(`/capa/${id}/advance`, req)).data as CAPAAdvanceResponse;
  if (r.warning) message.warning(r.warning);
  return r.capa;
}

export async function getD7Recommendations(id: string): Promise<D7RecommendationResponse> {
  const resp = await client.get(`/capa/${id}/d7-fmea-recommendations`);
  return resp.data;
}

export async function getD4Recommendations(id: string): Promise<D4RecommendationResponse> {
  try {
    const resp = await client.get(`/capa/${id}/d4-fmea-recommendations`);
    return resp.data;
  } catch (e: any) {
    if (e.response?.status === 422 && e.response?.data?.detail?.blocked === true) {
      throw new RecommendationBlockedError(e.response.data.detail);
    }
    throw e;
  }
}

export async function getD5Recommendations(id: string): Promise<D5RecommendationResponse> {
  try {
    const resp = await client.get(`/capa/${id}/d5-fmea-recommendations`);
    return resp.data;
  } catch (e: any) {
    if (e.response?.status === 422 && e.response?.data?.detail?.blocked === true) {
      throw new RecommendationBlockedError(e.response.data.detail);
    }
    throw e;
  }
}

export async function linkFMEA(id: string, fmea_id: string): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/link-fmea`, null, {
    params: { fmea_id },
  });
  return resp.data;
}

export async function adoptRecommendation(capaId: string, req: AdoptRequest): Promise<AdoptResponse> {
  const resp = await client.post(`/capa/${capaId}/adopt-recommendation`, req);
  return resp.data;
}
export async function listVerifications(capaId: string): Promise<Verification[]> {
  const resp = await client.get(`/capa/${capaId}/root-cause-verifications`);
  return resp.data;
}
export async function createVerification(capaId: string, req: VerificationCreate): Promise<Verification> {
  const resp = await client.post(`/capa/${capaId}/root-cause-verifications`, req);
  return resp.data;
}
export async function updateVerification(capaId: string, vid: string, req: VerificationUpdate): Promise<Verification> {
  const resp = await client.patch(`/capa/${capaId}/root-cause-verifications/${vid}`, req);
  return resp.data;
}
export async function recordD7Action(capaId: string, req: D7NodeActionCreate): Promise<D7NodeAction> {
  const resp = await client.post(`/capa/${capaId}/d7-node-actions`, req);
  return resp.data;
}
export async function listD7Actions(capaId: string): Promise<D7NodeAction[]> {
  const resp = await client.get(`/capa/${capaId}/d7-node-actions`);
  return resp.data;
}
export async function autoFillD7(capaId: string, req: D7AutoFillRequest): Promise<D7AutoFillResponse> {
  const resp = await client.post(`/capa/${capaId}/d7-auto-fill`, req);
  return resp.data;
}

export async function generatePpt(
  reportId: string,
): Promise<{ reviewStatus: string; reviewRounds: number; exportId: string | null }> {
  const resp = await client.post(`/capa/${reportId}/ppt-export`, {}, {
    responseType: "blob",
    timeout: 120000,
  });
  const reviewStatus = resp.headers["x-ppt-review-status"] || "skipped";
  const reviewRounds = parseInt(resp.headers["x-ppt-review-rounds"] || "0", 10);
  const exportId = resp.headers["x-ppt-export-id"] || null;
  const blob = new Blob([resp.data]);
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const cd = resp.headers["content-disposition"] || "";
  const m = cd.match(/filename\*=UTF-8''(.+)/);
  link.setAttribute("download", m ? decodeURIComponent(m[1]) : `8D_report_${reportId}.pptx`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
  return { reviewStatus, reviewRounds, exportId };
}

export async function getPptExportReviewReport(
  reportId: string,
  exportId: string,
): Promise<{ reviewReport: any }> {
  const resp = await client.get(`/capa/${reportId}/ppt-exports/${exportId}`);
  return { reviewReport: resp.data.review_report };
}
