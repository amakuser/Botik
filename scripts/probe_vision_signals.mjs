/**
 * Probe: measure reliability of each vision signal type on known pages.
 * Writes results to .artifacts/local/latest/vision/signal-quality.json.
 *
 * Signals tested (3 iterations each on fresh captures):
 *   A. status_badge      — classifyElementState on runtime cards (RUNNING/OFFLINE)
 *   B. error_text        — detectErrorText on jobs error panel
 *   C. panel_visibility  — detectPanelVisibility on telegram check result
 *   D. primary_label     — primary_label field on various panels
 *   E. active_nav_styling — active link in sidebar (known hard for a small model)
 *
 * Run: node scripts/probe_vision_signals.mjs
 */
import { chromium } from "@playwright/test";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const BASE = "http://127.0.0.1:4173";
const OLLAMA_HOST = "127.0.0.1";
const OLLAMA_PORT = 11434;
const MODEL = "gemma3:4b";
const ITERS = 3;

function ask(payload) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: OLLAMA_HOST, port: OLLAMA_PORT, path: "/api/chat", method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) } },
      (res) => { let body = ""; res.on("data", (c) => { body += c; }); res.on("end", () => {
        try { resolve(JSON.parse(body)); } catch { reject(new Error("parse")); }
      }); });
    req.on("error", reject);
    req.setTimeout(30000, () => req.destroy());
    req.write(payload); req.end();
  });
}

async function probe(imgB64, system, user) {
  const runs = [];
  for (let i = 0; i < ITERS; i++) {
    const payload = JSON.stringify({
      model: MODEL, format: "json", stream: false,
      messages: [{ role: "system", content: system }, { role: "user", content: user, images: [imgB64] }],
      options: { temperature: 0, num_predict: 120 },
    });
    const t0 = Date.now();
    try {
      const r = await ask(payload);
      let parsed;
      try { parsed = JSON.parse(r.message.content); } catch { parsed = { _raw: r.message.content.slice(0, 150) }; }
      runs.push({ iter: i + 1, latency_ms: Date.now() - t0, raw: parsed });
    } catch (e) { runs.push({ iter: i + 1, error: e.message }); }
  }
  return runs;
}

function reliability(runs, checkFn) {
  const matched = runs.filter((r) => !r.error && checkFn(r.raw)).length;
  return { matched, total: runs.length, rate: matched / runs.length };
}

const browser = await chromium.launch({ headless: true, args: ["--no-proxy-server"] });
const outDir = path.join(process.cwd(), ".artifacts", "local", "latest", "vision");
fs.mkdirSync(outDir, { recursive: true });

const report = { generated_at: new Date().toISOString(), model: MODEL, iters: ITERS, signals: {} };

// ── A. status_badge on live runtime cards (real backend, no mocks) ────────────
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(`${BASE}/runtime`);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(1200);
  const card = page.getByTestId("runtime.card.spot");
  const img = await card.screenshot({ animations: "disabled" });
  const runs = await probe(
    img.toString("base64"),
    'UI state inspector. JSON only: {"badge": "RUNNING|OFFLINE|UNKNOWN", "color": "green|red|gray|other"}',
    "What is the status badge text and color in the top-right corner of this card?",
  );
  report.signals.status_badge = {
    runs,
    reliability: reliability(runs, (r) => ["RUNNING", "OFFLINE"].includes(String(r.badge).toUpperCase())),
  };
  await page.close();
}

// ── B. error_text on jobs error panel (mocked 422) ───────────────────────────
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.route("**/jobs", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 422, contentType: "application/json",
        body: JSON.stringify({ detail: "Test: simulated start failure" }) });
    } else { await route.continue(); }
  });
  await page.goto(`${BASE}/jobs`);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);
  await page.getByTestId("job.preset.data-backfill").getByRole("button").click();
  await page.waitForTimeout(800);
  const panel = page.locator(".jobs-main .panel").last();
  const img = await panel.screenshot({ animations: "disabled" });
  const runs = await probe(
    img.toString("base64"),
    'UI inspector. JSON only: {"has_error": true|false, "text_visible": true|false, "summary": "what you see max 15 words"}',
    "Is there an error message or failure text visible in this UI region?",
  );
  report.signals.error_text = {
    runs,
    reliability: reliability(runs, (r) => r.has_error === true && r.text_visible === true),
  };
  await page.close();
}

// ── C. panel_visibility on telegram check result (mocked healthy response) ───
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const TELEGRAM_FIXTURE = {
    generated_at: "2026-01-01T00:00:00Z", source_mode: "fixture",
    summary: {
      bot_profile: "default", token_profile_name: "TELEGRAM_BOT_TOKEN",
      token_configured: false, internal_bot_disabled: false, connectivity_state: "unknown",
      connectivity_detail: "Проверка не выполнялась.", allowed_chat_count: 0,
      allowed_chats_masked: [], commands_count: 0, alerts_count: 0, errors_count: 0,
      last_successful_send: null, last_error: null, startup_status: "unknown",
    },
    recent_commands: [], recent_alerts: [], recent_errors: [],
    truncated: { recent_commands: false, recent_alerts: false, recent_errors: false },
  };
  const CHECK_RESULT = {
    checked_at: "2026-01-01T00:00:00Z", source_mode: "fixture", state: "healthy",
    detail: "getMe succeeded — bot is reachable.", bot_username: "test_bot",
    latency_ms: 42, error: null,
  };
  await page.route(/127\.0\.0\.1:8765\/telegram$/, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(TELEGRAM_FIXTURE) });
  });
  await page.route("**/telegram/connectivity-check", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CHECK_RESULT) });
  });
  await page.goto(`${BASE}/telegram`);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);
  await page.getByTestId("telegram.connectivity-check").click();
  await page.waitForTimeout(800);
  const panel = page.getByTestId("telegram.check.result");
  const img = await panel.screenshot({ animations: "disabled" });
  const runs = await probe(
    img.toString("base64"),
    'UI inspector. JSON only: {"panel_visible": true|false, "primary_label": "most prominent single status word shown or null"}',
    "Is a result or status panel visible in this region? What is the most prominent status word shown (e.g. healthy, error, unknown)?",
  );
  report.signals.panel_visibility = {
    runs,
    reliability: reliability(runs, (r) => r.panel_visible === true),
    primary_label_match_rate: reliability(
      runs,
      (r) => typeof r.primary_label === "string" && r.primary_label.toLowerCase().includes("healthy"),
    ).rate,
  };
  await page.close();
}

// ── D. primary_label (reuses signal C data — already captured) ────────────────
report.signals.primary_label_accuracy = {
  note: "Derived from panel_visibility runs — how often primary_label matched 'healthy'",
  rate: report.signals.panel_visibility.primary_label_match_rate,
};

// ── E. active_nav_styling — known hard (small region, subtle color) ──────────
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(`${BASE}/spot`);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(400);
  const nav = page.getByRole("navigation", { name: "Primary" });
  const img = await nav.screenshot({ animations: "disabled" });
  const runs = await probe(
    img.toString("base64"),
    'UI inspector. JSON only: {"active_link_text": "text of the visually highlighted nav link or null", "distinguishable": true|false}',
    "Which single nav link looks visually active or selected (different background/border/color)?",
  );
  report.signals.active_nav_styling = {
    runs,
    reliability: reliability(
      runs,
      (r) => typeof r.active_link_text === "string" && r.active_link_text.toLowerCase().includes("спот"),
    ),
  };
  await page.close();
}

await browser.close();

// Summary
const summary = Object.fromEntries(
  Object.entries(report.signals).map(([k, v]) => [k, v.reliability ?? { rate: v.rate ?? null }]),
);
report.summary = summary;

fs.writeFileSync(path.join(outDir, "signal-quality.json"), JSON.stringify(report, null, 2));
console.log("\n=== SIGNAL QUALITY SUMMARY ===");
for (const [k, v] of Object.entries(summary)) {
  const r = typeof v.rate === "number" ? (v.rate * 100).toFixed(0) + "%" : String(v.rate);
  const count = v.matched !== undefined ? ` (${v.matched}/${v.total})` : "";
  console.log(`  ${k.padEnd(24)} ${r}${count}`);
}
console.log(`\nReport: ${path.join(outDir, "signal-quality.json")}`);
