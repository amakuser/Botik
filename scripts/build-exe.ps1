param (
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$exeTarget = Join-Path $repoRoot "botik.exe"
$sourceExe = Join-Path $repoRoot "apps\desktop\src-tauri\target\release\botik_desktop.exe"
$version = (Get-Content (Join-Path $repoRoot "VERSION") -ErrorAction SilentlyContinue) -replace "version=", ""

Write-Host ""
Write-Host "=== Botik Build ($version) ===" -ForegroundColor Cyan
Write-Host ""

# 1. Kill running instances
$killed = 0
foreach ($name in @("botik_desktop", "botik")) {
    $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        Write-Host "  [kill] $($p.ProcessName) PID $($p.Id)" -ForegroundColor Yellow
        cmd /c "taskkill /PID $($p.Id) /T /F >nul 2>nul" | Out-Null
        $killed++
    }
}
if ($killed -gt 0) {
    Start-Sleep -Milliseconds 1000
    Write-Host "  Killed $killed process(es)" -ForegroundColor Yellow
}

# 2. Remove old exe so stale file can't run
if (Test-Path $exeTarget) {
    Remove-Item -LiteralPath $exeTarget -Force
    Write-Host "  [clean] Removed old botik.exe" -ForegroundColor DarkGray
}

# 3. Frontend build (vite)
if (-not $SkipFrontend) {
    Write-Host ""
    Write-Host "  [1/2] Building frontend (vite)..." -ForegroundColor White
    $frontendDir = Join-Path $repoRoot "frontend"
    corepack pnpm --dir $frontendDir build 2>&1 | Tee-Object -Variable frontendLog | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $frontendLog | Select-Object -Last 20 | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        throw "Frontend build failed (exit $LASTEXITCODE)"
    }
    Write-Host "  [1/2] Frontend OK" -ForegroundColor Green
}
else {
    Write-Host "  [1/2] Frontend skipped (-SkipFrontend)" -ForegroundColor DarkGray
}

# 4. Tauri build
Write-Host ""
Write-Host "  [2/2] Building Tauri desktop..." -ForegroundColor White

$cargoHome = "$env:USERPROFILE\.cargo\bin"
if (Test-Path $cargoHome) {
    $env:PATH = "$cargoHome;$env:PATH"
}

$vsDevCmdCandidates = @(
    "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"
)
$vsDevCmd = $vsDevCmdCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$desktopDir = (Resolve-Path "$repoRoot\apps\desktop").Path

if ($vsDevCmd) {
    cmd /c "`"$vsDevCmd`" -host_arch=x64 -arch=x64 >nul && corepack pnpm --dir `"$desktopDir`" exec tauri build --no-bundle 2>&1"
}
else {
    corepack pnpm --dir $desktopDir exec tauri build --no-bundle 2>&1
}

if ($LASTEXITCODE -ne 0) {
    throw "Tauri build failed (exit $LASTEXITCODE)"
}

# 5. Verify source exe exists and is freshly built
if (-not (Test-Path $sourceExe)) {
    throw "Built exe not found: $sourceExe"
}
$builtAt = (Get-Item $sourceExe).LastWriteTime
if ($builtAt -lt (Get-Date).AddMinutes(-5)) {
    Write-Host "  WARNING: built exe is older than 5 minutes — may not reflect latest changes" -ForegroundColor Yellow
}

# 6. Copy to project root
Copy-Item -Path $sourceExe -Destination $exeTarget -Force
$sizeMB = [math]::Round((Get-Item $exeTarget).Length / 1MB, 1)

Write-Host "  [2/2] Tauri OK" -ForegroundColor Green
Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host "  botik.exe → $exeTarget"
Write-Host "  Version  : $version"
Write-Host "  Size     : ${sizeMB} MB"
Write-Host "  Built at : $builtAt"
Write-Host ""
