from __future__ import annotations
import re, shutil, subprocess, tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

BASE = Path(__file__).resolve().parent
SYSTEM = BASE.parent


def _version_key(name: str):
    nums = [int(x) for x in re.findall(r"\d+", name)]
    return tuple(nums) if nums else (0,)


def _candidate_roots():
    """Search the Installer folder, its AZRAS version folder, and nearby parents."""
    roots = []
    p = BASE
    for _ in range(6):
        roots.extend([p, p.parent])
        p = p.parent
    out, seen = [], set()
    for r in roots:
        try:
            r = r.resolve()
        except Exception:
            continue
        if r in seen or not r.exists() or not r.is_dir():
            continue
        seen.add(r)
        out.append(r)
    return out


def resolve_product(folder_prefixes, bat_names, main_name: str = "main.py") -> Path | None:
    """Resolve a product entry point across current and historical folder names.

    PATCH p019:
    Public product names are authoritative, but historical source-folder/BAT
    identifiers remain supported where required for compatibility. The resolver
    therefore accepts aliases rather than forcing the release folder back to an
    obsolete public name.
    """
    if isinstance(folder_prefixes, str):
        folder_prefixes = (folder_prefixes,)
    if isinstance(bat_names, str):
        bat_names = (bat_names,)
    folder_prefixes = tuple(folder_prefixes)
    bat_names = tuple(bat_names)

    candidates: list[Path] = []
    for root in _candidate_roots():
        for folder_prefix in folder_prefixes:
            # 1. exact canonical/current or historical folder.
            canonical = root / folder_prefix
            if canonical.is_dir():
                for rel in (*bat_names, main_name):
                    p = canonical / rel
                    if p.is_file():
                        candidates.append(p)

            # 2. versioned/extracted sibling folders.
            try:
                children = [c for c in root.iterdir() if c.is_dir() and c.name.startswith(folder_prefix)]
            except Exception:
                children = []
            for child in children:
                for rel in (*bat_names, main_name):
                    p = child / rel
                    if p.is_file():
                        candidates.append(p)
                # 3. tolerate one extra wrapper directory produced by some unzip tools.
                try:
                    for sub in child.iterdir():
                        if not sub.is_dir():
                            continue
                        for rel in (*bat_names, main_name):
                            p = sub / rel
                            if p.is_file():
                                candidates.append(p)
                except Exception:
                    pass

    if not candidates:
        return None

    # Prefer BAT, then newest/highest-version folder.
    candidates = list(dict.fromkeys(candidates))
    candidates.sort(
        key=lambda p: (
            1 if p.name.lower().endswith(".bat") else 0,
            _version_key(p.parent.name),
            p.stat().st_mtime if p.exists() else 0,
        ),
        reverse=True,
    )
    return candidates[0]


def launch(entry: Path | None, folder_prefixes, bat_names):
    if isinstance(folder_prefixes, str):
        folder_prefixes = (folder_prefixes,)
    if isinstance(bat_names, str):
        bat_names = (bat_names,)
    if entry is None or not entry.exists():
        folder_prefix = folder_prefixes[0]
        bat_name = bat_names[0]
        expected = SYSTEM / folder_prefix / bat_name
        messagebox.showerror(
            "AZRAS",
            "Product launcher was not found.\n\n"
            f"Expected product: {folder_prefix}\n"
            f"Typical launcher: {expected}\n\n"
            f"AZRAS also searches this Installer's folder and its parent folders "
            f"for a sibling folder whose name starts with \"{folder_prefix}\" "
            f"(for example \"{folder_prefix}_v1.0.xxx\"), including one version "
            f"suffix. If no such folder or launcher .bat exists there, this "
            f"error is shown.\n"
            "Keep 00 / 01 / 02 / 03 product folders in the same AZRAS version folder."
        )
        return

    if entry.suffix.lower() == ".bat":
        subprocess.Popen(["cmd.exe", "/c", "start", "", str(entry)], cwd=str(entry.parent))
        return

    # BAT-less source-edition fallback.
    py = shutil.which("pyw.exe") or shutil.which("pyw") or shutil.which("pythonw.exe") or shutil.which("pythonw")
    if py:
        subprocess.Popen([py, str(entry)], cwd=str(entry.parent))
        return
    py = shutil.which("py.exe") or shutil.which("py") or shutil.which("python.exe") or shutil.which("python")
    if py:
        subprocess.Popen([py, str(entry)], cwd=str(entry.parent))
        return
    messagebox.showerror("AZRAS", f"Python launcher was not found for:\n{entry}")


PRODUCT_SPECS = [
    (
        "P", "AZRAS Planning",
        ("01_AZRAS_Planning", "01_AZRAS_Planning_Basic", "01_Planning"),
        ("run_AZRAS_Planning_without_build.bat", "run_AZRAS_Planning_Basic_without_build.bat"),
    ),
    (
        "E", "AZRAS Evaluation",
        ("02_AZRAS_Evaluation", "02_Evaluation"),
        ("run_AZRAS_Evaluation_without_build.bat",),
    ),
    (
        "C", "AZRAS Compare",
        ("03_AZRAS_Compare", "03_Compare"),
        ("run_AZRAS_Compare_without_build.bat",),
    ),
]

def main():
    app = tk.Tk()
    app.title("AZRAS v2.2.0")
    app.geometry("560x350")
    app.resizable(False, False)
    ttk.Label(app, text="AZRAS", font=("Yu Gothic UI", 28, "bold")).pack(pady=(24, 2))
    ttk.Label(app, text="Adaptive Zero-Rebuild Asset System  |  v2.2.0", font=("Yu Gothic UI", 11)).pack(pady=(0, 18))
    frame = ttk.Frame(app)
    frame.pack(fill="x", padx=50)
    for code, label, prefixes, bats in PRODUCT_SPECS:
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=7)
        ttk.Label(row, text=code, width=4, font=("Yu Gothic UI", 18, "bold")).pack(side="left")
        ttk.Button(
            row,
            text=label,
            command=lambda fp=prefixes, bn=bats: launch(resolve_product(fp, bn), fp, bn),
        ).pack(side="left", fill="x", expand=True, ipady=7)
    ttk.Label(
        app,
        text="Validated set: Planning 2.2.0 / Evaluation 2.2.0 / Compare 2.2.0",
        font=("Yu Gothic UI", 9),
    ).pack(side="bottom", pady=(4, 14))
    ttk.Label(app, text="v2.2.0: Planning / Evaluation / Compare", font=("Yu Gothic UI", 9)).pack(side="bottom")
    app.mainloop()

if __name__ == "__main__":
    main()
