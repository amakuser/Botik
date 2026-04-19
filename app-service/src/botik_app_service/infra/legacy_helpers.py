"""Standalone replacements for the deleted src.botik.gui.api_helpers functions.

All adapters that previously did lazy imports from src.botik.gui.api_helpers
should import from here instead.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]


def load_config(repo_root: Path) -> dict:
    config_path = repo_root / "config.yaml"
    if not config_path.exists() or _yaml is None:
        return {}
    with open(config_path, encoding="utf-8") as fh:
        return _yaml.safe_load(fh) or {}


def resolve_db_path(repo_root: Path, cfg: dict | None = None) -> Path:
    if cfg is None:
        cfg = load_config(repo_root)
    rel = cfg.get("storage", {}).get("path", "data/botik.db")
    return repo_root / rel


def resolve_log_path(repo_root: Path, cfg: dict | None = None) -> Path:
    if cfg is None:
        cfg = load_config(repo_root)
    log_dir = cfg.get("logging", {}).get("dir", "logs")
    return repo_root / log_dir / "botik.log"


def read_env_map(repo_root: Path) -> dict[str, str]:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return dict(os.environ)
    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def config_path(repo_root: Path) -> Path:
    return repo_root / "config.yaml"


def env_path(repo_root: Path) -> Path:
    return repo_root / ".env"


def active_models_path(repo_root: Path) -> Path:
    return repo_root / "data" / "ml" / "active_models.json"
