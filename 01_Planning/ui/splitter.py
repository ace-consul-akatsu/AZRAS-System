from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from .settings import UISettings

class AZRASSplitter(ttk.Panedwindow):
    """Reusable vertical/horizontal splitter with remembered sash position."""
    def __init__(self, master, key: str, orient=tk.VERTICAL, initial=520, minimum=45, **kwargs):
        super().__init__(master, orient=orient, **kwargs)
        self.key = key
        self.initial = initial
        self.minimum = minimum
        self.settings = UISettings()
        self._restored = False
        self.bind("<Configure>", self._restore_once, add="+")
        self.bind("<ButtonRelease-1>", self._remember, add="+")

    def add_panes(self, upper, lower):
        self.add(upper, weight=0)
        self.add(lower, weight=1)
        self.after_idle(self._restore_once)

    def _restore_once(self, _event=None):
        if self._restored or len(self.panes()) < 2:
            return
        self._restored = True
        pos = int(self.settings.get(f"splitter.{self.key}", self.initial))
        try:
            total = self.winfo_height() if str(self.cget("orient")) == str(tk.VERTICAL) else self.winfo_width()
            pos = max(self.minimum, min(pos, max(self.minimum, total - self.minimum)))
            self.sashpos(0, pos)
        except tk.TclError:
            pass

    def _remember(self, _event=None):
        if len(self.panes()) < 2:
            return
        try:
            self.settings.set(f"splitter.{self.key}", int(self.sashpos(0)))
        except tk.TclError:
            pass
