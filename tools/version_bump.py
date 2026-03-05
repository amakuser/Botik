"""
Version bump utility for Botik.

Usage examples:
  python tools/version_bump.py --show
  python tools/version_bump.py --increment 1
  python tools/version_bump.py --set-version 1.1.0 --reset-build
  python tools/version_bump.py --set-version 1.1.0 --increment 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.botik.version import VERSION_FILE, load_app_version


def write_version_file(path: Path, version: str, build: int) -> None:
    path.write_text(f"version={version}\nbuild={build}\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Botik version bump tool")
    parser.add_argument("--show", action="store_true", help="Show current version and exit")
    parser.add_argument("--set-version", default="", help="Set base semantic version (example: 1.2.0)")
    parser.add_argument("--increment", type=int, default=1, help="Increase build counter by N (can be 0)")
    parser.add_argument("--reset-build", action="store_true", help="Reset build to 0 before increment")
    args = parser.parse_args()

    current = load_app_version(VERSION_FILE)
    if args.show:
        print(current.label)
        return 0

    new_version = args.set_version.strip() or current.version
    new_build = current.build

    if args.set_version and args.reset_build:
        new_build = 0
    new_build += args.increment

    if new_build <= 0:
        raise SystemExit("build must be > 0 after increment")

    write_version_file(VERSION_FILE, version=new_version, build=new_build)
    updated = load_app_version(VERSION_FILE)

    print(f"old={current.label}")
    print(f"new={updated.label}")
    print(f"file={VERSION_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
