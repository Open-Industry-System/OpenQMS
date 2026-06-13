import { useState, useCallback } from 'react';
import { Modal, Steps, Button, Input, Card, Tag, Space, Table, Typography, Empty, InputNumber, Result } from 'antd';
import { PlusOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { GraphNode, GraphEdge } from '../../types';
import { generateFailureModes, suggestFailureChain, analyzeRisk, suggestMeasures } from '../../utils/dfmeaRules';

const { Title, Paragraph } = Typography;

interface GenerationWizardProps {
  open: boolean;
  onCancel: () => void;
  onComplete: (data: { nodes: GraphNode[]; edges: GraphEdge[] }) => void;
}

interface WizardData {
  scope: { team: string; timeframe: string; tool: string; task: string; trend: string };
  structureNodes: GraphNode[];
  structureEdges: GraphEdge[];
  functions: Record<string, { name: string; requirement: string; specification: string }>;
  failures: Array<{ functionId: string; mode: string; effect: string; cause: string; s: number; o: number; d: number }>;
  optimizations: Array<{ failureIndex: number; prevention: string; detection: string }>;
}

const STEP_TITLES = [
  '5T范围 (第一步)',
  '结构分析 (第二步)',
  '功能分析 (第三步)',
  '失效分析 (第四步)',
  '风险分析 (第五步)',
  '优化 (第六步)',
  '确认 (第七步)',
];

const STRUCTURE_EDGE_TYPES: Record<string, string> = {
  System: 'HAS_PROCESS_STEP',
  Subsystem: 'HAS_WORK_ELEMENT',
  Component: 'HAS_PARAMETER',
};

const CHILD_TYPE: Record<string, string> = {
  System: 'Subsystem',
  Subsystem: 'Component',
  Component: 'DesignParameter',
};

const TYPE_LABEL: Record<string, string> = {
  System: '系统',
  Subsystem: '子系统',
  Component: '零部件',
  DesignParameter: '设计参数',
  Interface: '接口',
};

function nextId(suffix: string): string {
  return 'w' + Date.now() + '_' + Math.random().toString(36).slice(2, 8) + '_' + suffix;
}

function createNode(type: string, name: string): GraphNode {
  return { id: nextId(type.toLowerCase()), type, name, severity: 0, occurrence: 0, detection: 0 };
}

function initialWizardData(): WizardData {
  return {
    scope: { team: '', timeframe: '', tool: '', task: '', trend: '' },
    structureNodes: [],
    structureEdges: [],
    functions: {},
    failures: [],
    optimizations: [],
  };
}

function generateSkeleton(data: WizardData): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  let c = 0;
  const nid = (s: string) => 'w' + Date.now() + '_' + (c++) + '_' + s;

  // Copy structure nodes
  for (const sn of data.structureNodes) {
    nodes.push({ ...sn });
  }
  // Copy structure edges
  for (const se of data.structureEdges) {
    edges.push({ ...se });
  }

  // Build function and failure nodes
  for (const [compId, func] of Object.entries(data.functions)) {
    if (!func.name.trim()) continue;
    const funcNodeId = nid('func');
    nodes.push({
      id: funcNodeId, type: 'ProcessWorkElementFunction', name: func.name,
      requirement: func.requirement || '', specification: func.specification || '',
      severity: 0, occurrence: 0, detection: 0,
    });
    edges.push({ source: compId, target: funcNodeId, type: 'HAS_FUNCTION' });

    const funcFailures = data.failures.filter((f) => f.functionId === compId);
    for (let fi = 0; fi < funcFailures.length; fi++) {
      const failure = funcFailures[fi];
      const globalIdx = data.failures.indexOf(failure);

      const fmId = nid('fm');
      nodes.push({ id: fmId, type: 'FailureMode', name: failure.mode, severity: 0, occurrence: 0, detection: 0 });
      edges.push({ source: funcNodeId, target: fmId, type: 'HAS_FAILURE_MODE' });

      const feId = nid('fe');
      nodes.push({ id: feId, type: 'FailureEffect', name: failure.effect, severity: failure.s, occurrence: 0, detection: 0 });
      edges.push({ source: fmId, target: feId, type: 'EFFECT_OF' });

      const fcId = nid('fc');
      nodes.push({ id: fcId, type: 'FailureCause', name: failure.cause, severity: 0, occurrence: failure.o, detection: 0 });
      edges.push({ source: fcId, target: fmId, type: 'CAUSE_OF' });

      const opt = data.optimizations.find((o) => o.failureIndex === globalIdx);

      const pcId = nid('pc');
      nodes.push({ id: pcId, type: 'PreventionControl', name: (opt && opt.prevention) ? opt.prevention : '现行设计预防控制', severity: 0, occurrence: 0, detection: 0 });
      edges.push({ source: fcId, target: pcId, type: 'PREVENTED_BY' });

      const dcId = nid('dc');
      nodes.push({ id: dcId, type: 'DetectionControl', name: (opt && opt.detection) ? opt.detection : '现行设计探测控制', severity: 0, occurrence: 0, detection: failure.d });
      edges.push({ source: fcId, target: dcId, type: 'DETECTED_BY' });
    }
  }
  return { nodes, edges };
}

export default function GenerationWizard({ open, onCancel, onComplete }: GenerationWizardProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [data, setData] = useState<WizardData>(initialWizardData());

  const handleCancel = useCallback(() => {
    setCurrentStep(0);
    setData(initialWizardData());
    onCancel();
  }, [onCancel]);

  const handleNext = useCallback(() => {
    if (currentStep < STEP_TITLES.length - 1) {
      setCurrentStep((s) => s + 1);
    }
  }, [currentStep]);

  const handlePrev = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep((s) => s - 1);
    }
  }, [currentStep]);

  const handleFinish = useCallback(() => {
    const skeleton = generateSkeleton(data);
    onComplete(skeleton);
    setCurrentStep(0);
    setData(initialWizardData());
  }, [data, onComplete]);

  const updateData = (patch: Partial<WizardData>) => {
    setData((prev) => ({ ...prev, ...patch }));
  };

  const canProceed = () => {
    switch (currentStep) {
      case 0: return data.scope.team.trim() && data.scope.task.trim();
      case 1: return data.structureNodes.length > 0;
      case 2: return Object.keys(data.functions).length > 0;
      case 3: return data.failures.length > 0;
      case 4: return data.failures.every((f) => f.s > 0 && f.o > 0 && f.d > 0);
      default: return true;
    }
  };

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 0:
        return (
          <div>
            <Title level={5}>5T 范围定义</Title>
            <Paragraph>请填写 DFMEA 分析的 5T 范围信息。</Paragraph>
            <div style={{ display: 'grid', gap: 12 }}>
              <Input placeholder="团队 (Team)" value={data.scope.team} onChange={(e) => updateData({ scope: { ...data.scope, team: e.target.value } })} />
              <Input placeholder="时间范围 (Timeframe)" value={data.scope.timeframe} onChange={(e) => updateData({ scope: { ...data.scope, timeframe: e.target.value } })} />
              <Input placeholder="工具 (Tool)" value={data.scope.tool} onChange={(e) => updateData({ scope: { ...data.scope, tool: e.target.value } })} />
              <Input placeholder="任务 (Task)" value={data.scope.task} onChange={(e) => updateData({ scope: { ...data.scope, task: e.target.value } })} />
              <Input placeholder="趋势 (Trend)" value={data.scope.trend} onChange={(e) => updateData({ scope: { ...data.scope, trend: e.target.value } })} />
            </div>
          </div>
        );
      case 1:
        return (
          <div>
            <Title level={5}>结构分析</Title>
            <Paragraph>构建系统 → 子系统 → 零部件 → 设计参数的层级结构，或添加接口节点连接不同分支。</Paragraph>
            <Space style={{ marginBottom: 12 }}>
              <Button size="small" icon={<PlusOutlined />} onClick={() => {
                const node = createNode('System', '新系统');
                updateData({ structureNodes: [...data.structureNodes, node] });
              }}>添加系统</Button>
              <Button size="small" icon={<PlusOutlined />} onClick={() => {
                const node: GraphNode = { ...createNode('Interface', '新接口'), interface_type: 'physical' };
                updateData({ structureNodes: [...data.structureNodes, node] });
              }}>添加接口</Button>
            </Space>
            <div style={{ marginTop: 12 }}>
              {data.structureNodes.map((node) => (
                <Card key={node.id} size="small" style={{ marginBottom: 8, marginLeft: node.type === 'Subsystem' ? 20 : node.type === 'Component' ? 40 : node.type === 'DesignParameter' ? 60 : 0 }}>
                  <Space>
                    <Tag color={node.type === 'System' ? 'red' : node.type === 'Subsystem' ? 'orange' : node.type === 'Component' ? 'green' : node.type === 'DesignParameter' ? 'blue' : 'purple'}>{TYPE_LABEL[node.type] || node.type}</Tag>
                    <Input size="small" value={node.name} onChange={(e) => {
                      updateData({ structureNodes: data.structureNodes.map((n) => n.id === node.id ? { ...n, name: e.target.value } : n) });
                    }} style={{ width: 200 }} />
                    {CHILD_TYPE[node.type] && (
                      <Button size="small" onClick={() => {
                        const childType = CHILD_TYPE[node.type];
                        const child = createNode(childType, `新${TYPE_LABEL[childType]}`);
                        updateData({
                          structureNodes: [...data.structureNodes, child],
                          structureEdges: [...data.structureEdges, { source: node.id, target: child.id, type: STRUCTURE_EDGE_TYPES[node.type] }],
                        });
                      }}>+ {TYPE_LABEL[CHILD_TYPE[node.type]]}</Button>
                    )}
                    <Button size="small" danger onClick={() => {
                      const toDelete = new Set<string>();
                      const collect = (id: string) => { toDelete.add(id); data.structureEdges.filter((e) => e.source === id).forEach((e) => collect(e.target)); };
                      collect(node.id);
                      updateData({
                        structureNodes: data.structureNodes.filter((n) => !toDelete.has(n.id)),
                        structureEdges: data.structureEdges.filter((e) => !toDelete.has(e.source) && !toDelete.has(e.target)),
                      });
                    }}>删除</Button>
                  </Space>
                </Card>
              ))}
              {data.structureNodes.length === 0 && <Empty description="点击上方按钮添加系统节点" />}
            </div>
          </div>
        );
      case 2:
        return (
          <div>
            <Title level={5}>功能分析</Title>
            <Paragraph>为每个零部件定义功能、技术要求和规格参数。</Paragraph>
            {data.structureNodes.filter((n) => n.type === 'Component').map((comp) => (
              <Card key={comp.id} size="small" title={comp.name} style={{ marginBottom: 12 }}>
                <Input placeholder="功能描述" value={data.functions[comp.id]?.name || ''} onChange={(e) => updateData({ functions: { ...data.functions, [comp.id]: { ...data.functions[comp.id], name: e.target.value } } })} style={{ marginBottom: 8 }} />
                <Input placeholder="技术要求" value={data.functions[comp.id]?.requirement || ''} onChange={(e) => updateData({ functions: { ...data.functions, [comp.id]: { ...data.functions[comp.id], requirement: e.target.value } } })} style={{ marginBottom: 8 }} />
                <Input placeholder="规格参数" value={data.functions[comp.id]?.specification || ''} onChange={(e) => updateData({ functions: { ...data.functions, [comp.id]: { ...data.functions[comp.id], specification: e.target.value } } })} />
              </Card>
            ))}
          </div>
        );
      case 3:
        return (
          <div>
            <Title level={5}>失效分析</Title>
            <Paragraph>为每个功能定义失效模式、影响和原因。系统将基于功能描述自动推荐失效模式。</Paragraph>
            {Object.entries(data.functions).map(([funcId, func]) => {
              if (!func.name.trim()) return null;
              const funcFailures = data.failures.filter((f) => f.functionId === funcId);
              const suggestedModes = generateFailureModes(func.name);
              return (
                <Card key={funcId} size="small" title={func.name} style={{ marginBottom: 12 }}>
                  {funcFailures.length === 0 && suggestedModes.length > 0 && (
                    <div style={{ marginBottom: 8, padding: 8, background: '#f6ffed', borderRadius: 4 }}>
                      <Tag color="green">推荐</Tag>
                      <span style={{ fontSize: 12 }}> 基于功能自动推荐：</span>
                      <Space size={4} style={{ marginTop: 4 }}>
                        {suggestedModes.slice(0, 3).map((mode) => (
                          <Button key={mode} size="small" onClick={() => {
                            const chain = suggestFailureChain(mode);
                            updateData({ failures: [...data.failures, { functionId: funcId, mode, effect: chain.effects[0] || '', cause: chain.causes[0] || '', s: 0, o: 0, d: 0 }] });
                          }}>{mode}</Button>
                        ))}
                      </Space>
                    </div>
                  )}
                  {funcFailures.map((failure, _idx) => {
                    const globalIdx = data.failures.indexOf(failure);
                    return (
                      <div key={globalIdx} style={{ marginBottom: 8, padding: 8, background: '#f5f5f5', borderRadius: 4 }}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Input size="small" value={failure.mode} onChange={(e) => { const u = [...data.failures]; u[globalIdx] = { ...failure, mode: e.target.value }; updateData({ failures: u }); }} addonBefore="失效模式" />
                          <Input size="small" value={failure.effect} onChange={(e) => { const u = [...data.failures]; u[globalIdx] = { ...failure, effect: e.target.value }; updateData({ failures: u }); }} addonBefore="失效影响" />
                          <Input size="small" value={failure.cause} onChange={(e) => { const u = [...data.failures]; u[globalIdx] = { ...failure, cause: e.target.value }; updateData({ failures: u }); }} addonBefore="失效原因" />
                          <Button size="small" danger onClick={() => updateData({ failures: data.failures.filter((_, i) => i !== globalIdx) })}>删除</Button>
                        </Space>
                      </div>
                    );
                  })}
                  <Button size="small" type="dashed" onClick={() => updateData({ failures: [...data.failures, { functionId: funcId, mode: '新失效模式', effect: '', cause: '', s: 0, o: 0, d: 0 }] })}>+ 添加失效模式</Button>
                </Card>
              );
            })}
          </div>
        );
      case 4:
        return (
          <div>
            <Title level={5}>风险分析</Title>
            <Paragraph>为每个失效链评估严重度(S)、发生度(O)、探测度(D)。</Paragraph>
            <Table
              size="small"
              dataSource={data.failures.map((f, i) => ({ ...f, key: i }))}
              columns={[
                { title: '失效模式', dataIndex: 'mode', width: 140 },
                { title: 'S', dataIndex: 's', width: 60, render: (v: number, r: any) => <InputNumber size="small" min={1} max={10} value={v || undefined} style={{ width: 50 }} onChange={(val) => { const u = [...data.failures]; u[r.key] = { ...u[r.key], s: val || 0 }; updateData({ failures: u }); }} /> },
                { title: 'O', dataIndex: 'o', width: 60, render: (v: number, r: any) => <InputNumber size="small" min={1} max={10} value={v || undefined} style={{ width: 50 }} onChange={(val) => { const u = [...data.failures]; u[r.key] = { ...u[r.key], o: val || 0 }; updateData({ failures: u }); }} /> },
                { title: 'D', dataIndex: 'd', width: 60, render: (v: number, r: any) => <InputNumber size="small" min={1} max={10} value={v || undefined} style={{ width: 50 }} onChange={(val) => { const u = [...data.failures]; u[r.key] = { ...u[r.key], d: val || 0 }; updateData({ failures: u }); }} /> },
                { title: 'RPN', width: 60, render: (_: unknown, r: any) => { const rpn = r.s * r.o * r.d; return <Tag color={rpn >= 100 ? 'red' : rpn >= 50 ? 'orange' : 'green'}>{rpn || 0}</Tag>; } },
                { title: 'AP', width: 80, render: (_: unknown, r: any) => { const { ap, hint: _hint } = analyzeRisk(r.s, r.o, r.d); return <div><Tag color={ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'green'}>{ap || '-'}</Tag>{ap === 'H' && <div style={{ fontSize: 11, color: '#cf1322' }}>必须优化</div>}</div>; } },
              ]}
              pagination={false}
            />
          </div>
        );
      case 5:
        return (
          <div>
            <Title level={5}>优化措施</Title>
            {(() => {
              const highRisk = data.failures.map((f, i) => ({ ...f, index: i })).filter((f) => analyzeRisk(f.s, f.o, f.d).ap === 'H');
              if (highRisk.length === 0) return (
                <Result icon={<CheckCircleOutlined />} title="无需强制优化" subTitle="所有失效模式 AP 均不为 H，当前风险可接受。" />
              );
              return (
                <div>
                  <Paragraph style={{ color: '#cf1322' }}>以下 {highRisk.length} 项 AP=H，必须采取优化措施：</Paragraph>
                  {highRisk.map((failure) => {
                    const measures = suggestMeasures(failure.mode, 'H');
                    return (
                      <Card key={failure.index} size="small" title={failure.mode} style={{ marginBottom: 12 }}>
                        <Input.TextArea rows={2} placeholder={measures.prevention.join(' / ')} value={data.optimizations.find((o) => o.failureIndex === failure.index)?.prevention || ''} onChange={(e) => {
                          const opts = [...data.optimizations];
                          const existing = opts.find((o) => o.failureIndex === failure.index);
                          if (existing) existing.prevention = e.target.value; else opts.push({ failureIndex: failure.index, prevention: e.target.value, detection: '' });
                          updateData({ optimizations: opts });
                        }} style={{ marginBottom: 8 }} />
                        <Input.TextArea rows={2} placeholder={measures.detection.join(' / ')} value={data.optimizations.find((o) => o.failureIndex === failure.index)?.detection || ''} onChange={(e) => {
                          const opts = [...data.optimizations];
                          const existing = opts.find((o) => o.failureIndex === failure.index);
                          if (existing) existing.detection = e.target.value; else opts.push({ failureIndex: failure.index, prevention: '', detection: e.target.value });
                          updateData({ optimizations: opts });
                        }} />
                      </Card>
                    );
                  })}
                </div>
              );
            })()}
          </div>
        );
      case 6:
        return (
          <div>
            <Title level={5}>确认创建</Title>
            <Card size="small" style={{ marginBottom: 12 }}>
              <div>结构节点: {data.structureNodes.length} 个</div>
              <div>功能节点: {Object.keys(data.functions).length} 个</div>
              <div>失效链: {data.failures.length} 条</div>
              <div>总节点: {generateSkeleton(data).nodes.length} 个</div>
              <div>总边: {generateSkeleton(data).edges.length} 条</div>
            </Card>
            <Paragraph>确认后将创建 DFMEA 文档并进入编辑器，你可以在编辑器中继续完善细节。</Paragraph>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <Modal
      title="DFMEA 生成向导"
      open={open}
      onCancel={handleCancel}
      width={800}
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <Button onClick={handleCancel}>取消</Button>
          <Space>
            {currentStep > 0 && <Button onClick={handlePrev}>上一步</Button>}
            {currentStep < STEP_TITLES.length - 1 ? (
              <Button type="primary" onClick={handleNext} disabled={!canProceed()}>下一步</Button>
            ) : (
              <Button type="primary" onClick={handleFinish}>完成</Button>
            )}
          </Space>
        </div>
      }
    >
      <Steps current={currentStep} size="small" style={{ marginBottom: 24 }}>
        {STEP_TITLES.map((title, i) => (
          <Steps.Step key={i} title={title} />
        ))}
      </Steps>
      {renderCurrentStep()}
    </Modal>
  );
}