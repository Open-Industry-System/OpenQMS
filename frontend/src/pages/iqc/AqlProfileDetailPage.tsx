import { useState, useEffect } from 'react';
import { Row, Col, Statistic, Descriptions, Table, App, Spin } from 'antd';
import { useParams } from 'react-router-dom';
import type { AqlProfile, AqlQualitySnapshot, AqlRecommendation } from '../../types';
import { listAqlProfiles, getAqlQualitySnapshot, listAqlRecommendations } from '../../api/iqcAql';
import AqlQualityChart from '../../components/iqc/AqlQualityChart';
import { PageShell, DataCard, StatusBadge } from '../../components/design';

const STATE_LABELS: Record<string, string> = {
  normal: '正常',
  tightened: '加严',
  reduced: '放宽',
  frozen: '冻结',
};

const REC_STATUS_VARIANTS: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
  pending: 'warning',
  forwarded: 'info',
  approved: 'success',
  effective: 'success',
  rejected: 'error',
  expired: 'info',
};

const REC_STATUS_LABELS: Record<string, string> = {
  pending: '待审批',
  forwarded: '已转交',
  approved: '已批准',
  effective: '已生效',
  rejected: '已拒绝',
  expired: '已过期',
};

export default function AqlProfileDetailPage() {
  const { message: _message } = App.useApp();
  const { supplierId, materialId } = useParams<{ supplierId: string; materialId: string }>();

  const [profile, setProfile] = useState<AqlProfile | null>(null);
  const [snapshot, setSnapshot] = useState<AqlQualitySnapshot | null>(null);
  const [recommendations, setRecommendations] = useState<AqlRecommendation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supplierId || !materialId) return;
    setLoading(true);

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

  const stateLabel = profile ? (STATE_LABELS[profile.state] || profile.state) : '';

  const recColumns = [
    { title: '建议AQL', dataIndex: 'recommended_aql', width: 90 },
    {
      title: '方向',
      dataIndex: 'direction',
      width: 80,
      render: (d: string) => <StatusBadge status="info">{d}</StatusBadge>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => (
        <StatusBadge status={REC_STATUS_VARIANTS[s] || 'info'}>
          {REC_STATUS_LABELS[s] || s}
        </StatusBadge>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
  ];

  return (
    <PageShell title="AQL档案详情">
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>
      ) : !profile ? (
        <DataCard title={null}>
          <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>未找到档案</div>
        </DataCard>
      ) : (
        <>
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <DataCard title={null}><Statistic title="基准AQL" value={profile.base_aql} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}><Statistic title="当前AQL" value={profile.current_aql} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}><Statistic title="状态" value={stateLabel} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}>
                <Statistic
                  title="生效日期"
                  value={profile.effective_from ? new Date(profile.effective_from).toLocaleDateString('zh-CN') : '—'}
                />
              </DataCard>
            </Col>
          </Row>

          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={12}>
              <DataCard title="检验统计">
                {snapshot ? (
                  <Descriptions column={1} bordered size="small">
                    <Descriptions.Item label="总批次数">{snapshot.total_batches}</Descriptions.Item>
                    <Descriptions.Item label="连续合格">{snapshot.consecutive_accepted}</Descriptions.Item>
                    <Descriptions.Item label="连续不合格">{snapshot.consecutive_rejected}</Descriptions.Item>
                    <Descriptions.Item label="30天批次">{snapshot.last_30d_batch_count}</Descriptions.Item>
                    <Descriptions.Item label="30天PPM">{snapshot.last_30d_ppm ?? '—'}</Descriptions.Item>
                    <Descriptions.Item label="90天PPM">{snapshot.last_90d_ppm ?? '—'}</Descriptions.Item>
                  </Descriptions>
                ) : (
                  <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>暂无数据</div>
                )}
              </DataCard>
            </Col>
            <Col span={12}>
              <DataCard title="供应商表现">
                {snapshot ? (
                  <Descriptions column={1} bordered size="small">
                    <Descriptions.Item label="供应商评级">{snapshot.supplier_rating || '—'}</Descriptions.Item>
                    <Descriptions.Item label="未关闭SCAR">{snapshot.open_scar_count}</Descriptions.Item>
                    <Descriptions.Item label="安全缺陷">{snapshot.has_safety_defect ? '是' : '否'}</Descriptions.Item>
                    <Descriptions.Item label="关联客诉">{snapshot.linked_customer_complaint ? '是' : '否'}</Descriptions.Item>
                    <Descriptions.Item label="计算状态">{snapshot.calculated_state || '—'}</Descriptions.Item>
                  </Descriptions>
                ) : (
                  <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>暂无数据</div>
                )}
              </DataCard>
            </Col>
          </Row>

          <DataCard title="质量趋势" style={{ marginBottom: 24 }}>
            <AqlQualityChart snapshots={snapshot ? [snapshot] : []} />
          </DataCard>

          <DataCard title="历史建议">
            <Table
              className="qf-table"
              rowKey="recommendation_id"
              columns={recColumns}
              dataSource={recommendations}
              pagination={false}
              size="small"
            />
          </DataCard>
        </>
      )}
    </PageShell>
  );
}
