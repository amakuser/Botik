/**
 * Layout integrity suite — JS-based, no pixel baselines needed.
 * Checks every page for horizontal overflow, zero-height containers, and left-edge clipping.
 * Fast and deterministic: passes on any machine without pre-generated snapshots.
 */

import { expect, test } from "@playwright/test";
import { checkLayoutIntegrity, waitForStableUI } from "./helpers";

const BASE = "http://127.0.0.1:4173";

const PAGES = [
  { name: "home",        url: "/" },
  { name: "health",      url: "/health" },
  { name: "jobs",        url: "/jobs" },
  { name: "logs",        url: "/logs" },
  { name: "runtime",     url: "/runtime" },
  { name: "spot",        url: "/spot" },
  { name: "futures",     url: "/futures" },
  { name: "telegram",    url: "/telegram" },
  { name: "analytics",   url: "/analytics" },
  { name: "models",      url: "/models" },
  { name: "diagnostics", url: "/diagnostics" },
  { name: "settings",    url: "/settings" },
  { name: "market",      url: "/market" },
  { name: "orderbook",   url: "/orderbook" },
  { name: "backtest",    url: "/backtest" },
];

for (const { name, url } of PAGES) {
  test(`layout: ${name} — no overflow, clipping, or zero-height containers`, async ({ page }) => {
    await page.goto(`${BASE}${url}`);
    await waitForStableUI(page);

    const issues = await checkLayoutIntegrity(page);
    expect(
      issues,
      `Layout issues on ${name}:\n${issues.map(i => `  [${i.issue}] ${i.selector}: ${i.detail}`).join("\n")}`,
    ).toHaveLength(0);
  });
}
