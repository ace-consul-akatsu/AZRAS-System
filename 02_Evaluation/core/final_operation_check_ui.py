from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.final_operation_check import (
    export_checks_csv, run_project_check, summarize_checks,
)
from core.i18n import I18N


class FinalOperationCheckWindow(tk.Toplevel):
    def __init__(self, master, root_dir: Path, project_context=None,
                 language: str = "ja"):
        super().__init__(master)
        self.root_dir = Path(root_dir)
        self.project_context = project_context
        self.i18n = I18N(self.root_dir, language)
        self.checks = []
        self.title(self.i18n.t("final_check.title"))
        self.geometry("1450x850")
        self.build()
        self.after(200, self.run_check)

    def build(self):
        t = self.i18n.t
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text=t("final_check.project_json")).pack(
            side="left", padx=4)
        self.path_var = tk.StringVar(
            value=self.project_context.display_path
            if self.project_context is not None else "")
        ttk.Entry(top, textvariable=self.path_var, width=115).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(top, text=t("final_check.open_json"),
                   command=self.choose_json).pack(side="left", padx=4)
        ttk.Button(top, text=t("final_check.rerun"),
                   command=self.run_check).pack(side="left", padx=4)
        ttk.Button(top, text=t("final_check.export_csv"),
                   command=self.save_csv).pack(side="left", padx=4)

        self.summary_var = tk.StringVar(value=t("final_check.waiting"))
        ttk.Label(self, textvariable=self.summary_var,
                  font=("Yu Gothic UI", 13, "bold")).pack(
                      fill="x", padx=14, pady=(2, 8))

        columns = ("section", "item", "status", "detail")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        headings = {
            "section": t("final_check.category"),
            "item": t("final_check.check_item"),
            "status": t("final_check.result"),
            "detail": t("final_check.details"),
        }
        widths = {"section": 180, "item": 300,
                  "status": 100, "detail": 800}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")
        self.tree.tag_configure("OK", foreground="#006400")
        self.tree.tag_configure("WARNING", foreground="#b36b00")
        self.tree.tag_configure("ERROR", foreground="#b00020")

        y_scroll = ttk.Scrollbar(
            self, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(
            self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(
            yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.pack(fill="both", expand=True, padx=(10, 25),
                       pady=(0, 25))
        y_scroll.place(relx=1.0, rely=0.105, relheight=0.84, anchor="ne")
        x_scroll.pack(fill="x", padx=10, side="bottom")

        ttk.Label(self, text=t("final_check.notice"),
                  foreground="#555555", wraplength=1400).pack(
                      fill="x", padx=12, pady=5)

    def choose_json(self):
        path = filedialog.askopenfilename(
            filetypes=[("Project JSON", "*.json")], parent=self)
        if path:
            self.path_var.set(path)
            self.run_check()

    def run_check(self):
        t = self.i18n.t
        path = self.path_var.get().strip()
        if not path:
            self.summary_var.set(t("final_check.load_first"))
            return
        self.checks = run_project_check(
            path, self.root_dir, self.i18n.language)
        for row in self.tree.get_children():
            self.tree.delete(row)
        for check in self.checks:
            self.tree.insert(
                "", "end",
                values=(check.section, check.item,
                        check.status, check.detail),
                tags=(check.status,))
        summary = summarize_checks(self.checks)
        self.summary_var.set(
            f"{t('final_check.summary')}  "
            f"OK: {summary['OK']}  "
            f"WARNING: {summary['WARNING']}  "
            f"ERROR: {summary['ERROR']}")
        if summary["ERROR"] == 0:
            messagebox.showinfo(
                t("final_check.dialog_title"),
                t("final_check.no_critical_error"), parent=self)

    def save_csv(self):
        t = self.i18n.t
        if not self.checks:
            self.run_check()
        if not self.checks:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=t("final_check.csv_filename"),
            filetypes=[("CSV", "*.csv")], parent=self)
        if path:
            export_checks_csv(
                self.checks, path, self.i18n.language)
            messagebox.showinfo(
                t("final_check.saved_title"),
                t("final_check.saved_message"), parent=self)
