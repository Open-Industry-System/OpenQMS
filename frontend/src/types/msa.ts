export interface Gauge {
  gauge_id: string;
  gauge_no: string;
  name: string;
  model: string | null;
  manufacturer: string | null;
  resolution: number | null;
  measuring_range: string | null;
  department: string | null;
  location: string | null;
  status: string;
  calibration_cycle_days: number | null;
  next_calibration_date: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface GaugeListResponse {
  items: Gauge[];
  total: number;
  page: number;
  page_size: number;
}

export interface GaugeCalibration {
  calibration_id: string;
  gauge_id: string;
  calibration_date: string;
  result: string;
  certificate_no: string | null;
  calibrated_by: string | null;
  notes: string | null;
  next_calibration_date: string | null;
  created_at: string;
}

export interface GaugeCalibrationListResponse {
  items: GaugeCalibration[];
}

export interface GrrStudy {
  study_id: string;
  study_no: string;
  title: string;
  method: string;
  gauge_id: string | null;
  characteristic_name: string;
  spc_characteristic_id: string | null;
  unit: string | null;
  tolerance_upper: number | null;
  tolerance_lower: number | null;
  reference_value: number | null;
  appraiser_count: number;
  part_count: number;
  trial_count: number;
  status: string;
  study_date: string | null;
  accepted_by: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface GrrStudyListResponse {
  items: GrrStudy[];
  total: number;
  page: number;
  page_size: number;
}

export interface GrrMeasurement {
  measurement_id: string;
  study_id: string;
  appraiser_name: string;
  part_no: string;
  trial_no: number;
  value: number;
}

export interface GrrResult {
  result_id: string;
  study_id: string;
  ev: number;
  av: number;
  grr: number;
  pv: number;
  tv: number;
  ndc: number;
  grr_percent_tol: number;
  grr_percent_tv: number;
  ev_percent: number;
  av_percent: number;
  pv_percent: number;
  conclusion: string;
  created_at: string;
}

export interface BiasStudy {
  study_id: string;
  study_no: string;
  title: string;
  gauge_id: string | null;
  characteristic_name: string;
  spc_characteristic_id: string | null;
  unit: string | null;
  reference_value: number;
  sample_size: number;
  status: string;
  study_date: string | null;
  accepted_by: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BiasStudyListResponse {
  items: BiasStudy[];
  total: number;
  page: number;
  page_size: number;
}

export interface BiasMeasurement {
  measurement_id: string;
  study_id: string;
  value: number;
  sequence_no: number;
}

export interface BiasResult {
  result_id: string;
  study_id: string;
  mean: number;
  bias: number;
  bias_percent: number | null;
  std_dev: number;
  t_statistic: number;
  p_value: number;
  lower_ci: number | null;
  upper_ci: number | null;
  conclusion: string;
  created_at: string;
}

export interface LinearityStudy {
  study_id: string;
  study_no: string;
  title: string;
  gauge_id: string | null;
  characteristic_name: string;
  spc_characteristic_id: string | null;
  unit: string | null;
  tolerance_upper: number | null;
  tolerance_lower: number | null;
  sample_size_per_reference: number;
  status: string;
  study_date: string | null;
  accepted_by: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface LinearityStudyListResponse {
  items: LinearityStudy[];
  total: number;
  page: number;
  page_size: number;
}

export interface LinearityMeasurement {
  measurement_id: string;
  study_id: string;
  reference_value: number;
  measured_value: number;
  sequence_no: number;
}

export interface LinearityResult {
  result_id: string;
  study_id: string;
  slope: number;
  intercept: number;
  r_squared: number;
  linearity: number;
  linearity_percent: number | null;
  bias_at_lower: number | null;
  bias_at_upper: number | null;
  conclusion: string;
  created_at: string;
}

export interface StabilityStudy {
  study_id: string;
  study_no: string;
  title: string;
  gauge_id: string | null;
  characteristic_name: string;
  spc_characteristic_id: string | null;
  unit: string | null;
  reference_value: number | null;
  subgroup_size: number;
  status: string;
  study_date: string | null;
  accepted_by: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface StabilityStudyListResponse {
  items: StabilityStudy[];
  total: number;
  page: number;
  page_size: number;
}

export interface StabilityMeasurement {
  measurement_id: string;
  study_id: string;
  measurement_date: string;
  sample_mean: number;
  sample_range: number;
  sequence_no: number;
}

export interface StabilityResult {
  result_id: string;
  study_id: string;
  ucl_mean: number;
  lcl_mean: number | null;
  cl_mean: number;
  ucl_range: number;
  lcl_range: number | null;
  cl_range: number;
  cpk: number | null;
  conclusion: string;
  created_at: string;
}

export interface AttributeStudy {
  study_id: string;
  study_no: string;
  title: string;
  gauge_id: string | null;
  characteristic_name: string;
  spc_characteristic_id: string | null;
  method: string;
  sample_size: number;
  known_standard_count: number | null;
  status: string;
  study_date: string | null;
  accepted_by: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AttributeStudyListResponse {
  items: AttributeStudy[];
  total: number;
  page: number;
  page_size: number;
}

export interface AttributeMeasurement {
  measurement_id: string;
  study_id: string;
  appraiser_name: string;
  part_no: string;
  known_standard: string;
  appraiser_decision: string;
  trial_no: number;
}

export interface AttributeResult {
  result_id: string;
  study_id: string;
  effectiveness: number;
  miss_rate: number;
  false_alarm_rate: number;
  kappa_within: number | null;
  kappa_vs_standard: number | null;
  kappa_between: number | null;
  conclusion: string;
  created_at: string;
}

export interface MsaStudyOverview {
  study_id: string;
  study_no: string;
  type: string;
  title: string;
  gauge_name: string | null;
  status: string;
  study_date: string | null;
  created_at: string;
}

export interface MsaStudyOverviewListResponse {
  items: MsaStudyOverview[];
  total: number;
  page: number;
  page_size: number;
}

export interface MsaSpcCharacteristic {
  ic_id: string;
  ic_code: string;
  process_name: string;
  characteristic_name: string;
  unit: string | null;
  spec_upper: number | null;
  spec_lower: number | null;
}
