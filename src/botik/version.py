"""
Application version helpers.

Version is stored in project root file:
  VERSION
with fields:
  version=1.0.0
  build=1
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT_DIR / "VERSION"

DEFAULT_VERSION = "0.1.0"
DEFAULT_BUILD = 1


@dataclass(frozen=True)
class AppVersion:
    version: str
    build: int

    @property
    def label(self) -> str:
        return f"{self.version}+{self.build}"


def load_app_version(path: Path | None = None) -> AppVersion:
    version_file = path or VERSION_FILE
    version = DEFAULT_VERSION
    build = DEFAULT_BUILD

    if version_file.exists():
        for raw_line in version_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "version" and value:
                version = value
            elif key == "build":
                try:
                    parsed = int(value)
                    if parsed > 0:
                        build = parsed
                except ValueError:
                    pass
    return AppVersion(version=version, build=build)


def get_app_version_label(path: Path | None = None) -> str:
    return load_app_version(path).label

