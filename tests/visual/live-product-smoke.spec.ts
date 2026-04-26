/**
 * Live product smoke — frontend against real backend, no mocks.
 *
 * Reduced replacement for the retired live-backend.spec.ts:
 *   - NO vision (no Ollama, no gemma3:4b)
 *   - NO OLLAMA_VISION gate — these tests run unconditionally
 *   - Read-only: no POSTs, no state mutation
 *   - Each test does two independent checks and asserts they agree:
 *       1. Backend  — direct HTTP GET against the real endpoint
 *       2. DOM      — what React renders after fetching the real response
 *     where the page exposes `data-ui-*` it also captures a semantic snapshot
 *     and asserts contract roles are present.
 *
 * Pre-conditions:
 *   - app-service running at 127.0.0.1:8765 (`pwsh ./scripts/dev-app-service.ps1`)
 *   - Vite dev/preview at 127.0.0.1:4173 (`pwsh ./scripts/dev-frontend.ps1`)
 *   - BOTIK_SESSION_TOKEN env var (defaults to "botik-dev-token")
 */

import { expect, test } from "@playwright/test";
import { waitForStableUI } from "./helpers";
import {
  captureSemanticSnapshot,
  findRegion,
  JOBS_STATE,
} from "./semantic.helpers";

const BASE = "http://127.0.0.1:4173";
const BACKEND = "http://127.0.0.1:8765";
const SESSION_TOKEN = process.env.BOTIK_SESSION_TOKEN ?? "botik-dev-token";

const HEADERS = { "x-botik-session-token": SESSION_TOKEN };

// ── /health vs real /health ─────────────────────────────────────────────────

test("live: health page renders real /health response", async ({ page, request }) => {
  const apiRes = await request.get(`${BACKEND}/health`, { headers: HEADERS });
  expect(apiRes.ok(), `backend /health should respond 200, got ${apiRes.status()}`).toBe(true);
  const apiBody = await apiRes.json();
  expect(apiBody.status, "backend /health.status").toBe("ok");
  expect(apiBody.service, "backend /health.service").toBe("botik-app-service");

  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const statusEl = page.getByTestId("health.status");
  const serviceEl = page.getByTestId("health.service");
  await expect(serviceEl).toContainText("botik-app-service", { timeout: 10_000 });
  await expect(statusEl).toContainText("ok");
});

// ── /runtime vs real /runtime-status ────────────────────────────────────────

test("live: runtime page renders real /runtime-status with correct badges", async ({ page, request }) => {
  const apiRes = await request.get(`${BACKEND}/runtime-status`, { headers: HEADERS });
  expect(apiRes.ok(), `backend /runtime-status should respond 200, got ${apiRes.status()}`).toBe(true);
  const apiBody = (await apiRes.json()) as {
    runtimes: Array<{ runtime_id: string; state: string }>;
  };
  const spotBackend = apiBody.runtimes.find((r) => r.runtime_id === "spot");
  const futuresBackend = apiBody.runtimes.find((r) => r.runtime_id === "futures");
  expect(spotBackend, "spot runtime in backend response").toBeTruthy();
  expect(futuresBackend, "futures runtime in backend response").toBeTruthy();

  await page.goto(`${BASE}/runtime`);
  await waitForStableUI(page);

  const spotCard = page.getByTestId("runtime.card.spot");
  const futuresCard = page.getByTestId("runtime.card.futures");
  await expect(spotCard).toBeVisible({ timeout: 10_000 });
  await expect(futuresCard).toBeVisible({ timeout: 10_000 });

  await expect(page.getByTestId("runtime.state.spot")).toHaveText(
    /RUNNING|OFFLINE|DEGRADED|UNKNOWN/,
    { timeout: 10_000 },
  );
  await expect(page.getByTestId("runtime.state.futures")).toHaveText(
    /RUNNING|OFFLINE|DEGRADED|UNKNOWN/,
    { timeout: 10_000 },
  );

  const domSpotBadge = (await page.getByTestId("runtime.state.spot").textContent() ?? "")
    .trim()
    .toUpperCase();
  const domFuturesBadge = (await page.getByTestId("runtime.state.futures").textContent() ?? "")
    .trim()
    .toUpperCase();

  expect(domSpotBadge, "DOM spot badge vs backend state").toBe(spotBackend!.state.toUpperCase());
  expect(domFuturesBadge, "DOM futures badge vs backend state").toBe(futuresBackend!.state.toUpperCase());
});

// ── /jobs vs real /jobs ─────────────────────────────────────────────────────

test("live: jobs page renders real /jobs (history + preset cards)", async ({ page, request }) => {
  const apiRes = await request.get(`${BACKEND}/jobs`, { headers: HEADERS });
  expect(apiRes.ok(), `backend /jobs should respond 200, got ${apiRes.status()}`).toBe(true);
  const apiBody = (await apiRes.json()) as Array<{ job_id: string; state?: string }>;
  expect(Array.isArray(apiBody), "backend /jobs must return a JSON array").toBe(true);
  const backendJobCount = apiBody.length;

  await page.goto(`${BASE}/jobs`);
  await waitForStableUI(page);

  if (backendJobCount === 0) {
    const emptyEl = page.getByTestId("jobs.history.empty");
    await expect(emptyEl).toBeVisible({ timeout: 10_000 });
    await expect(emptyEl).toContainText("Задач ещё не было");
  } else {
    await expect(page.locator(".jobs-list li").first()).toBeVisible({ timeout: 10_000 });
  }

  await expect(page.getByTestId("job.preset.data-backfill")).toBeVisible();
  await expect(page.getByTestId("job.preset.data-integrity")).toBeVisible();

  // Semantic contract — page root + history panel canonical state matches backend.
  const snapshot = await captureSemanticSnapshot(page);

  const pageRegion = findRegion(snapshot, { role: "page", scope: "jobs" });
  expect(pageRegion, "semantic: jobs page root discovered").not.toBeNull();

  const historyRegion = findRegion(snapshot, { role: "jobs-history" });
  expect(historyRegion, "semantic: jobs-history panel discovered").not.toBeNull();

  const expectedCanonical = backendJobCount === 0 ? JOBS_STATE.EMPTY : JOBS_STATE.NON_EMPTY;
  expect(
    historyRegion!.canonical_state,
    `semantic: jobs-history canonical_state must reflect backend jobs.length=${backendJobCount}`,
  ).toBe(expectedCanonical);
});

// ── /spot vs real /spot (read-only render) ──────────────────────────────────
//
// /spot exposes summary panel + summary cards + history panels. The endpoint
// always responds (fixture-backed in dev), so the page should always render.
// We assert backend reachability + page root + summary panel through the
// semantic contract — no asserts on specific numeric values (volatile).

test("live: spot page renders real /spot response", async ({ page, request }) => {
  const apiRes = await request.get(`${BACKEND}/spot`, { headers: HEADERS });
  expect(apiRes.ok(), `backend /spot should respond 200, got ${apiRes.status()}`).toBe(true);

  await page.goto(`${BASE}/spot`);
  await waitForStableUI(page);

  const snapshot = await captureSemanticSnapshot(page);

  const pageRegion = findRegion(snapshot, { role: "page", scope: "spot" });
  expect(pageRegion, "semantic: spot page root discovered").not.toBeNull();

  const summaryPanel = findRegion(snapshot, { role: "summary-panel", scope: "spot" });
  expect(summaryPanel, "semantic: spot summary panel discovered").not.toBeNull();

  // Summary cards on /spot use per-asset scopes (balance-assets, holdings,
  // orders, fills, intents) — page scope=spot is asserted above, so we count
  // summary-card occurrences without re-filtering by scope.
  const summaryCards = snapshot.regions.filter((r) => r.role === "summary-card");
  expect(
    summaryCards.length,
    "semantic: spot page must render at least one summary card",
  ).toBeGreaterThan(0);
});

// ── /models vs real /models (read-only render) ──────────────────────────────

test("live: models page renders real /models response", async ({ page, request }) => {
  const apiRes = await request.get(`${BACKEND}/models`, { headers: HEADERS });
  expect(apiRes.ok(), `backend /models should respond 200, got ${apiRes.status()}`).toBe(true);
  const apiBody = (await apiRes.json()) as { scopes?: Array<unknown> };
  expect(apiBody, "backend /models must return a JSON object").toBeTruthy();

  await page.goto(`${BASE}/models`);
  await waitForStableUI(page);

  const snapshot = await captureSemanticSnapshot(page);

  const pageRegion = findRegion(snapshot, { role: "page", scope: "models" });
  expect(pageRegion, "semantic: models page root discovered").not.toBeNull();

  const summaryPanel = findRegion(snapshot, { role: "summary-panel", scope: "models" });
  expect(summaryPanel, "semantic: models summary panel discovered").not.toBeNull();

  // At least one scope card or one summary card must render — both are acceptable
  // smoke evidence that the page received and rendered the backend response.
  // Page scope=models is asserted above, so we don't re-filter cards by scope.
  const scopeCards = snapshot.regions.filter((r) => r.role === "scope-card");
  const summaryCards = snapshot.regions.filter((r) => r.role === "summary-card");
  expect(
    scopeCards.length + summaryCards.length,
    "semantic: models page must render at least one scope-card or summary-card",
  ).toBeGreaterThan(0);
});
