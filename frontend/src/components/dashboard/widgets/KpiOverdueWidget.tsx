import { AlertOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import KPICard from "../KPICard";
import type { WidgetProps } from "./types";

export default function KpiOverdueWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const value = data.kpi?.overdue_tasks ?? 0;
  return (
    <KPICard
      title={t("widget.overdueTasks")}
      value={value}
      status={value > 0 ? "danger" : "success"}
      icon={<AlertOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
