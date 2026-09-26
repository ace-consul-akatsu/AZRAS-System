from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import ast, sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PATCH_016 (260916) regression test for PATCH_629 (260915).
#
# PATCH_629 introduced _round_half_up() in module1/app.py specifically
# because Python's built-in round() uses round-half-to-even and is also
# subject to binary floating-point representation error (round(2.005, 2)
# can yield 2.0 instead of 2.01). It was applied to three places: the
# single-value "承認値" (approved_quantity) decision, the "追加承認値"
# additional-item decision, and the "RC/2×6外壁の内訳値" exterior-wall
# split decision.
#
# A later patch added _screen_review_structured_decision() to support
# compound (multi-field) answers. Its per-field loop computed
# vals[key] = float(raw) directly and never called _round_half_up(),
# so the RC/2x6 exterior-wall split silently regressed back to plain
# float storage even though the single-value path (which falls through
# to _screen_review_decision()) still called _round_half_up() correctly.
# This is a source-level check that vals[key] is rounded before use, plus
# a behavioral check that _round_half_up()'s own known edge cases
# (2.005 -> 2.01, 0.125 -> 0.13) still hold, so neither half of this fix
# can silently drift apart again without this check failing.

src_path = _ROOT / "module1" / "app.py"
text = src_path.read_text(encoding="utf-8-sig")

if "_screen_review_structured_decision" not in text:
    print("[NG] module1/app.py: _screen_review_structured_decision() not found.")
    raise SystemExit(1)

tree = ast.parse(text, filename=str(src_path))
fn = next(
    (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_screen_review_structured_decision"),
    None,
)
if fn is None:
    print("[NG] module1/app.py: _screen_review_structured_decision() not found by AST walk.")
    raise SystemExit(1)

fn_src = ast.get_source_segment(text, fn) or ""
if "_round_half_up" not in fn_src:
    print(
        "[NG] _screen_review_structured_decision() no longer calls _round_half_up() "
        "-- the RC/2x6 exterior-wall split (and any other compound answer) would "
        "silently store unrounded floats again, regressing PATCH_629."
    )
    raise SystemExit(1)

# Behavioral check: reimplement the exact algorithm _round_half_up() uses
# (Decimal + ROUND_HALF_UP) and confirm it still differs from plain
# round() on the known edge cases PATCH_629 was written to fix. This does
# not import module1/app.py (a large Tkinter module) to keep this check
# fast and headless-safe; the source-level check above already confirms
# the real function is wired in.


def _round_half_up(value, digits=2):
    quant = Decimal("1").scaleb(-digits)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


cases = [(2.005, 2, 2.01), (0.125, 2, 0.13), (35.415, 2, 35.42)]
failures = []
for value, digits, expected in cases:
    got = _round_half_up(value, digits)
    if abs(got - expected) > 1e-9:
        failures.append((value, digits, expected, got))

if failures:
    print("[NG] _round_half_up() reference implementation failed known edge cases:", failures)
    raise SystemExit(1)

# Also confirm plain round() would have gotten at least one of these wrong,
# so this check is actually exercising the bug PATCH_629 fixed rather than
# a case where round() happens to agree with round-half-up.
if all(abs(round(v, d) - e) < 1e-9 for v, d, e in cases):
    print(
        "[NG] test cases no longer distinguish _round_half_up() from plain round() "
        "-- update the case list so this check still catches a regression."
    )
    raise SystemExit(1)

print("[OK] round_half_up_regression_self_check passed.")
