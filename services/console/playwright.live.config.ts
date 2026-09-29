import { defineConfig, devices } from "@playwright/test"

const baseURL = "https://127.0.0.1:3282"

export default defineConfig({
  testDir: "./e2e",
  testMatch: "live-d1.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    ignoreHTTPSErrors: true,
    trace: "on",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "node e2e/live-stack.mjs",
    url: baseURL,
    ignoreHTTPSErrors: true,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
