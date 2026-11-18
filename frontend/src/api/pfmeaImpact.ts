import http from "./client";
import type {
  ImpactOption, ImpactRecommendation, ImpactResultChoice, ImpactTarget, ImpactTaskStatusView, PfmeaImpactClients,
} from "../components/agent/PfmeaImpactPanel";

type Check = (value: unknown) => boolean;
const text: Check = value => typeof value === "string" && value.length <= 16384;
const bool: Check = value => typeof value === "boolean";
const uuid: Check = value => typeof value === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const list = (rule: Check, max = 256): Check => value => Array.isArray(value) && value.length <= max && value.every(rule);
const oneOf = (...choices: unknown[]): Check => value => choices.includes(value);
const optional = (rule: Check): Check => value => value === null || rule(value);
const object = (rules: Record<string, Check>): Check => value => typeof value === "object" && value !== null &&
  !Array.isArray(value) && Object.keys(value).length === Object.keys(rules).length &&
  Object.entries(rules).every(([key, rule]) =>
    Object.prototype.hasOwnProperty.call(value, key) && rule((value as Record<string, unknown>)[key]));
const page = (rule: Check, max = 50) => object({
  items: list(rule, max),
  total: value => typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 500,
});
const verdict = oneOf("impact_found", "no_impact_found", "insufficient_evidence");
const freshness = oneOf("current", "stale");
const task = object({
  taskId: uuid, resultId: optional(uuid),
  status: oneOf("blocked_capability", "ready", "queued", "running", "paused", "completed", "failed", "cancelled"),
});
const target = object({
  fmeaId: uuid, documentNo: text, title: text, approvedVersionId: uuid, approvedVersionLabel: text, hasUnapprovedRevision: bool,
});
const option = object({
  installation_id: uuid, deployment_id: uuid, name: text, version: text, kind: oneOf("local", "cloud"),
});
const past = object({
  taskId: uuid, resultId: uuid, approvedVersionLabel: text, freshness,
  createdAt: val => typeof val === "string" && Number.isFinite(Date.parse(val)),
});
const source = object({ id: uuid, label: text });
const recommendation = object({
  reportVersionLabel: text, approvedVersionLabel: text, freshness, conclusion: verdict,
  measures: list(object({
    measureId: uuid, formalRevision: optional(uuid), text, conclusion: verdict, facts: list(text),
    inference: text, reason: text, adjustments: list(text), gaps: list(text), evidence: list(source),
  }), 32),
});
const evidence = object({ label: text, text });

function parse<T>(value: unknown, rule: Check): T {
  if (!rule(value)) throw new Error("Invalid impact assessment response");
  return value as T;
}

function path(id: string): string {
  if (!uuid(id)) throw new Error("Invalid impact assessment reference");
  return id;
}

const base = (reportId: string) => `/capa/${path(reportId)}/pfmea-impact`;
const resultPath = (reportId: string, key: string) => {
  const ids = key.split("/");
  if (ids.length !== 2) throw new Error("Invalid impact result reference");
  return `${base(reportId)}/tasks/${path(ids[0])}/results/${path(ids[1])}`;
};

async function restricted<T>(request: () => Promise<{ data: unknown }>, rule: Check): Promise<T | null> {
  try {
    const response = await request();
    return parse<T>(response.data, rule);
  } catch (error) {
    const status = (error as { response?: { status?: number } })?.response?.status;
    if (status === 401 || status === 403 || status === 404) return null;
    throw error;
  }
}

export function pfmeaImpactAvailable(reportId: string, signal: AbortSignal) {
  return restricted<{ available: boolean; canGenerate: boolean }>(
    () => http.get(`${base(reportId)}/availability`, { signal }), object({ available: bool, canGenerate: bool }),
  );
}

type RawOption = { installation_id: string; deployment_id: string; name: string; version: string; kind: "local" | "cloud" };

export const pfmeaImpactClient: PfmeaImpactClients = {
  listTargets: (reportId, { page: pageNumber, pageSize }, signal) => restricted<{ items: ImpactTarget[]; total: number }>(
    () => http.get(`${base(reportId)}/targets`, { params: { page: pageNumber, page_size: pageSize }, signal }), page(target),
  ),

  async listOptions(reportId, { fmeaId, approvedVersionId }, signal) {
    const data = await restricted<{ items: RawOption[] }>(
      () => http.get(`${base(reportId)}/options`, {
        params: { fmea_id: path(fmeaId), approved_version_id: path(approvedVersionId) }, signal,
      }), object({ items: list(option, 50) }),
    );
    return data?.items.map((item): ImpactOption => ({
      installationId: item.installation_id, deploymentId: item.deployment_id,
      name: item.name, version: item.version, kind: item.kind,
    })) ?? null;
  },

  start: (reportId, input, signal) => restricted<ImpactTaskStatusView>(
    () => http.post(`${base(reportId)}/tasks`, {
      fmea_id: path(input.fmeaId), approved_version_id: path(input.approvedVersionId),
      installation_id: path(input.installationId ?? ""), model_deployment_id: path(input.deploymentId ?? ""),
      request_key: input.requestKey,
      ...(input.previousResultId ? { previous_result_id: path(input.previousResultId) } : {}),
    }, { signal }), task,
  ),

  launch: (reportId, taskId, signal) => restricted<ImpactTaskStatusView>(
    () => http.post(`${base(reportId)}/tasks/${path(taskId)}/launch`, undefined, { signal, timeout: 300000 }), task,
  ),

  cancel: (reportId, taskId, signal) => restricted<ImpactTaskStatusView>(
    () => http.post(`${base(reportId)}/tasks/${path(taskId)}/cancel`, undefined, { signal }), task,
  ),

  readTask: (reportId, taskId, signal) => restricted<ImpactTaskStatusView>(
    () => http.get(`${base(reportId)}/tasks/${path(taskId)}`, { signal }), task,
  ),

  listResults: (reportId, { page: pageNumber, pageSize }, signal) =>
    restricted<{ items: ImpactResultChoice[]; hasMore: boolean }>(
      () => http.get(`${base(reportId)}/results`, { params: { page: pageNumber, page_size: pageSize }, signal }),
      object({ items: list(past, 20), hasMore: bool }),
    ),

  readRecommendation: (reportId, key, signal) => restricted<ImpactRecommendation>(
    () => http.get(resultPath(reportId, key), { signal }), recommendation,
  ),

  readEvidence: (reportId, key, sourceId, signal) => restricted<{ label: string; text: string }>(
    () => http.get(`${resultPath(reportId, key)}/sources/${path(sourceId)}`, { signal }), evidence,
  ),
};
