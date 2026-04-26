# Desktop-native automated smoke — Tauri shell launch + window detection + screenshot.
#
# Restored 2026-04-26 in minimal form. Original was lost in M1 cleanup
# (untracked working tree, not backed up). Now retargeted from the retired
# PyInstaller `botik_desktop.exe` at repo root to the official Tauri build
# output at apps/desktop/src-tauri/target/release/botik_desktop.exe.
#
# Exit codes:
#   0 — exe launched, window found, visible, clean teardown
#   1 — launch failure / no HWND within timeout / process died early
#
# Usage:
#   pwsh ./tests/desktop-native/run-automated-smoke.ps1
#   pwsh ./tests/desktop-native/run-automated-smoke.ps1 -TimeoutSeconds 90
#   pwsh ./tests/desktop-native/run-automated-smoke.ps1 -KeepWindow  # don't kill at end

[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 60,
    [switch]$KeepWindow
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$exePath = Join-Path $repoRoot 'apps\desktop\src-tauri\target\release\botik_desktop.exe'
$artifactDir = Join-Path $repoRoot '.artifacts\local\latest\desktop-native\automated'
$logPath = Join-Path $artifactDir 'run.log'
$screenshotPath = Join-Path $artifactDir 'window-rect.png'

if (-not (Test-Path $artifactDir)) {
    New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
}

function Write-LogLine {
    param([string]$Line)
    $stamp = (Get-Date).ToString('o')
    "[$stamp] $Line" | Tee-Object -FilePath $logPath -Append
}

# Reset artifacts
Set-Content -Path $logPath -Value '' -Encoding UTF8
if (Test-Path $screenshotPath) { Remove-Item $screenshotPath -Force }

Write-LogLine "=== desktop-native automated smoke ==="
Write-LogLine "repo_root      = $repoRoot"
Write-LogLine "exe_path       = $exePath"
Write-LogLine "timeout_s      = $TimeoutSeconds"
Write-LogLine "artifact_dir   = $artifactDir"

if (-not (Test-Path $exePath)) {
    Write-LogLine "FAIL: exe not found. Build it via: corepack pnpm --dir ./apps/desktop build"
    Write-Host "[FAIL] Tauri exe not found at $exePath" -ForegroundColor Red
    exit 1
}

. (Join-Path $PSScriptRoot 'lib\Win32Window.ps1')

# ── Launch ──────────────────────────────────────────────────────────────────

Write-LogLine "launching exe..."
$process = $null
try {
    $process = Start-Process -FilePath $exePath -PassThru -WindowStyle Normal
} catch {
    Write-LogLine "FAIL: Start-Process threw: $($_.Exception.Message)"
    Write-Host "[FAIL] Launch failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-LogLine "process started, pid=$($process.Id)"

# Quick early-death check — if the exe exits before timeout, that's a fast fail
Start-Sleep -Seconds 2
if ($process.HasExited) {
    Write-LogLine "FAIL: process exited within 2s, exit_code=$($process.ExitCode)"
    Write-Host "[FAIL] Process died early (exit $($process.ExitCode))" -ForegroundColor Red
    exit 1
}

# ── Wait for HWND ───────────────────────────────────────────────────────────

Write-LogLine "waiting for top-level window (timeout=${TimeoutSeconds}s)..."
$hwnd = Find-BotikDesktopWindow -ProcessId $process.Id -TimeoutSeconds $TimeoutSeconds

if ($hwnd -eq [IntPtr]::Zero) {
    Write-LogLine "FAIL: no matching HWND found within timeout"
    if (-not $KeepWindow) { try { $process.Kill() } catch {} }
    Write-Host "[FAIL] No HWND found within ${TimeoutSeconds}s" -ForegroundColor Red
    exit 1
}

$snapshot = Get-WindowSnapshot -Hwnd $hwnd
Write-LogLine "hwnd=$($snapshot.hwnd) title='$($snapshot.title)' rect=($($snapshot.left),$($snapshot.top))-($($snapshot.right),$($snapshot.bottom)) visible=$($snapshot.visible)"

if (-not $snapshot.visible -or $snapshot.width -le 0 -or $snapshot.height -le 0) {
    Write-LogLine "FAIL: window not visible or zero-size (w=$($snapshot.width) h=$($snapshot.height))"
    if (-not $KeepWindow) { try { $process.Kill() } catch {} }
    Write-Host "[FAIL] Window present but not visible / zero-size" -ForegroundColor Red
    exit 1
}

# ── Capture screenshot ──────────────────────────────────────────────────────

Write-LogLine "capturing window screenshot..."
$captureOk = Save-WindowScreenshot -Hwnd $hwnd -OutPath $screenshotPath
Write-LogLine "screenshot_ok=$captureOk path=$screenshotPath"

# ── Stability check — process still alive after capture ─────────────────────

if ($process.HasExited) {
    Write-LogLine "FAIL: process died during capture, exit_code=$($process.ExitCode)"
    Write-Host "[FAIL] Process exited during capture" -ForegroundColor Red
    exit 1
}

# ── Teardown ────────────────────────────────────────────────────────────────

if (-not $KeepWindow) {
    Write-LogLine "tearing down (Kill pid=$($process.Id))..."
    try {
        $process.Kill()
        $process.WaitForExit(5000) | Out-Null
        Write-LogLine "process exited cleanly"
    } catch {
        Write-LogLine "WARN: Kill threw: $($_.Exception.Message)"
    }
} else {
    Write-LogLine "KeepWindow set — leaving window open, pid=$($process.Id)"
}

Write-LogLine "=== smoke PASSED ==="
Write-Host "[OK] desktop-native smoke passed (hwnd=$($snapshot.hwnd) title='$($snapshot.title)')" -ForegroundColor Green
exit 0
