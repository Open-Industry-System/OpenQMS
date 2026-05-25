import client from "./client";
import type { ManagementReview, ManagementReviewListResponse, ReviewOutput } from "../types";

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
