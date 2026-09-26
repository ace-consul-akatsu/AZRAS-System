
from __future__ import annotations

from datetime import datetime, timezone
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import urllib.parse
import webbrowser

from core.i18n import I18N
from core.error_text import friendly_exception_text
from core.canonical_language import CANONICAL_LANGUAGE, LANGUAGE_LABELS, normalize_ui_language, LANGUAGE_OPTIONS
from core.ui_style import (apply_common_style, standardize_module_window, create_scrollable_module_page, add_module_text_copy_button)
from core.ui_style import fit_window_to_screen
from core.module_report_ui import attach_module_report_button
from core.project_store import new_project, load_project, save_project, comparison_copy_block_reason
from core.project_coordinator import module_output_is_current
from services.project_export_paths import (
    default_project_filename,
    find_json_directory,
    project_output_directory,
    set_configured_json_directory,
    unified_project_json_path,
)
from services.construction_feasibility_screening import screen_construction_methods

INPUT_BG = "#fff4b8"
AUTO_BG = "#d9efff"
PROJECT_ID_BG = "#e6e6e6"
RESULT_BG = "#dff3df"





class Module0App(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language: str = CANONICAL_LANGUAGE, project_context=None):
        super().__init__(master)
        apply_common_style(self)
        standardize_module_window(self,0)
        self.root_dir = Path(root_dir)
        self.project_context = project_context
        self.i18n = I18N(self.root_dir, normalize_ui_language(language))
        self.country_master = json.loads(
            (self.root_dir / "data" / "countries_v9_2_9.json").read_text(encoding="utf-8")
        )["countries"]
        if self.project_context is not None and self.project_context.path is not None:
            self.project = self.project_context.reload()
            self.path = self.project_context.path
        else:
            self.project = new_project()
            self.path = None
        self.vars: dict[str, tk.StringVar] = {}
        # PATCH 508: when the user changes the save folder while a Project is
        # already open, the next Save must relocate that Project to the newly
        # selected base folder.  Previously only the default for *new* Projects
        # changed, so an open Project kept saving to its old location.
        self._save_directory_override: Path | None = None
        self.coordinate_text = tk.StringVar()
        self.parsed_latitude = tk.StringVar()
        self.parsed_longitude = tk.StringVar()
        self.title(self.i18n.t("module0"))
        self.build()
        self.bind("<FocusIn>", self.refresh_project_from_context)

    def build(self):
        self.collect(silent=True)
        for widget in self.winfo_children():
            widget.destroy()

        page=create_scrollable_module_page(self)
        t = self.i18n.t
        top = ttk.Frame(page)
        top.pack(fill="x", padx=12, pady=8)
        add_module_text_copy_button(self,top)

        ttk.Label(top, text=t("language")).pack(side="left")
        language = tk.StringVar(value=LANGUAGE_LABELS[self.i18n.language])
        language_box = ttk.Combobox(
            top,
            textvariable=language,
            values=LANGUAGE_OPTIONS,
            state="readonly",
            width=12,
        )
        language_box.pack(side="left", padx=5)
        language_box.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.change_language(
                "ja" if language.get() == LANGUAGE_LABELS["ja"] else CANONICAL_LANGUAGE
            ),
        )

        ttk.Label(
            page,
            text=(
                "内部データ標準：英語（Canonical）／日本語は表示翻訳"
                if self.i18n.language == "ja"
                else "Internal data standard: English (Canonical) / Japanese is a presentation translation"
            ),
            foreground="#555555",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 6))

        ttk.Button(
            top,
            text=self.i18n.t("print_this_module"),
            style="Primary.TButton",
            command=lambda: self.print_module_report(),
        ).pack(side="right", padx=(10, 4))
        ttk.Button(top, text=t("new"), command=self.new).pack(side="right", padx=4)
        ttk.Button(top, text=t("load"), command=self.load).pack(side="right", padx=4)
        ttk.Button(top, text=t("save"), command=self.save).pack(side="right", padx=4)
        ttk.Button(
            top,
            text="保存先変更" if self.i18n.language == "ja" else "Change save folder",
            command=self.change_save_directory,
        ).pack(side="right", padx=4)

        ttk.Label(
            self,
            text=t("country_selection_notice"),
            foreground="#555555",
            wraplength=1120,
        ).pack(fill="x", padx=16, pady=(0, 3))
        ttk.Label(
            self,
            text=t("google_maps_coordinate_notice"),
            foreground="#8b0000",
            wraplength=1120,
        ).pack(fill="x", padx=16, pady=(0, 3))
        ttk.Label(
            self,
            text=t("coordinate_usage_notice"),
            foreground="#8b0000",
            wraplength=1120,
        ).pack(fill="x", padx=16, pady=(0, 5))

        project_box = ttk.LabelFrame(page, text=t("project"))
        project_box.pack(fill="x", padx=12, pady=7)

        common = self.project["common"]
        self.project.setdefault("metadata", {})
        metadata = self.project["metadata"]

        fields = [
            ("project_name", "project_name", "input"),
            ("project_id", "project_id", "auto"),
            ("project_number", "project_number", "input"),
            ("country", "country", "input"),
            ("project_location", "project_location", "input"),
            ("usage", "building_use", "input"),
        ]

        for index, (label_key, data_key, field_type) in enumerate(fields):
            row = index // 2
            column = (index % 2) * 2
            ttk.Label(project_box, text=t(label_key)).grid(
                row=row, column=column, padx=8, pady=6, sticky="e"
            )

            if data_key == "project_id":
                value = self.project["project_id"]
            elif data_key == "project_number":
                value = metadata.get("project_number", "")
            elif data_key == "project_location":
                value = common.get("project_location", "")
                if not value:
                    legacy_city = str(common.get("city", "") or "").strip()
                    legacy_address = str(common.get("address", "") or "").strip()
                    value = " ".join(x for x in (legacy_city, legacy_address) if x)
            else:
                value = common.get(data_key, "")

            var = tk.StringVar(value=str(value))
            self.vars[data_key] = var
            if data_key == "country":
                entry = ttk.Combobox(
                    project_box,
                    textvariable=var,
                    values=self.country_master,
                    state="readonly",
                    width=41,
                )
            else:
                entry_bg = PROJECT_ID_BG if data_key == "project_id" else (AUTO_BG if field_type == "auto" else INPUT_BG)
                entry = tk.Entry(
                    project_box,
                    textvariable=var,
                    width=43,
                    bg=entry_bg,
                )
            entry.grid(
                row=row, column=column + 1, padx=8, pady=6, sticky="ew"
            )
            if field_type == "auto":
                readonly_bg = PROJECT_ID_BG if data_key == "project_id" else AUTO_BG
                entry.configure(state="readonly", readonlybackground=readonly_bg)

        ttk.Button(
            project_box,
            text=t("create_project_number"),
            command=self.generate_project_number,
        ).grid(row=4, column=0, padx=8, pady=6, sticky="e")

        project_box.columnconfigure(1, weight=1)
        project_box.columnconfigure(3, weight=1)

        action_box = ttk.LabelFrame(page, text=t("coordinate_settings"))
        action_box.pack(fill="x", padx=12, pady=7)

        ttk.Button(
            action_box,
            text=t("open_google_maps"),
            command=self.open_google_maps,
        ).grid(row=0, column=0, padx=7, pady=8)

        ttk.Label(action_box, text=t("google_coordinate_source")).grid(
            row=0, column=1, padx=7, pady=8, sticky="e"
        )
        tk.Entry(
            action_box,
            textvariable=self.coordinate_text,
            bg=INPUT_BG,
            width=58,
        ).grid(row=0, column=2, columnspan=3, padx=7, pady=8, sticky="ew")

        ttk.Button(
            action_box,
            text=t("paste_coordinates"),
            command=self.paste_coordinates,
        ).grid(row=0, column=5, padx=7, pady=8)

        ttk.Label(action_box, text=t("azras_coordinate_display")).grid(
            row=1, column=0, padx=7, pady=(12, 5), sticky="w"
        )

        ttk.Label(action_box, text=t("latitude")).grid(
            row=2, column=0, padx=7, pady=6, sticky="e"
        )
        tk.Entry(
            action_box,
            textvariable=self.parsed_latitude,
            state="readonly",
            readonlybackground=AUTO_BG,
            width=24,
        ).grid(row=2, column=1, padx=7, pady=6, sticky="w")

        ttk.Label(action_box, text=t("longitude")).grid(
            row=2, column=2, padx=7, pady=6, sticky="e"
        )
        tk.Entry(
            action_box,
            textvariable=self.parsed_longitude,
            state="readonly",
            readonlybackground=AUTO_BG,
            width=24,
        ).grid(row=2, column=3, padx=7, pady=6, sticky="w")

        ttk.Button(
            action_box,
            text=t("apply_coordinates_to_modules"),
            command=self.apply_coordinates,
        ).grid(row=2, column=5, padx=7, pady=6)

        ttk.Button(
            action_box,
            text=t("copy_location_bundle"),
            command=self.copy_location_bundle,
        ).grid(row=3, column=0, padx=7, pady=8)
        ttk.Label(
            action_box,
            text=t("coordinate_format_example"),
            foreground="#555555",
        ).grid(row=3, column=1, columnspan=5, padx=7, pady=8, sticky="w")

        action_box.columnconfigure(2, weight=1)
        action_box.columnconfigure(4, weight=1)

        # Restore any coordinates already stored in the Project JSON.
        raw_google_coordinate = common.get(
            "google_coordinate_source",
            common.get("location", {}).get("google_coordinate_raw", "")
        )
        self.coordinate_text.set(str(raw_google_coordinate or ""))

        stored_lat = common.get("latitude", "")
        stored_lon = common.get("longitude", "")
        if stored_lat != "":
            try:
                self.parsed_latitude.set(f"{float(stored_lat):.8f}")
            except (TypeError, ValueError):
                self.parsed_latitude.set(str(stored_lat))
        if stored_lon != "":
            try:
                self.parsed_longitude.set(f"{float(stored_lon):.8f}")
            except (TypeError, ValueError):
                self.parsed_longitude.set(str(stored_lon))

        ttk.Label(
            self,
            text=t("project_number_notice"),
            foreground="#555555",
            wraplength=1120,
        ).pack(fill="x", padx=16, pady=(2, 8))

        # Project setting summary: common explanatory table used across AZRAS modules.
        summary_title = "プロジェクト設定一覧" if self.i18n.language == "ja" else "Project settings summary"
        summary_box = ttk.LabelFrame(page, text=summary_title)
        summary_box.pack(fill="both", expand=True, padx=12, pady=(2, 10))

        columns = ("no", "item", "value", "unit", "basis", "source")
        self.summary_tree = ttk.Treeview(summary_box, columns=columns, show="headings", height=10)
        headers = (
            ("No.", "No."),
            ("項目", "Item"),
            ("値", "Value"),
            ("単位", "Unit"),
            ("算定根拠", "Basis / definition"),
            ("参照元", "Source"),
        )
        for col, (ja, en) in zip(columns, headers):
            self.summary_tree.heading(col, text=ja if self.i18n.language == "ja" else en)
        self.summary_tree.column("no", width=55, anchor="center", stretch=False)
        self.summary_tree.column("item", width=180, anchor="w")
        self.summary_tree.column("value", width=260, anchor="w")
        self.summary_tree.column("unit", width=75, anchor="center", stretch=False)
        self.summary_tree.column("basis", width=330, anchor="w")
        self.summary_tree.column("source", width=180, anchor="w")

        ybar = ttk.Scrollbar(summary_box, orient="vertical", command=self.summary_tree.yview)
        xbar = ttk.Scrollbar(summary_box, orient="horizontal", command=self.summary_tree.xview)
        self.summary_tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.summary_tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        summary_box.rowconfigure(0, weight=1)
        summary_box.columnconfigure(0, weight=1)

        self.refresh_project_summary()
        for var in list(self.vars.values()) + [self.coordinate_text, self.parsed_latitude, self.parsed_longitude]:
            try:
                var.trace_add("write", lambda *_args: self.refresh_project_summary())
            except Exception:
                pass

    def refresh_project_summary(self):
        tree = getattr(self, "summary_tree", None)
        if tree is None or not tree.winfo_exists():
            return
        for item_id in tree.get_children():
            tree.delete(item_id)

        ja = self.i18n.language == "ja"
        metadata = self.project.get("metadata", {})
        rows = [
            ("①", "プロジェクト名" if ja else "Project name", self.vars.get("project_name", tk.StringVar(value="")).get(), "-",
             "利用者が設定する物件識別名称" if ja else "User-defined project identification name",
             "Module 0 入力" if ja else "Module 0 input"),
            ("②", "Project ID" if ja else "Project ID", self.vars.get("project_id", tk.StringVar(value="")).get(), "-",
             "Project JSON作成時に自動生成される一意ID" if ja else "Unique ID generated when the Project JSON is created",
             "Project JSON"),
            ("③", "プロジェクト番号" if ja else "Project number", self.vars.get("project_number", tk.StringVar(value=str(metadata.get("project_number", "")))).get(), "-",
             "利用者入力または［プロジェクト番号作成］で生成" if ja else "User input or generated by Create project number",
             "Module 0 入力" if ja else "Module 0 input"),
            ("④", "国" if ja else "Country", self.vars.get("country", tk.StringVar(value="")).get(), "-",
             "国別の気象・通貨・地域条件を選ぶ基準" if ja else "Basis for country-specific weather, currency and regional conditions",
             "Module 0 入力／国マスター" if ja else "Module 0 input / country master"),
            ("⑤", "都市・所在地" if ja else "City / Location", self.vars.get("project_location", tk.StringVar(value="")).get(), "-",
             "計画地を一つの正式所在地として入力。地域解析・気象・建設単価で共通利用" if ja else "Authoritative project location shared by regional analysis, weather and construction pricing",
             "Module 0 入力" if ja else "Module 0 input"),
            ("⑥", "建物用途" if ja else "Building use", self.vars.get("building_use", tk.StringVar(value="")).get(), "-",
             "各Moduleの用途別条件を選択する基礎条件" if ja else "Base condition for use-specific assumptions in each module",
             "Module 0 入力" if ja else "Module 0 input"),
            ("⑦", "Google Maps座標原文" if ja else "Google Maps coordinate source", self.coordinate_text.get(), "-",
             "Google Mapsから貼り付けた緯度・経度の原文を保持" if ja else "Preserves the raw latitude/longitude text pasted from Google Maps",
             "Google Maps／利用者入力" if ja else "Google Maps / user input"),
            ("⑧", "緯度" if ja else "Latitude", self.parsed_latitude.get(), "deg",
             "⑧を解析し−90～90°の範囲で確認" if ja else "Parsed from ⑧ and validated within −90 to 90°",
             "⑧ Google Maps座標" if ja else "⑧ Google Maps coordinates"),
            ("⑨", "経度" if ja else "Longitude", self.parsed_longitude.get(), "deg",
             "⑧を解析し−180～180°の範囲で確認" if ja else "Parsed from ⑧ and validated within −180 to 180°",
             "⑧ Google Maps座標" if ja else "⑧ Google Maps coordinates"),
        ]
        for row in rows:
            tree.insert("", "end", values=row)

    def print_module_report(self):
        from core.module_report_ui import _create_module_report
        _create_module_report(self, 0)

    def change_language(self, language):
        host = self.master
        coordinator = None
        while host is not None:
            coordinator = getattr(host, "request_global_language", None)
            if callable(coordinator):
                break
            host = getattr(host, "master", None)
        if callable(coordinator):
            coordinator(language, source=self)
            return
        self._apply_global_language(language)

    def _apply_global_language(self, language):
        self.collect(silent=True)
        self.i18n.set_language(normalize_ui_language(language))
        self.title(self.i18n.t("module0"))
        self.build()

    def refresh_project_from_context(self, _event=None):
        if self.path is None or not self.path.exists():
            return
        try:
            latest = load_project(self.path)
            # Keep the user's unsaved Module 0 form values, but refresh all
            # module outputs, statuses, audit logs and linkage information.
            latest["common"] = dict(self.project.get("common", {}))
            latest["metadata"] = dict(self.project.get("metadata", {}))
            self.project = latest
            if self.project_context is not None:
                self.project_context.project = self.project
        except Exception:
            pass

    def collect(self, silent: bool = False):
        if not self.vars:
            return
        common = self.project["common"]
        metadata = self.project.setdefault("metadata", {})
        metadata["canonical_language"] = CANONICAL_LANGUAGE
        metadata["canonical_schema_version"] = "2.6"
        metadata["ui_language"] = self.i18n.language
        metadata["canonical_contract"] = {
            "internal_language": "en",
            "source_language_policy": "preserve original source text separately",
            "ui_translation_policy": "translate canonical English for display",
            "raw_source_language_fallback": "forbidden",
        }
        for key, var in self.vars.items():
            if key == "project_id":
                continue
            value = var.get().strip()
            if key == "scale_gfa_m2":
                try:
                    common[key] = float(value.replace(",", "")) if value else 0.0
                except ValueError:
                    if not silent:
                        raise
            elif key == "project_number":
                metadata[key] = value
            elif key == "project_location":
                common["project_location"] = value
                # PATCH 571 compatibility mirrors only. project_location is authoritative.
                common["city"] = value
                common["address"] = value
            elif key in ("latitude", "longitude"):
                if value:
                    try:
                        common[key] = float(value)
                    except ValueError:
                        common[key] = value
                else:
                    common[key] = ""
            else:
                common[key] = value

    def validate_coordinates(self) -> tuple[float, float]:
        try:
            latitude = float(self.parsed_latitude.get().strip())
            longitude = float(self.parsed_longitude.get().strip())
        except ValueError as exc:
            raise ValueError(self.i18n.t("invalid_coordinates")) from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError(self.i18n.t("coordinates_range_error"))
        return latitude, longitude

    def open_google_maps(self):
        parts = [
            self.vars.get("project_location", tk.StringVar()).get(),
            self.vars.get("country", tk.StringVar()).get(),
        ]
        query = " ".join(part.strip() for part in parts if part.strip())
        if query:
            url = "https://www.google.com/maps/search/?" + urllib.parse.urlencode({
                "api": "1",
                "query": query,
            })
        else:
            url = "https://www.google.com/maps"
        webbrowser.open(url)

    def parse_coordinate_pair(self, text: str) -> tuple[float, float]:
        cleaned = text.strip().replace("，", ",").replace("、", ",").replace("　", " ")
        parts = [p.strip() for p in cleaned.replace(",", " ").split() if p.strip()]
        if len(parts) != 2:
            raise ValueError(self.i18n.t("invalid_coordinate_pair"))
        try:
            latitude = float(parts[0])
            longitude = float(parts[1])
        except ValueError as exc:
            raise ValueError(self.i18n.t("invalid_coordinate_pair")) from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError(self.i18n.t("coordinates_range_error"))
        return latitude, longitude

    def paste_coordinates(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        source = text.strip()
        self.coordinate_text.set(source)
        if not source:
            return
        try:
            latitude, longitude = self.parse_coordinate_pair(source)
        except ValueError as exc:
            self.parsed_latitude.set("")
            self.parsed_longitude.set("")
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))
            return
        # Keep the original Google Maps value unchanged and show the
        # rounded AZRAS values in separate read-only fields.
        self.parsed_latitude.set(f"{latitude:.8f}")
        self.parsed_longitude.set(f"{longitude:.8f}")

    def apply_coordinates(self):
        try:
            latitude, longitude = self.validate_coordinates()
        except ValueError as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))
            return

        self.collect(silent=True)
        common = self.project["common"]
        common["latitude"] = latitude
        common["longitude"] = longitude
        common["google_coordinate_source"] = self.coordinate_text.get().strip()
        common["location"] = {
            "status": "coordinates_propagated",
            "source": "Google Maps / user-confirmed coordinates",
            "display_name": " ".join(
                part for part in [
                    str(common.get("project_location") or common.get("address") or common.get("city") or "").strip(),
                    str(common.get("country", "")).strip(),
                ] if part
            ),
            "latitude": latitude,
            "longitude": longitude,
            "propagated_to_modules": list(range(10)),
            "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "canonical_language": "en",
        }
        messagebox.showinfo("OK", self.i18n.t("coordinates_propagated"))

    def run_construction_screening(self):
        try:
            latitude, longitude = self.validate_coordinates()
            self.collect(silent=True)
            result = screen_construction_methods(self.root_dir, latitude, longitude, self.project)
            self.project.setdefault("common", {})["construction_feasibility_screening"] = result
        except Exception as exc:
            messagebox.showerror(self.i18n.t("construction_method_screening"), friendly_exception_text(exc,self.i18n.language), parent=self)
            return

        win = tk.Toplevel(self)
        win.title(self.i18n.t("construction_method_screening"))
        fit_window_to_screen(win,1080,620,720,460)
        win.minsize(900, 520)

        evidence = result.get("local_construction_evidence") or {}
        city = evidence.get("nearest_reference_city") or "—"
        distance = evidence.get("distance_km")
        distance_text = "—" if distance is None else f"{float(distance):,.0f} km"
        ttk.Label(
            win,
            text=f"{self.i18n.t('local_construction_evidence')}: {city} / {distance_text} / proxy={evidence.get('proxy_quality','none')}",
            font=("Arial", 11, "bold"),
        ).pack(fill="x", padx=12, pady=(12, 4))
        ttk.Label(
            win,
            text=self.i18n.t("construction_screening_notice"),
            foreground="#8b0000",
            wraplength=1030,
        ).pack(fill="x", padx=12, pady=(0, 8))

        tree = ttk.Treeview(win, columns=("method","status","reason"), show="headings")
        tree.heading("method", text=self.i18n.t("construction_method"))
        tree.heading("status", text=self.i18n.t("screening_status"))
        tree.heading("reason", text=self.i18n.t("screening_reason"))
        tree.column("method", width=230, anchor="w")
        tree.column("status", width=130, anchor="center")
        tree.column("reason", width=650, anchor="w")
        for row in result.get("methods") or []:
            reasons = row.get("reasons_ja") if self.i18n.language == "ja" else row.get("reasons_en")
            tree.insert("", "end", values=(
                row.get("label_ja") if self.i18n.language == "ja" else row.get("label_en"),
                row.get("status"),
                " / ".join(reasons or []),
            ))
        tree.pack(fill="both", expand=True, padx=12, pady=8)

        counts = result.get("counts") or {}
        trace = result.get("regulatory_hazard_trace") or {}
        applied_count = len(trace.get("applied_rules") or [])
        ttk.Label(
            win,
            text=" | ".join(f"{k}: {counts.get(k,0)}" for k in ("Candidate","Conditional","Excluded","Unknown"))
                 + f" | Regulatory/Hazard rules: {applied_count}",
        ).pack(fill="x", padx=12, pady=(0, 4))
        ttk.Label(
            win,
            text=self.i18n.t("regulatory_screening_disclaimer"),
            foreground="#8b0000",
            wraplength=1030,
        ).pack(fill="x", padx=12, pady=(0, 12))

    def copy_location_bundle(self):
        self.collect(silent=True)
        common = self.project.get("common", {})
        metadata = self.project.get("metadata", {})
        lines = [
            f'{self.i18n.t("project_name")}: {common.get("project_name", "")}',
            f'{self.i18n.t("project_id")}: {self.project.get("project_id", "")}',
            f'{self.i18n.t("project_number")}: {metadata.get("project_number", "")}',
            f'{self.i18n.t("country")}: {common.get("country", "")}',
            f'{self.i18n.t("city")}: {common.get("city", "")}',
            f'{self.i18n.t("address")}: {common.get("address", "")}',
            f'{self.i18n.t("latitude")}: {common.get("latitude", "")}',
            f'{self.i18n.t("longitude")}: {common.get("longitude", "")}',
            f'{self.i18n.t("usage")}: {common.get("building_use", "")}',
            f'{self.i18n.t("scale")}: {common.get("scale_gfa_m2", "")}',
        ]
        text = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        messagebox.showinfo("OK", self.i18n.t("copied_to_clipboard"))

    def generate_project_number(self):
        country = self.vars.get("country", tk.StringVar(value="")).get().strip()
        country_code = (
            self.project.get("common", {})
            .get("location", {})
            .get("country_code", "")
        )
        if not country_code:
            country_code = "JP" if country.lower() in ("japan", "日本") else "XX"
        number = f"AZR-{country_code.upper()}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        self.vars["project_number"].set(number)
        self.project.setdefault("metadata", {})["project_number"] = number

    def new(self):
        # A new project must not inherit the previously selected JSON path.
        self.project = new_project()
        self.path = None
        if self.project_context is not None:
            self.project_context.clear(self.project)
        self.vars = {}
        self.coordinate_text.set("")
        self.parsed_latitude.set("")
        self.parsed_longitude.set("")
        self.build()

    def load(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            self.project = load_project(path)
            self.path = Path(path)
            if self.project_context is not None:
                self.project_context.set(self.path, self.project)
            self.vars = {}
            self.build()
        except Exception as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))

    def change_save_directory(self):
        current = find_json_directory(self.root_dir)
        selected = filedialog.askdirectory(
            title="Project JSON・CSV保存先を選択" if self.i18n.language == "ja" else "Select Project JSON/CSV folder",
            initialdir=current,
            mustexist=False,
        )
        if not selected:
            return
        try:
            saved = set_configured_json_directory(selected)
            # Apply the user's explicit selection to the currently open Project
            # as well.  The actual move/copy is performed on the next Save so
            # cancelling or merely changing the preference never mutates files.
            self._save_directory_override = Path(saved) if saved is not None else None
        except Exception as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))
            return
        message = (
            f"Project JSON/CSVの保存先を変更しました。\n\n{saved}\n\n"
            "現在開いているProjectも、次回の『保存』からこの保存先へ保存されます。\n"
            "各物件のProject JSONと全ModuleのCSVは、選択先の一つの『物件名』フォルダーへ保存されます。"
            if self.i18n.language == "ja"
            else f"The Project JSON/CSV save folder was changed.\n\n{saved}\n\n"
                 "The currently open Project will also be saved under this location from the next Save.\n"
                 "Each project's JSON and all module CSV files are stored together in one project folder under the selected location."
        )
        messagebox.showinfo("保存先" if self.i18n.language == "ja" else "Save folder", message)

    def save(self):
        try:
            # Other modules may have updated the same Project JSON after Module 0
            # was opened. Preserve their latest results before saving Module 0.
            latest = None
            if self.path is not None and self.path.exists():
                try:
                    latest = load_project(self.path)
                except Exception:
                    latest = None

            current_common = dict(self.project.get("common", {}))
            current_metadata = dict(self.project.get("metadata", {}))
            if latest is not None:
                latest["common"] = current_common
                latest["metadata"] = current_metadata
                self.project = latest

            self.collect()
            common = self.project["common"]
            common["google_coordinate_source"] = self.coordinate_text.get().strip()
            common.setdefault("location", {})["google_coordinate_raw"] = self.coordinate_text.get().strip()
            latitude_text = self.parsed_latitude.get().strip()
            longitude_text = self.parsed_longitude.get().strip()
            if latitude_text or longitude_text:
                lat, lon = self.validate_coordinates()
                common["latitude"] = lat
                common["longitude"] = lon
                location = common.setdefault("location", {})
                if not location.get("status"):
                    location.update({
                        "status": "manual",
                        "display_name": location.get("display_name", ""),
                        "source": "Manual coordinate input",
                        "latitude": lat,
                        "longitude": lon,
                        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    })
        except ValueError as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))
            return

        if self.path is None:
            json_dir = find_json_directory(self.root_dir)
            path = filedialog.asksaveasfilename(
                initialdir=json_dir,
                initialfile=default_project_filename(self.project),
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
            )
            if not path:
                return
            self.path = unified_project_json_path(path)
        elif self._save_directory_override is not None:
            # The user explicitly changed the save folder while this Project was
            # open. Route the current JSON into that selected base directory.
            # unified_project_json_path() then creates/reuses the one-property
            # bundle folder below it. The old JSON is intentionally left intact.
            self.path = unified_project_json_path(
                self._save_directory_override / self.path.name
            )
            self._save_directory_override = None
        else:
            # Existing projects are migrated non-destructively into the unified
            # property folder on the next Module 0 save. The old JSON remains
            # untouched as a fallback copy.
            target = unified_project_json_path(self.path)
            if target.resolve() != self.path.resolve():
                self.path = target
        # PATCH_043: a comparison copy's project information is not edited
        # (a Module 0 save may also relocate the file out of the Compare folder).
        _blocked = comparison_copy_block_reason(self.project, "module0", self.i18n.language)
        if _blocked:
            messagebox.showwarning("AZRAS", _blocked)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        save_project(self.project, self.path)
        project_output_directory(self.path, 0)
        if self.project_context is not None:
            self.project_context.set(self.path, self.project)
        messagebox.showinfo(self.i18n.t("saved"), str(self.path))
