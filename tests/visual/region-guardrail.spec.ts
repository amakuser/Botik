/**
 * Proves VS-8 guardrail: classifiers refuse regions below VISION_REGION_MIN
 * without calling the model, and surface a structured reason instead of an
 * empty-JSON silent "pass".
 *
 * Runs only with OLLAMA_VISION=1 so the skip-vs-call distinction is meaningful.
 * No baseline screenshots — purely structural assertions.
 */

import { expect, test } from "@playwright/test";
import { waitForStableUI } from "./helpers";
import {
  classifyElementState,
  detectErrorText,
  detectPanelVisibility,
  isOllamaVisionEnabled,
  logVisionResult,
} from "./vision_loop.helpers";

const BASE = "http://127.0.0.1:4173";

test("guardrail: classifiers skip too-small regions with structured reason", async ({ page }) => {
  test.skip(!isOllamaVisionEnabled(), "OLLAMA_VISION=1 required so skip-vs-call is observable");

  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  // A single sidebar nav link is intentionally small chrome: width ~200, but
  // height ~36 which is below VISION_REGION_MIN.height=60. The signal probe
  // already showed active-link detection is 0/3 reliable on gemma3:4b, so
  // the guardrail should refuse before the model call.
  const tinyNavLink = page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "Состояние системы", exact: true });

  // ── classifyElementState skips ────────────────────────────────────────
  const stateRes = await classifyElementState(tinyNavLink, "nav-link-too-small@guardrail");
  logVisionResult("guardrail:state", stateRes.analysis,
    stateRes._too_small ? `skipped: ${stateRes.reason ?? ""}` : "CALLED model (unexpected)",
    stateRes.confidence);
  expect(stateRes._too_small, "classifyElementState must refuse sub-minimum region").toBe(true);
  expect(stateRes.confidence, "skipped classifier must report confidence=0").toBe(0);
  expect(stateRes.attempt, "skipped classifier must report attempt=0 (model never called)").toBe(0);
  expect(stateRes.analysis.latency_ms, "no model call means zero latency").toBe(0);
  expect(stateRes.analysis.raw._too_small, "raw payload must carry the skip flag for logs").toBe(true);
  expect(stateRes.reason ?? "", "reason must include the required minimum").toContain("require >=");

  // ── detectErrorText skips ─────────────────────────────────────────────
  const errRes = await detectErrorText(tinyNavLink, "nav-link-too-small@guardrail");
  logVisionResult("guardrail:error-text", errRes.analysis,
    errRes._too_small ? `skipped: ${errRes.reason ?? ""}` : "CALLED model (unexpected)",
    errRes.confidence);
  expect(errRes._too_small).toBe(true);
  expect(errRes.result.has_error, "sentinel result must be neutral (has_error=false)").toBe(false);
  expect(errRes.result.text_visible).toBe(false);
  expect(errRes.analysis.latency_ms).toBe(0);

  // ── detectPanelVisibility skips ───────────────────────────────────────
  const panelRes = await detectPanelVisibility(tinyNavLink, "nav-link-too-small@guardrail");
  logVisionResult("guardrail:panel", panelRes.analysis,
    panelRes._too_small ? `skipped: ${panelRes.reason ?? ""}` : "CALLED model (unexpected)",
    panelRes.confidence);
  expect(panelRes._too_small).toBe(true);
  expect(panelRes.result.panel_visible).toBe(false);
  expect(panelRes.result.primary_label).toBeNull();

  // ── And on a LARGE region (the full body) classifiers DO call the model ─
  // This is the inverse sanity check: the guardrail does not over-block.
  const bodyPanel = page.locator("body");
  const bodyRes = await detectPanelVisibility(bodyPanel, "body@guardrail-inverse");
  expect(bodyRes._too_small, "full body is not too small — guardrail must not over-block").toBe(false);
  expect(bodyRes.attempt, "full body triggers at least one model call").toBeGreaterThanOrEqual(1);
});
