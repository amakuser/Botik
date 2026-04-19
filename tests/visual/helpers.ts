import type { Locator, Page } from "@playwright/test";

/** Wait for page to be visually stable — DOM loaded + Framer Motion animations settled. */
export async function waitForStableUI(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);
}

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
