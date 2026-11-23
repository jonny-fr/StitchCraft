import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8765;
const WEB_PORT = 5199;
// fresh cache per run, so previews are computed (and report progress) instead of served from disk
const CACHE = join(tmpdir(), "stitchcraft-e2e-cache");

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  snapshotPathTemplate: "{testDir}/__screenshots__/{testFilePath}/{arg}-{projectName}-{platform}{ext}",
  workers: 1,
  fullyParallel: false,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    viewport: { width: 1280, height: 800 },
    locale: "de-DE",
    colorScheme: "light",
    launchOptions: { args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } }],
  webServer: [
    {
      command: `rm -rf "${CACHE}" && STITCHCRAFT_CACHE="${CACHE}" uv run uvicorn stitchcraft_api.app:app --port ${API_PORT}`,
      cwd: "..",
      url: `http://localhost:${API_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `STITCHCRAFT_API=http://localhost:${API_PORT} pnpm exec vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
