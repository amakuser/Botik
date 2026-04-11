$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:BOTIK_REPO_ROOT = $repoRoot

if (-not $env:BOTIK_ARTIFACTS_DIR) {
  $env:BOTIK_ARTIFACTS_DIR = "$repoRoot\.artifacts\local\latest\desktop-primary"
}
if (-not $env:BOTIK_FRONTEND_URL) {
  $env:BOTIK_FRONTEND_URL = "http://127.0.0.1:4173"
}
if (-not $env:BOTIK_SESSION_TOKEN) {
  $env:BOTIK_SESSION_TOKEN = "botik-dev-token"
}

function Test-HttpReady([string]$url) {
  $script = @"
import sys, urllib.request
req = urllib.request.Request('$url')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(req, timeout=2) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
"@
  $script | python -
  return $LASTEXITCODE -eq 0
}

function Wait-HttpReady([string]$url, [int]$timeoutSec = 45) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    if (Test-HttpReady $url) {
      return
    }
    Start-Sleep -Milliseconds 250
  }
  throw "Timed out waiting for $url"
}

$pwshCommand = Get-Command pwsh -ErrorAction SilentlyContinue
if ($pwshCommand) {
  $shellExe = $pwshCommand.Source
}
else {
  $shellExe = (Get-Command powershell -ErrorAction Stop).Source
}

$frontendStartedByScript = $false
$frontendProcess = $null
$frontendUrl = $env:BOTIK_FRONTEND_URL

if (-not (Test-HttpReady $frontendUrl)) {
  $frontendProcess = Start-Process -FilePath $shellExe -ArgumentList "-File", (Join-Path $repoRoot "scripts\dev-frontend.ps1") -PassThru -WindowStyle Hidden
  $frontendStartedByScript = $true
  Wait-HttpReady $frontendUrl
}

try {
  & (Join-Path $repoRoot "scripts\dev-desktop.ps1")
}
finally {
  if ($frontendStartedByScript -and $null -ne $frontendProcess) {
    try {
      $frontendProcess.Refresh()
      if (-not $frontendProcess.HasExited) {
        cmd /c "taskkill /PID $($frontendProcess.Id) /T /F >nul 2>nul" | Out-Null
      }
    }
    catch {
    }
  }
}
