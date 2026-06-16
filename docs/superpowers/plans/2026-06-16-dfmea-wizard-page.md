# DFMEA Wizard Page Implementation Plan (v4-fixed — revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the DFMEA generation wizard from a Modal into a full-page wizard with draft saving, step navigation, guidance cards, and cascade deletion.

**Architecture:** New page component `DFMEAWizardPage` at `/fmea/wizard/:id` with left sidebar (structure tree + step nav) and right content area (guidance card + step form). Uses existing `PUT /fmea/{id}` API with `lock_version` and serial request queue. 5T scope data stored in `graph_data.wizardScope` root property (small backend schema change).

**Tech Stack:** React 18, TypeScript, Ant Design 5, React Router v6, Zustand (existing), i18next (existing), existing `dfmeaRules.ts` utils, existing `buildRows` from `fmeaTable.ts`, existing `StructureTree` component

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/schemas/fmea.py` | Modify | Add `WizardScopeSchema`, `wizardScope` to `GraphDataSchema`, `lock_version` to `FMEAResponse` |
| `backend/app/api/fmea.py` | Modify | Add `DELETE /{fmea_id}` endpoint |
| `backend/app/services/fmea_service.py` | Modify | Add `delete_fmea` service function |
| `backend/app/services/graph_projection_service.py` | Modify | Add `delete_fmea_projection` method to clean up Neo4j |
| `backend/app/services/graph_sync_worker.py` | Modify | Branch on `fmea.deleted` event type |
| `frontend/src/types/index.ts` | Modify | Add `WizardScope` interface, `wizardScope` to `GraphData`, `lock_version` to `FMEADocument` |
| `frontend/src/api/fmea.ts` | Modify | Add `deleteFMEA` function |
| `frontend/src/App.tsx` | Modify | Add `/fmea/wizard/:id` route + import |
| `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` | Create | Main wizard page component (step orchestration, save, validation) |
| `frontend/src/components/dfmea/WizardGuidanceCard.tsx` | Create | Collapsible guidance card with i18n |
| `frontend/src/components/dfmea/WizardSidebar.tsx` | Create | Left sidebar: structure tree (using `buildTreeData` from `StructureTree.tsx`) + step navigation |
| `frontend/src/hooks/useWizardSave.ts` | Create | Serial PUT queue, debounce, lock_version, save state |
| `frontend/src/hooks/useWizardValidation.ts` | Create | Step completeness validation using `buildRows` |
| `frontend/src/utils/wizardCascadeDelete.ts` | Create | Cascade deletion for structure node removal (with unit tests) |
| `frontend/src/utils/wizardCascadeDelete.test.ts` | Create | Unit tests for cascade deletion |
| `frontend/src/pages/planning/fmea/FMEAListPage.tsx` | Modify | DFMEA creation navigates to wizard; draft rows link to wizard |
| `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` | Modify | Redirect draft DFMEAs to wizard |
| `frontend/src/locales/zh-CN/dfmea.json` | Modify | Add guidance card + wizard page translations |
| `frontend/src/locales/en-US/dfmea.json` | Modify | Add English translations |

---

## Task 1: Backend — Schema Changes + Delete Endpoint

**Files:**
- Modify: `backend/app/schemas/fmea.py`
- Modify: `backend/app/api/fmea.py`
- Modify: `backend/app/services/fmea_service.py`
- Modify: `backend/app/services/graph_projection_service.py`
- Modify: `backend/app/services/graph_sync_worker.py`

### 1a: Add WizardScopeSchema, lock_version to FMEAResponse, and wizardScope to GraphDataSchema

In `backend/app/schemas/fmea.py`, add before `GraphDataSchema`:

```python
class WizardScopeSchema(BaseModel):
    team: str | None = None
    timeframe: str | None = None
    tool: str | None = None
    task: str | None = None
    trend: str | None = None
    wizard_completed: bool | None = None  # Set True when wizard finishes; prevents editor redirect loop


class GraphDataSchema(BaseModel):
    nodes: list[GraphNodeSchema] = []
    edges: list[GraphEdgeSchema] = []
    wizardScope: WizardScopeSchema | None = None
```

Add `lock_version` to `FMEAResponse`:

```python
class FMEAResponse(BaseModel):
    fmea_id: uuid.UUID
    document_no: str
    title: str
    fmea_type: str
    product_line_code: str
    status: str
    version: int
    lock_version: int = 0
    graph_data: dict
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None

    model_config = {"from_attributes": True}
```

### 1b: Add delete_fmea service function

In `backend/app/services/fmea_service.py`, add after the `update_fmea` function:

```python
async def delete_fmea(db: AsyncSession, fmea_id: uuid.UUID, user_id: uuid.UUID) -> None:
    fmea = await get_fmea(db, fmea_id)
    if fmea is None:
        raise ValueError("FMEA not found")
    # Audit log for deletion
    audit_log = AuditLog(
        table_name="fmea_documents",
        record_id=fmea_id,
        action="DELETE",
        changed_fields={"title": fmea.title, "document_no": fmea.document_no, "fmea_type": fmea.fmea_type},
        operated_by=user_id,
    )
    db.add(audit_log)
    # GraphSync outbox event for Neo4j projection cleanup
    db.add(GraphSyncOutbox(
        aggregate_type="fmea",
        aggregate_id=fmea_id,
        event_type="fmea.deleted",
        payload={"product_line_code": fmea.product_line_code, "fmea_type": fmea.fmea_type},
    ))
    await db.delete(fmea)
    await db.commit()
```

Additionally, add a `delete_fmea_projection` method to `GraphProjectionService` in `backend/app/services/graph_projection_service.py`. Add it as a new method on the existing class, following the same `self._driver` + `session.execute_write(_tx)` pattern used by `sync_fmea_to_neo4j`:

```python
async def delete_fmea_projection(self, fmea_id: uuid.UUID) -> None:
    """从 Neo4j 删除该 FMEA 的所有投影节点（FMEA 行已从 PG 删除）。"""

    async def _tx(tx):
        result = await tx.run(
            "MATCH (n) WHERE n.fmea_id = $fmea_id DETACH DELETE n",
            {"fmea_id": str(fmea_id)},
        )
        await result.consume()

    async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
        await session.execute_write(_tx)
```

And update the graph sync worker in `backend/app/services/graph_sync_worker.py` to handle the `fmea.deleted` event. In `run_worker()`, replace the `try` block body inside the task loop (lines 217-224) with:

```python
if task.event_type == "fmea.deleted":
    await projection.delete_fmea_projection(task.aggregate_id)
    logger.info(f"Deleted FMEA {task.aggregate_id} projection from Neo4j")
else:
    await projection.sync_fmea_to_neo4j(task.aggregate_id)
    logger.info(f"Synced FMEA {task.aggregate_id} to Neo4j")
async with get_tenant_aware_session() as db:
    await _mark_completed(db, task.id)
```

Note: `settings` must be imported at the top of `graph_projection_service.py` (it already is). `projection` and `task` are the existing local variable names in the worker loop.

### 1c: Add DELETE endpoint

In `backend/app/api/fmea.py`, add after the `update_fmea` route:

```python
@router.delete("/{fmea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 EDIT 权限")
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if scope.effective_factory_id and fmea.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if fmea.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="FMEA not found")
    # Only allow deleting draft FMEAs
    if fmea.status != "draft":
        raise HTTPException(status_code=400, detail="只能删除草稿状态的FMEA")
    await fmea_service.delete_fmea(db, fmea_id, scope.user.user_id)
```

- [ ] **Step 1: Apply schema + service + API changes**

- [ ] **Step 2: Run backend tests**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/ -x --tb=short -q 2>&1 | tail -20`

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/fmea.py backend/app/services/fmea_service.py backend/app/api/fmea.py backend/app/services/graph_projection_service.py backend/app/services/graph_sync_worker.py
git commit -m "feat(dfmea-wizard): add WizardScopeSchema, lock_version, DELETE endpoint, Neo4j projection cleanup"
```

---

## Task 2: Frontend Types & API

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/fmea.ts`

### 2a: Add WizardScope, update GraphData, add lock_version to FMEADocument

In `frontend/src/types/index.ts`, add before `GraphData`:

```typescript
export interface WizardScope {
  team?: string;
  timeframe?: string;
  tool?: string;
  task?: string;
  trend?: string;
  wizard_completed?: boolean;  // True when wizard has finished; prevents editor redirect loop
}
```

Update `GraphData`:

```typescript
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  wizardScope?: WizardScope;
}
```

Add `lock_version` to the existing `FMEADocument` interface. Insert `lock_version: number;` after the `version` field (around line 99):

```typescript
// In the existing FMEADocument interface, add after `version: number;`:
  lock_version: number;
```

### 2b: Add deleteFMEA to API

In `frontend/src/api/fmea.ts`, add:

```typescript
export async function deleteFMEA(id: string): Promise<void> {
  await client.delete(`/fmea/${id}`);
}
```

- [ ] **Step 1: Apply type and API changes**

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit 2>&1 | head -30`

Expected: No new errors. The `lock_version` field may need to be handled in existing code that uses `FMEADocument` — if TS reports errors, add `lock_version: 0` as default in API response parsing.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/fmea.ts
git commit -m "feat(dfmea-wizard): add WizardScope type, lock_version, deleteFMEA API"
```

---

## Task 3: Cascade Delete Utility (with Unit Tests)

**Files:**
- Create: `frontend/src/utils/wizardCascadeDelete.ts`
- Create: `frontend/src/utils/wizardCascadeDelete.test.ts`

The cascade delete must handle shared control nodes correctly and follow the actual FMEA graph edge directions. Key edge directions from GenerationWizard.tsx:
- `HAS_PROCESS_STEP` / `HAS_WORK_ELEMENT` / `HAS_PARAMETER` — structural, parent→child
- `HAS_FUNCTION` — Component→Function
- `HAS_FAILURE_MODE` — Function→FailureMode
- `EFFECT_OF` — FailureMode→FailureEffect
- `CAUSE_OF` — FailureCause→FailureMode (**reversed**: source=cause, target=fm)
- `PREVENTED_BY` — FailureCause→PreventionControl
- `DETECTED_BY` — FailureCause→DetectionControl

The algorithm follows outgoing edges AND also follows CAUSE_OF edges in reverse (finding causes that point TO a FailureMode in the subtree).

```typescript
import type { GraphNode, GraphEdge } from '../types';

// Edge types that represent forward/downstream relationships
const FORWARD_EDGE_TYPES = new Set([
  'HAS_PROCESS_STEP', 'HAS_WORK_ELEMENT', 'HAS_PARAMETER',
  'HAS_FUNCTION', 'HAS_FAILURE_MODE', 'EFFECT_OF',
  'PREVENTED_BY', 'DETECTED_BY',
]);
// CAUSE_OF is special: source=FailureCause, target=FailureMode
// To find causes for a FailureMode, we look for edges where target=fmId

/**
 * Remove a structure node and cascade-delete truly orphaned downstream nodes.
 * Follows forward edges (parent→child) and also discovers FailureCauses
 * via CAUSE_OF edges (where source=cause, target=FailureMode).
 * Shared nodes (referenced by parents outside the deletion path) are kept;
 * only their edge from the deletion path is removed.
 */
export function cascadeDeleteStructureNode(
  nodeId: string,
  nodes: GraphNode[],
  edges: GraphEdge[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodeIdsToDelete = new Set<string>();
  const edgeKeysToDelete = new Set<string>();

  // The root node being deleted is always removed, regardless of parents
  nodeIdsToDelete.add(nodeId);

  // Remove all edges connected to the root node
  for (const e of edges) {
    if (e.source === nodeId || e.target === nodeId) {
      edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
    }
  }

  // BFS downstream from nodeId, following forward edges
  // and also discovering FailureCauses via CAUSE_OF (reversed)
  const downstream = new Set<string>();
  const queue = [nodeId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (downstream.has(current)) continue;
    // Skip the root — it's already handled above
    if (current === nodeId) {
      // Still traverse its children
      for (const e of edges) {
        if (e.source === current && FORWARD_EDGE_TYPES.has(e.type)) {
          queue.push(e.target);
        }
      }
      continue;
    }
    downstream.add(current);

    // Follow forward outgoing edges from this node
    for (const e of edges) {
      if (e.source === current && FORWARD_EDGE_TYPES.has(e.type)) {
        queue.push(e.target);
      }
    }

    // If this node is a FailureMode, find all FailureCauses pointing to it
    const node = nodes.find(n => n.id === current);
    if (node && node.type === 'FailureMode') {
      for (const e of edges) {
        if (e.target === current && e.type === 'CAUSE_OF') {
          queue.push(e.source);
        }
      }
    }
  }

  // For each downstream node (not the root), check if it has incoming edges
  // from OUTSIDE the deletion set. If yes, it's shared — keep it, only remove
  // edges from inside the set.
  for (const id of downstream) {
    const hasExternalParent = edges.some(
      e => e.target === id && !downstream.has(e.source) && e.source !== nodeId &&
         (FORWARD_EDGE_TYPES.has(e.type) || e.type === 'CAUSE_OF')
    );

    if (!hasExternalParent) {
      // No external parent — this node is orphaned, delete it
      nodeIdsToDelete.add(id);
    }

    // Remove edges where both endpoints are in the deletion set
    for (const e of edges) {
      if (e.source === id && downstream.has(e.target) && FORWARD_EDGE_TYPES.has(e.type)) {
        edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
      }
      if (e.type === 'CAUSE_OF' && e.source === id && downstream.has(e.target)) {
        edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
      }
    }
  }

  // Also remove all edges connected to deleted nodes
  for (const e of edges) {
    if (nodeIdsToDelete.has(e.source) || nodeIdsToDelete.has(e.target)) {
      edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
    }
  }

  const filteredNodes = nodes.filter(n => !nodeIdsToDelete.has(n.id));
  const filteredEdges = edges.filter(e => !edgeKeysToDelete.has(`${e.source}->${e.target}->${e.type}`));

  return { nodes: filteredNodes, edges: filteredEdges };
}
```

### Unit tests

Create `frontend/src/utils/wizardCascadeDelete.test.ts`:

```typescript
import { cascadeDeleteStructureNode } from './wizardCascadeDelete';
import type { GraphNode, GraphEdge } from '../types';

// Helper: make a node with defaults
const n = (id: string, type: string, name?: string): GraphNode => ({
  id, type, name: name || id, severity: 0, occurrence: 0, detection: 0,
});

// Helper: make an edge
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

describe('cascadeDeleteStructureNode', () => {
  it('deletes a single node with no children', () => {
    const nodes = [n('s1', 'System'), n('ss1', 'Subsystem')];
    const edges = [e('s1', 'ss1', 'HAS_PROCESS_STEP')];
    const result = cascadeDeleteStructureNode('ss1', nodes, edges);
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe('s1');
    expect(result.edges).toHaveLength(0);
  });

  it('cascades deletion through forward edges AND discovers causes via CAUSE_OF', () => {
    // Graph: s1 → ss1 → c1 → func1 → fm1 → fe1
    //                               fc1 →(CAUSE_OF)→ fm1
    //                               fc1 → pc1 (PREVENTED_BY)
    // Deleting ss1 should cascade to all downstream including fc1 (found via CAUSE_OF)
    const nodes = [
      n('s1', 'System'), n('ss1', 'Subsystem'), n('c1', 'Component'),
      n('func1', 'ProcessWorkElementFunction'), n('fm1', 'FailureMode'),
      n('fe1', 'FailureEffect'), n('fc1', 'FailureCause'), n('pc1', 'PreventionControl'),
    ];
    const edges = [
      e('s1', 'ss1', 'HAS_PROCESS_STEP'),
      e('ss1', 'c1', 'HAS_WORK_ELEMENT'),
      e('c1', 'func1', 'HAS_FUNCTION'),
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fc1', 'fm1', 'CAUSE_OF'),       // cause → FailureMode
      e('fc1', 'pc1', 'PREVENTED_BY'),
    ];
    const result = cascadeDeleteStructureNode('ss1', nodes, edges);
    // Only s1 should remain
    expect(result.nodes.map(n => n.id)).toEqual(['s1']);
    expect(result.edges).toHaveLength(0);
  });

  it('keeps shared PreventionControl referenced by cause outside deletion path', () => {
    // Two components, shared pc1:
    // c1 → func1 → fm1 ←(CAUSE_OF)— fc1 → pc1
    // c2 → func2 → fm2 ←(CAUSE_OF)— fc2 → pc1
    // Deleting c1 should cascade to func1, fm1, fc1 but NOT delete pc1 (shared with c2)
    const pc1 = n('pc1', 'PreventionControl', 'Shared PC');
    const nodes = [
      n('s1', 'System'), n('c1', 'Component'), n('c2', 'Component'),
      n('func1', 'ProcessWorkElementFunction'), n('func2', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'), n('fm2', 'FailureMode'),
      n('fc1', 'FailureCause'), n('fc2', 'FailureCause'),
      pc1,
    ];
    const edges = [
      e('s1', 'c1', 'HAS_PROCESS_STEP'), e('s1', 'c2', 'HAS_PROCESS_STEP'),
      e('c1', 'func1', 'HAS_FUNCTION'), e('c2', 'func2', 'HAS_FUNCTION'),
      e('func1', 'fm1', 'HAS_FAILURE_MODE'), e('func2', 'fm2', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'), e('fc2', 'fm2', 'CAUSE_OF'),
      e('fc1', 'pc1', 'PREVENTED_BY'), e('fc2', 'pc1', 'PREVENTED_BY'),
    ];
    const result = cascadeDeleteStructureNode('c1', nodes, edges);
    const remainingIds = result.nodes.map(n => n.id);
    // pc1 should be kept because fc2 (outside deletion path) also references it
    expect(remainingIds).toContain('pc1');
    expect(remainingIds).toContain('c2');
    expect(remainingIds).toContain('fc2');
    expect(remainingIds).not.toContain('c1');
    expect(remainingIds).not.toContain('func1');
    expect(remainingIds).not.toContain('fm1');
    expect(remainingIds).not.toContain('fc1');
    // The edge from fc1→pc1 should be removed, but fc2→pc1 should remain
    expect(result.edges.some(e => e.source === 'fc2' && e.target === 'pc1')).toBe(true);
    expect(result.edges.some(e => e.source === 'fc1' && e.target === 'pc1')).toBe(false);
  });
});
```

- [ ] **Step 1: Create cascade delete utility and tests**

- [ ] **Step 2: Run tests**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx vitest run src/utils/wizardCascadeDelete.test.ts 2>&1 | tail -20`

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/wizardCascadeDelete.ts frontend/src/utils/wizardCascadeDelete.test.ts
git commit -m "feat(dfmea-wizard): add cascade delete utility with unit tests"
```

---

## Task 4: useWizardSave Hook (Fixed Serial Queue)

**Files:**
- Create: `frontend/src/hooks/useWizardSave.ts`

The key fix: use a serial promise chain that never sets `pendingRef` to null until the entire chain completes. No `await` gap between promise resolution and the next queue check.

```typescript
import { useRef, useState, useCallback } from 'react';
import { message } from 'antd';
import { updateFMEA } from '../api/fmea';
import type { GraphData } from '../types';

interface UseWizardSaveOptions {
  fmeaId: string;
}

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export function useWizardSave({ fmeaId }: UseWizardSaveOptions) {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const lockVersionRef = useRef<number>(0);
  const queueTailRef = useRef<Promise<boolean>>(Promise.resolve(false));
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Hash of the last payload that was successfully saved — never reads live page state. */
  const lastSavedHashRef = useRef<string>('');

  const setLockVersion = useCallback((v: number) => {
    lockVersionRef.current = v;
  }, []);

  /** Serial save: enqueues after any in-flight save, returns true on success.
   *  `dataHash` is the hash of the payload snapshot AT enqueue time. On success,
   *  the hook writes `dataHash` into `lastSavedHashRef` — NOT the current page state. */
  const enqueueSave = useCallback(async (
    graphData: GraphData,
    title?: string,
    dataHash?: string,
  ): Promise<boolean> => {
    const doSave = async (): Promise<boolean> => {
      try {
        setSaveStatus('saving');
        const resp = await updateFMEA(fmeaId, {
          ...(title ? { title } : {}),
          graph_data: graphData,
          lock_version: lockVersionRef.current,
        });
        lockVersionRef.current = resp.lock_version ?? resp.version;
        if (dataHash) lastSavedHashRef.current = dataHash;
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus('idle'), 2000);
        return true;
      } catch (err: any) {
        setSaveStatus('error');
        if (err?.response?.status === 409 || String(err?.response?.data?.detail).includes('lock_version')) {
          message.error('数据已被其他会话修改，请刷新页面后重试');
        } else {
          message.error('保存失败，请重试');
        }
        return false;
      }
    };

    // Chain this save onto the tail of the queue
    const prevTail = queueTailRef.current;
    const newTail = prevTail.then(() => doSave());
    queueTailRef.current = newTail;
    return newTail;
  }, [fmeaId]);

  /** Debounced save: 500ms delay, cancels previous timer. Returns void (fire-and-forget). */
  const debouncedSave = useCallback((graphData: GraphData, title?: string, dataHash?: string) => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      enqueueSave(graphData, title, dataHash);
    }, 500);
  }, [enqueueSave]);

  /** Immediate save: cancels debounce, saves right away. Returns true on success. */
  const immediateSave = useCallback(async (
    graphData: GraphData,
    title?: string,
    dataHash?: string,
  ): Promise<boolean> => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    return await enqueueSave(graphData, title, dataHash);
  }, [enqueueSave]);

  return {
    saveStatus,
    setLockVersion,
    debouncedSave,
    immediateSave,
    lastSavedHashRef,
  };
}
```

- [ ] **Step 1: Create the hook file**

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useWizardSave.ts
git commit -m "feat(dfmea-wizard): add useWizardSave hook with serial queue and 409 handling"
```

---

## Task 5: useWizardValidation Hook (Using buildRows)

**Files:**
- Create: `frontend/src/hooks/useWizardValidation.ts`

This uses the existing `buildRows` from `fmeaTable.ts` which correctly follows the graph model: S on FailureEffect, O on FailureCause, D on DetectionControl.

```typescript
import { useMemo } from 'react';
import type { GraphNode, GraphEdge } from '../types';
import { buildRows } from '../utils/fmeaTable';

export interface StepValidation {
  step3Complete: boolean;
  step4Complete: boolean;
  step5Complete: boolean;
  warnings: number[];
}

export function useWizardValidation(nodes: GraphNode[], edges: GraphEdge[]): StepValidation {
  return useMemo(() => {
    const components = nodes.filter(n => n.type === 'Component');
    const functions = nodes.filter(n =>
      n.type === 'ProcessWorkElementFunction' ||
      n.type === 'ProcessItemFunction' ||
      n.type === 'ProcessStepFunction'
    );

    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const rows = buildRows(nodes, edges);

    // Step 3: Every Component should have at least one Function via HAS_FUNCTION edge
    const step3Complete = components.length > 0 && components.every(c => {
      return edges.some(e => e.source === c.id && e.type === 'HAS_FUNCTION');
    });

    // Step 4: Every Function should have at least one FailureMode
    const step4Complete = functions.length > 0 && functions.every(f => {
      return edges.some(e => e.source === f.id && e.type === 'HAS_FAILURE_MODE');
    });

    // Step 5: Every row in the FMEA table should have S/O/D > 0
    // S is on FailureEffect, O on FailureCause, D on DetectionControl
    const step5Complete = rows.length > 0 && rows.every(r => {
      const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const detectionNode = r.detectionControlIds.length > 0
        ? nodeMap.get(r.detectionControlIds[0])
        : null;

      return (effect?.severity ?? 0) > 0
          && (cause?.occurrence ?? 0) > 0
          && (detectionNode?.detection ?? 0) > 0;
    });

    const warnings: number[] = [];
    if (components.length > 0 && !step3Complete) warnings.push(2);
    if (functions.length > 0 && !step4Complete) warnings.push(3);
    if (rows.length > 0 && !step5Complete) warnings.push(4);

    return { step3Complete, step4Complete, step5Complete, warnings };
  }, [nodes, edges]);
}
```

- [ ] **Step 1: Create the hook file**

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useWizardValidation.ts
git commit -m "feat(dfmea-wizard): add useWizardValidation using buildRows for correct S/O/D"
```

---

## Task 6: WizardGuidanceCard Component

**Files:**
- Create: `frontend/src/components/dfmea/WizardGuidanceCard.tsx`

```tsx
import { useState, useEffect } from 'react';
import { Card } from 'antd';
import { BookOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface GuidanceCardProps {
  stepIndex: number;
}

const STORAGE_KEY = 'dfmea_wizard_card_collapsed';

export default function WizardGuidanceCard({ stepIndex }: GuidanceCardProps) {
  const { t } = useTranslation('dfmea');
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : false;
    } catch { return false; }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(collapsed));
  }, [collapsed]);

  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={
        <span>
          <BookOutlined style={{ marginRight: 8 }} />
          {t(`wizard.guidance.step${stepIndex}.title`)}
        </span>
      }
      aria-expanded={!collapsed}
    >
      {!collapsed && (
        <div>
          <p style={{ marginBottom: 8 }}>
            <strong>{t('wizard.guidance.purpose')}：</strong>
            {t(`wizard.guidance.step${stepIndex}.purpose`)}
          </p>
          <p style={{ marginBottom: 8 }}>
            <strong>{t('wizard.guidance.keyPoints')}：</strong>
            {t(`wizard.guidance.step${stepIndex}.keyPoints`)}
          </p>
          <p style={{ marginBottom: 0, color: '#666' }}>
            <strong>{t('wizard.guidance.example')}：</strong>
            {t(`wizard.guidance.step${stepIndex}.example`)}
          </p>
        </div>
      )}
      <a onClick={() => setCollapsed(c => !c)} style={{ fontSize: 12, marginTop: collapsed ? 0 : 8, display: 'inline-block' }}>
        {collapsed ? t('wizard.guidance.expand') : t('wizard.guidance.collapse')}
      </a>
    </Card>
  );
}
```

- [ ] **Step 1: Create the component**

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/dfmea/WizardGuidanceCard.tsx
git commit -m "feat(dfmea-wizard): add WizardGuidanceCard with collapse persistence"
```

---

## Task 7: WizardSidebar Component (with edges + proper tree)

**Files:**
- Create: `frontend/src/components/dfmea/WizardSidebar.tsx`

This component receives `edges` and uses the same tree-building logic as the production `StructureTree.tsx`.

```tsx
import { Steps, Tree, Empty, Typography } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { GraphNode, GraphEdge } from '../../types';

const STRUCTURE_TYPES = ['System', 'Subsystem', 'Component', 'Interface', 'DesignParameter'];
const VALID_EDGE_TYPES = new Set(['HAS_PROCESS_STEP', 'HAS_WORK_ELEMENT', 'HAS_PARAMETER']);

const TYPE_COLORS: Record<string, string> = {
  System: '#f5222d',
  Subsystem: '#fa8c16',
  Component: '#52c41a',
  Interface: '#722ed1',
  DesignParameter: '#1890ff',
};

interface WizardSidebarProps {
  currentStep: number;
  onStepClick: (step: number) => void;
  completedSteps: Set<number>;
  warnings: number[];
  structureNodes: GraphNode[];
  edges: GraphEdge[];
  onNodeSelect?: (nodeId: string) => void;
}

export default function WizardSidebar({
  currentStep,
  onStepClick,
  completedSteps,
  warnings,
  structureNodes,
  edges,
  onNodeSelect,
}: WizardSidebarProps) {
  const { t } = useTranslation('dfmea');

  const stepTitles = [
    t('wizard.steps.0'),
    t('wizard.steps.1'),
    t('wizard.steps.2'),
    t('wizard.steps.3'),
    t('wizard.steps.4'),
    t('wizard.steps.5'),
    t('wizard.steps.6'),
  ];

  const showStructure = currentStep >= 1;

  const treeData = buildTreeData(structureNodes, edges, t);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--qf-border)' }}>
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 12px' }}>
        {currentStep === 0 ? (
          <Empty description={t('wizard.sidebar.structureHint')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : treeData && treeData.length > 0 ? (
          <>
            <Typography.Text strong style={{ fontSize: 13, marginBottom: 8, display: 'block' }}>
              {t('wizard.sidebar.structureTree')}
            </Typography.Text>
            <Tree
              treeData={treeData}
              defaultExpandAll
              onSelect={(keys) => {
                if (keys.length > 0 && onNodeSelect) onNodeSelect(String(keys[0]));
              }}
              style={{ fontSize: 13 }}
            />
          </>
        ) : (
          <Empty description={t('wizard.sidebar.noStructure')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </div>

      <div style={{ borderTop: '1px solid var(--qf-border)', padding: '8px 12px' }}>
        <Steps
          direction="vertical"
          size="small"
          current={currentStep}
          items={stepTitles.map((title, i) => ({
            title,
            status: warnings.includes(i)
              ? 'error'
              : completedSteps.has(i)
                ? 'finish'
                : i === currentStep
                  ? 'process'
                  : 'wait',
            icon: warnings.includes(i) ? <WarningOutlined style={{ color: '#faad14' }} /> : undefined,
          }))}
          onChange={(step) => {
            if (step < currentStep || completedSteps.has(step)) {
              onStepClick(step);
            }
          }}
        />
      </div>
    </div>
  );
}

function buildTreeData(nodes: GraphNode[], edges: GraphEdge[], t: (key: string) => string) {
  const structureNodes = nodes.filter(n => STRUCTURE_TYPES.includes(n.type));
  const nodeMap = new Map(structureNodes.map(n => [n.id, n]));
  const edgeMap = new Map<string, string[]>();

  for (const edge of edges) {
    if (!VALID_EDGE_TYPES.has(edge.type)) continue;
    if (!edgeMap.has(edge.source)) edgeMap.set(edge.source, []);
    edgeMap.get(edge.source)!.push(edge.target);
  }

  const buildNode = (nodeId: string): any => {
    const node = nodeMap.get(nodeId);
    if (!node) return null;
    const children = edgeMap.get(nodeId)?.map(childId => buildNode(childId)).filter(Boolean) || [];
    return {
      key: node.id,
      title: (
        <span style={{ color: TYPE_COLORS[node.type] || '#333' }}>{node.name}</span>
      ),
      children,
    };
  };

  const childrenIds = new Set(
    edges.filter(e => VALID_EDGE_TYPES.has(e.type)).map(e => e.target)
  );
  const roots = structureNodes.filter(n => !childrenIds.has(n.id));
  return roots.map(r => buildNode(r.id)).filter(Boolean);
}
```

- [ ] **Step 1: Create the component**

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/dfmea/WizardSidebar.tsx
git commit -m "feat(dfmea-wizard): add WizardSidebar with edges-based tree and step nav"
```

---

## Task 8: i18n — Guidance Card & Wizard Page Strings

**Files:**
- Modify: `frontend/src/locales/zh-CN/dfmea.json`
- Modify: `frontend/src/locales/en-US/dfmea.json`

Add the following keys inside the existing `"wizard"` object. Do NOT use `...(existing keys)...` — merge properly with the existing content.

### zh-CN additions (inside existing `"wizard"` key):

```json
"guidance": {
  "expand": "展开",
  "collapse": "收起",
  "purpose": "目的",
  "keyPoints": "填写要点",
  "example": "示例",
  "step0": {
    "title": "第一步：5T范围定义",
    "purpose": "明确 DFMEA 分析的边界、团队和关注点，确保后续分析聚焦。",
    "keyPoints": "团队应包含设计、工艺、质量等跨职能成员；任务描述要具体到产品/系统层级。",
    "example": "团队：BMS设计组、工艺工程组；时间范围：2026年Q1-Q3；工具：FMEA工作表；任务：DC-DC转换器DFMEA分析；趋势：过往3款同类产品客户投诉统计"
  },
  "step1": {
    "title": "第二步：结构分析",
    "purpose": "将产品分解为系统→子系统→零部件的层级结构，为功能分析提供基础。",
    "keyPoints": "层级不宜超过4层；每个零部件应是可独立分析的物理单元；可添加接口节点表示跨分支的交互。",
    "example": "系统: BMS → 子系统: BMU / 充电管理 → 零部件: LTC6811 / MOSFET"
  },
  "step2": {
    "title": "第三步：功能分析",
    "purpose": "为每个零部件定义其功能、技术要求和规格参数。",
    "keyPoints": "功能描述用\"动词+名词\"格式（如\"采集单体电压\"）；技术要求描述期望性能指标；规格参数带公差。",
    "example": "零部件 LTC6811 → 功能: 采集单体电压 → 要求: 准确采集每个电芯电压 → 规格: 精度±2mV"
  },
  "step3": {
    "title": "第四步：失效分析",
    "purpose": "针对每个功能识别失效模式、失效影响和失效原因，形成完整的失效链。",
    "keyPoints": "失效模式 = 功能的反面；影响描述对系统的后果；原因要具体到可措施层面。",
    "example": "功能\"采集单体电压\" → 失效模式: 采集精度不足 → 影响: 控制决策偏差 → 原因: 传感器老化"
  },
  "step4": {
    "title": "第五步：风险分析",
    "purpose": "为每条失效链评估严重度(S)、发生度(O)、探测度(D)，计算措施优先级(AP)。",
    "keyPoints": "S评估失效影响严重程度(1-10)；O评估发生可能性(1-10)；D评估探测能力(1-10)；AP由系统自动计算。",
    "example": "S=8(严重) + O=4(偶发) + D=3(较难探测) → AP=H(必须优化)"
  },
  "step5": {
    "title": "第六步：优化措施",
    "purpose": "对 AP=H 的失效链制定预防和探测措施，降低风险。",
    "keyPoints": "预防措施降低发生度(O)；探测措施降低探测度(D)；严重度(S)通常只能通过设计变更降低。",
    "example": "预防: 传感器冗余布置 → 预期 O 从4降到2；探测: 在线实时监测 → 预期 D 从3降到2"
  },
  "step6": {
    "title": "第七步：确认创建",
    "purpose": "检查所有步骤的数据完整性，确认后进入正式编辑器继续完善。",
    "keyPoints": "检查结构是否完整、功能是否覆盖所有零部件、失效链是否有遗漏、S/O/D 是否填写。",
    "example": "确认后将创建 DFMEA 文档并进入编辑器，可在编辑器中继续添加细节。"
  }
},
"sidebar": {
  "structureTree": "结构树",
  "structureHint": "结构树将在第二步后出现",
  "noStructure": "暂无结构节点"
},
"page": {
  "title": "DFMEA 生成向导",
  "saveDraft": "保存草稿",
  "saveSaving": "保存中...",
  "saveSaved": "已保存 ✓",
  "saveError": "未保存 ●",
  "backToList": "返回列表",
  "nextStep": "下一步",
  "prevStep": "上一步",
  "finish": "完成并进入编辑器",
  "confirmEmptyDraft": "当前草稿为空，确定要放弃吗？确定后草稿将被删除。",
  "confirmEmptyDraftTitle": "放弃草稿？",
  "confirmEmptyDraftOk": "放弃并删除",
  "confirmEmptyDraftCancel": "继续编辑",
  "completionWarning": "以下步骤需要补全后才能完成：",
  "step3Incomplete": "功能分析 — 存在零部件未定义功能",
  "step4Incomplete": "失效分析 — 存在功能未定义失效模式",
  "step5Incomplete": "风险分析 — 存在失效模式未填写 S/O/D",
  "loading": "加载中..."
}
```

### en-US additions (inside existing `"wizard"` key):

```json
"guidance": {
  "expand": "Expand",
  "collapse": "Collapse",
  "purpose": "Purpose",
  "keyPoints": "Key Points",
  "example": "Example",
  "step0": {
    "title": "Step 1: 5T Scope Definition",
    "purpose": "Define the boundaries, team, and focus of the DFMEA analysis.",
    "keyPoints": "Team should include cross-functional members from design, process, and quality; task description should be specific to the product/system level.",
    "example": "Team: BMS Design Group, Process Engineering; Timeframe: 2026 Q1-Q3; Tool: FMEA Worksheet; Task: DC-DC Converter DFMEA; Trend: Customer complaints from 3 similar products"
  },
  "step1": {
    "title": "Step 2: Structure Analysis",
    "purpose": "Decompose the product into system → subsystem → component hierarchy for functional analysis.",
    "keyPoints": "Hierarchy should not exceed 4 levels; each component should be an independently analyzable physical unit; interface nodes can represent cross-branch interactions.",
    "example": "System: BMS → Subsystem: BMU / Charging Mgmt → Component: LTC6811 / MOSFET"
  },
  "step2": {
    "title": "Step 3: Function Analysis",
    "purpose": "Define functions, requirements, and specifications for each component.",
    "keyPoints": "Use verb+noun format for function descriptions; describe expected performance in requirements; include tolerances in specifications.",
    "example": "Component LTC6811 → Function: Acquire cell voltage → Requirement: Accurately acquire each cell voltage → Spec: ±2mV accuracy, ≥10Hz sampling"
  },
  "step3": {
    "title": "Step 4: Failure Analysis",
    "purpose": "Identify failure modes, effects, and causes for each function to form complete failure chains.",
    "keyPoints": "Failure mode = opposite of function; effect describes system-level consequence; cause should be specific enough for corrective action.",
    "example": "Function \"Acquire cell voltage\" → Failure mode: Insufficient accuracy → Effect: Control deviation → Cause: Sensor aging"
  },
  "step4": {
    "title": "Step 5: Risk Analysis",
    "purpose": "Evaluate Severity(S), Occurrence(O), and Detection(D) for each failure chain and calculate Action Priority(AP).",
    "keyPoints": "S evaluates failure effect severity(1-10); O evaluates cause occurrence likelihood(1-10); D evaluates current detection capability(1-10); AP is auto-calculated.",
    "example": "S=8(Severe) + O=4(Occasional) + D=3(Hard to detect) → AP=H(Must optimize)"
  },
  "step5": {
    "title": "Step 6: Optimization",
    "purpose": "Develop prevention and detection measures for AP=H failure chains to reduce risk.",
    "keyPoints": "Prevention measures reduce occurrence(O); detection measures improve detection(D); severity(S) typically requires design changes to reduce.",
    "example": "Prevention: Redundant sensor layout → Expected O from 4 to 2; Detection: Online real-time monitoring → Expected D from 3 to 2"
  },
  "step6": {
    "title": "Step 7: Confirm & Create",
    "purpose": "Review data completeness across all steps before entering the editor.",
    "keyPoints": "Check structure completeness, function coverage for all components, failure chain completeness, and S/O/D values.",
    "example": "After confirmation, the DFMEA document will be created and you can continue adding details in the editor."
  }
},
"sidebar": {
  "structureTree": "Structure Tree",
  "structureHint": "Structure tree will appear after Step 2",
  "noStructure": "No structure nodes yet"
},
"page": {
  "title": "DFMEA Generation Wizard",
  "saveDraft": "Save Draft",
  "saveSaving": "Saving...",
  "saveSaved": "Saved ✓",
  "saveError": "Unsaved ●",
  "backToList": "Back to List",
  "nextStep": "Next",
  "prevStep": "Previous",
  "finish": "Finish & Enter Editor",
  "confirmEmptyDraft": "The current draft is empty. Are you sure you want to discard it? It will be deleted.",
  "confirmEmptyDraftTitle": "Discard Draft?",
  "confirmEmptyDraftOk": "Discard & Delete",
  "confirmEmptyDraftCancel": "Continue Editing",
  "completionWarning": "The following steps need completion before finishing:",
  "step3Incomplete": "Function Analysis — Some components have no functions defined",
  "step4Incomplete": "Failure Analysis — Some functions have no failure modes defined",
  "step5Incomplete": "Risk Analysis — Some failure modes have missing S/O/D values",
  "loading": "Loading..."
}
```

- [ ] **Step 1: Merge i18n additions into both locale files**

- [ ] **Step 2: Verify JSON is valid**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/zh-CN/dfmea.json','utf8')); console.log('zh-CN OK')" && node -e "JSON.parse(require('fs').readFileSync('src/locales/en-US/dfmea.json','utf8')); console.log('en-US OK')"`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/locales/zh-CN/dfmea.json frontend/src/locales/en-US/dfmea.json
git commit -m "feat(dfmea-wizard): add guidance card and wizard page i18n strings"
```

---

## Task 9: DFMEAWizardPage — Page Shell + Load/Save

**Files:**
- Create: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`

This task creates the page shell, data loading, save integration, step navigation, and exit handling. It does NOT include step content forms (those come in Tasks 10-12).

```tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Modal, Spin, Typography, message, Input, InputNumber, Card, Tag, Empty, Table, Result } from 'antd';
import { ArrowLeftOutlined, PlusOutlined, CheckCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getFMEA, deleteFMEA } from '../../../api/fmea';
import type { FMEADocument, GraphNode, GraphEdge, WizardScope } from '../../../types';
import { useWizardSave, type SaveStatus } from '../../../hooks/useWizardSave';
import { useWizardValidation } from '../../../hooks/useWizardValidation';
import { useDfmeaRules } from '../../../utils/dfmeaRules';
import { buildRows } from '../../../utils/fmeaTable';
import { cascadeDeleteStructureNode } from '../../../utils/wizardCascadeDelete';
import WizardSidebar from '../../../components/dfmea/WizardSidebar';
import WizardGuidanceCard from '../../../components/dfmea/WizardGuidanceCard';

const { Title } = Typography;

export default function DFMEAWizardPage() {
  const { id: fmeaId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation('dfmea');

  const [fmea, setFmea] = useState<FMEADocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [wizardScope, setWizardScope] = useState<WizardScope>({});
  const [currentStep, setCurrentStep] = useState(0);
  const completedSteps = useRef(new Set<number>());

  const { saveStatus, setLockVersion, debouncedSave, immediateSave, lastSavedHashRef } = useWizardSave({ fmeaId: fmeaId! });
  const validation = useWizardValidation(nodes, edges);
  const dfmeaRules = useDfmeaRules();

  // Refs for beforeunload handler — always hold latest values without re-registering listener
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const scopeRef = useRef(wizardScope);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);
  useEffect(() => { edgesRef.current = edges; }, [edges]);
  useEffect(() => { scopeRef.current = wizardScope; }, [wizardScope]);

  /** Lightweight hash — captures node identity + name + type + edges + scope. */
  const computeHash = (n: GraphNode[], e: GraphEdge[], s: WizardScope) =>
    JSON.stringify({
      nodes: n.map(x => x.id + ':' + x.name + ':' + x.type),
      edges: e.map(x => x.source + '->' + x.target + ':' + x.type),
      scope: s,
    });

  // Load FMEA document
  useEffect(() => {
    if (!fmeaId) return;
    getFMEA(fmeaId).then(doc => {
      if (doc.fmea_type !== 'DFMEA') {
        navigate(`/fmea/${doc.fmea_id}`, { replace: true });
        return;
      }
      const loadedNodes = doc.graph_data?.nodes || [];
      const loadedEdges = doc.graph_data?.edges || [];
      const loadedScope = doc.graph_data?.wizardScope || {};
      setFmea(doc);
      setNodes(loadedNodes);
      setEdges(loadedEdges);
      setWizardScope(loadedScope);
      setLockVersion(doc.lock_version);
      // Mark initial state as "clean" — hash captured at load time
      lastSavedHashRef.current = computeHash(loadedNodes, loadedEdges, loadedScope);
      setLoading(false);
    }).catch(() => {
      message.error('加载失败');
      navigate('/fmea');
    });
  }, [fmeaId, navigate, setLockVersion, lastSavedHashRef]);

  // beforeunload warning — compare live state hash vs last-successfully-saved hash
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      const hash = computeHash(nodesRef.current, edgesRef.current, scopeRef.current);
      if (hash !== lastSavedHashRef.current) {
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []); // lastSavedHashRef is a ref — always reads latest without re-registering

  const updateGraphData = useCallback((newNodes: GraphNode[], newEdges: GraphEdge[], newScope?: WizardScope) => {
    setNodes(newNodes);
    setEdges(newEdges);
    if (newScope !== undefined) setWizardScope(newScope);
    // Compute hash at enqueue time — NOT at save-success time
    const hash = computeHash(newNodes, newEdges, newScope ?? wizardScope);
    debouncedSave({ nodes: newNodes, edges: newEdges, wizardScope: newScope ?? wizardScope }, fmea?.title, hash);
  }, [debouncedSave, wizardScope, fmea?.title]);

  const goToStep = useCallback((step: number) => {
    completedSteps.current.add(currentStep);
    setCurrentStep(step);
  }, [currentStep]);

  const handleFinish = async () => {
    const completedScope = { ...wizardScope, wizard_completed: true };
    const hash = computeHash(nodes, edges, completedScope);
    const success = await immediateSave({ nodes, edges, wizardScope: completedScope }, fmea?.title, hash);
    if (!success) return;
    navigate(`/fmea/${fmeaId}`);
  };

  const handleBackToList = () => {
    const hasOnlyInitialSystem = nodes.length <= 1 && edges.length === 0;
    if (hasOnlyInitialSystem) {
      Modal.confirm({
        title: t('wizard.page.confirmEmptyDraftTitle'),
        content: t('wizard.page.confirmEmptyDraft'),
        okText: t('wizard.page.confirmEmptyDraftOk'),
        cancelText: t('wizard.page.confirmEmptyDraftCancel'),
        okButtonProps: { danger: true },
        onOk: async () => {
          try { await deleteFMEA(fmeaId!); } catch { /* ignore */ }
          navigate('/fmea');
        },
      });
    } else {
      navigate('/fmea');
    }
  };

  const canFinish = validation.warnings.length === 0
    && validation.step3Complete
    && validation.step4Complete
    && validation.step5Complete;

  const saveStatusLabel: Record<SaveStatus, string> = {
    idle: '',
    saving: t('wizard.page.saveSaving'),
    saved: t('wizard.page.saveSaved'),
    error: t('wizard.page.saveError'),
  };

  // Placeholder — Tasks 10-12 insert real renderStep0..renderStep6 above this map
  const STEP_RENDERERS: Record<number, () => React.ReactNode> = {
    0: () => <div />,
    1: () => <div />,
    2: () => <div />,
    3: () => <div />,
    4: () => <div />,
    5: () => <div />,
    6: () => <div />,
  };

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 16px', borderBottom: '1px solid var(--qf-border)' }}>
        <Title level={4} style={{ margin: 0 }}>
          {t('wizard.page.title')} — {fmea?.document_no}
        </Title>
        <Space>
          <span aria-live="polite">{saveStatusLabel[saveStatus]}</span>
          <Button onClick={handleBackToList} icon={<ArrowLeftOutlined />}>{t('wizard.page.backToList')}</Button>
          <Button type="primary" onClick={() => {
            const hash = computeHash(nodes, edges, wizardScope);
            immediateSave({ nodes, edges, wizardScope }, fmea?.title, hash);
          }} loading={saveStatus === 'saving'}>
            {t('wizard.page.saveDraft')}
          </Button>
        </Space>
      </div>

      {/* Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left sidebar */}
        <div style={{ width: 280, flexShrink: 0, overflow: 'auto', background: '#fafafa' }}>
          <WizardSidebar
            currentStep={currentStep}
            onStepClick={goToStep}
            completedSteps={completedSteps.current}
            warnings={validation.warnings}
            structureNodes={nodes}
            edges={edges}
          />
        </div>

        {/* Right content area */}
        <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
          <WizardGuidanceCard stepIndex={currentStep} />

          {/* Step content — renderers added in Tasks 10-12 */}
          <div style={{ minHeight: 300 }}>
            {STEP_RENDERERS[currentStep]?.() || <div />}
          </div>

          {/* Bottom navigation */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--qf-border)' }}>
            {currentStep > 0 && (
              <Button onClick={() => goToStep(currentStep - 1)}>{t('wizard.page.prevStep')}</Button>
            )}
            {currentStep < 6 ? (
              <Button type="primary" onClick={() => goToStep(currentStep + 1)} loading={saveStatus === 'saving'}>
                {t('wizard.page.nextStep')}
              </Button>
            ) : (
              <Button type="primary" onClick={handleFinish} disabled={!canFinish} loading={saveStatus === 'saving'}>
                {t('wizard.page.finish')}
              </Button>
            )}
          </div>

          {/* Validation warnings for finish button */}
          {currentStep === 6 && validation.warnings.length > 0 && (
            <div style={{ marginTop: 16, padding: 12, background: '#fff2f0', border: '1px solid #ffccc7', borderRadius: 4 }}>
              <div style={{ fontWeight: 600, color: '#cf1322', marginBottom: 4 }}>{t('wizard.page.completionWarning')}</div>
              {validation.warnings.map(w => (
                <div key={w} style={{ color: '#cf1322' }}>• {t(`wizard.page.step${w}Incomplete`)}</div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 1: Create the page shell component**

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit 2>&1 | head -30`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea-wizard): add DFMEAWizardPage shell with load/save/validation"
```

**Note:** The `STEP_RENDERERS` map is defined inside the component (after `saveStatusLabel`, before `if (loading)`). It starts with placeholder empty renderers. Each Task 10-12 inserts `renderStep0`–`renderStep6` functions ABOVE the map and updates the corresponding map entry. This ensures the render functions have access to component state (`nodes`, `edges`, `updateGraphData`, `t`, `dfmeaRules`).

---

## Task 10: Step 1-2 Content (5T Scope + Structure Analysis)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`

### Step 0 — 5T Scope

Render 5 `Input` fields bound to `wizardScope.team/timeframe/tool/task/trend`. On change, call `updateGraphData(nodes, edges, newScope)`.

```tsx
const renderStep0 = () => (
  <div style={{ display: 'grid', gap: 12 }}>
    <Input placeholder={t('wizard.scope.team')} value={wizardScope.team || ''}
      onChange={e => updateGraphData(nodes, edges, { ...wizardScope, team: e.target.value })} />
    <Input placeholder={t('wizard.scope.timeframe')} value={wizardScope.timeframe || ''}
      onChange={e => updateGraphData(nodes, edges, { ...wizardScope, timeframe: e.target.value })} />
    <Input placeholder={t('wizard.scope.tool')} value={wizardScope.tool || ''}
      onChange={e => updateGraphData(nodes, edges, { ...wizardScope, tool: e.target.value })} />
    <Input placeholder={t('wizard.scope.task')} value={wizardScope.task || ''}
      onChange={e => updateGraphData(nodes, edges, { ...wizardScope, task: e.target.value })} />
    <Input placeholder={t('wizard.scope.trend')} value={wizardScope.trend || ''}
      onChange={e => updateGraphData(nodes, edges, { ...wizardScope, trend: e.target.value })} />
  </div>
);
```

### Step 1 — Structure Analysis

Render a list of structure nodes with add/delete/edit functionality. Uses `cascadeDeleteStructureNode` for delete. Add System/Interface buttons. Each node renders as a Card with inline Input for name editing and a delete button that calls cascade delete.

```tsx
const renderStep1 = () => {
  const structureNodes = nodes.filter(n => ['System', 'Subsystem', 'Component', 'Interface', 'DesignParameter'].includes(n.type));
  const CHILD_TYPE: Record<string, string> = { System: 'Subsystem', Subsystem: 'Component' };
  const CHILD_EDGE_TYPE: Record<string, string> = { System: 'HAS_PROCESS_STEP', Subsystem: 'HAS_WORK_ELEMENT' };

  const handleAddNode = (type: string, parentId?: string) => {
    const newNode: GraphNode = {
      id: `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_${type.toLowerCase()}`,
      type, name: t(`wizard.typeLabels.${type}`, { defaultValue: type }),
      severity: 0, occurrence: 0, detection: 0,
      ...(type === 'Interface' ? { interface_type: 'physical' } : {}),
    };
    const newEdges = parentId
      ? [...edges, { source: parentId, target: newNode.id, type: CHILD_EDGE_TYPE[nodes.find(n => n.id === parentId)?.type || 'System'] || 'HAS_PROCESS_STEP' }]
      : edges;
    updateGraphData([...nodes, newNode], newEdges);
  };

  const handleDeleteNode = (nodeId: string) => {
    const result = cascadeDeleteStructureNode(nodeId, nodes, edges);
    updateGraphData(result.nodes, result.edges);
  };

  const handleRenameNode = (nodeId: string, name: string) => {
    updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, name } : n), edges);
  };

  const typeLabel = (type: string) => t(`wizard.typeLabels.${type}`, { defaultValue: type });
  const TYPE_COLORS: Record<string, string> = { System: 'red', Subsystem: 'orange', Component: 'green', Interface: 'purple', DesignParameter: 'blue' };

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('System')}>{t('wizard.structure.addSystem')}</Button>
        <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('Interface')}>{t('wizard.structure.addInterface')}</Button>
      </Space>
      {structureNodes.length === 0 && <Empty description={t('wizard.structure.empty')} />}
      {structureNodes.map(node => (
        <Card key={node.id} size="small" style={{ marginBottom: 8, marginLeft: node.type === 'Subsystem' ? 20 : node.type === 'Component' ? 40 : 0 }}>
          <Space>
            <Tag color={TYPE_COLORS[node.type]}>{typeLabel(node.type)}</Tag>
            <Input size="small" value={node.name} style={{ width: 200 }}
              onChange={e => handleRenameNode(node.id, e.target.value)} />
            {CHILD_TYPE[node.type] && (
              <Button size="small" onClick={() => handleAddNode(CHILD_TYPE[node.type], node.id)}>
                + {typeLabel(CHILD_TYPE[node.type])}
              </Button>
            )}
            <Button size="small" danger onClick={() => handleDeleteNode(node.id)}>{t('wizard.structure.delete')}</Button>
          </Space>
        </Card>
      ))}
    </div>
  );
};
```

Insert `renderStep0` and `renderStep1` ABOVE the `STEP_RENDERERS` map inside the component. Then update the map entries: `STEP_RENDERERS[0] = renderStep0` and `STEP_RENDERERS[1] = renderStep1`.

- [ ] **Step 1: Add step content for steps 0 and 1**

- [ ] **Step 2: Verify the page renders steps 0 and 1**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea-wizard): add Step 1-2 content (5T scope + structure analysis)"
```

---

## Task 11: Step 3-4 Content (Function Analysis + Failure Analysis)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`

### Step 2 — Function Analysis

For each Component node, render a Card with Input fields for function name, requirement, and specification. Creates `ProcessWorkElementFunction` nodes linked via `HAS_FUNCTION` edges.

```tsx
const renderStep2 = () => {
  const components = nodes.filter(n => n.type === 'Component');
  if (components.length === 0) return <Empty description="请先在第二步添加零部件" />;

  const handleAddFunction = (compId: string) => {
    const funcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_func`;
    const funcNode: GraphNode = {
      id: funcId, type: 'ProcessWorkElementFunction', name: '',
      requirement: '', specification: '', severity: 0, occurrence: 0, detection: 0,
    };
    updateGraphData([...nodes, funcNode], [...edges, { source: compId, target: funcId, type: 'HAS_FUNCTION' }]);
  };

  const handleUpdateFunction = (funcId: string, field: 'name' | 'requirement' | 'specification', value: string) => {
    updateGraphData(nodes.map(n => n.id === funcId ? { ...n, [field]: value } : n), edges);
  };

  return (
    <div>
      {components.map(comp => {
        const funcEdges = edges.filter(e => e.source === comp.id && e.type === 'HAS_FUNCTION');
        const funcNodes = funcEdges.map(e => nodes.find(n => n.id === e.target)).filter(Boolean) as GraphNode[];
        return (
          <Card key={comp.id} size="small" title={comp.name} style={{ marginBottom: 12 }}>
            {funcNodes.map(fn => (
              <div key={fn.id} style={{ marginBottom: 8 }}>
                <Input placeholder={t('wizard.function.functionDesc')} value={fn.name}
                  onChange={e => handleUpdateFunction(fn.id, 'name', e.target.value)} style={{ marginBottom: 4 }} />
                <Input placeholder={t('wizard.function.requirement')} value={fn.requirement || ''}
                  onChange={e => handleUpdateFunction(fn.id, 'requirement', e.target.value)} style={{ marginBottom: 4 }} />
                <Input placeholder={t('wizard.function.specification')} value={fn.specification || ''}
                  onChange={e => handleUpdateFunction(fn.id, 'specification', e.target.value)} />
              </div>
            ))}
            <Button size="small" type="dashed" onClick={() => handleAddFunction(comp.id)}>
              + 添加功能
            </Button>
          </Card>
        );
      })}
    </div>
  );
};
```

### Step 3 — Failure Analysis

For each Function node, render failure mode/effect/cause inputs with smart recommendations from `useDfmeaRules`. Creates FailureMode, FailureEffect, FailureCause nodes with proper edge types.

```tsx
const renderStep3 = () => {
  const { generateFailureModes, suggestFailureChain } = dfmeaRules;
  const functions = nodes.filter(n => ['ProcessWorkElementFunction', 'ProcessItemFunction', 'ProcessStepFunction'].includes(n.type));

  if (functions.length === 0) return <Empty description="请先在第三步定义功能" />;

  const handleAddFailure = (funcId: string, mode?: string, effect?: string, cause?: string) => {
    const fmId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_fm`;
    const feId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_fe`;
    const fcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_fc`;
    const newNodes: GraphNode[] = [
      { id: fmId, type: 'FailureMode', name: mode || t('wizard.failure.newFailureMode'), severity: 0, occurrence: 0, detection: 0 },
      { id: feId, type: 'FailureEffect', name: effect || '', severity: 0, occurrence: 0, detection: 0 },
      { id: fcId, type: 'FailureCause', name: cause || '', severity: 0, occurrence: 0, detection: 0 },
    ];
    const newEdges: GraphEdge[] = [
      { source: funcId, target: fmId, type: 'HAS_FAILURE_MODE' },
      { source: fmId, target: feId, type: 'EFFECT_OF' },
      { source: fcId, target: fmId, type: 'CAUSE_OF' },
    ];
    updateGraphData([...nodes, ...newNodes], [...edges, ...newEdges]);
  };

  const handleDeleteFailureChain = (failureModeId: string) => {
    // Remove FailureMode, its FailureEffect, and connected FailureCause → PreventionControl/DetectionControl
    // Uses the same cascade logic but scoped to a single failure chain
    const toDelete = new Set<string>([failureModeId]);
    const edgesToDelete = new Set<string>();

    // Find FailureEffect (outgoing EFFECT_OF)
    for (const e of edges) {
      if (e.source === failureModeId && e.type === 'EFFECT_OF') {
        toDelete.add(e.target);
        edgesToDelete.add(`${e.source}->${e.target}->${e.type}`);
      }
    }

    // Find FailureCause (incoming CAUSE_OF)
    for (const e of edges) {
      if (e.target === failureModeId && e.type === 'CAUSE_OF') {
        toDelete.add(e.source);
        edgesToDelete.add(`${e.source}->${e.target}->${e.type}`);
        // Find PreventionControl and DetectionControl from this cause
        for (const e2 of edges) {
          if (e2.source === e.source && (e2.type === 'PREVENTED_BY' || e2.type === 'DETECTED_BY')) {
            // Only delete control nodes that are ONLY connected to this cause
            const otherParents = edges.filter(e3 => e3.target === e2.target && e3.source !== e.source);
            if (otherParents.length === 0) {
              toDelete.add(e2.target);
            }
            edgesToDelete.add(`${e2.source}->${e2.target}->${e2.type}`);
          }
        }
      }
    }

    // Remove edges targeting deleted nodes
    for (const e of edges) {
      if (toDelete.has(e.source) || toDelete.has(e.target)) {
        edgesToDelete.add(`${e.source}->${e.target}->${e.type}`);
      }
    }

    const filteredNodes = nodes.filter(n => !toDelete.has(n.id));
    const filteredEdges = edges.filter(e => !edgesToDelete.has(`${e.source}->${e.target}->${e.type}`));
    updateGraphData(filteredNodes, filteredEdges);
  };

  const handleUpdateNodeField = (nodeId: string, field: string, value: string) => {
    updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, [field]: value } : n), edges);
  };

  return (
    <div>
      {functions.map(func => {
        // Find FailureMode nodes connected to this function
        const fmEdges = edges.filter(e => e.source === func.id && e.type === 'HAS_FAILURE_MODE');
        const fmNodes = fmEdges.map(e => nodes.find(n => n.id === e.target)).filter(Boolean) as GraphNode[];
        const suggestedModes = generateFailureModes(func.name);

        return (
          <Card key={func.id} size="small" title={func.name} style={{ marginBottom: 12 }}>
            {fmNodes.length === 0 && suggestedModes.length > 0 && (
              <div style={{ marginBottom: 8, padding: 8, background: '#f6ffed', borderRadius: 4 }}>
                <Tag color="green">{t('wizard.failure.recommended')}</Tag>
                <span style={{ fontSize: 12 }}> {t('wizard.failure.autoRecommend')}</span>
                <Space size={4} style={{ marginTop: 4 }}>
                  {suggestedModes.slice(0, 3).map(mode => (
                    <Button key={mode} size="small" onClick={() => {
                      const chain = suggestFailureChain(mode);
                      handleAddFailure(func.id, mode, chain.effects[0] || '', chain.causes[0] || '');
                    }}>{mode}</Button>
                  ))}
                </Space>
              </div>
            )}
            {fmNodes.map(fmNode => {
              // Find this FM's FailureEffect (outgoing EFFECT_OF)
              const effectEdge = edges.find(e => e.source === fmNode.id && e.type === 'EFFECT_OF');
              const effectNode = effectEdge ? nodes.find(n => n.id === effectEdge!.target) : null;
              // Find this FM's FailureCause (incoming CAUSE_OF)
              const causeEdges = edges.filter(e => e.target === fmNode.id && e.type === 'CAUSE_OF');
              const causeNodes = causeEdges.map(e => nodes.find(n => n.id === e.source)).filter(Boolean) as GraphNode[];

              return (
                <div key={fmNode.id} style={{ marginBottom: 8, padding: 8, background: '#f5f5f5', borderRadius: 4 }}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Input size="small" value={fmNode.name} addonBefore={t('wizard.failure.failureMode')}
                      onChange={e => handleUpdateNodeField(fmNode.id, 'name', e.target.value)} />
                    <Input size="small" value={effectNode?.name || ''} addonBefore={t('wizard.failure.failureEffect')}
                      onChange={e => effectNode && handleUpdateNodeField(effectNode.id, 'name', e.target.value)} />
                    {causeNodes.map(causeNode => (
                      <Input key={causeNode.id} size="small" value={causeNode.name} addonBefore={t('wizard.failure.failureCause')}
                        onChange={e => handleUpdateNodeField(causeNode.id, 'name', e.target.value)} />
                    ))}
                    <Button size="small" danger onClick={() => handleDeleteFailureChain(fmNode.id)}>{t('wizard.failure.delete')}</Button>
                  </Space>
                </div>
              );
            })}
            <Button size="small" type="dashed" onClick={() => handleAddFailure(func.id)}>{t('wizard.failure.addFailureMode')}</Button>
          </Card>
        );
      })}
    </div>
  );
};

Insert `renderStep2` and `renderStep3` ABOVE the `STEP_RENDERERS` map inside the component. Then update `STEP_RENDERERS[2] = renderStep2` and `STEP_RENDERERS[3] = renderStep3`.

- [ ] **Step 1: Add step content for steps 2 and 3**

- [ ] **Step 2: Verify smart recommendations work**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea-wizard): add Step 3-4 content (function + failure analysis)"
```

---

## Task 12: Step 5-7 Content (Risk Analysis + Optimization + Confirmation)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`

### Step 4 — Risk Analysis (S/O/D)

Renders a Table of failure chain rows using `buildRows`. S is on FailureEffect, O on FailureCause, D on DetectionControl. Each row shows the failure mode name, and InputNumber for S/O/D. AP is auto-calculated via `analyzeRisk`.

```tsx
const renderStep4 = () => {
  const { analyzeRisk } = dfmeaRules;
  const rows = buildRows(nodes, edges);
  const nodeMap = new Map(nodes.map(n => [n.id, n]));

  if (rows.length === 0) return <Empty description="请先在第四步定义失效模式" />;

  const handleUpdateRisk = (row: FMEARow, field: 'severity' | 'occurrence' | 'detection', nodeId: string, value: number) => {
    updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, [field]: value } : n), edges);
  };

  return (
    <Table size="small" dataSource={rows} rowKey="key" pagination={false}
      columns={[
        { title: t('wizard.failure.failureMode'), dataIndex: 'key', width: 140, render: (_: any, r: FMEARow) => {
          const fm = nodeMap.get(r.failureModeNodeId);
          return fm?.name || '';
        }},
        { title: 'S', width: 60, render: (_: any, r: FMEARow) => {
          const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
          return <InputNumber size="small" min={1} max={10} value={effect?.severity || undefined}
            style={{ width: 50 }} onChange={val => effect && handleUpdateRisk(r, 'severity', effect.id, val || 0)} />;
        }},
        { title: 'O', width: 60, render: (_: any, r: FMEARow) => {
          const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
          return <InputNumber size="small" min={1} max={10} value={cause?.occurrence || undefined}
            style={{ width: 50 }} onChange={val => cause && handleUpdateRisk(r, 'occurrence', cause.id, val || 0)} />;
        }},
        { title: 'D', width: 60, render: (_: any, r: FMEARow) => {
          const dcId = r.detectionControlIds[0];
          const dc = dcId ? nodeMap.get(dcId) : null;
          return <InputNumber size="small" min={1} max={10} value={dc?.detection || undefined}
            style={{ width: 50 }} onChange={val => dc && handleUpdateRisk(r, 'detection', dc.id, val || 0)} />;
        }},
        { title: 'AP', width: 80, render: (_: any, r: FMEARow) => {
          const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
          const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
          const dcId = r.detectionControlIds[0];
          const dc = dcId ? nodeMap.get(dcId) : null;
          const s = effect?.severity || 0, o = cause?.occurrence || 0, d = dc?.detection || 0;
          const { ap } = analyzeRisk(s, o, d);
          return <Tag color={ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'green'}>{ap || '-'}</Tag>;
        }},
      ]}
    />
  );
};
```

### Step 5 — Optimization

Shows only AP=H failure chains. For each, renders prevention and detection measure Input.TextArea. Creates or updates PreventionControl and DetectionControl nodes with proper edges.

```tsx
const renderStep5 = () => {
  const { suggestMeasures, analyzeRisk } = dfmeaRules;
  const rows = buildRows(nodes, edges);
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const highRiskRows = rows.filter(r => {
    const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
    const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
    const dcId = r.detectionControlIds[0];
    const dc = dcId ? nodeMap.get(dcId) : null;
    const s = effect?.severity || 0, o = cause?.occurrence || 0, d = dc?.detection || 0;
    return analyzeRisk(s, o, d).ap === 'H';
  });

  if (highRiskRows.length === 0) {
    return <Result icon={<CheckCircleOutlined />} title={t('wizard.optimization.noOptimization')} subTitle={t('wizard.optimization.noOptimizationHint')} />;
  }

  const handleAddOptimization = (row: FMEARow, type: 'prevention' | 'detection', value: string) => {
    const causeId = row.failureCauseNodeId;
    if (!causeId) return;

    let newNodes = [...nodes];
    const newEdges = [...edges];

    if (type === 'prevention') {
      // Find existing PreventionControl for this cause, or create new
      const existingPcIds = edges
        .filter(e => e.source === causeId && e.type === 'PREVENTED_BY')
        .map(e => e.target);
      if (existingPcIds.length > 0) {
        // Update name on existing node
        newNodes = newNodes.map(n => n.id === existingPcIds[0] ? { ...n, name: value } : n);
      } else {
        const pcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_pc`;
        newNodes.push({ id: pcId, type: 'PreventionControl', name: value, severity: 0, occurrence: 0, detection: 0 });
        newEdges.push({ source: causeId, target: pcId, type: 'PREVENTED_BY' });
      }
    } else {
      // Find existing DetectionControl for this cause, or create new
      const existingDcIds = edges
        .filter(e => e.source === causeId && e.type === 'DETECTED_BY')
        .map(e => e.target);
      if (existingDcIds.length > 0) {
        newNodes = newNodes.map(n => n.id === existingDcIds[0] ? { ...n, name: value } : n);
      } else {
        const dcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_dc`;
        newNodes.push({ id: dcId, type: 'DetectionControl', name: value, severity: 0, occurrence: 0, detection: 0 });
        newEdges.push({ source: causeId, target: dcId, type: 'DETECTED_BY' });
      }
    }

    updateGraphData(newNodes, newEdges);
  };

  return (
    <div>
      <Paragraph style={{ color: '#cf1322' }}>{t('wizard.optimization.mustOptimize', { count: highRiskRows.length })}</Paragraph>
      {highRiskRows.map(r => {
        const fm = nodeMap.get(r.failureModeNodeId);
        const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
        const measures = suggestMeasures(fm?.name || '', 'H');
        const causeId = r.failureCauseNodeId;
        const existingPc = causeId ? edges.find(e => e.source === causeId && e.type === 'PREVENTED_BY') : null;
        const existingDc = causeId ? edges.find(e => e.source === causeId && e.type === 'DETECTED_BY') : null;
        const pcName = existingPc ? nodeMap.get(existingPc.target)?.name || '' : '';
        const dcName = existingDc ? nodeMap.get(existingDc.target)?.name || '' : '';

        return (
          <Card key={r.key} size="small" title={fm?.name || 'Failure Mode'} style={{ marginBottom: 12 }}>
            <Input.TextArea rows={2} placeholder={measures.prevention.join(' / ')} value={pcName}
              onChange={e => handleAddOptimization(r, 'prevention', e.target.value)} style={{ marginBottom: 8 }} />
            <Input.TextArea rows={2} placeholder={measures.detection.join(' / ')} value={dcName}
              onChange={e => handleAddOptimization(r, 'detection', e.target.value)} />
          </Card>
        );
      })}
    </div>
  );
};
```

### Step 6 — Confirmation

Shows summary statistics and a "Finish" button (already in the page shell). Lists counts of structure nodes, functions, failure chains, total nodes, total edges.

```tsx
const renderStep6 = () => {
  const structCount = nodes.filter(n => ['System', 'Subsystem', 'Component'].includes(n.type)).length;
  const funcCount = nodes.filter(n => n.type === 'ProcessWorkElementFunction').length;
  const fmCount = nodes.filter(n => n.type === 'FailureMode').length;
  const skeleton = { nodes, edges };

  return (
    <Card size="small" style={{ marginBottom: 12 }}>
      <div>{t('wizard.confirm.structureNodes', { count: structCount })}</div>
      <div>{t('wizard.confirm.functionNodes', { count: funcCount })}</div>
      <div>{t('wizard.confirm.failureChains', { count: fmCount })}</div>
      <div>{t('wizard.confirm.totalNodes', { count: skeleton.nodes.length })}</div>
      <div>{t('wizard.confirm.totalEdges', { count: skeleton.edges.length })}</div>
    </Card>
  );
};
```

Insert `renderStep4`, `renderStep5`, and `renderStep6` ABOVE the `STEP_RENDERERS` map inside the component. Then update the map to point to all 7 render functions:

```tsx
const STEP_RENDERERS: Record<number, () => React.ReactNode> = {
  0: renderStep0,
  1: renderStep1,
  2: renderStep2,
  3: renderStep3,
  4: renderStep4,
  5: renderStep5,
  6: renderStep6,
};
```

This replaces the placeholder map defined in Task 9.

- [ ] **Step 1: Add step content for steps 4, 5, and 6**

- [ ] **Step 2: Verify AP calculation and confirmation statistics**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx
git commit -m "feat(dfmea-wizard): add Step 5-7 content (risk + optimization + confirmation)"
```

---

## Task 13: Route + List Page + Editor Redirect Integration

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/planning/fmea/FMEAListPage.tsx`
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`

### 13a: Add route

In `App.tsx`, add import and route:

```tsx
import DFMEAWizardPage from "./pages/planning/fmea/DFMEAWizardPage";
// ... in routes, after /fmea/:id:
<Route path="/fmea/wizard/:id" element={<ProtectedRoute requiredModule="fmea"><DFMEAWizardPage /></ProtectedRoute>} />
```

### 13b: Modify FMEAListPage

In `FMEAListPage.tsx`:
1. Change `handleCreate` so DFMEA creation navigates to `/fmea/wizard/{id}`
2. In the columns actions, make draft DFMEAs navigate to the wizard
3. Remove the `GenerationWizard` modal and `wizardOpen` state

### 13c: Modify FMEAEditorPage

In `FMEAEditorPage.tsx`, add after the document load (around line 218):

```tsx
// Only redirect DFMEAs that are draft AND haven't completed the wizard.
// The wizard sets wizardScope.wizard_completed = true on finish, so we only
// redirect if that flag is absent — preventing a redirect loop.
if (doc.fmea_type === 'DFMEA' && doc.status === 'draft') {
  const wizardScope = doc.graph_data?.wizardScope;
  if (!wizardScope || !wizardScope.wizard_completed) {
    navigate(`/fmea/wizard/${doc.fmea_id}`, { replace: true });
    return;
  }
}
```

- [ ] **Step 1: Apply all integration changes**

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit 2>&1 | head -30`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/planning/fmea/FMEAListPage.tsx frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "feat(dfmea-wizard): integrate route, list page, and editor redirect"
```

---

## Task 14: Integration Test & Polish

- [ ] **Step 1: Start dev servers**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && uvicorn app.main:app --reload &` and `cd /Users/sam/Documents/Code/OpenQMS/frontend && npm run dev`

- [ ] **Step 2: Manual smoke test**

1. Login as admin → FMEA list → New FMEA → select DFMEA → submit
2. Verify redirect to `/fmea/wizard/{id}` with wizard page
3. Fill Step 1 5T fields → Next
4. Step 2: Add System/Subsystem/Component → verify structure tree in sidebar
5. Delete a node → verify cascade deletion
6. Step through all 7 steps → verify each renders correctly
7. Click "Save Draft" → verify save status shows ✓
8. Click "Back to List" → verify draft appears with "草稿" tag
9. Click draft row → verify it reopens wizard with data restored
10. Complete all steps → click "Finish" → verify redirect to editor

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "fix(dfmea-wizard): integration test fixes"
```

---

## Self-Review Checklist (v4-fixed)

- [x] **Spec coverage:** All sections covered — routes (Task 13), layout (Task 9), save mechanism (Task 4), step content (Tasks 10-12), validation (Task 5), cascade delete (Task 3), wizardScope (Tasks 1-2), i18n (Task 8), guidance cards (Task 6), sidebar (Task 7), editor redirect (Task 13), exit confirmation (Task 9)
- [x] **Placeholder scan:** No TBD/TODO/fill-in-later. All code blocks contain complete implementations. Step 3 failure analysis has full render code with handleAddFailure, handleDeleteFailureChain, and smart recommendations. Step 5 optimization has full PreventionControl/DetectionControl creation code.
- [x] **Type consistency:** `WizardScope` uses `wizard_completed` (not `_completed`), defined in both backend (Task 1) and frontend (Task 2). `lock_version` added to `FMEAResponse` (Task 1). `deleteFMEA` API (Task 2) matches backend DELETE endpoint (Task 1). `useWizardSave` returns `boolean` from `immediateSave` (Task 4). `useWizardValidation` uses `buildRows` (Task 5). `cascadeDeleteStructureNode` correctly handles root node deletion and CAUSE_OF edge direction (Task 3). `useDfmeaRules()` called at top level, not in render functions (Task 12 fix). `STEP_RENDERERS` placeholder defined inside the component in Task 9 with empty renderers. All imports listed in Task 9.
- [x] **Redirect loop fix:** `wizard_completed` flag prevents editor from redirecting completed wizards back. Editor only redirects if `wizardScope.wizard_completed` is absent or falsy (Task 13).
- [x] **Dirty flag fix (hash-at-enqueue):** Payload hash computed at enqueue time, passed to `debouncedSave`/`immediateSave`. On success, hook writes THAT hash (not current page state) into `lastSavedHashRef`. Race-free: if save A (hash-A) completes while page is already at hash-B, `lastSavedHashRef` stays at hash-A and `beforeunload` correctly warns about B. `nodesRef`/`edgesRef`/`scopeRef` ensure `beforeunload` handler always reads fresh state without re-registering. `dirtyRef` removed entirely — dirty state is `computeHash(live) !== lastSavedHashRef.current`.
- [x] **Cascade delete root node:** Root node `nodeId` always added to `nodeIdsToDelete`. External parent check only applies to descendant nodes.
- [x] **Step 2 edge types:** Uses `CHILD_EDGE_TYPE` mapping matching StructureTree.tsx: System→HAS_PROCESS_STEP, Subsystem→HAS_WORK_ELEMENT.
- [x] **Neo4j projection cleanup:** `delete_fmea` service includes audit log and outbox event (Task 1b). `delete_fmea_projection` uses `self._driver` (not `self.driver`), `settings.NEO4J_DATABASE`, and `session.execute_write(_tx)` pattern matching existing `sync_fmea_to_neo4j` (Task 1b). Worker branches on `task.event_type == "fmea.deleted"` using existing local variable names (`projection`, `task`) — no phantom `event_type`/`projection_service`/`aggregate_id` (Task 1b). Task 1 file list and commit command include `graph_projection_service.py` and `graph_sync_worker.py`.
- [x] **STEP_RENDERERS scoping:** Map defined INSIDE the component (after `saveStatusLabel`, before `if (loading)`). Tasks 10-12 insert `renderStep0`–`renderStep6` ABOVE the map and update entries. Single name `STEP_RENDERERS` throughout (no `STEP_CONTENT_MAP`). All `renderStep*` functions have access to component state.
- [x] **TypeScript compilation:** `let newNodes` instead of `const newNodes` in Task 12 optimization step. All imports present in Task 9.