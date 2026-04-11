@echo off
setlocal
cd /d "%~dp0"

set "LOG_DIR=%CD%\logs\script_logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
if not defined TS set "TS=%RANDOM%"
set "LOG_FILE=%LOG_DIR%\build_%TS%.log"
echo [botik] Build log: "%LOG_FILE%"
echo [botik] Building LEGACY FALLBACK portable EXE. Primary desktop path is pwsh ./scripts/run-primary-desktop.ps1
(
  echo ===== build_portable_exe.bat =====
  echo Started: %DATE% %TIME%
  echo Workdir: %CD%
)>"%LOG_FILE%"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

:: ── [1/4] Bump version ───────────────────────────────────────────────────
echo [1/4] Bumping version for legacy fallback build...
"%PY%" tools\bump_version.py
if errorlevel 1 (
  echo [WARN] Could not bump version, continuing.
)
type VERSION

:: ── [2/4] Write git SHA ──────────────────────────────────────────────────
echo [2/4] Writing version.txt...
for /f "delims=" %%i in ('git rev-parse HEAD 2^>^&1') do set "SHA=%%i"
if not "%SHA%"=="" (>version.txt echo %SHA% & echo [INFO] SHA: %SHA%)

:: ── [3/4] Kill old process, build EXE directly into project root ─────────
echo [3/4] Building legacy fallback EXE (low priority, no lag)...
powershell -NoProfile -Command "Stop-Process -Name botik -Force -ErrorAction SilentlyContinue" >nul 2>&1
start "" /low /wait "%PY%" -m PyInstaller --noconfirm --clean --distpath . botik.spec
if not exist "botik.exe" (
  echo [ERROR] Build failed - botik.exe not found. See: "%LOG_FILE%"
  exit /b 1
)

:: ── [4/4] Done ───────────────────────────────────────────────────────────
echo.
for /f "delims=" %%v in ('type VERSION') do set "VER=%%v"
echo ======================================
echo  Ready legacy fallback EXE: %CD%\botik.exe
echo  %VER%
echo  Primary GUI: pwsh ./scripts/run-primary-desktop.ps1
echo  Legacy fallback launch: run_windows_gui.bat
echo ======================================
echo Finished OK>>"%LOG_FILE%"
