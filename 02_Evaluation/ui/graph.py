from __future__ import annotations
from tkinter import ttk

class AZRASGraphFrame(ttk.Frame):
    """Common graph container. Existing matplotlib figures can be mounted here."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
