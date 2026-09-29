
from __future__ import annotations
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from services.project_export_paths import default_export_path, project_output_directory

from core.i18n import I18N, LANGUAGE_OPTIONS
from core.error_text import friendly_exception_text
from core.csv_export import write_dict_rows_csv
from core.ui_style import (apply_common_style, standardize_module_window, create_scrollable_pane_split, add_module_text_copy_button)
from core.module_report_ui import attach_module_report_button
from core.project_store import load_project, save_project
from core.project_coordinator import update_module_and_propagate, format_report
from core.number_format import format_number, header_with_unit
from core.line_chart import LineChart
from ui.editable_remarks import bind_editable_remarks, merge_note
from services.long_term_environment_engine_v9_3 import evaluate_long_term_environment
from services.grid_decarbonization_scenarios import GRID_DECARBONIZATION_SCENARIOS

INPUT_BG="#fff4b8"
AUTO_BG="#d9efff"
RESULT_BG="#dff3df"

def _f(value, default=0.0):
    """Safely convert a value to float for Module 4 display formatting."""
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)

class Module4App(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language: str = "ja", project_context=None):
        super().__init__(master)
        apply_common_style(self)
        standardize_module_window(self,4)
        self.project_context = project_context
        self.root_dir=Path(root_dir)
        self.i18n=I18N(self.root_dir,language)
        self.project=None
        self.project_path=None
        self.result=None
        self.user_notes={}
        self.project_file=tk.StringVar()
        self.period=tk.StringVar(value="200")
        self.operational_change=tk.StringVar(value="0")
        self.grid_scenario=tk.StringVar(value="standard")
        self.grid_change=tk.StringVar(value="-0.5")
        self.future_climate_enabled=tk.BooleanVar(value=False)
        self.future_warming_100=tk.StringVar(value="0.0")
        self.future_warming_200=tk.StringVar(value="0.0")
        self.future_climate_interval=tk.StringVar(value="20")
        self.include_biogenic=tk.BooleanVar(value=True)
        self.include_credit=tk.BooleanVar(value=True)
        self.factors=json.loads(
            (self.root_dir/"data"/"environmental_lca_factors_v9_3.json")
            .read_text(encoding="utf-8"))
        if self.project_context is not None and self.project_context.path is not None:
            self.project = self.project_context.reload()
            self.project_path = self.project_context.path
            self.project_file.set(self.project_context.display_path)
        self.title(self.i18n.t("module4"))
        self.build();attach_module_report_button(self,4)
        self.restore_saved_state()
        if self.project is not None:
            m3=self.project.get("module_outputs",{}).get("module3") or {}
            if m3.get("period_years"): self.period.set(str(m3["period_years"]))
        self.bind("<FocusIn>", self.refresh_project_from_context)

    def refresh_project_from_context(self, event=None):
        """Use only the Project JSON selected or created in Module 0."""
        if self.project_context is None or self.project_context.path is None:
            return False
        active_path = self.project_context.path
        current_path = getattr(self, "project_path", None)
        if current_path is None or Path(current_path) != Path(active_path):
            self.project = self.project_context.reload()
            self.project_path = active_path
            if hasattr(self, "project_file"):
                self.project_file.set(self.project_context.display_path)
        elif self.project is None:
            self.project = self.project_context.reload()
        return True

    def build(self):
        for w in self.winfo_children():
            w.destroy()
        top=ttk.Frame(self)
        top.pack(fill="x",padx=10,pady=6)
        t=self.i18n.t

        add_module_text_copy_button(self,top)
        ttk.Label(top,text=t("language")).pack(side="left")
        lang=tk.StringVar(value="日本語" if self.i18n.language=="ja" else "English")
        cb=ttk.Combobox(top,textvariable=lang,values=LANGUAGE_OPTIONS,
                        state="readonly",width=12)
        cb.pack(side="left",padx=5)
        cb.bind("<<ComboboxSelected>>",
                lambda e:self.change_language("ja" if lang.get()=="日本語" else "en"))



        ttk.Button(
            top, text=t("print_this_module"), style="Primary.TButton",
            command=lambda: self.print_module_report()
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_module4"), command=self.save_output
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_event_csv"), command=self.save_event_csv
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_annual_csv"), command=self.save_annual_csv
        ).pack(side="right", padx=4)

        # 画面を「長期環境評価を実行」ボタンの上で2分割する。
        # 上段＝プロジェクト選択・環境評価条件・実行ボタン（コンパクトな入力欄）、
        # 下段＝結果テーブル・グラフ・LCAモジュール区分クロスウォーク（画面の
        # 大部分を占め、常に見えている状態にする）。それぞれ独立してスクロール
        # するため、下段に何があるか気づかない、ということが起きにくい。
        split,upper,lower=create_scrollable_pane_split(self,upper_weight=2,lower_weight=5,initial_upper_fraction=0.34)

        project=ttk.LabelFrame(upper,text=t("project"))
        project.pack(fill="x",padx=10,pady=5)
        ttk.Label(project,text=t("project_json")).grid(row=0,column=0,padx=5,pady=4)
        tk.Entry(project,textvariable=self.project_file,width=108,state="readonly",readonlybackground=AUTO_BG).grid(
            row=0,column=1,padx=5,pady=4,sticky="ew")
        project.columnconfigure(1,weight=1)

        conditions=ttk.LabelFrame(upper,text=t("lca_conditions"))
        conditions.pack(fill="x",padx=10,pady=5)
        fields=[
            (t("evaluation_period"),self.period),
            (t("operational_change"),self.operational_change),
            (t("grid_decarbonization"),self.grid_change)
        ]
        for i,(label,var) in enumerate(fields):
            ttk.Label(conditions,text=label).grid(row=0,column=i*2,padx=5,pady=5)
            if var is self.period:
                tk.Entry(
                    conditions,textvariable=var,width=13,state="readonly",
                    readonlybackground=AUTO_BG
                ).grid(row=0,column=i*2+1,padx=5,pady=5)
            else:
                tk.Entry(conditions,textvariable=var,bg=INPUT_BG,width=13).grid(
                    row=0,column=i*2+1,padx=5,pady=5)
        ttk.Label(conditions,text=t("grid_decarbonization_scenario")).grid(row=4,column=0,padx=5,pady=4)
        self.grid_scenario_combo=ttk.Combobox(
            conditions,textvariable=self.grid_scenario,state="readonly",width=14,
            values=["low","standard","high","custom"]
        )
        self.grid_scenario_combo.grid(row=4,column=1,padx=5,pady=4,sticky="w")
        self.grid_scenario_combo.bind("<<ComboboxSelected>>",self.on_grid_scenario_changed)
        ttk.Label(
            conditions,text=t("grid_scenario_notice"),foreground="#555555",wraplength=760
        ).grid(row=4,column=2,columnspan=4,padx=5,pady=4,sticky="w")

        ttk.Checkbutton(
            conditions,text=t("future_climate_8760"),
            variable=self.future_climate_enabled
        ).grid(row=1,column=0,columnspan=2,padx=5,pady=4,sticky="w")
        ttk.Label(conditions,text=t("future_warming_100")).grid(row=1,column=2,padx=5,pady=4)
        tk.Entry(conditions,textvariable=self.future_warming_100,bg=INPUT_BG,width=10).grid(row=1,column=3,padx=5,pady=4)
        ttk.Label(conditions,text=t("future_warming_200")).grid(row=1,column=4,padx=5,pady=4)
        tk.Entry(conditions,textvariable=self.future_warming_200,bg=INPUT_BG,width=10).grid(row=1,column=5,padx=5,pady=4)
        ttk.Label(conditions,text=t("future_climate_interval")).grid(row=2,column=0,padx=5,pady=4)
        tk.Entry(conditions,textvariable=self.future_climate_interval,bg=INPUT_BG,width=10).grid(row=2,column=1,padx=5,pady=4)
        ttk.Label(
            conditions,text=t("future_climate_notice"),foreground="#8b0000",
            wraplength=920
        ).grid(row=2,column=2,columnspan=4,padx=5,pady=4,sticky="w")

        ttk.Checkbutton(conditions,text=t("include_biogenic"),
                        variable=self.include_biogenic).grid(row=3,column=0,columnspan=3,padx=5,pady=4,sticky="w")
        ttk.Checkbutton(conditions,text=t("include_recycling_credit"),
                        variable=self.include_credit).grid(row=3,column=3,columnspan=2,padx=5,pady=4,sticky="w")
        ttk.Button(conditions,text=t("edit_lca_factors"),
                   command=self.edit_factors).grid(row=3,column=5,padx=8,pady=4)

        ttk.Label(upper,text=t("lca_factor_notice"),foreground="#8b0000",
                  wraplength=1480).pack(fill="x",padx=12,pady=(3,1))
        ttk.Label(upper,text=t("system_boundary_notice"),foreground="#8b0000",
                  wraplength=1480).pack(fill="x",padx=12,pady=(1,4))
        ttk.Button(upper,text=t("calculate_lca"),command=self.calculate).pack(pady=6,ipady=5)

        # PATCH 195: PATCH 194 moved the result area into a scrollable lower canvas,
        # but a Panedwindow packed with only fill/expand has almost no requested height
        # inside that canvas.  It can therefore collapse to ~1 px and make calculated
        # results look as if they disappeared.  Give the result block an explicit
        # requested height; the lower canvas then scrolls the complete output area.
        body=ttk.Panedwindow(lower,orient="horizontal",height=420)
        body.pack(fill="both",expand=True,padx=0,pady=5)
        results=ttk.LabelFrame(body,text=t("lca_result"))
        timeline=ttk.LabelFrame(body,text=t("annual_timeline"))
        body.add(results,weight=2)
        body.add(timeline,weight=3)

        ttk.Label(
            results,
            text=(
                '【重要】本結果は、Module 1「図面解析・数量計算」で得られた数量を基に算定しています。通常表示の確定数量と黄色表示の暫定・想定数量はCO₂計算に含まれます。一方、Module 1で数量を算出できず赤表示となっている未積算項目は本結果に含まれません。未積算項目を人間が確認・追加入力したうえで再計算し、最終判断してください。未積算項目の内容によっては、CO₂排出量・LCA結果が大きく変わる場合があります。'
                if self.i18n.language=="ja" else
                'IMPORTANT: This result is calculated from quantities obtained in Module 1 Drawing Analysis / Quantity Calculation. Confirmed quantities and yellow provisional/assumed quantities are included in the CO2 calculation. Red items whose quantities could not be determined in Module 1 are not included. Have a human verify and add any unquantified items, then recalculate before making a final decision. Those omitted items may materially change CO2 emissions and LCA results.'
            ),
            foreground="#8b0000", wraplength=1100, justify="left"
        ).grid(row=0,column=0,columnspan=2,sticky="ew",padx=6,pady=(6,2))

        self.summary_tree=ttk.Treeview(
            results,
            columns=("no","item","value","unit","calculation_basis","reference_source"),
            show="headings",
        )
        summary_columns = [
            ("no", "No.", 55, "center"),
            ("item", t("item"), 285, "w"),
            ("value", t("value"), 145, "e"),
            ("unit", t("unit"), 105, "w"),
            ("calculation_basis", t("calculation_basis"), 430, "w"),
            ("reference_source", t("reference_source"), 300, "w"),
        ]
        for col, label, width, anchor in summary_columns:
            self.summary_tree.heading(col, text=label)
            self.summary_tree.column(col, width=width, anchor=anchor)
        sy = ttk.Scrollbar(results, orient="vertical", command=self.summary_tree.yview)
        sx = ttk.Scrollbar(results, orient="horizontal", command=self.summary_tree.xview)
        self.summary_tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.summary_tree.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=(2, 0))
        sy.grid(row=1, column=1, sticky="ns", pady=(2, 0))
        sx.grid(row=2, column=0, sticky="ew", padx=(6, 0), pady=(0, 6))
        results.rowconfigure(1, weight=1)
        results.columnconfigure(0, weight=1)

        cols=("year","annual_co2","cumulative_co2","annual_energy","cumulative_energy",
              "waste","reuse","recycle","landfill")
        self.timeline_tree=ttk.Treeview(timeline,columns=cols,show="headings")
        headings={
            "year":header_with_unit(t("year"), t("year_label")),"annual_co2":header_with_unit(t("annual_co2"),"kg-CO₂"),
            "cumulative_co2":header_with_unit(t("cumulative_co2"),"kg-CO₂"),
            "annual_energy":header_with_unit(t("annual_energy"),"MJ"),
            "cumulative_energy":header_with_unit(t("cumulative_energy"),"MJ"),
            "waste":header_with_unit(t("waste"),"kg"),"reuse":header_with_unit(t("reuse"),"kg"),
            "recycle":header_with_unit(t("recycle"),"kg"),"landfill":header_with_unit(t("landfill"),"kg")
        }
        widths={"year":65,"annual_co2":125,"cumulative_co2":135,
                "annual_energy":130,"cumulative_energy":145,
                "waste":100,"reuse":90,"recycle":100,"landfill":95}
        for col in cols:
            self.timeline_tree.heading(col,text=headings[col])
            self.timeline_tree.column(col,width=widths[col],anchor="e")
        y=ttk.Scrollbar(timeline,orient="vertical",command=self.timeline_tree.yview)
        x=ttk.Scrollbar(timeline,orient="horizontal",command=self.timeline_tree.xview)
        self.timeline_tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        self.timeline_tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        timeline.rowconfigure(0,weight=1)
        timeline.columnconfigure(0,weight=1)
        crosswalk_row=ttk.Panedwindow(lower,orient="horizontal",height=420)
        crosswalk_row.pack(fill="both",expand=True,padx=0,pady=(2,6))

        module_map=ttk.LabelFrame(crosswalk_row,text=t("lca_module_crosswalk"))
        graph=ttk.LabelFrame(
            crosswalk_row,
            text=("累積CO₂排出量グラフ" if self.i18n.language=="ja" else "Cumulative CO2 Graph"),
        )
        crosswalk_row.add(module_map,weight=3)
        crosswalk_row.add(graph,weight=2)

        ttk.Label(
            module_map,text=t("lca_module_crosswalk_notice"),foreground="#555555",
            wraplength=1000
        ).pack(fill="x",padx=6,pady=(4,2))
        self.lca_module_tree=ttk.Treeview(
            module_map,
            columns=("module","stage","co2","energy","resolution"),
            show="headings",height=5
        )
        for c,label,w,anchor in [
            ("module",t("lca_module"),90,"center"),
            ("stage",t("lca_stage"),260,"w"),
            ("co2",t("lca_co2"),130,"e"),
            ("energy",t("lca_energy"),130,"e"),
            ("resolution",t("lca_resolution"),150,"w"),
        ]:
            self.lca_module_tree.heading(c,text=label)
            self.lca_module_tree.column(c,width=w,anchor=anchor)
        my=ttk.Scrollbar(module_map,orient="vertical",command=self.lca_module_tree.yview)
        mx=ttk.Scrollbar(module_map,orient="horizontal",command=self.lca_module_tree.xview)
        self.lca_module_tree.configure(yscrollcommand=my.set,xscrollcommand=mx.set)
        self.lca_module_tree.pack(fill="both",expand=True,padx=(6,0),pady=(0,0),side="left")
        my.pack(side="left",fill="y",pady=(0,0))
        mx.pack(fill="x",padx=6,pady=(0,6))

        self.co2_chart=LineChart(graph,height=380)
        self.co2_chart.pack(fill="both",expand=True,padx=5,pady=(4,2))
        ttk.Label(
            graph,
            text=(
                "【ご注意】\n"
                "・同一EPW（8760時間）の運用値＋建設・更新・解体イベントCO₂を統合した年次累積です。\n"
                "・電力CO₂係数は地域別設定値を使用します。\n"
                "・税金（炭素税等）は含めていません。"
                if self.i18n.language=="ja" else
                "[Note]\n"
                "• Annual cumulative value combining the same EPW (8760-hour) operational value with\n"
                "  construction/renewal/demolition event CO2.\n"
                "• Uses the region-specific electricity CO2 factor.\n"
                "• Taxes (e.g. carbon tax) are not included."
            ),
            foreground="#d00000",wraplength=420,justify="left",font=("Yu Gothic UI",8),
        ).pack(fill="x",padx=8,pady=(2,8))


    def on_grid_scenario_changed(self,event=None):
        key=self.grid_scenario.get().strip().lower()
        row=GRID_DECARBONIZATION_SCENARIOS.get(key) or {}
        value=row.get("annual_change_pct")
        if value is not None:
            self.grid_change.set(str(value))

    def restore_saved_state(self):
        if self.project is None:
            return
        saved = self.project.get("module_outputs", {}).get("module4") or {}
        if not isinstance(saved, dict) or not saved:
            return
        self.user_notes = dict(saved.get("_user_notes") or {})
        snapshot = saved.get("_input_snapshot") or {}
        mapping = {
            "operational_change": self.operational_change,
            "grid_change": self.grid_change,
            "future_warming_100": self.future_warming_100,
            "future_warming_200": self.future_warming_200,
            "future_climate_interval": self.future_climate_interval,
        }
        # Long-term comparison master data is always calculated to 200 years.
        self.period.set("200")
        for key, variable in mapping.items():
            if snapshot.get(key) is not None:
                variable.set(str(snapshot[key]))
        if snapshot.get("grid_scenario"):
            self.grid_scenario.set(str(snapshot["grid_scenario"]))
        elif snapshot.get("grid_decarbonization_scenario"):
            scenario = snapshot["grid_decarbonization_scenario"]
            if isinstance(scenario, dict):
                self.grid_scenario.set(str(scenario.get("scenario_key") or "standard"))
            else:
                self.grid_scenario.set(str(scenario))
        if snapshot.get("include_credit") is not None:
            self.include_credit.set(bool(snapshot["include_credit"]))
        if snapshot.get("include_biogenic") is not None:
            self.include_biogenic.set(bool(snapshot["include_biogenic"]))
        if snapshot.get("future_climate_enabled") is not None:
            self.future_climate_enabled.set(bool(snapshot["future_climate_enabled"]))
        self.result = saved
        try:
            self.show_result()
        except Exception:
            pass

    def default_remark(self, item):
        remarks = {'新築': '材料数量×環境原単位。製品EPD等がある場合は原単位を置換してください。', '運用': 'Module 2の年間エネルギー結果と電力CO₂係数の経年変化から算出。', '修繕': 'Module 3の更新シナリオと交換数量に環境原単位を適用。', '解体': '解体・廃棄処理量と処理原単位から算出。', '再使用': '再使用・リサイクルによる控除値。控除条件を確認してください。', 'ライフサイクル': '新築＋運用＋更新＋解体－再使用・リサイクル控除。', '木材': '図面・数量解析から得た木材量を基礎に算出。', '炭素固定': '木材の生物由来炭素固定量の参考表示。'}
        text = str(item)
        for token, description in remarks.items():
            if token in text:
                return description
        return "計算条件および入力データに基づく算出値。備考欄はダブルクリックまたはF2で追記できます。"


    def change_language(self,language):
        self.i18n.set_language(language)
        self.title(self.i18n.t("module4"))
        self.build();attach_module_report_button(self,4)
        if self.result:
            self.show_result()

    def choose_project(self):
        p=filedialog.askopenfilename(
            initialdir=self.root_dir/"projects",filetypes=[("JSON","*.json")])
        if not p:return
        try:
            project=load_project(p)
            outputs=project.get("module_outputs",{})
            if not outputs.get("module1") or not outputs.get("module2") or not outputs.get("module3"):
                raise ValueError(self.i18n.t("module123_required"))
            self.project=project
            self.project_path=Path(p)
            self.project_file.set(p)
            # Module 4 always creates the 200-year master timeline.
            self.period.set("200")
        except Exception as exc:
            messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language))

    def calculate(self):
        self.period.set("200")
        if self.project is None:
            messagebox.showwarning("Warning",self.i18n.t("module123_required"))
            return
        try:
            self.result=evaluate_long_term_environment(
                self.project,self.factors,200,
                float(self.operational_change.get()),
                float(self.grid_change.get()),
                self.include_credit.get(),self.include_biogenic.get(),
                self.future_climate_enabled.get(),
                float(self.future_warming_100.get()),
                float(self.future_warming_200.get()),
                int(float(self.future_climate_interval.get())),
                self.grid_scenario.get()
            )
            self.show_result()
            messagebox.showinfo("OK",self.i18n.t("lca_complete"))
        except Exception as exc:
            messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language))

    def show_result(self):
        t=self.i18n.t
        for tree in (self.summary_tree,self.timeline_tree):
            for iid in tree.get_children():
                tree.delete(iid)
        if hasattr(self,"lca_module_tree"):
            for iid in self.lca_module_tree.get_children():
                self.lca_module_tree.delete(iid)
        if hasattr(self,"lca_module_tree"):
            crosswalk=self.result.get("lca_module_crosswalk") or {}
            for row in crosswalk.get("rows") or []:
                co2=row.get("co2_kg")
                energy=row.get("energy_MJ")
                self.lca_module_tree.insert("", "end", values=(
                    row.get("module_group",""),
                    row.get("stage_ja","") if self.i18n.language=="ja" else row.get("stage_en",""),
                    "" if co2 is None else f"{_f(co2):,.0f} kg-CO₂",
                    "—" if energy is None else f"{_f(energy):,.0f} MJ",
                    row.get("resolution",""),
                ))
        s=self.result["summary"]
        ja = self.i18n.language == "ja"
        rows = [
            ("①", t("initial_embodied_co2"), s["initial_embodied_co2_kg"], "kg-CO₂",
             "新築時の各材料数量×各材料のCO₂原単位の合計。" if ja else "Sum of each initial material quantity × its embodied-CO₂ factor.",
             "Module 1数量・LCA原単位" if ja else "Module 1 quantities / LCA factors"),
            ("②", t("operational_co2_total"), s["operational_co2_kg"], "kg-CO₂",
             "評価期間内の年間運用CO₂の累計。" if ja else "Cumulative annual operational CO₂ over the evaluation period.",
             "Module 2年間エネルギー・地域別電力CO₂係数" if ja else "Module 2 annual energy / regional grid CO₂ factor"),
            ("③", t("renewal_co2"), s["renewal_embodied_co2_kg"], "kg-CO₂",
             "修繕・更新イベントごとの交換数量×CO₂原単位の累計。" if ja else "Cumulative replacement quantities × CO₂ factors for repair/renewal events.",
             "Module 3更新シナリオ・LCA原単位" if ja else "Module 3 renewal scenario / LCA factors"),
            ("④", t("demolition_co2"), s["demolition_co2_kg"], "kg-CO₂",
             "解体・廃棄処理量×解体・処理CO₂原単位の累計。" if ja else "Cumulative demolition/waste quantities × demolition and treatment CO₂ factors.",
             "Module 3解体シナリオ・LCA原単位" if ja else "Module 3 demolition scenario / LCA factors"),
            ("⑤", t("recycling_credit"), -s["reuse_recycling_credit_kg"], "kg-CO₂",
             "再使用・リサイクルによるCO₂控除額。①～④から差し引く値。" if ja else "CO₂ credit from reuse/recycling; deducted from items ①–④.",
             "Module 3再使用・リサイクル条件" if ja else "Module 3 reuse/recycling conditions"),
            ("⑥", t("net_lifecycle_co2"), s["net_lifecycle_co2_kg"], "kg-CO₂",
             "①＋②＋③＋④＋⑤。" if ja else "① + ② + ③ + ④ + ⑤.",
             "①～⑤の集計" if ja else "Aggregation of ①–⑤"),
            ("⑦", t("initial_embodied_energy"), s["initial_embodied_energy_MJ"], "MJ",
             "新築時の各材料数量×各材料の一次エネルギー原単位の合計。" if ja else "Sum of each initial material quantity × its embodied-energy factor.",
             "Module 1数量・LCA原単位" if ja else "Module 1 quantities / LCA factors"),
            ("⑧", t("operational_energy_total"), s["operational_energy_MJ"], "MJ",
             "評価期間内の年間運用エネルギーの累計。" if ja else "Cumulative annual operational energy over the evaluation period.",
             "Module 2年間エネルギー" if ja else "Module 2 annual energy"),
            ("⑨", t("renewal_energy"), s["renewal_embodied_energy_MJ"], "MJ",
             "修繕・更新イベントごとの交換数量×一次エネルギー原単位の累計。" if ja else "Cumulative replacement quantities × embodied-energy factors for renewal events.",
             "Module 3更新シナリオ・LCA原単位" if ja else "Module 3 renewal scenario / LCA factors"),
            ("⑩", t("total_lifecycle_energy"), s["total_lifecycle_energy_MJ"], "MJ",
             "⑦＋⑧＋⑨（本モデルで計上するライフサイクルエネルギー合計）。" if ja else "⑦ + ⑧ + ⑨ (total lifecycle energy counted by this model).",
             "⑦～⑨の集計" if ja else "Aggregation of ⑦–⑨"),
            ("⑪", t("waste_generated"), s["waste_generated_kg"], "kg",
             "評価期間内に発生する解体・更新由来の廃棄物総量。" if ja else "Total waste generated by demolition and renewal during the evaluation period.",
             "Module 3イベント数量" if ja else "Module 3 event quantities"),
            ("⑫", t("reused_mass"), s["reused_mass_kg"], "kg",
             "⑪のうち再使用条件に適合する質量。" if ja else "Mass within ⑪ eligible for reuse.",
             "Module 3再使用率" if ja else "Module 3 reuse rate"),
            ("⑬", t("recycled_mass"), s["recycled_mass_kg"], "kg",
             "⑪のうちリサイクル条件に適合する質量。" if ja else "Mass within ⑪ eligible for recycling.",
             "Module 3リサイクル率" if ja else "Module 3 recycling rate"),
            ("⑭", t("landfill_mass"), s["landfill_mass_kg"], "kg",
             "⑪－⑫－⑬等から算定される最終処分量。" if ja else "Final disposal mass derived from ⑪ minus reuse/recycling quantities.",
             "Module 3廃棄物処理条件" if ja else "Module 3 waste-treatment conditions"),
            ("⑮", t("wood_volume"), s.get("wood_volume_m3",0.0), "m³",
             "図面・数量解析で取得した木材数量の合計。" if ja else "Total wood volume obtained from drawing/quantity analysis.",
             "Module 1数量" if ja else "Module 1 quantities"),
            ("⑯", t("dry_wood_mass"), s.get("dry_wood_mass_kg",0.0), "kg",
             "⑮×木材乾燥密度。" if ja else "⑮ × dry wood density.",
             "⑮・LCA木材密度" if ja else "⑮ / LCA wood density"),
            ("⑰", t("biogenic_carbon_mass"), s.get("biogenic_carbon_mass_kgC",0.0), "kg-C",
             "⑯×木材中の炭素含有率。" if ja else "⑯ × carbon fraction of dry wood.",
             "⑯・生物由来炭素係数" if ja else "⑯ / biogenic-carbon factor"),
            ("⑱", t("biogenic_storage"), s.get("biogenic_storage_kgCO2",0.0), "kg-CO₂",
             "⑰×44/12でCO₂換算した生物由来炭素固定量。" if ja else "Biogenic carbon storage converted to CO₂ equivalent as ⑰ × 44/12.",
             "⑰" if ja else "⑰"),
            ("⑲", t("biogenic_storage_tonnes"), s.get("biogenic_storage_tCO2",0.0), "t-CO₂",
             "⑱÷1,000。" if ja else "⑱ ÷ 1,000.",
             "⑱"),
            ("⑳", t("biogenic_storage_per_area"), s.get("biogenic_storage_kgCO2_per_m2",0.0), "kg-CO₂/m²",
             "⑱÷延床面積。" if ja else "⑱ ÷ gross floor area.",
             "⑱・Module 1延床面積" if ja else "⑱ / Module 1 gross floor area"),
            ("㉑", t("net_lifecycle_after_biogenic_reference"), s.get("net_lifecycle_co2_after_biogenic_reference_kg",0.0), "kg-CO₂",
             "⑥から生物由来炭素固定の参考値を反映した値。" if ja else "Reference value applying biogenic carbon storage to ⑥.",
             "⑥・⑱" if ja else "⑥ / ⑱"),
            ("㉒", t("co2_intensity_life"), s["net_co2_intensity_kg_m2_year"], "kg-CO₂/m²·year",
             "⑥÷延床面積÷評価期間。" if ja else "⑥ ÷ gross floor area ÷ evaluation period.",
             "⑥・Module 1延床面積・Module 4評価期間" if ja else "⑥ / Module 1 gross floor area / Module 4 evaluation period"),
            ("㉓", t("energy_intensity_life"), s["energy_intensity_MJ_m2_year"], "MJ/m²·year",
             "⑩÷延床面積÷評価期間。" if ja else "⑩ ÷ gross floor area ÷ evaluation period.",
             "⑩・Module 1延床面積・Module 4評価期間" if ja else "⑩ / Module 1 gross floor area / Module 4 evaluation period"),
        ]
        for no, item, value, unit, basis, source in rows:
            self.summary_tree.insert(
                "", "end",
                values=(no, item, format_number(value, unit), unit, basis, source),
            )
        for row in self.result["annual_timeline"]:
            self.timeline_tree.insert("","end",values=(
                format_number(row["year"], t("year_label"), 0),
                format_number(row["net_co2_kg"], "kg-CO₂"),
                format_number(row["cumulative_co2_kg"], "kg-CO₂"),
                format_number(row["total_energy_MJ"], "MJ"),
                format_number(row["cumulative_energy_MJ"], "MJ"),
                format_number(row["waste_kg"], "kg"),
                format_number(row["reused_kg"], "kg"),
                format_number(row["recycled_kg"], "kg"),
                format_number(row["landfill_kg"], "kg")
            ))
        self.update_co2_chart()

    def update_co2_chart(self):
        """Draw the same style of cumulative-CO2 graph 03_Compare shows in its
        comparison view, but for this single project only (Compare cannot be
        run standalone with just one Project JSON)."""
        if not hasattr(self,"co2_chart") or not self.result:
            return
        ja=self.i18n.language=="ja"
        tl=self.result.get("annual_timeline") or []
        try:
            period=int(float(self.period.get()))
        except (TypeError,ValueError):
            period=200
        series=[(int(row["year"]),row["cumulative_co2_kg"]/1000.0) for row in tl]
        self.co2_chart.set_data(
            (f"累積CO₂排出量（0～{period}年）" if ja else f"Cumulative CO2 Emissions (0-{period} years)"),
            "t-CO₂",
            list(range(0,period+1)),
            [(("累積CO₂" if ja else "Cumulative CO2"),series)] if series else [],
            tick_every=10,
            empty_message=("計算済みデータがありません" if ja else "No calculated data available"),
        )

    def edit_factors(self):
        d=tk.Toplevel(self)
        d.title(self.i18n.t("edit_lca_factors"))
        d.geometry("1200x680")
        t=self.i18n.t
        tree=ttk.Treeview(d,columns=("name","co2","energy","density"),show="headings")
        labels={"name":t("factor_name"),"co2":"kg-CO₂/unit",
                "energy":"MJ/unit","density":"kg/unit"}
        for c in ("name","co2","energy","density"):
            tree.heading(c,text=labels[c])
            tree.column(c,width=360 if c=="name" else 190,anchor="w")
        tree.pack(fill="both",expand=True,padx=8,pady=8)
        lang="ja" if self.i18n.language=="ja" else "en"
        for key,item in self.factors["materials"].items():
            tree.insert("","end",iid=key,values=(
                item[lang],item["embodied_co2_kg_per_unit"],
                item["embodied_energy_MJ_per_unit"],item["density_kg_per_unit"]))
        def edit():
            sel=tree.selection()
            if not sel:return
            key=sel[0]
            item=self.factors["materials"][key]
            w=tk.Toplevel(d);w.title(item[lang])
            vals={
                "embodied_co2_kg_per_unit":tk.StringVar(value=str(item["embodied_co2_kg_per_unit"])),
                "embodied_energy_MJ_per_unit":tk.StringVar(value=str(item["embodied_energy_MJ_per_unit"])),
                "density_kg_per_unit":tk.StringVar(value=str(item["density_kg_per_unit"]))
            }
            labels2=[("embodied_co2_kg_per_unit","kg-CO₂/unit"),
                     ("embodied_energy_MJ_per_unit","MJ/unit"),
                     ("density_kg_per_unit","kg/unit")]
            for r,(k,lbl) in enumerate(labels2):
                ttk.Label(w,text=lbl).grid(row=r,column=0,padx=6,pady=5)
                tk.Entry(w,textvariable=vals[k],bg=INPUT_BG).grid(row=r,column=1,padx=6,pady=5)
            def apply():
                for k,v in vals.items():item[k]=float(v.get())
                tree.item(key,values=(item[lang],item["embodied_co2_kg_per_unit"],
                                      item["embodied_energy_MJ_per_unit"],
                                      item["density_kg_per_unit"]))
                w.destroy()
            ttk.Button(w,text=t("save"),command=apply).grid(row=4,column=0,columnspan=2,pady=8)
        ttk.Button(d,text=t("edit_lca_factors"),command=edit).pack(pady=5)

    def save_annual_csv(self):
        if not self.result:return
        default_path=default_export_path(self.project_path,4,label="Module4_長期環境評価_年別結果")
        p=filedialog.asksaveasfilename(initialdir=default_path.parent,initialfile=default_path.name,defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if not p:return
        rows=self.result["annual_timeline"]
        write_dict_rows_csv(p,rows)

    def save_event_csv(self):
        if not self.result:return
        default_path=default_export_path(self.project_path,4,label="Module4_長期環境評価_イベント別結果")
        p=filedialog.asksaveasfilename(initialdir=default_path.parent,initialfile=default_path.name,defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if not p:return
        rows=self.result["event_impacts"]
        if not rows:return
        write_dict_rows_csv(p,rows)

    def save_output(self):
        self.refresh_project_from_context()
        if self.project is None or self.project_path is None or self.result is None:
            messagebox.showwarning("Warning", self.i18n.t("save_conditions_missing"))
            return
        try:
            self.result["_user_notes"] = dict(self.user_notes)
            report = update_module_and_propagate(
                self.project,
                self.project_path,
                "module4",
                self.result,
                {
    "period": int(float(self.period.get())),
    "operational_change": float(self.operational_change.get()),
    "grid_change": float(self.grid_change.get()),
    "grid_scenario": self.grid_scenario.get(),
    "include_credit": self.include_credit.get(),
    "include_biogenic": self.include_biogenic.get(),
    "future_climate_enabled": self.future_climate_enabled.get(),
    "future_warming_100": float(self.future_warming_100.get()),
    "future_warming_200": float(self.future_warming_200.get()),
    "future_climate_interval": int(float(self.future_climate_interval.get())),
    "language": self.i18n.language,
},
                self.root_dir,
            )
            if self.project_context is not None:
                self.project_context.set(self.project_path, self.project)
            messagebox.showinfo(
                self.i18n.t("saved"),
                format_report(report, self.i18n.language),
            )
        except Exception as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))
