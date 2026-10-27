import { defineConfig } from "@playwright/test";

// Phone-sized browser against a local API with fake providers (scripts/e2e_api.py).
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    viewport: { width: 360, height: 800 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    permissions: ["camera", "microphone"],
    launchOptions: {
      args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
  },
  webServer: [
    {
      command: "uv run python scripts/e2e_api.py",
      cwd: "..",
      url: "http://localhost:8000/api/v1/health",
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: "npx vite --port 5173 --strictPort",
      url: "http://localhost:5173",
      env: { VITE_API_BASE_URL: "http://localhost:8000" },
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});
