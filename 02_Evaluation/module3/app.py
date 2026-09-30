
from __future__ import annotations
from core.csv_export import write_dict_rows_csv
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from core.i18n import I18N, LANGUAGE_OPTIONS
from core.error_text import friendly_exception_text
from core.ui_style import (apply_common_style, standardize_module_window, create_scrollable_module_page, add_module_text_copy_button)
from core.module_report_ui import attach_module_report_button
from core.project_store import load_project
from core.project_coordinator import update_module_and_propagate, format_report
from services.renewal_scenario_engine_v9_2 import generate_scenario
from services.project_export_paths import default_export_path

INPUT_BG="#fff4b8"
AUTO_BG="#d9efff"
RESULT_BG="#dff3df"


def _detect_profile_from_project(project, profile_db):
    """Return the lifecycle profile that matches the selected construction method.

    Common construction identifiers are authoritative.  Older Module 1 files may
    contain the legacy default ``selected_building_profile = AZRAS`` even for a
    2×6 or RC project, which previously caused the wrong 200-year scenario.
    """
    common = (project or {}).get("common") or {}
    method_id = str(common.get("construction_method_id") or "").strip().lower()
    detail_id = str(common.get("construction_method_detail_id") or "").strip().lower()
    building_system = str(((common.get("detailed_configuration") or {}).get("building_system") or "")).strip().lower()
    general = ((common.get("detailed_configuration") or {}).get("general") or {})
    structure = str(general.get("structure") or "").strip().lower()
    method = str(general.get("method") or "").strip().lower()
    tokens = " ".join((method_id, detail_id, building_system, structure, method))

    candidates = []
    if "azras" in tokens:
        candidates.append("AZRAS")
    if any(x in tokens for x in ("2x6", "2×6", "wood_frame", "timber")):
        candidates.append("2x6 Timber")
    if any(x in tokens for x in ("rc_wall", "wall_rc", "wall-type")):
        candidates.append("RC Wall")
    if any(x in tokens for x in ("rc_frame", "conventional_rc", "moment_frame")):
        candidates.append("RC Frame")
    if any(x in tokens for x in ("steel_frame", "steel")):
        candidates.append("Steel Frame")
    if any(x in tokens for x in ("clt", "mass_timber")):
        candidates.append("CLT / Mass Timber")

    profiles = (profile_db or {}).get("profiles", {})
    for candidate in candidates:
        if candidate in profiles:
            return candidate

    legacy = ((project or {}).get("module_outputs", {}).get("module1") or {}).get("selected_building_profile")
    return legacy if legacy in profiles else None

class Module3App(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language: str = "ja", project_context=None):
        super().__init__(master)
        apply_common_style(self)
        standardize_module_window(self,3)
        self.project_context = project_context
        self.root_dir=Path(root_dir)
        self.i18n=I18N(self.root_dir,language)
        self.project=None
        self.project_path=None
        self.result=None
        self.project_file=tk.StringVar()
        self.profile_key=tk.StringVar(value="AZRAS")
        self.period=tk.StringVar(value="200")
        self.keep_same=tk.BooleanVar(value=True)
        self.layout_policy=tk.StringVar(value="adaptive")
        self.rebuild_cycle=tk.StringVar(value="0")
        self.rebuild_basis_text=tk.StringVar(value="")
        self.component_db=json.loads(
            (self.root_dir/"data"/"component_life_database_v9_2.json")
            .read_text(encoding="utf-8"))
        self.profile_db=json.loads(
            (self.root_dir/"data"/"construction_scenario_profiles_v9_2.json")
            .read_text(encoding="utf-8"))
        if self.project_context is not None and self.project_context.path is not None:
            self.project = self.project_context.reload()
            self.project_path = self.project_context.path
            self.project_file.set(self.project_context.display_path)
        self.title(self.i18n.t("module3"))
        self.build();attach_module_report_button(self,3)
        self.restore_saved_state()
        if self.project is not None:
            detected = _detect_profile_from_project(self.project, self.profile_db)
            if detected:
                self.profile_key.set(detected)
                if not self.result:
                    self._apply_profile_rebuild_default()
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
        detected = _detect_profile_from_project(self.project, self.profile_db)
        if detected and self.profile_key.get() != detected:
            self.profile_key.set(detected)
            saved = (self.project or {}).get("module_outputs", {}).get("module3") or {}
            snapshot = saved.get("_input_snapshot") or {}
            if snapshot.get("rebuild_cycle_years") is None:
                self._apply_profile_rebuild_default()
        return True

    def _profile_default_rebuild_cycle(self, profile_key=None):
        key = profile_key or self.profile_key.get()
        profile = self.profile_db.get("profiles", {}).get(key, {})
        return max(int(profile.get("default_rebuild_cycle_years", 0) or 0), 0)

    def _profile_rebuild_basis(self, profile_key=None):
        key = profile_key or self.profile_key.get()
        profile = self.profile_db.get("profiles", {}).get(key, {})
        field = "rebuild_cycle_basis_ja" if self.i18n.language == "ja" else "rebuild_cycle_basis_en"
        return str(profile.get(field, "Evaluation standard scenario"))

    def _profile_rebuild_editable(self, profile_key=None):
        key = profile_key or self.profile_key.get()
        profile = self.profile_db.get("profiles", {}).get(key, {})
        return bool(profile.get("rebuild_cycle_editable", key != "AZRAS"))

    def _update_rebuild_basis_display(self, source="profile_default"):
        if not hasattr(self, "rebuild_basis_text"):
            return
        if source == "user_input":
            text = "ユーザー設定値" if self.i18n.language == "ja" else "User-defined value"
        else:
            text = self._profile_rebuild_basis()
        self.rebuild_basis_text.set(text)

    def _apply_profile_rebuild_default(self, event=None):
        key = self.profile_key.get()
        self.rebuild_cycle.set(str(self._profile_default_rebuild_cycle(key)))
        if hasattr(self, "rebuild_cycle_entry"):
            self.rebuild_cycle_entry.configure(state="normal" if self._profile_rebuild_editable(key) else "disabled")
        self._update_rebuild_basis_display("profile_default")

    def build(self):
        for w in self.winfo_children():
            w.destroy()
        page=create_scrollable_module_page(self)
        t=self.i18n.t

        top=ttk.Frame(page)
        top.pack(fill="x",padx=10,pady=6)
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
            top, text=t("save_module3"), command=self.save_output
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_scenario_csv"), command=self.save_csv
        ).pack(side="right", padx=4)

        project=ttk.LabelFrame(page,text=t("project"))
        project.pack(fill="x",padx=10,pady=5)
        ttk.Label(project,text=t("project_json")).grid(row=0,column=0,padx=5,pady=4)
        tk.Entry(project,textvariable=self.project_file,width=105,state="readonly",readonlybackground=AUTO_BG).grid(
            row=0,column=1,padx=5,pady=4,sticky="ew")
        project.columnconfigure(1,weight=1)

        conditions=ttk.LabelFrame(page,text=t("scenario_conditions"))
        conditions.pack(fill="x",padx=10,pady=5)
        ttk.Label(conditions,text=t("construction_system")).grid(row=0,column=0,padx=5,pady=5)
        profile_cb=ttk.Combobox(conditions,textvariable=self.profile_key,
                     values=list(self.profile_db["profiles"].keys()),
                     state="readonly",width=25)
        profile_cb.grid(row=0,column=1,padx=5,pady=5)
        profile_cb.bind("<<ComboboxSelected>>", self._apply_profile_rebuild_default)
        ttk.Label(conditions,text=t("analysis_period")).grid(row=0,column=2,padx=5,pady=5)
        tk.Entry(conditions,textvariable=self.period,bg=INPUT_BG,width=10).grid(
            row=0,column=3,padx=5,pady=5)
        ttk.Checkbutton(conditions,text=t("same_use_scale"),
                        variable=self.keep_same).grid(row=0,column=4,padx=12,pady=5)

        ttk.Label(
            conditions,
            text=("全面建替え周期（年、0=なし）" if self.i18n.language=="ja" else "Full rebuild cycle (years, 0=none)")
        ).grid(row=1,column=0,padx=5,pady=5)
        self.rebuild_cycle_entry=tk.Entry(conditions,textvariable=self.rebuild_cycle,bg=INPUT_BG,width=12)
        self.rebuild_cycle_entry.grid(row=1,column=1,padx=5,pady=5,sticky="w")
        ttk.Label(
            conditions,
            text=("標準値の根拠：" if self.i18n.language=="ja" else "Default basis:")
        ).grid(row=1,column=2,padx=(10,2),pady=5,sticky="e")
        ttk.Label(
            conditions,
            textvariable=self.rebuild_basis_text,
            foreground="#555555"
        ).grid(row=1,column=3,columnspan=2,padx=5,pady=5,sticky="w")

        ttk.Label(conditions,text=t("layout_policy")).grid(row=2,column=0,padx=5,pady=5)
        values=["adaptive","accessibility","flexible"]
        labels={
            "adaptive":t("layout_adaptive"),
            "accessibility":t("layout_accessibility"),
            "flexible":t("layout_flexible")
        }
        self.layout_label_to_key={v:k for k,v in labels.items()}
        display=tk.StringVar(value=labels[self.layout_policy.get()])
        layout_cb=ttk.Combobox(conditions,textvariable=display,
                               values=list(labels.values()),state="readonly",width=55)
        layout_cb.grid(row=2,column=1,columnspan=3,padx=5,pady=5,sticky="w")
        layout_cb.bind("<<ComboboxSelected>>",
                       lambda e:self.layout_policy.set(self.layout_label_to_key[display.get()]))
        ttk.Button(conditions,text=t("edit_component_life"),
                   command=self.edit_component_lives).grid(row=2,column=4,padx=8,pady=5)

        ttk.Label(page,text=t("same_use_scale_note"),foreground="#8b0000",
                  wraplength=1480).pack(fill="x",padx=12,pady=(3,1))
        ttk.Label(page,text=t("scenario_notice"),foreground="#8b0000",
                  wraplength=1480).pack(fill="x",padx=12,pady=1)
        ttk.Label(page,text=t("scenario_provisional"),foreground="#8b0000",
                  wraplength=1480).pack(fill="x",padx=12,pady=(1,4))

        ttk.Button(page,text=t("generate_scenario"),command=self.generate).pack(pady=6,ipady=5)

        body=ttk.Panedwindow(page,orient="horizontal")
        body.pack(fill="both",expand=True,padx=10,pady=5)
        timeline=ttk.LabelFrame(body,text=t("scenario_timeline"))
        summary=ttk.LabelFrame(body,text=t("scenario_summary"))
        body.add(timeline,weight=4)
        body.add(summary,weight=1)

        cols=("year","action","component","scope","retained","removed","reused","recycled","layout")
        self.tree=ttk.Treeview(timeline,columns=cols,show="headings")
        headings={
            "year":t("year"),"action":t("action"),"component":t("component"),
            "scope":t("scope"),"retained":t("retained"),"removed":t("removed"),
            "reused":t("reused"),"recycled":t("recycled"),"layout":t("layout_change")
        }
        widths={"year":65,"action":135,"component":240,"scope":75,"retained":90,
                "removed":90,"reused":90,"recycled":100,"layout":390}
        for col in cols:
            self.tree.heading(col,text=headings[col])
            self.tree.column(col,width=widths[col],anchor="w")
        y=ttk.Scrollbar(timeline,orient="vertical",command=self.tree.yview)
        x=ttk.Scrollbar(timeline,orient="horizontal",command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        self.tree.grid(row=0,column=0,sticky="nsew")
        y.grid(row=0,column=1,sticky="ns")
        x.grid(row=1,column=0,sticky="ew")
        timeline.rowconfigure(0,weight=1)
        timeline.columnconfigure(0,weight=1)

        self.summary_text=tk.Text(summary,bg=RESULT_BG,wrap="word",width=38)
        self.summary_text.pack(fill="both",expand=True,padx=6,pady=6)
        self.rebuild_cycle_entry.configure(
            state="normal" if self._profile_rebuild_editable() else "disabled"
        )
        self._update_rebuild_basis_display("profile_default")


    def restore_saved_state(self):
        if self.project is None:
            return
        saved = self.project.get("module_outputs", {}).get("module3") or {}
        if not isinstance(saved, dict) or not saved:
            return
        snapshot = saved.get("_input_snapshot") or {}
        profile = snapshot.get("profile_key") or saved.get("construction_profile")
        if profile in self.profile_db.get("profiles", {}):
            self.profile_key.set(profile)
        if snapshot.get("period") is not None:
            self.period.set(str(snapshot["period"]))
        elif saved.get("period_years") is not None:
            self.period.set(str(saved["period_years"]))
        if snapshot.get("layout_policy") is not None:
            self.layout_policy.set(str(snapshot["layout_policy"]))
        if snapshot.get("keep_same") is not None:
            self.keep_same.set(bool(snapshot["keep_same"]))
        saved_rebuild = saved.get("rebuild_cycle") or {}
        saved_source = saved_rebuild.get("source", "profile_default")
        current_default = self._profile_default_rebuild_cycle(profile)

        # PATCH 077 / PATCH 088 — profile-default migration:
        # Historical project JSONs may retain former defaults (e.g. 2×6=50,
        # RC Frame=100). A saved profile-default value follows the CURRENT
        # profile definition (PATCH 088: RC Frame=90 years).
        # Only an explicit Module 3 user input is preserved across profile revisions.
        if saved_source == "module3_user_input":
            if snapshot.get("rebuild_cycle_years") is not None:
                self.rebuild_cycle.set(str(snapshot["rebuild_cycle_years"]))
            elif saved_rebuild.get("applied_cycle_years") is not None:
                self.rebuild_cycle.set(str(saved_rebuild["applied_cycle_years"]))
            else:
                self.rebuild_cycle.set(str(current_default))
        else:
            self.rebuild_cycle.set(str(current_default))

        if hasattr(self, "rebuild_cycle_entry"):
            self.rebuild_cycle_entry.configure(
                state="normal" if self._profile_rebuild_editable() else "disabled"
            )
        self._update_rebuild_basis_display(
            "user_input" if saved_source == "module3_user_input" else "profile_default"
        )
        self.result = saved
        try:
            self.show_result()
        except Exception:
            pass

    def change_language(self,language):
        self.i18n.set_language(language)
        self.title(self.i18n.t("module3"))
        self.build();attach_module_report_button(self,3)
        if self.result:
            self.show_result()

    def choose_project(self):
        p=filedialog.askopenfilename(
            initialdir=self.root_dir/"projects",filetypes=[("JSON","*.json")])
        if not p:return
        try:
            project=load_project(p)
            if not project.get("module_outputs",{}).get("module1"):
                raise ValueError(self.i18n.t("module1_required_m3"))
            self.project=project
            self.project_path=Path(p)
            self.project_file.set(p)
            detected = _detect_profile_from_project(project, self.profile_db)
            if detected:
                self.profile_key.set(detected)
                self._apply_profile_rebuild_default()
        except Exception as exc:
            messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language))

    def generate(self):
        if self.project is None:
            messagebox.showwarning("Warning",self.i18n.t("module1_required_m3"))
            return
        try:
            detected = _detect_profile_from_project(self.project, self.profile_db)
            if detected:
                self.profile_key.set(detected)
            period=int(float(self.period.get()))

            # PATCH 077 / PATCH 088 — do not let an obsolete saved profile
            # default override the current profile definition
            # (2×6=60 years, RC Frame=90 years).
            loaded_source = ((self.result or {}).get("rebuild_cycle") or {}).get(
                "source", "profile_default"
            )
            if loaded_source != "module3_user_input":
                self.rebuild_cycle.set(
                    str(self._profile_default_rebuild_cycle(self.profile_key.get()))
                )

            rebuild_cycle=int(float(self.rebuild_cycle.get()))
            if rebuild_cycle < 0:
                raise ValueError("全面建替え周期は0以上で入力してください。")
            if not self._profile_rebuild_editable():
                rebuild_cycle=self._profile_default_rebuild_cycle()
                self.rebuild_cycle.set(str(rebuild_cycle))
            self.result=generate_scenario(
                self.project,self.component_db,self.profile_db,
                self.profile_key.get(),period,self.i18n.language,
                self.layout_policy.get(),self.keep_same.get(),
                rebuild_cycle
            )
            default_cycle = self._profile_default_rebuild_cycle()
            if self._profile_rebuild_editable() and rebuild_cycle != default_cycle:
                self.result["rebuild_cycle"]["source"] = "module3_user_input"
                self.result["rebuild_cycle"]["basis"] = (
                    "ユーザー設定値" if self.i18n.language=="ja" else "User-defined value"
                )
                self._update_rebuild_basis_display("user_input")
            else:
                self.result["rebuild_cycle"]["source"] = "profile_default" if self.profile_key.get()!="AZRAS" else "AZRAS_no_full_rebuild"
                self.result["rebuild_cycle"]["basis"] = self._profile_rebuild_basis()
                self._update_rebuild_basis_display("profile_default")
            self.show_result()
            messagebox.showinfo("OK",self.i18n.t("scenario_complete"))
        except Exception as exc:
            messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language))

    # PATCH_635: previously the Treeview showed e["component"] verbatim,
    # which was baked in whatever language was active when generate_scenario()
    # last ran. If the scenario was generated in English and the UI is later
    # switched to Japanese (or vice versa), the timeline kept showing the
    # stale-language text until "シナリオ自動生成" was re-run. Every event
    # already carries a language-independent "component_key", so re-derive
    # the display name from component_db in the CURRENT UI language instead.
    _SPECIAL_COMPONENT_NAMES = {
        "all_infill": ("全インフィル", "All Infill"),
        "whole_building": ("建物全体", "Whole Building"),
    }

    def _component_display_name(self, event):
        key = event.get("component_key")
        ja = self.i18n.language == "ja"
        special = self._SPECIAL_COMPONENT_NAMES.get(key)
        if special:
            return special[0] if ja else special[1]
        comp = (self.component_db.get("components") or {}).get(key)
        if comp:
            return str(comp.get("ja" if ja else "en", "") or event.get("component", ""))
        # No key (older saved JSON) or unknown key: fall back to whatever
        # text was stored, rather than showing a blank cell.
        return event.get("component", "")

    def show_result(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        t=self.i18n.t
        action_labels={
            "inspection":t("inspection"),"repair":t("repair"),
            "replace_equipment":t("replace_equipment"),
            "replace_infill":t("replace_infill"),
            "skeleton_repair":t("skeleton_repair"),
            "full_rebuild":t("full_rebuild"),
            "partial_demolition":t("partial_demolition"),
            "retain_skeleton":t("retain_skeleton")
        }
        for e in self.result["events"]:
            self.tree.insert("", "end", values=(
                e["year"],action_labels.get(e["action"],e["action"]),
                self._component_display_name(e),t("all") if e["scope"]=="all" else t("partial"),
                f'{e["retained_fraction"]*100:.0f}%',
                f'{e["removed_fraction"]*100:.0f}%',
                f'{e["reused_fraction"]*100:.0f}%',
                f'{e["recycled_fraction"]*100:.0f}%',
                e.get("layout_change","")
            ))
        s=self.result["summary"]
        lines=[
            f'{t("construction_system")}: {self.result["construction_profile"]}',
            f'{t("analysis_period")}: {self.result["period_years"]}',
            ("全面建替え周期: " if self.i18n.language=="ja" else "Full rebuild cycle: ")
                + (("なし" if self.i18n.language=="ja" else "None") if self.result.get("rebuild_cycle",{}).get("applied_cycle_years",0)==0
                   else f'{self.result.get("rebuild_cycle",{}).get("applied_cycle_years")} 年'),
            ("建替え周期の根拠: " if self.i18n.language=="ja" else "Rebuild-cycle basis: ")
                + str(self.result.get("rebuild_cycle",{}).get("basis","")),
            f'{t("events_count")}: {s["events_count"]:,}',
            f'{t("equipment_updates")}: {s["equipment_updates"]:,}',
            f'{t("infill_updates")}: {s["infill_updates"]:,}',
            f'{t("skeleton_repairs")}: {s["skeleton_repairs"]:,}',
            f'{t("full_rebuilds")}: {s["full_rebuilds"]:,}',
            f'{t("retained_fraction")}: {s["final_skeleton_retained_fraction"]*100:.0f}%',
            "",
            t("same_use_scale_note")
        ]
        self.summary_text.delete("1.0","end")
        self.summary_text.insert("1.0","\n".join(lines))

    def edit_component_lives(self):
        dialog=tk.Toplevel(self)
        dialog.title(self.i18n.t("component_life"))
        dialog.geometry("1160x650")
        t=self.i18n.t
        cols=("component","inspection","repair","renewal","reuse","recycle")
        tree=ttk.Treeview(dialog,columns=cols,show="headings")
        labels={
            "component":t("component"),"inspection":t("inspection_cycle"),
            "repair":t("repair_cycle"),"renewal":t("renewal_cycle"),
            "reuse":t("reuse_fraction"),"recycle":t("recycle_fraction")
        }
        for c in cols:
            tree.heading(c,text=labels[c])
            tree.column(c,width=250 if c=="component" else 140,anchor="w")
        tree.pack(fill="both",expand=True,padx=8,pady=8)
        keys=[]
        lang="ja" if self.i18n.language=="ja" else "en"
        for key,item in self.component_db["components"].items():
            keys.append(key)
            tree.insert("", "end", iid=key, values=(
                item[lang],item["inspection_years"],item["repair_years"],
                item["renewal_years"],item["reusable_fraction"],
                item["recyclable_fraction"]
            ))
        def edit():
            sel=tree.selection()
            if not sel:return
            key=sel[0]
            item=self.component_db["components"][key]
            d=tk.Toplevel(dialog)
            d.title(item[lang])
            vars_={
                "inspection_years":tk.StringVar(value=str(item["inspection_years"])),
                "repair_years":tk.StringVar(value=str(item["repair_years"])),
                "renewal_years":tk.StringVar(value=str(item["renewal_years"])),
                "reusable_fraction":tk.StringVar(value=str(item["reusable_fraction"])),
                "recyclable_fraction":tk.StringVar(value=str(item["recyclable_fraction"]))
            }
            labels2=[
                ("inspection_years",t("inspection_cycle")),
                ("repair_years",t("repair_cycle")),
                ("renewal_years",t("renewal_cycle")),
                ("reusable_fraction",t("reuse_fraction")),
                ("recyclable_fraction",t("recycle_fraction"))
            ]
            for r,(k,lbl) in enumerate(labels2):
                ttk.Label(d,text=lbl).grid(row=r,column=0,padx=6,pady=5)
                tk.Entry(d,textvariable=vars_[k],bg=INPUT_BG).grid(row=r,column=1,padx=6,pady=5)
            def apply():
                for k,v in vars_.items():
                    item[k]=float(v.get()) if "fraction" in k else int(float(v.get()))
                tree.item(key,values=(item[lang],item["inspection_years"],item["repair_years"],
                                      item["renewal_years"],item["reusable_fraction"],
                                      item["recyclable_fraction"]))
                d.destroy()
            ttk.Button(d,text=t("save"),command=apply).grid(row=6,column=0,columnspan=2,pady=8)
        ttk.Button(dialog,text=t("edit_component_life"),command=edit).pack(pady=6)

    def save_csv(self):
        if not self.result:
            return
        if self.project_path is None:
            messagebox.showwarning("Warning", self.i18n.t("save_conditions_missing"))
            return
        default_path = default_export_path(
            self.project_path,
            3,
            label="Module3_タイムライン",
        )
        p = filedialog.asksaveasfilename(
            parent=self,
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not p:
            return
        # PATCH_014: the CSV follows the UI language (header, action, scope and
        # component names in Japanese); English output is unchanged.
        fields=["event_id","year","action","component_key","component","scope",
                "retained_fraction","removed_fraction","reused_fraction",
                "recycled_fraction","layout_change","basis"]
        t=self.i18n.t
        write_dict_rows_csv(
            p,self.result["events"],self.i18n.language,fields=fields,
            localizers={
                "action":lambda v,_row:t(str(v)) if t(str(v))!=str(v) else v,
                "scope":lambda v,_row:t(str(v)) if str(v) in ("all","partial") else v,
                "component":lambda _v,row:self._component_display_name(row),
            },
        )

    def save_output(self):
        self.refresh_project_from_context()
        if self.project is None or self.project_path is None or self.result is None:
            messagebox.showwarning("Warning", self.i18n.t("save_conditions_missing"))
            return
        try:
            report = update_module_and_propagate(
                self.project,
                self.project_path,
                "module3",
                self.result,
                {
    "profile_key": self.profile_key.get(),
    "period": int(float(self.period.get())),
    "layout_policy": self.layout_policy.get(),
    "keep_same": self.keep_same.get(),
    "rebuild_cycle_years": int(float(self.rebuild_cycle.get())),
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
