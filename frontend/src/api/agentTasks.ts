import client from "./client";
import type { ActivityPage, ActivityQuery, AgentTask, InstallationChoice, ReadonlyCheckpoint, RuntimeResult, TaskControl, TaskControlOut, TaskCreate, TaskMessageAccepted, TaskMessageCreate } from "../types/agentTask";
// Validate every user read before retaining restricted content. Unknown keys and
// union variants fail closed, including axios' raw invalid-JSON string fallback.
type Check = (v: unknown) => boolean;
const str = (max = 10000): Check => v => typeof v === "string" && v.length <= max;
const uuid: Check = v => typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const date: Check = v => typeof v === "string" && Number.isFinite(Date.parse(v));
const int = (min = 0, max = Number.MAX_SAFE_INTEGER): Check => v => typeof v === "number" && Number.isSafeInteger(v) && v >= min && v <= max;
const lit = (...values: unknown[]): Check => v => values.includes(v);
const nullable = (check: Check): Check => v => v === null || check(v);
const list = (check: Check, min = 0, max = 50): Check => v => Array.isArray(v) && v.length >= min && v.length <= max && v.every(check);
const object = (fields: Record<string, Check>): Check => v => typeof v === "object" && v !== null && !Array.isArray(v) && Object.keys(v).length === Object.keys(fields).length && Object.entries(fields).every(([key, check]) => Object.prototype.hasOwnProperty.call(v, key) && check((v as Record<string, unknown>)[key]));
const taskStatus = lit("blocked_capability", "ready", "paused", "completed", "failed", "cancelled");
const runStatus = lit("pending", "active", "paused", "stopped", "completed", "failed");
const action = lit("pause", "resume", "cancel", "restart");
const source = object({
  receipt_id: uuid,
  source_capa_id: uuid,
  projection_id: lit("capa.d4.summary.masked.v1"),
  projection_digest: v => typeof v === "string" && /^[a-f0-9]{64}$/.test(v),
  data_class: lit("internal")
});
const sources = list(source, 1, 20);
const eventPayload = object({
  stage: nullable(str(100)),
  message: nullable(str(1000)),
  completed: nullable(int(0, 1000000)),
  total: nullable(int(0, 1000000))
});
const analysis = list(str(2000), 0, 20);
const result = object({
  result_id: uuid,
  task_id: uuid,
  run_id: uuid,
  data_class: lit("restricted"),
  payload: object({
    explanations: analysis,
    support: analysis,
    opposition: analysis,
    missing_information: analysis,
    conditional_recommendations: analysis
  }),
  sources
});
const checkpoint = object({
  checkpoint_id: uuid,
  task_id: uuid,
  run_id: uuid,
  lease_epoch: int(),
  tenant_generation: int(),
  accepted_message_seq: int(),
  update_sequence: int(1),
  created_at: date,
  sources,
  is_latest: lit(true, false),
  prefix_eligible: lit(true, false)
});
const run = object({
  run_id: uuid,
  installation_id: uuid,
  plugin_version: str(),
  run_status: runStatus,
  lease_epoch: int()
});
const eventSourced = object({
  event_id: uuid,
  task_id: uuid,
  run_id: uuid,
  event_type: lit("progress", "query_completed"),
  data_class: lit("restricted"),
  payload: eventPayload,
  sources
});
const eventRunning = object({
  event_id: uuid,
  task_id: uuid,
  run_id: uuid,
  event_type: lit("progress"),
  presentation_code: lit("plugin_running"),
  created_at: date,
  sources: list(source, 0, 0)
});
const variants: Record<string, Check> = {
  message: object({
    message_id: uuid,
    sequence: int(1),
    author_id: uuid,
    content: str(),
    data_class: lit("restricted"),
    state: lit("queued", "claimed", "received")
  }),
  ack: object({ batch_id: uuid, state: lit("received") }),
  run_created: run,
  claim: run,
  finish: run,
  control: object({
    control_id: uuid,
    action,
    run_id: nullable(uuid),
    resulting_run_id: nullable(uuid),
    checkpoint_id: nullable(uuid)
  }),
  event: v => eventSourced(v) || eventRunning(v),
  result,
  checkpoint,
};
const item: Check = v => {
  if (typeof v !== "object" || v === null || !("kind" in v) || typeof v.kind !== "string" || !Object.prototype.hasOwnProperty.call(variants, v.kind))
    return false;
  return object({
    sequence: int(1),
    created_at: date,
    kind: lit(v.kind),
    data: variants[v.kind]
  })(v);
};
const task = object({
  task_id: uuid,
  target_capa_id: uuid,
  factory_id: uuid,
  preferred_installation_id: uuid,
  status: taskStatus,
  created_at: date,
  updated_at: date
});
const controlOut = object({
  control_id: uuid,
  task_id: uuid,
  task_status: taskStatus,
  run_id: nullable(uuid),
  run_status: nullable(runStatus),
  lease_epoch: nullable(int())
});
function parse<T>(value: unknown, check: Check): T {
  if (!check(value))
    throw new Error("Invalid Agent response");
  return value as T;
}
export function parseActivityPage(value: unknown): ActivityPage {
  const page = parse<ActivityPage>(value, object({
    task_id: uuid,
    task_status: taskStatus,
    run_id: nullable(uuid),
    run_status: nullable(runStatus),
    lease_epoch: nullable(int()),
    window_end_sequence: int(),
    next_before_sequence: nullable(int(1)),
    items: list(item)
  }));
  if ((page.run_id === null) !== (page.run_status === null) || (page.run_id === null) !== (page.lease_epoch === null) || (page.next_before_sequence !== null && page.next_before_sequence > page.window_end_sequence + 1) || page.items.some((entry, i) => entry.sequence > page.window_end_sequence || (i > 0 && entry.sequence <= page.items[i - 1].sequence)))
    throw new Error("Invalid Agent page bounds");
  return page;
}
const base = "/agent/tasks";
export async function getTaskAvailability(signal?: AbortSignal): Promise<{
  enabled: true;
}> {
  return parse((await client.get(`${base}/availability`, { signal })).data, object({ enabled: lit(true) }));
}
export async function listTaskInstallations(reportId: string, signal?: AbortSignal): Promise<{
  items: InstallationChoice[];
}> {
  return parse((await client.get(`${base}/installations`, { params: { report_id: reportId }, signal })).data, object({ items: list(object({ installation_id: uuid, plugin_key: str(), plugin_version: str() }), 0, 1000) }));
}
export async function listTasks(query: {
  page: number;
  page_size: number;
} = { page: 1, page_size: 20 }, signal?: AbortSignal): Promise<{
  items: AgentTask[];
  total: number;
  page: number;
  page_size: number;
}> {
  return parse((await client.get(base, { params: query, signal })).data, object({
    items: list(task, 0, 100),
    total: int(),
    page: int(1),
    page_size: int(1, 100)
  }));
}
export async function getTask(taskId: string, signal?: AbortSignal): Promise<AgentTask> {
  return parse((await client.get(`${base}/${taskId}`, { signal })).data, task);
}
export async function createTask(body: TaskCreate, signal?: AbortSignal): Promise<AgentTask> {
  return parse((await client.post(base, body, { signal })).data, task);
}
export async function appendTaskMessage(taskId: string, body: TaskMessageCreate, signal?: AbortSignal): Promise<TaskMessageAccepted> {
  return parse((await client.post(`${base}/${taskId}/messages`, body, { signal })).data, object({ message_id: uuid, sequence: int(1), state: lit("queued", "claimed", "accepted") }));
}
export async function controlTask(taskId: string, body: TaskControl, signal?: AbortSignal): Promise<TaskControlOut> {
  return parse((await client.post(`${base}/${taskId}/control`, body, { signal })).data, controlOut);
}
export async function getTaskActivity(taskId: string, query: ActivityQuery, signal?: AbortSignal): Promise<ActivityPage> {
  const page = parseActivityPage((await client.get(`${base}/${taskId}/activity`, { params: query, signal })).data);
  if (page.task_id !== taskId || page.items.length > query.page_size)
    throw new Error("Invalid Agent task page");
  return page;
}
export async function getTaskResult(taskId: string, resultId: string, signal?: AbortSignal): Promise<RuntimeResult> {
  return parse((await client.get(`${base}/${taskId}/results/${resultId}`, { signal })).data, result);
}
export async function getTaskCheckpoint(taskId: string, checkpointId: string, signal?: AbortSignal): Promise<ReadonlyCheckpoint> {
  return parse((await client.get(`${base}/${taskId}/checkpoints/${checkpointId}`, { signal })).data, checkpoint);
}
