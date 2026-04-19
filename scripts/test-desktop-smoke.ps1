$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$artifactsRoot = Join-Path $repoRoot ".artifacts\local\latest\desktop-smoke"
$logsDir = Join-Path $artifactsRoot "logs"
$structuredDir = Join-Path $artifactsRoot "structured"
$stateDir = Join-Path $artifactsRoot "state"
$dataBackfillDb = Join-Path $stateDir "data_backfill.sqlite3"
$spotReadFixtureDb = Join-Path $stateDir "spot_read.fixture.sqlite3"
$futuresReadFixtureDb = Join-Path $stateDir "futures_read.fixture.sqlite3"
$analyticsReadFixtureDb = Join-Path $stateDir "analytics_read.fixture.sqlite3"
$modelsReadFixtureDb = Join-Path $stateDir "models_read.fixture.sqlite3"
$modelsReadManifest = Join-Path $stateDir "active_models.fixture.yaml"
$telegramOpsFixture = Join-Path $structuredDir "telegram-ops.fixture.json"
$runtimeControlStateDir = Join-Path $stateDir "runtime-control"
$trainingControlStateDir = Join-Path $stateDir "training-control"
New-Item -ItemType Directory -Force -Path $artifactsRoot, $logsDir, $structuredDir, $stateDir | Out-Null

$frontendOut = Join-Path $logsDir "frontend.stdout.log"
$frontendErr = Join-Path $logsDir "frontend.stderr.log"
$serviceOut = Join-Path $logsDir "app-service.stdout.log"
$serviceErr = Join-Path $logsDir "app-service.stderr.log"
$lifecycleLog = Join-Path $structuredDir "service-events.jsonl"
$cleanupSummary = Join-Path $structuredDir "cleanup-summary.json"
$runtimeStatusFixture = Join-Path $structuredDir "runtime-status.fixture.json"
Remove-Item $frontendOut, $frontendErr, $serviceOut, $serviceErr, $lifecycleLog, $cleanupSummary, $dataBackfillDb, $spotReadFixtureDb, $futuresReadFixtureDb, $analyticsReadFixtureDb, $modelsReadFixtureDb, $modelsReadManifest, $runtimeStatusFixture, $telegramOpsFixture -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $runtimeControlStateDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $trainingControlStateDir -Recurse -Force -ErrorAction SilentlyContinue

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

$telegramOpsPayload = [pscustomobject]@{
  snapshot = [pscustomobject]@{
    generated_at = "2026-04-11T12:00:00Z"
    source_mode = "fixture"
    summary = [pscustomobject]@{
      bot_profile = "ops"
      token_profile_name = "TELEGRAM_BOT_TOKEN"
      token_configured = $true
      internal_bot_disabled = $false
      connectivity_state = "unknown"
      connectivity_detail = "Use connectivity check to verify Telegram Bot API reachability."
      allowed_chat_count = 2
      allowed_chats_masked = @("12***34", "56***78")
      commands_count = 2
      alerts_count = 1
      errors_count = 1
      last_successful_send = "fixture alert delivered"
      last_error = "fixture warning observed"
      startup_status = "configured"
    }
    recent_commands = @(
      [pscustomobject]@{
        ts = "2026-04-11T11:58:00Z"
        command = "/status"
        source = "telegram_bot"
        status = "ok"
        chat_id_masked = "12***34"
        username = "fixture_user"
        args = ""
      }
    )
    recent_alerts = @(
      [pscustomobject]@{
        ts = "2026-04-11T11:59:00Z"
        alert_type = "delivery"
        message = "fixture alert delivered"
        delivered = $true
        source = "telegram"
        status = "ok"
      }
    )
    recent_errors = @(
      [pscustomobject]@{
        ts = "2026-04-11T11:57:00Z"
        error = "fixture warning observed"
        source = "telegram"
        status = "warning"
      }
    )
    truncated = [pscustomobject]@{
      recent_commands = $false
      recent_alerts = $false
      recent_errors = $false
    }
  }
  connectivity_check_result = [pscustomobject]@{
    checked_at = "2026-04-11T12:00:10Z"
    source_mode = "fixture"
    state = "healthy"
    detail = "fixture connectivity check passed"
    bot_username = "botik_fixture_bot"
    latency_ms = 42.0
    error = $null
  }
}
$telegramOpsPayload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $telegramOpsFixture -Encoding UTF8

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

function Initialize-FuturesReadFixtureDb([string]$repoRootPath, [string]$dbPath) {
  $script = @"
import sqlite3
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
db_path = Path(sys.argv[2])
sys.path.insert(0, str(repo_root))
from src.botik.storage.futures_store import ensure_futures_schema, insert_futures_fill, upsert_futures_open_order, upsert_futures_position

connection = sqlite3.connect(db_path)
try:
    ensure_futures_schema(connection)
    upsert_futures_position(connection, account_type='UNIFIED', symbol='ETHUSDT', side='Buy', position_idx=1, margin_mode='cross', leverage=5.0, qty=0.02, entry_price=3000.0, mark_price=3010.5, liq_price=2500.0, unrealized_pnl=42.125, realized_pnl=None, take_profit=3050.0, stop_loss=2950.0, trailing_stop=None, protection_status='protected', strategy_owner='futures_spike_reversal', source_of_truth='fixture', recovered_from_exchange=False, updated_at_utc='2026-04-11T12:00:00Z')
    upsert_futures_position(connection, account_type='UNIFIED', symbol='BTCUSDT', side='Sell', position_idx=2, margin_mode='isolated', leverage=3.0, qty=0.01, entry_price=65000.0, mark_price=65100.0, liq_price=70000.0, unrealized_pnl=-10.5, realized_pnl=None, take_profit=64000.0, stop_loss=65500.0, trailing_stop=None, protection_status='repairing', strategy_owner=None, source_of_truth='fixture', recovered_from_exchange=True, updated_at_utc='2026-04-11T11:58:00Z')
    upsert_futures_open_order(connection, account_type='UNIFIED', symbol='ETHUSDT', status='New', order_id='fut-order-1', order_link_id='fut-link-1', side='Sell', order_type='Limit', time_in_force='GTC', price=3050.0, qty=0.02, reduce_only=True, close_on_trigger=False, strategy_owner='futures_spike_reversal', updated_at_utc='2026-04-11T12:00:00Z')
    insert_futures_fill(connection, account_type='UNIFIED', symbol='ETHUSDT', side='Buy', exec_id='fut-exec-1', order_id='fut-order-1', order_link_id='fut-link-1', price=3001.0, qty=0.02, exec_fee=0.15, fee_currency='USDT', is_maker=True, exec_time_ms=1700000000123, created_at_utc='2026-04-11T12:00:00Z')
finally:
    connection.close()
"@
  $script | python - $repoRootPath $dbPath
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to initialize futures read fixture DB"
  }
}

function Initialize-AnalyticsReadFixtureDb([string]$dbPath) {
  $script = @"
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
connection = sqlite3.connect(db_path)
try:
    connection.executescript('''
        CREATE TABLE futures_paper_trades (
            id INTEGER PRIMARY KEY,
            symbol TEXT,
            model_scope TEXT,
            net_pnl REAL,
            was_profitable INTEGER,
            opened_at_utc TEXT,
            closed_at_utc TEXT
        );
        CREATE TABLE outcomes (
            signal_id TEXT PRIMARY KEY,
            symbol TEXT,
            model_scope TEXT,
            net_pnl_quote REAL,
            was_profitable INTEGER,
            closed_at_utc TEXT
        );
    ''')
    connection.executemany(
        "INSERT INTO futures_paper_trades (symbol, model_scope, net_pnl, was_profitable, opened_at_utc, closed_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("BTCUSDT", "futures", 12.5, 1, "2026-04-08 09:00:00", "2026-04-08 10:00:00"),
            ("ETHUSDT", "futures", -3.0, 0, "2026-04-09 09:00:00", "2026-04-09 10:00:00"),
        ],
    )
    connection.executemany(
        "INSERT INTO outcomes (signal_id, symbol, model_scope, net_pnl_quote, was_profitable, closed_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("sig-1", "SOLUSDT", "spot", 5.0, 1, "2026-04-10 11:00:00"),
            ("sig-2", "XRPUSDT", "spot", 1.5, 1, "2026-04-11 12:00:00"),
        ],
    )
    connection.commit()
finally:
    connection.close()
"@
  $script | python - $dbPath
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to initialize analytics read fixture DB"
  }
}

function Initialize-ModelsReadFixture([string]$dbPath, [string]$manifestPath) {
  $script = @"
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
connection = sqlite3.connect(db_path)
try:
    connection.executescript('''
        CREATE TABLE model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT UNIQUE NOT NULL,
            path_or_payload TEXT,
            metrics_json TEXT,
            created_at_utc TEXT NOT NULL,
            is_active INTEGER DEFAULT 0
        );
        CREATE TABLE ml_training_runs (
            run_id TEXT PRIMARY KEY,
            model_scope TEXT NOT NULL,
            model_version TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            epoch INTEGER,
            max_epochs INTEGER,
            loss REAL,
            accuracy REAL,
            sharpe_ratio REAL,
            trade_count INTEGER,
            is_trained INTEGER NOT NULL DEFAULT 0,
            trained_at_utc TEXT,
            started_at_utc TEXT NOT NULL,
            finished_at_utc TEXT,
            notes TEXT
        );
    ''')
    connection.executemany(
        "INSERT INTO model_registry (model_id, path_or_payload, metrics_json, created_at_utc, is_active) VALUES (?, ?, ?, ?, ?)",
        [
            ("spot-champion-v3", "data/models/spot-champion-v3.pkl", '{"instrument":"spot","policy":"hybrid","source_mode":"executed","status":"ready","quality_score":0.81}', "2026-04-10T08:00:00Z", 1),
            ("spot-challenger-v4", "data/models/spot-challenger-v4.pkl", '{"instrument":"spot","policy":"model","source_mode":"paper","status":"candidate","quality_score":0.87}', "2026-04-11T10:00:00Z", 0),
            ("futures-paper-v2", "data/models/futures-paper-v2.pkl", '{"instrument":"futures","policy":"hard","source_mode":"paper","status":"ready","quality_score":0.74}', "2026-04-11T11:00:00Z", 1),
        ],
    )
    connection.executemany(
        "INSERT INTO ml_training_runs (run_id, model_scope, model_version, mode, status, is_trained, started_at_utc, finished_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("run-futures-1", "futures", "futures-paper-v2", "offline", "completed", 1, "2026-04-11T09:30:00Z", "2026-04-11T09:45:00Z"),
            ("run-spot-1", "spot", "spot-champion-v3", "offline", "completed", 1, "2026-04-10T08:00:00Z", "2026-04-10T08:20:00Z"),
        ],
    )
    connection.commit()
finally:
    connection.close()

manifest_path.write_text(
    "\n".join(
        [
            "manifest_version: 1",
            "product: botik_dashboard",
            "active_spot_model: spot-champion-v3",
            "active_futures_model: futures-paper-v2",
            "spot_checkpoint_path: data/models/spot-champion-v3.pkl",
            "futures_checkpoint_path: data/models/futures-paper-v2.pkl",
        ]
    ) + "\n",
    encoding="utf-8",
)
"@
  $script | python - $dbPath $manifestPath
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to initialize models read fixtures"
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

# Kill any lingering processes from previous runs
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
$appService = $null
$startedAt = Get-Date
$testsPassed = $false
Initialize-SpotReadFixtureDb $repoRoot $spotReadFixtureDb
Initialize-FuturesReadFixtureDb $repoRoot $futuresReadFixtureDb
Initialize-AnalyticsReadFixtureDb $analyticsReadFixtureDb
Initialize-ModelsReadFixture $modelsReadFixtureDb $modelsReadManifest
$env:BOTIK_RUNTIME_STATUS_FIXTURE_PATH = $runtimeStatusFixture
$env:BOTIK_RUNTIME_CONTROL_MODE = "fixture"
$env:BOTIK_SPOT_READ_FIXTURE_DB_PATH = $spotReadFixtureDb
$env:BOTIK_FUTURES_READ_FIXTURE_DB_PATH = $futuresReadFixtureDb
$env:BOTIK_TELEGRAM_OPS_FIXTURE_PATH = $telegramOpsFixture
$env:BOTIK_ANALYTICS_READ_FIXTURE_DB_PATH = $analyticsReadFixtureDb
$env:BOTIK_MODELS_READ_FIXTURE_DB_PATH = $modelsReadFixtureDb
$env:BOTIK_MODELS_READ_MANIFEST_PATH = $modelsReadManifest
$env:BOTIK_TRAINING_CONTROL_MODE = "fixture"
$env:BOTIK_DESKTOP_MODE = "true"
$env:BOTIK_ARTIFACTS_DIR = $artifactsRoot
$env:VITE_BOTIK_DESKTOP = "true"

try {
  # Write a synthetic "ready" event before app-service starts.
  # FileTail in LogsManager will pick this up on first poll, activating the desktop channel.
  # This replaces the event that botik_desktop.exe binary would normally write.
  Add-JsonLine $lifecycleLog @{
    timestamp = (Get-Date).ToString("o")
    kind = "ready"
    payload = @{ target = "app-service" }
  }

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

  corepack pnpm --dir $repoRoot exec playwright test --config "$repoRoot\tests\desktop-smoke\playwright.desktop.config.ts"
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

  # Defensive: kill any lingering botik_desktop processes
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
  if ($testsPassed -and (Test-Path $futuresReadFixtureDb)) {
    Remove-Item -LiteralPath $futuresReadFixtureDb -Force -ErrorAction SilentlyContinue
  }
  if ($testsPassed -and (Test-Path $analyticsReadFixtureDb)) {
    Remove-Item -LiteralPath $analyticsReadFixtureDb -Force -ErrorAction SilentlyContinue
  }
  if ($testsPassed -and (Test-Path $modelsReadFixtureDb)) {
    Remove-Item -LiteralPath $modelsReadFixtureDb -Force -ErrorAction SilentlyContinue
  }
  if ($testsPassed -and (Test-Path $modelsReadManifest)) {
    Remove-Item -LiteralPath $modelsReadManifest -Force -ErrorAction SilentlyContinue
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
    appServiceLog = @{
      stdout = $serviceOut
      stderr = $serviceErr
    }
    lifecycleLog = $lifecycleLog
    runtimeStatusFixture = $runtimeStatusFixture
    telegramOpsFixture = $telegramOpsFixture
    spotReadFixtureDb = @{
      path = $spotReadFixtureDb
      existsAfterCleanup = Test-Path $spotReadFixtureDb
    }
    futuresReadFixtureDb = @{
      path = $futuresReadFixtureDb
      existsAfterCleanup = Test-Path $futuresReadFixtureDb
    }
    analyticsReadFixtureDb = @{
      path = $analyticsReadFixtureDb
      existsAfterCleanup = Test-Path $analyticsReadFixtureDb
    }
    modelsReadFixtureDb = @{
      path = $modelsReadFixtureDb
      existsAfterCleanup = Test-Path $modelsReadFixtureDb
    }
    modelsReadManifest = @{
      path = $modelsReadManifest
      existsAfterCleanup = Test-Path $modelsReadManifest
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
