import axios from "axios";
import { readFileSync } from "fs";
import path from "path";

export const E2E_API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8001/api";

export const apiClient = axios.create({ baseURL: E2E_API_BASE_URL });

function storageStateToken(username: string): string | null {
  try {
    const statePath = path.resolve(
      process.cwd(),
      "e2e/.storage-state",
      `${username}.json`,
    );
    const state = JSON.parse(readFileSync(statePath, "utf-8"));
    for (const origin of state.origins || []) {
      const token = (origin.localStorage || []).find(
        (entry: { name: string; value: string }) => entry.name === "access_token",
      )?.value;
      if (typeof token === "string" && token.split(".").length === 3) return token;
    }
  } catch {
    // Global setup may not have created storage state yet; use API login fallback.
  }
  return null;
}

export async function loginForToken(username: string, password: string): Promise<string> {
  const stored = storageStateToken(username);
  if (stored) return stored;
  const r = await apiClient.post("/auth/login", { username, password });
  return r.data.access_token as string;
}

export async function authedApi(token: string) {
  return axios.create({ baseURL: E2E_API_BASE_URL, headers: { Authorization: `Bearer ${token}` } });
}

export async function completeD3Gate(capaId: string): Promise<void> {
  const { accountPassword } = await import("../fixtures/seed-state");
  const password = await accountPassword("engineer");
  const token = await loginForToken("engineer", password);
  const client = await authedApi(token);

  const imported = await client.post(`/capa/${capaId}/d3/import`, {
    snapshot_types: ["inventory", "shipment", "iqc", "spc"],
  });
  if (imported.data.report_status !== "done") {
    throw new Error(`D3 report not done: ${JSON.stringify(imported.data)}`);
  }

  await client.post(`/capa/${capaId}/d3/execution`, {
    source: "manual",
    measure_text: "E2E manual containment execution",
    result_status: "in_progress",
  });
}

export async function cleanupByPrefix(prefix: string): Promise<void> {
  // Best-effort; backend gated endpoint. Requires an admin token.
  // Read admin password from seed-state (single source of truth) via dynamic
  // import to avoid a circular dependency (api-client ← seed-state ← api-client).
  const { accountPassword } = await import("../fixtures/seed-state");
  const adminPw = await accountPassword("admin");
  const token = await loginForToken("admin", adminPw);
  const ac = await authedApi(token);
  await ac.post(`/e2e/cleanup?prefix=${encodeURIComponent(prefix)}`);
}
