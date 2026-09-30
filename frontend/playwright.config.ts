import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 10000 },
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5173",
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    channel:
      process.env.E2E_BROWSER_CHANNEL ||
      (process.platform === "darwin" ? "chrome" : undefined),
  },
  reporter: [["list"], ["html", { open: "never" }]],
});
