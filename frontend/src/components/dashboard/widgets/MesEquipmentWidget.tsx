import { Card, Statistic, Button, Row, Col } from "antd";
import { ToolOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { WidgetProps } from "./types";

export default function MesEquipmentWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const mes = data.mes ?? {};
  return (
    <Card title={<><ToolOutlined /> {t("widget.equipmentStatus")}</>} size="small" loading={loading}>
      {error ? (
        <Button onClick={onRetry} size="small">{t("riskList.retry")}</Button>
      ) : (
        <Row gutter={16}>
          <Col span={8}>
            <Statistic title={t("equipment.running")} value={mes.equipment_running ?? 0} valueStyle={{ color: "#52c41a" }} />
          </Col>
          <Col span={8}>
            <Statistic title={t("equipment.down")} value={mes.equipment_down ?? 0} valueStyle={{ color: "#ff4d4f" }} />
          </Col>
          <Col span={8}>
            <Statistic title={t("equipment.idle")} value={mes.equipment_idle ?? 0} valueStyle={{ color: "#faad14" }} />
          </Col>
        </Row>
      )}
    </Card>
  );
}
