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

---

## 11B MODEL EVALUATION — 2026-04-20

### Objective
Evaluate whether a ≈11B vision model is usable as a "deep audit" supplement to gemma3:4b.

### Models attempted

**llama3.2-vision:11b (Meta, 7.82 GB)**
- Architecture: Native multimodal transformer, NO separate CLIP projector
- VRAM estimate: ~7-8 GB (marginal fit in 8 GiB VRAM without other models loaded)
- Manifest blob: `sha256:9999d473...` (7,816,574,592 bytes)
- Manifest fetch: SUCCESS (registry.ollama.ai accessible)
- Blob download: FAILED — SSL handshake failure on Cloudflare R2

**llava-llama3:8b (8B, ~4.92 GB)**
- Architecture: LLaMA 3 base + CLIP projector (separate mmproj file)
- Status: SKIPPED — CLIP architecture suspected same hang as llava:7b (ExitCode=-1)

### Root cause of download failure

```
Error: max retries exceeded: Get "https://dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com/...": EOF
```

- `*.r2.cloudflarestorage.com` → `schannel: failed to receive handshake, SSL/TLS connection failed`
- Cloudflare R2 (Ollama's blob CDN) is inaccessible from this network
- Cause: likely ISP-level TLS blocking of R2 endpoints (Russia)
- Manifest registry (`registry.ollama.ai`) is accessible — only blob CDN blocked

### HuggingFace alternative

- `huggingface.co` CDN: ACCESSIBLE
- `bartowski/Llama-3.2-11B-Vision-Instruct-GGUF`: 401 Unauthorized (Meta license gating)
- `lmstudio-community/Llama-3.2-11B-Vision-Instruct-GGUF`: 401 Unauthorized (gated)
- `unsloth/Llama-3.2-11B-Vision-Instruct-GGUF`: 401 Unauthorized (gated)
- All variants require HF account + Meta license acceptance

### Pre-allocation artifact

Each failed `ollama pull` creates:
- `sha256-<hash>-partial`: Pre-allocated zero-filled file at FULL expected size
- `sha256-<hash>-partial-0` … `-15`: 16 chunk tracker files (50-60 bytes, all `Completed=0`)

These look like complete downloads but contain no actual data. SHA256 mismatch on them is expected.
Delete all with: `rm /c/Users/farik/.ollama/models/blobs/sha256-9999d473*-partial*`

### STEP 9 — FINAL VERDICT (updated after successful download via NekoBox VPN proxy)

| Model | Loads | Vision Works | Stable | Latency | Memory Fit | Better than 4B | Verdict |
|---|---|---|---|---|---|---|---|
| llama3.2-vision:11b | **YES** | **PARTIAL** (JSON 33%) | YES | 21-118s avg ~76s | **YES** 5.53 GB | **NO** | **NOT PRACTICAL** — 10-50× slower than gemma3:4b, JSON unreliable |
| llava-llama3:8b | SKIPPED | N/A | N/A | N/A | Unknown (~5-6 GB) | Unknown | **SKIPPED** — CLIP arch = same hang as llava:7b |

**gemma3:4b comparison:**

| Model | Latency (warm) | JSON valid | VRAM | Verdict |
|---|---|---|---|---|
| gemma3:4b | 1.4-4.6s | 100% | 5.18 GB | GOOD DEFAULT TOOL |
| llama3.2-vision:11b | 21-118s avg 76s | 33% (3-page test) | 5.53 GB | NOT PRACTICAL |

**How llama3.2-vision:11b was made to work:**
- `HTTPS_PROXY=http://127.0.0.1:2080` (NekoBox local proxy) set at Ollama serve process level
- Without proxy: Cloudflare R2 SSL handshake fails (ISP blocking)
- With proxy: downloaded at 30-45 MB/s in ~5 min

### Unblock paths

1. **Local VPN proxy**: Set `HTTPS_PROXY=http://127.0.0.1:<nekobox-port>` before starting Ollama, or configure Ollama via `OLLAMA_PROXY`. NekoBox typically exposes `127.0.0.1:10808` (mixed) or `127.0.0.1:7890` (HTTP).
2. **HF token + manual import**:
   - Accept Meta license at huggingface.co/meta-llama/Llama-3.2-11B-Vision-Instruct
   - `huggingface-cli login` → download GGUF
   - Create Modelfile → `ollama create llama3.2-vision:11b -f Modelfile`
3. **Current recommendation**: GATE-1 still applies — gemma3:4b at 1.6s/request is sufficient; defer 11B until either unblock path is confirmed working.

---

## STEP 10 — "AGENT EYES" TEST RESULTS (2026-04-20)

### Objective
Can a local vision model serve as "visual feedback" for UI automation — confirming button clicks, state changes, error banners?

### Test methodology
- Used existing baseline screenshots (25 PNGs from `tests/visual/baselines/`)
- Both models: JSON-constrained responses (`format: "json"`)
- Region crops (400×500px cards) vs full screenshots (~900×700px)
- Tasks: status badge detection, error banner detection

### Results

| Task | gemma3:4b | llama3.2-vision:11b |
|---|---|---|
| RUNNING badge (region crop) | ✅ 1.5s | ✅ 19.5s |
| OFFLINE badge (region crop) | ✅ 1.4s | ❌ 11.1s (said RUNNING) |
| Error banner — error page | ✅ 9.7s | ✅ 19.3s |
| Error banner — normal page | ❌ false positive | ❌ false positive |
| Telegram error banner | ✅ 1.4s | ✅ 11.1s |
| JSON correctness | ✅ all valid | ❌ schema template leaked |

**False positive on "normal" page:** Both models see red `OFFLINE` status badges on `runtime.png` as errors — question wording issue, not model capability issue.

**llama3.2-vision:11b JSON leakage:** With strict JSON schema, model outputs literal `"string or null"` instead of actual values — prompt template leaks into response.

### Verdict: gemma3:4b WINS for "Agent Eyes"

| Metric | gemma3:4b | llama3.2-vision:11b |
|---|---|---|
| Accuracy | better | worse (fails OFFLINE) |
| Speed warm (region) | **1.4s** | 11-19s |
| JSON reliability | **100%** | ~50% (template leakage) |
| VRAM | 5.18 GB | 5.53 GB |

**Recommendation:** Use `gemma3:4b` for agent eyes integration.
- Region crops → 1.4s per check (fast enough for automated testing)
- Full pages → 9.7s (acceptable for debug/audit mode)
- Improve question prompts: distinguish "action error banner" from "status indicators in cards"
- `llama3.2-vision:11b` adds NO value for this task and uses more VRAM
