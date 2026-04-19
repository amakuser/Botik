import type { Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { VISION_MODE, LLM_MODEL, LLM_MAX_TOKENS, SCREENSHOTS_DIR, ARTIFACTS_DIR, REPORT_PATH } from "./vision.config";
import { VISION_PROMPT } from "./vision.prompts";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface VisionIssue {
  type: "overlap" | "clipping" | "misalignment" | "visual-noise" | "contrast" | "hierarchy";
  severity: "low" | "medium" | "high";
  description: string;
  location_hint: string;
  confidence: number;
}

export interface VisionReport {
  issues: VisionIssue[];
  summary: string;
  confidence: number;
  mode: "llm" | "heuristic";
}

// ── Stable mock fixtures (same data as regression.spec.ts) ────────────────────

const MODELS_FIXTURE = {
  generated_at: "2026-01-01T00:00:00Z",
  source_mode: "fixture",
  summary: {
    total_models: 0, active_declared_count: 0, ready_scopes: 0, recent_training_runs_count: 0,
    latest_run_scope: "not available", latest_run_status: "not available",
    latest_run_mode: "not available", manifest_status: "missing", db_available: false,
  },
  scopes: [], registry_entries: [], recent_training_runs: [],
  truncated: { registry_entries: false, recent_training_runs: false },
};

const RUNTIME_OFFLINE_FIXTURE = {
  generated_at: "2026-01-01T00:00:00Z",
  runtimes: [
    {
      runtime_id: "spot", label: "Spot Runtime", state: "offline",
      pids: [], pid_count: 0, last_heartbeat_at: null, last_heartbeat_age_seconds: null,
      last_error: null, last_error_at: null,
      status_reason: "no matching runtime process detected", source_mode: "fixture",
    },
    {
      runtime_id: "futures", label: "Futures Runtime", state: "offline",
      pids: [], pid_count: 0, last_heartbeat_at: null, last_heartbeat_age_seconds: null,
      last_error: null, last_error_at: null,
      status_reason: "no matching runtime process detected", source_mode: "fixture",
    },
  ],
};

const TELEGRAM_FIXTURE = {
  generated_at: "2026-01-01T00:00:00Z",
  source_mode: "fixture",
  summary: {
    bot_profile: "default", token_profile_name: "TELEGRAM_BOT_TOKEN",
    token_configured: false, internal_bot_disabled: false,
    connectivity_state: "unknown", connectivity_detail: "Проверка не выполнялась.",
    allowed_chat_count: 0, allowed_chats_masked: [], commands_count: 0,
    alerts_count: 0, errors_count: 0, last_successful_send: null,
    last_error: null, startup_status: "unknown",
  },
  recent_commands: [], recent_alerts: [], recent_errors: [],
  truncated: { recent_commands: false, recent_alerts: false, recent_errors: false },
};

const SETTINGS_FIXTURE = {
  generated_at: "2026-01-01T00:00:00Z",
  source_mode: "unknown",
  env_file_path: null,
  env_file_exists: false,
  fields: [
    { key: "BYBIT_API_KEY",            label: "Bybit Demo API Key",       value: "", masked: true,  present: false },
    { key: "BYBIT_API_SECRET",         label: "Bybit Demo API Secret",    value: "", masked: true,  present: false },
    { key: "BYBIT_MAINNET_API_KEY",    label: "Bybit MainNet API Key",    value: "", masked: true,  present: false },
    { key: "BYBIT_MAINNET_API_SECRET", label: "Bybit MainNet API Secret", value: "", masked: true,  present: false },
    { key: "TELEGRAM_BOT_TOKEN",       label: "Telegram Bot Token",       value: "", masked: true,  present: false },
    { key: "TELEGRAM_CHAT_ID",         label: "Telegram Chat ID",         value: "", masked: false, present: false },
    { key: "DB_URL",                   label: "Database URL",             value: "", masked: false, present: false },
  ],
};

// ── Mock setup ────────────────────────────────────────────────────────────────

async function injectMock(page: Page, pattern: string | RegExp, body: unknown): Promise<void> {
  await page.route(pattern, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

export async function setupPageMocks(page: Page, pageName: string): Promise<void> {
  if (pageName === "models")   await injectMock(page, "**/models", MODELS_FIXTURE);
  if (pageName === "runtime")  await injectMock(page, "**/runtime-status", RUNTIME_OFFLINE_FIXTURE);
  if (pageName === "telegram") await injectMock(page, /127\.0\.0\.1:8765\/telegram$/, TELEGRAM_FIXTURE);
  if (pageName === "settings") await injectMock(page, /127\.0\.0\.1:8765\/settings$/, SETTINGS_FIXTURE);
}

// ── Screenshot ────────────────────────────────────────────────────────────────

export async function takeVisionScreenshot(page: Page, name: string): Promise<string> {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  const screenshotPath = path.join(SCREENSHOTS_DIR, `${name}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: false, animations: "disabled" });
  return screenshotPath;
}

// ── Heuristic analysis ────────────────────────────────────────────────────────

type RawIssue = { type: string; severity: string; description: string; location_hint: string; confidence: number };

export async function analyzeHeuristic(page: Page): Promise<VisionReport> {
  const issues = await page.evaluate((): RawIssue[] => {
    const found: RawIssue[] = [];

    // ── Helper: parse "rgb(r, g, b)" or "rgba(r, g, b, a)" ──────────────────
    function parseRgb(s: string): { r: number; g: number; b: number; a: number } | null {
      const m = s.match(/rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)/);
      if (!m) return null;
      return { r: +m[1], g: +m[2], b: +m[3], a: m[4] !== undefined ? +m[4] : 1 };
    }

    // ── Helper: perceived luminance (BT.601) ────────────────────────────────
    function luminance(r: number, g: number, b: number): number {
      return 0.299 * r + 0.587 * g + 0.114 * b;
    }

    // ── Helper: describe element position ───────────────────────────────────
    function locationHint(el: Element): string {
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const hPos = cx < vw / 3 ? "left" : cx > (vw * 2) / 3 ? "right" : "center";
      const vPos = cy < vh / 3 ? "top" : cy > (vh * 2) / 3 ? "bottom" : "middle";
      const tag = el.tagName.toLowerCase();
      const cls = el.className && typeof el.className === "string"
        ? el.className.trim().split(/\s+/)[0] : "";
      return `${vPos}-${hPos} — <${tag}${cls ? `.${cls}` : ""}>`;
    }

    // ── Check 1: Text too small (< 11px) ────────────────────────────────────
    const textSelectors = ["h1", "h2", "h3", "p", "span", "button", "a", "label", "td", "th", "li"];
    for (const sel of textSelectors) {
      for (const el of Array.from(document.querySelectorAll<HTMLElement>(sel))) {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const text = (el.textContent ?? "").trim();
        if (!text) continue;

        const fontSize = parseFloat(style.fontSize);
        if (fontSize < 8) {
          found.push({
            type: "contrast",
            severity: "high",
            description: `Text rendered at ${Math.round(fontSize)}px — below readable minimum. Content: "${text.slice(0, 40)}"`,
            location_hint: locationHint(el),
            confidence: 0.9,
          });
        } else if (fontSize < 11) {
          found.push({
            type: "contrast",
            severity: "low",
            description: `Text at ${Math.round(fontSize)}px may be difficult to read. Content: "${text.slice(0, 40)}"`,
            location_hint: locationHint(el),
            confidence: 0.75,
          });
        }
      }
    }

    // ── Check 2: Low contrast ────────────────────────────────────────────────
    // Walks up the DOM for effective background, but stops at any gradient/image.
    // This prevents false positives from elements with CSS linear-gradient backgrounds
    // (e.g. .button-primary), where getComputedStyle.backgroundColor is transparent
    // even though the visual background is a solid-looking gradient.
    const contrastSelectors = ["h1", "h2", "h3", "p", "button", "a", "label", ".status-chip", ".surface-badge"];
    for (const sel of contrastSelectors) {
      for (const el of Array.from(document.querySelectorAll<HTMLElement>(sel))) {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const text = (el.textContent ?? "").trim();
        if (!text) continue;

        const fgColor = parseRgb(style.color);
        if (!fgColor) continue;

        // Walk up to find effective background; bail if a gradient is encountered.
        let bgColor: { r: number; g: number; b: number } | null = null;
        let bgNode: Element | null = el;
        while (bgNode) {
          const bgStyle = getComputedStyle(bgNode);
          const bgImage = bgStyle.backgroundImage;
          // Gradient or image background: can't determine reliable contrast, skip this element.
          if (bgImage && bgImage !== "none") { bgColor = null; break; }
          const parsed = parseRgb(bgStyle.backgroundColor);
          if (parsed && parsed.a > 0.1) { bgColor = parsed; break; }
          bgNode = bgNode.parentElement;
        }
        if (!bgColor) continue;

        const fgLum = luminance(fgColor.r, fgColor.g, fgColor.b);
        const bgLum = luminance(bgColor.r, bgColor.g, bgColor.b);
        const diff = Math.abs(fgLum - bgLum);

        if (diff < 20) {
          found.push({
            type: "contrast",
            severity: "high",
            description: `Very low contrast between text and background (luminance diff: ${Math.round(diff)}). Text: "${text.slice(0, 40)}"`,
            location_hint: locationHint(el),
            confidence: 0.8,
          });
        } else if (diff < 30) {
          found.push({
            type: "contrast",
            severity: "medium",
            description: `Low contrast (luminance diff: ${Math.round(diff)}). Text: "${text.slice(0, 40)}"`,
            location_hint: locationHint(el),
            confidence: 0.6,
          });
        }
      }
    }

    // ── Check 3: Element overlap (interactive elements intersecting) ──────────
    const interactiveSelectors = ["button", "a[href]", "input", "[role='button']"];
    const rects: Array<{ el: Element; rect: DOMRect }> = [];
    for (const sel of interactiveSelectors) {
      for (const el of Array.from(document.querySelectorAll(sel))) {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") continue;
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) continue;
        rects.push({ el, rect: r });
      }
    }
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i].rect;
        const b = rects[j].rect;
        const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (overlapX > 4 && overlapY > 4) {
          const overlapArea = overlapX * overlapY;
          const smallerArea = Math.min(a.width * a.height, b.width * b.height);
          // Only flag if overlap is >15% of the smaller element
          if (smallerArea > 0 && overlapArea / smallerArea > 0.15) {
            found.push({
              type: "overlap",
              severity: "high",
              description: `Interactive elements overlap by ${Math.round(overlapArea)}px² (${Math.round((overlapArea / smallerArea) * 100)}% of smaller element)`,
              location_hint: locationHint(rects[i].el),
              confidence: 0.85,
            });
          }
        }
      }
    }

    // ── Check 4: Visible panel with no rendered content ───────────────────────
    for (const panel of Array.from(document.querySelectorAll<HTMLElement>(".panel, [class*='card']"))) {
      const style = getComputedStyle(panel);
      if (style.display === "none" || style.visibility === "hidden") continue;
      const rect = panel.getBoundingClientRect();
      if (rect.width < 50 || rect.height < 50) continue;
      // Only flag panels that have substantial size but no visible text at all
      const visibleText = (panel.textContent ?? "").trim().replace(/\s+/g, " ");
      if (visibleText.length === 0 && rect.height > 100) {
        found.push({
          type: "visual-noise",
          severity: "medium",
          description: `Visible panel/card has no rendered text content (${Math.round(rect.width)}×${Math.round(rect.height)}px)`,
          location_hint: locationHint(panel),
          confidence: 0.7,
        });
      }
    }

    return found;
  });

  const high = issues.filter(i => i.severity === "high").length;
  const total = issues.length;
  const summary = total === 0
    ? "No visual issues detected by heuristic analysis."
    : `Heuristic analysis found ${total} issue(s): ${high} high-severity.`;

  return {
    issues: issues as VisionIssue[],
    summary,
    confidence: 0.75, // heuristic analysis is inherently approximate
    mode: "heuristic",
  };
}

// ── LLM analysis ──────────────────────────────────────────────────────────────

export async function analyzeWithLLM(screenshotPath: string): Promise<VisionReport> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set — cannot use LLM mode");

  const imageData = fs.readFileSync(screenshotPath);
  const base64Image = imageData.toString("base64");

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: LLM_MODEL,
      max_tokens: LLM_MAX_TOKENS,
      messages: [
        {
          role: "user",
          content: [
            {
              type: "image",
              source: { type: "base64", media_type: "image/png", data: base64Image },
            },
            { type: "text", text: VISION_PROMPT },
          ],
        },
      ],
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Anthropic API error ${response.status}: ${errorText}`);
  }

  const data = await response.json() as { content: Array<{ type: string; text: string }> };
  const rawText = data.content.find(c => c.type === "text")?.text ?? "";

  // Extract JSON from the response (LLM may wrap in code block)
  const jsonMatch = rawText.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error(`LLM returned no JSON. Raw response:\n${rawText.slice(0, 500)}`);

  const parsed = JSON.parse(jsonMatch[0]) as { issues: VisionIssue[]; summary: string; confidence: number };

  return {
    issues: parsed.issues ?? [],
    summary: parsed.summary ?? "No summary provided.",
    confidence: parsed.confidence ?? 0.5,
    mode: "llm",
  };
}

// ── Orchestrator ──────────────────────────────────────────────────────────────

export async function runVisionAnalysis(page: Page, pageName: string): Promise<VisionReport> {
  const screenshotPath = await takeVisionScreenshot(page, pageName);

  if (VISION_MODE === "llm") {
    try {
      return await analyzeWithLLM(screenshotPath);
    } catch (err) {
      console.warn(`[vision] LLM analysis failed for "${pageName}", falling back to heuristic: ${(err as Error).message}`);
      const report = await analyzeHeuristic(page);
      return { ...report, mode: "heuristic" };
    }
  }

  return analyzeHeuristic(page);
}

// ── Report accumulator ────────────────────────────────────────────────────────

interface GlobalReport {
  generated_at: string;
  vision_mode: string;
  strict_mode: boolean;
  pages: Record<string, Omit<VisionReport, "mode">>;
  totals: { high: number; medium: number; low: number };
}

let _report: GlobalReport | null = null;

export function initReport(strictMode: boolean): void {
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  _report = {
    generated_at: new Date().toISOString(),
    vision_mode: VISION_MODE,
    strict_mode: strictMode,
    pages: {},
    totals: { high: 0, medium: 0, low: 0 },
  };
}

export function appendToReport(pageName: string, report: VisionReport): void {
  if (!_report) return;
  _report.pages[pageName] = { issues: report.issues, summary: report.summary, confidence: report.confidence };
  for (const issue of report.issues) {
    _report.totals[issue.severity]++;
  }
}

export function finalizeReport(): void {
  if (!_report) return;
  fs.writeFileSync(REPORT_PATH, JSON.stringify(_report, null, 2), "utf-8");
  console.log(`[vision] Report written → ${REPORT_PATH}`);
  console.log(`[vision] Totals: high=${_report.totals.high} medium=${_report.totals.medium} low=${_report.totals.low}`);
}
