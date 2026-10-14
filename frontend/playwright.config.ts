import { defineConfig } from '@playwright/test';

const hosted = process.env.E2E_BASE_URL;
export default defineConfig({
  testDir: './e2e',
  timeout: 45000,
  expect: { timeout: 10000 },
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  use: { baseURL: hosted || 'http://127.0.0.1:5117', viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: hosted ? undefined : { command: 'node e2e-server.mjs', url: 'http://127.0.0.1:5117/health/ready',
    timeout: 30000, reuseExistingServer: false },
});
