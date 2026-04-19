import type { Locator, Page, Route } from "@playwright/test";

// ── Stability ──────────────────────────────────────────────────────────────────

/** Wait for page to be visually stable — DOM loaded + Framer Motion animations settled. */
export async function waitForStableUI(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);
}

// ── Layout integrity ───────────────────────────────────────────────────────────

export interface LayoutIssue {
  selector: string;
  issue: "overflow-x" | "zero-height" | "clipped";
  detail: string;
}

/**
 * JS-based layout integrity check.
 * Detects: horizontal overflow, zero-height visible containers, left-edge clipping.
 * Returns an empty array when the layout is clean.
 */
export async function checkLayoutIntegrity(page: Page): Promise<LayoutIssue[]> {
  return page.evaluate((): LayoutIssue[] => {
    const issues: LayoutIssue[] = [];
    const viewportW = window.innerWidth;

    const selectors = ["main", "[role='main']", "section", ".app-route", "table", "thead", "tbody"];

    for (const sel of selectors) {
      const els = Array.from(document.querySelectorAll<HTMLElement>(sel));
      for (const el of els) {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);

        if (style.display === "none" || style.visibility === "hidden") continue;
        if (el.getAttribute("aria-hidden") === "true") continue;

        const tag = el.tagName.toLowerCase();
        const id = el.id ? `#${el.id}` : "";
        const cls = el.className && typeof el.className === "string"
          ? `.${el.className.trim().split(/\s+/)[0]}`
          : "";
        const desc = `${tag}${id}${cls}`;

        if (rect.height === 0 && el.children.length > 0) {
          issues.push({ selector: desc, issue: "zero-height", detail: `children=${el.children.length}` });
        }
        if (rect.right > viewportW + 2) {
          issues.push({ selector: desc, issue: "overflow-x", detail: `right=${Math.round(rect.right)} > vp=${viewportW}` });
        }
        if (rect.left < -2 && style.position !== "fixed" && style.position !== "sticky") {
          issues.push({ selector: desc, issue: "clipped", detail: `left=${Math.round(rect.left)}` });
        }
      }
    }

    return issues;
  });
}

// ── Text clipping ──────────────────────────────────────────────────────────────

export interface ClipIssue {
  selector: string;
  text: string;
  issue: "ellipsis-active" | "scroll-clipped";
}

/**
 * JS-based text clipping check.
 * Detects elements where overflow: hidden clips text OR text-overflow: ellipsis is active.
 * Checks elements matching the given CSS selectors (defaults to common interactive/label elements).
 */
export async function checkTextClipping(
  page: Page,
  selectors = ["h1", "h2", "h3", "button", "a", ".status-chip", ".surface-badge", ".app-shell__nav-link"],
): Promise<ClipIssue[]> {
  return page.evaluate((sels: string[]): ClipIssue[] => {
    const issues: ClipIssue[] = [];

    for (const sel of sels) {
      const els = Array.from(document.querySelectorAll<HTMLElement>(sel));
      for (const el of els) {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") continue;
        if (el.getAttribute("aria-hidden") === "true") continue;

        const text = (el.textContent ?? "").trim();
        if (!text) continue;

        const tag = el.tagName.toLowerCase();
        const id = el.id ? `#${el.id}` : "";
        const cls = el.className && typeof el.className === "string"
          ? `.${el.className.trim().split(/\s+/)[0]}`
          : "";
        const desc = `${tag}${id}${cls}`;

        // Ellipsis is visually active when: overflow hidden AND text-overflow ellipsis AND content wider than box
        const hasEllipsisStyle =
          style.overflow === "hidden" || style.overflowX === "hidden";
        const hasEllipsisText = style.textOverflow === "ellipsis";
        if (hasEllipsisStyle && hasEllipsisText && el.scrollWidth > el.clientWidth) {
          issues.push({ selector: desc, text: text.slice(0, 60), issue: "ellipsis-active" });
        }

        // Text is hidden by overflow:hidden without ellipsis — scroll-clipped
        if (
          (style.overflow === "hidden" || style.overflowX === "hidden") &&
          !hasEllipsisText &&
          el.scrollWidth > el.clientWidth + 2
        ) {
          issues.push({ selector: desc, text: text.slice(0, 60), issue: "scroll-clipped" });
        }
      }
    }

    return issues;
  }, selectors);
}

// ── Dynamic masks ──────────────────────────────────────────────────────────────

/**
 * Returns locators for dynamic content (timestamps, live values) to mask
 * during pixel-regression snapshots so they don't cause spurious failures.
 */
export function getDynamicMasks(page: Page): Locator[] {
  return [
    page.locator("time"),
    page.locator("[data-testid$='-timestamp']"),
    page.locator("[data-testid$='-date']"),
    page.locator("[data-testid='health.metric-value']"),
    page.locator("[data-testid='health.pipeline-step-status']"),
    // Prices and percentages in table cells are live-data
    page.locator("table tbody td"),
  ];
}

/**
 * Returns locators for dynamic fields in a RuntimeStatusCard.
 * Masks: heartbeat age, timestamp DDs, PID value, and the generated_at row.
 */
export function getRuntimeCardDynamicMasks(page: Page, runtimeId: string): Locator[] {
  return [
    page.locator(`[data-testid="runtime.heartbeat.${runtimeId}"]`),
    page.locator(`[data-testid="runtime.pids.${runtimeId}"]`),
    // The <dl> details section contains timestamps (last heartbeat, last error)
    page.locator(`[data-testid="runtime.card.${runtimeId}"] dl dd`),
  ];
}

// ── Network interception ───────────────────────────────────────────────────────

/**
 * Intercepts all requests matching urlPattern and returns HTTP 500.
 * Must be called before page.goto().
 */
export async function injectBackendError(
  page: Page,
  urlPattern: string | RegExp,
  body = '{"detail": "Injected test error"}',
): Promise<void> {
  await page.route(urlPattern, async (route: Route) => {
    await route.fulfill({ status: 500, contentType: "application/json", body });
  });
}

/**
 * Intercepts all requests matching urlPattern and returns the given JSON body.
 * Must be called before page.goto().
 */
export async function injectMockResponse(
  page: Page,
  urlPattern: string | RegExp,
  json: unknown,
): Promise<void> {
  await page.route(urlPattern, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(json),
    });
  });
}
