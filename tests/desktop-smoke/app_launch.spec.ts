import fs from "node:fs";
import path from "node:path";
import { expect, test } from "./fixtures";

test("desktop shell scaffold exists and is host-only", async () => {
  const repoRoot = path.resolve(__dirname, "..", "..");
  const cargoToml = path.join(repoRoot, "apps", "desktop", "src-tauri", "Cargo.toml");
  const mainRs = path.join(repoRoot, "apps", "desktop", "src-tauri", "src", "main.rs");
  const hostApi = path.join(repoRoot, "apps", "desktop", "src-tauri", "src", "host_api.rs");

  expect(fs.existsSync(cargoToml)).toBeTruthy();
  expect(fs.existsSync(mainRs)).toBeTruthy();
  expect(fs.existsSync(hostApi)).toBeTruthy();

  const rustMain = fs.readFileSync(mainRs, "utf-8");
  expect(rustMain).toContain("get_runtime_config");
  expect(rustMain).not.toContain("training");
  expect(rustMain).not.toContain("backfill");
});
