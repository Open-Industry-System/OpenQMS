import client from "./client";

export interface ImpactChainResponse {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

export interface SimilarNode {
  node_id: string;
  name: string;
  type: string;
  fmea_id: string;
  document_no: string;
}

export interface CrossFmeaStats {
  total_fmeas: number;
  total_nodes: number;
  node_type_distribution: Record<string, number>;
  ap_distribution: { H: number; M: number; L: number };
  high_ap_nodes: Array<{
    node_id: string;
    name: string;
    ap: string;
    rpn: number;
    fmea_id: string;
    document_no: string;
  }>;
  avg_rpn: number;
  top_failure_modes: Array<{
    name: string;
    rpn: number;
    fmea_id: string;
    document_no: string;
  }>;
}

export async function getImpactChain(
  fmeaId: string,
  nodeId: string
): Promise<ImpactChainResponse> {
  const res = await client.get(`/graph/fmea/${fmeaId}/impact/${nodeId}`);
  return res.data;
}

export async function getCauseChain(
  fmeaId: string,
  nodeId: string
): Promise<ImpactChainResponse> {
  const res = await client.get(`/graph/fmea/${fmeaId}/cause/${nodeId}`);
  return res.data;
}

export async function searchSimilarNodes(params: {
  node_type: string;
  name_keyword: string;
  product_line_code: string;
  limit?: number;
}): Promise<SimilarNode[]> {
  const res = await client.get("/graph/similar", { params });
  return res.data;
}

export async function getCrossFmeaStats(
  productLineCode: string
): Promise<CrossFmeaStats> {
  const res = await client.get("/graph/stats", {
    params: { product_line_code: productLineCode },
  });
  return res.data;
}

export async function triggerRebuild(): Promise<{ message: string }> {
  const res = await client.post("/graph/rebuild");
  return res.data;
}
