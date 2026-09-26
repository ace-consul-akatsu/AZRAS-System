from pathlib import Path
import ast, sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PATCH_634 baseline check: every .py file under the package must at least
# parse as valid Python. This mirrors the old delivery-time
# "all_NN_python_sources_compile" entry seen in past PATCH_*_REGRESSION.json
# files, but as a script that can actually be re-run instead of a one-off
# manual record.
errors = []
files = sorted(p for p in _ROOT.rglob("*.py") if "PATCH" not in p.parts and "dev_checks" not in p.parts)
for f in files:
    try:
        ast.parse(f.read_text(encoding="utf-8-sig"), filename=str(f))
    except SyntaxError as exc:
        errors.append(f"{f.relative_to(_ROOT)}: {exc}")

if errors:
    for e in errors:
        print("[NG]", e)
    raise SystemExit(1)
print(f"ALL_{len(files)}_PYTHON_SOURCES_COMPILE_PASS")
