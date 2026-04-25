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

// ── Region size / readability ─────────────────────────────────────────────────

export interface RegionSize {
  width: number;
  height: number;
  font_size_px: number | null;
}

/**
 * Returns the pixel size of a locator and its computed font-size (if any text).
 *
 * Use before a vision call on small regions: gemma3:4b becomes unreliable below
 * ~80×40 px (active_nav_styling signal probe: 0/3 on a compact sidebar link).
 * Known-reliable signals (status badge, error text, panel visibility) all use
 * regions ≥ 300×100 px.
 *
 * This is a DOM helper — no vision call, no network.
 */
export async function measureRegion(locator: Locator): Promise<RegionSize> {
  const box = await locator.boundingBox();
  if (!box) return { width: 0, height: 0, font_size_px: null };
  const fontSize = await locator.evaluate((el) => {
    const fs = getComputedStyle(el as HTMLElement).fontSize;
    const m = fs.match(/([\d.]+)px/);
    return m ? parseFloat(m[1]) : null;
  }).catch(() => null);
  return { width: Math.round(box.width), height: Math.round(box.height), font_size_px: fontSize };
}

/**
 * Minimum region dimensions for reliable gemma3:4b vision analysis.
 *
 * Empirical thresholds from scripts/probe_vision_signals.mjs (2026-04-21):
 *  - runtime card (≈360×220 px, badge font 12-13 px)         → 100% reliable
 *  - jobs error panel (≈520×360 px, body font 14 px)         → 100% reliable
 *  - telegram check result (≈520×72 px, state font 16 px)    → 100% reliable
 *  - sidebar nav link (≈220×36 px, font 14 px, subtle bg)    → 0% reliable
 *
 * Rule of thumb:
 *  - width  ≥ 120 px
 *  - height ≥ 60 px
 *  - font   ≥ 12 px
 *  - the region must have visible chrome (border, badge, icon, color block).
 *    Subtle CSS states like .is-active on nav links are NOT reliably readable.
 */
export const VISION_REGION_MIN = { width: 120, height: 60, font_size_px: 12 } as const;

/**
 * Returns true if a region is large enough + has big-enough text for gemma3:4b
 * to analyse reliably. When false, the caller should either enlarge the crop
 * (capture a parent panel) or rely on DOM assertions only.
 */
export function isRegionVisionReady(size: RegionSize): boolean {
  return (
    size.width >= VISION_REGION_MIN.width &&
    size.height >= VISION_REGION_MIN.height &&
    (size.font_size_px === null || size.font_size_px >= VISION_REGION_MIN.font_size_px)
  );
}

// ── Region layout sanity (post-action DOM check, no pixels involved) ─────────

export interface RegionLayoutCheck {
  /** Whether the element is in the DOM + offsetParent non-null + box > 0x0. */
  visible: boolean;
  /** Whether the box fits the minimum useful region (VISION_REGION_MIN). */
  sane_dimensions: boolean;
  /** Whether the element (or its descendants) has any rendered text. */
  has_content: boolean;
  size: RegionSize;
  text_length: number;
}

/**
 * DOM-only sanity check that a region remains usable AFTER a user action:
 *   - still visible (not collapsed / not hidden)
 *   - dimensions remain within VISION_REGION_MIN
 *   - contains non-empty text (so it is not a blank stub)
 * Use after fillField/clickByRole to confirm the UI did not silently
 * deflate the target area. No vision call.
 */
export async function checkRegionLayoutSanity(locator: Locator): Promise<RegionLayoutCheck> {
  const size = await measureRegion(locator);
  const visible = await locator.isVisible().catch(() => false);
  const text = await locator.textContent().catch(() => null);
  const textLen = (text ?? "").replace(/\s+/g, " ").trim().length;
  return {
    visible,
    sane_dimensions: isRegionVisionReady(size),
    has_content: textLen > 0,
    size,
    text_length: textLen,
  };
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
