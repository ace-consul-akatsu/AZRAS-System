# -*- coding: utf-8 -*-
"""PATCH_004 self-check: Python packages of the source edition.

A fresh Python stopped 01 Planning and 02 Evaluation at start-up
(ModuleNotFoundError: reportlab) while the Installer said nothing more was
needed.  The Installer now lists every package in the requirements.txt of the
products beside it, checks them with the DETECTED Python, and shows the pip
command for the user to run.  It never installs anything.

Run: python dev_checks/patch_004_python_package_check_self_check.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import package_check as PC  # noqa: E402
import azras_launcher as AL  # noqa: E402

FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


PLANNING_REQ = """# AZRAS Planning - Python runtime/build dependencies (version: VERSION.json)
# Tkinter is included with the standard Windows Python installer.
numpy
pandas
Pillow
opencv-python
PyMuPDF
pypdf
reportlab
pyflakes  # used by dev_checks only
"""
EVALUATION_REQ = """numpy
pandas
reportlab
pyflakes  # used by dev_checks only
jsonschema  # used by dev_checks only (full JSON Schema validation)
"""
COMPARE_REQ = """# Tkinter is included with the standard Windows Python installer.
# No third-party Python package is required for the dependency checker itself.
"""

print("PATCH_004 self-check")
print("-- 1. requirements parsing")
parsed = dict(PC.parse_requirements(PLANNING_REQ))
check(list(parsed) == ["numpy", "pandas", "Pillow", "opencv-python", "PyMuPDF", "pypdf", "reportlab", "pyflakes"],
      "every Planning requirement is read, comments skipped", list(parsed))
check(parsed["pyflakes"] is True and parsed["reportlab"] is False, "a dev_checks-only line is optional")
check(PC.parse_requirements("numpy>=1.26\nreportlab==4.2 ; python_version>'3.8'\n-r other.txt\n")
      == [("numpy", False), ("reportlab", False)], "version specifiers and -r lines")
check(PC.parse_requirements(COMPARE_REQ) == [], "a comments-only file lists nothing")
check((PC.import_name("Pillow"), PC.import_name("opencv-python"), PC.import_name("PyMuPDF"), PC.import_name("reportlab"))
      == ("PIL", "cv2", "fitz", "reportlab"), "pip names map to import names")

print("-- 2. product folders beside the Installer")
saved = AL.BASE
with tempfile.TemporaryDirectory() as td:
    system = Path(td) / "AZRAS"
    for folder, bat, req in (("01_Planning_48", "run_AZRAS_Planning_without_build.bat", PLANNING_REQ),
                             ("02_Evaluation_13", "run_AZRAS_Evaluation_without_build.bat", EVALUATION_REQ),
                             ("03_Compare_08", "run_AZRAS_Compare_without_build.bat", COMPARE_REQ)):
        (system / folder).mkdir(parents=True)
        (system / folder / bat).write_text("@echo off\n", encoding="ascii")
        (system / folder / "requirements.txt").write_text(req, encoding="utf-8")
    (system / "00_Installer_04").mkdir()
    try:
        AL.BASE = system / "00_Installer_04"
        folders = PC.product_folders(AL.resolve_product)
    finally:
        AL.BASE = saved
    check(sorted(folders) == ["Compare", "Evaluation", "Planning"], "all three products are found", sorted(folders))
    pk = PC.collect_packages(folders)
by = {p.pip_name.lower(): p for p in pk}
check(set(by) == {"numpy", "pandas", "pillow", "opencv-python", "pymupdf", "pypdf", "reportlab", "pyflakes", "jsonschema"},
      "the union of every product's requirements", sorted(by))
check(by["reportlab"].products == ["Planning", "Evaluation"] and not by["reportlab"].optional,
      "reportlab is required by Planning and Evaluation (the start-up crash)")
check(by["pyflakes"].optional and by["jsonschema"].optional, "dev_checks-only packages stay optional")
check(all(not p.optional for p in pk[:7]) and all(p.optional for p in pk[7:]), "required packages are listed first")

print("-- 3. checking with a Python, never installing")
probe = [PC.Package("json", "json", False), PC.Package("azras-no-such-package", "azras_no_such_package", False),
         PC.Package("azras-no-such-dev", "azras_no_such_dev", True)]
check(PC.check_installed(sys.executable, probe), "the detected Python answers the probe")
check([p.installed for p in probe] == [True, False, False], "installed / missing are told apart",
      [p.installed for p in probe])
check([p.pip_name for p in PC.missing(probe)] == ["azras-no-such-package"], "an optional package is not reported as missing")
check(not PC.check_installed(str(Path(td) / "no_python.exe"), probe[:1]), "an unusable Python is reported, not guessed")
check(PC.install_command(r"C:\Program Files\Python313\python.exe", ["numpy", "reportlab"])
      == '"C:\\Program Files\\Python313\\python.exe" -m pip install numpy reportlab', "a path with spaces is quoted")
check(PC.install_command(r"C:\Windows\py.exe", ["reportlab"]) == "py -m pip install reportlab", "py.exe becomes py")
src = (ROOT / "package_check.py").read_text(encoding="utf-8") + (ROOT / "azras_installer.py").read_text(encoding="utf-8")
check('"-m", "pip"' not in src and "pip install\"]" not in src and "subprocess.run([python_path, \"-c\"" in src,
      "no code path runs pip; only the import probe is executed")

print("-- 4. installation guide")
for name, stale in (("docs/AZRAS_Installation_Guide_JA.html", "追加インストールは不要"),
                    ("docs/AZRAS_Installation_Guide_EN.html", "no additional installation is required")):
    text = (ROOT / name).read_text(encoding="utf-8")
    check(stale not in text, f"{name} no longer says nothing else is needed")
check("インストール用コマンド" in (ROOT / "docs/AZRAS_Installation_Guide_JA.html").read_text(encoding="utf-8")
      and "Install Command" in (ROOT / "docs/AZRAS_Installation_Guide_EN.html").read_text(encoding="utf-8"),
      "both guides name the Install Command button")

print("-- 5. GUI (skipped without a display)")
try:
    import tkinter as tk
    _probe_tk = tk.Tk()
    _probe_tk.destroy()
    have_display = True
except Exception as exc:  # noqa: BLE001
    have_display = False
    print(f"  [SKIP] no display: {str(exc)[:60]}")
if have_display:
    import azras_installer as I
    from tkinter import messagebox
    shown = []
    saved_info = messagebox.showinfo
    messagebox.showinfo = lambda t, m, **k: shown.append(m)
    saved_collect = PC.collect_packages
    PC.collect_packages = lambda folders: [PC.Package("json", "json", False, ["Planning"]),
                                           PC.Package("azras-no-such-package", "azras_no_such_package", False,
                                                      ["Planning", "Evaluation"]),
                                           PC.Package("azras-no-such-dev", "azras_no_such_dev", True, ["Evaluation"])]
    try:
        for lang in ("ja", "en"):
            app = I.InstallerApp()
            app.language = lang
            app._build_ui()
            app.scan()
            rows = app.tree.get_children()
            check(rows[0] == "python" and "pkg:azras-no-such-package" in rows, f"[{lang}] package rows follow Python",
                  rows)
            st = app.tree.item("pkg:azras-no-such-package")["values"][3]
            check(st == I.localize_status("missing", lang), f"[{lang}] a missing package shows Not Detected", st)
            check("azras-no-such-package" in app.footer_var.get(), f"[{lang}] the footer names the missing package")
            shown.clear()
            app.show_install_command()
            check(shown and "-m pip install azras-no-such-package" in shown[0] and "azras-no-such-dev" in shown[0],
                  f"[{lang}] the command is shown (required, plus the optional one separately)")
            check(app.clipboard_get().endswith("-m pip install azras-no-such-package"),
                  f"[{lang}] the required command is on the clipboard")
            app.destroy()
    finally:
        messagebox.showinfo = saved_info
        PC.collect_packages = saved_collect

print()
if FAIL:
    print("[NG] PATCH_004 self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PATCH_004_PYTHON_PACKAGE_CHECK_PASS")
