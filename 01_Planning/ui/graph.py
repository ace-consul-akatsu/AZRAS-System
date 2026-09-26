from __future__ import annotations
import tkinter as tk
from tkinter import ttk

class AZRASGraphFrame(ttk.Frame):
    """Common graph container. Existing matplotlib figures can be mounted here."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)


class MultiSeriesBarChart(tk.Canvas):
    """Simple grouped bar chart drawn on a plain Tk Canvas (no matplotlib
    dependency), matching the style already used in
    regional_analysis/module10_ui.py. Each entry in `series` is
    (series_name, color_or_None, value); all entries share one Y axis and
    are drawn as a single row of bars (one bar per entry), grouped visually
    by category via `labels` beneath each bar.
    """

    DEFAULT_COLORS = ("#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
                       "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac")

    def draw(self, labels: list[str], values: list[float], y_title: str, title: str,
              colors: list[str] | None = None, value_format: str = "{:,.2f}"):
        self.delete("all")
        self.update_idletasks()
        width = max(self.winfo_width(), 760)
        height = max(self.winfo_height(), 440)
        left, right, top, bottom = 100, 35, 55, 110
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)
        self.create_text(width / 2, 22, text=title, font=("Yu Gothic UI", 13, "bold"))
        self.create_text(20, top + plot_h / 2, text=y_title, angle=90, font=("Yu Gothic UI", 9))
        if not labels or not values:
            self.create_text(width / 2, height / 2, text="No data")
            return
        vmax = max(max(values), 0.0)
        vmin = min(min(values), 0.0)
        span = (vmax - vmin) or 1.0
        for i in range(6):
            frac = i / 5
            value = vmin + span * frac
            y = top + plot_h - plot_h * frac
            self.create_line(left, y, width - right, y, fill="#dddddd")
            self.create_text(left - 8, y, text=value_format.format(value), anchor="e", font=("Yu Gothic UI", 8))
        zero_y = top + plot_h - ((0 - vmin) / span) * plot_h
        count = len(labels)
        slot = plot_w / max(count, 1)
        bar_w = min(80, slot * 0.6)
        palette = colors or [self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)] for i in range(count)]
        for i, (label, value, color) in enumerate(zip(labels, values, palette)):
            x = left + slot * (i + 0.5)
            y = top + plot_h - ((value - vmin) / span) * plot_h
            top_y, bottom_y = (y, zero_y) if value >= 0 else (zero_y, y)
            self.create_rectangle(x - bar_w / 2, top_y, x + bar_w / 2, bottom_y, fill=color, outline="#333333")
            self.create_text(x, y - 8 if value >= 0 else y + 8, text=value_format.format(value),
                              anchor="s" if value >= 0 else "n", font=("Yu Gothic UI", 8, "bold"))
            self.create_text(x, top + plot_h + 10, text=label, anchor="n",
                              width=max(80, int(slot - 4)), font=("Yu Gothic UI", 8))
        self.create_line(left, top, left, top + plot_h, width=1)
        self.create_line(left, zero_y, width - right, zero_y, width=1)
