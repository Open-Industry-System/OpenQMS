import client from "./client";
import type { DashboardData, DashboardSummary, DashboardAlerts, DashboardRecentAction } from "../types";

export async function getDashboard(productLine?: string): Promise<DashboardData> {
  const resp = await client.get("/dashboard", { params: { product_line: productLine || undefined } });
  return resp.data;
}

export async function getDashboardSummary(productLine?: string): Promise<DashboardSummary> {
  const resp = await client.get("/dashboard/summary", { params: { product_line: productLine || undefined } });
  return resp.data;
}

export async function getDashboardAlerts(productLine?: string): Promise<DashboardAlerts> {
  const resp = await client.get("/dashboard/alerts", { params: { product_line: productLine || undefined } });
  return resp.data;
}

export async function getDashboardRecentActions(): Promise<DashboardRecentAction[]> {
  const resp = await client.get("/dashboard/recent-actions");
  return resp.data;
}
