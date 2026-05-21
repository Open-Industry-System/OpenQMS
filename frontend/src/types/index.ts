export interface User {
  user_id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role: string;
  is_active: boolean;
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
  type: string;  // 节点类型：ProcessItem, ProcessStep, ProcessWorkElement 等
  name: string;  // 展示名称
  
  // 结构分析相关属性
  process_number?: string;   // 过程步骤工序号，如 "OP30"
  classification?: string;   // 作业要素的 4M 类别 (Man/Machine等) 或特殊特性分类 (CC/SC)
  
  // 功能分析与技术要求
  requirement?: string;      // 技术要求
  specification?: string;    // 产品特性公差参数
  
  // 风险评估数值
  severity: number;          // 综合严重度 (1-10)
  severity_plant?: number;   // 本厂影响严重度
  severity_customer?: number;// 直接客户/下级工厂影响严重度
  severity_user?: number;    // 最终用户影响严重度
  
  occurrence: number;        // 发生频度 (1-10)
  detection: number;         // 探测度 (1-10)
  
  // 建议优化与改进措施
  responsible?: string;      // 责任人
  due_date?: string;         // 计划完成日期
  status?: string;           // 状态
  action_taken?: string;     // 实际采取的措施描述
  completion_date?: string;  // 实际完成日期
  
  revised_severity?: number; // 改进后严重度
  revised_occurrence?: number;// 改进后频度
  revised_detection?: number; // 改进后探测度
  revised_ap?: string;       // 改进后措施优先级 (H / M / L)

  p_diagram?: {
    inputs: string[];
    outputs: string[];
    controls: string[];
    noise_factors: string[];
  };
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
