// ─── ERP Connection ───

export interface ERPConnection {
  connection_id: string;
  name: string;
  connector_type: string;
  config: Record<string, unknown>;
  is_active: boolean;
  product_line_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ERPSupplier {
  erp_supplier_id: string;
  supplier_code: string;
  name: string;
  status: string;
  link_status: string;
  openqms_supplier_id: string | null;
  payment_terms?: string;
  currency?: string;
  tax_id?: string;
  bank_info?: Record<string, unknown>;
  product_line_code: string | null;
}

export interface ERPCustomer {
  erp_customer_id: string;
  customer_code: string;
  name: string;
  status: string;
  link_status: string;
  openqms_customer_id: string | null;
  region?: string;
  customer_level?: string;
  tax_id?: string;
  product_line_code: string | null;
}

export interface ERPMaterial {
  material_id: string;
  material_code: string;
  name: string;
  specification?: string;
  unit?: string;
  material_type?: string;
  is_purchased: boolean;
  is_manufactured: boolean;
  status: string;
  product_line_code: string | null;
}

export interface ERPLocation {
  location_id: string;
  location_code: string;
  warehouse_code?: string;
  zone_code?: string;
  location_type: string;
  is_enabled: boolean;
  product_line_code: string | null;
}

export interface ERPPurchaseOrder {
  po_id: string;
  po_number: string;
  line_number: string;
  supplier_code?: string;
  material_code?: string;
  quantity?: number;
  unit_price?: number;
  currency?: string;
  delivery_date?: string;
  received_quantity?: number;
  status: string;
  lot_no?: string;
  product_line_code: string | null;
}

export interface ERPSalesOrder {
  so_id: string;
  so_number: string;
  line_number: string;
  customer_code?: string;
  material_code?: string;
  quantity?: number;
  unit_price?: number;
  delivery_date?: string;
  status: string;
  product_line_code: string | null;
}

export interface ERPInventoryBalance {
  balance_id: string;
  material_code: string;
  location_code: string;
  lot_no: string;
  supplier_lot_no?: string;
  quantity?: number;
  unit?: string;
  inventory_status: string;
  product_line_code: string | null;
}

export interface ERPShipment {
  erp_shipment_id: string;
  shipment_number: string;
  line_number: string;
  so_number?: string;
  customer_code?: string;
  material_code?: string;
  lot_no?: string;
  quantity?: number;
  shipment_date?: string;
  openqms_shipment_id: string | null;
  link_status: string;
  product_line_code: string | null;
}

export interface ERPCostRecord {
  cost_id: string;
  record_type: string;
  cost_category: string;
  cost_type: string;
  amount: number;
  currency?: string;
  period_month?: string;
  source_document_no?: string;
  material_code?: string;
  supplier_code?: string;
  cost_center?: string;
  cost_date?: string;
  description?: string;
  product_line_code: string | null;
}

export interface TraceabilityNode {
  id: string;
  type: string;
  label: string;
}

export interface TraceabilityEdge {
  from: string;
  to: string;
  type: string;
}

export interface TraceabilityGap {
  type: string;
  message: string;
  node_id?: string;
}

export interface TraceabilityResponse {
  nodes: TraceabilityNode[];
  edges: TraceabilityEdge[];
  gaps: TraceabilityGap[];
}

export interface ERPDashboardData {
  sync_health: Array<{ data_type: string; status: string; last_sync: string | null }>;
  coq_summary: Record<string, number>;
  pending_actions: unknown[];
  inventory_alerts: unknown[];
  shipment_risks: unknown[];
  kpis: Array<{ label: string; value: string | number; status?: string }>;
}