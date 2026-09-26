
from __future__ import annotations

import csv
import io
import tkinter as tk
from tkinter import ttk
from typing import Any

_installed = False
_last_tree_column: str | None = None


def _safe_event_generate(widget: tk.Misc, event_name: str) -> None:
    try:
        widget.event_generate(event_name)
    except tk.TclError:
        pass


def _entry_select_all(widget: tk.Misc) -> None:
    try:
        widget.selection_range(0, tk.END)
        widget.icursor(tk.END)
    except tk.TclError:
        try:
            widget.tag_add("sel", "1.0", tk.END)
            widget.mark_set("insert", "1.0")
        except tk.TclError:
            pass


def _entry_delete(widget: tk.Misc) -> None:
    try:
        if str(widget.cget("state")) == "readonly":
            return
    except tk.TclError:
        pass
    try:
        widget.delete("sel.first", "sel.last")
    except tk.TclError:
        try:
            widget.delete("1.0", tk.END)
        except tk.TclError:
            pass


def _copy_widget_text(widget: tk.Misc) -> None:
    # First use native selection copying.
    try:
        _safe_event_generate(widget, "<<Copy>>")
        return
    except Exception:
        pass


def _paste_widget_text(widget: tk.Misc) -> None:
    try:
        if str(widget.cget("state")) == "readonly":
            return
    except tk.TclError:
        pass
    _safe_event_generate(widget, "<<Paste>>")


def _cut_widget_text(widget: tk.Misc) -> None:
    try:
        if str(widget.cget("state")) == "readonly":
            return
    except tk.TclError:
        pass
    _safe_event_generate(widget, "<<Cut>>")


def _show_text_menu(event: tk.Event) -> str:
    widget = event.widget
    menu = tk.Menu(widget, tearoff=False)
    menu.add_command(label="切り取り / Cut", command=lambda: _cut_widget_text(widget))
    menu.add_command(label="コピー / Copy", command=lambda: _copy_widget_text(widget))
    menu.add_command(label="貼り付け / Paste", command=lambda: _paste_widget_text(widget))
    menu.add_command(label="削除 / Delete", command=lambda: _entry_delete(widget))
    menu.add_separator()
    menu.add_command(label="すべて選択 / Select All", command=lambda: _entry_select_all(widget))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        try:
            menu.grab_release()
        except tk.TclError:
            pass
    return "break"


def _tree_values_as_tsv(tree: ttk.Treeview, item_ids: list[str]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    columns = list(tree["columns"])
    writer.writerow([tree.heading(col, "text") for col in columns])
    for item_id in item_ids:
        values = tree.item(item_id, "values")
        writer.writerow(list(values))
    return output.getvalue().rstrip("\n")


def _tree_copy_rows(tree: ttk.Treeview, item_ids: list[str] | None = None) -> None:
    ids = item_ids or list(tree.selection())
    if not ids:
        focused = tree.focus()
        ids = [focused] if focused else []
    if not ids:
        return
    text = _tree_values_as_tsv(tree, ids)
    tree.clipboard_clear()
    tree.clipboard_append(text)
    tree.update_idletasks()


def _tree_copy_all(tree: ttk.Treeview) -> None:
    _tree_copy_rows(tree, list(tree.get_children("")))


def _tree_copy_cell(tree: ttk.Treeview, item_id: str, column: str) -> None:
    if not item_id or not column:
        return
    try:
        if column == "#0":
            value = tree.item(item_id, "text")
        else:
            index = int(column[1:]) - 1
            values = tree.item(item_id, "values")
            value = values[index] if index < len(values) else ""
    except Exception:
        value = ""
    tree.clipboard_clear()
    tree.clipboard_append(str(value))
    tree.update_idletasks()


def _tree_right_click(event: tk.Event) -> str:
    global _last_tree_column
    tree: ttk.Treeview = event.widget
    row = tree.identify_row(event.y)
    column = tree.identify_column(event.x)
    _last_tree_column = column
    if row:
        if row not in tree.selection():
            tree.selection_set(row)
        tree.focus(row)

    menu = tk.Menu(tree, tearoff=False)
    menu.add_command(
        label="セルをコピー / Copy Cell",
        command=lambda: _tree_copy_cell(tree, row or tree.focus(), column),
    )
    menu.add_command(
        label="選択行をコピー / Copy Selected Rows",
        command=lambda: _tree_copy_rows(tree),
    )
    menu.add_command(
        label="表全体をコピー / Copy Entire Table",
        command=lambda: _tree_copy_all(tree),
    )
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        try:
            menu.grab_release()
        except tk.TclError:
            pass
    return "break"


def _tree_ctrl_c(event: tk.Event) -> str:
    tree: ttk.Treeview = event.widget
    _tree_copy_rows(tree)
    return "break"


def _double_click_select_all(event: tk.Event) -> str:
    _entry_select_all(event.widget)
    return "break"


def install_global_clipboard_support(root: tk.Misc) -> None:
    """Install Windows-style clipboard behavior for all current/future widgets."""
    global _installed
    if _installed:
        return
    _installed = True

    for class_name in ("Entry", "TEntry", "Text", "Spinbox", "TSpinbox"):
        root.bind_class(class_name, "<Button-3>", _show_text_menu, add="+")
        root.bind_class(class_name, "<Double-Button-1>", _double_click_select_all, add="+")
        root.bind_class(class_name, "<Control-a>", lambda e: (_entry_select_all(e.widget), "break")[1], add="+")
        root.bind_class(class_name, "<Control-A>", lambda e: (_entry_select_all(e.widget), "break")[1], add="+")

    root.bind_class("Treeview", "<Button-3>", _tree_right_click, add="+")
    root.bind_class("Treeview", "<Control-c>", _tree_ctrl_c, add="+")
    root.bind_class("Treeview", "<Control-C>", _tree_ctrl_c, add="+")
