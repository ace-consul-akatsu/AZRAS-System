from __future__ import annotations

import csv
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

_INSTALLED = False
_ORIGINAL_TREEVIEW = ttk.Treeview


def _safe_number(value: Any):
    text = str(value).strip().replace(",", "")
    try:
        return (0, float(text))
    except (TypeError, ValueError):
        return (1, text.casefold())


class PlatformTreeview(_ORIGINAL_TREEVIEW):
    """Treeview with common AZRAS Platform table behaviour.

    This class keeps the normal ttk.Treeview API so existing modules do not
    need to be rewritten.  It adds common styling, extended selection,
    Excel-compatible copy, Esc clearing, sorting, zebra rows, CSV export and
    persistent column widths for every module table.
    """

    _counter = 0

    def __init__(self, master=None, **kw):
        PlatformTreeview._counter += 1
        self._azras_id = PlatformTreeview._counter
        self._azras_sort_reverse: dict[str, bool] = {}
        self._azras_selection_anchor: str | None = None
        self._azras_heading_commands: dict[str, Any] = {}

        kw.setdefault("selectmode", "extended")
        kw.setdefault("style", "AZRAS.Platform.Treeview")
        super().__init__(master, **kw)

        self._configure_common_style()
        self.tag_configure("azras_odd", background="#ffffff")
        self.tag_configure("azras_even", background="#f2f6fa")

        self.bind("<Control-c>", self._copy_selection, add="+")
        self.bind("<Control-C>", self._copy_selection, add="+")
        self.bind("<Control-a>", self._select_all, add="+")
        self.bind("<Control-A>", self._select_all, add="+")
        self.bind("<Escape>", self._clear_selection, add="+")
        self.bind("<Shift-Up>", lambda e: self._extend_keyboard(-1), add="+")
        self.bind("<Shift-Down>", lambda e: self._extend_keyboard(1), add="+")
        self.bind("<Shift-Home>", lambda e: self._extend_edge(first=True), add="+")
        self.bind("<Shift-End>", lambda e: self._extend_edge(first=False), add="+")
        self.bind("<<TreeviewSelect>>", self._remember_anchor, add="+")
        self.bind("<Button-3>", self._show_context_menu, add="+")
        self.bind("<ButtonRelease-1>", self._save_column_widths, add="+")
        self.after_idle(self._restore_column_widths)

        self._menu = tk.Menu(self, tearoff=False)
        self._menu.add_command(label="選択行をコピー", command=self._copy_selection)
        self._menu.add_command(label="全行を選択", command=self._select_all)
        self._menu.add_command(label="選択解除", command=self._clear_selection)
        self._menu.add_separator()
        self._menu.add_command(label="CSV保存", command=self._export_csv)

    def _configure_common_style(self):
        style = ttk.Style(self)
        style.configure(
            "AZRAS.Platform.Treeview",
            rowheight=25,
            borderwidth=1,
            relief="solid",
            background="#ffffff",
            fieldbackground="#ffffff",
        )
        style.configure(
            "AZRAS.Platform.Treeview.Heading",
            font=("TkDefaultFont", 9, "bold"),
            relief="raised",
            borderwidth=1,
            padding=(5, 4),
        )
        style.map(
            "AZRAS.Platform.Treeview",
            background=[("selected", "#cfe8ff")],
            foreground=[("selected", "#000000")],
        )

    def insert(self, parent, index, iid=None, **kw):
        tags = list(kw.pop("tags", ()))
        # Add alternating row shading without removing module-specific tags.
        row_no = len(self.get_children(parent))
        tags.append("azras_even" if row_no % 2 else "azras_odd")
        return super().insert(parent, index, iid=iid, tags=tuple(tags), **kw)

    def heading(self, column, option=None, **kw):
        # Existing explicit commands always take priority. Otherwise add sort.
        if "command" in kw and kw["command"]:
            self._azras_heading_commands[str(column)] = kw["command"]
        elif option is None and "text" in kw and "command" not in kw:
            kw["command"] = lambda c=str(column): self._sort_column(c)
        return super().heading(column, option, **kw)

    def _sort_column(self, column: str):
        rows = []
        for iid in self.get_children(""):
            rows.append((_safe_number(self.set(iid, column)), iid))
        reverse = self._azras_sort_reverse.get(column, False)
        rows.sort(key=lambda pair: pair[0], reverse=reverse)
        for n, (_, iid) in enumerate(rows):
            self.move(iid, "", n)
            current = [t for t in self.item(iid, "tags") if t not in {"azras_odd", "azras_even"}]
            current.append("azras_even" if n % 2 else "azras_odd")
            self.item(iid, tags=tuple(current))
        self._azras_sort_reverse[column] = not reverse

    def _ordered_selection(self):
        selected = set(self.selection())
        return [iid for iid in self.get_children("") if iid in selected]

    def _copy_selection(self, _event=None):
        items = self._ordered_selection()
        if not items and self.focus():
            items = [self.focus()]
        if not items:
            return "break"
        lines = ["\t".join(map(str, self.item(iid, "values"))) for iid in items]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.update_idletasks()
        return "break"

    def _select_all(self, _event=None):
        rows = self.get_children("")
        if rows:
            self.selection_set(rows)
            self.focus(rows[0])
            self._azras_selection_anchor = rows[0]
        return "break"

    def _clear_selection(self, _event=None):
        selected = self.selection()
        if selected:
            self.selection_remove(selected)
        self.focus("")
        self._azras_selection_anchor = None
        return "break"

    def _remember_anchor(self, _event=None):
        focus = self.focus()
        if focus and len(self.selection()) <= 1:
            self._azras_selection_anchor = focus

    def _extend_keyboard(self, step: int):
        rows = list(self.get_children(""))
        if not rows:
            return "break"
        focus = self.focus() if self.focus() in rows else rows[0]
        if self._azras_selection_anchor not in rows:
            self._azras_selection_anchor = focus
        idx = max(0, min(len(rows) - 1, rows.index(focus) + step))
        target = rows[idx]
        self._select_range(self._azras_selection_anchor, target)
        self.focus(target)
        self.see(target)
        return "break"

    def _extend_edge(self, first: bool):
        rows = list(self.get_children(""))
        if not rows:
            return "break"
        focus = self.focus() if self.focus() in rows else rows[0]
        if self._azras_selection_anchor not in rows:
            self._azras_selection_anchor = focus
        target = rows[0] if first else rows[-1]
        self._select_range(self._azras_selection_anchor, target)
        self.focus(target)
        self.see(target)
        return "break"

    def _select_range(self, start: str, end: str):
        rows = list(self.get_children(""))
        try:
            a, b = rows.index(start), rows.index(end)
        except ValueError:
            return
        lo, hi = sorted((a, b))
        self.selection_set(rows[lo : hi + 1])

    def _show_context_menu(self, event):
        row = self.identify_row(event.y)
        if row and row not in self.selection():
            self.selection_set(row)
            self.focus(row)
            self._azras_selection_anchor = row
        self._menu.tk_popup(event.x_root, event.y_root)

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        columns = self.cget("columns")
        with open(path, "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow([self.heading(c, "text") for c in columns])
            for iid in self.get_children(""):
                writer.writerow(self.item(iid, "values"))

    def _settings_key(self) -> str:
        # Stable enough across launches without requiring module rewrites.
        top = self.winfo_toplevel()
        title = ""
        try:
            title = top.title()
        except Exception:
            pass
        cols = "_".join(map(str, self.cget("columns")))
        return f"{title}|{cols}".replace("/", "_").replace("\\", "_")

    def _settings_file(self):
        from pathlib import Path
        return Path.home() / ".azras_platform" / "table_widths.tsv"

    def _restore_column_widths(self):
        try:
            path = self._settings_file()
            if not path.exists():
                return
            key = self._settings_key()
            for line in path.read_text(encoding="utf-8").splitlines():
                saved_key, col, width = line.split("\t", 2)
                if saved_key == key and col in self.cget("columns"):
                    self.column(col, width=int(width))
        except Exception:
            return

    def _save_column_widths(self, _event=None):
        try:
            path = self._settings_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            key = self._settings_key()
            current = {}
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    parts = line.split("\t", 2)
                    if len(parts) == 3 and parts[0] != key:
                        current[(parts[0], parts[1])] = parts[2]
            for col in self.cget("columns"):
                current[(key, str(col))] = str(self.column(col, "width"))
            text = "\n".join(f"{k}\t{c}\t{w}" for (k, c), w in current.items())
            path.write_text(text + ("\n" if text else ""), encoding="utf-8")
        except Exception:
            return


def install_global_treeview() -> None:
    """Install common table behaviour for Module 0–10 and comparison screens."""
    global _INSTALLED
    if _INSTALLED:
        return
    ttk.Treeview = PlatformTreeview
    _INSTALLED = True
