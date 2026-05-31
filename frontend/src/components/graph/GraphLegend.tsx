import { Card, Space, Tag } from "antd";

const NODE_STYLES: Array<{ type: string; label: string; color: string }> = [
  { type: "System", label: "系统", color: "#1890ff" },
  { type: "ProcessItem", label: "过程项", color: "#1890ff" },
  { type: "Subsystem", label: "子系统", color: "#69c0ff" },
  { type: "ProcessStep", label: "工序", color: "#69c0ff" },
  { type: "Component", label: "零部件", color: "#36cfc9" },
  { type: "ProcessWorkElement", label: "工作要素", color: "#36cfc9" },
  { type: "Function", label: "功能", color: "#52c41a" },
  { type: "FailureMode", label: "失效模式", color: "#ff4d4f" },
  { type: "FailureEffect", label: "失效影响", color: "#fa8c16" },
  { type: "FailureCause", label: "失效原因", color: "#faad14" },
  { type: "PreventionControl", label: "预防控制", color: "#73d13d" },
  { type: "DetectionControl", label: "探测控制", color: "#722ed1" },
  { type: "RecommendedAction", label: "建议措施", color: "#8c8c8c" },
];

export default function GraphLegend() {
  return (
    <Card size="small" title="图例" style={{ width: 200 }}>
      <Space direction="vertical" size="small">
        {NODE_STYLES.map((s) => (
          <Tag key={s.type} color={s.color}>
            {s.label}
          </Tag>
        ))}
      </Space>
    </Card>
  );
}
