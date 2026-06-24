import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePfmeaWizardValidation } from './usePfmeaWizardValidation';
import type { GraphNode, GraphEdge } from '../types';

const Z = { severity: 0, occurrence: 0, detection: 0 };

describe('usePfmeaWizardValidation', () => {
  it('step1 incomplete when a ProcessStep lacks process_number', () => {
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
      { id: 'ps', type: 'ProcessStep', name: '贴装', ...Z }, // no process_number
      { id: 'we', type: 'ProcessWorkElement', name: '机', classification: 'Machine', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'ps', type: 'HAS_PROCESS_STEP' },
      { source: 'ps', target: 'we', type: 'HAS_WORK_ELEMENT' },
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step1Complete).toBe(false);
    expect(result.current.warnings).toContain(1);
  });

  it('step1 incomplete when a WorkElement lacks classification', () => {
    const nodes: GraphNode[] = [
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'we', type: 'ProcessWorkElement', name: '机', ...Z }, // no classification
    ];
    const edges: GraphEdge[] = [{ source: 'ps', target: 'we', type: 'HAS_WORK_ELEMENT' }];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step1Complete).toBe(false);
  });

  it('step1 complete with process_number + 4M classification', () => {
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'we', type: 'ProcessWorkElement', name: '机', classification: 'Machine', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'ps', type: 'HAS_PROCESS_STEP' },
      { source: 'ps', target: 'we', type: 'HAS_WORK_ELEMENT' },
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step1Complete).toBe(true);
  });

  it('step4 incomplete when severity_plant/customer/user not all >0', () => {
    const nodes: GraphNode[] = [
      { id: 'psf', type: 'ProcessStepFunction', name: 'f', ...Z },
      { id: 'fm', type: 'FailureMode', name: 'm', ...Z },
      { id: 'fe', type: 'FailureEffect', name: 'e', ...Z, severity: 8, severity_plant: 4, severity_customer: 8, severity_user: 0 },
      { id: 'fc', type: 'FailureCause', name: 'c', ...Z, occurrence: 4 },
      { id: 'pc', type: 'PreventionControl', name: 'p', ...Z },
      { id: 'dc', type: 'DetectionControl', name: 'd', ...Z, detection: 3 },
    ];
    const edges: GraphEdge[] = [
      { source: 'psf', target: 'fm', type: 'HAS_FAILURE_MODE' },
      { source: 'fm', target: 'fe', type: 'EFFECT_OF' },
      { source: 'fc', target: 'fm', type: 'CAUSE_OF' },
      { source: 'fc', target: 'pc', type: 'PREVENTED_BY' },
      { source: 'fc', target: 'dc', type: 'DETECTED_BY' },
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step4Complete).toBe(false);
    expect(result.current.warnings).toContain(4);
  });

  it('step4 complete when all three severities + O/D + controls present', () => {
    const nodes: GraphNode[] = [
      { id: 'psf', type: 'ProcessStepFunction', name: 'f', ...Z },
      { id: 'fm', type: 'FailureMode', name: 'm', ...Z },
      { id: 'fe', type: 'FailureEffect', name: 'e', ...Z, severity: 8, severity_plant: 4, severity_customer: 8, severity_user: 8 },
      { id: 'fc', type: 'FailureCause', name: 'c', ...Z, occurrence: 4 },
      { id: 'pc', type: 'PreventionControl', name: 'p', ...Z },
      { id: 'dc', type: 'DetectionControl', name: 'd', ...Z, detection: 3 },
    ];
    const edges: GraphEdge[] = [
      { source: 'psf', target: 'fm', type: 'HAS_FAILURE_MODE' },
      { source: 'fm', target: 'fe', type: 'EFFECT_OF' },
      { source: 'fc', target: 'fm', type: 'CAUSE_OF' },
      { source: 'fc', target: 'pc', type: 'PREVENTED_BY' },
      { source: 'fc', target: 'dc', type: 'DETECTED_BY' },
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step4Complete).toBe(true);
  });

  it('step2 fails when a WEF maps to a sibling step\'s StepFunction (wrong branch)', () => {
    // Two steps each with a StepFunction; one WEF under ps1 but mapped from psf2 (wrong branch).
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
      { id: 'pif', type: 'ProcessItemFunction', name: '完成', ...Z },
      { id: 'ps1', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'ps2', type: 'ProcessStep', name: '焊接', process_number: 'OP20', ...Z },
      { id: 'psf1', type: 'ProcessStepFunction', name: '贴装功能', ...Z },
      { id: 'psf2', type: 'ProcessStepFunction', name: '焊接功能', ...Z },
      { id: 'we1', type: 'ProcessWorkElement', name: '机', classification: 'Machine', ...Z },
      { id: 'wef1', type: 'ProcessWorkElementFunction', name: '机功能', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'pif', type: 'HAS_FUNCTION' },
      { source: 'pi', target: 'ps1', type: 'HAS_PROCESS_STEP' },
      { source: 'pi', target: 'ps2', type: 'HAS_PROCESS_STEP' },
      { source: 'ps1', target: 'psf1', type: 'HAS_FUNCTION' },
      { source: 'ps2', target: 'psf2', type: 'HAS_FUNCTION' },
      { source: 'pif', target: 'psf1', type: 'FUNCTION_MAPPED_TO' },
      { source: 'pif', target: 'psf2', type: 'FUNCTION_MAPPED_TO' },
      { source: 'ps1', target: 'we1', type: 'HAS_WORK_ELEMENT' },
      { source: 'we1', target: 'wef1', type: 'HAS_FUNCTION' },
      { source: 'psf2', target: 'wef1', type: 'FUNCTION_MAPPED_TO' }, // WRONG: we1 is under ps1, should map from psf1
    ];
    const { result } = renderHook(() => usePfmeaWizardValidation(nodes, edges));
    expect(result.current.step2Complete).toBe(false);
    expect(result.current.warnings).toContain(2);
  });
});
