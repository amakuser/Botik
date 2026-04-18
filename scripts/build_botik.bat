@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

:: Try pwsh first, fall back to powershell
where pwsh >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "SHELL=pwsh"
) else (
    set "SHELL=powershell"
)

%SHELL% -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\build-exe.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo BUILD FAILED - see output above
    pause
    exit /b 1
)
endlocal
