from __future__ import annotations

import copy
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from core.ui_style import fit_window_to_screen
from core.error_text import friendly_exception_text

try:
    import fitz  # PyMuPDF
    from PIL import Image, ImageDraw, ImageTk
except Exception:
    fitz = None
    Image = ImageDraw = ImageTk = None

# Stored coordinates are always PDF points. The PDF itself is never redrawn.
CATEGORIES = {
    # structural layer
    "rc_exterior": ("RC外壁・外部RC", "#ff3030", "structure"),
    "rc_partition": ("RC戸境壁・内部構造RC", "#2878ff", "structure"),
    "two_by_six_exterior": ("2×6外壁", "#20b7bd", "structure"),
    "lgs_partition": ("LGS＋PB間仕切り", "#20a85a", "structure"),
    "timber_partition": ("木造間仕切り", "#f0b400", "structure"),
    "timber_beam": ("木造梁", "#9b42d6", "structure"),
    "rc_column": ("RC柱", "#202020", "structure"),
    "rc_beam": ("RC梁", "#6b32a8", "structure"),
    "unclassified": ("未判定", "#ff7f00", "structure"),
    # insulation layer
    "insulation_exterior": ("外壁断熱", "#ff4fa3", "insulation"),
    "insulation_interior": ("内断熱", "#f58ad2", "insulation"),
    "insulation_foundation": ("基礎下断熱", "#2f80ed", "insulation"),
    "insulation_slab": ("土間下断熱", "#f2c94c", "insulation"),
    "insulation_roof": ("屋根・天井断熱", "#9b51e0", "insulation"),
    "vapor_air_layer": ("防湿・気密層", "#27ae60", "insulation"),
    "insulation_other": ("断熱材・その他", "#828282", "insulation"),
}


class DrawingRecognitionViewer(tk.Toplevel):
    """Editable PDF-coordinate overlay editor.

    The original PDF page is rendered unchanged.  Annotations are composited with
    a true alpha layer using Pillow.  Users can add, select, move, resize,
    reclassify and delete annotations.  Structural and insulation annotations
    are separate switchable views.
    """

    HANDLE_PX = 8

    def __init__(self, master, pdf_path, analysis_result=None,
                 saved_annotations=None, on_save=None, language="ja"):
        super().__init__(master)
        self.language = "en" if str(language).lower().startswith("en") else "ja"
        self.title(self._tr("図面認識確認・修正 — 元PDF座標レイヤー", "Drawing Recognition Review — PDF Coordinate Layer"))
        fit_window_to_screen(self,1480,940,820,520)
        self.minsize(1000, 650)

        self.pdf_path = str(pdf_path or "")
        self.analysis = analysis_result or {}
        self.on_save = on_save
        self.doc = None
        self.page_index = 0
        self.zoom = 1.45
        self.opacity = tk.DoubleVar(value=0.50)
        self.layer = tk.StringVar(value="structure")
        self.mode = tk.StringVar(value="select")
        self.category = tk.StringVar(value="rc_exterior")
        self.status = tk.StringVar(value="")
        self.selected_index = None
        self.drag_state = None
        self.photo = None
        self.base_image = None
        self.annotations = self._normalise_annotations(saved_annotations or [])
        self.undo_stack = []
        self.redo_stack = []

        self._build()
        self._open_pdf()

    # ---------- UI ----------
    def _tr(self, ja, en):
        return ja if self.language == "ja" else en

    def _category_label(self, key):
        ja = CATEGORIES.get(key, CATEGORIES["unclassified"])[0]
        en = {
            "rc_exterior":"RC exterior wall / exterior RC",
            "rc_partition":"RC separation wall / internal structural RC",
            "two_by_six_exterior":"2x6 exterior wall",
            "lgs_partition":"LGS + gypsum-board partition",
            "timber_partition":"Timber partition",
            "timber_beam":"Timber beam",
            "rc_column":"RC column",
            "rc_beam":"RC beam",
            "unclassified":"Unclassified",
            "insulation_exterior":"Exterior-wall insulation",
            "insulation_interior":"Interior insulation",
            "insulation_foundation":"Under-foundation insulation",
            "insulation_slab":"Under-slab insulation",
            "insulation_roof":"Roof / ceiling insulation",
            "vapor_air_layer":"Vapor / air barrier",
            "insulation_other":"Other insulation",
        }.get(key, key)
        return ja if self.language == "ja" else en

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Button(top, text=self._tr("◀ 前ページ", "◀ Previous"), command=self.prev_page).pack(side="left")
        ttk.Button(top, text=self._tr("次ページ ▶", "Next ▶"), command=self.next_page).pack(side="left", padx=3)
        ttk.Button(top, text="－", width=3, command=lambda: self.change_zoom(-0.15)).pack(side="left", padx=(12, 1))
        ttk.Button(top, text="＋", width=3, command=lambda: self.change_zoom(0.15)).pack(side="left")
        ttk.Button(top, text=self._tr("全体表示", "Fit page"), command=self.fit_page).pack(side="left", padx=5)

        ttk.Radiobutton(top, text=self._tr("構造部材図", "Structure"), variable=self.layer,
                        value="structure", command=self._layer_changed).pack(side="left", padx=(18, 2))
        ttk.Radiobutton(top, text=self._tr("断熱材・位置図", "Insulation"), variable=self.layer,
                        value="insulation", command=self._layer_changed).pack(side="left", padx=2)

        ttk.Label(top, text=self._tr("透明度", "Opacity")).pack(side="left", padx=(18, 3))
        scale = ttk.Scale(top, from_=0.10, to=0.90, variable=self.opacity,
                          command=lambda _v: self.render())
        scale.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.opacity_label = ttk.Label(top, width=5)
        self.opacity_label.pack(side="left")

        ttk.Button(top, text=self._tr("元に戻す", "Undo"), command=self.undo).pack(side="right", padx=2)
        ttk.Button(top, text=self._tr("やり直す", "Redo"), command=self.redo).pack(side="right", padx=2)
        ttk.Button(top, text=self._tr("確認結果を保存", "Save review"), command=self.save_review).pack(side="right", padx=8)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        canvas_frame = ttk.Frame(body)
        side = ttk.Frame(body, width=330)
        body.add(canvas_frame, weight=5)
        body.add(side, weight=1)

        self.canvas = tk.Canvas(canvas_frame, bg="#555", cursor="crosshair")
        xs = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        ys = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self._mouse_down)
        self.canvas.bind("<B1-Motion>", self._mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._mouse_up)
        self.canvas.bind("<Delete>", lambda _e: self.delete_selected())
        self.bind("<Control-z>", lambda _e: self.undo())
        self.bind("<Control-y>", lambda _e: self.redo())

        edit = ttk.LabelFrame(side, text=self._tr("修正ツール", "Edit tools"))
        edit.pack(fill="x", padx=4, pady=4)
        ttk.Radiobutton(edit, text=self._tr("選択・移動・拡大縮小", "Select / move / resize"), variable=self.mode,
                        value="select", command=self._update_cursor).pack(anchor="w", padx=8, pady=3)
        ttk.Radiobutton(edit, text=self._tr("矩形を追加", "Add rectangle"), variable=self.mode,
                        value="add", command=self._update_cursor).pack(anchor="w", padx=8, pady=3)

        ttk.Label(edit, text=self._tr("部材・断熱区分", "Component / insulation class")).pack(anchor="w", padx=8, pady=(8, 2))
        self.cat_combo = ttk.Combobox(edit, state="readonly", width=35)
        self.cat_combo.pack(fill="x", padx=8)
        self.cat_combo.bind("<<ComboboxSelected>>", self._category_changed)
        ttk.Button(edit, text=self._tr("選択中の区分へ変更", "Change selected class"), command=self.reclassify_selected).pack(fill="x", padx=8, pady=5)
        ttk.Button(edit, text=self._tr("選択項目を削除", "Delete selected"), command=self.delete_selected).pack(fill="x", padx=8, pady=2)

        attrs = ttk.LabelFrame(side, text=self._tr("選択中の注釈", "Selected annotation"))
        attrs.pack(fill="x", padx=4, pady=6)
        self.selection_text = tk.StringVar(value=self._tr("未選択", "None selected"))
        ttk.Label(attrs, textvariable=self.selection_text, justify="left", wraplength=300).pack(fill="x", padx=8, pady=8)

        summary = ttk.LabelFrame(side, text=self._tr("このページの件数", "Counts on this page"))
        summary.pack(fill="both", expand=True, padx=4, pady=4)
        self.summary_text = tk.Text(summary, height=15, width=38, state="disabled")
        self.summary_text.pack(fill="both", expand=True, padx=5, pady=5)

        guide = ttk.LabelFrame(side, text=self._tr("操作", "Instructions"))
        guide.pack(fill="x", padx=4, pady=4)
        ttk.Label(
            guide,
            text=self._tr(
                "追加：『矩形を追加』で対象範囲をドラッグ\n"
                "選択：色付き範囲をクリック\n"
                "移動：選択範囲の中央をドラッグ\n"
                "拡大縮小：四隅の□をドラッグ\n"
                "区分変更：プルダウン選択後に変更\n"
                "削除：Deleteキーまたは削除ボタン\n\n"
                "元PDFは変更されません。保存されるのは\n"
                "PDF座標の確認・修正レイヤーだけです。",
                "Add: drag the target area in Add rectangle mode\n"
                "Select: click a colored area\n"
                "Move: drag the center of a selected area\n"
                "Resize: drag a corner handle\n"
                "Reclassify: choose a class, then apply\n"
                "Delete: Delete key or Delete selected\n\n"
                "The source PDF is never modified. Only the PDF-coordinate\n"
                "review/correction layer is saved.",
            ),
            justify="left", wraplength=300,
        ).pack(fill="x", padx=8, pady=8)

        ttk.Label(self, textvariable=self.status).pack(fill="x", padx=8, pady=(0, 6))
        self._refresh_category_combo()

    def _update_cursor(self):
        self.canvas.configure(cursor="crosshair" if self.mode.get() == "add" else "arrow")

    def _layer_changed(self):
        self.selected_index = None
        self._refresh_category_combo()
        self.render()

    def _refresh_category_combo(self):
        keys = [k for k, (_l, _c, layer) in CATEGORIES.items() if layer == self.layer.get()]
        values = [f"{k}｜{self._category_label(k)}" for k in keys]
        self.cat_combo["values"] = values
        current = self.category.get()
        if current not in keys:
            current = keys[0]
            self.category.set(current)
        self.cat_combo.set(f"{current}｜{self._category_label(current)}")

    def _category_changed(self, _event=None):
        raw = self.cat_combo.get()
        if "｜" in raw:
            self.category.set(raw.split("｜", 1)[0])

    # ---------- PDF and render ----------
    def _open_pdf(self):
        if fitz is None or Image is None:
            messagebox.showerror("Error", self._tr("PyMuPDF(fitz) と Pillow が必要です。", "PyMuPDF (fitz) and Pillow are required."))
            return
        if not self.pdf_path or not Path(self.pdf_path).exists():
            messagebox.showerror("Error", self._tr("元PDFファイルが見つかりません。", "The source PDF file could not be found."))
            return
        try:
            self.doc = fitz.open(self.pdf_path)
            self.render()
        except Exception as exc:
            messagebox.showerror("Error", self._tr(f"PDFを開けません。\n{exc}", f"Could not open the PDF.\n{exc}"))

    def change_zoom(self, delta):
        self.zoom = max(0.35, min(4.0, self.zoom + delta))
        self.render()

    def fit_page(self):
        if not self.doc:
            return
        self.update_idletasks()
        page = self.doc[self.page_index]
        avail_w = max(300, self.canvas.winfo_width() - 30)
        avail_h = max(300, self.canvas.winfo_height() - 30)
        self.zoom = max(0.35, min(3.0, min(avail_w / page.rect.width, avail_h / page.rect.height)))
        self.render()

    def render(self):
        if not self.doc:
            return
        self.page_index = max(0, min(self.page_index, len(self.doc) - 1))
        page = self.doc[self.page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        base = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        alpha = int(max(0.10, min(0.90, self.opacity.get())) * 255)
        visible = self._visible_indices()

        for idx in visible:
            ann = self.annotations[idx]
            x0, y0, x1, y1 = self._scaled_bbox(ann)
            _label, color, _layer = CATEGORIES.get(ann.get("category"), CATEGORIES["unclassified"])
            rgb = self._hex_to_rgb(color)
            draw.rectangle((x0, y0, x1, y1), fill=(*rgb, alpha), outline=(*rgb, 255), width=2)

        composited = Image.alpha_composite(base, overlay).convert("RGB")
        self.photo = ImageTk.PhotoImage(composited)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw", tags=("page",))
        self.canvas.configure(scrollregion=(0, 0, pix.width, pix.height))

        if self.selected_index in visible:
            self._draw_selection(self.annotations[self.selected_index])
        else:
            self.selected_index = None

        self.opacity_label.configure(text=f"{self.opacity.get()*100:.0f}%")
        self._update_selection_text()
        self._update_summary()
        auto = sum(1 for i in visible if self.annotations[i].get("source") == "auto")
        manual = len(visible) - auto
        if self.language == "ja":
            self.status.set(
                f"ページ {self.page_index + 1}/{len(self.doc)}　"
                f"{('構造部材図' if self.layer.get() == 'structure' else '断熱材・位置図')}　"
                f"自動候補 {auto}件／確認・手動 {manual}件　透明度 {self.opacity.get()*100:.0f}%"
            )
        else:
            self.status.set(
                f"Page {self.page_index + 1}/{len(self.doc)}  "
                f"{('Structure' if self.layer.get() == 'structure' else 'Insulation')}  "
                f"Auto candidates {auto} / reviewed-manual {manual}  opacity {self.opacity.get()*100:.0f}%"
            )

    def _draw_selection(self, ann):
        x0, y0, x1, y1 = self._scaled_bbox(ann)
        self.canvas.create_rectangle(x0, y0, x1, y1, outline="#ffffff", width=3, dash=(5, 3), tags="selection")
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            r = self.HANDLE_PX / 2
            self.canvas.create_rectangle(x-r, y-r, x+r, y+r, fill="#ffffff", outline="#111111", tags="selection")

    @staticmethod
    def _hex_to_rgb(value):
        value = value.lstrip("#")
        return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))

    def _scaled_bbox(self, ann):
        x0, y0, x1, y1 = ann["bbox"]
        return x0*self.zoom, y0*self.zoom, x1*self.zoom, y1*self.zoom

    # ---------- mouse editing ----------
    def _mouse_down(self, event):
        self.canvas.focus_set()
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if self.mode.get() == "add":
            self.drag_state = {"kind": "add", "start": (x, y), "current": (x, y)}
            return

        idx = self._hit_test(x, y)
        self.selected_index = idx
        if idx is None:
            self.drag_state = None
            self.render()
            return
        self._push_undo()
        ann = self.annotations[idx]
        handle = self._hit_handle(ann, x, y)
        self.drag_state = {
            "kind": "resize" if handle else "move",
            "handle": handle,
            "start": (x, y),
            "original": list(ann["bbox"]),
            "changed": False,
        }
        self.render()

    def _mouse_drag(self, event):
        if not self.drag_state:
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if self.drag_state["kind"] == "add":
            self.drag_state["current"] = (x, y)
            self.canvas.delete("rubber")
            sx, sy = self.drag_state["start"]
            color = CATEGORIES[self.category.get()][1]
            self.canvas.create_rectangle(sx, sy, x, y, outline=color, width=3, dash=(4, 3), tags="rubber")
            return

        idx = self.selected_index
        if idx is None:
            return
        sx, sy = self.drag_state["start"]
        dx = (x - sx) / self.zoom
        dy = (y - sy) / self.zoom
        x0, y0, x1, y1 = self.drag_state["original"]
        if self.drag_state["kind"] == "move":
            box = [x0+dx, y0+dy, x1+dx, y1+dy]
        else:
            box = [x0, y0, x1, y1]
            handle = self.drag_state["handle"]
            if "l" in handle: box[0] = x / self.zoom
            if "r" in handle: box[2] = x / self.zoom
            if "t" in handle: box[1] = y / self.zoom
            if "b" in handle: box[3] = y / self.zoom
            box = [min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3])]
        self.annotations[idx]["bbox"] = self._clamp_bbox(box)
        self.annotations[idx]["source"] = "manual_review"
        self.drag_state["changed"] = True
        self.render()

    def _mouse_up(self, event):
        if not self.drag_state:
            return
        if self.drag_state["kind"] == "add":
            sx, sy = self.drag_state["start"]
            ex = self.canvas.canvasx(event.x)
            ey = self.canvas.canvasy(event.y)
            self.canvas.delete("rubber")
            if abs(ex-sx) >= 6 and abs(ey-sy) >= 6:
                self._push_undo()
                box = self._clamp_bbox([
                    min(sx, ex)/self.zoom, min(sy, ey)/self.zoom,
                    max(sx, ex)/self.zoom, max(sy, ey)/self.zoom,
                ])
                self.annotations.append({
                    "page": self.page_index,
                    "category": self.category.get(),
                    "bbox": box,
                    "source": "manual_review",
                    "confirmed": True,
                })
                self.selected_index = len(self.annotations)-1
        elif not self.drag_state.get("changed") and self.undo_stack:
            # Remove no-op undo snapshot created on click.
            self.undo_stack.pop()
        self.drag_state = None
        self.render()

    def _hit_test(self, x, y):
        # Last annotation is visually topmost.
        for idx in reversed(self._visible_indices()):
            x0, y0, x1, y1 = self._scaled_bbox(self.annotations[idx])
            if x0 <= x <= x1 and y0 <= y <= y1:
                return idx
        return None

    def _hit_handle(self, ann, x, y):
        x0, y0, x1, y1 = self._scaled_bbox(ann)
        r = self.HANDLE_PX + 3
        handles = {"lt": (x0, y0), "rt": (x1, y0), "rb": (x1, y1), "lb": (x0, y1)}
        for name, (hx, hy) in handles.items():
            if abs(x-hx) <= r and abs(y-hy) <= r:
                return name
        return None

    def _clamp_bbox(self, box):
        page = self.doc[self.page_index]
        x0, y0, x1, y1 = box
        return [
            max(0.0, min(page.rect.width, x0)),
            max(0.0, min(page.rect.height, y0)),
            max(0.0, min(page.rect.width, x1)),
            max(0.0, min(page.rect.height, y1)),
        ]

    # ---------- editing commands ----------
    def reclassify_selected(self):
        if self.selected_index is None:
            messagebox.showinfo(self._tr("区分変更", "Reclassify"), self._tr("先に図面上の色付き範囲を選択してください。", "Select a colored area on the drawing first."))
            return
        cat = self.category.get()
        if CATEGORIES[cat][2] != self.layer.get():
            return
        self._push_undo()
        self.annotations[self.selected_index]["category"] = cat
        self.annotations[self.selected_index]["source"] = "manual_review"
        self.annotations[self.selected_index]["confirmed"] = True
        self.render()

    def delete_selected(self):
        if self.selected_index is None:
            return
        self._push_undo()
        del self.annotations[self.selected_index]
        self.selected_index = None
        self.render()

    def _push_undo(self):
        self.undo_stack.append(copy.deepcopy(self.annotations))
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(copy.deepcopy(self.annotations))
        self.annotations = self.undo_stack.pop()
        self.selected_index = None
        self.render()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self.annotations))
        self.annotations = self.redo_stack.pop()
        self.selected_index = None
        self.render()

    # ---------- summaries and persistence ----------
    def _visible_indices(self):
        layer = self.layer.get()
        return [
            i for i, a in enumerate(self.annotations)
            if int(a.get("page", 0)) == self.page_index
            and CATEGORIES.get(a.get("category"), CATEGORIES["unclassified"])[2] == layer
        ]

    def _update_selection_text(self):
        if self.selected_index is None:
            self.selection_text.set(self._tr("未選択", "None selected"))
            return
        ann = self.annotations[self.selected_index]
        label = self._category_label(ann.get("category"))
        x0, y0, x1, y1 = ann["bbox"]
        if self.language == "ja":
            self.selection_text.set(
                f"区分：{label}\n"
                f"PDFページ：{int(ann.get('page', 0))+1}\n"
                f"座標：({x0:.1f}, {y0:.1f})－({x1:.1f}, {y1:.1f})\n"
                f"幅×高さ：{x1-x0:.1f} × {y1-y0:.1f} pt\n"
                f"由来：{'自動候補' if ann.get('source') == 'auto' else '手動確認・修正'}"
            )
        else:
            self.selection_text.set(
                f"Class: {label}\n"
                f"PDF page: {int(ann.get('page', 0))+1}\n"
                f"Coordinates: ({x0:.1f}, {y0:.1f})-({x1:.1f}, {y1:.1f})\n"
                f"Width x height: {x1-x0:.1f} x {y1-y0:.1f} pt\n"
                f"Source: {'Auto candidate' if ann.get('source') == 'auto' else 'Manual review/correction'}"
            )

    def _update_summary(self):
        counts = {}
        for idx in self._visible_indices():
            cat = self.annotations[idx].get("category", "unclassified")
            counts[cat] = counts.get(cat, 0) + 1
        lines = []
        for cat, (label, _color, layer) in CATEGORIES.items():
            if layer == self.layer.get():
                lines.append(f"{self._category_label(cat)}: {counts.get(cat, 0)}" + ("件" if self.language == "ja" else ""))
        lines.append("")
        lines.append(self._tr("自動候補は必ず元PDFと照合し、誤りはこの画面で修正してください。", "Always verify auto candidates against the source PDF and correct errors here."))
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", "\n".join(lines))
        self.summary_text.configure(state="disabled")

    def _normalise_annotations(self, annotations):
        result = []
        for raw in annotations:
            if not isinstance(raw, dict):
                continue
            box = raw.get("bbox") or raw.get("rect") or raw.get("box")
            if not isinstance(box, (list, tuple)) or len(box) < 4:
                continue
            try:
                box = [float(v) for v in box[:4]]
                page = int(raw.get("page", raw.get("page_index", 0)))
            except Exception:
                continue
            cat = str(raw.get("category", "unclassified"))
            if cat not in CATEGORIES:
                cat = "unclassified"
            result.append({
                "page": page,
                "category": cat,
                "bbox": [min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3])],
                "source": raw.get("source", "manual_review"),
                "confirmed": bool(raw.get("confirmed", raw.get("source") != "auto")),
                "note": str(raw.get("note", "")),
            })
        # Include only genuine geometry returned by an analyzer. Never fabricate from totals.
        for ann in self._extract_auto_annotations():
            key = (ann["page"], ann["category"], tuple(round(v, 2) for v in ann["bbox"]))
            if not any((a["page"], a["category"], tuple(round(v, 2) for v in a["bbox"])) == key for a in result):
                result.append(ann)
        return result

    def _walk(self, obj):
        if isinstance(obj, dict):
            yield obj
            for value in obj.values():
                yield from self._walk(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from self._walk(value)

    def _extract_auto_annotations(self):
        aliases = {
            "rc_exterior": {"rc_exterior", "exterior_rc", "rc_wall_exterior", "exterior_wall_rc"},
            "rc_partition": {"rc_partition", "partition_rc", "dwelling_separation_rc", "internal_structural_rc"},
            "two_by_six_exterior": {"two_by_six_exterior", "2x6_exterior", "wood_exterior_wall"},
            "lgs_partition": {"lgs_partition", "lgs", "lgs_pb"},
            "timber_partition": {"timber_partition", "wood_partition", "timber"},
            "timber_beam": {"timber_beam", "wood_beam"},
            "rc_column": {"column", "rc_column"},
            "rc_beam": {"beam", "rc_beam"},
            "insulation_exterior": {"exterior_insulation", "insulation_exterior"},
            "insulation_interior": {"interior_insulation", "insulation_interior"},
            "insulation_foundation": {"foundation_insulation", "under_foundation_insulation"},
            "insulation_slab": {"slab_insulation", "under_slab_insulation"},
            "insulation_roof": {"roof_insulation", "ceiling_insulation"},
            "vapor_air_layer": {"vapor_barrier", "air_barrier", "vapor_air_layer"},
        }
        out = []
        for item in self._walk(self.analysis):
            p = item.get("page", item.get("page_index", item.get("pdf_page")))
            box = item.get("bbox", item.get("rect", item.get("box")))
            if p is None or not isinstance(box, (list, tuple)) or len(box) < 4:
                continue
            typ = str(item.get("category", item.get("type", item.get("class", "")))).lower()
            cat = next((k for k, names in aliases.items() if typ in names), None)
            if not cat:
                continue
            try:
                page = int(p)
                if page >= 1:  # analyzer page numbers are commonly one-based
                    page -= 1
                coords = [float(v) for v in box[:4]]
            except Exception:
                continue
            out.append({
                "page": page,
                "category": cat,
                "bbox": [min(coords[0], coords[2]), min(coords[1], coords[3]), max(coords[0], coords[2]), max(coords[1], coords[3])],
                "source": "auto",
                "confirmed": False,
                "note": "",
            })
        return out

    def prev_page(self):
        if self.doc and self.page_index > 0:
            self.page_index -= 1
            self.selected_index = None
            self.render()

    def next_page(self):
        if self.doc and self.page_index < len(self.doc)-1:
            self.page_index += 1
            self.selected_index = None
            self.render()

    def save_review(self):
        payload = copy.deepcopy(self.annotations)
        if self.on_save:
            try:
                self.on_save(payload)
            except Exception as exc:
                messagebox.showerror(self._tr("保存エラー", "Save error"), friendly_exception_text(exc,self.language))
                return
        messagebox.showinfo(
            self._tr("保存", "Saved"),
            self._tr(
                "元PDF座標の確認・修正レイヤーをModule1結果へ保存しました。\n"
                "Project JSONへ確定するにはModule1の『更新保存』を実行してください。",
                "The PDF-coordinate review/correction layer was saved to the Module 1 result.\n"
                "Use Update/Save in Module 1 to commit it to the Project JSON.",
            ),
        )
