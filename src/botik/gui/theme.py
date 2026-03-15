"""Shared desktop theme for the Botik Dashboard Shell."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


DARK_PALETTE: dict[str, str] = {
    "bg": "#0D1626",
    "bg_soft": "#131F32",
    "card": "#17253A",
    "card_alt": "#1D2C44",
    "line": "#2A3D59",
    "line_soft": "#22324B",
    "text": "#F3F7FF",
    "text_soft": "#A7B7D0",
    "text_dim": "#7F90AB",
    "accent": "#4B8EFF",
    "accent_hover": "#69A3FF",
    "accent_soft": "#203A63",
    "success": "#33C476",
    "danger": "#EE5E5E",
    "warning": "#E0B14A",
    "info": "#6EC3FF",
    "log_bg": "#0F1A2B",
    "log_fg": "#D8E8FF",
}


def apply_dark_theme(root: tk.Tk) -> dict[str, str]:
    """Configure ttk styles and return active color palette."""
    colors = dict(DARK_PALETTE)
    root.configure(bg=colors["bg"])

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=colors["bg"], foreground=colors["text"])
    style.configure("Root.TFrame", background=colors["bg"])
    style.configure("Card.TFrame", background=colors["card"], relief="flat", borderwidth=0)
    style.configure("CardAlt.TFrame", background=colors["card_alt"], relief="flat", borderwidth=0)
    style.configure("Hero.TFrame", background=colors["card_alt"], relief="flat", borderwidth=0)

    style.configure(
        "Title.TLabel",
        background=colors["bg"],
        foreground=colors["text"],
        font=("Segoe UI Semibold", 24, "bold"),
    )
    style.configure(
        "Subtitle.TLabel",
        background=colors["bg"],
        foreground=colors["text_soft"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "HeroTitle.TLabel",
        background=colors["card_alt"],
        foreground=colors["text"],
        font=("Segoe UI Semibold", 18, "bold"),
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
        foreground=colors["text"],
        font=("Segoe UI Semibold", 13, "bold"),
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
        foreground=colors["text"],
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
        font=("Segoe UI Semibold", 16, "bold"),
    )

    style.configure(
        "TNotebook",
        background=colors["bg"],
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=colors["bg_soft"],
        foreground=colors["text_soft"],
        padding=(18, 10),
        font=("Segoe UI Semibold", 10, "bold"),
        borderwidth=1,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors["accent"]), ("active", colors["card_alt"])],
        foreground=[("selected", colors["text"]), ("active", colors["text"])],
    )

    style.configure(
        "TButton",
        padding=(12, 7),
        font=("Segoe UI", 10),
        background=colors["bg_soft"],
        foreground=colors["text"],
        bordercolor=colors["line"],
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", colors["card_alt"]), ("pressed", colors["card"])],
        foreground=[("disabled", "#7087AD")],
    )

    style.configure(
        "Accent.TButton",
        font=("Segoe UI", 10, "bold"),
        background=colors["accent"],
        foreground="#FFFFFF",
    )
    style.map(
        "Accent.TButton",
        background=[("active", colors["accent_hover"]), ("pressed", colors["accent"])],
    )

    style.configure(
        "Start.TButton",
        font=("Segoe UI", 11, "bold"),
        background=colors["success"],
        foreground="#FFFFFF",
        padding=(14, 9),
    )
    style.map(
        "Start.TButton",
        background=[("active", "#35BF73"), ("pressed", "#1F8F4E")],
    )

    style.configure(
        "Stop.TButton",
        font=("Segoe UI", 11, "bold"),
        background=colors["danger"],
        foreground="#FFFFFF",
        padding=(14, 9),
    )
    style.map(
        "Stop.TButton",
        background=[("active", "#E85D5D"), ("pressed", "#B73737")],
    )
    style.configure(
        "Secondary.TButton",
        font=("Segoe UI", 10),
        background=colors["card_alt"],
        foreground=colors["text"],
        padding=(11, 7),
    )
    style.map(
        "Secondary.TButton",
        background=[("active", colors["accent_soft"]), ("pressed", colors["bg_soft"])],
    )
    style.configure(
        "DangerSecondary.TButton",
        font=("Segoe UI", 10, "bold"),
        background="#4A2024",
        foreground="#FFD8D8",
        padding=(11, 7),
    )
    style.map(
        "DangerSecondary.TButton",
        background=[("active", "#64282E"), ("pressed", "#3E171B")],
    )

    style.configure(
        "TEntry",
        fieldbackground=colors["bg_soft"],
        foreground=colors["text"],
        bordercolor=colors["line"],
        insertcolor=colors["text"],
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
    )
    style.configure(
        "Treeview",
        background=colors["bg_soft"],
        fieldbackground=colors["bg_soft"],
        foreground=colors["text"],
        bordercolor=colors["line"],
        rowheight=28,
    )
    style.configure(
        "Treeview.Heading",
        background=colors["card_alt"],
        foreground=colors["text"],
        relief="flat",
        font=("Segoe UI Semibold", 10, "bold"),
    )
    style.map("Treeview.Heading", background=[("active", colors["accent"])])
    style.map(
        "Treeview",
        background=[("selected", colors["accent_soft"])],
        foreground=[("selected", colors["text"])],
    )
    style.configure(
        "Vertical.TScrollbar",
        background=colors["bg_soft"],
        troughcolor=colors["card"],
        bordercolor=colors["line"],
        arrowcolor=colors["text_soft"],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=colors["bg_soft"],
        troughcolor=colors["card"],
        bordercolor=colors["line"],
        arrowcolor=colors["text_soft"],
    )
    return colors
