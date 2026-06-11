export interface ValidationResult {
  occurrence_id: string;
  run_id: string;
  finding_id: string;
  cp_id: string;
  validation_type: string;
  rule_id: string;
  severity: "error" | "warning" | "info";
  category: string;
  title: string;
  description: string | null;
  affected_items: string[];
  fmea_node_ids: string[];
  suggestion: string | null;
  suggestion_data: Record<string, unknown> | null;
  status: "open" | "accepted" | "rejected" | "resolved";
  resolved_by: string | null;
  resolved_at: string | null;
  present: boolean;
  created_at: string;
}

export interface ValidationRun {
  run_id: string;
  cp_id: string;
  trigger: string;
  status: "running" | "completed" | "failed";
  rule_count: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  started_at: string;
  completed_at: string | null;
  failed_rules: unknown[];
  created_by: string | null;
}

export interface ValidationSummary {
  run_id: string | null;
  status: string | null;
  total: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  open_count: number;
  resolved_count: number;
  rejected_count: number;
}

export interface ValidationResultsList {
  items: ValidationResult[];
  total: number;
}
