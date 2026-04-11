# Legacy Quarantine

This document defines the temporary fallback-only posture of the legacy pywebview and PyInstaller path after the primary product cutover.

## Core rule

The new Tauri desktop shell is now the default GUI/product path.
The legacy launcher and packaging assets remain in the repository only for:

- rollback;
- fallback troubleshooting;
- temporary compatibility during the retirement window.

They are not part of the primary operator workflow anymore.

## Quarantined fallback assets

The following assets remain physically present during quarantine:

- `src/botik/windows_entry.py`
- `run_windows_gui.bat`
- `build_portable_exe.bat`
- `build_windows_installer.bat`
- `installer.iss`
- `botik.spec`
- `botik.exe`

## Operator guidance

Use the primary path by default:

- source/dev primary GUI: `pwsh ./scripts/run-primary-desktop.ps1`
- packaged primary GUI: Tauri desktop shell build from `apps/desktop`

Use the legacy path only if rollback or fallback troubleshooting is explicitly required:

- source/dev fallback GUI: `python -m src.botik.gui.app`
- packaged fallback GUI: `botik.exe`
- fallback helper: `run_windows_gui.bat`

## What quarantine does not do

- it does not delete legacy assets;
- it does not rewrite legacy runtime internals;
- it does not restore legacy as the default path;
- it does not remove rollback capability.

## Next phase

Legacy Retirement may remove or archive these assets only after:

- the primary path remains stable on `master`;
- verification stays green;
- rollback-critical assets are proven unnecessary.
