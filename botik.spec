# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve().parent
if not (PROJECT_ROOT / "src" / "botik").exists():
    candidate = PROJECT_ROOT / "Botik"
    if (candidate / "src" / "botik").exists():
        PROJECT_ROOT = candidate
if not (PROJECT_ROOT / "src" / "botik").exists():
    PROJECT_ROOT = Path.cwd().resolve()

hiddenimports = []
hiddenimports += collect_submodules("src.botik")
hiddenimports += collect_submodules("webview")
hiddenimports += [
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "webview.platforms.mshtml",
    "webview.guilib",
    "webview.http",
    "webview.dom",
    "clr",          # pythonnet — required by pywebview on Windows
    "System",
    "System.Windows.Forms",
    "yaml",
    "psutil",
    "sqlite3",
    "aiohttp",
    "websockets",
]

datas = []

# ── Project HTML / config / version files ──────────────────────────────────
datas += [
    (str(PROJECT_ROOT / "dashboard_preview.html"), "."),
]

# Optional files — only include if they exist
for optional in [
    ".env.example",
    "config.example.yaml",
    "VERSION",
    "version.txt",
    "README.md",
    "dashboard_workspace_manifest.yaml",
    "dashboard_release_manifest.yaml",
    "active_models.yaml",
]:
    p = PROJECT_ROOT / optional
    if p.exists():
        datas.append((str(p), "."))

# ── Package data ────────────────────────────────────────────────────────────
datas += collect_data_files("src.botik")
datas += collect_data_files("webview")   # includes WebView2Loader.dll + JS files


a = Analysis(
    ["src/botik/windows_entry.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "wx"],
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
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
