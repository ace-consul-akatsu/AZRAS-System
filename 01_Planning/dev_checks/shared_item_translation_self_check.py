from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PATCH_005 regression test: module1/app.py and module5/app.py used to each
# maintain their own separate, independently-incomplete English->Japanese
# item-name translation dict, so a term known to one module could still
# display as raw English in the other (e.g. RC-Rahmen terms were missing
# from module5's dict; steel/girt/PHC-pile terms were missing from
# module5's dict; several AZRAS mandatory-scope-coverage terms were missing
# from module1's dict). Both are now consolidated into
# lang/item_names_ja.json via core/item_translations.py.
#
# This check verifies:
#   1. lang/item_names_ja.json exists, is valid JSON, and has a reasonable
#      minimum number of entries (guards against an empty/corrupted file).
#   2. module5/app.py no longer defines a large local "pairs = {...}"
#      literal in _quantity_item_display_name (i.e. it wasn't silently
#      reverted to a duplicate local dict).
#   3. A term that used to exist ONLY in module1's dict is now translatable
#      via module5's function, and a term that used to exist ONLY in
#      module5's dict is now translatable via module1's function --
#      proving the two modules are actually sharing one source, not just
#      coincidentally both containing the same entry.

import ast
import json

json_path = _ROOT / "lang" / "item_names_ja.json"
if not json_path.exists():
    print("[NG] lang/item_names_ja.json is missing.")
    raise SystemExit(1)
try:
    table = json.loads(json_path.read_text(encoding="utf-8-sig"))
except Exception as exc:
    print(f"[NG] lang/item_names_ja.json is not valid JSON: {exc}")
    raise SystemExit(1)
if not isinstance(table, dict) or len(table) < 200:
    print(f"[NG] lang/item_names_ja.json has only {len(table) if isinstance(table, dict) else 'N/A'} entries (expected 200+).")
    raise SystemExit(1)

m5_src = (_ROOT / "module5" / "app.py").read_text(encoding="utf-8-sig")
m5_tree = ast.parse(m5_src)
found_large_local_dict = False
uses_shared_loader = "item_translation_table" in m5_src
for node in ast.walk(m5_tree):
    if isinstance(node, ast.FunctionDef) and node.name == "_quantity_item_display_name":
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Dict) and len(sub.value.keys) > 20:
                found_large_local_dict = True
if found_large_local_dict:
    print("[NG] module5/app.py._quantity_item_display_name appears to have reverted to a large local dict literal instead of the shared table.")
    raise SystemExit(1)
if not uses_shared_loader:
    print("[NG] module5/app.py no longer references core.item_translations.item_translation_table.")
    raise SystemExit(1)

m1_src = (_ROOT / "module1" / "app.py").read_text(encoding="utf-8-sig")
if "item_translation_table" not in m1_src:
    print("[NG] module1/app.py no longer references core.item_translations.item_translation_table.")
    raise SystemExit(1)

# Cross-module sharing spot check: pull the two live functions and confirm
# each can translate a term that historically lived only in the OTHER
# module's dict.
import importlib.util

def _load_module5_display_fn():
    for node in ast.walk(m5_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_quantity_item_display_name":
            src = ast.get_source_segment(m5_src, node)
            ns = {}
            exec(src, ns)
            return ns["_quantity_item_display_name"]
    raise RuntimeError("not found")

def _load_module1_localize_fn():
    import re as _re
    m1_tree = ast.parse(m1_src)
    canon = None
    for node in m1_tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_CANONICAL_EN_REPLACEMENTS" for t in node.targets):
            canon = ast.literal_eval(node.value)
            break
    for node in ast.walk(m1_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_localize_takeoff_text":
            src = ast.get_source_segment(m1_src, node)
            ns = {"re": _re, "_CANONICAL_EN_REPLACEMENTS": canon or {}}
            exec(src, ns)
            return ns["_localize_takeoff_text"]
    raise RuntimeError("not found")

class _FakeI18N:
    language = "ja"
class _Fake:
    i18n = _FakeI18N()

m5_fn = _load_module5_display_fn()
m1_fn = _load_module1_localize_fn()

# Historically module1-only term: module5 must now resolve it too.
term_from_module1_only = "Steel connections: unresolved/estimated item count"
m5_result = m5_fn(_Fake(), term_from_module1_only)
if m5_result == term_from_module1_only:
    print(f"[NG] module5 still cannot translate a module1-only term: {term_from_module1_only!r}")
    raise SystemExit(1)

# Historically module5-only term: module1 must now resolve it too.
term_from_module5_only = "AZRAS internal RC party-wall concrete"
m1_result = m1_fn(_Fake(), term_from_module5_only)
if m1_result == term_from_module5_only:
    print(f"[NG] module1 still cannot translate a module5-only term: {term_from_module5_only!r}")
    raise SystemExit(1)

print(f"SHARED_ITEM_TRANSLATION_CONSISTENCY_PASS ({len(table)} entries)")
