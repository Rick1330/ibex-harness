import { defineConfig, devices } from "@playwright/test"

const baseURL = "http://127.0.0.1:3280"

export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["live-d1.spec.ts"],
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command:
      "CONSOLE_DATA_MODE=preview CONSOLE_PREVIEW=1 NEXT_PUBLIC_CONSOLE_PREVIEW=1 pnpm exec next dev --hostname 127.0.0.1 --port 3280",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
