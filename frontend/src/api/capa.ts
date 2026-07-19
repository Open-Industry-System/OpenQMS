import client from "./client";
import { message } from "antd";
import type {
  CAPAReport, CAPAListResponse, D7RecommendationResponse, D4RecommendationResponse,
  D5RecommendationResponse, AdoptRequest, AdoptResponse, Verification, VerificationCreate,
  VerificationUpdate, D7NodeAction, D7NodeActionCreate, D7AutoFillRequest, D7AutoFillResponse,
  StageRun, D3ImportRun, D3ContainmentSnapshot, D3ImpactReport, D3AiAdvice, D3AdviceAdoption,
  D3Execution, D3ImportRequest, D3GenerateReportRequest, D3GenerateAdviceRequest,
  D3DecideAdviceRequest, D3ExecutionCreate, D3ExecutionUpdate, D3AdviceResponse, SupplierSCAR,
  SinkKnowledgeResponse, KnowledgeSinkOutcomeDetail,
} from "../types";

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

export async function triggerScar(
  id: string,
  body: {
    supplier_id: string;
    description?: string;
    requested_action?: string;
    due_date?: string | null;
    affected_batches?: string[];
  },
): Promise<SupplierSCAR> {
  const resp = await client.post(`/capa/${id}/trigger-scar`, body);
  return resp.data;
}

export async function confirmRepeat(
  reportId: string,
  repeatConfirmed: boolean,
): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${reportId}/confirm-repeat`, {
    repeat_confirmed: repeatConfirmed,
  });
  return resp.data;
}

export async function listCapaSupplierOptions(params?: {
  page?: number;
  page_size?: number;
  search?: string;
}): Promise<{
  items: Array<{ supplier_id: string; supplier_no: string; name: string; status: string }>;
  total: number;
  page: number;
  page_size: number;
}> {
  const resp = await client.get("/capa/supplier-options", { params });
  return resp.data;
}

export async function createCAPA(data: {
  title: string;
  document_no: string;
  severity: string;
  due_date?: string;
  product_line_code?: string;
  supplier_id?: string | null;
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

/** Manual knowledge resink for D8_CLOSURE / ARCHIVED CAPA (US-E2E-01.8). */
export async function sinkKnowledge(capaId: string): Promise<SinkKnowledgeResponse> {
  const resp = await client.post(`/capa/${capaId}/sink-knowledge`);
  return resp.data;
}

/** Parse 422 knowledge-sink contract: detail.outcome blocked|failed. */
export function parseKnowledgeSinkError(err: unknown): KnowledgeSinkOutcomeDetail | null {
  const detail = (err as { response?: { status?: number; data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (
    detail &&
    typeof detail === "object" &&
    detail !== null &&
    "outcome" in detail &&
    ((detail as KnowledgeSinkOutcomeDetail).outcome === "blocked" ||
      (detail as KnowledgeSinkOutcomeDetail).outcome === "failed")
  ) {
    return detail as KnowledgeSinkOutcomeDetail;
  }
  return null;
}

/** Human-readable advance/resink error; prefers knowledge-sink outcome messaging. */
export function formatCapaAdvanceError(
  err: unknown,
  fallback: string,
  labels?: { blocked?: string; failed?: string },
): string {
  const sink = parseKnowledgeSinkError(err);
  if (sink) {
    const base =
      sink.outcome === "blocked"
        ? labels?.blocked || "知识库沉淀被阻断：LLM 未配置"
        : labels?.failed || "知识库沉淀失败，可重试";
    return sink.message ? `${base}：${sink.message}` : base;
  }
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  return fallback;
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

// ─── D3 Containment APIs ──────────────────────────────────────────────────────

export async function importD3Containment(
  capaId: string,
  req?: D3ImportRequest
): Promise<D3ImportRun> {
  const resp = await client.post(`/capa/${capaId}/d3/import`, req || {});
  return resp.data;
}

export async function getD3Runs(capaId: string): Promise<D3ImportRun[]> {
  const resp = await client.get(`/capa/${capaId}/d3/runs`);
  return resp.data;
}

export async function getD3Snapshots(capaId: string, runId?: string): Promise<D3ContainmentSnapshot[]> {
  const params = runId ? { run_id: runId } : {};
  const resp = await client.get(`/capa/${capaId}/d3/snapshots`, { params });
  return resp.data;
}

export async function generateD3Report(
  capaId: string,
  req: D3GenerateReportRequest
): Promise<D3ImpactReport> {
  const resp = await client.post(`/capa/${capaId}/d3/report`, req);
  return resp.data;
}

export async function getD3Report(capaId: string, runId?: string): Promise<D3ImpactReport | null> {
  const params = runId ? { run_id: runId } : {};
  const resp = await client.get(`/capa/${capaId}/d3/report`, { params });
  return resp.data;
}

export async function generateD3Advice(
  capaId: string,
  req: D3GenerateAdviceRequest
): Promise<{ report_id: string; status: string }> {
  const resp = await client.post(`/capa/${capaId}/d3/advice`, req);
  return resp.data;
}

export async function getD3Advice(capaId: string, runId?: string): Promise<D3AdviceResponse> {
  const params = runId ? { run_id: runId } : {};
  const resp = await client.get(`/capa/${capaId}/d3/advice`, { params });
  return resp.data;
}

export async function decideD3Advice(
  capaId: string,
  adviceId: string,
  req: D3DecideAdviceRequest
): Promise<D3AdviceAdoption> {
  const resp = await client.post(`/capa/${capaId}/d3/advice/${adviceId}/decision`, req);
  return resp.data;
}

export async function getD3Adoptions(capaId: string, runId?: string): Promise<D3AdviceAdoption[]> {
  const params = runId ? { run_id: runId } : {};
  const resp = await client.get(`/capa/${capaId}/d3/adoptions`, { params });
  return resp.data;
}

export async function recordD3Execution(
  capaId: string,
  req: D3ExecutionCreate
): Promise<D3Execution> {
  const resp = await client.post(`/capa/${capaId}/d3/execution`, req);
  return resp.data;
}

export async function updateD3Execution(
  capaId: string,
  executionId: string,
  req: D3ExecutionUpdate
): Promise<D3Execution> {
  const resp = await client.patch(`/capa/${capaId}/d3/execution/${executionId}`, req);
  return resp.data;
}

export async function getD3Executions(capaId: string, runId?: string): Promise<D3Execution[]> {
  const params = runId ? { run_id: runId } : {};
  const resp = await client.get(`/capa/${capaId}/d3/executions`, { params });
  return resp.data;
}

// ─── D8 Doc Update Gate APIs (US-E2E-01.7) ────────────────────────────────────

export interface DocGateAnalysis {
  analysis_id?: string;
  status: "running" | "done" | "failed" | string;
  affected_docs?: DocGateAffectedDoc[] | null;
  error?: string | null;
  is_current?: boolean;
}

export interface DocGateAffectedDoc {
  doc_type: string;
  doc_id: string;
  doc_name: string;
  baseline_version_id?: string | null;
  baseline_version?: { major?: number; minor?: number; sha256?: string } | null;
  key_points: Array<Record<string, unknown>>;
  update_suggestion: string;
}

export interface DocGateAuditRow {
  doc_type: string;
  doc_id: string;
  doc_name: string;
  status: "passed" | "pending_update" | "incomplete" | string;
  version_bump: boolean;
  covered_count: number;
  total_count: number;
  coverage?: Array<Record<string, unknown>>;
  version_before?: Record<string, unknown> | null;
  version_after?: Record<string, unknown> | null;
}

export interface DocGateDecision {
  decision: "passed" | "blocked" | "deferred" | null;
  no_affected_confirmed?: boolean;
  version_snapshot?: Array<Record<string, unknown>>;
  revision?: number | null;
  defer_reason?: string | null;
  defer_owner?: string | null;
  defer_deadline?: string | null;
  decided_at?: string | null;
}

export async function docGateImpact(capaId: string): Promise<DocGateAnalysis> {
  const resp = await client.post(`/capa/${capaId}/doc-gate/impact`);
  return resp.data;
}

export async function getDocGateImpact(capaId: string): Promise<DocGateAnalysis> {
  const resp = await client.get(`/capa/${capaId}/doc-gate/impact`);
  return resp.data;
}

export async function runDocGateAudit(capaId: string): Promise<{
  decision: string;
  audits: DocGateAuditRow[];
  audit_run_id: string;
}> {
  const resp = await client.post(`/capa/${capaId}/doc-gate/audit`);
  return resp.data;
}

export async function getDocGateAudit(capaId: string): Promise<{
  audit_run_id: string | null;
  audits: DocGateAuditRow[];
}> {
  const resp = await client.get(`/capa/${capaId}/doc-gate/audit`);
  return resp.data;
}

export async function recordDocGateDefer(
  capaId: string,
  payload: { reason: string; owner_id: string; deadline: string },
): Promise<{ decision: string }> {
  const resp = await client.post(`/capa/${capaId}/doc-gate/defer`, payload);
  return resp.data;
}

export async function confirmNoAffected(capaId: string): Promise<{
  decision: string;
  no_affected_confirmed: boolean;
}> {
  const resp = await client.post(`/capa/${capaId}/doc-gate/confirm-no-affected`);
  return resp.data;
}

export async function getDocGateDecision(capaId: string): Promise<DocGateDecision> {
  const resp = await client.get(`/capa/${capaId}/doc-gate/decision`);
  return resp.data;
}
