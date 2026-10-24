import { defineConfig } from "@playwright/test";

// The tests run on their own servers, with a fresh database and a scripted
// model, so they never touch the dev servers or call a real model.
export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/test-results",
  reporter: "list",
  use: { baseURL: "http://localhost:5174" },
  webServer: [
    {
      command: "uv run -m agent.tests.e2e_server",
      url: "http://127.0.0.1:8001/api/health",
      reuseExistingServer: false,
    },
    {
      command: "npx vite dashboard --mode e2e --port 5174 --strictPort",
      url: "http://localhost:5174",
      reuseExistingServer: false,
    },
  ],
});
