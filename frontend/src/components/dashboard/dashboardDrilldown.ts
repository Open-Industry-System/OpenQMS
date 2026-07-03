import type { DashboardWidgetsData } from "./widgets/types";
import type { ModuleKey } from "../../hooks/usePermission";

type CanView = (module: ModuleKey) => boolean;

/** KPI 数字卡下钻：单链接型 */
export interface KpiLinkDrilldown {
  kind: "link";
  url: string;
  /** 无目标模块查看权限时为 true（卡片灰显禁用） */
  disabled: boolean;
}

/** KPI 数字卡下钻：下拉菜单型（待办事项按分类展开） */
export interface KpiMenuDrilldownItem {
  /** dashboard 命名空间下的 i18n key */
  labelKey: string;
  url: string;
  count?: number;
  disabled: boolean;
}

export interface KpiMenuDrilldown {
  kind: "menu";
  items: KpiMenuDrilldownItem[];
}

export type KpiDrilldown = KpiLinkDrilldown | KpiMenuDrilldown | null;

/** 预警行下钻：跳详情页 */
export interface AlertRowDrilldown {
  url: string;
}

/**
 * 仪表盘 KPI 卡 → 下钻目标。
 * - 单链接卡：返回 {kind:'link', url, disabled}，无权限时 disabled=true。
 * - 待办事项卡：返回 {kind:'menu', items}，每项独立判权限。
 * - 月度趋势卡 / 未知类型：返回 null（不可点）。
 */
export function getKpiDrilldown(
  type: string,
  data: DashboardWidgetsData,
  canView: CanView,
): KpiDrilldown {
  switch (type) {
    case "kpi_overdue_tasks":
      return { kind: "link", url: "/capa?overdue=true", disabled: !canView("capa") };
    case "kpi_high_risk_items":
      return { kind: "link", url: "/fmea?high_rpn=true", disabled: !canView("fmea") };
    case "spc_abnormal_count":
      return { kind: "link", url: "/spc?abnormal=true", disabled: !canView("spc") };
    case "msa_gauge_expiry":
      return { kind: "link", url: "/msa/gauges?expiring=30d", disabled: !canView("msa") };
    case "iqc_pending_inspections":
      return { kind: "link", url: "/iqc/inspections?status=pending", disabled: !canView("iqc") };
    case "mes_equipment_status":
      return { kind: "link", url: "/mes/dashboard", disabled: !canView("mes") };
    case "kpi_pending_actions": {
      const b = data.kpi?.pending_breakdown ?? {};
      return {
        kind: "menu",
        items: [
          { labelKey: "drilldown.pendingFmea", url: "/fmea?pending=true", count: b.fmea ?? 0, disabled: !canView("fmea") },
          { labelKey: "drilldown.pendingCapa", url: "/capa?pending_action=true", count: b.capa ?? 0, disabled: !canView("capa") },
          { labelKey: "drilldown.pendingComplaint", url: "/customer-quality?status=open", count: b.complaint ?? 0, disabled: !canView("customer_quality") },
        ],
      };
    }
    default:
      return null;
  }
}

/**
 * 预警列表行 → 详情页 URL。
 * 无该模块查看权限或缺实体 ID 时返回 null（行灰显不响应）。
 */
export function getAlertRowDrilldown(
  type: string,
  item: { fmea_id?: string; report_id?: string; supplier_id?: string },
  canView: CanView,
): AlertRowDrilldown | null {
  switch (type) {
    case "alert_high_rpn_fmea":
      if (!canView("fmea") || !item.fmea_id) return null;
      return { url: `/fmea/${item.fmea_id}` };
    case "alert_overdue_capa":
      if (!canView("capa") || !item.report_id) return null;
      return { url: `/capa/${item.report_id}` };
    case "alert_high_ppm_suppliers":
      if (!canView("supplier") || !item.supplier_id) return null;
      return { url: `/suppliers/quality/${item.supplier_id}` };
    default:
      return null;
  }
}
