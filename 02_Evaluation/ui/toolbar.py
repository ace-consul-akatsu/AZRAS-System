from __future__ import annotations
from tkinter import ttk

class AZRASToolbar(ttk.Frame):
    def add_button(self, text, command, primary=False, side="left"):
        style="Primary.TButton" if primary else "TButton"
        button=ttk.Button(self,text=text,command=command,style=style)
        button.pack(side=side,padx=3,pady=2)
        return button
