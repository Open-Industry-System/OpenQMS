import { describe, it, expect } from 'vitest';
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
    expect(result.nodes.map(x => x.id)).toEqual(['s1']);
    expect(result.edges).toHaveLength(0);
  });

  it('deletes a root System and cascades everything', () => {
    // Full chain: s1 → ss1 → c1 → func1 → fm1 → fe1
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
    const result = cascadeDeleteStructureNode('s1', nodes, edges);
    expect(result.nodes).toHaveLength(0);
    expect(result.edges).toHaveLength(0);
  });

  it('keeps shared PreventionControl referenced by cause outside deletion path', () => {
    // Two components, shared pc1:
    // c1 → func1 → fm1 ←(CAUSE_OF)— fc1 → pc1
    // c2 → func2 → fm2 ←(CAUSE_OF)— fc2 → pc1
    // Deleting c1 should cascade to func1, fm1, fc1 but NOT delete pc1 (shared with c2)
    const nodes = [
      n('s1', 'System'), n('c1', 'Component'), n('c2', 'Component'),
      n('func1', 'ProcessWorkElementFunction'), n('func2', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'), n('fm2', 'FailureMode'),
      n('fc1', 'FailureCause'), n('fc2', 'FailureCause'),
      n('pc1', 'PreventionControl', 'Shared PC'),
    ];
    const edges = [
      e('s1', 'c1', 'HAS_PROCESS_STEP'), e('s1', 'c2', 'HAS_PROCESS_STEP'),
      e('c1', 'func1', 'HAS_FUNCTION'), e('c2', 'func2', 'HAS_FUNCTION'),
      e('func1', 'fm1', 'HAS_FAILURE_MODE'), e('func2', 'fm2', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'), e('fc2', 'fm2', 'CAUSE_OF'),
      e('fc1', 'pc1', 'PREVENTED_BY'), e('fc2', 'pc1', 'PREVENTED_BY'),
    ];
    const result = cascadeDeleteStructureNode('c1', nodes, edges);
    const remainingIds = result.nodes.map(x => x.id);
    // pc1 should be kept because fc2 (outside deletion path) also references it
    expect(remainingIds).toContain('pc1');
    expect(remainingIds).toContain('c2');
    expect(remainingIds).toContain('fc2');
    expect(remainingIds).not.toContain('c1');
    expect(remainingIds).not.toContain('func1');
    expect(remainingIds).not.toContain('fm1');
    expect(remainingIds).not.toContain('fc1');
    // The edge from fc1→pc1 should be removed, but fc2→pc1 should remain
    expect(result.edges.some(ed => ed.source === 'fc2' && ed.target === 'pc1')).toBe(true);
    expect(result.edges.some(ed => ed.source === 'fc1' && ed.target === 'pc1')).toBe(false);
  });

  it('discovers FailureCause via CAUSE_OF reverse edge from FailureMode', () => {
    // Simple graph: func1 → fm1 ←(CAUSE_OF)— fc1
    // Deleting func1 should discover fc1 via CAUSE_OF and delete both fm1 and fc1
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'), n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause'),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
    ];
    const result = cascadeDeleteStructureNode('func1', nodes, edges);
    // All should be deleted — fc1 has no external parent
    expect(result.nodes).toHaveLength(0);
    expect(result.edges).toHaveLength(0);
  });

  it('keeps RecommendedAction (OPTIMIZED_BY) shared by two causes when deleting one cause', () => {
    // OPTIMIZED_BY is intentionally NOT in FORWARD_EDGE_TYPES — recommended
    // actions are shared/recommended, not owned by a single cause, so they must
    // NOT cascade-delete with a cause.
    //   fc1 →(OPTIMIZED_BY)→ ra1
    //   fc2 →(OPTIMIZED_BY)→ ra1   (shared)
    //   func1 →(HAS_FAILURE_MODE)→ fm1 ←(CAUSE_OF)— fc1   (so fc1 is reachable)
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'), n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause'), n('fc2', 'FailureCause'),
      n('ra1', 'RecommendedAction', 'Shared recommended action'),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fc1', 'ra1', 'OPTIMIZED_BY'),
      e('fc2', 'ra1', 'OPTIMIZED_BY'),
    ];
    const result = cascadeDeleteStructureNode('fc1', nodes, edges);
    const remainingIds = result.nodes.map(x => x.id);
    // ra1 is kept (shared with fc2, AND OPTIMIZED_BY is excluded from cascade)
    expect(remainingIds).toContain('ra1');
    expect(remainingIds).toContain('fc2');
    expect(remainingIds).not.toContain('fc1');
    // fc1's OPTIMIZED_BY edge is removed; fc2's remains
    expect(result.edges.some(ed => ed.source === 'fc2' && ed.target === 'ra1' && ed.type === 'OPTIMIZED_BY')).toBe(true);
    expect(result.edges.some(ed => ed.source === 'fc1' && ed.target === 'ra1')).toBe(false);
  });

  it('deleting a FailureMode root cascades to its FailureCause and Prevention/Detection controls', () => {
    // Graph: psf → fm → fe
    //             fc →(CAUSE_OF)→ fm
    //             fc → pc (PREVENTED_BY)
    //             fc → dc (DETECTED_BY)
    // Deleting the root FailureMode should delete fm, fe, fc, pc, dc.
    const nodes = [
      n('psf', 'ProcessStepFunction'), n('fm', 'FailureMode'),
      n('fe', 'FailureEffect'), n('fc', 'FailureCause'),
      n('pc', 'PreventionControl'), n('dc', 'DetectionControl'),
    ];
    const edges = [
      e('psf', 'fm', 'HAS_FAILURE_MODE'),
      e('fm', 'fe', 'EFFECT_OF'),
      e('fc', 'fm', 'CAUSE_OF'),
      e('fc', 'pc', 'PREVENTED_BY'),
      e('fc', 'dc', 'DETECTED_BY'),
    ];
    const result = cascadeDeleteStructureNode('fm', nodes, edges);
    expect(result.nodes.map(x => x.id)).toEqual(['psf']);
    expect(result.edges).toHaveLength(0);
  });
});