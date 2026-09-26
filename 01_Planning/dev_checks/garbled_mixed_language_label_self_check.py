import ast
import re
from pathlib import Path

# PATCH (260916). Freely-worded item names imported from external AI-review
# data (e.g. an AZRAS_AI_TAKEOFF JSON import) were showing up in the
# Japanese UI as a garbled mixed-language mashup, such as
# "Electrical 配線 / 電線管 / circuiting" instead of a clean Japanese label.
# Root causes fixed:
#   1. _localize_takeoff_text()'s Japanese-mode substitution used a plain
#      str.replace() loop, which is case-sensitive (so a capitalized word
#      like "Electrical" silently missed a lowercase-only dictionary entry
#      "electrical") and matches raw substrings inside longer words (so the
#      key "duct" matched inside "ductwork", leaving "ダクトwork").
#   2. Plural English words with no Japanese equivalent left a bare "s"
#      glued onto the translated Japanese word (e.g. "幹線s", "器具s").
# This check does not attempt to guarantee full translation coverage for
# every possible externally-authored phrase (that is an open-ended
# dictionary-coverage problem) -- it only guards the two *mechanical*
# regressions above, plus a small set of concrete phrases seen in the field.

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "module1" / "app.py"
_text = _SRC.read_text(encoding="utf-8-sig")

tree = ast.parse(_text, filename=str(_SRC))
fn_node = next(
    (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_localize_takeoff_text"),
    None,
)
if fn_node is None:
    print("[NG] module1/app.py: _localize_takeoff_text() not found.")
    raise SystemExit(1)

fn_src = ast.get_source_segment(_text, fn_node) or ""
if "re.IGNORECASE" not in fn_src or r"\b(?:" not in fn_src:
    print(
        "[NG] _localize_takeoff_text() no longer appears to use a case-insensitive, "
        "word-boundary regex substitution for its Japanese-mode phrase pass -- this "
        "would silently regress to the old case-sensitive/partial-word-matching "
        "str.replace() loop that produced garbled mixed-language labels."
    )
    raise SystemExit(1)

if r"s\b" not in fn_src or "ぁ-ん" not in fn_src:
    print(
        "[NG] _localize_takeoff_text() no longer appears to strip a stray trailing "
        "\"s\" left glued to a translated Japanese word (e.g. \"幹線s\", \"器具s\")."
    )
    raise SystemExit(1)

# Behavioral check: extract and run the real function (no GUI/self needed
# beyond i18n.language) against known-problematic phrases.
lines = fn_src.split("\n")
lines = [l[4:] if l.startswith("    ") else l for l in lines]
fn_src2 = "\n".join(lines)

mod_ns = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(
        getattr(t, "id", None) == "_CANONICAL_EN_REPLACEMENTS" for t in node.targets
    ):
        exec(ast.get_source_segment(_text, node), {}, mod_ns)

ns = {"re": re, "_CANONICAL_EN_REPLACEMENTS": mod_ns.get("_CANONICAL_EN_REPLACEMENTS", {})}
try:
    exec(fn_src2, ns)
    func = ns["_localize_takeoff_text"]
except Exception as e:
    print(f"[NG] Could not extract/exec _localize_takeoff_text() for a behavioral test: {e}")
    raise SystemExit(1)


class _FakeI18n:
    language = "ja"


class _FakeSelf:
    i18n = _FakeI18n()


cases = [
    "Electrical wiring / conduit / circuiting",
    "Distribution panels / feeders / grounding",
    "LED lighting fixtures — main type",
    "Domestic water and sanitary drainage / piping",
    "Branch 配線 / 電線管",
    "Cold-water 配管",
    "Hot-water 配管",
    "屋根 structural sheathing / decking",
]

_stray_suffix_re = re.compile(r"[ぁ-んァ-ヶ一-龯々〆ヵヶ]s\b")
failures = []
for case in cases:
    try:
        out = func(_FakeSelf(), case)
    except Exception as e:
        failures.append((case, f"raised {e!r}"))
        continue
    if _stray_suffix_re.search(out):
        failures.append((case, f"stray plural 's' glued to Japanese text: {out!r}"))

if failures:
    print("[NG] garbled_mixed_language_label_self_check found regressions:")
    for case, reason in failures:
        print(f"   - {case!r}: {reason}")
    raise SystemExit(1)

print("[OK] garbled_mixed_language_label_self_check passed.")
