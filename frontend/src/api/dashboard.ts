import client from "./client";
import type {
  DashboardData,
  DashboardSummary,
  DashboardAlerts,
  DashboardRecentAction,
  DashboardWidgetLayoutConfig,
  DashboardWidgetData,
  QualityTrendInterpretation,
} from "../types";

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

export async function getDashboardLayout(): Promise<{
  layout_id: string | null;
  layout_config: DashboardWidgetLayoutConfig;
}> {
  const resp = await client.get("/dashboard/layout");
  return resp.data;
}

export async function saveDashboardLayout(
  layoutConfig: DashboardWidgetLayoutConfig
): Promise<unknown> {
  const resp = await client.put("/dashboard/layout", { layout_config: layoutConfig });
  return resp.data;
}

export async function getDashboardWidgets(
  types: string[],
  productLine?: string
): Promise<DashboardWidgetData> {
  const resp = await client.get("/dashboard/widgets", {
    params: {
      types: types.join(","),
      product_line: productLine || undefined,
    },
  });
  return resp.data;
}

export async function interpretQualityTrend(params: { product_line?: string }): Promise<QualityTrendInterpretation> {
  const resp = await client.post("/dashboard/widgets/quality-trend/interpret", params);
  return resp.data;
}
