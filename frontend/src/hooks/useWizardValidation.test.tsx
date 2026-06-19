import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWizardValidation } from './useWizardValidation';
import type { GraphNode, GraphEdge } from '../types';

const n = (id: string, type: string, props: Partial<GraphNode> = {}): GraphNode => ({
  id, type, name: id, severity: 0, occurrence: 0, detection: 0, ...props,
});
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

describe('useWizardValidation — Step 5 cause-less vs unrated', () => {
  it('reports missing cause (not unrated S/O/D) for a cause-less row', () => {
    // func1 → HAS_FAILURE_MODE → fm1, no FailureCause
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
    ];
    const edges = [e('func1', 'fm1', 'HAS_FAILURE_MODE')];
    const { result } = renderHook(() => useWizardValidation(nodes, edges));
    expect(result.current.step5MissingCause).toBe(true);
    expect(result.current.step5Unrated).toBe(false);
    expect(result.current.step5Complete).toBe(false);
    expect(result.current.warnings).toContain(4);
  });

  it('reports unrated S/O/D when a cause exists but a rating is still zero', () => {
    // func1 → fm1 ; fc1 → CAUSE_OF → fm1 ; fm1 → EFFECT_OF → fe1 (severity 0)
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 0 }),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fm1', 'fe1', 'EFFECT_OF'),
    ];
    const { result } = renderHook(() => useWizardValidation(nodes, edges));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(true);
    expect(result.current.step5Complete).toBe(false);
  });

  it('is complete when every caused row has S/O/D > 0', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 7 }),
      n('dc1', 'DetectionControl', { detection: 3 }),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fc1', 'dc1', 'DETECTED_BY'),
    ];
    const { result } = renderHook(() => useWizardValidation(nodes, edges));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(false);
    expect(result.current.step5Complete).toBe(true);
    expect(result.current.warnings).not.toContain(4);
  });
});
