# Regenerate all pixel-regression baselines.
# Run after intentional UI changes to accept the new appearance as correct.
# Prerequisites: app-service on :8765 and frontend on :4173 must already be running.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "Updating visual baselines (regression tests only)..." -ForegroundColor Yellow

pnpm playwright test `
  --config tests/visual/playwright.visual.config.ts `
  --grep "^visual:" `
  --update-snapshots

Write-Host "Baselines updated in tests/visual/baselines/" -ForegroundColor Green
Write-Host "Commit the new baselines: git add tests/visual/baselines/ && git commit -m 'chore: update visual baselines'" -ForegroundColor DarkGray
