@echo off
setlocal
cd /d "%~dp0"

set "LOG_DIR=%CD%\logs\script_logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
if not defined TS set "TS=%RANDOM%"
set "LOG_FILE=%LOG_DIR%\build_windows_installer_%TS%.log"
(
  echo [INFO] ===== build_windows_installer.bat =====
  echo [INFO] Started: %DATE% %TIME%
  echo [INFO] Workdir: %CD%
)>"%LOG_FILE%"
echo [botik] Installer build log: "%LOG_FILE%"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo [INFO] Python command: %PY%>>"%LOG_FILE%"

echo [1/3] Installing packaging dependencies...
"%PY%" -m pip install --upgrade pyinstaller >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERROR] pip install failed. See "%LOG_FILE%"
  exit /b 1
)

echo [2/3] Building one-file executable...
"%PY%" -m PyInstaller --noconfirm --clean botik.spec >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed. See "%LOG_FILE%"
  exit /b 1
)

echo [3/3] Building installer (Inno Setup)...
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss >>"%LOG_FILE%" 2>&1
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles%\Inno Setup 6\ISCC.exe" installer.iss >>"%LOG_FILE%" 2>&1
) else (
  echo [ERROR] Inno Setup Compiler (ISCC.exe) not found.>>"%LOG_FILE%"
  echo Inno Setup Compiler (ISCC.exe) not found. Install Inno Setup 6.
  exit /b 1
)
if errorlevel 1 (
  echo [ERROR] Inno Setup build failed. See "%LOG_FILE%"
  exit /b 1
)

echo Build complete.
echo EXE: dist\botik.exe
echo Installer: dist\installer\BotikInstaller.exe
echo [INFO] Finished OK>>"%LOG_FILE%"
