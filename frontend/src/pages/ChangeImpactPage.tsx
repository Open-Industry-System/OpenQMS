import { useState, useEffect } from "react";
import { App, Card, Col, Row, Typography } from "antd";
import { useTranslation } from "react-i18next";
import { ChangeHistoryTable, ImpactReportPanel } from "../components/change-impact";
import { listAllChangeImpacts, getChangeImpact } from "../api/changeImpact";
import type { ChangeImpactAnalysis, PaginatedChangeImpactResponse } from "../api/changeImpact";

export default function ChangeImpactPage() {
  const { t } = useTranslation("changeImpact");
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
      message.error(t("messages.loadHistoryFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (record: ChangeImpactAnalysis) => {
    try {
      const detail = await getChangeImpact(record.id);
      setSelected(detail);
    } catch (_err) {
      message.error(t("messages.loadDetailFailed"));
    }
  };

  const handleViewGraph = () => {
    if (!selected) return;
    const url = `/fmea/${selected.fmea_id}?tab=graph&highlightNode=${selected.node_id}`;
    window.open(url, "_blank");
  };

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>{t("page.title")}</Typography.Title>
      <Row gutter={16}>
        <Col span={10}>
          <Card title={t("page.history")} loading={loading}>
            <ChangeHistoryTable data={history} onSelect={handleSelect} />
          </Card>
        </Col>
        <Col span={14}>
          <Card title={t("page.detail")}>
            {selected ? (
              <ImpactReportPanel analysis={selected} onViewGraph={handleViewGraph} />
            ) : (
              <Typography.Text type="secondary">{t("page.selectHint")}</Typography.Text>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
