$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:PYTHONPATH = "$repoRoot\app-service\src;$repoRoot"
$env:BOTIK_APP_SERVICE_HOST = "127.0.0.1"
$env:BOTIK_APP_SERVICE_PORT = "8765"
if (-not $env:BOTIK_SESSION_TOKEN) {
  $env:BOTIK_SESSION_TOKEN = "botik-dev-token"
}
python -m uvicorn botik_app_service.main:app --host 127.0.0.1 --port 8765 --app-dir "$repoRoot\app-service\src"
