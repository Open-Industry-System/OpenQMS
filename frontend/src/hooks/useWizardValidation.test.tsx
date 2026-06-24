import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWizardValidation } from './useWizardValidation';
import type { GraphNode, GraphEdge } from '../types';

const n = (id: string, type: string, props: Partial<GraphNode> = {}): GraphNode => ({
  id, type, name: id, severity: 0, occurrence: 0, detection: 0, ...props,
});
const e = (source: string, target: string, type: string): GraphEdge => ({ source, target, type });

const MAP: Record<string, string> = { "接口矩阵": "Interface", "P图/参数图": "DesignParameter" };
const NO_TOOLS: string[] = [];
const NO_MAP: Record<string, string> = {};

describe('useWizardValidation — Step 5 cause-less vs unrated', () => {
  it('reports missing cause (not unrated S/O/D) for a cause-less row', () => {
    const nodes = [n('func1', 'ProcessWorkElementFunction'), n('fm1', 'FailureMode')];
    const edges = [e('func1', 'fm1', 'HAS_FAILURE_MODE')];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, NO_TOOLS, NO_MAP));
    expect(result.current.step5MissingCause).toBe(true);
    expect(result.current.step5Unrated).toBe(false);
    expect(result.current.step5Complete).toBe(false);
    expect(result.current.warnings).toContain(4);
  });

  it('reports unrated S/O/D when a cause exists but a rating is still zero', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 0 }),
    ];
    const edges = [e('func1', 'fm1', 'HAS_FAILURE_MODE'), e('fc1', 'fm1', 'CAUSE_OF'), e('fm1', 'fe1', 'EFFECT_OF')];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, NO_TOOLS, NO_MAP));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(true);
    expect(result.current.step5Complete).toBe(false);
  });

  it('is complete when every caused row has S/O/D > 0 and PC/DC filled', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 7 }),
      n('pc1', 'PreventionControl'),
      n('dc1', 'DetectionControl', { detection: 3 }),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fc1', 'pc1', 'PREVENTED_BY'),
      e('fc1', 'dc1', 'DETECTED_BY'),
    ];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, NO_TOOLS, NO_MAP));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(false);
    expect(result.current.step5Complete).toBe(true);
    expect(result.current.warnings).not.toContain(4);
  });
});

describe('useWizardValidation — multi-effect S=max', () => {
  it('rates a row complete when the max effect severity > 0 even if another effect is 0', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 0 }),
      n('fe2', 'FailureEffect', { severity: 7 }),
      n('pc1', 'PreventionControl'),
      n('dc1', 'DetectionControl', { detection: 3 }),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fm1', 'fe2', 'EFFECT_OF'),
      e('fc1', 'pc1', 'PREVENTED_BY'),
      e('fc1', 'dc1', 'DETECTED_BY'),
    ];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, NO_TOOLS, NO_MAP));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(false);
    expect(result.current.step5Complete).toBe(true);
  });

  it('rates a row unrated when every effect severity is 0', () => {
    const nodes = [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode'),
      n('fc1', 'FailureCause', { occurrence: 5 }),
      n('fe1', 'FailureEffect', { severity: 0 }),
      n('fe2', 'FailureEffect', { severity: 0 }),
      n('dc1', 'DetectionControl', { detection: 3 }),
    ];
    const edges = [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fm1', 'fe2', 'EFFECT_OF'),
      e('fc1', 'dc1', 'DETECTED_BY'),
    ];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, NO_TOOLS, NO_MAP));
    expect(result.current.step5MissingCause).toBe(false);
    expect(result.current.step5Unrated).toBe(true);
    expect(result.current.step5Complete).toBe(false);
  });
});

describe('useWizardValidation — structure gaps from selected tools', () => {
  it('reports a structure gap when a mapped tool has no HAS_PARAMETER-attached node', () => {
    const nodes = [n('comp1', 'Component')];
    const { result } = renderHook(() => useWizardValidation(nodes, [], ['接口矩阵'], MAP));
    expect(result.current.structureGaps).toEqual([{ tool: '接口矩阵', nodeType: 'Interface' }]);
  });

  it('reports no gap when the required node is attached via HAS_PARAMETER', () => {
    const nodes = [n('comp1', 'Component'), n('iface1', 'Interface')];
    const edges = [e('comp1', 'iface1', 'HAS_PARAMETER')];
    const { result } = renderHook(() => useWizardValidation(nodes, edges, ['接口矩阵'], MAP));
    expect(result.current.structureGaps).toEqual([]);
  });

  it('reports no gap when no structure-class tools are selected', () => {
    const nodes = [n('comp1', 'Component')];
    const { result } = renderHook(() => useWizardValidation(nodes, [], ['功能分析'], MAP));
    expect(result.current.structureGaps).toEqual([]);
  });

  it('does NOT put structure gaps into warnings (gaps stay separate, never block)', () => {
    const nodes = [n('sys1', 'System')];
    const { result } = renderHook(() => useWizardValidation(nodes, [], ['接口矩阵'], MAP));
    expect(result.current.structureGaps.length).toBe(1);
    // structureGaps is a separate field; gaps must never leak into warnings.
    // canFinish in DFMEAWizardPage = warnings.length===0 && step3/4/5 complete,
    // so as long as gaps aren't in warnings, they cannot block finish.
    expect(result.current.warnings).toEqual([]);
  });
});

describe('useWizardValidation — failure-chain name completeness (Step 4)', () => {
  // The wizard creates FM/FE/FC with empty names by default (so the AI
  // SmartSuggestionDropdown doesn't auto-fire on a placeholder). step4Complete
  // must therefore check non-empty NAMES, not just that a HAS_FAILURE_MODE
  // edge exists — otherwise a user can finish a DFMEA with blank failure fields.
  const chain = (fmName: string, feName: string, fcName: string) => ({
    nodes: [
      n('func1', 'ProcessWorkElementFunction'),
      n('fm1', 'FailureMode', { name: fmName }),
      n('fe1', 'FailureEffect', { name: feName, severity: 7 }),
      n('fc1', 'FailureCause', { name: fcName, occurrence: 5 }),
      n('dc1', 'DetectionControl', { name: '检测', detection: 3 }),
    ],
    edges: [
      e('func1', 'fm1', 'HAS_FAILURE_MODE'),
      e('fm1', 'fe1', 'EFFECT_OF'),
      e('fc1', 'fm1', 'CAUSE_OF'),
      e('fc1', 'dc1', 'DETECTED_BY'),
    ],
  });

  it('blocks completion when a FailureMode name is empty', () => {
    const c = chain('', '效应', '原因');
    const { result } = renderHook(() => useWizardValidation(c.nodes, c.edges, NO_TOOLS, NO_MAP));
    expect(result.current.step4Complete).toBe(false);
    expect(result.current.warnings).toContain(3);
  });

  it('blocks completion when a FailureEffect name is empty', () => {
    const c = chain('模式', '', '原因');
    const { result } = renderHook(() => useWizardValidation(c.nodes, c.edges, NO_TOOLS, NO_MAP));
    expect(result.current.step4Complete).toBe(false);
    expect(result.current.warnings).toContain(3);
  });

  it('blocks completion when a FailureCause name is empty', () => {
    const c = chain('模式', '效应', '');
    const { result } = renderHook(() => useWizardValidation(c.nodes, c.edges, NO_TOOLS, NO_MAP));
    expect(result.current.step4Complete).toBe(false);
    expect(result.current.warnings).toContain(3);
  });

  it('completes Step 4 when FM/FE/FC are all named', () => {
    const c = chain('模式', '效应', '原因');
    const { result } = renderHook(() => useWizardValidation(c.nodes, c.edges, NO_TOOLS, NO_MAP));
    expect(result.current.step4Complete).toBe(true);
    expect(result.current.warnings).not.toContain(3);
  });
});
