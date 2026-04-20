# Experimental Vision Track — Botik

> Local Ollama vision model research. Status as of 2026-04-20.
> None of this is integrated into the main test pipeline yet.

---

## MACHINE SPECS

- GPU: NVIDIA GeForce RTX 5060 (Blackwell, SM_120, compute 12.0)
- VRAM: 8.0 GiB total / ~6.6 GiB available
- RAM: 16 GiB
- OS: Windows 11
- Ollama version: 0.21.0

---

## KNOWN ENVIRONMENT ISSUES

### Issue 1: SQLite WAL corruption blocks Ollama startup
- Stale `db.sqlite-wal` + `db.sqlite-shm` in `C:\Users\farik\AppData\Local\Ollama\` prevent server from starting
- Fix: delete both files before starting `ollama serve`
- Status: documented, not automated

### Issue 2: Python urllib uses Windows system proxy
- `urllib.request.urlopen()` routes through system proxy → HTTP 502
- Fix: `urllib.request.build_opener(urllib.request.ProxyHandler({}))`
- Already applied in `scripts/benchmark_vision_models.py`

### Issue 3: Previous OLLAMA_LLM_LIBRARY=cpu was persistent
- Set via `[System.Environment]::SetEnvironmentVariable('OLLAMA_LLM_LIBRARY', 'cpu', 'User')`
- This made ALL Ollama instances use CPU → 185s per vision request
- Real GPU-mode performance: 1.4-4.6s per vision request
- The env var is now removed for GPU inference

---

## MODEL TEST RESULTS

### gemma3:4b (Q4_K_M, 3.3 GB)

| Test | Mode | Result | Latency | Notes |
|------|------|--------|---------|-------|
| text-only | GPU | verified | ~7s cold, <1s warm | |
| text-only | CPU | verified | 7s | model pre-loaded |
| 1x1 PNG | GPU | verified | 0.76s | prompt_tokens=274 (256 vision + text) |
| 32x32 PNG | GPU | verified | 1.14s | same prompt_tokens |
| 160x120 PNG | GPU | verified | 1.21s | same prompt_tokens |
| health.png 305KB | GPU | verified | 1.29s | same prompt_tokens |
| Full benchmark (4 pages, JSON schema) | GPU | verified | avg 1.6s | JSON valid 100%, schema 4/4 |
| 1x1 PNG | CPU | verified | 185.3s | prompt_eval_duration=6s (internal) but 179s unaccounted |
| Vision prompt (any) | CPU | too slow | 185s+ min | NOT PRACTICAL |

**Vision architecture:**
- Embedded vision encoder in single GGUF (no separate projector)
- `gemma3.mm.tokens_per_image: 256` — fixed cost regardless of image size
- `gemma3.vision.image_size: 896` — input always processed at 896×896
- Family: `['gemma3']`

**GPU classification:** GOOD DEFAULT TOOL
- Latency ≤ 5s per request
- JSON valid rate: 100%
- Schema score: 4/4
- VRAM used: ~5299 MiB (fits in 6.6 GiB available)

**CPU classification:** NOT PRACTICAL (185s minimum per request)

### llava:7b (Q4_0, 3.9 GB + 596 MB mmproj)

| Test | Mode | Result | Evidence |
|------|------|--------|----------|
| text-only | GPU | HANG | VRAM stays at ~1134 MiB (not loaded), runner spawns then exits |
| text-only | CPU | HANG | 300s timeout exceeded |
| vision | GPU | HANG | same |
| vision | CPU | not tested (text already hung) | — |
| CLI run | GPU | HANG → killed | Spinner only, STDOUT empty, ExitCode=-1 |

**Root cause: UNCONFIRMED**
- Model files are intact (3.9 GB main + 596 MB mmproj)
- Runner subprocess spawns but model never loads into VRAM
- GPU utilization: 4% for ~80s then drops → runner exits
- No Windows crash event, no error message
- Possible: CLIP projector (separate mmproj architecture) incompatible with RTX 5060 Blackwell or Ollama 0.21.0
- Possible: llava:7b Q4_0 format deprecated in Ollama 0.21.0

**Status:** blocked / incompatible in current environment

---

## PREVIOUS FAILED BENCHMARKS (from 2026-04-20 early session)

The `scripts/benchmark_vision_models.py` script ran with OLLAMA_LLM_LIBRARY=cpu set globally.
Results showed both models "NOT PRACTICAL" — this was INCORRECT due to CPU-only mode.

Corrected results (GPU mode, gemma3:4b):
```
GEMMA3:4B
  Available:       True
  Avg latency:     1.6s (was incorrectly reported as 120s)
  JSON valid rate: 100% (was incorrectly reported as 0%)
  Schema score:    4.0/4 (was incorrectly reported as 0.0/4)
  Classification:  GOOD DEFAULT TOOL
```

---

## HOW TO START OLLAMA IN GPU MODE (CORRECT METHOD)

```powershell
# 1. Kill any existing Ollama
Stop-Process -Name 'ollama' -Force -ErrorAction SilentlyContinue

# 2. Clean stale WAL files
Remove-Item "$env:LOCALAPPDATA\Ollama\db.sqlite-wal" -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\Ollama\db.sqlite-shm" -ErrorAction SilentlyContinue

# 3. Start WITHOUT OLLAMA_LLM_LIBRARY override
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$psi.Arguments = 'serve'
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
# Copy user env but EXCLUDE OLLAMA_LLM_LIBRARY
foreach ($k in [System.Environment]::GetEnvironmentVariables('User').Keys) {
    if ($k -ne 'OLLAMA_LLM_LIBRARY') {
        $psi.EnvironmentVariables[$k] = [System.Environment]::GetEnvironmentVariable($k, 'User')
    }
}
$p = [System.Diagnostics.Process]::Start($psi)
```

---

## WHAT WAS RULED OUT

| Hypothesis | Verdict | Evidence |
|---|---|---|
| RTX 5060 incompatible with Ollama vision | RULED OUT | gemma3:4b vision works at 1.6s avg on GPU |
| gemma3:4b multimodal path broken | RULED OUT | 4/4 pages pass with full JSON schema |
| Image payload format issue | RULED OUT | all sizes (1x1 to 305KB) work correctly |
| Ollama cannot start in GPU mode | RULED OUT (partially) | serves HTTP, detects GPU (compute=12.0, cuda_v13) |
| CPU path works for vision | PARTIAL | works but 185s/request = not practical |

## WHAT IS NOT YET RULED OUT

| Hypothesis | Status |
|---|---|
| llava:7b CLIP projector incompatible with Blackwell (compute 12.0) | unproven |
| llava:7b Q4_0 format deprecated in Ollama 0.21.0 | unproven |
| Previous 502 errors caused by SQLite WAL (not GPU) | likely but not proven directly |
