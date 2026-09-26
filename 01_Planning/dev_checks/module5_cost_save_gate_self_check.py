from pathlib import Path
import ast, sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PATCH_634 regression test for PATCH_631: Module 5's save_output() used to
# unconditionally "raise ValueError(...)" whenever any monetary gap or
# unpriced cost line existed, making it impossible to save a provisional
# result even when the user intended to proceed with defaults. PATCH_631
# replaced that hard block with a messagebox.askyesno confirmation, still
# allowing the user to cancel.
#
# This is a source-level (not behavioral) check: it does not open a real
# Tkinter window, but verifies that save_output() still contains the
# askyesno confirmation call guarding on monetary_gaps/unpriced, and does
# NOT contain a bare "raise ValueError" keyed to the same condition (which
# would mean a future edit silently reintroduced the hard block).

src_path = _ROOT / "module5" / "app.py"
text = src_path.read_text(encoding="utf-8-sig")

required_tokens = ["askyesno", "monetary_gap_count", "unpriced_cost_lines"]
missing = [t for t in required_tokens if t not in text]
if missing:
    print("[NG] module5/app.py is missing expected save-gate tokens:", missing)
    raise SystemExit(1)

tree = ast.parse(text, filename=str(src_path))
save_fn = next(
    (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "save_output"),
    None,
)
if save_fn is None:
    print("[NG] module5/app.py: save_output() not found.")
    raise SystemExit(1)

has_askyesno = any(
    isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "askyesno"
    for n in ast.walk(save_fn)
)
has_hard_raise = any(
    isinstance(n, ast.Raise)
    and isinstance(n.exc, ast.Call)
    and getattr(n.exc.func, "id", "") == "ValueError"
    and "incomplete" in ast.get_source_segment(text, n).lower()
    for n in ast.walk(save_fn)
    if ast.get_source_segment(text, n)
)

if not has_askyesno:
    print("[NG] save_output() no longer asks for confirmation before saving a provisional result.")
    raise SystemExit(1)
if has_hard_raise:
    print("[NG] save_output() appears to have reverted to a hard ValueError block for incomplete costs.")
    raise SystemExit(1)

print("MODULE5_COST_SAVE_GATE_IS_CONFIRM_NOT_BLOCK_PASS")
