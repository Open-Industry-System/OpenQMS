import type { GraphNode, GraphEdge } from "../types";

/** 工具映射的目标结构节点类型（仅结构类工具产生）。 */
export type StructureNodeType = "Interface" | "DesignParameter";

/** HAS_PARAMETER 边的合法 source：结构节点类型。 */
const STRUCTURE_PARENT_TYPES = new Set(["System", "Subsystem", "Component"]);

/**
 * 所选工具中、映射到指定 nodeType 的工具列表（去重、保序）。
 * toolStructureMap: { 工具存盘值: 节点类型 }（i18n 取，含双语 key）。
 */
export function toolsRequiringNodeType(
  selectedTools: string[],
  toolStructureMap: Record<string, string>,
  nodeType: StructureNodeType,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const tool of selectedTools) {
    if (toolStructureMap[tool] === nodeType && !seen.has(tool)) {
      seen.add(tool);
      out.push(tool);
    }
  }
  return out;
}

/**
 * 所选工具产生的结构缺口：工具→其要求的 nodeType，且该 nodeType 无任何通过
 * HAS_PARAMETER 挂接到【结构节点】的实例。仅 target 类型匹配不够——还须 source
 * 存在且为结构节点（System/Subsystem/Component），否则坏边（如 FailureCause→Interface
 * 或悬空 source）会让缺口错误消失。游离节点不算满足。
 */
export function structureGapsForTools(
  selectedTools: string[],
  toolStructureMap: Record<string, string>,
  nodes: GraphNode[],
  edges: GraphEdge[],
): Array<{ tool: string; nodeType: StructureNodeType }> {
  const nodeById = new Map(nodes.map((nd) => [nd.id, nd]));
  const attachedCountByType = new Map<string, number>();
  for (const ed of edges) {
    if (ed.type !== "HAS_PARAMETER") continue;
    const target = nodeById.get(ed.target);
    const source = nodeById.get(ed.source);
    if (!target || !source) continue; // 悬空 source/target 不算
    if (!STRUCTURE_PARENT_TYPES.has(source.type)) continue; // source 非结构节点不算
    attachedCountByType.set(target.type, (attachedCountByType.get(target.type) ?? 0) + 1);
  }

  const gaps: Array<{ tool: string; nodeType: StructureNodeType }> = [];
  const seenTools = new Set<string>();
  for (const tool of selectedTools) {
    const mapped = toolStructureMap[tool];
    if (mapped !== "Interface" && mapped !== "DesignParameter") continue;
    if (seenTools.has(tool)) continue;
    seenTools.add(tool);
    if ((attachedCountByType.get(mapped) ?? 0) === 0) {
      gaps.push({ tool, nodeType: mapped });
    }
  }
  return gaps;
}

/**
 * 选 Interface/DesignParameter 的挂接 parent：优先 Component，其次 System/Subsystem。
 * 无结构节点时返回 null（调用方应提示用户先建结构，不创建游离节点）。
 */
export function pickParamParent(nodes: GraphNode[]): GraphNode | null {
  return (
    nodes.find((nd) => nd.type === "Component") ??
    nodes.find((nd) => nd.type === "System") ??
    nodes.find((nd) => nd.type === "Subsystem") ??
    null
  );
}

/**
 * 纯函数构造一个挂接到 parent 的 Interface/DesignParameter 节点 + HAS_PARAMETER 边。
 * idFactory 注入避免在纯函数里碰 crypto（测试可传固定 id）。
 * 组件的 addAttachedParamNode 是此函数的薄包装（取 parent、调 updateGraphData）。
 */
export function buildAttachedParamNode(
  parent: GraphNode,
  nodeType: StructureNodeType,
  idFactory: () => string,
): { node: GraphNode; edge: GraphEdge } {
  const id = idFactory();
  const node: GraphNode = {
    id,
    type: nodeType,
    name: "", // 组件层用 i18n typeLabels 填名；纯函数保持无 i18n 依赖
    severity: 0,
    occurrence: 0,
    detection: 0,
    ...(nodeType === "Interface" ? { interface_type: "physical" } : {}),
  };
  const edge: GraphEdge = { source: parent.id, target: id, type: "HAS_PARAMETER" };
  return { node, edge };
}
