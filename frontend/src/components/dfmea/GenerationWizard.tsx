import { useState, useEffect, useMemo, useCallback } from 'react';
import { Modal, Steps, Button, Input, Card, Tag, Space, Table, Typography, Empty, InputNumber, Result, Divider, Popconfirm, Tooltip } from 'antd';
import { PlusOutlined, DeleteOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import type { GraphNode, GraphEdge } from '../../types';
import { generateFailureModes, suggestFailureChain, analyzeRisk, suggestMeasures } from '../../utils/dfmeaRules';

const { Title, Text, Paragraph } = Typography;

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
};

const CHILD_TYPE: Record<string, string> = {
  System: 'Subsystem',
  Subsystem: 'Component',
};

const TYPE_LABEL: Record<string, string> = {
  System: '系统',
  Subsystem: '子系统',
  Component: '零部件',
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

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 0:
        return (
          <div>
            <Title level={5}>5T范围定义</Title>
            <Paragraph>请填写DFMEA的5T范围信息（团队、时间、工具、任务、趋势）。</Paragraph>
          </div>
        );
      default:
        return (
          <Result
            icon={<CheckCircleOutlined />}
            title="向导就绪"
            subTitle="点击完成以生成DFMEA骨架，后续可在编辑器中细化。"
          />
        );
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
              <Button type="primary" onClick={handleNext}>下一步</Button>
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