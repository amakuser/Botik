$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:BOTIK_REPO_ROOT = $repoRoot
if (-not $env:BOTIK_ARTIFACTS_DIR) {
  $env:BOTIK_ARTIFACTS_DIR = "$repoRoot\.artifacts\local\latest\desktop-shell"
}
if (-not $env:BOTIK_SESSION_TOKEN) {
  $env:BOTIK_SESSION_TOKEN = "botik-dev-token"
}
$env:BOTIK_FRONTEND_URL = "http://127.0.0.1:4173"
$env:BOTIK_APP_SERVICE_HOST = "127.0.0.1"
$env:BOTIK_APP_SERVICE_PORT = "8765"

$cargoCommand = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $cargoCommand) {
  $cargoBinCandidates = @(
    "$env:USERPROFILE\.cargo\bin",
    "C:\Program Files\Rust stable MSVC 1.94\bin"
  )
  foreach ($candidate in $cargoBinCandidates) {
    if (Test-Path (Join-Path $candidate "cargo.exe")) {
      $env:PATH = "$candidate;$env:PATH"
      break
    }
  }
}

$vsDevCmdCandidates = @(
  "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
  "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
)
$vsDevCmd = $vsDevCmdCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($vsDevCmd) {
  $desktopDir = (Resolve-Path "$repoRoot\apps\desktop").Path
  $cmdLine = "`"$vsDevCmd`" -host_arch=x64 -arch=x64 >nul && corepack pnpm --dir `"$desktopDir`" exec tauri dev"
  cmd /c $cmdLine
}
else {
  corepack pnpm --dir "$repoRoot\apps\desktop" exec tauri dev
}
