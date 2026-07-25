import axios from "axios";

export const E2E_API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8001/api";

export const apiClient = axios.create({ baseURL: E2E_API_BASE_URL });

export async function loginForToken(username: string, password: string): Promise<string> {
  const r = await apiClient.post("/auth/login", { username, password });
  return r.data.access_token as string;
}

export async function authedApi(token: string) {
  return axios.create({ baseURL: E2E_API_BASE_URL, headers: { Authorization: `Bearer ${token}` } });
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
