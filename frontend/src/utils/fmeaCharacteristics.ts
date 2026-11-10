import type { Characteristic, GraphEdge, GraphNode } from "../types";

export interface CharacteristicOption {
  id: string;
  name: string;
}

export interface CharacteristicReferenceImpact {
  functionId: string;
  characteristicId: string;
  characteristicName: string;
}

export function characteristicKindForFunction(
  fmeaType: string | undefined,
  functionId: string,
  nodes: GraphNode[],
  edges: GraphEdge[],
): Characteristic["kind"] | undefined {
  const functionNode = nodes.find((node) => node.id === functionId);
  if (!functionNode?.type.endsWith("Function")) return undefined;
  const owners = edges.filter((edge) => edge.type === "HAS_FUNCTION" && edge.target === functionId);
  if (owners.length !== 1) return undefined;
  const owner = nodes.find((node) => node.id === owners[0].source);
  if (fmeaType === "DFMEA") {
    return owner && ["System", "Subsystem", "Component"].includes(owner.type) ? "product" : undefined;
  }
  if (fmeaType === "PFMEA") {
    if (owner?.type === "ProcessStep") return "product";
    if (owner?.type === "ProcessWorkElement") {
      const parents = edges.filter((edge) => edge.type === "HAS_WORK_ELEMENT" && edge.target === owner.id);
      if (parents.length === 1 && nodes.some((node) => node.id === parents[0].source && node.type === "ProcessStep")) return "process";
    }
  }
  return undefined;
}

export function updateFunctionCharacteristics(
  nodes: GraphNode[],
  functionId: string,
  characteristics: Characteristic[],
): GraphNode[] {
  return nodes.map((node) =>
    node.id === functionId ? { ...node, characteristics } : node,
  );
}

export function getSameStepProductCharacteristicOptions(
  nodes: GraphNode[],
  edges: GraphEdge[],
  processFunctionId: string,
): CharacteristicOption[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const functionOwnerId = edges.find(
    (edge) => edge.type === "HAS_FUNCTION" && edge.target === processFunctionId,
  )?.source ?? processFunctionId;
  const stepId = edges.find(
    (edge) => edge.type === "HAS_WORK_ELEMENT" && edge.target === functionOwnerId,
  )?.source;
  if (!stepId) return [];

  return edges
    .filter((edge) => edge.type === "HAS_FUNCTION" && edge.source === stepId)
    .flatMap((edge) => nodeById.get(edge.target)?.characteristics ?? [])
    .filter((characteristic) => characteristic.kind === "product")
    .map(({ id, name }) => ({ id, name }));
}

export function findCharacteristicReferenceImpacts(
  nodes: GraphNode[],
  deletedProductCharacteristicIds: string[],
): CharacteristicReferenceImpact[] {
  const deletedIds = new Set(deletedProductCharacteristicIds);
  return nodes.flatMap((node) =>
    (node.characteristics ?? [])
      .filter((characteristic) =>
        characteristic.kind === "process" &&
        characteristic.related_product_characteristic_ids.some((id) => deletedIds.has(id)),
      )
      .map((characteristic) => ({
        functionId: node.id,
        characteristicId: characteristic.id,
        characteristicName: characteristic.name,
      })),
  );
}

export function cleanupCharacteristicReferences(
  nodes: GraphNode[],
  deletedProductCharacteristicIds: string[],
): GraphNode[] {
  const deletedIds = new Set(deletedProductCharacteristicIds);
  return nodes.map((node) => {
    if (!Array.isArray(node.characteristics)) return node;
    return {
      ...node,
      characteristics: node.characteristics.map((characteristic) =>
        characteristic.kind === "process"
          ? {
              ...characteristic,
              related_product_characteristic_ids: characteristic.related_product_characteristic_ids.filter(
                (id) => !deletedIds.has(id),
              ),
            }
          : characteristic,
      ),
    };
  });
}
