# Next Steps — Testing & Vision

> Decision roadmap as of 2026-04-25. Each item is either a concrete action or a gate decision.

---

## WHAT IS PRODUCTION-GRADE RIGHT NOW

- `tests/visual/interaction.spec.ts` — all 4 scenarios pass with `OLLAMA_VISION=1`, no confidence-gate shortcuts.
- `tests/visual/live-backend.spec.ts` — **6 live scenarios** (health, runtime, jobs, start-spot, stop-spot, start-futures). Live interactions are **multi-region** as of 2026-04-23: every transition is corroborated by header.badge + actions.row + callouts with a structured `composeDecision` (confirmed/conflicted/skipped per region) plus a post-action `checkRegionLayoutSanity` DOM check. As of 2026-04-23 the three runtime interaction scenarios also carry a `captureSemanticSnapshot` + `compareSemanticSnapshots` pair that asserts `state_changed`/`action_availability_changed`/`callout_changed`/`region_added/removed` from data-ui-* attributes — independent of badge text. All 3-way confirmed with the extended `RUNNING|OFFLINE|DEGRADED|UNKNOWN` state schema.
- `tests/visual/semantic.spec.ts` + `tests/visual/semantic.helpers.ts` — 2026-04-25: semantic auto-region system covers `/runtime` AND `/jobs`. Live `/jobs` scenario auto-discovers 15 regions through `data-ui-*`, asserts `jobs-history` canonical bucket matches `backendJobCount`, requires both preset cards + their start actions, and refuses vision recommendation on layout-only roles.
- **Canonical state layer (2026-04-25):** every region carries `canonical_state` derived from `(role, raw)` via a single `CANONICAL_MAP` table. Three canonical enums: `RUNTIME_STATE.{INACTIVE,ACTIVE,DEGRADED}`, `JOBS_STATE.{EMPTY,NON_EMPTY}`, `ACTION_STATE.{ENABLED,DISABLED}`. Tests assert against the enum, the diff compares canonical first. A new spec proves a synthetic UI rename (`offline → idle`) yields `canonical_state===null` instead of silently passing.
- Classifiers `classifyElementState`, `detectErrorText`, `detectPanelVisibility` — 100% reliable on 3/3 probes, guarded by `VISION_REGION_MIN`.
- `tests/visual/region-guardrail.spec.ts` — proves too-small regions are refused without a model call.

## WHAT IS PARTIAL

- `tests/vision/agent_audit.spec.ts` — report-only triage tool, expected-state aware but still a 4B-model heuristic. Never a gate. Graduate findings into deterministic specs before trusting them.

## REGION GUARDRAIL (VS-8)

Every classifier returns `ClassifierResult<T>` with `_too_small: boolean`, `size: RegionSize`, and (when skipped) `reason: string`. Scenarios must check `_too_small` before trusting the result — the jobs bare-`<p>` pattern (where a 300x20px crop yielded confident garbage) is no longer silently possible.

## WHAT IS STILL FIXTURE-ONLY / MOCKED

- `tests/visual/regression.spec.ts`, `regions.spec.ts`, `states.spec.ts` — intentional (pixel reproducibility).
- `tests/visual/interaction.spec.ts` — intentional for the action-path scenarios (need deterministic failure modes).
- `tests/vision/vision.spec.ts` (Claude API path) — intentional fixtures.

## WHAT IS EXPLICITLY NOT RELIABLE

- `active_nav_styling` on sidebar links (gemma3:4b: 0/3 probe iter, confidently wrong). DOM-only for nav state.
- Any region below `VISION_REGION_MIN` in `tests/visual/helpers.ts` (120×60 px, 12 px font).
- llava:7b and llama3.2-vision:11b (verdict unchanged since 2026-04-20).

---

## IMMEDIATE (can be done now)

### VS-7: More live backend scenarios (read-only)
- **Status:** ✅ DONE (2026-04-22)
- **What was done:** added `live: jobs page renders real /jobs` in `tests/visual/live-backend.spec.ts`. Backend GET /jobs returns `[]` on dev → DOM shows `jobs.history.empty` with "Задач ещё не было" + both preset cards visible; vision `detectPanelVisibility` on `.jobs-history-panel` confirmed panel_visible=true, primary_label="не было", confidence=1.00, cross-check confirmed. No POSTs, read-only.
- **Verified 2026-04-22:** 8/8 vision tests pass — 4 interaction + 3 live-backend (health, runtime, jobs) + 1 region-guardrail.
- **Non-goal kept:** live telegram scenario — requires a real token and sends external traffic; remains fixture-only.

### VS-8: Region-size guardrails in the vision helpers
- **Status:** ✅ DONE (2026-04-21)
- **What was done:**
  - All 4 classifiers (`classifyElementState`, `detectActionBanner`, `detectErrorText`, `detectPanelVisibility`) now accept a `Locator` and measure it via `measureRegion()` before any model call.
  - Below-minimum regions return `{ _too_small: true, confidence: 0, attempt: 0, latency_ms: 0, reason: "region too small for reliable vision analysis (got WxH, font=Npx; require >=120x60 with font>=12px)" }` and are never sent to Ollama.
  - Sentinel result values (e.g. `badge="UNKNOWN"`, `has_error=false`) keep the return shape stable so callers do not crash, but every scenario callsite additionally asserts `_too_small === false` as a hard gate.
  - New spec `tests/visual/region-guardrail.spec.ts` — proves: tiny nav link (254x48) → all 3 classifiers skip with `latency=0ms, confidence=0, attempt=0`; full body → classifier DOES call model (guardrail does not over-block).
- **Verified 2026-04-21:** 7/7 vision tests pass (interaction + live-backend + guardrail) with the new gate in place; 1/1 agent_audit unchanged.

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
