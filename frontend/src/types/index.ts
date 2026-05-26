export interface AuditorInfo {
  is_auditor: boolean;
  qualifications: string[];
  last_qualification_date: string | null;
}

export interface User {
  user_id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role: string;
  is_active: boolean;
  auditor_info?: AuditorInfo;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  process_number?: string;
  classification?: string;
  requirement?: string;
  specification?: string;
  severity: number;
  severity_plant?: number;
  severity_customer?: number;
  severity_user?: number;
  occurrence: number;
  detection: number;
  responsible?: string;
  due_date?: string;
  status?: string;
  action_taken?: string;
  completion_date?: string;
  revised_severity?: number;
  revised_occurrence?: number;
  revised_detection?: number;
  ap?: string;
  revised_ap?: string;
  p_diagram?: {
    inputs: string[];
    outputs: string[];
    controls: string[];
    noise_factors: string[];
  };
  // DesignParameter fields (DFMEA-02)
  value?: number;
  tolerance_upper?: number;
  tolerance_lower?: number;
  unit?: string;
  // Interface fields (DFMEA-03)
  interface_type?: 'physical' | 'electrical' | 'software' | 'thermal' | 'communication';
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface FMEADocument {
  fmea_id: string;
  document_no: string;
  title: string;
  fmea_type: string;
  product_line_code: string;
  status: string;
  version: number;
  graph_data: GraphData;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  approved_by: string | null;
  approved_at: string | null;
}

export interface FMEAListResponse {
  items: FMEADocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface CAPAReport {
  report_id: string;
  document_no: string;
  title: string;
  product_line_code: string;
  status: string;
  severity: string;
  d1_team: { name: string; role: string }[];
  d2_description: string | null;
  d3_interim: string | null;
  d4_root_cause: string | null;
  d5_correction: string | null;
  d6_verification: string | null;
  d7_prevention: string | null;
  d8_closure: string | null;
  fmea_ref_id: string | null;
  due_date: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CAPAListResponse {
  items: CAPAReport[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardData {
  kpi: {
    total_fmea: number;
    approved_fmea: number;
    total_capa: number;
    open_capa: number;
    overdue_capa: number;
    avg_rpn: number;
    high_rpn_count: number;
    total_safety: number;
    pending_safety_approval: number;
    safety_suggestions: number;
    management_review: {
      total_reviews: number;
      closed_reviews: number;
      total_outputs: number;
      verified_outputs: number;
      pending_verification: number;
      completion_rate: number;
    };
  };
  trends: Record<string, unknown>;
  alerts: unknown[];
}

export interface ControlPlanItem {
  item_id: string;
  step_no: string;
  process_name: string;
  equipment: string;
  characteristic_no: string;
  product_characteristic: string;
  process_characteristic: string;
  special_class: string;
  specification_tolerance: string;
  evaluation_method: string;
  sample_size: string;
  sample_frequency: string;
  control_method: string;
  reaction_plan: string;
  source_fmea_node_id: string | null;
  sop_ref?: string;
  spc_chart_id?: string;
  gauge_id?: string;
  sort_order: number;
}

export interface ControlPlan {
  cp_id: string;
  document_no: string;
  title: string;
  fmea_ref_id: string | null;
  product_line_code: string;
  status: string;
  version: number;
  phase: string;
  part_no: string;
  part_name: string;
  contact_info: string;
  drawing_rev: string;
  org_factory: string;
  core_group: string;
  items: ControlPlanItem[];
  sync_pending: boolean;
  created_by: string | null;
  updated_by: string | null;
  approved_by: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
}

export interface ControlPlanListResponse {
  items: ControlPlan[];
  total: number;
  page: number;
  page_size: number;
}

export interface QualityGoal {
  goal_id: string;
  doc_no: string;
  parent_id: string | null;
  level: number;
  product_line_code: string | null;
  name: string;
  target_value: string;
  actual_value: string | null;
  unit: string;
  period: string;
  owner_id: string;
  status: "draft" | "pending" | "active" | "archived";
  approved_by: string | null;
  approved_at: string | null;
  reject_reason: string | null;
  description: string | null;
  data_source_formula?: string;
  created_at: string;
  updated_at: string;
}

export interface QualityGoalListResponse {
  items: QualityGoal[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditProgram {
  program_id: string;
  program_no: string;
  program_year: number;
  audit_type: "system" | "process" | "product";
  scope: string;
  criteria: string;
  status: "planned" | "active" | "completed";
  product_line_code?: string;
  created_by: string;
  created_at: string;
}

export interface AuditPlan {
  audit_id: string;
  plan_no: string;
  program_id: string;
  audit_scope: string;
  audit_criteria: string;
  planned_date: string;
  actual_date: string | null;
  lead_auditor: string | null;
  team_members: { user_id: string; username: string }[];
  checklist: AuditChecklistItem[];
  status: "planned" | "in_progress" | "completed" | "cancelled";
  product_line_code?: string;
  created_by: string;
  created_at: string;
}

export interface AuditFinding {
  finding_id: string;
  audit_id: string;
  clause_ref: string | null;
  finding_type: "major_nc" | "minor_nc" | "ofi" | "observation";
  description: string;
  root_cause: string | null;
  correction: string | null;
  corrective_action: string | null;
  capa_ref_id: string | null;
  status: "open" | "in_progress" | "verified" | "closed";
  due_date: string | null;
  closed_at: string | null;
  created_by: string | null;
  created_at: string;
}

export interface AuditChecklistItem {
  item_no: string;
  clause: string;
  question: string;
  result: "符合" | "不符合" | "不适用" | "";
  evidence: string;
  note: string;
}

export interface AuditProgramListResponse {
  items: AuditProgram[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditPlanListResponse {
  items: AuditPlan[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditFindingListResponse {
  items: AuditFinding[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditStats {
  program_count: number;
  planned_count: number;
  in_progress_count: number;
  completed_count: number;
  open_findings: number;
  major_nc_count: number;
}

export interface Supplier {
  supplier_id: string;
  supplier_no: string;
  name: string;
  short_name: string;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  address: string | null;
  product_scope: string | null;
  status: "pending_review" | "audit_required" | "approved" | "rejected" | "suspended";
  audit_plan_id: string | null;
  reject_reason: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SupplierCertification {
  cert_id: string;
  supplier_id: string;
  cert_type: string;
  cert_no: string;
  issued_by: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  file_url: string | null;
  created_at: string;
}

export interface SupplierEvaluation {
  eval_id: string;
  supplier_id: string;
  eval_period: string;
  eval_type: "quarterly" | "annual";
  quality_score: number;
  delivery_score: number;
  service_score: number;
  capa_count: number;
  finding_count: number;
  premium_freight_count: number;
  customer_disruption_count: number;
  capa_penalty: number;
  finding_penalty: number;
  premium_freight_penalty: number;
  customer_disruption_penalty: number;
  total_score: number;
  grade: "A" | "B" | "C" | "D";
  notes: string | null;
  evaluated_by: string;
  created_at: string;
}

export interface SupplierListResponse {
  items: Supplier[];
  total: number;
  page: number;
  page_size: number;
}

export interface SupplierStats {
  total_count: number;
  pending_review_count: number;
  approved_count: number;
  cert_expiry_30d_count: number;
}

export interface SupplierExpiryAlert {
  cert_id: string;
  supplier_id: string;
  supplier_name: string;
  supplier_short_name: string;
  cert_type: string;
  cert_no: string;
  expiry_date: string;
  days_remaining: number;
}

export interface ProductLine {
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export * from "./spc";
export * from "./msa";
export * from "./specialCharacteristic";

// --- Management Review ---
export interface ManagementReview {
  review_id: string;
  doc_no: string;
  title: string;
  review_date: string;
  actual_date: string | null;
  status: "draft" | "data_collected" | "in_review" | "closed";
  product_line_code: string | null;
  location: string | null;
  chair_person_id: string;
  participants: { user_id: string; name: string; role: string; department: string }[] | null;
  meeting_minutes: string | null;
  data_package: Record<string, unknown> | null;
  manual_inputs: Record<string, unknown> | null;
  attachments: { file_name: string; file_url: string; uploaded_at: string; uploaded_by: string }[] | null;
  created_by: string;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ManagementReviewListResponse {
  items: ManagementReview[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReviewOutput {
  output_id: string;
  review_id: string;
  category: "improvement_opportunity" | "system_change" | "resource_need";
  description: string;
  responsible_id: string | null;
  due_date: string | null;
  status: "pending" | "in_progress" | "completed" | "verified";
  completion_notes: string | null;
  verified_by: string | null;
  verified_at: string | null;
  verification_notes: string | null;
  created_at: string;
  updated_at: string;
}

// --- Version Management ---
export interface VersionBase {
  major_no: number;
  minor_no: number;
  change_type: "submit" | "approve" | "manual" | "rollback" | "fmea_sync";
  change_summary: string;
  created_by: string;
  created_at: string;
}

export interface FMEAVersion extends VersionBase {
  fmea_id: string;
  graph_data: GraphData;
}

export interface CPVersion extends VersionBase {
  cp_id: string;
  items: ControlPlanItem[];
}

export interface VersionListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface NodeChange {
  node_id: string;
  node_name: string;
  field: string;
  old_value: string;
  new_value: string;
}

export interface ModifiedNode {
  node_id: string;
  node_name: string;
  changes: NodeChange[];
  impact_chain: string[];
}

export interface FMEADiffResult {
  added_nodes: GraphNode[];
  deleted_nodes: GraphNode[];
  modified_nodes: ModifiedNode[];
}

export interface CPItemChange {
  item_id: string;
  step_no: string;
  field: string;
  old_value: string;
  new_value: string;
}

export interface CPItemDiff {
  item_id: string;
  step_no: string;
  diff_type: "added" | "deleted" | "modified";
  changes?: CPItemChange[];
}

export interface CPDiffResult {
  added_items: ControlPlanItem[];
  deleted_items: ControlPlanItem[];
  modified_items: CPItemDiff[];
}

export interface DiffSummary {
  added_count: number;
  deleted_count: number;
  modified_count: number;
}

export interface FMEACompareResponse {
  diff: FMEADiffResult;
  summary: DiffSummary;
}

export interface CPCompareResponse {
  diff: CPDiffResult;
  summary: DiffSummary;
}

export interface VerifyResponse {
  is_valid: boolean;
  warnings: string[];
}

export interface SyncPreviewItem {
  item_id: string;
  action: "add" | "sync" | "delete";
  step_no: string;
  current_value: Record<string, string | null> | null;
  fmea_new_value: Record<string, string | null>;
  merged_value: Record<string, string | null>;
}

export interface SyncPreviewResponse {
  fmea_version_id: string;
  fmea_version: string;
  items: SyncPreviewItem[];
  summary: {
    add_count: number;
    update_count: number;
    delete_count: number;
  };
}

export interface PPAPSubmission {
  submission_id: string;
  supplier_id: string;
  part_no: string;
  part_name: string;
  submission_level: number;
  submission_date: string | null;
  status: 'draft' | 'submitted' | 'approved' | 'rejected';
  approved_by: string | null;
  approved_at: string | null;
  notes: string | null;
  elements: PPAPElement[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PPAPElement {
  element_id: string;
  submission_id: string;
  element_no: number;
  element_name: string;
  status: 'pending' | 'submitted' | 'approved' | 'rejected';
  notes: string | null;
  sort_order: number;
}

export interface IqcInspection {
  inspection_id: string;
  inspection_no: string;
  supplier_id: string;
  part_no: string | null;
  part_name: string | null;
  lot_no: string | null;
  lot_qty: number | null;
  sample_qty: number | null;
  inspection_result: 'pending' | 'accepted' | 'rejected' | 'concession';
  defect_qty: number;
  defect_description: string | null;
  linked_capa_id: string | null;
  inspection_date: string | null;
  inspected_by: string | null;
}

export interface SupplierSCAR {
  scar_id: string;
  scar_no: string;
  supplier_id: string;
  source_type: 'iqc_reject' | 'audit_finding' | 'customer_complaint' | 'other';
  source_id: string | null;
  description: string;
  requested_action: string | null;
  supplier_response: string | null;
  status: 'open' | 'supplier_responded' | 'closed';
  issued_by: string | null;
  issued_date: string | null;
  due_date: string | null;
  closed_date: string | null;
}

export interface AuditChecklistTemplate {
  template_id: string;
  name: string;
  audit_type: 'system' | 'process' | 'product';
  items: AuditChecklistItem[];
  is_default: boolean;
  created_by: string | null;
  created_at: string;
}

// ─── IQC Types ───

export interface IqcMaterial {
  material_id: string;
  part_no: string;
  part_name: string;
  part_spec: string | null;
  material_type: string;
  default_aql: number | null;
  default_inspection_level: string | null;
  unit: string | null;
  product_line_code: string;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface IqcTemplateItem {
  item_id: string;
  template_id: string;
  sort_order: number;
  category: string;
  item_name: string;
  inspection_method: string | null;
  inspect_type: string;
  spec_upper: number | null;
  spec_lower: number | null;
  target_value: number | null;
  unit: string | null;
  sample_size: number | null;
  aql_level: number | null;
}

export interface IqcInspectionTemplate {
  template_id: string;
  template_name: string;
  material_id: string;
  version: number;
  is_active: boolean;
  items: IqcTemplateItem[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface IqcItemMeasurement {
  measurement_id: string;
  item_id: string;
  sequence_no: number;
  measured_value: number | null;
  attribute_result: string | null;
  remark: string | null;
}

export interface IqcInspectionItem {
  item_id: string;
  inspection_id: string;
  template_item_id: string | null;
  sort_order: number;
  category: string;
  item_name: string;
  inspect_type: string;
  spec_upper: number | null;
  spec_lower: number | null;
  target_value: number | null;
  sample_size: number | null;
  accept_no: number | null;
  reject_no: number | null;
  defect_qty: number;
  result: string;
  remark: string | null;
  measurements: IqcItemMeasurement[];
}

export interface IqcInspection {
  inspection_id: string;
  inspection_no: string;
  supplier_id: string;
  inspection_mode: string;
  material_id: string | null;
  template_id: string | null;
  part_no: string | null;
  part_name: string | null;
  lot_no: string | null;
  lot_qty: number | null;
  sample_qty: number | null;
  aql_level: string | null;
  inspection_level: string | null;
  sampling_standard: string | null;
  code_letter: string | null;
  accept_number: number | null;
  reject_number: number | null;
  inspection_result: string;
  defect_qty: number;
  defect_description: string | null;
  status: string;
  re_inspection: boolean;
  parent_inspection_id: string | null;
  product_line_code: string | null;
  linked_capa_id: string | null;
  linked_scar_id: string | null;
  judged_by: string | null;
  judged_at: string | null;
  inspection_date: string | null;
  inspected_by: string | null;
  items: IqcInspectionItem[];
  created_at: string;
  updated_at: string;
}

export interface AqlPlan {
  code_letter: string;
  sample_size: number;
  accept_number: number;
  reject_number: number;
  aql_level: number;
  inspection_level: string;
}

export interface IqcStats {
  total_inspections: number;
  accepted_count: number;
  rejected_count: number;
  concession_count: number;
  acceptance_rate: number;
  rejection_rate: number;
}

// ─── Customer Quality Types ───

export interface CustomerAttachment {
  file_name: string;
  file_url: string;
  uploaded_at: string;
  uploaded_by: string;
  category: string;
}

export interface Customer {
  customer_id: string;
  customer_code: string;
  name: string;
  segment: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  csr_list: Record<string, unknown>[] | null;
  ppm_target: number | null;
  annual_shipment_qty: number | null;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerListResponse {
  items: Customer[];
  total: number;
  page: number;
  page_size: number;
}

export interface CustomerSummary {
  customer_id: string;
  customer_code: string;
  name: string;
  segment: string | null;
  complaint_count: number;
  open_complaint_count: number;
  overdue_count: number;
  open_fatal_count: number;
  rma_count: number;
  independent_rma_qty: number;
  impact_qty: number;
  ppm: number | null;
  ppm_target: number | null;
  risk_light: "red" | "yellow" | "green";
}

export interface CustomerComplaint {
  complaint_id: string;
  complaint_no: string;
  product_line_code: string;
  customer_id: string;
  product_id: string | null;
  batch_no: string | null;
  serial_number: string | null;
  category: "safety" | "function" | "appearance" | "delivery";
  severity: "致命" | "严重" | "一般" | "轻微";
  defect_desc: string;
  impact_qty: number;
  occurred_date: string | null;
  received_date: string;
  due_date: string | null;
  status: "open" | "investigating" | "responded" | "closed" | "cancelled";
  fmea_ref_id: string | null;
  capa_ref_id: string | null;
  has_rma: boolean;
  preliminary_response: string | null;
  root_cause: string | null;
  corrective_action: string | null;
  attachments: CustomerAttachment[] | null;
  assignee_id: string | null;
  supplier_responsibility: boolean;
  scar_ref_id: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface ComplaintListResponse {
  items: CustomerComplaint[];
  total: number;
  page: number;
  page_size: number;
}

export interface RMARecord {
  rma_id: string;
  rma_no: string;
  product_line_code: string;
  customer_id: string;
  complaint_id: string | null;
  product_id: string | null;
  batch_no: string | null;
  serial_number: string | null;
  return_qty: number;
  defect_type: string;
  responsibility: "supplier" | "internal" | "transport" | "customer_misuse" | "unknown" | null;
  analysis_result: string | null;
  corrective_action: string | null;
  status: "open" | "analysis" | "action_pending" | "closed" | "cancelled";
  fmea_ref_id: string | null;
  capa_ref_id: string | null;
  scar_ref_id: string | null;
  attachments: CustomerAttachment[] | null;
  assignee_id: string | null;
  tracking_number: string | null;
  received_date: string | null;
  closed_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface RMARecordListResponse {
  items: RMARecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface CustomerQualityDashboard {
  kpi: {
    complaint_count: number;
    open_complaint_count: number;
    overdue_count: number;
    rma_count: number;
    return_qty: number;
    independent_rma_qty: number;
    impact_qty: number;
  };
  customers: CustomerSummary[];
  trend: { period: string; complaints: number; rma: number; rma_qty: number }[];
  complaints_by_status: Record<string, number>;
  complaints_by_severity: Record<string, number>;
  rma_by_status: Record<string, number>;
  rma_by_responsibility: Record<string, number>;
}
