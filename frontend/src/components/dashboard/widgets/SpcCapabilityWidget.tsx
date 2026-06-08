import { Card, Statistic, Button, Row, Col } from "antd";
import { BarChartOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function SpcCapabilityWidget({ data, loading, error, onRetry }: WidgetProps) {
  const summary = data.spc?.capability_summary;
  return (
    <Card title={<><BarChartOutlined /> 过程能力摘要</>} size="small" loading={loading}>
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : (
        <Row gutter={16}>
          <Col span={12}>
            <Statistic title="监控项数" value={summary?.count ?? 0} />
          </Col>
          <Col span={12}>
            <Statistic title="平均 CPK" value={summary?.cpk_avg ?? "—"} precision={2} />
          </Col>
        </Row>
      )}
    </Card>
  );
}
