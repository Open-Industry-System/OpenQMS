import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Modal, Spin, Typography, message, Input, Card, Tag, Empty, DatePicker, Select } from 'antd';
import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getFMEA, deleteFMEA } from '../../../api/fmea';
import type { FMEADocument, GraphNode, GraphEdge, WizardScope } from '../../../types';
import { useWizardSave, type SaveStatus } from '../../../hooks/useWizardSave';
import { usePfmeaWizardValidation } from '../../../hooks/usePfmeaWizardValidation';
import { buildRows, getRowSeverity } from '../../../utils/fmeaTable';
import { cascadeDeleteStructureNode } from '../../../utils/wizardCascadeDelete';
import WizardSidebar from '../../../components/pfmea/PFMEAWizardSidebar';
import WizardGuidanceCard from '../../../components/pfmea/PFMEAGuidanceCard';
import ScopeTagField from '../../../components/dfmea/ScopeTagField';
import type { ReactNode } from 'react';
import { rangeToTimeframe, timeframeToRange } from '../../../utils/wizardTimeframe';
import { parseScopeTokens } from '../../../utils/wizardScopeTokens';
import { orderStructureNodes } from '../../../utils/wizardStructureOrder';
import { ensureCauseControls } from '../../../utils/wizardGraphNormalize';

const { Title } = Typography;

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
    const hasOptimization = nodes.some(n => n.type === 'RecommendedAction');
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

  const renderStep2 = () => <div>{t('wizard.steps.2')}</div>;
  const renderStep3 = () => <div>{t('wizard.steps.3')}</div>;
  const renderStep4 = () => <div>{t('wizard.steps.4')}</div>;
  const renderStep5 = () => <div>{t('wizard.steps.5')}</div>;
  const renderStep6 = () => <div>{t('wizard.steps.6')}</div>;

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
