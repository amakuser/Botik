"""
Application version helpers.

Version is stored in project root file VERSION:
  version=0.0.22

Single incrementing number — patch part grows with every build.
At 100 → minor bumps: 0.0.99 → 0.1.0, 0.1.99 → 0.2.0, etc.
"""
from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT_DIR / "VERSION"
BUILD_SHA_FILE = ROOT_DIR / "version.txt"

DEFAULT_VERSION = "0.0.1"


def get_app_version_label(path: Path | None = None) -> str:
    """Return version string, e.g. '0.0.22'."""
    f = path or VERSION_FILE
    if f.exists():
        for raw in f.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("version="):
                v = line.split("=", 1)[1].strip()
                if v:
                    return v
    return DEFAULT_VERSION


def load_app_version(path: Path | None = None) -> str:
    """Alias for get_app_version_label (backward compatibility)."""
    return get_app_version_label(path)


def load_build_sha(path: Path | None = None) -> str:
    sha_file = path or BUILD_SHA_FILE
    if not sha_file.exists():
        return ""
    try:
        value = sha_file.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except Exception:
        return ""
    if not value:
        return ""
    if 6 <= len(value) <= 64 and all(ch in "0123456789abcdefABCDEF" for ch in value):
        return value
    return ""
