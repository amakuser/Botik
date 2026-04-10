"""
Shared helpers and path constants for the Botik dashboard API.

All modules in this package import ROOT_DIR, CONFIG_PATH, ENV_PATH and the
helper functions from here — never from each other or from webview_app.py.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from src.botik.utils.runtime import bundled_file


# ─────────────────────────────────────────────────────────────
#  Project-root resolution  (source mode vs PyInstaller exe)
# ─────────────────────────────────────────────────────────────

def _resolve_project_root() -> Path:
    """Return project root in both source and frozen (PyInstaller) modes.

    Source mode  : 3 levels up from this file (src/botik/gui → project root).
    Frozen mode  : walk from exe dir upward looking for .env or config.yaml.
                   Falls back to exe dir if neither is found (first run).
    """
    if bool(getattr(sys, "frozen", False)):
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in [exe_dir, exe_dir.parent]:
            if (candidate / ".env").exists() or (candidate / "config.yaml").exists():
                return candidate
        return exe_dir
    return Path(__file__).resolve().parents[3]


ROOT_DIR          = _resolve_project_root()
CONFIG_PATH       = ROOT_DIR / "config.yaml"
ENV_PATH          = ROOT_DIR / ".env"

# Read-only bundled assets (live in sys._MEIPASS when frozen)
HTML_PATH         = bundled_file("dashboard_preview.html", ROOT_DIR)
ACTIVE_MODELS_PATH = bundled_file("active_models.yaml", ROOT_DIR)

# Dashboard component paths
DASHBOARD_TEMPLATE = ROOT_DIR / "dashboard_template.html"
PAGES_DIR = ROOT_DIR / "src" / "botik" / "gui" / "pages"


def assemble_dashboard_html() -> str:
    """Assemble dashboard HTML from template + component page files.

    In source mode: reads dashboard_template.html and substitutes
    <!-- INJECT:page-X --> markers with contents of src/botik/gui/pages/page-X.html.

    Falls back to dashboard_preview.html if template is not found (frozen/exe mode).
    Regenerates dashboard_preview.html so the assembled output is always current.
    """
    if not DASHBOARD_TEMPLATE.exists():
        # Frozen exe: template not bundled, use pre-built HTML
        return HTML_PATH.read_text(encoding="utf-8")

    import re as _re

    template = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")

    def _substitute(match: "_re.Match[str]") -> str:  # type: ignore[name-defined]
        page_id = match.group(1)   # e.g. "page-home"
        page_file = PAGES_DIR / f"{page_id}.html"
        if page_file.exists():
            return page_file.read_text(encoding="utf-8")
        return match.group(0)  # leave marker in place if file missing

    assembled = _re.sub(r"<!-- INJECT:(page-[^>]+) -->", _substitute, template)

    # Write the assembled result back to dashboard_preview.html (keeps it current)
    try:
        HTML_PATH.write_text(assembled, encoding="utf-8")
    except Exception:
        pass  # read-only filesystem in some environments is fine

    return assembled

# Strategy ordering / label mapping used by trading API
STRATEGY_MODE_ORDER: list[str] = [
    "spot_spread",
    "spot_spike",
    "futures_spike_reversal",
]
STRATEGY_PRESET_LABELS: dict[str, str] = {
    "Spot Spread (Maker)":   "spot_spread",
    "Spot Spike Burst":      "spot_spike",
    "Futures Spike Reversal": "futures_spike_reversal",
}


# ─────────────────────────────────────────────────────────────
#  Config / env helpers
# ─────────────────────────────────────────────────────────────

def _load_yaml() -> dict[str, Any]:
    """Load config.yaml; returns {} on any error."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _read_env_map() -> dict[str, str]:
    """Parse .env file into a plain dict (key → value, no shell expansion)."""
    result: dict[str, str] = {}
    try:
        with open(ENV_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip()
    except Exception:
        pass
    return result


def _resolve_db_path(raw_cfg: dict) -> Path:
    """Resolve absolute path to botik.db from config dict."""
    db = str((raw_cfg.get("stats") or {}).get("db_path") or "data/botik.db")
    p = Path(db)
    if not p.is_absolute():
        p = ROOT_DIR / p
    return p


def _resolve_botik_log_path(raw_cfg: dict) -> Path:
    """Resolve absolute path to botik.log from config dict."""
    lp = str((raw_cfg.get("logging") or {}).get("log_path") or "logs/botik.log")
    p = Path(lp)
    if not p.is_absolute():
        p = ROOT_DIR / p
    return p


def _detect_launcher_mode() -> str:
    """Return 'packaged' when running as PyInstaller exe, else 'source'."""
    return "packaged" if bool(getattr(sys, "frozen", False)) else "source"


def _dashboard_subprocess_popen_kwargs() -> dict[str, Any]:
    """Return Windows-safe kwargs for subprocess calls from the dashboard process."""
    kwargs: dict[str, Any] = {}
    if sys.platform.startswith("win"):
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
        if creationflags:
            kwargs["creationflags"] = creationflags
        if startupinfo_cls:
            startupinfo = startupinfo_cls()
            startupinfo.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0))
            startupinfo.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
            kwargs["startupinfo"] = startupinfo
    return kwargs


def _dashboard_subprocess_run_kwargs() -> dict[str, Any]:
    """Return no-window kwargs for subprocess.run/check_output on the dashboard."""
    kwargs = _dashboard_subprocess_popen_kwargs()
    kwargs["stdin"] = subprocess.DEVNULL
    return kwargs


# ─────────────────────────────────────────────────────────────
#  Subprocess command builder (source + frozen exe)
# ─────────────────────────────────────────────────────────────

_WORKER_MODULE_MAP: dict[str, str] = {
    "backfill": "src.botik.data.backfill_entry",
    "live":     "src.botik.data.live_entry",
    "training": "src.botik.data.training_worker",
}


def _build_subprocess_cmd(worker: str, extra_args: list[str] | None = None) -> list[str]:
    """
    Build a subprocess command that works in both source and frozen (exe) modes.

    Source mode  → [python, -m, src.botik.data.<worker>, *extra_args]
    Frozen mode  → [botik.exe, --worker, <worker>, *extra_args]
                   (handled by windows_entry.py --worker dispatch)
    """
    if getattr(sys, "frozen", False):
        cmd: list[str] = [sys.executable, "--worker", worker]
    else:
        module = _WORKER_MODULE_MAP[worker]
        cmd = [sys.executable, "-m", module]
    if extra_args:
        cmd += extra_args
    return cmd
