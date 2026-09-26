from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.branding import (
    COMPANY_EN,
    COMPANY_JA,
    COPYRIGHT,
    DISPLAY_NAME,
    LICENSE_BILINGUAL,
)
from core.error_text import friendly_exception_text
from core.clipboard import install_global_clipboard_support
from core.i18n import I18N, LANGUAGE_OPTIONS
from core.project_context import ProjectContext
from core.project_store import load_project
from core.ui_style import FONT_FAMILY, apply_common_style
from module3.app import Module3App
from module4.app import Module4App
from module6.app import Module6App
from module7.app import Module7App
from core.evaluation_pipeline import ensure_internal_200_year_support


class AZRASEvaluationApp(tk.Tk):
    """Standalone Evaluation product: lifecycle scenario, 200-year environment, lifecycle cost, and business."""

    def __init__(self) -> None:
        super().__init__()
        self.i18n = I18N(ROOT, "en")
        self._ui_language = "en"
        self.project_context = ProjectContext()
        apply_common_style(self)
        install_global_clipboard_support(self)

        self.title(f"{DISPLAY_NAME} — {COMPANY_EN}")
        self.geometry("1040x760")
        self.minsize(900, 650)
        self._build_menu()
        self._build_ui()

    def _txt(self, ja: str, en: str) -> str:
        return ja if self.i18n.language == "ja" else en

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label=self._txt("Project JSONを開く", "Open Project JSON"), command=self.open_project)
        file_menu.add_separator()
        file_menu.add_command(label=self._txt("終了", "Exit"), command=self.destroy)
        menu_bar.add_cascade(label=self._txt("ファイル", "File"), menu=file_menu)

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label=self._txt("このソフトについて", "About"), command=self.show_about)
        help_menu.add_command(label=self._txt("ライセンス・免責事項", "License / Disclaimer"), command=self.show_license)
        menu_bar.add_cascade(label=self._txt("ヘルプ", "Help"), menu=help_menu)
        self.config(menu=menu_bar)

    def _build_ui(self) -> None:
        if hasattr(self, "_outer") and self._outer.winfo_exists():
            self._outer.destroy()
        outer = ttk.Frame(self, padding=(30, 22))
        self._outer = outer
        outer.pack(fill="both", expand=True)

        langbar = ttk.Frame(outer)
        langbar.pack(fill="x", pady=(0, 4))
        ttk.Label(langbar, text=self._txt("言語", "Language")).pack(side="right", padx=(8, 0))
        self._language_var = tk.StringVar(value="日本語" if self.i18n.language == "ja" else "English")
        cb = ttk.Combobox(langbar, textvariable=self._language_var, values=LANGUAGE_OPTIONS, state="readonly", width=12)
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", lambda _e: self.change_language("ja" if cb.current()==1 else "en"))

        ttk.Label(outer, text=DISPLAY_NAME, font=(FONT_FAMILY, 24, "bold"), anchor="center").pack(fill="x")
        ttk.Label(outer, text=self._txt("200年環境・修繕更新シナリオ・改修費・200年事業をProject JSONから評価", "Evaluate 200-year environment, lifecycle scenario, repair/renewal cost, and 200-year business from a Project JSON"), font=(FONT_FAMILY, 12), anchor="center").pack(fill="x", pady=(3, 4))
        ttk.Label(outer, text=f"Developed by {COMPANY_EN} / {COMPANY_JA}", foreground="#555555", anchor="center").pack(fill="x", pady=(0, 16))

        project = ttk.LabelFrame(outer, text=self._txt("評価対象Project JSON", "Evaluation Project JSON"), padding=(12, 10))
        project.pack(fill="x", pady=(0, 16))
        ttk.Button(project, text=self._txt("Project JSONを開く", "Open Project JSON"), command=self.open_project).pack(side="left")
        current_path = str(self.project_context.path) if self.project_context.path else self._txt("未選択：Planningで作成・保存したProject JSONを開いてください。", "Not selected: open a Project JSON created and saved in Planning.")
        self.project_label = ttk.Label(project, text=current_path, wraplength=650)
        self.project_label.pack(side="left", padx=14, fill="x", expand=True)

        grid = ttk.Frame(outer); grid.pack(fill="both", expand=True)
        entries = [
            (self._txt("200年環境", "200-year Environment"), Module4App, "environment", 0, 0),
            (self._txt("修繕・更新・解体シナリオ", "Repair / Renewal / Demolition Scenario"), Module3App, "renewal_scenario", 0, 1),
            (self._txt("改修・更新・解体費", "Repair / Renewal / Demolition Cost"), Module7App, "renewal_cost", 1, 0),
            (self._txt("200年事業", "200-year Business"), Module6App, "business", 1, 1),
        ]
        for label, app_class, purpose, row, column in entries:
            ttk.Button(grid, text=label, command=lambda cls=app_class, p=purpose: self.open_module(cls, p)).grid(row=row, column=column, padx=8, pady=8, sticky="nsew", ipady=24)
        for index in range(2):
            grid.columnconfigure(index, weight=1)
            grid.rowconfigure(index, weight=1)
        ttk.Label(
            grid,
            text=self._txt(
                "※ 修繕・更新・解体シナリオで更新周期・建替え周期・イベントを確認・保存し、その結果を改修・更新・解体費で積算します。保存した改修費は200年事業評価へ連携します。金額はPlanningの概算建設費を基準とする企画・比較用の概算値です。",
                "* Review and save renewal cycles, rebuild cycles and lifecycle events in the Repair / Renewal / Demolition Scenario screen, then cost those events in the Repair / Renewal / Demolition Cost screen. Saved lifecycle costs feed the 200-year business evaluation. Monetary values are planning estimates based on Planning approximate construction costs."
            ),
            foreground="#555555", wraplength=900, justify="center", anchor="center"
        ).grid(row=2, column=0, columnspan=2, padx=10, pady=(12, 0), sticky="ew")

        ttk.Label(outer, text=self._txt("※ 200年事業の金額はPlanningの概算値を基準とした企画・比較用の概算値です。契約金額・正式見積金額ではありません。", "* Monetary values in the 200-year business evaluation are planning estimates based on Planning approximate costs; they are not contract prices or formal quotations."), foreground="#8b0000", wraplength=900, anchor="center", justify="center").pack(fill="x", pady=(14, 2))
        ttk.Label(outer, text=f"{DISPLAY_NAME}   |   {COPYRIGHT}", foreground="#555555", anchor="e").pack(fill="x", pady=(6, 0))

    def change_language(self, language: str) -> None:
        if language == self.i18n.language:
            return
        self.i18n.set_language(language)
        self._ui_language = language
        self._build_menu()
        self._build_ui()

    def open_project(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title=self._txt("Planning Project JSONを開く", "Open Planning Project JSON"),
            filetypes=[("Project JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            project = load_project(path)
        except Exception as exc:
            messagebox.showerror(self._txt("Project読込エラー", "Project Load Error"), friendly_exception_text(exc,self.i18n.language), parent=self)
            return
        self.project_context.set(path, project)
        self.project_label.configure(text=str(Path(path)))

    def open_module(self, app_class, purpose: str = "") -> None:
        if self.project_context.path is None:
            messagebox.showwarning(
                self._txt("Project未選択", "Project Not Selected"),
                self._txt("先にPlanningで保存したProject JSONを開いてください。", "Open a Project JSON saved in Planning first."),
                parent=self,
            )
            return
        try:
            project = self.project_context.reload()
            project = ensure_internal_200_year_support(
                project,
                self.project_context.path,
                ROOT,
                self.i18n.language,
            )
            self.project_context.set(self.project_context.path, project)
        except Exception as exc:
            messagebox.showerror(
                self._txt("200年評価準備エラー", "200-year Evaluation Preparation Error"),
                str(exc),
                parent=self,
            )
            return
        app_class(self, ROOT, self.i18n.language, self.project_context)

    def show_about(self) -> None:
        messagebox.showinfo(
            self._txt("このソフトについて", "About"),
            f"{DISPLAY_NAME}\n\n{COMPANY_EN}\n{COMPANY_JA}\n\n{COPYRIGHT}",
            parent=self,
        )

    def show_license(self) -> None:
        window = tk.Toplevel(self)
        window.title(self._txt("ライセンス・免責事項", "License / Disclaimer"))
        window.geometry("760x620")
        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        text = tk.Text(outer, wrap="word", font=(FONT_FAMILY, 10), padx=12, pady=12)
        text.pack(fill="both", expand=True)
        text.insert("1.0", LICENSE_BILINGUAL)
        text.configure(state="disabled")
        ttk.Button(outer, text=self._txt("閉じる", "Close"), command=window.destroy).pack(anchor="e", pady=(10, 0))


if __name__ == "__main__":
    app = AZRASEvaluationApp()
    app.mainloop()
