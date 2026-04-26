# Legacy Retirement

This document records the point where the old pywebview and PyInstaller fallback path stopped being a supported operator or packaging path.

## Retired in earlier phase

The following legacy-facing assets were removed because the primary Tauri shell path is now stable, documented, packaged, and verified:

- `run_windows_gui.bat`
- `build_portable_exe.bat`
- `build_windows_installer.bat`
- `installer.iss`
- the PyInstaller/Inno-based packaging flow in `.github/workflows/windows-package.yml`

These assets were safe to retire because:

- the Tauri desktop shell is already the default GUI/product path;
- `corepack pnpm --dir ./apps/desktop build` is green on `master`;
- the migrated product surfaces are already verified through the primary shell path;
- keeping two supported packaging paths was creating operator and maintenance confusion.

## M1 Cleanup — 2026-04-26 (this phase)

Following 2026-04-26 user decisions (Windows/Tauri-first, no parallel stacks), the following were moved to external backup `C:/ai/aiBotik_legacy_backup_2026-04-26/` and removed from the active repo:

**Legacy Stack A (Python root entry stack, superseded by `src/botik/*`):**
- `main.py` (root)
- `core/` directory (7 files)
- `strategies/` directory (3 files)
- `tests/test_strategy.py` (only consumer of `/strategies`)

**PyInstaller packaging path (replaced by Tauri):**
- `botik.spec`
- `scripts/build-exe.ps1`
- `scripts/build_botik.bat`
- `botik.exe` (root, 8.8 MB)
- `botik_desktop.exe` (root, 8.8 MB)
- `package.json` "build:exe" script entry

**Retired SPA manifests** (already-deleted `dashboard_template.html` / `dashboard_preview.html` left these bookkeeping files behind):
- `dashboard_release_manifest.yaml`
- `dashboard_workspace_manifest.yaml`

**Debug artifacts:**
- `NULL` (0-byte file in repo root, untracked)

External backup includes `MOVED_FILES.md` with per-file evidence and rollback instructions.

## What still remains in legacy form

- `src/botik/windows_entry.py` — controlled compat-only
- `src/botik/gui/webview_app.py` — controlled compat-only
- legacy internal tests and compatibility code that still reference these modules

These remain only because they are still part of controlled compatibility/test cleanup. They are not the current product path.

`dashboard_template.html` and `dashboard_preview.html` were already physically gone from the repo before the M1 cleanup; their manifest files were the leftover bookkeeping that this phase removed.

## Rollback model after retirement

Rollback no longer means launching a supported legacy GUI fallback.

If the retirement phase needs to be reversed, rollback should happen through git history:

- revert the retirement PR; or
- check out a pre-retirement commit or tag for investigation.

The supported desktop path on current `master` remains the Tauri shell.
