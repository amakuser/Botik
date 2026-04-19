import { defineConfig } from "@playwright/test";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "..", "..");

export default defineConfig({
  testDir: __dirname,
  workers: 1,
  outputDir: path.join(repoRoot, ".artifacts", "local", "latest", "vision", "test-results"),
  reporter: [
    ["list"],
    ["html", { outputFolder: path.join(repoRoot, ".artifacts", "local", "latest", "vision", "html-report"), open: "never" }],
  ],
  use: {
    viewport: { width: 1280, height: 800 },
    launchOptions: {
      headless: true,
      args: ["--no-proxy-server"],
    },
  },
});
