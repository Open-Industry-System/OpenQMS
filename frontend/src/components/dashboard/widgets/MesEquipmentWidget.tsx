import { Card, Statistic, Button, Row, Col } from "antd";
import { ToolOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { usePermission } from "../../../hooks/usePermission";
import type { WidgetProps } from "./types";

export default function MesEquipmentWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const navigate = useNavigate();
  const { canView } = usePermission();
  const mes = data.mes ?? {};
  const canDrill = canView("mes");
  return (
    <Card
      title={<><ToolOutlined /> {t("widget.equipmentStatus")}</>}
      size="small"
      loading={loading}
      hoverable={canDrill}
      onClick={canDrill ? () => navigate("/mes/dashboard") : undefined}
      style={{ cursor: canDrill ? "pointer" : "default", height: "100%", opacity: canDrill ? 1 : 0.6 }}
    >
      {error ? (
        <Button onClick={(e) => { e.stopPropagation(); onRetry(); }} size="small">{t("riskList.retry")}</Button>
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
