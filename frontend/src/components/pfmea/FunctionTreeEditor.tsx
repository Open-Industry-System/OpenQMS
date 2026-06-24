import { useTranslation } from 'react-i18next';
import { Card, Input, Select, Button, Empty, Space } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { GraphNode, GraphEdge } from '../../types';

interface FunctionTreeEditorProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  fmeaId: string;
  onChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}

const Z = { severity: 0, occurrence: 0, detection: 0 };
const newId = (p: string) => `w${crypto.randomUUID()}_${p}`;

export default function FunctionTreeEditor({ nodes, edges, fmeaId, onChange }: FunctionTreeEditorProps) {
  const { t } = useTranslation('pfmea');
  void fmeaId;

  const itemFuncs = nodes.filter((n) => n.type === 'ProcessItemFunction');
  const stepNodes = nodes.filter((n) => n.type === 'ProcessStep');
  const weNodes = nodes.filter((n) => n.type === 'ProcessWorkElement');

  const updateNode = (id: string, patch: Partial<GraphNode>) => {
    onChange(nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)), edges);
  };

  // Branch-local parent resolution for FUNCTION_MAPPED_TO (spec §5 Step 2 + §8):
  //  - ProcessStepFunction  ← maps FROM the ProcessItemFunction of the ProcessItem
  //                              that owns this ProcessStep (HAS_PROCESS_STEP parent).
  //  - ProcessWorkElementFunction ← maps FROM the ProcessStepFunction of the ProcessStep
  //                              that owns this WorkElement (HAS_WORK_ELEMENT parent).
  //  - ProcessItemFunction   ← no FUNCTION_MAPPED_TO parent (top of the chain).
  // `structureParentId` is the id of the structure node this function is being added under
  // (ProcessItem / ProcessStep / ProcessWorkElement), passed from the add-button.
  const itemFunctionOf = (processItemId: string): GraphNode | undefined =>
    nodes.find((n) => n.type === 'ProcessItemFunction' &&
      edges.some((e) => e.source === processItemId && e.target === n.id && e.type === 'HAS_FUNCTION'));
  const stepFunctionOf = (processStepId: string): GraphNode | undefined =>
    nodes.find((n) => n.type === 'ProcessStepFunction' &&
      edges.some((e) => e.source === processStepId && e.target === n.id && e.type === 'HAS_FUNCTION'));
  const processItemOfStep = (stepId: string): GraphNode | undefined =>
    nodes.find((n) => n.type === 'ProcessItem' &&
      edges.some((e) => e.source === n.id && e.target === stepId && e.type === 'HAS_PROCESS_STEP'));

  const addFunction = (
    structureParentId: string,
    fnType: 'ProcessItemFunction' | 'ProcessStepFunction' | 'ProcessWorkElementFunction',
  ) => {
    const fid = newId('func');
    const fn: GraphNode = { id: fid, type: fnType, name: '', ...Z } as GraphNode;
    const newEdges: GraphEdge[] = [{ source: structureParentId, target: fid, type: 'HAS_FUNCTION' }];
    if (fnType === 'ProcessStepFunction') {
      // structureParentId is a ProcessStep; find its ProcessItem, then that item's function.
      const item = processItemOfStep(structureParentId);
      const itemFunc = item ? itemFunctionOf(item.id) : undefined;
      if (itemFunc) newEdges.push({ source: itemFunc.id, target: fid, type: 'FUNCTION_MAPPED_TO' });
    } else if (fnType === 'ProcessWorkElementFunction') {
      // structureParentId is a ProcessWorkElement; find its ProcessStep, then that step's function.
      const step = nodes.find((n) => n.type === 'ProcessStep' &&
        edges.some((e) => e.source === n.id && e.target === structureParentId && e.type === 'HAS_WORK_ELEMENT'));
      const stepFunc = step ? stepFunctionOf(step.id) : undefined;
      if (stepFunc) newEdges.push({ source: stepFunc.id, target: fid, type: 'FUNCTION_MAPPED_TO' });
    }
    // ProcessItemFunction: no FUNCTION_MAPPED_TO parent (chain root).
    onChange([...nodes, fn], [...edges, ...newEdges]);
  };

  const renderFunctionCard = (fn: GraphNode, allowClass: boolean, classOptions: { value: string; label: string }[]) => (
    <Card key={fn.id} size="small" style={{ marginBottom: 8 }}
      title={<Input size="small" value={fn.name} placeholder={t('wizard.function.functionDesc')}
        onChange={(e) => updateNode(fn.id, { name: e.target.value })} />}>
      <Space direction="vertical" style={{ width: '100%' }}>
        {fn.type === 'ProcessStepFunction' && (
          <Input size="small" addonBefore={t('wizard.function.specification')} value={fn.specification ?? ''}
            onChange={(e) => updateNode(fn.id, { specification: e.target.value })} placeholder="偏移度 <= 0.05mm" />
        )}
        {fn.type === 'ProcessWorkElementFunction' && (
          <Input size="small" addonBefore={t('wizard.function.requirement')} value={fn.requirement ?? ''}
            onChange={(e) => updateNode(fn.id, { requirement: e.target.value })} placeholder="贴装压力 3.0±0.5N" />
        )}
        {allowClass && (
          <Select size="small" value={fn.classification || undefined} placeholder={t('wizard.function.specialCharacteristic')}
            onChange={(v) => updateNode(fn.id, { classification: v || '' })} options={classOptions} style={{ width: 120 }} />
        )}
      </Space>
    </Card>
  );

  const classOpts = [
    { value: '', label: '-' },
    { value: 'CC', label: 'CC' },
    { value: 'SC', label: 'SC' },
  ];

  return (
    <div>
      {stepNodes.length === 0 && weNodes.length === 0 && itemFuncs.length === 0 && (
        <Empty description={t('wizard.function.description')} />
      )}
      {/* Item functions */}
      {itemFuncs.map((fn) => renderFunctionCard(fn, false, classOpts))}
      <Button icon={<PlusOutlined />} size="small" onClick={() => {
        const pi = nodes.find((n) => n.type === 'ProcessItem');
        if (pi) addFunction(pi.id, 'ProcessItemFunction');
      }}>{t('wizard.function.addItemFunction')}</Button>
      {/* Step functions */}
      {nodes.filter((n) => n.type === 'ProcessStepFunction').map((fn) => renderFunctionCard(fn, true, classOpts))}
      {stepNodes.map((ps) => (
        <Button key={ps.id} icon={<PlusOutlined />} size="small" onClick={() => addFunction(ps.id, 'ProcessStepFunction')}>
          {t('wizard.function.addStepFunction')} — {ps.process_number}
        </Button>
      ))}
      {/* Work element functions */}
      {nodes.filter((n) => n.type === 'ProcessWorkElementFunction').map((fn) => renderFunctionCard(fn, true, classOpts))}
      {weNodes.map((we) => (
        <Button key={we.id} icon={<PlusOutlined />} size="small" onClick={() => addFunction(we.id, 'ProcessWorkElementFunction')}>
          {t('wizard.function.addWorkElementFunction')} — {we.name}({we.classification})
        </Button>
      ))}
    </div>
  );
}
