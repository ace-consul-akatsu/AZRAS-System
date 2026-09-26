
from __future__ import annotations

import os
from pathlib import Path
from types import MethodType
from tkinter import filedialog, messagebox, ttk

from core.module_report import generate_module_report


def attach_module_report_button(window, module_no: int) -> None:
    """Attach the common report action to modules that do not define it natively.

    Modules 0 and 8 already provide their own method.  Modules 1-7 and 9 place
    a print button in ``build()`` but rely on this helper to supply the method.
    """
    if callable(getattr(window, "print_module_report", None)):
        return

    def _print_module_report(self):
        _create_module_report(self, module_no)

    window.print_module_report = MethodType(_print_module_report, window)


def _create_module_report(window, module_no: int) -> None:
    project = getattr(window, "project", None)
    if not isinstance(project, dict):
        messagebox.showwarning(
            "Warning",
            "Module 0でProject JSONを読み込むか保存してください。"
            if getattr(window.i18n, "language", "ja") == "ja"
            else "Load or save a Project JSON in Module 0.",
            parent=window,
        )
        return

    path = (
        getattr(window, "project_path", None)
        or getattr(window, "path", None)
        or getattr(getattr(window, "project_context", None), "path", None)
    )
    source = Path(path) if path else None
    project_name = project.get("common", {}).get("project_name") or "AZRAS_Project"
    default_name = f"{project_name}_Module{module_no}_Report.pdf"
    initial_dir = str(source.parent) if source else None

    output = filedialog.asksaveasfilename(
        parent=window,
        title="Module印刷PDFの保存先"
        if getattr(window.i18n, "language", "ja") == "ja"
        else "Save Module PDF",
        initialdir=initial_dir,
        initialfile=default_name,
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf")],
    )
    if not output:
        return

    try:
        result = generate_module_report(
            project,
            module_no,
            output,
            source,
            getattr(window.i18n, "language", "ja"),
        )
        open_now = messagebox.askyesno(
            "Completed",
            "Moduleの印刷用PDFを作成しました。開きますか？"
            if getattr(window.i18n, "language", "ja") == "ja"
            else "The module PDF was created. Open it?",
            parent=window,
        )
        if open_now:
            os.startfile(str(result))
    except Exception as exc:
        messagebox.showerror(
            "Error",
            (
                "Module印刷用PDFの作成に失敗しました。\n"
                f"{type(exc).__name__}: {exc}"
            ),
            parent=window,
        )
