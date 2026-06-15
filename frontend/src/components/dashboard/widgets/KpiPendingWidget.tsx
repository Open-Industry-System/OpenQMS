import { ClockCircleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import KPICard from "../KPICard";
import type { WidgetProps } from "./types";

export default function KpiPendingWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const value = data.kpi?.pending_actions ?? 0;
  return (
    <KPICard
      title={t("widget.pendingActions")}
      value={value}
      status={value > 0 ? "warning" : "success"}
      icon={<ClockCircleOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
