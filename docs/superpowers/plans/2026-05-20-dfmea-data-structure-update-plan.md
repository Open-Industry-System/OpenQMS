# DFMEA Data Structure Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the backend Pydantic schema and frontend TypeScript types of FMEA GraphNode to support all necessary attributes for DFMEA AIAG-VDA 5th edition, and implement the dynamic AP (Action Priority) calculation.

**Architecture:** Extend `GraphNodeSchema` in FastAPI/Pydantic and `GraphNode` in React/TypeScript with optional fields so that both DFMEA and PFMEA share the same flexible graph schema, storing technical requirements, design specifications, and optimization measures directly in nodes without database modification.

**Tech Stack:** React, TypeScript, FastAPI, Pydantic, Python.

---

### Task 1: Backend Pydantic Schema Extension

**Files:**
- Modify: `backend/app/schemas/fmea.py`

- [ ] **Step 1: Modify `GraphNodeSchema` in `backend/app/schemas/fmea.py`**

Add the DFMEA-specific optional attributes to `GraphNodeSchema` with default values so that they are backward compatible with PFMEA documents:

```python
class GraphNodeSchema(BaseModel):
    id: str
    type: str
    name: str
    process_number: str | None = None
    severity: int = 0
    occurrence: int = 0
    detection: int = 0
    # DFMEA specific fields
    requirement: str | None = None
    specification: str | None = None
    responsible: str | None = None
    due_date: str | None = None
    status: str | None = None
    action_taken: str | None = None
    completion_date: str | None = None
    revised_severity: int | None = None
    revised_occurrence: int | None = None
    revised_detection: int | None = None
    revised_ap: str | None = None
```

- [ ] **Step 2: Commit Backend Changes**

```bash
git add backend/app/schemas/fmea.py
git commit -m "schema: extend GraphNodeSchema with DFMEA specific optional fields"
```

---

### Task 2: Frontend TypeScript Types Extension

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Modify `GraphNode` in `frontend/src/types/index.ts`**

Add the corresponding TypeScript optional properties to `GraphNode` to align with the backend schema:

```typescript
export interface GraphNode {
  id: string;
  type: string;
  name: string;
  process_number?: string;
  severity: number;
  occurrence: number;
  detection: number;
  // DFMEA specific fields
  requirement?: string;
  specification?: string;
  responsible?: string;
  due_date?: string;
  status?: string;
  action_taken?: string;
  completion_date?: string;
  revised_severity?: number;
  revised_occurrence?: number;
  revised_detection?: number;
  revised_ap?: string;
}
```

- [ ] **Step 2: Commit Frontend Type Changes**

```bash
git add frontend/src/types/index.ts
git commit -m "types: extend GraphNode interface with DFMEA optional fields"
```

---

### Task 3: AP (Action Priority) Calculation Utility

**Files:**
- Create: `frontend/src/utils/fmea.ts`

- [ ] **Step 1: Write `calculateAP` utility function**

Create `frontend/src/utils/fmea.ts` to implement the VDA-AIAG FMEA 5th Edition Action Priority (AP) logic using S, O, D scores:

```typescript
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
```

- [ ] **Step 2: Commit AP Utility Changes**

```bash
git add frontend/src/utils/fmea.ts
git commit -m "feat: implement VDA-AIAG AP calculation helper function"
```
