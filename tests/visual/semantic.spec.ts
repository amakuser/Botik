/**
 * Semantic auto-region — sanity tests.
 *
 * These tests do not start any runtime, do not click any action button,
 * and do not call the vision model. They only:
 *   1. open the runtime page against a real backend
 *   2. capture a semantic snapshot
 *   3. assert the auto-discovery contract holds (roles present, keys
 *      stable, recommended_check sane)
 *   4. mutate one attribute via page.evaluate and assert
 *      compareSemanticSnapshots reports the right change shape
 *
 * Interaction-level checks (start/stop transitions) live elsewhere or
 * are exercised through manual smoke against the real Tauri shell — this
 * file just protects the helpers themselves from silent regressions.
 */

import { expect, test } from "@playwright/test";
import { waitForStableUI } from "./helpers";
import {
  ACTION_STATE,
  captureSemanticSnapshot,
  compareSemanticSnapshots,
  findRegion,
  JOBS_STATE,
  MODEL_STATE,
  regionKey,
  RUNTIME_STATE,
  summariseDiff,
} from "./semantic.helpers";

const BASE = "http://127.0.0.1:4173";

test("semantic: runtime page exposes the data-ui-* contract", async ({ page }) => {
  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);
  await expect(page.getByTestId("runtime.card.spot")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("runtime.card.futures")).toBeVisible({ timeout: 10_000 });

  const snap = await captureSemanticSnapshot(page);

  // Both runtime cards must be auto-discovered without us listing any
  // selectors in the test.
  const spotCard = findRegion(snap, { role: "runtime-card", scope: "spot" });
  const futuresCard = findRegion(snap, { role: "runtime-card", scope: "futures" });
  expect(spotCard, "spot runtime card discovered").not.toBeNull();
  expect(futuresCard, "futures runtime card discovered").not.toBeNull();
  // Assert via canonical, not raw — the frontend may rename "offline" to
  // "idle" tomorrow; the canonical bucket is what tests rely on.
  expect(
    spotCard!.canonical_state,
    "spot card carries a canonical RUNTIME_STATE",
  ).not.toBeNull();
  expect(
    Object.values(RUNTIME_STATE),
    "spot card canonical_state is one of RUNTIME_STATE",
  ).toContain(spotCard!.canonical_state);

  // Status badges follow the same contract.
  const spotBadge = findRegion(snap, { role: "status-badge", scope: "spot" });
  const futuresBadge = findRegion(snap, { role: "status-badge", scope: "futures" });
  expect(spotBadge, "spot status badge discovered").not.toBeNull();
  expect(futuresBadge, "futures status badge discovered").not.toBeNull();

  // Action buttons — start + stop on each scope.
  const spotStart = findRegion(snap, { role: "runtime-action", scope: "spot", action: "start" });
  const spotStop = findRegion(snap, { role: "runtime-action", scope: "spot", action: "stop" });
  const futuresStart = findRegion(snap, { role: "runtime-action", scope: "futures", action: "start" });
  const futuresStop = findRegion(snap, { role: "runtime-action", scope: "futures", action: "stop" });
  expect(spotStart, "spot start action").not.toBeNull();
  expect(spotStop, "spot stop action").not.toBeNull();
  expect(futuresStart, "futures start action").not.toBeNull();
  expect(futuresStop, "futures stop action").not.toBeNull();

  // recommended_check policy: actions must be DOM-only (button state is
  // authoritative, not a vision concern); status-badge should be vision
  // when its bbox clears the minimum.
  expect(spotStart!.recommended_check, "actions are DOM-checked").toBe("dom");
  expect(spotStop!.recommended_check, "actions are DOM-checked").toBe("dom");

  // Callouts present per scope. The exact `kind` value is a function of
  // backend state (info when no error, error when last_error is set), so
  // the test does not assert a specific kind — only that the callouts
  // exist on the page so the diff can later track changes to them.
  const spotCallouts = snap.regions.filter(
    (r) => r.role === "status-callout" && r.scope === "spot",
  );
  const futuresCallouts = snap.regions.filter(
    (r) => r.role === "status-callout" && r.scope === "futures",
  );
  expect(spotCallouts.length, "spot has callouts").toBeGreaterThanOrEqual(2);
  expect(futuresCallouts.length, "futures has callouts").toBeGreaterThanOrEqual(2);

  // Region keys must be stable (deterministic, no timestamps, no idx).
  for (const r of snap.regions) {
    const k = regionKey(r);
    expect(k, "region key is non-empty").not.toBe("");
    // No coordinates leak into the key.
    expect(k).not.toMatch(/[0-9]{2,}/);
  }
});

test("semantic: diff detects a state flip without any text comparison", async ({ page }) => {
  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);
  await expect(page.getByTestId("runtime.card.spot")).toBeVisible({ timeout: 10_000 });

  const before = await captureSemanticSnapshot(page);

  // Mutate the data-ui-state on the spot card to simulate a transition.
  // We rewrite the attribute in the DOM only — no backend, no vision.
  // This is the cleanest way to verify that compareSemanticSnapshots
  // reports the right shape for a state flip without depending on the
  // runtime actually starting (that path is exercised in live-backend).
  await page.evaluate(() => {
    const card = document.querySelector('[data-ui-role="runtime-card"][data-ui-scope="spot"]');
    if (card) card.setAttribute("data-ui-state", "running");
    const badge = document.querySelector('[data-ui-role="status-badge"][data-ui-scope="spot"]');
    if (badge) badge.setAttribute("data-ui-state", "running");
  });

  const after = await captureSemanticSnapshot(page);
  const diff = compareSemanticSnapshots(before, after);

  console.log(`[semantic-diff] ${summariseDiff(diff)}`);

  // The synthetic flip must surface as state_changed on BOTH the card
  // and its badge, and as nothing else (no spurious added/removed).
  expect(diff.state_changed.length, "two state_changed entries").toBe(2);
  expect(diff.region_added.length, "no spurious additions").toBe(0);
  expect(diff.region_removed.length, "no spurious removals").toBe(0);

  const cardChange = diff.state_changed.find(
    (c) => c.role === "runtime-card" && c.scope === "spot",
  );
  expect(cardChange, "card state_changed present").toBeTruthy();
  // Diff detail is canonical — e.g. "INACTIVE → ACTIVE", not "offline → running".
  expect(cardChange!.detail).toBe(`${RUNTIME_STATE.INACTIVE} → ${RUNTIME_STATE.ACTIVE}`);
  expect(cardChange!.after?.canonical_state).toBe(RUNTIME_STATE.ACTIVE);

  const badgeChange = diff.state_changed.find(
    (c) => c.role === "status-badge" && c.scope === "spot",
  );
  expect(badgeChange, "badge state_changed present").toBeTruthy();
  expect(badgeChange!.after?.canonical_state).toBe(RUNTIME_STATE.ACTIVE);
});

test("semantic: canonical state survives a UI rename (synthetic)", async ({ page }) => {
  // Verifies the headline promise of the canonical layer: tests don't
  // assert raw UI strings. We synthetically write an unmapped raw state
  // and confirm:
  //   1. canonical_state goes null on the renamed region
  //   2. the diff still reports a state_changed entry (raw fallback)
  // If a future frontend rename slips through without updating
  // CANONICAL_MAP, this is the test that flags it.
  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);
  await expect(page.getByTestId("runtime.card.spot")).toBeVisible({ timeout: 10_000 });

  const before = await captureSemanticSnapshot(page);
  const beforeCard = findRegion(before, { role: "runtime-card", scope: "spot" });
  expect(beforeCard!.canonical_state).toBe(RUNTIME_STATE.INACTIVE);

  // Pretend the frontend renamed `offline` → `idle` without updating
  // the canonical map.
  await page.evaluate(() => {
    const card = document.querySelector('[data-ui-role="runtime-card"][data-ui-scope="spot"]');
    if (card) card.setAttribute("data-ui-state", "idle");
  });

  const after = await captureSemanticSnapshot(page);
  const afterCard = findRegion(after, { role: "runtime-card", scope: "spot" });
  expect(
    afterCard!.canonical_state,
    "unmapped raw state must yield null canonical (not silently masked)",
  ).toBeNull();
  expect(afterCard!.state, "raw state preserved for diagnostics").toBe("idle");

  // Diff must still see the change (canonical INACTIVE → null).
  const diff = compareSemanticSnapshots(before, after);
  const cardChange = diff.state_changed.find(
    (c) => c.role === "runtime-card" && c.scope === "spot",
  );
  expect(cardChange, "rename detected via canonical → null transition").toBeTruthy();
});

test("semantic: jobs page exposes the data-ui-* contract", async ({ page }) => {
  await page.goto(`${BASE}/jobs`);
  await waitForStableUI(page);
  await expect(page.getByTestId("job.preset.data-backfill")).toBeVisible({ timeout: 10_000 });

  const snap = await captureSemanticSnapshot(page);

  // Page root carries scope=jobs.
  const pageRoot = findRegion(snap, { role: "page", scope: "jobs" });
  expect(pageRoot, "jobs page root discovered").not.toBeNull();

  // History panel exists and has a canonical JOBS_STATE.
  const history = findRegion(snap, { role: "jobs-history" });
  expect(history, "jobs-history discovered").not.toBeNull();
  expect(
    Object.values(JOBS_STATE),
    "jobs-history canonical_state is one of JOBS_STATE",
  ).toContain(history!.canonical_state);

  // Preset cards: both auto-discovered, with sane recommended_check.
  for (const scope of ["data-backfill", "data-integrity"] as const) {
    const preset = findRegion(snap, { role: "job-preset", scope });
    expect(preset, `${scope} preset card`).not.toBeNull();
    // Hybrid because preset cards are large and chrome-rich.
    expect(["hybrid", "dom"]).toContain(preset!.recommended_check);

    const startAction = findRegion(snap, { role: "job-action", scope, action: "start" });
    expect(startAction, `${scope} start action`).not.toBeNull();
    expect(startAction!.recommended_check, "actions are DOM-only").toBe("dom");
    expect(
      Object.values(ACTION_STATE),
      `${scope} start action canonical_state is one of ACTION_STATE`,
    ).toContain(startAction!.canonical_state);
  }

  // Toolbar actions: sample-import + selected-stop.
  const sampleStart = findRegion(snap, {
    role: "job-action",
    scope: "sample-import",
    action: "start",
  });
  const selectedStop = findRegion(snap, {
    role: "job-action",
    scope: "selected",
    action: "stop",
  });
  expect(sampleStart, "sample-import start action").not.toBeNull();
  expect(selectedStop, "selected stop action").not.toBeNull();
});

test("semantic: diff detects action_availability flip", async ({ page }) => {
  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);
  await expect(page.getByTestId("runtime.start.spot")).toBeVisible({ timeout: 10_000 });

  const before = await captureSemanticSnapshot(page);

  // Toggle the spot start button's state from enabled → disabled.
  await page.evaluate(() => {
    const btn = document.querySelector(
      '[data-ui-role="runtime-action"][data-ui-scope="spot"][data-ui-action="start"]',
    ) as HTMLButtonElement | null;
    if (btn) {
      btn.disabled = true;
      btn.setAttribute("data-ui-state", "disabled");
    }
  });

  const after = await captureSemanticSnapshot(page);
  const diff = compareSemanticSnapshots(before, after);

  console.log(`[semantic-diff] ${summariseDiff(diff)}`);

  expect(
    diff.action_availability_changed.length,
    "exactly one action availability flipped",
  ).toBe(1);
  const change = diff.action_availability_changed[0];
  expect(change.role).toBe("runtime-action");
  expect(change.scope).toBe("spot");
  expect(change.detail).toContain("enabled true → false");
  // Canonical: must have crossed from ENABLED → DISABLED.
  expect(change.before?.canonical_state).toBe(ACTION_STATE.ENABLED);
  expect(change.after?.canonical_state).toBe(ACTION_STATE.DISABLED);
});

test("semantic: health page exposes the data-ui-* contract", async ({ page }) => {
  await page.goto(`${BASE}/`);
  await waitForStableUI(page);
  // Wait for at least one metric card to render — the page is /
  await expect(page.getByTestId("home.metric.pnl-today")).toBeVisible({ timeout: 10_000 });

  const snap = await captureSemanticSnapshot(page);

  // 1. Page root with scope=health
  const pageRoot = findRegion(snap, { role: "page", scope: "health" });
  expect(pageRoot, "health page root discovered").not.toBeNull();

  // 2. Intro singleton
  const intro = findRegion(snap, { role: "health-intro" });
  expect(intro, "health-intro discovered").not.toBeNull();

  // 3. All 4 metric cards by scope (auto-discovered, no selector list).
  for (const scope of ["pnl-today", "balance", "trades", "positions"] as const) {
    const card = findRegion(snap, { role: "metric-card", scope });
    expect(card, `metric-card[${scope}] discovered`).not.toBeNull();
    // Card-like recommendedCheck: hybrid (vision-ready) or dom.
    expect(["hybrid", "dom"]).toContain(card!.recommended_check);
    // Metric cards do not carry state — canonical_state must be null.
    expect(card!.canonical_state, `metric-card[${scope}] is unmapped (no state)`).toBeNull();
  }

  // 4. Pipeline container — layout-only, dom-checked.
  const pipeline = findRegion(snap, { role: "pipeline", scope: "health" });
  expect(pipeline, "pipeline container discovered").not.toBeNull();
  expect(pipeline!.recommended_check).toBe("dom");

  // 5. All 3 pipeline steps + canonical state contract:
  //    "unknown" raw → canonical_state===null (intentional unmapped)
  //    "running"/"idle" raw → one of RUNTIME_STATE
  for (const scope of ["historical-data", "ml-models", "trading"] as const) {
    const step = findRegion(snap, { role: "pipeline-step", scope });
    expect(step, `pipeline-step[${scope}] discovered`).not.toBeNull();
    if (step!.state === "unknown") {
      expect(step!.canonical_state, `unknown raw must yield null canonical`).toBeNull();
    } else {
      expect(
        Object.values(RUNTIME_STATE),
        `pipeline-step[${scope}] canonical (raw=${step!.state}) is one of RUNTIME_STATE`,
      ).toContain(step!.canonical_state);
    }
    // pipeline-step is card-like.
    expect(["hybrid", "dom"]).toContain(step!.recommended_check);
  }

  // 6. Bootstrap layout section.
  const bootstrap = findRegion(snap, { role: "bootstrap", scope: "session" });
  expect(bootstrap, "bootstrap section discovered").not.toBeNull();
  expect(bootstrap!.recommended_check).toBe("dom");
});

test("semantic: telegram page exposes the data-ui-* contract", async ({ page }) => {
  await page.goto(`${BASE}/telegram`);
  await waitForStableUI(page);
  // Wait until summary cards render — that proves the page settled.
  await expect(page.getByTestId("telegram.summary.connectivity")).toBeVisible({ timeout: 10_000 });

  const snap = await captureSemanticSnapshot(page);

  // 1. Page root with scope=telegram.
  const pageRoot = findRegion(snap, { role: "page", scope: "telegram" });
  expect(pageRoot, "telegram page root discovered").not.toBeNull();

  // 2. Intro singleton.
  const intro = findRegion(snap, { role: "telegram-intro" });
  expect(intro, "telegram-intro discovered").not.toBeNull();
  expect(intro!.recommended_check).toBe("dom");

  // 3. Summary panel + 4 summary cards.
  const summaryPanel = findRegion(snap, { role: "summary-panel", scope: "telegram" });
  expect(summaryPanel, "summary panel").not.toBeNull();
  expect(["hybrid", "dom"]).toContain(summaryPanel!.recommended_check);

  for (const scope of ["connectivity", "allowed-chats", "alerts", "errors"] as const) {
    const card = findRegion(snap, { role: "summary-card", scope });
    expect(card, `summary-card[${scope}] discovered`).not.toBeNull();
    expect(["hybrid", "dom"]).toContain(card!.recommended_check);
    // Summary cards carry no state — canonical_state must be null (matches metric-card pattern).
    expect(card!.canonical_state).toBeNull();
  }

  // 4. Connectivity panel + 3 signals.
  const connectivityPanel = findRegion(snap, { role: "connectivity-panel", scope: "telegram" });
  expect(connectivityPanel, "connectivity-panel").not.toBeNull();
  expect(["hybrid", "dom"]).toContain(connectivityPanel!.recommended_check);

  for (const scope of ["bot", "token", "chats"] as const) {
    const signal = findRegion(snap, { role: "connectivity-signal", scope });
    expect(signal, `connectivity-signal[${scope}] discovered`).not.toBeNull();
    expect(signal!.recommended_check).toBe("dom");
  }

  // 5. Connectivity check action — DOM only, canonical ACTION_STATE.
  const checkAction = findRegion(snap, { role: "connectivity-action", scope: "check", action: "run" });
  expect(checkAction, "connectivity-action[check]").not.toBeNull();
  expect(checkAction!.recommended_check).toBe("dom");
  expect(Object.values(ACTION_STATE)).toContain(checkAction!.canonical_state);

  // 6. History panels — 3 with canonical JOBS_STATE.
  for (const scope of ["commands", "alerts", "errors"] as const) {
    const history = findRegion(snap, { role: "history-panel", scope });
    expect(history, `history-panel[${scope}]`).not.toBeNull();
    expect(["hybrid", "dom"]).toContain(history!.recommended_check);
    expect(Object.values(JOBS_STATE)).toContain(history!.canonical_state);
  }

  // 7. Initial result callouts MUST be absent — they only render after the check.
  const resultCallouts = snap.regions.filter(
    (r) => r.role === "status-callout" && r.scope === "connectivity-result",
  );
  expect(resultCallouts.length, "result callouts initially absent").toBe(0);
});

test("semantic: models page exposes the data-ui-* contract", async ({ page }) => {
  // Live backend — frontend talks to real /models at 127.0.0.1:8765. No
  // page.route. Backend returns 2 scopes (spot, futures) with ready=false
  // and "not available" lifecycle status in dev environment; both scope
  // cards render from real data.
  await page.goto(`${BASE}/models`);
  await waitForStableUI(page);
  await expect(page.getByTestId("models.summary.total-models")).toBeVisible({ timeout: 10_000 });
  // Wait for scope cards to render from live data — the scopes array always
  // returns spot+futures even when registry/training are empty.
  await expect(page.locator('[data-ui-role="scope-card"][data-ui-scope="spot"]')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-ui-role="scope-card"][data-ui-scope="futures"]')).toBeVisible({ timeout: 10_000 });

  const snap = await captureSemanticSnapshot(page);

  // 1. Page root with scope=models.
  const pageRoot = findRegion(snap, { role: "page", scope: "models" });
  expect(pageRoot, "models page root discovered").not.toBeNull();

  // 2. Intro singleton.
  const intro = findRegion(snap, { role: "models-intro" });
  expect(intro, "models-intro discovered").not.toBeNull();
  expect(intro!.recommended_check).toBe("dom");

  // 3. Summary panel + 4 summary cards.
  const summaryPanel = findRegion(snap, { role: "summary-panel", scope: "models" });
  expect(summaryPanel, "summary panel models").not.toBeNull();

  for (const scope of ["total-models", "active-declared", "ready-scopes", "recent-runs"] as const) {
    const card = findRegion(snap, { role: "summary-card", scope });
    expect(card, `summary-card[${scope}]`).not.toBeNull();
    expect(["hybrid", "dom"]).toContain(card!.recommended_check);
    // Summary cards carry no state — canonical_state must be null (matches metric-card pattern).
    expect(card!.canonical_state).toBeNull();
  }

  // 4. Training control card.
  const trainingControl = findRegion(snap, { role: "training-control", scope: "models" });
  expect(trainingControl, "training-control card").not.toBeNull();
  expect(["hybrid", "dom"]).toContain(trainingControl!.recommended_check);
  // training-control state is raw job lifecycle — canonical_state must be null
  // (job lifecycle is not yet in any canonical bucket — same honest gap as
  // jobs-list-item).
  expect(trainingControl!.canonical_state).toBeNull();

  // 5. 3 info-signals inside training-control.
  for (const scope of ["scope", "interval", "state"] as const) {
    const sig = findRegion(snap, { role: "info-signal", scope });
    expect(sig, `training info-signal[${scope}]`).not.toBeNull();
    expect(sig!.recommended_check).toBe("dom");
  }

  // 6. Training start/stop actions — DOM only with canonical ACTION_STATE.
  const startAction = findRegion(snap, { role: "training-action", scope: "training", action: "start" });
  const stopAction = findRegion(snap, { role: "training-action", scope: "training", action: "stop" });
  expect(startAction, "training start action").not.toBeNull();
  expect(stopAction, "training stop action").not.toBeNull();
  expect(startAction!.recommended_check).toBe("dom");
  expect(stopAction!.recommended_check).toBe("dom");
  expect(Object.values(ACTION_STATE)).toContain(startAction!.canonical_state);
  expect(Object.values(ACTION_STATE)).toContain(stopAction!.canonical_state);

  // 7. Scope panel + 2 scope cards (spot, futures) with MODEL_STATE canonical.
  const scopesPanel = findRegion(snap, { role: "summary-panel", scope: "scopes" });
  expect(scopesPanel, "scopes panel").not.toBeNull();

  for (const scope of ["spot", "futures"] as const) {
    const scopeCard = findRegion(snap, { role: "scope-card", scope });
    expect(scopeCard, `scope-card[${scope}]`).not.toBeNull();
    expect(["hybrid", "dom"]).toContain(scopeCard!.recommended_check);
    // scope-card canonical_state ∈ MODEL_STATE (not RUNTIME_STATE — semantically distinct).
    expect(Object.values(MODEL_STATE)).toContain(scopeCard!.canonical_state);

    // Status badge ГОТОВО/В ОЖИДАНИИ inside scope card — same MODEL_STATE.
    const readyBadge = findRegion(snap, { role: "status-badge", scope });
    expect(readyBadge, `status-badge[${scope}] readiness`).not.toBeNull();
    expect(Object.values(MODEL_STATE)).toContain(readyBadge!.canonical_state);

    // Reason callout — kind=info present.
    const callout = findRegion(snap, { role: "status-callout", scope, kind: "info" });
    expect(callout, `status-callout[${scope}, info]`).not.toBeNull();
  }

  // 8. Surface badges (registry/training) — present, but canonical_state=null
  //    because raw lifecycle ("not available", "completed", "failed", ...) is
  //    not in any canonical bucket. This is the honest gap.
  const registryBadge = findRegion(snap, { role: "status-badge", scope: "spot-registry" });
  expect(registryBadge, "spot-registry status-badge").not.toBeNull();
  expect(registryBadge!.canonical_state, "raw lifecycle stays unmapped").toBeNull();

  // 9. 2 history panels — JOBS_STATE empty/populated.
  for (const scope of ["registry-entries", "training-runs"] as const) {
    const history = findRegion(snap, { role: "history-panel", scope });
    expect(history, `history-panel[${scope}]`).not.toBeNull();
    expect(["hybrid", "dom"]).toContain(history!.recommended_check);
    expect(Object.values(JOBS_STATE)).toContain(history!.canonical_state);
  }
});

test("semantic: spot page exposes the data-ui-* contract", async ({ page }) => {
  // Live backend — same pattern as /models test. /spot is read-only;
  // backend in dev returns empty collections (balances/holdings/etc.) but the
  // page renders all 4 history panels and 5 summary cards regardless.
  await page.goto(`${BASE}/spot`);
  await waitForStableUI(page);
  await expect(page.getByTestId("spot.summary.balance-assets")).toBeVisible({ timeout: 10_000 });

  const snap = await captureSemanticSnapshot(page);

  // 1. Page root.
  const pageRoot = findRegion(snap, { role: "page", scope: "spot" });
  expect(pageRoot, "spot page root").not.toBeNull();

  // 2. Intro singleton.
  const intro = findRegion(snap, { role: "spot-intro" });
  expect(intro, "spot-intro").not.toBeNull();
  expect(intro!.recommended_check).toBe("dom");

  // 3. Summary panel + 5 summary cards.
  const summaryPanel = findRegion(snap, { role: "summary-panel", scope: "spot" });
  expect(summaryPanel, "summary panel spot").not.toBeNull();

  for (const scope of ["balance-assets", "holdings", "orders", "fills", "intents"] as const) {
    const card = findRegion(snap, { role: "summary-card", scope });
    expect(card, `summary-card[${scope}]`).not.toBeNull();
    expect(["hybrid", "dom"]).toContain(card!.recommended_check);
    // Summary cards carry no state — canonical_state must be null.
    expect(card!.canonical_state).toBeNull();
  }

  // 4. 4 history panels — JOBS_STATE empty/populated by row counts.
  //    In dev backend all collections are empty, so all four should be `empty`.
  for (const scope of ["balances", "holdings", "active-orders", "recent-fills"] as const) {
    const history = findRegion(snap, { role: "history-panel", scope });
    expect(history, `history-panel[${scope}]`).not.toBeNull();
    expect(["hybrid", "dom"]).toContain(history!.recommended_check);
    expect(Object.values(JOBS_STATE)).toContain(history!.canonical_state);
  }

  // 5. No actions — /spot is read-only. Sanity: no *-action role discovered.
  const anyAction = snap.regions.find((r) => r.role.endsWith("-action"));
  expect(anyAction, "/spot should have no action regions").toBeUndefined();
});
