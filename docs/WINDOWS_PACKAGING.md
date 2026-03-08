# Windows Packaging (EXE + Installer)

## What is built

- `dist\botik.exe` - single-file GUI executable (PyInstaller, `console=False`).
- `dist\installer\BotikInstaller.exe` - Inno Setup installer with shortcuts and optional autostart.

## Entrypoints

- GUI default: `botik.exe`
- Headless mode (optional): `botik.exe --nogui --config config.yaml`

Main launcher for packaged build: `src/botik/windows_entry.py`.

## Build locally

```bat
build_windows_installer.bat
```

Portable build without installer (run from project folder):

```bat
build_portable_exe.bat
run_windows_gui.bat
```

`build_portable_exe.bat` copies `dist\botik.exe` to project root as `botik.exe`.

Script logs are written to `logs\script_logs\`:

- `run_windows_gui_*.log`
- `build_portable_exe_*.log`
- `build_windows_installer_*.log`

Manual equivalent:

```bat
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean botik.spec
iscc installer.iss
```

## Installer behavior

- Installs to `Program Files\Botik`
- Creates Start Menu shortcut for GUI mode
- Optional desktop shortcut
- Optional Windows autostart entry
- Copies `version.txt` into install directory for runtime version tracking

## Runtime/logs

- GUI runs without console (`pythonw` semantics via windowed executable).
- GUI event log is written to `logs\gui.log`.
- Core bot logs are written by existing logging config (default `logs\botik.log`).

## Update behavior

- In source/git mode, Telegram `/update` uses git and updates `version.txt`.
- In installer mode (no `.git`), `/update` returns `repo_unavailable` and reports current `version.txt`.
  - Upgrade path in installer mode is: install newer `BotikInstaller.exe`.

## Notes

- Keep `version.txt` in repo and update it in CI/build step before packaging.
- If code-signing certificate is available, sign `dist\botik.exe` and installer artifact post-build.
