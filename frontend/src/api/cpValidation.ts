import client from "./client";
import type {
  ValidationResultsList,
  ValidationRun,
  ValidationSummary,
  ValidationResult,
} from "../types/cpValidation";

export async function getValidationResults(
  cpId: string,
  filters?: { status?: string; severity?: string }
): Promise<ValidationResultsList> {
  const resp = await client.get(`/control-plans/${cpId}/validation-results`, {
    params: filters,
  });
  return resp.data;
}

export async function triggerValidation(cpId: string): Promise<ValidationRun> {
  const resp = await client.post(`/control-plans/${cpId}/validate`);
  return resp.data;
}

export async function getValidationRuns(cpId: string): Promise<ValidationRun[]> {
  const resp = await client.get(`/control-plans/${cpId}/validation-runs`);
  return resp.data;
}

export async function getValidationSummary(cpId: string): Promise<ValidationSummary> {
  const resp = await client.get(`/control-plans/${cpId}/validation-summary`);
  return resp.data;
}

export async function rejectValidationResult(findingId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${findingId}/reject`);
  return resp.data;
}

export async function resolveValidationResult(findingId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${findingId}/resolve`);
  return resp.data;
}

export async function reopenValidationResult(findingId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${findingId}/reopen`);
  return resp.data;
}

export async function batchValidationSummaries(cpIds: string[]): Promise<Record<string, ValidationSummary>> {
  const resp = await client.post("/control-plans/validation-summaries", { cp_ids: cpIds });
  return resp.data.summaries;
}
