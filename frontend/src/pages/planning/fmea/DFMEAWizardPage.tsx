import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Modal, Spin, Typography, message, Input, Card, Tag, Empty, Table, InputNumber, Result } from 'antd';
import { ArrowLeftOutlined, PlusOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getFMEA, deleteFMEA } from '../../../api/fmea';
import type { FMEADocument, GraphNode, GraphEdge, WizardScope } from '../../../types';
import { useWizardSave, type SaveStatus } from '../../../hooks/useWizardSave';
import { useWizardValidation } from '../../../hooks/useWizardValidation';
import { useDfmeaRules } from '../../../utils/dfmeaRules';
import { buildRows, type FMEARow } from '../../../utils/fmeaTable';
import { cascadeDeleteStructureNode } from '../../../utils/wizardCascadeDelete';
import WizardSidebar from '../../../components/dfmea/WizardSidebar';
import WizardGuidanceCard from '../../../components/dfmea/WizardGuidanceCard';

const { Title, Paragraph } = Typography;

export default function DFMEAWizardPage() {
  const { id: fmeaId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation('dfmea');

  const [fmea, setFmea] = useState<FMEADocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [wizardScope, setWizardScope] = useState<WizardScope>({});
  const [currentStep, setCurrentStep] = useState(0);
  const completedSteps = useRef(new Set<number>());

  const { saveStatus, setLockVersion, debouncedSave, immediateSave, lastSavedHashRef } = useWizardSave({ fmeaId: fmeaId! });
  const validation = useWizardValidation(nodes, edges);
  const dfmeaRules = useDfmeaRules();

  // Refs for beforeunload handler — always hold latest values without re-registering listener
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const scopeRef = useRef(wizardScope);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);
  useEffect(() => { edgesRef.current = edges; }, [edges]);
  useEffect(() => { scopeRef.current = wizardScope; }, [wizardScope]);

  /** Stable hash of the full persisted state — captures every editable field
   *  (name, type, requirement, specification, S/O/D, optimization, scope). */
  const computeHash = (n: GraphNode[], e: GraphEdge[], s: WizardScope) =>
    JSON.stringify({ nodes: n, edges: e, scope: s });

  // Load FMEA document
  useEffect(() => {
    if (!fmeaId) return;
    getFMEA(fmeaId).then(doc => {
      if (doc.fmea_type !== 'DFMEA') {
        navigate(`/fmea/${doc.fmea_id}`, { replace: true });
        return;
      }
      const loadedNodes = doc.graph_data?.nodes || [];
      const loadedEdges = doc.graph_data?.edges || [];
      const loadedScope = doc.graph_data?.wizardScope || {};
      setFmea(doc);
      setNodes(loadedNodes);
      setEdges(loadedEdges);
      setWizardScope(loadedScope);
      setLockVersion(doc.lock_version);
      // Mark initial state as "clean" — hash captured at load time
      lastSavedHashRef.current = computeHash(loadedNodes, loadedEdges, loadedScope);
      setLoading(false);
    }).catch(() => {
      message.error('加载失败');
      navigate('/fmea');
    });
  }, [fmeaId, navigate, setLockVersion, lastSavedHashRef]);

  // beforeunload warning — compare live state hash vs last-successfully-saved hash
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      const hash = computeHash(nodesRef.current, edgesRef.current, scopeRef.current);
      if (hash !== lastSavedHashRef.current) {
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []); // lastSavedHashRef is a ref — always reads latest without re-registering

  const updateGraphData = useCallback((newNodes: GraphNode[], newEdges: GraphEdge[], newScope?: WizardScope) => {
    setNodes(newNodes);
    setEdges(newEdges);
    if (newScope !== undefined) setWizardScope(newScope);
    // Compute hash at enqueue time — NOT at save-success time
    const hash = computeHash(newNodes, newEdges, newScope ?? wizardScope);
    debouncedSave({ nodes: newNodes, edges: newEdges, wizardScope: newScope ?? wizardScope }, fmea?.title, hash);
  }, [debouncedSave, wizardScope, fmea?.title]);

  const goToStep = useCallback((step: number) => {
    completedSteps.current.add(currentStep);
    setCurrentStep(step);
  }, [currentStep]);

  const handleFinish = async () => {
    const completedScope = { ...wizardScope, wizard_completed: true };
    const hash = computeHash(nodes, edges, completedScope);
    const success = await immediateSave({ nodes, edges, wizardScope: completedScope }, fmea?.title, hash);
    if (!success) return;
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
    } else {
      navigate('/fmea');
    }
  };

  const canFinish = validation.warnings.length === 0
    && validation.step3Complete
    && validation.step4Complete
    && validation.step5Complete;

  const saveStatusLabel: Record<SaveStatus, string> = {
    idle: '',
    saving: t('wizard.page.saveSaving'),
    saved: t('wizard.page.saveSaved'),
    error: t('wizard.page.saveError'),
  };

  // Step 0 — 5T Scope
  const renderStep0 = () => (
    <div style={{ display: 'grid', gap: 12 }}>
      <Input placeholder={t('wizard.scope.team')} value={wizardScope.team || ''}
        onChange={e => updateGraphData(nodes, edges, { ...wizardScope, team: e.target.value })} />
      <Input placeholder={t('wizard.scope.timeframe')} value={wizardScope.timeframe || ''}
        onChange={e => updateGraphData(nodes, edges, { ...wizardScope, timeframe: e.target.value })} />
      <Input placeholder={t('wizard.scope.tool')} value={wizardScope.tool || ''}
        onChange={e => updateGraphData(nodes, edges, { ...wizardScope, tool: e.target.value })} />
      <Input placeholder={t('wizard.scope.task')} value={wizardScope.task || ''}
        onChange={e => updateGraphData(nodes, edges, { ...wizardScope, task: e.target.value })} />
      <Input placeholder={t('wizard.scope.trend')} value={wizardScope.trend || ''}
        onChange={e => updateGraphData(nodes, edges, { ...wizardScope, trend: e.target.value })} />
    </div>
  );

  // Step 1 — Structure Analysis
  const renderStep1 = () => {
    const structureNodes = nodes.filter(n => ['System', 'Subsystem', 'Component', 'Interface', 'DesignParameter'].includes(n.type));
    const CHILD_TYPE: Record<string, string> = { System: 'Subsystem', Subsystem: 'Component' };
    const CHILD_EDGE_TYPE: Record<string, string> = { System: 'HAS_PROCESS_STEP', Subsystem: 'HAS_WORK_ELEMENT' };

    const handleAddNode = (type: string, parentId?: string) => {
      const newNode: GraphNode = {
        id: `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_${type.toLowerCase()}`,
        type, name: t(`wizard.typeLabels.${type}`, { defaultValue: type }),
        severity: 0, occurrence: 0, detection: 0,
        ...(type === 'Interface' ? { interface_type: 'physical' } : {}),
      };
      const newEdges = parentId
        ? [...edges, { source: parentId, target: newNode.id, type: CHILD_EDGE_TYPE[nodes.find(n => n.id === parentId)?.type || 'System'] || 'HAS_PROCESS_STEP' }]
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

    const typeLabel = (type: string) => t(`wizard.typeLabels.${type}`, { defaultValue: type });
    const TYPE_COLORS: Record<string, string> = { System: 'red', Subsystem: 'orange', Component: 'green', Interface: 'purple', DesignParameter: 'blue' };

    return (
      <div>
        <Space style={{ marginBottom: 12 }}>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('System')}>{t('wizard.structure.addSystem')}</Button>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('Interface')}>{t('wizard.structure.addInterface')}</Button>
        </Space>
        {structureNodes.length === 0 && <Empty description={t('wizard.structure.empty')} />}
        {structureNodes.map(node => (
          <Card key={node.id} size="small" style={{ marginBottom: 8, marginLeft: node.type === 'Subsystem' ? 20 : node.type === 'Component' ? 40 : 0 }}>
            <Space>
              <Tag color={TYPE_COLORS[node.type]}>{typeLabel(node.type)}</Tag>
              <Input size="small" value={node.name} style={{ width: 200 }}
                onChange={e => handleRenameNode(node.id, e.target.value)} />
              {CHILD_TYPE[node.type] && (
                <Button size="small" onClick={() => handleAddNode(CHILD_TYPE[node.type], node.id)}>
                  + {typeLabel(CHILD_TYPE[node.type])}
                </Button>
              )}
              <Button size="small" danger onClick={() => handleDeleteNode(node.id)}>{t('wizard.structure.delete')}</Button>
            </Space>
          </Card>
        ))}
      </div>
    );
  };

  // Step 2 — Function Analysis
  const renderStep2 = () => {
    const components = nodes.filter(n => n.type === 'Component');
    if (components.length === 0) return <Empty description={t('wizard.function.title') + ' — ' + t('wizard.structure.empty')} />;

    const handleAddFunction = (compId: string) => {
      const funcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_func`;
      const funcNode: GraphNode = {
        id: funcId, type: 'ProcessWorkElementFunction', name: '',
        requirement: '', specification: '', severity: 0, occurrence: 0, detection: 0,
      };
      updateGraphData([...nodes, funcNode], [...edges, { source: compId, target: funcId, type: 'HAS_FUNCTION' }]);
    };

    const handleUpdateFunction = (funcId: string, field: 'name' | 'requirement' | 'specification', value: string) => {
      updateGraphData(nodes.map(n => n.id === funcId ? { ...n, [field]: value } : n), edges);
    };

    return (
      <div>
        {components.map(comp => {
          const funcEdges = edges.filter(e => e.source === comp.id && e.type === 'HAS_FUNCTION');
          const funcNodes = funcEdges.map(e => nodes.find(n => n.id === e.target)).filter(Boolean) as GraphNode[];
          return (
            <Card key={comp.id} size="small" title={comp.name} style={{ marginBottom: 12 }}>
              {funcNodes.map(fn => (
                <div key={fn.id} style={{ marginBottom: 8 }}>
                  <Input placeholder={t('wizard.function.functionDesc')} value={fn.name}
                    onChange={e => handleUpdateFunction(fn.id, 'name', e.target.value)} style={{ marginBottom: 4 }} />
                  <Input placeholder={t('wizard.function.requirement')} value={fn.requirement || ''}
                    onChange={e => handleUpdateFunction(fn.id, 'requirement', e.target.value)} style={{ marginBottom: 4 }} />
                  <Input placeholder={t('wizard.function.specification')} value={fn.specification || ''}
                    onChange={e => handleUpdateFunction(fn.id, 'specification', e.target.value)} />
                </div>
              ))}
              <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={() => handleAddFunction(comp.id)}>
                {t('wizard.failure.addFailureMode').replace('失效模式', '功能')}
              </Button>
            </Card>
          );
        })}
      </div>
    );
  };

  // Step 3 — Failure Analysis
  const renderStep3 = () => {
    const { generateFailureModes, suggestFailureChain } = dfmeaRules;
    const functions = nodes.filter(n => ['ProcessWorkElementFunction', 'ProcessItemFunction', 'ProcessStepFunction'].includes(n.type));

    if (functions.length === 0) return <Empty description={t('wizard.failure.title') + ' — ' + t('wizard.function.title')} />;

    const handleAddFailure = (funcId: string, mode?: string, effect?: string, cause?: string) => {
      const fmId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_fm`;
      const feId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_fe`;
      const fcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_fc`;
      const dcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_dc`;
      const newNodes: GraphNode[] = [
        { id: fmId, type: 'FailureMode', name: mode || t('wizard.failure.newFailureMode'), severity: 0, occurrence: 0, detection: 0 },
        { id: feId, type: 'FailureEffect', name: effect || '', severity: 0, occurrence: 0, detection: 0 },
        { id: fcId, type: 'FailureCause', name: cause || '', severity: 0, occurrence: 0, detection: 0 },
        // DetectionControl created up-front so Step 4 D is editable and AP is computable.
        { id: dcId, type: 'DetectionControl', name: t('wizard.optimization.detectionPlaceholder'), severity: 0, occurrence: 0, detection: 0 },
      ];
      const newEdges: GraphEdge[] = [
        { source: funcId, target: fmId, type: 'HAS_FAILURE_MODE' },
        { source: fmId, target: feId, type: 'EFFECT_OF' },
        { source: fcId, target: fmId, type: 'CAUSE_OF' },
        { source: fcId, target: dcId, type: 'DETECTED_BY' },
      ];
      updateGraphData([...nodes, ...newNodes], [...edges, ...newEdges]);
    };

    const handleDeleteFailureChain = (failureModeId: string) => {
      const toDelete = new Set<string>([failureModeId]);
      const edgesToDelete = new Set<string>();

      // Find FailureEffect (outgoing EFFECT_OF)
      for (const e of edges) {
        if (e.source === failureModeId && e.type === 'EFFECT_OF') {
          toDelete.add(e.target);
          edgesToDelete.add(`${e.source}->${e.target}->${e.type}`);
        }
      }

      // Find FailureCause (incoming CAUSE_OF)
      for (const e of edges) {
        if (e.target === failureModeId && e.type === 'CAUSE_OF') {
          toDelete.add(e.source);
          edgesToDelete.add(`${e.source}->${e.target}->${e.type}`);
          // Find PreventionControl and DetectionControl from this cause
          for (const e2 of edges) {
            if (e2.source === e.source && (e2.type === 'PREVENTED_BY' || e2.type === 'DETECTED_BY')) {
              // Only delete control nodes that are ONLY connected to this cause
              const otherParents = edges.filter(e3 => e3.target === e2.target && e3.source !== e.source);
              if (otherParents.length === 0) {
                toDelete.add(e2.target);
              }
              edgesToDelete.add(`${e2.source}->${e2.target}->${e2.type}`);
            }
          }
        }
      }

      // Remove edges targeting deleted nodes
      for (const e of edges) {
        if (toDelete.has(e.source) || toDelete.has(e.target)) {
          edgesToDelete.add(`${e.source}->${e.target}->${e.type}`);
        }
      }

      const filteredNodes = nodes.filter(n => !toDelete.has(n.id));
      const filteredEdges = edges.filter(e => !edgesToDelete.has(`${e.source}->${e.target}->${e.type}`));
      updateGraphData(filteredNodes, filteredEdges);
    };

    const handleUpdateNodeField = (nodeId: string, field: string, value: string) => {
      updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, [field]: value } : n), edges);
    };

    return (
      <div>
        {functions.map(func => {
          const fmEdges = edges.filter(e => e.source === func.id && e.type === 'HAS_FAILURE_MODE');
          const fmNodes = fmEdges.map(e => nodes.find(n => n.id === e.target)).filter(Boolean) as GraphNode[];
          const suggestedModes = generateFailureModes(func.name);

          return (
            <Card key={func.id} size="small" title={func.name} style={{ marginBottom: 12 }}>
              {fmNodes.length === 0 && suggestedModes.length > 0 && (
                <div style={{ marginBottom: 8, padding: 8, background: '#f6ffed', borderRadius: 4 }}>
                  <Tag color="green">{t('wizard.failure.recommended')}</Tag>
                  <span style={{ fontSize: 12 }}> {t('wizard.failure.autoRecommend')}</span>
                  <Space size={4} style={{ marginTop: 4 }}>
                    {suggestedModes.slice(0, 3).map(mode => (
                      <Button key={mode} size="small" onClick={() => {
                        const chain = suggestFailureChain(mode);
                        handleAddFailure(func.id, mode, chain.effects[0] || '', chain.causes[0] || '');
                      }}>{mode}</Button>
                    ))}
                  </Space>
                </div>
              )}
              {fmNodes.map(fmNode => {
                const effectEdge = edges.find(e => e.source === fmNode.id && e.type === 'EFFECT_OF');
                const effectNode = effectEdge ? nodes.find(n => n.id === effectEdge!.target) : null;
                const causeEdges = edges.filter(e => e.target === fmNode.id && e.type === 'CAUSE_OF');
                const causeNodes = causeEdges.map(e => nodes.find(n => n.id === e.source)).filter(Boolean) as GraphNode[];

                return (
                  <div key={fmNode.id} style={{ marginBottom: 8, padding: 8, background: '#f5f5f5', borderRadius: 4 }}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Input size="small" value={fmNode.name} addonBefore={t('wizard.failure.failureMode')}
                        onChange={e => handleUpdateNodeField(fmNode.id, 'name', e.target.value)} />
                      <Input size="small" value={effectNode?.name || ''} addonBefore={t('wizard.failure.failureEffect')}
                        onChange={e => effectNode && handleUpdateNodeField(effectNode.id, 'name', e.target.value)} />
                      {causeNodes.map(causeNode => (
                        <Input key={causeNode.id} size="small" value={causeNode.name} addonBefore={t('wizard.failure.failureCause')}
                          onChange={e => handleUpdateNodeField(causeNode.id, 'name', e.target.value)} />
                      ))}
                      <Button size="small" danger onClick={() => handleDeleteFailureChain(fmNode.id)}>{t('wizard.failure.delete')}</Button>
                    </Space>
                  </div>
                );
              })}
              <Button size="small" type="dashed" onClick={() => handleAddFailure(func.id)}>{t('wizard.failure.addFailureMode')}</Button>
            </Card>
          );
        })}
      </div>
    );
  };

  // Step 4 — Risk Analysis (S/O/D)
  const renderStep4 = () => {
    const { analyzeRisk } = dfmeaRules;
    const rows = buildRows(nodes, edges);
    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    if (rows.length === 0) return <Empty description={t('wizard.risk.empty')} />;

    const handleUpdateRisk = (nodeId: string, field: 'severity' | 'occurrence' | 'detection', value: number) => {
      updateGraphData(nodes.map(n => n.id === nodeId ? { ...n, [field]: value } : n), edges);
    };

    return (
      <Table size="small" dataSource={rows} rowKey="key" pagination={false}
        columns={[
          { title: t('wizard.failure.failureMode'), dataIndex: 'key', width: 140, render: (_: unknown, r: FMEARow) => {
            const fm = nodeMap.get(r.failureModeNodeId);
            return fm?.name || '';
          }},
          { title: 'S', width: 60, render: (_: unknown, r: FMEARow) => {
            const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
            return <InputNumber size="small" min={1} max={10} value={effect?.severity || undefined}
              style={{ width: 50 }} onChange={val => effect && handleUpdateRisk(effect.id, 'severity', val || 0)} />;
          }},
          { title: 'O', width: 60, render: (_: unknown, r: FMEARow) => {
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            return <InputNumber size="small" min={1} max={10} value={cause?.occurrence || undefined}
              style={{ width: 50 }} onChange={val => cause && handleUpdateRisk(cause.id, 'occurrence', val || 0)} />;
          }},
          { title: 'D', width: 60, render: (_: unknown, r: FMEARow) => {
            const dcId = r.detectionControlIds[0];
            const dc = dcId ? nodeMap.get(dcId) : null;
            return <InputNumber size="small" min={1} max={10} value={dc?.detection || undefined}
              style={{ width: 50 }} onChange={val => dc && handleUpdateRisk(dc.id, 'detection', val || 0)} />;
          }},
          { title: 'AP', width: 80, render: (_: unknown, r: FMEARow) => {
            const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            const dcId = r.detectionControlIds[0];
            const dc = dcId ? nodeMap.get(dcId) : null;
            const s = effect?.severity || 0, o = cause?.occurrence || 0, d = dc?.detection || 0;
            const { ap } = analyzeRisk(s, o, d);
            return <Tag color={ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'green'}>{ap || '-'}</Tag>;
          }},
        ]}
      />
    );
  };

  // Step 5 — Optimization
  const renderStep5 = () => {
    const { suggestMeasures, analyzeRisk } = dfmeaRules;
    const rows = buildRows(nodes, edges);
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const highRiskRows = rows.filter(r => {
      const effect = r.failureEffectNodeId ? nodeMap.get(r.failureEffectNodeId) : null;
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dcId = r.detectionControlIds[0];
      const dc = dcId ? nodeMap.get(dcId) : null;
      const s = effect?.severity || 0, o = cause?.occurrence || 0, d = dc?.detection || 0;
      return analyzeRisk(s, o, d).ap === 'H';
    });

    if (highRiskRows.length === 0) {
      return <Result icon={<CheckCircleOutlined />} title={t('wizard.optimization.noOptimization')} subTitle={t('wizard.optimization.noOptimizationHint')} />;
    }

    const handleAddOptimization = (row: FMEARow, type: 'prevention' | 'detection', value: string) => {
      const causeId = row.failureCauseNodeId;
      if (!causeId) return;

      let newNodes = [...nodes];
      const newEdges = [...edges];

      if (type === 'prevention') {
        const existingPcIds = edges
          .filter(e => e.source === causeId && e.type === 'PREVENTED_BY')
          .map(e => e.target);
        if (existingPcIds.length > 0) {
          newNodes = newNodes.map(n => n.id === existingPcIds[0] ? { ...n, name: value } : n);
        } else {
          const pcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_pc`;
          newNodes.push({ id: pcId, type: 'PreventionControl', name: value, severity: 0, occurrence: 0, detection: 0 });
          newEdges.push({ source: causeId, target: pcId, type: 'PREVENTED_BY' });
        }
      } else {
        const existingDcIds = edges
          .filter(e => e.source === causeId && e.type === 'DETECTED_BY')
          .map(e => e.target);
        if (existingDcIds.length > 0) {
          newNodes = newNodes.map(n => n.id === existingDcIds[0] ? { ...n, name: value } : n);
        } else {
          const dcId = `w${Date.now()}_${Math.random().toString(36).slice(2, 8)}_dc`;
          newNodes.push({ id: dcId, type: 'DetectionControl', name: value, severity: 0, occurrence: 0, detection: 0 });
          newEdges.push({ source: causeId, target: dcId, type: 'DETECTED_BY' });
        }
      }

      updateGraphData(newNodes, newEdges);
    };

    return (
      <div>
        <Paragraph style={{ color: '#cf1322' }}>{t('wizard.optimization.mustOptimize', { count: highRiskRows.length })}</Paragraph>
        {highRiskRows.map(r => {
          const fm = nodeMap.get(r.failureModeNodeId);
          const measures = suggestMeasures(fm?.name || '', 'H');
          const causeId = r.failureCauseNodeId;
          const existingPc = causeId ? edges.find(e => e.source === causeId && e.type === 'PREVENTED_BY') : null;
          const existingDc = causeId ? edges.find(e => e.source === causeId && e.type === 'DETECTED_BY') : null;
          const pcName = existingPc ? nodeMap.get(existingPc.target)?.name || '' : '';
          const dcName = existingDc ? nodeMap.get(existingDc.target)?.name || '' : '';

          return (
            <Card key={r.key} size="small" title={fm?.name || 'Failure Mode'} style={{ marginBottom: 12 }}>
              <Input.TextArea rows={2} placeholder={measures.prevention.join(' / ')} value={pcName}
                onChange={e => handleAddOptimization(r, 'prevention', e.target.value)} style={{ marginBottom: 8 }} />
              <Input.TextArea rows={2} placeholder={measures.detection.join(' / ')} value={dcName}
                onChange={e => handleAddOptimization(r, 'detection', e.target.value)} />
            </Card>
          );
        })}
      </div>
    );
  };

  // Step 6 — Confirmation
  const renderStep6 = () => {
    const structCount = nodes.filter(n => ['System', 'Subsystem', 'Component'].includes(n.type)).length;
    const funcCount = nodes.filter(n => n.type === 'ProcessWorkElementFunction').length;
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
      {/* Header */}
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

      {/* Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left sidebar */}
        <div style={{ width: 280, flexShrink: 0, overflow: 'auto', background: 'var(--qf-bg-panel)' }}>
          <WizardSidebar
            currentStep={currentStep}
            onStepClick={goToStep}
            completedSteps={completedSteps.current}
            warnings={validation.warnings}
            structureNodes={nodes}
            edges={edges}
          />
        </div>

        {/* Right content area */}
        <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
          <WizardGuidanceCard stepIndex={currentStep} />

          {/* Step content — renderers added in Tasks 10-12 */}
          <div style={{ minHeight: 300 }}>
            {STEP_RENDERERS[currentStep]?.() || <div />}
          </div>

          {/* Bottom navigation */}
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

          {/* Validation warnings for finish button */}
          {currentStep === 6 && validation.warnings.length > 0 && (
            <div style={{ marginTop: 16, padding: 12, background: '#fff2f0', border: '1px solid #ffccc7', borderRadius: 4 }}>
              <div style={{ fontWeight: 600, color: '#cf1322', marginBottom: 4 }}>{t('wizard.page.completionWarning')}</div>
              {validation.warnings.map(w => (
                <div key={w} style={{ color: '#cf1322' }}>• {t(`wizard.page.step${w + 1}Incomplete`)}</div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}