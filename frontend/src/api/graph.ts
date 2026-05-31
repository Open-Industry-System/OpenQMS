import client from "./client";

// ========== 原始数据类型（后端返回的多种格式）==========
export interface RawGraphNode {
  id?: string;
  node_id?: string;
  type?: string;
  label?: string;
  name?: string;
  severity?: number;
  occurrence?: number;
  detection?: number;
  ap?: string;
  [key: string]: unknown;
}

export interface RawGraphEdge {
  source: string;
  target: string;
  type?: string;
  label?: string;
}

// ========== 渲染数据类型（GraphCanvas 统一消费）==========
export interface RenderGraphNode {
  id: string;
  label: string;
  properties: {
    name: string;
    severity?: number;
    occurrence?: number;
    detection?: number;
    ap?: string;
    [key: string]: unknown;
  };
  style?: unknown;
}

export interface RenderGraphEdge {
  source: string;
  target: string;
  label: string;
  properties?: Record<string, unknown>;
}

// ========== 转换层（抹平 JSONB 扁平结构 vs Neo4j 嵌套结构）==========
export function normalizeGraphData(
  rawNodes: Array<Record<string, unknown>>,
  rawEdges: Array<Record<string, unknown>>
): { nodes: RenderGraphNode[]; edges: RenderGraphEdge[] } {
  return {
    nodes: rawNodes.map((n) => {
      const id = (n.id as string) ?? (n.node_id as string) ?? "";
      const label = (n.type as string) ?? (n.label as string) ?? "";
      const props = (n.properties as Record<string, unknown>) ?? n;
      return {
        id,
        label,
        properties: {
          name: (props.name as string) ?? (n.name as string) ?? "",
          severity: (props.severity as number) ?? (n.severity as number),
          occurrence: (props.occurrence as number) ?? (n.occurrence as number),
          detection: (props.detection as number) ?? (n.detection as number),
          ap: (props.ap as string) ?? (n.ap as string),
          ...props,
        },
        style: undefined,
      };
    }),
    edges: rawEdges.map((e) => ({
      source: (e.source as string) ?? "",
      target: (e.target as string) ?? "",
      label: (e.type as string) ?? (e.label as string) ?? "",
      properties: undefined,
    })),
  };
}

// ========== 兼容别名（后续组件统一使用 GraphNode / GraphEdge）==========
export type GraphNode = RenderGraphNode;
export type GraphEdge = RenderGraphEdge;

// ========== API 返回类型（原始数据，需 normalize 后使用）==========
export interface GraphChainResponse {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

export interface SimilarNode {
  node_id: string;
  name: string;
  type: string;
  fmea_id: string;
  document_no?: string;
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
    document_no?: string;
  }>;
  avg_rpn: number;
  top_failure_modes: Array<{ name: string; rpn: number; fmea_id: string }>;
}

export async function getImpactChain(
  fmeaId: string,
  nodeId: string
): Promise<GraphChainResponse> {
  const resp = await client.get(`/graph/fmea/${fmeaId}/impact/${nodeId}`);
  return resp.data;
}

export async function getCauseChain(
  fmeaId: string,
  nodeId: string
): Promise<GraphChainResponse> {
  const resp = await client.get(`/graph/fmea/${fmeaId}/cause/${nodeId}`);
  return resp.data;
}

export async function searchSimilarNodes(params: {
  node_type: string;
  name_keyword: string;
  product_line_code: string;
  limit?: number;
}): Promise<SimilarNode[]> {
  const resp = await client.get("/graph/similar", { params });
  return resp.data;
}

export async function getCrossFmeaStats(
  productLineCode: string
): Promise<CrossFmeaStats> {
  const resp = await client.get("/graph/stats", {
    params: { product_line_code: productLineCode },
  });
  return resp.data;
}
