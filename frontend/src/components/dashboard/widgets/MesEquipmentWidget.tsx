import { Card, Statistic, Button, Row, Col } from "antd";
import { ToolOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function MesEquipmentWidget({ data, loading, error, onRetry }: WidgetProps) {
  const mes = data.mes ?? {};
  return (
    <Card title={<><ToolOutlined /> 设备状态概览</>} size="small" loading={loading}>
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : (
        <Row gutter={16}>
          <Col span={8}>
            <Statistic title="运行中" value={mes.equipment_running ?? 0} valueStyle={{ color: "#52c41a" }} />
          </Col>
          <Col span={8}>
            <Statistic title="停机" value={mes.equipment_down ?? 0} valueStyle={{ color: "#ff4d4f" }} />
          </Col>
          <Col span={8}>
            <Statistic title="空闲" value={mes.equipment_idle ?? 0} valueStyle={{ color: "#faad14" }} />
          </Col>
        </Row>
      )}
    </Card>
  );
}
