import client from "./client";

export interface AnalyzeChangeImpactRequest {
  fmea_id: string;
  node_id: string;
  node_type: string;
  node_name: string;
  change_type: "attribute" | "structural";
  field_name?: string;
  new_value?: string;
}

export interface AffectedNode {
  node_id: string;
  node_type: string;
  name: string;
  path: string[];
  impact_type: string;
  hop_distance: number;
  risk_change: Record<string, unknown> | null;
}

export interface ImpactSummary {
  total_affected: number;
  failure_modes_affected: number;
  controls_affected: number;
  ap_upgraded_count: number;
  max_hop_distance: number;
}

export interface ChangeImpactResult {
  affected_nodes: AffectedNode[];
  summary: ImpactSummary;
}

export interface ChangeImpactAnalysis {
  id: string;
  fmea_id: string;
  product_line_code: string;
  node_id: string;
  node_type: string;
  node_name: string;
  change_type: string;
  field_name: string | null;
  old_value: string | null;
  new_value: string | null;
  scope: string;
  status: string;
  impact_score: number;
  impact_result: ChangeImpactResult;
  created_by: string;
  created_at: string;
}

export async function analyzeChangeImpact(data: AnalyzeChangeImpactRequest): Promise<ChangeImpactAnalysis> {
  const resp = await client.post("/change-impact/analyze", data);
  return resp.data;
}

export async function listChangeImpacts(fmeaId: string): Promise<ChangeImpactAnalysis[]> {
  const resp = await client.get(`/change-impact/fmea/${fmeaId}`);
  return resp.data;
}

export async function listAllChangeImpacts(productLineCode?: string): Promise<ChangeImpactAnalysis[]> {
  const resp = await client.get("/change-impact", {
    params: productLineCode ? { product_line_code: productLineCode } : undefined,
  });
  return resp.data;
}

export async function getChangeImpact(id: string): Promise<ChangeImpactAnalysis> {
  const resp = await client.get(`/change-impact/${id}`);
  return resp.data;
}
