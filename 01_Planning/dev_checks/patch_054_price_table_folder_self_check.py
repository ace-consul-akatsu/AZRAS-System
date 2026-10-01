# -*- coding: utf-8 -*-
"""PATCH_054 self-check: the regional unit-price table folder can be chosen.

The table used to be saved only in <configured Project JSON folder>/Regional_Unit_Price_Tables,
which can differ from the folder the Project was opened from.  Registration now
shows the folder first ("register here" / change / default / cancel), and the
chosen folder is remembered and used by Apply / Register / View.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAIL = []


def check(ok, label, detail=""):
    print(("  [OK]   " if ok else "  [NG]   ") + label + ("" if ok else f" :: {detail}"))
    if not ok:
        FAIL.append(label)


tmp = Path(tempfile.mkdtemp())
os.environ["APPDATA"] = str(tmp / "appdata")  # isolate storage_settings.json
import services.project_export_paths as P  # noqa: E402

print("PATCH_054 self-check")
print("-- 1. setting")
check(P.configured_price_table_directory() is None, "no folder chosen by default")
chosen = tmp / "Dropbox" / "AZRAS" / "Tables"
P.set_configured_price_table_directory(chosen)
check(P.configured_price_table_directory() == chosen.resolve() and chosen.is_dir(), "chosen folder remembered and created")
check(P.load_storage_settings().get("json_save_directory") is None, "Project JSON folder setting untouched")
P.set_configured_price_table_directory(None)
check(P.configured_price_table_directory() is None, "cleared back to default")

print("-- 2. Module 5")
try:
    import tkinter as tk
    _r = tk.Tk(); _r.destroy(); have = True
except Exception as exc:  # noqa: BLE001
    have = False; print(f"  [SKIP] no display: {str(exc)[:60]}")
if have:
    import module5.app as M
    P.set_configured_json_directory(tmp / "JSON")
    root = tk.Tk(); root.withdraw()
    app = M.Module5App(root, ROOT, language="ja")
    default = tmp / "JSON" / "Regional_Unit_Price_Tables"
    check(app._price_table_dir() == default.resolve() or app._price_table_dir() == default, "default = <JSON folder>/Regional_Unit_Price_Tables", app._price_table_dir())
    check("（既定）" in app.price_table_folder.get(), "folder shown on screen as default", app.price_table_folder.get())

    M.filedialog.askdirectory = lambda **k: str(chosen)
    check(app.change_price_table_folder() == chosen.resolve(), "'change folder' button stores the choice")
    check(app._price_table_dir() == chosen.resolve() and "（指定）" in app.price_table_folder.get(),
          "Apply/Register/View now use the chosen folder", app.price_table_folder.get())

    def run_dialog(*actions):
        def drive():
            dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
            buttons = {}

            def walk(w):
                for c in w.winfo_children():
                    try:
                        buttons[str(c.cget("text"))] = c
                    except Exception:  # noqa: BLE001
                        pass
                    walk(c)
            walk(dlg)
            for a in actions:
                buttons[a].invoke()
        app.after(200, drive)
        return app._ask_price_table_folder("登録")

    check(run_dialog("キャンセル") is None, "cancel in the registration folder dialog -> nothing saved")
    check(run_dialog("この保存先で登録") == chosen.resolve(), "'register in this folder' returns the chosen folder")
    other = tmp / "Other"
    M.filedialog.askdirectory = lambda **k: str(other)

    def change_then_ok():
        def drive():
            dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
            btn = {}

            def walk(w):
                for c in w.winfo_children():
                    try:
                        btn[str(c.cget("text"))] = c
                    except Exception:  # noqa: BLE001
                        pass
                    walk(c)
            walk(dlg)
            btn["変更…"].invoke(); btn["この保存先で登録"].invoke()
        app.after(200, drive)
        return app._ask_price_table_folder("登録")
    check(change_then_ok() == other.resolve() and P.configured_price_table_directory() == other.resolve(),
          "'change…' inside the dialog switches the folder for this and later registrations")
    check(run_dialog("既定に戻す", "この保存先で登録") == default, "'use default' inside the dialog returns the default folder")
    check(P.configured_price_table_directory() is None and app._price_table_dir() == default, "'use default' clears the choice")
    src = (ROOT / "module5" / "app.py").read_text(encoding="utf-8")
    i = src.index("def register_regional_price_table")
    body = src[i:i + 3000]
    check(body.index("_ask_price_table_folder") < body.index("RUPT.list_tables"),
          "register asks for the folder before reading/saving the table")
    try:
        app.destroy(); root.destroy()
    except Exception:  # noqa: BLE001
        pass

print()
if FAIL:
    print(f"PATCH_054 self-check: FAIL ({len(FAIL)})")
    sys.exit(1)
print("PATCH_054 self-check: PASS")
