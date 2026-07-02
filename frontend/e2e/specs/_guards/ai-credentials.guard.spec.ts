import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import path from "path";

test("AI credentials configured (smoke) or skip with warning", async () => {
  // ESM: no __dirname / require. cwd = frontend/ when Playwright runs.
  const envPath = path.resolve(process.cwd(), "e2e/.storage-state/e2e-env.json");
  const env = JSON.parse(readFileSync(envPath, "utf-8"));
  if (!env.hasLLM) {
    test.skip(true, "LLM_PROVIDER/LLM_API_KEY not configured — AI specs skipped");
  }
  // If configured: hit the recommendation smoke path via API (structure-only).
  // The real AI specs in m1-core assert behavior; here we only guard.
  expect(env.hasLLM).toBe(true);
});
