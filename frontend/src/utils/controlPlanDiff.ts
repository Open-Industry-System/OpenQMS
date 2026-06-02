import type { ControlPlanItem } from "../types";
import type { GraphDiff } from "./graphDiff";

export interface CPItemChange {
  type: "added" | "removed" | "modified";
  item_id: string;
  field?: string;
  oldValue?: unknown;
  newValue?: unknown;
  step_no?: string;
}

export interface ControlPlanDiff {
  itemChanges: CPItemChange[];
  conflictingFields: CPItemChange[];
}

export function adaptCPDiffToGraphDiff(cpDiff: ControlPlanDiff | null): GraphDiff | null {
  if (!cpDiff) return null;
  return {
    nodeChanges: cpDiff.itemChanges.map((c) => ({
      type: c.type,
      node_id: c.item_id,
      field: c.field,
      oldValue: c.oldValue,
      newValue: c.newValue,
      nodeType: c.step_no || "Item",
      name: c.step_no || "",
    })),
    edgeChanges: [],
    conflictingFields: cpDiff.conflictingFields.map((c) => ({
      type: c.type,
      node_id: c.item_id,
      field: c.field,
      oldValue: c.oldValue,
      newValue: c.newValue,
      nodeType: c.step_no || "Item",
      name: c.step_no || "",
    })),
  };
}

const ITEM_FIELDS: (keyof ControlPlanItem)[] = [
  "step_no",
  "process_name",
  "equipment",
  "characteristic_no",
  "product_characteristic",
  "process_characteristic",
  "special_class",
  "specification_tolerance",
  "evaluation_method",
  "sample_size",
  "sample_frequency",
  "control_method",
  "reaction_plan",
];

export function diffControlPlanItems(
  baseItems: ControlPlanItem[],
  latestItems: ControlPlanItem[],
  localItems: ControlPlanItem[]
): ControlPlanDiff {
  const itemChanges: CPItemChange[] = [];
  const conflictingFields: CPItemChange[] = [];

  const baseMap = new Map(baseItems.map((i) => [i.item_id, i]));
  const latestMap = new Map(latestItems.map((i) => [i.item_id, i]));
  const localMap = new Map(localItems.map((i) => [i.item_id, i]));

  // Check added/modified in latest
  for (const [id, latestItem] of latestMap) {
    const baseItem = baseMap.get(id);
    if (!baseItem) {
      itemChanges.push({
        type: "added",
        item_id: id,
        step_no: latestItem.step_no,
      });
    } else {
      for (const field of ITEM_FIELDS) {
        const baseVal = (baseItem as unknown as Record<string, unknown>)[field] ?? "";
        const latestVal = (latestItem as unknown as Record<string, unknown>)[field] ?? "";
        const localItem = localMap.get(id);
        const localVal = localItem ? (localItem as unknown as Record<string, unknown>)[field] ?? "" : "";

        if (baseVal !== latestVal) {
          itemChanges.push({
            type: "modified",
            item_id: id,
            field,
            oldValue: baseVal,
            newValue: latestVal,
            step_no: latestItem.step_no,
          });

          // Conflict if local also modified this field
          if (localItem && localVal !== "" && baseVal !== localVal) {
            conflictingFields.push({
              type: "modified",
              item_id: id,
              field,
              oldValue: baseVal,
              newValue: latestVal,
              step_no: latestItem.step_no,
            });
          }
        }
      }
    }
  }

  // Check removed
  for (const [id, baseItem] of baseMap) {
    if (!latestMap.has(id)) {
      itemChanges.push({
        type: "removed",
        item_id: id,
        step_no: baseItem.step_no,
      });
    }
  }

  return { itemChanges, conflictingFields };
}
