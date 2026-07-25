import { apiClient } from "../helpers/api-client";

export interface SeedState {
  factories: { code: string; name: string; id: string }[];
  product_lines: { code: string; name: string; factory_id: string }[];
  // password is included — seed_e2e is the single source of truth (demo creds are public).
  accounts: { username: string; password: string; role_key: string; factory_codes: string[] }[];
  known_docs: Record<string, string[]>;
  used_doc_numbers: string[];
}

let cached: SeedState | null = null;

export async function getSeedState(): Promise<SeedState> {
  if (cached) return cached;
  const r = await apiClient.get("/e2e/seed-state");
  cached = r.data as SeedState;
  return cached;
}

export async function accountPassword(username: string): Promise<string> {
  // Read from seed-state (single source of truth) — never hardcode.
  const s = await getSeedState();
  const acct = s.accounts.find(a => a.username === username);
  if (!acct) throw new Error(`[e2e] no seed account for ${username}`);
  return acct.password;
}
