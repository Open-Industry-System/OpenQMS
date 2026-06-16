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
          <Empty
            description={t('wizard.sidebar.structureHint', { defaultValue: '结构树将在第二步后出现' })}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : treeData && treeData.length > 0 ? (
          <>
            <Typography.Text strong style={{ fontSize: 13, marginBottom: 8, display: 'block' }}>
              {t('wizard.sidebar.structureTree', { defaultValue: '结构树' })}
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
          <Empty
            description={t('wizard.sidebar.noStructure', { defaultValue: '暂无结构节点' })}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
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