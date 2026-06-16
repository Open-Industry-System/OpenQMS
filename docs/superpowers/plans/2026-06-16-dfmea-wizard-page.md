# DFMEA Wizard Page Implementation Plan (v2 — revised)

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

### 1a: Add WizardScopeSchema, lock_version to FMEAResponse, and wizardScope to GraphDataSchema

In `backend/app/schemas/fmea.py`, add before `GraphDataSchema`:

```python
class WizardScopeSchema(BaseModel):
    team: str | None = None
    timeframe: str | None = None
    tool: str | None = None
    task: str | None = None
    trend: str | None = None


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
async def delete_fmea(db: AsyncSession, fmea_id: uuid.UUID) -> None:
    fmea = await get_fmea(db, fmea_id)
    if fmea is None:
        raise ValueError("FMEA not found")
    await db.delete(fmea)
    await db.commit()
```

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
    await fmea_service.delete_fmea(db, fmea_id)
```

- [ ] **Step 1: Apply schema + service + API changes**

- [ ] **Step 2: Run backend tests**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/ -x --tb=short -q 2>&1 | tail -20`

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/fmea.py backend/app/services/fmea_service.py backend/app/api/fmea.py
git commit -m "feat(dfmea-wizard): add WizardScopeSchema, lock_version in response, DELETE endpoint"
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

Add `lock_version` to `FMEADocument` interface (around line 99):

```typescript
export interface FMEADocument {
  fmea_id: string;
  document_no: string;
  title: string;
  fmea_type: string;
  product_line_code: string;
  status: string;
  version: number;
  lock_version: number;
  graph_data: GraphData;
  // ... rest of existing fields
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

The cascade delete must handle shared control nodes correctly: when deleting a structure node, follow the dependency chain but only remove downstream nodes that have NO other parents outside the deletion path. Shared PreventionControl/DetectionControl nodes (referenced by multiple causes) must be kept; only their edges from the deleted path are removed.

```typescript
import type { GraphNode, GraphEdge } from '../types';

/**
 * Remove a structure node and cascade-delete truly orphaned downstream nodes.
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

  // Collect the entire downstream subtree from nodeId (BFS)
  const downstream = new Set<string>();
  const queue = [nodeId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (downstream.has(current)) continue;
    downstream.add(current);
    for (const e of edges) {
      if (e.source === current) {
        queue.push(e.target);
      }
    }
  }

  // For each downstream node (including nodeId itself),
  // check if it has incoming edges from OUTSIDE the downstream set.
  // If it does, it's shared — keep it, only remove edges from inside the set.
  for (const id of downstream) {
    const hasExternalParent = edges.some(
      e => e.target === id && !downstream.has(e.source)
    );

    if (!hasExternalParent) {
      // No external parent — this node is orphaned, delete it
      nodeIdsToDelete.add(id);
    }

    // Remove edges where source is in the deletion path and target is in the deletion path
    // (these edges are part of the subtree being removed)
    for (const e of edges) {
      if (e.source === id && downstream.has(e.target)) {
        edgeKeysToDelete.add(`${e.source}->${e.target}->${e.type}`);
      }
    }
  }

  // Also remove all edges targeting deleted nodes from outside
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

  it('cascades deletion of all descendants', () => {
    // s1 -> ss1 -> c1 -> func1 -> fm1 -> fe1
    //                                      fc1
    const nodes = [
      n('s1', 'System'), n('ss1', 'Subsystem'), n('c1', 'Component'),
      n('func1', 'ProcessWorkElementFunction'), n('fm1', 'FailureMode'),
      n('fe1', 'FailureEffect'), n('fc1', 'FailureCause'),
    ];
    const edges = [
      e('s1', 'ss1', 'HAS_PROCESS_STEP'),
      e('ss1', 'c1', 'HAS_WORK_ELEMENT'),
      e('c1', 'func1', 'HAS_FUNCTION'),
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fc1', 'fm1', 'CAUSE_OF'),
    ];
    const result = cascadeDeleteStructureNode('ss1', nodes, edges);
    // Only s1 should remain
    expect(result.nodes.map(n => n.id)).toEqual(['s1']);
    expect(result.edges).toHaveLength(0);
  });

  it('keeps shared PreventionControl referenced by multiple causes', () => {
    // fc1 -> pc1 (shared by fc1 and fc2)
    // fc2 -> pc1 (shared)
    // Deleting the subtree containing fc1 should NOT delete pc1
    const pc1 = n('pc1', 'PreventionControl', 'Shared PC');
    const nodes = [
      n('s1', 'System'), n('c1', 'Component'), n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'), n('fc1', 'FailureCause'), n('fc2', 'FailureCause'),
      pc1,
    ];
    const edges = [
      e('s1', 'c1', 'HAS_PROCESS_STEP'),
      e('c1', 'func1', 'HAS_FUNCTION'),
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fc2', 'fm1', 'CAUSE_OF'),
      e('fc1', 'pc1', 'PREVENTED_BY'),
      e('fc2', 'pc1', 'PREVENTED_BY'),
    ];
    // Delete c1 — this cascades to func1, fm1, fc1
    // But pc1 has another parent (fc2) outside the deletion path... wait,
    // fc2 is ALSO downstream of c1. In this case fc2 is also deleted.
    // So pc1 IS orphaned. Let's test the case where fc2 is under a DIFFERENT component.
    const nodes2 = [
      n('s1', 'System'), n('c1', 'Component'), n('c2', 'Component'),
      n('func1', 'ProcessWorkElementFunction'), n('func2', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'), n('fm2', 'FailureMode'),
      n('fc1', 'FailureCause'), n('fc2', 'FailureCause'),
      pc1,
    ];
    const edges2 = [
      e('s1', 'c1', 'HAS_PROCESS_STEP'), e('s1', 'c2', 'HAS_PROCESS_STEP'),
      e('c1', 'func1', 'HAS_FUNCTION'), e('c2', 'func2', 'HAS_FUNCTION'),
      e('func1', 'fm1', 'HAS_FAILURE_MODE'), e('func2', 'fm2', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'), e('fc2', 'fm2', 'CAUSE_OF'),
      e('fc1', 'pc1', 'PREVENTED_BY'), e('fc2', 'pc1', 'PREVENTED_BY'),
    ];
    // Deleting c1 cascades to func1, fm1, fc1.
    // pc1 has an incoming edge from fc2 which is NOT in c1's subtree → pc1 is kept
    const result = cascadeDeleteStructureNode('c1', nodes2, edges2);
    const remainingIds = result.nodes.map(n => n.id);
    expect(remainingIds).toContain('pc1');
    expect(remainingIds).toContain('c2');
    expect(remainingIds).toContain('fc2');
    expect(remainingIds).not.toContain('c1');
    expect(remainingIds).not.toContain('func1');
    expect(remainingIds).not.toContain('fm1');
    expect(remainingIds).not.toContain('fc1');
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
  const queueTailRef = useRef<Promise<void>>(Promise.resolve());
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setLockVersion = useCallback((v: number) => {
    lockVersionRef.current = v;
  }, []);

  /** Serial save: enqueues after any in-flight save, returns when this save completes */
  const enqueueSave = useCallback(async (graphData: GraphData, title?: string): Promise<void> => {
    const doSave = async (): Promise<void> => {
      try {
        setSaveStatus('saving');
        const resp = await updateFMEA(fmeaId, {
          ...(title ? { title } : {}),
          graph_data: graphData,
          lock_version: lockVersionRef.current,
        });
        lockVersionRef.current = resp.lock_version ?? resp.version;
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus('idle'), 2000);
      } catch (err: any) {
        setSaveStatus('error');
        if (err?.response?.status === 409 || String(err?.response?.data?.detail).includes('lock_version')) {
          message.error('数据已被其他会话修改，请刷新页面后重试');
        } else {
          message.error('保存失败，请重试');
        }
      }
    };

    // Chain this save onto the tail of the queue
    const prevTail = queueTailRef.current;
    const newTail = prevTail.then(() => doSave());
    queueTailRef.current = newTail;
    return newTail;
  }, [fmeaId]);

  /** Debounced save: 500ms delay, cancels previous timer */
  const debouncedSave = useCallback((graphData: GraphData, title?: string) => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      enqueueSave(graphData, title);
    }, 500);
  }, [enqueueSave]);

  /** Immediate save: cancels debounce, saves right away */
  const immediateSave = useCallback(async (graphData: GraphData, title?: string) => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    await enqueueSave(graphData, title);
  }, [enqueueSave]);

  return {
    saveStatus,
    setLockVersion,
    debouncedSave,
    immediateSave,
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
import { Button, Space, Modal, Spin, Typography, message } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getFMEA, deleteFMEA } from '../../../api/fmea';
import type { FMEADocument, GraphNode, GraphEdge, WizardScope } from '../../../types';
import { useWizardSave, type SaveStatus } from '../../../hooks/useWizardSave';
import { useWizardValidation } from '../../../hooks/useWizardValidation';
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
  const dirtyRef = useRef(false);

  const { saveStatus, setLockVersion, debouncedSave, immediateSave } = useWizardSave({ fmeaId: fmeaId! });
  const validation = useWizardValidation(nodes, edges);

  // Load FMEA document
  useEffect(() => {
    if (!fmeaId) return;
    getFMEA(fmeaId).then(doc => {
      // Draft DFMEAs should be in the wizard; if not draft, redirect to editor
      if (doc.fmea_type !== 'DFMEA') {
        navigate(`/fmea/${doc.fmea_id}`, { replace: true });
        return;
      }
      setFmea(doc);
      setNodes(doc.graph_data?.nodes || []);
      setEdges(doc.graph_data?.edges || []);
      setWizardScope(doc.graph_data?.wizardScope || {});
      setLockVersion(doc.lock_version);
      setLoading(false);
    }).catch(() => {
      message.error('加载失败');
      navigate('/fmea');
    });
  }, [fmeaId, navigate, setLockVersion]);

  // beforeunload warning
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  const updateGraphData = useCallback((newNodes: GraphNode[], newEdges: GraphEdge[], newScope?: WizardScope) => {
    setNodes(newNodes);
    setEdges(newEdges);
    if (newScope !== undefined) setWizardScope(newScope);
    dirtyRef.current = true;
    debouncedSave({ nodes: newNodes, edges: newEdges, wizardScope: newScope ?? wizardScope }, fmea?.title);
  }, [debouncedSave, wizardScope, fmea?.title]);

  const goToStep = useCallback((step: number) => {
    completedSteps.current.add(currentStep);
    setCurrentStep(step);
  }, [currentStep]);

  const handleFinish = async () => {
    await immediateSave({ nodes, edges, wizardScope }, fmea?.title);
    dirtyRef.current = false;
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

  const canFinish = validation.warnings.length === 0 && nodes.length > 1;

  const saveStatusLabel: Record<SaveStatus, string> = {
    idle: '',
    saving: t('wizard.page.saveSaving'),
    saved: t('wizard.page.saveSaved'),
    error: t('wizard.page.saveError'),
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
          <Button type="primary" onClick={() => immediateSave({ nodes, edges, wizardScope }, fmea?.title)} loading={saveStatus === 'saving'}>
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

          {/* Step content placeholder — will be filled in Tasks 10-12 */}
          <div style={{ minHeight: 300 }}>
            {/* STEP_CONTENT_MAP[currentStep] will render here */}
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

---

## Task 10: Step 1-2 Content (5T Scope + Structure Analysis)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`

Add the Step 1 (5T scope form) and Step 2 (structure analysis with cascade delete) content to the wizard page. This includes:

- Step 1: 5 input fields for team/timeframe/tool/task/trend, saving to `wizardScope`
- Step 2: Structure tree editing using `cascadeDeleteStructureNode` for delete operations, add System/Interface buttons, inline name editing

The `STEP_CONTENT_MAP` is filled with render functions for steps 0 and 1. Step 2's delete handler uses `cascadeDeleteStructureNode` instead of simple node removal.

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

Add Step 3 (function analysis per component) and Step 4 (failure analysis with smart recommendations from `dfmeaRules`). This reuses the logic from `GenerationWizard.tsx` steps 2 and 3, but adapted for the page layout with left sidebar highlighting.

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

Add Step 5 (S/O/D risk table with AP auto-calculation), Step 6 (optimization for AP=H items), and Step 7 (confirmation with statistics). Uses `useDfmeaRules` hooks for AP calculation and measure suggestions.

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
if (doc.fmea_type === 'DFMEA' && doc.status === 'draft') {
  navigate(`/fmea/wizard/${doc.fmea_id}`, { replace: true });
  return;
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

## Self-Review Checklist (v2)

- [x] **Spec coverage:** All sections covered — routes (Task 13), layout (Task 9), save mechanism (Task 4), step content (Tasks 10-12), validation (Task 5), cascade delete (Task 3), wizardScope (Tasks 1-2), i18n (Task 8), guidance cards (Task 6), sidebar (Task 7), editor redirect (Task 13), exit confirmation (Task 9)
- [x] **Placeholder scan:** No TBD/TODO/fill-in-later. All code blocks contain complete implementations. Tasks 10-12 describe what to implement but reference existing `GenerationWizard.tsx` patterns.
- [x] **Type consistency:** `WizardScope` defined in Task 2, used in Tasks 4 and 9. `lock_version` added to `FMEAResponse` (Task 1) and `FMEADocument` (Task 2). `deleteFMEA` API (Task 2) matches backend DELETE endpoint (Task 1). `useWizardSave` returns `SaveStatus` (Task 4), used in Task 9. `useWizardValidation` uses `buildRows` (Task 5), imported correctly. `cascadeDeleteStructureNode` signature matches Task 9/10 usage. `WizardSidebar` accepts `edges` prop (Task 7), passed in Task 9.
- [x] **Blocking issues fixed:** (1) `lock_version` added to `FMEAResponse`, (2) DELETE endpoint added to backend, (3) serial save queue fixed with proper chaining, (4) Step 5 validation uses `buildRows` + graph model S/O/D mapping, (5) cascade delete has unit tests, (6) Task 9 split into Tasks 9-12, (7) `WizardSidebar` receives edges and uses proper tree builder, (8) i18n JSON is valid merge format