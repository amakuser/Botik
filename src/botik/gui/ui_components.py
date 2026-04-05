"""Small reusable Tk UI builders for Botik GUI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from src.botik.gui.theme import DARK_PALETTE as _P


# ──────────────────────────────────────────────────────────────────────────────
#  CARD  –  tk.Frame with a 1-px colored border via highlightthickness
# ──────────────────────────────────────────────────────────────────────────────

def hcard(
    parent: tk.Widget,
    *,
    padding: int = 16,
    bg: str | None = None,
    border: str | None = None,
    accent_top: bool = False,
    radius: int = 10,
) -> tuple[tk.Canvas, tk.Frame]:
    """
    Rounded card using Canvas.
    Returns (canvas, body) — grid/pack canvas, put your widgets into body.
    """
    bg_c  = bg     or _P["card"]
    brd_c = border or _P["card_border"]

    canvas = tk.Canvas(parent, bg=_P["bg"], bd=0, highlightthickness=0)

    # accent stripe (if needed) — drawn as Canvas rectangle at top
    top_stripe = 3 if accent_top else 0

    # Outer fill frame sits inside canvas window (inset 1px for border)
    fill = tk.Frame(canvas, bg=bg_c)
    win  = canvas.create_window(1, 1, anchor=tk.NW, window=fill)

    # Accent top bar
    if accent_top:
        tk.Frame(fill, bg=_P["accent"], height=top_stripe).pack(fill=tk.X)

    # Body with padding — callers put widgets here
    body = tk.Frame(fill, bg=bg_c, padx=padding, pady=padding)
    body.pack(fill=tk.BOTH, expand=True)

    def _resize(e: tk.Event) -> None:
        w, h = e.width, e.height
        _draw_rrect(canvas, 0, 0, w, h, radius, bg_c, brd_c)
        canvas.itemconfig(win, width=w - 2, height=h - 2)

    canvas.bind("<Configure>", _resize)
    return canvas, body


def hcard_alt(
    parent: tk.Widget,
    *,
    padding: int = 16,
    accent_top: bool = False,
    radius: int = 8,
) -> tuple[tk.Canvas, tk.Frame]:
    """Darker variant of hcard (uses card_alt bg)."""
    return hcard(parent, padding=padding, bg=_P["card_alt"], border=_P["line_soft"],
                 accent_top=accent_top, radius=radius)


# ──────────────────────────────────────────────────────────────────────────────
#  Legacy shim — keeps old callers working
# ──────────────────────────────────────────────────────────────────────────────

def card(parent: tk.Widget, *, padding: int = 10, style: str = "Card.TFrame") -> ttk.Frame:
    return ttk.Frame(parent, style=style, padding=padding)


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION HEADER with inline gradient line
# ──────────────────────────────────────────────────────────────────────────────

def section_header(
    parent: tk.Widget,
    text: str,
    *,
    subtitle: str = "",
    bg: str | None = None,
) -> tk.Frame:
    """
    Section header with a dim right-extending line after the text.
    Returns a tk.Frame container row.
    """
    bg_c = bg or _P["card"]
    row = tk.Frame(parent, bg=bg_c)
    row.pack(fill=tk.X, pady=(0, 10))

    lbl = tk.Label(
        row, text=text.upper(),
        bg=bg_c, fg=_P["text_soft"],
        font=("Segoe UI", 9, "bold"),
    )
    lbl.pack(side=tk.LEFT)

    # Separator line
    sep = tk.Frame(row, bg=_P["line_soft"], height=1)
    sep.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0), pady=6)

    if subtitle:
        tk.Label(parent, text=subtitle, bg=bg_c, fg=_P["text_dim"],
                 font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 4))
    return row


# ──────────────────────────────────────────────────────────────────────────────
#  SEPARATOR
# ──────────────────────────────────────────────────────────────────────────────

def separator(parent: tk.Widget, *, pady: int = 6) -> tk.Frame:
    """Thin horizontal separator line."""
    s = tk.Frame(parent, bg=_P["line"], height=1)
    s.pack(fill=tk.X, pady=pady)
    return s


# ──────────────────────────────────────────────────────────────────────────────
#  STATUS DOT
# ──────────────────────────────────────────────────────────────────────────────

def status_dot(parent: tk.Widget, *, state: str = "ok", size: int = 9) -> tk.Canvas:
    """
    A small colored circle indicator.
    state: "ok" | "warn" | "error" | "idle" | "info"
    """
    color_map = {
        "ok":    _P["success"],
        "warn":  _P["warning"],
        "error": _P["danger"],
        "idle":  _P["text_dim"],
        "info":  _P["info"],
    }
    dot_color = color_map.get(state, _P["text_dim"])
    try:
        bg_c = str(parent.cget("background"))
    except Exception:
        bg_c = _P["card_alt"]

    c = tk.Canvas(parent, width=size + 2, height=size + 2,
                  background=bg_c, bd=0, highlightthickness=0)
    c.create_oval(1, 1, size + 1, size + 1, fill=dot_color, outline="")
    return c


# ──────────────────────────────────────────────────────────────────────────────
#  METRIC CARD  (self-contained)
# ──────────────────────────────────────────────────────────────────────────────

def metric_card(
    parent: tk.Widget,
    *,
    title: str,
    value_var: tk.StringVar,
    value_style: str = "MetricValue.TLabel",
    subtitle: str = "",
    subtitle_var: tk.StringVar | None = None,
    padding: int = 14,
) -> ttk.Frame:
    """Legacy metric card using ttk.Frame — kept for compat."""
    frame = ttk.Frame(parent, style="CardAlt.TFrame", padding=padding)
    ttk.Label(frame, text=title, style="SectionAlt.TLabel").pack(anchor=tk.W)
    ttk.Label(frame, textvariable=value_var, style=value_style,
              justify=tk.LEFT).pack(anchor=tk.W, pady=(8, 0))
    if subtitle_var is not None:
        ttk.Label(frame, textvariable=subtitle_var,
                  style="MonoAlt.TLabel").pack(anchor=tk.W, pady=(4, 0))
    elif subtitle:
        ttk.Label(frame, text=subtitle,
                  style="Meta.TLabel").pack(anchor=tk.W, pady=(4, 0))
    return frame


# ──────────────────────────────────────────────────────────────────────────────
#  METRIC CARD (native tk — used in new home tab)
# ──────────────────────────────────────────────────────────────────────────────

def metric_tile(
    parent: tk.Widget,
    *,
    title: str,
    value_var: tk.StringVar,
    value_fg: str | None = None,
    icon: str = "",
    bg: str | None = None,
    radius: int = 10,
) -> tk.Canvas:
    """
    Rounded metric tile using Canvas.
    Returns the Canvas (pack/grid it yourself).
    """
    bg_c   = bg or _P["card"]
    brd_c  = _P["card_border"]
    val_fg = value_fg or _P["text"]

    canvas = tk.Canvas(parent, bg=_P["bg"], bd=0, highlightthickness=0)

    def _draw(event: tk.Event | None = None) -> None:
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 4 or h < 4:
            return
        canvas.delete("bg")
        # Draw rounded rect fill
        _draw_rrect(canvas, 0, 0, w, h, radius, bg_c, brd_c)

    canvas.bind("<Configure>", lambda e: (_draw(e), _place_inner(e)))

    inner = tk.Frame(canvas, bg=bg_c, padx=14, pady=12)
    win = canvas.create_window(2, 2, anchor=tk.NW, window=inner)

    def _place_inner(e: tk.Event) -> None:
        canvas.itemconfig(win, width=e.width - 4, height=e.height - 4)

    # Icon top-right (inside inner)
    if icon:
        tk.Label(inner, text=icon, bg=bg_c, fg=_P["text_dim"],
                 font=("Segoe UI", 16)).place(relx=1.0, rely=0.0, anchor=tk.NE)

    tk.Label(inner, text=title.upper(), bg=bg_c, fg=_P["text_dim"],
             font=("Segoe UI", 8, "bold"), anchor=tk.W).pack(anchor=tk.W)

    tk.Label(inner, textvariable=value_var, bg=bg_c, fg=val_fg,
             font=("Consolas", 13, "bold"), anchor=tk.W, justify=tk.LEFT,
             wraplength=200).pack(anchor=tk.W, pady=(5, 0))

    return canvas


def _draw_rrect(
    canvas: tk.Canvas, x0: int, y0: int, x1: int, y1: int,
    r: int, fill: str, outline: str,
) -> None:
    """Draw a filled rounded rectangle on canvas."""
    canvas.delete("bg")
    if x1 - x0 < r * 2 or y1 - y0 < r * 2:
        canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=1, tags="bg")
        return
    canvas.create_polygon(
        x0+r, y0,   x1-r, y0,   x1, y0+r,   x1, y1-r,
        x1-r, y1,   x0+r, y1,   x0, y1-r,   x0, y0+r,
        fill=fill, outline=outline, width=1, smooth=True, tags="bg",
    )


# ──────────────────────────────────────────────────────────────────────────────
#  ROUNDED CARD (Canvas-based — kept for opt-in use)
# ──────────────────────────────────────────────────────────────────────────────

def rounded_card(
    parent: tk.Widget,
    *,
    radius: int = 10,
    bg: str | None = None,
    border_color: str | None = None,
    padding: int = 12,
) -> tuple[tk.Canvas, tk.Frame]:
    """
    Card with rounded corners drawn on Canvas.
    Returns (canvas, inner_frame) — pack/grid canvas, put children into inner_frame.
    """
    card_bg = bg or _P["card"]
    border  = border_color or _P["card_border"]

    canvas = tk.Canvas(parent, background=_P["bg"], bd=0, highlightthickness=0)
    canvas.bind(
        "<Configure>",
        lambda e: _redraw_rounded(canvas, e.width, e.height, radius, card_bg, border),
    )

    inner = tk.Frame(canvas, background=card_bg)
    win   = canvas.create_window(padding, padding, anchor=tk.NW, window=inner)

    def _on_resize(e: tk.Event) -> None:
        _redraw_rounded(canvas, e.width, e.height, radius, card_bg, border)
        canvas.itemconfig(win, width=e.width - padding * 2)

    canvas.bind("<Configure>", _on_resize)
    return canvas, inner


def _redraw_rounded(canvas: tk.Canvas, w: int, h: int, r: int, fill: str, outline: str) -> None:
    canvas.delete("rcard")
    if w < r * 2 or h < r * 2:
        canvas.create_rectangle(0, 0, w, h, fill=fill, outline=outline, width=1, tags="rcard")
        return
    canvas.create_polygon(
        r, 0,  w - r, 0,  w, r,  w, h - r,  w - r, h,  r, h,  0, h - r,  0, r,
        fill=fill, outline=outline, width=1, smooth=True, tags="rcard",
    )


# ──────────────────────────────────────────────────────────────────────────────
#  FORM HELPERS
# ──────────────────────────────────────────────────────────────────────────────

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
    combo = ttk.Combobox(wrap, textvariable=variable, values=values,
                         state="readonly", width=width)
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
