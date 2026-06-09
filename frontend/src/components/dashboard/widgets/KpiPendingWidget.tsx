import { ClockCircleOutlined } from "@ant-design/icons";
import KPICard from "../KPICard";
import type { WidgetProps } from "./types";

export default function KpiPendingWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.kpi?.pending_actions ?? 0;
  return (
    <KPICard
      title="待办事项"
      value={value}
      status={value > 0 ? "warning" : "success"}
      icon={<ClockCircleOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
