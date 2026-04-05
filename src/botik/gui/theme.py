"""Shared desktop theme for the Botik Dashboard Shell."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


DARK_PALETTE: dict[str, str] = {
    # Backgrounds
    "bg": "#03070F",
    "bg_soft": "#060D1C",
    "bg_mid": "#0A1628",
    # Cards
    "card": "#0C1630",
    "card_alt": "#111F3A",
    "card_border": "#1A2E50",
    # Lines / separators
    "line": "#1A2E50",
    "line_soft": "#142340",
    # Text
    "text": "#E8F0FF",
    "text_soft": "#8FA8D0",
    "text_dim": "#4A6080",
    # Accent (blue)
    "accent": "#3D8BFF",
    "accent_hover": "#5FA3FF",
    "accent_soft": "#0F2248",
    # Status colors
    "success": "#00E599",
    "success_soft": "#002E20",
    "danger": "#FF4D6A",
    "danger_soft": "#2E0A12",
    "warning": "#FFB830",
    "warning_soft": "#2E1F00",
    "info": "#00D4C8",
    "info_soft": "#00222E",
    # Logs
    "log_bg": "#030811",
    "log_fg": "#D8E8FF",
}


def apply_dark_theme(root: tk.Tk) -> dict[str, str]:
    """Configure ttk styles and return active color palette."""
    colors = dict(DARK_PALETTE)
    root.configure(bg=colors["bg"])

    style = ttk.Style(root)
    style.theme_use("clam")

    # ── Base ──────────────────────────────────────────────────────
    style.configure(".", background=colors["bg"], foreground=colors["text"])
    style.configure("Root.TFrame", background=colors["bg"])
    style.configure(
        "Card.TFrame",
        background=colors["card"],
        relief="solid",
        borderwidth=1,
        lightcolor=colors["card_border"],
        darkcolor=colors["card_border"],
        bordercolor=colors["card_border"],
    )
    style.configure(
        "CardAlt.TFrame",
        background=colors["card_alt"],
        relief="solid",
        borderwidth=1,
        lightcolor=colors["line_soft"],
        darkcolor=colors["line_soft"],
        bordercolor=colors["line_soft"],
    )
    style.configure(
        "Hero.TFrame",
        background=colors["card_alt"],
        relief="solid",
        borderwidth=1,
        lightcolor=colors["accent_soft"],
        darkcolor=colors["accent_soft"],
        bordercolor=colors["accent_soft"],
    )

    # ── Labels ────────────────────────────────────────────────────
    style.configure(
        "Title.TLabel",
        background=colors["bg"],
        foreground=colors["text"],
        font=("Segoe UI Semibold", 22, "bold"),
    )
    style.configure(
        "Subtitle.TLabel",
        background=colors["bg"],
        foreground=colors["text_dim"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "HeroTitle.TLabel",
        background=colors["card_alt"],
        foreground=colors["text"],
        font=("Segoe UI Semibold", 16, "bold"),
    )
    style.configure(
        "HeroBody.TLabel",
        background=colors["card_alt"],
        foreground=colors["text_soft"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "Section.TLabel",
        background=colors["card"],
        foreground=colors["text_soft"],
        font=("Segoe UI Semibold", 11, "bold"),
    )
    style.configure(
        "Body.TLabel",
        background=colors["card"],
        foreground=colors["text_soft"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "Meta.TLabel",
        background=colors["card"],
        foreground=colors["text_dim"],
        font=("Segoe UI", 9),
    )
    style.configure(
        "Muted.TLabel",
        background=colors["card"],
        foreground=colors["text_dim"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "SectionAlt.TLabel",
        background=colors["card_alt"],
        foreground=colors["text_soft"],
        font=("Segoe UI Semibold", 11, "bold"),
    )
    style.configure(
        "BodyAlt.TLabel",
        background=colors["card_alt"],
        foreground=colors["text_soft"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "MetricValue.TLabel",
        background=colors["card_alt"],
        foreground=colors["text"],
        font=("Courier New", 15, "bold"),
    )

    # ── Metric value colors ───────────────────────────────────────
    style.configure(
        "MetricPositive.TLabel",
        background=colors["card_alt"],
        foreground=colors["success"],
        font=("Courier New", 15, "bold"),
    )
    style.configure(
        "MetricNegative.TLabel",
        background=colors["card_alt"],
        foreground=colors["danger"],
        font=("Courier New", 15, "bold"),
    )
    style.configure(
        "MetricAccent.TLabel",
        background=colors["card_alt"],
        foreground=colors["accent"],
        font=("Courier New", 15, "bold"),
    )
    style.configure(
        "MetricInfo.TLabel",
        background=colors["card_alt"],
        foreground=colors["info"],
        font=("Courier New", 15, "bold"),
    )

    # ── Mono labels (for numbers / logs) ─────────────────────────
    style.configure(
        "Mono.TLabel",
        background=colors["card"],
        foreground=colors["text_soft"],
        font=("Courier New", 10),
    )
    style.configure(
        "MonoAlt.TLabel",
        background=colors["card_alt"],
        foreground=colors["text_soft"],
        font=("Courier New", 10),
    )

    # ── Status labels ─────────────────────────────────────────────
    style.configure(
        "StatusOk.TLabel",
        background=colors["card_alt"],
        foreground=colors["success"],
        font=("Segoe UI", 10, "bold"),
    )
    style.configure(
        "StatusWarn.TLabel",
        background=colors["card_alt"],
        foreground=colors["warning"],
        font=("Segoe UI", 10, "bold"),
    )
    style.configure(
        "StatusError.TLabel",
        background=colors["card_alt"],
        foreground=colors["danger"],
        font=("Segoe UI", 10, "bold"),
    )

    # ── Notebook ──────────────────────────────────────────────────
    style.configure(
        "TNotebook",
        background=colors["bg"],
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=colors["bg_soft"],
        foreground=colors["text_dim"],
        padding=(18, 10),
        font=("Segoe UI Semibold", 10, "bold"),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors["card_alt"]), ("active", colors["card"])],
        foreground=[("selected", colors["accent"]), ("active", colors["text_soft"])],
    )

    # ── Buttons ───────────────────────────────────────────────────
    style.configure(
        "TButton",
        padding=(12, 7),
        font=("Segoe UI", 10),
        background=colors["card"],
        foreground=colors["text_soft"],
        bordercolor=colors["line"],
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", colors["card_alt"]), ("pressed", colors["bg_mid"])],
        foreground=[("active", colors["text"]), ("disabled", colors["text_dim"])],
    )

    style.configure(
        "Accent.TButton",
        font=("Segoe UI", 10, "bold"),
        background=colors["accent"],
        foreground="#FFFFFF",
        bordercolor=colors["accent"],
        padding=(12, 7),
    )
    style.map(
        "Accent.TButton",
        background=[("active", colors["accent_hover"]), ("pressed", "#2B6FDD")],
        foreground=[("disabled", colors["text_dim"])],
    )

    style.configure(
        "Start.TButton",
        font=("Segoe UI", 11, "bold"),
        background=colors["success"],
        foreground="#000E0A",
        bordercolor=colors["success"],
        padding=(14, 9),
    )
    style.map(
        "Start.TButton",
        background=[("active", "#00FFB2"), ("pressed", "#00A870")],
    )

    style.configure(
        "Stop.TButton",
        font=("Segoe UI", 11, "bold"),
        background=colors["danger"],
        foreground="#FFFFFF",
        bordercolor=colors["danger"],
        padding=(14, 9),
    )
    style.map(
        "Stop.TButton",
        background=[("active", "#FF6B82"), ("pressed", "#CC2040")],
    )

    style.configure(
        "Secondary.TButton",
        font=("Segoe UI", 10),
        background=colors["card_alt"],
        foreground=colors["text_soft"],
        bordercolor=colors["line"],
        padding=(11, 7),
    )
    style.map(
        "Secondary.TButton",
        background=[("active", colors["accent_soft"]), ("pressed", colors["card"])],
        foreground=[("active", colors["text"])],
    )

    style.configure(
        "DangerSecondary.TButton",
        font=("Segoe UI", 10, "bold"),
        background=colors["danger_soft"],
        foreground="#FFD8D8",
        bordercolor="#4A2030",
        padding=(11, 7),
    )
    style.map(
        "DangerSecondary.TButton",
        background=[("active", "#3E0F1A"), ("pressed", "#2A080F")],
    )

    # ── Entry / Combobox ──────────────────────────────────────────
    style.configure(
        "TEntry",
        fieldbackground=colors["bg_soft"],
        foreground=colors["text"],
        bordercolor=colors["line"],
        insertcolor=colors["text"],
        padding=(6, 4),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", colors["accent"])],
    )

    style.configure(
        "TCheckbutton",
        background=colors["card"],
        foreground=colors["text_soft"],
        font=("Segoe UI", 10),
    )
    style.map(
        "TCheckbutton",
        background=[("active", colors["card_alt"])],
        foreground=[("active", colors["text"])],
    )

    style.configure(
        "TCombobox",
        fieldbackground=colors["bg_soft"],
        foreground=colors["text"],
        bordercolor=colors["line"],
        insertcolor=colors["text"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", colors["bg_soft"])],
        selectbackground=[("readonly", colors["bg_soft"])],
        selectforeground=[("readonly", colors["text"])],
        bordercolor=[("focus", colors["accent"])],
    )

    # ── Treeview ──────────────────────────────────────────────────
    style.configure(
        "Treeview",
        background=colors["bg_soft"],
        fieldbackground=colors["bg_soft"],
        foreground=colors["text_soft"],
        bordercolor=colors["line"],
        rowheight=30,
        font=("Segoe UI", 10),
    )
    style.configure(
        "Treeview.Heading",
        background=colors["card_alt"],
        foreground=colors["text_dim"],
        relief="flat",
        font=("Segoe UI Semibold", 10, "bold"),
        padding=(8, 6),
    )
    style.map("Treeview.Heading", background=[("active", colors["accent_soft"])])
    style.map(
        "Treeview",
        background=[("selected", colors["accent_soft"])],
        foreground=[("selected", colors["accent"])],
    )

    # ── Progressbar ───────────────────────────────────────────────
    style.configure(
        "TProgressbar",
        troughcolor=colors["card_alt"],
        background=colors["accent"],
        bordercolor=colors["line"],
        lightcolor=colors["accent_hover"],
        darkcolor=colors["accent"],
        thickness=6,
    )
    style.configure(
        "Success.TProgressbar",
        troughcolor=colors["card_alt"],
        background=colors["success"],
        bordercolor=colors["line"],
        lightcolor=colors["success"],
        darkcolor=colors["success"],
        thickness=6,
    )

    # ── Scrollbars ────────────────────────────────────────────────
    style.configure(
        "Vertical.TScrollbar",
        background=colors["card"],
        troughcolor=colors["bg_soft"],
        bordercolor=colors["bg_soft"],
        arrowcolor=colors["text_dim"],
        width=8,
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=colors["card"],
        troughcolor=colors["bg_soft"],
        bordercolor=colors["bg_soft"],
        arrowcolor=colors["text_dim"],
        width=8,
    )

    return colors
