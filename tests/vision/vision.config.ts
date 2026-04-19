import path from "node:path";

const repoRoot = path.resolve(__dirname, "..", "..");

/** "llm" if ANTHROPIC_API_KEY is set, "heuristic" otherwise. Overrideable via VISION_MODE env. */
export const VISION_MODE = (process.env.VISION_MODE as "llm" | "heuristic") ??
  (process.env.ANTHROPIC_API_KEY ? "llm" : "heuristic");

/**
 * STRICT (default): fail the test when any issue has severity=high and confidence>0.7.
 * REPORT: never fail; write report.json only. Set VISION_STRICT=0 to enable.
 */
export const VISION_STRICT = process.env.VISION_STRICT !== "0";

/** Confidence threshold above which a high-severity issue causes failure in STRICT mode. */
export const FAIL_CONFIDENCE_THRESHOLD = 0.7;

export const ARTIFACTS_DIR = path.join(repoRoot, ".artifacts", "local", "latest", "vision");
export const SCREENSHOTS_DIR = path.join(ARTIFACTS_DIR, "screenshots");
export const REPORT_PATH = path.join(ARTIFACTS_DIR, "report.json");

export const LLM_MODEL = process.env.VISION_MODEL ?? "claude-haiku-4-5-20251001";
export const LLM_MAX_TOKENS = 1024;

export const BASE_URL = "http://127.0.0.1:4173";
export const BACKEND_URL = "http://127.0.0.1:8765";
