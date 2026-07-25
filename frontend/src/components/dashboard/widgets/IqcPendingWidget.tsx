import { ExperimentOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import KPICard from "../../dashboard/KPICard";
import { useKpiDrilldown } from "../useDashboardDrilldown";
import type { WidgetProps } from "./types";

export default function IqcPendingWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const value = data.iqc?.pending_inspections ?? 0;
  const drilldown = useKpiDrilldown("iqc_pending_inspections", data);
  return (
    <KPICard
      title={t("widget.iqcPendingInspections")}
      value={value}
      status={value > 0 ? "warning" : "success"}
      icon={<ExperimentOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
      onClick={drilldown.onClick}
      disabled={drilldown.disabled}
    />
  );
}
