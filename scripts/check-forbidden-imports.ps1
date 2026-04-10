$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

$frontendBad = rg -n 'from [''"]?(child_process|node:child_process|shelljs|execa|cross-spawn)[''"]?|require\([''"]?(child_process|node:child_process|shelljs|execa|cross-spawn)[''"]?\)' "$repoRoot\frontend\src"
if ($LASTEXITCODE -eq 0) {
  Write-Error "Forbidden frontend process import found.`n$frontendBad"
}

$tauriBad = rg -n 'invoke\(' "$repoRoot\frontend\src"
if ($LASTEXITCODE -eq 0) {
  $tauriOutsideHost = $tauriBad | Where-Object { $_ -notmatch 'shared[\\/]+host' }
  if ($tauriOutsideHost) {
    Write-Error "Direct Tauri invoke found outside shared/host boundary.`n$($tauriOutsideHost -join [Environment]::NewLine)"
  }
}

$pythonBad = rg -n 'subprocess\.(Popen|run|check_output|call)' "$repoRoot\app-service\src"
if ($LASTEXITCODE -eq 0) {
  $pythonOutsideAdapter = $pythonBad | Where-Object { $_ -notmatch 'process_adapter\.py' }
  if ($pythonOutsideAdapter) {
    Write-Error "Forbidden app-service subprocess usage found outside process_adapter.py.`n$($pythonOutsideAdapter -join [Environment]::NewLine)"
  }
}

Write-Host "Forbidden import checks passed."
