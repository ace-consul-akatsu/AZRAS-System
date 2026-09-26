import ast
from pathlib import Path

# PATCH (260917). After a Gemini submission returned a simplified,
# non-compliant response, the AZRAS AI START instruction text generated for
# EVERY provider (not just Gemini) was strengthened with: an explicit list of
# previously-seen failure modes, a restated hard output contract, and an
# 8-item pre-send self-check checklist. This guards against that strengthened
# template silently regressing back to the older, shorter version (e.g. if a
# future edit to this f-string drops a section without noticing).

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "module1" / "app.py"
_text = _SRC.read_text(encoding="utf-8-sig")

_REQUIRED_MARKERS = [
    "STOP AND READ FIRST",
    "BEFORE YOU RESPOND",
    "calculation_ledger, interpretation_basis, drawing_proof, evidence_status, and confidence",
    "Do not invent",
    "Did I actually look at the drawing pages",
]

missing = [m for m in _REQUIRED_MARKERS if m not in _text]
if missing:
    print(
        "[NG] The strengthened AZRAS AI START template appears to have regressed -- "
        "missing expected section(s):"
    )
    for m in missing:
        print("   -", m)
    raise SystemExit(1)

# Confirm this text is still built inside the request-package generator
# function (not just sitting somewhere else as dead text), and that the
# identity/self-check section still stays generic (does not hardcode a
# specific provider name into the shared template -- that would misidentify
# every other AI that receives the same file).
tree = ast.parse(_text, filename=str(_SRC))
start_text_assign = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(
        getattr(t, "id", None) == "start_text" for t in node.targets
    ):
        start_text_assign = node
        break

if start_text_assign is None:
    print("[NG] Could not find the start_text assignment building the AZRAS AI START text.")
    raise SystemExit(1)

segment = ast.get_source_segment(_text, start_text_assign) or ""
for bad in ("you are gemini", "you are chatgpt", "you are claude", "you are grok"):
    if bad in segment.lower():
        print(
            f"[NG] The shared start_text template hardcodes a specific provider identity "
            f"({bad!r}) -- this template is sent to every AI provider, so hardcoding one "
            f"provider's identity would misidentify every other provider that receives it."
        )
        raise SystemExit(1)

print("[OK] azras_ai_start_template_self_check passed.")
