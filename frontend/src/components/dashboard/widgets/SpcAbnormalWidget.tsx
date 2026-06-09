import { WarningOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function SpcAbnormalWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.spc?.abnormal_count ?? 0;
  return (
    <KPICard
      title="SPC 异常点数"
      value={value}
      status={value > 0 ? "danger" : "success"}
      subtitle="近7天"
      icon={<WarningOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
