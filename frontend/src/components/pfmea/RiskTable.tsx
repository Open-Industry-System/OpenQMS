import { useTranslation } from 'react-i18next';
import { Table, InputNumber, Popover, Tag, Tooltip } from 'antd';
import type { GraphNode, GraphEdge } from '../../types';
import { buildRows, getRowSeverity, type FMEARow } from '../../utils/fmeaTable';
import { calculateAP } from '../../utils/fmea';

interface RiskTableProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  fmeaId: string;
  onChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}

/** severity = max(plant, customer, user); 0 if any unset (caller treats 0 as unrated). */
export function computeSeverity(plant: number, customer: number, user: number): number {
  return Math.max(plant || 0, customer || 0, user || 0);
}

/** CC wins; else list SC WEF names (collapse to SC×N when >2); '-' when none. */
export function aggregateSpecialCharacteristic(
  stepFunc: GraphNode | undefined,
  weFunctionNodes: GraphNode[],
  edges: GraphEdge[],
): { label: string; tag: 'CC' | 'SC' | '-' } {
  if (stepFunc?.classification === 'CC') return { label: 'CC', tag: 'CC' };
  const scWefs = weFunctionNodes.filter((w) =>
    w.classification === 'SC' && edges.some((e) => e.source === stepFunc?.id && e.target === w.id && e.type === 'FUNCTION_MAPPED_TO'));
  if (scWefs.length === 0) return { label: '-', tag: '-' };
  if (scWefs.length <= 2) return { label: `SC(${scWefs.map((w) => w.name).join('/')})`, tag: 'SC' };
  return { label: `SC×${scWefs.length}`, tag: 'SC' };
}

export default function RiskTable({ nodes, edges, fmeaId, onChange }: RiskTableProps) {
  const { t } = useTranslation('pfmea');
  void fmeaId;
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const rows = buildRows(nodes, edges);

  const updateNode = (id: string, patch: Partial<GraphNode>) =>
    onChange(nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)), edges);

  const columns = [
    {
      title: t('wizard.failure.failureEffect'), dataIndex: 'effect', key: 'effect',
      render: (_: unknown, row: FMEARow) => row.failureEffectNodeIds.map((id) => nodeMap.get(id)?.name).join(' / '),
    },
    {
      title: 'S', key: 'severity', width: 90,
      render: (_: unknown, row: FMEARow) => {
        const feId = row.failureEffectNodeIds[0];
        const fe = feId ? nodeMap.get(feId) : undefined;
        const content = (
          <div style={{ display: 'grid', gap: 4 }}>
            <label>{t('wizard.risk.severityPlant')}<InputNumber min={0} max={10} value={fe?.severity_plant ?? 0}
              onChange={(v) => {
                const plant = v ?? 0;
                updateNode(feId!, { severity_plant: plant, severity: computeSeverity(plant, fe?.severity_customer ?? 0, fe?.severity_user ?? 0) });
              }} /></label>
            <label>{t('wizard.risk.severityCustomer')}<InputNumber min={0} max={10} value={fe?.severity_customer ?? 0}
              onChange={(v) => {
                const c = v ?? 0;
                updateNode(feId!, { severity_customer: c, severity: computeSeverity(fe?.severity_plant ?? 0, c, fe?.severity_user ?? 0) });
              }} /></label>
            <label>{t('wizard.risk.severityUser')}<InputNumber min={0} max={10} value={fe?.severity_user ?? 0}
              onChange={(v) => {
                const u = v ?? 0;
                updateNode(feId!, { severity_user: u, severity: computeSeverity(fe?.severity_plant ?? 0, fe?.severity_customer ?? 0, u) });
              }} /></label>
          </div>
        );
        return (
          <Popover content={content} title={t('wizard.risk.severityDialog')} trigger="click">
            <ButtonLike value={fe?.severity ?? 0} />
          </Popover>
        );
      },
    },
    { title: t('wizard.failure.failureMode'), key: 'fm', render: (_: unknown, row: FMEARow) => nodeMap.get(row.failureModeNodeId)?.name },
    { title: t('wizard.failure.failureCause'), key: 'fc', render: (_: unknown, row: FMEARow) => row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId)?.name : '' },
    { title: t('wizard.failure.preventionControl'), key: 'pc', render: (_: unknown, row: FMEARow) => row.preventionControlIds[0] ? nodeMap.get(row.preventionControlIds[0])?.name : '' },
    {
      title: 'O', key: 'o', width: 70,
      render: (_: unknown, row: FMEARow) => {
        const pcName = row.preventionControlIds[0] ? nodeMap.get(row.preventionControlIds[0])?.name ?? '' : '';
        const disabled = !pcName.trim();
        return <InputNumber min={0} max={10} disabled={disabled} value={row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId)?.occurrence ?? 0 : 0}
          onChange={(v) => updateNode(row.failureCauseNodeId!, { occurrence: v ?? 0 })} style={{ width: 60 }} />;
      },
    },
    { title: t('wizard.failure.detectionControl'), key: 'dc', render: (_: unknown, row: FMEARow) => row.detectionControlIds[0] ? nodeMap.get(row.detectionControlIds[0])?.name : '' },
    {
      title: 'D', key: 'd', width: 70,
      render: (_: unknown, row: FMEARow) => {
        const dcId = row.detectionControlIds[0];
        const dcName = dcId ? nodeMap.get(dcId)?.name ?? '' : '';
        const disabled = !dcName.trim();
        return <InputNumber min={0} max={10} disabled={disabled} value={dcId ? nodeMap.get(dcId)?.detection ?? 0 : 0}
          onChange={(v) => updateNode(dcId!, { detection: v ?? 0 })} style={{ width: 60 }} />;
      },
    },
    {
      title: t('wizard.risk.ap'), key: 'ap', width: 60,
      render: (_: unknown, row: FMEARow) => {
        const s = getRowSeverity(row, nodeMap);
        const o = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId)?.occurrence ?? 0 : 0;
        const d = row.detectionControlIds[0] ? nodeMap.get(row.detectionControlIds[0])?.detection ?? 0 : 0;
        const ap = calculateAP(s, o, d);
        const color = ap === 'H' ? 'red' : ap === 'M' ? 'orange' : 'default';
        return ap ? <Tag color={color}>{ap}</Tag> : '';
      },
    },
    {
      title: t('wizard.risk.class'), key: 'class', width: 90,
      render: (_: unknown, row: FMEARow) => {
        const stepFunc = nodeMap.get(row.functionNodeId);
        const wefs = nodes.filter((n) => n.type === 'ProcessWorkElementFunction');
        const { label, tag } = aggregateSpecialCharacteristic(stepFunc, wefs, edges);
        const bg = tag === 'CC' ? '#fff1f0' : tag === 'SC' ? '#fffbe6' : undefined;
        return <Tooltip title={label}><Tag style={{ background: bg }}>{label}</Tag></Tooltip>;
      },
    },
  ];

  return <Table rowKey="key" dataSource={rows} columns={columns as any} pagination={false} size="small" bordered />;
}

function ButtonLike({ value }: { value: number }) {
  return (
    <a
      role="button"
      tabIndex={0}
      aria-label={typeof value === 'number' && value > 0 ? `severity ${value}` : 'severity unrated'}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.currentTarget.click();
        }
      }}
    >
      {value || '-'}
    </a>
  );
}
