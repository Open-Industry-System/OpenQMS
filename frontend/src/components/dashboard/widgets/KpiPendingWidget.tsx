import { useState } from "react";
import { Dropdown } from "antd";
import { ClockCircleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import KPICard from "../KPICard";
import { useKpiDrilldown } from "../useDashboardDrilldown";
import type { WidgetProps } from "./types";

export default function KpiPendingWidget({ data, loading, error, onRetry }: WidgetProps) {
  const { t } = useTranslation("dashboard");
  const value = data.kpi?.pending_actions ?? 0;
  const drilldown = useKpiDrilldown("kpi_pending_actions", data);
  const [open, setOpen] = useState(false);

  const card = (
    <KPICard
      title={t("widget.pendingActions")}
      value={value}
      status={value > 0 ? "warning" : "success"}
      icon={<ClockCircleOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
      // 卡片点击切换菜单（KPICard 仅在非 loading/error 时触发 onClick）；
      // Enter/Space 经 KPICard 的 keydown 复用同一路径，键盘可达。
      onClick={() => setOpen((o) => !o)}
    />
  );

  if (!drilldown.menuItems) return card;

  return (
    <Dropdown
      menu={{ items: drilldown.menuItems, onClick: ({ key }) => drilldown.onMenuClick?.(key) }}
      trigger={["click"]}
      open={open}
      onOpenChange={setOpen}
    >
      {card}
    </Dropdown>
  );
}
