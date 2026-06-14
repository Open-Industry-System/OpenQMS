import { useState, useEffect, useCallback } from 'react';
import {
  Table, Tag, Space, Input, Select, Row, Col, Statistic, App, Button,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { AqlRecommendation } from '../../types';
import { listAqlRecommendations } from '../../api/iqcAql';
import AqlRecommendationDrawer from '../../components/iqc/AqlRecommendationDrawer';
import { PageShell, DataCard, StatusBadge } from '../../components/design';

const DIRECTION_MAP: Record<string, { label: string }> = {
  tighten: { label: '加严' },
  reduce: { label: '放宽' },
  freeze: { label: '冻结' },
  keep: { label: '保持' },
};

const STATUS_MAP: Record<string, { label: string }> = {
  pending: { label: '待审批' },
  forwarded: { label: '已转交' },
  approved: { label: '已批准' },
  effective: { label: '已生效' },
  rejected: { label: '已拒绝' },
  expired: { label: '已过期' },
};

const directionVariant = (dir: string): string => {
  switch (dir) {
    case 'tighten': return 'warning';
    case 'reduce': return 'success';
    case 'freeze': return 'error';
    case 'keep': return 'info';
    default: return 'info';
  }
};

const statusVariant = (status: string): string => {
  switch (status) {
    case 'approved':
    case 'effective':
      return 'success';
    case 'pending':
    case 'forwarded':
      return 'warning';
    case 'rejected':
      return 'error';
    default:
      return 'info';
  }
};

export default function AqlOptimizationPage() {
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
      message.error('加载建议列表失败');
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

  const columns = [
    {
      title: '供应商名称',
      dataIndex: 'supplier_id',
      width: 140,
      render: (v: string) => v || '—',
    },
    {
      title: '物料号',
      dataIndex: 'material_id',
      width: 140,
      render: (v: string) => v || '—',
    },
    {
      title: '当前AQL',
      dataIndex: 'current_aql',
      width: 90,
    },
    {
      title: '建议AQL',
      dataIndex: 'recommended_aql',
      width: 90,
    },
    {
      title: '方向',
      dataIndex: 'direction',
      width: 90,
      render: (dir: string) => {
        const cfg = DIRECTION_MAP[dir];
        return (
          <StatusBadge status={directionVariant(dir)}>
            {cfg?.label || dir}
          </StatusBadge>
        );
      },
    },
    {
      title: '触发规则',
      dataIndex: 'trigger_rules',
      width: 180,
      render: (rules: { rule_id: string; reason: string }[]) => (
        <Space size={4} wrap>
          {rules.map((r) => <Tag key={r.rule_id}>{r.rule_id}</Tag>)}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (status: string) => {
        const cfg = STATUS_MAP[status];
        return (
          <StatusBadge status={statusVariant(status)}>
            {cfg?.label || status}
          </StatusBadge>
        );
      },
    },
  ];

  return (
    <PageShell
      title="AQL优化建议"
      actions={
        <Button icon={<ReloadOutlined />} onClick={() => { fetchData(); fetchKpi(); }}>
          刷新
        </Button>
      }
    >
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <DataCard title="">
            <Statistic title="待审批" value={pendingCount} valueStyle={{ color: '#faad14' }} />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="">
            <Statistic title="今日生成" value={todayCount} />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="">
            <Statistic title="已批准" value={approvedCount} valueStyle={{ color: '#52c41a' }} />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="">
            <Statistic title="已拒绝" value={rejectedCount} valueStyle={{ color: '#ff4d4f' }} />
          </DataCard>
        </Col>
      </Row>

      <DataCard title="">
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 120 }}
            value={filterStatus}
            onChange={(v) => { setFilterStatus(v || undefined); setPage(1); }}
          >
            <Select.Option value="pending">待审批</Select.Option>
            <Select.Option value="forwarded">已转交</Select.Option>
            <Select.Option value="approved">已批准</Select.Option>
            <Select.Option value="effective">已生效</Select.Option>
            <Select.Option value="rejected">已拒绝</Select.Option>
            <Select.Option value="expired">已过期</Select.Option>
          </Select>
          <Select
            placeholder="方向"
            allowClear
            style={{ width: 120 }}
            value={filterDirection}
            onChange={(v) => { setFilterDirection(v || undefined); setPage(1); }}
          >
            <Select.Option value="tighten">加严</Select.Option>
            <Select.Option value="reduce">放宽</Select.Option>
            <Select.Option value="freeze">冻结</Select.Option>
          </Select>
          <Input
            placeholder="供应商ID"
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
