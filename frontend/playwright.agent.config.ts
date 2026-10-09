import { defineConfig, devices } from '@playwright/test';

// Owned pytest fixture supplies allocated Vite/backend ports. No shared global
// setup/teardown, e2e reset endpoint, Docker lifecycle or conventional 5174 port.
export default defineConfig({
  testDir: './e2e/specs',
  testMatch: ['**/agent/readonly-sidebar.spec.ts', '**/agent/local-trial.spec.ts', '**/capa/d4-text-preview.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120000,
  reporter: 'list',
  outputDir: process.env.AGENT_BROWSER_ARTIFACTS,
  use: {
    baseURL: process.env.AGENT_BROWSER_URL,
    screenshot: 'only-on-failure',
    trace: 'off',
  },
  projects: [{
    name: 'owned-chromium',
    use: { ...devices['Desktop Chrome'], launchOptions: {
      executablePath: process.env.OPENQMS_AGENT_BROWSER_EXECUTABLE || '/Users/sam/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
    } },
  }],
});
