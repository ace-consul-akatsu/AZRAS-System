from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.project_store import load_project, save_project
from core.error_text import friendly_exception_text
from services.construction_feasibility_screening import screen_construction_methods
from screening.physical_constructability import evaluate_physical_constructability


class ConstructionMethodScreeningApp(tk.Toplevel):
    """Run the Planning Basic primary method screen and the detailed physical secondary screen."""

    def __init__(self, master, root_dir: Path, language: str = "ja", project_context=None):
        super().__init__(master)
        self.root_dir = Path(root_dir)
        self.language = language
        self.project_context = project_context
        self.project: dict | None = None
        self.project_path: Path | None = None
        self.primary_result: dict | None = None
        self.secondary_result: dict | None = None
        self.title(self._t("工法候補 一次・二次診断", "Construction Method Primary & Secondary Screening"))
        self.geometry("1180x790")
        self.minsize(980, 680)
        self._load_context()
        self._build()
        self._refresh_project_label()
        if self.project:
            self._show_existing_primary()

    def _t(self, ja: str, en: str) -> str:
        return ja if self.language == "ja" else en

    def _apply_global_language(self, language: str) -> None:
        self.language = "ja" if language == "ja" else "en"
        self.title(self._t("工法候補 一次・二次診断", "Construction Method Primary & Secondary Screening"))
        for child in list(self.winfo_children()):
            if isinstance(child, tk.Toplevel):
                continue
            child.destroy()
        self._build()
        self._refresh_project_label()
        if self.project:
            self._show_existing_primary()

    def _primary_status_text(self, value: str | None) -> str:
        value = str(value or "Unknown")
        if self.language != "ja":
            return value
        return {
            "Candidate": "候補",
            "Conditional": "条件付き候補",
            "Excluded": "除外",
            "Unknown": "未判定",
        }.get(value, value)

    def _load_context(self) -> None:
        if self.project_context is None:
            return
        if self.project_context.path is not None:
            self.project = self.project_context.synchronize_from_disk()
            self.project_path = self.project_context.path
        elif self.project_context.project is not None:
            self.project = self.project_context.project

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=(16, 14))
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text=self._t("2. 工法候補 一次・二次診断", "2. Construction Method Primary & Secondary Screening"),
            font=("Yu Gothic UI", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=self._t(
                "一次診断で地域・法規・災害条件から工法候補を絞り、二次診断で生コン・道路・港湾・重機・技能者など物理施工性を確認します。",
                "Primary screening narrows construction-method candidates using regional, regulatory and hazard conditions; secondary screening checks physical constructability such as ready-mix supply, roads, ports, heavy equipment and skilled labor.",
            ),
            wraplength=1120,
            foreground="#555555",
        ).pack(fill="x", pady=(2, 10))

        pbox = ttk.LabelFrame(outer, text=self._t("対象Project JSON", "Project JSON"), padding=(10, 8))
        pbox.pack(fill="x", pady=(0, 10))
        ttk.Button(pbox, text=self._t("Project JSONを開く", "Open Project JSON"), command=self.open_project).pack(side="left")
        self.project_label = ttk.Label(pbox, text="", wraplength=900)
        self.project_label.pack(side="left", fill="x", expand=True, padx=12)

        action = ttk.Frame(outer)
        action.pack(fill="x", pady=(0, 10))
        ttk.Button(
            action,
            text=self._t("① 一次診断を実行", "① Run Primary Screening"),
            command=self.run_primary,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            action,
            text=self._t("② 二次診断を開く", "② Open Secondary Screening"),
            command=self.open_secondary,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            action,
            text=self._t("Project JSONへ保存", "Save to Project JSON"),
            command=self.save_to_project,
        ).pack(side="left")

        self.summary_label = ttk.Label(outer, text=self._t("一次診断：未実行", "Primary screening: not run"), foreground="#555555")
        self.summary_label.pack(fill="x", pady=(0, 6))

        table = ttk.LabelFrame(outer, text=self._t("一次診断結果", "Primary Screening Result"), padding=(5, 5))
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("method", "status", "reason"), show="headings")
        self.tree.heading("method", text=self._t("工法", "Method"))
        self.tree.heading("status", text=self._t("一次判定", "Primary"))
        self.tree.heading("reason", text=self._t("理由", "Reason"))
        self.tree.column("method", width=220, anchor="w")
        self.tree.column("status", width=130, anchor="center")
        self.tree.column("reason", width=760, anchor="w")
        y = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y.set)
        self.tree.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")
        ttk.Label(
            outer,
            text=self._t(
                "※ 診断は企画段階の候補整理です。Unknownは不可を意味せず、現地法規・供給者・物流条件の確認が必要です。",
                "Planning-stage screening only. Unknown does not mean unavailable; local regulations, suppliers and logistics still require confirmation.",
            ),
            foreground="#8b0000",
            wraplength=1120,
        ).pack(fill="x", pady=(8, 0))

    def _refresh_project_label(self) -> None:
        if self.project_path:
            text = str(self.project_path)
        elif self.project:
            text = self._t("Module 0の未保存Projectを使用中", "Using unsaved Module 0 project")
        else:
            text = self._t("未選択：先に1. 建築企画・基本条件でProjectを作成するか、JSONを開いてください。", "Not selected: create a project in 1. Project Planning or open a JSON file.")
        self.project_label.config(text=text)

    def open_project(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title=self._t("Project JSONを開く", "Open Project JSON"),
            filetypes=[("Project JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            project = load_project(path)
        except Exception as exc:
            messagebox.showerror(self._t("Project読込エラー", "Project Load Error"), friendly_exception_text(exc,self.language), parent=self)
            return
        self.project = project
        self.project_path = Path(path)
        if self.project_context is not None:
            self.project_context.set(self.project_path, self.project)
        self.primary_result = None
        self.secondary_result = None
        self._refresh_project_label()
        self._show_existing_primary()

    def _coordinates(self) -> tuple[float, float]:
        if not self.project:
            raise ValueError(self._t("Projectが選択されていません。", "No project is selected."))
        common = self.project.get("common") or {}
        loc = common.get("location") or {}
        lat = loc.get("latitude", common.get("latitude"))
        lon = loc.get("longitude", common.get("longitude"))
        if lat in (None, "") or lon in (None, ""):
            raise ValueError(self._t("緯度・経度がありません。先に1. 建築企画・基本条件で座標を設定してください。", "Latitude/longitude are missing. Set coordinates in 1. Project Planning first."))
        return float(lat), float(lon)

    def _show_existing_primary(self) -> None:
        if not self.project:
            return
        result = (self.project.get("common") or {}).get("construction_feasibility_screening")
        if isinstance(result, dict) and result:
            self.primary_result = result
            self._render_primary(result)

    def run_primary(self) -> None:
        try:
            lat, lon = self._coordinates()
            result = screen_construction_methods(self.root_dir, lat, lon, self.project)
            self.project.setdefault("common", {})["construction_feasibility_screening"] = result
            self.primary_result = result
            if self.project_context is not None:
                self.project_context.project = self.project
            self._render_primary(result)
        except Exception as exc:
            messagebox.showerror(self._t("一次診断エラー", "Primary Screening Error"), friendly_exception_text(exc,self.language), parent=self)

    def _render_primary(self, result: dict) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for row in result.get("methods") or []:
            reasons = row.get("reasons_ja") if self.language == "ja" else row.get("reasons_en")
            self.tree.insert("", "end", values=(
                row.get("label_ja") if self.language == "ja" else row.get("label_en"),
                self._primary_status_text(row.get("status")),
                " / ".join(reasons or []),
            ))
        counts = result.get("counts") or {}
        evidence = result.get("local_construction_evidence") or {}
        city = evidence.get("nearest_reference_city") or "—"
        distance = evidence.get("distance_km")
        dist = "—" if distance is None else f"{float(distance):,.0f} km"
        order = ("Candidate", "Conditional", "Excluded", "Unknown")
        self.summary_label.config(text=(
            " | ".join(f"{self._primary_status_text(k)}: {counts.get(k, 0)}" for k in order)
            + f" | {self._t('参照地域', 'Reference')}: {city} / {dist}"
        ))

    def open_secondary(self) -> None:
        if not self.project:
            messagebox.showwarning(self._t("Project未選択", "No Project"), self._t("先にProjectを選択してください。", "Select a project first."), parent=self)
            return
        if not self.primary_result:
            self.run_primary()
        if self.primary_result:
            PhysicalConstructabilityWindow(self, self.project, str(self.project_path or ""), self.language, self._accept_secondary)

    def _accept_secondary(self, result: dict) -> None:
        self.secondary_result = result
        if self.project is not None:
            self.project.setdefault("common", {})["physical_constructability_screening"] = result
            if self.project_context is not None:
                self.project_context.project = self.project

    def save_to_project(self) -> None:
        if not self.project:
            messagebox.showwarning(self._t("Project未選択", "No Project"), self._t("保存対象のProjectがありません。", "There is no project to save."), parent=self)
            return
        if not self.project_path:
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", filetypes=[("Project JSON", "*.json")])
            if not path:
                return
            self.project_path = Path(path)
        try:
            save_project(self.project, self.project_path, saved_by="AZRAS Planning / Method Screening")
            if self.project_context is not None:
                self.project_context.set(self.project_path, self.project)
            self._refresh_project_label()
            messagebox.showinfo(self._t("保存完了", "Saved"), str(self.project_path), parent=self)
        except Exception as exc:
            messagebox.showerror(self._t("保存エラー", "Save Error"), friendly_exception_text(exc,self.language), parent=self)


class PhysicalConstructabilityWindow(tk.Toplevel):
    def __init__(self, master, project_data: dict, source_path: str = "", language: str = "ja", on_result=None):
        super().__init__(master)
        self.project_data = project_data
        self.source_path = source_path
        self.language = language
        self.on_result = on_result
        self.result = None
        self.title(self._t("AZRAS Planning — 二次診断・物理施工性", "AZRAS Planning — Secondary Physical Constructability"))
        self.geometry("1180x760")
        self.minsize(980, 650)
        default_override = "自動" if self.language == "ja" else "Auto"
        self.overrides = {k: tk.StringVar(value=default_override) for k in ("ready_mix", "road_access", "port_access", "heavy_equipment", "skilled_labor")}
        self.online = tk.BooleanVar(value=True)
        self._build()
        self.run_evaluation()

    def _t(self, ja: str, en: str) -> str:
        return ja if self.language == "ja" else en

    def _primary_status_text(self, value: str | None) -> str:
        value = str(value or "Unknown")
        if self.language != "ja":
            return value
        return {
            "Candidate": "候補",
            "Conditional": "条件付き候補",
            "Excluded": "除外",
            "Unknown": "未判定",
        }.get(value, value)

    def _secondary_status_text(self, value: str | None) -> str:
        value = str(value or "Unknown")
        if self.language != "ja":
            return value
        return {
            "Feasible": "施工可能",
            "Conditional": "条件付き施工可能",
            "Difficult": "施工困難",
            "Unknown": "未判定",
            "Excluded": "除外",
        }.get(value, value)

    def _dimension_status_text(self, value: str | None) -> str:
        value = str(value or "Unknown")
        if self.language != "ja":
            return value
        return {
            "Confirmed": "確認済",
            "Evidence": "直接証拠あり",
            "Proxy": "代替判定",
            "Conditional": "条件付き",
            "Unavailable": "利用不可",
            "Unknown": "未確認",
        }.get(value, value)

    def _reason_text(self, reason: str) -> str:
        if self.language != "ja":
            return reason
        return {
            "01 regulatory/administrative screening already marked this method Excluded": "一次診断の法規・行政条件で、すでにこの工法は除外と判定されています。",
            "one or more required physical resources/access conditions are confirmed unavailable": "必要な施工資源またはアクセス条件のうち、1項目以上が利用不可と確認されています。",
            "all required physical dimensions have direct/confirmed evidence": "必要な物理的施工条件のすべてについて、直接証拠または確認済み情報があります。",
            "one or more required dimensions remain unverified": "必要な施工条件のうち、1項目以上が未確認です。",
            "available evidence is proxy/conditional rather than direct confirmation": "利用可能な情報は代替情報または条件付き情報であり、直接確認には至っていません。",
            "01 preliminary screening remains Conditional, so physical evidence alone cannot clear the method": "一次診断が条件付き候補のため、物理施工性の証拠だけでは施工可能とは確定できません。",
        }.get(reason, reason)

    def _override_values(self) -> tuple[str, ...]:
        return ("自動", "あり", "なし", "未確認") if self.language == "ja" else ("Auto", "Yes", "No", "Unknown")

    def _override_to_internal(self, value: str) -> str:
        if self.language != "ja":
            return value
        return {"自動": "Auto", "あり": "Yes", "なし": "No", "未確認": "Unknown"}.get(value, value)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=(14, 12))
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=self._t("二次診断・物理施工性詳細判定", "Secondary Screening — Physical Constructability"), font=("Yu Gothic UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text=self._t(
                "一次診断に、生コン・道路・港湾・重機・技能者の証拠を重ねます。未確認はUnknownのまま残し、地図未登録を不存在とは判定しません。",
                "Adds ready-mix, road, port, heavy-equipment and skilled-labor evidence to primary screening. Unverified items remain Unknown; absence from a map is not treated as nonexistence.",
            ),
            foreground="#8b0000", wraplength=1120,
        ).pack(fill="x", pady=(2, 8))

        controls = ttk.LabelFrame(outer, text=self._t("確認条件 / 手動補正", "Conditions / Manual Override"), padding=(8, 6))
        controls.pack(fill="x", pady=(0, 8))
        labels = [
            ("ready_mix", self._t("生コン供給", "Ready-mix")),
            ("road_access", self._t("大型車道路アクセス", "Heavy-vehicle road")),
            ("port_access", self._t("港湾アクセス", "Port access")),
            ("heavy_equipment", self._t("重機・揚重設備", "Heavy equipment")),
            ("skilled_labor", self._t("施工技能者", "Skilled labor")),
        ]
        for col, (key, label) in enumerate(labels):
            ttk.Label(controls, text=label).grid(row=0, column=col, padx=5, pady=3)
            ttk.Combobox(controls, textvariable=self.overrides[key], state="readonly", width=10, values=self._override_values()).grid(row=1, column=col, padx=5, pady=3)
        ttk.Checkbutton(controls, text=self._t("OpenStreetMap/Overpass補助証拠を取得", "Use OpenStreetMap/Overpass supporting evidence"), variable=self.online).grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="w")
        ttk.Button(controls, text=self._t("再判定", "Re-run"), command=self.run_evaluation).grid(row=2, column=3, padx=5, pady=5)
        ttk.Button(controls, text=self._t("判定JSON保存", "Save Result JSON"), command=self.save_json).grid(row=2, column=4, padx=5, pady=5)

        evbox = ttk.LabelFrame(outer, text=self._t("証拠サマリー", "Evidence Summary"), padding=(8, 5))
        evbox.pack(fill="x", pady=(0, 8))
        self.evidence_label = ttk.Label(evbox, text=self._t("未計算", "Not calculated"), wraplength=1120, justify="left")
        self.evidence_label.pack(fill="x")

        table = ttk.LabelFrame(outer, text=self._t("工法別 二次診断", "Secondary Screening by Method"), padding=(5, 5))
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("method", "s01", "physical", "requirements", "reason"), show="headings")
        heads = [
            ("method", self._t("工法", "Method"), 190),
            ("s01", self._t("一次判定", "Primary"), 110),
            ("physical", self._t("二次判定", "Secondary"), 120),
            ("requirements", self._t("要求条件", "Requirements"), 340),
            ("reason", self._t("理由", "Reason"), 360),
        ]
        for c, label, width in heads:
            self.tree.heading(c, text=label)
            self.tree.column(c, width=width, anchor="center" if c in ("s01", "physical") else "w")
        y = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y.set)
        self.tree.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")
        self.status_label = ttk.Label(outer, text="", foreground="#555555")
        self.status_label.pack(fill="x", pady=(6, 0))

    def run_evaluation(self) -> None:
        try:
            overrides = {k: self._override_to_internal(v.get()) for k, v in self.overrides.items()}
            self.result = evaluate_physical_constructability(self.project_data, overrides, self.online.get())
        except Exception as exc:
            messagebox.showerror(self._t("二次診断エラー", "Secondary Screening Error"), friendly_exception_text(exc,self.language), parent=self)
            return
        if self.on_result:
            self.on_result(self.result)
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        dims = self.result.get("dimension_assessment") or {}
        names = {
            "ready_mix": self._t("生コン", "Ready-mix"), "road_access": self._t("道路", "Road"),
            "port_access": self._t("港湾", "Port"), "heavy_equipment": self._t("重機", "Equipment"),
            "skilled_labor": self._t("技能者", "Labor"),
        }
        summary = [f"{names[k]}:{self._dimension_status_text((dims.get(k) or {}).get('status', 'Unknown'))}" for k in names]
        online = self.result.get("online_logistics_evidence") or {}
        if online.get("status") != "ok":
            online_status = str(online.get("status"))
            if self.language == "ja":
                online_status = {"not_run": "未取得", "unavailable": "取得不可", "error": "取得エラー"}.get(online_status, online_status)
            summary.append(self._t("オンライン証拠:", "Online evidence=") + online_status)
        self.evidence_label.config(text=" / ".join(summary))
        for row in self.result.get("methods") or []:
            req = row.get("required_dimension_states") or {}
            reqtext = ", ".join(f"{names.get(k, k)}:{self._dimension_status_text(v)}" for k, v in req.items())
            reasons = row.get("reasons_ja") if self.language == "ja" else row.get("reasons_en")
            if not reasons:
                reasons = [self._reason_text(x) for x in (row.get("reasons") or [])]
            self.tree.insert("", "end", values=(
                row.get("label_ja") if self.language == "ja" else (row.get("label_en") or row.get("method_id")),
                self._primary_status_text(row.get("screening_status_01")),
                self._secondary_status_text(row.get("physical_status")),
                reqtext,
                " / ".join(reasons or []),
            ))
        c = self.result.get("counts") or {}
        order = ("Feasible", "Conditional", "Difficult", "Unknown", "Excluded")
        self.status_label.config(text=" | ".join(f"{self._secondary_status_text(k)}: {c.get(k, 0)}" for k in order))

    def save_json(self) -> None:
        if not self.result:
            return
        initial = "AZRAS_Physical_Constructability.json"
        if self.source_path:
            initial = Path(self.source_path).stem + "_physical_constructability.json"
        path = filedialog.asksaveasfilename(parent=self, title=self._t("二次診断JSONを保存", "Save Secondary Screening JSON"), defaultextension=".json", initialfile=initial, filetypes=[("JSON", "*.json")])
        if not path:
            return
        payload = {"product": "01_AZRAS_Planning_Basic", "source_project": self.source_path, "physical_constructability": self.result}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo(self._t("保存完了", "Saved"), str(path), parent=self)
