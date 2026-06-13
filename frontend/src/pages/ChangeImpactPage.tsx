import { useState, useEffect } from "react";
import { App, Card, Col, Row, Typography } from "antd";
import { ChangeHistoryTable, ImpactReportPanel } from "../components/change-impact";
import { listAllChangeImpacts, getChangeImpact } from "../api/changeImpact";
import type { ChangeImpactAnalysis, PaginatedChangeImpactResponse } from "../api/changeImpact";

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
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>变更影响分析</Typography.Title>
      <Row gutter={16}>
        <Col span={10}>
          <Card title="分析历史" loading={loading}>
            <ChangeHistoryTable data={history} onSelect={handleSelect} />
          </Card>
        </Col>
        <Col span={14}>
          <Card title="分析详情">
            {selected ? (
              <ImpactReportPanel analysis={selected} onViewGraph={handleViewGraph} />
            ) : (
              <Typography.Text type="secondary">请选择左侧历史记录查看详情</Typography.Text>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
