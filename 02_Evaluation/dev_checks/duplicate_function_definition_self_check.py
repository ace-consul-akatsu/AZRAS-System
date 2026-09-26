from pathlib import Path
import ast

# PATCH addition (260916) -- cross-product process check requested after
# 01_Planning PATCH_017 found that a bug fixed in one function (PATCH_629's
# _round_half_up() rounding fix) silently regressed because a *different*,
# later-added function duplicated the same logic without the fix. That
# specific bug does not exist in this product, but the structural risk --
# two functions in the same scope with the same name, or the same logic
# copy-pasted into a second function -- is generic and worth catching
# automatically before it causes the same kind of drift here.
#
# This check only catches the narrowest, fully-mechanical form of that risk:
# two function definitions with the *same name* in the same scope (module
# top level, or the same class) in the same file. It intentionally does not
# attempt to detect copy-pasted-but-renamed logic (that needs human review),
# so passing this check is necessary but not sufficient evidence that no
# duplicate-logic risk exists in this product.

_ROOT = Path(__file__).resolve().parent.parent

findings = []
for pyfile in sorted(_ROOT.rglob("*.py")):
    if "__pycache__" in str(pyfile) or "/dev_checks/" in str(pyfile).replace("\\", "/"):
        continue
    try:
        text = pyfile.read_text(encoding="utf-8-sig")
        tree = ast.parse(text, filename=str(pyfile))
    except Exception:
        continue

    def scan(body, ctx):
        names = {}
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.setdefault(n.name, []).append(n.lineno)
            if isinstance(n, ast.ClassDef):
                scan(n.body, ctx + "." + n.name)
        for name, lines in names.items():
            if len(lines) > 1:
                findings.append(f"{pyfile.relative_to(_ROOT)}::{ctx}  duplicate function '{name}' at lines {lines}")

    scan(tree.body, pyfile.stem)

if findings:
    print("[NG] duplicate_function_definition_self_check found same-named functions in the same scope:")
    for f in findings:
        print("   -", f)
    print(
        "This does not by itself mean a bug exists, but two same-named functions in one "
        "scope means one silently shadows the other, or one is genuinely dead code left "
        "behind by a refactor -- both are exactly the kind of drift PATCH_017 found in "
        "01_Planning. Review and consolidate before shipping."
    )
    raise SystemExit(1)

print("[OK] duplicate_function_definition_self_check passed: no same-named function definitions found in the same scope.")
