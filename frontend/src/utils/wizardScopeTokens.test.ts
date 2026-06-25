import { describe, it, expect } from "vitest";
import { parseScopeTokens, stringifyScopeTokens } from "./wizardScopeTokens";

describe("parseScopeTokens", () => {
  it("splits on 、", () => {
    expect(parseScopeTokens("边界图、P图、接口矩阵")).toEqual(["边界图", "P图", "接口矩阵"]);
  });
  it("splits on ASCII and fullwidth , ; ，；", () => {
    expect(parseScopeTokens("a,b；c，d;e")).toEqual(["a", "b", "c", "d", "e"]);
  });
  it("trims tokens", () => {
    expect(parseScopeTokens(" 边界图 、 P图 ")).toEqual(["边界图", "P图"]);
  });
  it("dedupes preserving first-seen order", () => {
    expect(parseScopeTokens("边界图、P图、边界图")).toEqual(["边界图", "P图"]);
  });
  it("returns [] for empty/whitespace/null/undefined", () => {
    expect(parseScopeTokens("")).toEqual([]);
    expect(parseScopeTokens("   ")).toEqual([]);
    expect(parseScopeTokens(null)).toEqual([]);
    expect(parseScopeTokens(undefined)).toEqual([]);
  });
  it("returns a single value as one-element array", () => {
    expect(parseScopeTokens("FMEA模板")).toEqual(["FMEA模板"]);
  });
});

describe("stringifyScopeTokens", () => {
  it("joins with 、", () => {
    expect(stringifyScopeTokens(["边界图", "P图"])).toBe("边界图、P图");
  });
  it("returns '' for empty/null/undefined", () => {
    expect(stringifyScopeTokens([])).toBe("");
    expect(stringifyScopeTokens(null)).toBe("");
    expect(stringifyScopeTokens(undefined)).toBe("");
  });
  it("trims and drops empty tokens", () => {
    expect(stringifyScopeTokens([" 边界图 ", "", "P图"])).toBe("边界图、P图");
  });
  it("dedupes preserving first-seen order", () => {
    expect(stringifyScopeTokens(["边界图", "P图", "边界图"])).toBe("边界图、P图");
  });
  it("round-trips via parse", () => {
    const s = "边界图、P图、接口矩阵";
    expect(stringifyScopeTokens(parseScopeTokens(s))).toBe(s);
  });
});
