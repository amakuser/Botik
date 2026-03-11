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
hiddenimports += [
    "telebot",
    "yaml",
    "sqlite3",
    "aiohttp",
    "websockets",
]

datas = [
    (str(PROJECT_ROOT / ".env.example"), "."),
    (str(PROJECT_ROOT / "config.example.yaml"), "."),
    (str(PROJECT_ROOT / "VERSION"), "."),
    (str(PROJECT_ROOT / "version.txt"), "."),
    (str(PROJECT_ROOT / "README.md"), "."),
]
datas += collect_data_files("src.botik")


a = Analysis(
    ["src/botik/windows_entry.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
