"""Small reusable Tk UI builders for Botik GUI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def card(parent: tk.Widget, *, padding: int = 10, style: str = "Card.TFrame") -> ttk.Frame:
    return ttk.Frame(parent, style=style, padding=padding)


def section_header(parent: tk.Widget, text: str) -> ttk.Label:
    label = ttk.Label(parent, text=text, style="Section.TLabel")
    label.pack(anchor=tk.W)
    return label


def labeled_combobox(
    parent: tk.Widget,
    *,
    label: str,
    variable: tk.StringVar,
    values: list[str],
    width: int = 18,
) -> ttk.Combobox:
    wrap = ttk.Frame(parent, style="Card.TFrame")
    wrap.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(wrap, text=label, style="Body.TLabel").pack(anchor=tk.W)
    combo = ttk.Combobox(wrap, textvariable=variable, values=values, state="readonly", width=width)
    combo.pack(anchor=tk.W, pady=(3, 0))
    return combo


def labeled_entry(
    parent: tk.Widget,
    *,
    label: str,
    variable: tk.StringVar,
    width: int = 24,
) -> ttk.Entry:
    wrap = ttk.Frame(parent, style="Card.TFrame")
    wrap.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(wrap, text=label, style="Body.TLabel").pack(anchor=tk.W)
    entry = ttk.Entry(wrap, textvariable=variable, width=width)
    entry.pack(anchor=tk.W, pady=(3, 0))
    return entry
