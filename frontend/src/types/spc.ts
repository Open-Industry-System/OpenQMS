export interface InspectionCharacteristic {
  ic_id: string;
  ic_code: string;
  product_line: string;
  process_name: string;
  characteristic_name: string;
  spec_upper: number;
  spec_lower: number;
  target_value?: number;
  chart_type: "xbar_r" | "imr" | "histogram";
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
  chart_type: "xbar_r" | "imr" | "histogram";
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
}

export interface ChartDataResponse {
  chart_type: string;
  data_points: ChartDataPoint[];
  limits: ControlLimits;
  total_batches: number;
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
}

export interface SPCAlarmListResponse {
  items: SPCAlarm[];
  total: number;
  page: number;
  page_size: number;
}
