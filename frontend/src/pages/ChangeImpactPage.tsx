import { useState, useEffect } from "react";
import { App, Col, Row, Spin, Typography } from "antd";
import { ChangeHistoryTable, ImpactReportPanel } from "../components/change-impact";
import { listAllChangeImpacts, getChangeImpact } from "../api/changeImpact";
import type { ChangeImpactAnalysis, PaginatedChangeImpactResponse } from "../api/changeImpact";
import { useTranslation } from "react-i18next";
import { PageShell, DataCard } from "../components/design";

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
    <PageShell title={t("page.title")}>
      <Row gutter={16}>
        <Col span={10}>
          <DataCard title={t("page.history")} noPadding>
            <Spin spinning={loading}>
              <ChangeHistoryTable data={history} onSelect={handleSelect} />
            </Spin>
          </DataCard>
        </Col>
        <Col span={14}>
          <DataCard title={t("page.detail")}>
            {selected ? (
              <ImpactReportPanel analysis={selected} onViewGraph={handleViewGraph} />
            ) : (
              <Typography.Text type="secondary">{t("page.selectHint")}</Typography.Text>
            )}
          </DataCard>
        </Col>
      </Row>
    </PageShell>
  );
}
