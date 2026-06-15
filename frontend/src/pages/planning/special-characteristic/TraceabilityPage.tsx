import { useEffect, useState } from 'react';
import { Typography, Select, Space, Timeline, Empty, Spin, Alert } from 'antd';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  SafetyOutlined,
  FileTextOutlined,
  ExperimentOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import client from '../../../api/client';
import type { SpecialCharacteristic } from '../../../types/specialCharacteristic';
import { PageShell, DataCard, StatusBadge } from '../../../components/design';

const { Title, Text } = Typography;

interface FmeaSource {
  fmea_id: string;
  document_no: string;
  title: string;
  fmea_type: string;
  node_id: string;
  node_name: string;
  node_type: string;
  connected_failure_modes: { id: string; name: string; type: string }[];
}

interface CPItem {
  item_id: string;
  step_no: string;
  process_name: string;
  characteristic_no: string;
  special_class: string;
  specification_tolerance: string;
  cp_document_no: string;
  cp_title: string;
}

interface SPChar {
  ic_id: string;
  characteristic_name: string;
  chart_type: string;
  spec_target: number | null;
  spec_upper: number | null;
  spec_lower: number | null;
}

interface TraceabilityChain {
  sc_code: string;
  sc_name: string;
  sc_type: string;
  spec_requirement: string;
  product_line_code: string;
  fmea_source: FmeaSource | null;
  control_plan_items: CPItem[];
  spc_characteristics: SPChar[];
}

export default function TraceabilityPage() {
  const { t } = useTranslation('specialCharacteristic');
  const [scList, setScList] = useState<SpecialCharacteristic[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chain, setChain] = useState<TraceabilityChain | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    client.get('/api/special-characteristics/list').then((r) => setScList(r.data.items));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setChain(null);
      return;
    }
    setLoading(true);
    client
      .get(`/api/special-characteristics/traceability/${selectedId}`)
      .then((r) => setChain(r.data))
      .catch(() => setChain(null))
      .finally(() => setLoading(false));
  }, [selectedId]);

  return (
    <PageShell title={t('pageTitle.scTraceability')}>
      <DataCard title={null} style={{ marginBottom: 24 }}>
        <Space>
          <Text strong>{t('traceability.selectSC')}：</Text>
          <Select
            style={{ width: 360 }}
            placeholder={t('traceability.placeholder')}
            allowClear
            value={selectedId}
            onChange={setSelectedId}
            showSearch
            optionFilterProp="label"
            options={scList.map((sc) => ({
              value: sc.sc_id,
              label: `${sc.sc_code} - ${sc.sc_name} (${sc.sc_type})`,
            }))}
          />
        </Space>
      </DataCard>

      {loading && <Spin size="large" style={{ display: 'block', margin: '40px auto' }} />}

      {!loading && selectedId && !chain && (
        <Alert type="warning" message={t('traceability.loadFailed')} showIcon />
      )}

      {!loading && chain && (
        <div>
          <DataCard title={null} style={{ marginBottom: 24 }}>
            <Space>
              <StatusBadge status={chain.sc_type === 'CC' ? 'critical' : 'warning'}>
                {chain.sc_type}
              </StatusBadge>
              <Title level={5} style={{ margin: 0 }}>{chain.sc_code} - {chain.sc_name}</Title>
            </Space>
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">{t('traceability.specRequirement')}：</Text> {chain.spec_requirement || '—'}
            </div>
          </DataCard>

          <Timeline
            style={{ marginTop: 24 }}
            items={[
              {
                dot: <SafetyOutlined style={{ fontSize: 18 }} />,
                color: 'blue',
                children: (
                  <DataCard title={t('traceability.fmeaSource')} style={{ marginBottom: 16 }}>
                    {chain.fmea_source ? (
                      <div>
                        <Link to={`/fmea/${chain.fmea_source.fmea_id}`}>
                          <Text strong>{chain.fmea_source.document_no}</Text>
                        </Link>
                        <Text type="secondary"> — {chain.fmea_source.title}</Text>
                        <div style={{ marginTop: 8 }}>
                          <StatusBadge status="info">{chain.fmea_source.fmea_type}</StatusBadge>
                          <Text>{t('traceability.step')}: {chain.fmea_source.node_name} ({chain.fmea_source.node_type})</Text>
                        </div>
                        {chain.fmea_source.connected_failure_modes.length > 0 && (
                          <div style={{ marginTop: 8 }}>
                            <Text type="secondary">{t('traceability.relatedFailureModes')}：</Text>
                            {chain.fmea_source.connected_failure_modes.map((fm) => (
                              <StatusBadge key={fm.id} status="info" style={{ marginTop: 4 }}>
                                {fm.name}
                              </StatusBadge>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <Text type="secondary">{t('traceability.notLinkedFMEA')}</Text>
                    )}
                  </DataCard>
                ),
              },
              {
                dot: <FileTextOutlined style={{ fontSize: 18 }} />,
                color: 'green',
                children: (
                  <DataCard title={t('traceability.controlPlan')} style={{ marginBottom: 16 }}>
                    {chain.control_plan_items.length > 0 ? (
                      <div>
                        {chain.control_plan_items.map((item) => (
                          <div key={item.item_id} style={{ marginBottom: 12, padding: 8, background: '#f6ffed', borderRadius: 4 }}>
                            <Text strong>{item.cp_document_no}</Text>
                            <Text type="secondary"> — {item.cp_title}</Text>
                            <div style={{ marginTop: 4 }}>
                              <StatusBadge status="info">{t('traceability.step')} {item.step_no}</StatusBadge>
                              <Text> {item.process_name} / {item.characteristic_no}</Text>
                            </div>
                            <div style={{ marginTop: 4 }}>
                              <Text type="secondary">{t('traceability.specification')}：</Text> {item.specification_tolerance}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <Text type="secondary">{t('traceability.notInControlPlan')}</Text>
                    )}
                  </DataCard>
                ),
              },
              {
                dot: <ExperimentOutlined style={{ fontSize: 18 }} />,
                color: 'orange',
                children: (
                  <DataCard title={t('traceability.msaAnalysis')} style={{ marginBottom: 16 }}>
                    <Text type="secondary">{t('traceability.msaDescription')}</Text>
                  </DataCard>
                ),
              },
              {
                dot: <BarChartOutlined style={{ fontSize: 18 }} />,
                color: 'purple',
                children: (
                  <DataCard title={t('traceability.spcMonitor')}>
                    {chain.spc_characteristics.length > 0 ? (
                      <div>
                        {chain.spc_characteristics.map((ic) => (
                          <div key={ic.ic_id} style={{ marginBottom: 12, padding: 8, background: '#f9f0ff', borderRadius: 4 }}>
                            <Text strong>{ic.characteristic_name}</Text>
                            <StatusBadge status="info" style={{ marginLeft: 8 }}>{ic.chart_type}</StatusBadge>
                            <div style={{ marginTop: 4 }}>
                              {ic.spec_target !== null && <Text>{t('traceability.targetValue')}: {ic.spec_target} </Text>}
                              {ic.spec_upper !== null && <Text>USL: {ic.spec_upper} </Text>}
                              {ic.spec_lower !== null && <Text>LSL: {ic.spec_lower}</Text>}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <Text type="secondary">{t('traceability.notLinkedSPC')}</Text>
                    )}
                  </DataCard>
                ),
              },
            ]}
          />
        </div>
      )}

      {!selectedId && !loading && (
        <Empty description={t('traceability.emptyHint')} />
      )}
    </PageShell>
  );
}
