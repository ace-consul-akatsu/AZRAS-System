from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.i18n import I18N
from core.project_store import save_project
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from core.branding import COMPANY_EN, COMPANY_JA


class DetailedConfigurationApp(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language="ja", project_context=None):
        super().__init__(master)
        self.root_dir = Path(root_dir)
        self.project_context = project_context
        self.i18n = I18N(self.root_dir, language)
        self.data = json.loads(
            (self.root_dir / "data" / "detailed_building_classification_v1_1.json")
            .read_text(encoding="utf-8")
        )
        self.project = None
        self.path = None
        if project_context is not None and project_context.path is not None:
            self.project = project_context.reload()
            self.path = project_context.path

        self.vars = {
            "building_system": tk.StringVar(value="general"),
            "general_structure": tk.StringVar(),
            "general_method": tk.StringVar(),
            "core_structure": tk.StringVar(value="rc"),
            "core_method": tk.StringVar(value="cast_in_place"),
            "infill_structure": tk.StringVar(value="wood_frame"),
            "infill_method": tk.StringVar(value="2x6"),
            "outfill_wall_structure": tk.StringVar(value="wood"),
            "outfill_wall_method": tk.StringVar(value="timber_cladding"),
            "outfill_roof_structure": tk.StringVar(value="wood"),
            "outfill_roof_method": tk.StringVar(value="timber_truss"),
            "prefabrication_type": tk.StringVar(value="none"),
            "interior_substrate": tk.StringVar(),
            "interior_partition": tk.StringVar(),
            "insulation_position": tk.StringVar(),
            "exterior_finish": tk.StringVar(),
            "interior_finish": tk.StringVar(),
            "notes": tk.StringVar(),
        }
        self._combo_bindings = {}

        self.title(self.t("title"))
        self.geometry("1260x900")
        self.minsize(1050, 760)
        self._build()
        self._restore()
        self._refresh_all()
        self._update_summary()

    def t(self, key):
        ja = {
            "title": "詳細構造・工法・部位構成",
            "notice": "選択内容はProject JSONへ保存され、Integrated_Comparisonの詳細比較に使用されます。",
            "system": "建築システム",
            "general": "一般建築",
            "azras": "AZRAS Platform",
            "general_structure": "構造",
            "general_method": "工法詳細",
            "core": "Core構造",
            "core_method": "Core工法詳細",
            "infill": "Infill構造",
            "infill_method": "Infill工法詳細",
            "wall": "Outfill（外壁）構造",
            "wall_method": "Outfill（外壁）工法詳細",
            "roof": "Outfill（屋根）構造",
            "roof_method": "Outfill（屋根）工法詳細",
            "prefab": "プレハブ化区分",
            "assembly": "内部・断熱・仕上げ",
            "substrate": "内装下地",
            "partition": "内部間仕切り",
            "insulation": "断熱位置",
            "exterior": "外装仕上げ",
            "interior": "内装仕上げ",
            "notes": "備考",
            "summary": "現在の選択内容",
            "save": "Project JSONを更新保存",
            "print": "このModuleを印刷",
            "print_title": "詳細構造・工法・部位構成",
            "print_saved": "PDFを保存しました。",
            "print_error": "印刷用PDFを作成できませんでした。",
            "no_project": "先に共通プロジェクト・基本条件でProject JSONを新規保存または読み込んでください。",
            "saved": "詳細構造・工法・部位構成を同じProject JSONへ保存しました。",
            "required": "構造または工法詳細が未選択です。",
        }
        en = {
            "title": "Detailed Structure, Method and Assemblies",
            "notice": "Selections are saved to the Project JSON and used by Integrated_Comparison.",
            "system": "Building System",
            "general": "General Building",
            "azras": "AZRAS Platform",
            "general_structure": "Structure",
            "general_method": "Construction Method",
            "core": "Core Structure",
            "core_method": "Core Method",
            "infill": "Infill Structure",
            "infill_method": "Infill Method",
            "wall": "Outfill Wall Structure",
            "wall_method": "Outfill Wall Method",
            "roof": "Outfill Roof Structure",
            "roof_method": "Outfill Roof Method",
            "prefab": "Prefabrication Type",
            "assembly": "Interior, Insulation and Finishes",
            "substrate": "Interior Substrate",
            "partition": "Interior Partition",
            "insulation": "Insulation Position",
            "exterior": "Exterior Finish",
            "interior": "Interior Finish",
            "notes": "Notes",
            "summary": "Current Selection",
            "save": "Update and Save Project JSON",
            "print": "Print This Module",
            "print_title": "Detailed Structure, Method and Assemblies",
            "print_saved": "The PDF was saved.",
            "print_error": "The print PDF could not be created.",
            "no_project": "Create or load a Project JSON in Common Project and Basic Conditions first.",
            "saved": "The detailed structure, method and assemblies were saved to the active Project JSON.",
            "required": "A required structure or method is not selected.",
        }
        return (ja if self.i18n.language == "ja" else en).get(key, key)

    def _items(self, section, key=None):
        source = self.data.get(section, {})
        if key is not None:
            source = source.get(key, [])
        lang = self.i18n.language
        return [(item["id"], item.get(lang, item["id"])) for item in source]

    def _make_combo(self, parent, row, label, var_key, options, callback=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=8, pady=6, sticky="e")
        display = tk.StringVar()
        combo = ttk.Combobox(parent, textvariable=display, state="readonly", width=42)
        combo.grid(row=row, column=1, padx=8, pady=6, sticky="w")
        self._combo_bindings[var_key] = (combo, display)
        self._set_combo(var_key, options)
        def changed(_event=None):
            combo_widget, display_var = self._combo_bindings[var_key]
            mapping = getattr(combo_widget, "_azras_mapping", {})
            self.vars[var_key].set(mapping.get(display_var.get(), ""))
            if callback:
                callback()
            self._update_summary()
        combo.bind("<<ComboboxSelected>>", changed)
        return combo

    def _set_combo(self, var_key, options):
        combo, display = self._combo_bindings[var_key]
        ids = [item[0] for item in options]
        names = [item[1] for item in options]
        mapping = dict(zip(names, ids))
        reverse = dict(zip(ids, names))
        combo._azras_mapping = mapping
        combo.configure(values=names)
        current = self.vars[var_key].get()
        if current not in ids:
            current = ids[0] if ids else ""
            self.vars[var_key].set(current)
        display.set(reverse.get(current, ""))

    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        topbar = ttk.Frame(outer)
        topbar.pack(fill="x", pady=(2, 4))

        ttk.Label(
            topbar,
            text=self.t("title"),
            font=("Yu Gothic UI", 18, "bold"),
        ).pack(side="left", padx=(4, 12))

        ttk.Button(
            topbar,
            text=self.t("print"),
            style="Primary.TButton",
            command=self.print_module,
        ).pack(side="right", padx=4)

        ttk.Button(
            topbar,
            text=self.t("save"),
            command=self.save,
        ).pack(side="right", padx=4)

        ttk.Label(
            outer,
            text=self.t("notice"),
            foreground="#8b0000",
            wraplength=1160,
        ).pack(fill="x", pady=(0, 8))

        system = ttk.LabelFrame(outer, text=self.t("system"))
        system.pack(fill="x", pady=5)
        ttk.Radiobutton(
            system, text=self.t("general"), variable=self.vars["building_system"],
            value="general", command=self._toggle
        ).pack(side="left", padx=24, pady=8)
        ttk.Radiobutton(
            system, text=self.t("azras"), variable=self.vars["building_system"],
            value="azras", command=self._toggle
        ).pack(side="left", padx=24, pady=8)

        columns = ttk.Frame(outer)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=1)
        columns.columnconfigure(1, weight=1)

        self.general_frame = ttk.LabelFrame(columns, text=self.t("general"))
        self.general_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self._make_combo(
            self.general_frame, 0, self.t("general_structure"), "general_structure",
            self._items("structures", "general"), self._refresh_general_method
        )
        self._make_combo(
            self.general_frame, 1, self.t("general_method"), "general_method", []
        )

        self.azras_frame = ttk.LabelFrame(columns, text=self.t("azras"))
        self.azras_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        self._make_combo(
            self.azras_frame, 0, self.t("core"), "core_structure",
            self._items("structures", "azras_core"), self._refresh_core_method
        )
        self._make_combo(self.azras_frame, 1, self.t("core_method"), "core_method", [])
        self._make_combo(
            self.azras_frame, 2, self.t("infill"), "infill_structure",
            self._items("structures", "azras_infill"), self._refresh_infill_method
        )
        self._make_combo(self.azras_frame, 3, self.t("infill_method"), "infill_method", [])
        self._make_combo(
            self.azras_frame, 4, self.t("wall"), "outfill_wall_structure",
            self._items("structures", "outfill_wall"), self._refresh_wall_method
        )
        self._make_combo(self.azras_frame, 5, self.t("wall_method"), "outfill_wall_method", [])
        self._make_combo(
            self.azras_frame, 6, self.t("roof"), "outfill_roof_structure",
            self._items("structures", "outfill_roof"), self._refresh_roof_method
        )
        self._make_combo(self.azras_frame, 7, self.t("roof_method"), "outfill_roof_method", [])
        self._make_combo(
            self.azras_frame, 8, self.t("prefab"), "prefabrication_type",
            self._items("prefabrication_types")
        )

        assembly = ttk.LabelFrame(outer, text=self.t("assembly"))
        assembly.pack(fill="x", pady=5)
        substrate = [(x["id"], x[self.i18n.language]) for x in self.data["interior_substrates"]]
        partitions = [(x["id"], x[self.i18n.language]) for x in self.data["interior_partition_systems"]]
        insulation = [(x["id"], x[self.i18n.language]) for x in self.data["insulation_positions"]]
        self._make_combo(assembly, 0, self.t("substrate"), "interior_substrate", substrate)
        self._make_combo(assembly, 1, self.t("partition"), "interior_partition", partitions)
        self._make_combo(assembly, 2, self.t("insulation"), "insulation_position", insulation)

        ttk.Label(assembly, text=self.t("exterior")).grid(row=0, column=2, padx=8, pady=6, sticky="e")
        ttk.Entry(assembly, textvariable=self.vars["exterior_finish"], width=38).grid(row=0, column=3, padx=8, pady=6)
        ttk.Label(assembly, text=self.t("interior")).grid(row=1, column=2, padx=8, pady=6, sticky="e")
        ttk.Entry(assembly, textvariable=self.vars["interior_finish"], width=38).grid(row=1, column=3, padx=8, pady=6)
        ttk.Label(assembly, text=self.t("notes")).grid(row=2, column=2, padx=8, pady=6, sticky="e")
        ttk.Entry(assembly, textvariable=self.vars["notes"], width=58).grid(row=2, column=3, padx=8, pady=6)

        summary_frame = ttk.LabelFrame(outer, text=self.t("summary"))
        summary_frame.pack(fill="both", expand=True, pady=5)
        self.summary_text = tk.Text(summary_frame, height=8, wrap="word", state="disabled")
        self.summary_text.pack(fill="both", expand=True, padx=6, pady=6)


    def _refresh_general_method(self):
        self._set_combo("general_method", self._items("methods", self.vars["general_structure"].get()))

    def _refresh_core_method(self):
        self._set_combo("core_method", self._items("core_methods", self.vars["core_structure"].get()))

    def _refresh_infill_method(self):
        self._set_combo("infill_method", self._items("methods", self.vars["infill_structure"].get()))

    def _refresh_wall_method(self):
        self._set_combo(
            "outfill_wall_method",
            self._items("outfill_wall_methods", self.vars["outfill_wall_structure"].get())
        )

    def _refresh_roof_method(self):
        self._set_combo(
            "outfill_roof_method",
            self._items("outfill_roof_methods", self.vars["outfill_roof_structure"].get())
        )

    def _refresh_all(self):
        self._refresh_general_method()
        self._refresh_core_method()
        self._refresh_infill_method()
        self._refresh_wall_method()
        self._refresh_roof_method()
        self._toggle()

    def _toggle(self):
        general = self.vars["building_system"].get() == "general"
        for child in self.general_frame.winfo_children():
            try:
                child.configure(state="normal" if general else "disabled")
            except tk.TclError:
                pass
        for child in self.azras_frame.winfo_children():
            try:
                child.configure(state="disabled" if general else "normal")
            except tk.TclError:
                pass
        self._update_summary()

    def _label(self, section, key, value):
        items = self.data.get(section, {}).get(key, []) if key is not None else self.data.get(section, [])
        for item in items:
            if item.get("id") == value:
                return item.get(self.i18n.language, value)
        return value or "-"

    def _method_label(self, section, structure, value):
        return self._label(section, structure, value)

    def _update_summary(self):
        if not hasattr(self, "summary_text"):
            return
        if self.vars["building_system"].get() == "general":
            lines = [
                f'{self.t("system")}: {self.t("general")}',
                f'{self.t("general_structure")}: {self._label("structures", "general", self.vars["general_structure"].get())}',
                f'{self.t("general_method")}: {self._method_label("methods", self.vars["general_structure"].get(), self.vars["general_method"].get())}',
            ]
        else:
            lines = [
                f'{self.t("system")}: {self.t("azras")}',
                f'{self.t("core")}: {self._label("structures", "azras_core", self.vars["core_structure"].get())}',
                f'{self.t("core_method")}: {self._method_label("core_methods", self.vars["core_structure"].get(), self.vars["core_method"].get())}',
                f'{self.t("infill")}: {self._label("structures", "azras_infill", self.vars["infill_structure"].get())}',
                f'{self.t("infill_method")}: {self._method_label("methods", self.vars["infill_structure"].get(), self.vars["infill_method"].get())}',
                f'{self.t("wall")}: {self._label("structures", "outfill_wall", self.vars["outfill_wall_structure"].get())}',
                f'{self.t("wall_method")}: {self._method_label("outfill_wall_methods", self.vars["outfill_wall_structure"].get(), self.vars["outfill_wall_method"].get())}',
                f'{self.t("roof")}: {self._label("structures", "outfill_roof", self.vars["outfill_roof_structure"].get())}',
                f'{self.t("roof_method")}: {self._method_label("outfill_roof_methods", self.vars["outfill_roof_structure"].get(), self.vars["outfill_roof_method"].get())}',
                f'{self.t("prefab")}: {self._label("prefabrication_types", None, self.vars["prefabrication_type"].get())}',
            ]
        lines += [
            f'{self.t("substrate")}: {self._label("interior_substrates", None, self.vars["interior_substrate"].get())}',
            f'{self.t("partition")}: {self._label("interior_partition_systems", None, self.vars["interior_partition"].get())}',
            f'{self.t("insulation")}: {self._label("insulation_positions", None, self.vars["insulation_position"].get())}',
        ]
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", "\n".join(lines))
        self.summary_text.configure(state="disabled")

    def _restore(self):
        if not self.project:
            return
        cfg = (self.project.get("common") or {}).get("detailed_configuration") or {}
        self.vars["building_system"].set(cfg.get("building_system", "general"))
        general = cfg.get("general") or {}
        azras = cfg.get("azras") or {}
        assemblies = cfg.get("assemblies") or {}
        restore_map = {
            "general_structure": general.get("structure", ""),
            "general_method": general.get("method", ""),
            "core_structure": azras.get("core_structure", "rc"),
            "core_method": azras.get("core_method", "cast_in_place"),
            "infill_structure": azras.get("infill_structure", "wood_frame"),
            "infill_method": azras.get("infill_method", "2x6"),
            "outfill_wall_structure": azras.get("outfill_wall_structure", "wood"),
            "outfill_wall_method": azras.get("outfill_wall_method", "timber_cladding"),
            "outfill_roof_structure": azras.get("outfill_roof_structure", "wood"),
            "outfill_roof_method": azras.get("outfill_roof_method", "timber_truss"),
            "prefabrication_type": azras.get(
                "prefabrication_type",
                "partial" if azras.get("prefabrication") else "none"
            ),
            "interior_substrate": assemblies.get("interior_substrate", ""),
            "interior_partition": assemblies.get("interior_partition", ""),
            "insulation_position": assemblies.get("insulation_position", ""),
            "exterior_finish": assemblies.get("exterior_finish", ""),
            "interior_finish": assemblies.get("interior_finish", ""),
            "notes": assemblies.get("notes", ""),
        }
        for key, value in restore_map.items():
            self.vars[key].set(value)

    def print_module(self):
        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title=self.t("print"),
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile=(
                    "詳細構造・工法・部位構成.pdf"
                    if self.i18n.language == "ja"
                    else "Detailed_Structure_Method_Assemblies.pdf"
                ),
            )
            if not path:
                return

            try:
                pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
                font_name = "HeiseiKakuGo-W5"
            except Exception:
                font_name = "Helvetica"

            c = canvas.Canvas(path, pagesize=A4)
            width, height = A4
            margin = 42

            def draw_footer(page_number: int) -> None:
                c.setFont(font_name, 7)
                c.setFillColorRGB(0.4, 0.4, 0.4)
                c.drawRightString(width - margin, 24, f"{COMPANY_EN} / {COMPANY_JA}")
                c.drawString(margin, 24, f"Page {page_number}")
                c.setFillColorRGB(0, 0, 0)

            page_number = 1
            y = height - 52

            c.setFont(font_name, 16)
            c.drawString(margin, y, self.t("print_title"))
            y -= 28

            c.setFont(font_name, 9)
            c.drawString(margin, y, self.t("notice"))
            y -= 24

            summary = self.summary_text.get("1.0", "end").strip()
            lines = summary.splitlines() if summary else ["-"]

            c.setFont(font_name, 10)
            for line in lines:
                if y < 55:
                    draw_footer(page_number)
                    c.showPage()
                    page_number += 1
                    c.setFont(font_name, 10)
                    y = height - 52
                c.drawString(margin, y, line[:90])
                y -= 17

            draw_footer(page_number)
            c.save()
            messagebox.showinfo(
                self.t("title"),
                self.t("print_saved"),
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror(
                self.t("title"),
                f'{self.t("print_error")}\n{exc}',
                parent=self,
            )

    def save(self):
        if self.project_context is None or self.project_context.path is None:
            messagebox.showwarning(self.t("title"), self.t("no_project"), parent=self)
            return

        system = self.vars["building_system"].get()
        if system == "general":
            required = ("general_structure", "general_method")
        else:
            required = (
                "core_structure", "core_method", "infill_structure", "infill_method",
                "outfill_wall_structure", "outfill_wall_method",
                "outfill_roof_structure", "outfill_roof_method",
            )
        if any(not self.vars[key].get() for key in required):
            messagebox.showwarning(self.t("title"), self.t("required"), parent=self)
            return

        self.project = self.project_context.reload()
        self.path = self.project_context.path
        common = self.project.setdefault("common", {})
        common["analysis_mode"] = "pro"
        common["detailed_configuration"] = {
            "schema_version": "2.0",
            "building_system": system,
            "general": {
                "structure": self.vars["general_structure"].get(),
                "method": self.vars["general_method"].get(),
            },
            "azras": {
                "core_structure": self.vars["core_structure"].get(),
                "core_method": self.vars["core_method"].get(),
                "infill_structure": self.vars["infill_structure"].get(),
                "infill_method": self.vars["infill_method"].get(),
                "outfill_wall_structure": self.vars["outfill_wall_structure"].get(),
                "outfill_wall_method": self.vars["outfill_wall_method"].get(),
                "outfill_roof_structure": self.vars["outfill_roof_structure"].get(),
                "outfill_roof_method": self.vars["outfill_roof_method"].get(),
                "prefabrication_type": self.vars["prefabrication_type"].get(),
                "prefabrication": self.vars["prefabrication_type"].get() != "none",
            },
            "assemblies": {
                "interior_substrate": self.vars["interior_substrate"].get(),
                "interior_partition": self.vars["interior_partition"].get(),
                "insulation_position": self.vars["insulation_position"].get(),
                "exterior_finish": self.vars["exterior_finish"].get().strip(),
                "interior_finish": self.vars["interior_finish"].get().strip(),
                "notes": self.vars["notes"].get().strip(),
            },
            "status": "configured",
        }
        save_project(self.project, self.path)
        self.project_context.set(self.path, self.project)
        messagebox.showinfo(self.t("title"), self.t("saved"), parent=self)
