import { defineConfig } from "@playwright/test";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "..", "..");

export default defineConfig({
  testDir: __dirname,
  workers: 1,
  outputDir: path.join(repoRoot, ".artifacts", "local", "latest", "e2e", "test-results"),
  reporter: [["html", { outputFolder: path.join(repoRoot, ".artifacts", "local", "latest", "e2e", "html-report") }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    launchOptions: {
      headless: true,
      args: ["--no-proxy-server"],
    },
  },
});
