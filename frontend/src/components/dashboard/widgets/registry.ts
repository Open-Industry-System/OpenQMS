import type { WidgetMeta, WidgetProps } from "./types";
import KpiPendingWidget from "./KpiPendingWidget";
import KpiOverdueWidget from "./KpiOverdueWidget";
import KpiRiskWidget from "./KpiRiskWidget";
import KpiTrendWidget from "./KpiTrendWidget";
import AlertHighRpnWidget from "./AlertHighRpnWidget";
import AlertOverdueCapaWidget from "./AlertOverdueCapaWidget";
import AlertHighPpmWidget from "./AlertHighPpmWidget";
import RecentActionsWidget from "./RecentActionsWidget";

const placeholderComponent: React.FC<WidgetProps> = () => null;

export const widgetRegistry: Record<string, WidgetMeta & { component: React.FC<WidgetProps> }> = {
  kpi_pending_actions: {
    type: "kpi_pending_actions",
    name: "待办事项",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiPendingWidget,
  },
  kpi_overdue_tasks: {
    type: "kpi_overdue_tasks",
    name: "超期任务",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiOverdueWidget,
  },
  kpi_high_risk_items: {
    type: "kpi_high_risk_items",
    name: "高风险项",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiRiskWidget,
  },
  kpi_month_trend: {
    type: "kpi_month_trend",
    name: "本月新增 FMEA",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: KpiTrendWidget,
  },
  alert_high_rpn_fmea: {
    type: "alert_high_rpn_fmea",
    name: "高 RPN FMEA Top5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "fmea",
    component: AlertHighRpnWidget,
  },
  alert_overdue_capa: {
    type: "alert_overdue_capa",
    name: "超期 CAPA Top5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "capa",
    component: AlertOverdueCapaWidget,
  },
  alert_high_ppm_suppliers: {
    type: "alert_high_ppm_suppliers",
    name: "PPM 超标供应商 Top5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "supplier",
    component: AlertHighPpmWidget,
  },
  recent_actions: {
    type: "recent_actions",
    name: "最近操作",
    category: "list",
    defaultSize: { w: 12, h: 3 },
    minSize: { w: 6, h: 2 },
    module: "dashboard",
    component: RecentActionsWidget,
  },
  spc_abnormal_count: {
    type: "spc_abnormal_count",
    name: "SPC 异常点数",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "spc",
    component: placeholderComponent,
  },
  spc_capability_summary: {
    type: "spc_capability_summary",
    name: "过程能力摘要",
    category: "chart",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "spc",
    component: placeholderComponent,
  },
  msa_gauge_expiry: {
    type: "msa_gauge_expiry",
    name: "量具到期提醒",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "msa",
    component: placeholderComponent,
  },
  iqc_pending_inspections: {
    type: "iqc_pending_inspections",
    name: "IQC 待检批次",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "iqc",
    component: placeholderComponent,
  },
  mes_equipment_status: {
    type: "mes_equipment_status",
    name: "设备状态概览",
    category: "chart",
    defaultSize: { w: 4, h: 3 },
    minSize: { w: 3, h: 2 },
    module: "mes",
    component: placeholderComponent,
  },
  supplier_ppm_trend: {
    type: "supplier_ppm_trend",
    name: "供应商 PPM 趋势",
    category: "chart",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "supplier",
    component: placeholderComponent,
  },
};

export function getWidgetMeta(type: string): WidgetMeta | undefined {
  return widgetRegistry[type];
}

export function getWidgetComponent(type: string): React.FC<WidgetProps> | undefined {
  return widgetRegistry[type]?.component;
}

export function getAllWidgets(): (WidgetMeta & { component: React.FC<WidgetProps> })[] {
  return Object.values(widgetRegistry);
}
