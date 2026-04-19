# Run the visual test suite (layout integrity + pixel regression).
# Prerequisites: app-service on :8765 and frontend on :4173 must already be running.
#
# Usage:
#   .\scripts\test-visual.ps1              # run all visual tests
#   .\scripts\test-visual.ps1 -Layout     # layout integrity only (no baselines needed)
#   .\scripts\test-visual.ps1 -Regression # pixel regression only
#   .\scripts\test-visual.ps1 -OpenReport # open HTML report after run

param(
  [switch]$Layout,
  [switch]$Regression,
  [switch]$OpenReport
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$config = "tests/visual/playwright.visual.config.ts"
$grepArg = if ($Layout) { @("--grep", "^layout:") } elseif ($Regression) { @("--grep", "^visual:") } else { @() }

Write-Host "Running visual tests..." -ForegroundColor Cyan
pnpm playwright test --config $config @grepArg

$exitCode = $LASTEXITCODE

if ($OpenReport) {
  $report = Join-Path $repoRoot ".artifacts/local/latest/visual/html-report/index.html"
  if (Test-Path $report) { Start-Process $report }
}

exit $exitCode
