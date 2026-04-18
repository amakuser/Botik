param (
    [switch]$OpenReport
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$desktopSmoke = Join-Path $repoRoot "tests\desktop-smoke"
$reportDir = Join-Path $repoRoot ".artifacts\local\latest\desktop-smoke\html-report"

Write-Host ""
Write-Host "=== Visual Audit ===" -ForegroundColor Cyan
Write-Host "  Expects dev server running at http://127.0.0.1:4173"
Write-Host "  Expects app-service at http://127.0.0.1:8765"
Write-Host ""

# Check frontend is up
$script = @"
import sys, urllib.request
req = urllib.request.Request('http://127.0.0.1:4173')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(req, timeout=2) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
"@
$script | python -
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: frontend not running at :4173" -ForegroundColor Red
    Write-Host "  Start it with: npm run dev:desktop" -ForegroundColor Yellow
    exit 1
}

corepack pnpm --dir $repoRoot exec playwright test `
    --config "$desktopSmoke\playwright.desktop.config.ts" `
    "$desktopSmoke\visual_audit.spec.ts"

$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "  All visual checks passed" -ForegroundColor Green
} else {
    Write-Host "  Some checks failed — see report" -ForegroundColor Yellow
}

Write-Host "  Report: $reportDir\index.html"
Write-Host ""

if ($OpenReport -or $exitCode -ne 0) {
    if (Test-Path "$reportDir\index.html") {
        Start-Process "$reportDir\index.html"
    }
}

exit $exitCode
