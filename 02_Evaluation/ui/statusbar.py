from __future__ import annotations
import tkinter as tk
from tkinter import ttk

class AZRASStatusBar(ttk.Frame):
    def __init__(self, master, text="", **kwargs):
        super().__init__(master, **kwargs)
        self.text=tk.StringVar(value=text)
        ttk.Label(self,textvariable=self.text,anchor="w").pack(fill="x",padx=6,pady=2)
    def set(self,text): self.text.set(text)
