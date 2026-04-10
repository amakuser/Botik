$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$env:PYTHONPATH = "$repoRoot\app-service\src;$repoRoot"
python -m pytest "$repoRoot\tests\unit\python" -q
corepack pnpm --dir "$repoRoot\frontend" test
