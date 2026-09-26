
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

FONT_FAMILY = "Yu Gothic UI"
FONT_SIZE = 10
TITLE_SIZE = 20
SUBTITLE_SIZE = 11
WINDOW_BG = "#f3f5f7"
PANEL_BG = "#ffffff"
INPUT_BG = "#fff2b3"
READONLY_BG = "#dceef8"
RESULT_BG = "#e6f4e6"

MODULE_WINDOW = {
    0: ("1260x760", 1080, 650),
    1: ("1520x900", 1220, 760),
    2: ("1500x900", 1220, 760),
    3: ("1540x900", 1240, 760),
    4: ("1580x920", 1260, 780),
    5: ("1600x940", 1280, 800),
    6: ("1600x940", 1280, 800),
    7: ("1560x900", 1240, 760),
    8: ("1600x940", 1280, 800),
    9: ("1580x920", 1260, 780),
}

def apply_common_style(root: tk.Misc) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
    root.option_add("*Font", (FONT_FAMILY, FONT_SIZE))
    root.option_add("*TCombobox*Listbox.font", (FONT_FAMILY, FONT_SIZE))
    style.configure(".", font=(FONT_FAMILY, FONT_SIZE))
    style.configure("TFrame", background=WINDOW_BG)
    style.configure("TLabel", background=WINDOW_BG)
    style.configure("TLabelframe", background=WINDOW_BG, padding=(8, 5))
    style.configure("TLabelframe.Label", background=WINDOW_BG,
                    font=(FONT_FAMILY, FONT_SIZE, "bold"))
    style.configure("TButton", padding=(10, 5))
    style.configure("Primary.TButton", padding=(14, 7),
                    font=(FONT_FAMILY, FONT_SIZE, "bold"))
    style.configure("TCheckbutton", background=WINDOW_BG)
    style.configure("Treeview", rowheight=26, background=PANEL_BG,
                    fieldbackground=PANEL_BG)
    style.configure("Treeview.Heading",
                    font=(FONT_FAMILY, FONT_SIZE, "bold"), padding=(6, 5))
    style.map("Treeview", background=[("selected", "#3478bf")],
              foreground=[("selected", "#ffffff")])
    try:
        root.configure(background=WINDOW_BG)
    except tk.TclError:
        pass

def standardize_module_window(window: tk.Toplevel, module_no: int) -> None:
    geometry, min_width, min_height = MODULE_WINDOW.get(
        module_no, ("1500x900", 1200, 740)
    )
    window.geometry(geometry)
    window.minsize(min_width, min_height)
    window.resizable(True, True)


def create_scrollable_module_page(window: tk.Toplevel) -> ttk.Frame:
    """PATCH 064: stable vertically scrollable module page.

    Improvements over PATCH 063:
      - no bind_all(): destroyed module canvases no longer receive wheel events
      - the page is never shorter than the visible viewport, preserving layout balance
      - scrollregion follows the page's requested size
      - wheel scrolling is ignored by Treeview/Text/Listbox controls
    """
    host = ttk.Frame(window)
    host.pack(fill="both", expand=True)

    canvas = tk.Canvas(
        host,
        highlightthickness=0,
        borderwidth=0,
        background=WINDOW_BG,
    )
    vbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    vbar.pack(side="right", fill="y")

    page = ttk.Frame(canvas)
    page_window = canvas.create_window((0, 0), window=page, anchor="nw")

    state = {"alive": True}

    def _alive() -> bool:
        try:
            return bool(state["alive"] and canvas.winfo_exists())
        except Exception:
            return False

    def _sync_layout(_event=None):
        if not _alive():
            return
        try:
            canvas.update_idletasks()
            viewport_w = max(1, canvas.winfo_width())
            viewport_h = max(1, canvas.winfo_height())
            req_h = max(1, page.winfo_reqheight())

            # Width follows viewport. Height is at least viewport height so modules
            # that use fill/expand retain their original visual balance.
            canvas.itemconfigure(
                page_window,
                width=viewport_w,
                height=max(viewport_h, req_h),
            )
            canvas.configure(scrollregion=canvas.bbox("all"))
        except tk.TclError:
            pass

    page.bind("<Configure>", _sync_layout, add="+")
    canvas.bind("<Configure>", _sync_layout, add="+")

    def _inside_own_scroll_control(target) -> bool:
        current = target
        while current is not None and current is not window:
            if isinstance(current, (ttk.Treeview, tk.Text, tk.Listbox)):
                return True
            current = getattr(current, "master", None)
        return False

    def _wheel(event):
        if not _alive():
            return None
        try:
            target = window.winfo_containing(event.x_root, event.y_root)
        except Exception:
            target = None

        if _inside_own_scroll_control(target):
            return None

        try:
            delta = getattr(event, "delta", 0)
            if delta:
                canvas.yview_scroll((-3 if delta > 0 else 3), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(3, "units")
        except tk.TclError:
            return None
        return "break"

    # Bind to this Toplevel only. Tk's bind tags deliver child events to the
    # containing Toplevel, so global bind_all is unnecessary and unsafe.
    window.bind("<MouseWheel>", _wheel, add="+")
    window.bind("<Button-4>", _wheel, add="+")
    window.bind("<Button-5>", _wheel, add="+")

    def _on_destroy(event):
        if event.widget is window:
            state["alive"] = False

    window.bind("<Destroy>", _on_destroy, add="+")
    window._module_scroll_host = host
    window._module_scroll_canvas = canvas
    window._module_scroll_page = page
    window.after_idle(_sync_layout)
    return page

def _collect_widget_text(widget: tk.Misc, rows: list[str], depth: int = 0) -> None:
    """Collect visible module text for range selection and copying."""
    indent = "  " * min(depth, 5)
    cls = widget.winfo_class()
    try:
        if cls in {
            "TLabel", "Label", "TButton", "Button", "TCheckbutton",
            "Checkbutton", "TRadiobutton", "Radiobutton", "TLabelframe",
            "Labelframe",
        }:
            value = str(widget.cget("text") or "").strip()
            if value:
                rows.append(indent + value)
        elif cls in {"TEntry", "Entry", "TCombobox", "Combobox", "Spinbox"}:
            value = str(widget.get() or "").strip()
            if value:
                rows.append(indent + value)
        elif cls == "Text":
            value = str(widget.get("1.0", "end-1c") or "").strip()
            if value:
                rows.append(indent + value)
        elif cls == "Treeview":
            columns = list(widget["columns"])
            headings = []
            for col in columns:
                heading = str(widget.heading(col, "text") or "").strip()
                if heading:
                    headings.append(heading)
            if headings:
                rows.append(indent + "\t".join(headings))
            item_ids = widget.get_children("")
            limit = 10000
            for iid in item_ids[:limit]:
                values = widget.item(iid, "values")
                if values:
                    rows.append(indent + "\t".join(str(v) for v in values))
            if len(item_ids) > limit:
                rows.append(indent + f"... {len(item_ids)-limit} rows omitted ...")
    except Exception:
        pass

    for child in widget.winfo_children():
        _collect_widget_text(child, rows, depth + 1)


def open_module_text_copy_view(window: tk.Toplevel) -> None:
    """Open a selectable text-only view of the current module screen."""
    rows: list[str] = []
    source = getattr(window, "_module_scroll_page", window)
    _collect_widget_text(source, rows)

    dialog = tk.Toplevel(window)
    language = getattr(getattr(window, "i18n", None), "language", "ja")
    dialog.title("画面文字コピー" if language == "ja" else "Copy screen text")
    dialog.geometry("1050x760")
    dialog.minsize(720, 480)

    frame = ttk.Frame(dialog)
    frame.pack(fill="both", expand=True, padx=8, pady=8)
    text = tk.Text(frame, wrap="word", undo=False)
    ybar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    xbar = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
    text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

    text.grid(row=0, column=0, sticky="nsew")
    ybar.grid(row=0, column=1, sticky="ns")
    xbar.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    text.insert("1.0", "\n".join(rows))
    text.mark_set("insert", "1.0")
    text.focus_set()

    def _select_all(_event=None):
        text.tag_add("sel", "1.0", "end-1c")
        return "break"
    text.bind("<Control-a>", _select_all)
    text.bind("<Control-A>", _select_all)


def add_module_text_copy_button(window: tk.Toplevel, toolbar: tk.Misc) -> None:
    """Add copy-view button and Ctrl+Shift+C shortcut."""
    language = getattr(getattr(window, "i18n", None), "language", "ja")
    label = "画面文字コピー" if language == "ja" else "Copy screen text"
    ttk.Button(
        toolbar, text=label,
        command=lambda: open_module_text_copy_view(window),
    ).pack(side="right", padx=4)
    window.bind(
        "<Control-Shift-C>",
        lambda _e: open_module_text_copy_view(window),
        add="+",
    )
    window.bind(
        "<Control-Shift-c>",
        lambda _e: open_module_text_copy_view(window),
        add="+",
    )

# Compatibility helper retained for post-PATCH474 auxiliary dialogs only.
# Main Module windows/layout above intentionally follow PATCH474 exactly.
def fit_window_to_screen(window, width, height, min_width=640, min_height=420, margin_x=72, margin_y=110):
    window.geometry(f"{int(width)}x{int(height)}")
    window.minsize(int(min_width), int(min_height))
    window.resizable(True, True)
    return int(width), int(height)
