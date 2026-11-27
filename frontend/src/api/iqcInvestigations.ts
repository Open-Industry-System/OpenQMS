import client from "./client";

export type InvestigationAction = "check_existing" | "supplement_existing" | "consider_new";

export interface InspectionFamilyMember {
  inspection_id: string;
  inspection_no: string;
  inspection_date: string | null;
  status: string;
  inspection_result: string;
  parent_inspection_id: string | null;
}

export interface InvestigationFacts extends InspectionFamilyMember {
  inspection_revision: number;
  product_line_code: string | null;
  part_no: string | null;
  part_name: string | null;
  lot_no: string | null;
  lot_qty: number | null;
  sample_qty: number | null;
  defect_qty: number | null;
  defect_description: string | null;
  aql_level: string | null;
  accept_number: number | null;
  reject_number: number | null;
  judged_at: string | null;
  prior_inspection_result?: "rejected";
  disposition_changed?: boolean;
  family_complete: boolean;
  family: InspectionFamilyMember[];
}

export interface InvestigationContext {
  inspection_id: string;
  expected_version: string;
  eligible: boolean;
  eligibility_reason?: "pending_inspection" | "accepted_inspection" | "unverified_disposition" | null;
  deployments: { deployment_id: string; name: string; version: string }[];
  facts: InvestigationFacts;
}

export interface InvestigationTask {
  task_id: string;
  status: string;
  result_id?: string | null;
  created_at?: string;
}

export interface InvestigationEvidence {
  receipt_id: string;
  projection: string;
  version: string;
  data: unknown;
}

export interface InvestigationResult {
  result_id: string;
  task_id: string;
  created_at: string;
  stale: boolean;
  model_deployment?: { name: string; version: string } | null;
  card: {
    action: InvestigationAction;
    facts: InvestigationFacts;
    missing: string[];
    next_steps: string[];
    d2: string | null;
    evidence: InvestigationEvidence[];
  };
  current_hint: {
    action: InvestigationAction;
    investigations: {
      kind: "capa" | "scar";
      object_id: string;
      number: string;
      status: string;
      summary?: string | null;
      href?: string;
    }[];
    checked_modules: string[];
  };
}

export interface CreateInvestigation {
  expected_version: string;
  request_key: string;
  model_deployment_id: string;
  previous_result_id?: string;
}

const inspectionPath = (id: string) => `/iqc/inspections/${encodeURIComponent(id)}`;
const tasksPath = (id: string) => `${inspectionPath(id)}/investigations`;
const taskPath = (id: string, taskId: string) => `${tasksPath(id)}/${encodeURIComponent(taskId)}`;

export const iqcInvestigations = {
  async context(id: string, signal: AbortSignal): Promise<InvestigationContext> {
    const response = await client.get(`${inspectionPath(id)}/investigation-context`, { signal });
    return response.data;
  },
  async list(id: string, signal: AbortSignal): Promise<{ items: InvestigationTask[] }> {
    const response = await client.get(tasksPath(id), { signal });
    return response.data;
  },
  async create(id: string, data: CreateInvestigation, signal: AbortSignal): Promise<InvestigationTask> {
    const response = await client.post(tasksPath(id), data, { signal });
    return response.data;
  },
  async launch(id: string, taskId: string, signal: AbortSignal): Promise<InvestigationTask> {
    const response = await client.post(`${taskPath(id, taskId)}/launch`, null, { signal, timeout: 130_000 });
    return response.data;
  },
  async control(id: string, taskId: string, operation: "pause" | "resume" | "cancel",
    signal: AbortSignal): Promise<InvestigationTask> {
    const response = await client.post(`${taskPath(id, taskId)}/control`, { operation }, { signal });
    return response.data;
  },
  async result(id: string, taskId: string, resultId: string, signal: AbortSignal): Promise<InvestigationResult> {
    const response = await client.get(`${taskPath(id, taskId)}/results/${encodeURIComponent(resultId)}`, { signal });
    return response.data;
  },
};
