/** User-facing DTOs only. Runtime credentials never enter the browser. */
export type TaskStatus = "blocked_capability" | "ready" | "paused" | "completed" | "failed" | "cancelled";
export type RunStatus = "pending" | "active" | "paused" | "stopped" | "completed" | "failed";
export type TaskAction = "pause" | "resume" | "cancel" | "restart";
export interface AgentTask {
  task_id: string;
  target_capa_id: string;
  factory_id: string;
  preferred_installation_id: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
}
export interface TaskCreate {
  report_id: string;
  installation_id: string;
  request_key: string;
  initial_text: string;
}
export interface InstallationChoice {
  installation_id: string;
  plugin_key: string;
  plugin_version: string;
}
export interface TaskMessageCreate {
  content: string;
  idempotency_key: string;
}
export interface TaskMessageAccepted {
  message_id: string;
  sequence: number;
  state: "queued" | "claimed" | "accepted";
}
export interface TaskControl {
  action: TaskAction;
  run_id?: string | null;
  expected_epoch?: number | null;
  checkpoint_id?: string | null;
  idempotency_key: string;
}
export interface TaskControlOut {
  control_id: string;
  task_id: string;
  task_status: TaskStatus;
  run_id: string | null;
  run_status: RunStatus | null;
  lease_epoch: number | null;
}
export interface RuntimeSource {
  receipt_id: string;
  source_capa_id: string;
  projection_id: "capa.d4.summary.masked.v1";
  projection_digest: string;
  data_class: "internal";
}
export interface EventPayload {
  stage: string | null;
  message: string | null;
  completed: number | null;
  total: number | null;
}
export interface ResultPayload {
  explanations: string[];
  support: string[];
  opposition: string[];
  missing_information: string[];
  conditional_recommendations: string[];
}
export interface RuntimeResult {
  result_id: string;
  task_id: string;
  run_id: string;
  data_class: "restricted";
  payload: ResultPayload;
  sources: RuntimeSource[];
}
export interface ReadonlyCheckpoint {
  checkpoint_id: string;
  task_id: string;
  run_id: string;
  lease_epoch: number;
  tenant_generation: number;
  accepted_message_seq: number;
  update_sequence: number;
  created_at: string;
  sources: RuntimeSource[];
  is_latest: boolean;
  prefix_eligible: boolean;
}
interface ItemBase {
  sequence: number;
  created_at: string;
}
export type ActivityItem = ItemBase & ({
  kind: "message";
  data: {
    message_id: string;
    sequence: number;
    author_id: string;
    content: string;
    data_class: "restricted";
    state: "queued" | "claimed" | "received";
  };
} | {
  kind: "ack";
  data: {
    batch_id: string;
    state: "received";
  };
} | {
  kind: "run_created" | "claim" | "finish";
  data: {
    run_id: string;
    installation_id: string;
    plugin_version: string;
    run_status: RunStatus;
    lease_epoch: number;
  };
} | {
  kind: "control";
  data: {
    control_id: string;
    action: TaskAction;
    run_id: string | null;
    resulting_run_id: string | null;
    checkpoint_id: string | null;
  };
} | {
  kind: "event";
  data: ({
    event_id: string;
    task_id: string;
    run_id: string;
    event_type: "progress" | "query_completed";
    data_class: "restricted";
    payload: EventPayload;
    sources: RuntimeSource[];
  } | {
    event_id: string;
    task_id: string;
    run_id: string;
    event_type: "progress";
    presentation_code: "plugin_running";
    created_at: string;
    sources: [
    ];
  });
} | {
  kind: "result";
  data: RuntimeResult;
} | {
  kind: "checkpoint";
  data: ReadonlyCheckpoint;
});
export interface ActivityPage {
  task_id: string;
  task_status: TaskStatus;
  run_id: string | null;
  run_status: RunStatus | null;
  lease_epoch: number | null;
  window_end_sequence: number;
  next_before_sequence: number | null;
  items: ActivityItem[];
}
export interface ActivityQuery {
  page_size: number;
  before_sequence?: number;
  window_end_sequence?: number;
}
