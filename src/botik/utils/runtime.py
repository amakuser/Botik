"""
Helpers for runtime path resolution in source and frozen (PyInstaller) modes.
"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_root(default_file: str, levels_up: int) -> Path:
    """
    Resolve mutable runtime root (config, .env, data/).

    - Source mode: project root based on `default_file` and `levels_up`.
    - Frozen mode: directory where executable is located.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(default_file).resolve().parents[levels_up]


def bundled_file(filename: str, fallback: Path) -> Path:
    """
    Resolve a read-only file bundled by PyInstaller (goes to sys._MEIPASS).

    - Frozen mode: sys._MEIPASS/filename (extracted bundle), fallback to exe dir.
    - Source mode: fallback / filename (same as ROOT_DIR / filename).
    """
    if is_frozen():
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        candidate = meipass / filename
        if candidate.exists():
            return candidate
        # fallback: next to the exe (e.g. when user copies HTML manually)
        return Path(sys.executable).resolve().parent / filename
    return fallback / filename

