
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
from services.investment_engine_v9_5 import calculate_investment


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

INPUT_BG="#fff4b8"
AUTO_BG="#d9efff"
RESULT_BG="#dff3df"

class Module6App(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language: str = "ja", project_context=None):
        super().__init__(master)
        apply_common_style(self)
        standardize_module_window(self,6)
        self.project_context = project_context
        self.root_dir=Path(root_dir)
        self.i18n=I18N(self.root_dir,language)
        self.project=None
        self.project_path=None
        self.result=None
        self.user_notes={}
        self.project_file=tk.StringVar()
        self.profile=tk.StringVar(value="Japan / Residential")
        self.profile_display=tk.StringVar(value="")
        self.region_id=tk.StringVar(value="JP_NAGOYA")
        self.region_db=json.loads(
            (self.root_dir/"data"/"region_master_v1.json").read_text(encoding="utf-8"))
        self.db=json.loads(
            (self.root_dir/"data"/"investment_assumptions_v9_5.json")
            .read_text(encoding="utf-8"))
        self.vars={
            "analysis_years":tk.StringVar(value="200"),
            "annual_rent_per_m2":tk.StringVar(),
            "target_gross_yield_percent":tk.StringVar(value="8.0"),
            "vacancy_rate_percent":tk.StringVar(),
            "rent_growth_percent":tk.StringVar(),
            "construction_cost_escalation_percent":tk.StringVar(value="2.8"),
            "general_inflation_percent":tk.StringVar(value="2.6"),
            "operating_expense_percent":tk.StringVar(),
            "annual_maintenance_percent_of_cost":tk.StringVar(value="0.0"),
            "property_tax_percent_of_cost":tk.StringVar(value="0"),
            "insurance_percent_of_cost":tk.StringVar(),
            "earthquake_insurance_share_percent":tk.StringVar(value="0.0"),
            "earthquake_insurance_discount_percent":tk.StringVar(value="0.0"),
            "discount_rate_percent":tk.StringVar(),
            "terminal_cap_rate_percent":tk.StringVar(),
            "terminal_sale_cost_percent":tk.StringVar(),
            "land_cost":tk.StringVar(value="0"),
            "other_initial_cost":tk.StringVar(value="0"),
            "loan_to_cost_percent":tk.StringVar(value="70"),
            "annual_interest_rate_percent":tk.StringVar(value="1.8"),
            "loan_term_years":tk.StringVar(value="30"),
            "total_dwelling_units":tk.StringVar(value="3"),
            "partial_renewal_affected_dwelling_units":tk.StringVar(value="1"),
            "partial_renewal_affected_floor_area_m2":tk.StringVar(value="0"),
            "partial_renewal_downtime_months":tk.StringVar(value="1.0"),
            "all_infill_downtime_months":tk.StringVar(value="3.0"),
            "full_rebuild_reletting_months":tk.StringVar(value="3.0"),
            "full_rebuild_relocation_compensation_months":tk.StringVar(value="2.0"),
            "full_rebuild_moving_expense_base_currency":tk.StringVar(value="0"),
            "moving_expense_standard_migrated":tk.StringVar(value="1")
        }
        self.rent_setting_method=tk.StringVar(value="gross_yield")
        # PATCH_006: the user's own target yield.  In market-rent mode the yield
        # entry DISPLAYS the yield derived from the market rent, so the typed
        # target is kept here and restored when switching back.
        self._user_target_yield="8.0"
        self._yield_field_shows_implied=False
        self.use_loan=tk.BooleanVar(value=False)
        if self.project_context is not None and self.project_context.path is not None:
            self.project = self.project_context.reload()
            self.project_path = self.project_context.path
            self.project_file.set(self.project_context.display_path)
            if self._project_currency()=="JPY":
                self.vars["full_rebuild_moving_expense_base_currency"].set("300000")
        self.title(self.i18n.t("module6"))
        self.apply_profile()
        self.build();attach_module_report_button(self,6)
        self.restore_saved_state()
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

    def _profile_region_label(self):
        rec=self._region_record()
        if not rec:
            return ""
        return rec.get("label_ja" if self.i18n.language=="ja" else "label_en",rec.get("id",""))

    def _profile_choices(self):
        region=self._profile_region_label()
        if self.i18n.language=="ja":
            return [f"{region} / 住宅",f"{region} / オフィス","ユーザー定義"]
        return [f"{region} / Residential",f"{region} / Office","User Defined"]

    def _profile_type_from_display(self,text=None):
        text=text if text is not None else self.profile_display.get()
        if text in ("ユーザー定義","User Defined"):
            return "user"
        if str(text).endswith("/ オフィス") or str(text).endswith("/ Office"):
            return "office"
        return "residential"

    def _sync_profile_combo(self, keep_type=True):
        if not hasattr(self,"profile_combo"):
            return
        ptype=self._profile_type_from_display() if keep_type else "residential"
        choices=self._profile_choices()
        self.profile_combo.configure(values=choices)
        if ptype=="office":
            self.profile_display.set(choices[1])
        elif ptype=="user":
            self.profile_display.set(choices[2])
        else:
            self.profile_display.set(choices[0])

    def _on_profile_selected(self,event=None):
        self.apply_profile()

    def _region_record(self, region_id=None):
        rid=region_id or self.region_id.get()
        for rec in self.region_db.get("regions",[]):
            if rec.get("id")==rid:
                return rec
        return None

    def _region_labels(self):
        key="label_ja" if self.i18n.language=="ja" else "label_en"
        return [r.get(key,r.get("id","")) for r in self.region_db.get("regions",[])]

    def _region_id_from_label(self,label):
        key="label_ja" if self.i18n.language=="ja" else "label_en"
        for rec in self.region_db.get("regions",[]):
            if rec.get(key)==label:
                return rec.get("id")
        return self.region_db.get("default_region_id","JP_NAGOYA")

    def _sync_region_combo(self):
        if not hasattr(self,"region_combo"): return
        rec=self._region_record()
        if not rec: return
        key="label_ja" if self.i18n.language=="ja" else "label_en"
        self.region_combo.configure(values=self._region_labels())
        self.region_combo.set(rec.get(key,rec.get("id","")))

    def _on_region_selected(self,event=None):
        if not hasattr(self,"region_combo"): return
        self.region_id.set(self._region_id_from_label(self.region_combo.get()))
        self.apply_region_profile()
        self._sync_profile_combo(keep_type=True)

    def apply_region_profile(self):
        rec=self._region_record()
        if not rec: return
        defaults=rec.get("investment_defaults")
        if defaults:
            for key in ("general_inflation_percent","construction_cost_escalation_percent"):
                if key in defaults and defaults[key] is not None:
                    self.vars[key].set(str(defaults[key]))
            msg=(rec.get("note_ja","") if self.i18n.language=="ja" else rec.get("note_en",""))
        else:
            msg=(
                "海外地域の一般物価・建設費上昇率は、公式統計の対象期間を確認後に登録します。現在の入力値は変更していません。税制はModule 6に含めません。"
                if self.i18n.language=="ja" else
                "Overseas inflation and construction-cost escalation defaults will be registered after source-period verification. Current input values were not changed. Taxes are excluded from Module 6."
            )
        if hasattr(self,"region_note"):
            self.region_note.config(text=msg)

    def _project_currency(self):
        project=self.project if isinstance(self.project,dict) else {}
        m5=(project.get("module_outputs") or {}).get("module5") if isinstance(project.get("module_outputs"),dict) else {}
        if isinstance(m5,dict) and m5.get("currency"):
            return str(m5.get("currency")).upper()
        common=project.get("common") if isinstance(project.get("common"),dict) else {}
        ident=common.get("project_identity") if isinstance(common.get("project_identity"),dict) else {}
        return str(ident.get("currency") or "JPY").upper()

    def build(self):
        for w in self.winfo_children():w.destroy()
        top=ttk.Frame(self);top.pack(fill="x",padx=10,pady=6)
        t=self.i18n.t
        project_currency=self._project_currency()
        L=lambda ja,en: ja if self.i18n.language=="ja" else en

        add_module_text_copy_button(self,top)
        ttk.Label(top,text=t("language")).pack(side="left")
        lang=tk.StringVar(value="日本語" if self.i18n.language=="ja" else "English")
        cb=ttk.Combobox(top,textvariable=lang,values=LANGUAGE_OPTIONS,state="readonly",width=12)
        cb.pack(side="left",padx=5)
        cb.bind("<<ComboboxSelected>>",lambda e:self.change_language("ja" if lang.get()=="日本語" else "en"))



        ttk.Button(
            top, text=t("print_this_module"), style="Primary.TButton",
            command=lambda: self.print_module_report()
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_module6"), command=self.save_output
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_cashflow_csv"), command=self.save_csv
        ).pack(side="right", padx=4)

        # 画面を「投資評価を計算」ボタンの上で2分割する。
        # 上段＝プロジェクト選択・投資条件・借入条件・工事中家賃影響・実行ボタン
        # （コンパクトな入力欄）、下段＝投資評価結果・キャッシュフロー・投資回収
        # グラフ・長期比較表（画面の大部分を占め、常に見えている状態にする）。
        # それぞれ独立してスクロールするため、下段に投資回収グラフがあることに
        # 気づかない、ということが起きにくい。
        split,upper,lower=create_scrollable_pane_split(self,upper_weight=2,lower_weight=5,initial_upper_fraction=0.34)

        project=ttk.LabelFrame(upper,text=t("project"));project.pack(fill="x",padx=0,pady=5)
        ttk.Label(project,text=t("project_json")).grid(row=0,column=0,padx=5,pady=4)
        tk.Entry(project,textvariable=self.project_file,width=108,state="readonly",readonlybackground=AUTO_BG).grid(row=0,column=1,padx=5,pady=4,sticky="ew")
        project.columnconfigure(1,weight=1)

        conditions=ttk.LabelFrame(upper,text=t("investment_conditions"));conditions.pack(fill="x",padx=0,pady=5)

        # PATCH 112: common region master shared conceptually with regional unit-cost
        # profiles and the future tax module.
        ttk.Label(conditions,text=("評価国・地域" if self.i18n.language=="ja" else "Evaluation country / region")).grid(row=0,column=0,padx=4,pady=4,sticky="e")
        self.region_combo=ttk.Combobox(conditions,values=self._region_labels(),state="readonly",width=28)
        self.region_combo.grid(row=0,column=1,padx=4,pady=4,sticky="w")
        self._sync_region_combo()
        self.region_combo.bind("<<ComboboxSelected>>",self._on_region_selected)
        self.region_note=ttk.Label(conditions,text="",foreground="#8b0000",wraplength=780,justify="left")
        self.region_note.grid(row=0,column=2,columnspan=6,padx=8,pady=4,sticky="w")
        self.apply_region_profile()

        ttk.Label(conditions,text=t("investment_profile")).grid(row=1,column=0,padx=4,pady=4)
        self.profile_combo=ttk.Combobox(
            conditions,textvariable=self.profile_display,
            values=self._profile_choices(),state="readonly",width=28
        )
        self.profile_combo.grid(row=1,column=1,padx=4,pady=4)
        self._sync_profile_combo(keep_type=False)
        self.profile_combo.bind("<<ComboboxSelected>>",self._on_profile_selected)
        ttk.Button(conditions,text=t("apply_investment_profile"),command=self.apply_profile).grid(row=1,column=2,padx=5,pady=4)

        # PATCH 108: Rent can be set from target gross yield or entered directly as market rent.
        rent_mode_label="家賃設定方式" if self.i18n.language=="ja" else "Rent-setting method"
        ttk.Label(conditions,text=rent_mode_label).grid(row=2,column=0,padx=4,pady=4,sticky="e")
        rent_mode_values=(
            ["表面利回りから逆算（標準）","市場家賃を直接入力"]
            if self.i18n.language=="ja"
            else ["Derive from gross yield (standard)","Enter market rent directly"]
        )
        self.rent_mode_combo=ttk.Combobox(conditions,values=rent_mode_values,state="readonly",width=28)
        self.rent_mode_combo.grid(row=2,column=1,padx=4,pady=4,sticky="w")
        self._sync_rent_mode_combo()
        self.rent_mode_combo.bind("<<ComboboxSelected>>",self._on_rent_mode_selected)

        self.yield_label=ttk.Label(
            conditions,
            text=("目標表面利回り (%)" if self.i18n.language=="ja" else "Target gross yield (%)")
        )
        self.yield_label.grid(row=2,column=2,padx=4,pady=4,sticky="e")
        self.yield_entry=tk.Entry(conditions,textvariable=self.vars["target_gross_yield_percent"],bg=INPUT_BG,width=15)
        self.yield_entry.grid(row=2,column=3,padx=4,pady=4)
        # PATCH_006: a rebuilt panel (e.g. language switch) keeps the mode.
        self._apply_yield_field_mode()

        ttk.Label(
            conditions,
            text=(
                "標準：初年度総家賃＝初期投資額×目標表面利回り。市場家賃方式では年間賃料単価を直接使用します。"
                if self.i18n.language=="ja"
                else "Standard: Year-1 gross rent = initial investment × target gross yield. Market-rent mode uses the annual rent-per-m² input."
            ),
            foreground="#8b0000"
        ).grid(row=2,column=4,columnspan=4,padx=8,pady=4,sticky="w")

        defs=[
            ("analysis_years","analysis_years"),("annual_rent_per_m2","annual_rent_per_m2"),
            ("vacancy_rate_percent","vacancy_rate"),("rent_growth_percent","rent_growth_rate"),
            ("construction_cost_escalation_percent","construction_cost_escalation_percent"),
            ("general_inflation_percent","general_inflation_percent"),
            ("operating_expense_percent","operating_expense_rate"),
            ("annual_maintenance_percent_of_cost","maintenance_rate"),
            ("insurance_percent_of_cost","insurance_rate"),
            ("earthquake_insurance_share_percent","earthquake_insurance_share_percent"),
            ("earthquake_insurance_discount_percent","earthquake_insurance_discount_percent"),
            ("discount_rate_percent","discount_rate"),
            ("terminal_cap_rate_percent","terminal_cap_rate"),
            ("terminal_sale_cost_percent","terminal_sale_cost"),
            ("land_cost","land_cost"),("other_initial_cost","other_initial_cost")
        ]
        for i,(key,label) in enumerate(defs):
            r=3+i//4;c=(i%4)*2
            special_labels={
                "annual_rent_per_m2":(
                    f"市場家賃入力：年間賃料単価 ({project_currency}/m²・年)" if self.i18n.language=="ja"
                    else f"Market-rent input: annual rent ({project_currency}/m²/year)"
                ),
                "construction_cost_escalation_percent":(
                    "建設・更新工事費上昇率 (%)" if self.i18n.language=="ja"
                    else "Construction / renewal cost escalation (%)"
                ),
                "general_inflation_percent":(
                    "一般物価上昇率 (%)" if self.i18n.language=="ja"
                    else "General inflation (%)"
                ),
                "discount_rate_percent":(
                    "割引率（選択 1.0～4.0%）" if self.i18n.language=="ja"
                    else "Discount rate (select 1.0–4.0%)"
                ),
                "annual_maintenance_percent_of_cost":(
                    "日常維持管理費率（Module 7外・%/年）" if self.i18n.language=="ja"
                    else "Routine upkeep rate (outside Module 7, %/yr)"
                ),
                "earthquake_insurance_share_percent":(
                    "保険料のうち地震保険相当分 (%)" if self.i18n.language=="ja"
                    else "Earthquake-insurance share of total insurance (%)"
                ),
                "earthquake_insurance_discount_percent":(
                    "地震保険割引率（確認済みのみ・%）" if self.i18n.language=="ja"
                    else "Earthquake-insurance discount (verified only, %)"
                ),
            }
            ttk.Label(conditions,text=special_labels.get(key,t(label))).grid(row=r,column=c,padx=4,pady=4,sticky="e")
            if key == "analysis_years":
                tk.Entry(
                    conditions,textvariable=self.vars[key],width=15,state="readonly",
                    readonlybackground=AUTO_BG
                ).grid(row=r,column=c+1,padx=4,pady=4)
            elif key == "discount_rate_percent":
                # PATCH 111: selectable discount-rate sensitivity range.
                # Keep the project/profile value when it is one of the supported values.
                discount_values=("1.0","1.5","2.0","2.5","3.0","3.5","4.0")
                if self.vars[key].get().strip() not in discount_values:
                    self.vars[key].set("4.0")
                ttk.Combobox(
                    conditions,
                    textvariable=self.vars[key],
                    values=discount_values,
                    state="readonly",
                    width=13
                ).grid(row=r,column=c+1,padx=4,pady=4)
            else:
                tk.Entry(conditions,textvariable=self.vars[key],bg=INPUT_BG,width=15).grid(row=r,column=c+1,padx=4,pady=4)

        finance=ttk.LabelFrame(upper,text=t("financing"));finance.pack(fill="x",padx=0,pady=5)
        ttk.Checkbutton(finance,text=t("use_loan"),variable=self.use_loan).grid(row=0,column=0,padx=5,pady=4)
        for i,(key,label) in enumerate([
            ("loan_to_cost_percent","loan_to_cost"),
            ("annual_interest_rate_percent","loan_interest"),
            ("loan_term_years","loan_term")
        ]):
            ttk.Label(finance,text=t(label)).grid(row=0,column=i*2+1,padx=4,pady=4)
            tk.Entry(finance,textvariable=self.vars[key],bg=INPUT_BG,width=14).grid(row=0,column=i*2+2,padx=4,pady=4)

        interruption=ttk.LabelFrame(
            upper,
            text=("工事中の家賃・退去影響" if self.i18n.language=="ja" else "Construction business interruption")
        )
        interruption.pack(fill="x",padx=0,pady=5)
        interruption_defs=[
            ("total_dwelling_units","総住戸数","Total dwelling units"),
            ("partial_renewal_affected_dwelling_units","同時工事住戸数","Dwelling units under work"),
            ("partial_renewal_affected_floor_area_m2","工事対象床面積 m²（0=住戸数から自動）","Affected floor area m² (0=derive from unit count)"),
            ("partial_renewal_downtime_months","部分更新の賃料停止月数","Partial-renewal downtime months"),
            ("all_infill_downtime_months","全インフィル更新の賃料停止月数","All-infill downtime months"),
            ("full_rebuild_reletting_months","全面建替え後の再募集空室月数","Post-rebuild reletting months"),
            ("full_rebuild_relocation_compensation_months","全面建替え時の退去補償（月額賃料換算）","Rebuild relocation compensation (rent-months)"),
            ("full_rebuild_moving_expense_base_currency",f"全面建替え時の移転実費（現在価格・{project_currency}）",f"Rebuild actual moving expense (current-price {project_currency})")
        ]
        ttk.Label(
            interruption,
            text=(
                "退去補償は家賃連動。移転実費は現在価格で入力し、一般物価上昇率で将来額へ連動します。"
                " ※移転実費の算出における物価連動は日本の公共事業の土地収用法・損失補償の考え方を参考にしています。"
                " 標準初期値は100,000円/戸×3戸＝300,000円（現在価格）。"
                " 日本の公共事業における動産移転料・損失補償の考え方と、愛知県の家族世帯の引越費用水準を参考にした比較用標準値です。"
                " 実際の事業では個別見積りにより変更してください。"
                if self.i18n.language=="ja" else
                "Tenant compensation is rent-linked. Actual moving expense is entered at current prices and escalated with general inflation. "
                "The inflation linkage is informed by Japanese public-project land expropriation/loss-compensation practice."
            ),
            wraplength=1500
        ).grid(row=3,column=0,columnspan=6,sticky="w",padx=4,pady=(6,2))

        for i,(key,ja,en) in enumerate(interruption_defs):
            r=i//3;c=(i%3)*2
            ttk.Label(interruption,text=(ja if self.i18n.language=="ja" else en)).grid(row=r,column=c,padx=4,pady=4,sticky="e")
            tk.Entry(interruption,textvariable=self.vars[key],bg=INPUT_BG,width=14).grid(row=r,column=c+1,padx=4,pady=4)

        ttk.Label(upper,text=t("investment_notice"),foreground="#8b0000",wraplength=1500).pack(fill="x",padx=12,pady=(3,1))
        ttk.Label(upper,text=t("investment_assumption_notice"),foreground="#8b0000",wraplength=1500).pack(fill="x",padx=12,pady=(1,2))
        ttk.Label(
            upper,
            text=(
                "【保険料の扱い】工法だけを理由にAZRASへ自動的な保険料優遇は与えません。"
                " 地震保険については、耐震等級等の確認資料がある場合に10～50%の割引があり得るため、"
                "『保険料のうち地震保険相当分』と『確認済み割引率』を分けて入力します。"
                " 確認資料がない場合は割引率0%のまま使用してください。"
                if self.i18n.language=="ja" else
                "[Insurance treatment] No automatic insurance advantage is assigned by construction method. "
                "For earthquake insurance, verified seismic-performance documentation may justify a 10–50% discount. "
                "Enter the earthquake-insurance share and verified discount separately; otherwise keep the discount at 0%."
            ),
            foreground="#8b0000",wraplength=1500
        ).pack(fill="x",padx=12,pady=(1,4))

        ttk.Label(
            upper,
            text=(
                "【維持管理費の重複防止】Module 7の計画修繕・更新・交換・解体・建替え費は、"
                "Module 6の日常維持管理費には含めません。Module 6の維持管理費率は、"
                "清掃・軽微な日常補修・定期保守などModule 7に未計上の費用だけに使用します。"
                if self.i18n.language=="ja" else
                "[No maintenance double counting] Planned repair, renewal, replacement, demolition and rebuild costs are counted in Module 7 only. "
                "The Module 6 maintenance rate is limited to routine upkeep not represented in Module 7."
            ),
            foreground="#8b0000",wraplength=1500
        ).pack(fill="x",padx=12,pady=(1,4))

        ttk.Label(
            upper,
            text=(
                "【4つの率は別条件】家賃上昇率／建設・更新工事費上昇率／一般物価上昇率／NPV割引率を分離します。"
                " 建替え・更新費は発生年まで工事費上昇率で名目額へ増額し、その後NPV割引率で現在価値へ換算します。"
                if self.i18n.language=="ja" else
                "[Four independent rates] Rent growth, construction/renewal cost escalation, general inflation, and NPV discount rate are separate assumptions. "
                "Renewal/rebuild costs are first escalated to the event-year nominal amount, then discounted to present value."
            ),
            foreground="#8b0000",wraplength=1500
        ).pack(fill="x",padx=12,pady=(1,4))

        ttk.Label(
            upper,
            text=(
                "【税金の取扱い】土地・建物に関する税金は国・地域によって税制が異なるため、"
                "本シミュレーションのCF計算対象外とし、別途考慮してください。"
                if self.i18n.language=="ja" else
                "[Tax treatment] Taxes related to land and buildings vary by country and jurisdiction. "
                "They are excluded from this simulation cash flow and must be considered separately."
            ),
            foreground="#8b0000",wraplength=1500
        ).pack(fill="x",padx=12,pady=(1,4))
        ttk.Label(
            upper,
            text=(
                "※ 工法比較を行う場合の注意：同じ間取り・規模・立地条件で、異なる工法の経済性を比較できます。"
                "初期計算では、各工法とも初期設定利回り8％を基準として事業性を算定します。"
                "ただし、工法ごとに建設費が異なるため、利回り8％から逆算した家賃も工法ごとに異なります。"
                "純粋に工法による経済性の違いを比較する場合は、初期計算後、実際の市場で妥当と考えられる家賃を設定し、"
                "各工法とも同じ家賃に入れ直して再確認してください。"
                "また、各工法のProject JSONをChatGPTにアップロードし、同じ家賃条件で50年・100年・150年・200年の事業性を比較するなどと質問すると、各工法の違いを短時間で詳しく確認できます。"
                if self.i18n.language=="ja" else
                "Note for construction-method comparisons: When comparing different construction methods under the same plan, scale, and location, "
                "the initial calculation uses the default 8% target gross yield. Because construction costs differ, the rent back-calculated from 8% also differs by method. "
                "For a pure construction-method comparison, rerun each method using the same realistic market rent. You can also upload each Project JSON to ChatGPT and ask for comparisons at 50, 100, 150, and 200 years under the same rent assumption."
            ),
            foreground="#8b0000",wraplength=1500,justify="left"
        ).pack(fill="x",padx=12,pady=(2,6))

        ttk.Button(upper,text=t("calculate_investment"),command=self.calculate).pack(pady=6,ipady=5)

        # PATCH 195: same PATCH 194 lower-canvas collapse as Module 4.
        # Keep the investment result/cash-flow tables visibly allocated and let the
        # independent lower canvas handle vertical scrolling of the remaining outputs.
        body=ttk.Panedwindow(lower,orient="horizontal",height=420)
        body.pack(fill="both",expand=True,padx=0,pady=5)
        summary=ttk.LabelFrame(body,text=t("investment_result"))
        timeline=ttk.LabelFrame(body,text=t("cashflow_timeline"))
        body.add(summary,weight=2);body.add(timeline,weight=4)

        graphs=ttk.LabelFrame(lower,text=L("200年間投資回収グラフ","200-Year Investment Recovery Graphs"))
        graphs.pack(fill="both",expand=True,padx=0,pady=5)
        graphs.columnconfigure(0,weight=1,uniform="inv")
        graphs.columnconfigure(1,weight=1,uniform="inv")
        graphs.rowconfigure(0,weight=1)

        n=ttk.LabelFrame(graphs,text=L("① 単純投資回収（初回回収の確認）","① Simple Payback (First Recovery)"))
        n.grid(row=0,column=0,sticky="nsew",padx=(6,4),pady=6)
        self.simple_payback_label=ttk.Label(n,text=L("単純投資回収年：—","Simple payback year: —"),foreground="#333")
        self.simple_payback_label.pack(anchor="e",padx=8,pady=(3,0))
        self.nominal_cf_chart=LineChart(n,height=360)
        self.nominal_cf_chart.pack(fill="both",expand=True,padx=5,pady=(1,2))
        ttk.Label(
            n,
            text=L(
                "【ご注意】\n・「単純回収年」と同じ名目累積CF系列で、初回の投資回収を確認します。\n"
                "・0円ラインを下から上へ初めて超える年が単純投資回収年です。\n"
                "・初回回収を見やすくするため、グラフは回収年の約10年後までを拡大表示します。\n"
                "・30年以降の更新・建替えを含む200年間の長期評価は右側の現在価値ベース回収で確認します。",
                "[Note]\n• Uses the same nominal cumulative CF series as \"Simple Payback Year\" to identify the first recovery.\n"
                "• Simple payback is the first year the series crosses the zero line from below.\n"
                "• The graph is expanded to about 10 years after recovery for visibility.\n"
                "• Long-term 200-year evaluation including renewal/rebuild after year 30 is shown in the present-value panel on the right.",
            ),
            foreground="#d00000",wraplength=600,justify="left",font=("Yu Gothic UI",8),
        ).pack(fill="x",padx=8,pady=(4,8))

        f=ttk.LabelFrame(graphs,text=L("② 現在価値ベース回収（割引累積CF）","② Present-Value Recovery (Discounted Cumulative CF)"))
        f.grid(row=0,column=1,sticky="nsew",padx=(4,6),pady=6)
        self.cash_payback_label=ttk.Label(f,text=L("現在価値ベース回収：—","Present-value recovery: —"),foreground="#333")
        self.cash_payback_label.pack(anchor="e",padx=8,pady=(3,0))
        self.discounted_cf_chart=LineChart(f,height=360)
        self.discounted_cf_chart.pack(fill="both",expand=True,padx=5,pady=(1,2))
        ttk.Label(
            f,
            text=L(
                "【ご注意】\n・割引率で将来CFを現在価値へ割り引いて累積します。\n"
                "・0円ラインを下から上へ初めて超える年を現在価値ベース回収年とします。\n"
                "・0未満は現在価値ベースで投資未回収であり、年間利益が赤字という意味ではありません。\n"
                "・終価（売却価値）は含みません。",
                "[Note]\n• Future CF is discounted to present value at the discount rate and accumulated.\n"
                "• The first year the series crosses the zero line from below is the present-value recovery year.\n"
                "• A value below zero means unrecovered on a present-value basis, not an annual loss.\n"
                "• Terminal (sale) value is not included.",
            ),
            foreground="#d00000",wraplength=600,justify="left",font=("Yu Gothic UI",8),
        ).pack(fill="x",padx=8,pady=(4,8))

        horizons=ttk.LabelFrame(lower,text=L("60年・120年・180年・200年 名目DCF事業性比較","60/120/180/200-Year Nominal DCF Business Comparison"))
        horizons.pack(fill="x",padx=0,pady=5)
        self.horizon_tree=ttk.Treeview(
            horizons,
            columns=("horizon","construction","construction_tax","npv","lifecycle","lifecycle_tax","interruption","terminal","payback"),
            show="headings",
            height=4
        )
        for c,label,w in [
            ("horizon",L("評価期間","Evaluation Period"),90),
            ("construction",L("初期建設費（税抜）","Initial Construction Cost (excl. tax)"),150),
            ("construction_tax",L("建設時税金（別途）","Construction Taxes (separate)"),145),
            ("npv",L("事業NPV（税抜）","Business NPV (excl. tax)"),150),
            ("lifecycle",L("更新・建替費（将来名目・税抜）","Renewal/Rebuild Cost (future nominal, excl. tax)"),205),
            ("lifecycle_tax",L("更新時税金（別途）","Renewal Taxes (separate)"),145),
            ("interruption",L("事業中断費","Business Interruption Cost"),150),
            ("terminal",L("期末価値","Terminal Value"),150),
            ("payback",L("単純回収年","Simple Payback Year"),110),
        ]:
            self.horizon_tree.heading(c,text=label)
            self.horizon_tree.column(c,width=w,anchor="e" if c!="horizon" else "center")
        self.horizon_tree.pack(fill="x",expand=True,padx=6,pady=6)
        ttk.Label(
            horizons,
            text=L("名目DCF：現在入力の上昇率で将来額を算定し、割引率で現在価値化。120～200年は長期シナリオとして解釈してください。","Nominal DCF: future amounts use the current escalation inputs and are discounted to present value. Interpret 120–200 years as long-term scenarios.")
        ).pack(anchor="w",padx=8,pady=(0,6))

        constant_price=ttk.LabelFrame(lower,text=L("現在価格による長期工法比較（投資NPVではありません）","Long-Term Method Comparison at Current Prices (not investment NPV)"))
        constant_price.pack(fill="x",padx=0,pady=5)
        ttk.Label(
            constant_price,
            text=(
                "Module 7の修繕・更新・解体・建替え費を現在価格のまま集計します。将来物価を予測せず、工法そのものの長期費用差を比較する補助指標です。"
                if self.i18n.language=="ja" else
                "Module 7 lifecycle work is summed at current prices. This is a long-term method-cost comparison, not an investment NPV."
            ),wraplength=1500
        ).pack(anchor="w",padx=8,pady=4)
        self.constant_price_tree=ttk.Treeview(
            constant_price,columns=("horizon","initial","lifecycle","combined"),show="headings",height=4
        )
        for c,label,w in [("horizon",L("評価期間","Evaluation Period"),100),("initial",L("初期建設費（現在価格）","Initial Construction Cost (current prices)"),190),("lifecycle",L("更新・建替費（現在価格）","Renewal/Rebuild Cost (current prices)"),210),("combined",L("建設＋更新等（現在価格）","Construction + Renewal etc. (current prices)"),210)]:
            self.constant_price_tree.heading(c,text=label); self.constant_price_tree.column(c,width=w,anchor="e" if c!="horizon" else "center")
        self.constant_price_tree.pack(fill="x",expand=True,padx=6,pady=(0,6))

        japan_ref=ttk.LabelFrame(lower,text=L("日本の長期実績を踏まえた参考設定","Reference Settings Informed by Japan Long-Run Data"))
        japan_ref.pack(fill="x",padx=0,pady=5)
        ttk.Label(
            japan_ref,
            text=(
                "日本の標準参考初期値：建設・更新工事費上昇率 2.8%/年、一般物価上昇率 2.6%/年。"
                "※その根拠は日本の過去約60年の統計値による。"
                " 建設工事費は国土交通省「建設工事費デフレーター」、一般物価は総務省「消費者物価指数（CPI）」を参照。"
                " 120年・180年については同一公式系列で直接検証できないため、この値は長期感度分析の参考値として扱います。"
                if self.i18n.language=="ja" else
                "Japan reference scenarios: Low 1.0% / Standard 1.5% / High 2.0%. "
                "These are sensitivity assumptions informed by Japan's long-run MLIT construction-cost deflator and Statistics Bureau CPI. "
                "They are reference scenarios, not forecasts; comparable official construction series do not span 120 or 180 years."
            ),
            wraplength=1500
        ).pack(anchor="w",padx=8,pady=5)
        ttk.Label(
            japan_ref,
            text=(
                "主比較（60・120・180年）は、現在入力されている建設・更新工事費上昇率と一般物価上昇率から毎回再計算します。"
                if self.i18n.language=="ja" else
                "Primary 60/120/180-year comparison is rebuilt every time from the current escalation and inflation inputs."
            )
        ).pack(anchor="w",padx=8,pady=(0,5))


        sensitivity=ttk.LabelFrame(lower,text=L("上昇率 感度分析（日本60年実績を標準参考）","Escalation Sensitivity (Japan 60-Year Data as Reference)"))
        sensitivity.pack(fill="x",padx=0,pady=5)
        ttk.Label(
            sensitivity,
            text=(
                "標準は建設・更新工事費 2.8%／一般物価 2.6%。低位は2.3%／2.1%、高位は3.3%／3.1%。"
                "家賃上昇率、NPV割引率、その他の条件は主計算と同じです。"
                if self.i18n.language=="ja" else
                "Only construction/renewal escalation and general inflation are varied together; rent growth, discount rate and all other conditions remain unchanged."
            )
        ).pack(anchor="w",padx=8,pady=(4,4))
        self.sensitivity_tree=ttk.Treeview(
            sensitivity,
            columns=("scenario","rate","h60","h120","h180","h200"),
            show="headings",
            height=3
        )
        for c,label,w in [
            ("scenario",L("シナリオ","Scenario"),100),
            ("rate",L("建設費 / 物価","Construction / Inflation"),125),
            ("h60",L("60年 NPV","60-Year NPV"),155),
            ("h120",L("120年 NPV","120-Year NPV"),155),
            ("h180",L("180年 NPV","180-Year NPV"),155),
            ("h200",L("200年 NPV","200-Year NPV"),155),
        ]:
            self.sensitivity_tree.heading(c,text=label)
            self.sensitivity_tree.column(c,width=w,anchor="e" if c not in ("scenario","rate") else "center")
        self.sensitivity_tree.pack(fill="x",expand=True,padx=6,pady=(0,6))
        discount_sensitivity=ttk.LabelFrame(lower,text=L("割引率 感度分析（他条件固定）","Discount-Rate Sensitivity (other conditions fixed)"))
        discount_sensitivity.pack(fill="x",padx=0,pady=5)
        ttk.Label(discount_sensitivity,text=L("2/3/4/5/6%＋現在入力率で50・100・150・200年NPVを自動比較。各期間末の終価も再計算します。","Automatically compares 50/100/150/200-year NPV at 2/3/4/5/6% plus the current input rate. Terminal value is recalculated for each horizon."),wraplength=1000).pack(fill="x",padx=6,pady=(4,2))
        self.discount_sensitivity_tree=ttk.Treeview(discount_sensitivity,columns=("rate","h50","h100","h150","h200"),show="headings",height=6)
        for c,label,w in [("rate",L("割引率","Discount Rate"),120),("h50",L("50年 NPV","50-Year NPV"),170),("h100",L("100年 NPV","100-Year NPV"),170),("h150",L("150年 NPV","150-Year NPV"),170),("h200",L("200年 NPV","200-Year NPV"),170)]:
            self.discount_sensitivity_tree.heading(c,text=label); self.discount_sensitivity_tree.column(c,width=w,anchor="center" if c=="rate" else "e")
        self.discount_sensitivity_tree.pack(fill="x",expand=True,padx=6,pady=(0,6))

        ttk.Label(
            summary,
            text=(
                '【重要】本結果は、Module 1「図面解析・数量計算」で得られた数量を基礎とする建設費・更新費等を用いて算定しています。通常表示の確定数量と黄色表示の暫定・想定数量は計算に含まれます。一方、Module 1で数量を算出できず赤表示となっている未積算項目は本結果に含まれません。未積算項目を人間が確認・追加入力したうえで再計算し、最終判断してください。未積算項目の内容によっては、建設費・LCC・キャッシュフロー・NPV・IRR等が大きく変わる場合があります。'
                if self.i18n.language=="ja" else
                'IMPORTANT: This result uses construction and lifecycle costs derived from quantities obtained in Module 1 Drawing Analysis / Quantity Calculation. Confirmed quantities and yellow provisional/assumed quantities are included. Red items whose quantities could not be determined in Module 1 are not included. Have a human verify and add any unquantified items, then recalculate before making a final decision. Those omitted items may materially change construction cost, LCC, cash flow, NPV, and IRR.'
            ),
            foreground="#8b0000", wraplength=1050, justify="left"
        ).pack(fill="x",padx=6,pady=(6,2))

        self.summary_tree=ttk.Treeview(summary,columns=("item","value","unit","remark","source"),show="headings")
        summary_columns=[
            ("item","item",260),
            ("value","value",150),
            ("unit","unit",90),
            ("remark","calculation_basis",470),
            ("source","reference_source",250),
        ]
        for c,key,w in summary_columns:
            self.summary_tree.heading(c,text=t(key));self.summary_tree.column(c,width=w,anchor="e" if c=="value" else "w")
        self.summary_tree.pack(fill="both",expand=True,padx=6,pady=6)
        # 算定根拠列は、従来の備考欄と同様にダブルクリック/F2で追記可能。
        bind_editable_remarks(self.summary_tree, self.user_notes, remark_column="remark")

        cols=("year","gross","effective","rentloss","relocation","opex","maintenance","noi","lifecycle","debt","cash","discounted","balance")
        self.tree=ttk.Treeview(timeline,columns=cols,show="headings")
        headings={
            "year":t("year"),"gross":header_with_unit(t("gross_rent"),project_currency),"effective":header_with_unit(t("effective_rent"),project_currency),
            "opex":header_with_unit(t("operating_expense"),project_currency),"maintenance":header_with_unit(t("maintenance_cost"),project_currency),
            "rentloss":(f"工事中家賃損失 ({project_currency})" if self.i18n.language=="ja" else f"Construction rent loss ({project_currency})"),
            "relocation":(f"退去・再募集関連費 ({project_currency})" if self.i18n.language=="ja" else f"Relocation / reletting cost ({project_currency})"),
            "noi":header_with_unit(t("noi"),project_currency),
            "lifecycle":(f"更新・建替費・将来名目 ({project_currency})" if self.i18n.language=="ja" else f"Renewal / rebuild future nominal cost ({project_currency})"),
            "debt":header_with_unit(t("debt_service"),project_currency),"cash":header_with_unit(t("before_tax_cash_flow"),project_currency),
            "discounted":header_with_unit(t("discounted_cash_flow"),project_currency),"balance":header_with_unit(t("loan_balance"),project_currency)
        }
        widths={"year":60,"gross":120,"effective":120,"rentloss":130,"relocation":140,
                "opex":110,"maintenance":110,"noi":120,"lifecycle":130,"debt":110,
                "cash":130,"discounted":130,"balance":120}
        for c in cols:
            self.tree.heading(c,text=headings[c]);self.tree.column(c,width=widths[c],anchor="e")
        y=ttk.Scrollbar(timeline,orient="vertical",command=self.tree.yview)
        x=ttk.Scrollbar(timeline,orient="horizontal",command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        self.tree.grid(row=0,column=0,sticky="nsew");y.grid(row=0,column=1,sticky="ns");x.grid(row=1,column=0,sticky="ew")
        timeline.rowconfigure(0,weight=1);timeline.columnconfigure(0,weight=1)


    def _sync_rent_mode_combo(self):
        if not hasattr(self,"rent_mode_combo"):
            return
        if self.i18n.language=="ja":
            text="表面利回りから逆算（標準）" if self.rent_setting_method.get()=="gross_yield" else "市場家賃を直接入力"
        else:
            text="Derive from gross yield (standard)" if self.rent_setting_method.get()=="gross_yield" else "Enter market rent directly"
        self.rent_mode_combo.set(text)

    def _on_rent_mode_selected(self,event=None):
        text=self.rent_mode_combo.get() if hasattr(self,"rent_mode_combo") else ""
        if text in ("市場家賃を直接入力","Enter market rent directly"):
            self.rent_setting_method.set("market_rent")
        else:
            self.rent_setting_method.set("gross_yield")
        self._apply_yield_field_mode()

    def _implied_yield_from_result(self):
        """PATCH_006: derived gross yield of the last calculation, or None.

        Only a result calculated in market-rent mode is used: a gross-yield
        result would just echo the target back.
        """
        s=(self.result or {}).get("summary") if isinstance(self.result,dict) else None
        if not isinstance(s,dict) or s.get("rent_setting_method")!="market_rent":
            return None
        v=s.get("implied_gross_yield_percent")
        if v is None:
            v=s.get("year1_gross_yield_percent")
        try:
            return float(v)
        except Exception:
            return None

    def _apply_yield_field_mode(self):
        """PATCH_006: make the yield entry follow the rent-setting method.

        * gross-yield mode: an editable input, the user's target.
        * market-rent mode: read-only, showing the yield this Project earns at
          the entered market rent (rent x GFA / initial investment), refreshed
          after each calculation.  The typed target is preserved and comes back
          unchanged when the user switches back.
        """
        if not hasattr(self,"yield_entry"):
            return
        ja=(self.i18n.language=="ja")
        var=self.vars["target_gross_yield_percent"]
        if self.rent_setting_method.get()=="market_rent":
            if not self._yield_field_shows_implied:
                self._user_target_yield=var.get() or self._user_target_yield
            implied=self._implied_yield_from_result()
            var.set(f"{implied:.2f}" if implied is not None else "")
            self._yield_field_shows_implied=True
            self.yield_entry.configure(state="readonly",readonlybackground="#E8E8E8")
            self.yield_label.configure(text=("表面利回り (%)（市場家賃から算出）" if ja
                                             else "Gross yield (%) (derived from market rent)"))
        else:
            if self._yield_field_shows_implied:
                var.set(self._user_target_yield or "8.0")
            self._yield_field_shows_implied=False
            self.yield_entry.configure(state="normal")
            self.yield_label.configure(text=("目標表面利回り (%)" if ja else "Target gross yield (%)"))

    def restore_saved_state(self):
        if self.project is None:
            return
        saved = self.project.get("module_outputs", {}).get("module6") or {}
        if not isinstance(saved, dict) or not saved:
            return
        self.user_notes = dict(saved.get("_user_notes") or {})
        snapshot = saved.get("_input_snapshot") or {}
        settings = snapshot.get("settings") or {}

        saved_region=settings.get("region_profile_id")
        if saved_region and self._region_record(saved_region):
            self.region_id.set(saved_region)
        else:
            self.region_id.set(self.region_db.get("default_region_id","JP_NAGOYA"))
        self._sync_region_combo()
        self.apply_region_profile()
        self._sync_profile_combo(keep_type=False)

        # PATCH 108: legacy projects did not store a rent-setting method.
        # On first recalculation they adopt the new planning standard:
        # gross-yield-derived rent at 8.0%, while the old annual_rent_per_m2
        # remains available if the user switches to market-rent mode.
        method=settings.get("rent_setting_method")
        if method in ("gross_yield","market_rent"):
            self.rent_setting_method.set(method)
        else:
            self.rent_setting_method.set("gross_yield")
        if settings.get("target_gross_yield_percent") is None:
            settings["target_gross_yield_percent"]=8.0
        self._sync_rent_mode_combo()

        # PATCH 215: moving expense is denominated in the Project currency.
        # The historical *_yen field is imported only for JPY projects.
        # It must never become USD/EUR/etc. by reinterpretation.
        try:
            currency=self._project_currency()
            if settings.get("full_rebuild_moving_expense_base_currency") is None:
                if currency=="JPY":
                    legacy_move=float(settings.get("full_rebuild_moving_expense_base_yen",0) or 0)
                    settings["full_rebuild_moving_expense_base_currency"]=legacy_move if legacy_move>0 else 300000.0
                else:
                    settings["full_rebuild_moving_expense_base_currency"]=0.0
            settings["moving_expense_standard_migrated"]=1.0
        except Exception:
            pass

        for key, variable in self.vars.items():
            if key == "analysis_years":
                variable.set("200")
            elif key == "property_tax_percent_of_cost":
                variable.set("0")
            elif settings.get(key) is not None:
                variable.set(str(settings[key]))
        if settings.get("use_loan") is not None:
            self.use_loan.set(bool(settings["use_loan"]))
        # PATCH_006: the saved target is the user's input, never the displayed
        # derived yield.
        if settings.get("target_gross_yield_percent") is not None:
            self._user_target_yield=str(settings["target_gross_yield_percent"])
        self._yield_field_shows_implied=False
        self.result = saved
        try:
            self.show_result()
        except Exception:
            pass
        self._apply_yield_field_mode()

    def default_remark(self, item):
        if self.i18n.language=="ja":
            remarks = {'修繕': 'Module 3のイベント時期・数量とModule 5の単価を使用。', '解体': '対象数量×解体単価＋廃棄物処理費。', '廃棄': '廃棄物量×処理単価。', '再使用': '再使用・リサイクル控除率と対象数量から算出。', '年平均': '評価期間の総額÷評価年数。'}
            fallback="計算条件および入力データに基づく算出値。備考欄はダブルクリックまたはF2で追記できます。"
        else:
            remarks = {'repair': 'Uses Module 3 event timing/quantities and Module 5 unit costs.', 'demolition': 'Applicable quantity × demolition unit cost + waste-disposal cost.', 'waste': 'Waste quantity × disposal unit cost.', 'reuse': 'Calculated from reuse/recycling credit rate and applicable quantity.', 'annual average': 'Total over the evaluation period ÷ evaluation years.'}
            fallback="Calculated from the current conditions and input data. Double-click or press F2 in the remarks column to add a note."
        text = str(item)
        for token, description in remarks.items():
            if token.lower() in text.lower():
                return description
        return fallback


    def change_language(self,language):
        self.i18n.set_language(language);self.title(self.i18n.t("module6"));self.build();attach_module_report_button(self,6)
        if self.result:self.show_result()

    def choose_project(self):
        p=filedialog.askopenfilename(initialdir=self.root_dir/"projects",filetypes=[("JSON","*.json")])
        if not p:return
        try:
            project=load_project(p)
            if not project.get("module_outputs",{}).get("module5"):
                raise ValueError(self.i18n.t("module5_required_m6"))
            self.project=project;self.project_path=Path(p);self.project_file.set(p)
        except Exception as exc:messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language))

    def apply_profile(self):
        ptype=self._profile_type_from_display()
        if ptype=="user":
            self.profile.set("User Defined")
            return

        rec=self._region_record() or {}
        rid=rec.get("id","JP_NAGOYA")

        # Japan/Nagoya keeps the existing verified baseline profiles.
        # Overseas standard investment-condition profiles will be enabled only
        # after their official source values are registered; do not silently
        # apply Japan assumptions to another country.
        if rid!="JP_NAGOYA":
            self.profile.set("User Defined")
            # Apply only values that have been verified and activated for the
            # selected region. Unverified fields are deliberately left unchanged.
            self.apply_region_profile()
            return

        key="Japan / Office" if ptype=="office" else "Japan / Residential"
        self.profile.set(key)
        p=self.db["profiles"][key]
        for k,val in p.items():
            if k in self.vars and k not in ("analysis_years","target_gross_yield_percent"):
                self.vars[k].set(str(val))
        self.vars["analysis_years"].set("200")
        self.vars["property_tax_percent_of_cost"].set("0")
        self.vars["target_gross_yield_percent"].set("8.0")
        self._user_target_yield="8.0"
        self._yield_field_shows_implied=False
        self.rent_setting_method.set("gross_yield")
        self._sync_rent_mode_combo()
        self._apply_yield_field_mode()
        self.apply_region_profile()

    def settings(self):
        # PATCH_006: in market-rent mode the yield entry shows a derived value
        # (possibly blank before the first calculation).  Submit the user's own
        # target instead, so switching modes can never turn a result into an
        # input.
        result={}
        for k,v in self.vars.items():
            raw=v.get()
            if k=="target_gross_yield_percent" and self._yield_field_shows_implied:
                raw=self._user_target_yield or "8.0"
            result[k]=float(str(raw).replace(",",""))
        result["rent_setting_method"]=self.rent_setting_method.get() or "gross_yield"
        # PATCH_009: persist whether the target yield is an active premise or
        # merely a stored preference for switching back to gross-yield mode.
        result["target_gross_yield_active"]=(result["rent_setting_method"]=="gross_yield")
        result["region_profile_id"]=self.region_id.get() or "JP_NAGOYA"
        result["analysis_years"]=200
        result["property_tax_percent_of_cost"]=0.0
        result["loan_term_years"]=int(result["loan_term_years"])
        result["total_dwelling_units"]=int(result["total_dwelling_units"])
        result["partial_renewal_affected_dwelling_units"]=int(result["partial_renewal_affected_dwelling_units"])
        if result["total_dwelling_units"] <= 0:
            raise ValueError("総住戸数は1以上で入力してください。" if self.i18n.language=="ja" else "Total dwelling units must be at least 1.")
        if result["partial_renewal_affected_dwelling_units"] <= 0:
            raise ValueError("同時工事住戸数は1以上で入力してください。" if self.i18n.language=="ja" else "Concurrent work units must be at least 1.")
        if result["partial_renewal_affected_dwelling_units"] > result["total_dwelling_units"]:
            raise ValueError("同時工事住戸数は総住戸数以下にしてください。" if self.i18n.language=="ja" else "Concurrent work units must not exceed total dwelling units.")
        if result["rent_setting_method"]=="gross_yield" and result["target_gross_yield_percent"] <= 0:
            raise ValueError("目標表面利回りは0より大きい値を入力してください。" if self.i18n.language=="ja" else "Target gross yield must be greater than zero.")
        if result["rent_setting_method"]=="market_rent" and result["annual_rent_per_m2"] <= 0:
            raise ValueError("市場家賃方式では年間賃料単価を0より大きい値で入力してください。" if self.i18n.language=="ja" else "In market-rent mode, annual rent per m² must be greater than zero.")
        result["use_loan"]=self.use_loan.get()
        return result

    def _empty_required_fields(self):
        """PATCH_009: return only fields required by the active rent method.

        Gross-yield mode does not require annual_rent_per_m2 because rent is
        derived from the target yield. Market-rent mode does not require
        target_gross_yield_percent because the yield field is a read-only
        result derived from rent and initial investment.
        """
        method=self.rent_setting_method.get() or "gross_yield"
        inactive=set()
        if method=="gross_yield":
            inactive.add("annual_rent_per_m2")
        elif method=="market_rent":
            inactive.add("target_gross_yield_percent")
        return [
            key for key, variable in self.vars.items()
            if key not in inactive and not variable.get().strip()
        ]

    def calculate(self):
        self.vars["analysis_years"].set("200")
        if self.project is None:
            messagebox.showwarning(
                "Warning",
                self.i18n.t("module5_required_m6"),
                parent=self,
            )
            return

        module5 = (
            self.project.get("module_outputs", {}).get("module5")
        )
        if not isinstance(module5, dict) or not module5:
            messagebox.showwarning(
                self.i18n.t("module6_prerequisite_title"),
                self.i18n.t("module6_module5_missing"),
                parent=self,
            )
            return

        total_cost = (
            module5.get("summary", {}).get("total_construction_cost")
        )
        try:
            total_cost = float(total_cost)
        except (TypeError, ValueError):
            total_cost = 0.0

        if total_cost <= 0:
            messagebox.showwarning(
                self.i18n.t("module6_prerequisite_title"),
                self.i18n.t("module6_module5_invalid"),
                parent=self,
            )
            return

        # PATCH_009: required fields depend on the selected rent-setting method.
        # In market-rent mode the visible yield field is intentionally blank
        # before the first calculation, so it must not trigger an input error.
        empty_fields = self._empty_required_fields()
        if empty_fields:
            labels = [
                self.i18n.t(key) if self.i18n.t(key) != key else key
                for key in empty_fields
            ]
            messagebox.showwarning(
                self.i18n.t("module6_input_error_title"),
                self.i18n.t("module6_empty_fields").format(
                    fields="、".join(labels)
                ),
                parent=self,
            )
            return

        try:
            settings = self.settings()
            self.result = calculate_investment(self.project, settings)
            self.show_result()
            # PATCH_006: refresh the derived yield shown in market-rent mode.
            self._apply_yield_field_mode()
            messagebox.showinfo(
                "OK",
                self.i18n.t("investment_complete"),
                parent=self,
            )
        except ValueError as exc:
            messagebox.showerror(
                self.i18n.t("module6_input_error_title"),
                str(exc),
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror(
                "Error",
                self.i18n.t("module6_unexpected_error").format(
                    error=f"{type(exc).__name__}: {exc}"
                ),
                parent=self,
            )

    def show_result(self):
        for tr in (self.summary_tree,self.tree):
            for iid in tr.get_children():tr.delete(iid)
        if hasattr(self,"horizon_tree"):
            for iid in self.horizon_tree.get_children():
                self.horizon_tree.delete(iid)
        if hasattr(self,"constant_price_tree"):
            for iid in self.constant_price_tree.get_children():
                self.constant_price_tree.delete(iid)
        if hasattr(self,"sensitivity_tree"):
            for iid in self.sensitivity_tree.get_children(): self.sensitivity_tree.delete(iid)
        if hasattr(self,"discount_sensitivity_tree"):
            for iid in self.discount_sensitivity_tree.get_children(): self.discount_sensitivity_tree.delete(iid)
        t=self.i18n.t;s=self.result["summary"];cur=self.result["currency"]
        L=lambda ja,en: ja if self.i18n.language=="ja" else en
        if hasattr(self,"horizon_tree"):
            for key in ("60","120","180","200"):
                hs=(self.result.get("horizon_summaries") or {}).get(key) or {}
                if not hs:
                    continue
                self.horizon_tree.insert("", "end", values=(
                    (f"{key}年" if self.i18n.language=="ja" else f"{key} years"),
                    f"{_f(hs.get('construction_cost_before_tax',hs.get('construction_cost'))):,.0f} {cur}",
                    f"{_f(hs.get('construction_tax')):,.0f} {cur}",
                    f"{_f(hs.get('unlevered_npv')):,.0f} {cur}",
                    f"{_f(hs.get('total_lifecycle_event_cost_before_tax',hs.get('total_lifecycle_event_cost'))):,.0f} {cur}",
                    f"{_f(hs.get('total_lifecycle_tax')):,.0f} {cur}",
                    f"{_f(hs.get('total_business_interruption_cost')):,.0f} {cur}",
                    f"{_f(hs.get('terminal_value')):,.0f} {cur}",
                    ((str(hs.get("simple_payback_year"))+"年") if self.i18n.language=="ja" else (str(hs.get("simple_payback_year"))+" years")) if hs.get("simple_payback_year") is not None else "-",
                ))
        if hasattr(self,"constant_price_tree"):
            for key in ("60","120","180","200"):
                cp=(self.result.get("constant_price_comparison") or {}).get(key) or {}
                if cp:
                    self.constant_price_tree.insert("", "end", values=(
                        (f"{key}年" if self.i18n.language=="ja" else f"{key} years"),
                        f"{_f(cp.get('initial_construction_cost_before_tax')):,.0f} {cur}",
                        f"{_f(cp.get('lifecycle_event_cost_base_year')):,.0f} {cur}",
                        f"{_f(cp.get('combined_construction_and_lifecycle_base_year')):,.0f} {cur}",
                    ))
        if hasattr(self,"sensitivity_tree"):
            scenarios=self.result.get("sensitivity_scenarios") or {}
            for skey in ("low","standard","high"):
                sc=scenarios.get(skey) or {}
                hs=sc.get("horizons") or {}
                if not hs:
                    continue
                self.sensitivity_tree.insert("", "end", values=(
                    (sc.get("label_ja",skey) if self.i18n.language=="ja" else sc.get("label_en",skey.title())),
                    f"{_f(sc.get('construction_rate_percent')):.1f}% / {_f(sc.get('inflation_rate_percent')):.1f}%",
                    f"{_f((hs.get('60') or {}).get('unlevered_npv')):,.0f} {cur}",
                    f"{_f((hs.get('120') or {}).get('unlevered_npv')):,.0f} {cur}",
                    f"{_f((hs.get('180') or {}).get('unlevered_npv')):,.0f} {cur}",
                    f"{_f((hs.get('200') or {}).get('unlevered_npv')):,.0f} {cur}",
                ))
        if hasattr(self,"discount_sensitivity_tree"):
            for key in sorted((self.result.get("discount_rate_sensitivity") or {}),key=lambda x:float(x)):
                ds=self.result["discount_rate_sensitivity"][key]; hs=ds.get("horizons") or {}; marker=" ★" if ds.get("is_current_input") else ""
                self.discount_sensitivity_tree.insert("", "end", values=(f"{_f(ds.get('discount_rate_percent')):.2f}%{marker}",
                    f"{_f((hs.get('50') or {}).get('unlevered_npv')):,.0f} {cur}",f"{_f((hs.get('100') or {}).get('unlevered_npv')):,.0f} {cur}",
                    f"{_f((hs.get('150') or {}).get('unlevered_npv')):,.0f} {cur}",f"{_f((hs.get('200') or {}).get('unlevered_npv')):,.0f} {cur}"))
        cf=self.result.get("cashflow") or []
        year1=cf[0] if cf else {}
        settings=self.result.get("settings") or {}
        lang=getattr(self.i18n,"language","ja")

        if lang == "ja":
            rows=[
                ("① 建設費",s.get("construction_cost"),cur,"Module 5で算定した建設費総額。","Module 5：建設費積算"),
                ("② 土地取得費",s.get("land_cost"),cur,"Module 6で入力した土地取得費。","Module 6：入力条件"),
                ("③ その他初期費用",s.get("other_initial_cost"),cur,"Module 6で入力したその他初期費用。","Module 6：入力条件"),
                ("④ 初期総投資額",s.get("initial_total_investment"),cur,"①＋②＋③","Module 5＋Module 6"),
                ("⑤ 借入額",s.get("loan_amount"),cur,"④×借入比率（借入を利用しない場合は0）","Module 6：借入条件"),
                ("⑥ 自己資金",s.get("equity_investment"),cur,"④－⑤","Module 6：算定"),
                ("⑦ 初年度総賃料",s.get("year1_gross_rent"),cur+"/year","表面利回り方式：初期投資額×目標表面利回り／市場家賃方式：延床面積×年間賃料単価","Module 6：家賃設定方式"),
                ("⑦-2 戸当たり月額家賃",s.get("year1_monthly_rent_per_unit"),cur+"/戸・月","初年度総賃料÷12÷総住戸数","Module 6：家賃設定結果"),
                ("⑧ 初年度有効賃料",s.get("year1_effective_rent"),cur+"/year","⑦×（1－空室率）","Module 6：空室率"),
                ("⑨ 初年度運営費",year1.get("operating_expense"),cur+"/year","⑧×運営費率","Module 6：運営費率"),
                ("⑩ 初年度維持修繕費",year1.get("maintenance_cost"),cur+"/year","①×年間維持修繕費率","Module 5＋Module 6"),
                ("⑪ 土地・建物関連税（別途）",None,"","国・地域により税制が異なるため本シミュレーションのCF計算対象外。別途考慮してください。","Module 6：税金除外方針"),
                ("⑫ 初年度保険料",year1.get("insurance_cost"),cur+"/year","①×保険料率","Module 5＋Module 6"),
                ("⑬ 初年度営業純収益（NOI）",s.get("year1_noi"),cur+"/year","⑧－⑨－⑩－⑫（土地・建物関連税は別途）","Module 6：投資評価計算"),
                ("⑭ 初年度表面利回り",s.get("year1_gross_yield_percent"),"%","⑦÷④×100","Module 6：投資評価計算"),
                ("⑮ 初年度営業純収益利回り（NOI利回り）",s.get("year1_noi_yield_percent"),"%","⑬÷④×100","Module 6：投資評価計算"),
                ("⑯ 事業正味現在価値（NPV・借入前）",s.get("unlevered_npv"),cur,"各年の借入前CFを割引率で現在価値化し、④を控除。","Module 6：全期間CF＋割引率"),
                ("⑰ 事業内部収益率（IRR・借入前）",s.get("unlevered_irr_percent"),"%","事業NPVが0となる内部収益率。CFの符号が複数回反転する場合は複数解となるため「-」表示。","Module 6：全期間CF"),
                ("⑱ 自己資金正味現在価値（NPV）",s.get("equity_npv"),cur,"借入返済後の各年CFを割引率で現在価値化し、⑥を控除。","Module 6：全期間CF＋借入条件"),
                ("⑲ 自己資金内部収益率（IRR）",s.get("equity_irr_percent"),"%","自己資金NPVが0となる内部収益率。CFの符号が複数回反転する場合は複数解となるため「-」表示。","Module 6：全期間CF＋借入条件"),
                ("⑳ 最終年売却価値",s.get("terminal_value"),cur,"評価最終年の翌年営業純収益（NOI）÷最終還元利回り（Cap Rate）。","Module 6：最終還元利回り"),
                ("㉑ 累積キャッシュフロー",s.get("cumulative_equity_cash_flow_ex_terminal",s.get("cumulative_equity_cash_flow")),cur,"－⑥＋評価期間中の自己資金CF累計。最終年売却価値は含めず、⑳に分離表示。","Module 6：キャッシュフロー"),
                ("㉒ 借入返済累計",s.get("total_debt_service"),cur,"各年の元利返済額の合計。","Module 6：借入条件・キャッシュフロー"),
                ("㉓ 初年度返済余裕倍率（DSCR）",s.get("year1_dscr"),"x","⑬÷初年度元利返済額。","Module 6：営業純収益（NOI）＋借入条件"),
                ("㉔ 単純回収年",s.get("simple_payback_year"),t("year_label"),"累積自己資金CFが0以上となる最初の年。","Module 6：キャッシュフロー"),
            ]
        else:
            rows=[
                ("① Construction cost",s.get("construction_cost"),cur,"Construction cost calculated in Module 5.","Module 5: Construction Cost"),
                ("② Land acquisition cost",s.get("land_cost"),cur,"Land cost entered in Module 6.","Module 6: Inputs"),
                ("③ Other initial cost",s.get("other_initial_cost"),cur,"Other initial cost entered in Module 6.","Module 6: Inputs"),
                ("④ Initial total investment",s.get("initial_total_investment"),cur,"① + ② + ③","Modules 5 + 6"),
                ("⑤ Loan amount",s.get("loan_amount"),cur,"④ × loan-to-cost ratio; zero when financing is disabled.","Module 6: Financing"),
                ("⑥ Equity investment",s.get("equity_investment"),cur,"④ - ⑤","Module 6: Calculation"),
                ("⑦ Year-1 gross rent",s.get("year1_gross_rent"),cur+"/year","Gross-yield mode: initial investment × target yield; market mode: GFA × annual rent/m².","Module 6: Rent-setting method"),
                ("⑦-2 Monthly rent per dwelling",s.get("year1_monthly_rent_per_unit"),cur+"/unit/month","Year-1 gross rent ÷ 12 ÷ dwelling units","Module 6: Rent result"),
                ("⑧ Year-1 effective rent",s.get("year1_effective_rent"),cur+"/year","⑦ × (1 - vacancy rate).","Module 6: Vacancy"),
                ("⑨ Year-1 operating expense",year1.get("operating_expense"),cur+"/year","⑧ × operating expense rate.","Module 6: Operating expense"),
                ("⑩ Year-1 maintenance",year1.get("maintenance_cost"),cur+"/year","① × annual maintenance rate.","Modules 5 + 6"),
                ("⑪ Land/building-related taxes (separate)",None,"","Excluded from this simulation cash flow because tax regimes vary by jurisdiction; consider separately.","Module 6: Tax-exclusion policy"),
                ("⑫ Year-1 insurance",year1.get("insurance_cost"),cur+"/year","① × insurance rate.","Modules 5 + 6"),
                ("⑬ Year-1 Net Operating Income (NOI)",s.get("year1_noi"),cur+"/year","⑧ - ⑨ - ⑩ - ⑫ (land/building taxes excluded)","Module 6: Investment calculation"),
                ("⑭ Year-1 gross yield",s.get("year1_gross_yield_percent"),"%","⑦ ÷ ④ × 100","Module 6: Investment calculation"),
                ("⑮ Year-1 NOI yield",s.get("year1_noi_yield_percent"),"%","⑬ ÷ ④ × 100","Module 6: Investment calculation"),
                ("⑯ Project Net Present Value (NPV, unlevered)",s.get("unlevered_npv"),cur,"Present value of all unlevered CF less ④.","Module 6: Full-period CF + discount rate"),
                ("⑰ Project Internal Rate of Return (IRR, unlevered)",s.get("unlevered_irr_percent"),"%","Discount rate at which project NPV equals zero. Shown as '-' when multiple cash-flow sign changes make conventional IRR non-unique.","Module 6: Full-period CF"),
                ("⑱ Equity Net Present Value (NPV)",s.get("equity_npv"),cur,"Present value of post-debt CF less ⑥.","Module 6: Full-period CF + financing"),
                ("⑲ Equity Internal Rate of Return (IRR)",s.get("equity_irr_percent"),"%","Discount rate at which equity NPV equals zero. Shown as '-' when multiple cash-flow sign changes make conventional IRR non-unique.","Module 6: Full-period CF + financing"),
                ("⑳ Terminal sale value",s.get("terminal_value"),cur,"Next-year Net Operating Income (NOI) ÷ terminal capitalization rate (Cap Rate).","Module 6: Terminal cap rate"),
                ("㉑ Cumulative cash flow",s.get("cumulative_equity_cash_flow_ex_terminal",s.get("cumulative_equity_cash_flow")),cur,"-⑥ + cumulative equity CF excluding terminal sale; terminal value is reported separately in ⑳.","Module 6: Cash flow"),
                ("㉒ Cumulative debt service",s.get("total_debt_service"),cur,"Sum of annual principal and interest payments.","Module 6: Financing + cash flow"),
                ("㉓ Year-1 Debt Service Coverage Ratio (DSCR)",s.get("year1_dscr"),"x","⑬ ÷ Year-1 debt service.","Module 6: Net Operating Income (NOI) + financing"),
                ("㉔ Simple payback year",s.get("simple_payback_year"),t("year_label"),"First year cumulative equity CF becomes non-negative.","Module 6: Cash flow"),
            ]

        for item,value,unit,basis,source in rows:
            if value is None:
                display="-"
            elif unit in ("%","x"):
                display=format_number(value,unit)
            elif unit==t("year_label"):
                display=f"{int(value)}"
            else:
                display=format_number(value,unit)
            display_basis=merge_note(self.user_notes,item,basis)
            self.summary_tree.insert("","end",values=(item,display,unit,display_basis,source))

        for r in self.result["cashflow"]:
            self.tree.insert("","end",values=(
                r["year"],format_number(r["gross_rent"],cur),format_number(r["effective_rent"],cur),
                format_number(r.get("construction_rent_loss",0.0),cur),
                format_number(r.get("relocation_tenant_cost",0.0),cur),
                format_number(r["operating_expense"],cur),format_number(r["maintenance_cost"],cur),
                format_number(r["noi"],cur),format_number(r.get("lifecycle_event_cost",0.0),cur),
                format_number(r["debt_service"],cur),
                format_number(r["before_tax_cash_flow"],cur),format_number(r["discounted_cash_flow"],cur),
                format_number(r["loan_balance"],cur)
            ))
        self.update_investment_charts()

    def _cf_payback_year(self,rows):
        """Same rule as 03_Compare's _discounted_payback_year: first year the
        series reaches/crosses zero from below."""
        prev=None
        for year,value in rows:
            if prev is None and value>=0:return int(year)
            if prev is not None and prev[1]<0<=value:return int(year)
            prev=(year,value)
        return None

    def update_investment_charts(self):
        """Draw the same two recovery graphs 03_Compare shows in its
        comparison view (単純投資回収 / 現在価値ベース回収), but for this
        single project only (Compare cannot be run standalone with just one
        Project JSON)."""
        if not hasattr(self,"nominal_cf_chart") or not self.result:
            return
        ja=self.i18n.language=="ja"
        L=lambda j,e: j if ja else e
        s=self.result.get("summary") or {}
        cf=self.result.get("cashflow") or []
        cur=self.result.get("currency") or self._project_currency()
        initial=s.get("initial_total_investment")

        def series_for(key):
            rows=[(0,-initial)] if initial is not None else []
            for r in cf:
                y=r.get("year");v=r.get(key)
                if y is None or v is None:continue
                rows.append((int(y),v))
            return rows

        nominal_rows=series_for("cumulative_unlevered_cash_flow_ex_terminal")
        discounted_rows=series_for("cumulative_discounted_unlevered_cash_flow_ex_terminal")

        py_nominal=self._cf_payback_year(nominal_rows)
        py_discounted=self._cf_payback_year(discounted_rows)

        self.simple_payback_label.config(text=L("単純投資回収年：","Simple payback year: ")+(
            L(f"{py_nominal}年",f"Year {py_nominal}") if py_nominal is not None
            else L("期間内未回収","not recovered within the period")
        ))
        self.cash_payback_label.config(text=L("現在価値ベース回収：","Present-value recovery: ")+(
            L(f"{py_discounted}年",f"Year {py_discounted}") if py_discounted is not None
            else L("期間内未回収","not recovered within the period")
        ))

        max_year=max((y for y,_ in nominal_rows),default=0)
        display_year=min(max_year,max(30,(py_nominal or 0)+10)) if nominal_rows else 50
        nominal_display=[(y,v) for y,v in nominal_rows if y<=display_year]
        self.nominal_cf_chart.set_data(
            L(f"単純投資回収（0～{display_year}年・初回回収点拡大）",
              f"Simple Payback (0-{display_year} years, zoomed to first recovery)"),
            cur,list(range(0,display_year+1)),
            [(L("累積CF","Cumulative CF"),nominal_display)] if nominal_display else [],
            tick_every=5,
            empty_message=L("単純投資回収用の名目累積CFを作成できません。",
                             "Cannot build nominal cumulative CF for simple payback."),
            zero_line=True,
            zero_line_label=L("±0（投資回収基準）","±0 (payback threshold)"),
        )

        disc_max_year=max((y for y,_ in discounted_rows),default=0)
        self.discounted_cf_chart.set_data(
            L(f"現在価値累積CF（0～{disc_max_year}年・終価除外・土地建物税別途）",
              f"Present-Value Cumulative CF (0-{disc_max_year} years, ex-terminal, taxes separate)"),
            cur,list(range(0,disc_max_year+1)),
            [(L("累積現在価値CF","Cumulative PV CF"),discounted_rows)] if discounted_rows else [],
            tick_every=10,
            empty_message=L("指定期間までの現在価値累積CFを作成できません。",
                             "Cannot build present-value cumulative CF for the given period."),
            zero_line=True,
            zero_line_label=L("±0（投資回収基準）","±0 (payback threshold)"),
        )

    def save_csv(self):
        if not self.result:return
        default_path=default_export_path(self.project_path,6,label="Module6_投資評価_キャッシュフロー")
        p=filedialog.asksaveasfilename(initialdir=default_path.parent,initialfile=default_path.name,defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if not p:return
        rows=self.result["cashflow"]
        # PATCH_014: header follows the UI language; English unchanged.
        write_dict_rows_csv(p,rows,self.i18n.language)

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
                "module6",
                self.result,
                {
    "settings": self.settings(),
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
