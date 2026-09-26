from __future__ import annotations

import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .settings import UISettings


class AZRASTable(ttk.Frame):
    """Shared table with borders, sorting, multi-row copy and CSV export."""

    def __init__(
        self,
        master,
        columns,
        headings=None,
        widths=None,
        anchors=None,
        settings_key="table",
        height=12,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.settings_key = settings_key
        self.settings = UISettings()
        self.columns = tuple(columns)
        self._sort_reverse = {}
        self._selection_anchor = None
        self._details = {}

        style = ttk.Style(self)
        style.configure(
            "AZRAS.Treeview", rowheight=25, borderwidth=1, relief="solid"
        )
        style.configure(
            "AZRAS.Treeview.Heading",
            font=("TkDefaultFont", 9, "bold"),
            relief="raised",
            borderwidth=1,
        )
        style.map("AZRAS.Treeview", background=[("selected", "#cfe8ff")])

        # extended: Ctrl-click and Shift-click can select multiple rows.
        self.tree = ttk.Treeview(
            self,
            columns=self.columns,
            show="headings",
            height=height,
            style="AZRAS.Treeview",
            selectmode="extended",
        )
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(
            yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        headings = headings or {c: c for c in self.columns}
        widths = widths or {}
        anchors = anchors or {}
        saved = self.settings.get(f"columns.{settings_key}", {}) or {}
        for c in self.columns:
            self.tree.heading(
                c, text=headings.get(c, c), command=lambda col=c: self._sort(col)
            )
            self.tree.column(
                c,
                width=int(saved.get(c, widths.get(c, 140))),
                anchor=anchors.get(c, "w"),
                stretch=True,
            )

        self.tree.tag_configure("odd", background="#ffffff")
        self.tree.tag_configure("even", background="#f2f6fa")

        self.tree.bind("<Control-c>", self.copy_selection)
        self.tree.bind("<Control-C>", self.copy_selection)
        self.tree.bind("<Control-a>", self.select_all)
        self.tree.bind("<Control-A>", self.select_all)
        self.tree.bind("<Escape>", self.clear_selection)
        self.tree.bind("<Button-1>", self._excel_left_click, add="+")
        self.tree.bind("<Shift-Up>", lambda event: self._extend_by_keyboard(-1))
        self.tree.bind("<Shift-Down>", lambda event: self._extend_by_keyboard(1))
        self.tree.bind("<Shift-Home>", lambda event: self._extend_to_edge("first"))
        self.tree.bind("<Shift-End>", lambda event: self._extend_to_edge("last"))
        self.tree.bind("<<TreeviewSelect>>", self._remember_anchor, add="+")
        self.tree.bind("<Button-3>", self._popup)
        self.tree.bind("<Double-1>", self._show_detail_from_event)
        self.tree.bind("<ButtonRelease-1>", self._save_widths, add="+")

        self.menu = tk.Menu(self, tearoff=False)
        self.menu.add_command(label="選択行をコピー", command=self.copy_selection)
        self.menu.add_command(label="全行を選択", command=self.select_all)
        self.menu.add_separator()
        self.menu.add_command(label="CSV保存", command=self.export_csv)
        self.menu.add_separator()
        self.menu.add_command(label="詳細を表示", command=self.show_selected_detail)

        # Clicking elsewhere in the module clears the current table selection.
        # This keeps the highlight from remaining indefinitely after the user
        # moves to another input area.
        self.winfo_toplevel().bind(
            "<Button-1>", self._clear_when_click_outside, add="+"
        )

    # Treeview-compatible methods used by existing modules
    def insert(self, parent="", index="end", iid=None, **kw):
        tags = tuple(kw.pop("tags", ())) + (
            "even" if len(self.tree.get_children()) % 2 else "odd",
        )
        return self.tree.insert(parent, index, iid=iid, tags=tags, **kw)

    def delete(self, *items):
        return self.tree.delete(*items)

    def get_children(self, item=None):
        return self.tree.get_children(item)

    def heading(self, *a, **k):
        return self.tree.heading(*a, **k)

    def column(self, *a, **k):
        return self.tree.column(*a, **k)

    def pack(self, *a, **k):
        return super().pack(*a, **k)

    def grid(self, *a, **k):
        return super().grid(*a, **k)

    def _sort(self, col):
        rows = []
        for iid in self.tree.get_children(""):
            raw = self.tree.set(iid, col)
            try:
                key = float(str(raw).replace(",", ""))
            except Exception:
                key = str(raw).casefold()
            rows.append((key, iid))
        reverse = self._sort_reverse.get(col, False)
        rows.sort(key=lambda x: x[0], reverse=reverse)
        for n, (_, iid) in enumerate(rows):
            self.tree.move(iid, "", n)
            self.tree.item(iid, tags=("even" if n % 2 else "odd",))
        self._sort_reverse[col] = not reverse

    def _ordered_selection(self):
        selected = set(self.tree.selection())
        return [iid for iid in self.tree.get_children("") if iid in selected]

    def copy_selection(self, _event=None):
        """Copy selected rows as tab-separated text for direct paste into Excel."""
        items = self._ordered_selection()
        if not items:
            focus = self.tree.focus()
            if focus:
                items = [focus]
        if not items:
            return "break"
        text = "\n".join(
            "\t".join(map(str, self.tree.item(iid, "values"))) for iid in items
        )
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        return "break"

    def select_all(self, _event=None):
        rows = self.tree.get_children("")
        if rows:
            self.tree.selection_set(rows)
            self.tree.focus(rows[0])
            self._selection_anchor = rows[0]
        return "break"

    def clear_selection(self, _event=None):
        """Clear all selected rows and the active-row focus."""
        selected = self.tree.selection()
        if selected:
            self.tree.selection_remove(selected)
        self.tree.focus("")
        self._selection_anchor = None
        return "break"

    def _excel_left_click(self, event):
        """Provide an intuitive Excel-like way to cancel a row selection.

        * Clicking the blank part of the table clears the selection.
        * Clicking the only selected row once more clears it.
        * Ctrl/Shift clicks retain the normal extended-selection behaviour.
        """
        row = self.tree.identify_row(event.y)
        region = self.tree.identify_region(event.x, event.y)
        modifier_pressed = bool(event.state & 0x0005)  # Shift or Ctrl on Windows

        if not row and region in {"nothing", "cell", "tree"}:
            self.clear_selection()
            return "break"

        selected = self.tree.selection()
        if (
            row
            and not modifier_pressed
            and len(selected) == 1
            and selected[0] == row
        ):
            self.clear_selection()
            return "break"
        return None

    def _clear_when_click_outside(self, event):
        """Clear this table when another control in the module is clicked."""
        widget = event.widget
        current = widget
        while current is not None:
            if current == self.tree:
                return None
            try:
                current = current.master
            except (AttributeError, tk.TclError):
                break
        if self.tree.selection():
            self.after_idle(self.clear_selection)
        return None

    def _remember_anchor(self, _event=None):
        focus = self.tree.focus()
        selected = self.tree.selection()
        if focus and (not selected or len(selected) == 1):
            self._selection_anchor = focus

    def _extend_by_keyboard(self, step):
        rows = list(self.tree.get_children(""))
        if not rows:
            return "break"
        focus = self.tree.focus() or rows[0]
        try:
            index = rows.index(focus)
        except ValueError:
            index = 0
        if self._selection_anchor not in rows:
            self._selection_anchor = focus
        new_index = max(0, min(len(rows) - 1, index + step))
        target = rows[new_index]
        self._select_range(self._selection_anchor, target)
        self.tree.focus(target)
        self.tree.see(target)
        return "break"

    def _extend_to_edge(self, edge):
        rows = list(self.tree.get_children(""))
        if not rows:
            return "break"
        focus = self.tree.focus() or rows[0]
        if self._selection_anchor not in rows:
            self._selection_anchor = focus
        target = rows[0] if edge == "first" else rows[-1]
        self._select_range(self._selection_anchor, target)
        self.tree.focus(target)
        self.tree.see(target)
        return "break"

    def _select_range(self, start_iid, end_iid):
        rows = list(self.tree.get_children(""))
        try:
            start = rows.index(start_iid)
            end = rows.index(end_iid)
        except ValueError:
            return
        lo, hi = sorted((start, end))
        self.tree.selection_set(rows[lo : hi + 1])

    def set_detail(self, iid, title, text):
        self._details[str(iid)] = (str(title), str(text))

    def show_selected_detail(self):
        iid = self.tree.focus()
        if not iid:
            selected = self.tree.selection()
            iid = selected[0] if selected else None
        if not iid:
            return
        detail = self._details.get(str(iid))
        if detail:
            messagebox.showinfo(detail[0], detail[1], parent=self)

    def _show_detail_from_event(self, event):
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if row and col == f"#{len(self.columns)}":
            self.tree.focus(row)
            self.tree.selection_set(row)
            self.show_selected_detail()
            return "break"

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([self.tree.heading(c, "text") for c in self.columns])
            for iid in self.tree.get_children(""):
                writer.writerow(self.tree.item(iid, "values"))

    def _popup(self, event):
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
            self.tree.focus(row)
            self._selection_anchor = row
        self.menu.tk_popup(event.x_root, event.y_root)

    def _save_widths(self, _event=None):
        self.settings.set(
            f"columns.{self.settings_key}",
            {c: self.tree.column(c, "width") for c in self.columns},
        )
