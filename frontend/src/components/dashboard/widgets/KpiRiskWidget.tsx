import { WarningOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import KPICard from "../KPICard";
import type { WidgetProps } from "./types";

export default function KpiRiskWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const value = data.kpi?.high_risk_items ?? 0;
  return (
    <KPICard
      title={t("widget.highRiskItems")}
      value={value}
      status={value > 0 ? "danger" : "success"}
      icon={<WarningOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
