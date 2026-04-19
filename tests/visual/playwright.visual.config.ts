import { defineConfig } from "@playwright/test";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "..", "..");

export default defineConfig({
  testDir: __dirname,
  snapshotDir: path.join(__dirname, "baselines"),
  snapshotPathTemplate: "{snapshotDir}/{arg}{-projectName}{ext}",
  workers: 1,
  outputDir: path.join(repoRoot, ".artifacts", "local", "latest", "visual", "test-results"),
  reporter: [
    ["html", { outputFolder: path.join(repoRoot, ".artifacts", "local", "latest", "visual", "html-report") }],
  ],
  use: {
    baseURL: "http://127.0.0.1:4173",
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    viewport: { width: 1280, height: 800 },
    launchOptions: {
      headless: true,
      args: ["--no-proxy-server"],
    },
  },
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.05,
      threshold: 0.2,
      animations: "disabled",
    },
  },
});
