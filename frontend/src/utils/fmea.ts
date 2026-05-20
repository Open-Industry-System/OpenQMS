/**
 * Calculates the Action Priority (AP) based on Severity (S), Occurrence (O), and Detection (D) scores.
 * Ref: AIAG-VDA FMEA Handbook (2019) Appendix C1.5
 * Returns "H" (High), "M" (Medium), "L" (Low), or "" (if S/O/D are out of range)
 */
export function calculateAP(s: number, o: number, d: number): "H" | "M" | "L" | "" {
  if (s < 1 || s > 10 || o < 1 || o > 10 || d < 1 || d > 10) {
    return "";
  }

  // Severity 9-10
  if (s >= 9) {
    if (o >= 4) return "H";
    if (o === 3 || o === 2) {
      return d >= 7 ? "H" : d >= 5 ? "M" : "L";
    }
    return "L"; // o === 1
  }

  // Severity 7-8
  if (s >= 7) {
    if (o >= 8) return "H";
    if (o === 6 || o === 7) {
      return d >= 2 ? "H" : "M";
    }
    if (o === 4 || o === 5) {
      return d >= 7 ? "H" : "M";
    }
    if (o === 2 || o === 3) {
      return d >= 5 ? "M" : "L";
    }
    return "L"; // o === 1
  }

  // Severity 4-6
  if (s >= 4) {
    if (o >= 8) {
      return d >= 5 ? "H" : "M";
    }
    if (o === 6 || o === 7) {
      return d >= 2 ? "M" : "L";
    }
    if (o === 4 || o === 5) {
      return d >= 7 ? "M" : "L";
    }
    return "L"; // o <= 3
  }

  // Severity 1-3
  if (o >= 8) {
    return d >= 5 ? "M" : "L";
  }
  return "L";
}
