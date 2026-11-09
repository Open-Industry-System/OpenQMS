import client from "./client";
import type { AgentTaskAttachment, AttachmentStatus } from "../types/agentAttachment";

type Check = (value: unknown) => boolean;
const uuid: Check = value => typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const date: Check = value => typeof value === "string" && Number.isFinite(Date.parse(value));
const nullable = (check: Check): Check => value => value === null || check(value);
const status = (...values: AttachmentStatus[]): Check => value => typeof value === "string" && values.includes(value as AttachmentStatus);
const attachmentStatus = status("scanning", "promoting", "available", "rejected_malware", "rejected_scanner", "failed_storage", "purging", "purged");
const attachment = (value: unknown): value is AgentTaskAttachment => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const input = value as Record<string, unknown>;
  const fields: Record<keyof AgentTaskAttachment, Check> = {
    attachment_id: uuid,
    display_name: nullable(value => typeof value === "string" && value.length > 0 && value.length <= 255),
    extension: nullable(value => typeof value === "string" && /^[a-z0-9]+$/.test(value) && value.length <= 16),
    byte_size: nullable(value => typeof value === "number" && Number.isSafeInteger(value) && value >= 0),
    status: attachmentStatus,
    created_at: date,
    updated_at: date,
    expires_at: date,
  };
  return Object.keys(input).length === Object.keys(fields).length
    && Object.entries(fields).every(([key, check]) => Object.prototype.hasOwnProperty.call(input, key) && check(input[key]));
};

function parse(value: unknown): AgentTaskAttachment {
  if (!attachment(value)) throw new Error("Invalid Agent attachment response");
  return value;
}

const base = (taskId: string) => `/agent/tasks/${taskId}/attachments`;

export async function getAttachmentAvailability(taskId: string, signal?: AbortSignal): Promise<{ enabled: true }> {
  const value = (await client.get(`${base(taskId)}/availability`, { signal })).data;
  if (typeof value !== "object" || value === null || Array.isArray(value)
    || Object.keys(value).length !== 1 || (value as { enabled?: unknown }).enabled !== true)
    throw new Error("Invalid Agent attachment availability");
  return { enabled: true };
}

export async function uploadTaskAttachment(taskId: string, file: File, signal?: AbortSignal): Promise<AgentTaskAttachment> {
  const body = new FormData();
  body.append("file", file);
  return parse((await client.post(base(taskId), body, { signal })).data);
}

export async function listTaskAttachments(taskId: string, signal?: AbortSignal): Promise<{ items: AgentTaskAttachment[] }> {
  const value = (await client.get(base(taskId), { signal })).data;
  if (typeof value !== "object" || value === null || Array.isArray(value)
    || Object.keys(value).length !== 1 || !Array.isArray((value as { items?: unknown }).items))
    throw new Error("Invalid Agent attachment list");
  return { items: (value as { items: unknown[] }).items.map(parse) };
}

export async function downloadTaskAttachment(taskId: string, attachmentId: string, signal?: AbortSignal): Promise<Blob> {
  const response = await client.get(`${base(taskId)}/${attachmentId}/download`, { signal, responseType: "blob" });
  if (!(response.data instanceof Blob)) throw new Error("Invalid Agent attachment download");
  return response.data;
}

export async function deleteTaskAttachment(taskId: string, attachmentId: string, signal?: AbortSignal): Promise<void> {
  await client.delete(`${base(taskId)}/${attachmentId}`, { signal });
}
