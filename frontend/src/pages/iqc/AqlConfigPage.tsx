import { useState, useEffect } from 'react';
import { Form, Input, Select, Button, App, Row, Col, Space, Spin } from 'antd';
import { RestOutlined, SaveOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { AqlConfig } from '../../types';
import { listAqlConfigs, updateAqlConfig, resetAqlConfigs } from '../../api/iqcAql';
import { useAuthStore } from '../../store/authStore';
import { PageShell, DataCard } from '../../components/design';

export default function AqlConfigPage() {
  const { t } = useTranslation('iqc');
  const { t: tc } = useTranslation('common');
  const { message, modal } = App.useApp();
  const user = useAuthStore((s) => s.user);
  const [configs, setConfigs] = useState<AqlConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [productLine, setProductLine] = useState<string | undefined>();
  const [form] = Form.useForm();

  const isAdmin = user?.role_key === 'admin';

  const fetchConfigs = async (pl?: string) => {
    setLoading(true);
    try {
      const data = await listAqlConfigs(pl);
      setConfigs(data);
      // Set form values
      const formValues: Record<string, string> = {};
      data.forEach((c) => { formValues[c.config_key] = c.config_value; });
      form.setFieldsValue(formValues);
    } catch {
      message.error(t('messages.loadConfigFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigs(productLine);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productLine]);

  if (!isAdmin) {
    return (
      <PageShell title={t('pageTitle.aqlConfig')}>
        <DataCard title="">
          <div style={{ textAlign: 'center', padding: 48, color: '#999' }}>{t('messages.adminOnly')}</div>
        </DataCard>
      </PageShell>
    );
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      // Only save changed values
      const updates = configs.filter((c) => values[c.config_key] !== c.config_value);
      await Promise.all(updates.map((c) => updateAqlConfig(c.config_key, { config_value: values[c.config_key] })));
      message.success(t('messages.configSaved'));
      fetchConfigs(productLine);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      message.error(tc('messages.operationFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    modal.confirm({
      title: t('modal.resetConfigTitle'),
      content: t('modal.resetConfigContent'),
      onOk: async () => {
        try {
          await resetAqlConfigs();
          message.success(t('messages.configReset'));
          fetchConfigs(productLine);
        } catch {
          message.error(tc('messages.operationFailed'));
        }
      },
    });
  };

  return (
    <PageShell
      title={t('pageTitle.aqlConfig')}
      actions={
        <Select
          placeholder={t('placeholder.productLineWithGlobal')}
          allowClear
          style={{ width: 200 }}
          value={productLine}
          onChange={(v) => setProductLine(v || undefined)}
        >
          <Select.Option value="DC-DC-100">DC-DC-100</Select.Option>
        </Select>
      }
    >
      <DataCard title="">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>
        ) : (
          <Form form={form} layout="vertical">
            <Row gutter={16}>
              {configs.map((c) => (
                <Col span={8} key={c.config_key}>
                  <Form.Item
                    name={c.config_key}
                    label={
                      <span>
                        {c.config_key}
                        {c.description && <span style={{ color: '#999', fontSize: 12, marginLeft: 4 }}>({c.description})</span>}
                      </span>
                    }
                  >
                    <Input disabled={!c.is_editable} />
                  </Form.Item>
                </Col>
              ))}
            </Row>
            <Space style={{ marginTop: 16 }}>
              <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
                {tc('actions.save')}
              </Button>
              <Button icon={<RestOutlined />} onClick={handleReset}>
                {t('actions.resetConfig')}
              </Button>
            </Space>
          </Form>
        )}
      </DataCard>
    </PageShell>
  );
}
