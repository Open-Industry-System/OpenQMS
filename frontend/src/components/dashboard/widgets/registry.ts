import type { WidgetMeta, WidgetProps } from "./types";
import QualityTrendAIWidget from "./QualityTrendAIWidget";
import KpiPendingWidget from "./KpiPendingWidget";
import KpiOverdueWidget from "./KpiOverdueWidget";
import KpiRiskWidget from "./KpiRiskWidget";
import KpiTrendWidget from "./KpiTrendWidget";
import AlertHighRpnWidget from "./AlertHighRpnWidget";
import AlertOverdueCapaWidget from "./AlertOverdueCapaWidget";
import AlertHighPpmWidget from "./AlertHighPpmWidget";
import RecentActionsWidget from "./RecentActionsWidget";
import SpcAbnormalWidget from "./SpcAbnormalWidget";
import SpcCapabilityWidget from "./SpcCapabilityWidget";
import MsaGaugeExpiryWidget from "./MsaGaugeExpiryWidget";
import IqcPendingWidget from "./IqcPendingWidget";
import MesEquipmentWidget from "./MesEquipmentWidget";
import SupplierPpmWidget from "./SupplierPpmWidget";

export const widgetRegistry: Record<string, WidgetMeta & { component: React.FC<WidgetProps> }> = {
  kpi_pending_actions: {
    type: "kpi_pending_actions",
    nameKey: "widget.pendingActions",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiPendingWidget,
  },
  kpi_overdue_tasks: {
    type: "kpi_overdue_tasks",
    nameKey: "widget.overdueTasks",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiOverdueWidget,
  },
  kpi_high_risk_items: {
    type: "kpi_high_risk_items",
    nameKey: "widget.highRiskItems",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiRiskWidget,
  },
  kpi_month_trend: {
    type: "kpi_month_trend",
    nameKey: "widget.monthTrend",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiTrendWidget,
  },
  alert_high_rpn_fmea: {
    type: "alert_high_rpn_fmea",
    nameKey: "widget.highRpnFmeaTop5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "fmea",
    component: AlertHighRpnWidget,
  },
  alert_overdue_capa: {
    type: "alert_overdue_capa",
    nameKey: "widget.overdueCapaTop5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "capa",
    component: AlertOverdueCapaWidget,
  },
  alert_high_ppm_suppliers: {
    type: "alert_high_ppm_suppliers",
    nameKey: "widget.highPpmSuppliersTop5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "supplier",
    component: AlertHighPpmWidget,
  },
  recent_actions: {
    type: "recent_actions",
    nameKey: "widget.recentActions",
    category: "list",
    defaultSize: { w: 12, h: 3 },
    minSize: { w: 6, h: 2 },
    module: "dashboard",
    component: RecentActionsWidget,
  },
  spc_abnormal_count: {
    type: "spc_abnormal_count",
    nameKey: "widget.spcAbnormalCount",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "spc",
    component: SpcAbnormalWidget,
  },
  spc_capability_summary: {
    type: "spc_capability_summary",
    nameKey: "widget.capabilitySummary",
    category: "chart",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "spc",
    component: SpcCapabilityWidget,
  },
  msa_gauge_expiry: {
    type: "msa_gauge_expiry",
    nameKey: "widget.gaugeExpiry",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "msa",
    component: MsaGaugeExpiryWidget,
  },
  iqc_pending_inspections: {
    type: "iqc_pending_inspections",
    nameKey: "widget.iqcPendingInspections",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "iqc",
    component: IqcPendingWidget,
  },
  mes_equipment_status: {
    type: "mes_equipment_status",
    nameKey: "widget.equipmentStatus",
    category: "chart",
    defaultSize: { w: 4, h: 3 },
    minSize: { w: 3, h: 2 },
    module: "mes",
    component: MesEquipmentWidget,
  },
  supplier_ppm_trend: {
    type: "supplier_ppm_trend",
    nameKey: "widget.supplierPpmTrend",
    category: "chart",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "supplier",
    component: SupplierPpmWidget,
  },
  quality_trend_ai_summary: {
    type: "quality_trend_ai_summary",
    nameKey: "widget.qualityTrendAi",
    category: "ai",
    defaultSize: { w: 8, h: 5 },
    minSize: { w: 6, h: 4 },
    module: "dashboard",
    component: QualityTrendAIWidget,
  },
};

export function getWidgetMeta(type: string): WidgetMeta | undefined {
  return widgetRegistry[type];
}

export function getWidgetNameKey(type: string): string {
  return widgetRegistry[type]?.nameKey ?? "widget.unknown";
}

export function getWidgetComponent(type: string): React.FC<WidgetProps> | undefined {
  return widgetRegistry[type]?.component;
}

export function getAllWidgets(): (WidgetMeta & { component: React.FC<WidgetProps> })[] {
  return Object.values(widgetRegistry);
}
