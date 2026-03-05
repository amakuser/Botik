@echo off
setlocal
cd /d "%~dp0"

rem Prefer GUI interpreter (pythonw) to avoid console-only launch.
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m src.botik.gui.app
  exit /b 0
)

rem Fallback: console python (will keep window open if GUI cannot start).
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

"%PY%" -m src.botik.gui.app
if errorlevel 1 pause
