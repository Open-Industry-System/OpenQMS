import { ExperimentOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function IqcPendingWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.iqc?.pending_inspections ?? 0;
  return (
    <KPICard
      title="IQC 待检批次"
      value={value}
      status={value > 0 ? "warning" : "success"}
      icon={<ExperimentOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
