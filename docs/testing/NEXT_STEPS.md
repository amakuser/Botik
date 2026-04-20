# Next Steps — Testing & Vision

> Decision roadmap as of 2026-04-20. Each item is either a concrete action or a gate decision.

---

## IMMEDIATE (can be done now)

### VS-1: Update benchmark script for GPU mode
- **Status:** blocked by stale OLLAMA_LLM_LIBRARY=cpu env var (now removed)
- **Action:** Update `scripts/benchmark_vision_models.py` to:
  1. Start Ollama in GPU mode (exclude OLLAMA_LLM_LIBRARY from env)
  2. Use 30s timeout (GPU does it in <5s)
  3. Re-run and overwrite old "NOT PRACTICAL" results
- **Expected result:** gemma3:4b = GOOD DEFAULT TOOL

### VS-2: Remove persistent OLLAMA_LLM_LIBRARY=cpu
- **Action:** `[System.Environment]::SetEnvironmentVariable('OLLAMA_LLM_LIBRARY', $null, 'User')`
- **Why:** This was the root cause of the "NOT PRACTICAL" false result
- **Status:** done (removed for current session, confirm permanently removed)

---

## NEAR-TERM (next 1-2 sessions)

### VS-3: Integrate gemma3:4b into vision layer
- **Status:** ✅ DONE (2026-04-20)
- **What was done:**
  - Created `tests/visual/vision_loop.helpers.ts` — production-grade Ollama client
  - Added ACTION→SNAPSHOT→ANALYSIS→DECISION loop to `interaction.spec.ts` (3 scenarios)
  - JSON schema validation, confidence gating, retry, DOM cross-check, caching
  - Separate exploratory agent: `tests/vision/agent_audit.spec.ts` (OLLAMA_AGENT=1)
- **Result:** 4/4 interaction tests pass with OLLAMA_VISION=1

### VS-4: Diagnose llava:7b hang
- **Required for:** deciding whether to keep or remove llava:7b
- **Action:**
  1. Try `ollama pull llava-llama3:8b` (modern llava variant) as replacement
  2. If it loads: test vision on GPU
  3. If it also hangs: confirms Ollama 0.21.0 + CLIP projector + Blackwell issue
- **Decision point:** if llava-llama3 works → use it as second control model; if not → remove llava:7b from test matrix
- **Note (2026-04-20):** llava-llama3:8b also blocked by R2 CDN issue (see VS-6). Download not attempted due to CLIP hang risk + network blocker.

### VS-6: Unblock Cloudflare R2 for Ollama downloads
- **Status:** NEW — BLOCKER for any future model pull
- **Problem:** `*.r2.cloudflarestorage.com` returns SSL handshake failure from this network (ISP blocking suspected)
- **Evidence:** `schannel: failed to receive handshake` when accessing R2 directly; `registry.ollama.ai` works fine
- **Action options (choose one):**
  1. **Proxy**: Set `HTTPS_PROXY=http://127.0.0.1:<port>` (NekoBox HTTP proxy, typically 10808 or 7890) and restart Ollama serve with that env var
  2. **Manual HF import**: Accept Meta license on HuggingFace, download GGUF via `huggingface-cli`, import with `ollama create`
  3. **Accept limitation**: Keep gemma3:4b as sole local model until network situation changes
- **Prerequisite for:** VS-4 (llava-llama3), GATE-1 (11B evaluation)

### VS-5: Ollama startup automation
- **Action:** Create `scripts/start_ollama_gpu.ps1` that:
  1. Kills existing Ollama
  2. Cleans WAL/SHM files
  3. Starts in GPU mode (excludes OLLAMA_LLM_LIBRARY)
  4. Waits for server ready
- **Why:** prevents repeating the SQLite WAL corruption issue

---

## GATED DECISIONS

### GATE-1: Should we test llama3.2-vision:11b?
- **Current answer:** NO
- **Why:** gemma3:4b already achieves GOOD DEFAULT TOOL classification at 1.6s/request
- **Condition to change:** if gemma3:4b shows systematic false negatives in production use

### GATE-2: Should local vision replace Claude API vision?
- **Current answer:** NO — use as supplement, not replacement
- **Why:** Claude API is more capable (fewer false negatives); local = offline backup
- **Condition to change:** if API cost becomes an issue at production test frequency

### GATE-3: Should vision tests be in CI?
- **Current answer:** NOT YET
- **Blockers:** requires running Ollama on CI runner (Windows GitHub Actions)
- **Condition to change:** when VS-5 (Ollama startup automation) is done and CI runner has GPU

---

## BLOCKED

### BLK-1: llava:7b
- **Blocked by:** unknown incompatibility (RTX 5060 + CLIP projector or Q4_0 format)
- **Action needed:** try llava-llama3 as replacement (VS-4)

### BLK-2: Visual tests in CI
- **Blocked by:** no CI runner with Ollama installed + ANTHROPIC_API_KEY secret
- **Partial workaround:** Claude API vision tests can run in CI with the secret set

---

## WHAT SHOULD NOT BE ASSUMED IN FUTURE SESSIONS

1. `OLLAMA_LLM_LIBRARY=cpu` may be set in user environment — ALWAYS check before starting Ollama for vision
2. Ollama may fail to start if `db.sqlite-wal` exists — ALWAYS clean before starting
3. Python `urllib.request.urlopen()` uses system proxy — ALWAYS use `ProxyHandler({})`
4. CPU mode vision: 185s+ per request — NEVER set 120s timeout for CPU vision
5. GPU mode (gemma3:4b): 1-5s per request — 30s timeout is sufficient
6. llava:7b does NOT work on this machine — do not use or troubleshoot further without VS-4
7. The "NOT PRACTICAL" benchmark results from 2026-04-20 session are INVALID (CPU-only artifact)
