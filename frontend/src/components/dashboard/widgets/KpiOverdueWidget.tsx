import { AlertOutlined } from "@ant-design/icons";
import KPICard from "../KPICard";
import type { WidgetProps } from "./types";

export default function KpiOverdueWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.kpi?.overdue_tasks ?? 0;
  return (
    <KPICard
      title="超期任务"
      value={value}
      status={value > 0 ? "danger" : "success"}
      icon={<AlertOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
