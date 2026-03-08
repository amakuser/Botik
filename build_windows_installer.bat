@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/3] Installing packaging dependencies...
"%PY%" -m pip install --upgrade pyinstaller
if errorlevel 1 exit /b 1

echo [2/3] Building one-file executable...
"%PY%" -m PyInstaller --noconfirm --clean botik.spec
if errorlevel 1 exit /b 1

echo [3/3] Building installer (Inno Setup)...
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles%\Inno Setup 6\ISCC.exe" installer.iss
) else (
  echo Inno Setup Compiler (ISCC.exe) not found. Install Inno Setup 6.
  exit /b 1
)
if errorlevel 1 exit /b 1

echo Build complete.
echo EXE: dist\botik.exe
echo Installer: dist\installer\BotikInstaller.exe

