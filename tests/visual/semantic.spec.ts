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
 * The interaction-level checks live in live-backend.spec.ts where the
 * real start/stop transitions happen — this file just protects the
 * helpers themselves from silent regressions.
 */

import { expect, test } from "@playwright/test";
import { waitForStableUI } from "./helpers";
import {
  ACTION_STATE,
  captureSemanticSnapshot,
  compareSemanticSnapshots,
  findRegion,
  JOBS_STATE,
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
