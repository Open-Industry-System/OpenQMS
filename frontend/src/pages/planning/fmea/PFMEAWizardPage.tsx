import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Modal, Spin, Typography, message, Input, Card, Tag, Empty, DatePicker, Select, InputNumber, Result, Row, Col } from 'antd';
import { ArrowLeftOutlined, PlusOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { getFMEA, deleteFMEA } from '../../../api/fmea';
import { calculateAP } from '../../../utils/fmea';
import type { FMEADocument, GraphNode, GraphEdge, WizardScope } from '../../../types';
import { useWizardSave, type SaveStatus } from '../../../hooks/useWizardSave';
import { usePfmeaWizardValidation } from '../../../hooks/usePfmeaWizardValidation';
import { buildRows, getRowSeverity, getProcessChain, type FMEARow } from '../../../utils/fmeaTable';
import { cascadeDeleteStructureNode } from '../../../utils/wizardCascadeDelete';
import WizardSidebar from '../../../components/pfmea/PFMEAWizardSidebar';
import WizardGuidanceCard from '../../../components/pfmea/PFMEAGuidanceCard';
import ScopeTagField from '../../../components/dfmea/ScopeTagField';
import SmartSuggestionDropdown from '../../../components/dfmea/SmartSuggestionDropdown';
import type { ReactNode } from 'react';
import { rangeToTimeframe, timeframeToRange } from '../../../utils/wizardTimeframe';
import FunctionTreeEditor from '../../../components/pfmea/FunctionTreeEditor';
import { parseScopeTokens } from '../../../utils/wizardScopeTokens';
import { orderStructureNodes } from '../../../utils/wizardStructureOrder';
import RiskTable from '../../../components/pfmea/RiskTable';
import { createWizardFailureChain, ensureCauseControls } from '../../../utils/wizardGraphNormalize';
import { usePfmeaRules } from '../../../utils/pfmeaRules';

const { Title, Paragraph } = Typography;

const STRUCTURE_TYPES = ['ProcessItem', 'ProcessStep', 'ProcessWorkElement'];
const FUNCTION_TYPES = ['ProcessItemFunction', 'ProcessStepFunction', 'ProcessWorkElementFunction'];
const CHILD_TYPE: Record<string, string> = { ProcessItem: 'ProcessStep', ProcessStep: 'ProcessWorkElement' };
const CHILD_EDGE_TYPE: Record<string, string> = { ProcessItem: 'HAS_PROCESS_STEP', ProcessStep: 'HAS_WORK_ELEMENT' };

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div style={{ marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}

export default function PFMEAWizardPage() {
  const { id: fmeaId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation('pfmea');
  const { suggest4MCauses } = usePfmeaRules();
  const cause4MHints = useMemo(() => suggest4MCauses(), [suggest4MCauses]);

  const [fmea, setFmea] = useState<FMEADocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [wizardScope, setWizardScope] = useState<WizardScope>({});
  const [currentStep, setCurrentStep] = useState(0);
  const [conflictOpen, setConflictOpen] = useState(false);

  const completedSteps = useMemo(() => {
    const set = new Set<number>();
    const hasScope = !!(wizardScope.team || wizardScope.timeframe || wizardScope.tool || wizardScope.task || wizardScope.trend);
    const hasAny = nodes.length > 0;
    const hasStructure = nodes.some(n => STRUCTURE_TYPES.includes(n.type));
    const hasFunction = nodes.some(n => FUNCTION_TYPES.includes(n.type));
    const hasFailure = nodes.some(n => n.type === 'FailureMode');
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const hasRating = buildRows(nodes, edges).some(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dc = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      return getRowSeverity(r, nodeMap) > 0 || (cause?.occurrence ?? 0) > 0 || (dc?.detection ?? 0) > 0;
    });
    const hasOptimization = nodes.some(n => n.type === 'RecommendedAction' && (n.responsible ?? '').trim());
    if (hasScope || hasAny) set.add(0);
    if (hasStructure) set.add(1);
    if (hasFunction) set.add(2);
    if (hasFailure) set.add(3);
    if (hasRating) set.add(4);
    if (hasOptimization) set.add(5);
    return set;
  }, [nodes, edges, wizardScope]);

  const maxReachableStep = useMemo(() => {
    let furthest = -1;
    for (let i = 0; i <= 6; i++) if (completedSteps.has(i)) furthest = i;
    return Math.min(furthest + 1, 6);
  }, [completedSteps]);

  const { saveStatus, setLockVersion, debouncedSave, immediateSave, lastSavedHashRef } = useWizardSave({
    fmeaId: fmeaId!,
    onConflict: () => setConflictOpen(true),
  });
  const selectedTools = parseScopeTokens(wizardScope.tool || '');
  const validation = usePfmeaWizardValidation(nodes, edges, selectedTools, {});

  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const scopeRef = useRef(wizardScope);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);
  useEffect(() => { edgesRef.current = edges; }, [edges]);
  useEffect(() => { scopeRef.current = wizardScope; }, [wizardScope]);

  const computeHash = (n: GraphNode[], e: GraphEdge[], s: WizardScope) =>
    JSON.stringify({ nodes: n, edges: e, scope: s });

  useEffect(() => {
    if (!fmeaId) return;
    getFMEA(fmeaId).then(doc => {
      if (doc.fmea_type !== 'PFMEA') {
        navigate(`/fmea/${doc.fmea_id}`, { replace: true });
        return;
      }
      const loadedNodes = doc.graph_data?.nodes || [];
      const loadedEdges = doc.graph_data?.edges || [];
      const loadedScope = doc.graph_data?.wizardScope || {};
      setLockVersion(doc.lock_version);
      lastSavedHashRef.current = computeHash(loadedNodes, loadedEdges, loadedScope);
      const { nodes: normNodes, edges: normEdges, changed } = ensureCauseControls(loadedNodes, loadedEdges);
      setFmea(doc);
      setNodes(normNodes);
      setEdges(normEdges);
      setWizardScope(loadedScope);
      setLoading(false);
      if (changed) {
        const normalizedHash = computeHash(normNodes, normEdges, loadedScope);
        immediateSave({ nodes: normNodes, edges: normEdges, wizardScope: loadedScope }, doc.title, normalizedHash);
      }
    }).catch((err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } } };
      message.error(e?.response?.data?.detail || t('wizard.page.loadFailed'));
      navigate('/fmea');
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fmeaId, navigate, setLockVersion, lastSavedHashRef]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      const hash = computeHash(nodesRef.current, edgesRef.current, scopeRef.current);
      if (hash !== lastSavedHashRef.current) {
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
    // lastSavedHashRef is a ref — always reads latest without re-registering
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateGraphData = useCallback((newNodes: GraphNode[], newEdges: GraphEdge[], newScope?: WizardScope) => {
    setNodes(newNodes);
    setEdges(newEdges);
    if (newScope !== undefined) setWizardScope(newScope);
    const hash = computeHash(newNodes, newEdges, newScope ?? wizardScope);
    debouncedSave({ nodes: newNodes, edges: newEdges, wizardScope: newScope ?? wizardScope }, fmea?.title, hash);
  }, [debouncedSave, wizardScope, fmea?.title]);

  const goToStep = useCallback((step: number) => {
    setCurrentStep(step);
  }, []);

  const handleFinish = async () => {
    const completedScope = { ...wizardScope, wizard_completed: true };
    const hash = computeHash(nodes, edges, completedScope);
    const success = await immediateSave({ nodes, edges, wizardScope: completedScope }, fmea?.title, hash);
    if (!success) {
      if (saveStatus !== 'conflict') {
        message.error(t('wizard.page.finishFailed'));
      }
      return;
    }
    navigate(`/fmea/${fmeaId}`);
  };

  const handleBackToList = () => {
    const hasOnlyInitialSystem = nodes.length <= 1 && edges.length === 0;
    if (hasOnlyInitialSystem) {
      Modal.confirm({
        title: t('wizard.page.confirmEmptyDraftTitle'),
        content: t('wizard.page.confirmEmptyDraft'),
        okText: t('wizard.page.confirmEmptyDraftOk'),
        cancelText: t('wizard.page.confirmEmptyDraftCancel'),
        okButtonProps: { danger: true },
        onOk: async () => {
          try { await deleteFMEA(fmeaId!); } catch { /* ignore */ }
          navigate('/fmea');
        },
      });
      return;
    }
    const liveHash = computeHash(nodesRef.current, edgesRef.current, scopeRef.current);
    if (liveHash !== lastSavedHashRef.current) {
      Modal.confirm({
        title: t('wizard.page.confirmLeaveTitle', { defaultValue: '离开向导？' }),
        content: t('wizard.page.confirmLeave', { defaultValue: '有未保存的更改，确定离开吗？' }),
        okText: t('wizard.page.confirmLeaveOk', { defaultValue: '离开' }),
        cancelText: t('wizard.page.confirmEmptyDraftCancel'),
        okButtonProps: { danger: true },
        onOk: () => navigate('/fmea'),
      });
      return;
    }
    navigate('/fmea');
  };

  const canFinish = validation.warnings.length === 0
    && validation.step1Complete
    && validation.step2Complete
    && validation.step3Complete
    && validation.step4Complete
    && validation.step5Complete;

  const saveStatusLabel: Record<SaveStatus, string> = {
    idle: '',
    saving: t('wizard.page.saveSaving'),
    saved: t('wizard.page.saveSaved'),
    error: t('wizard.page.saveError'),
    conflict: t('wizard.page.conflictTitle'),
  };

  const renderStep0 = () => {
    const legacyTimeframe =
      wizardScope.timeframe && !timeframeToRange(wizardScope.timeframe) ? wizardScope.timeframe : null;
    return (
      <div style={{ display: 'grid', gap: 12 }}>
        <Field label={t('wizard.scope.team')}>
          <Input value={wizardScope.team || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, team: e.target.value })} />
        </Field>
        <Field label={t('wizard.scope.timeframe')}>
          <DatePicker.RangePicker
            style={{ width: '100%' }}
            value={timeframeToRange(wizardScope.timeframe || '')}
            onChange={(range) => updateGraphData(nodes, edges, { ...wizardScope, timeframe: rangeToTimeframe(range) })}
          />
          {legacyTimeframe && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t('wizard.scope.legacyTimeframe', { value: legacyTimeframe })}
            </Typography.Text>
          )}
        </Field>
        <Field label={t('wizard.scope.tool')}>
          <ScopeTagField
            value={wizardScope.tool || ''}
            onChange={v => updateGraphData(nodes, edges, { ...wizardScope, tool: v })}
            presets={t('wizard.scope.toolPresets', { returnObjects: true }) as string[]}
            triggerType="pfmea_tool"
            fmeaId={fmeaId!}
            context={{ fmea_title: fmea?.title, product_line_code: fmea?.product_line_code ?? '', task: wizardScope.task || '', team: wizardScope.team || '' }}
          />
        </Field>
        <Field label={t('wizard.scope.task')}>
          <Input value={wizardScope.task || ''} onChange={e => updateGraphData(nodes, edges, { ...wizardScope, task: e.target.value })} />
        </Field>
        <Field label={t('wizard.scope.trend')}>
          <ScopeTagField
            value={wizardScope.trend || ''}
            onChange={v => updateGraphData(nodes, edges, { ...wizardScope, trend: v })}
            presets={t('wizard.scope.trendPresets', { returnObjects: true }) as string[]}
            triggerType="pfmea_trend"
            fmeaId={fmeaId!}
            context={{ fmea_title: fmea?.title, product_line_code: fmea?.product_line_code ?? '', task: wizardScope.task || '', team: wizardScope.team || '' }}
          />
        </Field>
      </div>
    );
  };

  const renderStep1 = () => {
    const structureNodes = nodes.filter(n => STRUCTURE_TYPES.includes(n.type));

    const handleAddNode = (type: string, parentId?: string) => {
      const newNode: GraphNode = {
        id: `w${crypto.randomUUID()}_${type.toLowerCase()}`,
        type,
        name: t(`wizard.typeLabels.${type}`, { defaultValue: type }),
        severity: 0, occurrence: 0, detection: 0,
        ...(type === 'ProcessStep' ? { process_number: '' } : {}),
        ...(type === 'ProcessWorkElement' ? { classification: '' } : {}),
      };
      const newEdges = parentId
        ? [...edges, { source: parentId, target: newNode.id, type: CHILD_EDGE_TYPE[nodes.find(n => n.id === parentId)?.type || 'ProcessItem'] || 'HAS_PROCESS_STEP' }]
        : edges;
      updateGraphData([...nodes, newNode], newEdges);
    };

    const handleDeleteNode = (nodeId: string) => {
      const result = cascadeDeleteStructureNode(nodeId, nodes, edges);
      updateGraphData(result.nodes, result.edges);
    };

    const handleRenameNode = (nodeId: string, name: string) => {
      updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, name } : n), edges);
    };

    const handleProcessNumberChange = (nodeId: string, process_number: string) => {
      updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, process_number } : n), edges);
    };

    const handleClassificationChange = (nodeId: string, classification: string) => {
      updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, classification } : n), edges);
    };

    const typeLabel = (type: string) => t(`wizard.typeLabels.${type}`, { defaultValue: type });
    const TYPE_COLORS: Record<string, string> = { ProcessItem: 'red', ProcessStep: 'orange', ProcessWorkElement: 'green' };

    const childToParent: Record<string, string> = {};
    for (const e of edges) {
      if (e.type === 'HAS_PROCESS_STEP' || e.type === 'HAS_WORK_ELEMENT') {
        childToParent[e.target] = e.source;
      }
    }
    const depthOf = (id: string): number => {
      let depth = 0;
      let cur: string | undefined = id;
      const guard = new Set<string>();
      while (childToParent[cur] && !guard.has(cur)) {
        guard.add(cur);
        cur = childToParent[cur];
        depth += 1;
      }
      return depth;
    };

    const orderedStructureNodes = orderStructureNodes(structureNodes, edges);

    return (
      <div>
        <Space style={{ marginBottom: 12 }}>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('ProcessItem')}>{t('wizard.structure.addProcessItem')}</Button>
        </Space>
        {structureNodes.length === 0 && <Empty description={t('wizard.structure.empty')} />}
        {orderedStructureNodes.map(node => (
          <Card key={node.id} size="small" style={{ marginBottom: 8, marginLeft: depthOf(node.id) * 20 }}>
            <Space>
              <Tag color={TYPE_COLORS[node.type]}>{typeLabel(node.type)}</Tag>
              <Input size="small" value={node.name} style={{ width: 200 }}
                onChange={e => handleRenameNode(node.id, e.target.value)} />
              {node.type === 'ProcessStep' && (
                <Input size="small" placeholder={t('wizard.structure.processNumber')} value={node.process_number || ''}
                  onChange={e => handleProcessNumberChange(node.id, e.target.value)} style={{ width: 100 }} />
              )}
              {node.type === 'ProcessWorkElement' && (
                <Select size="small" placeholder={t('wizard.structure.classification4M')} value={node.classification || undefined}
                  onChange={v => handleClassificationChange(node.id, v)}
                  options={[
                    { value: 'Man', label: '人 Man' },
                    { value: 'Machine', label: '机 Machine' },
                    { value: 'Material', label: '料 Material' },
                    { value: 'Environment', label: '环 Environment' },
                  ]}
                  style={{ width: 120 }} />
              )}
              {CHILD_TYPE[node.type] && (
                <Button size="small" onClick={() => handleAddNode(CHILD_TYPE[node.type], node.id)}>
                  + {t(
                    CHILD_TYPE[node.type] === 'ProcessStep'
                      ? 'wizard.structure.addProcessStep'
                      : 'wizard.structure.addWorkElement'
                  )}
                </Button>
              )}
              <Button size="small" danger onClick={() => handleDeleteNode(node.id)}>{t('wizard.structure.delete')}</Button>
            </Space>
          </Card>
        ))}
      </div>
    );
  };

  const renderStep2 = () => (
    <FunctionTreeEditor nodes={nodes} edges={edges} fmeaId={fmeaId!} onChange={(n, e) => updateGraphData(n, e)} />
  );

  // Step 3 — Failure Analysis (failure chains hang off ProcessStepFunction)
  const renderStep3 = () => {
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const processStep = (funcId: string) => getProcessChain(funcId, nodeMap, edges);

    // FM only hangs off ProcessStepFunction per PFMEA spec.
    const stepFuncs = nodes.filter(n => n.type === 'ProcessStepFunction');
    if (stepFuncs.length === 0) return <Empty description={t('wizard.failure.title') + ' — ' + t('wizard.function.title')} />;

    // For a ProcessStepFunction, walk HAS_FUNCTION back to ProcessStep, then
    // collect its HAS_WORK_ELEMENT children to surface 4M hints.
    const workElementsForStepFunction = (funcId: string) => {
      const fnEdge = edges.find(e => e.target === funcId && e.type === 'HAS_FUNCTION');
      const stepId = fnEdge?.source;
      if (!stepId) return [];
      return edges
        .filter(e => e.source === stepId && e.type === 'HAS_WORK_ELEMENT')
        .map(e => nodeMap.get(e.target))
        .filter(Boolean) as GraphNode[];
    };

    const handleAddFailure = (funcId: string) => {
      const { newNodes, newEdges } = createWizardFailureChain(funcId);
      updateGraphData([...nodes, ...newNodes], [...edges, ...newEdges]);
    };

    const handleDeleteFailureChain = (failureModeId: string) => {
      const result = cascadeDeleteStructureNode(failureModeId, nodes, edges);
      updateGraphData(result.nodes, result.edges);
    };

    const handleUpdateNodeField = (nodeId: string, field: string, value: string) => {
      updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, [field]: value } : n), edges);
    };

    const handleUpdateControl = (causeId: string, type: 'prevention' | 'detection', value: string) => {
      const edgeType = type === 'prevention' ? 'PREVENTED_BY' : 'DETECTED_BY';
      const ctrlEdge = edges.find(e => e.source === causeId && e.type === edgeType);
      if (!ctrlEdge) return;
      updateGraphData(
        nodes.map(n => n.id === ctrlEdge.target ? { ...n, name: value } : n),
        edges,
      );
    };

    return (
      <div>
        {stepFuncs.map(func => {
          const fmEdges = edges.filter(e => e.source === func.id && e.type === 'HAS_FAILURE_MODE');
          const fmNodes = fmEdges.map(e => nodeMap.get(e.target)).filter(Boolean) as GraphNode[];
          const workElements = workElementsForStepFunction(func.id);
          const workElementNames = workElements.map(we => `${we.classification || ''}:${we.name}`).join(', ');
          const baseContext = {
            function_description: func.name,
            process_step: processStep(func.id),
          };

          return (
            <Card key={func.id} size="small" title={func.name} style={{ marginBottom: 12 }}>
              {workElements.length > 0 && (
                <div style={{ fontSize: 12, marginBottom: 8, color: 'var(--qf-text-secondary)' }}>
                  <span style={{ fontWeight: 600 }}>{t('wizard.failure.workElementHint')}：</span>
                  {workElementNames}
                </div>
              )}
              {fmNodes.map(fmNode => {
                const effectEdge = edges.find(e => e.source === fmNode.id && e.type === 'EFFECT_OF');
                const effectNode = effectEdge ? nodes.find(n => n.id === effectEdge!.target) : null;
                const causeEdges = edges.filter(e => e.target === fmNode.id && e.type === 'CAUSE_OF');
                const causeNodes = causeEdges.map(e => nodeMap.get(e.source)).filter(Boolean) as GraphNode[];

                return (
                  <div key={fmNode.id} style={{ marginBottom: 8, padding: 8, background: 'var(--qf-bg-elevated)', border: '1px solid var(--qf-border)', borderRadius: 'var(--qf-radius-md)' }}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div>
                        <div style={{ fontSize: 12, marginBottom: 2 }}>{t('wizard.failure.failureMode')}</div>
                        <SmartSuggestionDropdown
                          triggerType="failure_mode"
                          context={baseContext}
                          fmeaId={fmeaId!}
                          value={fmNode.name}
                          onChange={(val) => handleUpdateNodeField(fmNode.id, 'name', val)}
                          onSelect={(s) => handleUpdateNodeField(fmNode.id, 'name', s.name)}
                        />
                      </div>
                      {effectNode && (
                        <div>
                          <div style={{ fontSize: 12, marginBottom: 2 }}>{t('wizard.failure.failureEffect')}</div>
                          <SmartSuggestionDropdown
                            triggerType="failure_effect"
                            context={{ failure_mode: fmNode.name, ...baseContext }}
                            fmeaId={fmeaId!}
                            value={effectNode.name}
                            onChange={(val) => handleUpdateNodeField(effectNode.id, 'name', val)}
                            onSelect={(s) => handleUpdateNodeField(effectNode.id, 'name', s.name)}
                          />
                        </div>
                      )}
                      {causeNodes.map(causeNode => {
                        const pcEdge = edges.find(e => e.source === causeNode.id && e.type === 'PREVENTED_BY');
                        const dcEdge = edges.find(e => e.source === causeNode.id && e.type === 'DETECTED_BY');
                        const pcName = pcEdge ? nodes.find(n => n.id === pcEdge.target)?.name || '' : '';
                        const dcName = dcEdge ? nodes.find(n => n.id === dcEdge.target)?.name || '' : '';
                        return (
                          <div key={causeNode.id}>
                            <div style={{ fontSize: 12, marginBottom: 2 }}>{t('wizard.failure.failureCause')}</div>
                            <SmartSuggestionDropdown
                              triggerType="failure_cause"
                              context={{ failure_mode: fmNode.name, ...baseContext, work_elements: workElementNames }}
                              fmeaId={fmeaId!}
                              value={causeNode.name}
                              onChange={(val) => handleUpdateNodeField(causeNode.id, 'name', val)}
                              onSelect={(s) => handleUpdateNodeField(causeNode.id, 'name', s.name)}
                            />
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>
                              <span style={{ color: 'var(--qf-text-secondary)' }}>{t('wizard.failure.cause4MHint')}：</span>
                              <Space size={[4, 4]} wrap>
                                {Object.entries(cause4MHints).flatMap(([category, hints]) =>
                                  hints.slice(0, 2).map((hint, idx) => (
                                    <Tag
                                      key={`${category}-${idx}`}
                                      style={{ cursor: 'pointer' }}
                                      onClick={() => handleUpdateNodeField(causeNode.id, 'name', hint)}
                                      title={`${category}: ${hint}`}
                                    >
                                      {hint}
                                    </Tag>
                                  ))
                                )}
                              </Space>
                            </div>
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.preventionControl')}</div>
                            <SmartSuggestionDropdown
                              triggerType="prevention_control"
                              context={{ failure_mode: fmNode.name, ...baseContext }}
                              fmeaId={fmeaId!}
                              value={pcName}
                              onChange={(val) => handleUpdateControl(causeNode.id, 'prevention', val)}
                              onSelect={(s) => handleUpdateControl(causeNode.id, 'prevention', s.name)}
                            />
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.detectionControl')}</div>
                            <SmartSuggestionDropdown
                              triggerType="detection_control"
                              context={{ failure_mode: fmNode.name, ...baseContext }}
                              fmeaId={fmeaId!}
                              value={dcName}
                              onChange={(val) => handleUpdateControl(causeNode.id, 'detection', val)}
                              onSelect={(s) => handleUpdateControl(causeNode.id, 'detection', s.name)}
                            />
                          </div>
                        );
                      })}
                      <Button size="small" danger onClick={() => handleDeleteFailureChain(fmNode.id)}>{t('wizard.failure.delete')}</Button>
                    </Space>
                  </div>
                );
              })}
              <Button size="small" type="dashed" onClick={() => handleAddFailure(func.id)}>{t('wizard.failure.addFailureChain')}</Button>
            </Card>
          );
        })}
      </div>
    );
  };
  const renderStep4 = () => (
    <RiskTable nodes={nodes} edges={edges} fmeaId={fmeaId!} onChange={(n, e) => updateGraphData(n, e)} />
  );
  const renderStep5 = () => {
    const rows = buildRows(nodes, edges);
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const highRiskRows = rows.map(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dcId = r.detectionControlIds[0];
      const dc = dcId ? nodeMap.get(dcId) : null;
      const s = getRowSeverity(r, nodeMap), o = cause?.occurrence || 0, d = dc?.detection || 0;
      return { row: r, s, o, d, ap: calculateAP(s, o, d) };
    }).filter(x => x.ap === 'H');

    if (highRiskRows.length === 0) {
      return <Result icon={<CheckCircleOutlined />} title={t('wizard.optimization.noOptimization')} subTitle={t('wizard.optimization.noOptimizationHint')} />;
    }

    const handleActionField = (row: FMEARow, field: string, value: unknown) => {
      const existingId = row.recommendedActionIds[0];
      if (existingId) {
        updateGraphData(nodes.map(n => n.id === existingId ? { ...n, [field]: value } : n), edges);
        return;
      }
      const raId = `w${crypto.randomUUID()}_ra`;
      const newNode: GraphNode = { id: raId, type: 'RecommendedAction', name: '', severity: 0, occurrence: 0, detection: 0, [field]: value };
      const sourceId = row.failureCauseNodeId || row.failureModeNodeId;
      updateGraphData([...nodes, newNode], [...edges, { source: sourceId, target: raId, type: 'OPTIMIZED_BY' }]);
    };

    const statusOptions = [
      { value: 'open', label: t('wizard.optimization.statusOptions.open') },
      { value: 'undecided', label: t('wizard.optimization.statusOptions.undecided') },
      { value: 'planned', label: t('wizard.optimization.statusOptions.planned') },
      { value: 'done', label: t('wizard.optimization.statusOptions.done') },
      { value: 'notExecuted', label: t('wizard.optimization.statusOptions.notExecuted') },
    ];

    return (
      <div>
        <Paragraph style={{ color: '#cf1322' }}>{t('wizard.optimization.mustOptimize', { count: highRiskRows.length })}</Paragraph>
        {highRiskRows.map(({ row: r, s, o, d }) => {
          const fm = nodeMap.get(r.failureModeNodeId);
          const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
          const raId = r.recommendedActionIds[0];
          const ra = raId ? nodeMap.get(raId) : null;
          const revisedS = ra?.revised_severity || 0;
          const revisedO = ra?.revised_occurrence || 0;
          const revisedD = ra?.revised_detection || 0;
          const revisedAp = calculateAP(revisedS || s, revisedO || o, revisedD || d);
          const apColor = revisedAp === 'H' ? 'red' : revisedAp === 'M' ? 'orange' : 'green';
          const toDate = (v?: string) => (v ? dayjs(v) : undefined);

          return (
            <Card key={r.key} size="small" style={{ marginBottom: 12 }}
              title={<Space wrap align="center">
                <Tag color="red">{t('wizard.optimization.apBadge')}</Tag>
                <span>{fm?.name || ''}</span>
                <span style={{ color: 'var(--qf-text-tertiary)', fontSize: 12 }}>S{s} O{o} D{d}</span>
              </Space>}>
              <Row gutter={[12, 8]}>
                <Col span={24}>
                  <Field label={t('wizard.optimization.measure')}>
                    <Input.TextArea rows={2} placeholder={t('wizard.optimization.measurePlaceholder')} value={ra?.name || ''}
                      onChange={e => handleActionField(r, 'name', e.target.value)} />
                  </Field>
                </Col>
                <Col xs={24} sm={8}>
                  <Field label={t('wizard.optimization.responsible')}>
                    <Input size="small" placeholder={t('wizard.optimization.responsiblePlaceholder')}
                      value={ra?.responsible || ''} onChange={e => handleActionField(r, 'responsible', e.target.value)} />
                  </Field>
                </Col>
                <Col xs={24} sm={8}>
                  <Field label={t('wizard.optimization.dueDate')}>
                    <DatePicker size="small" style={{ width: '100%' }} placeholder={t('wizard.optimization.dueDate')} value={toDate(ra?.due_date)}
                      onChange={v => handleActionField(r, 'due_date', v ? v.format('YYYY-MM-DD') : '')} />
                  </Field>
                </Col>
                <Col xs={24} sm={8}>
                  <Field label={t('wizard.optimization.status')}>
                    <Select size="small" style={{ width: '100%' }} options={statusOptions} allowClear
                      value={ra?.status} onChange={v => handleActionField(r, 'status', v)} />
                  </Field>
                </Col>
                <Col span={24}>
                  <Field label={t('wizard.optimization.actionTaken')}>
                    <Input.TextArea rows={2} placeholder={t('wizard.optimization.actionTakenPlaceholder')}
                      value={ra?.action_taken || ''} onChange={e => handleActionField(r, 'action_taken', e.target.value)} />
                  </Field>
                </Col>
                <Col xs={24} sm={8}>
                  <Field label={t('wizard.optimization.completionDate')}>
                    <DatePicker size="small" style={{ width: '100%' }} placeholder={t('wizard.optimization.completionDate')} value={toDate(ra?.completion_date)}
                      onChange={v => handleActionField(r, 'completion_date', v ? v.format('YYYY-MM-DD') : '')} />
                  </Field>
                </Col>
                <Col xs={24} sm={16}>
                  <Field label={t('wizard.optimization.revisedRatings')}>
                    <Space wrap>
                      <span>S'</span>
                      <InputNumber size="small" min={1} max={10} style={{ width: 56 }} value={revisedS || undefined}
                        onChange={v => handleActionField(r, 'revised_severity', (v ?? 0) as number)} />
                      <span>O'</span>
                      <InputNumber size="small" min={1} max={10} style={{ width: 56 }} value={revisedO || undefined}
                        onChange={v => handleActionField(r, 'revised_occurrence', (v ?? 0) as number)} />
                      <span>D'</span>
                      <InputNumber size="small" min={1} max={10} style={{ width: 56 }} value={revisedD || undefined}
                        onChange={v => handleActionField(r, 'revised_detection', (v ?? 0) as number)} />
                      <span>{t('wizard.optimization.revisedAp')}</span>
                      {revisedAp ? <Tag color={apColor}>{revisedAp}</Tag> : <Tag>-</Tag>}
                    </Space>
                  </Field>
                </Col>
              </Row>
            </Card>
          );
        })}
      </div>
    );
  };
  const renderStep6 = () => {
    const structCount = nodes.filter(n => STRUCTURE_TYPES.includes(n.type)).length;
    const funcCount = nodes.filter(n => FUNCTION_TYPES.includes(n.type)).length;
    const fmCount = nodes.filter(n => n.type === 'FailureMode').length;

    return (
      <Card size="small" style={{ marginBottom: 12 }}>
        <div>{t('wizard.confirm.structureNodes', { count: structCount })}</div>
        <div>{t('wizard.confirm.functionNodes', { count: funcCount })}</div>
        <div>{t('wizard.confirm.failureChains', { count: fmCount })}</div>
        <div>{t('wizard.confirm.totalNodes', { count: nodes.length })}</div>
        <div>{t('wizard.confirm.totalEdges', { count: edges.length })}</div>
      </Card>
    );
  };

  const STEP_RENDERERS: Record<number, () => React.ReactNode> = {
    0: renderStep0,
    1: renderStep1,
    2: renderStep2,
    3: renderStep3,
    4: renderStep4,
    5: renderStep5,
    6: renderStep6,
  };

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 16px', borderBottom: '1px solid var(--qf-border)' }}>
        <Title level={4} style={{ margin: 0 }}>
          {t('wizard.page.title')} — {fmea?.document_no}
        </Title>
        <Space>
          <span aria-live="polite">{saveStatusLabel[saveStatus]}</span>
          <Button onClick={handleBackToList} icon={<ArrowLeftOutlined />}>{t('wizard.page.backToList')}</Button>
          <Button type="primary" onClick={() => {
            const hash = computeHash(nodes, edges, wizardScope);
            immediateSave({ nodes, edges, wizardScope }, fmea?.title, hash);
          }} loading={saveStatus === 'saving'}>
            {t('wizard.page.saveDraft')}
          </Button>
        </Space>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{ width: 280, flexShrink: 0, overflow: 'auto', background: 'var(--qf-bg-panel)' }}>
          <WizardSidebar
            currentStep={currentStep}
            onStepClick={goToStep}
            completedSteps={completedSteps}
            maxReachableStep={maxReachableStep}
            warnings={validation.warnings}
            structureNodes={nodes}
            edges={edges}
          />
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
          <WizardGuidanceCard stepIndex={currentStep} />

          <div style={{ minHeight: 300 }}>
            {STEP_RENDERERS[currentStep]?.() || <div />}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--qf-border)' }}>
            {currentStep > 0 && (
              <Button onClick={() => goToStep(currentStep - 1)}>{t('wizard.page.prevStep')}</Button>
            )}
            {currentStep < 6 ? (
              <Button type="primary" onClick={() => goToStep(currentStep + 1)} loading={saveStatus === 'saving'}>
                {t('wizard.page.nextStep')}
              </Button>
            ) : (
              <Button type="primary" onClick={handleFinish} disabled={!canFinish} loading={saveStatus === 'saving'}>
                {t('wizard.page.finish')}
              </Button>
            )}
          </div>

          {currentStep === 6 && validation.warnings.length > 0 && (
            <div style={{ marginTop: 16, padding: 12, background: 'var(--qf-red-dim)', border: '1px solid var(--qf-red)', borderRadius: 'var(--qf-radius-md)' }}>
              <div style={{ fontWeight: 600, color: 'var(--qf-red)', marginBottom: 4 }}>{t('wizard.page.completionWarning')}</div>
              {validation.warnings.map(w => (
                <div key={w} style={{ color: 'var(--qf-red)' }}>• {t(`wizard.page.step${w + 1}Incomplete`)}</div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Modal
        open={conflictOpen}
        closable={false}
        maskClosable={false}
        title={t('wizard.page.conflictTitle')}
        footer={[
          <Button key="reload" type="primary" onClick={() => window.location.reload()}>
            {t('wizard.page.conflictReload')}
          </Button>,
        ]}
      >
        {t('wizard.page.conflictContent')}
      </Modal>
    </div>
  );
}
