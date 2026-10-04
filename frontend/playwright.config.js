import { defineConfig, devices } from "@playwright/test";

const backendPort = 18111;
const frontendPort = 15174;
const testDatabase = `sqlite:////tmp/steward-ground-zero-e2e-${process.pid}.db`;
const pythonCommand = process.env.E2E_PYTHON || "../.venv/bin/python";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${pythonCommand} -m uvicorn app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${backendPort}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        APP_ENV: "test",
        DATABASE_URL: testDatabase,
        SEED_DEMO_DATA: "true",
        AUTH_MODE: "demo",
        CATALOG_PUBLISHER: "mock",
        TESTGEN_MODE: "mock",
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_BACKEND_URL: `http://127.0.0.1:${backendPort}` },
    },
  ],
});
