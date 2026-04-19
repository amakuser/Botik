/**
 * Text clipping / truncation checks.
 * Detects when a UI element's text is hidden by overflow:hidden or
 * actively truncated by text-overflow:ellipsis.
 *
 * These are JS-based, deterministic, and require no baselines.
 * They fire on every page to catch regressions in label/button/badge layout.
 */

import { expect, test } from "@playwright/test";
import { checkTextClipping, waitForStableUI } from "./helpers";

const BASE = "http://127.0.0.1:4173";

// Selectors to check on every page
const LABEL_SELECTORS = ["h1", "h2", "h3", ".app-shell__nav-link", ".status-chip", ".surface-badge"];
const BUTTON_SELECTORS = ["button"];
const ALL_SELECTORS = [...LABEL_SELECTORS, ...BUTTON_SELECTORS];

// High-value pages where text clipping is most likely to surface
const PAGES_FOR_CLIP_CHECK = [
  { name: "health",   url: "/" },
  { name: "runtime",  url: "/runtime" },
  { name: "jobs",     url: "/jobs" },
  { name: "telegram", url: "/telegram" },
  { name: "spot",     url: "/spot" },
  { name: "futures",  url: "/futures" },
  { name: "models",   url: "/models" },
];

for (const { name, url } of PAGES_FOR_CLIP_CHECK) {
  test(`text-clip: ${name} — headings, buttons, nav links, chips not clipped`, async ({ page }) => {
    await page.goto(`${BASE}${url}`);
    await waitForStableUI(page);

    const issues = await checkTextClipping(page, ALL_SELECTORS);
    expect(
      issues,
      `Text clipping on ${name}:\n${issues.map(i => `  [${i.issue}] ${i.selector}: "${i.text}"`).join("\n")}`,
    ).toHaveLength(0);
  });
}

// Dedicated sidebar nav check — applies across all routes since nav is always rendered
test("text-clip: sidebar nav labels — no truncation across all routes", async ({ page }) => {
  // Navigate to the longest label in the nav to stress the sidebar width
  await page.goto(`${BASE}/`);
  await waitForStableUI(page);

  const issues = await checkTextClipping(page, [".app-shell__nav-link", ".app-shell__nav-group-title"]);
  expect(
    issues,
    `Nav label clipping:\n${issues.map(i => `  [${i.issue}] ${i.selector}: "${i.text}"`).join("\n")}`,
  ).toHaveLength(0);
});
