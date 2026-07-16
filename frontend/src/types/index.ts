export interface AuditorInfo {
  is_auditor: boolean;
  qualifications: string[];
  last_qualification_date: string | null;
}

export interface Factory {
  id: string;
  code: string;
  name: string;
  location?: string;
  is_active: boolean;
}

export interface AssignableRoleOption {
  role_key: string;
  name_zh: string;
  name_en: string;
}

export interface FactoryScope {
  accessible_factory_ids: string[] | null;  // null = all factories
  default_factory_id: string | null;
}

export interface User {
  user_id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role_key: string;
  legacy_role?: string | null;
  permissions: Record<string, number>;
  product_lines: { product_line_code: string; name?: string }[];
  bypass_row_level_security: boolean;
  is_active: boolean;
  auditor_info?: AuditorInfo;
  factory_scope?: FactoryScope | null;
  factories?: Factory[];
  tenant_id?: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
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

export interface WizardScope {
  team?: string;
  timeframe?: string;
  tool?: string;
  task?: string;
  trend?: string;
  wizard_completed?: boolean;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  wizardScope?: WizardScope;
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
  lock_version: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  approved_by: string | null;
  approved_at: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type FMEAListResponse = PaginatedResponse<FMEADocument>;

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
  fmea_node_id: string | null;
  due_date: string | null;
  d4_retry_count: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  scar_ref_id?: string | null;
  linked_scar?: {
    scar_id: string;
    scar_no: string;
    status: string;
    supplier_id: string;
  } | null;
  d3_affected_lots?: string[];
}

export type CAPAListResponse = PaginatedResponse<CAPAReport>;

export interface RelatedCAPAItem {
  report_id: string;
  document_no: string;
  title: string;
  status: string;
  product_line_code?: string;
  link_sources?: string[];
}

/** Knowledge sink embedding lifecycle (US-E2E-01.8). */
export type KnowledgeEmbeddingStatus = "pending" | "ready" | "failed";

export interface KnowledgeEntrySummary {
  entry_id: string;
  source_type: string;
  source_id: string;
  document_no: string;
  title: string;
  severity: string | null;
  product_line_code: string;
  factory_id: string;
  status: string;
  embedding_status: KnowledgeEmbeddingStatus | string;
  embedding_id: string | null;
  lesson_summary: string | null;
  tags: string[];
  created_at: string;
}

export interface KnowledgeEntryDetail extends KnowledgeEntrySummary {
  fields: Record<string, unknown>;
  content_hash?: string | null;
  llm_status?: string | null;
  updated_at?: string | null;
}

export type KnowledgeEntryListResponse = PaginatedResponse<KnowledgeEntrySummary>;

export interface SinkKnowledgeResponse {
  entry_id: string;
  source_type: string;
  source_id: string;
  document_no: string;
  title: string;
  embedding_status: KnowledgeEmbeddingStatus | string;
  content_hash?: string | null;
  llm_status?: string | null;
}

export interface KnowledgeSinkOutcomeDetail {
  outcome: "blocked" | "failed";
  reason?: string;
  message?: string;
}


export interface ReviewSkill {
  skill_id: string;
  tenant_schema: string | null;
  name: string;
  content: string;
  version: number;
  is_active: boolean;
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

export interface DashboardSummary {
  pending_actions: number;
  overdue_tasks: number;
  high_risk_items: number;
  month_trend: number;
}

export interface DashboardAlerts {
  high_rpn_fmeas: Array<{
    fmea_id: string;
    document_no: string;
    node_name: string;
    rpn: number;
  }>;
  overdue_capas: Array<{
    report_id: string;
    document_no: string;
    overdue_days: number;
  }>;
  high_ppm_suppliers: Array<{
    supplier_id: string;
    supplier_name: string;
    ppm: number;
  }>;
}

export interface DashboardRecentAction {
  record_id: string;
  table_name: string;
  entity_no: string;
  action: string;
  operated_at: string;
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
  lock_version: number;
  created_by: string | null;
  updated_by: string | null;
  approved_by: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  customer_requirements?: { title: string; description: string; source_customer_id: string | null; synced_at: string | null; source: string }[];
}

export type ControlPlanListResponse = PaginatedResponse<ControlPlan>;

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
  audit_type: "system" | "process" | "product" | "customer";
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
  audit_category: string;
  customer_name?: string;
  customer_type?: string;
  audit_mode?: string;
  customer_confirmation_doc?: CustomerAuditAttachment[];
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
  status: "open" | "in_progress" | "closed";
  due_date: string | null;
  closed_at: string | null;
  customer_confirmed: boolean;
  customer_confirmation_date: string | null;
  customer_confirmation_attachments: CustomerAuditAttachment[];
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

export type SupplierListResponse = PaginatedResponse<Supplier>;

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

export interface ProductType {
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductLine {
  code: string;
  name: string;
  is_active: boolean;
  product_type_code: string | null;
  created_at: string;
  updated_at: string;
}

export * from "./spc";
export * from "./msa";
export * from "./specialCharacteristic";
export * from "./plm";
export * from "./erp";

// --- Management Review ---
export interface ManagementReview {
  review_id: string;
  doc_no: string;
  title: string;
  review_date: string;
  actual_date: string | null;
  status: "draft" | "data_collected" | "in_review" | "closed";
  report_status: "none" | "draft" | "final";
  generated_report: ManagementReviewReport | null;
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

export interface ManagementReviewReportSection {
  key: string;
  title: string;
  source: "data_package" | "manual_input";
  base_text: string;
  ai_analysis: string;
  findings: string[];
  recommendations: string[];
  manual_text: string;
  data_snapshot: Record<string, unknown> | string | unknown[] | number | boolean | null;
}

export interface ManagementReviewReport {
  generated_at: string;
  generation_model: string;
  llm_enriched: boolean;
  sections: ManagementReviewReportSection[];
  executive_summary: string;
  overall_recommendations: string[];
  updated_at?: string | null;
}

export interface ReviewReportVersion {
  report_id: string;
  review_id: string;
  version_no: number;
  content: ManagementReviewReport;
  created_by: string;
  finalized_by: string | null;
  finalized_at: string | null;
  created_at: string;
  updated_at: string;
}

// --- Version Management ---
export interface VersionBase {
  version_id: string;
  major_no: number;
  minor_no: number;
  change_type: string | null;
  change_summary: string | null;
  created_by: string | null;
  created_at: string;
}

export interface FMEAVersion extends VersionBase {
  fmea_id: string;
}

export interface FMEAVersionDetail extends FMEAVersion {
  snapshot: GraphData;
  sha256_hash: string;
}

export interface CPVersion extends VersionBase {
  cp_id: string;
  source_fmea_version_id: string | null;
}

export interface CPVersionHeader {
  document_no: string | null;
  title: string | null;
  fmea_ref_id: string | null;
  product_line_code: string | null;
  status: string | null;
  phase: string | null;
  part_no: string | null;
  part_name: string | null;
  contact_info: string | null;
  drawing_rev: string | null;
  org_factory: string | null;
  core_group: string | null;
}

export interface CPVersionDetail extends CPVersion {
  header_snapshot: CPVersionHeader;
  items_snapshot: ControlPlanItem[];
  sha256_hash: string;
}

export interface RollbackResponse {
  version_id: string;
  major_no: number;
  minor_no: number;
  change_type: string | null;
  change_summary: string | null;
  created_at: string;
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
  ppap_no: string;
  supplier_id: string;
  supplier_name: string | null;
  supplier_no: string | null;
  part_no: string;
  part_name: string;
  submission_level: number;
  submission_date: string | null;
  customer_name: string | null;
  product_line_code: string | null;
  status: 'draft' | 'under_review' | 'approved' | 'rejected';
  revision: number;
  rejection_reason: string | null;
  approved_by: string | null;
  approved_at: string | null;
  notes: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  elements: PPAPElement[];
}

export interface PPAPElement {
  element_id: string;
  submission_id: string;
  element_no: number;
  element_name: string;
  required: boolean;
  status: 'pending' | 'in_review' | 'approved' | 'not_applicable';
  reviewed_by: string | null;
  reviewed_at: string | null;
  file_url: string | null;
  notes: string | null;
  sort_order: number;
}

export interface PPAPListResponse {
  items: PPAPSubmission[];
  total: number;
  page: number;
  page_size: number;
}

export interface PPAPCreate {
  supplier_id: string;
  part_no: string;
  part_name: string;
  submission_level: number;
  submission_date?: string;
  customer_name?: string;
  product_line_code?: string;
  notes?: string;
}

export interface PPAPElementUpdate {
  status?: 'pending' | 'in_review' | 'approved' | 'not_applicable';
  notes?: string | null;
  file_url?: string | null;
}

export interface PPAPTransitionRequest {
  action: 'submit' | 'approve' | 'reject' | 'resubmit';
  rejection_reason?: string;
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
  supplier_name?: string;
  supplier_no?: string;
  source_type: 'iqc' | 'complaint' | 'rma' | 'manual' | 'capa';
  source_id?: string;
  description: string;
  product_line_code?: string;
  requested_action?: string;
  supplier_response?: string;
  status: 'open' | 'in_progress' | 'responded' | 'verified' | 'closed';
  capa_ref_id?: string;
  resolution_summary?: string;
  issued_by?: string;
  issued_date?: string;
  due_date?: string;
  closed_date?: string;
  created_at: string;
  updated_at: string;
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
  inspection_result: 'pending' | 'accepted' | 'rejected' | 'concession';
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
  supplier_id: string | null;
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
  // Enhanced fields
  spc_cpks: { product_line_code: string; cpk: number | null; ppk: number | null; last_updated: string | null }[];
  warranty_total: number;
  avg_satisfaction: number | null;
  audit_summary: { completed_count: number; finding_count: number; last_audit_date: string | null } | null;
}

// ─── Supplier Quality Dashboard ───

export interface QualityKPI {
  total_suppliers: number;
  overall_ppm: number;
  batch_acceptance_rate: number;
  open_scar_count: number;
}

export interface PPMTrendPoint {
  month: string;
  ppm: number;
}

export interface GradeDistribution {
  A: number;
  B: number;
  C: number;
  D: number;
}

export interface SupplierRankingItem {
  supplier_id: string;
  supplier_no: string;
  name: string;
  grade: string;
  ppm: number;
  batch_acceptance_rate: number;
  delivery_rate: number;
  open_scar_count: number;
}

export interface QualityDashboardResponse {
  kpi: QualityKPI;
  ppm_trend: PPMTrendPoint[];
  grade_distribution: GradeDistribution;
  ranking: SupplierRankingItem[];
}

export interface SupplierQualityStats {
  grade: string;
  total_score: number;
  quality_score: number;
  delivery_score: number;
  service_score: number;
  ppm: number;
  batch_acceptance_rate: number;
  total_inspections: number;
  accepted_count: number;
  scar_count: number;
  open_scar_count: number;
}

export interface SupplierQualityDetailResponse {
  supplier: Supplier;
  stats: SupplierQualityStats;
  ppm_trend: PPMTrendPoint[];
  acceptance_trend: { month: string; rate: number }[];
}

export interface SupplierCompareItem {
  supplier_id: string;
  name: string;
  supplier_no: string;
  grade: string;
  ppm: number;
  batch_acceptance_rate: number;
  delivery_rate: number;
  open_scar_count: number;
  quality_score: number;
  delivery_score: number;
  service_score: number;
}

export interface SupplierCompareResponse {
  suppliers: SupplierCompareItem[];
  ppm_trends: Record<string, PPMTrendPoint[]>;
}

export type SCARListResponse = PaginatedResponse<SupplierSCAR>;

export interface SCARCreate {
  supplier_id: string;
  source_type: 'iqc' | 'complaint' | 'rma' | 'manual';
  source_id?: string;
  description: string;
  product_line_code?: string;
  requested_action?: string;
  due_date?: string;
}

export interface SCARUpdate {
  description?: string;
  requested_action?: string;
  due_date?: string;
}

export interface SCARTransitionRequest {
  action: 'start' | 'respond' | 'verify' | 'reject' | 'close' | 'reopen';
  supplier_response?: string;
  resolution_summary?: string;
}

export interface SCARLinkCAPARequest {
  capa_ref_id: string;
}

// ─── APQP 项目质量策划 ───

export interface APQPProject {
  project_id: string;
  project_code: string;
  project_name: string;
  product_name: string;
  product_line_code: string;
  customer_name: string | null;
  description: string | null;
  target_sop_date: string | null;
  team_members: { name: string; role: string; department: string }[] | null;
  current_phase: number;
  phase_name: string;
  phase_status: string | null;
  project_status: string;
  phase_1_completed_at: string | null;
  phase_2_completed_at: string | null;
  phase_3_completed_at: string | null;
  phase_4_completed_at: string | null;
  phase_5_completed_at: string | null;
  gate_approved_by: string | null;
  gate_approved_by_name: string | null;
  gate_approved_at: string | null;
  gate_comments: string | null;
  gate_history: APQPGateHistoryEntry[] | null;
  dfmea_id: string | null;
  dfmea_document_no: string | null;
  pfmea_id: string | null;
  pfmea_document_no: string | null;
  control_plan_id: string | null;
  control_plan_document_no: string | null;
  ppap_submission_id: string | null;
  ppap_submission_part_no: string | null;
  ppap_submission_part_name: string | null;
  created_by: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface APQPGateHistoryEntry {
  phase: number;
  action: string;
  user_id: string;
  user_name: string;
  comments: string | null;
  timestamp: string;
}

export interface APQPListResponse {
  items: APQPProject[];
  total: number;
  page: number;
  page_size: number;
}

export interface APQPProjectCreate {
  project_name: string;
  product_name: string;
  product_line_code: string;
  customer_name?: string;
  description?: string;
  target_sop_date?: string;
  team_members?: { name: string; role: string; department: string }[];
  dfmea_id?: string;
  pfmea_id?: string;
  control_plan_id?: string;
  ppap_submission_id?: string;
}

export interface APQPProjectUpdate {
  project_name?: string;
  product_name?: string;
  product_line_code?: string;
  customer_name?: string | null;
  description?: string | null;
  target_sop_date?: string | null;
  team_members?: { name: string; role: string; department: string }[] | null;
  dfmea_id?: string | null;
  pfmea_id?: string | null;
  control_plan_id?: string | null;
  ppap_submission_id?: string | null;
}

export interface APQPGateTransition {
  action: "submit_gate" | "approve_gate" | "reject_gate" | "cancel";
  comments?: string;
}

export interface APQPProjectStats {
  total_projects: number;
  active_count: number;
  pending_approval_count: number;
  completed_count: number;
  cancelled_count: number;
  overdue_count: number;
  phase_distribution: Record<number, number>;
}

export interface CustomerAuditAttachment {
  file_name: string;
  file_url: string;
  file_size?: number;
  file_type?: string;
  uploaded_at?: string;
  uploaded_by?: string;
}

export interface CustomerAuditStats {
  total_customer_audits: number;
  planned: number;
  in_progress: number;
  completed: number;
  open_findings: number;
  major_nc_count: number;
  customer_confirmed_count: number;
  pending_confirmation_count: number;
}

export interface FindingTransitionRequest {
  action: "start_progress" | "close";
  customer_confirmed?: boolean;
  customer_confirmation_date?: string;
  customer_confirmation_attachments?: CustomerAuditAttachment[];
}

export interface CustomerConfirmationRequest {
  confirmation_date: string;
  attachments?: CustomerAuditAttachment[];
}

// ─── Shipment Records ───

export interface ShipmentRecord {
  shipment_id: string;
  customer_id: string;
  shipment_date: string;
  quantity: number;
  batch_no: string | null;
  destination: string | null;
  notes: string | null;
  product_line_code: string | null;
  created_at: string;
}

// ─── D7 Prevention Recurrence ───

export interface D7Recommendation {
  fmea_id: string | null;
  fmea_document_no: string | null;
  failure_mode_node_id: string;
  failure_mode_name: string | null;
  failure_cause_node_id: string | null;
  failure_cause_name: string | null;
  prevention_control_node_id: string | null;
  prevention_control_name: string | null;
  match_source: "linked" | "keyword" | "rule";
  match_reason: string;
  related_d4_keywords: string[];
  suggested_prevention: string | null;
}

export interface D7RecommendationResponse {
  recommendations: D7Recommendation[];
}

export interface D4Recommendation {
  stage_index?: number | null;
  failure_cause_node_id: string | null;
  failure_cause_name: string;
  failure_cause_desc: string | null;
  failure_mode_node_id: string | null;
  failure_mode_name: string | null;
  fmea_document_no: string | null;
  fmea_id: string | null;
  match_source:
    | "linked"
    | "keyword"
    | "rule"
    | "fmea_graph"
    | "semantic_search"
    | "historical_capa"
    | "llm"
    | "same_type_product_kb"
    | "lessons_learned"
    | "spc_anomaly"
    | "mes"
    | "iqc"
    | "supplier_history";
  match_reason: string;
  related_d2_keywords: string[];
  confidence: number;
  source_capa_id: string | null;
  source_capa_document_no: string | null;
  source_product_line_code: string | null;
  ap?: string | null;
  severity?: number | null;
  occurrence?: number | null;
  detection?: number | null;
}

export interface StageRun {
  index: number;
  name: string;
  source: string;
  status: "pending" | "running" | "done" | "skipped" | "error" | "blocked";
  hit_count: number;
  summary: string;
  error?: string | null;
  llm_attempted?: number | null;
  llm_succeeded?: number | null;
  llm_failed?: number | null;
}

export interface D4RecommendationResponse {
  stages: StageRun[];
  items: D4Recommendation[];
}

export interface D5ExistingControl {
  stage_index?: number | null;
  failure_mode_node_id: string | null;
  failure_mode_name: string | null;
  failure_cause_node_id: string | null;
  failure_cause_name: string | null;
  control_node_id: string;
  control_name: string;
  control_type: "prevention" | "detection";
  match_source: string;
  match_reason: string;
  fmea_id: string | null;
  fmea_document_no: string | null;
  ap?: string | null;
  severity?: number | null;
  occurrence?: number | null;
  detection?: number | null;
}

export interface D5GeneralSuggestion {
  stage_index?: number | null;
  content: string;
  category: string;
  basis: string;
  confidence: number;
  match_reason: string | null;
  match_source: string | null;
  source_capa_id: string | null;
  source_capa_document_no: string | null;
  ap?: string | null;
  severity?: number | null;
  occurrence?: number | null;
  detection?: number | null;
}

export interface D5RecommendationResponse {
  stages: StageRun[];
  existing_controls: D5ExistingControl[];
  general_suggestions: D5GeneralSuggestion[];
}

// --- CAPA AI Draft ---

export type DraftFormat = "structured" | "paragraph";

export interface DraftRequest {
  format: DraftFormat;
  request_id: string;
}

export interface DraftResponse {
  content: string;
  structured_data: Record<string, unknown> | null;
  request_id: string;
  step: string;
}

export interface AIDraftCapabilitiesResponse {
  ai_draft_enabled: boolean;
  llm_provider: string | null;
}

export interface DraftCapabilitiesResponse {
  available_steps: string[];
  current_step: string;
}

export type {
  WidgetMeta as DashboardWidgetMeta,
  WidgetLayoutItem as DashboardWidgetLayoutItem,
  DashboardLayoutConfig as DashboardWidgetLayoutConfig,
  DashboardWidgetsData as DashboardWidgetData,
  WidgetProps as DashboardWidgetProps,
  WidgetCategory as DashboardWidgetCategory,
  QualityTrendInterpretation,
} from "../components/dashboard/widgets/types";

// --- Lessons Learned ---

export interface LessonsLearnedRequest {
  problem_description?: string;
}

export interface LessonCard {
  id: string;
  title: string;
  summary: string;
  source_type: "fmea" | "capa" | "audit";
  source_document_no: string;
  source_id: string;
  source_product_line: string;
  same_product_line: boolean;
  confidence: number;
  match_reason: string;
  root_cause?: string;
  action?: string;
  severity?: string;
  metadata?: Record<string, unknown>;
}

export interface LessonCategories {
  fmea: LessonCard[];
  capa: LessonCard[];
  audit: LessonCard[];
}

export interface LessonsLearnedResponse {
  highlights: LessonCard[];
  categories: LessonCategories;
  source: string;
  cached: boolean;
}

// ─── IQC AQL Optimization Types ───

export interface AqlProfile {
  profile_id: string;
  supplier_id: string;
  material_id: string;
  base_aql: number;
  current_aql: number;
  min_aql: number | null;
  max_aql: number | null;
  inspection_level: string;
  state: 'normal' | 'tightened' | 'reduced' | 'frozen';
  frozen_until: string | null;
  frozen_reason: string | null;
  effective_from: string;
  approved_by: string | null;
  approved_at: string | null;
  state_changed_at: string | null;
  product_line_code: string;
  created_at: string;
  updated_at: string;
}

export interface AqlRecommendation {
  recommendation_id: string;
  profile_id: string;
  supplier_id: string;
  material_id: string;
  current_aql: number;
  recommended_aql: number;
  direction: 'keep' | 'reduce' | 'tighten' | 'freeze';
  trigger_rules: { rule_id: string; reason: string }[];
  evidence: Record<string, unknown>;
  status: 'pending' | 'forwarded' | 'approved' | 'effective' | 'rejected' | 'expired';
  approval_level: 'engineer' | 'manager';
  engineer_decision: string | null;
  engineer_decided_by: string | null;
  engineer_decided_at: string | null;
  manager_decision: string | null;
  manager_decided_by: string | null;
  manager_decided_at: string | null;
  effective_from: string | null;
  expires_at: string;
  created_at: string;
}

export interface AqlQualitySnapshot {
  snapshot_id: string;
  supplier_id: string;
  material_id: string;
  total_batches: number;
  consecutive_accepted: number;
  consecutive_rejected: number;
  last_30d_batch_count: number;
  last_30d_ppm: number | null;
  last_90d_ppm: number | null;
  open_scar_count: number;
  supplier_rating: string | null;
  has_safety_defect: boolean;
  linked_customer_complaint: boolean;
  calculated_state: string | null;
  snapshot_at: string;
}

export interface AqlConfig {
  config_id: string;
  config_key: string;
  config_value: string;
  value_type: string;
  description: string | null;
  product_line_code: string | null;
  is_editable: boolean;
}

export interface AqlPreviewResult {
  target_state: string;
  recommended_aql: number;
  direction: string;
  trigger_rules: { rule_id: string; reason: string }[];
  evidence: Record<string, unknown>;
}

// ─── Supplier Risk Alert ──────────────────────────────────────────────────────
export interface RuleResultDetail {
  rule_id: string;
  triggered: boolean;
  score: number;
  detail: string;
  category: string;
  critical: boolean;
}

export interface SupplierRiskAlert {
  alert_id: string;
  supplier_id: string;
  supplier_name: string;
  supplier_no: string;
  risk_level: "low" | "medium" | "high" | "critical";
  risk_score: number;
  quality_score: number;
  delivery_score: number;
  compliance_score: number;
  rule_results: Record<string, RuleResultDetail>;
  alert_type: "initial" | "escalated" | "routine";
  status: "open" | "acknowledged" | "action_taken" | "ignored" | "closed";
  handled_by: string | null;
  handled_at: string | null;
  handle_note: string | null;
  linked_scar_id: string | null;
  linked_capa_id: string | null;
  snapshot_date: string;
  product_line_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface RiskDashboard {
  high_risk_count: number;
  critical_risk_count: number;
  open_alert_count: number;
  avg_risk_score: number;
  risk_distribution: Record<string, number>;
  supplier_risk_points: Array<{
    supplier_id: string;
    supplier_name: string;
    quality_score: number;
    delivery_score: number;
    compliance_score: number;
    risk_level: string;
    risk_score: number;
  }>;
}

export interface SupplierRiskConfig {
  config_id: string;
  rule_id: string;
  enabled: boolean;
  thresholds: Record<string, unknown>;
  weight: number;
  supplier_id: string | null;
  category: string;
  product_line_code: string | null;
  updated_by: string;
  updated_at: string;
}

export interface NotificationChannel {
  channel_id: string;
  channel_type: "email" | "webhook";
  config: Record<string, unknown>;
  min_risk_level: string;
  enabled: boolean;
  supplier_id: string | null;
  product_line_code: string | null;
  created_by: string;
  created_at: string;
}

// --- Supply Chain Risk Map ---

export interface HeatmapCell {
  key: string;
  value: number | null;
  risk_index: number | null;
  level: string | null;
  diff: number | null;
  source: "risk_evaluation" | "erp_po" | "supplier_evaluation_fallback" | "iqc_inspection" | "missing";
}

export interface HeatmapColumn {
  key: string;
  label: string;
  type: "score" | "percent" | "number" | "count" | "risk";
  polarity: "higher_is_risk" | "lower_is_risk" | "neutral_exposure";
}

export interface HeatmapRow {
  supplier_id: string;
  supplier_name: string;
  cells: HeatmapCell[];
}

export interface HeatmapResponse {
  period: string;
  prev_period: string | null;
  product_line_code: string | null;
  columns: HeatmapColumn[];
  rows: HeatmapRow[];
}

export interface TimelineResponse {
  periods: string[];
  current_period: string;
  supplier_count: number;
}

export interface SupplierDimensionTrend {
  period: string;
  risk_score: number;
  quality_score: number;
  delivery_score: number;
  compliance_score: number;
}

export interface SupplierDetailResponse {
  supplier_id: string;
  supplier_name: string;
  product_line_code: string | null;
  period: string;
  dimensions: Record<string, { raw_value: number | null; risk_index: number | null; polarity: string; source: string }>;
  trend: SupplierDimensionTrend[];
}

export interface ComparisonResponse {
  period: string;
  suppliers: Array<{
    supplier_id: string;
    supplier_name: string;
    dimensions: Record<string, { raw_value: number | null; risk_index: number | null; polarity: string; source: string }>;
  }>;
}

export interface SnapshotGenerateResponse {
  snapshot_count: number;
  period: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string | null;
  email?: string | null;
  role_key: string;
}

export interface UserUpdateRequest {
  display_name?: string | null;
  email?: string | null;
  role_key?: string | null;
  is_active?: boolean | null;
  password?: string | null;
  default_factory_id?: string | null;
  factory_ids?: string[] | null;
}

export interface RoleOption {
  id: string;
  role_key: string;
  name_zh: string;
  name_en: string;
  is_system: boolean;
  is_editable: boolean;
}

export interface AuditLogItem {
  log_id: string;
  table_name: string;
  record_id: string;
  action: string;
  operated_by: string | null;
  ip_address: string | null;
  operated_at: string | null;
  changed_fields: Record<string, unknown> | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
}

export interface LoginLogItem {
  log_id: string;
  username: string;
  user_id: string | null;
  success: boolean;
  failure_reason: string | null;
  ip_address: string | null;
  occurred_at: string | null;
}

export interface SystemLogItem {
  log_id: string;
  logger_name: string;
  level: string;
  message: string;
  module: string | null;
  traceback: string | null;
  occurred_at: string | null;
}

// --- CAPA D4 verification / adoption / D7 node actions (Spec A) ---
export interface AdoptRequest {
  d_step: "d4" | "d5";
  adopted_text: string;
  source: string;
  stage_index?: number | null;
  item_ref?: Record<string, unknown> | null;
}
export interface AdoptResponse {
  adoption_id: string;
  d_step: string;
  field_value: string;
}
export type VerificationMethod = "measurement" | "observation" | "reproduction";
export type VerificationConclusion = "pending" | "passed" | "failed";

export interface Verification {
  verification_id: string;
  capa_id: string;
  root_cause_text: string;
  method: VerificationMethod | null;
  result: string | null;
  is_verified: boolean;
  conclusion: VerificationConclusion;
  evidence_attachments: Record<string, unknown>[];
  source_ref: Record<string, unknown> | null;
  verified_by: string | null;
  verified_at: string | null;
  created_at: string;
}
export interface VerificationCreate {
  root_cause_text: string;
  method?: VerificationMethod;
  result?: string;
  conclusion?: VerificationConclusion;
  evidence_attachments?: Record<string, unknown>[];
  source_ref?: Record<string, unknown> | null;
}
export interface VerificationUpdate {
  method?: VerificationMethod;
  result?: string;
  conclusion?: VerificationConclusion;
  evidence_attachments?: Record<string, unknown>[];
  source_ref?: Record<string, unknown> | null;
}
export interface D7NodeAction {
  action_id: string;
  capa_id: string;
  action: "confirmed" | "skipped" | "auto_filled";
  fmea_id: string | null;
  failure_mode_node_id: string;
  failure_cause_node_id: string | null;
  match_source: string;
  prevention_control_node_id: string | null;
  prevention_control_name_before: string | null;
  prevention_control_name_after: string | null;
  reason: string | null;
  acted_by: string;
  acted_at: string;
}
export interface D7NodeActionCreate {
  action: "confirmed" | "skipped";
  fmea_id: string | null;
  failure_mode_node_id: string;
  failure_cause_node_id?: string | null;
  match_source: string;
  reason?: string | null;
}
export interface D7AutoFillRequest {
  fmea_id: string | null;
  failure_mode_node_id: string;
  failure_cause_node_id: string;
  match_source: string;
}
export interface D7AutoFillResponse {
  action_id: string;
  prevention_control_node_id: string;
  prevention_control_name_after: string;
  is_new_control: boolean;
}

// ─── D3 Containment Types ──────────────────────────────────────────────────────

export interface D3ImportRun {
  run_id: string;
  capa_id: string;
  factory_id: string;
  status: "importing" | "completed" | "failed";
  is_current: boolean;
  imported_types: string[];
  analysis_context: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
  created_at: string;
}

export interface D3ProvenanceEntry {
  source_type: string;
  snapshot_id: string | null;
  record_key: string;
  stage: string;
}

export interface D3ContainmentSnapshot {
  snapshot_id: string;
  run_id: string;
  factory_id: string;
  snapshot_type: "inventory" | "shipment" | "iqc" | "spc";
  payload: Record<string, unknown>[];
  record_count: number;
  imported_at: string;
  created_at: string;
}

export interface D3ImpactReport {
  report_id: string;
  run_id: string;
  factory_id: string;
  is_current: boolean;
  status: "running" | "done" | "failed" | "superseded";
  risk_level: "high" | "medium" | "low" | null;
  risk_floor: "high" | "medium" | "low" | null;
  risk_explanation: string | null;
  batches: Record<string, unknown>[] | null;
  impact_qty: Record<string, unknown> | Record<string, unknown>[] | null;
  customer_impact: Record<string, unknown>[] | null;
  time_window: Record<string, unknown> | null;
  llm_available: boolean;
  model: string | null;
  stage_runs: Record<string, unknown>[] | null;
  prompt_stats: Record<string, unknown> | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
  generated_by: string;
  generated_at: string;
  created_at: string;
  // Populated by GET when a newer failed/superseded attempt exists alongside the
  // still-valid current report, so the UI can show a "最近一次重试失败" banner.
  latest_attempt_status?: "done" | "failed" | "superseded" | null;
  latest_attempt_error?: string | null;
}

export type D3AdviceType = "recall" | "isolate" | "notify_customer" | "strict_inspection" | "alternative";

export interface D3AiAdvice {
  advice_id: string;
  advice_type: D3AdviceType;
  advice_text: string;
  source_provenance: D3ProvenanceEntry[];
  target_batch_refs: string[] | null;
  adoption_status?: "adopted" | "rejected" | null;
}

export interface D3AdviceAdoption {
  adoption_id: string;
  advice_id: string;
  factory_id: string;
  decision: "adopted" | "rejected";
  adopted_text: string | null;
  advice_type: D3AdviceType;
  source_provenance: D3ProvenanceEntry[];
  decided_by: string;
  decided_at: string;
  created_at: string;
}

export interface D3AdviceResponse {
  advice: D3AiAdvice[];
  status?: "done" | "failed";
  error?: string | null;
  // Populated by GET when a newer failed attempt exists alongside the still-valid
  // current generation, so the UI can show a "最近一次重试失败" banner.
  latest_attempt_status?: "done" | "failed" | null;
  latest_attempt_error?: string | null;
}

export interface D3Execution {
  execution_id: string;
  source: "manual" | "adopted";
  advice_id: string | null;
  generation_id: string | null;
  result_status: "completed" | "in_progress" | "pending" | "failed";
  measure_text: string | null;
  evidence_refs: Record<string, unknown>[];
}

// D3 Request Types

export interface D3ImportRequest {
  snapshot_types?: string[];
}

export interface D3GenerateReportRequest {
  run_id: string;
}

export interface D3GenerateAdviceRequest {
  run_id: string;
}

export interface D3DecideAdviceRequest {
  decision: "adopted" | "rejected";
  adopted_text?: string | null;
}

export interface D3ExecutionCreate {
  source: "manual" | "adopted";
  advice_id?: string | null;
  measure_text: string;
  result_status?: "completed" | "in_progress" | "pending" | "failed";
  evidence_refs?: Record<string, unknown>[];
}

export interface D3ExecutionUpdate {
  result_status?: "completed" | "in_progress" | "pending" | "failed" | null;
  measure_text?: string | null;
  evidence_refs?: Record<string, unknown>[] | null;
}
