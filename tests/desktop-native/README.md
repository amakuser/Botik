# Desktop-Native Tests

Real-process desktop smoke for the Tauri shell. No browser, no Playwright DOM —
launches the actual packaged exe, asserts the OS window appears, captures
evidence, then tears down.

## Status (2026-04-26)

- **Smoke lane (`run-automated-smoke.ps1`):** restored in minimal form, retargeted
  to the official Tauri build output `apps/desktop/src-tauri/target/release/botik_desktop.exe`.
  This replaces the retired root-level `botik_desktop.exe` (PyInstaller).
- **Interactive framework (`interactive/`):** previously held a Playwright-via-CDP
  attach harness with reconcile/verify/evidence primitives and 3 scenarios
  (non-intrusive-sentinel, scroll-architecture-audit, settings-test-connection).
  This was lost in the M1 cleanup of 2026-04-26 (was untracked, not backed up
  before `rm -rf`). **Pending reconstruction or restoration from any operator-side backup.**

## Target

```
apps/desktop/src-tauri/target/release/botik_desktop.exe
```

The exe is produced by:
```
corepack pnpm --dir ./apps/desktop build
```

## Run

```
pwsh ./tests/desktop-native/run-automated-smoke.ps1
```

Exit code:
- `0` — exe launched, HWND found, window visible, clean teardown
- `1` — launch failure / no HWND within timeout / process died early

Artifacts:
- `.artifacts/local/latest/desktop-native/automated/window-rect.png` — full-screen capture
- `.artifacts/local/latest/desktop-native/automated/run.log` — text log

## What this lane proves

- The Tauri exe binary is launchable
- A top-level window with the expected title appears within the timeout
- The process does not crash within the smoke window
- The OS chrome (titlebar + frame) is rendered

## What this lane does NOT prove

- DOM contents inside the WebView2 (use `tests/desktop-smoke/` for that, browser-only)
- App-service sidecar lifecycle correctness (use unit + integration tests)
- Multi-step user flows (would require the lost interactive framework)

## Rebuilding the interactive framework (out of scope right now)

If/when the interactive framework needs to come back, it should:
- Spawn the Tauri exe via `Start-Process` and capture PID
- Attach Playwright via Chrome DevTools Protocol on the WebView2 debug port
  (Tauri exposes this via `--remote-debugging-port` if configured in `tauri.conf.json`)
- Provide reusable `harness.launch()` / `harness.detach()` lifecycle helpers
- Provide action / detect / evidence / reconcile / verify primitive modules
- Live in `tests/desktop-native/interactive/` with its own `playwright.interactive.config.ts`

The original implementation is in external backup neither in git nor in
`C:/ai/aiBotik_legacy_backup_2026-04-26/` — would need to be written fresh
or recovered from operator-side backup if any exists (OneDrive history,
external drives, IDE local history outside the project).
