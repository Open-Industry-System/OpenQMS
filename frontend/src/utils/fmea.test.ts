import { describe, it, expect } from "vitest";
import { calculateAP } from "./fmea";

describe("calculateAP - AIAG-VDA 2019 matrix", () => {
  // Severity 9-10
  it("returns H for S=10, O=4, D=1", () => {
    expect(calculateAP(10, 4, 1)).toBe("H");
  });
  it("returns H for S=10, O=3, D=7", () => {
    expect(calculateAP(10, 3, 7)).toBe("H");
  });
  it("returns M for S=10, O=3, D=5", () => {
    expect(calculateAP(10, 3, 5)).toBe("M");
  });
  it("returns L for S=10, O=3, D=4", () => {
    expect(calculateAP(10, 3, 4)).toBe("L");
  });
  it("returns L for S=10, O=1, D=1", () => {
    expect(calculateAP(10, 1, 1)).toBe("L");
  });

  // Severity 7-8
  it("returns H for S=8, O=8, D=1", () => {
    expect(calculateAP(8, 8, 1)).toBe("H");
  });
  it("returns H for S=8, O=6, D=2", () => {
    expect(calculateAP(8, 6, 2)).toBe("H");
  });
  it("returns M for S=8, O=6, D=1", () => {
    expect(calculateAP(8, 6, 1)).toBe("M");
  });
  it("returns H for S=8, O=4, D=7", () => {
    expect(calculateAP(8, 4, 7)).toBe("H");
  });
  it("returns M for S=8, O=4, D=6", () => {
    expect(calculateAP(8, 4, 6)).toBe("M");
  });
  it("returns M for S=8, O=2, D=5", () => {
    expect(calculateAP(8, 2, 5)).toBe("M");
  });
  it("returns L for S=8, O=2, D=4", () => {
    expect(calculateAP(8, 2, 4)).toBe("L");
  });

  // Severity 4-6
  it("returns H for S=6, O=8, D=5", () => {
    expect(calculateAP(6, 8, 5)).toBe("H");
  });
  it("returns M for S=6, O=8, D=4", () => {
    expect(calculateAP(6, 8, 4)).toBe("M");
  });
  it("returns M for S=6, O=6, D=2", () => {
    expect(calculateAP(6, 6, 2)).toBe("M");
  });
  it("returns L for S=6, O=6, D=1", () => {
    expect(calculateAP(6, 6, 1)).toBe("L");
  });

  // Severity 1-3
  it("returns M for S=3, O=8, D=5", () => {
    expect(calculateAP(3, 8, 5)).toBe("M");
  });
  it("returns L for S=3, O=8, D=4", () => {
    expect(calculateAP(3, 8, 4)).toBe("L");
  });
  it("returns L for S=3, O=1, D=1", () => {
    expect(calculateAP(3, 1, 1)).toBe("L");
  });

  // Invalid
  it("returns empty string for out-of-range inputs", () => {
    expect(calculateAP(11, 5, 5)).toBe("");
    expect(calculateAP(5, 0, 5)).toBe("");
    expect(calculateAP(5, 5, 11)).toBe("");
  });
});
