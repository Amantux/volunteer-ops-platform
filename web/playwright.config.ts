import { defineConfig, devices } from '@playwright/test';

/**
 * E2E config. Starts a production build via `next start` on port 3000.
 *
 * NOTE: these specs assume the FastAPI backend is reachable at
 * http://localhost:8000 (the next.config.js rewrite proxies /api/* to it) and
 * that it has at least one open, public session seeded. Run the backend first,
 * e.g. `cd ../backend && uvicorn app.main:app` plus its seed step.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run start',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
