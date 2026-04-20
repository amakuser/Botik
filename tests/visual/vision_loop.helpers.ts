/**
 * Vision loop helpers — gemma3:4b integration for interaction tests.
 *
 * Implements the ACTION → SNAPSHOT → ANALYSIS → DECISION loop using a local
 * Ollama vision model. All analysis functions are only called when the caller
 * checks isOllamaVisionEnabled(), so existing CI pipelines are unaffected.
 *
 * Model:    gemma3:4b  (1.4s warm, JSON 100%, region crops ~400-500px)
 * Endpoint: http://127.0.0.1:11434/api/chat
 *
 * HTTP transport: node:http — bypasses any HTTPS_PROXY env var set for Ollama
 * model downloads (proxy is irrelevant for loopback requests).
 *
 * Enable:   OLLAMA_VISION=1 npx playwright test ...
 */

import type { Locator } from "@playwright/test";
import * as http from "node:http";

const OLLAMA_HOST = "127.0.0.1";
const OLLAMA_PORT = 11434;
const OLLAMA_MODEL = "gemma3:4b";

// ── Enable guard ───────────────────────────────────────────────────────────────

/** Returns true when OLLAMA_VISION=1 is set in the environment. */
export function isOllamaVisionEnabled(): boolean {
  return process.env.OLLAMA_VISION === "1";
}

// ── Region capture ─────────────────────────────────────────────────────────────

/**
 * Captures a PNG screenshot of the given locator region.
 * Uses Playwright's locator.screenshot() — no full-page capture, animations disabled.
 */
export async function captureRegion(locator: Locator): Promise<Buffer> {
  return Buffer.from(await locator.screenshot({ animations: "disabled" }));
}

// ── Ollama transport (direct loopback, no proxy) ───────────────────────────────

interface OllamaResponse {
  content: string;
  latency_ms: number;
}

function postToOllama(payload: string, timeoutMs = 30_000): Promise<OllamaResponse> {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    const req = http.request(
      {
        hostname: OLLAMA_HOST,
        port: OLLAMA_PORT,
        path: "/api/chat",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
        },
      },
      (res) => {
        let body = "";
        res.on("data", (chunk: string) => { body += chunk; });
        res.on("end", () => {
          try {
            const data = JSON.parse(body) as { message: { content: string } };
            resolve({ content: data.message.content, latency_ms: Date.now() - t0 });
          } catch {
            reject(new Error(`Ollama response parse error: ${body.slice(0, 300)}`));
          }
        });
      },
    );
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`Ollama request timed out after ${timeoutMs}ms`));
    });
    req.write(payload);
    req.end();
  });
}

// ── Core analysis ──────────────────────────────────────────────────────────────

export interface RegionAnalysis {
  raw: Record<string, unknown>;
  latency_ms: number;
  model: string;
  region: string;
}

/**
 * Sends a region image to gemma3:4b for JSON analysis.
 *
 * @param imageBytes  PNG buffer from captureRegion()
 * @param region      Human-readable name for logging (e.g. "runtime.card.spot@before")
 * @param systemPrompt  Defines the expected JSON schema
 * @param question    Specific question about the image
 */
export async function analyzeRegion(
  imageBytes: Buffer,
  region: string,
  systemPrompt: string,
  question: string,
): Promise<RegionAnalysis> {
  const imageB64 = imageBytes.toString("base64");
  const payload = JSON.stringify({
    model: OLLAMA_MODEL,
    format: "json",
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: question, images: [imageB64] },
    ],
    stream: false,
    options: { temperature: 0, num_predict: 100 },
  });

  const { content, latency_ms } = await postToOllama(payload);

  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(content) as Record<string, unknown>;
  } catch {
    raw = { _unparseable: content.slice(0, 200) };
  }

  return { raw, latency_ms, model: OLLAMA_MODEL, region };
}

// ── Element state classifier ───────────────────────────────────────────────────

export interface StateClassification {
  badge: "RUNNING" | "OFFLINE" | "UNKNOWN";
  color: "green" | "red" | "gray" | "other";
}

/**
 * Classifies the runtime status badge in a card region.
 *
 * Scope: the small badge in the top-right corner of a RuntimeStatusCard.
 * NOT for detecting action error banners — use detectActionBanner() for that.
 */
export async function classifyElementState(
  imageBytes: Buffer,
  region: string,
): Promise<{ result: StateClassification; analysis: RegionAnalysis }> {
  const analysis = await analyzeRegion(
    imageBytes,
    region,
    'UI state inspector. Respond with JSON only: {"badge": "RUNNING|OFFLINE|UNKNOWN", "color": "green|red|gray|other"}',
    "What is the status badge text and color in the top-right corner of this card?",
  );

  const rawBadge = String(analysis.raw.badge ?? "UNKNOWN").toUpperCase();
  const rawColor = String(analysis.raw.color ?? "other").toLowerCase();

  const badge = (["RUNNING", "OFFLINE", "UNKNOWN"].includes(rawBadge)
    ? rawBadge
    : "UNKNOWN") as StateClassification["badge"];

  const color = (["green", "red", "gray", "other"].includes(rawColor)
    ? rawColor
    : "other") as StateClassification["color"];

  return { result: { badge, color }, analysis };
}

// ── Action banner detector ─────────────────────────────────────────────────────

export interface ActionBannerResult {
  has_action_banner: boolean;
  banner_type: "error" | "success" | "warning" | null;
  text: string | null;
}

/**
 * Detects a standalone action result notification in a region.
 *
 * "Action banner" = a notification that appears as a result of a user action
 * (e.g. "Error: failed to start job"). This is distinct from status badges
 * embedded inside component cards (RUNNING/OFFLINE).
 *
 * The question wording intentionally excludes persistent status indicators
 * to avoid the false-positive pattern where both models misread OFFLINE badges
 * as error banners.
 */
export async function detectActionBanner(
  imageBytes: Buffer,
  region: string,
): Promise<{ result: ActionBannerResult; analysis: RegionAnalysis }> {
  const analysis = await analyzeRegion(
    imageBytes,
    region,
    'UI inspector. Respond with JSON only: {"has_action_banner": true|false, "banner_type": "error|success|warning|null", "text": "notification text or null"}',
    "Is there a standalone notification box or alert that appeared as a result of a user action (not a card status badge)?",
  );

  const bannerType = analysis.raw.banner_type as string | null;
  const validTypes = ["error", "success", "warning"];

  return {
    result: {
      has_action_banner: Boolean(analysis.raw.has_action_banner),
      banner_type: (bannerType && validTypes.includes(bannerType)
        ? bannerType
        : null) as ActionBannerResult["banner_type"],
      text: (analysis.raw.text as string | undefined) ?? null,
    },
    analysis,
  };
}

// ── Panel visibility detector ──────────────────────────────────────────────────

export interface PanelVisibilityResult {
  panel_visible: boolean;
  primary_label: string | null;
}

/**
 * Checks whether a result panel is rendered and identifies its primary status label.
 * Used to confirm that an action produced a visible response panel (e.g. connectivity check result).
 */
export async function detectPanelVisibility(
  imageBytes: Buffer,
  region: string,
): Promise<{ result: PanelVisibilityResult; analysis: RegionAnalysis }> {
  const analysis = await analyzeRegion(
    imageBytes,
    region,
    'UI inspector. Respond with JSON only: {"panel_visible": true|false, "primary_label": "most prominent single status word shown or null"}',
    "Is a result or status panel visible in this region? What is the most prominent status word shown (e.g. healthy, error, unknown)?",
  );

  return {
    result: {
      panel_visible: Boolean(analysis.raw.panel_visible),
      primary_label: (analysis.raw.primary_label as string | undefined) ?? null,
    },
    analysis,
  };
}

// ── State comparison ───────────────────────────────────────────────────────────

export type StateDecision =
  | "transition_confirmed"   // badge changed to expected value
  | "no_change"              // badge did not change
  | "unexpected_state";      // badge changed but to wrong value

export interface StateComparison {
  changed: boolean;
  from_badge: string;
  to_badge: string;
  decision: StateDecision;
}

/**
 * Compares before/after state classifications to confirm a state transition.
 * Pure function — no model call.
 *
 * @param expected  The expected { from, to } badge transition (e.g. OFFLINE → RUNNING)
 */
export function compareStates(
  before: StateClassification,
  after: StateClassification,
  expected: { from: StateClassification["badge"]; to: StateClassification["badge"] },
): StateComparison {
  const changed = before.badge !== after.badge;
  const decision: StateDecision =
    after.badge === expected.to
      ? "transition_confirmed"
      : changed
        ? "unexpected_state"
        : "no_change";

  return { changed, from_badge: before.badge, to_badge: after.badge, decision };
}

// ── Logging ────────────────────────────────────────────────────────────────────

/**
 * Logs a structured vision-loop result line.
 *
 * Output format:
 *   [vision-loop] scenario="..." region="..." model=... latency=...ms result={...} decision="..."
 */
export function logVisionResult(
  scenario: string,
  analysis: RegionAnalysis,
  decision: string,
): void {
  console.log(
    `[vision-loop] scenario="${scenario}" region="${analysis.region}" model=${analysis.model} ` +
      `latency=${analysis.latency_ms}ms result=${JSON.stringify(analysis.raw)} decision="${decision}"`,
  );
}
