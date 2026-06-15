import { Card, Tag, Button, Row, Col, Typography, Divider } from "antd";
import { useTranslation } from "react-i18next";
import type { ChangeImpactAnalysis } from "../../api/changeImpact";
import ImpactScoreTag from "./ImpactScoreTag";
import AffectedNodeList from "./AffectedNodeList";

interface ImpactReportPanelProps {
  analysis: ChangeImpactAnalysis;
  onViewGraph?: () => void;
}

const { Text, Title } = Typography;

export default function ImpactReportPanel({
  analysis,
  onViewGraph,
}: ImpactReportPanelProps) {
  const { t } = useTranslation("changeImpact");
  const summary = analysis.impact_result?.summary;
  const affectedNodes = analysis.impact_result?.affected_nodes ?? [];

  return (
    <div>
      <Card title={t("report.changeInfo")} size="small">
        <Row gutter={16}>
          <Col span={6}>
            <Text type="secondary">{t("report.nodeName")}：</Text>
            <Text strong>{analysis.node_name}</Text>
          </Col>
          <Col span={6}>
            <Text type="secondary">{t("report.type")}：</Text>
            <Text>{analysis.node_type}</Text>
          </Col>
          <Col span={6}>
            <Text type="secondary">{t("report.changeType")}：</Text>
            <Tag color={analysis.change_type === "attribute" ? "blue" : "purple"}>
              {analysis.change_type === "attribute" ? t("report.changeTypeAttribute") : t("report.changeTypeStructure")}
            </Tag>
          </Col>
          <Col span={6}>
            <Text type="secondary">{t("report.field")}：</Text>
            <Text>{analysis.field_name ?? "—"}</Text>
          </Col>
        </Row>
        {analysis.new_value !== null && (
          <Row style={{ marginTop: 8 }}>
            <Col span={24}>
              <Text type="secondary">{t("report.newValue")}：</Text>
              <Text>{analysis.new_value}</Text>
            </Col>
          </Row>
        )}
      </Card>

      <Divider />

      <Row gutter={16}>
        <Col span={6}>
          <Card size="small">
            <Text type="secondary">{t("report.impactScore")}</Text>
            <div style={{ marginTop: 4 }}>
              <ImpactScoreTag score={analysis.impact_score} />
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Text type="secondary">{t("report.affectedNodesCount")}</Text>
            <Title level={4} style={{ margin: "4px 0 0 0" }}>
              {summary?.total_affected ?? 0}
            </Title>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Text type="secondary">{t("report.failureModeCount")}</Text>
            <Title level={4} style={{ margin: "4px 0 0 0" }}>
              {summary?.failure_modes_affected ?? 0}
            </Title>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Text type="secondary">{t("report.apUpgradedCount")}</Text>
            <Title level={4} style={{ margin: "4px 0 0 0" }}>
              {summary?.ap_upgraded_count ?? 0}
            </Title>
          </Card>
        </Col>
      </Row>

      <Divider />

      <Card title={t("report.affectedNodes")} size="small">
        <AffectedNodeList nodes={affectedNodes} />
      </Card>

      {onViewGraph && (
        <div style={{ marginTop: 16, textAlign: "center" }}>
          <Button type="primary" onClick={onViewGraph}>
            {t("report.viewInGraph")}
          </Button>
        </div>
      )}
    </div>
  );
}
