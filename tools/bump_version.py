"""Auto-increments the patch number in the VERSION file.

Usage: python tools/bump_version.py
Rules: 0.0.22 -> 0.0.23 -> ... -> 0.0.99 -> 0.1.0 -> ... -> 0.1.99 -> 0.2.0
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"

txt = VERSION_FILE.read_text(encoding="utf-8").strip()
v = txt.split("=", 1)[1].strip()
major, minor, patch = (int(x) for x in v.split("."))

patch += 1
if patch >= 100:
    patch = 0
    minor += 1
if minor >= 100:
    minor = 0
    major += 1

new_v = f"{major}.{minor}.{patch}"
VERSION_FILE.write_text(f"version={new_v}\n", encoding="utf-8")
print(f"version: {v} -> {new_v}")
