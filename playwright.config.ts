import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8015",
    trace: "retain-on-failure"
  },
  webServer: [
    {
      command: "node scripts/run-test-server.mjs",
      url: "http://127.0.0.1:8015/health",
      reuseExistingServer: false,
      timeout: 30_000
    },
    {
      command: "python -m http.server 4173 --bind 127.0.0.1 --directory apps/extension/dist",
      url: "http://127.0.0.1:4173/sidepanel.html",
      reuseExistingServer: false,
      timeout: 30_000
    }
  ],
  projects: [{ name: "chromium", use: { browserName: "chromium" } }]
});
