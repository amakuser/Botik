# Windows Packaging (EXE + Installer)

## What is built

- Primary GUI/product path: Tauri desktop shell from `apps/desktop`.
- Temporary legacy fallback path: PyInstaller-based `botik.exe` and installer flow remain available until later retirement.

## Entrypoints

- Source/dev primary GUI: `pwsh ./scripts/run-primary-desktop.ps1`
- Source/dev shell-only: `pwsh ./scripts/dev-desktop.ps1`
- Packaged primary GUI: `corepack pnpm --dir ./apps/desktop build`
- Legacy fallback GUI: `botik.exe` or `run_windows_gui.bat`
- Legacy fallback headless trading: `botik.exe --nogui --role trading --config config.yaml`
- Legacy fallback headless ML: `botik.exe --nogui --role ml --config config.yaml --ml-mode online`

Temporary legacy packaged launcher: `src/botik/windows_entry.py`.

Важно:
- primary GUI cutover does not remove the legacy launcher yet;
- rollback remains possible because the legacy launcher/build path still exists;
- `python -m src.botik.gui.app` and `botik.exe` are fallback-only during this phase.

## Build locally

Primary shell build:

```bat
corepack pnpm --dir apps/desktop build
```

Primary source/dev launch:

```bat
pwsh ./scripts/run-primary-desktop.ps1
```

Legacy fallback build:

```bat
build_windows_installer.bat
```

Portable build without installer (run from project folder):

```bat
build_portable_exe.bat
run_windows_gui.bat
```

`build_portable_exe.bat` copies `dist\botik.exe` to project root as `botik.exe`.
`run_windows_gui.bat` в этом контексте — helper-скрипт для legacy fallback path, а не основной пользовательский запуск.

Script logs are written to `logs\script_logs\`:

- `run_windows_gui_*.log`
- `build_portable_exe_*.log`
- `build_windows_installer_*.log`
- `windows_entry.log` (startup/runtime errors before GUI is fully initialized)

## Installer behavior

- Tauri shell is now the primary GUI packaging target.
- Legacy installer behavior remains documented only as a fallback until the later retirement phase.

## Runtime/logs

- The Tauri desktop shell owns GUI startup and managed app-service lifecycle for the migrated product path.
- Desktop shell artifacts and logs are written under `.artifacts/local/...` in source/dev and test runs.
- Legacy GUI logs remain available only for rollback and fallback troubleshooting.

## Source mode vs packaged mode

- Primary source/dev mode:
  - `pwsh ./scripts/run-primary-desktop.ps1`
  - `pwsh ./scripts/dev-app-service.ps1`
  - `pwsh ./scripts/dev-frontend.ps1`
- Primary packaged mode:
  - `corepack pnpm --dir ./apps/desktop build`
- Legacy fallback mode:
  - `python -m src.botik.gui.app`
  - `botik.exe`
  - `botik.exe --nogui --role trading ...`
  - `botik.exe --nogui --role ml ...`

## Update behavior

- In source/git mode, Telegram `/update` uses git and updates `version.txt`.
- In installer mode (no `.git`), `/update` returns `repo_unavailable` and reports current `version.txt`.
  - Upgrade path in installer mode is: install newer `BotikInstaller.exe`.

## Notes

- Keep rollback possible until the later legacy retirement phase.
- Do not delete `windows_entry.py`, `run_windows_gui.bat`, or legacy packaging assets in the cutover phase.
- If code-signing certificate is available, sign the primary desktop artifact for the Tauri shell and any temporary legacy fallback artifact separately.
