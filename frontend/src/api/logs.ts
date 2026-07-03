import client from "./client";
import type { PaginatedResponse, AuditLogItem, LoginLogItem, SystemLogItem } from "../types";

export async function listAuditLogs(params: Record<string, unknown>): Promise<PaginatedResponse<AuditLogItem>> {
  const resp = await client.get("/admin/logs/audit", { params });
  return resp.data;
}

export async function listLoginLogs(params: Record<string, unknown>): Promise<PaginatedResponse<LoginLogItem>> {
  const resp = await client.get("/admin/logs/login", { params });
  return resp.data;
}

export async function listSystemLogs(params: Record<string, unknown>): Promise<PaginatedResponse<SystemLogItem>> {
  const resp = await client.get("/admin/logs/system", { params });
  return resp.data;
}
