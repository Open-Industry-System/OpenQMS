import { describe, expect, it } from "vitest";
import type { Characteristic, GraphNode } from "../types";
import { diffGraphs } from "./graphDiff";

const Z = { severity: 0, occurrence: 0, detection: 0 };

const characteristic = (classification: string | null): Characteristic => ({
  id: "product-char",
  kind: "product",
  name: "贴装偏移量",
  specification: "≤0.05",
  unit: "mm",
  classification,
  reference: "DWG-01",
  related_product_characteristic_ids: [],
});

const node = (patch: Partial<GraphNode> = {}): GraphNode => ({
  id: "function-1",
  type: "ProcessStepFunction",
  name: "准确贴装",
  characteristics: [],
  ...Z,
  ...patch,
});

describe("diffGraphs structured characteristics", () => {
  it("reports a remote characteristic addition while local changes another field", () => {
    const result = diffGraphs(
      [node()], [],
      [node({ characteristics: [characteristic("CC")] })], [],
      [node({ name: "精确贴装" })], [],
    );

    expect(result.nodeChanges).toEqual(expect.arrayContaining([
      expect.objectContaining({ node_id: "function-1", field: "characteristics" }),
    ]));
    expect(result.conflictingFields).toEqual([]);
  });

  it("marks concurrent characteristic edits as a conflict using deep content comparison", () => {
    const result = diffGraphs(
      [node({ characteristics: [characteristic(null)] })], [],
      [node({ characteristics: [characteristic("CC")] })], [],
      [node({ characteristics: [characteristic("SC")] })], [],
    );

    expect(result.conflictingFields).toEqual(expect.arrayContaining([
      expect.objectContaining({ node_id: "function-1", field: "characteristics" }),
    ]));
  });

  it("does not report equivalent characteristic arrays with different references", () => {
    const base = [characteristic("CC")];
    const result = diffGraphs(
      [node({ characteristics: base })], [],
      [node({ characteristics: [{ ...base[0] }] })], [],
      [node({ characteristics: [{ ...base[0] }] })], [],
    );

    expect(result.nodeChanges).toEqual([]);
    expect(result.conflictingFields).toEqual([]);
  });
});
