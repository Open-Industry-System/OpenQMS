export interface SpecialCharacteristic {
  sc_id: string;
  sc_code: string;
  sc_name: string;
  sc_type: "CC" | "SC";
  customer_symbol: string | null;
  sc_category: string | null;
  spec_requirement: string | null;
  parent_sc_id: string | null;
  source_fmea_id: string | null;
  source_fmea_title: string | null;
  source_fmea_document_no: string | null;
  source_node_id: string;
  source_type: "DFMEA" | "PFMEA";
  cp_item_id: string | null;
  msa_study_id: string | null;
  msa_status: "PENDING" | "PASS" | "FAIL";
  sop_ref: string | null;
  product_line_code: string;
  is_supplier_shared: boolean;
  supplier_code: string | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SCListResponse {
  items: SpecialCharacteristic[];
  total: number;
  page: number;
  page_size: number;
}

export interface MatrixRow {
  sc_id: string;
  sc_code: string;
  sc_name: string;
  sc_type: string;
  customer_symbol: string | null;
  product_line_code: string;
  has_dfmea: boolean;
  has_pfmea: boolean;
  has_cp: boolean;
  msa_status: string;
  has_sop: boolean;
  dfmea_link: string | null;
  pfmea_link: string | null;
  cp_link: string | null;
  msa_link: string | null;
}

export interface MatrixResponse {
  characteristics: MatrixRow[];
}

export interface SeverityWarning {
  node_id: string;
  node_name: string;
  severity: number;
  fmea_id: string;
  fmea_title: string;
}

export interface CPSyncStatusItem {
  item_id: string;
  step_no: string;
  process_name: string;
  current_special_class: string | null;
  expected_special_class: string | null;
  is_out_of_sync: boolean;
}

export interface CPSyncStatusResponse {
  items: CPSyncStatusItem[];
  total_out_of_sync: number;
}
