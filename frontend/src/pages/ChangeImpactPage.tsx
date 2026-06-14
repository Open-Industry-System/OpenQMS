import { useState, useEffect } from "react";
import { App, Col, Row, Spin, Typography } from "antd";
import { ChangeHistoryTable, ImpactReportPanel } from "../components/change-impact";
import { listAllChangeImpacts, getChangeImpact } from "../api/changeImpact";
import type { ChangeImpactAnalysis, PaginatedChangeImpactResponse } from "../api/changeImpact";
import { PageShell, DataCard } from "../components/design";

export default function ChangeImpactPage() {
  const { message } = App.useApp();
  const [history, setHistory] = useState<ChangeImpactAnalysis[]>([]);
  const [selected, setSelected] = useState<ChangeImpactAnalysis | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { loadHistory(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const resp: PaginatedChangeImpactResponse = await listAllChangeImpacts();
      setHistory(resp.items);
    } catch (_err) {
      message.error("加载历史失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (record: ChangeImpactAnalysis) => {
    try {
      const detail = await getChangeImpact(record.id);
      setSelected(detail);
    } catch (_err) {
      message.error("获取详情失败");
    }
  };

  const handleViewGraph = () => {
    if (!selected) return;
    const url = `/fmea/${selected.fmea_id}?tab=graph&highlightNode=${selected.node_id}`;
    window.open(url, "_blank");
  };

  return (
    <PageShell title="变更影响分析">
      <Row gutter={16}>
        <Col span={10}>
          <DataCard title="分析历史" noPadding>
            <Spin spinning={loading}>
              <ChangeHistoryTable data={history} onSelect={handleSelect} />
            </Spin>
          </DataCard>
        </Col>
        <Col span={14}>
          <DataCard title="分析详情">
            {selected ? (
              <ImpactReportPanel analysis={selected} onViewGraph={handleViewGraph} />
            ) : (
              <Typography.Text type="secondary">请选择左侧历史记录查看详情</Typography.Text>
            )}
          </DataCard>
        </Col>
      </Row>
    </PageShell>
  );
}
