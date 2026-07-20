import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const repositoryRoot = resolve(__dirname, "../..");

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  outputDir: resolve(repositoryRoot, "artifacts/gate3/e2e-output"),
  reporter: [
    ["line"],
    ["html", { outputFolder: resolve(repositoryRoot, "artifacts/gate3/latest/ui-e2e-report"), open: "never" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    cwd: __dirname,
    env: { PHOTOFOLD_REPOSITORY_ROOT: repositoryRoot },
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
