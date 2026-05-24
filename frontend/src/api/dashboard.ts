import client from "./client";
import type { DashboardData } from "../types";

export async function getDashboard(productLine?: string): Promise<DashboardData> {
  const resp = await client.get("/dashboard", { params: { product_line: productLine || undefined } });
  return resp.data;
}
