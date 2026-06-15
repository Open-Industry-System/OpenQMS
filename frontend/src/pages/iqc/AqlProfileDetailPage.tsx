import { useState, useEffect, useMemo } from 'react';
import { Card, Row, Col, Statistic, Descriptions, Table, Tag, App, Spin } from 'antd';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { AqlProfile, AqlQualitySnapshot, AqlRecommendation } from '../../types';
import { listAqlProfiles, getAqlQualitySnapshot, listAqlRecommendations } from '../../api/iqcAql';
import AqlQualityChart from '../../components/iqc/AqlQualityChart';

export default function AqlProfileDetailPage() {
  const { t, i18n } = useTranslation('iqc');
  const { t: tc } = useTranslation('common');
  const { message: _message } = App.useApp();
  const { supplierId, materialId } = useParams<{ supplierId: string; materialId: string }>();

  const [profile, setProfile] = useState<AqlProfile | null>(null);
  const [snapshot, setSnapshot] = useState<AqlQualitySnapshot | null>(null);
  const [recommendations, setRecommendations] = useState<AqlRecommendation[]>([]);
  const [loading, setLoading] = useState(true);

  const stateMap = useMemo<Record<string, { label: string; status: 'success' | 'warning' | 'processing' | 'error' | 'default' }>>(
    () => ({
      normal: { label: t('status.profileState.normal'), status: 'success' },
      tightened: { label: t('status.profileState.tightened'), status: 'warning' },
      reduced: { label: t('status.profileState.reduced'), status: 'processing' },
      frozen: { label: t('status.profileState.frozen'), status: 'error' },
    }),
    [t]
  );

  const recStatusMap = useMemo<Record<string, { label: string; color: string }>>(
    () => ({
      pending: { label: t('status.recStatus.pending'), color: 'orange' },
      forwarded: { label: t('status.recStatus.forwarded'), color: 'blue' },
      approved: { label: t('status.recStatus.approved'), color: 'green' },
      effective: { label: t('status.recStatus.effective'), color: 'green' },
      rejected: { label: t('status.recStatus.rejected'), color: 'red' },
      expired: { label: t('status.recStatus.expired'), color: 'default' },
    }),
    [t]
  );

  useEffect(() => {
    if (!supplierId || !materialId) return;
    setLoading(true);

    // Profile lookup via list API filtered by supplier_id, then match material_id
    const profileP = listAqlProfiles({ supplier_id: supplierId, page: 1, page_size: 100 })
      .then((resp) => {
        const found = resp.items.find((p: AqlProfile) => p.material_id === materialId);
        return found || null;
      })
      .catch(() => null);

    const snapshotP = getAqlQualitySnapshot(supplierId, materialId).catch(() => null);
    const recsP = listAqlRecommendations({ supplier_id: supplierId, material_id: materialId, page: 1, page_size: 50 })
      .catch(() => ({ items: [] }));

    Promise.all([profileP, snapshotP, recsP]).then(([p, s, r]) => {
      setProfile(p as AqlProfile | null);
      setSnapshot(s as AqlQualitySnapshot | null);
      setRecommendations((r as { items: AqlRecommendation[] }).items);
      setLoading(false);
    });
  }, [supplierId, materialId]);

  if (loading) return <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>;
  if (!profile) return <Card><div style={{ textAlign: 'center', padding: 24, color: '#999' }}>{t('messages.profileNotFound')}</div></Card>;

  const stateCfg = stateMap[profile.state] || { label: profile.state, status: 'default' as const };

  const formatDate = (v: string | null) => v ? new Date(v).toLocaleDateString(i18n.language) : '—';
  const formatDateTime = (v: string) => v ? new Date(v).toLocaleString(i18n.language) : '—';

  const recColumns = [
    { title: t('table.recommendedAql'), dataIndex: 'recommended_aql', width: 90 },
    {
      title: t('table.direction'),
      dataIndex: 'direction',
      width: 80,
      render: (d: string) => <Tag>{d}</Tag>,
    },
    {
      title: t('table.status'),
      dataIndex: 'status',
      width: 90,
      render: (s: string) => {
        const cfg = recStatusMap[s];
        return <Tag color={cfg?.color}>{cfg?.label || s}</Tag>;
      },
    },
    { title: t('table.createdAt'), dataIndex: 'created_at', width: 160, render: formatDateTime },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card><Statistic title={t('table.baseAql')} value={profile.base_aql} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title={t('table.currentAql')} value={profile.current_aql} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title={t('table.state')} value={stateCfg.label} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title={t('table.effectiveFrom')} value={formatDate(profile.effective_from)} /></Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card title={t('detail.inspectionStats')} size="small">
            {snapshot ? (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('descriptions.totalBatches')}>{snapshot.total_batches}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.consecutiveAccepted')}>{snapshot.consecutive_accepted}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.consecutiveRejected')}>{snapshot.consecutive_rejected}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.last30dBatches')}>{snapshot.last_30d_batch_count}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.last30dPpm')}>{snapshot.last_30d_ppm ?? '—'}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.last90dPpm')}>{snapshot.last_90d_ppm ?? '—'}</Descriptions.Item>
              </Descriptions>
            ) : (
              <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>{tc('empty.data')}</div>
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card title={t('detail.supplierPerformance')} size="small">
            {snapshot ? (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('descriptions.supplierRating')}>{snapshot.supplier_rating || '—'}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.openScar')}>{snapshot.open_scar_count}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.safetyDefect')}>{snapshot.has_safety_defect ? t('status.yes') : t('status.no')}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.linkedComplaint')}>{snapshot.linked_customer_complaint ? t('status.yes') : t('status.no')}</Descriptions.Item>
                <Descriptions.Item label={t('descriptions.calculatedState')}>{snapshot.calculated_state || '—'}</Descriptions.Item>
              </Descriptions>
            ) : (
              <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>{tc('empty.data')}</div>
            )}
          </Card>
        </Col>
      </Row>

      <Card title={t('detail.qualityTrend')} style={{ marginBottom: 24 }}>
        <AqlQualityChart snapshots={snapshot ? [snapshot] : []} />
      </Card>

      <Card title={t('detail.historyRecommendations')}>
        <Table
          rowKey="recommendation_id"
          columns={recColumns}
          dataSource={recommendations}
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  );
}
