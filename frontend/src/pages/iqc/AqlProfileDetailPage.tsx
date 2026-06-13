import { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Descriptions, Table, Tag, App, Spin } from 'antd';
import { useParams } from 'react-router-dom';
import type { AqlProfile, AqlQualitySnapshot, AqlRecommendation } from '../../types';
import { listAqlProfiles, getAqlQualitySnapshot, listAqlRecommendations } from '../../api/iqcAql';
import AqlQualityChart from '../../components/iqc/AqlQualityChart';

const STATE_MAP: Record<string, { label: string; status: 'success' | 'warning' | 'processing' | 'error' | 'default' }> = {
  normal: { label: '正常', status: 'success' },
  tightened: { label: '加严', status: 'warning' },
  reduced: { label: '放宽', status: 'processing' },
  frozen: { label: '冻结', status: 'error' },
};

const REC_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待审批', color: 'orange' },
  forwarded: { label: '已转交', color: 'blue' },
  approved: { label: '已批准', color: 'green' },
  effective: { label: '已生效', color: 'green' },
  rejected: { label: '已拒绝', color: 'red' },
  expired: { label: '已过期', color: 'default' },
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
  if (!profile) return <Card><div style={{ textAlign: 'center', padding: 24, color: '#999' }}>未找到档案</div></Card>;

  const stateCfg = STATE_MAP[profile.state] || { label: profile.state, status: 'default' as const };

  const recColumns = [
    { title: '建议AQL', dataIndex: 'recommended_aql', width: 90 },
    {
      title: '方向',
      dataIndex: 'direction',
      width: 80,
      render: (d: string) => <Tag>{d}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => {
        const cfg = REC_STATUS_MAP[s];
        return <Tag color={cfg?.color}>{cfg?.label || s}</Tag>;
      },
    },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card><Statistic title="基准AQL" value={profile.base_aql} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="当前AQL" value={profile.current_aql} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="状态" value={stateCfg.label} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="生效日期" value={profile.effective_from ? new Date(profile.effective_from).toLocaleDateString('zh-CN') : '—'} /></Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card title="检验统计" size="small">
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
          </Card>
        </Col>
        <Col span={12}>
          <Card title="供应商表现" size="small">
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
          </Card>
        </Col>
      </Row>

      <Card title="质量趋势" style={{ marginBottom: 24 }}>
        <AqlQualityChart snapshots={snapshot ? [snapshot] : []} />
      </Card>

      <Card title="历史建议">
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
