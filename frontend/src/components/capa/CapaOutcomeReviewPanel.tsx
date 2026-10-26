import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Descriptions, Divider, Empty, Space, Spin, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { getCapaOutcomeReview } from '../../api/capa';
import { isCompleteOutcomeReview, type CapaOutcomeReview } from '../../types/capaOutcomeReview';
import { DataCard } from '../design';
import { useCapaViewRequests } from './useCapaViewRequests';

interface Props {
  reportId: string;
  status: string;
  canApprove: boolean;
  credentialIdentity: string;
  onReviewChange: (review: CapaOutcomeReview | null) => void;
}
const reviewStates = ['D8_APPROVAL_PENDING', 'D8_CLOSURE', 'ARCHIVED'];
const plainStyle = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'inherit' } as const;

export default function CapaOutcomeReviewPanel({ reportId, status, canApprove, credentialIdentity, onReviewChange }: Props) {
  const { t } = useTranslation('capa');
  const identity = JSON.stringify([credentialIdentity, reportId, status, canApprove]);
  const requests = useCapaViewRequests(identity);
  const callback = useRef(onReviewChange);
  callback.current = onReviewChange;
  const [loaded, setLoaded] = useState<{ identity: string; value: CapaOutcomeReview } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const review = loaded?.identity === identity ? loaded.value : null;
  const load = useCallback(async () => {
    requests.invalidate();
    setLoaded(null); callback.current(null); setError('');
    if (!reviewStates.includes(status)) return;
    const request = requests.begin();
    setLoading(true);
    try {
      const value = await getCapaOutcomeReview(reportId, request.signal);
      if (!request.current()) return;
      if (!isCompleteOutcomeReview(value, reportId, status)) throw new Error('incomplete outcome read');
      setLoaded({ identity, value }); callback.current(value);
    } catch (e) {
      if (!request.current()) return;
      setLoaded(null); callback.current(null); setLoading(false);
      requests.invalidate();
      const code = (e as { response?: { status?: number } })?.response?.status;
      setError(t(code === 409 ? 'outcome.conflict' : [401, 403, 404].includes(code ?? 0) ? 'outcome.denied' : 'outcome.loadFailed'));
    } finally {
      if (request.current()) setLoading(false);
      request.finish();
    }
  }, [requests, reportId, status, identity, t]);
  useEffect(() => {
    void load();
    return () => { requests.invalidate(); callback.current(null); };
  }, [load, requests]);
  if (!reviewStates.includes(status)) return null;
  const metadata = (value: unknown) => <pre style={plainStyle}>{JSON.stringify(value, null, 2)}</pre>;
  return <DataCard title={t('outcome.title')} extra={<Button onClick={() => void load()} disabled={loading}>{t('outcome.reload')}</Button>}>
    {loading && <Spin />}
    {error && <Alert type="warning" showIcon message={error} />}
    {review && <>
      <Space wrap>
        <Tag>{t(`status.${review.status}`, review.status)}</Tag>
        <Tag data-e2e="capa-outcome-binding" color={review.binding_status === 'verified' ? 'success' : 'warning'}>{t(`outcome.binding.${review.binding_status}`)}</Tag>
      </Space>
      <Typography.Paragraph style={{ ...plainStyle, marginTop: 12 }}>
        {t('outcome.round')}: {review.review_round_id ?? '—'}<br />{t('outcome.revision')}: {review.revision}
      </Typography.Paragraph>
      <section data-e2e="capa-outcome-core">
        <Descriptions column={1} size="small" layout="vertical" items={Object.entries(review.core).map(([key, value]) => ({
          key, label: t(`outcome.core.${key}`), children: <div style={plainStyle}>{value || '—'}</div>,
        }))} />
        <Divider orientation="left">{t('outcome.verifications')}</Divider>
        {review.verifications.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        {review.verifications.map(row => <section key={row.verification_id} style={{ marginBottom: 16 }}>
          <Space wrap><Tag>{t(`verification.method.${row.method ?? 'none'}`, row.method ?? '—')}</Tag><Tag>{t(`outcome.conclusion.${row.conclusion}`, row.conclusion)}</Tag></Space>
          <p style={plainStyle}>{row.root_cause_text}</p><p style={plainStyle}>{row.result || '—'}</p>
          <p style={plainStyle}>{row.verification_id} · {row.verified_by ?? '—'} · {row.verified_at ?? '—'} · {row.created_at}</p>
          <Typography.Text strong>{t('outcome.evidence')}</Typography.Text>{metadata(row.evidence_attachments)}
          <Typography.Text strong>{t('outcome.source')}</Typography.Text>{metadata(row.source_ref)}
        </section>)}
        <Divider orientation="left">{t('outcome.d7')}</Divider>
        <section data-e2e="capa-outcome-d7">
          {review.d7_actions.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          {review.d7_actions.map(row => <section key={row.action_id} style={{ marginBottom: 16 }}>
            <Space wrap><Tag>{t(`outcome.action.${row.action}`, row.action)}</Tag><Tag>{t(`outcome.actionStatus.${row.status}`, row.status)}</Tag></Space>
            <p style={plainStyle}>{row.prevention_control_name_before || '—'}</p><p style={plainStyle}>{row.prevention_control_name_after || '—'}</p>
            {metadata({ action_id: row.action_id, fmea_id: row.fmea_id, failure_mode_node_id: row.failure_mode_node_id,
              failure_cause_node_id: row.failure_cause_node_id, match_source: row.match_source,
              prevention_control_node_id: row.prevention_control_node_id, reason: row.reason, acted_by: row.acted_by, acted_at: row.acted_at })}
          </section>)}
        </section>
        <Divider orientation="left">{t('outcome.documents')}</Divider>
        {review.documents.length === 0 && <Typography.Paragraph>{t('outcome.noDocuments')}</Typography.Paragraph>}
        {review.documents.map(doc => <section key={`${doc.module}:${doc.object_id}:${doc.version_id}`}>
          <Tag>{doc.module === 'planning' ? t('outcome.controlPlan') : 'FMEA'}</Tag>
          <p style={plainStyle}>{t('outcome.object')}: {doc.object_id}<br />{t('outcome.version')}: {doc.version_id}</p>
          <p style={plainStyle}>{doc.sha256}</p>
        </section>)}
        {review.decision && <><Divider orientation="left">{t('outcome.decision')}</Divider>
          <Tag>{t(`outcome.decisionAction.${review.decision.action}`)}</Tag>{metadata(review.decision)}</>}
      </section>
      <Divider />
      <section data-e2e="capa-outcome-supplement"><Tag>{t('outcome.supplement')}</Tag>
        <p style={plainStyle}>{review.supplement.text || '—'}</p>
        <p style={plainStyle}>{review.supplement.updated_by ?? '—'} · {review.supplement.updated_at ?? '—'}</p>
      </section>
    </>}
  </DataCard>;
}
