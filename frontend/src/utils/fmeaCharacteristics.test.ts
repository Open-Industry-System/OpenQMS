import { describe, expect, it } from "vitest";
import type { Characteristic, GraphEdge, GraphNode } from "../types";
import {
  characteristicKindForFunction,
  cleanupCharacteristicReferences,
  findCharacteristicReferenceImpacts,
  getSameStepProductCharacteristicOptions,
  updateFunctionCharacteristics,
} from "./fmeaCharacteristics";

const Z = { severity: 0, occurrence: 0, detection: 0 };

const product: Characteristic = {
  id: "product-char",
  kind: "product",
  name: "贴装偏移量",
  specification: "≤0.05",
  unit: "mm",
  classification: null,
  reference: null,
  related_product_characteristic_ids: [],
};

const process: Characteristic = {
  id: "process-char",
  kind: "process",
  name: "贴装压力",
  specification: "3.0±0.5",
  unit: "N",
  classification: "SC",
  reference: null,
  related_product_characteristic_ids: ["product-char"],
};

describe("fmeaCharacteristics", () => {
  it("derives kind from actual unique HAS_FUNCTION ownership rather than shared function names", () => {
    const nodes: GraphNode[] = [
      { id: "step", type: "ProcessStep", name: "SMT", ...Z },
      { id: "we", type: "ProcessWorkElement", name: "Machine", ...Z },
      { id: "component", type: "Component", name: "PCB", ...Z },
      { id: "fn", type: "ProcessWorkElementFunction", name: "function", ...Z },
    ];
    const owner = (source: string): GraphEdge => ({ source, target: "fn", type: "HAS_FUNCTION" });
    const parent: GraphEdge = { source: "step", target: "we", type: "HAS_WORK_ELEMENT" };
    expect(characteristicKindForFunction("PFMEA", "fn", nodes, [owner("step")])).toBe("product");
    expect(characteristicKindForFunction("PFMEA", "fn", nodes, [owner("we"), parent])).toBe("process");
    expect(characteristicKindForFunction("DFMEA", "fn", nodes, [owner("component")])).toBe("product");
    for (const edges of [[], [owner("missing")], [owner("step"), owner("we")], [owner("we")]]) {
      expect(characteristicKindForFunction("PFMEA", "fn", nodes, edges)).toBeUndefined();
    }
    expect(characteristicKindForFunction("DFMEA", "fn", nodes, [owner("step")])).toBeUndefined();
    expect(characteristicKindForFunction("PFMEA", "fn", nodes, [owner("component")])).toBeUndefined();
    expect(characteristicKindForFunction(undefined, "fn", nodes, [owner("step")])).toBeUndefined();
    expect(characteristicKindForFunction("PFMEA", "step", nodes, [owner("step")])).toBeUndefined();
    expect(nodes[3].characteristics).toBeUndefined();
  });

  it("updates only the selected function and preserves every other graph field", () => {
    const nodes: GraphNode[] = [
      { id: "fn", type: "ProcessStepFunction", name: "准确贴装", specification: "legacy", characteristics: [], ...Z },
      { id: "fm", type: "FailureMode", name: "虚焊", severity: 8, occurrence: 3, detection: 4 },
    ];

    expect(updateFunctionCharacteristics(nodes, "fn", [product])).toEqual([
      expect.objectContaining({ id: "fn", name: "准确贴装", specification: "legacy", characteristics: [product] }),
      nodes[1],
    ]);
  });

  it("offers only product characteristics from the same PFMEA step", () => {
    const nodes: GraphNode[] = [
      { id: "step-1", type: "ProcessStep", name: "贴装", ...Z },
      { id: "step-2", type: "ProcessStep", name: "回流焊", ...Z },
      { id: "product-fn", type: "ProcessStepFunction", name: "准确贴装", characteristics: [product], ...Z },
      { id: "other-product-fn", type: "ProcessStepFunction", name: "焊点质量", characteristics: [{ ...product, id: "other-char" }], ...Z },
      { id: "process-fn", type: "ProcessWorkElementFunction", name: "贴装压力", ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: "step-1", target: "product-fn", type: "HAS_FUNCTION" },
      { source: "step-1", target: "process-fn", type: "HAS_WORK_ELEMENT" },
      { source: "step-2", target: "other-product-fn", type: "HAS_FUNCTION" },
    ];

    expect(getSameStepProductCharacteristicOptions(nodes, edges, "process-fn")).toEqual([
      { id: "product-char", name: "贴装偏移量" },
    ]);
  });

  it("reports and removes process references when a product characteristic is confirmed deleted", () => {
    const nodes: GraphNode[] = [
      { id: "product-fn", type: "ProcessStepFunction", name: "准确贴装", characteristics: [product], ...Z },
      { id: "process-fn", type: "ProcessWorkElementFunction", name: "贴装压力", characteristics: [process], ...Z },
    ];

    expect(findCharacteristicReferenceImpacts(nodes, ["product-char"])).toEqual([
      { functionId: "process-fn", characteristicId: "process-char", characteristicName: "贴装压力" },
    ]);
    expect(cleanupCharacteristicReferences(nodes, ["product-char"])[1].characteristics?.[0].related_product_characteristic_ids).toEqual([]);
  });
});
