import { WarningOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function SpcAbnormalWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const value = data.spc?.abnormal_count ?? 0;
  return (
    <KPICard
      title={t("widget.spcAbnormalCount")}
      value={value}
      status={value > 0 ? "danger" : "success"}
      subtitle={t("kpi.subtitle.spcAbnormal")}
      icon={<WarningOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
