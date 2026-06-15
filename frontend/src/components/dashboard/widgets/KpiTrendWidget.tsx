import { RiseOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import KPICard from "../KPICard";
import type { WidgetProps } from "./types";

export default function KpiTrendWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const value = data.kpi?.month_trend ?? 0;
  const trend = value > 0 ? `↑ +${value}` : value < 0 ? `↓ ${value}` : "—";
  return (
    <KPICard
      title={t("widget.monthTrend")}
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
