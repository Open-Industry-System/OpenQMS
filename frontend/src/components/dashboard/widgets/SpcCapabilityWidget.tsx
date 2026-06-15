import { Card, Statistic, Button, Row, Col } from "antd";
import { BarChartOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { WidgetProps } from "./types";

export default function SpcCapabilityWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const summary = data.spc?.capability_summary;
  return (
    <Card title={<><BarChartOutlined /> {t("widget.capabilitySummary")}</>} size="small" loading={loading}>
      {error ? (
        <Button onClick={onRetry} size="small">{t("riskList.retry")}</Button>
      ) : (
        <Row gutter={16}>
          <Col span={12}>
            <Statistic title={t("spc.count")} value={summary?.count ?? 0} />
          </Col>
          <Col span={12}>
            <Statistic title={t("spc.avgCpk")} value={summary?.cpk_avg ?? "—"} precision={2} />
          </Col>
        </Row>
      )}
    </Card>
  );
}
