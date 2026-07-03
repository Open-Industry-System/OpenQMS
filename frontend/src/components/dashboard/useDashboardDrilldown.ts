import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import type { MenuProps } from "antd";
import { useTranslation } from "react-i18next";
import { usePermission } from "../../hooks/usePermission";
import type { DashboardWidgetsData } from "./widgets/types";
import { getKpiDrilldown, getAlertRowDrilldown } from "./dashboardDrilldown";

type MenuItem = NonNullable<MenuProps["items"]>[number];

export interface KpiDrilldownProps {
  /** 链接型卡片的点击处理；菜单型/不可点时为 undefined */
  onClick?: () => void;
  /** 无目标模块权限时为 true（KPICard 灰显禁用） */
  disabled: boolean;
  /** 菜单型卡片的菜单项；链接型时为 undefined */
  menuItems?: MenuItem[];
  /** 菜单项点击：key 即目标 URL */
  onMenuClick?: (key: string) => void;
}

/**
 * 把纯映射 getKpiDrilldown 接到 navigate + 权限 + i18n。
 * 链接型 → 返回 onClick/disabled；菜单型 → 返回 menuItems/onMenuClick。
 */
export function useKpiDrilldown(type: string, data: DashboardWidgetsData): KpiDrilldownProps {
  const navigate = useNavigate();
  const { canView } = usePermission();
  const { t } = useTranslation("dashboard");

  const config = getKpiDrilldown(type, data, canView);
  if (!config) return { onClick: undefined, disabled: false };
  if (config.kind === "link") {
    return {
      onClick: config.disabled ? undefined : () => navigate(config.url),
      disabled: config.disabled,
    };
  }
  const menuItems: MenuItem[] = config.items.map((it) => ({
    key: it.url,
    label: `${t(it.labelKey)}${it.count !== undefined ? ` (${it.count})` : ""}`,
    disabled: it.disabled,
  }));
  return {
    onClick: undefined,
    disabled: false,
    menuItems,
    onMenuClick: (key: string) => navigate(key),
  };
}

export interface AlertDrilldownInfo {
  clickable: boolean;
  onClick?: () => void;
}

/** 预警行下钻：返回每行的 clickable + onClick。 */
export function useAlertDrilldown(type: string) {
  const navigate = useNavigate();
  const { canView } = usePermission();
  return useCallback(
    (item: { fmea_id?: string; report_id?: string; supplier_id?: string }): AlertDrilldownInfo => {
      const d = getAlertRowDrilldown(type, item, canView);
      if (!d) return { clickable: false };
      return { clickable: true, onClick: () => navigate(d.url) };
    },
    [type, navigate, canView],
  );
}
