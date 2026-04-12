# Legacy Retirement

This document records the point where the old pywebview and PyInstaller fallback path stopped being a supported operator or packaging path.

## Retired in this phase

The following legacy-facing assets were removed because the primary Tauri shell path is now stable, documented, packaged, and verified:

- `run_windows_gui.bat`
- `build_portable_exe.bat`
- `build_windows_installer.bat`
- `installer.iss`
- `botik.spec`
- the PyInstaller/Inno-based packaging flow in `.github/workflows/windows-package.yml`

These assets were safe to retire because:

- the Tauri desktop shell is already the default GUI/product path;
- `corepack pnpm --dir ./apps/desktop build` is green on `master`;
- the migrated product surfaces are already verified through the primary shell path;
- keeping two supported packaging paths was creating operator and maintenance confusion.

## What still remains

Some legacy code remains in the repository, but it is no longer a supported operator or packaging path:

- `src/botik/windows_entry.py`
- `src/botik/gui/webview_app.py`
- `dashboard_template.html`
- `dashboard_preview.html`
- legacy internal tests and compatibility code that still reference these modules

These remain only because they are still part of controlled compatibility/test cleanup. They are not the current product path.

## Rollback model after retirement

Rollback no longer means launching a supported legacy GUI fallback.

If the retirement phase needs to be reversed, rollback should happen through git history:

- revert the retirement PR; or
- check out a pre-retirement commit or tag for investigation.

The supported desktop path on current `master` remains the Tauri shell.
