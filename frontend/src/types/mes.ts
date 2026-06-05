export interface MESConnection {
  connection_id: string;
  name: string;
  connector_type: "mock" | "rest";
  config: Record<string, any>;
  is_active: boolean;
  product_line_code: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface MESConnectionCreate {
  name: string;
  connector_type: "mock" | "rest";
  config: Record<string, any>;
  product_line_code?: string;
}

export interface MESProductionOrder {
  order_id: string;
  connection_id: string;
  order_no: string;
  product_model: string | null;
  process_route: string | null;
  status: string;
  planned_qty: number | null;
  actual_qty: number | null;
  started_at: string | null;
  completed_at: string | null;
  product_line_code: string | null;
  created_at: string;
}

export interface MESEquipmentStatus {
  record_id: string;
  equipment_code: string;
  equipment_name: string | null;
  status: string;
  availability: number | null;
  performance: number | null;
  quality: number | null;
  oee: number | null;
  downtime_reason: string | null;
  recorded_at: string;
  product_line_code: string | null;
}

export interface MESScrapRecord {
  scrap_id: string;
  connection_id: string;
  external_id: string;
  order_no: string | null;
  order_id: string | null;
  equipment_code: string | null;
  defect_type: string;
  defect_category: string | null;
  defect_qty: number;
  total_qty: number;
  defect_description: string | null;
  recorded_at: string;
  product_line_code: string | null;
}

export interface MESEquipmentSummary {
  equipment_code: string;
  equipment_name: string | null;
  status: string;
  availability: number | null;
  performance: number | null;
  quality: number | null;
  oee: number | null;
}

export interface MESDashboardData {
  equipment_summary: MESEquipmentSummary[];
  running_count: number;
  down_count: number;
  total_planned: number;
  total_actual: number;
  scrap_by_category: Record<string, number>;
  scrap_trend_7d: any[];
}
