/**
 * Vision loop helpers — gemma3:4b (Ollama) integration for interaction tests.
 *
 * Provides ACTION → SNAPSHOT → ANALYSIS → DECISION loop.
 * Includes: JSON schema validation, retry, confidence gating,
 * region caching, DOM cross-check, and structured logging.
 *
 * Model:    gemma3:4b  (1.4s warm, JSON 100%, region crops)
 * Endpoint: http://127.0.0.1:11434/api/chat (node:http — no proxy)
 *
 * Modes:
 *   OLLAMA_VISION=1  — enables vision loop in interaction tests
 *   OLLAMA_AGENT=1   — enables exploratory agent audit
 */

import type { Locator } from "@playwright/test";
import * as http from "node:http";

const OLLAMA_HOST = "127.0.0.1";
const OLLAMA_PORT = 11434;
const OLLAMA_MODEL = "gemma3:4b";

// ── Enable flags ───────────────────────────────────────────────────────────────

/** Returns true when OLLAMA_VISION=1 is set. */
export function isOllamaVisionEnabled(): boolean {
  return process.env.OLLAMA_VISION === "1";
}

/** Returns true when OLLAMA_AGENT=1 is set (exploratory audit mode). */
export function isOllamaAgentEnabled(): boolean {
  return process.env.OLLAMA_AGENT === "1";
}

// ── Region capture ─────────────────────────────────────────────────────────────

/**
 * Captures a PNG screenshot of the given locator region.
 * Never full-page — always a bounded region crop.
 */
export async function captureRegion(locator: Locator): Promise<Buffer> {
  return Buffer.from(await locator.screenshot({ animations: "disabled" }));
}

// ── JSON schema validation ─────────────────────────────────────────────────────

export interface SchemaValidation {
  valid: boolean;
  confidence: number;  // 0.0–1.0: fraction of keys that matched expected enum values
  issues: string[];
}

/**
 * Validates a model response against a schema spec.
 * spec maps each required key to its allowed string values.
 *
 * Example: validateSchema(raw, { badge: ["RUNNING","OFFLINE","UNKNOWN"], color: ["green","red"] })
 */
export function validateSchema(
  raw: Record<string, unknown>,
  spec: Record<string, string[]>,
): SchemaValidation {
  const issues: string[] = [];
  let matched = 0;
  const keys = Object.keys(spec);

  for (const key of keys) {
    if (!(key in raw)) {
      issues.push(`missing key: ${key}`);
      continue;
    }
    const val = String(raw[key] ?? "").toLowerCase();
    const allowed = spec[key].map((v) => v.toLowerCase());
    if (!allowed.includes(val)) {
      issues.push(`${key}="${val}" not in [${spec[key].join("|")}]`);
      continue;
    }
    matched++;
  }

  return {
    valid: issues.length === 0,
    confidence: keys.length > 0 ? matched / keys.length : 0,
    issues,
  };
}

// ── Cross-check (vision vs DOM/backend) ───────────────────────────────────────

export interface CrossCheckResult {
  agreed: boolean;
  vision_value: string;
  dom_value: string;
  /** confirmed = vision & DOM agree; conflict = they disagree; uncertain = one side is unknown */
  outcome: "confirmed" | "conflict" | "uncertain";
}

/**
 * Compares a vision-derived value with a DOM-derived value.
 * Pure function — no model call.
 *
 * @param visionValue  String extracted from vision analysis (e.g. "RUNNING", "visible")
 * @param domValue     String derived from Playwright DOM (e.g. "RUNNING", "visible")
 */
export function buildCrossCheck(visionValue: string, domValue: string): CrossCheckResult {
  const v = visionValue.trim().toLowerCase();
  const d = domValue.trim().toLowerCase();
  const agreed = v === d;
  const uncertain = v === "unknown" || v === "uncertain" || d === "unknown" || d === "uncertain";
  return {
    agreed,
    vision_value: visionValue,
    dom_value: domValue,
    outcome: uncertain ? "uncertain" : agreed ? "confirmed" : "conflict",
  };
}

// ── Region cache ───────────────────────────────────────────────────────────────

const _cache = new Map<string, { raw: Record<string, unknown>; latency_ms: number }>();

function hashImageBytes(imageBytes: Buffer): string {
  let h = 2166136261;
  const end = Math.min(512, imageBytes.length);
  for (let i = 0; i < end; i++) {
    h ^= imageBytes[i];
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h.toString(16);
}

function cacheKey(imageBytes: Buffer, question: string): string {
  return `${hashImageBytes(imageBytes)}:${question.slice(0, 60)}`;
}

/** Clears the in-memory region analysis cache. Call in test.afterEach if needed. */
export function clearRegionCache(): void {
  _cache.clear();
}

// ── Ollama transport ───────────────────────────────────────────────────────────

interface OllamaResponse { content: string; latency_ms: number }

function postToOllama(payload: string, timeoutMs = 30_000): Promise<OllamaResponse> {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    const req = http.request(
      {
        hostname: OLLAMA_HOST, port: OLLAMA_PORT, path: "/api/chat",
        method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) },
      },
      (res) => {
        let body = "";
        res.on("data", (chunk: string) => { body += chunk; });
        res.on("end", () => {
          try {
            const d = JSON.parse(body) as { message: { content: string } };
            resolve({ content: d.message.content, latency_ms: Date.now() - t0 });
          } catch {
            reject(new Error(`Ollama parse error: ${body.slice(0, 200)}`));
          }
        });
      },
    );
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`Ollama timeout after ${timeoutMs}ms`)));
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

async function analyzeRegionRaw(
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

/**
 * Sends a region image to gemma3:4b for JSON analysis.
 * Includes: in-memory cache (by image hash + question), 1 retry on invalid JSON.
 *
 * @param imageBytes  PNG buffer from captureRegion()
 * @param region      Human-readable name for logs (e.g. "runtime.card.spot@before")
 * @param systemPrompt  Defines expected JSON schema
 * @param question    Specific query about the image
 */
export async function analyzeRegion(
  imageBytes: Buffer,
  region: string,
  systemPrompt: string,
  question: string,
  bypassCache = false,
): Promise<RegionAnalysis> {
  const key = cacheKey(imageBytes, question);
  if (!bypassCache) {
    const cached = _cache.get(key);
    if (cached) {
      return { raw: cached.raw, latency_ms: cached.latency_ms, model: OLLAMA_MODEL, region };
    }
  }

  let result = await analyzeRegionRaw(imageBytes, region, systemPrompt, question);

  // Retry once if the response is unparseable or empty (safety net for model inconsistency)
  if ("_unparseable" in result.raw || Object.keys(result.raw).length === 0) {
    result = await analyzeRegionRaw(imageBytes, `${region}[retry]`, systemPrompt, question);
  }

  _cache.set(key, { raw: result.raw, latency_ms: result.latency_ms });
  return result;
}

// ── Element state classifier ───────────────────────────────────────────────────

export interface StateClassification {
  badge: "RUNNING" | "OFFLINE" | "UNKNOWN";
  color: "green" | "red" | "gray" | "other";
}

const STATE_SCHEMA: Record<string, string[]> = {
  badge: ["RUNNING", "OFFLINE", "UNKNOWN"],
  color: ["green", "red", "gray", "other"],
};

/**
 * Classifies the runtime status badge in a card region.
 *
 * Returns the badge value, confidence (schema match rate), and attempt count.
 * "action error banners" are NOT this function's scope — use detectActionBanner().
 */
export async function classifyElementState(
  imageBytes: Buffer,
  region: string,
): Promise<{ result: StateClassification; analysis: RegionAnalysis; confidence: number; attempt: number }> {
  const system = 'UI state inspector. JSON only: {"badge": "RUNNING|OFFLINE|UNKNOWN", "color": "green|red|gray|other"}';
  const question = "What is the status badge text and color in the top-right corner of this card?";

  let analysis = await analyzeRegion(imageBytes, region, system, question);
  let validation = validateSchema(analysis.raw, STATE_SCHEMA);
  let attempt = 1;

  if (!validation.valid && attempt < 2) {
    analysis = await analyzeRegion(imageBytes, `${region}[retry]`, system, question, true);
    validation = validateSchema(analysis.raw, STATE_SCHEMA);
    attempt = 2;
  }

  const rawBadge = String(analysis.raw.badge ?? "UNKNOWN").toUpperCase();
  const rawColor = String(analysis.raw.color ?? "other").toLowerCase();

  const badge = (["RUNNING", "OFFLINE", "UNKNOWN"].includes(rawBadge)
    ? rawBadge : "UNKNOWN") as StateClassification["badge"];
  const color = (["green", "red", "gray", "other"].includes(rawColor)
    ? rawColor : "other") as StateClassification["color"];

  return { result: { badge, color }, analysis, confidence: validation.confidence, attempt };
}

// ── Action banner detector ─────────────────────────────────────────────────────

export interface ActionBannerResult {
  has_action_banner: boolean;
  banner_type: "error" | "success" | "warning" | null;
  text: string | null;
}

const BANNER_SCHEMA: Record<string, string[]> = {
  has_action_banner: ["true", "false"],
  banner_type: ["error", "success", "warning", "null"],
};

/**
 * Detects a standalone action result notification in a region.
 *
 * "Action banner" = a notification that appears after a user action.
 * NOT a persistent status badge inside a component card.
 *
 * Separated from classifyElementState() to prevent the false-positive pattern
 * where an OFFLINE status badge is misinterpreted as an error notification.
 */
export async function detectActionBanner(
  imageBytes: Buffer,
  region: string,
): Promise<{ result: ActionBannerResult; analysis: RegionAnalysis; confidence: number; attempt: number }> {
  const system = 'UI inspector. JSON only: {"has_action_banner": true|false, "banner_type": "error|success|warning|null", "text": "notification text or null"}';
  const question = "Is there a standalone notification box or alert that appeared as a result of a user action (not a card status badge)?";

  let analysis = await analyzeRegion(imageBytes, region, system, question);
  let validation = validateSchema(analysis.raw, BANNER_SCHEMA);
  let attempt = 1;

  if (!validation.valid && attempt < 2) {
    analysis = await analyzeRegion(imageBytes, `${region}[retry]`, system, question, true);
    validation = validateSchema(analysis.raw, BANNER_SCHEMA);
    attempt = 2;
  }

  const bannerType = analysis.raw.banner_type as string | null;
  const validTypes = ["error", "success", "warning"];

  return {
    result: {
      has_action_banner: Boolean(analysis.raw.has_action_banner),
      banner_type: (bannerType && validTypes.includes(bannerType)
        ? bannerType : null) as ActionBannerResult["banner_type"],
      text: (analysis.raw.text as string | undefined) ?? null,
    },
    analysis,
    confidence: validation.confidence,
    attempt,
  };
}

// ── Panel visibility detector ──────────────────────────────────────────────────

export interface PanelVisibilityResult {
  panel_visible: boolean;
  primary_label: string | null;
}

const PANEL_SCHEMA: Record<string, string[]> = {
  panel_visible: ["true", "false"],
};

/**
 * Checks whether a result panel is rendered and identifies its primary status label.
 */
export async function detectPanelVisibility(
  imageBytes: Buffer,
  region: string,
): Promise<{ result: PanelVisibilityResult; analysis: RegionAnalysis; confidence: number; attempt: number }> {
  const system = 'UI inspector. JSON only: {"panel_visible": true|false, "primary_label": "most prominent single status word shown or null"}';
  const question = "Is a result or status panel visible in this region? What is the most prominent status word shown (e.g. healthy, error, unknown)?";

  let analysis = await analyzeRegion(imageBytes, region, system, question);
  let validation = validateSchema(analysis.raw, PANEL_SCHEMA);
  let attempt = 1;

  if (!validation.valid && attempt < 2) {
    analysis = await analyzeRegion(imageBytes, `${region}[retry]`, system, question, true);
    validation = validateSchema(analysis.raw, PANEL_SCHEMA);
    attempt = 2;
  }

  return {
    result: {
      panel_visible: Boolean(analysis.raw.panel_visible),
      primary_label: (analysis.raw.primary_label as string | undefined) ?? null,
    },
    analysis,
    confidence: validation.confidence,
    attempt,
  };
}

// ── State comparison ───────────────────────────────────────────────────────────

export type StateDecision =
  | "transition_confirmed"
  | "no_change"
  | "unexpected_state";

export interface StateComparison {
  changed: boolean;
  from_badge: string;
  to_badge: string;
  decision: StateDecision;
}

/**
 * Compares before/after state classifications to confirm a state transition.
 * Pure function — no model call.
 */
export function compareStates(
  before: StateClassification,
  after: StateClassification,
  expected: { from: StateClassification["badge"]; to: StateClassification["badge"] },
): StateComparison {
  const changed = before.badge !== after.badge;
  const decision: StateDecision =
    after.badge === expected.to ? "transition_confirmed"
    : changed ? "unexpected_state"
    : "no_change";
  return { changed, from_badge: before.badge, to_badge: after.badge, decision };
}

// ── Structured logging ─────────────────────────────────────────────────────────

/**
 * Writes a structured vision-loop log line.
 *
 * Format:
 *   [vision-loop] scenario="..." region="..." model=... latency=...ms
 *                 result={...} confidence=... attempt=N decision="..."
 *                 cross_check=outcome(vision=...,dom=...)
 */
export function logVisionResult(
  scenario: string,
  analysis: RegionAnalysis,
  decision: string,
  confidence?: number,
  crossCheck?: CrossCheckResult,
): void {
  const parts = [
    `[vision-loop] scenario="${scenario}"`,
    `region="${analysis.region}"`,
    `model=${analysis.model}`,
    `latency=${analysis.latency_ms}ms`,
    `result=${JSON.stringify(analysis.raw)}`,
    `decision="${decision}"`,
  ];
  if (confidence !== undefined) parts.push(`confidence=${confidence.toFixed(2)}`);
  if (crossCheck) {
    parts.push(`cross_check=${crossCheck.outcome}(vision=${crossCheck.vision_value},dom=${crossCheck.dom_value})`);
  }
  console.log(parts.join(" "));
}
