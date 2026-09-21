import { describe, expect, it } from "vitest";
import zh from "./zh-CN/home.json";
import en from "./en-US/home.json";

function shape(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(shape);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, child]) => [key, shape(child)]),
    );
  }
  return typeof value;
}

describe("home i18n contract", () => {
  it("keeps Chinese and English structures identical", () => {
    expect(shape(en)).toEqual(shape(zh));
  });

  it("keeps the approved section cardinalities", () => {
    for (const locale of [zh, en]) {
      expect(locale.metrics).toHaveLength(4);
      expect(locale.ai.stages).toHaveLength(4);
      expect(locale.ai.useCases).toHaveLength(4);
      expect(locale.ai.trust).toHaveLength(6);
      expect(locale.capabilities.items).toHaveLength(6);
      expect(locale.architecture.stack).toHaveLength(7);
    }
  });
});
