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
import { isRegionVisionReady, measureRegion, VISION_REGION_MIN, type RegionSize } from "./helpers";

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

// ── Region guardrail (VS-8) ────────────────────────────────────────────────────

/**
 * Common shape returned by every classifier. `_too_small=true` means the
 * region did not meet VISION_REGION_MIN (see tests/visual/helpers.ts) so the
 * model was never called — confidence is 0 and `reason` explains why. The
 * inner `result` is a neutral sentinel (OFFLINE/UNKNOWN/false) so tests can
 * still read fields without crashing, but an honest scenario should check
 * `_too_small` first and either enlarge the crop or fail explicitly.
 */
export interface ClassifierResult<T> {
  result: T;
  analysis: RegionAnalysis;
  confidence: number;
  attempt: number;
  _too_small: boolean;
  size: RegionSize;
  reason?: string;
}

function tooSmallReason(size: RegionSize): string {
  return (
    `region too small for reliable vision analysis ` +
    `(got ${size.width}x${size.height}, font=${size.font_size_px ?? "?"}px; ` +
    `require >=${VISION_REGION_MIN.width}x${VISION_REGION_MIN.height} with font>=${VISION_REGION_MIN.font_size_px}px — ` +
    `see tests/visual/helpers.ts VISION_REGION_MIN)`
  );
}

function tooSmallAnalysis(region: string, size: RegionSize): RegionAnalysis {
  return {
    raw: { _too_small: true, size: size as unknown as Record<string, unknown> },
    latency_ms: 0,
    model: OLLAMA_MODEL,
    region,
  };
}

// ── Element state classifier ───────────────────────────────────────────────────

export interface StateClassification {
  /**
   * Runtime lifecycle states that the heartbeat monitor emits and the
   * frontend labels on the card:
   *   - RUNNING  — process alive, heartbeats fresh
   *   - OFFLINE  — no process / no heartbeat
   *   - DEGRADED — process alive but heartbeats stale or errors accumulating;
   *                the frontend styles this with an orange/amber chip, which
   *                gemma3:4b already reports natively (confirmed 2026-04-22
   *                on the live-interaction scenario — the schema rejected a
   *                perfectly correct answer). Added to close that gap.
   *   - UNKNOWN  — genuine classifier abstention (off-schema or ambiguous).
   */
  badge: "RUNNING" | "OFFLINE" | "DEGRADED" | "UNKNOWN";
  color: "green" | "red" | "orange" | "gray" | "other";
}

const STATE_SCHEMA: Record<string, string[]> = {
  badge: ["RUNNING", "OFFLINE", "DEGRADED", "UNKNOWN"],
  color: ["green", "red", "orange", "gray", "other"],
};

/**
 * Classifies the runtime status badge in a card region.
 *
 * VS-8 guardrail: measures the locator before calling the model. If the
 * region is below VISION_REGION_MIN, returns `_too_small=true, confidence=0`
 * without ever sending pixels to gemma3:4b — a 80x30 sidebar-link crop will
 * no longer silently produce a confident wrong answer.
 */
export async function classifyElementState(
  locator: Locator,
  region: string,
): Promise<ClassifierResult<StateClassification>> {
  const size = await measureRegion(locator);
  if (!isRegionVisionReady(size)) {
    const reason = tooSmallReason(size);
    return {
      result: { badge: "UNKNOWN", color: "other" },
      analysis: tooSmallAnalysis(region, size),
      confidence: 0, attempt: 0, _too_small: true, size, reason,
    };
  }

  const imageBytes = await captureRegion(locator);
  // Prompt intentionally unchanged in wording — only the enum lists grew.
  // An earlier attempt to add "if DEGRADED, return DEGRADED..." coaching
  // caused the model to misclassify OFFLINE cards as RUNNING. gemma3:4b
  // already emits {"badge":"DEGRADED","color":"orange"} for degraded cards
  // without any coaching; the schema just needed to accept it.
  const system = 'UI state inspector. JSON only: {"badge": "RUNNING|OFFLINE|DEGRADED|UNKNOWN", "color": "green|red|orange|gray|other"}';
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

  const badge = (["RUNNING", "OFFLINE", "DEGRADED", "UNKNOWN"].includes(rawBadge)
    ? rawBadge : "UNKNOWN") as StateClassification["badge"];
  const color = (["green", "red", "orange", "gray", "other"].includes(rawColor)
    ? rawColor : "other") as StateClassification["color"];

  return {
    result: { badge, color }, analysis,
    confidence: validation.confidence, attempt,
    _too_small: false, size,
  };
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
  locator: Locator,
  region: string,
): Promise<ClassifierResult<ActionBannerResult>> {
  const size = await measureRegion(locator);
  if (!isRegionVisionReady(size)) {
    const reason = tooSmallReason(size);
    return {
      result: { has_action_banner: false, banner_type: null, text: null },
      analysis: tooSmallAnalysis(region, size),
      confidence: 0, attempt: 0, _too_small: true, size, reason,
    };
  }

  const imageBytes = await captureRegion(locator);
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
    _too_small: false, size,
  };
}

// ── Error text detector ────────────────────────────────────────────────────────

export interface ErrorTextResult {
  has_error: boolean;
  text_visible: boolean;
  summary: string | null;
}

const ERROR_TEXT_SCHEMA: Record<string, string[]> = {
  has_error: ["true", "false"],
  text_visible: ["true", "false"],
};

/**
 * Detects failure/error text inside a panel region.
 *
 * Different from detectActionBanner: targets a panel whose body contains
 * raw error text (e.g. a server detail message) rather than a styled
 * notification with icon/color chrome. Proven reliable on small .panel crops
 * where actionBanner returns {} (see scripts/probe_jobs_vision.mjs).
 */
export async function detectErrorText(
  locator: Locator,
  region: string,
): Promise<ClassifierResult<ErrorTextResult>> {
  const size = await measureRegion(locator);
  if (!isRegionVisionReady(size)) {
    const reason = tooSmallReason(size);
    return {
      result: { has_error: false, text_visible: false, summary: null },
      analysis: tooSmallAnalysis(region, size),
      confidence: 0, attempt: 0, _too_small: true, size, reason,
    };
  }

  const imageBytes = await captureRegion(locator);
  const system = 'UI inspector. JSON only: {"has_error": true|false, "text_visible": true|false, "summary": "what you see max 15 words"}';
  const question = "Is there an error message or failure text visible in this UI region?";

  let analysis = await analyzeRegion(imageBytes, region, system, question);
  let validation = validateSchema(analysis.raw, ERROR_TEXT_SCHEMA);
  let attempt = 1;

  if (!validation.valid && attempt < 2) {
    analysis = await analyzeRegion(imageBytes, `${region}[retry]`, system, question, true);
    validation = validateSchema(analysis.raw, ERROR_TEXT_SCHEMA);
    attempt = 2;
  }

  return {
    result: {
      has_error: Boolean(analysis.raw.has_error),
      text_visible: Boolean(analysis.raw.text_visible),
      summary: (analysis.raw.summary as string | undefined) ?? null,
    },
    analysis,
    confidence: validation.confidence,
    attempt,
    _too_small: false, size,
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
  locator: Locator,
  region: string,
): Promise<ClassifierResult<PanelVisibilityResult>> {
  const size = await measureRegion(locator);
  if (!isRegionVisionReady(size)) {
    const reason = tooSmallReason(size);
    return {
      result: { panel_visible: false, primary_label: null },
      analysis: tooSmallAnalysis(region, size),
      confidence: 0, attempt: 0, _too_small: true, size, reason,
    };
  }

  const imageBytes = await captureRegion(locator);
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
    _too_small: false, size,
  };
}

// ── Composite multi-region decision ────────────────────────────────────────────

/**
 * Per-region outcome for a live action. The test does not vote — it tags
 * each region as confirmed/conflict/skipped with a short, honest reason.
 */
export interface RegionOutcome {
  name: string;
  status: "confirmed" | "conflict" | "skipped";
  reason: string;
  /** Optional structured payload: before/after labels, size, classifier name. */
  details?: Record<string, unknown>;
}

/**
 * Aggregated decision over a set of region outcomes. `final_outcome`
 * is a mechanical mapping — any `conflict` wins; otherwise
 * all-confirmed > partial > no-signal. Never inflates a partial into a
 * pass: the test still has to decide whether partial is acceptable.
 */
export interface CompositeDecision {
  action: string;
  confirmed_regions: string[];
  conflicted_regions: string[];
  skipped_regions: string[];
  final_outcome: "all_confirmed" | "partial_confirmed" | "conflict" | "no_signal";
  regions: RegionOutcome[];
}

/**
 * Build a composite decision from per-region outcomes.
 *   conflict  — any region tagged conflict → final "conflict"
 *   confirmed — all tagged confirmed → "all_confirmed"
 *   mix       — some confirmed + some skipped → "partial_confirmed"
 *   empty     — no regions or all skipped → "no_signal"
 *
 * Pure — no model call, no DOM call.
 */
export function composeDecision(action: string, outcomes: RegionOutcome[]): CompositeDecision {
  const confirmed = outcomes.filter((o) => o.status === "confirmed").map((o) => o.name);
  const conflict = outcomes.filter((o) => o.status === "conflict").map((o) => o.name);
  const skipped = outcomes.filter((o) => o.status === "skipped").map((o) => o.name);

  let final: CompositeDecision["final_outcome"];
  if (conflict.length > 0) final = "conflict";
  else if (confirmed.length === 0) final = "no_signal";
  else if (skipped.length === 0) final = "all_confirmed";
  else final = "partial_confirmed";

  return {
    action,
    confirmed_regions: confirmed,
    conflicted_regions: conflict,
    skipped_regions: skipped,
    final_outcome: final,
    regions: outcomes,
  };
}

/**
 * Convenience: turn a "does expected match actual" check for one region into
 * a RegionOutcome. Keeps composeDecision callsites short and symmetric.
 */
export function regionOutcome(
  name: string,
  condition: boolean,
  reason: string,
  details?: Record<string, unknown>,
): RegionOutcome {
  return {
    name,
    status: condition ? "confirmed" : "conflict",
    reason,
    details,
  };
}

/**
 * Mark a region as honestly skipped (e.g. classifier returned `_too_small`
 * or the region is not applicable in this env). Skipped ≠ passed.
 */
export function regionSkipped(
  name: string, reason: string, details?: Record<string, unknown>,
): RegionOutcome {
  return { name, status: "skipped", reason, details };
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
 *
 * `expected.to` accepts either a single target badge ("RUNNING") or a set
 * (["RUNNING", "DEGRADED"]). The set form is the honest way to express
 * "action worked = anything but OFFLINE" when the runtime may legitimately
 * land in any of several active states — e.g. the spot runtime in a dev
 * env without Bybit creds that flips RUNNING → DEGRADED within one poll
 * interval. No inflation of confidence; just the right vocabulary.
 */
export function compareStates(
  before: StateClassification,
  after: StateClassification,
  expected: {
    from: StateClassification["badge"] | Array<StateClassification["badge"]>;
    to:   StateClassification["badge"] | Array<StateClassification["badge"]>;
  },
): StateComparison {
  const fromSet = Array.isArray(expected.from) ? expected.from : [expected.from];
  const toSet = Array.isArray(expected.to) ? expected.to : [expected.to];
  const changed = before.badge !== after.badge;
  const fromMatched = fromSet.includes(before.badge);
  const toMatched = toSet.includes(after.badge);
  const decision: StateDecision =
    fromMatched && toMatched ? "transition_confirmed"
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
