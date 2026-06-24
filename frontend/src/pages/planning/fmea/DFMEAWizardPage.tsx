import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Modal, Spin, Typography, message, Input, Card, Tag, Empty, Table, InputNumber, Result, DatePicker } from 'antd';
import { ArrowLeftOutlined, PlusOutlined, CheckCircleOutlined, BulbOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getFMEA, deleteFMEA } from '../../../api/fmea';
import type { FMEADocument, GraphNode, GraphEdge, WizardScope } from '../../../types';
import { useWizardSave, type SaveStatus } from '../../../hooks/useWizardSave';
import { useWizardValidation } from '../../../hooks/useWizardValidation';
import { useDfmeaRules } from '../../../utils/dfmeaRules';
import { buildRows, getRowSeverity, getProcessChain, type FMEARow } from '../../../utils/fmeaTable';
import { cascadeDeleteStructureNode } from '../../../utils/wizardCascadeDelete';
import WizardSidebar from '../../../components/dfmea/WizardSidebar';
import WizardGuidanceCard from '../../../components/dfmea/WizardGuidanceCard';
import ScopeTagField from '../../../components/dfmea/ScopeTagField';
import SmartSuggestionDropdown from '../../../components/dfmea/SmartSuggestionDropdown';
import type { ReactNode } from 'react';
import { rangeToTimeframe, timeframeToRange } from '../../../utils/wizardTimeframe';
import { parseScopeTokens } from '../../../utils/wizardScopeTokens';
import { toolsRequiringNodeType, pickParamParent, buildAttachedParamNode, type StructureNodeType } from '../../../utils/wizardToolStructure';
import { orderStructureNodes } from '../../../utils/wizardStructureOrder';
import { createWizardFailureChain, ensureCauseControls } from '../../../utils/wizardGraphNormalize';

const { Title, Paragraph } = Typography;

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div style={{ marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}

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
  const [conflictOpen, setConflictOpen] = useState(false);

  /** Steps whose data is already present in the loaded draft — used for the
   *  sidebar's status checkmarks AND to derive how far forward the user may
   *  jump. Derived from graph data (not a session ref) so it survives save →
   *  exit → reopen: a saved draft's earlier steps stay navigable. */
  const completedSteps = useMemo(() => {
    const set = new Set<number>();
    const hasScope = !!(wizardScope.team || wizardScope.timeframe || wizardScope.tool || wizardScope.task || wizardScope.trend);
    const hasAny = nodes.length > 0;
    const hasStructure = nodes.some(n => ['System', 'Subsystem', 'Component', 'Interface', 'DesignParameter'].includes(n.type));
    const hasFunction = nodes.some(n => ['ProcessWorkElementFunction', 'ProcessItemFunction', 'ProcessStepFunction'].includes(n.type));
    const hasFailure = nodes.some(n => n.type === 'FailureMode');
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const hasRating = buildRows(nodes, edges).some(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dc = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
      return getRowSeverity(r, nodeMap) > 0 || (cause?.occurrence ?? 0) > 0 || (dc?.detection ?? 0) > 0;
    });
    const hasOptimization = nodes.some(n => (n.type === 'PreventionControl' || n.type === 'DetectionControl') && (n.name ?? '').trim());
    if (hasScope || hasAny) set.add(0);
    if (hasStructure) set.add(1);
    if (hasFunction) set.add(2);
    if (hasFailure) set.add(3);
    if (hasRating) set.add(4);
    if (hasOptimization) set.add(5);
    return set;
  }, [nodes, edges, wizardScope]);

  /** Furthest reached step + 1 — the step the user is about to work on next.
   *  Forward sidebar jumps are allowed up to and including this step. */
  const maxReachableStep = useMemo(() => {
    let furthest = -1;
    for (let i = 0; i <= 6; i++) if (completedSteps.has(i)) furthest = i;
    return Math.min(furthest + 1, 6);
  }, [completedSteps]);

  const { saveStatus, setLockVersion, debouncedSave, immediateSave, lastSavedHashRef } = useWizardSave({
    fmeaId: fmeaId!,
    onConflict: () => setConflictOpen(true),
  });
  const toolStructureMap = t('wizard.scope.toolStructureMap', { returnObjects: true }) as Record<string, string>;
  const selectedTools = parseScopeTokens(wizardScope.tool || '');
  const validation = useWizardValidation(nodes, edges, selectedTools, toolStructureMap);
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
      // setLockVersion FIRST: useWizardSave.lockVersionRef defaults to 0; if
      // ensureCauseControls triggers immediateSave before this runs, the save
      // would go out with lock_version:0 and 409.
      setLockVersion(doc.lock_version);
      // Baseline hash = pre-normalization loaded state (backend's current
      // state). Kept as the "clean" reference; NOT overwritten with the
      // normalized hash — see below.
      lastSavedHashRef.current = computeHash(loadedNodes, loadedEdges, loadedScope);
      // Normalize legacy drafts: every FailureCause gets a PC + DC so Step 5's
      // O/D editors always have a node to write to.
      const { nodes: normNodes, edges: normEdges, changed } = ensureCauseControls(loadedNodes, loadedEdges);
      setFmea(doc);
      setNodes(normNodes);
      setEdges(normEdges);
      setWizardScope(loadedScope);
      setLoading(false);
      // If normalization added nodes/edges, persist the fix to the backend.
      // Pass the NORMALIZED hash as dataHash: the save hook writes it into
      // lastSavedHashRef only on SUCCESS (useWizardSave.ts:84). On failure,
      // lastSavedHashRef stays at the pre-normalization baseline, so the live
      // (normalized) state differs from it and beforeunload will warn — the
      // user is not silently dropped despite the backend not being fixed.
      if (changed) {
        const normalizedHash = computeHash(normNodes, normEdges, loadedScope);
        immediateSave({ nodes: normNodes, edges: normEdges, wizardScope: loadedScope }, doc.title, normalizedHash);
      }
    }).catch((err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } } };
      message.error(e?.response?.data?.detail || t('wizard.page.loadFailed'));
      navigate('/fmea');
    });
    // t 用于错误提示文案，但不应触发重载（否则切换语言会重拉文档、丢失未保存的 wizard 编辑）
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    setCurrentStep(step);
  }, []);

  const handleFinish = async () => {
    const completedScope = { ...wizardScope, wizard_completed: true };
    const hash = computeHash(nodes, edges, completedScope);
    const success = await immediateSave({ nodes, edges, wizardScope: completedScope }, fmea?.title, hash);
    if (!success) {
      // Save hook already surfaced the underlying error (conflict modal or
      // error toast). Don't navigate — the finish did not persist.
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
    // Non-empty draft: if there are unsaved changes (including a normalization
    // save that failed/in-flight — lastSavedHashRef still at pre-normalization
    // baseline while live state is normalized), confirm before leaving.
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

  // Step 0 — 5T Scope
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
            triggerType="dfmea_tool"
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
            triggerType="dfmea_trend"
            fmeaId={fmeaId!}
            context={{ fmea_title: fmea?.title, product_line_code: fmea?.product_line_code ?? '', task: wizardScope.task || '', team: wizardScope.team || '' }}
          />
        </Field>
      </div>
    );
  };

  // Step 1 — Structure Analysis
  const renderStep1 = () => {
    const structureNodes = nodes.filter(n => ['System', 'Subsystem', 'Component', 'Interface', 'DesignParameter'].includes(n.type));
    const CHILD_TYPE: Record<string, string> = { System: 'Subsystem', Subsystem: 'Component' };
    const CHILD_EDGE_TYPE: Record<string, string> = { System: 'HAS_PROCESS_STEP', Subsystem: 'HAS_WORK_ELEMENT' };

    const handleAddNode = (type: string, parentId?: string) => {
      const newNode: GraphNode = {
        id: `w${crypto.randomUUID()}_${type.toLowerCase()}`,
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

    const addAttachedParamNode = (nodeType: StructureNodeType, parentId?: string) => {
      // Interface/DesignParameter 须通过 HAS_PARAMETER 依附结构节点（不复用 handleAddNode：
      // 后者无 parent 建游离节点、CHILD_EDGE_TYPE 不含 HAS_PARAMETER）。
      // 挂接逻辑由 wizardToolStructure 的纯函数承担（pickParamParent + buildAttachedParamNode），
      // 便于单测；此处是薄包装。
      // parentId 由结构卡片上的「+ 接口 / + 设计参数」按钮传入，让用户显式选择挂接到
      // 哪个 System/Subsystem/Component；省略时回退到 pickParamParent 自动选取。
      const parent = parentId ? nodes.find(n => n.id === parentId) : pickParamParent(nodes);
      if (!parent) {
        message.warning(t('wizard.scope.toolGuideNeedStructure'));
        return;
      }
      const { node, edge } = buildAttachedParamNode(parent, nodeType, () => `w${crypto.randomUUID()}_${nodeType.toLowerCase()}`);
      const newNode: GraphNode = { ...node, name: t(`wizard.typeLabels.${nodeType}`, { defaultValue: nodeType }) };
      updateGraphData([...nodes, newNode], [...edges, edge]);
    };

    // 工具引导：所选结构类工具、且对应 nodeType 无 HAS_PARAMETER 挂接实例时，提示+一键创建。
    // 挂接判定与 structureGapsForTools 一致：须 source 存在且为结构节点。
    const attachedCount = (nodeType: StructureNodeType) =>
      edges.filter(ed => ed.type === 'HAS_PARAMETER'
        && nodes.find(nd => nd.id === ed.target)?.type === nodeType
        && ['System', 'Subsystem', 'Component'].includes(nodes.find(nd => nd.id === ed.source)?.type ?? '')).length;
    const guideNodeTypes: StructureNodeType[] = attachedCount('Interface') === 0 ? ['Interface'] : [];
    if (attachedCount('DesignParameter') === 0) guideNodeTypes.push('DesignParameter');
    const guideRows = guideNodeTypes
      .map(nt => {
        const tools = toolsRequiringNodeType(selectedTools, toolStructureMap, nt);
        return tools.length > 0 ? { nodeType: nt, tool: tools[0] } : null;
      })
      .filter((r): r is { nodeType: StructureNodeType; tool: string } => r !== null);

    // Derive depth from graph edges (System=0, Subsystem=1, Component=2) so
    // every child — including Interface/DesignParameter, which carry no descent
    // edge of their own — inherits its parent's depth + 1 instead of falling
    // back to 0. Sort by depth so children render under their parents.
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
    // Interface/DesignParameter attach to a structure node via HAS_PARAMETER —
    // inherit that parent's depth + 1 so they indent under their host.
    const paramParentOf: Record<string, string> = {};
    for (const e of edges) {
      if (e.type === 'HAS_PARAMETER') paramParentOf[e.target] = e.source;
    }
    const depthOfAny = (node: GraphNode): number => {
      if (childToParent[node.id]) return depthOf(node.id);
      if (paramParentOf[node.id]) return depthOf(paramParentOf[node.id]) + 1;
      return 0;
    };
    // DFS order from edges: each parent immediately followed by its own
    // subtree, so a subsystem's components render under *that* subsystem
    // instead of the next one (depth-only sort grouped all components after
    // all subsystems). depthOfAny still drives indentation (marginLeft).
    const orderedStructureNodes = orderStructureNodes(structureNodes, edges);

    return (
      <div>
        {guideRows.length > 0 && (
          <div style={{ marginBottom: 12, padding: '10px 12px', background: 'var(--qf-amber-dim)', border: '1px solid var(--qf-amber)', borderRadius: 'var(--qf-radius-md)' }}>
            {guideRows.map(row => (
              <div key={row.nodeType} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, color: 'var(--qf-text-primary)', fontSize: 13 }}>
                <BulbOutlined style={{ color: 'var(--qf-amber)', flexShrink: 0 }} />
                <span style={{ flex: 1 }}>
                  {t(`wizard.scope.toolGuide.${row.nodeType}`, { tool: row.tool })}
                </span>
              </div>
            ))}
          </div>
        )}
        <Space style={{ marginBottom: 12 }}>
          <Button size="small" icon={<PlusOutlined />} onClick={() => handleAddNode('System')}>{t('wizard.structure.addSystem')}</Button>
          <Button size="small" icon={<PlusOutlined />} onClick={() => addAttachedParamNode('Interface')}>{t('wizard.structure.addInterface')}</Button>
        </Space>
        {structureNodes.length === 0 && <Empty description={t('wizard.structure.empty')} />}
        {orderedStructureNodes.map(node => (
          <Card key={node.id} size="small" style={{ marginBottom: 8, marginLeft: depthOfAny(node) * 20 }}>
            <Space>
              <Tag color={TYPE_COLORS[node.type]}>{typeLabel(node.type)}</Tag>
              <Input size="small" value={node.name} style={{ width: 200 }}
                onChange={e => handleRenameNode(node.id, e.target.value)} />
              {CHILD_TYPE[node.type] && (
                <Button size="small" onClick={() => handleAddNode(CHILD_TYPE[node.type], node.id)}>
                  + {typeLabel(CHILD_TYPE[node.type])}
                </Button>
              )}
              {['System', 'Subsystem', 'Component'].includes(node.type) && (
                <>
                  <Button size="small" onClick={() => addAttachedParamNode('Interface', node.id)}>
                    + {typeLabel('Interface')}
                  </Button>
                  <Button size="small" onClick={() => addAttachedParamNode('DesignParameter', node.id)}>
                    + {typeLabel('DesignParameter')}
                  </Button>
                </>
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
      const funcId = `w${crypto.randomUUID()}_func`;
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
                {t('wizard.failure.addFunction')}
              </Button>
            </Card>
          );
        })}
      </div>
    );
  };

  // Step 3 — Failure Analysis
  const renderStep3 = () => {
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const processStep = (funcId: string) => getProcessChain(funcId, nodeMap, edges);
    const functions = nodes.filter(n => ['ProcessWorkElementFunction', 'ProcessItemFunction', 'ProcessStepFunction'].includes(n.type));

    if (functions.length === 0) return <Empty description={t('wizard.failure.title') + ' — ' + t('wizard.function.title')} />;

    const handleAddFailure = (funcId: string, mode?: string, effect?: string, cause?: string) => {
      const { newNodes, newEdges } = createWizardFailureChain(funcId);
      // Override FM/FE/FC names when caller supplied explicit values (AI suggestions).
      if (mode) { const fm = newNodes.find(n => n.type === 'FailureMode'); if (fm) fm.name = mode; }
      if (effect) { const fe = newNodes.find(n => n.type === 'FailureEffect'); if (fe) fe.name = effect; }
      if (cause) { const fc = newNodes.find(n => n.type === 'FailureCause'); if (fc) fc.name = cause; }
      updateGraphData([...nodes, ...newNodes], [...edges, ...newEdges]);
    };

    // Delete a failure chain (FailureMode + its Effects/Causes/Controls).
    // cascadeDeleteStructureNode already BFS-follows EFFECT_OF + CAUSE_OF +
    // PREVENTED_BY/DETECTED_BY and keeps controls referenced by surviving rows.
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
      if (!ctrlEdge) return; // ensureCauseControls (load) guarantees existence; guard anyway.
      updateGraphData(
        nodes.map(n => n.id === ctrlEdge.target ? { ...n, name: value } : n),
        edges,
      );
    };

    return (
      <div>
        {functions.map(func => {
          const fmEdges = edges.filter(e => e.source === func.id && e.type === 'HAS_FAILURE_MODE');
          const fmNodes = fmEdges.map(e => nodes.find(n => n.id === e.target)).filter(Boolean) as GraphNode[];

          return (
            <Card key={func.id} size="small" title={func.name} style={{ marginBottom: 12 }}>
              {fmNodes.map(fmNode => {
                const effectEdge = edges.find(e => e.source === fmNode.id && e.type === 'EFFECT_OF');
                const effectNode = effectEdge ? nodes.find(n => n.id === effectEdge!.target) : null;
                const causeEdges = edges.filter(e => e.target === fmNode.id && e.type === 'CAUSE_OF');
                const causeNodes = causeEdges.map(e => nodes.find(n => n.id === e.source)).filter(Boolean) as GraphNode[];

                return (
                  <div key={fmNode.id} style={{ marginBottom: 8, padding: 8, background: 'var(--qf-bg-elevated)', border: '1px solid var(--qf-border)', borderRadius: 'var(--qf-radius-md)' }}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div>
                        <div style={{ fontSize: 12, marginBottom: 2 }}>{t('wizard.failure.failureMode')}</div>
                        <SmartSuggestionDropdown
                          triggerType="failure_mode"
                          context={{ function_description: func.name, process_step: processStep(func.id) }}
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
                            context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
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
                              context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
                              fmeaId={fmeaId!}
                              value={causeNode.name}
                              onChange={(val) => handleUpdateNodeField(causeNode.id, 'name', val)}
                              onSelect={(s) => handleUpdateNodeField(causeNode.id, 'name', s.name)}
                            />
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.preventionControl')}</div>
                            <SmartSuggestionDropdown
                              triggerType="prevention_control"
                              context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
                              fmeaId={fmeaId!}
                              value={pcName}
                              onChange={(val) => handleUpdateControl(causeNode.id, 'prevention', val)}
                              onSelect={(s) => handleUpdateControl(causeNode.id, 'prevention', s.name)}
                            />
                            <div style={{ fontSize: 12, marginBottom: 2, marginTop: 4 }}>{t('wizard.failure.detectionControl')}</div>
                            <SmartSuggestionDropdown
                              triggerType="detection_control"
                              context={{ failure_mode: fmNode.name, function_description: func.name, process_step: processStep(func.id) }}
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
      <div>
        {validation.step5MissingControl && (
          <div style={{ marginBottom: 12, padding: '10px 12px', background: 'var(--qf-amber-dim)', border: '1px solid var(--qf-amber)', borderRadius: 'var(--qf-radius-md)', color: 'var(--qf-text-primary)', fontSize: 13 }}>
            {t('wizard.risk.missingControlHint')}
          </div>
        )}
        <Table size="small" dataSource={rows} rowKey="key" pagination={false} scroll={{ x: 1080 }}
          columns={[
          { title: t('wizard.failure.failureMode'), dataIndex: 'key', width: 140, render: (_: unknown, r: FMEARow) => {
            const fm = nodeMap.get(r.failureModeNodeId);
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: fm?.name || '' }}>{fm?.name || ''}</Typography.Text>;
          }},
          { title: t('wizard.failure.failureEffect'), width: 140, render: (_: unknown, r: FMEARow) => {
            const names = r.failureEffectNodeIds
              .map(id => nodeMap.get(id)?.name || '')
              .filter(Boolean)
              .join('；');
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: names }}>{names}</Typography.Text>;
          }},
          { title: t('wizard.failure.failureCause'), width: 140, render: (_: unknown, r: FMEARow) => {
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: cause?.name || '' }}>{cause?.name || ''}</Typography.Text>;
          }},
          { title: t('wizard.failure.preventionControl'), width: 140, render: (_: unknown, r: FMEARow) => {
            const pc = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0]) : null;
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: pc?.name || '' }}>{pc?.name || ''}</Typography.Text>;
          }},
          { title: t('wizard.failure.detectionControl'), width: 140, render: (_: unknown, r: FMEARow) => {
            const dc = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0]) : null;
            return <Typography.Text style={{ fontSize: 12 }} ellipsis={{ tooltip: dc?.name || '' }}>{dc?.name || ''}</Typography.Text>;
          }},
          { title: 'S', width: 60, render: (_: unknown, r: FMEARow) => {
            // S is mode/effect-level (shared across a mode's causes) — NOT gated
            // by this row's PC/DC. Another cause row under the same mode may
            // have filled controls and already set S.
            const s = getRowSeverity(r, nodeMap);
            const effectIds = new Set(r.failureEffectNodeIds);
            return <InputNumber size="small" min={1} max={10} value={s || undefined}
              style={{ width: 50 }} onChange={val => {
                const v = val || 0;
                updateGraphData(nodes.map(n => effectIds.has(n.id) ? { ...n, severity: v } : n), edges);
              }} />;
          }},
          { title: 'O', width: 60, render: (_: unknown, r: FMEARow) => {
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name || '' : '';
            const dcName = r.detectionControlIds[0] ? nodeMap.get(r.detectionControlIds[0])?.name || '' : '';
            const locked = !pcName.trim() || !dcName.trim();
            return <InputNumber size="small" min={1} max={10} value={cause?.occurrence || undefined}
              style={{ width: 50 }} disabled={locked}
              onChange={val => cause && handleUpdateRisk(cause.id, 'occurrence', val || 0)} />;
          }},
          { title: 'D', width: 60, render: (_: unknown, r: FMEARow) => {
            const dcId = r.detectionControlIds[0];
            const dc = dcId ? nodeMap.get(dcId) : null;
            const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name || '' : '';
            const dcName = dc?.name || '';
            const locked = !pcName.trim() || !dcName.trim();
            return <InputNumber size="small" min={1} max={10} value={dc?.detection || undefined}
              style={{ width: 50 }} disabled={locked}
              onChange={val => dc && handleUpdateRisk(dc.id, 'detection', val || 0)} />;
          }},
          { title: 'AP', width: 80, render: (_: unknown, r: FMEARow) => {
            const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
            const dcId = r.detectionControlIds[0];
            const dc = dcId ? nodeMap.get(dcId) : null;
            const pcName = r.preventionControlIds[0] ? nodeMap.get(r.preventionControlIds[0])?.name || '' : '';
            const dcName = dc?.name || '';
            const locked = !pcName.trim() || !dcName.trim();
            if (locked) return <Tag>{t('wizard.risk.controlsFirst')}</Tag>;
            const s = getRowSeverity(r, nodeMap), o = cause?.occurrence || 0, d = dc?.detection || 0;
            const { ap } = analyzeRisk(s, o, d);
            return <Tag color={ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'green'}>{ap || '-'}</Tag>;
          }},
        ]}
        />
      </div>
    );
  };

  // Step 5 — Optimization
  const renderStep5 = () => {
    const { suggestMeasures, analyzeRisk } = dfmeaRules;
    const rows = buildRows(nodes, edges);
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const highRiskRows = rows.filter(r => {
      const cause = r.failureCauseNodeId ? nodeMap.get(r.failureCauseNodeId) : null;
      const dcId = r.detectionControlIds[0];
      const dc = dcId ? nodeMap.get(dcId) : null;
      const s = getRowSeverity(r, nodeMap), o = cause?.occurrence || 0, d = dc?.detection || 0;
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
          const pcId = `w${crypto.randomUUID()}_pc`;
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
          const dcId = `w${crypto.randomUUID()}_dc`;
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
            completedSteps={completedSteps}
            maxReachableStep={maxReachableStep}
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
            <div style={{ marginTop: 16, padding: 12, background: 'var(--qf-red-dim)', border: '1px solid var(--qf-red)', borderRadius: 'var(--qf-radius-md)' }}>
              <div style={{ fontWeight: 600, color: 'var(--qf-red)', marginBottom: 4 }}>{t('wizard.page.completionWarning')}</div>
              {validation.warnings.map(w => (
                <div key={w} style={{ color: 'var(--qf-red)' }}>• {t(
                  w === 4 && validation.step5MissingCause
                    ? 'wizard.page.step5IncompleteMissingCause'
                    : `wizard.page.step${w + 1}Incomplete`
                )}</div>
              ))}
            </div>
          )}
          {currentStep === 6 && validation.structureGaps.length > 0 && (
            <div style={{ marginTop: 16, padding: 12, background: 'var(--qf-amber-dim)', border: '1px solid var(--qf-amber)', borderRadius: 'var(--qf-radius-md)' }}>
              {validation.structureGaps.map((g, i) => (
                <div key={`${g.tool}-${g.nodeType}-${i}`} style={{ color: 'var(--qf-amber)' }}>
                  ⚠ {t('wizard.page.structureGap', { tool: g.tool, nodeType: t(`wizard.typeLabels.${g.nodeType}`, { defaultValue: g.nodeType }) })}
                </div>
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