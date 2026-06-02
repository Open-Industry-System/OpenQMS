import { Card, Tag, Button, Row, Col, Typography, Divider } from "antd";
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
  const summary = analysis.impact_result?.summary;
  const affectedNodes = analysis.impact_result?.affected_nodes ?? [];

  return (
    <div>
      {/* 上部：变更信息卡片 */}
      <Card title="变更信息" size="small">
        <Row gutter={16}>
          <Col span={6}>
            <Text type="secondary">节点名：</Text>
            <Text strong>{analysis.node_name}</Text>
          </Col>
          <Col span={6}>
            <Text type="secondary">类型：</Text>
            <Text>{analysis.node_type}</Text>
          </Col>
          <Col span={6}>
            <Text type="secondary">变更类型：</Text>
            <Tag color={analysis.change_type === "attribute" ? "blue" : "purple"}>
              {analysis.change_type === "attribute" ? "属性" : "结构"}
            </Tag>
          </Col>
          <Col span={6}>
            <Text type="secondary">字段：</Text>
            <Text>{analysis.field_name ?? "—"}</Text>
          </Col>
        </Row>
        {analysis.new_value !== null && (
          <Row style={{ marginTop: 8 }}>
            <Col span={24}>
              <Text type="secondary">新值：</Text>
              <Text>{analysis.new_value}</Text>
            </Col>
          </Row>
        )}
      </Card>

      <Divider />

      {/* 中部：统计卡片 */}
      <Row gutter={16}>
        <Col span={6}>
          <Card size="small">
            <Text type="secondary">影响评分</Text>
            <div style={{ marginTop: 4 }}>
              <ImpactScoreTag score={analysis.impact_score} />
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Text type="secondary">受影响节点数</Text>
            <Title level={4} style={{ margin: "4px 0 0 0" }}>
              {summary?.total_affected ?? 0}
            </Title>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Text type="secondary">FailureMode 数</Text>
            <Title level={4} style={{ margin: "4px 0 0 0" }}>
              {summary?.failure_modes_affected ?? 0}
            </Title>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Text type="secondary">AP 升级数</Text>
            <Title level={4} style={{ margin: "4px 0 0 0" }}>
              {summary?.ap_upgraded_count ?? 0}
            </Title>
          </Card>
        </Col>
      </Row>

      <Divider />

      {/* 下部：受影响节点列表 */}
      <Card title="受影响节点" size="small">
        <AffectedNodeList nodes={affectedNodes} />
      </Card>

      {/* 底部：查看图谱按钮 */}
      {onViewGraph && (
        <div style={{ marginTop: 16, textAlign: "center" }}>
          <Button type="primary" onClick={onViewGraph}>
            在图谱中查看
          </Button>
        </div>
      )}
    </div>
  );
}
