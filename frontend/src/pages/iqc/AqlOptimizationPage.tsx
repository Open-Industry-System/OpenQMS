import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Table, Tag, Space, Input, Select, Row, Col, Statistic, App, Button,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { AqlRecommendation } from '../../types';
import { listAqlRecommendations } from '../../api/iqcAql';
import AqlRecommendationDrawer from '../../components/iqc/AqlRecommendationDrawer';
import { PageShell, DataCard, StatusBadge } from '../../components/design';

export default function AqlOptimizationPage() {
  const { t } = useTranslation('iqc');
  const { t: tc } = useTranslation('common');
  const { message } = App.useApp();

  const [data, setData] = useState<AqlRecommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [filterDirection, setFilterDirection] = useState<string | undefined>();
  const [filterSupplier, setFilterSupplier] = useState('');

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selected, setSelected] = useState<AqlRecommendation | null>(null);

  // KPI counts derived from data (we'll compute from what we have)
  const [kpiData, setKpiData] = useState<AqlRecommendation[]>([]);

  const directionMap = useMemo<Record<string, { label: string; color: string; emoji: string }>>(
    () => ({
      tighten: { label: t('status.recDirection.tighten'), color: 'orange', emoji: '🔴' },
      reduce: { label: t('status.recDirection.reduce'), color: 'green', emoji: '🟢' },
      freeze: { label: t('status.recDirection.freeze'), color: 'red', emoji: '🔵' },
      keep: { label: t('status.recDirection.keep'), color: 'default', emoji: '' },
    }),
    [t]
  );

  const statusMap = useMemo<Record<string, { label: string; color: string }>>(
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

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (filterStatus) params.status = filterStatus;
      if (filterDirection) params.direction = filterDirection;
      if (filterSupplier) params.supplier_id = filterSupplier;
      const resp = await listAqlRecommendations(params);
      setData(resp.items);
      setTotal(resp.total);
    } catch {
      message.error(t('messages.loadRecommendationListFailed'));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, filterStatus, filterDirection, filterSupplier]);

  // Fetch all for KPI (first page large enough for counts)
  const fetchKpi = useCallback(async () => {
    try {
      const resp = await listAqlRecommendations({ page: 1, page_size: 200 });
      setKpiData(resp.items);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    fetchKpi();
  }, [fetchKpi]);

  const pendingCount = kpiData.filter((r) => r.status === 'pending' || r.status === 'forwarded').length;
  const todayStr = new Date().toISOString().slice(0, 10);
  const todayCount = kpiData.filter((r) => r.created_at.slice(0, 10) === todayStr).length;
  const approvedCount = kpiData.filter((r) => r.status === 'approved' || r.status === 'effective').length;
  const rejectedCount = kpiData.filter((r) => r.status === 'rejected').length;

  const columns = useMemo(
    () => [
      {
        title: t('table.supplierName'),
        dataIndex: 'supplier_id',
        width: 140,
        render: (v: string) => v || '—',
      },
      {
        title: t('table.materialId'),
        dataIndex: 'material_id',
        width: 140,
        render: (v: string) => v || '—',
      },
      {
        title: t('table.currentAql'),
        dataIndex: 'current_aql',
        width: 90,
      },
      {
        title: t('table.recommendedAql'),
        dataIndex: 'recommended_aql',
        width: 90,
      },
      {
        title: t('table.direction'),
        dataIndex: 'direction',
        width: 90,
        render: (dir: string) => {
          const cfg = directionMap[dir];
          if (!cfg) return dir;
          return <Tag color={cfg.color}>{cfg.emoji} {cfg.label}</Tag>;
        },
      },
      {
        title: t('table.triggerRules'),
        dataIndex: 'trigger_rules',
        width: 180,
        render: (rules: { rule_id: string; reason: string }[]) => (
          <Space size={4} wrap>
            {rules.map((r) => <Tag key={r.rule_id}>{r.rule_id}</Tag>)}
          </Space>
        ),
      },
      {
        title: t('table.status'),
        dataIndex: 'status',
        width: 90,
        render: (status: string) => {
          const cfg = statusMap[status];
          return <Tag color={cfg?.color}>{cfg?.label || status}</Tag>;
        },
      },
    ],
    [t, directionMap, statusMap]
  );

  return (
    <PageShell
      title={t('pageTitle.aqlOptimization')}
      actions={
        <Button icon={<ReloadOutlined />} onClick={() => { fetchData(); fetchKpi(); }}>
          {tc('actions.refresh')}
        </Button>
      }
    >
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <DataCard title="">
            <Statistic title={t('stats.pendingApproval')} value={pendingCount} valueStyle={{ color: '#faad14' }} />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="">
            <Statistic title={t('stats.generatedToday')} value={todayCount} />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="">
            <Statistic title={t('stats.approvedCount')} value={approvedCount} valueStyle={{ color: '#52c41a' }} />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="">
            <Statistic title={t('stats.rejectedCountRec')} value={rejectedCount} valueStyle={{ color: '#ff4d4f' }} />
          </DataCard>
        </Col>
      </Row>

      <DataCard title="">
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            placeholder={t('placeholder.selectStatus')}
            allowClear
            style={{ width: 120 }}
            value={filterStatus}
            onChange={(v) => { setFilterStatus(v || undefined); setPage(1); }}
          >
            <Select.Option value="pending">{t('status.recStatus.pending')}</Select.Option>
            <Select.Option value="forwarded">{t('status.recStatus.forwarded')}</Select.Option>
            <Select.Option value="approved">{t('status.recStatus.approved')}</Select.Option>
            <Select.Option value="effective">{t('status.recStatus.effective')}</Select.Option>
            <Select.Option value="rejected">{t('status.recStatus.rejected')}</Select.Option>
            <Select.Option value="expired">{t('status.recStatus.expired')}</Select.Option>
          </Select>
          <Select
            placeholder={t('placeholder.selectDirection')}
            allowClear
            style={{ width: 120 }}
            value={filterDirection}
            onChange={(v) => { setFilterDirection(v || undefined); setPage(1); }}
          >
            <Select.Option value="tighten">{t('status.recDirection.tighten')}</Select.Option>
            <Select.Option value="reduce">{t('status.recDirection.reduce')}</Select.Option>
            <Select.Option value="freeze">{t('status.recDirection.freeze')}</Select.Option>
          </Select>
          <Input
            placeholder={t('placeholder.supplierId')}
            allowClear
            style={{ width: 200 }}
            value={filterSupplier}
            onChange={(e) => setFilterSupplier(e.target.value)}
            onPressEnter={() => { setPage(1); fetchData(); }}
          />
        </Space>

        <Table
          className="qf-table"
          rowKey="recommendation_id"
          columns={columns}
          dataSource={data}
          loading={loading}
          onRow={(record) => ({
            onClick: () => { setSelected(record); setDrawerOpen(true); },
            style: { cursor: 'pointer' },
          })}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => { setPage(p); setPageSize(ps || 20); },
          }}
        />
      </DataCard>

      <AqlRecommendationDrawer
        open={drawerOpen}
        recommendation={selected}
        onClose={() => setDrawerOpen(false)}
        onAction={() => { setDrawerOpen(false); fetchData(); fetchKpi(); }}
      />
    </PageShell>
  );
}
