$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$artifactsRoot = Join-Path $repoRoot ".artifacts\local\latest\desktop-smoke"
$logsDir = Join-Path $artifactsRoot "logs"
$structuredDir = Join-Path $artifactsRoot "structured"
$stateDir = Join-Path $artifactsRoot "state"
$dataBackfillDb = Join-Path $stateDir "data_backfill.sqlite3"
$spotReadFixtureDb = Join-Path $stateDir "spot_read.fixture.sqlite3"
$runtimeControlStateDir = Join-Path $stateDir "runtime-control"
New-Item -ItemType Directory -Force -Path $artifactsRoot, $logsDir, $structuredDir, $stateDir | Out-Null

$frontendOut = Join-Path $logsDir "frontend.stdout.log"
$frontendErr = Join-Path $logsDir "frontend.stderr.log"
$desktopOut = Join-Path $logsDir "desktop.stdout.log"
$desktopErr = Join-Path $logsDir "desktop.stderr.log"
$lifecycleLog = Join-Path $structuredDir "service-events.jsonl"
$cleanupSummary = Join-Path $structuredDir "cleanup-summary.json"
$runtimeStatusFixture = Join-Path $structuredDir "runtime-status.fixture.json"
Remove-Item $frontendOut, $frontendErr, $desktopOut, $desktopErr, $lifecycleLog, $cleanupSummary, $dataBackfillDb, $spotReadFixtureDb, $runtimeStatusFixture -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $runtimeControlStateDir -Recurse -Force -ErrorAction SilentlyContinue

$runtimeStatusPayload = [pscustomobject]@{
  generated_at = "2026-04-11T10:00:00Z"
  runtimes = @(
    [pscustomobject]@{
      runtime_id = "spot"
      label = "Spot Runtime"
      state = "offline"
      pids = @()
      pid_count = 0
      last_heartbeat_at = $null
      last_heartbeat_age_seconds = $null
      last_error = $null
      last_error_at = $null
      status_reason = "no matching runtime process detected"
      source_mode = "fixture"
    },
    [pscustomobject]@{
      runtime_id = "futures"
      label = "Futures Runtime"
      state = "offline"
      pids = @()
      pid_count = 0
      last_heartbeat_at = $null
      last_heartbeat_age_seconds = $null
      last_error = $null
      last_error_at = $null
      status_reason = "no matching runtime process detected"
      source_mode = "fixture"
    }
  )
}
$runtimeStatusPayload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $runtimeStatusFixture -Encoding UTF8

function Initialize-SpotReadFixtureDb([string]$repoRootPath, [string]$dbPath) {
  $script = @"
import sqlite3
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
db_path = Path(sys.argv[2])
sys.path.insert(0, str(repo_root))
from src.botik.storage.spot_store import ensure_spot_schema, insert_spot_fill, insert_spot_position_intent, upsert_spot_balance, upsert_spot_holding, upsert_spot_order

connection = sqlite3.connect(db_path)
try:
    ensure_spot_schema(connection)
    upsert_spot_balance(connection, account_type='UNIFIED', asset='USDT', free_qty=1200.0, locked_qty=100.0, source_of_truth='fixture', updated_at_utc='2026-04-11T12:00:00Z')
    upsert_spot_balance(connection, account_type='UNIFIED', asset='BTC', free_qty=0.01, locked_qty=0.0, source_of_truth='fixture', updated_at_utc='2026-04-11T12:00:00Z')
    upsert_spot_holding(connection, account_type='UNIFIED', symbol='BTCUSDT', base_asset='BTC', free_qty=0.01, locked_qty=0.0, avg_entry_price=60000.0, hold_reason='strategy_entry', source_of_truth='fixture', recovered_from_exchange=False, strategy_owner='spot_spread', updated_at_utc='2026-04-11T12:00:00Z')
    upsert_spot_holding(connection, account_type='UNIFIED', symbol='ETHUSDT', base_asset='ETH', free_qty=0.2, locked_qty=0.0, avg_entry_price=3000.0, hold_reason='unknown_recovered_from_exchange', source_of_truth='fixture', recovered_from_exchange=True, strategy_owner=None, updated_at_utc='2026-04-11T11:55:00Z')
    upsert_spot_order(connection, account_type='UNIFIED', symbol='BTCUSDT', side='Buy', status='New', price=60000.0, qty=0.01, order_id='order-1', order_link_id='link-1', order_type='Limit', time_in_force='PostOnly', strategy_owner='spot_spread', updated_at_utc='2026-04-11T12:00:00Z')
    insert_spot_fill(connection, account_type='UNIFIED', symbol='BTCUSDT', side='Buy', exec_id='exec-1', order_id='order-1', order_link_id='link-1', price=60000.0, qty=0.01, fee=0.02, fee_currency='USDT', is_maker=True, exec_time_ms=1700000000123, created_at_utc='2026-04-11T12:00:00Z')
    insert_spot_position_intent(connection, account_type='UNIFIED', symbol='BTCUSDT', side='Buy', intended_qty=0.01, intended_price=60000.0, strategy_owner='spot_spread', created_at_utc='2026-04-11T12:00:00Z')
finally:
    connection.close()
"@
  $script | python - $repoRootPath $dbPath
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to initialize spot read fixture DB"
  }
}

function Add-JsonLine([string]$path, [object]$payload) {
  ($payload | ConvertTo-Json -Compress -Depth 8) | Add-Content -LiteralPath $path -Encoding UTF8
}

function Wait-Http200([string]$url, [hashtable]$headers, [int]$timeoutSec = 60) {
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
    Start-Sleep -Milliseconds 500
  }
  throw "Timed out waiting for $url"
}

function Wait-DesktopProcess([int]$timeoutSec = 90) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    $process = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'botik_desktop*' } | Select-Object -First 1
    if ($process) {
      return $process
    }
    Start-Sleep -Milliseconds 500
  }
  throw "Timed out waiting for botik_desktop process"
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

Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'botik_desktop*' } | ForEach-Object {
  try {
    cmd /c "taskkill /PID $($_.Id) /T /F >nul 2>nul" | Out-Null
  }
  catch {
  }
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

$frontend = $null
$desktop = $null
$desktopProcess = $null
$startedAt = Get-Date
$testsPassed = $false
Initialize-SpotReadFixtureDb $repoRoot $spotReadFixtureDb
$env:BOTIK_RUNTIME_STATUS_FIXTURE_PATH = $runtimeStatusFixture
$env:BOTIK_RUNTIME_CONTROL_MODE = "fixture"
$env:BOTIK_SPOT_READ_FIXTURE_DB_PATH = $spotReadFixtureDb

try {
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
  Wait-Http200 "http://127.0.0.1:4173/" @{}

  $env:BOTIK_ARTIFACTS_DIR = $artifactsRoot
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "spawn_requested"
    payload = @{ target = "desktop-shell" }
  }
  $desktop = Start-Process -FilePath $shellExe -ArgumentList "-File", (Join-Path $repoRoot "scripts\dev-desktop.ps1") -PassThru -WindowStyle Hidden -RedirectStandardOutput $desktopOut -RedirectStandardError $desktopErr
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "spawned"
    payload = @{ target = "desktop-shell"; pid = $desktop.Id }
  }

  Wait-Http200 "http://127.0.0.1:8765/health" @{ "x-botik-session-token" = "botik-dev-token" }
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "ready"
    payload = @{ target = "app-service"; url = "http://127.0.0.1:8765/health" }
  }
  Wait-Http200 "http://127.0.0.1:8765/bootstrap" @{ "x-botik-session-token" = "botik-dev-token" }
  $desktopProcess = Wait-DesktopProcess
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "ready"
    payload = @{ target = "desktop-shell"; pid = $desktopProcess.Id }
  }
  Wait-Http200 "http://127.0.0.1:4173/" @{}
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "ready"
    payload = @{ target = "frontend"; url = "http://127.0.0.1:4173/" }
  }

  corepack pnpm --dir $repoRoot exec playwright test --config "$repoRoot\tests\desktop-smoke\playwright.desktop.config.ts"
  $testsPassed = $true
}
finally {
  foreach ($proc in @($desktop, $frontend)) {
    if ($null -ne $proc -and -not $proc.HasExited) {
      cmd /c "taskkill /PID $($proc.Id) /T /F >nul 2>nul" | Out-Null
      Add-JsonLine $lifecycleLog @{
        timestamp = (Get-Date).ToString("o")
        kind = "process_killed"
        payload = @{ pid = $proc.Id }
      }
    }
  }

  Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'botik_desktop*' } | ForEach-Object {
    cmd /c "taskkill /PID $($_.Id) /T /F >nul 2>nul" | Out-Null
    Add-JsonLine $lifecycleLog @{
      timestamp = (Get-Date).ToString("o")
      kind = "process_killed"
      payload = @{ pid = $_.Id; name = $_.ProcessName }
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
  if ($testsPassed -and (Test-Path $spotReadFixtureDb)) {
    Remove-Item -LiteralPath $spotReadFixtureDb -Force -ErrorAction SilentlyContinue
  }
  if ($testsPassed -and (Test-Path $runtimeControlStateDir)) {
    Remove-Item -LiteralPath $runtimeControlStateDir -Recurse -Force -ErrorAction SilentlyContinue
  }

  $summary = [pscustomobject]@{
    startedAt = $startedAt.ToString("o")
    finishedAt = (Get-Date).ToString("o")
    listenersAfterCleanup = Get-ListenerCounts
    frontendLog = @{
      stdout = $frontendOut
      stderr = $frontendErr
    }
    desktopLog = @{
      stdout = $desktopOut
      stderr = $desktopErr
    }
    appServiceLog = @{
      stdout = (Join-Path $logsDir "app-service.stdout.log")
      stderr = (Join-Path $logsDir "app-service.stderr.log")
    }
    lifecycleLog = $lifecycleLog
    runtimeStatusFixture = $runtimeStatusFixture
    spotReadFixtureDb = @{
      path = $spotReadFixtureDb
      existsAfterCleanup = Test-Path $spotReadFixtureDb
    }
    dataBackfillDb = @{
      path = $dataBackfillDb
      existsAfterCleanup = Test-Path $dataBackfillDb
    }
    runtimeControlStateDir = @{
      path = $runtimeControlStateDir
      existsAfterCleanup = Test-Path $runtimeControlStateDir
    }
  }
  $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $cleanupSummary -Encoding UTF8
}
