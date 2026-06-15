import { useTranslation } from 'react-i18next';
import type { AqlQualitySnapshot } from '../../types';

interface Props {
  snapshots: AqlQualitySnapshot[];
}

export default function AqlQualityChart({ snapshots }: Props) {
  const { t } = useTranslation('iqc');

  if (!snapshots || snapshots.length === 0) {
    return <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>{t('chart.noTrendData')}</div>;
  }

  // Placeholder — @ant-design/charts not installed
  return (
    <div style={{ padding: 24, textAlign: 'center', color: '#999', border: '1px dashed #d9d9d9', borderRadius: 8 }}>
      {t('chart.trendChartPlaceholder')}
      <div style={{ marginTop: 8, fontSize: 12 }}>
        {t('chart.snapshotCount', { count: snapshots.length })}
      </div>
    </div>
  );
}
