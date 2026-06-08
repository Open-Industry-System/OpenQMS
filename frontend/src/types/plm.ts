// ─── PLM Connection ───

export interface PLMConnection {
  connection_id: string;
  name: string;
  connector_type: string;
  config: Record<string, any>;
  is_active: boolean;
  product_line_code: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PLMConnectionCreate {
  name: string;
  connector_type: string;
  config: Record<string, any>;
  product_line_code: string;
}

export interface PLMConnectionUpdate {
  name?: string;
  connector_type?: string;
  config?: Record<string, any>;
  is_active?: boolean;
  product_line_code?: string;
}

export interface PLMConnectionListResponse {
  items: PLMConnection[];
  total: number;
  page: number;
  page_size: number;
}

// ─── PLM Part ───

export interface PLMPart {
  part_id: string;
  connection_id: string;
  external_id: string;
  part_number: string;
  name: string;
  revision: string;
  material: string | null;
  specification: string | null;
  status: string;
  is_safety_related: boolean;
  is_key_characteristic: boolean;
  source_updated_at: string | null;
  product_line_code: string | null;
  plm_raw_data: Record<string, any> | null;
}

// ─── PLM BOM ───

export interface PLMBOM {
  bom_id: string;
  connection_id: string;
  external_id: string;
  parent_part_number: string;
  parent_revision: string;
  child_part_number: string;
  child_revision: string;
  quantity: number;
  bom_revision: string;
  level: number;
  source_updated_at: string | null;
  product_line_code: string | null;
  plm_raw_data: Record<string, any> | null;
}

export interface PLMBOMTreeNode {
  parent_part_number: string;
  parent_revision: string;
  child_part_number: string;
  child_revision: string;
  quantity: number;
  level: number;
  bom_revision: string;
}

export interface PLMBOMTreeResponse {
  root: string;
  items: PLMBOMTreeNode[];
  total: number;
}

// ─── PLM Change Order ───

export interface PLMChangeOrder {
  change_id: string;
  connection_id: string;
  external_id: string;
  change_number: string;
  title: string;
  description: string | null;
  change_type: string;
  status: string;
  priority: string;
  affected_part_numbers: string[];
  proposed_changes: Record<string, any> | null;
  requested_by: string | null;
  approved_by: string | null;
  planned_implementation_date: string | null;
  actual_implementation_date: string | null;
  source_updated_at: string | null;
  product_line_code: string | null;
  plm_raw_data: Record<string, any> | null;
}

// ─── PLM Change Impact Task ───

export interface PLMChangeImpactTask {
  task_id: string;
  change_id: string;
  status: string;
  retry_count: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  result: Record<string, any> | null;
}

// ─── PLM Dashboard ───

export interface PLMDashboard {
  part_count: number;
  bom_count: number;
  pending_ecn_count: number;
  pending_sc_count: number;
  recent_changes: PLMChangeOrder[];
}
