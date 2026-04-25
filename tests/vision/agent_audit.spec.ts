/**
 * Exploratory UI agent audit.
 *
 * Mode: SEMI-AUTONOMOUS / NON-BLOCKING
 * Activated by:  OLLAMA_AGENT=1
 *
 * Scope (honest):
 *   Read-only risk map across known regions on a known page.
 *   Differentiates EXPECTED state (e.g. both runtimes offline in fixture) from
 *   UNEXPECTED state (e.g. layout broken, content missing). Without this, every
 *   OFFLINE badge looks "broken" to a small model — which was the 2026-04-20
 *   iteration's main failure mode.
 *
 * What it is:
 *   - A triage tool for "is anything surprising on this page right now?"
 *   - A source of candidate regions for deterministic interaction tests.
 *
 * What it is NOT:
 *   - A full UI audit (it does not exercise flows, it does not click anything).
 *   - A replacement for deterministic specs (any suspicious finding still
 *     needs a dedicated test in tests/visual/interaction.spec.ts).
 *
 * Separation of concerns:
 *   tests/visual/ interaction.spec.ts → deterministic, strict, CI-suitable
 *   tests/visual/ live-backend.spec.ts → real backend, strict, CI-suitable
 *   tests/vision/ agent_audit.spec.ts → exploratory, heuristic, report-only (THIS FILE)
 */

import { test } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  analyzeRegion,
  captureRegion,
  clearRegionCache,
  isOllamaAgentEnabled,
  logVisionResult,
  type RegionAnalysis,
} from "../visual/vision_loop.helpers";
import { setupPageMocks } from "./vision.helpers";
import { BASE_URL } from "./vision.config";

// ── Types ─────────────────────────────────────────────────────────────────────

type RiskLevel = "matches_expected" | "unexpected" | "likely_broken" | "uncertain";

interface RegionRisk {
  name: string;
  expected: string;         // what a human says this region should show
  observed: string;         // what the model actually reports
  risk_level: RiskLevel;
  reason: string;
  key_elements: string[];
  confidence: number;
  latency_ms: number;
}

/**
 * Candidate assertion the exploratory agent suggests for a future deterministic
 * test. Each candidate is concrete enough to copy into interaction.spec.ts.
 */
interface CandidateAssertion {
  region: string;
  rationale: string;
  suggested_spec_name: string;
  suggested_locator_hint: string;
  suggested_classifier: "classifyElementState" | "detectErrorText" | "detectPanelVisibility" | "DOM only";
  suggested_assertion: string;
}

interface AgentAuditReport {
  generated_at: string;
  page: string;
  model: "gemma3:4b";
  regions_scanned: number;
  risk_map: RegionRisk[];
  summary: Record<RiskLevel, number>;
  deterministic_test_candidates: string[];
  /**
   * Structured candidate assertions to seed future deterministic tests.
   * Emitted for `matches_expected` regions too — they are cheap to copy, and
   * making the list larger than just the broken cases is often what turns a
   * triage run into an actionable backlog item.
   */
  candidate_assertions: CandidateAssertion[];
  candidate_region_targets: Array<{ region: string; selector_or_testid: string; why: string }>;
}

// ── Region definitions with expected state ────────────────────────────────────

// Each region carries an explicit expected-state string that is injected into
// the model prompt. The model answers relative to expectation, not from scratch.
interface RegionSpec {
  name: string;
  testId: string | null;
  selector: string | null;
  expected: string;
}

// Region selectors are chosen deliberately small. Giving gemma3:4b the full
// <main> element or a vaguely-scoped [role='navigation'] degrades the signal:
// - full <main> often exceeds the 896×896 vision canvas and gets downsampled
//   until the model reports "empty UI"
// - nav links have subtle .is-active styling that a 4B model cannot read
//   reliably (probe_vision_signals.mjs: 0/3 on active-link detection)
// So we stick to visible, chrome-rich regions the model can answer about.
const RUNTIME_REGIONS: RegionSpec[] = [
  { name: "page-heading",         testId: null, selector: "h1",
    expected: "a page heading text, clearly readable" },
  { name: "spot-runtime-card",    testId: "runtime.card.spot", selector: null,
    expected: "a card titled 'Spot Runtime' with an OFFLINE status badge in red/gray (fixture is offline)" },
  { name: "futures-runtime-card", testId: "runtime.card.futures", selector: null,
    expected: "a card titled 'Futures Runtime' with an OFFLINE status badge in red/gray (fixture is offline)" },
  { name: "runtime-start-spot",   testId: "runtime.start.spot", selector: null,
    expected: "a clickable 'Start' button for the Spot runtime, enabled when runtime is offline" },
];

// ── Prompt ────────────────────────────────────────────────────────────────────

const RISK_SYSTEM =
  'UI inspector for a dark-theme trading dashboard. You are given a description of ' +
  'what the region is EXPECTED to show. Judge whether what you see matches expectation. ' +
  'JSON only: {"matches_expected": true|false, ' +
  '"observed": "brief description of what you see in max 15 words", ' +
  '"reason": "why it matches or does not match, max 20 words", ' +
  '"key_elements": ["up to 3 visible element descriptions"]}. ' +
  'If what you see is functionally the same as expected (same state, same controls visible), ' +
  'return matches_expected=true even if wording differs. Only return false when the region ' +
  'is visibly broken, missing, or shows a different state than expected.';

function buildQuestion(expected: string): string {
  return (
    `EXPECTED: ${expected}\n\n` +
    "Does this region match the expected description? Report matches_expected, observed, reason, and key_elements."
  );
}

// ── Risk classification ───────────────────────────────────────────────────────

/**
 * Map the model's boolean answer + confidence to a 4-level risk bucket.
 *
 * - matches_expected=true              → matches_expected
 * - matches_expected=false (explicit)  → unexpected (candidate for investigation)
 * - missing element / cannot analyse   → uncertain
 * - verbal indicator of breakage       → likely_broken
 */
function classifyRisk(raw: Record<string, unknown>): RiskLevel {
  if (raw._missing === true) return "uncertain";
  const matches = raw.matches_expected;
  const reason = String(raw.reason ?? "").toLowerCase();
  if (matches === true) return "matches_expected";
  if (matches === false) {
    if (/broken|missing|empty|blank|error rendering|layout/.test(reason)) return "likely_broken";
    return "unexpected";
  }
  return "uncertain";
}

function confidenceFor(level: RiskLevel): number {
  // These are heuristic weights; gemma3:4b's own confidence estimates are not
  // reliable, so we use risk level as a proxy.
  return level === "matches_expected" ? 0.85
    : level === "unexpected" ? 0.6
    : level === "likely_broken" ? 0.7
    : 0.3;
}

// ── Report output ─────────────────────────────────────────────────────────────

const ARTIFACTS_DIR = path.join(__dirname, "..", "..", ".artifacts", "local", "latest", "vision");
const REPORT_PATH = path.join(ARTIFACTS_DIR, "agent-audit.json");

function writeReport(report: AgentAuditReport): void {
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf-8");
}

// ── Spec ──────────────────────────────────────────────────────────────────────

test.beforeAll(() => {
  clearRegionCache();
});

test("agent: runtime page — scan key regions and produce risk map", async ({ page }) => {
  test.skip(!isOllamaAgentEnabled(), "OLLAMA_AGENT=1 required to run exploratory agent audit");

  await setupPageMocks(page, "runtime");
  await page.goto(`${BASE_URL}/runtime`);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);

  const riskMap: RegionRisk[] = [];

  for (const region of RUNTIME_REGIONS) {
    let analysis: RegionAnalysis | null = null;

    try {
      const locator = region.testId
        ? page.getByTestId(region.testId)
        : page.locator(region.selector ?? "").first();

      const isVisible = await locator.isVisible().catch(() => false);
      if (!isVisible) {
        riskMap.push({
          name: region.name, expected: region.expected, observed: "(element not found)",
          risk_level: "uncertain", reason: "element not visible or not found",
          key_elements: [], confidence: 0.0, latency_ms: 0,
        });
        console.log(`[agent-audit] region="${region.name}" skipped (not visible)`);
        continue;
      }

      const img = await captureRegion(locator);
      analysis = await analyzeRegion(img, region.name, RISK_SYSTEM, buildQuestion(region.expected));

      const riskLevel = classifyRisk(analysis.raw);
      const observed = String(analysis.raw.observed ?? "");
      const reason = String(analysis.raw.reason ?? "");

      const rawElements = analysis.raw.key_elements;
      const keyElements: string[] = Array.isArray(rawElements)
        ? (rawElements as unknown[]).slice(0, 3).map(String) : [];

      riskMap.push({
        name: region.name,
        expected: region.expected,
        observed: observed || "(no observation)",
        risk_level: riskLevel,
        reason,
        key_elements: keyElements,
        confidence: confidenceFor(riskLevel),
        latency_ms: analysis.latency_ms,
      });

      logVisionResult(`agent-scan:${region.name}`, analysis, `risk=${riskLevel}`);

    } catch (err) {
      const msg = (err as Error).message.slice(0, 80);
      riskMap.push({
        name: region.name, expected: region.expected, observed: "(analysis error)",
        risk_level: "uncertain", reason: `analysis error: ${msg}`,
        key_elements: [], confidence: 0.0, latency_ms: analysis?.latency_ms ?? 0,
      });
      console.log(`[agent-audit] region="${region.name}" error: ${msg}`);
    }
  }

  // ── Summary ──────────────────────────────────────────────────────────────
  const summary: Record<RiskLevel, number> = {
    matches_expected: 0, unexpected: 0, likely_broken: 0, uncertain: 0,
  };
  for (const r of riskMap) summary[r.risk_level]++;

  // ── Deterministic-test candidates ────────────────────────────────────────
  // Only `unexpected` and `likely_broken` surface as candidates. `uncertain`
  // is noise from the small model, not a signal worth writing a test for.
  const candidates: string[] = [];
  for (const r of riskMap) {
    if (r.risk_level === "unexpected") {
      candidates.push(
        `[unexpected] "${r.name}" — expected: ${r.expected} | observed: ${r.observed} | ` +
        `consider a deterministic test in tests/visual/interaction.spec.ts.`,
      );
    }
    if (r.risk_level === "likely_broken") {
      candidates.push(
        `[BROKEN] "${r.name}" — ${r.reason} | add a regression test in tests/visual/regression.spec.ts.`,
      );
    }
  }
  if (candidates.length === 0) {
    candidates.push("No region flagged as unexpected. Deterministic coverage is sufficient for this page.");
  }

  // Candidate assertions — one per scanned region. We key classifier choice
  //   off the region spec's expected description: status badge/card → state,
  //   button → panel_visibility, anything mentioning error/failure →
  //   error_text. Rationale is the agent's own observed reason.
  const candidateAssertions: CandidateAssertion[] = [];
  const candidateTargets: Array<{ region: string; selector_or_testid: string; why: string }> = [];
  for (const region of RUNTIME_REGIONS) {
    const risk = riskMap.find((r) => r.name === region.name);
    if (!risk) continue;
    const hint = region.testId ? `data-testid="${region.testId}"` : (region.selector ?? "?");
    const expectedLower = region.expected.toLowerCase();

    let cls: CandidateAssertion["suggested_classifier"];
    let assertion: string;
    if (/badge|status/.test(expectedLower) && /card/.test(region.name)) {
      cls = "classifyElementState";
      assertion = `expect(classifyElementState(locator,'${region.name}')).result.badge ∈ {RUNNING,OFFLINE,DEGRADED}`;
    } else if (/error|failure/.test(expectedLower)) {
      cls = "detectErrorText";
      assertion = `expect(detectErrorText(locator,'${region.name}')).result.has_error === <expected>`;
    } else if (/button|click/.test(expectedLower)) {
      cls = "detectPanelVisibility";
      assertion = `expect(detectPanelVisibility(locator,'${region.name}')).result.panel_visible === true`;
    } else if (/heading/.test(expectedLower)) {
      cls = "DOM only";
      assertion = `expect(page.locator('${hint}')).toBeVisible() + toHaveText(/.../)`;
    } else {
      cls = "detectPanelVisibility";
      assertion = `expect(detectPanelVisibility(locator,'${region.name}')).result.panel_visible === true`;
    }

    candidateAssertions.push({
      region: region.name,
      rationale: `${risk.risk_level}: ${risk.reason || risk.observed}`,
      suggested_spec_name: `${region.name}-${risk.risk_level === "matches_expected" ? "smoke" : "regression"}`,
      suggested_locator_hint: hint,
      suggested_classifier: cls,
      suggested_assertion: assertion,
    });
    candidateTargets.push({
      region: region.name,
      selector_or_testid: hint,
      why: `expected: ${region.expected}`,
    });
  }

  const report: AgentAuditReport = {
    generated_at: new Date().toISOString(),
    page: "runtime",
    model: "gemma3:4b",
    regions_scanned: riskMap.length,
    risk_map: riskMap,
    summary,
    deterministic_test_candidates: candidates,
    candidate_assertions: candidateAssertions,
    candidate_region_targets: candidateTargets,
  };

  writeReport(report);

  console.log(
    `[agent-audit] page=runtime regions=${riskMap.length} ` +
    `matches=${summary.matches_expected} unexpected=${summary.unexpected} ` +
    `broken=${summary.likely_broken} uncertain=${summary.uncertain}`,
  );
  console.log(`[agent-audit] report → ${REPORT_PATH}`);

  // Report-only: no test.fail() calls.
});
