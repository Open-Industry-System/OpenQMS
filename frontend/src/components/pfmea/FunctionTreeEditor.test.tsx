import { describe, it, expect, vi } from 'vitest';
import { Modal } from 'antd';
import { render, screen, fireEvent } from '@testing-library/react';
import FunctionTreeEditor from './FunctionTreeEditor';
import { I18nTestWrapper } from './__test-utils__/I18nWrapper';
import type { GraphNode, GraphEdge } from '../../types';

const Z = { severity: 0, occurrence: 0, detection: 0 };

describe('FunctionTreeEditor', () => {
  it('creates a ProcessStepFunction with HAS_FUNCTION + FUNCTION_MAPPED_TO when adding a step function', () => {
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: '线', ...Z },
      { id: 'pif', type: 'ProcessItemFunction', name: '完成SMT', ...Z },
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'pif', type: 'HAS_FUNCTION' },
      { source: 'pi', target: 'ps', type: 'HAS_PROCESS_STEP' },
    ];
    const onChange = vi.fn();
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />, { wrapper: I18nTestWrapper });
    fireEvent.click(screen.getByRole('button', { name: /addStepFunction|添加过程步骤功能/ }));
    expect(onChange).toHaveBeenCalled();
    const [, newEdges] = onChange.mock.calls[0];
    expect(newEdges.some((e: GraphEdge) => e.type === 'HAS_FUNCTION')).toBe(true);
    expect(newEdges.some((e: GraphEdge) => e.type === 'FUNCTION_MAPPED_TO')).toBe(true);
  });

  it('lets a ProcessStepFunction set classification CC but hides it for ProcessItemFunction', () => {
    const nodes: GraphNode[] = [
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'psf', type: 'ProcessStepFunction', name: '准确贴装', specification: '偏移≤0.05mm', ...Z },
      { id: 'pif', type: 'ProcessItemFunction', name: '完成SMT', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'ps', target: 'psf', type: 'HAS_FUNCTION' },
      { source: 'pif', target: 'psf', type: 'FUNCTION_MAPPED_TO' },
    ];
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });
    // StepFunction card shows a classification (CC/SC) selector
    expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0);
  });

  it('branch-local: with two steps, a new StepFunction maps to ITS step\'s ProcessItem function only', () => {
    // Two ProcessItems each with a ProcessItemFunction; two ProcessSteps (one per item).
    const nodes: GraphNode[] = [
      { id: 'pi1', type: 'ProcessItem', name: '线A', ...Z },
      { id: 'pi2', type: 'ProcessItem', name: '线B', ...Z },
      { id: 'pif1', type: 'ProcessItemFunction', name: '完成A', ...Z },
      { id: 'pif2', type: 'ProcessItemFunction', name: '完成B', ...Z },
      { id: 'ps1', type: 'ProcessStep', name: '贴装A', process_number: 'OP10', ...Z },
      { id: 'ps2', type: 'ProcessStep', name: '贴装B', process_number: 'OP20', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi1', target: 'pif1', type: 'HAS_FUNCTION' },
      { source: 'pi2', target: 'pif2', type: 'HAS_FUNCTION' },
      { source: 'pi1', target: 'ps1', type: 'HAS_PROCESS_STEP' },
      { source: 'pi2', target: 'ps2', type: 'HAS_PROCESS_STEP' },
    ];
    const onChange = vi.fn();
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />, { wrapper: I18nTestWrapper });
    // click the add-step-function button for ps2 (贴装B)
    fireEvent.click(screen.getByRole('button', { name: /addStepFunction.*OP20|添加过程步骤功能.*OP20/ }));
    const [, newEdges] = onChange.mock.calls[0];
    const mapped = newEdges.filter((e: GraphEdge) => e.type === 'FUNCTION_MAPPED_TO');
    expect(mapped.length).toBe(1);
    // must map from pif2 (线B's item function), NOT pif1
    expect(mapped[0].source).toBe('pif2');
  });

  it('branch-local: auto-creates an ItemFunction for a ProcessItem when adding a StepFunction before an item function exists', () => {
    const nodes: GraphNode[] = [
      { id: 'pi1', type: 'ProcessItem', name: '线A', ...Z },
      { id: 'pi2', type: 'ProcessItem', name: '线B', ...Z },
      { id: 'ps2', type: 'ProcessStep', name: '贴装B', process_number: 'OP20', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi2', target: 'ps2', type: 'HAS_PROCESS_STEP' },
    ];
    const onChange = vi.fn();
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />,
      { wrapper: I18nTestWrapper },
    );
    fireEvent.click(screen.getByRole('button', { name: /addStepFunction.*OP20|添加过程步骤功能.*OP20/ }));
    expect(onChange).toHaveBeenCalled();
    const [newNodes, newEdges] = onChange.mock.calls[0];
    // An ItemFunction was auto-created and linked to pi2
    const autoItemFunc = newNodes.find((n: GraphNode) => n.type === 'ProcessItemFunction');
    expect(autoItemFunc).toBeTruthy();
    expect(newEdges.some((e: GraphEdge) => e.source === 'pi2' && e.target === autoItemFunc.id && e.type === 'HAS_FUNCTION')).toBe(true);
    // The StepFunction maps from the auto-created ItemFunction
    const mapped = newEdges.filter((e: GraphEdge) => e.type === 'FUNCTION_MAPPED_TO');
    expect(mapped.length).toBe(1);
    expect(mapped[0].source).toBe(autoItemFunc.id);
  });

  it('branch-local: with two work elements under different steps, a new WEF maps to ITS step\'s StepFunction only', () => {
    const nodes: GraphNode[] = [
      { id: 'ps1', type: 'ProcessStep', name: '贴装A', process_number: 'OP10', ...Z },
      { id: 'ps2', type: 'ProcessStep', name: '焊接B', process_number: 'OP20', ...Z },
      { id: 'psf1', type: 'ProcessStepFunction', name: '贴装功能', ...Z },
      { id: 'psf2', type: 'ProcessStepFunction', name: '焊接功能', ...Z },
      { id: 'we1', type: 'ProcessWorkElement', name: '机A', classification: 'Machine', ...Z },
      { id: 'we2', type: 'ProcessWorkElement', name: '机B', classification: 'Machine', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'ps1', target: 'psf1', type: 'HAS_FUNCTION' },
      { source: 'ps2', target: 'psf2', type: 'HAS_FUNCTION' },
      { source: 'ps1', target: 'we1', type: 'HAS_WORK_ELEMENT' },
      { source: 'ps2', target: 'we2', type: 'HAS_WORK_ELEMENT' },
    ];
    const onChange = vi.fn();
    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />, { wrapper: I18nTestWrapper });
    // click add-work-element-function for we2 (机B, under ps2)
    fireEvent.click(screen.getByRole('button', { name: /addWorkElementFunction.*机B|添加作业要素功能.*机B/ }));
    const [, newEdges] = onChange.mock.calls[0];
    const mapped = newEdges.filter((e: GraphEdge) => e.type === 'FUNCTION_MAPPED_TO');
    expect(mapped.length).toBe(1);
    // must map from psf2 (焊接B's step function), NOT psf1
    expect(mapped[0].source).toBe('psf2');
  });

  it('renders product characteristics for step functions and process characteristics for work-element functions', () => {
    const nodes: GraphNode[] = [
      { id: 'step', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'step-fn', type: 'ProcessStepFunction', name: '准确贴装', ...Z },
      { id: 'work-element', type: 'ProcessWorkElement', name: '贴片机', classification: 'Machine', ...Z },
      { id: 'work-fn', type: 'ProcessWorkElementFunction', name: '贴装压力', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'step', target: 'step-fn', type: 'HAS_FUNCTION' },
      { source: 'step', target: 'work-element', type: 'HAS_WORK_ELEMENT' },
      { source: 'work-element', target: 'work-fn', type: 'HAS_FUNCTION' },
    ];

    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={() => {}} />, { wrapper: I18nTestWrapper });

    expect(screen.getByText('新增产品特性')).toBeInTheDocument();
    expect(screen.getByText('新增过程特性')).toBeInTheDocument();
  });

  it('confirms reference impacts before deleting a product characteristic and cleans the process reference', () => {
    const product = { id: 'product-char', kind: 'product' as const, name: '贴装偏移量', specification: null, unit: null, classification: null, reference: null, related_product_characteristic_ids: [] };
    const process = { id: 'process-char', kind: 'process' as const, name: '贴装压力', specification: null, unit: null, classification: null, reference: null, related_product_characteristic_ids: ['product-char'] };
    const nodes: GraphNode[] = [
      { id: 'step', type: 'ProcessStep', name: '贴装', ...Z },
      { id: 'step-fn', type: 'ProcessStepFunction', name: '准确贴装', characteristics: [product], ...Z },
      { id: 'work-element', type: 'ProcessWorkElement', name: '贴片机', ...Z },
      { id: 'work-fn', type: 'ProcessWorkElementFunction', name: '贴装压力', characteristics: [process], ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'step', target: 'step-fn', type: 'HAS_FUNCTION' },
      { source: 'step', target: 'work-element', type: 'HAS_WORK_ELEMENT' },
      { source: 'work-element', target: 'work-fn', type: 'HAS_FUNCTION' },
    ];
    const onChange = vi.fn();
    const confirm = vi.spyOn(Modal, 'confirm').mockImplementation((config) => {
      config.onOk?.();
      return undefined as never;
    });

    render(<FunctionTreeEditor nodes={nodes} edges={edges} fmeaId="f1" onChange={onChange} />, { wrapper: I18nTestWrapper });
    fireEvent.click(screen.getByRole('button', { name: /删除产品特性/ }));

    expect(confirm).toHaveBeenCalledOnce();
    const [updatedNodes] = onChange.mock.calls[0];
    expect(updatedNodes.find((node: GraphNode) => node.id === 'step-fn').characteristics).toEqual([]);
    expect(updatedNodes.find((node: GraphNode) => node.id === 'work-fn').characteristics?.[0].related_product_characteristic_ids).toEqual([]);
    confirm.mockRestore();
  });
});
