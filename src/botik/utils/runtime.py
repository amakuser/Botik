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
    Resolve mutable runtime root.

    - Source mode: project root based on `default_file` and `levels_up`.
    - Frozen mode: directory where executable is located.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(default_file).resolve().parents[levels_up]

