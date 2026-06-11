import client from "./client";
import type { ManagementReview, ManagementReviewListResponse, ReviewOutput, ManagementReviewReport, ReviewReportVersion } from "../types";

export async function listManagementReviews(params: {
  page?: number;
  page_size?: number;
  status?: string;
  product_line_code?: string;
}): Promise<ManagementReviewListResponse> {
  const resp = await client.get("/management-reviews", { params });
  return resp.data;
}

export async function getManagementReview(id: string): Promise<ManagementReview> {
  const resp = await client.get(`/management-reviews/${id}`);
  return resp.data;
}

export async function createManagementReview(data: {
  title: string;
  review_date: string;
  product_line_code?: string | null;
  location?: string | null;
  chair_person_id: string;
  participants?: { user_id: string; name: string; role: string; department: string }[] | null;
}): Promise<ManagementReview> {
  const resp = await client.post("/management-reviews", data);
  return resp.data;
}

export async function updateManagementReview(
  id: string,
  data: Record<string, unknown>,
): Promise<ManagementReview> {
  const resp = await client.put(`/management-reviews/${id}`, data);
  return resp.data;
}

export async function deleteManagementReview(id: string): Promise<void> {
  await client.delete(`/management-reviews/${id}`);
}

export async function collectData(id: string): Promise<ManagementReview> {
  const resp = await client.post(`/management-reviews/${id}/collect-data`);
  return resp.data;
}

export async function refreshData(id: string): Promise<ManagementReview> {
  const resp = await client.post(`/management-reviews/${id}/refresh-data`);
  return resp.data;
}

export async function backToDraft(id: string): Promise<ManagementReview> {
  const resp = await client.post(`/management-reviews/${id}/back-to-draft`);
  return resp.data;
}

export async function startReview(id: string): Promise<ManagementReview> {
  const resp = await client.post(`/management-reviews/${id}/start-review`);
  return resp.data;
}

export async function closeReview(id: string): Promise<ManagementReview> {
  const resp = await client.post(`/management-reviews/${id}/close`);
  return resp.data;
}

export async function reopenReview(id: string): Promise<ManagementReview> {
  const resp = await client.post(`/management-reviews/${id}/reopen`);
  return resp.data;
}

export async function listOutputs(reviewId: string): Promise<ReviewOutput[]> {
  const resp = await client.get(`/management-reviews/${reviewId}/outputs`);
  return resp.data;
}

export async function createOutput(
  reviewId: string,
  data: { category: string; description: string; responsible_id?: string | null; due_date?: string | null },
): Promise<ReviewOutput> {
  const resp = await client.post(`/management-reviews/${reviewId}/outputs`, data);
  return resp.data;
}

export async function updateOutput(
  reviewId: string,
  outputId: string,
  data: Record<string, unknown>,
): Promise<ReviewOutput> {
  const resp = await client.put(`/management-reviews/${reviewId}/outputs/${outputId}`, data);
  return resp.data;
}

export async function deleteOutput(reviewId: string, outputId: string): Promise<void> {
  await client.delete(`/management-reviews/${reviewId}/outputs/${outputId}`);
}

export async function verifyOutput(
  reviewId: string,
  outputId: string,
  verification_notes: string,
): Promise<ReviewOutput> {
  const resp = await client.post(`/management-reviews/${reviewId}/outputs/${outputId}/verify`, {
    verification_notes,
  });
  return resp.data;
}

export async function generateReport(
  id: string,
  use_llm: boolean = true,
): Promise<{ report_status: string; generated_report: ManagementReviewReport }> {
  const resp = await client.post(`/management-reviews/${id}/report/generate`, { use_llm });
  return resp.data;
}

export async function saveReportDraft(
  id: string,
  report: ManagementReviewReport,
): Promise<{ report_status: string; generated_report: ManagementReviewReport }> {
  const resp = await client.post(`/management-reviews/${id}/report/save-draft`, { generated_report: report });
  return resp.data;
}

export async function finalizeReport(id: string): Promise<ReviewReportVersion> {
  const resp = await client.post(`/management-reviews/${id}/report/finalize`);
  return resp.data;
}

export async function reopenReport(id: string): Promise<{ report_status: string }> {
  const resp = await client.post(`/management-reviews/${id}/report/reopen`);
  return resp.data;
}

export async function listReportVersions(id: string): Promise<ReviewReportVersion[]> {
  const resp = await client.get(`/management-reviews/${id}/report/versions`);
  return resp.data;
}

export async function getReportVersion(reviewId: string, reportId: string): Promise<ReviewReportVersion> {
  const resp = await client.get(`/management-reviews/${reviewId}/report/versions/${reportId}`);
  return resp.data;
}

export async function exportReport(id: string, format: string = "markdown"): Promise<{ markdown: string }> {
  const resp = await client.get(`/management-reviews/${id}/report/export`, { params: { format } });
  return resp.data;
}
