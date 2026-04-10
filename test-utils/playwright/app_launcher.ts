import { ChildProcess, spawn } from "node:child_process";
import path from "node:path";

export interface StartedProcess {
  process: ChildProcess;
  name: string;
}

export function launchPwshScript(repoRoot: string, scriptName: string): StartedProcess {
  const scriptPath = path.join(repoRoot, "scripts", scriptName);
  const child = spawn("pwsh", ["-File", scriptPath], {
    cwd: repoRoot,
    stdio: "pipe",
    windowsHide: true,
  });
  return { process: child, name: scriptName };
}

export async function stopProcess(started: StartedProcess | undefined): Promise<void> {
  if (!started || started.process.killed) {
    return;
  }
  started.process.kill("SIGTERM");
}
