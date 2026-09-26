from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PATCH_634: this check exists specifically because of the module5/module7-
# style bug class where a variable (e.g. "project_currency") is referenced
# inside a method's UI-building code but never assigned in that method,
# raising a NameError the first time the window is built or the language is
# switched. pyflakes' "undefined name" (F821) check catches this class of
# bug statically, without needing to open every module in the GUI.
#
# Run: python dev_checks/pyflakes_undefined_names_self_check.py
try:
    from pyflakes.api import checkPath
    from pyflakes.reporter import Reporter
except ImportError:
    # PATCH_048: this used to print [SKIP] and exit 0, so a run without
    # pyflakes reported "all dev_checks PASS" while this check never ran.
    # A check that could not run is a failure, not a pass.
    print("[NG] pyflakes is not installed, so undefined names were NOT checked.")
    print("     Install with: pip install pyflakes   (then run this check again)")
    raise SystemExit(1)

import io

files = sorted(
    p for p in _ROOT.rglob("*.py")
    if "PATCH" not in p.parts and "dev_checks" not in p.parts
)

out, err = io.StringIO(), io.StringIO()
reporter = Reporter(out, err)
for f in files:
    warnings = checkPath(str(f), reporter)

output = out.getvalue()
undefined_lines = [line for line in output.splitlines() if "undefined name" in line]
# PATCH_048: a file pyflakes cannot parse (syntax/encoding error) is reported
# on the error stream only; it used to be ignored, so an unparseable file was
# silently "clean".  Treat it as a failure too.
unparsed_lines = [line for line in err.getvalue().splitlines() if line.strip()]

if undefined_lines or unparsed_lines:
    for line in undefined_lines:
        print("[NG]", line)
    for line in unparsed_lines:
        print("[NG] could not check:", line)
    raise SystemExit(1)
print(f"PYFLAKES_UNDEFINED_NAMES_CLEAN_ACROSS_{len(files)}_FILES_PASS")
