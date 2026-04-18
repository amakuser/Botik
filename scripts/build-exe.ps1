param (
    [switch]$SkipFrontend,
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$version = (Get-Content (Join-Path $repoRoot "VERSION") -ErrorAction SilentlyContinue) -replace "version=", ""
$exeTarget = Join-Path $repoRoot "botik.exe"

Write-Host ""
Write-Host "=== Botik Build ($version) ===" -ForegroundColor Cyan
Write-Host ""

# 1. Kill running instances
$killed = 0
foreach ($name in @("botik")) {
    $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        Write-Host "  [kill] $($p.ProcessName) PID $($p.Id)" -ForegroundColor Yellow
        cmd /c "taskkill /PID $($p.Id) /T /F >nul 2>nul" | Out-Null
        $killed++
    }
}
if ($killed -gt 0) {
    Start-Sleep -Milliseconds 800
    Write-Host "  Killed $killed process(es)" -ForegroundColor Yellow
}

# 2. Build frontend (vite)
if (-not $SkipFrontend) {
    Write-Host "  [1/2] Building frontend..." -ForegroundColor White
    $frontendDir = Join-Path $repoRoot "frontend"
    Push-Location $frontendDir
    try {
        & pnpm build 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "pnpm build failed" }
    } finally {
        Pop-Location
    }
    Write-Host "  [1/2] Frontend OK — dist/ ready" -ForegroundColor Green
} else {
    Write-Host "  [1/2] Frontend skipped (-SkipFrontend)" -ForegroundColor DarkGray
}

# 3. PyInstaller
Write-Host "  [2/2] Running PyInstaller..." -ForegroundColor White
Push-Location $repoRoot
try {
    $cleanFlag = if ($SkipClean) { "" } else { "--clean" }
    if ($cleanFlag) {
        & python -m PyInstaller $cleanFlag botik.spec 2>&1 | Tee-Object -Variable piLog | Out-Null
    } else {
        & python -m PyInstaller botik.spec 2>&1 | Tee-Object -Variable piLog | Out-Null
    }
    if ($LASTEXITCODE -ne 0) {
        $piLog | Select-Object -Last 30 | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        throw "PyInstaller failed (exit $LASTEXITCODE)"
    }
} finally {
    Pop-Location
}

# 4. Copy dist/botik.exe to root
$distExe = Join-Path $repoRoot "dist" "botik.exe"
if (-not (Test-Path $distExe)) {
    throw "dist/botik.exe not found after build"
}
Copy-Item -Path $distExe -Destination $exeTarget -Force
$sizeMB = [math]::Round((Get-Item $exeTarget).Length / 1MB, 1)

Write-Host "  [2/2] PyInstaller OK" -ForegroundColor Green
Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host "  botik.exe  → $exeTarget"
Write-Host "  Version    : $version"
Write-Host "  Size       : ${sizeMB} MB"
Write-Host ""
Write-Host "  Double-click botik.exe to launch." -ForegroundColor Green
Write-Host ""
