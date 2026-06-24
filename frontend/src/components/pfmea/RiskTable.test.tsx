import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import RiskTable, { computeSeverity, aggregateSpecialCharacteristic } from './RiskTable';
import type { GraphNode, GraphEdge } from '../../types';
import { I18nTestWrapper } from './__test-utils__/I18nWrapper';

const Z = { severity: 0, occurrence: 0, detection: 0 };

const baseRow = () => {
  const nodes: GraphNode[] = [
    { id: 'psf', type: 'ProcessStepFunction', name: '准确贴装', classification: 'CC', ...Z },
    { id: 'fm', type: 'FailureMode', name: '贴装偏移', ...Z },
    { id: 'fe', type: 'FailureEffect', name: '功能丧失', ...Z, severity_plant: 0, severity_customer: 0, severity_user: 0 },
    { id: 'fc', type: 'FailureCause', name: '吸嘴磨损', ...Z },
    { id: 'pc', type: 'PreventionControl', name: '校准', ...Z },
    { id: 'dc', type: 'DetectionControl', name: 'AOI', ...Z },
  ];
  const edges: GraphEdge[] = [
    { source: 'psf', target: 'fm', type: 'HAS_FAILURE_MODE' },
    { source: 'fm', target: 'fe', type: 'EFFECT_OF' },
    { source: 'fc', target: 'fm', type: 'CAUSE_OF' },
    { source: 'fc', target: 'pc', type: 'PREVENTED_BY' },
    { source: 'fc', target: 'dc', type: 'DETECTED_BY' },
  ];
  return { nodes, edges };
};

describe('RiskTable', () => {
  it('disables O/D inputs while PC/DC name empty', () => {
    const { nodes, edges } = baseRow();
    nodes[4] = { ...nodes[4], name: '' }; // empty PC
    nodes[5] = { ...nodes[5], name: '' }; // empty DC
    render(<RiskTable nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });
    // O and D spin inputs should be disabled
    const disabledNums = screen.getAllByRole('spinbutton').filter((el) => (el as HTMLInputElement).disabled);
    expect(disabledNums.length).toBeGreaterThan(0);
  });

  it('shows CC (read-only) from ProcessStepFunction.classification', () => {
    const { nodes, edges } = baseRow();
    render(<RiskTable nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });
    expect(screen.getByText('CC')).toBeInTheDocument();
  });

  it('shows SC list when no CC and WEFs have SC', () => {
    const { nodes, edges } = baseRow();
    nodes[0] = { ...nodes[0], classification: '' }; // step func no CC
    nodes.push({ id: 'wef', type: 'ProcessWorkElementFunction', name: '贴装压力', classification: 'SC', ...Z } as GraphNode);
    edges.push({ source: 'psf', target: 'wef', type: 'FUNCTION_MAPPED_TO' });
    render(<RiskTable nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });
    expect(screen.getByText(/SC/)).toBeInTheDocument();
  });

  // --- stable pure-function tests (recommended over fragile dialog interaction) ---
  describe('computeSeverity', () => {
    it('returns the max of the three sub-fields', () => {
      expect(computeSeverity(4, 8, 8)).toBe(8);
      expect(computeSeverity(0, 0, 0)).toBe(0);
      expect(computeSeverity(9, 3, 1)).toBe(9);
    });
  });

  describe('aggregateSpecialCharacteristic', () => {
    const Z2 = { severity: 0, occurrence: 0, detection: 0 };
    it('CC wins over SC', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: 'CC', ...Z2 } as GraphNode;
      const wefs = [{ id: 'wef', type: 'ProcessWorkElementFunction', name: 'n', classification: 'SC', ...Z2 } as GraphNode];
      const edges: GraphEdge[] = [{ source: 'psf', target: 'wef', type: 'FUNCTION_MAPPED_TO' }];
      expect(aggregateSpecialCharacteristic(stepFunc, wefs, edges).tag).toBe('CC');
    });
    it('lists SC WEF names when <=2 and no CC', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: '', ...Z2 } as GraphNode;
      const wefs = [
        { id: 'wef1', type: 'ProcessWorkElementFunction', name: '压力', classification: 'SC', ...Z2 } as GraphNode,
        { id: 'wef2', type: 'ProcessWorkElementFunction', name: '温度', classification: 'SC', ...Z2 } as GraphNode,
      ];
      const edges: GraphEdge[] = [
        { source: 'psf', target: 'wef1', type: 'FUNCTION_MAPPED_TO' },
        { source: 'psf', target: 'wef2', type: 'FUNCTION_MAPPED_TO' },
      ];
      const r = aggregateSpecialCharacteristic(stepFunc, wefs, edges);
      expect(r.tag).toBe('SC');
      expect(r.label).toBe('SC(压力/温度)');
    });
    it('collapses to SC×N when >2', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: '', ...Z2 } as GraphNode;
      const wefs = [1, 2, 3].map((i) => ({ id: `wef${i}`, type: 'ProcessWorkElementFunction', name: `n${i}`, classification: 'SC', ...Z2 } as GraphNode));
      const edges: GraphEdge[] = wefs.map((w) => ({ source: 'psf', target: w.id, type: 'FUNCTION_MAPPED_TO' }));
      expect(aggregateSpecialCharacteristic(stepFunc, wefs, edges).label).toBe('SC×3');
    });
    it('returns - when none', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: '', ...Z2 } as GraphNode;
      expect(aggregateSpecialCharacteristic(stepFunc, [], []).label).toBe('-');
    });
    it('only counts WEFs linked to THIS step function (branch-local)', () => {
      const stepFunc = { id: 'psf', type: 'ProcessStepFunction', name: 'f', classification: '', ...Z2 } as GraphNode;
      const wefs = [{ id: 'wef', type: 'ProcessWorkElementFunction', name: '压力', classification: 'SC', ...Z2 } as GraphNode];
      const edges: GraphEdge[] = [{ source: 'OTHER', target: 'wef', type: 'FUNCTION_MAPPED_TO' }]; // linked to a different step func
      expect(aggregateSpecialCharacteristic(stepFunc, wefs, edges).label).toBe('-');
    });
  });
});
