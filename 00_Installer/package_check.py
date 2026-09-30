# -*- coding: utf-8 -*-
"""PATCH_004: Python package check for the AZRAS source edition.

The four-product audit found that 01 Planning and 02 Evaluation stop at start
up on a fresh Python (ModuleNotFoundError: reportlab), while the Installer and
the installation guide said that nothing else had to be installed once Python
was detected.

This module
  * reads requirements.txt of every product folder beside the Installer (the
    same folder search the launcher uses), so the list always follows the
    products actually present;
  * asks the DETECTED Python (not the one running the Installer, which may be a
    frozen EXE) which of those packages it can import;
  * builds the pip command the user runs.

It never installs anything.  No tkinter import, so it is testable headless.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# pip distribution name (lower case) -> import name, where they differ.
IMPORT_NAMES = {
    "pillow": "PIL",
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "pymupdf": "fitz",
    "pyyaml": "yaml",
    "scikit-learn": "sklearn",
}

# Same products, folders and launch files as azras_launcher.PRODUCT_SPECS.
PRODUCTS = (
    ("Planning", ("01_AZRAS_Planning", "01_AZRAS_Planning_Basic", "01_Planning"),
     ("run_AZRAS_Planning_without_build.bat", "run_AZRAS_Planning_Basic_without_build.bat")),
    ("Evaluation", ("02_AZRAS_Evaluation", "02_Evaluation"), ("run_AZRAS_Evaluation_without_build.bat",)),
    ("Compare", ("03_AZRAS_Compare", "03_Compare"), ("run_AZRAS_Compare_without_build.bat",)),
)


@dataclass
class Package:
    pip_name: str
    import_name: str
    optional: bool
    products: list[str] = field(default_factory=list)
    installed: bool | None = None  # None = could not be checked


def import_name(pip_name: str) -> str:
    key = pip_name.strip().lower()
    return IMPORT_NAMES.get(key, key.replace("-", "_"))


def parse_requirements(text: str) -> list[tuple[str, bool]]:
    """(pip name, optional) for every requirement line.

    A line whose comment says it is used by dev_checks only is optional: the
    product runs without it; only its self-checks need it.
    """
    out = []
    for raw in text.splitlines():
        line, _, comment = raw.partition("#")
        line = line.strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~;\[\s]", line, maxsplit=1)[0].strip()
        if not name:
            continue
        out.append((name, "dev_checks" in comment.lower()))
    return out


def product_folders(resolve) -> dict[str, Path]:
    """``resolve`` is azras_launcher.resolve_product."""
    found = {}
    for label, prefixes, bats in PRODUCTS:
        entry = resolve(prefixes, bats)
        if entry is not None:
            found[label] = Path(entry).parent
    return found


def collect_packages(folders: dict[str, Path]) -> list[Package]:
    by_name: dict[str, Package] = {}
    for label, folder in folders.items():
        req = folder / "requirements.txt"
        if not req.is_file():
            continue
        for name, optional in parse_requirements(req.read_text(encoding="utf-8-sig")):
            key = name.lower()
            pkg = by_name.get(key)
            if pkg is None:
                pkg = by_name[key] = Package(name, import_name(name), optional)
            pkg.optional = pkg.optional and optional  # required by any product = required
            if label not in pkg.products:
                pkg.products.append(label)
    return sorted(by_name.values(), key=lambda p: (p.optional, p.pip_name.lower()))


_PROBE = ("import importlib.util,json,sys;"
          "print(json.dumps({m:importlib.util.find_spec(m) is not None for m in sys.argv[1:]}))")


def check_installed(python_path: str, packages: list[Package], timeout: float = 60.0) -> bool:
    """Fill Package.installed using the detected Python.  False = probe failed."""
    if not python_path or not packages:
        return False
    names = sorted({p.import_name for p in packages})
    try:
        cp = subprocess.run([python_path, "-c", _PROBE, *names], capture_output=True, text=True,
                            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        result = json.loads(cp.stdout.strip().splitlines()[-1]) if cp.returncode == 0 else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        result = None
    if not isinstance(result, dict):
        return False
    for p in packages:
        p.installed = bool(result.get(p.import_name))
    return True


def install_command(python_path: str, pip_names: list[str]) -> str:
    """The command the USER runs.  Nothing is executed here."""
    if not pip_names:
        return ""
    exe = python_path or "python"
    name = exe.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name in ("py.exe", "py"):
        exe = "py"
    elif " " in exe:
        exe = f'"{exe}"'
    return f"{exe} -m pip install " + " ".join(pip_names)


def missing(packages: list[Package], include_optional: bool = False) -> list[Package]:
    return [p for p in packages if p.installed is False and (include_optional or not p.optional)]
