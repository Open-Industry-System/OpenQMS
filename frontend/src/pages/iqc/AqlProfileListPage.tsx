import { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Badge, Space, Select, Button, Modal, Form, Input, InputNumber, App,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { AqlProfile } from '../../types';
import { listAqlProfiles, createAqlProfile } from '../../api/iqcAql';
import { useAuthStore } from '../../store/authStore';

const STATE_MAP: Record<string, { label: string; status: 'success' | 'warning' | 'processing' | 'error' | 'default' }> = {
  normal: { label: '正常', status: 'success' },
  tightened: { label: '加严', status: 'warning' },
  reduced: { label: '放宽', status: 'processing' },
  frozen: { label: '冻结', status: 'error' },
};

export default function AqlProfileListPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const [data, setData] = useState<AqlProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [filterState, setFilterState] = useState<string | undefined>();
  const [filterProductLine, setFilterProductLine] = useState<string | undefined>();

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (filterState) params.state = filterState;
      if (filterProductLine) params.product_line_code = filterProductLine;
      const resp = await listAqlProfiles(params);
      setData(resp.items);
      setTotal(resp.total);
    } catch {
      message.error('加载档案列表失败');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, filterState, filterProductLine]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setCreating(true);
      await createAqlProfile(values);
      message.success('档案创建成功');
      setCreateOpen(false);
      createForm.resetFields();
      fetchData();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      message.error('创建失败');
    } finally {
      setCreating(false);
    }
  };

  const isAdmin = user?.role_key === 'admin';
  const isEngineer = user?.role_key === 'quality_engineer' || user?.role_key === 'engineer';

  const columns = [
    {
      title: '供应商',
      dataIndex: 'supplier_id',
      width: 140,
    },
    {
      title: '物料号',
      dataIndex: 'material_id',
      width: 140,
    },
    {
      title: '基准AQL',
      dataIndex: 'base_aql',
      width: 90,
    },
    {
      title: '当前AQL',
      dataIndex: 'current_aql',
      width: 90,
    },
    {
      title: '状态',
      dataIndex: 'state',
      width: 90,
      render: (state: string) => {
        const cfg = STATE_MAP[state];
        return <Badge status={cfg?.status || 'default'} text={cfg?.label || state} />;
      },
    },
    {
      title: '冻结截止',
      dataIndex: 'frozen_until',
      width: 140,
      render: (v: string | null) => v ? new Date(v).toLocaleDateString('zh-CN') : '—',
    },
    {
      title: '生效日期',
      dataIndex: 'effective_from',
      width: 120,
      render: (v: string) => v ? new Date(v).toLocaleDateString('zh-CN') : '—',
    },
  ];

  return (
    <div>
      <Card
        title="AQL档案管理"
        extra={
          <Space>
            {(isAdmin || isEngineer) && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                新建档案
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 120 }}
            value={filterState}
            onChange={(v) => { setFilterState(v || undefined); setPage(1); }}
          >
            <Select.Option value="normal">正常</Select.Option>
            <Select.Option value="tightened">加严</Select.Option>
            <Select.Option value="reduced">放宽</Select.Option>
            <Select.Option value="frozen">冻结</Select.Option>
          </Select>
          <Input
            placeholder="产品线"
            allowClear
            style={{ width: 160 }}
            value={filterProductLine || ''}
            onChange={(e) => { setFilterProductLine(e.target.value || undefined); setPage(1); }}
          />
        </Space>

        <Table
          rowKey="profile_id"
          columns={columns}
          dataSource={data}
          loading={loading}
          onRow={(record) => ({
            onClick: () => navigate(`/iqc/aql-optimization/profiles/${record.supplier_id}/${record.material_id}`),
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
      </Card>

      <Modal
        title="新建AQL档案"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        confirmLoading={creating}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="supplier_id" label="供应商ID" rules={[{ required: true, message: '请输入供应商ID' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="material_id" label="物料ID" rules={[{ required: true, message: '请输入物料ID' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="base_aql" label="基准AQL" rules={[{ required: true, message: '请输入基准AQL' }]}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="current_aql" label="当前AQL" rules={[{ required: true, message: '请输入当前AQL' }]}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="product_line_code" label="产品线" rules={[{ required: true, message: '请输入产品线' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="min_aql" label="最小AQL">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="max_aql" label="最大AQL">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="inspection_level" label="检验水平">
            <Select allowClear>
              <Select.Option value="I">I</Select.Option>
              <Select.Option value="II">II</Select.Option>
              <Select.Option value="III">III</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
