import type { AqlQualitySnapshot } from '../../types';

interface Props {
  snapshots: AqlQualitySnapshot[];
}

export default function AqlQualityChart({ snapshots }: Props) {
  if (!snapshots || snapshots.length === 0) {
    return <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>暂无趋势数据</div>;
  }

  // Placeholder — @ant-design/charts not installed
  return (
    <div style={{ padding: 24, textAlign: 'center', color: '#999', border: '1px dashed #d9d9d9', borderRadius: 8 }}>
      趋势图 (需要安装 @ant-design/charts)
      <div style={{ marginTop: 8, fontSize: 12 }}>
        共 {snapshots.length} 个快照数据点
      </div>
    </div>
  );
}
