/**
 * Probe: test multiple prompts + crops on the jobs error scenario.
 * Writes results to .artifacts/local/latest/vision/jobs-probe.json.
 *
 * Run: node scripts/probe_jobs_vision.mjs
 */
import { chromium } from "@playwright/test";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const BASE = "http://127.0.0.1:4173";
const OLLAMA_HOST = "127.0.0.1";
const OLLAMA_PORT = 11434;
const MODEL = "gemma3:4b";

function ask(payload) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: OLLAMA_HOST, port: OLLAMA_PORT, path: "/api/chat", method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) } },
      (res) => {
        let body = "";
        res.on("data", (c) => { body += c; });
        res.on("end", () => {
          try { resolve(JSON.parse(body)); }
          catch { reject(new Error("parse: " + body.slice(0, 100))); }
        });
      }
    );
    req.on("error", reject);
    req.setTimeout(45000, () => req.destroy());
    req.write(payload); req.end();
  });
}

async function probe(imgB64, label, systemPrompt, userQuestion, iters = 3) {
  const results = [];
  for (let i = 0; i < iters; i++) {
    const payload = JSON.stringify({
      model: MODEL, format: "json", stream: false,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userQuestion, images: [imgB64] },
      ],
      options: { temperature: 0, num_predict: 120 },
    });
    const t0 = Date.now();
    try {
      const r = await ask(payload);
      const latency = Date.now() - t0;
      let parsed;
      try { parsed = JSON.parse(r.message.content); } catch { parsed = { _raw: r.message.content.slice(0, 200) }; }
      results.push({ iter: i + 1, latency_ms: latency, raw: parsed });
    } catch (e) {
      results.push({ iter: i + 1, error: e.message });
    }
  }
  return { label, results };
}

const browser = await chromium.launch({ headless: true, args: ["--no-proxy-server"] });
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

const outDir = path.join(process.cwd(), ".artifacts", "local", "latest", "vision");
fs.mkdirSync(outDir, { recursive: true });

// Three different crops
const bare = await page.getByTestId("jobs.action-error").screenshot({ animations: "disabled" });
const section = await page.locator(".jobs-main .panel").last().screenshot({ animations: "disabled" });
const mainArea = await page.locator(".jobs-main").screenshot({ animations: "disabled" });

fs.writeFileSync(path.join(outDir, "probe_bare.png"), bare);
fs.writeFileSync(path.join(outDir, "probe_section.png"), section);
fs.writeFileSync(path.join(outDir, "probe_main.png"), mainArea);

const bareB64 = bare.toString("base64");
const sectionB64 = section.toString("base64");
const mainB64 = mainArea.toString("base64");

// Prompt variants
const PROMPTS = {
  current: {
    system: 'UI inspector. JSON only: {"has_action_banner": true|false, "banner_type": "error|success|warning|null", "text": "notification text or null"}',
    user: "Is there a standalone notification box or alert that appeared as a result of a user action (not a card status badge)?",
  },
  simple_error_text: {
    system: 'UI inspector. JSON only: {"has_error": true|false, "text_visible": true|false, "summary": "what you see max 15 words"}',
    user: "Is there an error message or failure text visible in this UI region?",
  },
  panel_with_heading: {
    system: 'UI panel inspector. JSON only: {"heading_visible": true|false, "heading_text": "string or null", "body_has_error_content": true|false}',
    user: "Describe the panel: is there a heading? does the body contain error/failure content?",
  },
  describe_only: {
    system: 'JSON only: {"primary_content": "what is the main visible content in 10 words"}',
    user: "What is the main visible content of this region?",
  },
};

const report = { generated_at: new Date().toISOString(), crops: {} };

for (const [cropName, b64] of [["bare", bareB64], ["section", sectionB64], ["main", mainB64]]) {
  report.crops[cropName] = {};
  for (const [promptName, p] of Object.entries(PROMPTS)) {
    console.log(`\n=== crop=${cropName} prompt=${promptName} ===`);
    const r = await probe(b64, `${cropName}/${promptName}`, p.system, p.user, 3);
    report.crops[cropName][promptName] = r;
    for (const it of r.results) {
      console.log(`  iter=${it.iter} latency=${it.latency_ms}ms raw=${JSON.stringify(it.raw).slice(0, 140)}`);
    }
  }
}

fs.writeFileSync(path.join(outDir, "jobs-probe.json"), JSON.stringify(report, null, 2));
console.log(`\nReport: ${path.join(outDir, "jobs-probe.json")}`);

await browser.close();
