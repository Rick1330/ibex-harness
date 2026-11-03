import { defineConfig, devices } from '@playwright/test'

const baseURL = 'http://127.0.0.1:3282'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    // Serve the deployed artifact (.output/public) the way Cloudflare Pages
    // does — the Nitro server can answer requests the static deployment
    // cannot, which would let tests pass against behavior that never ships.
    command: 'HOST=127.0.0.1 PORT=3282 node scripts/serve-static.mjs',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
