import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Modal, Spin, Typography, message } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getFMEA, deleteFMEA } from '../../../api/fmea';
import type { FMEADocument, GraphNode, GraphEdge, WizardScope } from '../../../types';
import { useWizardSave, type SaveStatus } from '../../../hooks/useWizardSave';
import { useWizardValidation } from '../../../hooks/useWizardValidation';
import { useDfmeaRules } from '../../../utils/dfmeaRules';
import { buildRows } from '../../../utils/fmeaTable';
import { cascadeDeleteStructureNode } from '../../../utils/wizardCascadeDelete';
import WizardSidebar from '../../../components/dfmea/WizardSidebar';
import WizardGuidanceCard from '../../../components/dfmea/WizardGuidanceCard';

const { Title } = Typography;

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

  /** Lightweight hash — captures node identity + name + type + edges + scope. */
  const computeHash = (n: GraphNode[], e: GraphEdge[], s: WizardScope) =>
    JSON.stringify({
      nodes: n.map(x => x.id + ':' + x.name + ':' + x.type),
      edges: e.map(x => x.source + '->' + x.target + ':' + x.type),
      scope: s,
    });

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

  // Placeholder — Tasks 10-12 insert real renderStep0..renderStep6 above this map
  const STEP_RENDERERS: Record<number, () => React.ReactNode> = {
    0: () => <div />,
    1: () => <div />,
    2: () => <div />,
    3: () => <div />,
    4: () => <div />,
    5: () => <div />,
    6: () => <div />,
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
        <div style={{ width: 280, flexShrink: 0, overflow: 'auto', background: '#fafafa' }}>
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
                <div key={w} style={{ color: '#cf1322' }}>• {t(`wizard.page.step${w}Incomplete`)}</div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}