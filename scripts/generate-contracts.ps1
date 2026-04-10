$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$tempJson = Join-Path $env:TEMP "botik-foundation-openapi.json"
$generatedTs = Join-Path $repoRoot "frontend\src\shared\contracts\generated.ts"
$pythonScript = @'
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root / "app-service" / "src"))
from botik_app_service.main import create_app

app = create_app()
spec = app.openapi()
Path(sys.argv[2]).write_text(json.dumps(spec, ensure_ascii=True, indent=2), encoding="utf-8")
'@

$scriptFile = Join-Path $env:TEMP "botik-write-openapi.py"
Set-Content -LiteralPath $scriptFile -Value $pythonScript -Encoding UTF8
python $scriptFile $repoRoot $tempJson
corepack pnpm exec openapi-typescript $tempJson --output $generatedTs
