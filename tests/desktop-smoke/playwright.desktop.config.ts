import { defineConfig } from "@playwright/test";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "..", "..");

export default defineConfig({
  testDir: __dirname,
  outputDir: path.join(repoRoot, ".artifacts", "local", "latest", "desktop-smoke", "test-results"),
  reporter: [["html", { outputFolder: path.join(repoRoot, ".artifacts", "local", "latest", "desktop-smoke", "html-report") }]],
  use: {
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
});
