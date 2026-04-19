param(
    [switch]$Report,       # REPORT mode: never fails, only writes report.json
    [switch]$LLM,          # Force LLM mode (requires ANTHROPIC_API_KEY)
    [switch]$Heuristic,    # Force heuristic mode
    [switch]$OpenReport    # Open HTML report after run
)

$config = "tests/vision/playwright.vision.config.ts"

# ── Mode selection ────────────────────────────────────────────────────────────

if ($Report) {
    $env:VISION_STRICT = "0"
    Write-Host "[vision] Mode: REPORT (never fails)"
} else {
    $env:VISION_STRICT = "1"
    Write-Host "[vision] Mode: STRICT (fails on high severity + confidence>0.7)"
}

if ($LLM) {
    $env:VISION_MODE = "llm"
    if (-not $env:ANTHROPIC_API_KEY) {
        Write-Host "[vision] WARNING: -LLM requested but ANTHROPIC_API_KEY is not set."
        Write-Host "         Set it with: `$env:ANTHROPIC_API_KEY = '<your-key>'"
        exit 1
    }
    Write-Host "[vision] Vision: LLM (claude)"
} elseif ($Heuristic) {
    $env:VISION_MODE = "heuristic"
    Write-Host "[vision] Vision: Heuristic (JS-based)"
} else {
    if ($env:ANTHROPIC_API_KEY) {
        Write-Host "[vision] Vision: LLM (ANTHROPIC_API_KEY detected)"
    } else {
        Write-Host "[vision] Vision: Heuristic (no ANTHROPIC_API_KEY)"
    }
}

# ── Run tests ─────────────────────────────────────────────────────────────────

Write-Host "[vision] Running vision tests..."
npx playwright test --config $config

$exitCode = $LASTEXITCODE
$reportPath = ".artifacts/local/latest/vision/report.json"

if (Test-Path $reportPath) {
    Write-Host "[vision] Report: $reportPath"
}

if ($OpenReport) {
    $htmlReport = ".artifacts/local/latest/vision/html-report/index.html"
    if (Test-Path $htmlReport) {
        Start-Process $htmlReport
    }
}

exit $exitCode
