from __future__ import annotations
import tkinter as tk
from tkinter import simpledialog


def bind_editable_remarks(tree, notes: dict, remark_column: str = "remark"):
    """Double-click the remark cell to edit it. Notes are keyed by the first column text."""
    def edit(event=None):
        row_id = tree.identify_row(event.y) if event is not None else (tree.selection()[0] if tree.selection() else "")
        col_id = tree.identify_column(event.x) if event is not None else ""
        if not row_id:
            return
        columns = list(tree["columns"])
        try:
            remark_index = columns.index(remark_column) + 1
        except ValueError:
            return
        if event is not None and col_id != f"#{remark_index}":
            return
        values = list(tree.item(row_id, "values"))
        if not values:
            return
        key = str(values[0])
        current = str(values[remark_index - 1]) if len(values) >= remark_index else notes.get(key, "")
        new_value = simpledialog.askstring("備考編集", f"{key} の備考", initialvalue=current, parent=tree.winfo_toplevel())
        if new_value is None:
            return
        notes[key] = new_value
        while len(values) < remark_index:
            values.append("")
        values[remark_index - 1] = new_value
        tree.item(row_id, values=values)
    tree.bind("<Double-1>", edit, add="+")
    tree.bind("<F2>", edit, add="+")
    return edit


def merge_note(notes: dict, key: str, default: str) -> str:
    return str(notes.get(str(key), default))
