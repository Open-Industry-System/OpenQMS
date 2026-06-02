import client from "./client";
import type { ActiveUser, EditingArea } from "../types/collaboration";

export async function heartbeat(
  documentType: string,
  documentId: string,
  action: string,
  editingArea?: EditingArea
): Promise<void> {
  await client.post("/collaboration/heartbeat", {
    document_type: documentType,
    document_id: documentId,
    action,
    editing_area: editingArea || null,
  });
}

export async function leaveSession(
  documentType: string,
  documentId: string
): Promise<void> {
  await client.delete(`/collaboration/leave/${documentType}/${documentId}`);
}

export interface ActiveUsersResponse {
  users: ActiveUser[];
  total: number;
}

export async function getActiveUsers(
  documentType: string,
  documentId: string
): Promise<ActiveUsersResponse> {
  const resp = await client.get(`/collaboration/${documentType}/${documentId}/active-users`);
  return resp.data;
}
