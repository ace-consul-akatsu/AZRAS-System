# -*- coding: utf-8 -*-
"""PATCH_005: the 比較前提表 (comparison premise book) screen.

The decision logic lives in premise_book.py; this file is only the screen:
four lists the human works through, and one button that writes the comparison
group folder.

  A 除外工種リスト  which items are method-specific / method-dependent work.
  B 単価差リスト    shared items whose unit price differs -> choose one price.
  C 範囲差リスト    items some Projects carry and others do not -> a quantity
                    decision, made in the SOURCE Project, not here.
  D 事業前提        Module 5/6/7 settings, and the market rent every Project
                    must share (rent derived from construction cost is refused).
  E 工法差の前提    durability and renewal cycles; shown, never unified.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from comparison import premise_book as PB
# PATCH_006: Japanese display names; decisions/keys stay English-canonical.
from comparison import display_ja as DJ

CATEGORIES = [("common", "共通（比較対象）", "Common (compared)"),
              ("method_dependent_work", "仕事が違う（単価差から除外）", "Work differs (excluded from price list)"),
              ("method_specific", "工法固有（両方から除外）", "Method-specific (excluded from both)")]
SCOPE_DECISIONS = [("accept_method_difference", "工法差として了承", "Accept as a method difference"),
                   ("fix_source_quantity", "元Projectの数量を見直す", "Revise the quantity in the source Project")]


MAX_BUILDINGS = 7  # 03 Compare accepts 2..7 Project JSONs
BUILDING_COLS = tuple(f"p{i}" for i in range(1, MAX_BUILDINGS + 1))
BUILDING_HEADS = tuple((f"p{i}", f"建物{i}", 130) for i in range(1, MAX_BUILDINGS + 1))


def _pad(vals):
    vals = list(vals)[:MAX_BUILDINGS]
    return vals + [""] * (MAX_BUILDINGS - len(vals))


def _fmt(v):
    return "-" if v is None else (f"{v:,.2f}" if isinstance(v, float) else str(v))


def _fmt_ja(v):
    """PATCH_006: like _fmt, but coded values (market_rent, True...) in Japanese."""
    if isinstance(v, (bool, str)):
        return DJ.value_ja(str(v))
    return _fmt(v)


class ChoiceDialog(tk.Toplevel):
    """A small modal list-choice box (optionally with a free value)."""

    def __init__(self, parent, title, prompt, options, allow_value=False, value_label=""):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.result = None
        self.var = tk.StringVar(value=options[0][0] if options else "")
        self.value = tk.StringVar()
        ttk.Label(self, text=prompt, wraplength=560, justify="left").pack(anchor="w", padx=12, pady=(10, 6))
        for key, text in options:
            ttk.Radiobutton(self, text=text, value=key, variable=self.var).pack(anchor="w", padx=18, pady=1)
        if allow_value:
            row = ttk.Frame(self)
            row.pack(anchor="w", padx=18, pady=(6, 0))
            ttk.Label(row, text=value_label).pack(side="left")
            tk.Entry(row, textvariable=self.value, width=18).pack(side="left", padx=6)
        box = ttk.Frame(self)
        box.pack(fill="x", padx=12, pady=10)
        ttk.Button(box, text="OK", command=self._ok).pack(side="right", padx=4)
        ttk.Button(box, text="キャンセル", command=self.destroy).pack(side="right")
        self.grab_set()
        self.wait_window(self)

    def _ok(self):
        self.result = (self.var.get(), self.value.get().strip())
        self.destroy()


class PremiseBookTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.classification = PB.load_classification()
        self.sources: list[tuple[str, dict]] = []
        self.lists = None
        self.decisions = None
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self):
        ttk.Label(self, text="7. 比較前提表（同じ建物・工法違いの比較前提をそろえる）",
                  font=("Yu Gothic UI", 15, "bold")).pack(anchor="w", padx=14, pady=(8, 2))
        ttk.Label(self, text=("1. 建物・JSON選択で元Projectを選んでから「一覧を作成」を押してください。"
                              "単価差・範囲差・事業前提を決めると、比較用コピーを新しいフォルダーへ書き出します。"
                              "元Projectは変更しません。"),
                  foreground="#555", wraplength=1380).pack(fill="x", padx=14, pady=(0, 6))
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14, pady=2)
        ttk.Button(bar, text="一覧を作成", command=self.build_lists).pack(side="left")
        ttk.Button(bar, text="比較用コピーを作成", command=self.create_group).pack(side="left", padx=6)
        ttk.Button(bar, text="区分表を読込", command=self.load_classification_file).pack(side="left", padx=6)
        self.status = ttk.Label(bar, text="未作成", foreground="#555")
        self.status.pack(side="left", padx=12)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=6)
        self.tab_price = ttk.Frame(nb)
        self.tab_scope = ttk.Frame(nb)
        self.tab_class = ttk.Frame(nb)
        self.tab_business = ttk.Frame(nb)
        self.tab_method = ttk.Frame(nb)
        nb.add(self.tab_price, text="B 単価差リスト")
        nb.add(self.tab_scope, text="C 範囲差リスト")
        nb.add(self.tab_class, text="A 除外工種リスト")
        nb.add(self.tab_business, text="D 事業前提")
        nb.add(self.tab_method, text="E 工法差の前提（表示のみ）")

        # PATCH_008: Compare loads 2-7 buildings; buildings 4-7 were cut off here.
        self.price_tree = self._tree(self.tab_price, ("item", "unit", "diff", "decision", *BUILDING_COLS),
                                     (("item", "工種", 200), ("unit", "単位", 80), ("diff", "差", 90),
                                      ("decision", "採用", 240), *BUILDING_HEADS))
        self.price_tree.bind("<Double-1>", self._edit_price)
        ttk.Label(self.tab_price, text="行をダブルクリックして採用単価を選びます。「個別のまま」を選ぶとその工種は統一しません。",
                  foreground="#555").pack(anchor="w", padx=10, pady=2)

        self.scope_tree = self._tree(self.tab_scope, ("item", "kind", "unit", "have", "lack", "decision"),
                                     (("item", "工種・部位", 220), ("kind", "種別", 110), ("unit", "単位", 80),
                                      ("have", "あり", 300), ("lack", "なし", 300), ("decision", "決定", 240)))
        self.scope_tree.bind("<Double-1>", self._edit_scope)
        ttk.Label(self.tab_scope, text="範囲差は単価では直りません。数量の見直しは元Projectで行い、その後コピーを作り直してください。"
                       "赤い行は建物規模の差です。同じ建物の比較では延床面積・建築面積・階数・戸数が一致している必要があります（面積は±3%まで）。",
                  foreground="#8b0000", wraplength=1380).pack(anchor="w", padx=10, pady=2)

        self.class_tree = self._tree(self.tab_class, ("item", "category"),
                                     (("item", "工種", 300), ("category", "区分", 420)))
        self.class_tree.bind("<Double-1>", self._edit_class)

        self.business_tree = self._tree(self.tab_business, ("item", "value", *BUILDING_COLS),
                                        (("item", "前提", 380), ("value", "統一値", 200), *BUILDING_HEADS))
        self.business_tree.bind("<Double-1>", self._edit_business)

        self.method_tree = self._tree(self.tab_method, ("item", "structure", "rebuild", "retain"),
                                      (("item", "建物", 320), ("structure", "構造部位", 220),
                                       ("rebuild", "建替・全面更新の年", 260), ("retain", "骨組み継続の年", 200)))

    def _tree(self, parent, cols, heads):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=6)
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c, h, w in heads:
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w")
        y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)  # PATCH_008: up to 7 building columns
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    # --------------------------------------------------------------- build
    def load_classification_file(self):
        p = filedialog.askopenfilename(title="区分表JSON", filetypes=[("JSON", "*.json")], parent=self)
        if not p:
            return
        try:
            self.classification = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror("AZRAS", str(exc), parent=self)
            return
        if self.sources:
            self.build_lists()

    def build_lists(self):
        paths = [v.get() for v in self.app.paths if v.get()]
        if len(paths) < 2:
            messagebox.showwarning("AZRAS", "1. 建物・JSON選択で2件以上のProject JSONを選んでください。", parent=self)
            return
        try:
            self.sources = [(p, json.loads(Path(p).read_text(encoding="utf-8"))) for p in paths]
        except Exception as exc:
            messagebox.showerror("AZRAS", str(exc), parent=self)
            return
        projects = [pj for _, pj in self.sources]
        self.lists = PB.build_lists(projects, self.classification)
        self.decisions = PB.default_decisions(self.lists)
        if self.lists["blocking"]:
            messagebox.showwarning("AZRAS", "比較前提を揃えられません：" + ", ".join(
                (("通貨が不一致：" + b.split(":", 1)[1]) if b.startswith("currency_mismatch:")
                 else "所在地が不一致" if b == "location_mismatch" else b) for b in self.lists["blocking"]), parent=self)
        self._refresh()

    def _refresh(self):
        L, D = self.lists, self.decisions
        # PATCH_006: project labels on this screen use the Japanese method name.
        labels = [PB.project_label(pj, "ja") for _, pj in self.sources] if len(self.sources) == len(L["labels"]) else L["labels"]
        for tree in (self.price_tree, self.scope_tree, self.class_tree, self.business_tree, self.method_tree):
            for iid in tree.get_children():
                tree.delete(iid)
        for r in L["price_rows"]:
            rates = {c["project_index"]: c["rate"] for c in r["candidates"]}
            vals = [_fmt(rates.get(i)) for i in range(len(labels))]
            self.price_tree.insert("", "end", iid=r["row_id"],
                                   values=(DJ.cost_key_ja(r["key"]), DJ.unit_ja(r["unit"]), ("差あり" if r["differs"] else "一致"),
                                           self._price_text(r["row_id"]), *_pad(vals)))
        for r in L["scope_rows"]:
            if r["kind"] == "building":
                # PATCH_009: show each Project's value, and how far apart they are.
                have = " / ".join(f"{labels[i]}: {_fmt(v)}" for i, v in sorted(r["values"].items()))
                lack = (f"最大/最小 {r['ratio']:.2f}倍　同じ建物か確認" if r.get("ratio") else "同じ建物か確認")
            else:
                have = ", ".join(labels[i] for i in r["present"])
                lack = ", ".join(labels[i] for i in r["missing"])
            self.scope_tree.insert("", "end", iid=r["row_id"],
                                   values=(r.get("label_ja") or DJ.cost_key_ja(r["key"]), DJ.kind_ja(r["kind"]), DJ.unit_ja(r["unit"]),
                                           have, lack, self._scope_text(r["row_id"])),
                                   tags=(("building",) if r["kind"] == "building" else ()))
        self.scope_tree.tag_configure("building", foreground="#9c0006", background="#ffc7ce")
        keys = sorted({c["key"] for c in [r for r in L["price_rows"]]}
                      | {r["key"] for r in L["scope_rows"] if r["kind"] == "item"}
                      | set((self.classification.get("method_specific") or {}).get("keys") or [])
                      | set((self.classification.get("method_dependent_work") or {}).get("keys") or []))
        for k in keys:
            cls = PB.classify(k, self.classification)
            self.class_tree.insert("", "end", iid=f"class:{k}", values=(DJ.cost_key_ja(k), dict((c[0], c[1]) for c in CATEGORIES)[cls]))
        for r in L["business_rows"]:
            if not (r["differs"] or r["required"]):
                continue
            vals = [_fmt_ja(r["values"].get(i)) for i in range(len(labels))]
            self.business_tree.insert("", "end", iid=r["row_id"],
                                      values=(DJ.setting_ja(r["row_id"]), _fmt_ja(D["business"].get(r["row_id"])), *_pad(vals)))
        for r in L["method_premise_rows"]:
            idx = r.get("project_index")
            shown = labels[idx] if isinstance(idx, int) and idx < len(labels) else r["label"]
            self.method_tree.insert("", "end", values=(shown, DJ.component_ja(r["structure_component"]),
                                                       r["full_rebuild_or_all_infill_years"], r["retain_skeleton_years"]))
        left = PB.validate_decisions(L, D)
        self.status.config(text=("未決定 %d 件" % len(left)) if left else "決定済み（コピーを作成できます）",
                           foreground="#8b0000" if left else "#006400")

    def _label_ja(self, cand):
        i = cand.get("project_index")
        if isinstance(i, int) and i < len(self.sources):
            return PB.project_label(self.sources[i][1], "ja")
        return cand.get("label") or ""

    def _price_text(self, row_id):
        d = (self.decisions["price"] or {}).get(row_id) or {}
        if d.get("mode") == "unify":
            return f"統一 {_fmt(float(d['rate']))}"
        if d.get("mode") == "keep_separate":
            return "個別のまま"
        return "未決定"

    def _scope_text(self, row_id):
        d = (self.decisions["scope"] or {}).get(row_id) or {}
        return dict((k, ja) for k, ja, _ in SCOPE_DECISIONS).get(d.get("decision"), "未決定")

    # --------------------------------------------------------------- edits
    def _edit_price(self, event=None):
        if not self.lists:
            return
        row_id = self.price_tree.focus()
        row = next((r for r in self.lists["price_rows"] if r["row_id"] == row_id), None)
        if not row:
            return
        options = [(str(c["project_index"]),
                    f"{self._label_ja(c)} : {_fmt(c['rate'])} / {DJ.unit_ja(row['unit'])}"
                    + (f"  [{c['scope_definition']}]" if c["scope_definition"] else "")
                    + (f"  {c['source_title'][:60]}" if c["source_title"] else ""))
                   for c in row["candidates"]]
        options.append(("keep_separate", "個別のまま（統一しない）"))
        options.append(("manual", "手入力"))
        dlg = ChoiceDialog(self, "採用単価の選択", f"{DJ.cost_key_ja(row['key'])} ({DJ.unit_ja(row['unit'])})", options,
                           allow_value=True, value_label="手入力値")
        if not dlg.result:
            return
        choice, value = dlg.result
        if choice == "keep_separate":
            self.decisions["price"][row_id] = {"mode": "keep_separate"}
        elif choice == "manual":
            try:
                rate = float(value.replace(",", ""))
            except ValueError:
                messagebox.showerror("AZRAS", "単価は数値で入力してください。", parent=self)
                return
            self.decisions["price"][row_id] = {"mode": "unify", "rate": rate, "from_project": None, "manual": True}
        else:
            idx = int(choice)
            rate = next(c["rate"] for c in row["candidates"] if c["project_index"] == idx)
            self.decisions["price"][row_id] = {"mode": "unify", "rate": float(rate), "from_project": idx}
        self._refresh()

    def _edit_scope(self, event=None):
        if not self.lists:
            return
        row_id = self.scope_tree.focus()
        row = next((r for r in self.lists["scope_rows"] if r["row_id"] == row_id), None)
        if not row:
            return
        dlg = ChoiceDialog(self, "範囲差の決定", f"{row.get('label_ja') or DJ.cost_key_ja(row['key'])}",
                           [(k, ja) for k, ja, _ in SCOPE_DECISIONS])
        if dlg.result:
            self.decisions["scope"][row_id] = {"decision": dlg.result[0], "note": ""}
            self._refresh()

    def _edit_class(self, event=None):
        iid = self.class_tree.focus()
        if not iid.startswith("class:"):
            return
        key = iid.split(":", 1)[1]
        dlg = ChoiceDialog(self, "区分の変更", DJ.cost_key_ja(key), [(k, ja) for k, ja, _ in CATEGORIES])
        if not dlg.result:
            return
        cat = dlg.result[0]
        for name in ("method_specific", "method_dependent_work"):
            block = self.classification.setdefault(name, {}).setdefault("keys", [])
            if key in block:
                block.remove(key)
        if cat in ("method_specific", "method_dependent_work"):
            self.classification[cat]["keys"].append(key)
        projects = [pj for _, pj in self.sources]
        self.lists = PB.build_lists(projects, self.classification)
        self.decisions = PB.default_decisions(self.lists)
        self._refresh()

    def _edit_business(self, event=None):
        row_id = self.business_tree.focus()
        row = next((r for r in self.lists["business_rows"] if r["row_id"] == row_id), None)
        if not row:
            return
        shown = [PB.project_label(pj, "ja") for _, pj in self.sources]
        opts = [(json.dumps(v, ensure_ascii=False), f"{shown[i] if i < len(shown) else self.lists['labels'][i]} : {_fmt_ja(v)}")
                for i, v in row["values"].items()]
        opts.append(("manual", "手入力"))
        dlg = ChoiceDialog(self, "事業前提の統一値", DJ.setting_ja(row_id), opts, allow_value=True, value_label="手入力値")
        if not dlg.result:
            return
        choice, value = dlg.result
        if choice == "manual":
            raw = value
            try:
                val = float(raw.replace(",", ""))
            except ValueError:
                val = raw
        else:
            val = json.loads(choice)
        if row_id == "module6:rent_setting_method" and val != "market_rent":
            messagebox.showwarning("AZRAS", "建物間の比較では家賃を建設費から逆算できません。市場家賃を直接入力してください。",
                                   parent=self)
            return
        self.decisions["business"][row_id] = val
        self._refresh()

    # -------------------------------------------------------------- create
    def create_group(self):
        if not self.lists:
            messagebox.showwarning("AZRAS", "先に一覧を作成してください。", parent=self)
            return
        left = PB.validate_decisions(self.lists, self.decisions)
        if left:
            messagebox.showwarning("AZRAS", "未決定の項目があります：\n" + "\n".join(left[:12]), parent=self)
            return
        default_parent = str(Path(self.sources[0][0]).resolve().parent.parent)
        parent = filedialog.askdirectory(title="比較グループを作るフォルダー（JSONフォルダー）",
                                         initialdir=default_parent, parent=self)
        if not parent:
            return
        name = ChoiceDialog(self, "比較グループ名", "フォルダー名に使う名前を入力してください。",
                            [("manual", "入力した名前を使う")], allow_value=True, value_label="名前")
        group_name = (name.result or ("manual", ""))[1] or "工法比較"
        try:
            out = PB.write_group(parent, group_name, self.sources, self.classification, self.lists, self.decisions)
        except Exception as exc:
            messagebox.showerror("AZRAS", str(exc), parent=self)
            return
        messagebox.showinfo("AZRAS",
                            "比較用コピーを作成しました。\n\n"
                            f"{out['folder']}\n前提表の版: {out['version']}\n\n"
                            "この後の手順\n"
                            "1. 01 Planning で各コピーの Module 5 を再計算・保存\n"
                            "2. 02 Evaluation で各コピーの Module 7 → Module 6 を再計算・保存\n"
                            "3. 1. 建物・JSON選択でコピーを選び直して比較\n\n"
                            "元Projectは変更していません。",
                            parent=self)
