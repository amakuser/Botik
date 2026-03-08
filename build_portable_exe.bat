@echo off
setlocal
cd /d "%~dp0"

set "LOG_DIR=%CD%\logs\script_logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
if not defined TS set "TS=%RANDOM%"
set "LOG_FILE=%LOG_DIR%\build_portable_exe_%TS%.log"
(
  echo [INFO] ===== build_portable_exe.bat =====
  echo [INFO] Started: %DATE% %TIME%
  echo [INFO] Workdir: %CD%
)>"%LOG_FILE%"
echo [botik] Build log: "%LOG_FILE%"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo [INFO] Python command: %PY%>>"%LOG_FILE%"

echo [1/4] Installing/upgrading PyInstaller...
"%PY%" -m pip install --upgrade pyinstaller >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERROR] pip install failed. See "%LOG_FILE%"
  exit /b 1
)

echo [2/4] Writing version.txt from current git commit...
for /f "delims=" %%i in ('git rev-parse HEAD 2^>^&1') do set "BOTIK_COMMIT=%%i"
if not "%BOTIK_COMMIT%"=="" (
  >version.txt echo %BOTIK_COMMIT%
  echo [INFO] version.txt updated: %BOTIK_COMMIT%>>"%LOG_FILE%"
  echo [INFO] version.txt updated: %BOTIK_COMMIT%
)
if "%BOTIK_COMMIT%"=="" (
  echo [WARN] git rev-parse HEAD returned empty.>>"%LOG_FILE%"
)

echo [3/4] Building one-file EXE...
"%PY%" -m PyInstaller --noconfirm --clean botik.spec >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed. See "%LOG_FILE%"
  exit /b 1
)

echo [4/4] Copying EXE to project root...
copy /Y "dist\botik.exe" "botik.exe" >nul
if errorlevel 1 (
  echo [ERROR] Failed to copy dist\botik.exe to botik.exe.>>"%LOG_FILE%"
  echo [ERROR] Copy step failed. See "%LOG_FILE%"
  exit /b 1
)
echo [INFO] Copied dist\botik.exe -> botik.exe>>"%LOG_FILE%"

echo Portable build ready: "%CD%\botik.exe"
echo Run: run_windows_gui.bat
echo [INFO] Finished OK>>"%LOG_FILE%"
