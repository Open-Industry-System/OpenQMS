import { RiseOutlined } from "@ant-design/icons";
import KPICard from "../KPICard";
import type { WidgetProps } from "./types";

export default function KpiTrendWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.kpi?.month_trend ?? 0;
  const trend = value > 0 ? `↑ +${value}` : value < 0 ? `↓ ${value}` : "—";
  return (
    <KPICard
      title="本月新增"
      value={value}
      status={value > 0 ? "success" : value < 0 ? "danger" : "success"}
      subtitle={trend}
      icon={<RiseOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
