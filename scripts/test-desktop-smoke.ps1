$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$artifactsRoot = Join-Path $repoRoot ".artifacts\local\latest\desktop-smoke"
$logsDir = Join-Path $artifactsRoot "logs"
$structuredDir = Join-Path $artifactsRoot "structured"
New-Item -ItemType Directory -Force -Path $artifactsRoot, $logsDir, $structuredDir | Out-Null

$frontendOut = Join-Path $logsDir "frontend.stdout.log"
$frontendErr = Join-Path $logsDir "frontend.stderr.log"
$desktopOut = Join-Path $logsDir "desktop.stdout.log"
$desktopErr = Join-Path $logsDir "desktop.stderr.log"
$lifecycleLog = Join-Path $structuredDir "service-events.jsonl"
$cleanupSummary = Join-Path $structuredDir "cleanup-summary.json"
Remove-Item $frontendOut, $frontendErr, $desktopOut, $desktopErr, $lifecycleLog, $cleanupSummary -ErrorAction SilentlyContinue

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

  corepack pnpm exec playwright test --config "$repoRoot\tests\desktop-smoke\playwright.desktop.config.ts"
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
  }
  $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $cleanupSummary -Encoding UTF8
}
