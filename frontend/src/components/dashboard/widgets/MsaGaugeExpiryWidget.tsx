import { ToolOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function MsaGaugeExpiryWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const value = data.msa?.gauges_expiring_30d ?? 0;
  return (
    <KPICard
      title={t("widget.gaugeExpiry")}
      value={value}
      status={value > 0 ? "warning" : "success"}
      subtitle={t("kpi.subtitle.gaugeExpiry")}
      icon={<ToolOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
