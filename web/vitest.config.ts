import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.mjs"],
    // Forks pool can hang indefinitely on GitHub-hosted runners with jsdom.
    pool: "threads",
    maxWorkers: 2,
    testTimeout: 15_000,
    hookTimeout: 15_000,
    teardownTimeout: 5_000,
  },
});
