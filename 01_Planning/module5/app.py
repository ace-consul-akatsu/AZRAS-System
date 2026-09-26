
from __future__ import annotations
import csv
import json
import os
import re
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from services.project_export_paths import default_export_path, project_output_directory

from core.i18n import I18N
from core.error_text import friendly_exception_text
from core.ai_security_audit import PublicEvidencePolicyError, enforce_public_evidence_urls, record_ai_import_audit, record_ai_request_audit
from core.canonical_language import LANGUAGE_OPTIONS
from core.ui_style import (
    apply_common_style, standardize_module_window, create_scrollable_module_page,
    add_module_text_copy_button, fit_window_to_screen
)
from core.module_report_ui import attach_module_report_button
from core.project_store import load_project, save_project, comparison_copy_block_reason, comparison_copy_info
from core.project_coordinator import update_module_and_propagate, format_report, module_output_is_current, require_current_module_output, module_output_fingerprint, module1_cost_dependency_fingerprint
from core.number_format import format_number, header_with_unit, parse_number, format_input_number
from ui.editable_remarks import bind_editable_remarks, merge_note
from services.construction_cost_engine_v9_4 import (
    calculate_construction_cost, resolve_location_profile_from_project,
    evaluate_unit_cost_dataset_freshness, extract_quantities
)

INPUT_BG="#fff4b8"
AUTO_BG="#d9efff"
RESULT_BG="#dff3df"

AZRAS_AI_STANDARD_RULES_V3_EN = """[AZRAS AI REQUEST STANDARD RULES v3 — TIME, EVIDENCE, AND TECHNICAL SAFETY CONTROLS]
1. RESPONSE-TIME TARGET: Aim to complete this response within 10 minutes. Do not stop merely to ask whether to continue when the target is reached. If additional searching/re-verification would exceed the target without materially improving the evidence, stop expanding the search and finish the required JSON, leaving genuinely unresolved items explicitly unresolved. Accuracy and evidence integrity remain higher priority than speed.
2. MINIMUM PRIVILEGE: do not connect to, attempt to log into, or guess/use credentials for any closed network or authenticated system. Do not retrieve data beyond the supplied materials and ordinary public web search/browsing. Do not write to, modify, or execute any action on an external system unless this request explicitly authorizes it.
3. TECHNICAL AZRAS IMPORT BOUNDARY: AZRAS accepts evidence URLs only from public HTTP/HTTPS origins. localhost, loopback, RFC1918/private/link-local targets, credential-bearing URLs, single-label intranet hosts, and non-web schemes are rejected by code when the response is imported. The AZRAS request packet contains no private-network credentials or private endpoints. This is an AZRAS-side enforcement boundary; do not claim that AZRAS controls the AI provider's internal network architecture.
4. SANDBOXING: confine the work to the supplied drawings/specifications/data and public web information. Do not perform sending, execution, setting changes, or any other operation that can cause real-world effects on an external system.
5. HUMAN-APPROVAL CHECKPOINT: if an action outside this scope is necessary, do not perform it. State the missing requirement in the returned evidence/status. Do not interrupt an otherwise completable JSON response merely to ask for permission.
6. EVIDENCE-SUFFICIENCY STOP RULE: avoid repeated search or repeated re-verification once sufficient evidence exists. Prefer the most direct source first; escalate only when needed. Do not accumulate extra sources solely to increase source count.
7. OBSERVABLE AUDIT LOGGING: AZRAS records each generated request and each imported/rejected AI response using hashes, reviewer/time metadata, explicit source URLs and validation/security anomalies, and refreshes a rolling 7-day anomaly summary for AZRAS operator/designer review. Hidden chain-of-thought is neither requested nor stored; only explicit evidence/reason fields returned in the JSON are auditable.
8. MONITORING AND ANOMALY REPORTING: if the task appears to require unauthorized access, an out-of-scope data source, or another unusual action, do not perform it. Report the limitation in the structured result and list the sources actually consulted.
"""
# Compatibility alias for code or documentation that still names the v2 constant.
AZRAS_AI_STANDARD_RULES_V2_EN = AZRAS_AI_STANDARD_RULES_V3_EN


class Module5App(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language: str = "ja", project_context=None):
        super().__init__(master)
        apply_common_style(self)
        standardize_module_window(self,5)
        self.project_context = project_context
        self.root_dir=Path(root_dir)
        self.i18n=I18N(self.root_dir,language)
        self.project=None
        self.project_path=None
        self.result=None
        self.user_notes={}
        self.project_file=tk.StringVar()
        self.project_state_notice=tk.StringVar(value="")
        self.location=tk.StringVar(value="Japan / Nagoya")
        # PATCH 468: show the authoritative Project location separately from the legacy representative profile.
        self.project_cost_location=tk.StringVar(value="-")
        # PATCH 448: planning and detailed pricing share the same quantity/cost engine.
        # Only the unit-cost sourcing policy changes.
        self.cost_provider_mode=tk.StringVar(value="approximate")
        self.currency=tk.StringVar(value="JPY")
        self.unit_cost_data_date=tk.StringVar(value="-")
        self.unit_cost_source=tk.StringVar(value="-")
        self.unit_cost_freshness=tk.StringVar(value="not_available")
        self.regional_cost_coverage=tk.StringVar(value=("地域単価カバレッジ: 未計算" if language=="ja" else "Regional cost coverage: Not calculated"))
        self.market_validity_summary=tk.StringVar(value=("建設費妥当性: 未計算" if language=="ja" else "Construction-cost validity: Not calculated"))
        self.market_calibration_summary=tk.StringVar(value=("2026市場校正: 未計算" if language=="ja" else "2026 market calibration: Not calculated"))
        # PATCH 464: session-only AI Approximate Cost Provider exchange.
        # The raw AI response is not copied into AZRAS and no global unit-cost DB is written.
        self.ai_cost_session=None
        self.ai_cost_session_status=tk.StringVar(value=("AI概算単価: 未取込" if language=="ja" else "AI approximate prices: Not imported"))
        # PATCH 420: make incomplete pricing visible beside the total itself.
        self.total_completeness_notice=tk.StringVar(value="")
        self.cost_year=tk.StringVar(value="2026")
        self.use_common_2004_price_basis=tk.BooleanVar(value=True)
        self.common_2004_to_target_cost_factor=tk.StringVar(value="1.60")
        self.common_2004_market_calibration_factor=tk.StringVar(value="0.5630355")
        self.material_index=tk.StringVar(value="105")
        self.labor_index=tk.StringVar(value="105")
        self.productivity_index=tk.StringVar(value="100")
        self.site_condition=tk.StringVar(value="flat_clear")
        self.access_condition=tk.StringVar(value="good")
        self.work_time_condition=tk.StringVar(value="day")
        self.excavated_soil_stockpile_mode=tk.StringVar(value="no_stockpile")
        self.rates={}
        self.equipment_vars={}
        self.rc_foundation_unit_price_vars={
            k:tk.StringVar(value="0") for k in (
                "excavation","backfill","imported_fill","soil_disposal","blinding_concrete","ground_preparation"
            )
        }
        self.custom_conditions=[]
        self.condition_matrix=self._default_condition_matrix()
        self.db=json.loads(
            (self.root_dir/"data"/"construction_cost_database_v9_4.json")
            .read_text(encoding="utf-8"))
        for key,val in self.db["rates"].items():
            self.rates[key]=tk.StringVar(value=str(val))
        if self.project_context is not None and self.project_context.path is not None:
            self.project = self.project_context.reload()
            self.project_path = self.project_context.path
            self.project_file.set(self.project_context.display_path)
        self.title(self.i18n.t("module5"))
        self.build();attach_module_report_button(self,5)
        self.apply_location()
        self._apply_project_location_initial_profile()
        self._refresh_project_cost_location()
        self.restore_saved_state()
        self.bind("<FocusIn>", self.refresh_project_from_context)

    def _default_condition_matrix(self):
        """Four groups x five rows. Existing three choices are preloaded; blank rows remain editable."""
        result={"site":[],"access":[],"work_time":[],"reserve":[]}
        defaults={
            "site":[
                ("flat_clear","平坦・障害物なし・十分な施工ヤード",0.0,"標準条件。補正なし。"),
                ("moderate","一般的な市街地条件",8.0,"施工ヤード・周辺制約を考慮した企画比較用補正。"),
                ("difficult","狭小・高低差・障害物あり",20.0,"小運搬・仮設・施工能率低下を考慮した企画比較用補正。"),
            ],
            "access":[
                ("good","大型車搬入可能",0.0,"標準搬入条件。補正なし。"),
                ("restricted","大型車搬入制限あり",8.0,"車両制限・小運搬増加を考慮した企画比較用補正。"),
                ("manual","小運搬・人力搬入が多い",18.0,"小運搬・人力搬入の増加を考慮した企画比較用補正。"),
            ],
            "work_time":[
                ("day","昼間施工",0.0,"標準作業時間。補正なし。"),
                ("limited","時間制限あり",8.0,"作業可能時間の制限による能率低下を考慮。"),
                ("night","夜間・休日施工を含む",20.0,"割増賃金・照明・管理費増加を考慮。"),
            ],
        }
        selected={"site":"flat_clear","access":"good","work_time":"day"}
        for category in ("site","access","work_time"):
            for key,name,rate,basis in defaults[category]:
                result[category].append({"checked":key==selected[category],"key":key,"condition":name,"rate_percent":rate,"amount_jpy":None,"amount_local_currency":None,"amount_currency":None,"basis":basis})
            while len(result[category])<5:
                result[category].append({"checked":False,"key":"","condition":"","rate_percent":0.0,"amount_jpy":None,"amount_local_currency":None,"amount_currency":None,"basis":""})
        for _ in range(5):
            result["reserve"].append({"checked":False,"key":"","condition":"","rate_percent":0.0,"amount_jpy":None,"amount_local_currency":None,"amount_currency":None,"basis":""})
        return result

    def _selected_condition_row(self, category):
        rows=self.condition_matrix.get(category,[])
        for row in rows:
            if row.get("checked"):
                return row
        return rows[0] if rows else {"rate_percent":0.0,"condition":""}

    def _sync_legacy_condition_vars(self):
        mapping=(("site",self.site_condition),("access",self.access_condition),("work_time",self.work_time_condition))
        for category,var in mapping:
            row=self._selected_condition_row(category)
            key=row.get("key") or var.get()
            if key:
                var.set(key)

    def _refresh_project_state_notice(self):
        if not hasattr(self, "project_state_notice"):
            return
        project = self.project if isinstance(self.project, dict) else {}
        messages = []
        for key, label in (("module1", "Module 1"), ("module5", "Module 5")):
            output = (project.get("module_outputs") or {}).get(key)
            if isinstance(output, dict) and output and not module_output_is_current(project, key):
                state = str(((project.get("module_status") or {}).get(key) or {}).get("status") or "stale")
                messages.append(f"{label}: {state}")
        if messages:
            if self.i18n.language == "ja":
                self.project_state_notice.set("⚠ 再計算が必要です: " + " / ".join(messages))
            else:
                self.project_state_notice.set("⚠ Recalculation required: " + " / ".join(messages))
        else:
            self.project_state_notice.set("")

    def _apply_project_location_initial_profile(self):
        """PATCH 429: initialize an uncalculated Module 5 from Project location.

        Saved Module 5 snapshots remain authoritative user choices.  This helper
        only supplies the initial profile when Module 5 has not yet been saved.
        """
        project = self.project if isinstance(self.project, dict) else {}
        saved = (project.get("module_outputs") or {}).get("module5")
        if isinstance(saved, dict) and saved:
            return False
        resolved = resolve_location_profile_from_project(project, self.db)
        key = resolved.get("location_key") or resolved.get("fallback_location_key")
        if key and key in (self.db.get("locations") or {}):
            self.location.set(str(key))
            self.apply_location()
            return True
        return False

    def refresh_project_from_context(self, event=None):
        """Synchronize the active Project JSON even when its path did not change.

        PATCH 423: another open module can update the same Project file.  Comparing
        only the pathname left Module 5 holding an old in-memory Module 1 result.
        Always synchronize from disk on focus/action so same-path updates are seen.
        """
        if self.project_context is None or self.project_context.path is None:
            return False
        active_path = self.project_context.path
        latest = self.project_context.synchronize_from_disk()
        if latest is None:
            return False
        self.project = latest
        self.project_path = active_path
        if hasattr(self, "project_file"):
            self.project_file.set(self.project_context.display_path)
        self._apply_project_location_initial_profile()
        self._refresh_project_state_notice()
        return True

    def _ui(self, ja, en):
        return ja if self.i18n.language == "ja" else en

    def build(self):
        for w in self.winfo_children():
            w.destroy()
        # PATCH 432: Module 5 uses a true two-pane workspace.  The upper
        # assumptions pane scrolls independently; the lower result pane stays
        # visible and can be resized with the horizontal sash.
        page=ttk.Frame(self)
        page.pack(fill="both",expand=True)
        t=self.i18n.t
        ui=self._ui
        self._equipment_currency_labels=[]
        self._rc_currency_labels=[]

        # PATCH 432: mirror Module 1's vertical result splitter.  The upper pane
        # contains project/cost assumptions, while the lower pane contains the
        # cost breakdown/results.  Users can drag the horizontal sash to give
        # either side more room without changing the calculation state.
        self.result_vertical_split=tk.PanedWindow(
            page, orient="vertical", sashwidth=9, sashrelief="raised", bd=0
        )
        self.result_vertical_split.pack(fill="both",expand=True)
        upper_host=ttk.Frame(self.result_vertical_split)
        lower_panel=ttk.Frame(self.result_vertical_split)
        self.result_vertical_split.add(upper_host,minsize=180,stretch="always")
        self.result_vertical_split.add(lower_panel,minsize=220,stretch="always")

        # Independent scrolling for the (long) Module 5 assumption area.
        upper_canvas=tk.Canvas(upper_host,highlightthickness=0,borderwidth=0)
        upper_scroll=ttk.Scrollbar(upper_host,orient="vertical",command=upper_canvas.yview)
        upper_xscroll=ttk.Scrollbar(upper_host,orient="horizontal",command=upper_canvas.xview)
        upper_canvas.configure(yscrollcommand=upper_scroll.set,xscrollcommand=upper_xscroll.set)
        upper_host.rowconfigure(0,weight=1);upper_host.columnconfigure(0,weight=1)
        upper_canvas.grid(row=0,column=0,sticky="nsew")
        upper_scroll.grid(row=0,column=1,sticky="ns")
        upper_xscroll.grid(row=1,column=0,sticky="ew")
        upper_panel=ttk.Frame(upper_canvas)
        _upper_window=upper_canvas.create_window((0,0),window=upper_panel,anchor="nw")
        def _sync_upper_scroll(_event=None):
            try:
                upper_canvas.update_idletasks()
                # PATCH 493: preserve the original Module 5 content width.
                # On a wide/maximized monitor the controls no longer spread apart;
                # on a smaller monitor the existing horizontal scrollbar exposes
                # the rest of the unchanged layout.
                design_w=max(1,int(getattr(self,"_azras_design_width",1600))-28)
                upper_canvas.itemconfigure(
                    _upper_window,
                    width=max(1,design_w,upper_panel.winfo_reqwidth())
                )
                upper_canvas.configure(scrollregion=upper_canvas.bbox("all"))
            except tk.TclError:
                pass
        upper_panel.bind("<Configure>",_sync_upper_scroll,add="+")
        upper_canvas.bind("<Configure>",_sync_upper_scroll,add="+")
        def _upper_wheel(event):
            try:
                upper_canvas.yview_scroll((-3 if event.delta>0 else 3),"units")
            except tk.TclError:
                pass
            return "break"
        upper_canvas.bind("<MouseWheel>",_upper_wheel)
        upper_panel.bind("<MouseWheel>",_upper_wheel)

        # Start near a 55/45 split, but only after Tk knows the real window size.
        def _set_initial_split():
            try:
                h=max(500,self.winfo_height())
                self.result_vertical_split.sash_place(0,0,int(h*0.55))
            except tk.TclError:
                pass
        self.after_idle(_set_initial_split)

        top=ttk.Frame(upper_panel)
        top.pack(fill="x",padx=10,pady=6)
        add_module_text_copy_button(self,top)
        ttk.Label(top,text=t("language")).pack(side="left")
        lang=tk.StringVar(value="日本語" if self.i18n.language=="ja" else "English")
        cb=ttk.Combobox(top,textvariable=lang,values=LANGUAGE_OPTIONS,state="readonly",width=12)
        cb.pack(side="left",padx=5)
        cb.bind("<<ComboboxSelected>>",
                lambda e:self.change_language("ja" if lang.get()=="日本語" else "en"))



        ttk.Button(
            top, text=t("print_this_module"), style="Primary.TButton",
            command=lambda: self.print_module_report()
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_module5"), command=self.save_output
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_cost_csv"), command=self.save_csv
        ).pack(side="right", padx=4)

        project=ttk.LabelFrame(upper_panel,text=t("project"))
        project.pack(fill="x",padx=10,pady=5)
        ttk.Label(project,text=t("project_json")).grid(row=0,column=0,padx=5,pady=4)
        tk.Entry(
            project,
            textvariable=self.project_file,
            width=108,
            state="readonly",
            readonlybackground=AUTO_BG,
        ).grid(row=0,column=1,padx=5,pady=4,sticky="ew")
        ttk.Label(project,textvariable=self.project_state_notice,foreground="#b00020",wraplength=900,justify="left").grid(row=1,column=0,columnspan=2,padx=5,pady=(0,4),sticky="w")
        project.columnconfigure(1,weight=1)
        self._refresh_project_state_notice()

        conditions=ttk.LabelFrame(upper_panel,text=t("cost_conditions"))
        conditions.pack(fill="x",padx=10,pady=5)

        ttk.Label(conditions,text=ui("建設費調査地域","Construction Cost Location")).grid(
            row=0,column=0,padx=5,pady=4
        )
        ttk.Label(conditions,textvariable=self.project_cost_location,foreground="#006400").grid(
            row=0,column=1,columnspan=2,padx=5,pady=4,sticky="w"
        )
        ttk.Label(conditions,text=ui("代表地域プロファイル（参考）","Representative Regional Profile (reference)")).grid(
            row=1,column=0,padx=5,pady=4
        )
        location_cb=ttk.Combobox(conditions,textvariable=self.location,
                                 values=list(self.db["locations"].keys()),
                                 state="readonly",width=28)
        location_cb.grid(row=1,column=1,padx=5,pady=4)
        location_cb.bind("<<ComboboxSelected>>",lambda e:self.apply_location())
        ttk.Button(conditions,text=t("apply_location_cost"),
                   command=self.apply_location).grid(row=1,column=2,padx=5)

        labels_vars=[
            ("currency",self.currency),("cost_year",self.cost_year),
            ("material_index",self.material_index),("labor_index",self.labor_index),
            ("productivity_index",self.productivity_index)
        ]
        for i,(label,var) in enumerate(labels_vars):
            r=0 if i<2 else 2
            c=3+(i if i<2 else i-2)*2
            ttk.Label(conditions,text=t(label)).grid(row=r,column=c,padx=4,pady=4)
            tk.Entry(conditions,textvariable=var,bg=INPUT_BG,width=11).grid(
                row=r,column=c+1,padx=4,pady=4)

        common_basis=ttk.LabelFrame(upper_panel,text=ui("3工法共通 2004年価格基準","Common 2004 Price Basis for Three Methods"))
        common_basis.pack(fill="x",padx=10,pady=5)
        ttk.Checkbutton(common_basis,text=ui("AZRAS・2×6・RCラーメンを同一の2004年価格基準で比較","Compare AZRAS, 2x6 and RC frame on the same 2004 price basis"),
                        variable=self.use_common_2004_price_basis).grid(row=0,column=0,columnspan=5,sticky="w",padx=6,pady=4)
        ttk.Label(common_basis,text=ui("2004年→評価年 上昇係数","2004 → evaluation-year escalation factor")).grid(row=1,column=0,sticky="w",padx=6)
        tk.Entry(common_basis,textvariable=self.common_2004_to_target_cost_factor,bg=INPUT_BG,width=10).grid(row=1,column=1,sticky="w",padx=4)
        ttk.Label(common_basis,text=ui("共通市場校正係数","Common market calibration factor")).grid(row=1,column=2,sticky="w",padx=6)
        tk.Entry(common_basis,textvariable=self.common_2004_market_calibration_factor,bg=INPUT_BG,width=10).grid(row=1,column=3,sticky="w",padx=4)
        ttk.Label(common_basis,text=ui("全工法に同じ価格係数を適用。価格差は数量・施工歩掛り・工種構成から算出。","The same price factors are applied to all methods; cost differences come from quantities, productivity and trade composition."),
                  foreground="#8b0000").grid(row=2,column=0,columnspan=5,sticky="w",padx=6,pady=3)
        ttk.Label(common_basis,text=ui("校正基準：高島2号 2004-09-25／34,500,000円（税別）／延床245.52m²／外断熱なし。AZRASだけの総額置換はしません。","Calibration reference: Takashima No.2, 2004-09-25 / JPY 34,500,000 excl. tax / GFA 245.52 m² / no external insulation. AZRAS total is not replaced separately."),
                  foreground="#555").grid(row=3,column=0,columnspan=5,sticky="w",padx=6,pady=(0,4))

        ttk.Button(
            conditions,
            text=ui("施工条件追加","Add Construction Conditions"),
            command=self.edit_custom_conditions,
        ).grid(row=2,column=0,columnspan=2,padx=5,pady=6,sticky="w")
        ttk.Label(
            conditions,
            text=ui("敷地・搬入・作業時間・予備の各5行からチェック選択します。","Select from five rows each for site, access, work-time and contingency conditions."),
            foreground="#555555",
        ).grid(row=2,column=2,columnspan=6,padx=5,pady=6,sticky="w")

        rates_frame=ttk.Frame(conditions)
        rates_frame.grid(row=3,column=0,columnspan=8,sticky="w")
        rate_defs=[
            ("overhead_rate","overhead_percent"),("contingency_rate","contingency_percent"),
            ("design_rate","design_supervision_percent"),("tax_rate","tax_percent")
        ]
        for i,(label,key) in enumerate(rate_defs):
            ttk.Label(rates_frame,text=t(label)).grid(row=0,column=i*2,padx=4,pady=4)
            tk.Entry(rates_frame,textvariable=self.rates[key],bg=INPUT_BG,width=10).grid(
                row=0,column=i*2+1,padx=4,pady=4)

        equipment=ttk.LabelFrame(upper_panel,text=t("equipment_packages"))
        equipment.pack(fill="x",padx=10,pady=5)
        headers=[t("include"),t("item"),t("package_cost")]
        for c,h in enumerate(headers):
            ttk.Label(equipment,text=h).grid(row=0,column=c,padx=6,pady=3)
        lang_key="ja" if self.i18n.language=="ja" else "en"
        if not self.equipment_vars:
            for key,item in self.db["equipment_packages"].items():
                self.equipment_vars[key]={
                    "include":tk.BooleanVar(value=(key in {"hvac","electrical","plumbing","kitchen","bathroom"})),
                    "cost":tk.StringVar(value=str(item["default_cost_jpy"]))
                }
        for r,(key,item) in enumerate(self.db["equipment_packages"].items(),1):
            ttk.Checkbutton(equipment,variable=self.equipment_vars[key]["include"]).grid(
                row=r,column=0,padx=6,pady=2)
            ttk.Label(equipment,text=item[lang_key]).grid(row=r,column=1,padx=6,pady=2,sticky="w")
            self.equipment_vars[key]["cost"].set(
                format_input_number(self.equipment_vars[key]["cost"].get())
            )
            cost_entry=tk.Entry(
                equipment,textvariable=self.equipment_vars[key]["cost"],
                bg=INPUT_BG,width=18,justify="right"
            )
            cost_entry.grid(row=r,column=2,padx=(6,2),pady=2)
            cost_entry.bind(
                "<FocusIn>",
                lambda _e,v=self.equipment_vars[key]["cost"]:
                    v.set(str(int(parse_number(v.get()))))
            )
            cost_entry.bind(
                "<FocusOut>",
                lambda _e,v=self.equipment_vars[key]["cost"]:
                    v.set(format_input_number(v.get()))
            )
            _cur_label=ttk.Label(equipment,text=self.currency.get() or "JPY")
            _cur_label.grid(row=r,column=3,padx=(2,8),pady=2,sticky="w")
            self._equipment_currency_labels.append(_cur_label)

        provider=ttk.LabelFrame(upper_panel,text=ui("建設費 Cost Provider","Construction Cost Provider"))
        provider.pack(fill="x",padx=10,pady=5)
        # PATCH_458: AZRAS business planning uses approximate cost only. Detailed
        # estimating is handed off as a detailed-quantity CSV from Module 1.
        self.cost_provider_mode.set("approximate")
        ttk.Label(provider,text="AZRAS Approximate Cost Provider").grid(row=0,column=0,sticky="w",padx=8,pady=3)
        ttk.Label(
            provider,
            text=ui("事業計画用：無料概算データ。詳細見積はModule 1の詳細数量CSVを外部積算へ渡します。",
                    "Business planning: free approximate data. Detailed estimating uses the Module 1 detailed-quantity CSV outside AZRAS.")
        ).grid(row=0,column=1,sticky="w",padx=8,pady=3)
        provider.columnconfigure(1,weight=1)

        costdata=ttk.LabelFrame(upper_panel,text=ui("地域単価データ","Regional Unit-Cost Data"))
        costdata.pack(fill="x",padx=10,pady=5)
        ttk.Label(costdata,text=ui("データ年月","Data date")).grid(row=0,column=0,sticky="w",padx=8,pady=3)
        ttk.Label(costdata,textvariable=self.unit_cost_data_date).grid(row=0,column=1,sticky="w",padx=5,pady=3)
        ttk.Label(costdata,text=ui("出典","Source")).grid(row=1,column=0,sticky="w",padx=8,pady=3)
        ttk.Label(costdata,textvariable=self.unit_cost_source).grid(row=1,column=1,sticky="w",padx=5,pady=3)
        ttk.Label(costdata,text=ui("状態","Status")).grid(row=2,column=0,sticky="w",padx=8,pady=3)
        ttk.Label(costdata,textvariable=self.unit_cost_freshness).grid(row=2,column=1,sticky="w",padx=5,pady=3)
        ttk.Label(costdata,textvariable=self.regional_cost_coverage).grid(row=3,column=0,columnspan=2,sticky="w",padx=8,pady=3)
        ttk.Label(costdata,textvariable=self.market_validity_summary).grid(row=4,column=0,columnspan=3,sticky="w",padx=8,pady=3)
        ttk.Label(costdata,textvariable=self.market_calibration_summary).grid(row=5,column=0,columnspan=3,sticky="w",padx=8,pady=3)
        # PATCH 465: AI research is the standard Approximate Cost Provider path.
        # PATCH 503: make every AI-cost research step explicit so the same import
        # button is not mentally reused for three different stages.  All three
        # import buttons intentionally use the same validated importer; the
        # surrounding request/re-check functions enforce the required evidence order.
        ttk.Button(costdata,text=ui("① ChatGPT一次調査依頼書","1. Create ChatGPT Primary Research Request"),command=self.show_ai_cost_request).grid(row=0,column=2,sticky="ew",padx=8,pady=3)
        ttk.Button(costdata,text=ui("② ChatGPT調査JSON取込","2. Import ChatGPT Research JSON"),command=self.import_ai_cost_json).grid(row=1,column=2,sticky="ew",padx=8,pady=3)
        ttk.Button(costdata,text=ui("③ 他AI再調査依頼書","3. Create Independent AI Review Request"),command=self.show_ai_cost_review_request).grid(row=2,column=2,sticky="ew",padx=8,pady=3)
        ttk.Button(costdata,text=ui("④ 各AIのJSONを順次取込","4. Import Each AI JSON in Sequence"),command=self.import_ai_cost_json).grid(row=3,column=2,sticky="ew",padx=8,pady=3)
        ttk.Button(costdata,text=ui("⑤ ChatGPT最終再確認依頼書","5. Create ChatGPT FINAL Re-check Request"),command=self.show_ai_cost_recheck_request).grid(row=4,column=2,sticky="ew",padx=8,pady=3)
        ttk.Button(costdata,text=ui("⑥ ChatGPT最終再確認JSON取込 → 終了","6. Import ChatGPT FINAL Re-check JSON → Finish"),command=self.import_ai_cost_json).grid(row=5,column=2,sticky="ew",padx=8,pady=3)
        ttk.Button(costdata,text=ui("建設費妥当性詳細","Construction-Cost Validity Details"),command=self.show_cost_validity_diagnostic).grid(row=6,column=2,sticky="ew",padx=8,pady=3)
        ttk.Separator(costdata,orient="horizontal").grid(row=7,column=2,sticky="ew",padx=8,pady=(6,6))
        ttk.Button(costdata,text=ui("地域単価JSONを取込（手動）","Import Regional-Cost JSON (Manual)"),command=self.import_regional_cost_dataset).grid(row=8,column=2,sticky="ew",padx=8,pady=3)
        ttk.Button(costdata,text=ui("地域単価を編集（手動）","Edit Regional Unit Costs (Manual)"),command=self.edit_regional_unit_costs).grid(row=9,column=2,sticky="ew",padx=8,pady=3)
        ttk.Button(costdata,text=ui("地域単価テンプレート保存（手動）","Save Regional-Cost Template (Manual)"),command=self.export_regional_cost_template).grid(row=10,column=2,sticky="ew",padx=8,pady=3)
        ttk.Label(costdata,textvariable=self.ai_cost_session_status,foreground="#006400").grid(row=11,column=0,columnspan=3,sticky="w",padx=8,pady=(2,4))
        ttk.Label(costdata,text=ui("AI依頼時: TXT等を添付後、依頼画面の「AIへ送る短文をコピー」をAIチャット本文へ貼り付けて送信してください。","When requesting AI research: attach the TXT/files, then use “Copy short message for AI” and paste it into the AI chat."),foreground="#8B4513").grid(row=12,column=0,columnspan=3,sticky="w",padx=8,pady=(0,4))
        costdata.columnconfigure(1,weight=1)

        soil_handling=ttk.LabelFrame(upper_panel,text=ui("根切土の現場内仮置場","On-site Excavated-Soil Stockpile"))
        soil_handling.pack(fill="x",padx=10,pady=5)
        ttk.Radiobutton(
            soil_handling,
            text=ui("あり：掘削土を必要埋戻しに再利用し、余剰土だけを場外搬出","Available: reuse excavated soil for required backfill and dispose only of surplus"),
            variable=self.excavated_soil_stockpile_mode,
            value="stockpile_available"
        ).grid(row=0,column=0,sticky="w",padx=8,pady=3)
        ttk.Radiobutton(
            soil_handling,
            text=ui("なし：根切土を全量場外搬出し、必要埋戻しは客土・購入土を搬入","Unavailable: dispose all excavated soil off-site and import required backfill"),
            variable=self.excavated_soil_stockpile_mode,
            value="no_stockpile"
        ).grid(row=1,column=0,sticky="w",padx=8,pady=3)
        ttk.Label(
            soil_handling,
            text=ui("初期値は「なし」。3工法に同一の敷地施工条件として適用します。","Default is Unavailable. The same site condition is applied to all three methods."),
            foreground="#555"
        ).grid(row=2,column=0,sticky="w",padx=8,pady=(0,5))

        rc_rates=ttk.LabelFrame(upper_panel,text=ui("基礎土工・地業 2026年確認単価（3工法共通）","Foundation Earthwork / Groundwork 2026 Verified Unit Costs (Common)"))
        rc_rates.pack(fill="x",padx=10,pady=5)
        ttk.Label(
            rc_rates,
            text=ui("0円は『未確認・総額へ未反映』。入力値は現在年の完成単価として扱い、2004年係数を二重適用しません。","Zero means unverified and excluded from the total. Entered values are current-year completed unit costs; the 2004 factor is not applied twice."),
            foreground="#8b0000"
        ).grid(row=0,column=0,columnspan=5,sticky="w",padx=6,pady=3)
        ttk.Label(
            rc_rates,
            text=ui("国交省2026積算基準の公開歩掛を根拠表示しますが、愛知県の主要資材・市場単価は非公表のため自動推定しません。","Published 2026 MLIT productivity references are shown as evidence; undisclosed local material/market prices are not auto-estimated."),
            foreground="#555"
        ).grid(row=1,column=0,columnspan=5,sticky="w",padx=6,pady=(0,4))
        _rc_rate_labels={
            "excavation":ui("根切り・掘削","Excavation"),
            "backfill":ui("埋戻し・締固め","Backfill / compaction"),
            "imported_fill":ui("客土・購入土（運搬込）","Imported fill incl. delivery"),
            "soil_disposal":ui("残土処分（運搬・受入込）","Surplus-soil disposal incl. haul/tipping"),
            "blinding_concrete":ui("捨てコンクリート","Blinding concrete"),
            "ground_preparation":ui("砕石地業","Crushed-stone groundwork"),
        }
        for _r,(_key,_name) in enumerate(_rc_rate_labels.items(),2):
            ttk.Label(rc_rates,text=_name).grid(row=_r,column=0,sticky="w",padx=6,pady=2)
            _entry=tk.Entry(
                rc_rates,textvariable=self.rc_foundation_unit_price_vars[_key],
                bg=INPUT_BG,width=16,justify="right"
            )
            _entry.grid(row=_r,column=1,sticky="w",padx=4,pady=2)
            _unit_label=ttk.Label(rc_rates,text=f"{self.currency.get() or 'JPY'}/m³")
            _unit_label.grid(row=_r,column=2,sticky="w",padx=4,pady=2)
            self._rc_currency_labels.append(_unit_label)
            _entry.bind(
                "<FocusOut>",
                lambda _e,v=self.rc_foundation_unit_price_vars[_key]:
                    v.set(format_input_number(v.get()))
            )

        ttk.Label(upper_panel,text=t("cost_notice"),foreground="#8b0000",
                  wraplength=1500).pack(fill="x",padx=12,pady=(3,1))
        ttk.Label(upper_panel,text=t("unit_cost_notice"),foreground="#8b0000",
                  wraplength=1500).pack(fill="x",padx=12,pady=(1,4))

        action=ttk.Frame(upper_panel)
        action.pack(fill="x",padx=10,pady=4)
        ttk.Button(action,text=t("edit_unit_costs"),command=self.edit_unit_costs).pack(side="left",padx=5)
        ttk.Button(action,text=t("calculate_cost"),command=self.calculate).pack(side="left",padx=5)
        ttk.Button(action,text=ui("工事費明細書","Detailed Cost Statement"),command=self.show_detailed_statement).pack(side="left",padx=5)
        ttk.Button(action,text=ui("数量→金額対応監査","Quantity → Cost Audit"),command=self.show_quantity_cost_audit).pack(side="left",padx=5)

        ttk.Label(
            lower_panel,
            text=("▲ 境界線をマウスで上下にドラッグすると工事費結果を広げられます"
                  if self.i18n.language=="ja"
                  else "▲ Drag the divider up or down to resize the construction-cost results"),
            foreground="#555555",
        ).pack(fill="x",padx=12,pady=(2,0))

        body=ttk.Panedwindow(lower_panel,orient="horizontal")
        body.pack(fill="both",expand=True,padx=10,pady=5)
        breakdown=ttk.LabelFrame(body,text=t("cost_breakdown"))
        summary=ttk.LabelFrame(body,text=t("cost_result"))
        body.add(breakdown,weight=3)
        body.add(summary,weight=2)

        cols=("no","item","qty","unit","price_status","material","labor","equipment","total")
        self.tree=ttk.Treeview(breakdown,columns=cols,show="headings")
        _display_currency=(str((self.result or {}).get("currency") or self.currency.get() or "JPY"))
        headings={
            "no":("No." if self.i18n.language!="ja" else "No."),
            "item":t("item"),"qty":t("quantity_used"),"unit":t("unit"),
            "price_status":("単価状態" if self.i18n.language=="ja" else "Price status"),
            "material":header_with_unit(t("material_cost"),_display_currency),"labor":header_with_unit(t("labor_cost"),_display_currency),
            "equipment":header_with_unit(t("equipment_cost"),_display_currency),"total":header_with_unit(t("line_total"),_display_currency)
        }
        widths={"no":52,"item":230,"qty":100,"unit":70,"price_status":105,"material":125,"labor":125,"equipment":125,"total":140}
        for c in cols:
            self.tree.heading(c,text=headings[c])
            self.tree.column(c,width=widths[c],stretch=False,anchor="center" if c=="no" else ("e" if c not in ("item","unit","price_status") else "w"))
        self.tree.tag_configure("estimated_price", background="#ffe699", foreground="#5f4500")
        self.tree.tag_configure("unpriced", background="#ffcccc", foreground="#8b0000")
        breakdown.rowconfigure(0,weight=1);breakdown.columnconfigure(0,weight=1)
        self.tree.grid(row=0,column=0,sticky="nsew",padx=(6,0),pady=(6,0))
        breakdown_y=ttk.Scrollbar(breakdown,orient="vertical",command=self.tree.yview)
        breakdown_x=ttk.Scrollbar(breakdown,orient="horizontal",command=self.tree.xview)
        self.tree.configure(yscrollcommand=breakdown_y.set,xscrollcommand=breakdown_x.set)
        breakdown_y.grid(row=0,column=1,sticky="ns",padx=(0,6),pady=(6,0))
        breakdown_x.grid(row=1,column=0,sticky="ew",padx=(6,0),pady=(0,6))

        summary_cols=("no","item","value","unit","basis","source")
        ttk.Label(
            summary,
            text=(
                '【重要】本結果は、Module 1「図面解析・数量計算」で得られた数量を基に算定しています。通常表示の確定数量と黄色表示の暫定・想定数量は計算に含まれます。一方、Module 1で数量を算出できず赤表示となっている未積算項目は本結果に含まれません。未積算項目を人間が確認・追加入力したうえで再計算し、最終判断してください。未積算項目の内容によっては、建設費・LCC・事業収支等が大きく変わる場合があります。'
                if self.i18n.language=="ja" else
                'IMPORTANT: This result is calculated from quantities obtained in Module 1 Drawing Analysis / Quantity Calculation. Confirmed quantities and yellow provisional/assumed quantities are included. Red items whose quantities could not be determined in Module 1 are not included. Have a human verify and add any unquantified items, then recalculate before making a final decision. Those omitted items may materially change construction cost, LCC, and business results.'
            ),
            foreground="#8b0000", wraplength=1100, justify="left"
        ).pack(fill="x",padx=6,pady=(6,2))
        self.total_completeness_label=ttk.Label(
            summary, textvariable=self.total_completeness_notice,
            foreground="#8b0000", wraplength=1100, justify="left"
        )
        self.total_completeness_label.pack(fill="x",padx=6,pady=(6,0))
        summary_scroll=ttk.Frame(summary)
        summary_scroll.pack(fill="both",expand=True,padx=6,pady=6)
        summary_scroll.rowconfigure(0,weight=1);summary_scroll.columnconfigure(0,weight=1)
        self.summary_tree=ttk.Treeview(summary_scroll,columns=summary_cols,show="headings")
        summary_headers={
            "no": t("result_no"),
            "item": t("item"),
            "value": t("value"),
            "unit": t("unit"),
            "basis": t("calculation_basis"),
            "source": t("reference_source"),
        }
        summary_widths={"no":55,"item":250,"value":150,"unit":95,"basis":390,"source":280}
        for c in summary_cols:
            self.summary_tree.heading(c,text=summary_headers[c])
            self.summary_tree.column(c,width=summary_widths[c],stretch=False,anchor="e" if c=="value" else "w")
        summary_y=ttk.Scrollbar(summary_scroll,orient="vertical",command=self.summary_tree.yview)
        summary_x=ttk.Scrollbar(summary_scroll,orient="horizontal",command=self.summary_tree.xview)
        self.summary_tree.configure(yscrollcommand=summary_y.set,xscrollcommand=summary_x.set)
        self.summary_tree.grid(row=0,column=0,sticky="nsew")
        summary_y.grid(row=0,column=1,sticky="ns")
        summary_x.grid(row=1,column=0,sticky="ew")
        # PATCH 493: retain strong references and keep wheel events local to the
        # right-hand result table so the upper canvas cannot intermittently steal
        # its vertical scrolling after focus/sash changes.
        self._summary_y_scrollbar=summary_y
        self._summary_x_scrollbar=summary_x
        def _summary_wheel(event):
            try:
                delta=getattr(event,"delta",0)
                if delta:
                    self.summary_tree.yview_scroll(-3 if delta>0 else 3,"units")
                    return "break"
            except tk.TclError:
                pass
            return None
        self.summary_tree.bind("<MouseWheel>",_summary_wheel,add="+")


    def _current_ai_cost_overlay(self):
        """Return the Project-specific AI approximate-cost overlay for Module 5.

        PATCH_038: AI prices remain excluded from the shared regional-cost DB on
        disk, but the adopted overlay is a genuine Project input and must survive
        save/reload and automatic upstream recalculation.
        """
        loc=(self.db.get("locations") or {}).get(self.location.get())
        if not isinstance(loc,dict):
            return None
        overlay=loc.get("_session_ai_unit_cost_overlay")
        if not isinstance(overlay,dict):
            return None
        return json.loads(json.dumps(overlay,ensure_ascii=False))

    def _restore_ai_cost_overlay_from_snapshot(self, snapshot):
        """Restore a saved Project-specific AI price overlay into session memory."""
        if not isinstance(snapshot,dict):
            return False
        overlay=snapshot.get("ai_cost_provider_overlay")
        if not isinstance(overlay,dict) or not overlay:
            return False
        loc=(self.db.get("locations") or {}).get(self.location.get())
        if not isinstance(loc,dict):
            return False
        overlay=json.loads(json.dumps(overlay,ensure_ascii=False))
        binding=overlay.setdefault("project_binding",{})
        if isinstance(binding,dict):
            binding.setdefault("project_id",str((self.project or {}).get("project_id") or ""))
            binding.setdefault("project_name",str(((self.project or {}).get("common") or {}).get("project_name") or ""))
        loc["_session_ai_unit_cost_overlay"]=overlay
        evidence=overlay.get("session_evidence")
        self.ai_cost_session=json.loads(json.dumps(evidence,ensure_ascii=False)) if isinstance(evidence,dict) else None
        if isinstance(self.ai_cost_session,dict):
            reviewers=self.ai_cost_session.get("reviewers") or []
            adopted=self.ai_cost_session.get("adopted_unit_costs") or {}
            packages=self.ai_cost_session.get("adopted_equipment_packages") or []
            self.ai_cost_session_status.set(self._ui(
                f"AI概算単価: 保存済Project入力を復元 / {len(reviewers)}AI / 単価 {len(adopted)} / 設備 {len(packages)} / 共通DB保存なし",
                f"AI approximate prices: restored from saved Project input / {len(reviewers)} AI / rates {len(adopted)} / equipment {len(packages)} / no shared-DB persistence"))
        return True

    def restore_saved_state(self):
        if self.project is None:
            return
        saved = self.project.get("module_outputs", {}).get("module5") or {}
        if not isinstance(saved, dict) or not saved:
            return
        self.user_notes = dict(saved.get("_user_notes") or {})
        snapshot = saved.get("_input_snapshot") or {}
        location = snapshot.get("location")
        if location:
            self.location.set(str(location))
            # PATCH 418: synchronize all location-derived UI/runtime fields when
            # reopening a saved project.  Merely restoring the combobox text left
            # currency/FX/regional-cost freshness (and package default currency)
            # from the previously open location.  Apply the location defaults first;
            # saved user-edited settings and package prices are restored below.
            try:
                self.apply_location()
            except Exception:
                pass
        settings = snapshot.get("settings") or {}
        simple = {
            "cost_year": self.cost_year,
            "material_index": self.material_index,
            "labor_index": self.labor_index,
            "productivity_index": self.productivity_index,
            "common_2004_to_target_cost_factor": self.common_2004_to_target_cost_factor,
            "common_2004_market_calibration_factor": self.common_2004_market_calibration_factor,
        }
        for key, variable in simple.items():
            if settings.get(key) is not None:
                variable.set(str(settings[key]))
        # PATCH_458: detailed paid-provider mode is retired from AZRAS planning.
        # Legacy Project JSONs remain readable but Module 5 always recalculates
        # business-plan construction cost with the approximate provider.
        self.cost_provider_mode.set("approximate")
        if settings.get("use_common_2004_price_basis") is not None:
            self.use_common_2004_price_basis.set(bool(settings.get("use_common_2004_price_basis")))
        # Restore percentage rates from decimal engine values.
        rate_map = {
            "overhead_rate": "overhead_percent",
            "contingency_rate": "contingency_percent",
            "design_rate": "design_supervision_percent",
            "tax_rate": "tax_percent",
        }
        for source, target in rate_map.items():
            if settings.get(source) is not None and target in self.rates:
                self.rates[target].set(str(float(settings[source])))
        _saved_soil_mode=str(settings.get("excavated_soil_stockpile_mode") or "no_stockpile")
        if _saved_soil_mode in {"stockpile_available","no_stockpile"}:
            self.excavated_soil_stockpile_mode.set(_saved_soil_mode)
        _saved_rc_rates=settings.get("rc_foundation_unit_price_overrides") or {}
        if isinstance(_saved_rc_rates,dict):
            for _k,_v in _saved_rc_rates.items():
                if _k in self.rc_foundation_unit_price_vars:
                    self.rc_foundation_unit_price_vars[_k].set(format_input_number(_v))
        self.custom_conditions = list(snapshot.get("custom_conditions") or [])
        saved_matrix=snapshot.get("condition_matrix")
        if isinstance(saved_matrix,dict):
            self.condition_matrix=saved_matrix
            for _category in ("site","access","work_time","reserve"):
                for _row in self.condition_matrix.get(_category,[]):
                    _row.setdefault("amount_jpy",None)
                    _row.setdefault("amount_local_currency",None)
                    _row.setdefault("amount_currency",None)
                    # PATCH 433: historical direct-condition amounts were stored
                    # under the misleading name amount_jpy even for USD/EUR/etc.
                    # The saved Module 5 location tells us which currency that
                    # number actually represented.  Migrate it without conversion.
                    if _row.get("amount_local_currency") is None and _row.get("amount_jpy") is not None:
                        _row["amount_local_currency"]=_row.get("amount_jpy")
                        _row["amount_currency"]=str(self.currency.get() or "JPY")
                    _row["condition"]=self._canonical_condition_text(_row.get("condition",""))
                    _row["basis"]=self._canonical_condition_text(_row.get("basis",""))
        self._sync_legacy_condition_vars()
        equipment = snapshot.get("equipment_selection") or {}
        if isinstance(equipment, dict):
            for key, value in equipment.items():
                if key not in self.equipment_vars:
                    continue
                # PATCH 405: equipment_vars is a {include, cost} variable pair.
                # Older restore code called .set() on the dict itself, so saved
                # package selections/costs were silently not restored.
                try:
                    if isinstance(value,dict):
                        if "include" in value:
                            self.equipment_vars[key]["include"].set(bool(value.get("include")))
                        if value.get("cost") is not None:
                            self.equipment_vars[key]["cost"].set(format_input_number(value.get("cost")))
                    else:
                        # Legacy scalar snapshots represented package cost only.
                        self.equipment_vars[key]["cost"].set(format_input_number(value))
                except Exception:
                    pass
        # PATCH_038: restore the Project-specific AI Cost Provider input before
        # any saved/stale result is displayed or recalculated.
        try:
            self._restore_ai_cost_overlay_from_snapshot(snapshot)
        except Exception:
            pass
        # PATCH 375: keep stale saved inputs available for editing, but never
        # present a stale Module 5 cost result as the current result after reload.
        if module_output_is_current(self.project, "module5"):
            self.result = saved
            try:
                self.show_result()
            except Exception:
                pass
        else:
            self.result = None
        self._refresh_project_state_notice()

    def summary_explanation(self, key):
        """Return (calculation basis, reference source) for Module 5 result rows.

        PATCH 485: the summary distinguishes the *direct-construction-cost total*
        from optional component breakdowns.  When the adopted rate is all-in,
        material/labor/plant cannot be truthfully separated, so rows ②-④ are
        explicitly informational breakdowns already contained in row ①.
        """
        ja = self.i18n.language == "ja"
        basis_ja = {
            "direct_total": "採用数量×採用単価による直接工事費の合計。一式単価と内訳分離単価を含む。②～④は①の内訳であり重複加算しない",
            "direct_material_breakdown": "①直接工事費のうち、材料・労務・機械を分離できる単価だけの材料内訳",
            "direct_labor_breakdown": "①直接工事費のうち、材料・労務・機械を分離できる単価だけの労務内訳",
            "direct_equipment_breakdown": "①直接工事費のうち、材料・労務・機械を分離できる単価だけの機械・仮設内訳",
            "condition": "施工条件補正による増減額。①直接工事費には反映済みの参考内訳",
            "additional_condition": "追加施工条件として選択した補正額の合計",
            "additional_equipment": "選択した設備一式価格の合計",
            "overhead": "（直接工事費＋追加設備費）を基礎にした諸経費",
            "contingency": "（工事原価＋諸経費）× 予備費率",
            "design": "（工事原価＋諸経費＋予備費）× 設計・監理率",
            "subtotal": "工事原価＋諸経費＋予備費＋設計・監理費",
            "tax": "税抜建設費 × 税率",
            "total": "税抜建設費＋税額",
            "per_m2": "税込建設費 ÷ 延床面積",
            "duration": "延床面積 ÷ 施工生産性 × 施工条件係数 ＋ 準備・試運転期間",
        }
        source_ja = {
            "direct_total": "Module 1 数量・Module 5 採用単価",
            "direct_material_breakdown": "Module 5 内訳分離単価",
            "direct_labor_breakdown": "Module 5 内訳分離単価",
            "direct_equipment_breakdown": "Module 5 内訳分離単価",
            "condition": "Module 5 施工条件",
            "additional_condition": "Module 5 追加施工条件",
            "additional_equipment": "Module 5 追加設備",
            "overhead": "Module 5 諸経費率",
            "contingency": "Module 5 予備費率",
            "design": "Module 5 設計・監理率",
            "subtotal": "Module 5 建設費積算",
            "tax": "Module 5 税率",
            "total": "Module 5 建設費積算",
            "per_m2": "Module 0 延床面積・Module 5 建設費",
            "duration": "Module 0 延床面積・Module 5 生産性/施工条件",
        }
        basis_en = {
            "direct_total": "Total direct construction cost from adopted quantities × adopted rates. Rows ②-④ are included breakdowns and are not added again",
            "direct_material_breakdown": "Material component only where the adopted rate is explicitly component-split; included in row ①",
            "direct_labor_breakdown": "Labor component only where the adopted rate is explicitly component-split; included in row ①",
            "direct_equipment_breakdown": "Plant/temporary component only where the adopted rate is explicitly component-split; included in row ①",
            "condition": "Site-condition adjustment amount already reflected in row ①; shown as an informational breakdown",
            "additional_condition": "Sum of selected additional construction-condition adjustments",
            "additional_equipment": "Sum of selected lump-sum equipment packages",
            "overhead": "Overhead based on direct construction cost plus added equipment",
            "contingency": "(Construction base + overhead) × contingency rate",
            "design": "(Construction base + overhead + contingency) × design/supervision rate",
            "subtotal": "Construction base + overhead + contingency + design/supervision",
            "tax": "Construction cost before tax × tax rate",
            "total": "Construction cost before tax + tax",
            "per_m2": "Total construction cost ÷ gross floor area",
            "duration": "Gross floor area ÷ productivity × site factors + mobilization/commissioning",
        }
        source_en = {
            "direct_total": "Module 1 quantities / Module 5 adopted unit prices",
            "direct_material_breakdown": "Module 5 component-split rates",
            "direct_labor_breakdown": "Module 5 component-split rates",
            "direct_equipment_breakdown": "Module 5 component-split rates",
            "condition": "Module 5 construction conditions",
            "additional_condition": "Module 5 additional conditions",
            "additional_equipment": "Module 5 additional equipment",
            "overhead": "Module 5 overhead rate",
            "contingency": "Module 5 contingency rate",
            "design": "Module 5 design/supervision rate",
            "subtotal": "Module 5 construction-cost calculation",
            "tax": "Module 5 tax rate",
            "total": "Module 5 construction-cost calculation",
            "per_m2": "Module 0 gross floor area / Module 5 construction cost",
            "duration": "Module 0 gross floor area / Module 5 productivity and conditions",
        }
        if ja:
            return basis_ja.get(key, "算定式・入力条件に基づく算出値"), source_ja.get(key, "Project JSON / Module 5")
        return basis_en.get(key, "Calculated from the stated formula and input conditions"), source_en.get(key, "Project JSON / Module 5")


    def _regional_cost_coverage_text(self, cov):
        """PATCH 461: show price-basis class and coverage without overstating verification."""
        cov=cov or {}
        total=int(cov.get("used_cost_item_count") or 0)
        full=int(cov.get("full_local_item_count") or 0)
        partial=int(cov.get("partial_local_item_count") or 0)
        fallback=int(cov.get("regional_fallback_item_count") or 0)
        comp_pct=float(cov.get("local_component_coverage_percent") or 0.0)
        basis=str(cov.get("pricing_basis_class") or "")
        ds_status=str(cov.get("unit_cost_dataset_status") or "not_available")

        if self.i18n.language=="ja":
            status_label={
                "verified":"確認済み",
                "estimated":"推定値",
                "outdated":"古いデータ",
                "update_required":"更新確認が必要",
                "not_available":"現地単価未登録",
            }.get(ds_status,ds_status)
            if basis=="verified_local_unit_prices":
                basis_label="確認済み現地単価"
            elif basis=="mixed_local_and_azras_regional_estimate":
                basis_label=(
                    "一部確認済み現地単価＋AZRAS地域概算値"
                    if ds_status=="verified"
                    else "一部現地単価登録＋AZRAS地域概算値"
                )
            else:
                basis_label="AZRAS地域概算値"
            return (
                f"単価区分: {basis_label} | 現地単価成分カバレッジ {comp_pct:.1f}% "
                f"| 完全現地 {full} / 部分現地 {partial} / 地域概算 {fallback} "
                f"(使用工事項目 {total}) | データ状態: {status_label}"
            )

        status_label={
            "verified":"Verified",
            "estimated":"Estimated",
            "outdated":"Outdated",
            "update_required":"Update check required",
            "not_available":"Local unit costs not registered",
        }.get(ds_status,ds_status)
        if basis=="verified_local_unit_prices":
            basis_label="Verified local unit prices"
        elif basis=="mixed_local_and_azras_regional_estimate":
            basis_label=(
                "Partly verified local + AZRAS regional estimate"
                if ds_status=="verified"
                else "Partly registered local + AZRAS regional estimate"
            )
        else:
            basis_label="AZRAS regional estimate"
        return (
            f"Price basis: {basis_label} | Local-price component coverage {comp_pct:.1f}% "
            f"| full local {full} / partial local {partial} / regional estimate {fallback} "
            f"(used cost items {total}) | data status: {status_label}"
        )

    def _refresh_localized_runtime_texts(self):
        """Refresh localized StringVars without changing project/cost inputs.

        PATCH 433: rebuilding widgets on a live language switch is not enough;
        several status StringVars contain already-localized text.  Recompute only
        their display strings and never call apply_location(), because that would
        reset user-edited package values.
        """
        loc=(self.db.get("locations") or {}).get(self.location.get(),{}) or {}
        audit=evaluate_unit_cost_dataset_freshness(loc) if loc else {}
        status=str(audit.get("status") or "not_available")
        labels_ja={"verified":"確認済み","estimated":"推定値","outdated":"古いデータ","update_required":"更新確認が必要","not_available":"現地単価未登録"}
        labels_en={"verified":"Verified","estimated":"Estimated","outdated":"Outdated","update_required":"Update check required","not_available":"Local unit costs not registered"}
        labels=labels_ja if self.i18n.language=="ja" else labels_en
        self.unit_cost_freshness.set(labels.get(status,status))
        if self.result:
            cov=self.result.get("regional_unit_cost_coverage_audit") or {}
            if cov:
                self.regional_cost_coverage.set(self._regional_cost_coverage_text(cov))
            mcal=self.result.get("market_calibration_2026") or {}
            if mcal:
                unp=mcal.get("known_unpriced_foundation_items") or []
                self.market_calibration_summary.set((
                    f"2026市場校正: 木造係数 {mcal.get('wood_factor_applied_to_fallback_components',0):.3f} / RC係数 {mcal.get('rc_factor_applied_to_fallback_components',0):.3f} / 未単価基礎工種 {len(unp)}"
                    if self.i18n.language=="ja" else
                    f"2026 market calibration: timber factor {mcal.get('wood_factor_applied_to_fallback_components',0):.3f} / RC factor {mcal.get('rc_factor_applied_to_fallback_components',0):.3f} / unpriced foundation items {len(unp)}"
                ))
            diag=self.result.get("construction_cost_validity_diagnostic") or {}
            if diag:
                bm=diag.get("benchmark_per_m2",diag.get("benchmark_jpy_per_m2")); est=diag.get("software_estimate_ex_tax_per_m2",diag.get("software_estimate_ex_tax_jpy_per_m2"))
                cur=str(diag.get("currency") or self.result.get("currency") or self.currency.get() or "JPY")
                gap=diag.get("gap_vs_benchmark_percent")
                if bm is None:
                    self.market_validity_summary.set((f"建設費妥当性: {float(est or 0):,.0f} {cur}/㎡ / 外部ベンチマークなし" if self.i18n.language=="ja" else f"Construction-cost validity: {cur} {float(est or 0):,.0f}/m² / no applicable external benchmark"))
                else:
                    self.market_validity_summary.set((f"建設費妥当性: {float(est or 0):,.0f} {cur}/㎡ / 基準 {float(bm):,.0f} {cur}/㎡ / 差 {float(gap or 0):+.1f}%" if self.i18n.language=="ja" else f"Construction-cost validity: {cur} {float(est or 0):,.0f}/m² / benchmark {cur} {float(bm):,.0f}/m² / gap {float(gap or 0):+.1f}%"))
        self._refresh_project_state_notice()
        self._refresh_project_cost_location()

    def change_language(self,language):
        # PATCH 422: Module 5 is now launched from the Planning shell, so its
        # language selector must participate in the same process-wide language
        # synchronization contract as Module 1/2.
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
        self.i18n.set_language(language)
        self.title(self.i18n.t("module5"))
        self.build();attach_module_report_button(self,5)
        self._refresh_localized_runtime_texts()
        if self.result:
            self.show_result()

    def choose_project(self):
        p=filedialog.askopenfilename(initialdir=self.root_dir/"projects",filetypes=[("JSON","*.json")])
        if not p:return
        try:
            project=load_project(p)
            try:
                require_current_module_output(project, "module1", "Module 1")
            except ValueError:
                raise ValueError(self.i18n.t("module1_required_m5"))
            self.project=project
            self.project_path=Path(p)
            self.project_file.set(p)
            self._refresh_project_state_notice()
            self._refresh_project_cost_location()
            # PATCH 056: registered project location -> Module 5 cost profile.
            _resolved=resolve_location_profile_from_project(self.project,self.db)
            _auto_key=_resolved.get("location_key")
            if _auto_key:
                self.location.set(str(_auto_key))
                self.apply_location()
            elif _resolved.get("fallback_location_key"):
                self.location.set(str(_resolved["fallback_location_key"]))
                self.apply_location()
        except Exception as exc:
            messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language))

    def _regional_cost_directory(self) -> Path:
        p=self.root_dir / "data" / "regional_cost"
        p.mkdir(parents=True,exist_ok=True)
        return p

    def import_regional_cost_dataset(self):
        """PATCH 062: import a versioned regional cost JSON without changing program code."""
        src=filedialog.askopenfilename(
            parent=self,
            title=self._ui("地域単価JSONを選択","Select Regional-Cost JSON"),
            filetypes=[("JSON","*.json"),("All files","*.*")]
        )
        if not src:
            return
        try:
            raw=json.loads(Path(src).read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror(self._ui("地域単価JSON","Regional-Cost JSON"),self._ui("JSONを読み込めません。\n","Cannot read JSON.\n")+friendly_exception_text(exc,self.i18n.language),parent=self)
            return

        required=["region_key","currency","data_date","last_checked_date","status","source_name","source_references","unit_costs"]
        missing=[k for k in required if k not in raw]
        if missing:
            messagebox.showerror(
                self._ui("地域単価JSON","Regional-Cost JSON"),
                self._ui("必須項目が不足しています：\n","Required fields are missing:\n")+", ".join(missing),
                parent=self
            )
            return

        region=str(raw.get("region_key") or "").strip()
        if region not in (self.db.get("locations") or {}):
            messagebox.showerror(
                self._ui("地域単価JSON","Regional-Cost JSON"),
                self._ui("region_key が現在の地域DBに登録されていません。\n","region_key is not registered in the current regional database.\n")+region,
                parent=self
            )
            return

        if not isinstance(raw.get("unit_costs"),dict):
            messagebox.showerror(self._ui("地域単価JSON","Regional-Cost JSON"),self._ui("unit_costs はJSONオブジェクトである必要があります。","unit_costs must be a JSON object."),parent=self)
            return

        # Validate any supplied item keys against the Module 5 cost database.
        known=set((self.db.get("base_unit_costs_jpy") or {}).keys())
        unknown=sorted(set(raw["unit_costs"].keys())-known)
        if unknown:
            messagebox.showerror(
                self._ui("地域単価JSON","Regional-Cost JSON"),
                self._ui("Module 5に存在しない工事項目があります：\n","The JSON contains work items not defined in Module 5:\n")+", ".join(unknown),
                parent=self
            )
            return

        # Never overwrite another version silently. Filename includes region/date.
        safe_region=re.sub(r"[^A-Za-z0-9_-]+","_",region).strip("_")
        safe_date=re.sub(r"[^0-9]+","_",str(raw.get("data_date") or "")).strip("_")
        dest=self._regional_cost_directory() / f"{safe_region}_{safe_date}.json"
        if dest.exists():
            ans=messagebox.askyesno(
                self._ui("地域単価JSON","Regional-Cost JSON"),
                self._ui(f"同じ地域・データ日のファイルが既にあります。\n上書きしますか？\n\n{dest.name}",f"A file for the same region and data date already exists.\nOverwrite it?\n\n{dest.name}"),
                parent=self
            )
            if not ans:
                return
        try:
            dest.write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding="utf-8")
        except Exception as exc:
            messagebox.showerror(self._ui("地域単価JSON","Regional-Cost JSON"),self._ui("保存できません。\n","Could not save.\n")+friendly_exception_text(exc,self.i18n.language),parent=self)
            return

        # Make the imported file discoverable by PATCH 061's latest-data-date selector.
        stem_map={
            "Japan / Tokyo":"JP_Tokyo",
            "Japan / Nagoya":"JP_Nagoya",
            "Japan / Sapporo":"JP_Sapporo",
            "United States / New York":"US_New_York",
            "United Kingdom / London":"UK_London",
        }
        stem=stem_map.get(region)
        if stem:
            canonical=self._regional_cost_directory() / f"{stem}_{str(raw.get('data_date') or '').replace('-','_')}.json"
            if canonical!=dest:
                canonical.write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding="utf-8")
                try:
                    dest.unlink()
                except Exception:
                    pass
                dest=canonical

        messagebox.showinfo(
            self._ui("地域単価JSON","Regional-Cost JSON"),
            self._ui("地域単価データを取り込みました。\n次回のModule 5計算では、同地域の最新 data_date が自動採用されます。\n\n","Regional unit-cost data was imported.\nThe latest data_date for this region will be used automatically in the next Module 5 calculation.\n\n")
            +dest.name,
            parent=self
        )
        # Refresh visible metadata if this is the currently selected region.
        if self.location.get()==region:
            self.apply_location()

    def export_regional_cost_template(self):
        """PATCH 062: save an empty 23-item regional cost template for future source updates."""
        region=str(self.location.get() or "User Defined")
        loc=(self.db.get("locations") or {}).get(region,{})
        currency=str(loc.get("currency") or "JPY")
        base=self.db.get("base_unit_costs_jpy") or {}

        items={}
        for key,row in base.items():
            items[key]={
                "unit":row.get("unit"),
                "material":None,
                "labor":None,
                "equipment":None,
                "status":"not_available",
                "source_name":None,
                "source_reference":None,
                "source_date":None,
                "note":None
            }

        template={
            "schema_version":"1.2",
            "region_key":region,
            "currency":currency,
            "data_date":"YYYY-MM-DD",
            "last_checked_date":"YYYY-MM-DD",
            "status":"not_available",
            "source_type":"official_public_source_or_verified_market_quote",
            "source_name":None,
            "source_references":[],
            "unit_costs_status":"fill_only_verified_or_explicitly_estimated_items",
            "unit_costs":items,
            "note_ja":"出典で確認できた項目だけ数値を入力してください。未確認項目はnullのままにします。"
        }

        safe_region=re.sub(r"[^A-Za-z0-9_-]+","_",region).strip("_") or "regional_cost"
        dest=filedialog.asksaveasfilename(
            parent=self,
            title="地域単価テンプレート保存",
            defaultextension=".json",
            initialfile=f"{safe_region}_TEMPLATE.json",
            filetypes=[("JSON","*.json")]
        )
        if not dest:
            return
        try:
            Path(dest).write_text(json.dumps(template,ensure_ascii=False,indent=2),encoding="utf-8")
            messagebox.showinfo(self._ui("地域単価テンプレート","Regional-Cost Template"),self._ui("保存しました。\n","Saved.\n")+str(dest),parent=self)
        except Exception as exc:
            messagebox.showerror(self._ui("地域単価テンプレート","Regional-Cost Template"),self._ui("保存できません。\n","Could not save.\n")+friendly_exception_text(exc,self.i18n.language),parent=self)


    def _latest_regional_cost_json(self, region: str) -> Path | None:
        """PATCH 066: return newest regional cost JSON by data_date."""
        import datetime as _dt

        stem_map={
            "Japan / Tokyo":"JP_Tokyo",
            "Japan / Nagoya":"JP_Nagoya",
            "Japan / Sapporo":"JP_Sapporo",
            "United States / New York":"US_New_York",
            "United Kingdom / London":"UK_London",
        }
        stem=stem_map.get(region)
        if not stem:
            return None
        folder=self._regional_cost_directory()
        candidates=[]
        for p in folder.glob(f"{stem}_*.json"):
            try:
                raw=json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            d=str(raw.get("data_date") or "")
            parsed=None
            for fmt in ("%Y-%m-%d","%Y-%m","%Y"):
                try:
                    parsed=_dt.datetime.strptime(d,fmt).date()
                    break
                except Exception:
                    pass
            candidates.append((parsed,p))
        if not candidates:
            return None
        candidates.sort(key=lambda x:(x[0] is not None,x[0] or _dt.date.min),reverse=True)
        return candidates[0][1]

    def edit_regional_unit_costs(self):
        """PATCH 066: source-backed per-item local unit-cost editor."""
        region=str(self.location.get() or "")
        if not region:
            messagebox.showerror(self._ui("地域単価編集","Regional Unit-Cost Editor"),self._ui("地域単価プロファイルを選択してください。","Select a regional cost profile."),parent=self)
            return

        current_path=self._latest_regional_cost_json(region)
        if current_path and current_path.exists():
            try:
                dataset=json.loads(current_path.read_text(encoding="utf-8"))
            except Exception:
                dataset={}
        else:
            loc=(self.db.get("locations") or {}).get(region,{})
            dataset={
                "schema_version":"1.0",
                "region_key":region,
                "currency":str(loc.get("currency") or "JPY"),
                "data_date":"",
                "last_checked_date":"",
                "status":"not_available",
                "source_type":"official_public_source_or_verified_market_quote",
                "source_name":None,
                "source_references":[],
                "unit_costs_status":"not_yet_populated",
                "unit_costs":{},
                "note_ja":""
            }

        dialog=tk.Toplevel(self)
        dialog.title(self._ui("地域単価編集 - ","Regional Unit-Cost Editor - ")+region)
        fit_window_to_screen(dialog,1320,820,820,560)
        dialog.minsize(1000,620)
        dialog.transient(self)

        top=ttk.Frame(dialog)
        top.pack(fill="x",padx=8,pady=8)

        data_date_var=tk.StringVar(value=str(dataset.get("data_date") or ""))
        checked_var=tk.StringVar(value=str(dataset.get("last_checked_date") or ""))
        source_name_var=tk.StringVar(value=str(dataset.get("source_name") or ""))
        status_var=tk.StringVar(value=str(dataset.get("status") or "estimated"))

        ttk.Label(top,text=self._ui("地域","Region")).grid(row=0,column=0,sticky="w",padx=4,pady=3)
        ttk.Label(top,text=region).grid(row=0,column=1,sticky="w",padx=4,pady=3)
        ttk.Label(top,text=self._ui("通貨","Currency")).grid(row=0,column=2,sticky="w",padx=4,pady=3)
        ttk.Label(top,text=str(dataset.get("currency") or "")).grid(row=0,column=3,sticky="w",padx=4,pady=3)

        ttk.Label(top,text=self._ui("データ日 YYYY-MM-DD","Data date YYYY-MM-DD")).grid(row=1,column=0,sticky="w",padx=4,pady=3)
        ttk.Entry(top,textvariable=data_date_var,width=16).grid(row=1,column=1,sticky="w",padx=4,pady=3)
        ttk.Label(top,text=self._ui("最終確認日","Last checked")).grid(row=1,column=2,sticky="w",padx=4,pady=3)
        ttk.Entry(top,textvariable=checked_var,width=16).grid(row=1,column=3,sticky="w",padx=4,pady=3)

        ttk.Label(top,text=self._ui("データ状態","Data status")).grid(row=2,column=0,sticky="w",padx=4,pady=3)
        ttk.Combobox(
            top,textvariable=status_var,state="readonly",width=18,
            values=["verified","estimated","outdated","update_required","not_available"]
        ).grid(row=2,column=1,sticky="w",padx=4,pady=3)
        ttk.Label(top,text=self._ui("全体出典名","Overall source name")).grid(row=2,column=2,sticky="w",padx=4,pady=3)
        ttk.Entry(top,textvariable=source_name_var,width=60).grid(row=2,column=3,columnspan=3,sticky="ew",padx=4,pady=3)
        top.columnconfigure(3,weight=1)

        body=ttk.Panedwindow(dialog,orient="horizontal")
        body.pack(fill="both",expand=True,padx=8,pady=(0,8))

        left=ttk.Frame(body)
        right=ttk.Frame(body)
        body.add(left,weight=3)
        body.add(right,weight=2)

        columns=("item","unit","material","labor","equipment","status")
        tree=ttk.Treeview(left,columns=columns,show="headings",selectmode="browse")
        headings=(
            {
                "item":"工事項目","unit":"単位","material":"材料","labor":"労務",
                "equipment":"機械・その他","status":"状態"
            }
            if self.i18n.language=="ja"
            else {
                "item":"Work item","unit":"Unit","material":"Material","labor":"Labor",
                "equipment":"Equipment / Other","status":"Status"
            }
        )
        widths={"item":250,"unit":80,"material":110,"labor":110,"equipment":120,"status":150}
        for c in columns:
            tree.heading(c,text=headings[c])
            tree.column(c,width=widths[c],stretch=False,anchor="w" if c in {"item","status"} else "e")
        sy=ttk.Scrollbar(left,orient="vertical",command=tree.yview)
        sx=ttk.Scrollbar(left,orient="horizontal",command=tree.xview)
        tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        sx.pack(side="bottom",fill="x")
        sy.pack(side="right",fill="y")
        tree.pack(side="left",fill="both",expand=True)

        edit=ttk.LabelFrame(right,text=self._ui("選択項目","Selected Item"))
        edit.pack(fill="both",expand=True)

        key_var=tk.StringVar()
        item_var=tk.StringVar()
        unit_var=tk.StringVar()
        material_var=tk.StringVar()
        labor_var=tk.StringVar()
        equipment_var=tk.StringVar()
        item_status_var=tk.StringVar(value="not_available")
        item_source_name_var=tk.StringVar()
        item_source_ref_var=tk.StringVar()
        item_source_date_var=tk.StringVar()
        item_note_var=tk.StringVar()

        labels=(
            [("項目キー",key_var,True),("工事項目",item_var,True),("単位",unit_var,True),("材料単価",material_var,False),("労務単価",labor_var,False),("機械・その他単価",equipment_var,False),("出典名",item_source_name_var,False),("出典URL/資料番号",item_source_ref_var,False),("出典年月",item_source_date_var,False),("備考",item_note_var,False)]
            if self.i18n.language=="ja" else
            [("Item key",key_var,True),("Work item",item_var,True),("Unit",unit_var,True),("Material unit cost",material_var,False),("Labor unit cost",labor_var,False),("Equipment / other unit cost",equipment_var,False),("Source name",item_source_name_var,False),("Source URL / document no.",item_source_ref_var,False),("Source date",item_source_date_var,False),("Notes",item_note_var,False)]
        )
        for r,(label,var,readonly) in enumerate(labels):
            ttk.Label(edit,text=label).grid(row=r,column=0,sticky="nw",padx=6,pady=4)
            ent=ttk.Entry(edit,textvariable=var,width=48)
            if readonly:
                ent.configure(state="readonly")
            ent.grid(row=r,column=1,sticky="ew",padx=6,pady=4)

        r=len(labels)
        ttk.Label(edit,text=self._ui("状態","Status")).grid(row=r,column=0,sticky="w",padx=6,pady=4)
        ttk.Combobox(
            edit,textvariable=item_status_var,state="readonly",
            values=["verified","estimated","outdated","update_required","not_available"]
        ).grid(row=r,column=1,sticky="ew",padx=6,pady=4)
        edit.columnconfigure(1,weight=1)

        base=self.db.get("base_unit_costs_jpy") or {}
        unit_costs=dataset.setdefault("unit_costs",{})

        def _num(v):
            if v in ("",None):
                return None
            try:
                return float(str(v).replace(",",""))
            except Exception:
                raise ValueError(self._ui("単価は数値で入力してください。","Enter a numeric unit cost."))

        def _display(v):
            if v is None:
                return ""
            try:
                return f"{float(v):g}"
            except Exception:
                return str(v)

        def reload_tree(select_key=None):
            for iid in tree.get_children():
                tree.delete(iid)
            for key,row in base.items():
                local=unit_costs.get(key) or {}
                iid=tree.insert("", "end", iid=key, values=(
                    row.get("ja" if self.i18n.language=="ja" else "en") or row.get("ja") or key,
                    row.get("unit") or "",
                    _display(local.get("material")),
                    _display(local.get("labor")),
                    _display(local.get("equipment")),
                    local.get("status") or "not_available",
                ))
            if select_key and tree.exists(select_key):
                tree.selection_set(select_key)
                tree.focus(select_key)
                tree.see(select_key)

        def load_selected(_event=None):
            sel=tree.selection()
            if not sel:
                return
            key=sel[0]
            row=base.get(key,{})
            local=unit_costs.get(key) or {}
            key_var.set(key)
            item_var.set(str(row.get("ja") or key))
            unit_var.set(str(row.get("unit") or ""))
            material_var.set(_display(local.get("material")))
            labor_var.set(_display(local.get("labor")))
            equipment_var.set(_display(local.get("equipment")))
            item_status_var.set(str(local.get("status") or "not_available"))
            item_source_name_var.set(str(local.get("source_name") or ""))
            item_source_ref_var.set(str(local.get("source_reference") or ""))
            item_source_date_var.set(str(local.get("source_date") or ""))
            item_note_var.set(str(local.get("note") or ""))

        def apply_item():
            key=key_var.get()
            if not key:
                return
            try:
                material=_num(material_var.get())
                labor=_num(labor_var.get())
                equipment=_num(equipment_var.get())
            except ValueError as exc:
                messagebox.showerror(self._ui("地域単価編集","Regional Unit-Cost Editor"),friendly_exception_text(exc,self.i18n.language),parent=dialog)
                return

            st=item_status_var.get() or "not_available"
            source=item_source_name_var.get().strip()
            source_ref=item_source_ref_var.get().strip()
            source_date=item_source_date_var.get().strip()

            # Verified/estimated prices must always carry provenance.
            if st in {"verified","estimated"}:
                if all(v is None for v in (material,labor,equipment)):
                    messagebox.showerror(
                        "地域単価編集",
                        "verified / estimated にする場合は、少なくとも1つの単価を入力してください。",
                        parent=dialog
                    )
                    return
                if not source:
                    messagebox.showerror(
                        "地域単価編集",
                        "verified / estimated にする場合は出典名を入力してください。",
                        parent=dialog
                    )
                    return
                if not source_date:
                    messagebox.showerror(
                        "地域単価編集",
                        "verified / estimated にする場合は出典年月を入力してください。",
                        parent=dialog
                    )
                    return

            unit_costs[key]={
                "unit":unit_var.get(),
                "material":material,
                "labor":labor,
                "equipment":equipment,
                "status":st,
                "source_name":source or None,
                "source_reference":source_ref or None,
                "source_date":source_date or None,
                "note":item_note_var.get().strip() or None
            }
            reload_tree(key)

        ttk.Button(edit,text=self._ui("この項目を反映","Apply This Item"),command=apply_item).grid(
            row=r+1,column=0,columnspan=2,sticky="ew",padx=6,pady=10
        )

        tree.bind("<<TreeviewSelect>>",load_selected)

        bottom=ttk.Frame(dialog)
        bottom.pack(fill="x",padx=8,pady=(0,8))

        def save_dataset():
            import datetime as _dt
            d=data_date_var.get().strip()
            checked=checked_var.get().strip()
            for label,val in [("データ日",d),("最終確認日",checked)]:
                try:
                    _dt.datetime.strptime(val,"%Y-%m-%d")
                except Exception:
                    messagebox.showerror(
                        "地域単価編集",
                        f"{label}は YYYY-MM-DD 形式で入力してください。",
                        parent=dialog
                    )
                    return

            dataset["region_key"]=region
            dataset["data_date"]=d
            dataset["last_checked_date"]=checked
            dataset["status"]=status_var.get() or "estimated"
            dataset["source_name"]=source_name_var.get().strip() or None
            dataset["unit_costs"]=unit_costs

            populated=[
                k for k,v in unit_costs.items()
                if isinstance(v,dict) and any(v.get(x) is not None for x in ("material","labor","equipment"))
            ]
            dataset["unit_costs_status"]=(
                "partially_populated_source_backed" if populated else "not_yet_populated"
            )
            dataset["unit_costs_populated_count"]=len(populated)
            dataset["unit_costs_total_item_count"]=len(base)

            stem_map={
                "Japan / Tokyo":"JP_Tokyo",
                "Japan / Nagoya":"JP_Nagoya",
                "Japan / Sapporo":"JP_Sapporo",
                "United States / New York":"US_New_York",
                "United Kingdom / London":"UK_London",
            }
            stem=stem_map.get(region)
            if not stem:
                messagebox.showerror(self._ui("地域単価編集","Regional Unit-Cost Editor"),self._ui("この地域の保存ファイル名規則が未設定です。","No save-file naming rule is configured for this region."),parent=dialog)
                return

            target=self._regional_cost_directory() / f"{stem}_{d.replace('-','_')}.json"
            if target.exists() and target != current_path:
                if not messagebox.askyesno(
                    "地域単価編集",
                    f"{target.name} は既に存在します。上書きしますか？",
                    parent=dialog
                ):
                    return

            try:
                target.write_text(json.dumps(dataset,ensure_ascii=False,indent=2),encoding="utf-8")
            except Exception as exc:
                messagebox.showerror(self._ui("地域単価編集","Regional Unit-Cost Editor"),self._ui("保存できません。\n","Could not save.\n")+friendly_exception_text(exc,self.i18n.language),parent=dialog)
                return

            messagebox.showinfo(
                self._ui("地域単価編集","Regional Unit-Cost Editor"),
                (f"保存しました。\n{target.name}\n\n単価登録済み: {len(populated)} / {len(base)} 項目\n次回計算時は同地域の最新 data_date が自動採用されます。"
                 if self.i18n.language=="ja" else
                 f"Saved.\n{target.name}\n\nPriced items: {len(populated)} / {len(base)}\nThe latest data_date for this region will be selected automatically on the next calculation."),
                parent=dialog
            )
            if self.location.get()==region:
                self.apply_location()

        ttk.Button(bottom,text=self._ui("保存","Save"),command=save_dataset).pack(side="right",padx=4)
        ttk.Button(bottom,text=self._ui("閉じる","Close"),command=dialog.destroy).pack(side="right",padx=4)

        reload_tree()
        first=tree.get_children()
        if first:
            tree.selection_set(first[0])
            tree.focus(first[0])
            load_selected()


    def show_cost_validity_diagnostic(self):
        diag=(self.result or {}).get("construction_cost_validity_diagnostic") or {}
        if not diag:
            messagebox.showinfo(self._ui("建設費妥当性","Construction-Cost Validity"),self._ui("先に計算してください。","Calculate construction cost first."),parent=self)
            return
        dlg=tk.Toplevel(self)
        dlg.title(self._ui("建設費妥当性診断","Construction-Cost Validity Diagnostic"))
        fit_window_to_screen(dlg,1050,760,760,520)
        dlg.minsize(800,560)

        top=ttk.Frame(dlg)
        top.pack(fill="x",padx=10,pady=10)
        bm=diag.get("benchmark_jpy_per_m2")
        est=diag.get("software_estimate_ex_tax_jpy_per_m2")
        gap=diag.get("gap_vs_benchmark_percent")
        shortfall=diag.get("shortfall_to_benchmark",diag.get("shortfall_to_benchmark_jpy"))
        diag_currency=str(diag.get("currency") or (self.result or {}).get("currency") or self.currency.get() or "JPY")
        ttk.Label(top,text=self._ui(f"工法: {diag.get('method','-')}",f"Method: {diag.get('method','-')}")).pack(anchor="w")
        ttk.Label(top,text=self._ui(f"ソフト計算: {float(est or 0):,.0f} {diag_currency}/㎡（税抜）",f"Software estimate: {diag_currency} {float(est or 0):,.0f}/m² excl. tax")).pack(anchor="w")
        ttk.Label(top,text=(self._ui("外部ベンチマーク: -","External benchmark: -") if bm is None else self._ui(f"外部ベンチマーク: {float(bm):,.0f} {diag_currency}/㎡",f"External benchmark: {diag_currency} {float(bm):,.0f}/m²"))).pack(anchor="w")
        if gap is not None:
            ttk.Label(top,text=self._ui(f"差: {float(gap):+.1f}%   同延床面積での不足額目安: {float(shortfall or 0):,.0f} {diag_currency}",f"Gap: {float(gap):+.1f}%   Indicative shortfall at the same GFA: {diag_currency} {float(shortfall or 0):,.0f}")).pack(anchor="w")
        ttk.Label(top,text=str(diag.get("judgment_ja" if self.i18n.language=="ja" else "judgment_en") or diag.get("judgment_ja") or ""),wraplength=980).pack(anchor="w",pady=(5,0))
        ttk.Label(top,text=str(diag.get("source_scope_warning_ja" if self.i18n.language=="ja" else "source_scope_warning_en") or diag.get("source_scope_warning_ja") or ""),wraplength=980).pack(anchor="w",pady=(3,0))

        panes=ttk.Panedwindow(dlg,orient="horizontal")
        panes.pack(fill="both",expand=True,padx=10,pady=(0,10))

        left=ttk.LabelFrame(panes,text=self._ui("直接工事費グループ","Direct-Cost Groups"))
        right=ttk.LabelFrame(panes,text=self._ui("優先確認項目","Priority Checks"))
        panes.add(left,weight=1);panes.add(right,weight=1)

        gt=ttk.Treeview(left,columns=("group","cost","share"),show="headings")
        for c,label,w in (([("group","区分",220),("cost","金額",150),("share","構成比",100)]) if self.i18n.language=="ja" else ([("group","Group",220),("cost","Cost",150),("share","Share",100)])):
            gt.heading(c,text=label);gt.column(c,width=w,stretch=False,anchor="e" if c!="group" else "w")
        gt_y=ttk.Scrollbar(left,orient="vertical",command=gt.yview);gt_x=ttk.Scrollbar(left,orient="horizontal",command=gt.xview)
        gt.configure(yscrollcommand=gt_y.set,xscrollcommand=gt_x.set)
        gt_x.pack(side="bottom",fill="x",padx=5);gt_y.pack(side="right",fill="y",pady=5);gt.pack(side="left",fill="both",expand=True,padx=5,pady=5)
        for row in diag.get("direct_cost_group_breakdown") or []:
            gt.insert("","end",values=(row.get("group"),f"{float(row.get('cost') if row.get('cost') is not None else row.get('cost_jpy') or 0):,.0f}",f"{float(row.get('share_percent') or 0):.1f}%"))

        ct=ttk.Treeview(right,columns=("priority","issue","detail"),show="headings")
        for c,label,w in (([("priority","優先度",80),("issue","確認区分",170),("detail","内容",430)]) if self.i18n.language=="ja" else ([("priority","Priority",80),("issue","Check type",170),("detail","Details",430)])):
            ct.heading(c,text=label);ct.column(c,width=w,stretch=False,anchor="w")
        ct_y=ttk.Scrollbar(right,orient="vertical",command=ct.yview);ct_x=ttk.Scrollbar(right,orient="horizontal",command=ct.xview)
        ct.configure(yscrollcommand=ct_y.set,xscrollcommand=ct_x.set)
        ct_x.pack(side="bottom",fill="x",padx=5);ct_y.pack(side="right",fill="y",pady=5);ct.pack(side="left",fill="both",expand=True,padx=5,pady=5)
        _issue_en={
            "regional_unit_price_coverage":"Regional unit-price coverage",
            "partial_local_price":"Partial local-price verification",
            "building_services_scope":"Building-services scope",
            "rc_concrete_missing":"RC concrete scope missing",
            "rc_reinforcing_steel_missing":"RC reinforcement scope missing",
            "rc_formwork_missing":"RC formwork scope missing",
            "temporary_works_and_site_overhead":"Temporary works / site overhead",
            "finishes_and_services":"Finishes and services",
            "benchmark_scope_difference":"Benchmark scope difference",
        }
        _detail_en={
            "regional_unit_price_coverage":"Some work items still use regional-index estimates; replace them with verified local prices or quotations where available.",
            "partial_local_price":"Some work items have only partially verified local price components; remaining components use regional estimates.",
            "building_services_scope":"Recheck the completed-building scope of residential equipment packages.",
            "rc_concrete_missing":"The principal RC concrete scope is missing or not auditable.",
            "rc_reinforcing_steel_missing":"The principal RC reinforcing-steel scope is missing or not auditable.",
            "rc_formwork_missing":"The principal RC formwork scope is missing or not auditable.",
            "temporary_works_and_site_overhead":"Check whether scaffolding, lifting, temporary works and site overhead are included at market-contract level.",
            "finishes_and_services":"Check specifications, quantities and prices for finishes, openings, plumbing, electrical and HVAC beyond the RC frame.",
            "benchmark_scope_difference":"The result is near the structural benchmark, but the benchmark is not a project-specific contract estimate.",
        }
        for row in diag.get("priority_checks") or []:
            detail=(row.get("detail_ja") if self.i18n.language=="ja" else (row.get("detail_en") or _detail_en.get(str(row.get("issue") or "")) or row.get("detail_ja")))
            issue=row.get("issue") if self.i18n.language=="ja" else _issue_en.get(str(row.get("issue") or ""),row.get("issue"))
            ct.insert("","end",values=(row.get("priority"),issue,detail))

    
    def _default_ai_cost_dir(self):
        """Project-local exchange folder. AZRAS does not create a global price cache."""
        self.refresh_project_from_context()
        base=Path(self.project_path).parent if self.project_path is not None else (self.root_dir/"projects")
        return base / "AI_CostProvider"

    # PATCH_011: マルコさん asked for the construction-cost AI request/response
    # workflow to use the SAME four-folder layout already used by Module 1's
    # takeoff workflow (R1/01_Request for Estimate, 02_AI response,
    # 03_Request for Recheck, 04_Final determination). Kept as its own root
    # ("AI_CostProvider/R1") rather than sharing Module 1's R1 folder, since
    # takeoff and cost are different AI exchanges with different schemas and
    # should not be mixed in the same folder.
    def _ai_cost_round_root(self):
        return self._default_ai_cost_dir() / "R1"

    def _ensure_ai_cost_round_layout(self):
        root=self._ai_cost_round_root()
        folders={
            "request": root / "01_Request for Estimate",
            "responses": root / "02_AI response",
            "recheck": root / "03_Request for Recheck",
            "final": root / "04_Final determination",
        }
        for folder in folders.values():
            folder.mkdir(parents=True,exist_ok=True)
        return folders

    def _ai_cost_security_audit_dir(self):
        """Keep observable AI request/response security audit under the existing R1 final folder."""
        return self._ensure_ai_cost_round_layout()["final"] / "AI_Audit"

    def _copy_ai_cost_json_to_round_folder(self, source_path, folder_key):
        """Best-effort copy of an imported/adopted AI cost JSON into the R1
        round folder, mirroring Module 1's own R1/02_AI response and
        R1/04_Final determination record-keeping. Never raises: a copy
        failure must not block the in-memory import/reconciliation that
        already succeeded."""
        try:
            folders=self._ensure_ai_cost_round_layout()
            target_dir=folders[folder_key]
            src=Path(source_path)
            target=target_dir/src.name
            if target.resolve()==src.resolve():
                return
            import shutil as _shutil
            if target.exists():
                stamp=datetime.now(timezone.utc).strftime("%y%m%d_%H%M%S")
                target=target_dir/f"{stamp}_{src.name}"
            _shutil.copy2(src,target)
        except Exception:
            pass

    def _ai_cost_request_scope(self):
        """Return only the cost scopes actually needed by the current Module 1 result."""
        self.refresh_project_from_context()
        if not isinstance(self.project,dict) or self.project_path is None:
            raise ValueError(self._ui("先にModule 0でProject JSONを選択してください。","Select a Project JSON in Module 0 first."))
        module1=require_current_module_output(self.project,"module1","Module 1")
        quantities,provenance,excluded=extract_quantities(self.project,module1,self.settings())
        base=self.db.get("base_unit_costs_jpy") or {}
        items=[]
        for key,qty in sorted(quantities.items()):
            rec=base.get(key) or {}
            if not rec:
                continue
            items.append({
                "cost_item_key":key,
                "item_name":self._cost_item_canonical_name_en(key),
                "quantity":float(qty),
                "unit":str(rec.get("unit") or ""),
                "quantity_basis":str((provenance.get(key) or {}).get("basis") or "Module 1 adopted quantity"),
            })
        packages=[]
        for key,data in self.equipment_selection().items():
            if not bool(data.get("include")):
                continue
            meta=(self.db.get("equipment_packages") or {}).get(key) or {}
            packages.append({
                "package_key":key,
                "name":str(meta.get("en") or meta.get("ja") or key),
                "required_currency":str(self.currency.get() or "JPY"),
            })
        gfa=float(((self.project.get("common") or {}).get("scale_gfa_m2") or 0.0))
        return {"items":items,"equipment_packages":packages,"gross_floor_area_m2":gfa,"excluded_quantity_count":len(excluded)}

    def _authoritative_project_cost_location(self):
        """Return the Project address/locality used for AI pricing; representative profile is reference-only."""
        common=(self.project.get("common") or {}) if isinstance(self.project,dict) else {}
        locobj=common.get("location") or {}
        project_location=str(common.get("project_location") or locobj.get("project_location") or "").strip()
        address=str(common.get("address") or locobj.get("address") or "").strip()
        country=str(common.get("country") or locobj.get("country") or "").strip()
        city=str(common.get("city") or locobj.get("city") or "").strip()
        if project_location:
            return project_location
        if address:
            return " ".join(x for x in (city,address) if x)
        parts=[x for x in (city,country) if x]
        return ", ".join(parts) or str(self.location.get() or "-")

    def _cost_profile_match_basis(self):
        """PATCH_039: how the Module 5 regional profile relates to the Project address.

        Returns a short, machine-stable token used in the AI request and in the
        Module 5 header.  It never changes a price; it only stops a country
        reference city from being presented as the project's own region.
        """
        try:
            resolved=resolve_location_profile_from_project(self.project,self.db) if isinstance(self.project,dict) else {}
        except Exception:
            resolved={}
        level=str(resolved.get("match_level") or "")
        selected=str(self.location.get() or "")
        if level=="matched_city" and selected==str(resolved.get("location_key") or ""):
            return "matched_project_city"
        if level=="matched_prefecture" and selected==str(resolved.get("location_key") or ""):
            # PATCH_042: the prefecture's representative city - a regional
            # match, not a national guess, so no proxy warning is shown.
            return "matched_prefecture_representative_city"
        if level=="country_reference_fallback" and selected==str(resolved.get("location_key") or ""):
            return "country_reference_fallback_not_project_city"
        if selected and selected!=str(resolved.get("location_key") or ""):
            return "manually_selected_profile"
        return "unresolved_profile"

    def _cost_profile_proxy_notice(self):
        """PATCH_039: short bilingual warning when the profile is not the project city."""
        basis=self._cost_profile_match_basis()
        if basis=="manually_selected_profile":
            # PATCH_042: a saved Module 5 keeps its profile (saved snapshots are
            # authoritative), but Projects saved before the Japanese address
            # matching was fixed carry the old automatic fallback.  Say which
            # profile the address actually resolves to; never switch silently.
            try:
                _res=resolve_location_profile_from_project(self.project,self.db) if isinstance(self.project,dict) else {}
            except Exception:
                _res={}
            _key=str(_res.get("location_key") or "")
            if _key and _res.get("profile_is_regional_match") and _key!=str(self.location.get() or ""):
                return (f"案件所在地に対応する代表プロファイルは {_key} です（現在の選択: {self.location.get()}）。"
                        "意図した選択でなければ地域プロファイルを切り替えて再計算してください。"
                        if self.i18n.language=="ja" else
                        f"The project address resolves to {_key} (currently selected: {self.location.get()}). "
                        "If this was not intended, switch the regional profile and recalculate.")
            return ""
        if basis!="country_reference_fallback_not_project_city":
            return ""
        return (f"代表プロファイル {self.location.get()} は案件所在地の都市ではありません（国の基準都市による自動選択）。"
                "地域係数・生産性・工期は参考値として扱い、単価はAI概算単価／現地見積で確定してください。"
                if self.i18n.language=="ja" else
                f"Representative profile {self.location.get()} is the country reference city, not the project city. "
                "Treat the regional indices, productivity and duration as reference values and settle unit prices from the AI cost provider or a local quotation.")

    def _refresh_project_cost_location(self):
        try:
            text=self._authoritative_project_cost_location()
            # PATCH_043: say plainly that this is a comparison copy.
            _cc=comparison_copy_info(self.project)
            if _cc:
                text=(self._ui("【比較用コピー】","[Comparison copy] ")
                      +text+self._ui(f"  比較前提表: {_cc.get('premise_book_file') or '-'}（版 {_cc.get('premise_book_version') or '-'}）",
                                     f"  Premise book: {_cc.get('premise_book_file') or '-'} (version {_cc.get('premise_book_version') or '-'})"))
            notice=self._cost_profile_proxy_notice()
            if notice:
                text=f"{text}  ⚠ {notice}"
            self.project_cost_location.set(text)
        except Exception:
            self.project_cost_location.set("-")

    def _ai_cost_request_text(self):
        scope=self._ai_cost_request_scope()
        common=(self.project.get("common") or {}) if isinstance(self.project,dict) else {}
        locobj=common.get("location") or {}
        project_name=Path(self.project_path).stem if self.project_path else "PROJECT_NAME"
        region=self.location.get()
        # PATCH_039: the AI response must not label AZRAS's representative cost
        # profile as the project's planning region.  When the profile was only
        # reached through the country reference city (e.g. an Illinois project
        # falling back to "United States / New York"), say so explicitly rather
        # than shipping the wrong region name into the returned JSON.
        planning_region=self._authoritative_project_cost_location()
        profile_basis=self._cost_profile_match_basis()
        currency=str(self.currency.get() or "JPY").upper()
        country=str(common.get("country") or locobj.get("country") or region.split(" / ",1)[0] or "")
        city=str(common.get("city") or locobj.get("city") or (region.split(" / ",1)[1] if " / " in region else ""))
        address=str(common.get("project_location") or locobj.get("project_location") or common.get("address") or locobj.get("address") or "")
        return f'''AZRAS AI APPROXIMATE COST PRIMARY RESEARCH REQUEST v1.4 — ENGLISH CANONICAL

Project: {project_name}
Construction cost research location: {address or (city + ", " + country).strip(", ")}
Project country: {country}
Project city/location (AUTHORITATIVE unified Project field): {address}
Project address/location (AUTHORITATIVE for geographic pricing): {address}
Planning regional profile (REFERENCE ONLY; NEVER override the project address): {region}
Planning regional profile basis: {profile_basis}
Required construction-cost currency: {currency}

{AZRAS_AI_STANDARD_RULES_V3_EN}
[ROLE]
You are ChatGPT acting as the PRIMARY research guide for AZRAS. Research current planning-stage construction unit prices for the AUTHORITATIVE project address above using web-accessible sources.
This is the free AZRAS Approximate Cost Provider workflow, not a contract estimate.
If the Planning regional profile names a different representative city, do NOT stop or ask the user which city to use: the project address governs the research location.

[NON-NEGOTIABLE PRICE ORIGIN RULE]
1. Build the construction price from the selected country/region market in its local currency.
2. NEVER start from a Japanese/Japan JPY unit price and convert it by FX.
3. NEVER use FX to manufacture a missing local construction unit price.
4. Do not invent a material/labor/equipment split. Each returned numeric component must be directly supported by a cited source.
5. If a source supports only one combined installed/all-in unit rate, put it ONLY in installed_unit_cost with pricing_structure:"installed_all_in". NEVER place a combined installed rate in material, labor, or equipment.
6. MANDATORY SEARCH FIRST: if web-search/browsing is available, actually use it before deciding not_found. Do not stop from a pre-search specification-gap check alone.
7. PERMITTED PLANNING ASSUMPTIONS: do not make unsupported assumptions. When an exact specification is missing, a standard commercial/industrial planning assumption MAY be used only for provisional_estimate, and every assumption must be disclosed in estimate_basis/evidence_note. It can never be confirmed.
8. A physical unit conversion (for example USD/ft2 to USD/m2) is permitted only when the source unit and conversion are stated. Product size, crew productivity, finish specification, thickness, or similar assumptions are permitted only under Rule 7 and must remain provisional.
9. For equipment packages, distinguish lump_sum from unit_rate_per_gfa. Never put a per-area rate into a lump-sum cost field.
10. Prefer the most geographically specific source available: project city/metro > state/province/region > country.
11. Prefer current sources. Record publication/effective date and geographic scope.
12. Government/public primary sources, recognized construction-cost publications, official statistical/industry sources and clearly attributable market references are preferred. AI-generated estimating services may be cited only when clearly identified as such and must not by themselves elevate a value to confirmed.
13. Every numeric value must carry a traceable source URL/reference, source_type, scope_definition, and a short evidence note.
14. PROVISIONAL ESTIMATE PRIORITY: if an exact price is unavailable, continue city/metro -> state/region -> national comparable research. If a defensible benchmark exists, return provisional_estimate rather than not_found and disclose all planning assumptions.
15. NOT_FOUND AS LAST RESORT: only after web research was completed and no defensible source-backed benchmark/comparable can be established may the market item be returned not_found.
16. WEB CAPABILITY STATUS: always report research_execution. If web research is unavailable or fails, do NOT classify the market item itself as not_found. Use research_unavailable for affected item/package statuses and explain the execution failure.
17. SEARCH STOP RULE: for each item, stop expanding the search when (a) a direct city/metro/state primary or industry source supports the requested scope, or (b) a defensible broader planning comparable is established with its limitations disclosed. Do not keep searching solely to collect more URLs.
18. Return one JSON file only. Do not return prose as the final answer.

[AZRAS PURPOSE — ROOT CAUSE FIRST]
The primary purpose is NOT to win a multi-AI price vote. The primary purpose is to establish WHY each planning price is reasonable.
For every item, identify the actual price basis, included work, excluded work, geographic basis, date, conversion, assumptions, unresolved points, and possible overlap with other AZRAS cost items.
Your result becomes the research map that other AIs will independently re-check. Do not hide uncertainty. If a defensible price cannot be established, leave it unresolved and explain exactly what is missing.

[CURRENT PROJECT PRICE SCOPE]
{json.dumps(scope,ensure_ascii=False,indent=2)}

[REQUIRED RETURN FILENAME]
`YYMMDD_HHMM_AZRAS_AI_APPROX_COST_{project_name}_<ai_name>.json`
Use the actual completion time. <ai_name> must identify the AI that actually performed the research, lowercase ASCII.

[REQUIRED JSON]
{{
  "schema":"AZRAS_AI_APPROX_COST",
  "schema_version":"1.4",
  "canonical_language":"en",
  "project":"{project_name}",
  "analysis":{{
    "type":"AI web research for approximate construction unit costs",
    "research_role":"primary_guide",
    "ai_reviewer":"Actual AI name",
    "status":"complete|partial",
    "completed_at":"ISO-8601 timestamp",
    "method_note":"Brief research method"
  }},
  "research_execution":{{
    "web_research_status":"completed|unavailable|failed",
    "web_search_attempted":true,
    "web_source_count":0,
    "research_failure_reason":null
  }},
  "location":{{
    "planning_region":"{planning_region}",
    "representative_cost_profile":"{region}",
    "representative_cost_profile_basis":"{profile_basis}",
    "country":"{country}",
    "city":"{city}",
    "project_address":"{address}",
    "research_location_basis":"project_address_authoritative",
    "currency":"{currency}"
  }},
  "unit_costs":{{
    "concrete":{{
      "unit":"m3",
      "material":null,
      "labor":null,
      "equipment":null,
      "installed_unit_cost":null,
      "provisional_unit_cost":null,
      "pricing_structure":"component_split|installed_all_in|provisional_estimate|not_found|research_unavailable",
      "candidate_quality":{{"source_type":"primary_market|government|industry|cost_guide|market|ai_generated_service|other","scope_definition":"material_only|installed_all_in|component_split|other","scope_includes":[],"scope_excludes":[],"assumptions_disclosed":false,"geographic_level":"city|metro|state|national|other","unresolved_points":[],"comparable_for_reconciliation":true,"exclusion_reason":null}},
      "installed_evidence":{{"status":"found|not_found|research_unavailable","source_type":null,"source_title":null,"source_url":null,"publication_date":null,"geographic_scope":null,"source_unit":null,"conversion_note":null,"evidence_note":null}},
      "provisional_evidence":{{"status":"found|not_found|research_unavailable","source_type":null,"source_title":null,"source_url":null,"publication_date":null,"geographic_scope":null,"source_unit":null,"conversion_note":null,"estimate_basis":null,"evidence_note":null}},
      "components":{{
        "material":{{"status":"found|not_found|research_unavailable","source_type":null,"source_title":null,"source_url":null,"publication_date":null,"geographic_scope":null,"evidence_note":null}},
        "labor":{{"status":"found|not_found|research_unavailable","source_type":null,"source_title":null,"source_url":null,"publication_date":null,"geographic_scope":null,"evidence_note":null}},
        "equipment":{{"status":"found|not_found|research_unavailable","source_type":null,"source_title":null,"source_url":null,"publication_date":null,"geographic_scope":null,"evidence_note":null}}
      }}
    }}
  }},
  "equipment_packages":{{
    "hvac":{{
      "pricing_mode":"lump_sum|unit_rate_per_gfa|not_found|research_unavailable",
      "cost":null,
      "unit_cost":null,
      "unit":"{currency}/m2_gfa",
      "currency":"{currency}",
      "status":"found|not_found|research_unavailable",
      "source_type":null,
      "source_title":null,
      "source_url":null,
      "publication_date":null,
      "geographic_scope":null,
      "evidence_note":null
    }}
  }},
  "research_sources":[
    {{"source_title":"","source_url":"","publication_date":null,"geographic_scope":"","source_type":"government|public|industry|market|other"}}
  ]
}}

Return only keys requested in CURRENT PROJECT PRICE SCOPE. Keep construction-item units exactly as requested.
For equipment unit_rate_per_gfa, normalize a sourced area rate to {currency}/m2_gfa and disclose any physical unit conversion.
If research_execution.web_research_status is unavailable or failed, set all affected item/package statuses to research_unavailable, keep numeric price fields null, and do not claim that the market price itself was not found.
A zero is valid only when a source explicitly proves a true zero price. Otherwise use null/not_found.
'''

    def _ai_cost_primary_summary_for_review(self):
        loc=self.db["locations"][self.location.get()]
        overlay=loc.get("_session_ai_unit_cost_overlay") if isinstance(loc,dict) else None
        sessions=list((overlay or {}).get("ai_candidate_sessions") or [])
        primary=[x for x in sessions if x.get("research_role")=="primary_guide" or self._ai_cost_norm_text(x.get("reviewer")).startswith("chatgpt")]
        if not primary:
            raise ValueError(self._ui("先にChatGPTの一次調査JSONを取り込んでください。","Import the ChatGPT primary-research JSON first."))
        p=max(primary,key=lambda x:str(x.get("completed_at") or ""))
        rows={}
        for key,c in (p.get("unit_cost_candidates") or {}).items():
            rows[key]={"unit":c.get("unit"),"pricing_structure":c.get("pricing_structure"),"price":self._ai_cost_candidate_total(c),"candidate_quality":c.get("candidate_quality"),"evidence":c.get("provisional_evidence") or c.get("installed_evidence") or c.get("source_components") or {}}
        return {"primary_reviewer":p.get("reviewer"),"completed_at":p.get("completed_at"),"source_json":p.get("source_json"),"researched_items":rows,"unresolved_items":p.get("incomplete_items") or []}

    def _ai_cost_review_request_text(self):
        scope=self._ai_cost_request_scope(); primary=self._ai_cost_primary_summary_for_review()
        project_name=Path(self.project_path).stem if self.project_path else "PROJECT_NAME"
        return f'''AZRAS AI APPROXIMATE COST INDEPENDENT REVIEW REQUEST v1.4 — ENGLISH CANONICAL

Project: {project_name}
Authoritative construction-cost location: {self._authoritative_project_cost_location()}
Currency: {str(self.currency.get() or "JPY").upper()}

{AZRAS_AI_STANDARD_RULES_V3_EN}
[PURPOSE]
This is NOT a price-voting exercise and NOT a request to match ChatGPT's numbers.
ChatGPT has performed the primary research and established an initial price basis. Independently re-check that BASIS using web research.
Find unreasonable parts, better/local/newer evidence, prices ChatGPT could not establish, ambiguities that can be resolved, and double-counting or scope errors.

[INDEPENDENCE RULE]
Do not copy the primary number merely because it is shown. Re-open/re-search cited sources where possible and independently search for corroborating or contradicting evidence. A different number is useful when its reason is explained.

[RESEARCH ROUTE]
1. Use the authoritative project location: city/metro first, then state/region, then national.
2. Keep each AZRAS item's requested unit and work scope. Do not silently broaden scope.
3. Identify what the price includes/excludes, especially work already represented by another AZRAS item.
4. Prefer primary market, government, recognized industry and construction-cost sources; record URL, date and geography.
5. Disclose physical conversions and every planning assumption.
6. If web research is unavailable, report research_unavailable; never invent a price.
7. For an unresolved primary item, actively search for a defensible source-backed planning value.
8. For every reviewed item report: supports_primary_basis | challenges_primary_basis | fills_primary_gap | clarifies_primary_ambiguity | still_unresolved.

[CURRENT AZRAS PRICE SCOPE]
{json.dumps(scope,ensure_ascii=False,indent=2)}

[CHATGPT PRIMARY RESEARCH MAP — RE-CHECK THIS, DO NOT BLINDLY FOLLOW IT]
{json.dumps(primary,ensure_ascii=False,indent=2)}

[MANDATORY REVIEW OUTPUT CONTRACT]
- This is a CONSTRUCTION-COST review. Do NOT return AZRAS_AI_TAKEOFF, AZRAS_AI_TAKEOFF_FINAL_REVIEW, or any quantity-takeoff schema.
- Root schema MUST be "AZRAS_AI_APPROX_COST" and schema_version MUST be "1.4".
- analysis.research_role MUST be "reviewer"; analysis.ai_reviewer must identify the AI actually responding; analysis.completed_at must be ISO-8601 UTC.
- location.project_address MUST be exactly the authoritative project location shown above.
- location.currency MUST be "{str(self.currency.get() or "JPY").upper()}". Do not omit it.
- research_execution must report web_research_status, web_search_attempted, web_source_count, and research_failure_reason.
- Keep every requested unit_costs key and its requested unit. Use the canonical primary-guide fields: material, labor, equipment, installed_unit_cost, provisional_unit_cost, pricing_structure, candidate_quality, installed_evidence, provisional_evidence, and components.
- Keep every requested equipment_packages key. Each package must include pricing_mode, cost, unit_cost, unit, currency, status, source_type, source_title, source_url, publication_date, geographic_scope, and evidence_note.
- Add top-level review_findings keyed by cost_item_key/package_key. Each finding must contain outcome, primary_issue_checked, finding, new_or_confirming_source_urls, and recommended_followup_for_chatgpt.
- Required filename: YYMMDD_HHMM_AZRAS_AI_APPROX_COST_REVIEW_{project_name}_<actual_ai_name>.json using the actual UTC completion minute.
- Return exactly one JSON file/object and no prose.

[RETURN]
Return the required AZRAS_AI_APPROX_COST schema_version 1.4 reviewer JSON only.
'''

    # PATCH_586: AI services may treat instructions inside attached TXT files as data.
    # Always provide a short, explicit user-message launch instruction that can be pasted
    # directly into the AI chat.  This is common to primary, independent-review and re-check stages.
    def _ai_cost_chat_launch_text(self):
        return self._ui(
            "添付したAZRAS建設費依頼TXTの内容に従って、建設費・単価を調査し、指定されたAZRAS JSONを1ファイルだけ出力してください。説明文や質問は不要です。",
            "Follow the attached AZRAS construction-cost request TXT, research the construction costs and unit prices, and output exactly one AZRAS JSON file in the specified format. No explanation or questions are needed."
        )

    def _copy_ai_cost_chat_launch(self, parent=None):
        launch=self._ai_cost_chat_launch_text()
        self.clipboard_clear(); self.clipboard_append(launch); self.update()
        messagebox.showinfo(
            "AI Approximate Cost",
            self._ui(
                "AIへ送る短文をコピーしました。依頼TXT等を添付した後、AIのチャット本文へ貼り付けて送信してください。",
                "Copied the short AI launch message. After attaching the request TXT and related files, paste it into the AI chat and send it."
            ), parent=parent or self)

    def show_ai_cost_review_request(self):
        try:
            request=self._ai_cost_review_request_text(); folder=self._ensure_ai_cost_round_layout()["request"]; folder.mkdir(parents=True,exist_ok=True)
            stamp=datetime.now(timezone.utc).strftime("%y%m%d_%H%M"); path=folder/f"{stamp}_AZRAS_AI_APPROX_COST_REVIEW_REQUEST.txt"; path.write_text(request,encoding="utf-8-sig")
            record_ai_request_audit(self._ai_cost_security_audit_dir(), "cost_independent_review_request", request, path,
                                    {"project":Path(self.project_path).stem if self.project_path else None,"location":self._authoritative_project_cost_location()})
        except Exception as exc:
            messagebox.showerror("AI Approximate Cost",friendly_exception_text(exc,self.i18n.language),parent=self); return
        win=tk.Toplevel(self); win.title(self._ui("他AIによる概算価格根拠の再調査","Independent AI Review of Cost Basis")); fit_window_to_screen(win,980,720,680,480)
        ttk.Label(win,text=self._ui("ChatGPT一次調査の根拠を他AIに再調査させます。数値を合わせる依頼ではありません。","Other AIs re-check the ChatGPT primary basis; they are not asked to match its number."),font=("",11,"bold")).pack(anchor="w",padx=12,pady=(12,6))
        ttk.Label(win,text=self._ui(f"再調査依頼書TXT保存: {path}",f"Review request TXT saved: {path}"),foreground="#006400").pack(anchor="w",padx=12,pady=(0,4))
        ttk.Label(win,text=self._ui("重要: 依頼TXTを添付するだけでなく、下の「AIへ送る短文をコピー」を押し、AIのチャット本文へ貼り付けて送信してください。","Important: Do not rely on the attached TXT alone. Click “Copy short message for AI”, paste it into the AI chat, and send it."),foreground="#8B4513").pack(anchor="w",padx=12,pady=(0,4))
        txt_host=ttk.Frame(win);txt_host.pack(fill="both",expand=True,padx=12,pady=6);txt_host.rowconfigure(0,weight=1);txt_host.columnconfigure(0,weight=1)
        txt=tk.Text(txt_host,wrap="none"); txt_y=ttk.Scrollbar(txt_host,orient="vertical",command=txt.yview);txt_x=ttk.Scrollbar(txt_host,orient="horizontal",command=txt.xview);txt.configure(yscrollcommand=txt_y.set,xscrollcommand=txt_x.set)
        txt.grid(row=0,column=0,sticky="nsew");txt_y.grid(row=0,column=1,sticky="ns");txt_x.grid(row=1,column=0,sticky="ew"); txt.insert("1.0",request)
        def copy_request():
            self.clipboard_clear(); self.clipboard_append(request); self.update(); messagebox.showinfo("AI Approximate Cost",self._ui("再調査依頼書をコピーしました。ChatGPT以外のAIへ送ってください。","Review request copied. Send it to non-ChatGPT AIs."),parent=win)
        bar=ttk.Frame(win); bar.pack(fill="x",padx=12,pady=(4,12)); ttk.Button(bar,text=self._ui("再調査依頼書をコピー","Copy review request"),command=copy_request).pack(side="left"); ttk.Button(bar,text=self._ui("AIへ送る短文をコピー","Copy short message for AI"),command=lambda:self._copy_ai_cost_chat_launch(win)).pack(side="left",padx=(8,0)); ttk.Button(bar,text=self._ui("閉じる","Close"),command=win.destroy).pack(side="right")

    @staticmethod
    def _ai_cost_recheck_needs_full_evidence(outcome):
        """Only these outcomes justify resending full evidence for an item in the re-check
        request; supports_primary_basis items are already agreed and get a one-line summary."""
        return str(outcome or "").strip().lower() in {
            "challenges_primary_basis","fills_primary_gap","clarifies_primary_ambiguity","still_unresolved",""}

    def _ai_cost_recheck_context(self):
        """Build the evidence packet for ChatGPT's post-review re-check.

        To keep this request from growing every round, an item is reduced to a one-line
        confirmed_supported_items entry once every reviewer's finding for it is
        supports_primary_basis; only items a reviewer actually challenged, gap-filled,
        flagged ambiguous, or left unresolved carry their full evidence packet."""
        loc=self.db["locations"][self.location.get()]
        overlay=loc.get("_session_ai_unit_cost_overlay") if isinstance(loc,dict) else None
        sessions=list((overlay or {}).get("ai_candidate_sessions") or [])
        primary=[x for x in sessions if x.get("research_role") in {"primary_guide","primary_recheck"} or self._ai_cost_norm_text(x.get("reviewer")).startswith("chatgpt")]
        reviewers=[x for x in sessions if x.get("research_role")=="reviewer"]
        if not primary:
            raise ValueError(self._ui("先にChatGPTの一次調査JSONを取り込んでください。","Import the ChatGPT primary-research JSON first."))
        if not reviewers:
            raise ValueError(self._ui("先に他AIの再調査JSONを取り込んでください。","Import at least one independent-review JSON first."))
        p=max(primary,key=lambda x:str(x.get("completed_at") or ""))
        primary_rows={}
        for key,c in (p.get("unit_cost_candidates") or {}).items():
            primary_rows[key]={"unit":c.get("unit"),"pricing_structure":c.get("pricing_structure"),"price":self._ai_cost_candidate_total(c),"candidate_quality":c.get("candidate_quality"),"evidence":c.get("provisional_evidence") or c.get("installed_evidence") or c.get("source_components") or {}}
        # Determine, per cost_item_key, whether ANY reviewer raised something other than
        # supports_primary_basis. Only those keys keep full per-reviewer evidence.
        keys_needing_review=set()
        for r in reviewers:
            for key,finding in (r.get("review_findings") or {}).items():
                outcome=finding.get("outcome") if isinstance(finding,dict) else finding
                if self._ai_cost_recheck_needs_full_evidence(outcome):
                    keys_needing_review.add(key)
            for key in (r.get("unit_cost_candidates") or {}).keys():
                if key not in (r.get("review_findings") or {}):
                    keys_needing_review.add(key)  # no explicit finding recorded → treat as needing review, don't silently drop
        confirmed_supported_items=[]
        for key,row in primary_rows.items():
            if key not in keys_needing_review:
                confirmed_supported_items.append({"cost_item_key":key,"unit":row.get("unit"),"price":row.get("price"),
                    "supporting_reviewers":sorted([r.get("reviewer") for r in reviewers
                        if isinstance((r.get("review_findings") or {}).get(key),dict)
                        and str((r.get("review_findings") or {}).get(key,{}).get("outcome") or "").lower()=="supports_primary_basis"])})
        def _filter_incomplete(_rows):
            out=[]
            for _rec in (_rows or []):
                if not isinstance(_rec,dict): continue
                _key=_rec.get("cost_item_key") or _rec.get("package_key")
                if _key in keys_needing_review:
                    out.append(_rec)
            return out
        reviewer_packet=[]
        for r in reviewers:
            numeric={}
            for key,c in (r.get("unit_cost_candidates") or {}).items():
                if key not in keys_needing_review:
                    continue
                numeric[key]={"unit":c.get("unit"),"pricing_structure":c.get("pricing_structure"),"price":self._ai_cost_candidate_total(c),"candidate_quality":c.get("candidate_quality"),"evidence":c.get("provisional_evidence") or c.get("installed_evidence") or c.get("source_components") or {},"scope_overlap_risk":bool(c.get("scope_overlap_risk"))}
            findings={key:f for key,f in (r.get("review_findings") or {}).items() if key in keys_needing_review}
            filtered_incomplete=_filter_incomplete(r.get("incomplete_items") or [])
            if not numeric and not findings and not filtered_incomplete:
                continue  # this reviewer had nothing but supported items — nothing left to re-check
            reviewer_packet.append({"reviewer":r.get("reviewer"),"completed_at":r.get("completed_at"),"source_json":r.get("source_json"),"research_execution_status":r.get("research_execution_status"),"review_findings":findings,"numeric_candidates":numeric,"incomplete_items":filtered_incomplete})
        researched_items_needing_review={k:v for k,v in primary_rows.items() if k in keys_needing_review}
        return {
            "primary":{"reviewer":p.get("reviewer"),"completed_at":p.get("completed_at"),"source_json":p.get("source_json"),
                "researched_items_needing_review":researched_items_needing_review,"unresolved_items":_filter_incomplete(p.get("incomplete_items") or [])},
            "confirmed_supported_items":confirmed_supported_items,
            "independent_reviews":reviewer_packet,
        }

    def _ai_cost_recheck_request_text(self):
        scope=self._ai_cost_request_scope(); context=self._ai_cost_recheck_context()
        project_name=Path(self.project_path).stem if self.project_path else "PROJECT_NAME"
        currency=str(self.currency.get() or "JPY").upper()
        return f'''AZRAS AI APPROXIMATE COST CHATGPT RE-CHECK REQUEST v1.5 — ENGLISH CANONICAL

Project: {project_name}
Authoritative construction-cost location: {self._authoritative_project_cost_location()}
Currency: {currency}

{AZRAS_AI_STANDARD_RULES_V3_EN}
[PURPOSE]
You are ChatGPT performing the FINAL EVIDENCE RE-CHECK after independent AI reviews.
This is NOT a majority vote, NOT averaging, and NOT a request to copy another AI's number.
Re-open and independently verify useful new evidence. Resolve challenged assumptions, fill primary gaps only where the new evidence is defensible, reject scope-mismatched evidence, and leave genuinely unresolved items unresolved.

[DECISION RULE]
1. The existing ChatGPT primary basis remains the starting point, not an unquestionable answer.
2. For reviewer findings marked challenges_primary_basis, directly re-check the challenged source/scope/conversion.
3. For fills_primary_gap, independently open/re-search the proposed source before adopting any numeric value.
4. For clarifies_primary_ambiguity, resolve the ambiguity when evidence permits; otherwise record exactly what remains unknown.
5. For supports_primary_basis, confirm only after independently checking the evidence trail; do not count AI agreement as proof.
6. Reject double counting. Preserve AZRAS cost ownership: one work scope must not be monetized twice.
7. Prefer project city/metro, then state/region, then national. Prefer direct/current/traceable sources.
8. If a reviewer source is malformed, inaccessible, weak, AI-generated, or scope-mismatched, say so and do not adopt it automatically.
9. When the evidence supports a revised planning price, return that price with the full basis and source. When it does not, keep not_found.
10. Web research must actually be performed. If unavailable, return research_unavailable rather than inventing a price.
11. confirmed_supported_items are items where every reviewer's finding was supports_primary_basis; they are compact summaries, not settled results. If your own re-check of a confirmed_supported_items source turns up a problem, treat it as a fresh challenge: report it and revise that item's decision under recheck_findings.
12. researched_items_needing_review and independent_reviews carry only the cost_item_key/package_key values that a reviewer actually challenged, gap-filled, flagged ambiguous, or left unresolved (or that had no recorded finding). These, not the already-supported items, are where your web research time should go.

[CURRENT AZRAS PRICE SCOPE]
{json.dumps(scope,ensure_ascii=False,indent=2)}

[PRIMARY BASIS + INDEPENDENT REVIEW EVIDENCE PACKET — confirmed_supported_items is a one-line-per-item summary; researched_items_needing_review and independent_reviews carry full evidence only for items with a real discrepancy or open status]
{json.dumps(context,ensure_ascii=False,indent=2)}

[RETURN]
Return AZRAS_AI_APPROX_COST schema_version 1.4 JSON only.
Returned filename MUST be: YYMMDD_HHMM_AZRAS_AI_APPROX_COST_FINAL_{project_name}_chatgpt.json using the actual completion minute in UTC. Do not use local time or seconds.
The FINAL marker is mandatory because this response is the formal ChatGPT final re-check result imported at step ⑥.
Set analysis.research_role="primary_recheck" and ai_reviewer to the actual ChatGPT model name.
Keep the same unit_costs/equipment_packages structures used by the v1.4 primary request, including candidate_quality.scope_includes, scope_excludes and unresolved_points.
Add top-level recheck_findings keyed by every requested cost_item_key/package_key with:
- decision: retained_primary_basis | revised_primary_basis | reviewer_gap_verified_and_filled | reviewer_evidence_rejected | still_unresolved
- primary_basis_checked
- reviewer_evidence_checked
- final_reason
- accepted_source_urls
- rejected_source_urls
- remaining_uncertainty
The returned numeric price is the current AZRAS planning price basis only when supported by your re-check. Do not return a reviewer number merely because another AI proposed it.
'''

    def show_ai_cost_recheck_request(self):
        try:
            request=self._ai_cost_recheck_request_text(); folder=self._ensure_ai_cost_round_layout()["recheck"]; folder.mkdir(parents=True,exist_ok=True)
            stamp=datetime.now(timezone.utc).strftime("%y%m%d_%H%M"); path=folder/f"{stamp}_AZRAS_AI_APPROX_COST_CHATGPT_FINAL_RECHECK_REQUEST.txt"; path.write_text(request,encoding="utf-8-sig")
            record_ai_request_audit(self._ai_cost_security_audit_dir(), "cost_final_recheck_request", request, path,
                                    {"project":Path(self.project_path).stem if self.project_path else None,"location":self._authoritative_project_cost_location()})
        except Exception as exc:
            messagebox.showerror("AI Approximate Cost",friendly_exception_text(exc,self.i18n.language),parent=self); return
        win=tk.Toplevel(self); win.title(self._ui("ChatGPTによる概算価格根拠の再確認","ChatGPT Re-check of Approximate-Cost Evidence")); fit_window_to_screen(win,980,720,680,480)
        ttk.Label(win,text=self._ui("他AIが発見・反証・補完した根拠をChatGPTへ戻し、Webで再確認します。多数決ではありません。","Return reviewer evidence to ChatGPT for an independent web re-check; this is not price voting."),font=("",11,"bold")).pack(anchor="w",padx=12,pady=(12,6))
        ttk.Label(win,text=self._ui(f"再確認依頼書TXT保存: {path}",f"Re-check request TXT saved: {path}"),foreground="#006400").pack(anchor="w",padx=12,pady=(0,4))
        ttk.Label(win,text=self._ui("重要: 依頼TXTを添付するだけでなく、下の「AIへ送る短文をコピー」を押し、AIのチャット本文へ貼り付けて送信してください。","Important: Do not rely on the attached TXT alone. Click “Copy short message for AI”, paste it into the AI chat, and send it."),foreground="#8B4513").pack(anchor="w",padx=12,pady=(0,4))
        txt_host=ttk.Frame(win);txt_host.pack(fill="both",expand=True,padx=12,pady=6);txt_host.rowconfigure(0,weight=1);txt_host.columnconfigure(0,weight=1)
        txt=tk.Text(txt_host,wrap="none"); txt_y=ttk.Scrollbar(txt_host,orient="vertical",command=txt.yview);txt_x=ttk.Scrollbar(txt_host,orient="horizontal",command=txt.xview);txt.configure(yscrollcommand=txt_y.set,xscrollcommand=txt_x.set)
        txt.grid(row=0,column=0,sticky="nsew");txt_y.grid(row=0,column=1,sticky="ns");txt_x.grid(row=1,column=0,sticky="ew"); txt.insert("1.0",request)
        def copy_request():
            self.clipboard_clear(); self.clipboard_append(request); self.update(); messagebox.showinfo("AI Approximate Cost",self._ui("再確認依頼書をコピーしました。ChatGPTへ送ってください。","Re-check request copied. Send it to ChatGPT."),parent=win)
        bar=ttk.Frame(win); bar.pack(fill="x",padx=12,pady=(4,12)); ttk.Button(bar,text=self._ui("再確認依頼書をコピー","Copy re-check request"),command=copy_request).pack(side="left"); ttk.Button(bar,text=self._ui("AIへ送る短文をコピー","Copy short message for AI"),command=lambda:self._copy_ai_cost_chat_launch(win)).pack(side="left",padx=(8,0)); ttk.Button(bar,text=self._ui("閉じる","Close"),command=win.destroy).pack(side="right")

    def _save_ai_cost_request_txt(self,request):
        if not isinstance(request,str) or not request.strip():
            raise ValueError("AI approximate-cost request text is empty.")
        folder=self._ensure_ai_cost_round_layout()["request"]; folder.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime("%y%m%d_%H%M")
        target=folder/f"{stamp}_AZRAS_AI_APPROX_COST_REQUEST.txt"
        tmp=folder/f".{stamp}_AZRAS_AI_APPROX_COST_REQUEST.tmp"
        tmp.write_text(request,encoding="utf-8-sig"); os.replace(tmp,target)
        record_ai_request_audit(self._ai_cost_security_audit_dir(), "cost_primary_request", request, target,
                                {"project":Path(self.project_path).stem if self.project_path else None,"location":self._authoritative_project_cost_location()})
        return target

    def show_ai_cost_request(self):
        # PATCH_507: cost research is downstream of the current Module 1 quantity scope.
        self.refresh_project_from_context()
        if self.project is None:
            messagebox.showwarning("AI Approximate Cost",self._ui("先にModule 0でProject JSONを選択してください。","Select a Project JSON in Module 0 first."),parent=self); return
        try:
            require_current_module_output(self.project, "module1", "Module 1")
        except Exception:
            messagebox.showwarning(
                "AI Approximate Cost",
                self._ui(
                    "AIによる地域単価調査の前に、先に『図面解析・数量計算』を実行してください。数量・単位・工種範囲を確定してから単価調査を行います。",
                    "Before AI regional unit-cost research, run Drawing Analysis / Quantity Calculation first. Unit-cost research must follow the established quantities, units, and work scope."),
                parent=self); return
        try:
            request=self._ai_cost_request_text()
            path=self._save_ai_cost_request_txt(request)
        except Exception as exc:
            messagebox.showerror("AI Approximate Cost",friendly_exception_text(exc,self.i18n.language),parent=self); return
        win=tk.Toplevel(self); win.title(self._ui("AI概算単価 調査開始","Start AI Approximate-Cost Research")); fit_window_to_screen(win,980,720,680,480)
        ttk.Label(win,text=self._ui("下の一次調査依頼書をChatGPTへ送り、ChatGPTから返されたJSONを②「ChatGPT調査JSON取込」へ取り込んでください。","Send this primary research request to ChatGPT, then import the JSON returned by ChatGPT using ② Import ChatGPT Research JSON."),font=("",11,"bold")).pack(anchor="w",padx=12,pady=(12,6))
        ttk.Label(win,text=self._ui(f"依頼書TXT保存: {path}",f"Request TXT saved: {path}"),foreground="#006400").pack(anchor="w",padx=12,pady=(0,4))
        ttk.Label(win,text=self._ui("重要: 依頼TXTを添付するだけでなく、下の「AIへ送る短文をコピー」を押し、AIのチャット本文へ貼り付けて送信してください。","Important: Do not rely on the attached TXT alone. Click “Copy short message for AI”, paste it into the AI chat, and send it."),foreground="#8B4513").pack(anchor="w",padx=12,pady=(0,4))
        txt_host=ttk.Frame(win);txt_host.pack(fill="both",expand=True,padx=12,pady=6);txt_host.rowconfigure(0,weight=1);txt_host.columnconfigure(0,weight=1)
        txt=tk.Text(txt_host,wrap="none"); txt_y=ttk.Scrollbar(txt_host,orient="vertical",command=txt.yview);txt_x=ttk.Scrollbar(txt_host,orient="horizontal",command=txt.xview);txt.configure(yscrollcommand=txt_y.set,xscrollcommand=txt_x.set)
        txt.grid(row=0,column=0,sticky="nsew");txt_y.grid(row=0,column=1,sticky="ns");txt_x.grid(row=1,column=0,sticky="ew"); txt.insert("1.0",request)
        def copy_request():
            self.clipboard_clear(); self.clipboard_append(request); self.update()
            messagebox.showinfo("AI Approximate Cost",self._ui("一次調査依頼書をコピーしました。ChatGPTへ送ってください。","Primary research request copied. Send it to ChatGPT."),parent=win)
        bar=ttk.Frame(win); bar.pack(fill="x",padx=12,pady=(4,12))
        ttk.Button(bar,text=self._ui("ChatGPTへの依頼書をコピー","Copy request for ChatGPT"),command=copy_request).pack(side="left")
        ttk.Button(bar,text=self._ui("AIへ送る短文をコピー","Copy short message for AI"),command=lambda:self._copy_ai_cost_chat_launch(win)).pack(side="left",padx=(8,0))
        ttk.Button(bar,text=self._ui("閉じる","Close"),command=win.destroy).pack(side="right")

    @staticmethod
    def _ai_cost_component_source_ok(comp):
        if not isinstance(comp,dict): return False
        if str(comp.get("status") or "").lower()!="found": return False
        return bool(str(comp.get("source_url") or comp.get("source_reference") or "").strip())

    @staticmethod
    def _ai_cost_norm_text(value):
        return " ".join(str(value or "").strip().lower().replace("\\","/").split())

    @staticmethod
    def _ai_cost_candidate_total(rec):
        if not isinstance(rec,dict):
            return None
        structure=str(rec.get("pricing_structure") or "").lower()
        if structure in {"installed_all_in","provisional_estimate"}:
            key="installed_unit_cost" if structure=="installed_all_in" else "provisional_unit_cost"
            try: return float(rec.get(key))
            except Exception: return None
        if structure=="component_split":
            try: return sum(float(rec.get(x)) for x in ("material","labor","equipment"))
            except Exception: return None
        return None

    def _ai_cost_source_fingerprint(self, rec):
        if not isinstance(rec,dict): return ""
        structure=str(rec.get("pricing_structure") or "").lower()
        urls=[]
        if structure=="provisional_estimate":
            urls.append(str((rec.get("provisional_evidence") or {}).get("source_url") or ""))
        elif structure=="installed_all_in":
            urls.append(str((rec.get("installed_evidence") or {}).get("source_url") or ""))
        else:
            comps=rec.get("source_components") or rec.get("components") or {}
            for c in ("material","labor","equipment"):
                urls.append(str((comps.get(c) or {}).get("source_url") or ""))
        norm=[]
        for u in urls:
            u=self._ai_cost_norm_text(u)
            if not u: continue
            raw=u.replace("https://","",1).replace("http://","",1)
            domain=raw.split("/",1)[0].split()[0].lower().lstrip("www.")
            if domain: norm.append(domain)
        return "|".join(sorted(set(norm)))

    def _ai_cost_evidence_rank(self, rec, project_address):
        """Deterministic evidence ordering; no hidden price averaging or subjective weights."""
        if not isinstance(rec,dict): return (0,0,0,0)
        structure=str(rec.get("pricing_structure") or "").lower()
        if structure=="provisional_estimate": ev=rec.get("provisional_evidence") or {}
        elif structure=="installed_all_in": ev=rec.get("installed_evidence") or {}
        else:
            comps=rec.get("components") or {}
            scopes=" ".join(str((comps.get(c) or {}).get("geographic_scope") or "") for c in ("material","labor","equipment"))
            dates=" ".join(str((comps.get(c) or {}).get("publication_date") or "") for c in ("material","labor","equipment"))
            ev={"geographic_scope":scopes,"publication_date":dates,"source_url":" ".join(str((comps.get(c) or {}).get("source_url") or "") for c in ("material","labor","equipment"))}
        geo=self._ai_cost_norm_text(ev.get("geographic_scope"))
        addr=self._ai_cost_norm_text(project_address)
        geo_rank=0
        if any(x in geo for x in ("nashville","37210")) or (addr and addr in geo): geo_rank=3
        elif any(x in geo for x in ("tennessee"," tn ","tn,")): geo_rank=2
        elif any(x in geo for x in ("united states","national","u.s.","usa")): geo_rank=1
        date_text=str(ev.get("publication_date") or "")
        year=0
        import re as _re
        m=_re.search(r"(20\d{2})",date_text)
        if m: year=int(m.group(1))
        exact_rank=2 if structure in {"installed_all_in","component_split"} else (1 if structure=="provisional_estimate" else 0)
        has_url=1 if str(ev.get("source_url") or ev.get("source_reference") or "").strip() else 0
        q=rec.get("candidate_quality") or {}
        source_type=self._ai_cost_norm_text(q.get("source_type") or ev.get("source_type"))
        source_rank={"primary_market":6,"government":6,"industry":5,"cost_guide":4,"market":3,"public":3,"other":2,"ai_generated_service":1}.get(source_type,2)
        return (geo_rank,year,source_rank,has_url,exact_rank)

    def _ai_cost_scope_overlap_risk(self, key, rec, requested_keys):
        """Reject obvious double-counting descriptions, not merely high/low prices."""
        if not isinstance(rec,dict): return False
        if str(rec.get("pricing_structure") or "").lower()!="installed_all_in": return False
        if key=="concrete" and "formwork" in requested_keys:
            ev=rec.get("installed_evidence") or {}
            text=self._ai_cost_norm_text(" ".join(str(ev.get(x) or "") for x in ("source_title","conversion_note","evidence_note")))
            if "formwork" in text or "includes labor/form" in text or "form/finish" in text:
                return True
        return False

    def _parse_ai_cost_payload(self, payload, source_path, scope, expected_currency):
        _schema=str(payload.get("schema") or "")
        if _schema!="AZRAS_AI_APPROX_COST":
            if _schema in {"AZRAS_AI_TAKEOFF","AZRAS_AI_TAKEOFF_FINAL_REVIEW"}:
                raise ValueError(self._ui(
                    f"選択したJSONは数量積算用（{_schema}）で、Module 5 の建設費・単価JSONではありません。③『他AI再調査依頼書』に従って返された AZRAS_AI_APPROX_COST JSON を④で選択してください。",
                    f"The selected JSON is a quantity-takeoff response ({_schema}), not a Module 5 construction-cost response. In step ④ select the AZRAS_AI_APPROX_COST JSON returned from the step ③ independent cost-review request."))
            raise ValueError(f"Unsupported AI cost schema: {payload.get('schema') or '(missing)'}")
        schema_version=str(payload.get("schema_version") or "")
        if schema_version not in {"1.0","1.1","1.2","1.3","1.4"}:
            raise ValueError(f"Unsupported AI cost schema_version: {payload.get('schema_version')}")
        # PATCH_045: reviewer AIs sometimes omit the canonical currency field even
        # though their evidence and monetary field names explicitly identify the same
        # currency as the Project.  Keep the primary-guide contract strict, but permit
        # a reviewer-only compatibility fallback when the payload itself contains
        # unambiguous currency evidence (for example JPY/m2 source units or price_JPY).
        # Never infer when no currency evidence exists or when multiple currencies occur.
        _analysis0=payload.get("analysis") if isinstance(payload.get("analysis"),dict) else {}
        _reviewer0=str((_analysis0.get("ai_reviewer") or _analysis0.get("reviewer") or "UnknownAI")).strip()
        _research_role0=str((_analysis0.get("research_role") or ("primary_guide" if _reviewer0.lower().startswith("chatgpt") else "reviewer"))).lower()
        currency_candidates=[]
        def _push_currency(value, origin):
            cur=str(value or "").strip().upper()
            if cur:
                currency_candidates.append((origin,cur))
        _push_currency(((payload.get("location") or {}).get("currency") if isinstance(payload.get("location"),dict) else None),"location.currency")
        _push_currency(payload.get("currency"),"currency")
        _push_currency(((payload.get("analysis") or {}).get("currency") if isinstance(payload.get("analysis"),dict) else None),"analysis.currency")
        pp_for_currency=payload.get("equipment_packages") or {}
        if isinstance(pp_for_currency,dict):
            _pkg_iter=pp_for_currency.values()
        elif isinstance(pp_for_currency,list):
            _pkg_iter=pp_for_currency
        else:
            _pkg_iter=[]
        for _pkg in _pkg_iter:
            if isinstance(_pkg,dict):
                _push_currency(_pkg.get("currency") or _pkg.get("required_currency"),"equipment_packages.currency")
        declared_currencies=sorted(set(cur for _,cur in currency_candidates))
        if len(declared_currencies)>1:
            raise ValueError(f"AI cost currency conflict: expected {expected_currency}, declarations={declared_currencies}")
        got_currency=declared_currencies[0] if declared_currencies else ""
        currency_validation={"mode":"declared" if got_currency else "missing","evidence":currency_candidates}
        if not got_currency and _research_role0=="reviewer":
            # Search only explicit machine-readable hints in the reviewer payload.
            # Field-name suffixes (price_JPY/cost_USD) and source-unit strings
            # (JPY/m2, USD/ft2, etc.) are admissible evidence; country/address alone
            # is intentionally insufficient to infer currency.
            known={"JPY","USD","EUR","GBP","AUD","CAD","NZD","CNY","RMB","KRW","INR","CHF","SEK","NOK","DKK","SGD","HKD","TWD","THB","MYR","IDR","PHP","VND","AED","SAR","QAR","ZAR","BRL","MXN"}
            inferred=set()
            def _scan_currency_hints(obj):
                if isinstance(obj,dict):
                    for _k,_v in obj.items():
                        _ku=str(_k).upper()
                        for _cur in known:
                            if _ku.endswith("_"+_cur) or _ku.startswith(_cur+"_"):
                                inferred.add(_cur)
                        if str(_k).lower() in {"source_unit","currency","required_currency"} and isinstance(_v,str):
                            _vu=_v.upper()
                            for _cur in known:
                                if _cur in _vu:
                                    inferred.add(_cur)
                        _scan_currency_hints(_v)
                elif isinstance(obj,list):
                    for _v in obj:
                        _scan_currency_hints(_v)
            _scan_currency_hints(payload)
            if inferred=={expected_currency}:
                got_currency=expected_currency
                currency_validation={"mode":"reviewer_payload_inference","evidence":sorted(inferred)}
            elif len(inferred)>1:
                raise ValueError(f"AI cost currency conflict: expected {expected_currency}, inferred={sorted(inferred)}")
        if got_currency!=expected_currency:
            raise ValueError(f"AI cost currency mismatch: expected {expected_currency}, got {got_currency or '(missing)'}")
        expected_address=self._authoritative_project_cost_location()
        _analysis=payload.get("analysis") if isinstance(payload.get("analysis"),dict) else {}
        _loc=payload.get("location") if isinstance(payload.get("location"),dict) else {}
        _auth_loc=_analysis.get("authoritative_location") if isinstance(_analysis.get("authoritative_location"),dict) else {}
        got_address=str(_loc.get("project_address") or _loc.get("authoritative_location") or _auth_loc.get("address") or "").strip()
        if expected_address and got_address and self._ai_cost_norm_text(expected_address)!=self._ai_cost_norm_text(got_address):
            raise ValueError(self._ui(
                f"AI回答の調査住所がProject住所と一致しません: {got_address} / Project: {expected_address}",
                f"AI response project address does not match the Project address: {got_address} / Project: {expected_address}"))
        reviewer=str((_analysis.get("ai_reviewer") or _analysis.get("reviewer") or "UnknownAI")).strip()
        research_role=str((_analysis.get("research_role") or ("primary_guide" if reviewer.lower().startswith("chatgpt") else "reviewer"))).lower()
        _evo=_analysis.get("evolution_observation") if isinstance(_analysis.get("evolution_observation"),dict) else {}
        completed=str((_analysis.get("completed_at") or _analysis.get("reviewed_at") or _analysis.get("response_timestamp") or _evo.get("response_timestamp") or ""))
        execution=payload.get("research_execution") if isinstance(payload.get("research_execution"),dict) else {}
        if schema_version in {"1.3","1.4"}:
            research_status=str(execution.get("web_research_status") or "").lower()
            attempted=execution.get("web_search_attempted")
            # Primary-guide/recheck responses must obey the canonical execution block.
            # Reviewer AIs are compatibility-tolerant: retain their evidence as legacy_unknown
            # when they omit only this metadata, rather than rejecting the whole JSON.
            if research_status not in {"completed","unavailable","failed"}:
                if research_role=="reviewer":
                    research_status="legacy_unknown"; attempted=None
                else:
                    raise ValueError("AZRAS AI cost v1.3 requires research_execution.web_research_status = completed|unavailable|failed")
            elif research_status=="completed" and attempted is False:
                if research_role=="reviewer":
                    research_status="legacy_unknown"
                else:
                    raise ValueError("AZRAS AI cost v1.3 reports completed web research but web_search_attempted is false")
        else:
            research_status="legacy_unknown"
            attempted=None
        research_eligible=(research_status in {"completed","legacy_unknown"})
        if research_role=="primary_recheck" and schema_version=="1.4" and not isinstance(payload.get("recheck_findings"),dict):
            raise ValueError("AZRAS AI cost primary_recheck v1.4 requires top-level recheck_findings")
        req_by_key={x["cost_item_key"]:x for x in scope["items"]}
        requested_keys=set(req_by_key)
        candidates={}; incomplete=[]
        unit_payload=payload.get("unit_costs") or {}
        if isinstance(unit_payload,list):
            unit_payload={str(x.get("cost_item_key")):x for x in unit_payload if isinstance(x,dict) and x.get("cost_item_key")}
        for key,req in req_by_key.items():
            rec=unit_payload.get(key) if isinstance(unit_payload,dict) else None
            # PATCH 528 reviewer compatibility: several AIs return a compact
            # price/evidence record instead of the primary-guide field names.
            if isinstance(rec,dict) and research_role=="reviewer" and rec.get("price") is not None:
                rec=dict(rec)
                _simple_ev=rec.get("evidence") if isinstance(rec.get("evidence"),dict) else {}
                _finding=(payload.get("review_findings") or {}).get(key) if isinstance(payload.get("review_findings"),dict) else {}
                if not _simple_ev.get("source_url") and isinstance(_finding,dict):
                    _urls=_finding.get("new_or_confirming_source_urls") or []
                    if _urls:
                        _simple_ev=dict(_simple_ev); _simple_ev["source_url"]=_urls[0]
                        _simple_ev.setdefault("status","found")
                        _simple_ev.setdefault("source_type","other")
                        _simple_ev.setdefault("source_title",f"{reviewer} reviewer evidence")
                        _simple_ev.setdefault("evidence_note",str(_finding.get("finding") or rec.get("note") or "Reviewer source evidence"))
                _structure=str(rec.get("pricing_structure") or "installed_all_in").lower()
                if _structure not in {"installed_all_in","component_split","provisional_estimate"}:
                    _structure="installed_all_in"
                rec["pricing_structure"]=_structure
                if _structure=="installed_all_in":
                    rec.setdefault("installed_unit_cost",rec.get("price")); rec.setdefault("installed_evidence",_simple_ev)
                elif _structure=="provisional_estimate":
                    rec.setdefault("provisional_unit_cost",rec.get("price")); rec.setdefault("provisional_evidence",_simple_ev)
                if not isinstance(rec.get("candidate_quality"),dict):
                    rec["candidate_quality"]={"source_type":str(_simple_ev.get("source_type") or "other").lower(),"scope_definition":"installed_all_in" if _structure=="installed_all_in" else "other","scope_includes":[],"scope_excludes":[],"assumptions_disclosed":True,"geographic_level":"other","unresolved_points":[],"comparable_for_reconciliation":True}
            if not isinstance(rec,dict):
                incomplete.append({"cost_item_key":key,"reason":"missing_response_item"}); continue
            if str(rec.get("unit") or "")!=str(req.get("unit") or ""):
                incomplete.append({"cost_item_key":key,"reason":"unit_mismatch"}); continue
            structure=str(rec.get("pricing_structure") or "component_split").lower()
            comps=rec.get("components") or {}
            if not research_eligible or structure=="research_unavailable":
                incomplete.append({"cost_item_key":key,"reason":"research_unavailable" if research_status=="unavailable" else ("research_failed" if research_status=="failed" else "research_not_eligible")})
                continue
            cand=None
            if schema_version in {"1.2","1.3","1.4"} and structure=="provisional_estimate":
                ev=rec.get("provisional_evidence") or {}
                try: val=float(rec.get("provisional_unit_cost"))
                except Exception: val=None
                if val is not None and val>=0 and self._ai_cost_component_source_ok(ev):
                    cand={"provisional_unit_cost":val,"pricing_structure":"provisional_estimate","unit":req.get("unit"),"provisional_evidence":ev,"certainty":"estimated","display_color":"yellow"}
            elif schema_version in {"1.1","1.2","1.3","1.4"} and structure=="installed_all_in":
                ev=rec.get("installed_evidence") or {}
                try: val=float(rec.get("installed_unit_cost"))
                except Exception: val=None
                if val is not None and val>=0 and self._ai_cost_component_source_ok(ev):
                    cand={"installed_unit_cost":val,"pricing_structure":"installed_all_in","unit":req.get("unit"),"installed_evidence":ev,"certainty":"confirmed","display_color":"normal"}
            elif structure=="component_split":
                vals={}; valid=True
                for component in ("material","labor","equipment"):
                    try: num=float(rec.get(component)) if rec.get(component) is not None and str(rec.get(component)).strip()!="" else None
                    except Exception: num=None
                    if num is None or num<0 or not self._ai_cost_component_source_ok(comps.get(component)):
                        valid=False; break
                    vals[component]=num
                if valid:
                    cand={"material":vals["material"],"labor":vals["labor"],"equipment":vals["equipment"],"pricing_structure":"component_split","unit":req.get("unit"),"source_components":comps,"certainty":"confirmed","display_color":"normal"}
            if cand is None:
                incomplete.append({"cost_item_key":key,"reason":"unsupported_or_incomplete_price"}); continue
            quality=rec.get("candidate_quality") if isinstance(rec.get("candidate_quality"),dict) else {}
            if schema_version in {"1.3","1.4"}:
                allowed_source_types={"primary_market","government","industry","cost_guide","market","ai_generated_service","other"}
                allowed_scopes={"material_only","installed_all_in","component_split","other"}
                if self._ai_cost_norm_text(quality.get("source_type")) not in allowed_source_types or self._ai_cost_norm_text(quality.get("scope_definition")) not in allowed_scopes or "assumptions_disclosed" not in quality or "comparable_for_reconciliation" not in quality:
                    incomplete.append({"cost_item_key":key,"reason":"candidate_quality_missing_or_invalid"})
                    continue
                if structure=="provisional_estimate" and quality.get("assumptions_disclosed") is not True:
                    incomplete.append({"cost_item_key":key,"reason":"provisional_assumptions_not_disclosed"})
                    continue
                if schema_version=="1.4":
                    _basis_lists_ok=isinstance(quality.get("scope_includes"),list) and isinstance(quality.get("scope_excludes"),list) and isinstance(quality.get("unresolved_points"),list)
                    if not _basis_lists_ok:
                        if research_role=="reviewer":
                            quality=dict(quality); quality.setdefault("scope_includes",[]); quality.setdefault("scope_excludes",[]); quality.setdefault("unresolved_points",[]); quality["review_metadata_incomplete"]=True
                        else:
                            incomplete.append({"cost_item_key":key,"reason":"v1.4_price_basis_fields_missing"})
                            continue
            cand.update({"reviewer":reviewer,"source_json":Path(source_path).name,"completed_at":completed,"research_execution_status":research_status,"candidate_quality":quality})
            if schema_version in {"1.3","1.4"} and quality.get("comparable_for_reconciliation") is False:
                cand["not_comparable_for_reconciliation"]=True
            if self._ai_cost_scope_overlap_risk(key,rec,requested_keys):
                cand["scope_overlap_risk"]=True
            candidates[key]=cand
        packages={}
        pp=payload.get("equipment_packages") or {}
        if isinstance(pp,list):
            pp={str(x.get("package_key")):x for x in pp if isinstance(x,dict) and x.get("package_key")}
        for pkg in scope["equipment_packages"]:
            key=pkg["package_key"]; rec=pp.get(key) if isinstance(pp,dict) else None
            if isinstance(rec,dict) and research_role=="reviewer" and rec.get("price") is not None:
                rec=dict(rec); rec.setdefault("currency",rec.get("required_currency") or got_currency)
                rec.setdefault("pricing_mode","lump_sum"); rec.setdefault("cost",rec.get("price")); rec.setdefault("status","found")
                if not rec.get("source_url"): rec["source_url"]=rec.get("evidence_url")
            if not isinstance(rec,dict): continue
            if not research_eligible or str(rec.get("status") or "").lower()=="research_unavailable": continue
            if str(rec.get("currency") or "").upper()!=expected_currency: continue
            if str(rec.get("status") or "").lower()!="found" or not str(rec.get("source_url") or rec.get("source_reference") or "").strip(): continue
            mode=str(rec.get("pricing_mode") or "").lower(); rate=None; cost=None
            if schema_version in {"1.1","1.2","1.3","1.4"} and mode=="lump_sum":
                try: cost=float(rec.get("cost"))
                except Exception: cost=None
            elif schema_version in {"1.1","1.2","1.3","1.4"} and mode=="unit_rate_per_gfa" and str(rec.get("unit") or "")==f"{expected_currency}/m2_gfa":
                try: rate=float(rec.get("unit_cost")); cost=rate*float(scope.get("gross_floor_area_m2") or 0.0)
                except Exception: cost=None
            if cost is not None and cost>0:
                packages[key]={"package_key":key,"cost":cost,"unit_rate":rate,"currency":expected_currency,"pricing_mode":mode,"source":rec,"reviewer":reviewer,"source_json":Path(source_path).name,"completed_at":completed,"research_execution_status":research_status}
        return {"reviewer":reviewer,"research_role":research_role,"completed_at":completed,"source_json":Path(source_path).name,"schema_version":schema_version,"research_execution":execution,"research_execution_status":research_status,"research_eligible":research_eligible,"currency_validation":currency_validation,"unit_cost_candidates":candidates,"equipment_candidates":packages,"incomplete_items":incomplete,"research_sources":payload.get("research_sources") or [],"review_findings":payload.get("review_findings") or {},"recheck_findings":payload.get("recheck_findings") or {}}

    def _reconcile_ai_cost_candidates(self, sessions, scope):
        """Primary -> peer review -> ChatGPT re-check; reviewer prices never auto-adopt."""
        by_key={k:[] for k in [x["cost_item_key"] for x in scope["items"]]}
        for sess in sessions:
            for key,c in (sess.get("unit_cost_candidates") or {}).items():
                cc=dict(c); cc["research_role"]=sess.get("research_role") or "reviewer"
                by_key.setdefault(key,[]).append(cc)
        recheck_sessions=[x for x in sessions if x.get("research_role")=="primary_recheck" and x.get("research_execution_status") not in {"unavailable","failed"}]
        latest_recheck=max(recheck_sessions,key=lambda x:self._ai_cost_norm_text(x.get("completed_at"))) if recheck_sessions else None
        recheck_findings=(latest_recheck.get("recheck_findings") or {}) if latest_recheck else {}
        adopted={}; audit={}
        for key,cands in by_key.items():
            eligible=[c for c in cands if not c.get("scope_overlap_risk") and c.get("research_execution_status") not in {"unavailable","failed"}]
            rechecks=[c for c in eligible if c.get("research_role")=="primary_recheck"]
            guides=[c for c in eligible if c.get("research_role")=="primary_guide" or (self._ai_cost_norm_text(c.get("reviewer")).startswith("chatgpt") and c.get("research_role")!="primary_recheck")]
            reviewers=[c for c in eligible if c.get("research_role")=="reviewer"]
            chosen=None; basis="no_usable_research"; stage="unresolved"
            if rechecks:
                chosen=max(rechecks,key=lambda c:self._ai_cost_norm_text(c.get("completed_at"))); chosen=dict(chosen); basis="chatgpt_post_review_recheck"; stage="rechecked"
            elif latest_recheck is not None and key in recheck_findings:
                # A completed final re-check explicitly addressed this item but did
                # not return a defensible numeric candidate.  Do not fall back to an
                # older primary or reviewer number and hide that final uncertainty.
                finding=recheck_findings.get(key) or {}
                audit[key]={"status":"unresolved","verification_model":"primary_peer_review_chatgpt_recheck","verification_stage":"rechecked_unresolved","adoption_basis":"chatgpt_recheck_left_unresolved","candidate_count":len(cands),"recheck_decision":finding.get("decision"),"recheck_reason":finding.get("final_reason")}; continue
            elif guides:
                chosen=max(guides,key=lambda c:(self._ai_cost_evidence_rank(c,self._authoritative_project_cost_location()),self._ai_cost_norm_text(c.get("completed_at")))); chosen=dict(chosen); basis="chatgpt_primary_basis_pending_peer_recheck" if reviewers else "chatgpt_primary_basis"; stage="primary"
            elif reviewers:
                # Reviewer evidence is retained for the re-check packet but does NOT
                # become a cost input until ChatGPT independently verifies it.
                audit[key]={"status":"unresolved","verification_model":"primary_peer_review_chatgpt_recheck","verification_stage":"reviewer_gap_pending_recheck","adoption_basis":"reviewer_evidence_pending_chatgpt_recheck","candidate_count":len(cands),"reviewer_candidate_count":len(reviewers)}; continue
            if chosen is None:
                audit[key]={"status":"unresolved","verification_model":"primary_peer_review_chatgpt_recheck","verification_stage":stage,"adoption_basis":basis,"candidate_count":len(cands)}; continue
            chosen["pricing_status"]={"rechecked":"ai_post_review_rechecked_provisional","primary":"ai_primary_basis_provisional"}.get(stage,"ai_research_provisional")
            chosen["certainty"]="estimated"; chosen["display_color"]="yellow"; chosen["verification_stage"]=stage
            base=self._ai_cost_candidate_total(chosen); corroborating=[]; conflicts=[]
            for r in reviewers:
                rv=self._ai_cost_candidate_total(r)
                if base is None or rv is None: continue
                rel=abs(base-rv)/max(abs(base),abs(rv),1.0)
                if rel<=0.10: corroborating.append(r.get("reviewer"))
                else: conflicts.append({"reviewer":r.get("reviewer"),"rate":rv,"relative_difference":rel})
            chosen["review_corroboration_count"]=len(corroborating); chosen["review_conflict_count"]=len(conflicts)
            if chosen.get("pricing_structure")=="provisional_estimate":
                chosen["source_pricing_structure"]="provisional_estimate"; chosen["installed_unit_cost"]=float(chosen.get("provisional_unit_cost")); chosen["installed_evidence"]=chosen.get("provisional_evidence") or {}; chosen["pricing_structure"]="installed_all_in"
            adopted[key]=chosen
            audit[key]={"status":"provisional","verification_model":"primary_peer_review_chatgpt_recheck","verification_stage":stage,"adoption_basis":basis,"candidate_count":len(cands),"primary_candidate_count":len(guides),"recheck_candidate_count":len(rechecks),"reviewer_candidate_count":len(reviewers),"corroborating_reviewers":corroborating,"material_conflicts":conflicts,"chosen_reviewer":chosen.get("reviewer"),"chosen_rate":self._ai_cost_candidate_total(chosen)}
        return adopted,audit

    def _reconcile_ai_equipment_candidates(self, sessions, scope, expected_currency):
        """Equipment follows the same evidence loop; reviewer-only prices are not adopted."""
        by_key={k:[] for k in [x["package_key"] for x in scope["equipment_packages"]]}
        for sess in sessions:
            for key,c in (sess.get("equipment_candidates") or {}).items():
                cc=dict(c); cc["research_role"]=sess.get("research_role") or "reviewer"
                by_key.setdefault(key,[]).append(cc)
        recheck_sessions=[x for x in sessions if x.get("research_role")=="primary_recheck" and x.get("research_execution_status") not in {"unavailable","failed"}]
        latest_recheck=max(recheck_sessions,key=lambda x:self._ai_cost_norm_text(x.get("completed_at"))) if recheck_sessions else None
        recheck_findings=(latest_recheck.get("recheck_findings") or {}) if latest_recheck else {}
        adopted=[]
        for key,cands in by_key.items():
            if not cands: continue
            rechecks=[c for c in cands if c.get("research_role")=="primary_recheck"]
            primary=[c for c in cands if c.get("research_role")=="primary_guide" or (self._ai_cost_norm_text(c.get("reviewer")).startswith("chatgpt") and c.get("research_role")!="primary_recheck")]
            if rechecks: pool=rechecks; basis="chatgpt_post_review_recheck"
            elif latest_recheck is not None and key in recheck_findings: continue
            elif primary: pool=primary; basis="chatgpt_primary_basis"
            else: continue
            chosen=max(pool,key=lambda c:(self._ai_cost_norm_text(c.get("completed_at")),self._ai_cost_norm_text(c.get("reviewer"))))
            rec=dict(chosen); rec["certainty"]="estimated"; rec["display_color"]="yellow"; rec["verification_model"]="primary_peer_review_chatgpt_recheck"; rec["adoption_basis"]=basis
            if key in self.equipment_vars: self.equipment_vars[key]["cost"].set(format_input_number(rec["cost"]))
            adopted.append(rec)
        return adopted

    def _ai_cost_changelog_dir(self):
        self.refresh_project_from_context()
        base=Path(self.project_path).parent if self.project_path is not None else (self.root_dir/"projects")
        return base / "AI_Cost_Changelog"

    def _build_ai_cost_changelog(self, previous_adopted, previous_audit, new_adopted, new_audit, scope):
        """Diff the unit-cost adoption state before/after one AI-JSON import.

        Returns a list of row dicts (one per cost_item_key that exists in
        either snapshot) describing what changed: a brand-new price, a
        changed price/reviewer, a status change with the same price, or no
        change at all. Equipment packages are not included here -- they
        already have their own adopted-list structure and are comparatively
        rare to change mid-session; this can be extended the same way later
        if needed.
        """
        previous_adopted=previous_adopted or {}; previous_audit=previous_audit or {}
        new_adopted=new_adopted or {}; new_audit=new_audit or {}
        names={x["cost_item_key"]:x.get("item_name") or x["cost_item_key"] for x in (scope.get("items") or [])}
        keys=sorted(set(previous_adopted)|set(new_adopted)|set(previous_audit)|set(new_audit), key=lambda k: names.get(k,k))
        rows=[]
        for key in keys:
            before=previous_adopted.get(key); after=new_adopted.get(key)
            before_price=self._ai_cost_candidate_total(before) if before else None
            after_price=self._ai_cost_candidate_total(after) if after else None
            before_status=str((previous_audit.get(key) or {}).get("status") or ("provisional" if before else "unresolved"))
            after_status=str((new_audit.get(key) or {}).get("status") or ("provisional" if after else "unresolved"))
            before_reviewer=str(before.get("reviewer") or "") if before else ""
            after_reviewer=str(after.get("reviewer") or "") if after else ""
            if before is None and after is not None:
                change="new"
            elif before is not None and after is None:
                change="removed"
            elif before_price is not None and after_price is not None and abs(before_price-after_price) > max(abs(before_price),abs(after_price),1.0)*1e-6:
                change="price_changed"
            elif before_status != after_status or before_reviewer != after_reviewer:
                change="status_changed"
            else:
                change="unchanged"
            if change=="unchanged":
                continue
            rows.append({
                "cost_item_key":key,
                "item_name":names.get(key,key),
                "change":change,
                "before_price":before_price,
                "after_price":after_price,
                "before_status":before_status,
                "after_status":after_status,
                "before_reviewer":before_reviewer,
                "after_reviewer":after_reviewer,
            })
        return rows

    def _show_ai_cost_changelog(self, rows, session_meta=None):
        """Display, save and (re)load the unit-cost changelog produced by
        one or more AI-JSON import steps. Opened automatically at the end
        of import_ai_cost_json(); the Load button lets the user bring back
        a previously saved changelog file for reference at any time,
        independent of whether an import just ran."""
        win=tk.Toplevel(self)
        win.title(self._ui("AI概算単価 変更履歴","AI Approximate Cost Changelog"))
        win.geometry("1180x520")
        ja=self.i18n.language=="ja"
        change_labels_ja={"new":"新規確定","price_changed":"価格変更","status_changed":"状態変更","removed":"取消・不明化"}
        change_labels_en={"new":"New price","price_changed":"Price changed","status_changed":"Status changed","removed":"Removed / now unresolved"}
        change_labels=change_labels_ja if ja else change_labels_en
        note=self._ui(
            "この画面はJSON取込1回ごとの単価変更点だけを示します（変更が無い項目は表示されません）。保存すると同じ内容をあとから読込できます。",
            "This shows only the unit-cost items that changed on this import (unchanged items are omitted). Save to reload the same list later."
        )
        ttk.Label(win,text=note,justify="left",wraplength=1140).pack(fill="x",padx=10,pady=(10,4))

        cols=("item","change","before_price","after_price","before_status","after_status","before_reviewer","after_reviewer")
        headers_ja=("項目","変更種別","変更前 単価","変更後 単価","変更前 状態","変更後 状態","変更前 回答AI","変更後 回答AI")
        headers_en=("Item","Change","Before price","After price","Before status","After status","Before reviewer","After reviewer")
        headers=headers_ja if ja else headers_en
        tree=ttk.Treeview(win,columns=cols,show="headings",height=16)
        widths=(260,110,110,110,110,110,110,110)
        for c,h,w in zip(cols,headers,widths):
            tree.heading(c,text=h); tree.column(c,width=w,anchor="center" if c!="item" else "w")
        tree.pack(fill="both",expand=True,padx=10,pady=4)

        def _fmt_price(v):
            return "-" if v is None else f"{v:,.0f}"

        def _populate(rows_to_show):
            for iid in tree.get_children(): tree.delete(iid)
            for r in rows_to_show:
                tree.insert("","end",values=(
                    r.get("item_name",r.get("cost_item_key","")),
                    change_labels.get(r.get("change",""),r.get("change","")),
                    _fmt_price(r.get("before_price")), _fmt_price(r.get("after_price")),
                    r.get("before_status",""), r.get("after_status",""),
                    r.get("before_reviewer",""), r.get("after_reviewer",""),
                ))
            if not rows_to_show:
                tree.insert("","end",values=(self._ui("（変更なし）","(no changes)"),"","","","","","",""))

        _populate(rows)
        current={"rows":rows,"meta":session_meta or {}}

        def save_changelog():
            folder=self._ai_cost_changelog_dir()
            try: folder.mkdir(parents=True,exist_ok=True)
            except Exception as exc:
                messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language),parent=win); return
            stamp=datetime.now(timezone.utc).strftime("%y%m%d_%H%M")
            project_name=Path(self.project_path).stem if self.project_path else "Project"
            safe_name="".join(ch if ch not in '<>:"/\\|?*' else '_' for ch in project_name).strip() or "Project"
            base=f"{stamp}_AZRAS_AI_COST_CHANGELOG_{safe_name}"
            json_path=folder/f"{base}.json"
            if json_path.exists():
                seq=2
                while (folder/f"{base}_{seq}.json").exists(): seq+=1
                json_path=folder/f"{base}_{seq}.json"
            payload={
                "schema":"AZRAS_AI_COST_CHANGELOG_V1",
                "project_json":str(self.project_path) if self.project_path else None,
                "saved_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "session_meta":current["meta"],
                "rows":current["rows"],
            }
            try:
                with open(json_path,"w",encoding="utf-8") as f:
                    json.dump(payload,f,ensure_ascii=False,indent=2,default=str)
            except Exception as exc:
                messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language),parent=win); return
            messagebox.showinfo("Saved",
                (f"変更履歴を保存しました。\n\n{json_path}" if ja else f"Saved the changelog.\n\n{json_path}"),
                parent=win)

        def load_changelog():
            folder=self._ai_cost_changelog_dir()
            initialdir=str(folder) if folder.exists() else (str(Path(self.project_path).parent) if self.project_path else str(self.root_dir))
            path=filedialog.askopenfilename(
                parent=win,
                title=self._ui("保存済み変更履歴を開く","Open saved changelog"),
                initialdir=initialdir,
                filetypes=[("AZRAS AI cost changelog","*.json"),("JSON","*.json"),("All files","*.*")],
            )
            if not path: return
            try:
                with open(path,"r",encoding="utf-8-sig") as f:
                    payload=json.load(f)
                if not isinstance(payload,dict) or payload.get("schema")!="AZRAS_AI_COST_CHANGELOG_V1":
                    raise ValueError(self._ui("AZRAS AI変更履歴JSONではありません。","This is not an AZRAS AI cost changelog JSON."))
                loaded_rows=payload.get("rows") or []
                current["rows"]=loaded_rows; current["meta"]=payload.get("session_meta") or {}
                _populate(loaded_rows)
                saved_at=str(payload.get("saved_at") or "")
                status_var.set((f"読込: {Path(path).name}" + (f" / 保存日時: {saved_at}" if saved_at else "")) if ja
                               else (f"Loaded: {Path(path).name}" + (f" / Saved at: {saved_at}" if saved_at else "")))
            except Exception as exc:
                messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language),parent=win)

        btns=ttk.Frame(win); btns.pack(fill="x",padx=10,pady=(4,10))
        ttk.Button(btns,text=self._ui("変更履歴を保存","Save changelog"),command=save_changelog).pack(side="left")
        ttk.Button(btns,text=self._ui("変更履歴を読込","Load changelog"),command=load_changelog).pack(side="left",padx=(8,0))
        status_var=tk.StringVar(value=self._ui("保存先: Projectフォルダー / AI_Cost_Changelog","Save to: Project folder / AI_Cost_Changelog"))
        ttk.Label(btns,textvariable=status_var).pack(side="left",padx=(12,0))

    def _comparison_copy_price_block(self, action):
        """PATCH_043: stop price changes on a comparison copy, with the reason."""
        reason = comparison_copy_block_reason(self.project, action, self.i18n.language)
        if reason:
            messagebox.showwarning(self._ui("比較用コピー", "Comparison copy"), reason, parent=self)
            return True
        return False

    def import_ai_cost_json(self):
        if self._comparison_copy_price_block("module5_ai_cost_import"):
            return
        """Import one or more AI responses, validate location/currency, then reconcile deterministically in session memory only."""
        self.refresh_project_from_context()
        if self.project_path is None:
            messagebox.showwarning("AI Approximate Cost",self._ui("先にModule 0でProject JSONを選択してください。","Select a Project JSON in Module 0 first."),parent=self); return
        initial=self._ensure_ai_cost_round_layout()["responses"]
        try: initial.mkdir(parents=True,exist_ok=True)
        except Exception: pass
        paths=filedialog.askopenfilenames(title=self._ui("AI概算単価JSONを選択（複数可）","Select AI Approximate-Cost JSON(s)"),initialdir=str(initial),filetypes=[("AZRAS AI Approximate Cost JSON","*.json"),("JSON","*.json")])
        if not paths: return
        try:
            scope=self._ai_cost_request_scope(); expected_currency=str(self.currency.get() or "JPY").upper()
            loc=self.db["locations"][self.location.get()]
            previous_overlay=loc.get("_session_ai_unit_cost_overlay") if isinstance(loc,dict) else None
            import copy as _copy
            previous_adopted=_copy.deepcopy((previous_overlay or {}).get("unit_costs") or {})
            previous_audit=_copy.deepcopy((previous_overlay or {}).get("reconciliation_audit") or {})
            sessions=list((previous_overlay or {}).get("ai_candidate_sessions") or [])
            seen={(str(x.get("source_json")),str(x.get("reviewer")),str(x.get("completed_at"))) for x in sessions}
            imported=[]
            for path in paths:
                payload=json.loads(Path(path).read_text(encoding="utf-8-sig"))
                try:
                    _url_policy_report=enforce_public_evidence_urls(payload)
                except PublicEvidencePolicyError as _sec:
                    record_ai_import_audit(self._ai_cost_security_audit_dir(), "cost_response_rejected", path, payload,
                                           url_policy_report=_sec.report, extra_anomalies=["public_evidence_url_policy_rejection"])
                    raise ValueError(str(_sec))
                sess=self._parse_ai_cost_payload(payload,path,scope,expected_currency)
                sid=(sess.get("source_json"),sess.get("reviewer"),sess.get("completed_at"))
                if sid not in seen:
                    sessions.append(sess); seen.add(sid); imported.append(sess)
                    # PATCH_011: keep a per-project evidentiary copy of every
                    # imported AI cost-response JSON in R1/02_AI response,
                    # mirroring Module 1's takeoff-workflow record-keeping.
                    # A ChatGPT final re-check response (research_role
                    # "primary_recheck") is additionally copied into
                    # R1/04_Final determination, since that import is the
                    # one that becomes the formally adopted price basis.
                    self._copy_ai_cost_json_to_round_folder(path,"responses")
                    if str(sess.get("research_role") or "")=="primary_recheck":
                        self._copy_ai_cost_json_to_round_folder(path,"final")
                    _extra=[]
                    if str(sess.get("research_execution_status") or "") in {"unavailable","failed"}:
                        _extra.append("research_execution_"+str(sess.get("research_execution_status")))
                    record_ai_import_audit(self._ai_cost_security_audit_dir(), "cost_response_import", path, payload,
                                           url_policy_report=_url_policy_report, extra_anomalies=_extra,
                                           decision_summary={"research_role":sess.get("research_role"),"research_execution_status":sess.get("research_execution_status"),"incomplete_item_count":len(sess.get("incomplete_items") or [])})
            adopted,audit=self._reconcile_ai_cost_candidates(sessions,scope)
            adopted_packages=self._reconcile_ai_equipment_candidates(sessions,scope,expected_currency)
            reviewers=[]
            for x in sessions:
                r=str(x.get("reviewer") or "UnknownAI")
                if r not in reviewers: reviewers.append(r)
            researched=sum(1 for x in sessions if x.get("research_execution_status")=="completed")
            research_unavailable=sum(1 for x in sessions if x.get("research_execution_status") in {"unavailable","failed"})
            legacy_unknown=sum(1 for x in sessions if x.get("research_execution_status")=="legacy_unknown")
            latest_completed=max([str(x.get("completed_at") or "") for x in sessions] or [""])
            incomplete=[]
            for x in sessions: incomplete.extend(x.get("incomplete_items") or [])
            session={"schema":"AZRAS_AI_APPROX_COST_SESSION_V3","reviewers":reviewers,"source_jsons":[x.get("source_json") for x in sessions],"planning_region_reference":self.location.get(),"project_cost_location":self._authoritative_project_cost_location(),"currency":expected_currency,"completed_at":latest_completed,"imported_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"adopted_unit_costs":adopted,"reconciliation_audit":audit,"incomplete_items":incomplete,"adopted_equipment_packages":adopted_packages,"research_execution_summary":{"completed":researched,"unavailable_or_failed":research_unavailable,"legacy_unknown":legacy_unknown},"raw_response_not_persisted_by_azras":True}
            loc["_session_ai_unit_cost_overlay"]={
                "project_binding":{
                    "project_id":str((self.project or {}).get("project_id") or ""),
                    "project_name":str(((self.project or {}).get("common") or {}).get("project_name") or ""),
                },
                "unit_costs":adopted,"ai_candidate_sessions":sessions,"ai_sessions":[{"reviewer":x.get("reviewer"),"source_json":x.get("source_json"),"completed_at":x.get("completed_at")} for x in sessions],
                "unit_cost_dataset":{"region_key":self._authoritative_project_cost_location(),"representative_profile":self.location.get(),"data_date":latest_completed[:10] if latest_completed else None,"last_checked_date":datetime.now(timezone.utc).strftime("%Y-%m-%d"),"source_name":"AI Approximate Cost Research (primary basis + independent review)","source_reference":"; ".join(str(x.get("source_json")) for x in sessions),"source_type":"ai_web_research_user_supplied_json","status":"estimated","note_ja":"ChatGPT一次調査の価格根拠を出発点とし、他AIが再調査・反証・補完し、その新しい根拠をChatGPTが再確認する。多数決では価格を決めない。共通DBへ保存しない。"},
                "session_evidence":session,"reconciliation_audit":audit,
                # PATCH 469: equipment-package prices are part of the same session-only
                # AI Cost Provider overlay.  The construction-cost engine must consume
                # these directly rather than relying on Tk entry widgets as a data bus.
                "equipment_packages":adopted_packages,
            }
            self.ai_cost_session=session
            self.unit_cost_data_date.set(latest_completed[:10] if latest_completed else datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            self.unit_cost_source.set("AI Approximate Cost Research ("+", ".join(reviewers)+")")
            self.unit_cost_freshness.set(self._ui("一次根拠＋他AI再調査","Primary basis + independent AI review"))
            confirmed=sum(1 for x in audit.values() if x.get("status")=="confirmed"); estimated=sum(1 for x in audit.values() if x.get("status")=="provisional"); unresolved=sum(1 for x in audit.values() if x.get("status")=="unresolved")
            rechecked=sum(1 for x in audit.values() if x.get("verification_stage")=="rechecked")
            pending_recheck=sum(1 for x in audit.values() if x.get("verification_stage")=="reviewer_gap_pending_recheck")
            challenge_count=sum(1 for sess in sessions for f in (sess.get("review_findings") or {}).values() if isinstance(f,dict) and str(f.get("outcome") or "")=="challenges_primary_basis")
            gap_fill_findings=sum(1 for sess in sessions for f in (sess.get("review_findings") or {}).values() if isinstance(f,dict) and str(f.get("outcome") or "")=="fills_primary_gap")
            equipment_adopted=len(adopted_packages); equipment_requested=len(scope.get("equipment_packages") or [])
            self.ai_cost_session_status.set(self._ui(
                f"AI概算単価: {len(reviewers)}AI / Web調査完了 {researched} / 再確認済 {rechecked} / ChatGPT再確認待ち {pending_recheck} / 反証指摘 {challenge_count} / 不明補完候補 {gap_fill_findings} / 不明 {unresolved} / 設備 {equipment_adopted}/{equipment_requested} / DB保存なし",
                f"AI approximate prices: {len(reviewers)} AI / researched {researched} / rechecked {rechecked} / pending ChatGPT re-check {pending_recheck} / challenges {challenge_count} / gap-fill findings {gap_fill_findings} / unresolved {unresolved} / equipment {equipment_adopted}/{equipment_requested} / no DB persistence"))
            # PATCH_038: importing an AI price JSON changes Module 5 inputs.
            # Recalculate immediately so the table cannot remain on the pre-import
            # all-zero/unpriced result. Saving remains an explicit user action.
            _recalculated=self.calculate(silent_success=True)
            messagebox.showinfo("AI Approximate Cost",self._ui(
                f"AI調査結果を取り込みました。一次根拠と再調査結果を区別して保持します。\nAI: {len(reviewers)}\nWeb調査完了: {researched}\n調査不可・失敗: {research_unavailable}\n旧版状態不明: {legacy_unknown}\n確定: {confirmed}\n想定: {estimated}\n不明: {unresolved}\n建設費再計算: {'完了' if _recalculated else '要確認'}\n\n採用単価は現在のProject用入力として扱い、共通地域単価DBへは保存しません。Module 5の「保存」でProjectへ保持されます。",
                f"AI research results imported. Primary basis and independent reviews are retained separately.\nAI: {len(reviewers)}\nWeb research completed: {researched}\nUnavailable/failed: {research_unavailable}\nLegacy status unknown: {legacy_unknown}\nConfirmed: {confirmed}\nProvisional: {estimated}\nUnresolved: {unresolved}\nConstruction-cost recalculation: {'completed' if _recalculated else 'review required'}\n\nAdopted prices are Project-specific inputs and are not written to the shared regional-cost database. Use Module 5 Save to persist them with the Project."),parent=self)
            # PATCH_006: show what actually changed on THIS import step (new
            # prices, price changes, status changes) so the user does not have
            # to manually diff Module 5's totals before/after each of the
            # ②/④/⑥ AI-JSON import steps. The window also offers Save/Load so
            # a changelog can be kept and reviewed later.
            try:
                changelog_rows=self._build_ai_cost_changelog(previous_adopted,previous_audit,adopted,audit,scope)
                self._show_ai_cost_changelog(changelog_rows,session_meta={"reviewers":reviewers,"imported_at":session.get("imported_at")})
            except Exception as exc:
                messagebox.showerror("AI Approximate Cost",friendly_exception_text(exc,self.i18n.language),parent=self)
        except Exception as exc:
            messagebox.showerror("AI Approximate Cost",friendly_exception_text(exc,self.i18n.language),parent=self)

    def apply_location(self):
        loc=self.db["locations"][self.location.get()]
        _previous_currency=str(self.currency.get() or "JPY")
        _next_currency=str(loc.get("currency") or "JPY")
        self.currency.set(_next_currency)
        # PATCH 433: direct construction-condition monetary overrides are local-
        # currency inputs.  Never reinterpret a JPY amount as USD (or vice versa)
        # after the user changes regional profile.  Percentage adjustments remain.
        if _previous_currency != _next_currency:
            for _category in ("site","access","work_time","reserve"):
                for _row in self.condition_matrix.get(_category,[]):
                    if _row.get("amount_local_currency") is not None or _row.get("amount_jpy") is not None:
                        _row["amount_local_currency"]=None
                        _row["amount_currency"]=None
                        _row["amount_jpy"]=None
        self.cost_year.set(str(loc["year"]))
        self.material_index.set(str(loc["material_index"]))
        self.labor_index.set(str(loc["labor_index"]))
        self.productivity_index.set(str(loc["productivity_index"]))
        # PATCH 463: equipment package defaults in the common DB are JPY-only.
        # They may be shown in Japan, but must never be converted into foreign
        # local-currency construction prices. Foreign projects require a local
        # package price (or a local MEP detail price) entered in that currency.
        if self.equipment_vars:
            cur=str(loc.get("currency") or "JPY")
            for _key,_vars in self.equipment_vars.items():
                _base=float((self.db.get("equipment_packages",{}).get(_key,{}) or {}).get("default_cost_jpy") or 0.0)
                _vars["cost"].set(format_input_number(_base if cur=="JPY" else 0.0))
        _audit=evaluate_unit_cost_dataset_freshness(loc)
        self.unit_cost_data_date.set(str(_audit.get("data_date") or "-"))
        self.unit_cost_source.set(str(_audit.get("source_name") or self._ui("現地確認単価未登録","Verified local unit costs not registered")))
        _status=str(_audit.get("status") or "not_available")
        _labels_ja={
            "verified":"確認済み", "estimated":"推定値", "outdated":"古いデータ",
            "update_required":"更新確認が必要", "not_available":"現地単価未登録",
        }
        _labels_en={
            "verified":"Verified", "estimated":"Estimated", "outdated":"Outdated",
            "update_required":"Update check required", "not_available":"Local unit costs not registered",
        }
        _labels=_labels_ja if self.i18n.language=="ja" else _labels_en
        self.unit_cost_freshness.set(_labels.get(_status,_status))
        for _label in getattr(self,"_equipment_currency_labels",[]):
            _label.configure(text=cur)
        for _label in getattr(self,"_rc_currency_labels",[]):
            _label.configure(text=f"{cur}/m³")
        # PATCH 432: pre-calculation result headers must follow the selected
        # project currency too; PATCH 419 previously refreshed them only after
        # a calculation result existed.
        if hasattr(self,"tree"):
            _t=self.i18n.t
            for _col,_label in (("material",_t("material_cost")),("labor",_t("labor_cost")),("equipment",_t("equipment_cost")),("total",_t("line_total"))):
                self.tree.heading(_col,text=header_with_unit(_label,cur))

    def settings(self):
        return {
            "cost_year":float(self.cost_year.get()),
            "material_index":float(self.material_index.get()),
            "labor_index":float(self.labor_index.get()),
            "productivity_index":float(self.productivity_index.get()),
            "site_factor":1.0+float(self._selected_condition_row("site").get("rate_percent",0.0) or 0.0)/100.0,
            "access_factor":1.0+float(self._selected_condition_row("access").get("rate_percent",0.0) or 0.0)/100.0,
            "work_time_factor":1.0+float(self._selected_condition_row("work_time").get("rate_percent",0.0) or 0.0)/100.0,
            "overhead_rate":float(self.rates["overhead_percent"].get()),
            "contingency_rate":float(self.rates["contingency_percent"].get()),
            "cost_provider_mode":str(self.cost_provider_mode.get() or "approximate"),
            "design_rate":float(self.rates["design_supervision_percent"].get()),
            "tax_rate":float(self.rates["tax_percent"].get()),
            "use_common_2004_price_basis":bool(self.use_common_2004_price_basis.get()),
            "common_2004_to_target_cost_factor":float(self.common_2004_to_target_cost_factor.get()),
            "common_2004_market_calibration_factor":float(self.common_2004_market_calibration_factor.get()),
            "excavated_soil_stockpile_mode":str(self.excavated_soil_stockpile_mode.get() or "no_stockpile"),
            "rc_foundation_unit_price_overrides":{
                k:parse_number(v.get()) for k,v in self.rc_foundation_unit_price_vars.items()
            }
        }

    def equipment_selection(self):
        return {k:{"include":v["include"].get(),"cost":parse_number(v["cost"].get()),
                   "cost_basis":"ui_local_currency"}
                for k,v in self.equipment_vars.items()}

    def calculate(self, *, silent_success=False):
        self.refresh_project_from_context()
        if self.project is None:
            messagebox.showwarning("Warning",self.i18n.t("module1_required_m5"));return
        try:
            require_current_module_output(self.project, "module1", "Module 1")
            module1_fingerprint = module1_cost_dependency_fingerprint(self.project)
            self.result=calculate_construction_cost(
                self.project,self.db,self.location.get(),self.settings(),self.equipment_selection())
            self.result["upstream_module1_fingerprint"] = module1_fingerprint
            _integrity=self.result.get("quantity_to_cost_line_integrity_audit") or {}
            if _integrity.get("status")=="fail":
                raise ValueError(
                    "Module 1 → Module 5 quantity/cost-line integrity failed: "
                    + ", ".join(str(x) for x in (_integrity.get("missing_cost_line_keys") or []))
                )
            if isinstance(self.ai_cost_session,dict):
                self.result["ai_approximate_cost_provider_evidence"]=json.loads(json.dumps(self.ai_cost_session,ensure_ascii=False))
            self.apply_custom_condition_adjustments()
            self.result["equipment_detail_mode"] = "drawing_trade_breakdown"
            self.result["equipment_trade_breakdown"] = self.build_equipment_trade_breakdown()
            _cov=(self.result.get("regional_unit_cost_coverage_audit") or {})
            if _cov:
                self.regional_cost_coverage.set(self._regional_cost_coverage_text(_cov))
            _mcal=(self.result.get("market_calibration_2026") or {})
            if _mcal:
                _unp=_mcal.get("known_unpriced_foundation_items") or []
                self.market_calibration_summary.set(
                    (f"2026市場校正: 木造係数 {_mcal.get('wood_factor_applied_to_fallback_components',0):.3f} / RC係数 {_mcal.get('rc_factor_applied_to_fallback_components',0):.3f} / 未単価基礎工種 {len(_unp)}"
                     if self.i18n.language=="ja" else
                     f"2026 market calibration: timber factor {_mcal.get('wood_factor_applied_to_fallback_components',0):.3f} / RC factor {_mcal.get('rc_factor_applied_to_fallback_components',0):.3f} / unpriced foundation items {len(_unp)}")
                )
            _diag=(self.result.get("construction_cost_validity_diagnostic") or {})
            if _diag:
                _gap=_diag.get("gap_vs_benchmark_percent")
                _bm=_diag.get("benchmark_per_m2",_diag.get("benchmark_jpy_per_m2"))
                _est=_diag.get("software_estimate_ex_tax_per_m2",_diag.get("software_estimate_ex_tax_jpy_per_m2"))
                _cur=str(_diag.get("currency") or self.result.get("currency") or self.currency.get() or "JPY")
                if _bm is None:
                    self.market_validity_summary.set(
                        (f"建設費妥当性: {_est:,.0f} {_cur}/㎡ / 外部ベンチマークなし"
                         if self.i18n.language=="ja" else
                         f"Construction-cost validity: {_cur} {_est:,.0f}/m² / no applicable external benchmark")
                    )
                else:
                    self.market_validity_summary.set(
                        (f"建設費妥当性: {_est:,.0f} {_cur}/㎡ / 基準 {_bm:,.0f} {_cur}/㎡ / 差 {_gap:+.1f}%"
                         if self.i18n.language=="ja" else
                         f"Construction-cost validity: {_cur} {_est:,.0f}/m² / benchmark {_cur} {_bm:,.0f}/m² / gap {_gap:+.1f}%")
                    )
            self.show_result()
            if not silent_success:
                messagebox.showinfo("OK",self.i18n.t("cost_complete"))
            return True
        except Exception as exc:
            messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language))
            return False

    def _cost_item_display_name(self,key):
        lang="ja" if self.i18n.language=="ja" else "en"
        item=self.db.get("base_unit_costs_jpy",{}).get(key,{})
        if key!="dimension_lumber":
            return item.get(lang,key)
        common=(self.project or {}).get("common",{}) or {}
        method=str(common.get("construction_method_id") or "")
        if method=="azras":
            return "AZRAS更新木造・一般木材" if lang=="ja" else "AZRAS renewable timber/infill"
        return "2×6構造木材・一般木材" if lang=="ja" else "2x6 structural/general lumber"

    def _cost_item_canonical_name_en(self,key):
        """English-canonical cost item name for AI exchange; independent of UI language."""
        item=self.db.get("base_unit_costs_jpy",{}).get(key,{})
        if key!="dimension_lumber":
            return str(item.get("en") or key)
        common=(self.project or {}).get("common",{}) or {}
        method=str(common.get("construction_method_id") or "")
        if method=="azras":
            return "AZRAS renewable timber/infill"
        return "2x6 structural/general lumber"

    def _quantity_item_display_name(self, value):
        """Bilingual presentation for Module 1 quantity/audit labels.

        Project JSON remains canonical/mixed-source data.  This function is only
        a display adapter so Japanese and English UI do not leak the opposite
        language into the construction-cost table.
        """
        text=str(value or "").strip()
        from core.item_translations import item_translation_table
        # PATCH_005: this dict used to be maintained here as a large local
        # literal, duplicating module1/app.py's own separate translation
        # table. Both are now consolidated into lang/item_names_ja.json,
        # loaded via core.item_translations so a translation added there is
        # immediately available to every module, not just whichever one a
        # patch happened to touch. module5-specific overrides/aliases that
        # are not appropriate to share (none currently) would go in
        # `extra` below.
        pairs=item_translation_table("ja")
        if self.i18n.language=="ja":
            if text in pairs: return pairs[text]
            out=text
            for en,ja in sorted(pairs.items(),key=lambda x:len(x[0]),reverse=True): out=out.replace(en,ja)
            return out
        # English: normalize known legacy mixed labels before reverse translation.
        english_aliases={
            "AZRAS 2×6外壁正味 area":"AZRAS 2×6 exterior-wall net area",
            "AZRAS屋根水平投影 area":"AZRAS roof horizontal projection area",
            "AZRAS ceiling gypsum board13mm":"AZRAS ceiling gypsum board 13 mm",
        }
        if text in english_aliases: return english_aliases[text]
        rev={ja:en for en,ja in pairs.items()}
        if text in rev: return rev[text]
        out=text
        for ja,en in sorted(rev.items(),key=lambda x:len(x[0]),reverse=True): out=out.replace(ja,en)
        fragments=[("内部間仕切","internal partition"),("外壁","exterior wall"),("屋根","roof"),("床","floor"),("天井","ceiling"),("基礎","foundation"),("断熱材","insulation"),("正味面積","net area"),("適用面積","applicable area"),("部材長","member length"),("中心線長","centerline length"),("暫定一般仕様","provisional general specification"),("コンクリート","concrete"),("石膏ボード","gypsum board"),("勾配","pitch"),("面積","area"),("長さ","length")]
        for ja,en in fragments: out=out.replace(ja,en)
        return out

    def show_result(self):
        for tr in (self.tree,self.summary_tree):
            for iid in tr.get_children():tr.delete(iid)
        lang="ja" if self.i18n.language=="ja" else "en"
        currency=self.result["currency"]

        # PATCH 419: headings must follow the *calculation result* currency,
        # not the JPY value that happened to exist when the widget was built.
        _t=self.i18n.t
        for _col,_label in (
            ("material",_t("material_cost")),
            ("labor",_t("labor_cost")),
            ("equipment",_t("equipment_cost")),
            ("total",_t("line_total")),
        ):
            self.tree.heading(_col,text=header_with_unit(_label,currency))

        _display_no=0
        for row in self.result["cost_lines"]:
            item=self.db["base_unit_costs_jpy"][row["cost_item_key"]]
            _ps=str(row.get("pricing_display_status") or "priced").lower()
            _unpriced=(_ps=="unpriced")
            _estimated=(_ps=="estimated_price")
            _price_label=(
                ("不明・要確認" if lang=="ja" else "Unknown / review") if _unpriced
                else (("想定・暫定単価" if lang=="ja" else "Estimated / provisional") if _estimated
                      else ("確定・根拠単価" if lang=="ja" else "Confirmed / evidenced"))
            )
            _na=("未単価" if lang=="ja" else "Unpriced")
            _display_no+=1
            _all_in=(str(row.get("pricing_structure") or "").lower()=="installed_all_in")
            _component_na=("—" if _all_in and not _unpriced else None)
            self.tree.insert("","end",values=(
                _display_no,item[lang],format_number(row["quantity"],row["unit"]),row["unit"],_price_label,
                _na if _unpriced else (_component_na if _all_in else format_number(row["material_cost"],currency)),
                _na if _unpriced else (_component_na if _all_in else format_number(row["labor_cost"],currency)),
                _na if _unpriced else (_component_na if _all_in else format_number(row["equipment_cost"],currency)),
                _na if _unpriced else format_number(row["line_total_after_conditions"],currency)
            ), tags=(("unpriced",) if _unpriced else (("estimated_price",) if _estimated else ())))

        # PATCH 435: principal scopes that are blocked/missing must remain
        # visible even though they are intentionally absent from monetary lines.
        _scope_audit=self.result.get("cost_scope_completeness_audit") or {}
        _scope_names={
            "foundation_preparation_group":("基礎土工・地業","Foundation earthwork / groundwork"),
            "structural_steel":("構造用鉄骨","Structural steel"),
            "concrete":("コンクリート","Concrete"),
            "reinforcing_steel":("鉄筋","Reinforcing steel"),
            "formwork":("型枠","Formwork"),
            "dimension_lumber":("構造木材","Structural timber"),
        }
        _existing={str(x.get("cost_item_key")) for x in self.result.get("cost_lines",[])}
        for _a in _scope_audit.get("items",[]) or []:
            _key=str(_a.get("cost_item_key") or "")
            _status=str(_a.get("status") or "")
            if _key in _existing and _status in {"priced","unpriced"}:
                continue
            _dbitem=(self.db.get("base_unit_costs_jpy",{}) or {}).get(_key,{})
            _nm=(_scope_names.get(_key) or (_dbitem.get("ja",_key),_dbitem.get("en",_key)))[0 if lang=="ja" else 1]
            _labels={
                "blocked":("保留・積算対象外","Blocked / held"),
                "missing_quantity":("数量未確定","Missing quantity"),
                "missing_unit_cost_definition":("積算行未生成","Cost line missing"),
                "unpriced":("未単価","Unpriced"),
            }
            _pl=(_labels.get(_status) or (_status,_status))[0 if lang=="ja" else 1]
            _qty=_a.get("quantity")
            _unit=str(_a.get("unit") or "")
            _qtxt="" if _qty in (None,"") else format_number(_qty,_unit or None)
            _display_no+=1
            _audit_tag=("unpriced",) if _status in {"blocked","missing_quantity","missing_unit_cost_definition","unpriced"} else ()
            self.tree.insert("","end",values=(_display_no,_nm,_qtxt,_unit,_pl,"—","—","—","—"), tags=_audit_tag)

        # PATCH 437: show Module 1 physical quantities that were previously
        # invisible in Module 5.  Parent-package detail is visible but never
        # added twice; genuinely unmapped quantities remain numeric + Unpriced.
        _coverage=self.result.get("quantity_cost_coverage_audit") or {}
        _coverage_labels={
            "unpriced_unmapped":("未単価・個別単価未登録","Unpriced / no individual unit-cost mapping"),
            "supporting_evidence":("積算根拠・補助数量","Supporting / intermediate quantity"),
            "unpriced":("未単価","Unpriced"),
            "blocked":("保留・積算対象外","Blocked / held"),
            "blocked_by_parent":("親工種が保留","Parent scope blocked"),
            "included_in_parent":("親工種に包含（重複計上なし）","Included in parent scope (no double count)"),
            "missing_quantity":("数量未確定","Missing quantity"),
        }
        _skip_parent={"structural_steel","reinforcing_steel"}
        for _r in _coverage.get("rows",[]) or []:
            _st=str(_r.get("status") or "")
            if _st in {"audit_only","included_in_cost_line","supporting_evidence"}:
                continue
            _parent=str(_r.get("parent_cost_item_key") or "")
            # Individual steel/rebar details are summarized by the principal
            # blocked scope above; do not flood the main cost table.
            if _parent in _skip_parent and _st in {"included_in_parent","blocked_by_parent","unpriced"}:
                continue
            _qty=_r.get("quantity")
            _unit=str(_r.get("unit") or "")
            # specification-only unresolved rows stay in Module 1; Module 5
            # shows them only when they represent a monetary gap.
            if _st=="missing_quantity" and not bool(_r.get("monetary_gap")):
                continue
            _label=(_coverage_labels.get(_st) or (_st,_st))[0 if lang=="ja" else 1]
            _qtxt="" if _qty in (None,"") else format_number(_qty,_unit or None)
            _display_no+=1
            _coverage_tag=("unpriced",) if _st in {"unpriced_unmapped","unpriced","blocked","blocked_by_parent","missing_quantity"} and bool(_r.get("monetary_gap")) else ()
            self.tree.insert("","end",values=(_display_no,self._quantity_item_display_name(_r.get("canonical_item") or _r.get("item") or ""),_qtxt,_unit,_label,"—","—","—","—"), tags=_coverage_tag)

        s=self.result["summary"];t=self.i18n.t
        _unpriced_lines=list(self.result.get("unpriced_cost_lines") or [])
        _scope_audit=self.result.get("cost_scope_completeness_audit") or {}
        _scope_incomplete=not bool(_scope_audit.get("is_complete",True))
        _partial_total=bool(self.result.get("construction_cost_is_partial")) or (bool(self.result.get("priced_total_excludes_unpriced_items")) and bool(_unpriced_lines))
        if _partial_total:
            _missing=int(_scope_audit.get("blocking_or_missing_scope_count") or 0)
            _scope_unpriced=int(_scope_audit.get("unpriced_scope_count") or 0)
            _coverage=self.result.get("quantity_cost_coverage_audit") or {}
            _coverage_gap=int(_coverage.get("monetary_gap_count") or 0)
            _gap_items=list(_coverage.get("monetary_gap_items") or [])
            _gap_names=[self._quantity_item_display_name(x.get("canonical_item") or x.get("item") or x.get("scope_id") or "") for x in _gap_items if str(x.get("item") or x.get("scope_id") or "").strip()]
            if lang=="ja":
                _gap_detail=(" 残存項目: " + " / ".join(_gap_names[:8])) if _gap_names else ""
                self.total_completeness_notice.set(
                    f"【不完全・暫定総額】主要工種の未確定/保留 {_missing}件、主要工種未単価 {_scope_unpriced}件、"
                    f"その他の数量→金額未接続 {_coverage_gap}件があります。"
                    f"これらは総額・㎡単価に完全反映されていません。{_gap_detail}"
                )
            else:
                _gap_detail=(" Remaining: " + "; ".join(_gap_names[:8])) if _gap_names else ""
                self.total_completeness_notice.set(
                    f"[INCOMPLETE / PROVISIONAL TOTAL] {_missing} principal scope(s) are missing/blocked, {_scope_unpriced} principal scope(s) are unpriced, "
                    f"and {_coverage_gap} additional cost scope(s) are not yet monetized. "
                    f"The total and cost/m² do not represent a complete construction cost.{_gap_detail}"
                )
        else:
            self.total_completeness_notice.set(
                "主要工種を含め、表示工種は単価反映済みです。" if lang=="ja" else "Principal construction scopes are complete and displayed cost items are priced."
            )
        additional_condition_label = "追加施工条件補正" if self.i18n.language=="ja" else "Additional Construction-condition Adjustment"
        _partial_suffix = ("（未単価除外・暫定）" if lang=="ja" else " (unpriced items excluded; provisional)") if _partial_total else ""
        # PATCH 485: row ① is the direct-cost total. Rows ②-④ are only the
        # component-split portion already INCLUDED in ①; all-in rates have no
        # invented material/labor/plant split.
        _split_material=_split_labor=_split_equipment=0.0
        for _r in self.result.get("cost_lines",[]) or []:
            if str(_r.get("pricing_display_status") or "").lower()=="unpriced":continue
            if str(_r.get("pricing_structure") or "").lower()=="installed_all_in":continue
            _before=float(_r.get("line_total_before_conditions") or 0.0);_after=float(_r.get("line_total_after_conditions") or 0.0)
            _factor=(_after/_before) if abs(_before)>1e-12 else 1.0
            _split_material+=float(_r.get("material_cost") or 0.0)*_factor
            _split_labor+=float(_r.get("labor_cost") or 0.0)*_factor
            _split_equipment+=float(_r.get("equipment_cost") or 0.0)*_factor
        rows=[
            ("①",self._ui("直接工事費（一式＋分離単価）","Direct Construction Cost (all-in + split rates)"),s.get("adjusted_direct_cost",0.0),currency,"direct_total",False),
            ("②",self._ui("　材料内訳（①に含む・分離分のみ）","  Material breakdown (included in ①; split rates only)"),_split_material,currency,"direct_material_breakdown",True),
            ("③",self._ui("　労務内訳（①に含む・分離分のみ）","  Labor breakdown (included in ①; split rates only)"),_split_labor,currency,"direct_labor_breakdown",True),
            ("④",self._ui("　機械・仮設内訳（①に含む・分離分のみ）","  Plant/temporary breakdown (included in ①; split rates only)"),_split_equipment,currency,"direct_equipment_breakdown",True),
            ("⑤",self._ui("　施工条件補正（①に反映済み）","  Site-condition adjustment (already reflected in ①)"),s["condition_adjustment"],currency,"condition",False),
            ("⑥",additional_condition_label,s.get("additional_condition_adjustment",0.0),currency,"additional_condition",False),
            ("⑦",t("additional_equipment_cost"),s["additional_equipment_cost"],currency,"additional_equipment",False),
            ("⑧",t("overhead_cost"),s["overhead_cost"],currency,"overhead",False),
            ("⑨",t("contingency_cost"),s["contingency_cost"],currency,"contingency",False),
            ("⑩",t("design_cost"),s["design_supervision_cost"],currency,"design",False),
            ("⑪",t("subtotal_before_tax")+_partial_suffix,s["subtotal_before_tax"],currency,"subtotal",False),
            ("⑫",t("tax_amount")+_partial_suffix,s["tax_amount"],currency,"tax",False),
            ("⑬",t("total_construction_cost")+_partial_suffix,s["total_construction_cost"],currency,"total",False),
            ("⑭",t("cost_per_m2")+_partial_suffix,s["cost_per_m2"],currency+"/m²","per_m2",False),
            ("⑮",t("construction_duration"),s["estimated_construction_duration_months"],t("months"),"duration",False)
        ]
        for no,item,value,unit,key,is_breakdown in rows:
            basis,source=self.summary_explanation(key)
            _display_value=("—" if is_breakdown and abs(float(value or 0.0))<1e-12 else format_number(value,unit,1 if unit==t("months") else None))
            self.summary_tree.insert("","end",values=(no,item,_display_value,unit,basis,source))

    def _condition_translation_map(self):
        return {
            "平坦・障害物なし・十分な施工ヤード":"Level site, no obstacles, adequate working space",
            "一般的な市街地条件":"Typical urban site conditions",
            "狭小・高低差・障害物あり":"Confined site / level differences / obstacles",
            "大型車搬入可能":"Large-vehicle access available",
            "大型車搬入制限あり":"Large-vehicle access restricted",
            "小運搬・人力搬入が多い":"Frequent short-haul / manual handling",
            "昼間施工":"Daytime work",
            "時間制限あり":"Restricted working hours",
            "夜間・休日施工を含む":"Includes night / holiday work",
            "標準条件。補正なし。":"Standard condition; no adjustment.",
            "施工ヤード・周辺制約を考慮した企画比較用補正。":"Planning adjustment for working-space and surrounding constraints.",
            "小運搬・仮設・施工能率低下を考慮した企画比較用補正。":"Planning adjustment for short-haul, temporary works and lower productivity.",
            "標準搬入条件。補正なし。":"Standard access; no adjustment.",
            "車両制限・小運搬増加を考慮した企画比較用補正。":"Planning adjustment for vehicle restrictions and added short-haul handling.",
            "小運搬・人力搬入の増加を考慮した企画比較用補正。":"Planning adjustment for increased short-haul and manual handling.",
            "標準作業時間。補正なし。":"Standard working hours; no adjustment.",
            "作業可能時間の制限による能率低下を考慮。":"Accounts for lower productivity due to restricted working hours.",
            "割増賃金・照明・管理費増加を考慮。":"Accounts for premium wages, lighting and added management cost.",
        }

    def _canonical_condition_text(self, value):
        """Keep standard condition strings language-neutral in saved state.

        PATCH 433: PATCH 431 localized the editor fields, but saving the English
        display text could overwrite the canonical Japanese standard string.
        Reverse only exact built-in translations; genuine user-entered text is
        preserved verbatim.
        """
        text=str(value or "")
        reverse={v:k for k,v in self._condition_translation_map().items()}
        return reverse.get(text,text)

    def _localized_condition_text(self, value):
        text=self._canonical_condition_text(value)
        if self.i18n.language == "ja":
            return text
        return self._condition_translation_map().get(text,text)

    def edit_custom_conditions(self):
        dialog=tk.Toplevel(self)
        dialog.title(self._ui("施工条件補正追加","Add Construction-Condition Adjustments"))
        fit_window_to_screen(dialog,1420,760,820,520)
        dialog.transient(self)

        categories=[
            ("site",self._ui("敷地条件","Site Conditions")),
            ("access",self._ui("搬入条件","Access Conditions")),
            ("work_time",self._ui("作業時間条件","Work-Time Conditions")),
            ("reserve",self._ui("予備条件","Contingency Conditions")),
        ]
        working=json.loads(json.dumps(self.condition_matrix,ensure_ascii=False))
        widgets={}

        header=ttk.Frame(dialog)
        header.pack(fill="x",padx=10,pady=(10,4))
        ttk.Label(header,text=self._ui("各区分5行。使用する条件をチェックし、補正率と決定根拠を確認・編集してください。","Five rows per category. Select applicable conditions and review/edit the adjustment and basis."),foreground="#8b0000").pack(side="left")
        ttk.Label(header,text=self._ui("敷地・搬入・作業時間は各1件、予備条件は複数選択可能です。","Select one each for site, access and work-time; multiple contingency conditions are allowed."),foreground="#555555").pack(side="left",padx=16)

        scroll_host=ttk.Frame(dialog);scroll_host.pack(fill="both",expand=True,padx=10,pady=4)
        scroll_host.rowconfigure(0,weight=1);scroll_host.columnconfigure(0,weight=1)
        canvas=tk.Canvas(scroll_host,highlightthickness=0)
        scroll=ttk.Scrollbar(scroll_host,orient="vertical",command=canvas.yview)
        xscroll=ttk.Scrollbar(scroll_host,orient="horizontal",command=canvas.xview)
        inner=ttk.Frame(canvas)
        inner.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=inner,anchor="nw")
        canvas.configure(yscrollcommand=scroll.set,xscrollcommand=xscroll.set)
        canvas.grid(row=0,column=0,sticky="nsew");scroll.grid(row=0,column=1,sticky="ns");xscroll.grid(row=1,column=0,sticky="ew")

        def choose_one(category,index):
            if category=="reserve":
                return
            for i,row in enumerate(working[category]):
                row["checked"]=(i==index)
                widgets[(category,i,"checked")].set(i==index)

        for group_index,(category,title) in enumerate(categories):
            frame=ttk.LabelFrame(inner,text=title)
            frame.grid(row=group_index,column=0,sticky="ew",padx=5,pady=7)
            inner.columnconfigure(0,weight=1)
            heads=(("使用","No.","条件名","補正率 %","金額決定根拠・出典") if self.i18n.language=="ja" else ("Use","No.","Condition","Adjustment %","Decision basis / source"))
            widths=(6,5,34,12,86)
            for c,(h,w) in enumerate(zip(heads,widths)):
                ttk.Label(frame,text=h).grid(row=0,column=c,padx=4,pady=4,sticky="w")
                if c in (2,4):frame.columnconfigure(c,weight=1)
            for i in range(5):
                row=working[category][i]
                checked=tk.BooleanVar(value=bool(row.get("checked")))
                name=tk.StringVar(value=self._localized_condition_text(row.get("condition",'')))
                rate=tk.StringVar(value=str(row.get("rate_percent",0.0)))
                basis=tk.StringVar(value=self._localized_condition_text(row.get("basis",'')))
                widgets[(category,i,"checked")]=checked
                widgets[(category,i,"condition")]=name
                widgets[(category,i,"rate")]=rate
                widgets[(category,i,"basis")]=basis
                cb=ttk.Checkbutton(frame,variable=checked,command=lambda cat=category,idx=i:choose_one(cat,idx) if widgets[(cat,idx,"checked")].get() else None)
                cb.grid(row=i+1,column=0,padx=4,pady=3)
                ttk.Label(frame,text=str(i+1)).grid(row=i+1,column=1,padx=4,pady=3)
                tk.Entry(frame,textvariable=name,width=36,bg=INPUT_BG).grid(row=i+1,column=2,padx=4,pady=3,sticky="ew")
                tk.Entry(frame,textvariable=rate,width=12,bg=INPUT_BG,justify="right").grid(row=i+1,column=3,padx=4,pady=3)
                tk.Entry(frame,textvariable=basis,width=88,bg=INPUT_BG).grid(row=i+1,column=4,padx=4,pady=3,sticky="ew")

        footer=ttk.Frame(dialog)
        footer.pack(fill="x",padx=10,pady=8)
        def save_and_close():
            for category,_title in categories:
                for i,row in enumerate(working[category]):
                    row["checked"]=bool(widgets[(category,i,"checked")].get())
                    row["condition"]=self._canonical_condition_text(widgets[(category,i,"condition")].get().strip())
                    try:row["rate_percent"]=float(widgets[(category,i,"rate")].get().replace(",","" ) or 0.0)
                    except ValueError:
                        messagebox.showerror(self._ui("入力エラー","Input Error"),self._ui(f"{_title} {i+1}行目の補正率を数値で入力してください。",f"Enter a numeric adjustment for row {i+1} of {_title}."),parent=dialog);return
                    row["basis"]=self._canonical_condition_text(widgets[(category,i,"basis")].get().strip())
            for category in ("site","access","work_time"):
                if not any(r.get("checked") for r in working[category]):
                    working[category][0]["checked"]=True
            self.condition_matrix=working
            self._sync_legacy_condition_vars()
            self.custom_conditions=[]
            for row in self.condition_matrix.get("reserve",[]):
                if row.get("checked") and (row.get("condition") or row.get("basis") or row.get("rate_percent") is not None):
                    self.custom_conditions.append({"condition":row.get("condition",""),"rate_percent":row.get("rate_percent",0.0),"basis":row.get("basis","")})
            dialog.destroy()
        ttk.Button(footer,text=self._ui("保存して閉じる","Save and Close"),style="Primary.TButton",command=save_and_close).pack(side="right",padx=5)
        ttk.Button(footer,text=self._ui("キャンセル","Cancel"),command=dialog.destroy).pack(side="right",padx=5)

    def apply_custom_condition_adjustments(self):
        if not self.result:
            return
        summary=self.result.get("summary",{})
        base=float(summary.get("subtotal_before_tax",0.0) or 0.0)
        rate=sum(float(x.get("rate_percent",0.0) or 0.0) for x in self.custom_conditions)/100.0
        amount=base*rate
        summary["additional_condition_adjustment"]=amount
        summary["condition_adjustment"]=float(summary.get("condition_adjustment",0.0) or 0.0)+amount
        tax_rate=float(self.rates["tax_percent"].get())/100.0
        summary["subtotal_before_tax"]=base+amount
        summary["tax_amount"]=summary["subtotal_before_tax"]*tax_rate
        summary["total_construction_cost"]=summary["subtotal_before_tax"]+summary["tax_amount"]
        area=float(self.project.get("building",{}).get("total_floor_area_m2",0.0) or 0.0)
        if area>0:summary["cost_per_m2"]=summary["total_construction_cost"]/area
        self.result["custom_condition_adjustments"]=list(self.custom_conditions)

    def build_equipment_trade_breakdown(self):
        labels={
            "hvac":"HVAC work","electrical":"Electrical work","plumbing":"Plumbing and sanitary work",
            "kitchen":"Kitchen equipment work","bathroom":"Bathroom / unit-bath work","unit_bath":"Unit-bath work","other":"Other equipment work"
        }
        result=[]
        # PATCH 405: display the monetary owner actually used by the engine, not
        # merely the current checkbox state. This keeps the detail statement
        # consistent when an approved MEP detail scope replaces a package.
        used_packages=(self.result or {}).get("equipment_packages") or []
        if used_packages:
            for pkg in used_packages:
                key=str(pkg.get("package_key") or "")
                result.append({
                    "trade":labels.get(key,key),
                    "source":"Module 5 package price (package monetary owner)",
                    "amount":float(pkg.get("cost") or 0.0),
                })
        elif not ((self.result or {}).get("mep_detail_cost_bridge") or {}).get("replaced_package_scopes"):
            # Compatibility for pre-PATCH-405 results.
            for key,data in self.equipment_vars.items():
                if data["include"].get():
                    result.append({"trade":labels.get(key,key),"source":"drawings / equipment legend / simplified lump-sum price", "amount":parse_number(data["cost"].get())})
        for detail in (((self.result or {}).get("mep_detail_cost_bridge") or {}).get("detail_rows") or []):
            key=str(detail.get("replaced_package_scope_id") or detail.get("mep_trade") or "other")
            result.append({
                "trade":labels.get(key,key),
                "source":f"MEP drawing detail × mapped unit price; replaces package [{key}]",
                "amount":float(detail.get("amount") or 0.0),
            })
        return result

    def _renewal_unit_for_cost_item(self, cost_item_key, item_name=""):
        """Return canonical renewal-unit data; localization is presentation-only."""
        mapping={
            "concrete": ("rc_structure", "Manage concrete, reinforcement and embedded hardware as one RC structural assembly.", "not_individually_replaceable"),
            "reinforcing_steel": ("rc_structure", "Reinforcement is embedded in concrete and managed as part of the RC structural assembly.", "not_individually_replaceable"),
            "formwork": ("rc_construction_temporary_work", "Formwork is temporary work for concrete placement and is not a post-completion renewal target.", "not_applicable"),
            "structural_steel": ("steel_structure", "Manage columns, beams, connections and fire protection as one structural system.", "generally_not_individually_replaceable"),
            "dimension_lumber": ("timber_structure_or_renewable_unit", "Manage by construction zone or renewable unit for walls, floors and roofs.", "replace_by_zone"),
            "clt": ("timber_clt_panel_system", "Manage panels, connections and adjacent finishes as one construction unit.", "panel_based"),
            "phenolic_foam": ("envelope_insulation_system", "Manage insulation, substrate, vapor/waterproof layers and finishes by construction area.", "generally_not_individually_replaceable"),
            "mineral_wool": ("envelope_insulation_system", "Manage insulation, substrate, vapor/waterproof layers and finishes by construction area.", "generally_not_individually_replaceable"),
            "glass_wool": ("envelope_insulation_system", "Manage insulation, substrate, vapor/waterproof layers and finishes by construction area.", "generally_not_individually_replaceable"),
            "windows": ("opening_system", "Manage sash, glazing, hardware and perimeter waterproofing as one opening unit.", "opening_unit"),
            "roofing": ("roof_waterproofing_system", "Manage roofing, waterproofing, substrate and flashings by construction area.", "generally_not_individually_replaceable"),
            "doors": ("door_system", "Manage door leaf, frame and hardware as one opening unit.", "opening_unit"),
            "interior_finish": ("interior_finish_system", "Manage substrate and finish by room or construction zone.", "generally_not_individually_replaceable"),
            "external_finish": ("exterior_finish_system", "Manage cladding, substrate, ventilation layer and waterproofing by construction area.", "generally_not_individually_replaceable"),
        }
        return mapping.get(str(cost_item_key), ("other_construction_unit", "Manage by the construction extent that can actually be removed and replaced.", "review_required"))

    def _localize_renewal_unit(self, unit, policy, replaceable):
        if self.i18n.language!="ja":
            return unit.replace("_"," ").title(), policy, replaceable.replace("_"," ")
        ja_units={
            "rc_structure":"RC躯体",
            "rc_construction_temporary_work":"RC施工仮設",
            "steel_structure":"鉄骨躯体",
            "timber_structure_or_renewable_unit":"木質構造体／更新木造ユニット",
            "timber_clt_panel_system":"木質構造体／CLTパネル系",
            "envelope_insulation_system":"外皮断熱システム",
            "opening_system":"開口部システム",
            "roof_waterproofing_system":"屋根・防水システム",
            "door_system":"建具システム",
            "interior_finish_system":"内装システム",
            "exterior_finish_system":"外壁仕上げシステム",
            "other_construction_unit":"その他施工単位",
        }
        ja_policies={
            "Manage by the construction extent that can actually be removed and replaced.":"実際に撤去・交換できる施工範囲を1つの更新単位として管理します。",
            "Manage concrete, reinforcement and embedded hardware as one RC structural assembly.":"コンクリート・鉄筋・埋込み金物を一体のRC躯体として管理します。",
            "Reinforcement is embedded in concrete and managed as part of the RC structural assembly.":"鉄筋はコンクリート内に埋め込まれるため、RC躯体の一部として管理します。",
            "Formwork is temporary work for concrete placement and is not a post-completion renewal target.":"型枠はコンクリート打設時の仮設工事であり、竣工後の更新対象にはしません。",
            "Manage columns, beams, connections and fire protection as one structural system.":"柱・梁・接合部・耐火被覆を一体の鉄骨構造システムとして管理します。",
            "Manage by construction zone or renewable unit for walls, floors and roofs.":"壁・床・屋根は、施工区画または交換可能な更新単位ごとに管理します。",
            "Manage panels, connections and adjacent finishes as one construction unit.":"パネル・接合部・周辺仕上げを一体の施工単位として管理します。",
            "Manage insulation, substrate, vapor/waterproof layers and finishes by construction area.":"断熱材・下地・防湿／防水層・仕上げを施工範囲ごとにまとめて管理します。",
            "Manage sash, glazing, hardware and perimeter waterproofing as one opening unit.":"サッシ・ガラス・金物・周囲防水を一体の開口部単位として管理します。",
            "Manage roofing, waterproofing, substrate and flashings by construction area.":"屋根材・防水・下地・水切りを施工範囲ごとにまとめて管理します。",
            "Manage door leaf, frame and hardware as one opening unit.":"扉・枠・金物を一体の建具単位として管理します。",
            "Manage substrate and finish by room or construction zone.":"下地と仕上げを室または施工区画ごとにまとめて管理します。",
            "Manage cladding, substrate, ventilation layer and waterproofing by construction area.":"外装材・下地・通気層・防水を施工範囲ごとにまとめて管理します。",
        }
        ja_replaceable={
            "review_required":"要確認",
            "not_individually_replaceable":"材料単独では更新しない",
            "generally_not_individually_replaceable":"原則として材料単独では更新しない",
            "opening_unit":"開口部単位で更新",
            "not_applicable":"対象外",
            "replace_by_zone":"施工区画単位で更新",
            "panel_based":"パネル単位で更新",
        }
        return ja_units.get(unit,unit), ja_policies.get(policy,policy), ja_replaceable.get(replaceable,replaceable)


    def _renewal_unit_rows(self):
        """Aggregate material/trade rows by physically renewable assembly."""
        grouped={}
        lang="ja" if self.i18n.language=="ja" else "en"
        for row in self.result.get("cost_lines",[]):
            key=row.get("cost_item_key","")
            item=self.db.get("base_unit_costs_jpy",{}).get(key,{})
            name=item.get(lang,key)
            unit_id,policy,replaceable=self._renewal_unit_for_cost_item(key,name)
            unit,policy,replaceable=self._localize_renewal_unit(unit_id,policy,replaceable)
            data=grouped.setdefault(unit,{"items":[],"policy":policy,"replaceable":replaceable})
            if name not in data["items"]:
                data["items"].append(name)
        return [(unit,"・".join(data["items"]),data["policy"],data["replaceable"]) for unit,data in grouped.items()]

    def show_quantity_cost_audit(self):
        """PATCH 438: show every Module 1 takeoff row and its Module 5 disposition."""
        if not self.result:
            messagebox.showwarning("Warning",self._ui("先に建設費を計算してください。","Calculate construction cost first."),parent=self);return
        audit=self.result.get("quantity_cost_coverage_audit") or {}
        win=tk.Toplevel(self)
        win.title(self._ui("Module 1数量 → Module 5金額対応監査","Module 1 Quantity → Module 5 Cost Audit"))
        fit_window_to_screen(win,1500,820,820,520)
        lang="ja" if self.i18n.language=="ja" else "en"
        rows=list(audit.get("rows") or [])
        from collections import Counter
        counts=Counter(str(r.get("status") or "") for r in rows)
        summary=(
            f"全{len(rows)}行 / 金額行 {counts.get('included_in_cost_line',0)} / 親工種包含 {counts.get('included_in_parent',0)} / "
            f"未単価 {counts.get('unpriced',0)+counts.get('unpriced_unmapped',0)} / 保留 {counts.get('blocked',0)+counts.get('blocked_by_parent',0)} / "
            f"積算根拠 {counts.get('supporting_evidence',0)} / 監査専用 {counts.get('audit_only',0)} / 数量未確定 {counts.get('missing_quantity',0)}"
            if lang=="ja" else
            f"{len(rows)} rows total / monetized {counts.get('included_in_cost_line',0)} / included in parent {counts.get('included_in_parent',0)} / "
            f"unpriced {counts.get('unpriced',0)+counts.get('unpriced_unmapped',0)} / blocked {counts.get('blocked',0)+counts.get('blocked_by_parent',0)} / "
            f"supporting evidence {counts.get('supporting_evidence',0)} / audit-only {counts.get('audit_only',0)} / missing quantity {counts.get('missing_quantity',0)}"
        )
        ttk.Label(win,text=summary,foreground="#8b0000",wraplength=1460,justify="left").pack(fill="x",padx=8,pady=(8,4))
        cols=("no","item","quantity","unit","status","owner","category","reason")
        tree=ttk.Treeview(win,columns=cols,show="headings")
        heads=(
            ("No.","項目","数量","単位","Module 5状態","金額所有工種","区分","理由")
            if lang=="ja" else
            ("No.","Item","Quantity","Unit","Module 5 status","Monetary owner","Category","Reason")
        )
        widths=(55,330,100,75,185,150,150,430)
        for c,h,w in zip(cols,heads,widths):
            tree.heading(c,text=h);tree.column(c,width=w,stretch=False,anchor="e" if c=="quantity" else "w")
        y=ttk.Scrollbar(win,orient="vertical",command=tree.yview);x=ttk.Scrollbar(win,orient="horizontal",command=tree.xview)
        tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        tree.pack(fill="both",expand=True,padx=(8,24),pady=(4,24));y.place(relx=1.0,x=-20,y=55,relheight=0.88);x.pack(side="bottom",fill="x",padx=8)
        status_labels={
            "included_in_cost_line":("金額計算済み","Monetized"),
            "included_in_parent":("親工種に包含（重複計上なし）","Included in parent (no double count)"),
            "unpriced":("数量あり・未単価","Quantity available / unpriced"),
            "unpriced_unmapped":("数量あり・個別単価未登録","Quantity available / no unit-cost mapping"),
            "blocked":("保留","Blocked"),
            "blocked_by_parent":("親工種が保留","Parent scope blocked"),
            "supporting_evidence":("積算根拠・補助数量","Supporting / intermediate quantity"),
            "audit_only":("監査専用","Audit only"),
            "missing_quantity":("数量未確定","Missing quantity"),
        }
        # PATCH 486: The audit data remains canonical English internally, but
        # Japanese UI must not expose internal English category/reason strings.
        category_ja={
            "reinforcement":"鉄筋", "structure":"構造", "steel member":"鉄骨部材",
            "secondary steel member":"鉄骨二次部材", "secondary steel member audit":"鉄骨二次部材・監査",
            "steel connection":"鉄骨接合", "steel connection audit":"鉄骨接合・監査",
            "building scale":"建物規模", "geometry":"形状・寸法", "opening":"開口・建具",
        }
        def _audit_category_text(v):
            raw=str(v or "")
            if lang!="ja": return raw
            low=raw.strip().lower()
            return category_ja.get(low, raw)
        def _audit_reason_text(v):
            raw=str(v or "")
            if lang!="ja": return raw
            low=raw.strip().lower()
            exact={
                "audit/geometry evidence quantity; not a direct monetary owner":"監査・形状確認用の数量であり、直接の金額計上対象ではありません",
                "specification/evidence exists but no adopted physical quantity":"仕様・根拠はありますが、採用できる物理数量が未確定です",
                "drawing geometry/orientation evidence; used to derive a parent quantity, not separately priced":"図面の形状・方位の根拠数量です。親工種の数量算出に使用し、個別には金額計上しません",
                "representative structural-member layout/count evidence; structural-steel parent scope owns cost":"代表構造部材の配置・本数の根拠です。金額は親工種の構造用鉄骨で計上します",
                "foundation-beam geometry evidence; used to derive concrete/rebar/formwork quantities, not separately priced":"基礎梁の形状根拠です。コンクリート・鉄筋・型枠数量の算出に使用し、個別には金額計上しません",
                "finish target-area geometry; material finish rows or the parent finish scope own cost":"仕上対象面積の根拠です。金額は仕上材料行または親仕上工種で計上します",
                "structural/detail layout evidence; final monetary owner is the structural-steel parent scope":"構造・詳細配置の根拠です。最終的な金額は親工種の構造用鉄骨で計上します",
                "interior-finish audit/control flag; not a physical monetary owner":"内装仕上の監査・管理情報であり、物理的な金額計上対象ではありません",
                "opening/fixture symbol count supports the area/package quantity; not separately priced":"開口・器具記号の個数は面積・一式数量の根拠であり、個別には金額計上しません",
                "reinforcement calculation evidence; final monetary owner is the reinforcing-steel contract":"鉄筋数量の算出根拠です。最終的な金額は親工種の鉄筋で計上します",
                "structural-steel member/connection evidence; final monetary owner is the structural-steel contract":"鉄骨部材・接合部の数量根拠です。最終的な金額は親工種の構造用鉄骨で計上します",
            }
            if low in exact: return exact[low]
            if low.startswith("included in module 5 cost line:"):
                key=raw.split(":",1)[1].strip() if ":" in raw else ""
                return f"Module 5の金額行「{self._cost_item_display_name(key)}」で計上済みです"
            if low.startswith("included in parent package "):
                key=raw[len("Included in parent package "):].split(";",1)[0].strip()
                return f"親工種「{self._cost_item_display_name(key)}」に含まれます。別途加算すると二重計上になります"
            if low.startswith("physical quantity maps to "):
                key=raw[len("Physical quantity maps to "):].split(",",1)[0].strip()
                return f"物理数量は「{self._cost_item_display_name(key)}」に対応しますが、金額行または単価が未設定です"
            if low.startswith("final quantity contract blocks parent scope "):
                key=raw[len("Final quantity contract blocks parent scope "):].strip()
                return f"最終数量契約により親工種「{self._cost_item_display_name(key)}」は保留されています"
            if low.startswith("parent scope ") and " is held; detail is not a separate monetary owner" in low:
                key=raw[len("Parent scope "):].split(" is held",1)[0].strip()
                return f"親工種「{self._cost_item_display_name(key)}」が保留中のため、この詳細数量は個別の金額計上対象にしません"
            if low.startswith("reinforcement calculation evidence;"):
                return "鉄筋数量の算出根拠です。最終的な金額は親工種の鉄筋で計上します"
            if low.startswith("structural-steel member/connection evidence;"):
                return "鉄骨部材・接合部の数量根拠です。最終的な金額は親工種の構造用鉄骨で計上します"
            if low.startswith("foundation-beam geometry evidence;"):
                return "基礎梁の形状根拠です。親工種の数量算出に使用し、個別には金額計上しません"
            return raw
        for r in rows:
            st=str(r.get("status") or "")
            owner=str(r.get("cost_item_key") or r.get("parent_cost_item_key") or "")
            owner_name=self._cost_item_display_name(owner) if owner else "—"
            qty=r.get("quantity")
            unit=str(r.get("unit") or "")
            qtxt="" if qty in (None,"") else format_number(qty,unit or None)
            tree.insert("","end",values=(
                int(r.get("row_index") or 0)+1,str(r.get("item") or ""),qtxt,unit,
                (status_labels.get(st) or (st,st))[0 if lang=="ja" else 1],owner_name,
                _audit_category_text(r.get("category")),_audit_reason_text(r.get("reason"))
            ))

    def show_detailed_statement(self):
        if not self.result:
            messagebox.showwarning("Warning",self._ui("先に建設費を計算してください。","Calculate construction cost first."),parent=self);return
        win=tk.Toplevel(self);win.title(self._ui("工事費明細書（詳細版）","Detailed Construction-Cost Statement"));fit_window_to_screen(win,1450,800,820,520)
        win.minsize(760,480)
        nb=ttk.Notebook(win);nb.pack(fill="both",expand=True,padx=8,pady=8)
        f1=ttk.Frame(nb);f2=ttk.Frame(nb);f3=ttk.Frame(nb);f4=ttk.Frame(nb)
        nb.add(f1,text=self._ui("材料・工種別 新築時内訳","New-Build Breakdown by Material / Trade"))
        nb.add(f2,text=self._ui("設備工事明細","Equipment-Work Breakdown"))
        nb.add(f3,text=self._ui("施工条件補正根拠","Construction-Condition Adjustment Basis"))
        nb.add(f4,text=self._ui("更新単位別管理","Renewal-Unit Management"))

        _unpriced_lines=list(self.result.get("unpriced_cost_lines") or [])
        _partial_total=bool(self.result.get("construction_cost_is_partial")) or (bool(self.result.get("priced_total_excludes_unpriced_items")) and bool(_unpriced_lines))
        _detail_note=(
            ((f"【暫定総額】未単価工種 {len(_unpriced_lines)}件は総額・㎡単価に含まれていません。 " if _partial_total else "") + "費用・新築時CO₂・新築時エネルギーは材料／工種別に集計します。耐用年数・更新年は材料単体ではなく、実際に交換できる『更新単位』で管理します。")
            if self.i18n.language=="ja" else
            ((f"[PROVISIONAL TOTAL] {len(_unpriced_lines)} unpriced trades are excluded from the total and cost/m². " if _partial_total else "") + "Cost, new-build CO₂ and new-build energy are aggregated by material/trade. Service life and renewal are managed by physically replaceable renewal units, not individual materials.")
        )
        note=ttk.Label(
            f1,
            text=_detail_note,
            foreground="#8b0000",wraplength=1380,justify="left")
        note.pack(fill="x",padx=6,pady=(6,2))
        cols=("trade","quantity","unit","price_status","material","labor","equipment","total","renewal_unit","single_replace","basis")
        f1_tree=ttk.Frame(f1);f1_tree.pack(fill="both",expand=True,padx=6,pady=(2,6));f1_tree.rowconfigure(0,weight=1);f1_tree.columnconfigure(0,weight=1)
        tree=ttk.Treeview(f1_tree,columns=cols,show="headings")
        cur=self.result.get("currency","JPY")
        heads=(("材料・工種","数量","単位","単価状態",f"材料費 ({cur})",f"労務費 ({cur})",f"機械・仮設費 ({cur})",f"合計 ({cur})","所属する更新単位","単独更新","算出根拠") if self.i18n.language=="ja" else ("Material / trade","Quantity","Unit","Price status",f"Material ({cur})",f"Labor ({cur})",f"Equipment / temporary ({cur})",f"Total ({cur})","Renewal unit","Standalone renewal","Basis"))
        # PATCH 489: keep a genuinely wider virtual table than the dialog viewport.
        # PATCH 488 added horizontal scrollbars, but the total column width was only
        # slightly wider than the window; on a large display the scrollbar thumb was
        # almost full-width and the table could appear stuck at a clipped x-position.
        # Preserve readable columns and let the horizontal scrollbar do real work.
        widths=(250,95,70,120,145,145,175,145,260,190,1200)
        for c,h,w in zip(cols,heads,widths):
            tree.heading(c,text=h);tree.column(c,width=w,minwidth=w,stretch=False,anchor="e" if c in ("quantity","material","labor","equipment","total") else "w")
        tree_y=ttk.Scrollbar(f1_tree,orient="vertical",command=tree.yview);tree_x=ttk.Scrollbar(f1_tree,orient="horizontal",command=tree.xview)
        tree.configure(yscrollcommand=tree_y.set,xscrollcommand=tree_x.set)
        tree.grid(row=0,column=0,sticky="nsew");tree_y.grid(row=0,column=1,sticky="ns");tree_x.grid(row=1,column=0,sticky="ew")
        # Always open from the true left edge so the first column is never clipped.
        win.after_idle(lambda t=tree: t.xview_moveto(0.0))
        lang="ja" if self.i18n.language=="ja" else "en"
        for row in self.result.get("cost_lines",[]):
            key=row.get("cost_item_key")
            item=self.db["base_unit_costs_jpy"].get(key,{})
            item_name=self._cost_item_display_name(key)
            renewal_unit_id,policy,single_replace=self._renewal_unit_for_cost_item(key,item_name)
            renewal_unit,policy,single_replace=self._localize_renewal_unit(renewal_unit_id,policy,single_replace)
            _ps=str(row.get("pricing_display_status") or "priced").lower()
            _unpriced=(_ps=="unpriced")
            _price_label=(("未単価" if _unpriced else ("確定単価" if _ps=="confirmed_override" else "単価あり")) if lang=="ja" else ("Unpriced" if _unpriced else ("Confirmed price" if _ps=="confirmed_override" else "Priced")))
            _na=("未単価" if lang=="ja" else "Unpriced")
            _all_in=(str(row.get("pricing_structure") or "").lower()=="installed_all_in")
            tree.insert("","end",values=(
                item_name,row.get("quantity"),row.get("unit"),_price_label,
                _na if _unpriced else ("—" if _all_in else format_number(row.get("material_cost",0),cur)),
                _na if _unpriced else ("—" if _all_in else format_number(row.get("labor_cost",0),cur)),
                _na if _unpriced else ("—" if _all_in else format_number(row.get("equipment_cost",0),cur)),
                _na if _unpriced else format_number(row.get("line_total_after_conditions",0),cur),
                renewal_unit,single_replace,(
                ("【図面数量】" if row.get("quantity_source_type")=="drawing_quantity" else
                 "【計画補完】" if row.get("quantity_source_type")=="method_fallback_estimate" else "")
                + (row.get("quantity_basis") or "数量×地域・年度補正単価")
            )))

        # PATCH 490: Treeview cells do not wrap.  A horizontal scrollbar can move
        # the table, but it cannot reveal text that has already been clipped by a
        # too-narrow cell.  Size the long text columns to their actual contents
        # (with a generous cap) so the far-right text remains readable by
        # horizontal scrolling even on a 24-inch display.
        try:
            import tkinter.font as tkfont
            _font=tkfont.nametofont("TkDefaultFont")
            def _fit_text_col(_tree,_col,_minimum,_pad=80):
                # PATCH 491: do not cap long-text columns. Treeview never wraps
                # cell text, so a width cap physically discards the tail even
                # when the horizontal scrollbar is at its far-right position.
                _w=_minimum
                _idx=list(_tree["columns"]).index(_col)
                _head=str(_tree.heading(_col).get("text") or "")
                _w=max(_w,_font.measure(_head)+_pad)
                for _iid in _tree.get_children(""):
                    _vals=_tree.item(_iid,"values") or ()
                    if _idx < len(_vals):
                        _w=max(_w,_font.measure(str(_vals[_idx] or ""))+_pad)
                _tree.column(_col,width=_w,minwidth=_minimum,stretch=False)
            _fit_text_col(tree,"basis",1200)
            _fit_text_col(tree,"renewal_unit",260)
            _fit_text_col(tree,"single_replace",190)
        except Exception:
            tree.column("basis",width=4200,minwidth=1200,stretch=False)

        # PATCH 491: after three iterations of widening Treeview columns, switch
        # to a second, non-clipping path as well.  The selected row is shown in
        # a wrapped read-only detail pane, so every character remains readable
        # on small displays even if the table is scrolled or the OS font/DPI
        # differs from the width measured above.
        detail_box=ttk.LabelFrame(f1,text=self._ui("選択行の全文","Full text of selected row"))
        detail_box.pack(fill="x",padx=6,pady=(0,6))
        detail_text=tk.Text(detail_box,height=5,wrap="word")
        detail_y=ttk.Scrollbar(detail_box,orient="vertical",command=detail_text.yview)
        detail_text.configure(yscrollcommand=detail_y.set,state="disabled")
        detail_text.pack(side="left",fill="both",expand=True,padx=(4,0),pady=4)
        detail_y.pack(side="right",fill="y",padx=(0,4),pady=4)
        def _show_full_detail(_event=None):
            _sel=tree.selection()
            if not _sel:
                return
            _vals=tree.item(_sel[0],"values") or ()
            _pairs=[]
            for _c,_h,_v in zip(cols,heads,_vals):
                _pairs.append(f"{_h}: {_v}")
            detail_text.configure(state="normal")
            detail_text.delete("1.0","end")
            detail_text.insert("1.0","\n".join(_pairs))
            detail_text.configure(state="disabled")
        tree.bind("<<TreeviewSelect>>",_show_full_detail,add="+")
        if tree.get_children(""):
            _first=tree.get_children("")[0]
            tree.selection_set(_first);tree.focus(_first);_show_full_detail()

        f2_tree=ttk.Frame(f2);f2_tree.pack(fill="both",expand=True,padx=6,pady=6);f2_tree.rowconfigure(0,weight=1);f2_tree.columnconfigure(0,weight=1)
        ecols=("trade","amount","source");et=ttk.Treeview(f2_tree,columns=ecols,show="headings")
        _eh=( (("trade","設備工種",300),("amount",f"金額 ({cur})",180),("source","数量・金額の根拠",1200)) if self.i18n.language=="ja" else (("trade","Equipment trade",300),("amount",f"Amount ({cur})",180),("source","Quantity / amount basis",1200)) )
        for c,h,w in _eh:
            et.heading(c,text=h);et.column(c,width=w,minwidth=w,stretch=False,anchor="w")
        et_y=ttk.Scrollbar(f2_tree,orient="vertical",command=et.yview);et_x=ttk.Scrollbar(f2_tree,orient="horizontal",command=et.xview)
        et.configure(yscrollcommand=et_y.set,xscrollcommand=et_x.set)
        et.grid(row=0,column=0,sticky="nsew");et_y.grid(row=0,column=1,sticky="ns");et_x.grid(row=1,column=0,sticky="ew")
        win.after_idle(lambda t=et: t.xview_moveto(0.0))
        for row in self.result.get("equipment_trade_breakdown",[]):
            et.insert("","end",values=(row["trade"],format_number(row["amount"],cur),row["source"]))

        f3_tree=ttk.Frame(f3);f3_tree.pack(fill="both",expand=True,padx=6,pady=(6,0));f3_tree.rowconfigure(0,weight=1);f3_tree.columnconfigure(0,weight=1)
        ccols=("condition","amount","basis");ct=ttk.Treeview(f3_tree,columns=ccols,show="headings",selectmode="browse")
        _ch=( (("condition","条件",300),("amount",f"補正額（直接入力） ({cur})",220),("basis","決定根拠・出典",1400)) if self.i18n.language=="ja" else (("condition","Condition",300),("amount",f"Adjustment amount (direct) ({cur})",220),("basis","Decision basis / source",1400)) )
        for c,h,w in _ch:
            ct.heading(c,text=h);ct.column(c,width=w,minwidth=w,stretch=False,anchor="w")
        ct_y=ttk.Scrollbar(f3_tree,orient="vertical",command=ct.yview);ct_x=ttk.Scrollbar(f3_tree,orient="horizontal",command=ct.xview)
        ct.configure(yscrollcommand=ct_y.set,xscrollcommand=ct_x.set)
        ct.grid(row=0,column=0,sticky="nsew");ct_y.grid(row=0,column=1,sticky="ns");ct_x.grid(row=1,column=0,sticky="ew")
        win.after_idle(lambda t=ct: t.xview_moveto(0.0))
        direct_rows={}
        current_condition_total=float(self.result.get("summary",{}).get("condition_adjustment",0.0) or 0.0)
        base_for_legacy=max(float(self.result.get("summary",{}).get("subtotal_before_tax",0.0) or 0.0)-current_condition_total,0.0)
        for category in ("site","access","work_time","reserve"):
            for idx,row in enumerate(self.condition_matrix.get(category,[])):
                if not row.get("checked"):
                    continue
                amount=row.get("amount_local_currency")
                amount_currency=str(row.get("amount_currency") or cur)
                if amount is not None and amount_currency != cur:
                    amount=None
                if amount is None:
                    amount=base_for_legacy*float(row.get("rate_percent",0.0) or 0.0)/100.0
                iid=ct.insert("","end",values=(self._localized_condition_text(row.get("condition")),format_number(amount,cur),self._localized_condition_text(row.get("basis"))))
                direct_rows[iid]=(category,idx)
        help_bar=ttk.Frame(f3);help_bar.pack(fill="x",padx=6,pady=6)
        ttk.Label(help_bar,text=self._ui("補正額セルをダブルクリック、または行を選択してF2で金額を直接入力します。補正率は使用しません。","Double-click the adjustment amount cell, or select a row and press F2, to enter the amount directly. Percentage adjustment is not used."),foreground="#8b0000").pack(side="left")

        def edit_direct_amount(event=None):
            iid=ct.focus() or (ct.selection()[0] if ct.selection() else "")
            if not iid or iid not in direct_rows:return
            bbox=ct.bbox(iid,"amount")
            if not bbox:return
            x,y,w,h=bbox;raw=str(ct.set(iid,"amount")).replace(",","");var=tk.StringVar(value=raw)
            entry=tk.Entry(ct,textvariable=var,justify="right",bg=INPUT_BG);entry.place(x=x,y=y,width=w,height=h);entry.focus_set();entry.select_range(0,"end")
            def commit(_e=None):
                try:value=float(var.get().replace(",","") or 0.0)
                except ValueError:
                    messagebox.showerror(self._ui("入力エラー","Input Error"),self._ui("補正額を数値で入力してください。","Enter a numeric adjustment amount."),parent=win);entry.focus_set();return
                category,idx=direct_rows[iid]
                self.condition_matrix[category][idx]["amount_local_currency"]=value
                self.condition_matrix[category][idx]["amount_currency"]=cur
                self.condition_matrix[category][idx]["amount_jpy"]=None
                ct.set(iid,"amount",format_number(value,cur));entry.destroy()
            entry.bind("<Return>",commit);entry.bind("<FocusOut>",commit);entry.bind("<Escape>",lambda e:entry.destroy())
        ct.bind("<Double-1>",lambda e: edit_direct_amount(e) if ct.identify_column(e.x)=="#2" else None);ct.bind("<F2>",edit_direct_amount)

        def apply_direct_amounts():
            selected_total=0.0
            for category in ("site","access","work_time","reserve"):
                for row in self.condition_matrix.get(category,[]):
                    if row.get("checked"):
                        amount=row.get("amount_local_currency")
                        amount_currency=str(row.get("amount_currency") or cur)
                        if amount is not None and amount_currency != cur:
                            amount=None
                        if amount is None:
                            amount=base_for_legacy*float(row.get("rate_percent",0.0) or 0.0)/100.0
                            row["amount_local_currency"]=amount
                            row["amount_currency"]=cur
                            row["amount_jpy"]=None
                        selected_total+=float(amount or 0.0)
            summary=self.result.get("summary",{});old=float(summary.get("condition_adjustment",0.0) or 0.0);delta=selected_total-old
            summary["condition_adjustment"]=selected_total
            summary["additional_condition_adjustment"]=sum(
                float(r.get("amount_local_currency") or 0.0)
                for r in self.condition_matrix.get("reserve",[])
                if r.get("checked") and str(r.get("amount_currency") or cur)==cur
            )
            summary["subtotal_before_tax"]=float(summary.get("subtotal_before_tax",0.0) or 0.0)+delta
            tax_rate=float(self.rates["tax_percent"].get())/100.0;summary["tax_amount"]=summary["subtotal_before_tax"]*tax_rate
            summary["total_construction_cost"]=summary["subtotal_before_tax"]+summary["tax_amount"]
            area=float(self.project.get("building",{}).get("total_floor_area_m2",0.0) or 0.0) if self.project else 0.0
            if area>0:summary["cost_per_m2"]=summary["total_construction_cost"]/area
            self.result["condition_matrix"]=self.condition_matrix;self.render()
            messagebox.showinfo(self._ui("反映完了","Applied"),self._ui(f"詳細版の施工条件補正額 {format_number(selected_total,cur)} を建設費へ反映しました。",f"Applied detailed construction-condition adjustment {format_number(selected_total,cur)} to construction cost."),parent=win)
        ttk.Button(help_bar,text=self._ui("入力金額を建設費へ反映","Apply Entered Amounts to Construction Cost"),style="Primary.TButton",command=apply_direct_amounts).pack(side="right")

        ttk.Label(
            f4,
            text=self._ui("ここでは材料単体の耐用年数・更新年を設定しません。修繕・更新・解体は、実際に撤去・交換可能な構成単位で管理します。","Material-level service life/renewal years are not set here. Repair, renewal and demolition are managed by physically removable/replaceable assembly units."),
            foreground="#8b0000",wraplength=1380,justify="left").pack(fill="x",padx=6,pady=(6,2))
        ucols=("unit","components","policy","replaceable")
        f4_tree=ttk.Frame(f4);f4_tree.pack(fill="both",expand=True,padx=6,pady=6);f4_tree.rowconfigure(0,weight=1);f4_tree.columnconfigure(0,weight=1)
        ut=ttk.Treeview(f4_tree,columns=ucols,show="headings")
        _uh=( (("unit","更新単位",260),("components","含まれる材料・工種",900),("policy","更新・解体の判断単位",1200),("replaceable","材料単独更新",190)) if self.i18n.language=="ja" else (("unit","Renewal unit",260),("components","Included materials / trades",900),("policy","Renewal / demolition decision unit",1200),("replaceable","Material-only renewal",190)) )
        for c,h,w in _uh:
            ut.heading(c,text=h,anchor="w");ut.column(c,width=w,minwidth=w,stretch=False,anchor="w")
        ut_y=ttk.Scrollbar(f4_tree,orient="vertical",command=ut.yview);ut_x=ttk.Scrollbar(f4_tree,orient="horizontal",command=ut.xview)
        ut.configure(yscrollcommand=ut_y.set,xscrollcommand=ut_x.set)
        ut.grid(row=0,column=0,sticky="nsew");ut_y.grid(row=0,column=1,sticky="ns");ut_x.grid(row=1,column=0,sticky="ew")
        win.after_idle(lambda t=ut: t.xview_moveto(0.0))
        for unit,components,policy,replaceable in self._renewal_unit_rows():
            ut.insert("","end",values=(unit,components,policy,replaceable))

    def edit_unit_costs(self):
        if self._comparison_copy_price_block("module5_manual_unit_cost_edit"):
            return
        """PATCH 485: Project-specific parent/child unit-cost editor.

        The editor follows the same display order/numbering as Module 5's
        material/trade table, exposes physical Module 1 child quantities, and
        keeps parent-package pricing separate from optional child-detail input.
        Child prices never double-count automatically.  A parent can explicitly
        switch to child-rollup mode; the selected child totals are then converted
        to one parent all-in rate for the existing cost engine.
        """
        if not self.result:
            messagebox.showwarning("Warning",self._ui("先に建設費を計算してください。","Calculate construction cost first."),parent=self);return
        import copy
        d=tk.Toplevel(self);d.title(self.i18n.t("edit_unit_costs"));fit_window_to_screen(d,1760,820,820,520)
        t=self.i18n.t;lang="ja" if self.i18n.language=="ja" else "en"
        currency=str(self.result.get("currency") or self.currency.get() or "JPY").upper()
        cols=("no","relation","item","quantity","unit","adopted","structure","material","labor","equipment","status","source")
        tree_host=ttk.Frame(d);tree_host.pack(fill="both",expand=True,padx=8,pady=8);tree_host.rowconfigure(0,weight=1);tree_host.columnconfigure(0,weight=1)
        tree=ttk.Treeview(tree_host,columns=cols,show="headings",selectmode="browse")
        labels={
            "no":"No.","relation":self._ui("親子","Parent / child"),"item":t("item"),"quantity":self._ui("採用数量","Adopted qty"),"unit":t("unit"),
            "adopted":self._ui("採用単価","Adopted unit price"),"structure":self._ui("単価構成","Price structure"),
            "material":self._ui("材料内訳","Material component"),"labor":self._ui("労務内訳","Labor component"),
            "equipment":self._ui("機械・仮設内訳","Plant / temporary component"),"status":self._ui("単価状態","Price status"),
            "source":self._ui("採用単価の出所","Adopted price source")}
        widths={"no":55,"relation":120,"item":300,"quantity":105,"unit":70,"adopted":125,"structure":180,"material":110,"labor":110,"equipment":125,"status":145,"source":250}
        for c in cols:
            tree.heading(c,text=labels[c]);tree.column(c,width=widths[c],stretch=False,anchor="e" if c in {"no","quantity","adopted","material","labor","equipment"} else "w")
        tree_y=ttk.Scrollbar(tree_host,orient="vertical",command=tree.yview);tree_x=ttk.Scrollbar(tree_host,orient="horizontal",command=tree.xview)
        tree.configure(yscrollcommand=tree_y.set,xscrollcommand=tree_x.set)
        tree.grid(row=0,column=0,sticky="nsew");tree_y.grid(row=0,column=1,sticky="ns");tree_x.grid(row=1,column=0,sticky="ew")
        tree.tag_configure("parent",font=("TkDefaultFont",9,"bold"))
        tree.tag_configure("child",foreground="#333333")
        tree.tag_configure("audit",foreground="#777777")
        tree.tag_configure("unpriced",foreground="#b00000")

        def _status_text(code):
            code=str(code or "").strip().lower()
            mapping={"confirmed_price":self._ui("根拠確認済","Evidence checked"),"estimated_price":self._ui("概算・暫定","Provisional estimate"),
                "confirmed_override":self._ui("手動確認単価","Manually confirmed"),"user_confirmed_current_unit_rate":self._ui("手動確認単価","Manually confirmed"),
                "user_manual_detail_rollup":self._ui("子項目手動積上げ","Manual child roll-up"),"unpriced":self._ui("未単価・要確認","Unpriced / review required"),
                "priced":self._ui("単価あり","Priced")}
            return mapping.get(code,code or self._ui("単価あり","Priced"))
        def _source_text(code):
            code=str(code or "").strip()
            mapping={"local_installed_all_in":self._ui("現地調査・一式単価","Local research / all-in rate"),
                "user_confirmed_current_year_all_in_local_currency":self._ui("手動入力・現地通貨一式単価","Manual local-currency all-in rate"),
                "foreign_local_unit_unpriced_missing":self._ui("現地単価未取得","Local price not obtained"),
                "foreign_local_unit_cost_required_no_jpy_fx_fallback":self._ui("現地単価未取得（日本単価・為替換算なし）","Local price missing (no JPY/FX fallback)"),
                "base_unit_costs_jpy":self._ui("日本基準単価","Japan base unit price"),"japan_base_regional_index":self._ui("日本基準単価・地域補正","Japan base unit price / regional adjustment"),
                "Module 5 current calculation":self._ui("現在のModule 5計算","Current Module 5 calculation"),
                "Module 5 manual unit-cost edit":self._ui("現在Projectの手動編集","Current Project manual edit"),
                "Module 5 manual detail rollup":self._ui("子項目手動積上げ","Manual child-detail roll-up"),
                "Module 5 manual child-detail unit-cost edit":self._ui("子項目手動単価","Manual child-detail unit rate")}
            if code.startswith("foreign_local_unit_unpriced_"):return self._ui("現地単価未取得・要確認","Local price not obtained / review required")
            return mapping.get(code,code or self._ui("現在のModule 5計算","Current Module 5 calculation"))
        def _structure_text(structure,unpriced=False):
            if unpriced:return "—"
            if str(structure or "").lower()=="installed_all_in":return self._ui("一式単価（内訳未分離）","All-in rate (components not split)")
            return self._ui("材料・労務・機械の内訳単価","Component-split rate")
        def _fmt(v):return "—" if v is None else f"{float(v):,.6f}".rstrip("0").rstrip(".")
        def _qtyfmt(v):
            if v in (None,""):return "—"
            try:return f"{float(v):,.6f}".rstrip("0").rstrip(".")
            except Exception:return str(v)
        def _letters(n):
            # A..Z, AA..AZ ...
            out="";n=int(n)
            while True:
                n,r=divmod(n,26);out=chr(65+r)+out
                if n==0:return out
                n-=1

        loc=self.db["locations"][self.location.get()]
        overlay=loc.setdefault("_session_ai_unit_cost_overlay",{})
        units=overlay.setdefault("unit_costs",{})
        detail_units=overlay.setdefault("detail_unit_costs",{})
        parent_modes=overlay.setdefault("parent_pricing_modes",{})

        # Build the same principal display order as the Module 5 table, then append
        # its physical child/support rows in the same audit order.
        display=[];seen_parent_keys=set();existing=set()
        for line in self.result.get("cost_lines",[]) or []:
            key=str(line.get("cost_item_key") or "")
            if not key:continue
            existing.add(key)
            item=(self.db.get("base_unit_costs_jpy",{}) or {}).get(key,{})
            display.append({"kind":"cost","cost_item_key":key,"item":self._cost_item_display_name(key) or item.get(lang,key),"quantity":line.get("quantity"),"unit":line.get("unit"),"line":line})
        scope_audit=self.result.get("cost_scope_completeness_audit") or {}
        scope_names={"foundation_preparation_group":self._ui("基礎土工・地業","Foundation earthwork / groundwork"),"structural_steel":self._ui("構造用鉄骨","Structural steel"),"concrete":self._ui("コンクリート","Concrete"),"reinforcing_steel":self._ui("鉄筋","Reinforcing steel"),"formwork":self._ui("型枠","Formwork"),"dimension_lumber":self._ui("構造木材","Structural timber")}
        for a in scope_audit.get("items",[]) or []:
            key=str(a.get("cost_item_key") or "");st=str(a.get("status") or "")
            if key in existing and st in {"priced","unpriced"}:continue
            dbitem=(self.db.get("base_unit_costs_jpy",{}) or {}).get(key,{})
            display.append({"kind":"scope","cost_item_key":key,"item":scope_names.get(key) or dbitem.get(lang,key),"quantity":a.get("quantity"),"unit":a.get("unit"),"scope_status":st})
        coverage=self.result.get("quantity_cost_coverage_audit") or {}
        _skip_parent={"structural_steel","reinforcing_steel"}
        for r in coverage.get("rows",[]) or []:
            st=str(r.get("status") or "")
            if st in {"audit_only","included_in_cost_line"}:continue
            _parent_for_filter=str(r.get("parent_cost_item_key") or "")
            if _parent_for_filter in _skip_parent and st in {"included_in_parent","blocked_by_parent","unpriced"}:continue
            qty=r.get("quantity");unit=str(r.get("unit") or "")
            if st=="missing_quantity" and not bool(r.get("monetary_gap")):continue
            # Keep audit rows visible for traceability, but only physical non-audit
            # rows can be given a monetary child rate.
            display.append({"kind":"detail","row_index":r.get("row_index"),"item":str(r.get("item") or ""),"quantity":qty,"unit":unit,
                "parent_cost_item_key":str(r.get("parent_cost_item_key") or r.get("cost_item_key") or ""),"coverage_status":st,"monetary_gap":bool(r.get("monetary_gap")),"reason":r.get("reason")})

        # Parent letters are assigned in the order in which a parent first appears.
        child_parent_keys=[]
        for rec in display:
            if rec.get("kind")!="detail":continue
            pk=str(rec.get("parent_cost_item_key") or "")
            if pk and pk not in child_parent_keys:child_parent_keys.append(pk)
        group={pk:_letters(i) for i,pk in enumerate(child_parent_keys)}

        current_lines={str(r.get("cost_item_key") or ""):r for r in (self.result.get("cost_lines") or []) if r.get("cost_item_key")}
        row_state={};parent_iid={};detail_iids_by_parent={}

        def _parent_mode(pk):
            v=parent_modes.get(pk)
            if isinstance(v,dict):return str(v.get("mode") or "parent_all_in")
            return str(v or "parent_all_in")
        def _parent_relation(pk,no):
            g=group.get(pk)
            if not g:return ""
            mode=_parent_mode(pk)
            return self._ui(f"親{g}・{'子積上げ' if mode=='detail_sum' else '親単価'}",f"Parent {g} / {'child roll-up' if mode=='detail_sum' else 'parent rate'}")
        def _child_relation(pk,no,include):
            g=group.get(pk)
            if not g:return ""
            flag=self._ui("計上","included") if include else self._ui("参考","reference")
            return f"{g}-{no} [{flag}]"

        for no,rec in enumerate(display,1):
            kind=rec.get("kind");pk=str(rec.get("parent_cost_item_key") or rec.get("cost_item_key") or "")
            if kind in {"cost","scope"}:
                key=str(rec.get("cost_item_key") or "");line=current_lines.get(key);base_item=(self.db.get("base_unit_costs_jpy",{}) or {}).get(key,{})
                if line is not None:
                    unpriced=str(line.get("pricing_display_status") or "").lower()=="unpriced";structure=str(line.get("pricing_structure") or "component_split")
                    if unpriced:components=(None,None,None);adopted=None
                    else:
                        m=float(line.get("material_unit_cost") or 0);l=float(line.get("labor_unit_cost") or 0);e=float(line.get("equipment_unit_cost") or 0)
                        adopted=float(line.get("installed_all_in_unit_cost") if structure=="installed_all_in" and line.get("installed_all_in_unit_cost") is not None else m+l+e)
                        components=(None,None,None) if structure=="installed_all_in" else (m,l,e)
                    _meta=line.get("regional_unit_cost_metadata") if isinstance(line.get("regional_unit_cost_metadata"),dict) else {}
                    _meta_status=str(_meta.get("pricing_status") or "")
                    status=_status_text("unpriced" if unpriced else (_meta_status if _meta_status in {"user_manual_detail_rollup","user_manual_current_project_override"} else line.get("pricing_display_status")))
                    source=_source_text(_meta.get("source_name") or line.get("unit_price_source") or "Module 5 current calculation")
                else:
                    structure="unpriced";components=(None,None,None);adopted=None;unpriced=True;status=self._ui("未単価・要確認","Unpriced / review required");source=self._ui("現在のProjectでは採用単価なし","No adopted price for current Project")
                iid=f"cost:{key}:{no}";parent_iid[key]=iid
                state={**rec,"iid":iid,"no":no,"key":key,"adopted":adopted,"components":components,"structure":structure,"status":status,"source":source,"unpriced":unpriced,"base_item":base_item}
                row_state[iid]=state
                relation=_parent_relation(key,no)
                tree.insert("","end",iid=iid,values=(no,relation,self._quantity_item_display_name(rec.get("canonical_item") or rec.get("item")),_qtyfmt(rec.get("quantity")),rec.get("unit"),_fmt(adopted),_structure_text(structure,unpriced),_fmt(components[0]),_fmt(components[1]),_fmt(components[2]),status,source),tags=(("parent",) if relation else (("unpriced",) if unpriced else ())))
            else:
                rid=str(rec.get("row_index"));saved=detail_units.get(rid) if isinstance(detail_units.get(rid),dict) else {}
                structure=str(saved.get("pricing_structure") or "installed_all_in")
                include=bool(saved.get("rollup_include"))
                editable=(str(rec.get("coverage_status") or "")!="audit_only" and rec.get("quantity") not in (None,"") and str(rec.get("unit") or "") not in {"","—","仕様","spec","spec."})
                if saved:
                    if structure=="installed_all_in":adopted=saved.get("installed_unit_cost");components=(None,None,None)
                    else:
                        components=tuple(saved.get(k) for k in ("material","labor","equipment"));adopted=sum(float(x or 0) for x in components)
                    status=self._ui("手動子単価","Manual child rate");source=self._ui("現在Projectの子項目手動入力","Current Project child-detail input")
                else:
                    adopted=None;components=(None,None,None);status=(self._ui("監査専用・単価対象外","Audit only / non-monetary") if not editable else self._ui("子単価未入力","Child rate not entered"));source="—"
                iid=f"detail:{rid}:{no}";state={**rec,"iid":iid,"no":no,"detail_id":rid,"parent_key":pk,"adopted":adopted,"components":components,"structure":structure,"status":status,"source":source,"unpriced":adopted is None,"editable":editable,"rollup_include":include}
                row_state[iid]=state;detail_iids_by_parent.setdefault(pk,[]).append(iid)
                relation=_child_relation(pk,no,include)
                tag="audit" if not editable else ("child" if adopted is not None else "unpriced")
                tree.insert("","end",iid=iid,values=(no,relation,self._quantity_item_display_name(rec.get("canonical_item") or rec.get("item")),_qtyfmt(rec.get("quantity")),rec.get("unit"),_fmt(adopted),_structure_text(structure,adopted is None),_fmt(components[0]),_fmt(components[1]),_fmt(components[2]),status,source),tags=(tag,))

        def _refresh_relation(pk):
            pi=parent_iid.get(pk)
            if pi and pi in row_state:
                st=row_state[pi];vals=list(tree.item(pi,"values"));vals[1]=_parent_relation(pk,st["no"]);tree.item(pi,values=vals)
            for iid in detail_iids_by_parent.get(pk,[]):
                st=row_state[iid];vals=list(tree.item(iid,"values"));vals[1]=_child_relation(pk,st["no"],bool(st.get("rollup_include")));tree.item(iid,values=vals)

        def _rebuild_parent_rollup(pk,show_message=True):
            if not pk or _parent_mode(pk)!="detail_sum":return False
            pi=parent_iid.get(pk);pst=row_state.get(pi) if pi else None
            if not pst or pst.get("quantity") in (None,""):
                if show_message:messagebox.showwarning(self._ui("子項目積上げ","Child roll-up"),self._ui("親工種の採用数量がないため積上げ単価を作成できません。","The parent has no adopted quantity, so a roll-up rate cannot be created."),parent=d)
                return False
            included=[];missing=[];total=0.0
            for iid in detail_iids_by_parent.get(pk,[]):
                st=row_state[iid]
                if not st.get("rollup_include"):continue
                if not st.get("editable"):continue
                if st.get("adopted") is None:missing.append(st.get("item"));continue
                try:q=float(st.get("quantity") or 0);u=float(st.get("adopted") or 0)
                except Exception:continue
                total+=q*u;included.append(st)
            if missing:
                if show_message:messagebox.showwarning(self._ui("子項目積上げ未完了","Child roll-up incomplete"),self._ui("『計上』に指定した子項目に未単価があります。親単価は更新しません。\n","Some child rows marked 'included' have no unit price. The parent rate was not updated.\n")+"\n".join(str(x) for x in missing[:12]),parent=d)
                return False
            if not included:
                if show_message:messagebox.showwarning(self._ui("子項目積上げ","Child roll-up"),self._ui("『計上』に指定した子項目がありません。","No child rows are marked for inclusion."),parent=d)
                return False
            pq=float(pst.get("quantity") or 0)
            if pq<=0:return False
            rate=total/pq
            units[pk]={"unit":pst.get("unit"),"installed_unit_cost":rate,"pricing_structure":"installed_all_in","pricing_status":"user_manual_detail_rollup","source_name":"Module 5 manual detail rollup","source_reference":"current Project child-detail rows","detail_rollup_total":total,"detail_rollup_child_count":len(included),"note_ja":"現在Projectで明示的に『計上』指定した子項目の数量×手動単価を合計し、親工種の一式単価へロールアップ。子項目は別加算せず二重計上しない。"}
            pst.update({"adopted":rate,"components":(None,None,None),"structure":"installed_all_in","status":self._ui("子項目手動積上げ・再計算待ち","Manual child roll-up / recalc required"),"source":self._ui("子項目手動積上げ","Manual child-detail roll-up"),"unpriced":False})
            vals=list(tree.item(pi,"values"));vals[5]=_fmt(rate);vals[6]=_structure_text("installed_all_in");vals[7]=vals[8]=vals[9]="—";vals[10]=pst["status"];vals[11]=pst["source"];tree.item(pi,values=vals,tags=("parent",))
            return True

        ttk.Label(d,text=self._ui(
            f"表示通貨: {currency}。No.はModule 5の工種・材料別内訳と同じ表示順です。親A・A-35等で親子関係を示します。子項目へ単価を入力しても自動加算しません。『計上』指定した子だけを親の子積上げ方式へ切替えた場合、子数量×子単価の合計を親一式へ置換し、親と子を二重計上しません。監査専用の幾何・仕様行は単価対象外です。",
            f"Currency: {currency}. No. follows the Module 5 material/trade display order. Parent/child links are shown as Parent A, A-35, etc. Entering a child rate does not add it automatically. Only child rows explicitly marked 'included' are rolled into the parent when child-roll-up mode is selected, preventing double counting. Audit-only geometry/specification rows are non-monetary."),foreground="#8b0000",wraplength=1700,justify="left").pack(fill="x",padx=10,pady=(0,5))

        def _selected_parent_key():
            sel=tree.selection()
            if not sel:return ""
            st=row_state.get(sel[0]) or {}
            return str(st.get("parent_key") or st.get("key") or "")

        def toggle_parent_mode():
            pk=_selected_parent_key()
            if not pk or pk not in group:
                messagebox.showinfo(self._ui("親子計上方式","Parent/child pricing mode"),self._ui("子項目を持つ親工種またはその子項目を選択してください。","Select a parent with child rows or one of its child rows."),parent=d);return
            cur=_parent_mode(pk)
            state=parent_modes.get(pk) if isinstance(parent_modes.get(pk),dict) else {"mode":cur}
            if cur!="detail_sum":
                # Preserve the pre-rollup overlay entry so the user can revert.
                state={"mode":"detail_sum","previous_unit_cost":copy.deepcopy(units.get(pk)) if pk in units else None}
                parent_modes[pk]=state
                if not _rebuild_parent_rollup(pk,show_message=True):
                    state["mode"]="parent_all_in"
                    parent_modes[pk]=state
            else:
                prev=state.get("previous_unit_cost") if isinstance(state,dict) else None
                if prev is None:units.pop(pk,None)
                else:units[pk]=copy.deepcopy(prev)
                parent_modes[pk]={"mode":"parent_all_in","previous_unit_cost":None}
                pi=parent_iid.get(pk);pst=row_state.get(pi) if pi else None
                line=current_lines.get(pk)
                if pst and line:
                    unpriced=str(line.get("pricing_display_status") or "").lower()=="unpriced";structure=str(line.get("pricing_structure") or "component_split")
                    if unpriced:adopted=None;comps=(None,None,None)
                    else:
                        m=float(line.get("material_unit_cost") or 0);l=float(line.get("labor_unit_cost") or 0);e=float(line.get("equipment_unit_cost") or 0);adopted=float(line.get("installed_all_in_unit_cost") if structure=="installed_all_in" and line.get("installed_all_in_unit_cost") is not None else m+l+e);comps=(None,None,None) if structure=="installed_all_in" else (m,l,e)
                    pst.update({"adopted":adopted,"components":comps,"structure":structure,"unpriced":unpriced,"status":_status_text("unpriced" if unpriced else line.get("pricing_display_status")),"source":_source_text(line.get("unit_price_source") or "Module 5 current calculation")})
                    vals=list(tree.item(pi,"values"));vals[5]=_fmt(adopted);vals[6]=_structure_text(structure,unpriced);vals[7]=_fmt(comps[0]);vals[8]=_fmt(comps[1]);vals[9]=_fmt(comps[2]);vals[10]=pst["status"];vals[11]=pst["source"];tree.item(pi,values=vals,tags=("parent",))
            _refresh_relation(pk)

        def edit():
            sel=tree.selection()
            if not sel:return
            iid=sel[0];state=row_state[iid]
            if state.get("kind")=="detail":
                if not state.get("editable"):
                    messagebox.showinfo(self._ui("単価対象外","Non-monetary row"),self._ui("この行は監査・幾何・仕様の補助情報であり、直接の単価所有者ではありません。","This row is audit/geometry/specification evidence and is not a direct monetary owner."),parent=d);return
                w=tk.Toplevel(d);w.title(str(state.get("item")))
                v=tk.StringVar(value=("" if state.get("adopted") is None else _fmt(state.get("adopted")).replace(",","")))
                inc=tk.BooleanVar(value=bool(state.get("rollup_include")))
                ttk.Label(w,text=self._ui("子項目一式単価","Child all-in unit price")).grid(row=0,column=0,padx=6,pady=5,sticky="w");tk.Entry(w,textvariable=v,bg=INPUT_BG).grid(row=0,column=1,padx=6,pady=5)
                ttk.Label(w,text=f"{currency} / {state.get('unit')}",foreground="#555").grid(row=1,column=0,columnspan=2,pady=2)
                if state.get("parent_key"):
                    ttk.Checkbutton(w,text=self._ui("親工種の子項目積上げに含める（明示選択）","Include in parent child-roll-up (explicit selection)"),variable=inc).grid(row=2,column=0,columnspan=2,padx=6,pady=5,sticky="w")
                ttk.Label(w,text=self._ui("子単価は入力しただけでは建設費へ加算しません。親を『子積上げ』方式に切替え、かつこの行を『計上』指定した場合だけ親金額へ反映します。","A child rate is not added merely by entering it. It affects cost only when the parent is switched to child-roll-up mode and this row is explicitly included."),foreground="#8b0000",wraplength=560,justify="left").grid(row=3,column=0,columnspan=2,padx=6,pady=4,sticky="w")
                def save_detail():
                    raw=(v.get() or "").replace(",","").strip()
                    if not raw:
                        detail_units.pop(state["detail_id"],None);val=None
                    else:
                        try:val=float(raw)
                        except ValueError:messagebox.showerror(self._ui("単価編集","Edit Unit Costs"),self._ui("単価は数値で入力してください。","Enter a numeric unit cost."),parent=w);return
                        if val<0:messagebox.showerror(self._ui("単価編集","Edit Unit Costs"),self._ui("単価に負数は入力できません。","Unit cost cannot be negative."),parent=w);return
                        detail_units[state["detail_id"]]={"item":state.get("item"),"quantity":state.get("quantity"),"unit":state.get("unit"),"parent_cost_item_key":state.get("parent_key"),"installed_unit_cost":val,"pricing_structure":"installed_all_in","rollup_include":bool(inc.get()),"source_name":"Module 5 manual child-detail unit-cost edit","source_reference":"current Project / Module 1 row","note_ja":"Module 1子項目へ手動一式単価を設定。親子二重計上防止のため、明示的に子積上げへ切替えるまで建設費へは加算しない。"}
                    state.update({"adopted":val,"components":(None,None,None),"structure":"installed_all_in","rollup_include":bool(inc.get()),"status":self._ui("手動子単価","Manual child rate") if val is not None else self._ui("子単価未入力","Child rate not entered"),"source":self._ui("現在Projectの子項目手動入力","Current Project child-detail input") if val is not None else "—"})
                    vals=list(tree.item(iid,"values"));vals[1]=_child_relation(state.get("parent_key"),state["no"],bool(inc.get()));vals[5]=_fmt(val);vals[6]=_structure_text("installed_all_in",val is None);vals[7]=vals[8]=vals[9]="—";vals[10]=state["status"];vals[11]=state["source"];tree.item(iid,values=vals,tags=(("child",) if val is not None else ("unpriced",)))
                    if _parent_mode(state.get("parent_key"))=="detail_sum":_rebuild_parent_rollup(state.get("parent_key"),show_message=False)
                    _refresh_relation(state.get("parent_key"));w.destroy()
                ttk.Button(w,text=t("save"),command=save_detail).grid(row=4,column=0,columnspan=2,pady=8);return

            key=str(state.get("key") or "");base_item=state.get("base_item") or {};w=tk.Toplevel(d);w.title(str(state.get("item")))
            current_structure=str(state.get("structure") or "component_split")
            # An unpriced principal row is intentionally editable as a new all-in
            # rate, so every monetary parent scope can ultimately receive a manual price.
            if current_structure in {"installed_all_in","unpriced"}:
                v=tk.StringVar(value=("" if state.get("adopted") is None else _fmt(state.get("adopted")).replace(",","")))
                ttk.Label(w,text=self._ui("一式単価","All-in unit price")).grid(row=0,column=0,padx=6,pady=5,sticky="w");tk.Entry(w,textvariable=v,bg=INPUT_BG).grid(row=0,column=1,padx=6,pady=5)
                ttk.Label(w,text=self._ui("材料・労務・機械等の内訳を分離できない総合単価として保存します。","Saved as a combined all-in rate without inventing a material/labor/equipment split."),foreground="#8b0000").grid(row=1,column=0,columnspan=2,padx=6,pady=3,sticky="w")
                ttk.Label(w,text=currency+" / "+str(state.get("unit") or base_item.get("unit") or ""),foreground="#555").grid(row=2,column=0,columnspan=2,pady=3)
                def apply_all_in():
                    try:val=float((v.get() or "0").replace(",",""))
                    except ValueError:messagebox.showerror(self._ui("単価編集","Edit Unit Costs"),self._ui("単価は数値で入力してください。","Enter a numeric unit cost."),parent=w);return
                    if val<0:messagebox.showerror(self._ui("単価編集","Edit Unit Costs"),self._ui("単価に負数は入力できません。","Unit cost cannot be negative."),parent=w);return
                    units[key]={"unit":state.get("unit") or base_item.get("unit"),"installed_unit_cost":val,"pricing_structure":"installed_all_in","pricing_status":"user_manual_current_project_override","source_name":"Module 5 manual unit-cost edit","source_reference":"current Project session","note_ja":"現在ProjectのModule 5単価編集で一式単価を手動設定。材料・労務・機械への架空分解はしない。"}
                    state.update({"adopted":val,"components":(None,None,None),"structure":"installed_all_in","status":self._ui("手動編集・再計算待ち","Manual edit / recalc required"),"source":self._ui("現在Projectの手動編集","Current Project manual edit"),"unpriced":False})
                    vals=list(tree.item(iid,"values"));vals[5]=_fmt(val);vals[6]=_structure_text("installed_all_in");vals[7]=vals[8]=vals[9]="—";vals[10]=state["status"];vals[11]=state["source"];tree.item(iid,values=vals,tags=(("parent",) if key in group else ()));w.destroy()
                ttk.Button(w,text=t("save"),command=apply_all_in).grid(row=3,column=0,columnspan=2,pady=8)
            else:
                vals=state.get("components") or (None,None,None);vars_={k:tk.StringVar(value=("" if vv is None else _fmt(vv).replace(",",""))) for k,vv in zip(("material","labor","equipment"),vals)}
                defs=[("material",self._ui("材料内訳","Material component")),("labor",self._ui("労務内訳","Labor component")),("equipment",self._ui("機械・仮設内訳","Plant / temporary component"))]
                for r,(k,lbl) in enumerate(defs):ttk.Label(w,text=lbl).grid(row=r,column=0,padx=6,pady=5,sticky="w");tk.Entry(w,textvariable=vars_[k],bg=INPUT_BG).grid(row=r,column=1,padx=6,pady=5)
                ttk.Label(w,text=currency+" / "+str(state.get("unit") or base_item.get("unit") or ""),foreground="#555").grid(row=3,column=0,columnspan=2,pady=3)
                def apply_components():
                    try:parsed={k:float((v.get() or "0").replace(",","")) for k,v in vars_.items()}
                    except ValueError:messagebox.showerror(self._ui("単価編集","Edit Unit Costs"),self._ui("単価は数値で入力してください。","Enter numeric unit costs."),parent=w);return
                    if any(v<0 for v in parsed.values()):messagebox.showerror(self._ui("単価編集","Edit Unit Costs"),self._ui("単価に負数は入力できません。","Unit costs cannot be negative."),parent=w);return
                    units[key]={"unit":state.get("unit") or base_item.get("unit"),"material":parsed["material"],"labor":parsed["labor"],"equipment":parsed["equipment"],"pricing_structure":"component_split","pricing_status":"user_manual_current_project_override","source_name":"Module 5 manual unit-cost edit","source_reference":"current Project session","note_ja":"現在ProjectのModule 5単価編集で内訳単価を手動設定。"}
                    comps=(parsed["material"],parsed["labor"],parsed["equipment"]);adopted=sum(comps);state.update({"components":comps,"adopted":adopted,"status":self._ui("手動編集・再計算待ち","Manual edit / recalc required"),"source":self._ui("現在Projectの手動編集","Current Project manual edit"),"unpriced":False})
                    vals=list(tree.item(iid,"values"));vals[5]=_fmt(adopted);vals[6]=_structure_text("component_split");vals[7]=_fmt(comps[0]);vals[8]=_fmt(comps[1]);vals[9]=_fmt(comps[2]);vals[10]=state["status"];vals[11]=state["source"];tree.item(iid,values=vals,tags=(("parent",) if key in group else ()));w.destroy()
                ttk.Button(w,text=t("save"),command=apply_components).grid(row=4,column=0,columnspan=2,pady=8)

        bar=ttk.Frame(d);bar.pack(fill="x",padx=8,pady=(0,8))
        ttk.Button(bar,text=t("edit_unit_costs"),command=edit).pack(side="left",padx=4)
        ttk.Button(bar,text=self._ui("親単価 ⇔ 子項目積上げ","Parent rate ⇔ child roll-up"),command=toggle_parent_mode).pack(side="left",padx=4)
        ttk.Label(bar,text=self._ui("編集後は『建設費・工期を計算』で再計算してください。","Recalculate construction cost/duration after editing."),foreground="#555").pack(side="left",padx=14)

    def save_csv(self):
        if not self.result:return
        default_path=default_export_path(self.project_path,5,label="Module5_建設費内訳")
        p=filedialog.asksaveasfilename(initialdir=default_path.parent,initialfile=default_path.name,defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if not p:return
        rows=self.result["cost_lines"]
        currency=str(self.result.get("currency") or self.currency.get() or "JPY")
        export_rows=[dict(row,currency=currency,record_type="cost_line") for row in rows]
        for audit_row in ((self.result.get("quantity_cost_coverage_audit") or {}).get("rows") or []):
            export_rows.append({
                "record_type":"module1_quantity_cost_audit",
                "cost_item_key":audit_row.get("cost_item_key") or audit_row.get("parent_cost_item_key"),
                "item":audit_row.get("item"),
                "quantity":audit_row.get("quantity"),
                "unit":audit_row.get("unit"),
                "pricing_display_status":audit_row.get("status"),
                "quantity_source":audit_row.get("category"),
                "quantity_basis":audit_row.get("reason"),
                "currency":currency,
            })
        if not export_rows:
            return
        fieldnames=[]
        for row in export_rows:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)
        with open(p,"w",newline="",encoding="utf-8-sig") as f:
            writer=csv.DictWriter(f,fieldnames=fieldnames,extrasaction="ignore")
            writer.writeheader();writer.writerows(export_rows)

    def save_output(self):
        self.refresh_project_from_context()
        if self.project is None or self.project_path is None or self.result is None:
            messagebox.showwarning("Warning", self.i18n.t("save_conditions_missing"))
            return
        try:
            require_current_module_output(self.project, "module1", "Module 1")
            calculated_fp = self.result.get("upstream_module1_fingerprint")
            current_fp = module1_cost_dependency_fingerprint(self.project)
            if not calculated_fp or not current_fp or calculated_fp != current_fp:
                raise ValueError(
                    "Module 1 cost-relevant data changed after this Module 5 calculation, or this result predates the dependency fingerprint. "
                    "Recalculate Module 5 before saving."
                )
            _integrity=self.result.get("quantity_to_cost_line_integrity_audit") or {}
            if _integrity.get("status")!="pass":
                raise ValueError("Module 1 → Module 5 quantity/cost-line integrity is not PASS. Recalculate and resolve the linkage before saving.")
            _coverage=self.result.get("quantity_cost_coverage_audit") or {}
            _monetary_gaps=int(_coverage.get("monetary_gap_count",0) or 0)
            _unpriced=len(self.result.get("unpriced_cost_lines") or [])
            if _monetary_gaps>0 or _unpriced>0 or bool(self.result.get("construction_cost_is_partial")):
                _proceed=messagebox.askyesno(
                    "警告" if self.i18n.language=="ja" else "Warning",
                    (
                        f"建設費が未完成です(数量-金額未接続={_monetary_gaps}件、未単価行={_unpriced}件)。\n"
                        "これらの項目は総額・㎡単価に含まれず、暫定・想定区分のまま後段(Evaluation/Compare等)へ引き継がれます。\n"
                        "このまま暫定結果として保存しますか?"
                        if self.i18n.language=="ja" else
                        f"Construction cost is incomplete (monetary gaps={_monetary_gaps}, unpriced cost lines={_unpriced}).\n"
                        "These items are excluded from the total/unit cost and will be carried forward as provisional to downstream modules (Evaluation/Compare, etc.).\n"
                        "Save as a provisional result anyway?"
                    ),
                )
                if not _proceed:
                    return
            self.result["_user_notes"] = dict(self.user_notes)
            # Stable interfaces for downstream comparison/audit.
            self.result["trade_material_breakdown"] = list(self.result.get("cost_lines",[]))
            self.result["quantity_source_register"] = dict(self.result.get("quantity_provenance",{}))
            self.result["method_screening_exclusions"] = list(self.result.get("excluded_quantities",[]))
            report = update_module_and_propagate(
                self.project,
                self.project_path,
                "module5",
                self.result,
                {
    "location": self.location.get(),
    "settings": self.settings(),
    "equipment_selection": self.equipment_selection(),
    "custom_conditions": list(self.custom_conditions),
    "condition_matrix": self.condition_matrix,
    "ai_cost_provider_overlay": self._current_ai_cost_overlay(),
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
