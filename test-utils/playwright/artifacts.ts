import fs from "node:fs";
import path from "node:path";

export function ensureArtifactsDir(repoRoot: string, relativeDir: string): string {
  const full = path.join(repoRoot, ".artifacts", relativeDir);
  fs.mkdirSync(full, { recursive: true });
  return full;
}
