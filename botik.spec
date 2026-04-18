# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Botik.

Bundles:
  - src/botik/              — trading runtime + entry point
  - app-service/src/        — FastAPI app-service
  - frontend/dist/          — compiled Vite/React frontend (must build first)

Build:
  cd frontend && pnpm build
  pyinstaller --clean botik.spec
"""
from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve()

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports: list[str] = []
hiddenimports += collect_submodules("src.botik")
hiddenimports += collect_submodules("botik_app_service")
hiddenimports += [
    # uvicorn internals loaded dynamically
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.off",
    "uvicorn.lifespan.on",
    "uvicorn.middleware",
    "uvicorn.middleware.asgi2",
    "uvicorn.middleware.message_logger",
    "uvicorn.middleware.proxy_headers",
    # starlette / fastapi
    "starlette.routing",
    "starlette.responses",
    "starlette.staticfiles",
    "starlette.middleware.cors",
    "fastapi.staticfiles",
    # async / http
    "anyio",
    "anyio._backends._asyncio",
    "h11",
    # optional speedups (ok if absent)
    "httptools",
    "watchfiles",
    # project deps
    "yaml",
    "sqlite3",
    "aiohttp",
    "websockets",
]

# ── Data files ────────────────────────────────────────────────────────────────
_dist = PROJECT_ROOT / "frontend" / "dist"
if not _dist.exists():
    raise SystemExit(
        f"\n[botik.spec] frontend/dist/ not found — run `pnpm build` in frontend/ first.\n"
    )

datas: list[tuple[str, str]] = [
    (str(_dist), "frontend/dist"),
    (str(PROJECT_ROOT / "VERSION"), "."),
    (str(PROJECT_ROOT / "config.example.yaml"), "."),
]
if (PROJECT_ROOT / "active_models.yaml").exists():
    datas.append((str(PROJECT_ROOT / "active_models.yaml"), "."))
if (PROJECT_ROOT / ".env.example").exists():
    datas.append((str(PROJECT_ROOT / ".env.example"), "."))

datas += collect_data_files("botik_app_service")

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["src/botik/windows_entry.py"],
    pathex=[
        str(PROJECT_ROOT),
        str(PROJECT_ROOT / "app-service" / "src"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="botik",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
