/**
 * Semantic auto-region system.
 *
 * Goal: stop hard-coding region selectors and expected text in tests.
 * Instead, the frontend tags meaningful elements with `data-ui-*`
 * attributes (a parallel contract to `data-testid`, not a replacement),
 * and these helpers discover, snapshot and diff those regions.
 *
 * Contract emitted by the frontend (see frontend/src/features/runtime):
 *   data-ui-role    — what the element IS (runtime-card, status-badge,
 *                     status-callout, runtime-action, action-row, ...)
 *   data-ui-scope   — semantic owner (e.g. "spot", "futures") — optional
 *   data-ui-state   — current state (offline|running|degraded|enabled|
 *                     disabled|...) — optional
 *   data-ui-action  — what action the element triggers (start|stop) —
 *                     optional, only meaningful on actionable elements
 *   data-ui-kind    — semantic flavour (info|warning|error) — optional,
 *                     used on callouts/banners
 *
 * Tests must consume `data-ui-*` through these helpers, never read the
 * raw text or pixel positions of regions.
 */

import type { Locator, Page } from "@playwright/test";
import { VISION_REGION_MIN } from "./helpers";

// ── Canonical state layer ─────────────────────────────────────────────────────

/**
 * Canonical state vocabularies, decoupled from the visible UI strings.
 *
 * The frontend is free to rename `offline → idle` or translate
 * `populated → загружено` without breaking tests, as long as the
 * `data-ui-state` value still maps to the same canonical bucket.
 *
 * Tests assert against these enums; never against raw `data-ui-state`
 * strings.
 */
export const RUNTIME_STATE = {
  INACTIVE: "INACTIVE",
  ACTIVE: "ACTIVE",
  DEGRADED: "DEGRADED",
} as const;
export type RuntimeState = typeof RUNTIME_STATE[keyof typeof RUNTIME_STATE];

export const JOBS_STATE = {
  EMPTY: "EMPTY",
  NON_EMPTY: "NON_EMPTY",
} as const;
export type JobsState = typeof JOBS_STATE[keyof typeof JOBS_STATE];

export const ACTION_STATE = {
  ENABLED: "ENABLED",
  DISABLED: "DISABLED",
} as const;
export type ActionState = typeof ACTION_STATE[keyof typeof ACTION_STATE];

/**
 * Union of every canonical bucket that the snapshot can carry. `null`
 * means the (role, raw) pair has no canonical mapping yet — the test
 * may still use the raw string for that region but should not pretend
 * it is canonical.
 */
export type CanonicalState = RuntimeState | JobsState | ActionState;

/**
 * Static mapping table — single source of truth.
 *
 * Keyed first by role, then by lower-cased raw `data-ui-state`. Roles
 * not present here have no canonical state (e.g. layout containers,
 * `jobs-list-item` with per-job lifecycle states that are out of the
 * three canonical vocabularies).
 *
 * If the frontend renames an existing UI state without updating this
 * table, `toCanonicalState` returns `null` and the caller MUST decide
 * whether that is a known new state or a regression.
 */
const CANONICAL_MAP: Record<string, Record<string, CanonicalState>> = {
  // Runtime card + status badge — three lifecycle buckets.
  "runtime-card": {
    offline: RUNTIME_STATE.INACTIVE,
    running: RUNTIME_STATE.ACTIVE,
    degraded: RUNTIME_STATE.DEGRADED,
  },
  "status-badge": {
    // The status badge appears in two contexts (runtime card, selected
    // job). Both share the same lifecycle vocabulary for the values we
    // care about. Per-job lifecycle states (queued, succeeded, ...)
    // intentionally remain unmapped.
    offline: RUNTIME_STATE.INACTIVE,
    running: RUNTIME_STATE.ACTIVE,
    degraded: RUNTIME_STATE.DEGRADED,
  },

  // Jobs history panel — two-bucket vocabulary.
  "jobs-history": {
    empty: JOBS_STATE.EMPTY,
    populated: JOBS_STATE.NON_EMPTY,
  },
  "jobs-list": {
    // The list-container only renders when populated, but we keep both
    // entries so a future "loading" branch shows up as null and gets
    // flagged.
    populated: JOBS_STATE.NON_EMPTY,
    empty: JOBS_STATE.EMPTY,
  },

  // Action buttons — both runtime and job actions share enabled/disabled.
  "runtime-action": {
    enabled: ACTION_STATE.ENABLED,
    disabled: ACTION_STATE.DISABLED,
  },
  "job-action": {
    enabled: ACTION_STATE.ENABLED,
    disabled: ACTION_STATE.DISABLED,
  },
};

/**
 * Pure mapping. Returns the canonical state, or `null` if the (role, raw)
 * pair is not in the table. `null` is a meaningful answer — it means the
 * region carries a state the canonical layer does not currently classify.
 */
export function toCanonicalState(role: string, raw: string | null): CanonicalState | null {
  if (raw === null) return null;
  const byRole = CANONICAL_MAP[role];
  if (!byRole) return null;
  return byRole[raw.toLowerCase()] ?? null;
}

// ── Region shape ──────────────────────────────────────────────────────────────

export type CheckMethod = "vision" | "dom" | "backend" | "hybrid";

export interface RegionBBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SemanticRegion {
  /** data-ui-role — the only required attribute. */
  role: string;
  /** data-ui-scope — semantic owner, may be empty. */
  scope: string | null;
  /**
   * Raw `data-ui-state` value as written by the frontend. Kept for
   * debugging and for regions whose state is outside any canonical
   * vocabulary; tests should NOT assert on this — use `canonical_state`.
   */
  state: string | null;
  /**
   * Canonical state bucket (`RUNTIME_STATE` | `JOBS_STATE` |
   * `ACTION_STATE`). `null` means the (role, raw) pair has no mapping
   * — either the region is layout-only (no state) or the raw string
   * is a known unmapped value (e.g. job lifecycle on a list item).
   */
  canonical_state: CanonicalState | null;
  /** data-ui-action — only on action-triggering elements. */
  action: string | null;
  /** data-ui-kind — flavour for callouts/banners. */
  kind: string | null;
  /** Visible bounding box; zero-area regions are filtered out. */
  bbox: RegionBBox;
  /** textContent length — used for layout sanity, not text matching. */
  text_length: number;
  /** Element is rendered AND has non-zero box AND not display:none. */
  visible: boolean;
  /** Whether the element is `<button disabled>` etc. */
  disabled: boolean;
  /**
   * Recommended verification method, derived from role + size.
   * Tests should respect this — calling vision on a region marked "dom"
   * is a contract violation, not a "best effort".
   */
  recommended_check: CheckMethod;
}

/**
 * Stable identity key for a region across snapshots.
 * Two regions are "the same region" iff their (role, scope, action, kind)
 * tuples match. State is intentionally NOT part of the key — that is what
 * the diff inspects.
 */
export function regionKey(r: SemanticRegion): string {
  return [
    r.role,
    r.scope ?? "",
    r.action ?? "",
    r.kind ?? "",
  ].join("|");
}

// ── recommended_check policy ──────────────────────────────────────────────────

/**
 * Maps (role, size) to a recommended verification method. Pure function —
 * keeps the policy in one place so tests don't reinvent it per scenario.
 *
 * Categories (intentionally feature-agnostic — no special-case per page):
 *   - card-like panels (runtime-card, job-preset, job-status, jobs-history)
 *     → hybrid if bbox is vision-ready, else dom
 *   - chrome-rich small regions (status-badge, status-callout)
 *     → vision if bbox is vision-ready, else dom
 *   - actionable elements (runtime-action, job-action)
 *     → dom (button enabled/disabled is authoritative)
 *   - layout containers (action-row, status-callouts, jobs-list,
 *     jobs-list-item, job-toolbar, page) → dom
 *   - empty-state markers → dom (presence is the signal)
 *   - anything else → hybrid if vision-ready, else dom
 */
export function recommendedCheck(role: string, bbox: RegionBBox): CheckMethod {
  const visionReady =
    bbox.width >= VISION_REGION_MIN.width && bbox.height >= VISION_REGION_MIN.height;

  switch (role) {
    // Card-like panels: state lives in DOM, rendering can be cross-checked by vision.
    case "runtime-card":
    case "job-preset":
    case "job-status":
    case "jobs-history":
      return visionReady ? "hybrid" : "dom";

    // Small chrome-rich regions: vision is the natural reader.
    case "status-badge":
    case "status-callout":
      return visionReady ? "vision" : "dom";

    // Actionable elements: button enabled/disabled is a DOM fact, not a vision one.
    case "runtime-action":
    case "job-action":
      return "dom";

    // Layout containers: presence + structure, not pixels.
    case "action-row":
    case "status-callouts":
    case "jobs-list":
    case "jobs-list-item":
    case "job-toolbar":
    case "page":
      return "dom";

    // Empty-state markers: the fact that they exist is the signal.
    case "empty-state":
      return "dom";

    default:
      return visionReady ? "hybrid" : "dom";
  }
}

// ── Auto-region discovery ─────────────────────────────────────────────────────

/**
 * Scans the page for all visible elements carrying `data-ui-role`.
 * Returns one record per element. Hidden elements (display:none, zero-box,
 * visibility:hidden) are dropped — the snapshot reflects what a user
 * sees right now, not the static DOM.
 *
 * No selector list is hard-coded in tests; any new role added in the
 * frontend (data-ui-role="...") is discovered automatically.
 */
export async function collectSemanticRegions(page: Page): Promise<SemanticRegion[]> {
  // Single page.evaluate — DOM walk happens once, results serialised back.
  const raw = await page.evaluate(() => {
    const out: Array<{
      role: string;
      scope: string | null;
      state: string | null;
      action: string | null;
      kind: string | null;
      bbox: { x: number; y: number; width: number; height: number };
      text_length: number;
      visible: boolean;
      disabled: boolean;
    }> = [];

    const nodes = document.querySelectorAll<HTMLElement>("[data-ui-role]");
    for (const el of Array.from(nodes)) {
      const rect = el.getBoundingClientRect();
      const cs = window.getComputedStyle(el);
      const visible =
        cs.display !== "none" &&
        cs.visibility !== "hidden" &&
        rect.width > 0 &&
        rect.height > 0;

      // Skip elements that cannot be meaningfully observed at all.
      // We still keep zero-state attributes — the diff cares about them.
      if (!visible && rect.width === 0 && rect.height === 0) {
        // Element exists in DOM but has no box. Record it as invisible
        // rather than dropping it so visibility_changed transitions are
        // detectable.
        out.push({
          role: el.getAttribute("data-ui-role") ?? "",
          scope: el.getAttribute("data-ui-scope"),
          state: el.getAttribute("data-ui-state"),
          action: el.getAttribute("data-ui-action"),
          kind: el.getAttribute("data-ui-kind"),
          bbox: { x: 0, y: 0, width: 0, height: 0 },
          text_length: (el.textContent ?? "").trim().length,
          visible: false,
          disabled: (el as HTMLButtonElement).disabled === true,
        });
        continue;
      }

      out.push({
        role: el.getAttribute("data-ui-role") ?? "",
        scope: el.getAttribute("data-ui-scope"),
        state: el.getAttribute("data-ui-state"),
        action: el.getAttribute("data-ui-action"),
        kind: el.getAttribute("data-ui-kind"),
        bbox: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        },
        text_length: (el.textContent ?? "").trim().length,
        visible,
        disabled: (el as HTMLButtonElement).disabled === true,
      });
    }
    return out;
  });

  return raw.map((r) => ({
    ...r,
    recommended_check: recommendedCheck(r.role, r.bbox),
    canonical_state: toCanonicalState(r.role, r.state),
  }));
}

/**
 * Resolves a Playwright Locator for a semantic region. Used by callers
 * that want to run a vision classifier on a region the snapshot says
 * is vision-worthy. Does NOT hard-code selectors per region — it builds
 * a CSS selector from the semantic key.
 *
 * Returns the FIRST matching element. The (role, scope, action, kind)
 * tuple is unique by design in the runtime card we control; if a future
 * role is non-unique, callers should narrow the scope.
 */
export function locatorForRegion(page: Page, region: SemanticRegion): Locator {
  const parts: string[] = [`[data-ui-role="${region.role}"]`];
  if (region.scope !== null) parts.push(`[data-ui-scope="${region.scope}"]`);
  if (region.action !== null) parts.push(`[data-ui-action="${region.action}"]`);
  if (region.kind !== null) parts.push(`[data-ui-kind="${region.kind}"]`);
  return page.locator(parts.join("")).first();
}

// ── Snapshot ──────────────────────────────────────────────────────────────────

export interface SemanticSnapshot {
  /** ISO timestamp of capture — purely for logs/artifacts. */
  captured_at: string;
  /** All discovered regions, in DOM order. */
  regions: SemanticRegion[];
}

/**
 * Capture a full semantic snapshot of the current page.
 *
 * The shape mirrors what the test asks for: a list of regions identified
 * by stable (role, scope, action, kind) keys, plus their current
 * observable state — not their text content, not their pixel position
 * relative to the viewport, not their CSS class list.
 */
export async function captureSemanticSnapshot(page: Page): Promise<SemanticSnapshot> {
  const regions = await collectSemanticRegions(page);
  return {
    captured_at: new Date().toISOString(),
    regions,
  };
}

// ── Diff ──────────────────────────────────────────────────────────────────────

export type SemanticChangeType =
  | "state_changed"
  | "action_availability_changed"
  | "callout_changed"
  | "visibility_changed"
  | "region_added"
  | "region_removed";

export interface SemanticChange {
  type: SemanticChangeType;
  key: string;
  role: string;
  scope: string | null;
  /** Human-readable description, e.g. "offline → running". */
  detail: string;
  /** Per-change payload for callers that need exact before/after values. */
  before?: Partial<SemanticRegion>;
  after?: Partial<SemanticRegion>;
}

export interface SemanticDiff {
  changes: SemanticChange[];
  /** Quick lookups — same data as `changes`, partitioned. */
  state_changed: SemanticChange[];
  action_availability_changed: SemanticChange[];
  callout_changed: SemanticChange[];
  visibility_changed: SemanticChange[];
  region_added: SemanticChange[];
  region_removed: SemanticChange[];
}

function indexByKey(snapshot: SemanticSnapshot): Map<string, SemanticRegion> {
  const m = new Map<string, SemanticRegion>();
  for (const r of snapshot.regions) {
    // Last-write-wins on duplicate keys; not expected in our DOM, but
    // tolerated rather than crashing.
    m.set(regionKey(r), r);
  }
  return m;
}

/**
 * Diff two snapshots in semantic terms.
 *
 * Detects:
 *   - state_changed              — same region, data-ui-state differs
 *   - action_availability_changed — runtime-action toggled enabled↔disabled
 *   - callout_changed            — status-callout kind changed (info↔warning↔error)
 *   - visibility_changed         — region appeared/disappeared without being added/removed
 *   - region_added / region_removed — keyed region present in only one snapshot
 *
 * Stable in the face of:
 *   - text changes (we never compare text)
 *   - language changes (we never compare visible labels)
 *   - bbox movement (bbox is recorded, not compared)
 *   - viewport resize (visibility rules apply, not coordinates)
 */
export function compareSemanticSnapshots(
  before: SemanticSnapshot,
  after: SemanticSnapshot,
): SemanticDiff {
  const beforeIdx = indexByKey(before);
  const afterIdx = indexByKey(after);

  const changes: SemanticChange[] = [];

  // Walk before → after to detect removals + same-key changes.
  for (const [key, b] of beforeIdx.entries()) {
    const a = afterIdx.get(key);
    if (!a) {
      changes.push({
        type: "region_removed",
        key,
        role: b.role,
        scope: b.scope,
        detail: `region ${key} removed`,
        before: b,
      });
      continue;
    }

    // visibility_changed wins over state_changed when one side is invisible
    if (b.visible !== a.visible) {
      changes.push({
        type: "visibility_changed",
        key,
        role: b.role,
        scope: b.scope,
        detail: `visible ${b.visible} → ${a.visible}`,
        before: b,
        after: a,
      });
      // If a region just became visible/invisible, downstream state
      // comparisons are noisy — skip them for this region.
      continue;
    }

    // State change — covers runtime-card, status-badge, jobs-history.
    // Compared by canonical_state when available; falls back to raw
    // strings only for regions whose state is outside any canonical
    // vocabulary. Action buttons are excluded — their availability
    // is tracked by action_availability_changed below.
    const isAction = b.role === "runtime-action" || b.role === "job-action";
    if (!isAction) {
      const bCan = b.canonical_state ?? null;
      const aCan = a.canonical_state ?? null;
      const canonicalDiffer = bCan !== aCan;
      const rawDiffer = (b.state ?? null) !== (a.state ?? null);
      // Trigger on canonical change; if both sides are unmapped (null),
      // fall back to raw so unmapped regions still surface mutations
      // (e.g. job-status state="queued" → "running").
      const both_unmapped = bCan === null && aCan === null;
      if (canonicalDiffer || (both_unmapped && rawDiffer)) {
        const beforeStr = bCan ?? b.state ?? "null";
        const afterStr = aCan ?? a.state ?? "null";
        changes.push({
          type: "state_changed",
          key,
          role: b.role,
          scope: b.scope,
          detail: `${beforeStr} → ${afterStr}`,
          before: b,
          after: a,
        });
      }
    }

    // Action availability — runtime-action OR job-action. Compared by
    // canonical ACTION_STATE.ENABLED/DISABLED, not by the raw enum value
    // (which the frontend may rename without breaking the contract).
    if (isAction) {
      const beforeEnabled =
        b.canonical_state === ACTION_STATE.ENABLED && !b.disabled;
      const afterEnabled =
        a.canonical_state === ACTION_STATE.ENABLED && !a.disabled;
      if (beforeEnabled !== afterEnabled) {
        changes.push({
          type: "action_availability_changed",
          key,
          role: b.role,
          scope: b.scope,
          detail: `enabled ${beforeEnabled} → ${afterEnabled}`,
          before: b,
          after: a,
        });
      }
    }

    // Callout flavour changed (info → error etc.)
    if (b.role === "status-callout" && (b.kind ?? null) !== (a.kind ?? null)) {
      // Note: kind is part of the stable key, so a kind flip technically
      // shows up as remove+add. We additionally surface it as
      // callout_changed when the (role, scope) pair is preserved.
      changes.push({
        type: "callout_changed",
        key,
        role: b.role,
        scope: b.scope,
        detail: `kind ${b.kind ?? "null"} → ${a.kind ?? "null"}`,
        before: b,
        after: a,
      });
    }
  }

  // Walk after to detect additions, plus the (rare) callout kind flip
  // that came in via the key change.
  for (const [key, a] of afterIdx.entries()) {
    if (beforeIdx.has(key)) continue;

    // If a callout changed kind, it shows here as a new region AND in
    // before as a removed region. Detect that pairing and emit a
    // callout_changed alongside the add/remove for clarity.
    if (a.role === "status-callout") {
      const sibling = [...beforeIdx.values()].find(
        (b) => b.role === "status-callout" && b.scope === a.scope && b.kind !== a.kind,
      );
      if (sibling) {
        changes.push({
          type: "callout_changed",
          key,
          role: a.role,
          scope: a.scope,
          detail: `kind ${sibling.kind ?? "null"} → ${a.kind ?? "null"}`,
          before: sibling,
          after: a,
        });
      }
    }

    changes.push({
      type: "region_added",
      key,
      role: a.role,
      scope: a.scope,
      detail: `region ${key} added`,
      after: a,
    });
  }

  const partition = (t: SemanticChangeType) => changes.filter((c) => c.type === t);
  return {
    changes,
    state_changed: partition("state_changed"),
    action_availability_changed: partition("action_availability_changed"),
    callout_changed: partition("callout_changed"),
    visibility_changed: partition("visibility_changed"),
    region_added: partition("region_added"),
    region_removed: partition("region_removed"),
  };
}

// ── Helpers used by live scenarios ────────────────────────────────────────────

/**
 * Find a single region in a snapshot by partial match. Returns null if
 * not found, so callers can decide whether absence is a failure.
 */
export function findRegion(
  snapshot: SemanticSnapshot,
  match: { role: string; scope?: string; action?: string; kind?: string },
): SemanticRegion | null {
  return (
    snapshot.regions.find(
      (r) =>
        r.role === match.role &&
        (match.scope === undefined || r.scope === match.scope) &&
        (match.action === undefined || r.action === match.action) &&
        (match.kind === undefined || r.kind === match.kind),
    ) ?? null
  );
}

/**
 * Pretty-print a diff for log output. Intentionally compact — the test
 * also asserts on structured diff fields, this is for humans skimming
 * Playwright output.
 */
export function summariseDiff(diff: SemanticDiff): string {
  if (diff.changes.length === 0) return "no semantic changes";
  return diff.changes
    .map((c) => `${c.type}[${c.role}${c.scope ? `:${c.scope}` : ""}]: ${c.detail}`)
    .join("; ");
}
