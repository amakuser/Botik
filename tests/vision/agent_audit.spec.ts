/**
 * Exploratory UI agent audit.
 *
 * Mode: SEMI-AUTONOMOUS / NON-BLOCKING
 * Activated by:  OLLAMA_AGENT=1
 *
 * This spec is NOT a CI gate. It never fails a test.
 * It scans key regions of a page, produces a risk map, and writes
 * a structured JSON report for human review.
 *
 * Separation of concerns:
 *   tests/visual/ interaction.spec.ts → deterministic, strict, CI-suitable
 *   tests/vision/ agent_audit.spec.ts → exploratory, heuristic, report-only (THIS FILE)
 *
 * What it does:
 *   1. Opens a known page with mocked backend fixtures
 *   2. Enumerates predefined key regions
 *   3. Sends each region screenshot to gemma3:4b for risk assessment
 *   4. Classifies risk: likely_ok | suspicious | likely_broken | uncertain
 *   5. If a region looks suspicious, notes it and suggests a deterministic test
 *   6. Writes structured JSON report to .artifacts/local/latest/vision/agent-audit.json
 *
 * What it does NOT do:
 *   - No video / stream processing
 *   - No full-page screenshots (region-first only)
 *   - No destructive actions (no form submissions, no irreversible state changes)
 *   - No CI gate (test.fail() is never called)
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

// ── Report types ───────────────────────────────────────────────────────────────

type RiskLevel = "likely_ok" | "suspicious" | "likely_broken" | "uncertain";

interface RegionRisk {
  name: string;
  risk_level: RiskLevel;
  reason: string;
  key_elements: string[];
  confidence: number;
  latency_ms: number;
}

interface AgentAuditReport {
  generated_at: string;
  page: string;
  model: "gemma3:4b";
  regions_scanned: number;
  risk_map: RegionRisk[];
  summary: Record<RiskLevel, number>;
  recommendations: string[];
}

// ── Risk assessment prompt ─────────────────────────────────────────────────────

const RISK_SYSTEM =
  'UI quality inspector for a dark-theme trading dashboard. ' +
  'JSON only: {"risk_level": "likely_ok|suspicious|likely_broken|uncertain", ' +
  '"reason": "brief observation max 20 words", ' +
  '"key_elements": ["up to 3 visible element descriptions"]}. ' +
  'Use suspicious if you see: wrong colors, missing content, broken layout, unexpected state.';

const RISK_QUESTION =
  "Is this UI region rendering correctly? Identify risk level, reason, and key visible elements.";

// ── Region definitions for the runtime page ───────────────────────────────────

// These use stable selectors — same as deterministic tests — so the agent
// analyses the same bounded regions the production tests rely on.
const RUNTIME_REGIONS = [
  { name: "sidebar-navigation",   testId: null,  selector: "[role='navigation']" },
  { name: "page-heading",         testId: null,  selector: "h1" },
  { name: "spot-runtime-card",    testId: "runtime.card.spot",    selector: null },
  { name: "futures-runtime-card", testId: "runtime.card.futures", selector: null },
  { name: "page-main-content",    testId: null,  selector: "main" },
] as const;

// ── Confidence from risk level ─────────────────────────────────────────────────

function riskConfidence(level: RiskLevel): number {
  return level === "likely_ok" ? 0.85 : level === "uncertain" ? 0.3 : 0.7;
}

// ── Report output ──────────────────────────────────────────────────────────────

const ARTIFACTS_DIR = path.join(__dirname, "..", "..", ".artifacts", "local", "latest", "vision");
const REPORT_PATH = path.join(ARTIFACTS_DIR, "agent-audit.json");

function writeReport(report: AgentAuditReport): void {
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf-8");
}

// ── Spec ───────────────────────────────────────────────────────────────────────

test.beforeAll(() => {
  clearRegionCache();
});

test("agent: runtime page — scan key regions and produce risk map", async ({ page }) => {
  // Exploratory mode is opt-in; skip silently in normal CI runs
  test.skip(!isOllamaAgentEnabled(), "OLLAMA_AGENT=1 required to run exploratory agent audit");

  await setupPageMocks(page, "runtime");
  await page.goto(`${BASE_URL}/runtime`);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);

  const riskMap: RegionRisk[] = [];

  for (const region of RUNTIME_REGIONS) {
    let analysis: RegionAnalysis | null = null;

    try {
      // Resolve the locator
      const locator = region.testId
        ? page.getByTestId(region.testId)
        : page.locator(region.selector).first();

      const isVisible = await locator.isVisible().catch(() => false);
      if (!isVisible) {
        riskMap.push({
          name: region.name, risk_level: "uncertain",
          reason: "element not visible or not found", key_elements: [],
          confidence: 0.0, latency_ms: 0,
        });
        console.log(`[agent-audit] region="${region.name}" skipped (not visible)`);
        continue;
      }

      const img = await captureRegion(locator);
      analysis = await analyzeRegion(img, region.name, RISK_SYSTEM, RISK_QUESTION);

      const rawLevel = String(analysis.raw.risk_level ?? "uncertain");
      const VALID_LEVELS: RiskLevel[] = ["likely_ok", "suspicious", "likely_broken", "uncertain"];
      const riskLevel: RiskLevel = VALID_LEVELS.includes(rawLevel as RiskLevel)
        ? (rawLevel as RiskLevel) : "uncertain";

      const rawElements = analysis.raw.key_elements;
      const keyElements: string[] = Array.isArray(rawElements)
        ? (rawElements as unknown[]).slice(0, 3).map(String)
        : [];

      riskMap.push({
        name: region.name,
        risk_level: riskLevel,
        reason: String(analysis.raw.reason ?? ""),
        key_elements: keyElements,
        confidence: riskConfidence(riskLevel),
        latency_ms: analysis.latency_ms,
      });

      logVisionResult(`agent-scan:${region.name}`, analysis, `risk=${riskLevel}`);

    } catch (err) {
      const msg = (err as Error).message.slice(0, 80);
      riskMap.push({
        name: region.name, risk_level: "uncertain",
        reason: `analysis error: ${msg}`, key_elements: [],
        confidence: 0.0, latency_ms: analysis?.latency_ms ?? 0,
      });
      console.log(`[agent-audit] region="${region.name}" error: ${msg}`);
    }
  }

  // ── Summary ────────────────────────────────────────────────────────────────
  const summary: Record<RiskLevel, number> = {
    likely_ok: 0, suspicious: 0, likely_broken: 0, uncertain: 0,
  };
  for (const r of riskMap) summary[r.risk_level]++;

  // ── Recommendations ────────────────────────────────────────────────────────
  const recommendations: string[] = [];
  for (const r of riskMap) {
    if (r.risk_level === "suspicious") {
      recommendations.push(
        `[suspicious] "${r.name}" — consider adding a deterministic test. Reason: ${r.reason}`,
      );
    }
    if (r.risk_level === "likely_broken") {
      recommendations.push(
        `[BROKEN] "${r.name}" — add regression test immediately. Reason: ${r.reason}`,
      );
    }
  }
  if (recommendations.length === 0) {
    recommendations.push("All scanned regions appear healthy. No immediate action required.");
  }

  const report: AgentAuditReport = {
    generated_at: new Date().toISOString(),
    page: "runtime",
    model: "gemma3:4b",
    regions_scanned: riskMap.length,
    risk_map: riskMap,
    summary,
    recommendations,
  };

  writeReport(report);

  console.log(
    `[agent-audit] page=runtime regions=${riskMap.length} ` +
    `ok=${summary.likely_ok} suspicious=${summary.suspicious} ` +
    `broken=${summary.likely_broken} uncertain=${summary.uncertain}`,
  );
  console.log(`[agent-audit] report → ${REPORT_PATH}`);

  // No test.fail() calls — this is a report-only exploratory spec.
  // To graduate a suspicious finding into a deterministic test,
  // add it to tests/visual/interaction.spec.ts with vision loop + cross-check.
});
