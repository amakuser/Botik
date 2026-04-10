$ErrorActionPreference = "Stop"
$template = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")) ".github\pull_request_template.md"
$required = @(
  "Selectors added or changed:",
  "Tests added:",
  "Headless observability path:",
  "Job lifecycle touched:"
)
$content = Get-Content -Raw $template
foreach ($needle in $required) {
  if (-not $content.Contains($needle)) {
    Write-Error "PR template is missing required section: $needle"
  }
}
Write-Host "PR template rules check passed."
