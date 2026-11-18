import { beforeEach, describe, expect, it, vi } from "vitest";
import http from "./client";
import { pfmeaImpactClient } from "./pfmeaImpact";

vi.mock("./client", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const [report, target, version, install, model, task, result] = Array.from({ length: 7 },
  (_, index) => `00000000-0000-0000-0000-${String(index + 1).padStart(12, "0")}`);
const signal = new AbortController().signal;

describe("R7 employee client", () => {
  beforeEach(() => vi.clearAllMocks());

  it("binds creation to the path, selected approval, and selected deployment", async () => {
    vi.mocked(http.post).mockResolvedValue({ data: { taskId: task, status: "blocked_capability", resultId: null } });
    const run = await pfmeaImpactClient.start(report, {
      fmeaId: target, approvedVersionId: version, installationId: install, deploymentId: model, requestKey: "same-key",
    }, signal);
    expect(run?.taskId).toBe(task);
    expect(http.post).toHaveBeenCalledWith(`/capa/${report}/pfmea-impact/tasks`, {
      fmea_id: target, approved_version_id: version, installation_id: install, model_deployment_id: model,
      request_key: "same-key",
    }, { signal });
  });

  it("cannot retain an unauthorized history body or a half-validated response", async () => {
    vi.mocked(http.get).mockRejectedValueOnce({ response: { status: 404 } })
      .mockResolvedValueOnce({ data: { measures: [{ text: "Sensitive invalid response" }] } });
    const key = `${task}/${result}`;
    expect(await pfmeaImpactClient.readRecommendation(report, key, signal)).toBeNull();
    await expect(pfmeaImpactClient.readRecommendation(report, key, signal)).rejects.toThrow();
    expect(http.get).toHaveBeenCalledWith(`/capa/${report}/pfmea-impact/tasks/${task}/results/${result}`, { signal });
  });
});
