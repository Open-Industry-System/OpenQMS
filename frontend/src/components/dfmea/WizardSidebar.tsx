import { Steps, Tree, Empty } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ReactNode, CSSProperties } from 'react';
import type { GraphNode, GraphEdge } from '../../types';

const STRUCTURE_TYPES = ['System', 'Subsystem', 'Component', 'Interface', 'DesignParameter'];
const VALID_EDGE_TYPES = new Set(['HAS_PROCESS_STEP', 'HAS_WORK_ELEMENT', 'HAS_PARAMETER']);

// 结构节点类型颜色 — 使用设计系统 token，与工业暗色主题一致
const TYPE_COLORS: Record<string, string> = {
  System: 'var(--qf-red)',
  Subsystem: 'var(--qf-amber)',
  Component: 'var(--qf-green)',
  Interface: 'var(--qf-purple)',
  DesignParameter: 'var(--qf-blue)',
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

/** 区块标题 — 复用设计系统的青色强调条（.qf-card__title::before 样式） */
function SectionHeader({ children }: { children: ReactNode }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      fontFamily: 'var(--qf-font-display)',
      fontSize: 13,
      fontWeight: 600,
      color: 'var(--qf-text-primary)',
      marginBottom: 10,
      letterSpacing: '0.02em',
    }}>
      <span style={{
        width: 3,
        height: 14,
        borderRadius: 2,
        background: 'var(--qf-cyan)',
        boxShadow: '0 0 8px var(--qf-cyan-glow)',
        flexShrink: 0,
      }} />
      {children}
    </div>
  );
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
      {/* 结构树 */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px', minHeight: 0 }}>
        {currentStep === 0 ? (
          <Empty
            description={t('wizard.sidebar.structureHint', { defaultValue: '结构树将在第二步后出现' })}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : treeData && treeData.length > 0 ? (
          <>
            <SectionHeader>{t('wizard.sidebar.structureTree', { defaultValue: '结构树' })}</SectionHeader>
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
          <Empty
            description={t('wizard.sidebar.noStructure', { defaultValue: '暂无结构节点' })}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )}
      </div>

      {/* 步骤导航 */}
      <div style={{ borderTop: '1px solid var(--qf-divider)', padding: '12px 16px', flexShrink: 0 }}>
        <SectionHeader>{t('wizard.sidebar.steps', { defaultValue: '步骤' })}</SectionHeader>
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
            icon: warnings.includes(i) ? <WarningOutlined style={{ color: 'var(--qf-amber)' }} /> : undefined,
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
        <span style={{ color: TYPE_COLORS[node.type] || 'var(--qf-text-primary)' }}>{node.name}</span>
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