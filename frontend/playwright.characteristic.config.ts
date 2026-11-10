import { defineConfig, devices } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

// Opt-in configuration: never invokes shared global setup/teardown or reset.
if (!process.env.CHARACTERISTIC_PYTHON) throw new Error('Explicit installed test Python required for read-only outbox metadata assertion');
const tag = process.env.CHARACTERISTIC_RUN_TAG;
if (!tag || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(tag)) throw new Error('Fresh safe invocation tag required');
if (!process.env.CHARACTERISTIC_WORKER_PID) throw new Error('Explicit owned worker PID required');
const database = process.env.DATABASE_URL;
if (!database || process.env.TEST_DATABASE_URL !== database) throw new Error('Explicit identical owned DB URLs required');
const db = new URL(database.replace('postgresql+asyncpg:', 'postgresql:'));
if (db.hostname !== '127.0.0.1' || !['55432', '55433'].includes(db.port) || db.pathname !== '/qms_test' || db.search || db.hash) throw new Error('Only owned qms_test is authorized');
// The new integration endpoint also needs main's registered Docker identity.
execFileSync(process.env.CHARACTERISTIC_PYTHON!, ['-c', 'import os; from tests.e2e.characteristic_bootstrap import require_owned_database; require_owned_database(os.environ)'], { cwd: resolve('../backend'), stdio: 'pipe' });
const baseURL = process.env.CHARACTERISTIC_UI_URL;
const apiURL = process.env.CHARACTERISTIC_API_URL;
for (const value of [baseURL, apiURL]) {
  if (!value) throw new Error('Explicit owned loopback UI/API URLs required');
  const url = new URL(value);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || Number(url.port) < 1024) throw new Error('Loopback high ports required');
}
export default defineConfig({
  testDir: './e2e/specs',
  testMatch: '**/characteristic-correction.spec.ts',
  fullyParallel: false, workers: 1, retries: 0, forbidOnly: true,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  reporter: 'list',
  outputDir: `./test-results/characteristic-correction-${tag}`,
  use: { baseURL, locale: 'zh-CN', actionTimeout: 10_000, viewport: { width: 1600, height: 1000 }, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [{ name: 'owned-chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1600, height: 1000 } } }],
});
