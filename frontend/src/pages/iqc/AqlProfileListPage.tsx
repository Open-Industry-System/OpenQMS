import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card, Table, Badge, Space, Select, Button, Modal, Form, Input, InputNumber, App,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { AqlProfile } from '../../types';
import { listAqlProfiles, createAqlProfile } from '../../api/iqcAql';
import { useAuthStore } from '../../store/authStore';

export default function AqlProfileListPage() {
  const { t } = useTranslation('iqc');
  const { t: tc } = useTranslation('common');
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

  const stateMap = useMemo<Record<string, { label: string; status: 'success' | 'warning' | 'processing' | 'error' | 'default' }>>(
    () => ({
      normal: { label: t('status.profileState.normal'), status: 'success' },
      tightened: { label: t('status.profileState.tightened'), status: 'warning' },
      reduced: { label: t('status.profileState.reduced'), status: 'processing' },
      frozen: { label: t('status.profileState.frozen'), status: 'error' },
    }),
    [t]
  );

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
      message.error(t('messages.loadProfileListFailed'));
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
      message.success(t('messages.profileCreated'));
      setCreateOpen(false);
      createForm.resetFields();
      fetchData();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      message.error(tc('messages.operationFailed'));
    } finally {
      setCreating(false);
    }
  };

  const isAdmin = user?.role_key === 'admin';
  const isEngineer = user?.role_key === 'quality_engineer' || user?.role_key === 'engineer';

  const columns = useMemo(
    () => [
      {
        title: t('table.supplier'),
        dataIndex: 'supplier_id',
        width: 140,
      },
      {
        title: t('table.materialId'),
        dataIndex: 'material_id',
        width: 140,
      },
      {
        title: t('table.baseAql'),
        dataIndex: 'base_aql',
        width: 90,
      },
      {
        title: t('table.currentAql'),
        dataIndex: 'current_aql',
        width: 90,
      },
      {
        title: t('table.state'),
        dataIndex: 'state',
        width: 90,
        render: (state: string) => {
          const cfg = stateMap[state];
          return <Badge status={cfg?.status || 'default'} text={cfg?.label || state} />;
        },
      },
      {
        title: t('table.frozenUntil'),
        dataIndex: 'frozen_until',
        width: 140,
        render: (v: string | null) => v ? new Date(v).toLocaleDateString() : '—',
      },
      {
        title: t('table.effectiveFrom'),
        dataIndex: 'effective_from',
        width: 120,
        render: (v: string) => v ? new Date(v).toLocaleDateString() : '—',
      },
    ],
    [t, stateMap]
  );

  return (
    <div>
      <Card
        title={t('pageTitle.profileList')}
        extra={
          <Space>
            {(isAdmin || isEngineer) && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                {t('actions.newProfile')}
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={fetchData}>{tc('actions.refresh')}</Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            placeholder={t('placeholder.selectStatus')}
            allowClear
            style={{ width: 120 }}
            value={filterState}
            onChange={(v) => { setFilterState(v || undefined); setPage(1); }}
          >
            <Select.Option value="normal">{t('status.profileState.normal')}</Select.Option>
            <Select.Option value="tightened">{t('status.profileState.tightened')}</Select.Option>
            <Select.Option value="reduced">{t('status.profileState.reduced')}</Select.Option>
            <Select.Option value="frozen">{t('status.profileState.frozen')}</Select.Option>
          </Select>
          <Input
            placeholder={t('placeholder.productLine')}
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
        title={t('modal.newProfile')}
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        confirmLoading={creating}
        okText={tc('actions.save')}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="supplier_id" label={t('form.supplierId')} rules={[{ required: true, message: t('validation.enterSupplierId') }]}>
            <Input />
          </Form.Item>
          <Form.Item name="material_id" label={t('form.materialId')} rules={[{ required: true, message: t('validation.enterMaterialId') }]}>
            <Input />
          </Form.Item>
          <Form.Item name="base_aql" label={t('form.baseAql')} rules={[{ required: true, message: t('validation.enterBaseAql') }]}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="current_aql" label={t('form.currentAql')} rules={[{ required: true, message: t('validation.enterCurrentAql') }]}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="product_line_code" label={t('form.productLine')} rules={[{ required: true, message: t('validation.enterProductLine') }]}>
            <Input />
          </Form.Item>
          <Form.Item name="min_aql" label={t('form.minAql')}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="max_aql" label={t('form.maxAql')}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="inspection_level" label={t('form.inspectionLevel')}>
            <Select allowClear placeholder={t('placeholder.selectInspectionLevel')}>
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
