from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.branding import (
    COMPANY_EN,
    COMPANY_JA,
    COPYRIGHT,
    DISPLAY_NAME,
    GITHUB,
    LICENSE_BILINGUAL,
)
from core.clipboard import install_global_clipboard_support
from core.canonical_language import CANONICAL_LANGUAGE, LANGUAGE_LABELS, normalize_ui_language, LANGUAGE_OPTIONS
from core.i18n import I18N
from core.project_context import ProjectContext
from core.ui_style import FONT_FAMILY, SUBTITLE_SIZE, apply_common_style
from module0.app import Module0App
from module1.app import Module1App
from module2.app import Module2App
from module5.app import Module5App
from screening.app import ConstructionMethodScreeningApp
from regional_analysis.module9_ui import RegionalLocationManager
from regional_analysis.module10_ui import RegionalComparisonApp


class AZRASPlanningApp(tk.Tk):
    """Planning-stage AZRAS application.

    This child product exposes planning, method screening, Module 1/2/5, and regional Module 9/10 workflows.
    Shared calculation engines and the common project schema remain compatible
    with the other AZRAS products.
    """

    def __init__(self) -> None:
        super().__init__()
        self.i18n = I18N(ROOT, CANONICAL_LANGUAGE)
        self.project_context = ProjectContext()

        apply_common_style(self)
        install_global_clipboard_support(self)
        self.title(f"{DISPLAY_NAME} — {COMPANY_EN}")
        self.geometry("1040x820")
        self.minsize(900, 700)
        self.language_var = tk.StringVar(value=LANGUAGE_LABELS[CANONICAL_LANGUAGE])
        self._build()
        self._install_menu()

    def _install_menu(self) -> None:
        menu_bar = tk.Menu(self)
        help_menu = tk.Menu(menu_bar, tearoff=False)
        if self.i18n.language == "ja":
            about_label = "このソフトについて"
            license_label = "ライセンス・免責事項"
            exit_label = "終了"
            help_label = "ヘルプ"
        else:
            about_label = "About"
            license_label = "License & Disclaimer"
            exit_label = "Exit"
            help_label = "Help"
        help_menu.add_command(label=about_label, command=self._show_about)
        help_menu.add_command(label=license_label, command=self._show_license)
        help_menu.add_separator()
        help_menu.add_command(label=exit_label, command=self.destroy)
        menu_bar.add_cascade(label=help_label, menu=help_menu)
        self.config(menu=menu_bar)

    def _change_language(self, event=None) -> None:
        language = "ja" if self.language_var.get() == LANGUAGE_LABELS["ja"] else CANONICAL_LANGUAGE
        self.request_global_language(language, source=self)

    def _walk_toplevels(self, widget=None):
        """Yield every currently displayed child/grandchild Toplevel."""
        widget = self if widget is None else widget
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel):
                yield child
            yield from self._walk_toplevels(child)

    def _rebuild_parent_shell_preserve_children(self) -> None:
        """Rebuild only the cover UI; never destroy open module windows."""
        for child in list(self.winfo_children()):
            if isinstance(child, tk.Toplevel):
                continue
            child.destroy()
        self._build()
        self._install_menu()

    def request_global_language(self, language: str, source=None) -> None:
        """Synchronize one language across cover + every open module window.

        A language change initiated by either the cover (parent) or any module
        (child) is authoritative for the entire AZRAS Planning process.
        """
        language = normalize_ui_language(language)
        self.i18n.set_language(language)
        self.language_var.set(LANGUAGE_LABELS[language])
        self._rebuild_parent_shell_preserve_children()

        # Snapshot first because rebuilding a module may recreate nested widgets.
        windows = list(self._walk_toplevels())
        for window in windows:
            try:
                if not window.winfo_exists():
                    continue
                handler = getattr(window, "_apply_global_language", None)
                if callable(handler):
                    handler(language)
            except tk.TclError:
                pass

    def _text(self, ja: str, en: str) -> str:
        return ja if self.i18n.language == "ja" else en

    def _show_about(self) -> None:
        if self.i18n.language == "ja":
            description = (
                "これから建てる単一工法の建物について、世界各地域の気象条件を用いて\n"
                "8760時間解析を行い、環境性能・エネルギー性能・地域適合性を\n"
                "比較評価する企画設計支援製品です。"
            )
            title = "このソフトについて"
        else:
            description = (
                "This planning tool evaluates one construction method across world regions using\n"
                "8,760-hour weather analysis, comparing environmental performance, energy performance,\n"
                "and regional suitability."
            )
            title = "About"
        body = (
            f"{DISPLAY_NAME}\n\n{description}\n\n"
            f"Developed by\n{COMPANY_EN}\n{COMPANY_JA}\n\n"
            f"{COPYRIGHT}\n{GITHUB}"
        )
        messagebox.showinfo(title, body, parent=self)

    def _show_license(self) -> None:
        window = tk.Toplevel(self)
        window.title("ライセンス・免責事項 / License & Disclaimer")
        window.geometry("760x620")
        window.transient(self)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="ライセンス・免責事項 / License & Disclaimer",
            font=(FONT_FAMILY, SUBTITLE_SIZE, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        text = tk.Text(frame, wrap="word", padx=12, pady=12, font=(FONT_FAMILY, 10))
        text.pack(fill="both", expand=True)
        text.insert("1.0", LICENSE_BILINGUAL)
        text.configure(state="disabled")
        ttk.Button(frame, text=self._text("閉じる", "Close"), command=window.destroy).pack(anchor="e", pady=(10, 0))

    def _build(self) -> None:
        t = self._text
        outer = ttk.Frame(self, padding=(30, 22))
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=DISPLAY_NAME, font=(FONT_FAMILY, 24, "bold"), anchor="center").pack(fill="x")
        ttk.Label(
            outer,
            text=t("建築企画・世界地域別環境性能評価", "Building Planning & Global Regional Environmental Performance Evaluation"),
            font=(FONT_FAMILY, 13, "bold"), anchor="center",
        ).pack(fill="x", pady=(4, 4))
        ttk.Label(
            outer,
            text=t(
                "これから建てる単一工法の建物について、世界各地域の気象条件を用いて8760時間解析を行い、\n環境性能・エネルギー性能・地域適合性を比較評価し、企画設計の判断材料を作成します。",
                "For a building using one construction method, 8,760-hour analysis is performed with weather data from regions worldwide.\nEnvironmental performance, energy performance, and regional suitability are compared to support planning decisions.",
            ),
            justify="center", anchor="center",
        ).pack(fill="x", pady=(0, 18))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 12))
        ttk.Label(controls, text=t("言語", "Language")).pack(side="left")
        self.language_var.set("日本語" if self.i18n.language == "ja" else "English")
        language_box = ttk.Combobox(controls, textvariable=self.language_var, values=LANGUAGE_OPTIONS, state="readonly", width=12)
        language_box.pack(side="left", padx=6)
        language_box.bind("<<ComboboxSelected>>", self._change_language)

        ttk.Label(
            outer,
            text=t(
                "内部データ標準：英語（Canonical）／日本語は表示翻訳",
                "Internal data standard: English (Canonical) / Japanese is a presentation translation",
            ),
            foreground="#555555",
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        button_area = ttk.Frame(outer)
        button_area.pack(fill="both", expand=True)
        button_area.columnconfigure(0, weight=1)
        button_area.columnconfigure(1, weight=1)
        for row in range(4):
            button_area.rowconfigure(row, weight=1)

        entries = [
            (t("1. 建築企画・基本条件", "1. Project Planning & Basic Conditions"), "Project Planning / Module 0", lambda: Module0App(self, ROOT, self.i18n.language, self.project_context)),
            (t("2. 工法候補 一次・二次診断", "2. Construction Method Primary & Secondary Screening"), t("地域・法規・災害 → 物理施工性", "Region / Regulation / Hazard → Physical Constructability"), lambda: ConstructionMethodScreeningApp(self, ROOT, self.i18n.language, self.project_context)),
            (t("3. 図面解析・数量・建物性能解析", "3. Drawing Analysis, Quantity & Building Performance"), "Drawing & Quantity / Module 1", lambda: Module1App(self, ROOT, self.i18n.language, self.project_context)),
            (t("4. 環境・CO₂・地域別8760時間解析", "4. Environment, CO₂ & Regional 8,760-Hour Analysis"), "Environment & Energy / Module 2", lambda: Module2App(self, ROOT, self.i18n.language, self.project_context)),
            (t("5. 建設費・数量別工事費", "5. Construction Cost & Quantity-Based Pricing"), "Construction Cost / Module 5", lambda: Module5App(self, ROOT, self.i18n.language, self.project_context)),
            (t("6. 地域別Project生成", "6. Regional Project Generation"), "Regional Project Manager / Module 9", lambda: RegionalLocationManager(self, ROOT, self.i18n.language, self.project_context)),
            (t("7. 地域比較・指定日時グラフ", "7. Regional Comparison & Selected-Hour Graphs"), "Regional Comparison / Module 10", lambda: RegionalComparisonApp(self, ROOT, self.i18n.language, self.project_context)),
        ]
        for index, (primary, secondary, command) in enumerate(entries):
            row, column = divmod(index, 2)
            ttk.Button(button_area, text=f"{primary}\n{secondary}", command=command).grid(
                row=row, column=column, padx=10, pady=9, sticky="nsew", ipady=16
            )

        ttk.Label(
            outer,
            text=t(
                "建築企画 → 工法候補一次・二次診断 → 図面・数量解析 → 地域別8760時間解析 → 建設費 → 世界地域比較 → 企画判断\nProject JSONは将来のAZRAS Compare / Evaluation / Professional / Twinへ引き継げます。",
                "Building planning → Primary & secondary method screening → Drawing & quantity analysis → Regional 8,760-hour analysis → Construction cost → Global regional comparison → Planning decision\nProject JSON can be transferred to AZRAS Compare / Evaluation / Professional / Twin.",
            ),
            justify="center", anchor="center", foreground="#555555",
        ).pack(fill="x", pady=(14, 4))
        ttk.Label(outer, text=f"{DISPLAY_NAME}  |  {COPYRIGHT}", foreground="#555555", anchor="e").pack(fill="x")


if __name__ == "__main__":
    app = AZRASPlanningApp()
    app.mainloop()
