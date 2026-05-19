# QMS State Model Prototype

**THROWAWAY** - Do not ship. This prototype exists to answer a design question.

## Question

Does the FMEA/8D state machine and knowledge graph model feel right when driven by hand?

Specifically:
1. Do the FMEA state transitions (DRAFT→REVIEW→APPROVED/REWORK) cover real workflows?
2. Is the 8D linear progression (D1→D2→…→D8) too rigid, or does it match practice?
3. Does the knowledge graph node/edge model support the traversal patterns we need?
4. Does product-line isolation feel natural for scoping data?

## Run

```bash
python3 prototypes/qms_state_prototype/tui.py
```

## What to explore

- Create FMEA documents in different product lines and transition states
- Drive an 8D report through its stages
- Build graph nodes and edges, then traverse neighbors
- Try transitioning a FMEA from DRAFT→APPROVED (should fail—must go through REVIEW)
- Try advancing an 8D backward (should fail—linear only)

## When done

The answer—whatever this teaches about the state models—belongs in a commit message or ADR. The TUI shell (`tui.py`) is throwaway; `models.py` is the bit worth keeping.
