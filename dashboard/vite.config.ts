import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The e2e mode points at the end-to-end tests' backend, which uses a scripted model.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    proxy: {
      "/api":
        mode === "e2e" ? "http://127.0.0.1:8001" : "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    coverage: {
      include: ["src/**"],
      exclude: ["src/main.tsx"],
      thresholds: { statements: 80 },
    },
  },
}));
