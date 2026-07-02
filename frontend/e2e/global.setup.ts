import { existsSync, mkdirSync, writeFileSync } from "fs";
import path from "path";
import { chromium } from "@playwright/test";
import { apiClient } from "./helpers/api-client";
import { getSeedState, accountPassword } from "./fixtures/seed-state";

// frontend package.json is "type":"module" — __dirname is undefined under ESM. Playwright
// runs with cwd = frontend/ (make e2e-run cd's there), so resolve relative to process.cwd().
const STORAGE_DIR = path.resolve(process.cwd(), "e2e/.storage-state");

const ROLES = ["admin", "engineer", "manager", "viewer", "groupadmin"];

export default async function globalSetup() {
  mkdirSync(STORAGE_DIR, { recursive: true });

  // 1. Credential detection + alert.
  const hasLLM = !!(process.env.LLM_PROVIDER && process.env.LLM_API_KEY);
  if (!hasLLM) {
    // eslint-disable-next-line no-console
    console.warn(
      "\n⚠️  LLM_PROVIDER/LLM_API_KEY not configured → AI specs will be skipped.\n" +
      "   Fill .env.e2e to enable them.\n"
    );
  }
  writeFileSync(
    path.join(STORAGE_DIR, "e2e-env.json"),
    JSON.stringify({ hasLLM, ts: "fixed" })
  );

  // 2. Seed-state presence check.
  try {
    await getSeedState();
  } catch (e) {
    throw new Error(`[e2e] seed-state unreachable: is the e2e stack up and seeded? (${String(e)})`);
  }

  // 3. UI login per role → storageState.
  const browser = await chromium.launch();
  for (const username of ROLES) {
    const password = await accountPassword(username);
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto("http://localhost:5174/login");
    await page.waitForLoadState("networkidle");
    await page.getByPlaceholder(/用户名|username/i).fill(username);
    await page.getByPlaceholder(/密码|password/i).fill(password);
    await page.getByRole("button", { name: /登\s*录|login/i }).click();
    await page.waitForURL(/\/dashboard|\/capa|\/fmea/);
    await ctx.storageState({ path: path.join(STORAGE_DIR, `${username}.json`) });
    await ctx.close();
  }
  await browser.close();
  // silence unused import warning for apiClient
  void apiClient;
}
