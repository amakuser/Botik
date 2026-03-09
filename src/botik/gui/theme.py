"""Shared desktop theme for Botik Tk GUI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


DARK_PALETTE: dict[str, str] = {
    "bg": "#0B1424",
    "bg_soft": "#111D33",
    "card": "#16263F",
    "card_alt": "#1A2C47",
    "line": "#2A4063",
    "text": "#E8F0FF",
    "text_soft": "#9EB4D8",
    "accent": "#3B82F6",
    "accent_hover": "#5A9AFF",
    "success": "#27AE60",
    "danger": "#D64545",
    "warning": "#D9A441",
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
    style.configure("Card.TFrame", background=colors["card"], relief="flat")
    style.configure("CardAlt.TFrame", background=colors["card_alt"], relief="flat")

    style.configure(
        "Title.TLabel",
        background=colors["bg"],
        foreground=colors["text"],
        font=("Segoe UI", 22, "bold"),
    )
    style.configure(
        "Subtitle.TLabel",
        background=colors["bg"],
        foreground=colors["text_soft"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "Section.TLabel",
        background=colors["card"],
        foreground=colors["text"],
        font=("Segoe UI", 12, "bold"),
    )
    style.configure(
        "Body.TLabel",
        background=colors["card"],
        foreground=colors["text_soft"],
        font=("Segoe UI", 10),
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
        padding=(16, 8),
        font=("Segoe UI", 10, "bold"),
        borderwidth=1,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors["accent"]), ("active", colors["card_alt"])],
        foreground=[("selected", colors["text"]), ("active", colors["text"])],
    )

    style.configure(
        "TButton",
        padding=(10, 5),
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
        padding=(12, 8),
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
        padding=(12, 8),
    )
    style.map(
        "Stop.TButton",
        background=[("active", "#E85D5D"), ("pressed", "#B73737")],
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
        rowheight=24,
    )
    style.configure(
        "Treeview.Heading",
        background=colors["card_alt"],
        foreground=colors["text"],
        relief="flat",
        font=("Segoe UI", 10, "bold"),
    )
    style.map("Treeview.Heading", background=[("active", colors["accent"])])
    style.configure("Vertical.TScrollbar", background=colors["bg_soft"], bordercolor=colors["line"])
    style.configure("Horizontal.TScrollbar", background=colors["bg_soft"], bordercolor=colors["line"])
    return colors
