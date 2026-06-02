export interface InspectionCharacteristic {
  ic_id: string;
  ic_code: string;
  product_line: string;
  process_name: string;
  characteristic_name: string;
  spec_upper: number;
  spec_lower: number;
  target_value?: number;
  chart_type: "xbar_r" | "imr" | "histogram" | "p" | "np" | "c" | "u";
  subgroup_size: number;
  control_limits_locked: boolean;
  rules_config: Record<string, boolean>;
  created_by_id: string;
  created_at: string;
  updated_at: string;
}

export interface InspectionCharacteristicListResponse {
  items: InspectionCharacteristic[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateICRequest {
  product_line?: string;
  process_name: string;
  characteristic_name: string;
  spec_upper: number;
  spec_lower: number;
  target_value?: number;
  chart_type: "xbar_r" | "imr" | "histogram" | "p" | "np" | "c" | "u";
  subgroup_size?: number;
  rules_config?: Record<string, boolean>;
}

export interface SampleBatch {
  batch_id: string;
  ic_id: string;
  batch_no: string;
  sampled_at: string;
  subgroup_size: number;
  values: number[];
  inspected_count?: number;
  defect_count?: number;
}

export interface ChartDataPoint {
  batch_index: number;
  batch_no: string;
  sampled_at: string;
  x_value?: number;
  r_value?: number;
  alarm_flags: number[];
}

export interface ControlLimits {
  ucl?: number;
  lcl?: number;
  cl?: number;
  r_ucl?: number;
  r_lcl?: number;
  r_cl?: number;
  ucl_list?: number[];
  lcl_list?: number[];
}

export interface ControlLimitSnapshot {
  snapshot_id: string;
  ic_id: string;
  ucl: number;
  lcl: number;
  cl: number;
  r_ucl?: number;
  r_lcl?: number;
  r_cl?: number;
  version_no: number;
  is_active: boolean;
  is_locked: boolean;
  calculated_at: string;
  created_at: string;
}

export interface ChartDataResponse {
  chart_type: string;
  data_points: ChartDataPoint[];
  limits: ControlLimits;
  total_batches: number;
  active_snapshot?: ControlLimitSnapshot;
}

export interface CapabilityResponse {
  cp: number;
  cpk: number;
  cpu: number;
  cpl: number;
  pp: number;
  ppk: number;
  ppu: number;
  ppl: number;
  cm: number;
  cmk: number;
  theoretical_ppm: number;
  actual_ppm: number;
  grade: string;
  advice: string;
}

export interface SPCAlarm {
  alarm_id: string;
  ic_id: string;
  batch_id?: string;
  rule_no: number;
  triggered_at: string;
  severity: "critical" | "major" | "minor";
  status: "open" | "acknowledged" | "closed";
  linked_capa_id?: string;
  acknowledged_by_id?: string;
  acknowledged_at?: string;
  confirmed_fmea_id?: string;
  confirmed_fmea_node_id?: string;
}

export interface SPCAlarmListResponse {
  items: SPCAlarm[];
  total: number;
  page: number;
  page_size: number;
}

export interface FMEAMatch {
  node_id: string;
  name: string;
  node_type: string;
  fmea_id: string;
  document_no: string;
  match_source: "control_plan" | "process_name" | "characteristic_name";
  match_score: number;
  rpn: number;
  ap: string;
  severity: number;
  occurrence: number;
  detection: number;
  path: string;
  cause_preview: string[];
  control_count: number;
}

export interface FMEAMatchResponse {
  alarm_id: string;
  ic_code: string;
  process_name: string;
  characteristic_name: string;
  recommendations: FMEAMatch[];
  has_confirmed: boolean;
  confirmed_fmea_id: string | null;
  confirmed_fmea_node_id: string | null;
}

export interface ConfirmFMEARequest {
  fmea_id: string;
  node_id: string;
}
