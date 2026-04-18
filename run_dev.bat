@echo off
REM Botik dev runner — starts app-service + frontend dev server
REM Open http://localhost:5173 in browser after both windows appear

title Botik Dev

echo Starting app-service on http://127.0.0.1:8765 ...
start "Botik app-service" cmd /k "cd /d %~dp0app-service\src && python -m uvicorn botik_app_service.main:app --host 127.0.0.1 --port 8765 --reload"

echo Starting frontend dev server on http://localhost:5173 ...
start "Botik frontend" cmd /k "cd /d %~dp0frontend && pnpm dev"

timeout /t 3 /nobreak >nul
start http://localhost:5173
