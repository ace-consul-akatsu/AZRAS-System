from pathlib import Path

# PATCH (260917). The 8760-hour insulation/thermal-mass comparison screen used
# to show a separate "基礎" (foundation) row that could never show anything
# but 未確認/unresolved, because Module 1 never populates a distinct
# assemblies["foundation"] entry and this project's construction uses an
# integrated mat foundation (べた基礎) where the foundation and the
# ground-floor slab are the same physical pour. After two rounds of
# confusion about where a confirmed foundation-bottom-insulation setting
# should show up, the "foundation" row was removed and the "slab" row's
# label was renamed to 床・土間・ベタ基礎 to make explicit that it now
# covers the mat foundation too. This guards against silently
# reintroducing the dead row or its old label.

_ROOT = Path(__file__).resolve().parent.parent

_module2 = (_ROOT / "module2" / "app.py").read_text(encoding="utf-8-sig")
_components_line = next((l for l in _module2.splitlines() if l.strip().startswith("components = [")), None)
if _components_line is None:
    print('[NG] Could not find the components = [...] line in module2/app.py to check.')
    raise SystemExit(1)
if "foundation" in _components_line:
    print(
        '[NG] module2/app.py\'s components list still includes "foundation" -- the dead '
        '"基礎" comparison row (which could never show anything but 未確認) was '
        "intentionally removed; re-adding it would reintroduce the same confusion."
    )
    raise SystemExit(1)

_envelope = (_ROOT / "services" / "envelope_insulation_model_v1.py").read_text(encoding="utf-8-sig")
if '"床・土間"' in _envelope and '"床・土間・ベタ基礎"' not in _envelope:
    print(
        '[NG] services/envelope_insulation_model_v1.py COMPONENT_LABELS_JA appears to '
        'have reverted the "slab" label from 床・土間・ベタ基礎 back to 床・土間.'
    )
    raise SystemExit(1)
if '"床・土間・ベタ基礎"' not in _envelope:
    print(
        '[NG] services/envelope_insulation_model_v1.py COMPONENT_LABELS_JA is missing '
        'the expected 床・土間・ベタ基礎 label for the "slab" component.'
    )
    raise SystemExit(1)

print("[OK] foundation_row_removed_self_check passed.")
