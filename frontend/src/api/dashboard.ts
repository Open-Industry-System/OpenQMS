import client from "./client";
import type { DashboardData } from "../types";

export async function getDashboard(): Promise<DashboardData> {
  const resp = await client.get("/dashboard");
  return resp.data;
}
