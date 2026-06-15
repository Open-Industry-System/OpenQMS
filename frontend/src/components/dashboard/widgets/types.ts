import type { ModuleKey } from "../../../hooks/usePermission";

export type WidgetCategory = "kpi" | "alert" | "chart" | "list" | "ai";

export interface WidgetMeta {
  type: string;
  nameKey: string;
  category: WidgetCategory;
  defaultSize: { w: number; h: number };
  minSize: { w: number; h: number };
  module: ModuleKey;
}

export interface WidgetLayoutItem {
  i: string;
  type: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardLayoutConfig {
  lg: WidgetLayoutItem[];
}

export interface QualityTrendMetadata {
  omitted_modules?: string[];
  available_modules?: string[];
  scope_description?: string;
  selected_product_line?: string | null;
}

export type QualityTrendRiskLevel = "low" | "medium" | "high" | "insufficient_data";

export interface QualityTrendSummary {
  risk_level?: QualityTrendRiskLevel;
  headline?: string;
  evidence?: Array<{ id?: string; label?: string; value?: number; trend?: string; severity?: string }>;
  actions?: Array<{ priority?: string; text?: string }>;
  data_window_days?: number;
  generated_at?: string;
  evidence_hash?: string;
  scope_hash?: string;
  ai_available?: boolean;
  metadata?: QualityTrendMetadata;
}

export interface QualityTrendInterpretation {
  summary: string;
  possible_causes: string[];
  impact_scope: string[];
  recommended_actions: Array<{ priority?: string; action?: string; reason?: string }>;
  evidence_refs: string[];
  confidence: "low" | "medium" | "high";
  model: string;
  evidence_hash: string;
  scope_hash: string;
  generated_at: string;
  cached: boolean;
}

export interface DashboardWidgetsData {
  kpi: {
    pending_actions?: number;
    overdue_tasks?: number;
    high_risk_items?: number;
    month_trend?: number;
  };
  alerts: {
    high_rpn_fmeas?: Array<{ fmea_id: string; document_no: string; node_name: string; rpn: number }>;
    overdue_capas?: Array<{ report_id: string; document_no: string; overdue_days: number }>;
    high_ppm_suppliers?: Array<{ supplier_id: string; supplier_name: string; ppm: number }>;
  };
  recent_actions: Array<{
    record_id: string;
    table_name: string;
    entity_no: string;
    action: string;
    operated_at: string;
  }>;
  spc: {
    abnormal_count?: number;
    capability_summary?: { count: number; cpk_avg: number | null };
  };
  msa: {
    gauges_expiring_30d?: number;
  };
  iqc: {
    pending_inspections?: number;
  };
  mes: {
    equipment_running?: number;
    equipment_down?: number;
    equipment_idle?: number;
  };
  supplier: {
    ppm_trend?: Array<{ supplier_id: string; supplier_name: string; ppm: number }>;
  };
  quality_trend?: { summary?: QualityTrendSummary };
  errors: Record<string, string>;
}

export interface WidgetProps {
  data: DashboardWidgetsData;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}
