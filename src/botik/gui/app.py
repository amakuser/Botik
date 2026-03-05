"""
Desktop GUI launcher for local operation (Windows/Linux desktop).

Features:
- Start/stop trading and ML processes.
- Live logs inside the app.
- Preflight run button.
- Settings tab to edit .env and config.yaml directly.
"""
from __future__ import annotations

import asyncio
import os
import queue
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk, messagebox

import yaml


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT_DIR / ".env"
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"


def _default_python() -> str:
    win_venv = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    posix_venv = ROOT_DIR / ".venv" / "bin" / "python"
    if win_venv.exists():
        return str(win_venv)
    if posix_venv.exists():
        return str(posix_venv)
    return sys.executable


def _read_env_map(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip()
    return data


def _upsert_env(path: Path, updates: dict[str, str]) -> None:
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    consumed: set[str] = set()
    out: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                consumed.add(key)
                continue
        out.append(line)

    for key, val in updates.items():
        if key not in consumed:
            out.append(f"{key}={val}")

    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


class ManagedProcess:
    def __init__(self, name: str, on_output: Callable[[str], None]) -> None:
        self.name = name
        self.on_output = on_output
        self.proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self.last_exit_code: int | None = None
        self.state: str = "stopped"  # stopped | running | error

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, cmd: list[str], cwd: Path) -> None:
        if self.running:
            return
        self.last_exit_code = None
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.state = "running"
        self.on_output(f"[{self.name}] started: {' '.join(cmd)}")
        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()

    def _read_output(self) -> None:
        if self.proc is None or self.proc.stdout is None:
            return
        for line in self.proc.stdout:
            self.on_output(f"[{self.name}] {line.rstrip()}")
        code = self.proc.wait()
        self.last_exit_code = code
        self.state = "stopped" if code == 0 else "error"
        self.on_output(f"[{self.name}] exited with code {code}")

    def stop(self) -> None:
        if not self.running or self.proc is None:
            return
        self.on_output(f"[{self.name}] stopping...")
        self.proc.terminate()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.on_output(f"[{self.name}] force kill")
            self.proc.kill()
        self.last_exit_code = 0
        self.state = "stopped"
        self.on_output(f"[{self.name}] stopped")


class BotikGui:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Botik Desktop")
        self.root.geometry("1180x790")
        self.root.minsize(1020, 700)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.trading = ManagedProcess("trading", self._enqueue_log)
        self.ml = ManagedProcess("ml", self._enqueue_log)

        self.python_var = tk.StringVar(value=_default_python())
        self.config_var = tk.StringVar(value=str(DEFAULT_CONFIG_PATH))

        self.env_vars: dict[str, tk.StringVar] = {
            "TELEGRAM_BOT_TOKEN": tk.StringVar(),
            "TELEGRAM_CHAT_ID": tk.StringVar(),
            "BYBIT_API_KEY": tk.StringVar(),
            "BYBIT_API_SECRET_KEY": tk.StringVar(),
            "BYBIT_RSA_PRIVATE_KEY_PATH": tk.StringVar(),
        }

        self.cfg_execution_mode = tk.StringVar(value="paper")
        self.cfg_start_paused = tk.BooleanVar(value=True)
        self.cfg_bybit_host = tk.StringVar(value="api-demo.bybit.com")
        self.cfg_ws_host = tk.StringVar(value="stream.bybit.com")
        self.cfg_symbols = tk.StringVar(value="BTCUSDT,ETHUSDT")
        self.cfg_target_profit = tk.StringVar(value="0.0002")
        self.cfg_safety_buffer = tk.StringVar(value="0.0001")
        self.cfg_stop_loss = tk.StringVar(value="0.003")
        self.cfg_take_profit = tk.StringVar(value="0.005")
        self.cfg_hold_timeout = tk.StringVar(value="180")
        self.cfg_maker_only = tk.BooleanVar(value=True)

        self.balance_total_var = tk.StringVar(value="n/a")
        self.balance_available_var = tk.StringVar(value="n/a")
        self.balance_wallet_var = tk.StringVar(value="n/a")
        self.open_orders_var = tk.StringVar(value="0")
        self.api_status_var = tk.StringVar(value="not checked")
        self.snapshot_time_var = tk.StringVar(value="-")

        self._suspend_autosave = False
        self._autosave_env_after_id: str | None = None
        self._autosave_cfg_after_id: str | None = None
        self._runtime_refresh_lock = threading.Lock()
        self._runtime_refresh_inflight = False

        self._setup_style()
        self._build_ui()
        self._setup_edit_shortcuts()
        self._setup_autosave()
        self.load_settings()

        self._update_status()
        self._drain_logs()
        self._schedule_runtime_refresh(initial_delay_ms=1000)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_edit_shortcuts(self) -> None:
        self._edit_menu_target: tk.Widget | None = None
        self.edit_menu = tk.Menu(self.root, tearoff=0)
        self.edit_menu.add_command(label="Cut", command=lambda: self._edit_action("cut"))
        self.edit_menu.add_command(label="Copy", command=lambda: self._edit_action("copy"))
        self.edit_menu.add_command(label="Paste", command=lambda: self._edit_action("paste"))
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Select All", command=lambda: self._edit_action("select_all"))

        # Global edit shortcuts for focused Entry/Text widgets, independent from keyboard layout.
        self.root.bind_all("<Control-KeyPress>", self._on_ctrl_keypress, add="+")
        self.root.bind_all("<Shift-Insert>", lambda e: self._edit_action("paste", event=e), add="+")

    def _on_ctrl_keypress(self, event: tk.Event) -> str | None:
        keycode_map = {
            67: "copy",       # C
            88: "cut",        # X
            86: "paste",      # V
            65: "select_all", # A
        }
        keysym_map = {
            "c": "copy", "с": "copy",
            "x": "cut", "ч": "cut",
            "v": "paste", "м": "paste",
            "a": "select_all", "ф": "select_all",
        }
        action = keycode_map.get(getattr(event, "keycode", -1))
        if action is None:
            action = keysym_map.get(str(getattr(event, "keysym", "")).lower())
        if action is None:
            return None
        return self._edit_action(action, event=event)

    def _setup_autosave(self) -> None:
        for var in self.env_vars.values():
            var.trace_add("write", lambda *_: self._schedule_autosave_env())

        cfg_vars: list[tk.Variable] = [
            self.cfg_execution_mode,
            self.cfg_start_paused,
            self.cfg_bybit_host,
            self.cfg_ws_host,
            self.cfg_symbols,
            self.cfg_target_profit,
            self.cfg_safety_buffer,
            self.cfg_stop_loss,
            self.cfg_take_profit,
            self.cfg_hold_timeout,
            self.cfg_maker_only,
            self.config_var,
        ]
        for var in cfg_vars:
            var.trace_add("write", lambda *_: self._schedule_autosave_cfg())

    def _schedule_autosave_env(self) -> None:
        if self._suspend_autosave:
            return
        if self._autosave_env_after_id is not None:
            self.root.after_cancel(self._autosave_env_after_id)
        self._autosave_env_after_id = self.root.after(500, self._autosave_env)

    def _schedule_autosave_cfg(self) -> None:
        if self._suspend_autosave:
            return
        if self._autosave_cfg_after_id is not None:
            self.root.after_cancel(self._autosave_cfg_after_id)
        self._autosave_cfg_after_id = self.root.after(700, self._autosave_cfg)

    def _autosave_env(self) -> None:
        self._autosave_env_after_id = None
        self.save_env(show_popup=False)

    def _autosave_cfg(self) -> None:
        self._autosave_cfg_after_id = None
        self.save_config(show_popup=False)

    def _flush_autosave(self) -> None:
        if self._autosave_env_after_id is not None:
            self.root.after_cancel(self._autosave_env_after_id)
            self._autosave_env_after_id = None
            self.save_env(show_popup=False)
        if self._autosave_cfg_after_id is not None:
            self.root.after_cancel(self._autosave_cfg_after_id)
            self._autosave_cfg_after_id = None
            self.save_config(show_popup=False)

    def _setup_style(self) -> None:
        bg = "#F3F7F5"
        card = "#FFFFFF"
        accent = "#0E7C66"
        text = "#17312B"
        soft = "#6B8178"

        self.root.configure(bg=bg)
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("Root.TFrame", background=bg)
        style.configure("Card.TFrame", background=card, relief="flat")
        style.configure("Title.TLabel", background=bg, foreground=text, font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=bg, foreground=soft, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=card, foreground=text, font=("Segoe UI", 11, "bold"))
        style.configure("Body.TLabel", background=card, foreground=text, font=("Segoe UI", 9))
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton", background=[("active", accent)])

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root, style="Root.TFrame", padding=12)
        root_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root_frame, text="Botik Control Console", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            root_frame,
            text="Desktop mode for local monitoring and settings. Server mode stays CLI/systemd.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        notebook = ttk.Notebook(root_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.control_tab = ttk.Frame(notebook, style="Root.TFrame")
        self.settings_tab = ttk.Frame(notebook, style="Root.TFrame")
        notebook.add(self.control_tab, text="Control")
        notebook.add(self.settings_tab, text="Settings")

        self._build_control_tab()
        self._build_settings_tab()
        self._attach_context_menu_to_entries(self.root)

    def _is_edit_widget(self, widget: tk.Widget | None) -> bool:
        return isinstance(widget, (tk.Entry, ttk.Entry, tk.Text))

    def _attach_context_menu_to_entries(self, parent: tk.Widget) -> None:
        for child in parent.winfo_children():
            if isinstance(child, (tk.Entry, ttk.Entry, tk.Text)):
                child.bind("<Button-3>", self._show_edit_menu)
                child.bind("<Button-2>", self._show_edit_menu)
                child.bind("<Shift-F10>", self._show_edit_menu)
                child.bind("<Menu>", self._show_edit_menu)
            self._attach_context_menu_to_entries(child)

    def _show_edit_menu(self, event: tk.Event) -> None:
        self._edit_menu_target = event.widget
        x_root = getattr(event, "x_root", 0) or self.root.winfo_pointerx()
        y_root = getattr(event, "y_root", 0) or self.root.winfo_pointery()
        try:
            self.edit_menu.tk_popup(x_root, y_root)
        finally:
            self.edit_menu.grab_release()

    def _edit_action(self, action: str, event: tk.Event | None = None) -> str | None:
        widget = event.widget if event is not None else self._edit_menu_target
        if widget is None or not self._is_edit_widget(widget):
            widget = self.root.focus_get()
            if widget is None or not self._is_edit_widget(widget):
                return None

        if action == "copy":
            widget.event_generate("<<Copy>>")
        elif action == "cut":
            widget.event_generate("<<Cut>>")
        elif action == "paste":
            widget.event_generate("<<Paste>>")
        elif action == "select_all":
            widget.event_generate("<<SelectAll>>")
        return "break" if event is not None else None

    def _build_control_tab(self) -> None:
        left = ttk.Frame(self.control_tab, style="Root.TFrame")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8), pady=4)
        right = ttk.Frame(self.control_tab, style="Root.TFrame")
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0), pady=4)

        path_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        path_card.pack(fill=tk.X)
        ttk.Label(path_card, text="Runtime Paths", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W, columnspan=2)

        ttk.Label(path_card, text="Python", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Entry(path_card, textvariable=self.python_var, width=95).grid(row=1, column=1, sticky=tk.EW, padx=8)
        ttk.Label(path_card, text="Config", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=6)
        ttk.Entry(path_card, textvariable=self.config_var, width=95).grid(row=2, column=1, sticky=tk.EW, padx=8)
        path_card.columnconfigure(1, weight=1)

        action_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        action_card.pack(fill=tk.X, pady=8)
        ttk.Label(action_card, text="Actions", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W)

        ttk.Button(action_card, text="Start Trading", command=self.start_trading).grid(row=1, column=0, sticky=tk.EW, padx=4, pady=6)
        ttk.Button(action_card, text="Stop Trading", command=self.stop_trading).grid(row=1, column=1, sticky=tk.EW, padx=4, pady=6)
        ttk.Button(action_card, text="Run Preflight", command=self.run_preflight, style="Accent.TButton").grid(row=1, column=2, sticky=tk.EW, padx=4, pady=6)

        ttk.Button(action_card, text="Start ML", command=self.start_ml).grid(row=2, column=0, sticky=tk.EW, padx=4, pady=6)
        ttk.Button(action_card, text="Stop ML", command=self.stop_ml).grid(row=2, column=1, sticky=tk.EW, padx=4, pady=6)
        ttk.Button(action_card, text="Clear Log", command=self.clear_log).grid(row=2, column=2, sticky=tk.EW, padx=4, pady=6)
        ttk.Button(action_card, text="Copy Selected", command=self.copy_selected_log).grid(row=3, column=0, sticky=tk.EW, padx=4, pady=6)
        ttk.Button(action_card, text="Copy All", command=self.copy_all_log).grid(row=3, column=1, sticky=tk.EW, padx=4, pady=6)
        ttk.Label(action_card, text="Tip: right click in log for copy menu", style="Body.TLabel").grid(row=3, column=2, sticky=tk.EW, padx=4, pady=6)

        for i in range(3):
            action_card.columnconfigure(i, weight=1)

        account_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        account_card.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(account_card, text="Счет и ордера", style="Section.TLabel").grid(
            row=0, column=0, columnspan=6, sticky=tk.W
        )
        ttk.Label(account_card, text="Баланс USDT", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Label(account_card, textvariable=self.balance_total_var, style="Body.TLabel").grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Label(account_card, text="Доступно", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(account_card, textvariable=self.balance_available_var, style="Body.TLabel").grid(row=1, column=3, sticky=tk.W, pady=4)
        ttk.Label(account_card, text="Кошелек", style="Body.TLabel").grid(row=1, column=4, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(account_card, textvariable=self.balance_wallet_var, style="Body.TLabel").grid(row=1, column=5, sticky=tk.W, pady=4)

        ttk.Label(account_card, text="Открытые ордера", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Label(account_card, textvariable=self.open_orders_var, style="Body.TLabel").grid(row=2, column=1, sticky=tk.W, pady=4)
        ttk.Label(account_card, text="API", style="Body.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(16, 0), pady=4)
        ttk.Label(account_card, textvariable=self.api_status_var, style="Body.TLabel").grid(row=2, column=3, columnspan=2, sticky=tk.W, pady=4)
        ttk.Label(account_card, text="Обновлено", style="Body.TLabel").grid(row=2, column=5, sticky=tk.E, pady=4)
        ttk.Label(account_card, textvariable=self.snapshot_time_var, style="Body.TLabel").grid(row=2, column=6, sticky=tk.W, pady=4, padx=(6, 0))
        ttk.Button(account_card, text="Обновить данные", command=self.refresh_runtime_snapshot).grid(
            row=1, column=6, rowspan=1, sticky=tk.E, padx=(14, 0), pady=2
        )
        account_card.columnconfigure(6, weight=1)

        orders_frame = ttk.Frame(account_card, style="Card.TFrame")
        orders_frame.grid(row=3, column=0, columnspan=7, sticky=tk.EW, pady=(8, 0))
        orders_frame.columnconfigure(0, weight=1)
        orders_frame.columnconfigure(1, weight=1)

        open_card = ttk.Frame(orders_frame, style="Card.TFrame")
        open_card.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 6))
        ttk.Label(open_card, text="Открытые ордера (биржа)", style="Body.TLabel").pack(anchor=tk.W)
        self.open_orders_tree = ttk.Treeview(
            open_card,
            columns=("symbol", "side", "price", "qty", "status"),
            show="headings",
            height=5,
        )
        for col, title, width in [
            ("symbol", "Symbol", 95),
            ("side", "Side", 60),
            ("price", "Price", 90),
            ("qty", "Qty", 90),
            ("status", "Status", 90),
        ]:
            self.open_orders_tree.heading(col, text=title)
            self.open_orders_tree.column(col, width=width, anchor=tk.W)
        self.open_orders_tree.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        history_card = ttk.Frame(orders_frame, style="Card.TFrame")
        history_card.grid(row=0, column=1, sticky=tk.NSEW, padx=(6, 0))
        ttk.Label(history_card, text="История ордеров (локальная БД)", style="Body.TLabel").pack(anchor=tk.W)
        self.order_history_tree = ttk.Treeview(
            history_card,
            columns=("time", "symbol", "side", "status", "price", "qty"),
            show="headings",
            height=5,
        )
        for col, title, width in [
            ("time", "Time", 130),
            ("symbol", "Symbol", 90),
            ("side", "Side", 60),
            ("status", "Status", 90),
            ("price", "Price", 90),
            ("qty", "Qty", 90),
        ]:
            self.order_history_tree.heading(col, text=title)
            self.order_history_tree.column(col, width=width, anchor=tk.W)
        self.order_history_tree.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        log_card = ttk.Frame(left, style="Card.TFrame", padding=10)
        log_card.pack(fill=tk.BOTH, expand=True)
        ttk.Label(log_card, text="Live Log", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 6))
        self.log_text = tk.Text(
            log_card,
            wrap=tk.WORD,
            height=24,
            bg="#FFFDF8",
            fg="#1E3C34",
            insertbackground="#1E3C34",
            relief=tk.FLAT,
            font=("Consolas", 10),
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.bind("<Control-c>", self._on_ctrl_c)
        self.log_text.bind("<Button-3>", self._show_log_context_menu)
        self.log_menu = tk.Menu(self.root, tearoff=0)
        self.log_menu.add_command(label="Copy Selected", command=self.copy_selected_log)
        self.log_menu.add_command(label="Copy All", command=self.copy_all_log)

        status_card = ttk.Frame(right, style="Card.TFrame", padding=10)
        status_card.pack(fill=tk.X)
        ttk.Label(status_card, text="Status", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 6))
        self.mode_label = ttk.Label(status_card, text="execution.mode: unknown", style="Body.TLabel")
        self.mode_label.pack(anchor=tk.W, pady=3)
        self.trading_row = ttk.Frame(status_card, style="Card.TFrame")
        self.trading_row.pack(fill=tk.X, pady=3)
        self.trading_led = tk.Canvas(self.trading_row, width=14, height=14, highlightthickness=0, bg="#FFFFFF")
        self.trading_led.pack(side=tk.LEFT, padx=(0, 6))
        self.trading_label = ttk.Label(self.trading_row, text="trading: stopped", style="Body.TLabel")
        self.trading_label.pack(side=tk.LEFT)
        self.ml_row = ttk.Frame(status_card, style="Card.TFrame")
        self.ml_row.pack(fill=tk.X, pady=3)
        self.ml_led = tk.Canvas(self.ml_row, width=14, height=14, highlightthickness=0, bg="#FFFFFF")
        self.ml_led.pack(side=tk.LEFT, padx=(0, 6))
        self.ml_label = ttk.Label(self.ml_row, text="ml: stopped", style="Body.TLabel")
        self.ml_label.pack(side=tk.LEFT)

        hint = ttk.Frame(right, style="Card.TFrame", padding=10)
        hint.pack(fill=tk.X, pady=8)
        ttk.Label(hint, text="Hint", style="Section.TLabel").pack(anchor=tk.W)
        ttk.Label(
            hint,
            text="For first local run use execution.mode=paper,\nthen run Preflight and Start Trading.",
            style="Body.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=6)

    def _build_settings_tab(self) -> None:
        settings_root = ttk.Frame(self.settings_tab, style="Root.TFrame")
        settings_root.pack(fill=tk.BOTH, expand=True, padx=2, pady=4)

        env_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        env_card.pack(fill=tk.X)
        ttk.Label(env_card, text=".env Secrets", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W)

        secret_fields = {"TELEGRAM_BOT_TOKEN", "BYBIT_API_KEY", "BYBIT_API_SECRET_KEY"}
        row = 1
        for key, var in self.env_vars.items():
            ttk.Label(env_card, text=key, style="Body.TLabel").grid(row=row, column=0, sticky=tk.W, pady=4)
            show = "*" if key in secret_fields else ""
            ttk.Entry(env_card, textvariable=var, width=100, show=show).grid(row=row, column=1, sticky=tk.EW, padx=8)
            row += 1
        env_card.columnconfigure(1, weight=1)

        cfg_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        cfg_card.pack(fill=tk.X, pady=8)
        ttk.Label(cfg_card, text="config.yaml Quick Settings", style="Section.TLabel").grid(row=0, column=0, columnspan=4, sticky=tk.W)

        ttk.Label(cfg_card, text="execution.mode", style="Body.TLabel").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Combobox(cfg_card, textvariable=self.cfg_execution_mode, values=["paper", "live"], state="readonly", width=14).grid(row=1, column=1, sticky=tk.W)

        ttk.Label(cfg_card, text="start_paused", style="Body.TLabel").grid(row=1, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Checkbutton(cfg_card, variable=self.cfg_start_paused).grid(row=1, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="bybit.host", style="Body.TLabel").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_bybit_host, width=28).grid(row=2, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="ws_public_host", style="Body.TLabel").grid(row=2, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(cfg_card, textvariable=self.cfg_ws_host, width=28).grid(row=2, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="symbols (comma)", style="Body.TLabel").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_symbols, width=28).grid(row=3, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="maker_only", style="Body.TLabel").grid(row=3, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Checkbutton(cfg_card, variable=self.cfg_maker_only).grid(row=3, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="target_profit", style="Body.TLabel").grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_target_profit, width=16).grid(row=4, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="safety_buffer", style="Body.TLabel").grid(row=4, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(cfg_card, textvariable=self.cfg_safety_buffer, width=16).grid(row=4, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="stop_loss_pct", style="Body.TLabel").grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_stop_loss, width=16).grid(row=5, column=1, sticky=tk.W)
        ttk.Label(cfg_card, text="take_profit_pct", style="Body.TLabel").grid(row=5, column=2, sticky=tk.W, padx=(18, 0))
        ttk.Entry(cfg_card, textvariable=self.cfg_take_profit, width=16).grid(row=5, column=3, sticky=tk.W)

        ttk.Label(cfg_card, text="hold_timeout_sec", style="Body.TLabel").grid(row=6, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg_card, textvariable=self.cfg_hold_timeout, width=16).grid(row=6, column=1, sticky=tk.W)

        btn_card = ttk.Frame(settings_root, style="Card.TFrame", padding=10)
        btn_card.pack(fill=tk.X)
        ttk.Button(btn_card, text="Reload From Files", command=self.load_settings).pack(side=tk.LEFT, padx=4)
        ttk.Label(
            btn_card,
            text="Auto-save is ON: changes in fields are written to .env/config.yaml automatically.",
            style="Body.TLabel",
        ).pack(side=tk.LEFT, padx=12)

    def _enqueue_log(self, text: str) -> None:
        self.log_queue.put(text)

    def _drain_logs(self) -> None:
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
        self.root.after(200, self._drain_logs)

    def _load_execution_mode(self) -> str:
        cfg_path = Path(self.config_var.get())
        if not cfg_path.exists():
            return "config not found"
        try:
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return "config parse error"
        mode = ((raw.get("execution") or {}).get("mode") or "live").strip().lower()
        return mode

    def _set_led(self, canvas: tk.Canvas, color: str) -> None:
        canvas.delete("all")
        canvas.create_oval(2, 2, 12, 12, fill=color, outline=color)

    def _status_text(self, proc: ManagedProcess) -> str:
        if proc.state == "running":
            return "RUNNING"
        if proc.state == "error":
            code = proc.last_exit_code if proc.last_exit_code is not None else "?"
            return f"ERROR (exit={code})"
        return "STOPPED"

    def _status_color(self, proc: ManagedProcess) -> str:
        if proc.state == "running":
            return "#28A745"  # green
        if proc.state == "error":
            return "#D93025"  # red
        return "#7A7A7A"  # gray

    def _update_status(self) -> None:
        mode = self._load_execution_mode()
        self.mode_label.config(text=f"execution.mode: {mode}")
        self.trading_label.config(text=f"trading: {self._status_text(self.trading)}")
        self.ml_label.config(text=f"ml: {self._status_text(self.ml)}")
        self._set_led(self.trading_led, self._status_color(self.trading))
        self._set_led(self.ml_led, self._status_color(self.ml))
        self.root.after(500, self._update_status)

    def _cmd(self, *parts: str) -> list[str]:
        return [self.python_var.get(), *parts]

    def _load_yaml(self) -> dict:
        cfg_path = Path(self.config_var.get())
        if not cfg_path.exists():
            return {}
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return {}
        return raw

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _fmt_num(value: Any, precision: int = 4) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "n/a"
        return f"{v:.{precision}f}"

    def _resolve_db_path(self, raw_cfg: dict[str, Any]) -> Path:
        rel = str((raw_cfg.get("storage") or {}).get("path") or "data/botik.db")
        path = Path(rel)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    def _schedule_runtime_refresh(self, initial_delay_ms: int = 7000) -> None:
        self.root.after(initial_delay_ms, self._runtime_refresh_tick)

    def _runtime_refresh_tick(self) -> None:
        self.refresh_runtime_snapshot()
        self._schedule_runtime_refresh(initial_delay_ms=7000)

    def refresh_runtime_snapshot(self) -> None:
        with self._runtime_refresh_lock:
            if self._runtime_refresh_inflight:
                return
            self._runtime_refresh_inflight = True
        threading.Thread(target=self._load_runtime_snapshot_worker, daemon=True).start()

    def _load_runtime_snapshot_worker(self) -> None:
        try:
            snapshot = self._load_runtime_snapshot()
            self.root.after(0, lambda s=snapshot: self._apply_runtime_snapshot(s))
        except Exception as exc:
            self._enqueue_log(f"[ui] runtime snapshot error: {exc}")
        finally:
            with self._runtime_refresh_lock:
                self._runtime_refresh_inflight = False

    def _load_runtime_snapshot(self) -> dict[str, Any]:
        raw_cfg = self._load_yaml()
        env_data = _read_env_map(ENV_PATH)
        mode = str(((raw_cfg.get("execution") or {}).get("mode") or "paper")).strip().lower()
        db_path = self._resolve_db_path(raw_cfg)

        snapshot: dict[str, Any] = {
            "balance_total": "n/a",
            "balance_available": "n/a",
            "balance_wallet": "n/a",
            "open_orders_count": 0,
            "open_orders_rows": [],
            "history_rows": self._read_local_order_history(db_path),
            "api_status": f"mode={mode}",
            "updated_at": datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
        }

        if mode != "live":
            local_open = self._read_local_open_orders(db_path)
            snapshot["open_orders_rows"] = local_open
            snapshot["open_orders_count"] = len(local_open)
            return snapshot

        api_key = env_data.get("BYBIT_API_KEY") or os.environ.get("BYBIT_API_KEY")
        api_secret = (
            env_data.get("BYBIT_API_SECRET_KEY")
            or env_data.get("BYBIT_API_SECRET")
            or os.environ.get("BYBIT_API_SECRET_KEY")
            or os.environ.get("BYBIT_API_SECRET")
        )
        rsa_key_path = env_data.get("BYBIT_RSA_PRIVATE_KEY_PATH") or os.environ.get("BYBIT_RSA_PRIVATE_KEY_PATH")
        host = str((raw_cfg.get("bybit") or {}).get("host") or "api-demo.bybit.com").strip()

        if not api_key:
            snapshot["api_status"] = "нет BYBIT_API_KEY"
            local_open = self._read_local_open_orders(db_path)
            snapshot["open_orders_rows"] = local_open
            snapshot["open_orders_count"] = len(local_open)
            return snapshot
        if not api_secret and not rsa_key_path:
            snapshot["api_status"] = "нет секрета API (HMAC/RSA)"
            local_open = self._read_local_open_orders(db_path)
            snapshot["open_orders_rows"] = local_open
            snapshot["open_orders_count"] = len(local_open)
            return snapshot

        live_data = asyncio.run(
            self._fetch_live_account_snapshot(
                host=host,
                api_key=api_key,
                api_secret=api_secret,
                rsa_key_path=rsa_key_path,
            )
        )
        snapshot.update(live_data)
        return snapshot

    async def _fetch_live_account_snapshot(
        self,
        host: str,
        api_key: str,
        api_secret: str | None,
        rsa_key_path: str | None,
    ) -> dict[str, Any]:
        from src.botik.execution.bybit_rest import BybitRestClient

        client = BybitRestClient(
            base_url=f"https://{host}",
            api_key=api_key,
            api_secret=api_secret,
            rsa_private_key_path=rsa_key_path,
        )

        wallet_resp, open_resp = await asyncio.gather(
            client.get_wallet_balance(account_type="UNIFIED"),
            client.get_open_orders(),
        )

        out: dict[str, Any] = {
            "api_status": f"host={host}",
            "open_orders_rows": [],
            "open_orders_count": 0,
        }

        if wallet_resp.get("retCode") != 0:
            out["api_status"] = f"wallet retCode={wallet_resp.get('retCode')}"
        else:
            wallet_item = ((wallet_resp.get("result") or {}).get("list") or [{}])[0]
            coins = wallet_item.get("coin") or []
            usdt = next((c for c in coins if str(c.get("coin", "")).upper() == "USDT"), None)
            total = wallet_item.get("totalEquity") or wallet_item.get("totalWalletBalance")
            available = wallet_item.get("totalAvailableBalance")
            wallet = usdt.get("walletBalance") if usdt else None
            out["balance_total"] = self._fmt_num(total, precision=4)
            out["balance_available"] = self._fmt_num(available, precision=4)
            out["balance_wallet"] = self._fmt_num(wallet if wallet is not None else total, precision=4)

        if open_resp.get("retCode") != 0:
            status = f"open_orders retCode={open_resp.get('retCode')}"
            if out.get("api_status"):
                out["api_status"] = f"{out['api_status']}; {status}"
            else:
                out["api_status"] = status
            return out

        open_list = (open_resp.get("result") or {}).get("list") or []
        rows: list[tuple[str, str, str, str, str]] = []
        for item in open_list[:80]:
            rows.append(
                (
                    str(item.get("symbol") or ""),
                    str(item.get("side") or ""),
                    str(item.get("price") or ""),
                    str(item.get("qty") or ""),
                    str(item.get("orderStatus") or ""),
                )
            )
        out["open_orders_rows"] = rows
        out["open_orders_count"] = len(open_list)
        return out

    def _read_local_order_history(self, db_path: Path, limit: int = 80) -> list[tuple[str, str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                """
                SELECT COALESCE(updated_at_utc, created_at_utc) AS ts, symbol, side, status, price, qty
                FROM orders
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
            return [(str(r[0] or ""), str(r[1] or ""), str(r[2] or ""), str(r[3] or ""), str(r[4] or ""), str(r[5] or "")) for r in rows]
        except sqlite3.Error as exc:
            self._enqueue_log(f"[ui] db read error: {exc}")
            return []
        finally:
            conn.close()

    def _read_local_open_orders(self, db_path: Path, limit: int = 80) -> list[tuple[str, str, str, str, str]]:
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                """
                SELECT symbol, side, price, qty, status
                FROM orders
                WHERE status IN ('New', 'PartiallyFilled')
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(limit, 1),),
            ).fetchall()
            return [(str(r[0] or ""), str(r[1] or ""), str(r[2] or ""), str(r[3] or ""), str(r[4] or "")) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _set_tree_rows(self, tree: ttk.Treeview, rows: list[tuple[Any, ...]]) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for row in rows:
            tree.insert("", tk.END, values=row)

    def _apply_runtime_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.balance_total_var.set(str(snapshot.get("balance_total", "n/a")))
        self.balance_available_var.set(str(snapshot.get("balance_available", "n/a")))
        self.balance_wallet_var.set(str(snapshot.get("balance_wallet", "n/a")))
        self.open_orders_var.set(str(snapshot.get("open_orders_count", 0)))
        self.api_status_var.set(str(snapshot.get("api_status", "n/a")))
        self.snapshot_time_var.set(str(snapshot.get("updated_at", "-")))
        self._set_tree_rows(self.open_orders_tree, list(snapshot.get("open_orders_rows") or []))
        self._set_tree_rows(self.order_history_tree, list(snapshot.get("history_rows") or []))

    def load_settings(self) -> None:
        self._suspend_autosave = True
        try:
            env_data = _read_env_map(ENV_PATH)
            for key, var in self.env_vars.items():
                var.set(env_data.get(key, ""))

            raw = self._load_yaml()
            self.cfg_execution_mode.set(str(((raw.get("execution") or {}).get("mode") or "paper")).lower())
            self.cfg_start_paused.set(bool(raw.get("start_paused", True)))
            self.cfg_bybit_host.set(str((raw.get("bybit") or {}).get("host") or "api-demo.bybit.com"))
            self.cfg_ws_host.set(str((raw.get("bybit") or {}).get("ws_public_host") or "stream.bybit.com"))
            symbols = raw.get("symbols") or ["BTCUSDT", "ETHUSDT"]
            self.cfg_symbols.set(",".join(str(s) for s in symbols))

            strategy = raw.get("strategy") or {}
            self.cfg_target_profit.set(str(strategy.get("target_profit", 0.0002)))
            self.cfg_safety_buffer.set(str(strategy.get("safety_buffer", 0.0001)))
            self.cfg_stop_loss.set(str(strategy.get("stop_loss_pct", 0.003)))
            self.cfg_take_profit.set(str(strategy.get("take_profit_pct", 0.005)))
            self.cfg_hold_timeout.set(str(strategy.get("position_hold_timeout_sec", 180)))
            self.cfg_maker_only.set(bool(strategy.get("maker_only", True)))
        finally:
            self._suspend_autosave = False
        self._enqueue_log("[settings] loaded from files")

    def save_env(self, show_popup: bool = True) -> bool:
        updates = {k: v.get().strip() for k, v in self.env_vars.items()}
        try:
            _upsert_env(ENV_PATH, updates)
        except Exception as exc:
            if show_popup:
                messagebox.showerror("Save failed", f".env save error:\n{exc}")
            return False
        self._enqueue_log(f"[settings] .env auto-saved: {ENV_PATH}")
        if show_popup:
            messagebox.showinfo("Saved", f".env updated:\n{ENV_PATH}")
        return True

    def save_config(self, show_popup: bool = True) -> bool:
        cfg_path = Path(self.config_var.get())
        raw = self._load_yaml()
        raw.setdefault("execution", {})
        raw.setdefault("bybit", {})
        raw.setdefault("strategy", {})

        try:
            raw["execution"]["mode"] = self.cfg_execution_mode.get().strip().lower()
            raw["start_paused"] = bool(self.cfg_start_paused.get())

            raw["bybit"]["host"] = self.cfg_bybit_host.get().strip()
            raw["bybit"]["ws_public_host"] = self.cfg_ws_host.get().strip()
            raw["symbols"] = [s.strip().upper() for s in self.cfg_symbols.get().split(",") if s.strip()]

            raw["strategy"]["target_profit"] = float(self.cfg_target_profit.get().strip())
            raw["strategy"]["safety_buffer"] = float(self.cfg_safety_buffer.get().strip())
            raw["strategy"]["stop_loss_pct"] = float(self.cfg_stop_loss.get().strip())
            raw["strategy"]["take_profit_pct"] = float(self.cfg_take_profit.get().strip())
            raw["strategy"]["position_hold_timeout_sec"] = int(self.cfg_hold_timeout.get().strip())
            raw["strategy"]["maker_only"] = bool(self.cfg_maker_only.get())
            cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
        except Exception as exc:
            if show_popup:
                messagebox.showerror("Save failed", f"config save error:\n{exc}")
            return False

        self._enqueue_log(f"[settings] config auto-saved: {cfg_path}")
        if show_popup:
            messagebox.showinfo("Saved", f"config.yaml updated:\n{cfg_path}")
        return True

    def save_all(self) -> None:
        try:
            self.save_env(show_popup=False)
            self.save_config(show_popup=False)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self._enqueue_log("[settings] save all completed")

    def start_trading(self) -> None:
        self._flush_autosave()
        mode = self._load_execution_mode()
        if mode == "live":
            if not messagebox.askyesno(
                "Live Mode Warning",
                "execution.mode=live. This can place real orders.\nContinue?",
            ):
                return
        cmd = self._cmd("-m", "src.botik.main", "--config", self.config_var.get())
        self.trading.start(cmd, ROOT_DIR)

    def stop_trading(self) -> None:
        self.trading.stop()

    def start_ml(self) -> None:
        self._flush_autosave()
        cmd = self._cmd("-m", "ml_service.run_loop", "--config", self.config_var.get())
        self.ml.start(cmd, ROOT_DIR)

    def stop_ml(self) -> None:
        self.ml.stop()

    def run_preflight(self) -> None:
        self._flush_autosave()
        cmd = self._cmd("tools/preflight.py", "--config", self.config_var.get(), "--timeout-sec", "15")
        threading.Thread(target=self._run_one_shot, args=(cmd,), daemon=True).start()

    def _run_one_shot(self, cmd: list[str]) -> None:
        self._enqueue_log(f"[preflight] started: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.stdout is not None:
            for line in proc.stdout:
                self._enqueue_log(f"[preflight] {line.rstrip()}")
        code = proc.wait()
        self._enqueue_log(f"[preflight] exited with code {code}")

    def _on_ctrl_c(self, _event: tk.Event) -> str:
        self.copy_selected_log()
        return "break"

    def _show_log_context_menu(self, event: tk.Event) -> None:
        try:
            self.log_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.log_menu.grab_release()

    def copy_selected_log(self) -> None:
        try:
            selected = self.log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(selected)
        self._enqueue_log("[ui] copied selected log text")

    def copy_all_log(self) -> None:
        full = self.log_text.get("1.0", tk.END).rstrip()
        if not full:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(full)
        self._enqueue_log("[ui] copied full log")

    def clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _on_close(self) -> None:
        self._flush_autosave()
        self.trading.stop()
        self.ml.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = BotikGui()
    app.run()


if __name__ == "__main__":
    main()
