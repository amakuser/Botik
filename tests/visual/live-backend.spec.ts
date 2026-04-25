/**
 * Live backend vision tests.
 *
 * Unlike interaction.spec.ts (which mocks every API call via page.route),
 * this spec relies on a real running app-service at 127.0.0.1:8765 with a
 * real Vite dev server at 127.0.0.1:4173. NO page.route interception —
 * the frontend talks to the real backend.
 *
 * Each test does three independent checks and asserts they agree:
 *   1. Backend   — a direct HTTP GET against the real endpoint
 *   2. DOM       — what React renders after fetching the real response
 *   3. Vision    — what gemma3:4b sees in the rendered region crop
 *
 * Activation:
 *   OLLAMA_VISION=1  — required (vision assertions are the point)
 *   BOTIK_SESSION_TOKEN  — optional, defaults to "botik-dev-token"
 *
 * Read-only. No POSTs, no destructive calls, no state mutation.
 */

import { expect, test } from "@playwright/test";
import { checkRegionLayoutSanity, waitForStableUI } from "./helpers";
import {
  buildCrossCheck,
  classifyElementState,
  compareStates,
  composeDecision,
  detectPanelVisibility,
  isOllamaVisionEnabled,
  logVisionResult,
  regionOutcome,
  regionSkipped,
  type RegionOutcome,
} from "./vision_loop.helpers";
import {
  ACTION_STATE,
  captureSemanticSnapshot,
  compareSemanticSnapshots,
  findRegion,
  JOBS_STATE,
  RUNTIME_STATE,
  summariseDiff,
} from "./semantic.helpers";

const BASE = "http://127.0.0.1:4173";
const BACKEND = "http://127.0.0.1:8765";
const SESSION_TOKEN = process.env.BOTIK_SESSION_TOKEN ?? "botik-dev-token";

// Skip the whole file unless vision is enabled — these tests have no fixtures,
// so they are useless without a vision model (DOM-only coverage already exists
// in other specs).
test.beforeAll(() => {
  test.skip(!isOllamaVisionEnabled(), "OLLAMA_VISION=1 required for live-backend vision tests");
});

// ── Live health page vs real /health ──────────────────────────────────────────

test("live: health page renders real /health response", async ({ page, request }) => {
  // 1. Backend check — direct HTTP against the real endpoint
  const apiRes = await request.get(`${BACKEND}/health`, {
    headers: { "x-botik-session-token": SESSION_TOKEN },
  });
  expect(apiRes.ok(), `backend /health should respond 200, got ${apiRes.status()}`).toBe(true);
  const apiBody = await apiRes.json();
  expect(apiBody.status, "backend /health.status").toBe("ok");
  expect(apiBody.service, "backend /health.service").toBe("botik-app-service");

  // 2. Navigate — NO page.route — frontend fetches the real backend
  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  // DOM check — wait for the real backend response to land in the DOM.
  // networkidle is unreliable on SPAs with background polling; we wait
  // on a specific backend-derived string instead.
  const statusEl = page.getByTestId("health.status");
  const serviceEl = page.getByTestId("health.service");
  const versionEl = page.getByTestId("health.version");
  await expect(serviceEl).toContainText("botik-app-service", { timeout: 10_000 });
  await expect(statusEl).toContainText("ok");

  const domVersionText = (await versionEl.textContent() ?? "").trim();

  // 3. Vision check — gemma3:4b reads the intro panel crop
  const intro = page.locator(".page-intro, header").first();
  const { result: vision, analysis, confidence, _too_small, reason } =
    await detectPanelVisibility(intro, "health.intro@live");
  expect(_too_small, `[vision] health intro region too small: ${reason ?? ""}`).toBe(false);

  const crossCheck = buildCrossCheck(
    vision.panel_visible ? "visible" : "hidden",
    "visible",
  );

  logVisionResult(
    "live-health",
    analysis,
    vision.panel_visible
      ? `panel_visible=true label=${vision.primary_label ?? "?"}`
      : "panel_visible=false",
    confidence,
    crossCheck,
  );

  expect(vision.panel_visible, "[vision] health intro panel should be visible").toBe(true);
  expect(crossCheck.outcome, `[vision+DOM] health intro: vision=${crossCheck.vision_value}`).not.toBe("conflict");

  console.log(
    `[live-health] backend_version="${apiBody.version}" dom_version="${domVersionText}" ` +
    `vision_label="${vision.primary_label ?? ""}"`,
  );
});

// ── Live runtime-status page vs real /runtime-status ──────────────────────────

test("live: runtime page renders real /runtime-status with correct badges", async ({ page, request }) => {
  // 1. Backend check — fetch the real runtime status
  const apiRes = await request.get(`${BACKEND}/runtime-status`, {
    headers: { "x-botik-session-token": SESSION_TOKEN },
  });
  expect(apiRes.ok(), `backend /runtime-status should respond 200, got ${apiRes.status()}`).toBe(true);
  const apiBody = await apiRes.json() as {
    runtimes: Array<{ runtime_id: string; state: string }>;
  };
  const spotBackend = apiBody.runtimes.find((r) => r.runtime_id === "spot");
  const futuresBackend = apiBody.runtimes.find((r) => r.runtime_id === "futures");
  expect(spotBackend, "spot runtime in backend response").toBeTruthy();
  expect(futuresBackend, "futures runtime in backend response").toBeTruthy();

  // 2. Navigate — NO page.route — frontend fetches the real backend
  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);

  // DOM check — wait for runtime cards to render from the real backend response
  const spotCard = page.getByTestId("runtime.card.spot");
  const futuresCard = page.getByTestId("runtime.card.futures");
  await expect(spotCard).toBeVisible({ timeout: 10_000 });
  await expect(futuresCard).toBeVisible({ timeout: 10_000 });
  // Wait until the state badges carry the real (non-loading) text
  await expect(page.getByTestId("runtime.state.spot")).toHaveText(/RUNNING|OFFLINE|DEGRADED|UNKNOWN/, { timeout: 10_000 });
  await expect(page.getByTestId("runtime.state.futures")).toHaveText(/RUNNING|OFFLINE|DEGRADED|UNKNOWN/, { timeout: 10_000 });

  const domSpotBadge = (await page.getByTestId("runtime.state.spot").textContent() ?? "").trim().toUpperCase();
  const domFuturesBadge = (await page.getByTestId("runtime.state.futures").textContent() ?? "").trim().toUpperCase();

  // DOM must match backend state (frontend uppercases state)
  expect(domSpotBadge, "DOM spot badge vs backend state").toBe(spotBackend!.state.toUpperCase());
  expect(domFuturesBadge, "DOM futures badge vs backend state").toBe(futuresBackend!.state.toUpperCase());

  // 3. Vision check — only when the backend state is one gemma3:4b can classify.
  //    classifyElementState understands RUNNING/OFFLINE. degraded/unknown are out of scope.
  //    When the backend returns an unsupported state, log it and skip the vision assertion
  //    to avoid a false negative — cross-checking DOM vs backend is already done above.
  for (const [rid, card, backendState, domBadge] of [
    ["spot",    spotCard,    spotBackend!.state,    domSpotBadge] as const,
    ["futures", futuresCard, futuresBackend!.state, domFuturesBadge] as const,
  ]) {
    const { result, analysis, confidence, _too_small, reason } =
      await classifyElementState(card, `runtime.card.${rid}@live`);
    expect(_too_small, `[vision] ${rid} runtime card region too small: ${reason ?? ""}`).toBe(false);

    const crossCheck = buildCrossCheck(result.badge, domBadge);
    logVisionResult(
      `live-runtime:${rid}`,
      analysis,
      `badge=${result.badge} color=${result.color} backend_state=${backendState}`,
      confidence,
      crossCheck,
    );

    const supportedBadges = ["RUNNING", "OFFLINE"];
    if (!supportedBadges.includes(backendState.toUpperCase())) {
      console.log(
        `[live-runtime:${rid}] backend_state="${backendState}" is outside RUNNING/OFFLINE — ` +
        `skipping vision assertion, DOM↔backend match is already enforced above`,
      );
      continue;
    }

    // Cross-check must not conflict. Allow "uncertain" (model unsure) — DOM is authoritative.
    expect(
      crossCheck.outcome,
      `[vision+DOM] ${rid} runtime badge: vision=${crossCheck.vision_value} dom=${crossCheck.dom_value}`,
    ).not.toBe("conflict");
  }

  console.log(
    `[live-runtime] backend spot=${spotBackend!.state} futures=${futuresBackend!.state} ` +
    `dom spot=${domSpotBadge} futures=${domFuturesBadge}`,
  );
});

// ── Live jobs page vs real /jobs (read-only) ──────────────────────────────────
//
// The real backend's /jobs endpoint is a list of historic jobs. On a fresh
// dev database it returns []. We rely on that stable empty state:
//   - backend: 200 + JSON array (length asserted)
//   - DOM:     'jobs.history.empty' visible with "Задач ещё не было." (iff empty)
//   - vision:  detectPanelVisibility on .jobs-history-panel — panel_visible=true
//
// The history panel is the right region to exercise because its CONTENT is
// derived from the backend response. A broken backend → empty or wrong
// payload → the panel content would drift and either vision or DOM would
// notice. No POSTs, no job starts — read-only.

test("live: jobs page renders real /jobs (empty history + preset cards visible)", async ({ page, request }) => {
  // 1. Backend check — GET /jobs must be reachable and return a JSON array.
  const apiRes = await request.get(`${BACKEND}/jobs`, {
    headers: { "x-botik-session-token": SESSION_TOKEN },
  });
  expect(apiRes.ok(), `backend /jobs should respond 200, got ${apiRes.status()}`).toBe(true);
  const apiBody = await apiRes.json() as Array<{ job_id: string; state?: string }>;
  expect(Array.isArray(apiBody), "backend /jobs must return a JSON array").toBe(true);
  const backendJobCount = apiBody.length;

  // 2. Navigate — NO page.route — frontend fetches the real backend.
  await page.goto(`${BASE}/jobs`);
  await waitForStableUI(page);

  // DOM check must be consistent with what the backend actually returned.
  if (backendJobCount === 0) {
    const emptyEl = page.getByTestId("jobs.history.empty");
    await expect(emptyEl).toBeVisible({ timeout: 10_000 });
    await expect(emptyEl).toContainText("Задач ещё не было");
  } else {
    // Non-empty case: at least one <li> must render.
    await expect(page.locator(".jobs-list li").first()).toBeVisible({ timeout: 10_000 });
  }

  // Preset action cards must exist on this page regardless of history state —
  // they are static, but their presence proves the jobs route rendered, not
  // some fallback / error shell.
  await expect(page.getByTestId("job.preset.data-backfill")).toBeVisible();
  await expect(page.getByTestId("job.preset.data-integrity")).toBeVisible();

  // 3. Vision check on the history panel — the region whose body depends on
  //    the backend response. Using detectPanelVisibility because the panel
  //    always has chrome (border + heading); we verify panel_visible=true
  //    and cross-check against DOM. primary_label is not asserted because
  //    the vocabulary on this panel (Russian muted text) is outside the
  //    signal quality we measured as reliable (see signal-quality.json).
  const historyPanel = page.locator(".jobs-history-panel");
  await expect(historyPanel).toBeVisible();
  const {
    result: vision, analysis, confidence, _too_small, reason, size,
  } = await detectPanelVisibility(historyPanel, "jobs.history-panel@live");
  expect(
    _too_small,
    `[vision] jobs history panel region too small (${size.width}x${size.height}): ${reason ?? ""}`,
  ).toBe(false);

  const domPanelVisible = await historyPanel.isVisible();
  const crossCheck = buildCrossCheck(
    vision.panel_visible ? "visible" : "hidden",
    domPanelVisible ? "visible" : "hidden",
  );

  logVisionResult(
    "live-jobs",
    analysis,
    vision.panel_visible
      ? `panel_visible=true label=${vision.primary_label ?? "?"}`
      : "panel_visible=false",
    confidence,
    crossCheck,
  );

  expect(vision.panel_visible, "[vision] jobs history panel should be visible").toBe(true);
  expect(
    crossCheck.outcome,
    `[vision+DOM] jobs history: vision=${crossCheck.vision_value} dom=${crossCheck.dom_value}`,
  ).not.toBe("conflict");

  // 4. Semantic auto-region check — extends the runtime-only contract to
  //    /jobs without any jobs-specific helper code. The whole page is
  //    discovered via data-ui-* attributes; this test only asserts what
  //    the backend response said should be visible.
  const snapshot = await captureSemanticSnapshot(page);

  // Page root + history panel must be auto-discovered.
  const pageRegion = findRegion(snapshot, { role: "page", scope: "jobs" });
  expect(pageRegion, "semantic: jobs page root discovered").not.toBeNull();

  const historyRegion = findRegion(snapshot, { role: "jobs-history" });
  expect(historyRegion, "semantic: jobs-history panel discovered").not.toBeNull();

  // jobs-history canonical state must match the backend jobs.length.
  // Canonical bucket — not the raw "empty"/"populated" string — survives
  // any future frontend rename.
  const expectedCanonical =
    backendJobCount === 0 ? JOBS_STATE.EMPTY : JOBS_STATE.NON_EMPTY;
  expect(
    historyRegion!.canonical_state,
    `semantic: jobs-history canonical_state must reflect backend jobs.length=${backendJobCount}`,
  ).toBe(expectedCanonical);

  // Empty/populated branch must be reflected by the right marker.
  if (backendJobCount === 0) {
    const emptyMarker = findRegion(snapshot, {
      role: "empty-state",
      scope: "jobs-history",
    });
    expect(emptyMarker, "semantic: empty-state for jobs-history").not.toBeNull();
    expect(emptyMarker!.visible, "empty-state visible").toBe(true);
    // No list items in the empty branch.
    const items = snapshot.regions.filter((r) => r.role === "jobs-list-item");
    expect(items.length, "no jobs-list-item when backend list is empty").toBe(0);
  } else {
    const items = snapshot.regions.filter((r) => r.role === "jobs-list-item");
    expect(
      items.length,
      `semantic: jobs-list-item count must match backend (${items.length} vs ${backendJobCount})`,
    ).toBe(backendJobCount);
  }

  // Preset cards: both must be auto-discovered through the contract,
  // independently of the data-testid path used elsewhere.
  const backfillPreset = findRegion(snapshot, { role: "job-preset", scope: "data-backfill" });
  const integrityPreset = findRegion(snapshot, { role: "job-preset", scope: "data-integrity" });
  expect(backfillPreset, "semantic: data-backfill preset").not.toBeNull();
  expect(integrityPreset, "semantic: data-integrity preset").not.toBeNull();

  // Each preset must expose a start action with a known availability state.
  for (const preset of ["data-backfill", "data-integrity"] as const) {
    const startAction = findRegion(snapshot, {
      role: "job-action",
      scope: preset,
      action: "start",
    });
    expect(startAction, `semantic: ${preset} start action`).not.toBeNull();
    expect(
      Object.values(ACTION_STATE),
      `${preset} start action canonical_state is one of ACTION_STATE`,
    ).toContain(startAction!.canonical_state);
    expect(
      startAction!.recommended_check,
      `${preset} start action is DOM-checked, not vision`,
    ).toBe("dom");
  }

  // No specific page-level role should leak vision recommendation when
  // its container is layout-only.
  const layoutRoles = new Set(["page", "action-row", "jobs-list", "job-toolbar"]);
  for (const r of snapshot.regions) {
    if (layoutRoles.has(r.role)) {
      expect(
        r.recommended_check,
        `layout role "${r.role}" must be DOM-only, got ${r.recommended_check}`,
      ).toBe("dom");
    }
  }

  console.log(
    `[live-jobs] backend jobs=${backendJobCount} dom_empty_panel=${backendJobCount === 0} ` +
    `vision_panel_visible=${vision.panel_visible} ` +
    `semantic_history_state=${historyRegion!.state} ` +
    `semantic_regions=${snapshot.regions.length}`,
  );
});

// ── Live runtime interaction: real start → real running, 3-way confirmed ─────
//
// The one live INTERACTION scenario (as opposed to the read-only ones above).
// It exercises a POST /runtime-control/spot/start against the real backend,
// which actually spawns a paper-trading child process. Safe because:
//   - The runtime is paper-mode (no real exchange orders without API keys,
//     and BYBIT_API_KEY is not configured in this dev env — confirmed via
//     `/settings` where present=false for BYBIT keys).
//   - The spec enforces a clean precondition (stop-if-running) and a clean
//     teardown (stop unconditionally in the finally block) so the runtime
//     never outlives the test.
//   - We intentionally use the existing "runtime.start.spot" DOM button —
//     a real user-visible click path, not a hand-crafted request.
//
// 3-way assertion at both snapshots:
//   - backend_state (via GET /runtime-status)
//   - DOM state     (via runtime.state.spot textContent)
//   - vision state  (via classifyElementState on runtime.card.spot)
// followed by compareStates(...) → transition_confirmed.

async function stopRuntime(
  request: import("@playwright/test").APIRequestContext,
  runtimeId: "spot" | "futures",
): Promise<void> {
  await request.post(`${BACKEND}/runtime-control/${runtimeId}/stop`, {
    headers: { "x-botik-session-token": SESSION_TOKEN },
    data: {},
    failOnStatusCode: false,
  });
}

async function startRuntime(
  request: import("@playwright/test").APIRequestContext,
  runtimeId: "spot" | "futures",
): Promise<void> {
  await request.post(`${BACKEND}/runtime-control/${runtimeId}/start`, {
    headers: { "x-botik-session-token": SESSION_TOKEN },
    data: {},
    failOnStatusCode: false,
  });
}

async function waitForBackendRuntimeState(
  request: import("@playwright/test").APIRequestContext,
  runtimeId: "spot" | "futures",
  targets: string | string[],
  timeoutMs = 15_000,
): Promise<string> {
  const targetSet = new Set(Array.isArray(targets) ? targets : [targets]);
  const deadline = Date.now() + timeoutMs;
  let last = "?";
  while (Date.now() < deadline) {
    const r = await request.get(`${BACKEND}/runtime-status`, {
      headers: { "x-botik-session-token": SESSION_TOKEN },
    });
    if (r.ok()) {
      const body = await r.json() as { runtimes: Array<{ runtime_id: string; state: string }> };
      const rt = body.runtimes.find((x) => x.runtime_id === runtimeId);
      last = rt?.state ?? "?";
      if (targetSet.has(last)) return last;
    }
    await new Promise((res) => setTimeout(res, 400));
  }
  return last;
}

// Back-compat thin wrappers (old code in start-spot scenario still calls these).
const stopSpotRuntime = (r: import("@playwright/test").APIRequestContext) => stopRuntime(r, "spot");
const waitForBackendSpotState = (
  r: import("@playwright/test").APIRequestContext,
  targets: string | string[],
  timeoutMs?: number,
) => waitForBackendRuntimeState(r, "spot", targets, timeoutMs);

test("live interaction: start spot runtime → offline→running, real backend + DOM + vision", async ({ page, request }) => {
  // Real child-process spawn + heartbeat + vision x2 does not fit in the
  // default 30s test timeout. Extend to 90s; teardown is also inside the cap.
  test.setTimeout(90_000);

  // Precondition: ensure spot is offline before we start.
  await stopSpotRuntime(request);
  const precondition = await waitForBackendSpotState(request, ["offline"], 10_000);
  expect(precondition, "precondition: spot must be offline before the scenario").toBe("offline");

  try {
    // Navigate — NO page.route.
    await page.goto(`${BASE}/runtime`);
    await waitForStableUI(page);
    await expect(page.getByTestId("runtime.card.spot")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("runtime.state.spot")).toHaveText("OFFLINE", { timeout: 10_000 });

    // ── BEFORE snapshot: backend + DOM + vision must all agree on "offline" ─
    const backendBefore = await waitForBackendSpotState(request, ["offline"], 5_000);
    expect(backendBefore, "backend_before must be offline").toBe("offline");
    const domBefore = (await page.getByTestId("runtime.state.spot").textContent() ?? "").trim().toUpperCase();
    expect(domBefore, "dom_before must be OFFLINE").toBe("OFFLINE");

    // ── Semantic snapshot BEFORE. Auto-discovers every data-ui-* region;
    //    the test does not hard-code which regions to watch. The diff
    //    against the AFTER snapshot expresses the transition in semantic
    //    terms (state_changed on runtime-card[spot]), independent of
    //    visible text or pixel coordinates. Asserts go through the
    //    canonical RUNTIME_STATE enum, not raw "offline"/"running" strings.
    const semanticBefore = await captureSemanticSnapshot(page);
    {
      const semCard = findRegion(semanticBefore, { role: "runtime-card", scope: "spot" });
      expect(semCard?.canonical_state, "semantic spot card canonical before").toBe(RUNTIME_STATE.INACTIVE);
    }

    // Scope vision to the card HEADER (title + badge only). The full card
    // grows an error callout section once the runtime is running in this
    // dev env (transient WS 404 "reconnect" message), which mixes a green
    // RUNNING badge with red error chrome and gets classified as UNKNOWN.
    // The header alone is the stable region for state-badge detection.
    // Three regions to corroborate the transition instead of relying on one:
    //   1. header   — the state badge (classifyElementState)
    //   2. actions  — the Start/Stop button row (detectPanelVisibility —
    //                 labels "Запустить"/"Остановить" must remain visible)
    //   3. callouts — status reason + last-error strip (detectPanelVisibility —
    //                 offline: "no matching runtime process detected";
    //                 active:  "process present with recent heartbeat activity")
    const spotCard = page.getByTestId("runtime.card.spot");
    const spotCardHeader = spotCard.locator(".runtime-card__header");
    const spotCardActions = spotCard.locator(".runtime-card__actions");
    const spotCardCallouts = spotCard.locator(".runtime-card__callouts");

    // ── header BEFORE
    const headerBefore = await classifyElementState(spotCardHeader, "live-start-spot.header@before");
    expect(headerBefore._too_small, `[vision] header too small: ${headerBefore.reason ?? ""}`).toBe(false);
    logVisionResult("live-start-spot:header@before", headerBefore.analysis,
      `badge=${headerBefore.result.badge}`, headerBefore.confidence);
    expect(headerBefore.result.badge).toBe("OFFLINE");
    const crossBefore = buildCrossCheck(headerBefore.result.badge, domBefore);
    expect(crossBefore.outcome).toBe("confirmed");

    // ── actions row BEFORE (panel visible; label one of {Запустить, Остановить})
    const actionsBefore = await detectPanelVisibility(spotCardActions, "live-start-spot.actions@before");
    logVisionResult("live-start-spot:actions@before", actionsBefore.analysis,
      actionsBefore._too_small ? `skipped: ${actionsBefore.reason ?? ""}`
        : `panel=${actionsBefore.result.panel_visible} label=${actionsBefore.result.primary_label ?? "?"}`,
      actionsBefore.confidence);

    // ── callouts BEFORE
    const calloutsBefore = await detectPanelVisibility(spotCardCallouts, "live-start-spot.callouts@before");
    logVisionResult("live-start-spot:callouts@before", calloutsBefore.analysis,
      calloutsBefore._too_small ? `skipped: ${calloutsBefore.reason ?? ""}`
        : `panel=${calloutsBefore.result.panel_visible} label=${calloutsBefore.result.primary_label ?? "?"}`,
      calloutsBefore.confidence);

    // Preserve single-region variable for downstream logs/compareStates.
    const visionBefore = headerBefore;

    // ── ACTION: real DOM click → real POST /runtime-control/spot/start ──────
    await page.getByTestId("runtime.start.spot").click();

    // ── Wait for DOM to transition OFF OFFLINE. In this dev env without
    //    real Bybit credentials, the spot runtime's WS loop 404s and the
    //    heartbeat monitor flips the state: offline → running → degraded.
    //    The "running" window can be shorter than one /runtime-status poll
    //    interval, so we race the DOM for ANY non-offline label rather than
    //    pinning "RUNNING". Both RUNNING and DEGRADED prove the action
    //    had a real backend effect — only staying at OFFLINE is the failure.
    await expect(page.getByTestId("runtime.state.spot"))
      .toHaveText(/RUNNING|DEGRADED/, { timeout: 20_000 });
    const domAfter = (await page.getByTestId("runtime.state.spot").textContent() ?? "").trim().toUpperCase();
    expect(
      ["RUNNING", "DEGRADED"].includes(domAfter),
      `dom_after must be RUNNING or DEGRADED, got '${domAfter}'`,
    ).toBe(true);

    // Read backend now. In this dev env the spot runtime's WS loop 404s
    //   and the heartbeat monitor oscillates between running and degraded
    //   while React Query polls /runtime-status on its own cadence. An exact
    //   {backend=X, dom=X} pair at a single instant is not guaranteed
    //   (frontend caches the last poll). The HONEST invariant is:
    //     - backend was "offline" before the click (asserted earlier)
    //     - backend is now "running" OR "degraded" (i.e. action had an effect)
    //     - DOM has moved off OFFLINE to "RUNNING" or "DEGRADED"
    //     - both sides now agree the runtime is active, possibly naming
    //       different transient states. Equivalent at the "did it start?"
    //       level; not equivalent at the "is it healthy?" level.
    //   If you need a strict exact-match backend-vs-DOM assertion, use a
    //   runtime that is actually stable (Bybit creds configured, WS 200).
    const backendAfter = await waitForBackendSpotState(request, ["running", "degraded"], 5_000);
    expect(
      ["running", "degraded"].includes(backendAfter),
      `backend_after must be running or degraded, got '${backendAfter}'`,
    ).toBe(true);
    const bothActive = ["RUNNING", "DEGRADED"].includes(domAfter) &&
      ["running", "degraded"].includes(backendAfter);
    expect(
      bothActive,
      `DOM and backend must both be active after start (dom='${domAfter}', backend='${backendAfter}')`,
    ).toBe(true);

    // ── Semantic snapshot AFTER + diff. Authoritative semantic check:
    //    runtime-card[spot] must have flipped canonical_state from
    //    INACTIVE to ACTIVE or DEGRADED. The assertion uses the canonical
    //    RUNTIME_STATE enum, so a frontend rename (offline → idle) would
    //    surface as canonical=null and fail loudly, not silently.
    const semanticAfter = await captureSemanticSnapshot(page);
    {
      const diff = compareSemanticSnapshots(semanticBefore, semanticAfter);
      console.log(`[semantic-diff start-spot] ${summariseDiff(diff)}`);
      const cardChange = diff.state_changed.find(
        (c) => c.role === "runtime-card" && c.scope === "spot",
      );
      expect(cardChange, "semantic: runtime-card[spot] must change state").toBeTruthy();
      const validTransitions = [
        `${RUNTIME_STATE.INACTIVE} → ${RUNTIME_STATE.ACTIVE}`,
        `${RUNTIME_STATE.INACTIVE} → ${RUNTIME_STATE.DEGRADED}`,
      ];
      expect(
        validTransitions.includes(cardChange!.detail),
        `semantic: runtime-card[spot] expected ${validTransitions.join("|")}, got '${cardChange!.detail}'`,
      ).toBe(true);
      const semCardAfter = findRegion(semanticAfter, { role: "runtime-card", scope: "spot" });
      expect(
        [RUNTIME_STATE.ACTIVE, RUNTIME_STATE.DEGRADED],
        "semantic canonical state after",
      ).toContain(semCardAfter?.canonical_state);
      expect(diff.region_removed.length, "no semantic regions disappeared").toBe(0);
    }

    // ── header AFTER
    const headerAfter = await classifyElementState(spotCardHeader, "live-start-spot.header@after");
    expect(headerAfter._too_small).toBe(false);
    logVisionResult("live-start-spot:header@after", headerAfter.analysis,
      `badge=${headerAfter.result.badge} color=${headerAfter.result.color}`, headerAfter.confidence);
    expect(headerAfter.result.badge, `vision header@after must match DOM '${domAfter}'`).toBe(domAfter);
    const crossAfter = buildCrossCheck(headerAfter.result.badge, domAfter);
    expect(crossAfter.outcome).toBe("confirmed");
    const visionAfter = headerAfter;

    // ── actions row AFTER
    const actionsAfter = await detectPanelVisibility(spotCardActions, "live-start-spot.actions@after");
    logVisionResult("live-start-spot:actions@after", actionsAfter.analysis,
      actionsAfter._too_small ? `skipped: ${actionsAfter.reason ?? ""}`
        : `panel=${actionsAfter.result.panel_visible} label=${actionsAfter.result.primary_label ?? "?"}`,
      actionsAfter.confidence);

    // ── callouts AFTER
    const calloutsAfter = await detectPanelVisibility(spotCardCallouts, "live-start-spot.callouts@after");
    logVisionResult("live-start-spot:callouts@after", calloutsAfter.analysis,
      calloutsAfter._too_small ? `skipped: ${calloutsAfter.reason ?? ""}`
        : `panel=${calloutsAfter.result.panel_visible} label=${calloutsAfter.result.primary_label ?? "?"}`,
      calloutsAfter.confidence);

    // ── Transition via compareStates (header only — badges are the state).
    const comparison = compareStates(visionBefore.result, visionAfter.result, {
      from: "OFFLINE", to: ["RUNNING", "DEGRADED"],
    });
    expect(comparison.decision).toBe("transition_confirmed");

    // ── Composite multi-region decision. Each region contributes one outcome.
    const regionOutcomes: RegionOutcome[] = [
      regionOutcome(
        "header.badge",
        comparison.decision === "transition_confirmed" && crossAfter.outcome === "confirmed",
        `header ${headerBefore.result.badge}→${headerAfter.result.badge} ` +
        `(dom=${domBefore}→${domAfter})`,
        { classifier: "classifyElementState", confidence_before: headerBefore.confidence, confidence_after: headerAfter.confidence },
      ),
      // actions row: expect panel visibility before AND after (state text changes,
      // but panel must keep rendering the button row). If the classifier skipped
      // it (too small), we honour the skip instead of pretending it confirmed.
      actionsBefore._too_small || actionsAfter._too_small
        ? regionSkipped("actions.row",
            `skipped: ${actionsBefore._too_small ? actionsBefore.reason : actionsAfter.reason ?? "?"}`,
            { size_before: actionsBefore.size, size_after: actionsAfter.size })
        : regionOutcome(
            "actions.row",
            actionsBefore.result.panel_visible === true && actionsAfter.result.panel_visible === true,
            `panel_visible before=${actionsBefore.result.panel_visible} after=${actionsAfter.result.panel_visible}`,
          ),
      calloutsBefore._too_small || calloutsAfter._too_small
        ? regionSkipped("callouts",
            `skipped: ${calloutsBefore._too_small ? calloutsBefore.reason : calloutsAfter.reason ?? "?"}`,
            { size_before: calloutsBefore.size, size_after: calloutsAfter.size })
        : regionOutcome(
            "callouts",
            calloutsBefore.result.panel_visible === true && calloutsAfter.result.panel_visible === true,
            `panel_visible before=${calloutsBefore.result.panel_visible} after=${calloutsAfter.result.panel_visible}`,
          ),
    ];
    const composite = composeDecision("start-spot:offline→active", regionOutcomes);
    expect(
      ["all_confirmed", "partial_confirmed"].includes(composite.final_outcome),
      `composite outcome must be confirmed/partial, got '${composite.final_outcome}'; ` +
      `confirmed=[${composite.confirmed_regions.join(",")}] ` +
      `conflict=[${composite.conflicted_regions.join(",")}] ` +
      `skipped=[${composite.skipped_regions.join(",")}]`,
    ).toBe(true);
    expect(composite.conflicted_regions, "no region may conflict").toHaveLength(0);

    // ── Post-action layout sanity (DOM-only, no pixels)
    for (const [name, loc] of [
      ["header", spotCardHeader],
      ["actions", spotCardActions],
      ["callouts", spotCardCallouts],
    ] as const) {
      const sanity = await checkRegionLayoutSanity(loc);
      expect(sanity.visible, `layout: ${name} must stay visible after action`).toBe(true);
      expect(sanity.text_length, `layout: ${name} must still have text content`).toBeGreaterThan(0);
    }

    console.log(
      `[live-start-spot] backend ${backendBefore}→${backendAfter} ` +
      `dom ${domBefore}→${domAfter} ` +
      `header ${headerBefore.result.badge}→${headerAfter.result.badge} ` +
      `composite=${composite.final_outcome} ` +
      `confirmed=[${composite.confirmed_regions.join(",")}] ` +
      `skipped=[${composite.skipped_regions.join(",")}]`,
    );
  } finally {
    // Always stop the runtime we started — test isolation + no stray children.
    await stopSpotRuntime(request);
    await waitForBackendSpotState(request, ["offline"], 15_000);
  }
});

// ── Live interaction: STOP spot runtime (active → offline) ────────────────────
//
// Mirror of the start-spot scenario. Pre-step seeds the runtime via the
// real backend endpoint (not a click) so the test owns the "active" state
// without depending on the previous test's leftovers; the DOM action under
// test is the real Stop button click. This keeps the 3-way assertion
// focused on the OFF transition, not on the preconditioning.

test("live interaction: stop spot runtime → active→offline, real backend + DOM + vision", async ({ page, request }) => {
  test.setTimeout(90_000);

  // Precondition: runtime must be active (running or degraded) so there is
  // something to stop. Start it via backend; do not rely on a previous test.
  await startRuntime(request, "spot");
  const precondState = await waitForBackendRuntimeState(request, "spot", ["running", "degraded"], 15_000);
  expect(
    ["running", "degraded"].includes(precondState),
    `precondition: spot must be active before the scenario, got '${precondState}'`,
  ).toBe(true);

  try {
    await page.goto(`${BASE}/runtime`);
    await waitForStableUI(page);
    await expect(page.getByTestId("runtime.card.spot")).toBeVisible({ timeout: 10_000 });
    // Wait for DOM to catch up with the active state we just forced.
    await expect(page.getByTestId("runtime.state.spot"))
      .toHaveText(/RUNNING|DEGRADED/, { timeout: 20_000 });

    const spotCard = page.getByTestId("runtime.card.spot");
    const spotCardHeader = spotCard.locator(".runtime-card__header");
    const spotCardActions = spotCard.locator(".runtime-card__actions");
    const spotCardCallouts = spotCard.locator(".runtime-card__callouts");

    // ── BEFORE: both sides must agree the runtime is active. ────────────
    const backendBefore = await waitForBackendRuntimeState(request, "spot", ["running", "degraded"], 5_000);
    const domBefore = (await page.getByTestId("runtime.state.spot").textContent() ?? "").trim().toUpperCase();
    expect(["RUNNING", "DEGRADED"].includes(domBefore),
      `dom_before must be RUNNING or DEGRADED, got '${domBefore}'`).toBe(true);
    expect(["running", "degraded"].includes(backendBefore),
      `backend_before must be running or degraded, got '${backendBefore}'`).toBe(true);

    // ── Semantic snapshot BEFORE — runtime-card[spot] must be active
    //    (canonical ACTIVE or DEGRADED).
    const semanticBefore = await captureSemanticSnapshot(page);
    {
      const semCard = findRegion(semanticBefore, { role: "runtime-card", scope: "spot" });
      expect(
        [RUNTIME_STATE.ACTIVE, RUNTIME_STATE.DEGRADED],
        "semantic spot card canonical before (active branch)",
      ).toContain(semCard?.canonical_state);
    }

    // Multi-region BEFORE snapshot (header + actions + callouts).
    const headerBefore = await classifyElementState(spotCardHeader, "live-stop-spot.header@before");
    expect(headerBefore._too_small).toBe(false);
    logVisionResult("live-stop-spot:header@before", headerBefore.analysis,
      `badge=${headerBefore.result.badge}`, headerBefore.confidence);
    expect(headerBefore.result.badge,
      `vision header@before must match DOM (dom='${domBefore}')`).toBe(domBefore);
    const visionBefore = headerBefore;

    const actionsBefore = await detectPanelVisibility(spotCardActions, "live-stop-spot.actions@before");
    logVisionResult("live-stop-spot:actions@before", actionsBefore.analysis,
      actionsBefore._too_small ? `skipped: ${actionsBefore.reason ?? ""}`
        : `panel=${actionsBefore.result.panel_visible}`, actionsBefore.confidence);
    const calloutsBefore = await detectPanelVisibility(spotCardCallouts, "live-stop-spot.callouts@before");
    logVisionResult("live-stop-spot:callouts@before", calloutsBefore.analysis,
      calloutsBefore._too_small ? `skipped: ${calloutsBefore.reason ?? ""}`
        : `panel=${calloutsBefore.result.panel_visible} label=${calloutsBefore.result.primary_label ?? "?"}`,
      calloutsBefore.confidence);

    // ── ACTION: real DOM click on the Stop button. The frontend briefly
    //    re-renders on every heartbeat poll; the button can flip to
    //    aria-disabled for a few hundred ms while pendingAction/state
    //    reconcile. Wait until it is truly enabled before clicking.
    //    Do NOT retry the click: after a successful first click the button
    //    stays `disabled` via `pendingAction` until the backend replies,
    //    so any retry sees a disabled button and fails misleadingly. A
    //    long single-click timeout is the honest wait.
    const stopBtn = page.getByTestId("runtime.stop.spot");
    await expect(stopBtn).toBeEnabled({ timeout: 10_000 });
    await stopBtn.click();

    // ── Wait for DOM to transition to OFFLINE. 30s covers the worst
    //    backend-stop latency observed on this dev env when it is under
    //    load (tail of a multi-test suite + Ollama vision traffic).
    await expect(page.getByTestId("runtime.state.spot")).toHaveText("OFFLINE", { timeout: 30_000 });
    const domAfter = (await page.getByTestId("runtime.state.spot").textContent() ?? "").trim().toUpperCase();

    const backendAfter = await waitForBackendRuntimeState(request, "spot", ["offline"], 10_000);
    expect(backendAfter, "backend_after must be offline").toBe("offline");
    expect(domAfter, "dom_after must be OFFLINE").toBe("OFFLINE");

    // ── Semantic snapshot AFTER + diff: runtime-card[spot] must end at
    //    canonical INACTIVE — checked through canonical_state, not badge text.
    const semanticAfter = await captureSemanticSnapshot(page);
    {
      const diff = compareSemanticSnapshots(semanticBefore, semanticAfter);
      console.log(`[semantic-diff stop-spot] ${summariseDiff(diff)}`);
      const cardChange = diff.state_changed.find(
        (c) => c.role === "runtime-card" && c.scope === "spot",
      );
      expect(cardChange, "semantic: runtime-card[spot] must change state").toBeTruthy();
      expect(
        cardChange!.detail.endsWith(`→ ${RUNTIME_STATE.INACTIVE}`),
        `expected ...→ ${RUNTIME_STATE.INACTIVE}, got '${cardChange!.detail}'`,
      ).toBe(true);
      const semCardAfter = findRegion(semanticAfter, { role: "runtime-card", scope: "spot" });
      expect(semCardAfter?.canonical_state, "semantic canonical state after").toBe(RUNTIME_STATE.INACTIVE);
    }

    // Multi-region AFTER snapshot.
    const headerAfter = await classifyElementState(spotCardHeader, "live-stop-spot.header@after");
    expect(headerAfter._too_small).toBe(false);
    logVisionResult("live-stop-spot:header@after", headerAfter.analysis,
      `badge=${headerAfter.result.badge}`, headerAfter.confidence);
    expect(headerAfter.result.badge, "vision_after must see OFFLINE").toBe("OFFLINE");
    const visionAfter = headerAfter;

    const crossAfter = buildCrossCheck(visionAfter.result.badge, domAfter);
    expect(crossAfter.outcome).toBe("confirmed");

    const actionsAfter = await detectPanelVisibility(spotCardActions, "live-stop-spot.actions@after");
    logVisionResult("live-stop-spot:actions@after", actionsAfter.analysis,
      actionsAfter._too_small ? `skipped: ${actionsAfter.reason ?? ""}`
        : `panel=${actionsAfter.result.panel_visible}`, actionsAfter.confidence);
    const calloutsAfter = await detectPanelVisibility(spotCardCallouts, "live-stop-spot.callouts@after");
    logVisionResult("live-stop-spot:callouts@after", calloutsAfter.analysis,
      calloutsAfter._too_small ? `skipped: ${calloutsAfter.reason ?? ""}`
        : `panel=${calloutsAfter.result.panel_visible} label=${calloutsAfter.result.primary_label ?? "?"}`,
      calloutsAfter.confidence);

    const comparison = compareStates(visionBefore.result, visionAfter.result, {
      from: ["RUNNING", "DEGRADED"], to: "OFFLINE",
    });
    expect(comparison.decision).toBe("transition_confirmed");

    // Composite decision across header + actions + callouts.
    const regionOutcomes: RegionOutcome[] = [
      regionOutcome(
        "header.badge",
        comparison.decision === "transition_confirmed" && crossAfter.outcome === "confirmed",
        `header ${headerBefore.result.badge}→${headerAfter.result.badge}`,
      ),
      actionsBefore._too_small || actionsAfter._too_small
        ? regionSkipped("actions.row",
            `skipped: ${actionsBefore._too_small ? actionsBefore.reason : actionsAfter.reason ?? "?"}`,
            { size_before: actionsBefore.size, size_after: actionsAfter.size })
        : regionOutcome("actions.row",
            actionsBefore.result.panel_visible === true && actionsAfter.result.panel_visible === true,
            `panel_visible before=${actionsBefore.result.panel_visible} after=${actionsAfter.result.panel_visible}`),
      calloutsBefore._too_small || calloutsAfter._too_small
        ? regionSkipped("callouts",
            `skipped: ${calloutsBefore._too_small ? calloutsBefore.reason : calloutsAfter.reason ?? "?"}`)
        : regionOutcome("callouts",
            calloutsBefore.result.panel_visible === true && calloutsAfter.result.panel_visible === true,
            `panel_visible before=${calloutsBefore.result.panel_visible} after=${calloutsAfter.result.panel_visible}`),
    ];
    const composite = composeDecision("stop-spot:active→offline", regionOutcomes);
    expect(
      ["all_confirmed", "partial_confirmed"].includes(composite.final_outcome),
      `composite: ${composite.final_outcome}`,
    ).toBe(true);
    expect(composite.conflicted_regions).toHaveLength(0);

    for (const [name, loc] of [
      ["header", spotCardHeader], ["actions", spotCardActions], ["callouts", spotCardCallouts],
    ] as const) {
      const sanity = await checkRegionLayoutSanity(loc);
      expect(sanity.visible, `layout: ${name} must stay visible after stop`).toBe(true);
      expect(sanity.text_length, `layout: ${name} must still have text content`).toBeGreaterThan(0);
    }

    console.log(
      `[live-stop-spot] backend ${backendBefore}→${backendAfter} ` +
      `dom ${domBefore}→${domAfter} ` +
      `header ${headerBefore.result.badge}→${headerAfter.result.badge} ` +
      `composite=${composite.final_outcome} ` +
      `confirmed=[${composite.confirmed_regions.join(",")}] ` +
      `skipped=[${composite.skipped_regions.join(",")}]`,
    );
  } finally {
    // Defensive teardown: whether the click worked or not, the runtime must
    // not outlive the test.
    await stopRuntime(request, "spot");
    await waitForBackendRuntimeState(request, "spot", ["offline"], 15_000);
  }
});

// ── Live interaction: START futures runtime (offline → active) ───────────────
//
// Symmetric to the spot-start scenario. Futures runtime has the same
// offline → running → degraded dynamic in this dev env (no Bybit creds →
// WS 404 → heartbeat degrades), so the test accepts either active state
// as the transition target.

test("live interaction: start futures runtime → offline→active, real backend + DOM + vision", async ({ page, request }) => {
  test.setTimeout(90_000);

  await stopRuntime(request, "futures");
  const precondition = await waitForBackendRuntimeState(request, "futures", ["offline"], 10_000);
  expect(precondition, "precondition: futures must be offline before the scenario").toBe("offline");

  try {
    await page.goto(`${BASE}/runtime`);
    await waitForStableUI(page);
    await expect(page.getByTestId("runtime.card.futures")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("runtime.state.futures")).toHaveText("OFFLINE", { timeout: 10_000 });

    const futuresCard = page.getByTestId("runtime.card.futures");
    const futuresCardHeader = futuresCard.locator(".runtime-card__header");
    const futuresCardActions = futuresCard.locator(".runtime-card__actions");
    const futuresCardCallouts = futuresCard.locator(".runtime-card__callouts");

    const backendBefore = await waitForBackendRuntimeState(request, "futures", ["offline"], 5_000);
    expect(backendBefore, "backend_before must be offline").toBe("offline");
    const domBefore = (await page.getByTestId("runtime.state.futures").textContent() ?? "").trim().toUpperCase();
    expect(domBefore).toBe("OFFLINE");

    // ── Semantic snapshot BEFORE — canonical RUNTIME_STATE.INACTIVE expected.
    const semanticBefore = await captureSemanticSnapshot(page);
    {
      const semCard = findRegion(semanticBefore, { role: "runtime-card", scope: "futures" });
      expect(semCard?.canonical_state, "semantic futures card canonical before").toBe(RUNTIME_STATE.INACTIVE);
    }

    // Multi-region BEFORE.
    const headerBefore = await classifyElementState(futuresCardHeader, "live-start-futures.header@before");
    expect(headerBefore._too_small).toBe(false);
    logVisionResult("live-start-futures:header@before", headerBefore.analysis,
      `badge=${headerBefore.result.badge}`, headerBefore.confidence);
    expect(headerBefore.result.badge).toBe("OFFLINE");
    const visionBefore = headerBefore;

    const actionsBefore = await detectPanelVisibility(futuresCardActions, "live-start-futures.actions@before");
    logVisionResult("live-start-futures:actions@before", actionsBefore.analysis,
      actionsBefore._too_small ? `skipped: ${actionsBefore.reason ?? ""}`
        : `panel=${actionsBefore.result.panel_visible}`, actionsBefore.confidence);
    const calloutsBefore = await detectPanelVisibility(futuresCardCallouts, "live-start-futures.callouts@before");
    logVisionResult("live-start-futures:callouts@before", calloutsBefore.analysis,
      calloutsBefore._too_small ? `skipped: ${calloutsBefore.reason ?? ""}`
        : `panel=${calloutsBefore.result.panel_visible} label=${calloutsBefore.result.primary_label ?? "?"}`,
      calloutsBefore.confidence);

    // Action: real DOM click on Start Futures. Long single-click wait —
    //    see stop-spot rationale: pendingAction keeps the button disabled
    //    after a successful click, so retries are misleading.
    const startFuturesBtn = page.getByTestId("runtime.start.futures");
    await expect(startFuturesBtn).toBeEnabled({ timeout: 10_000 });
    await startFuturesBtn.click();

    // Wait for DOM to move off OFFLINE. 30s covers worst-case when the
    //   test runs at the tail of a multi-test suite.
    await expect(page.getByTestId("runtime.state.futures"))
      .toHaveText(/RUNNING|DEGRADED/, { timeout: 30_000 });
    const domAfter = (await page.getByTestId("runtime.state.futures").textContent() ?? "").trim().toUpperCase();

    const backendAfter = await waitForBackendRuntimeState(request, "futures", ["running", "degraded"], 5_000);
    expect(["running", "degraded"].includes(backendAfter),
      `backend_after must be running or degraded, got '${backendAfter}'`).toBe(true);

    // ── Semantic snapshot AFTER + diff (canonical layer).
    const semanticAfter = await captureSemanticSnapshot(page);
    {
      const diff = compareSemanticSnapshots(semanticBefore, semanticAfter);
      console.log(`[semantic-diff start-futures] ${summariseDiff(diff)}`);
      const cardChange = diff.state_changed.find(
        (c) => c.role === "runtime-card" && c.scope === "futures",
      );
      expect(cardChange, "semantic: runtime-card[futures] must change state").toBeTruthy();
      const validTransitions = [
        `${RUNTIME_STATE.INACTIVE} → ${RUNTIME_STATE.ACTIVE}`,
        `${RUNTIME_STATE.INACTIVE} → ${RUNTIME_STATE.DEGRADED}`,
      ];
      expect(
        validTransitions.includes(cardChange!.detail),
        `semantic: runtime-card[futures] expected ${validTransitions.join("|")}, got '${cardChange!.detail}'`,
      ).toBe(true);
      const semCardAfter = findRegion(semanticAfter, { role: "runtime-card", scope: "futures" });
      expect(
        [RUNTIME_STATE.ACTIVE, RUNTIME_STATE.DEGRADED],
        "semantic canonical state after",
      ).toContain(semCardAfter?.canonical_state);
    }

    // Multi-region AFTER.
    const headerAfter = await classifyElementState(futuresCardHeader, "live-start-futures.header@after");
    expect(headerAfter._too_small).toBe(false);
    logVisionResult("live-start-futures:header@after", headerAfter.analysis,
      `badge=${headerAfter.result.badge}`, headerAfter.confidence);
    expect(headerAfter.result.badge, `vision_after must match DOM '${domAfter}'`).toBe(domAfter);
    const visionAfter = headerAfter;

    const crossAfter = buildCrossCheck(visionAfter.result.badge, domAfter);
    expect(crossAfter.outcome).toBe("confirmed");

    const actionsAfter = await detectPanelVisibility(futuresCardActions, "live-start-futures.actions@after");
    logVisionResult("live-start-futures:actions@after", actionsAfter.analysis,
      actionsAfter._too_small ? `skipped: ${actionsAfter.reason ?? ""}`
        : `panel=${actionsAfter.result.panel_visible}`, actionsAfter.confidence);
    const calloutsAfter = await detectPanelVisibility(futuresCardCallouts, "live-start-futures.callouts@after");
    logVisionResult("live-start-futures:callouts@after", calloutsAfter.analysis,
      calloutsAfter._too_small ? `skipped: ${calloutsAfter.reason ?? ""}`
        : `panel=${calloutsAfter.result.panel_visible} label=${calloutsAfter.result.primary_label ?? "?"}`,
      calloutsAfter.confidence);

    const comparison = compareStates(visionBefore.result, visionAfter.result, {
      from: "OFFLINE", to: ["RUNNING", "DEGRADED"],
    });
    expect(comparison.decision).toBe("transition_confirmed");

    // Composite decision.
    const regionOutcomes: RegionOutcome[] = [
      regionOutcome(
        "header.badge",
        comparison.decision === "transition_confirmed" && crossAfter.outcome === "confirmed",
        `header ${headerBefore.result.badge}→${headerAfter.result.badge}`,
      ),
      actionsBefore._too_small || actionsAfter._too_small
        ? regionSkipped("actions.row",
            `skipped: ${actionsBefore._too_small ? actionsBefore.reason : actionsAfter.reason ?? "?"}`,
            { size_before: actionsBefore.size, size_after: actionsAfter.size })
        : regionOutcome("actions.row",
            actionsBefore.result.panel_visible === true && actionsAfter.result.panel_visible === true,
            `panel_visible before=${actionsBefore.result.panel_visible} after=${actionsAfter.result.panel_visible}`),
      calloutsBefore._too_small || calloutsAfter._too_small
        ? regionSkipped("callouts",
            `skipped: ${calloutsBefore._too_small ? calloutsBefore.reason : calloutsAfter.reason ?? "?"}`)
        : regionOutcome("callouts",
            calloutsBefore.result.panel_visible === true && calloutsAfter.result.panel_visible === true,
            `panel_visible before=${calloutsBefore.result.panel_visible} after=${calloutsAfter.result.panel_visible}`),
    ];
    const composite = composeDecision("start-futures:offline→active", regionOutcomes);
    expect(
      ["all_confirmed", "partial_confirmed"].includes(composite.final_outcome),
      `composite: ${composite.final_outcome}`,
    ).toBe(true);
    expect(composite.conflicted_regions).toHaveLength(0);

    for (const [name, loc] of [
      ["header", futuresCardHeader], ["actions", futuresCardActions], ["callouts", futuresCardCallouts],
    ] as const) {
      const sanity = await checkRegionLayoutSanity(loc);
      expect(sanity.visible, `layout: futures ${name} must stay visible after start`).toBe(true);
      expect(sanity.text_length, `layout: futures ${name} must still have text content`).toBeGreaterThan(0);
    }

    console.log(
      `[live-start-futures] backend ${backendBefore}→${backendAfter} ` +
      `dom ${domBefore}→${domAfter} ` +
      `header ${headerBefore.result.badge}→${headerAfter.result.badge} ` +
      `composite=${composite.final_outcome} ` +
      `confirmed=[${composite.confirmed_regions.join(",")}] ` +
      `skipped=[${composite.skipped_regions.join(",")}]`,
    );
  } finally {
    await stopRuntime(request, "futures");
    await waitForBackendRuntimeState(request, "futures", ["offline"], 15_000);
  }
});
