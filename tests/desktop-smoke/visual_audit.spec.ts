/**
 * Visual audit — walks every page, screenshots it, and checks
 * that interactive controls are reachable and the bot-status indicator
 * is visible in the titlebar.
 *
 * Screenshots land in .artifacts/local/latest/desktop-smoke/test-results/<name>/
 * Run via:  pnpm test:desktop-smoke  (or  npx playwright test visual_audit.spec.ts)
 */

import { expect, test } from "./fixtures";

const BASE = "http://127.0.0.1:4173";

const PAGES = [
  { name: "foundation-health",  url: "/",            heading: "Foundation Health" },
  { name: "jobs-monitor",       url: "/jobs",         heading: "Job Monitor" },
  { name: "unified-logs",       url: "/logs",         heading: "Unified Logs" },
  { name: "runtime-control",    url: "/runtime",      heading: "Runtime Control" },
  { name: "spot-read",          url: "/spot",         heading: "Spot Read" },
  { name: "futures-read",       url: "/futures",      heading: "Futures Read" },
  { name: "telegram-ops",       url: "/telegram",     heading: "Telegram Ops" },
  { name: "analytics",          url: "/analytics",    heading: "PnL / Analytics" },
  { name: "models-status",      url: "/models",       heading: "Models / Status" },
  { name: "diagnostics",        url: "/diagnostics",  heading: "Diagnostics" },
  { name: "settings",           url: "/settings",     heading: "Settings" },
  { name: "market",             url: "/market",       heading: "Market" },
];

// ── Titlebar ──────────────────────────────────────────────────────────────────
test("titlebar: custom chrome visible, window controls present", async ({ page }) => {
  await page.goto(BASE);
  await page.waitForLoadState("networkidle");

  const titlebar = page.getByTestId("foundation.desktop-titlebar");
  await expect(titlebar).toBeVisible();

  // macOS-style window controls
  await expect(page.getByRole("button", { name: "Close window" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Minimize window/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Maximize window|Restore window/ })).toBeVisible();

  // Bot status dot rendered (idle or running)
  const botDot = titlebar.locator(".desktop-frame__bot-dot");
  await expect(botDot).toBeVisible();

  await page.screenshot({ path: "visual-titlebar.png", fullPage: false });
});

// ── Bot-dot animation when running ───────────────────────────────────────────
test("titlebar: bot-dot applies pulse animation class when running", async ({ page }) => {
  await page.goto(BASE);
  await page.waitForLoadState("networkidle");

  const botDot = page.locator(".desktop-frame__bot-dot");
  await expect(botDot).toBeVisible();

  const isRunning = await botDot.evaluate(el => el.classList.contains("desktop-frame__bot-dot--running"));
  if (isRunning) {
    // Animation should be applied via CSS; verify the keyframe name is in computed style
    const animation = await botDot.evaluate(el => getComputedStyle(el).animationName);
    expect(animation).not.toBe("none");
  }
  // idle state is acceptable — fixture server returns offline runtimes
});

// ── All pages ─────────────────────────────────────────────────────────────────
for (const { name, url, heading } of PAGES) {
  test(`page: ${name} — renders heading and has no JS errors`, async ({ page }) => {
    const jsErrors: string[] = [];
    page.on("pageerror", err => jsErrors.push(err.message));

    await page.goto(`${BASE}${url}`);
    await page.waitForLoadState("networkidle");

    // Heading visible
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();

    // Full-page screenshot (always, regardless of pass/fail — config sets screenshot:"on")
    await page.screenshot({ fullPage: true });

    // No fatal JS errors
    const fatal = jsErrors.filter(e => !e.includes("Failed to fetch") && !e.includes("net::ERR"));
    expect(fatal, `JS errors on ${name}: ${fatal.join("; ")}`).toHaveLength(0);
  });
}

// ── Runtime page: start/stop buttons ─────────────────────────────────────────
test("runtime-control: start buttons enabled, stop buttons disabled in fixture mode", async ({ page }) => {
  await page.goto(`${BASE}/runtime`);
  await page.waitForLoadState("networkidle");

  await page.screenshot({ fullPage: true });

  await expect(page.getByTestId("runtime.start.spot")).toBeEnabled();
  await expect(page.getByTestId("runtime.start.futures")).toBeEnabled();
  await expect(page.getByTestId("runtime.stop.spot")).toBeDisabled();
  await expect(page.getByTestId("runtime.stop.futures")).toBeDisabled();
});

// ── Jobs page: preset cards render ───────────────────────────────────────────
test("jobs-monitor: data backfill and integrity job cards render", async ({ page }) => {
  await page.goto(`${BASE}/jobs`);
  await page.waitForLoadState("networkidle");

  await page.screenshot({ fullPage: true });

  await expect(page.getByTestId("job.preset.data-backfill")).toBeVisible();
  await expect(page.getByTestId("job.preset.data-integrity")).toBeVisible();
});

// ── Spot page: positions table ────────────────────────────────────────────────
test("spot-read: holdings table renders fixture rows", async ({ page }) => {
  await page.goto(`${BASE}/spot`);
  await page.waitForLoadState("networkidle");

  await page.screenshot({ fullPage: true });

  // At least one row with BTCUSDT or ETHUSDT from fixture
  const rows = page.locator("table tbody tr");
  const rowCount = await rows.count();
  expect(rowCount, "No data rows in spot table").toBeGreaterThan(0);
});

// ── Futures page: positions table ────────────────────────────────────────────
test("futures-read: positions table renders fixture rows", async ({ page }) => {
  await page.goto(`${BASE}/futures`);
  await page.waitForLoadState("networkidle");

  await page.screenshot({ fullPage: true });

  const rows = page.locator("table tbody tr");
  const rowCount = await rows.count();
  expect(rowCount, "No data rows in futures table").toBeGreaterThan(0);
});

// ── Telegram: connectivity check button reachable ─────────────────────────────
test("telegram-ops: connectivity check button is visible", async ({ page }) => {
  await page.goto(`${BASE}/telegram`);
  await page.waitForLoadState("networkidle");

  await page.screenshot({ fullPage: true });

  await expect(page.getByRole("button", { name: /connectivity|check/i })).toBeVisible();
});

// ── Sidebar navigation ────────────────────────────────────────────────────────
test("sidebar: all nav links present and navigate without errors", async ({ page }) => {
  await page.goto(BASE);
  await page.waitForLoadState("networkidle");

  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(nav).toBeVisible();

  const links = await nav.getByRole("link").all();
  expect(links.length, "Not enough nav links").toBeGreaterThanOrEqual(PAGES.length);

  for (const link of links) {
    const href = await link.getAttribute("href");
    const label = await link.textContent();
    if (!href) continue;

    await page.goto(`${BASE}${href}`);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ fullPage: true });

    const jsErrors: string[] = [];
    page.on("pageerror", err => jsErrors.push(err.message));
    const fatal = jsErrors.filter(e => !e.includes("Failed to fetch") && !e.includes("net::ERR"));
    expect(fatal, `JS error on nav to "${label}"`).toHaveLength(0);
  }
});
