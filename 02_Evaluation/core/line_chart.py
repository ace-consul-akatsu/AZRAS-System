"""Self-contained Tkinter Canvas line-chart widget.

Ported verbatim (structure/behavior unchanged) from 03_Compare's main.py
LineChart class, so that 02_Evaluation can draw the same style of graph
for a single building without depending on the Compare product (which
requires 2+ regions to run at all).

No external dependency beyond tkinter + math, matching the source.
"""
from __future__ import annotations
import math
import tkinter as tk


class LineChart(tk.Canvas):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg='white', highlightthickness=1, highlightbackground='#bbb', **kw)
        self.title = ''
        self.ylabel = ''
        self.labels = []
        self.series = []
        self.tick_every = None
        self.empty_message = '計算済みデータがありません'
        self.zero_line = False
        self.zero_line_label = '±0（投資回収基準）'
        self._hover_points = []
        self.bind('<Configure>', lambda e: self.redraw())
        self.bind('<Motion>', self._on_motion)
        self.bind('<Leave>', lambda e: self.delete('tooltip'))

    def set_data(self, title, ylabel, labels, series, tick_every=None,
                 empty_message='計算済みデータがありません', zero_line=False,
                 zero_line_label='±0（投資回収基準）'):
        self.title = title
        self.ylabel = ylabel
        self.labels = labels
        self.series = series
        self.tick_every = tick_every
        self.empty_message = empty_message
        self.zero_line = zero_line
        self.zero_line_label = zero_line_label
        self.redraw()

    def _on_motion(self, event):
        self.delete('tooltip')
        if not self._hover_points:
            return
        nearest = None
        best = 10.0 ** 9
        for px, py, name, xlabel, value in self._hover_points:
            d = (event.x - px) ** 2 + (event.y - py) ** 2
            if d < best:
                best = d
                nearest = (px, py, name, xlabel, value)
        if nearest is None or best > 12 ** 2:
            return
        px, py, name, xlabel, value = nearest
        if isinstance(value, (int, float)):
            value_text = f'{value:,.3f}' if abs(value) < 100 else f'{value:,.1f}'
        else:
            value_text = str(value)
        text = f'{name}\n{xlabel}：{value_text} {self.ylabel}'
        tid = self.create_text(px + 12, py - 12, text=text, anchor='sw', justify='left',
                                font=('Yu Gothic UI', 9), fill='black', tags='tooltip')
        box = self.bbox(tid)
        if box:
            pad = 5
            rect = self.create_rectangle(box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad,
                                          fill='#fffde7', outline='#777', tags='tooltip')
            self.tag_lower(rect, tid)
        self.tag_raise('tooltip')

    def redraw(self):
        self.delete('all')
        self._hover_points = []
        w = max(self.winfo_width(), 360)
        h = max(self.winfo_height(), 220)
        L, R, T, B = 78, 22, 46, 42
        self.create_text(w / 2, 20, text=self.title, font=('Yu Gothic UI', 12, 'bold'))
        vals = [v for _, pts in self.series for _, v in pts if isinstance(v, (int, float))]
        if not vals:
            self.create_text(w / 2, h / 2, text=self.empty_message, font=('Yu Gothic UI', 11), justify='center')
            return
        ymin = min(0, min(vals))
        ymax = max(vals)
        ymax = ymax if ymax > ymin else ymin + 1
        for i in range(5):
            y = T + (h - T - B) * i / 4
            val = ymax - (ymax - ymin) * i / 4
            self.create_line(L, y, w - R, y, fill='#ddd')
            self.create_text(L - 7, y, text=f'{val:,.0f}', anchor='e', font=('Yu Gothic UI', 8))
        self.create_line(L, T, L, h - B)
        self.create_line(L, h - B, w - R, h - B)
        self.create_text(18, h - B + 27, text=self.ylabel, font=('Yu Gothic UI', 10, 'bold'), anchor='w')
        colors = ['#1565c0', '#d32f2f', '#2e7d32', '#6a1b9a', '#ef6c00', '#00838f', '#5d4037']
        n = max((len(x) for _, x in self.series), default=1)

        def xy(i, v):
            return L + (w - L - R) * (i / max(n - 1, 1)), T + (h - T - B) * (ymax - v) / (ymax - ymin)

        if self.zero_line and ymin <= 0 <= ymax:
            zy = xy(0, 0)[1]
            self.create_line(L, zy, w - R, zy, fill='#333', width=2, dash=(6, 4))
            self.create_text(L + 6, zy - 6, text=self.zero_line_label, anchor='sw',
                              font=('Yu Gothic UI', 9, 'bold'), fill='#333')
        for si, (name, pts) in enumerate(self.series):
            coords = []
            for i, v in pts:
                coords.extend(xy(i, v))
            if len(coords) >= 4:
                self.create_line(*coords, fill=colors[si % len(colors)], width=2.2)
            for i, v in pts:
                x, y = xy(i, v)
                self.create_oval(x - 2.2, y - 2.2, x + 2.2, y + 2.2, fill=colors[si % len(colors)], outline='')
                xlabel = self.labels[i] if isinstance(i, int) and 0 <= i < len(self.labels) else i
                self._hover_points.append((x, y, name, xlabel, v))
            x0 = L + si * 155
            self.create_line(x0, T - 14, x0 + 20, T - 14, fill=colors[si % len(colors)], width=3)
            self.create_text(x0 + 25, T - 14, text=name, anchor='w', font=('Yu Gothic UI', 8))
        if self.tick_every:
            indices = [i for i, lab in enumerate(self.labels) if isinstance(lab, (int, float)) and int(lab) % self.tick_every == 0]
            if 0 not in indices:
                indices = [0] + indices
            if n - 1 not in indices:
                indices.append(n - 1)
        else:
            step = max(1, math.ceil(n / 12))
            indices = list(range(0, n, step))
            if n - 1 not in indices:
                indices.append(n - 1)
        for i in sorted(set(indices)):
            x, _ = xy(i, ymin)
            lab = self.labels[i] if i < len(self.labels) else str(i)
            self.create_text(x, h - B + 15, text=str(lab), font=('Yu Gothic UI', 8))
