"""
Benchmark script: gemma3:4b vs llama3.2-vision:11b for UI screenshot analysis.

Sends project screenshots to each model via Ollama REST API and measures:
- Whether the model starts successfully
- Latency per request (cold + warm)
- JSON output quality vs expected schema
- Memory pressure (from /proc or nvidia-smi approximation)

Usage:
  python scripts/benchmark_vision_models.py [--screenshots-dir <path>] [--model <name>]
"""

import base64
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SCREENSHOTS_DIR = Path(__file__).parent.parent / ".artifacts" / "local" / "latest" / "vision" / "screenshots"
RESULTS_DIR = Path(__file__).parent.parent / ".artifacts" / "local" / "latest" / "vision" / "benchmark"

MODELS = ["gemma3:4b", "llava:7b"]

# Representative screenshots: clean, dense, state-change, potentially problematic
BENCHMARK_PAGES = ["health", "analytics", "runtime", "spot"]

PROMPT = """You are a UI quality reviewer analyzing a web application screenshot.
This is a dark-theme trading dashboard. Dark backgrounds are intentional. Numeric fields may be empty — expected.

Identify only OBJECTIVE visual quality problems. Return ONLY valid JSON, no other text:
{
  "issues": [
    {
      "type": "overlap|clipping|misalignment|visual-noise|contrast|hierarchy",
      "severity": "low|medium|high",
      "description": "Specific description of what you see",
      "location_hint": "Where on screen",
      "confidence": 0.0
    }
  ],
  "summary": "One-sentence overall assessment",
  "confidence": 0.0
}

If no issues: {"issues": [], "summary": "No visual issues detected.", "confidence": 0.95}"""


def check_ollama_running() -> bool:
    try:
        with _opener.open(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def get_installed_models() -> list[str]:
    try:
        with _opener.open(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            data = json.loads(r.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def query_model(model: str, image_b64: str) -> tuple[dict | None, float, str]:
    """Returns (parsed_json_or_none, latency_seconds, raw_text)."""
    payload = json.dumps({
        "model": model,
        "prompt": PROMPT,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 512},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.time()
    try:
        with _opener.open(req, timeout=120) as r:
            latency = time.time() - t0
            raw = json.loads(r.read())
            text = raw.get("response", "")
            try:
                # Strip markdown fences if present
                clean = text.strip()
                if clean.startswith("```"):
                    clean = "\n".join(clean.split("\n")[1:])
                    clean = clean.rsplit("```", 1)[0].strip()
                parsed = json.loads(clean)
                return parsed, latency, text
            except json.JSONDecodeError:
                return None, latency, text
    except urllib.error.URLError as e:
        latency = time.time() - t0
        return None, latency, f"ERROR: {e}"
    except TimeoutError:
        latency = time.time() - t0
        return None, latency, "ERROR: timeout"


def validate_schema(parsed: dict | None) -> dict:
    """Check if response matches expected schema. Returns score dict."""
    if parsed is None:
        return {"valid_json": False, "has_issues_array": False, "has_summary": False,
                "has_confidence": False, "issues_well_formed": False, "score": 0}

    has_issues = isinstance(parsed.get("issues"), list)
    has_summary = isinstance(parsed.get("summary"), str)
    has_confidence = isinstance(parsed.get("confidence"), (int, float))

    issues_ok = True
    if has_issues:
        for issue in parsed["issues"]:
            required_keys = {"type", "severity", "description", "location_hint", "confidence"}
            if not required_keys.issubset(issue.keys()):
                issues_ok = False
                break
            if issue.get("severity") not in ("low", "medium", "high"):
                issues_ok = False
                break
            if issue.get("type") not in ("overlap", "clipping", "misalignment", "visual-noise", "contrast", "hierarchy"):
                issues_ok = False
                break

    score = sum([has_issues, has_summary, has_confidence, issues_ok])
    return {
        "valid_json": True,
        "has_issues_array": has_issues,
        "has_summary": has_summary,
        "has_confidence": has_confidence,
        "issues_well_formed": issues_ok,
        "score": score,  # 0-4
    }


def get_vram_mb() -> int | None:
    """Try nvidia-smi to get used VRAM in MB."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode().strip()
        return int(out.split("\n")[0])
    except Exception:
        return None


def benchmark_model(model: str, pages: list[str]) -> dict:
    print(f"\n{'='*60}")
    print(f"BENCHMARKING: {model}")
    print(f"{'='*60}")

    installed = get_installed_models()
    if not any(model in m for m in installed):
        print(f"  ✗ Model not installed. Installed: {installed or 'none'}")
        return {"model": model, "available": False, "error": "not installed"}

    print(f"  ✓ Model available")

    results = []
    for page in pages:
        img_path = SCREENSHOTS_DIR / f"{page}.png"
        if not img_path.exists():
            print(f"  [skip] {page}: screenshot not found at {img_path}")
            continue

        print(f"  [{page}] encoding screenshot...", end=" ", flush=True)
        img_b64 = encode_image(img_path)

        vram_before = get_vram_mb()
        print(f"querying model...", end=" ", flush=True)

        parsed, latency, raw = query_model(model, img_b64)
        vram_after = get_vram_mb()

        schema = validate_schema(parsed)
        issue_count = len(parsed["issues"]) if parsed and isinstance(parsed.get("issues"), list) else -1

        status = "✓ JSON" if schema["valid_json"] else "✗ BAD"
        print(f"{status} | {latency:.1f}s | {issue_count} issues | schema {schema['score']}/4")

        results.append({
            "page": page,
            "latency_s": round(latency, 2),
            "valid_json": schema["valid_json"],
            "schema_score": schema["score"],
            "issue_count": issue_count,
            "summary": parsed.get("summary", "") if parsed else "",
            "vram_before_mb": vram_before,
            "vram_after_mb": vram_after,
            "raw_length": len(raw),
        })

        # Warm up pause between requests
        time.sleep(1)

    if not results:
        return {"model": model, "available": True, "error": "no screenshots found"}

    avg_latency = sum(r["latency_s"] for r in results) / len(results)
    avg_schema = sum(r["schema_score"] for r in results) / len(results)
    json_ok_rate = sum(1 for r in results if r["valid_json"]) / len(results)

    print(f"\n  Summary: avg_latency={avg_latency:.1f}s  json_ok={json_ok_rate:.0%}  schema={avg_schema:.1f}/4")

    return {
        "model": model,
        "available": True,
        "requests": len(results),
        "avg_latency_s": round(avg_latency, 2),
        "json_ok_rate": round(json_ok_rate, 2),
        "avg_schema_score": round(avg_schema, 2),
        "results": results,
    }


def classify(data: dict) -> str:
    if not data.get("available"):
        return "NOT PRACTICAL ON THIS MACHINE"
    if data.get("error"):
        return "NOT PRACTICAL ON THIS MACHINE"

    latency = data.get("avg_latency_s", 999)
    json_rate = data.get("json_ok_rate", 0)
    schema = data.get("avg_schema_score", 0)

    if latency > 60:
        return "NOT PRACTICAL ON THIS MACHINE"
    if json_rate < 0.5 or schema < 2:
        return "NOT PRACTICAL ON THIS MACHINE"
    if latency <= 15 and json_rate >= 0.8 and schema >= 3:
        return "GOOD DEFAULT TOOL"
    return "OPTIONAL DEEP REVIEW TOOL"


def main():
    print("Vision Model Benchmark")
    print(f"Screenshots dir: {SCREENSHOTS_DIR}")
    print(f"Testing pages: {BENCHMARK_PAGES}")

    if not check_ollama_running():
        print("ERROR: Ollama server not running at http://127.0.0.1:11434")
        sys.exit(1)

    print(f"Ollama running ✓")
    print(f"Installed models: {get_installed_models() or 'none'}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = {}
    for model in MODELS:
        data = benchmark_model(model, BENCHMARK_PAGES)
        data["classification"] = classify(data)
        all_results[model] = data

    # Write raw results
    results_path = RESULTS_DIR / "benchmark_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)

    # Print final report
    print(f"\n{'='*60}")
    print("FINAL REPORT")
    print(f"{'='*60}")
    for model, data in all_results.items():
        print(f"\n{model.upper()}")
        print(f"  Available:       {data.get('available', False)}")
        if data.get("available"):
            print(f"  Avg latency:     {data.get('avg_latency_s', 'N/A')}s")
            print(f"  JSON valid rate: {data.get('json_ok_rate', 0):.0%}")
            print(f"  Schema score:    {data.get('avg_schema_score', 0):.1f}/4")
        print(f"  Classification:  ► {data['classification']}")

    print(f"\nRaw results: {results_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
