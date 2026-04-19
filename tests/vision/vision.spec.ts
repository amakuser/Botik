/**
 * Vision-assisted UI review layer.
 *
 * This suite screenshots each page and runs a semantic quality analysis:
 *   VISION_MODE=llm        → sends screenshot to Claude API (requires ANTHROPIC_API_KEY)
 *   VISION_MODE=heuristic  → JS-based checks (text size, contrast, overlap, empty panels)
 *
 * Mode is auto-selected: "llm" if ANTHROPIC_API_KEY is set, otherwise "heuristic".
 *
 * Failure policy (VISION_STRICT=1, default):
 *   Fails if any issue has severity=high AND confidence>0.7.
 *
 * Report mode (VISION_STRICT=0):
 *   Never fails. Always writes .artifacts/local/latest/vision/report.json.
 *
 * Distinction from tests/visual/*:
 *   - visual tests: pixel diff, DOM geometry, text truncation
 *   - vision tests: semantic image analysis — overlap, contrast, hierarchy, misalignment
 */

import { expect, test } from "@playwright/test";
import {
  appendToReport,
  finalizeReport,
  initReport,
  runVisionAnalysis,
  setupPageMocks,
} from "./vision.helpers";
import { BASE_URL, FAIL_CONFIDENCE_THRESHOLD, VISION_MODE, VISION_STRICT } from "./vision.config";

const VISION_PAGES = [
  { name: "health",    url: "/" },
  { name: "spot",      url: "/spot" },
  { name: "futures",   url: "/futures" },
  { name: "analytics", url: "/analytics" },
  { name: "models",    url: "/models" },
  { name: "jobs",      url: "/jobs" },
  { name: "runtime",   url: "/runtime" },
  { name: "telegram",  url: "/telegram" },
  { name: "settings",  url: "/settings" },
];

test.beforeAll(() => {
  initReport(VISION_STRICT);
  console.log(`[vision] VISION_MODE=${VISION_MODE}  STRICT=${VISION_STRICT}`);
});

test.afterAll(() => {
  finalizeReport();
});

for (const { name, url } of VISION_PAGES) {
  test(`vision: ${name}`, async ({ page }) => {
    await setupPageMocks(page, name);
    await page.goto(`${BASE_URL}${url}`);

    // Wait for Framer Motion animations to settle (same as visual tests)
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(400);

    const report = await runVisionAnalysis(page, name);
    appendToReport(name, report);

    if (VISION_STRICT) {
      const blocking = report.issues.filter(
        (i) => i.severity === "high" && i.confidence > FAIL_CONFIDENCE_THRESHOLD,
      );

      expect(
        blocking,
        [
          `[vision:${name}] ${blocking.length} blocking issue(s) detected (severity=high, confidence>${FAIL_CONFIDENCE_THRESHOLD}):`,
          ...blocking.map((i) =>
            `  [${i.type}] ${i.description}\n  location: ${i.location_hint}\n  confidence: ${i.confidence}`,
          ),
          `Summary: ${report.summary}`,
        ].join("\n"),
      ).toHaveLength(0);
    }
  });
}
