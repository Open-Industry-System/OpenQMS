import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import PFMEAWizardSidebar from './PFMEAWizardSidebar';
import zhPFMEA from '../../locales/zh-CN/pfmea.json';
import type { GraphNode, GraphEdge } from '../../types';

const i18nTest = i18n.createInstance();
i18nTest
  .use(initReactI18next)
  .init({
    lng: 'zh-CN',
    fallbackLng: 'zh-CN',
    interpolation: { escapeValue: false },
    resources: {
      'zh-CN': { pfmea: zhPFMEA },
    },
  });

function I18nTestWrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18nTest}>{children}</I18nextProvider>;
}

const Z = { severity: 0, occurrence: 0, detection: 0 };

describe('PFMEAWizardSidebar', () => {
  it('renders 7 step labels from pfmea namespace', () => {
    render(
      <PFMEAWizardSidebar
        currentStep={0} onStepClick={() => {}} completedSteps={new Set()}
        maxReachableStep={0} warnings={[]} structureNodes={[]} edges={[]} />,
      { wrapper: I18nTestWrapper },
    );
    expect(screen.getAllByText(/5T范围|5T Scope|结构分析|Structure Analysis/i).length).toBeGreaterThan(0);
  });

  it('renders ProcessItem/ProcessStep/WorkElement in structure tree', () => {
    const nodes: GraphNode[] = [
      { id: 'pi', type: 'ProcessItem', name: 'SMT线', ...Z },
      { id: 'ps', type: 'ProcessStep', name: '贴装', process_number: 'OP10', ...Z },
      { id: 'we', type: 'ProcessWorkElement', name: '贴片机', classification: 'Machine', ...Z },
    ];
    const edges: GraphEdge[] = [
      { source: 'pi', target: 'ps', type: 'HAS_PROCESS_STEP' },
      { source: 'ps', target: 'we', type: 'HAS_WORK_ELEMENT' },
    ];
    render(
      <PFMEAWizardSidebar currentStep={1} onStepClick={() => {}} completedSteps={new Set([0,1])}
        maxReachableStep={2} warnings={[]} structureNodes={nodes} edges={edges} />,
      { wrapper: I18nTestWrapper },
    );
    expect(screen.getByText('SMT线')).toBeInTheDocument();
    expect(screen.getByText(/贴装/)).toBeInTheDocument();
  });
});
