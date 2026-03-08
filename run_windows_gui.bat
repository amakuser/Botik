@echo off
setlocal
cd /d "%~dp0"

set "LOG_DIR=%CD%\logs\script_logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
if not defined TS set "TS=%RANDOM%"
set "LOG_FILE=%LOG_DIR%\run_windows_gui_%TS%.log"
(
  echo [INFO] ===== run_windows_gui.bat =====
  echo [INFO] Started: %DATE% %TIME%
  echo [INFO] Workdir: %CD%
)>"%LOG_FILE%"
echo [botik] Launcher log: "%LOG_FILE%"

rem Prefer packaged executable when available.
if exist "botik.exe" (
  echo [INFO] Found portable EXE: botik.exe>>"%LOG_FILE%"
  start "" "botik.exe"
  echo [INFO] start botik.exe exit=%ERRORLEVEL%>>"%LOG_FILE%"
  exit /b 0
)

if exist "dist\botik.exe" (
  echo [INFO] Found packaged EXE: dist\botik.exe>>"%LOG_FILE%"
  start "" "dist\botik.exe"
  echo [INFO] start dist\botik.exe exit=%ERRORLEVEL%>>"%LOG_FILE%"
  exit /b 0
)

rem Prefer GUI interpreter (pythonw) to avoid console-only launch.
if exist ".venv\Scripts\pythonw.exe" (
  echo [INFO] Launching via pythonw -m src.botik.windows_entry>>"%LOG_FILE%"
  start "" ".venv\Scripts\pythonw.exe" -m src.botik.windows_entry
  echo [INFO] start pythonw module exit=%ERRORLEVEL%>>"%LOG_FILE%"
  exit /b 0
)

rem Fallback: console python (will keep window open if GUI cannot start).
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo [INFO] Fallback launch command: %PY% -m src.botik.windows_entry>>"%LOG_FILE%"
"%PY%" -m src.botik.windows_entry >>"%LOG_FILE%" 2>&1
set "RC=%ERRORLEVEL%"
echo [INFO] Fallback exit code: %RC%>>"%LOG_FILE%"
if not "%RC%"=="0" (
  echo [ERROR] GUI start failed with exit code %RC%. See "%LOG_FILE%"
)
if errorlevel 1 pause
