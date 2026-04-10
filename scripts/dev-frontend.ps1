$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:VITE_BOTIK_APP_SERVICE_URL = "http://127.0.0.1:8765"
if (-not $env:VITE_BOTIK_SESSION_TOKEN) {
  $env:VITE_BOTIK_SESSION_TOKEN = "botik-dev-token"
}
corepack pnpm --dir "$repoRoot\frontend" dev --host 127.0.0.1 --port 4173
