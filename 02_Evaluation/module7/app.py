
from __future__ import annotations
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from services.project_export_paths import default_export_path

from core.i18n import I18N, LANGUAGE_OPTIONS
from core.error_text import friendly_exception_text
from core.csv_export import write_dict_rows_csv
from core.ui_style import (apply_common_style, standardize_module_window, create_scrollable_module_page, add_module_text_copy_button)
from core.module_report_ui import attach_module_report_button
from core.project_store import load_project
from core.project_coordinator import update_module_and_propagate, format_report
from core.number_format import format_number, header_with_unit
from ui.editable_remarks import bind_editable_remarks, merge_note
from services.repair_demolition_cost_engine_v9_6 import calculate

INPUT_BG = "#fff4b8"

AUTO_BG="#d9efff"
FACTOR_KEYS = (
    ("reuse_credit", "reuse_credit_percent"),
    ("recycling_credit", "recycling_credit_percent"),
    ("waste", "waste_percent"),
    ("temporary", "temporary_percent"),
    ("overhead", "overhead_percent"),
    ("contingency", "contingency_percent"),
    ("tax", "tax_percent"),
)

SUMMARY_ROWS = (
    ("total_lifecycle_work_cost", "summary_total_cost"),
    ("average_annual_cost", "summary_average_annual"),
    ("cost_per_m2_year", "summary_cost_m2_year"),
    ("total_demolition_cost", "summary_demolition"),
    ("total_waste_cost", "summary_waste"),
    ("total_credits", "summary_credits"),
)

class Module7App(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language: str = "ja", project_context=None):
        super().__init__(master)
        apply_common_style(self)
        standardize_module_window(self,7)
        self.project_context = project_context
        self.root_dir = Path(root_dir)
        self.i18n = I18N(self.root_dir, language)
        self.db = json.loads(
            (self.root_dir / "data" / "repair_demolition_cost_assumptions_v9_6.json")
            .read_text(encoding="utf-8")
        )
        self.project = None
        self.path = None
        self.result = None
        self.user_notes = {}
        self.project_file = tk.StringVar()

        # GUI displays percentages as 45, 5, 25... while the engine receives 0.45, 0.05, 0.25...
        self.vars = {
            key: tk.StringVar(value=f"{float(self.db['factors'][key]) * 100:g}")
            for key, _ in FACTOR_KEYS
        }

        if self.project_context is not None and self.project_context.path is not None:
            self.project = self.project_context.reload()
            self.path = self.project_context.path
            self.project_file.set(self.project_context.display_path)
        self.title(self.i18n.t("module7"))
        self.build();attach_module_report_button(self,7)
        self.restore_saved_state()
        self.bind("<FocusIn>", self.refresh_project_from_context)

    def refresh_project_from_context(self, event=None):
        """Use only the Project JSON selected or created in Module 0."""
        if self.project_context is None or self.project_context.path is None:
            return False
        active_path = self.project_context.path
        current_path = getattr(self, "path", None)
        if current_path is None or Path(current_path) != Path(active_path):
            self.project = self.project_context.reload()
            self.path = active_path
            if hasattr(self, "project_file"):
                self.project_file.set(self.project_context.display_path)
        elif self.project is None:
            self.project = self.project_context.reload()
        return True

    def _project_currency(self):
        project=self.project if isinstance(self.project,dict) else {}
        m5=(project.get("module_outputs") or {}).get("module5") if isinstance(project.get("module_outputs"),dict) else {}
        if isinstance(m5,dict) and m5.get("currency"):
            return str(m5.get("currency")).upper()
        return "JPY"

    def build(self):
        for widget in self.winfo_children():
            widget.destroy()

        page=create_scrollable_module_page(self)
        t = self.i18n.t
        self.title(t("module7"))

        top = ttk.Frame(page)
        top.pack(fill="x", padx=10, pady=5)
        add_module_text_copy_button(self,top)
        ttk.Label(top, text=t("language")).pack(side="left")
        language_value = tk.StringVar(
            value="日本語" if self.i18n.language == "ja" else "English"
        )
        language_box = ttk.Combobox(
            top,
            textvariable=language_value,
            values=LANGUAGE_OPTIONS,
            state="readonly",
            width=12,
        )
        language_box.pack(side="left", padx=5)
        language_box.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.change_language(
                "ja" if language_value.get() == "日本語" else "en"
            ),
        )



        ttk.Button(
            top, text=t("print_this_module"), style="Primary.TButton",
            command=lambda: self.print_module_report()
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_module7"), command=self.save_output
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_event_cost_csv"), command=self.save_csv
        ).pack(side="right", padx=4)

        project_frame = ttk.LabelFrame(page, text=t("project"))
        project_frame.pack(fill="x", padx=10, pady=4)
        ttk.Label(project_frame, text=t("project_json")).grid(
            row=0, column=0, padx=4, pady=4
        )
        tk.Entry(
            project_frame,
            textvariable=self.project_file,
            width=105,
            state="readonly",
            readonlybackground=AUTO_BG,
        ).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        project_frame.columnconfigure(1, weight=1)

        settings_frame = ttk.LabelFrame(page, text=t("module7_settings"))
        settings_frame.pack(fill="x", padx=10, pady=4)
        for index, (key, label_key) in enumerate(FACTOR_KEYS):
            row = index // 4
            column = (index % 4) * 2
            ttk.Label(settings_frame, text=t(label_key)).grid(
                row=row, column=column, padx=4, pady=4, sticky="e"
            )
            tk.Entry(
                settings_frame,
                textvariable=self.vars[key],
                bg=INPUT_BG,
                width=12,
            ).grid(row=row, column=column + 1, padx=4, pady=4)

        ttk.Label(
            page,
            text=t("repair_cost_notice"),
            foreground="#8b0000",
            wraplength=1450,
        ).pack(fill="x", padx=12, pady=4)

        ttk.Button(
            page,
            text=t("calculate_repair_cost"),
            command=self.run_calculation,
        ).pack(pady=5)

        body = ttk.Panedwindow(page, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=5)

        summary_frame = ttk.LabelFrame(body, text=t("repair_cost_result"))
        event_frame = ttk.LabelFrame(body, text=t("event_cost_timeline"))
        body.add(summary_frame, weight=2)
        body.add(event_frame, weight=4)

        self.summary_tree = ttk.Treeview(
            summary_frame,
            columns=("item", "value", "unit", "calculation_basis", "reference_source"),
            show="headings",
        )
        for column, heading, width in (
            ("item", t("item"), 305),
            ("value", t("value"), 150),
            ("unit", t("unit"), 90),
            ("calculation_basis", t("calculation_basis"), 430),
            ("reference_source", t("reference_source"), 300),
        ):
            self.summary_tree.heading(column, text=heading)
            self.summary_tree.column(
                column,
                width=width,
                anchor="e" if column == "value" else "w",
            )
        self.summary_tree.pack(fill="both", expand=True)
        # The calculation-basis cell remains editable (double-click / F2),
        # replacing the former generic remarks field.
        bind_editable_remarks(
            self.summary_tree, self.user_notes, remark_column="calculation_basis"
        )

        columns = (
            "year", "action", "component", "work",
            "demolition", "waste", "credit", "total"
        )
        # PATCH_634: project_currency was used here without ever being
        # assigned, causing a NameError every time this module opened or
        # the language was switched (build() runs in both paths), which
        # crashed the module and left the takeoff/results blank.
        project_currency = self._project_currency()
        headings = (
            t("event_year"), t("event_action"), t("event_component"),
            header_with_unit(t("event_work_cost"),project_currency), header_with_unit(t("event_demolition_cost"),project_currency),
            header_with_unit(t("event_waste_cost"),project_currency), header_with_unit(t("event_credit"),project_currency), header_with_unit(t("event_total"),project_currency)
        )
        widths = (70, 150, 230, 145, 120, 130, 135, 145)
        self.event_tree = ttk.Treeview(
            event_frame, columns=columns, show="headings"
        )
        for column, heading, width in zip(columns, headings, widths):
            self.event_tree.heading(column, text=heading)
            self.event_tree.column(
                column,
                width=width,
                anchor="w" if column in ("action", "component") else "e",
            )
        y_scroll = ttk.Scrollbar(
            event_frame, orient="vertical", command=self.event_tree.yview
        )
        x_scroll = ttk.Scrollbar(
            event_frame, orient="horizontal", command=self.event_tree.xview
        )
        self.event_tree.configure(
            yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set
        )
        self.event_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        event_frame.rowconfigure(0, weight=1)
        event_frame.columnconfigure(0, weight=1)


        if self.result:
            self.show_result()

    def restore_saved_state(self):
        if self.project is None:
            return
        saved = self.project.get("module_outputs", {}).get("module7") or {}
        if not isinstance(saved, dict) or not saved:
            return
        self.user_notes = dict(saved.get("_user_notes") or {})
        snapshot = saved.get("_input_snapshot") or {}
        settings = snapshot.get("settings") or {}
        for key, _label in FACTOR_KEYS:
            if settings.get(key) is not None and key in self.vars:
                self.vars[key].set(f"{float(settings[key]) * 100:g}")
        self.result = saved
        try:
            self.show_result()
        except Exception:
            pass

    def summary_explanation(self, key: str):
        """Return numbered item label, calculation basis and traceable source."""
        t = self.i18n.t
        labels = {
            "total_lifecycle_work_cost": (
                "①",
                "全イベントの修繕・更新・再建費＋解体費＋廃棄物処理費－再使用・リサイクル控除の合計"
                if self.i18n.language == "ja"
                else "Sum of all event repair/renewal/rebuild, demolition and waste costs less reuse/recycling credits",
                "Module 3 シナリオ＋Module 5 建設費＋Module 7 設定"
                if self.i18n.language == "ja"
                else "Module 3 scenario + Module 5 construction cost + Module 7 settings",
            ),
            "average_annual_cost": (
                "②",
                "①÷評価期間" if self.i18n.language == "ja" else "① ÷ assessment period",
                "①＋Project JSON（評価期間）"
                if self.i18n.language == "ja"
                else "① + Project JSON (assessment period)",
            ),
            "cost_per_m2_year": (
                "③",
                "②÷延床面積" if self.i18n.language == "ja" else "② ÷ gross floor area",
                "②＋Project JSON（延床面積）"
                if self.i18n.language == "ja"
                else "② + Project JSON (gross floor area)",
            ),
            "total_demolition_cost": (
                "④",
                "全解体イベントの解体費合計"
                if self.i18n.language == "ja"
                else "Sum of demolition costs for all demolition events",
                "Module 3 イベント＋Module 5 建設費＋Module 7 解体条件"
                if self.i18n.language == "ja"
                else "Module 3 events + Module 5 construction cost + Module 7 demolition settings",
            ),
            "total_waste_cost": (
                "⑤",
                "全イベントの廃棄物処理費合計"
                if self.i18n.language == "ja"
                else "Sum of waste-disposal costs for all events",
                "Module 3 イベント＋Module 7 廃棄物処理条件"
                if self.i18n.language == "ja"
                else "Module 3 events + Module 7 waste settings",
            ),
            "total_credits": (
                "⑥",
                "再使用控除＋リサイクル控除の累計"
                if self.i18n.language == "ja"
                else "Cumulative reuse credits + recycling credits",
                "Module 3 イベント＋Module 7 再使用・リサイクル条件"
                if self.i18n.language == "ja"
                else "Module 3 events + Module 7 reuse/recycling settings",
            ),
        }
        number, basis, source = labels.get(
            key,
            ("",
             "計算条件および入力データに基づく算定" if self.i18n.language == "ja" else "Calculated from configured conditions and input data",
             "Project JSON"),
        )
        label_key = dict(SUMMARY_ROWS).get(key, key)
        item_label = f"{number} {t(label_key)}".strip()
        return item_label, basis, source



    def change_language(self, language: str):
        self.i18n.set_language(language)
        self.build();attach_module_report_button(self,7)

    def choose_project(self):
        path = filedialog.askopenfilename(
            filetypes=[(self.i18n.t("select_json_filetype"), "*.json")]
        )
        if not path:
            return
        try:
            project = load_project(path)
            outputs = project.get("module_outputs", {})
            if not outputs.get("module3") or not outputs.get("module5"):
                raise ValueError(self.i18n.t("module35_required"))
            self.project = project
            self.path = Path(path)
            self.project_file.set(path)
        except Exception as exc:
            messagebox.showerror(self.i18n.t("error_title"), friendly_exception_text(exc,self.i18n.language))

    def engine_settings(self):
        values = {}
        for key, _ in FACTOR_KEYS:
            raw = self.vars[key].get().replace(",", "").strip()
            values[key] = float(raw) / 100.0
        return values

    def run_calculation(self):
        if self.project is None:
            messagebox.showwarning(
                self.i18n.t("warning_title"),
                self.i18n.t("no_project_selected"),
            )
            return
        try:
            self.result = calculate(
                self.project, self.db, self.engine_settings()
            )
            self.show_result()
            messagebox.showinfo("OK", self.i18n.t("repair_cost_complete"))
        except Exception as exc:
            messagebox.showerror(self.i18n.t("error_title"), friendly_exception_text(exc,self.i18n.language))

    def action_label(self, action_key: str) -> str:
        language_key = "ja" if self.i18n.language == "ja" else "en"
        return self.db.get("action_rates", {}).get(
            action_key, {}
        ).get(language_key, action_key)

    def component_label(self, component_key: str, fallback: str = "") -> str:
        translated = self.i18n.t(f"component_{component_key}")
        if translated != f"component_{component_key}":
            return translated
        return fallback or component_key

    def show_result(self):
        if not hasattr(self, "summary_tree") or not hasattr(self, "event_tree"):
            return
        for tree in (self.summary_tree, self.event_tree):
            for item_id in tree.get_children():
                tree.delete(item_id)

        t = self.i18n.t
        summary = self.result["summary"]
        currency = self.result["currency"]

        for key, label_key in SUMMARY_ROWS:
            unit = currency
            if key == "average_annual_cost":
                unit = (
                    "円／年"
                    if self.i18n.language == "ja" and currency == "JPY"
                    else f"{currency}/year"
                )
            elif key == "cost_per_m2_year":
                unit = (
                    "円／m²・年"
                    if self.i18n.language == "ja" and currency == "JPY"
                    else f"{currency}/m²·year"
                )
            item_label, basis, source = self.summary_explanation(key)
            self.summary_tree.insert(
                "",
                "end",
                values=(
                    item_label,
                    format_number(summary[key], unit),
                    unit,
                    merge_note(self.user_notes, item_label, basis),
                    source,
                ),
            )

        for row in self.result["event_costs"]:
            credit = row["reuse_credit"] + row["recycling_credit"]
            self.event_tree.insert(
                "",
                "end",
                values=(
                    row["year"],
                    self.action_label(row["action"]),
                    self.component_label(
                        row.get("component_key", ""),
                        row.get("component", ""),
                    ),
                    format_number(row["work_cost"],currency),
                    format_number(row["demolition_cost"],currency),
                    format_number(row["waste_cost"],currency),
                    format_number(credit,currency),
                    format_number(row["event_total"],currency),
                ),
            )

    def save_csv(self):
        if not self.result:
            return
        # This screen is displayed as Module 6.  Use the active Project JSON path;
        # self.project_path never existed and prevented the event CSV from being saved.
        if self.path is None:
            messagebox.showwarning("Warning", self.i18n.t("save_conditions_missing"))
            return
        default_path = default_export_path(
            self.path,
            6,
            label="Module6_修繕更新解体積算_イベント別",
        )
        path = filedialog.asksaveasfilename(
            parent=self,
            title="解体・修繕タイムラインCSVの保存先"
            if self.i18n.language == "ja" else "Save demolition and repair timeline CSV",
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        rows = self.result["event_costs"]
        write_dict_rows_csv(path, rows)

    def save_output(self):
        self.refresh_project_from_context()
        if self.project is None or self.path is None or self.result is None:
            messagebox.showwarning("Warning", self.i18n.t("save_conditions_missing"))
            return
        try:
            self.result["_user_notes"] = dict(self.user_notes)
            report = update_module_and_propagate(
                self.project,
                self.path,
                "module7",
                self.result,
                {
    "settings": self.engine_settings(),
    "language": self.i18n.language,
},
                self.root_dir,
            )
            if self.project_context is not None:
                self.project_context.set(self.path, self.project)
            messagebox.showinfo(
                self.i18n.t("saved"),
                format_report(report, self.i18n.language),
            )
        except Exception as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))
