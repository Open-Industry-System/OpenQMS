import { WarningOutlined } from "@ant-design/icons";
import KPICard from "../KPICard";
import type { WidgetProps } from "./types";

export default function KpiRiskWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.kpi?.high_risk_items ?? 0;
  return (
    <KPICard
      title="高风险项"
      value={value}
      status={value > 0 ? "danger" : "success"}
      icon={<WarningOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
