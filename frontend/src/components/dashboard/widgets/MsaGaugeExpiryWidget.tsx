import { ToolOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function MsaGaugeExpiryWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.msa?.gauges_expiring_30d ?? 0;
  return (
    <KPICard
      title="量具到期提醒"
      value={value}
      status={value > 0 ? "warning" : "success"}
      subtitle="30天内到期"
      icon={<ToolOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
