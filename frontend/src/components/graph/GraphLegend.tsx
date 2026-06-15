import { Card, Space, Tag } from "antd";
import { useTranslation } from "react-i18next";

const NODE_TYPES = [
  { type: "System", key: "system", color: "#1890ff" },
  { type: "ProcessItem", key: "processItem", color: "#1890ff" },
  { type: "Subsystem", key: "subsystem", color: "#69c0ff" },
  { type: "ProcessStep", key: "processStep", color: "#69c0ff" },
  { type: "Component", key: "component", color: "#36cfc9" },
  { type: "ProcessWorkElement", key: "processWorkElement", color: "#36cfc9" },
  { type: "Function", key: "function", color: "#52c41a" },
  { type: "FailureMode", key: "failureMode", color: "#ff4d4f" },
  { type: "FailureEffect", key: "failureEffect", color: "#fa8c16" },
  { type: "FailureCause", key: "failureCause", color: "#faad14" },
  { type: "PreventionControl", key: "preventionControl", color: "#73d13d" },
  { type: "DetectionControl", key: "detectionControl", color: "#722ed1" },
  { type: "RecommendedAction", key: "recommendedAction", color: "#8c8c8c" },
];

export default function GraphLegend() {
  const { t } = useTranslation("graph");
  return (
    <Card size="small" title={t("legend.title")} style={{ width: 200 }}>
      <Space direction="vertical" size="small">
        {NODE_TYPES.map((s) => (
          <Tag key={s.type} color={s.color}>
            {t(`legend.${s.key}`)}
          </Tag>
        ))}
      </Space>
    </Card>
  );
}
