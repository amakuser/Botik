$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$artifactsRoot = Join-Path $repoRoot ".artifacts\local\latest\e2e"
$logsDir = Join-Path $artifactsRoot "logs"
$structuredDir = Join-Path $artifactsRoot "structured"
$stateDir = Join-Path $artifactsRoot "state"
$dataBackfillDb = Join-Path $stateDir "data_backfill.sqlite3"
New-Item -ItemType Directory -Force -Path $artifactsRoot, $logsDir, $structuredDir, $stateDir | Out-Null

$serviceOut = Join-Path $logsDir "app-service.stdout.log"
$serviceErr = Join-Path $logsDir "app-service.stderr.log"
$frontendOut = Join-Path $logsDir "frontend.stdout.log"
$frontendErr = Join-Path $logsDir "frontend.stderr.log"
$lifecycleLog = Join-Path $structuredDir "service-events.jsonl"
$cleanupSummary = Join-Path $structuredDir "cleanup-summary.json"
Remove-Item $serviceOut, $serviceErr, $frontendOut, $frontendErr, $lifecycleLog, $cleanupSummary, $dataBackfillDb -ErrorAction SilentlyContinue

function Add-JsonLine([string]$path, [object]$payload) {
  ($payload | ConvertTo-Json -Compress -Depth 8) | Add-Content -LiteralPath $path -Encoding UTF8
}

function Wait-Http200([string]$url, [hashtable]$headers, [int]$timeoutSec = 30) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    $headerLines = ''
    foreach ($kv in $headers.GetEnumerator()) {
      $headerLines += "req.add_header('$($kv.Key)', '$($kv.Value)')`n"
    }
    $script = @"
import sys, urllib.request
req = urllib.request.Request('$url')
$headerLines
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(req, timeout=2) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
"@
    $script | python -
    if ($LASTEXITCODE -eq 0) {
      return
    }
    Start-Sleep -Milliseconds 250
  }
  throw "Timed out waiting for $url"
}

function Get-ListenerCounts() {
  $result = foreach ($port in 4173, 8765) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    [pscustomobject]@{
      port = $port
      listenerCount = $listeners.Count
      owningProcesses = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    }
  }
  return $result
}

foreach ($port in @(4173, 8765)) {
  $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($listener in $listeners) {
    try {
      cmd /c "taskkill /PID $($listener.OwningProcess) /T /F >nul 2>nul" | Out-Null
    }
    catch {
    }
  }
}

$pwshCommand = Get-Command pwsh -ErrorAction SilentlyContinue
if ($pwshCommand) {
  $shellExe = $pwshCommand.Source
}
else {
  $shellExe = (Get-Command powershell -ErrorAction Stop).Source
}

$appService = $null
$frontend = $null
$startedAt = Get-Date
$testsPassed = $false
$env:BOTIK_ARTIFACTS_DIR = $artifactsRoot

try {
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "spawn_requested"
    payload = @{ target = "app-service" }
  }
  $appService = Start-Process -FilePath $shellExe -ArgumentList "-File", (Join-Path $repoRoot "scripts\dev-app-service.ps1") -PassThru -WindowStyle Hidden -RedirectStandardOutput $serviceOut -RedirectStandardError $serviceErr
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "spawned"
    payload = @{ target = "app-service"; pid = $appService.Id }
  }

  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "spawn_requested"
    payload = @{ target = "frontend" }
  }
  $frontend = Start-Process -FilePath $shellExe -ArgumentList "-File", (Join-Path $repoRoot "scripts\dev-frontend.ps1") -PassThru -WindowStyle Hidden -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "spawned"
    payload = @{ target = "frontend"; pid = $frontend.Id }
  }

  Wait-Http200 "http://127.0.0.1:8765/health" @{ "x-botik-session-token" = "botik-dev-token" }
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "ready"
    payload = @{ target = "app-service"; url = "http://127.0.0.1:8765/health" }
  }

  Wait-Http200 "http://127.0.0.1:4173/" @{}
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "ready"
    payload = @{ target = "frontend"; url = "http://127.0.0.1:4173/" }
  }

  corepack pnpm --dir $repoRoot exec playwright test --config "$repoRoot\tests\e2e\playwright.config.ts"
  $testsPassed = $true
}
finally {
  $shutdownRequested = $false
  try {
    Add-JsonLine $lifecycleLog @{
      timestamp = (Get-Date).ToString("o")
      kind = "shutdown_requested"
      payload = @{ target = "app-service"; mode = "http-admin" }
    }
    Invoke-WebRequest -Method Post -Uri "http://127.0.0.1:8765/admin/shutdown?session_token=botik-dev-token" | Out-Null
    $shutdownRequested = $true
  }
  catch {
    Add-JsonLine $lifecycleLog @{
      timestamp = (Get-Date).ToString("o")
      kind = "shutdown_request_failed"
      payload = @{ target = "app-service"; message = $_.Exception.Message }
    }
  }

  foreach ($proc in @($frontend, $appService)) {
    if ($null -ne $proc -and -not $proc.HasExited) {
      cmd /c "taskkill /PID $($proc.Id) /T /F >nul 2>nul" | Out-Null
      Add-JsonLine $lifecycleLog @{
        timestamp = (Get-Date).ToString("o")
        kind = "process_killed"
        payload = @{ pid = $proc.Id }
      }
    }
  }

  foreach ($port in @(4173, 8765)) {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
      try {
        cmd /c "taskkill /PID $($listener.OwningProcess) /T /F >nul 2>nul" | Out-Null
        Add-JsonLine $lifecycleLog @{
          timestamp = (Get-Date).ToString("o")
          kind = "port_cleanup"
          payload = @{ port = $port; pid = $listener.OwningProcess }
        }
      }
      catch {
      }
    }
  }

  if ($testsPassed -and (Test-Path $dataBackfillDb)) {
    Remove-Item -LiteralPath $dataBackfillDb -Force -ErrorAction SilentlyContinue
  }

  $summary = [pscustomobject]@{
    startedAt = $startedAt.ToString("o")
    finishedAt = (Get-Date).ToString("o")
    shutdownRequested = $shutdownRequested
    listenersAfterCleanup = Get-ListenerCounts
    appServiceLog = @{
      stdout = $serviceOut
      stderr = $serviceErr
    }
    frontendLog = @{
      stdout = $frontendOut
      stderr = $frontendErr
    }
    lifecycleLog = $lifecycleLog
    dataBackfillDb = @{
      path = $dataBackfillDb
      existsAfterCleanup = Test-Path $dataBackfillDb
    }
  }
  $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $cleanupSummary -Encoding UTF8
}
