import ast
from pathlib import Path

# PATCH (260917). The 8760-hour insulation/thermal-mass comparison screen's
# "床・土間" row showed 現状断熱位置 as 未確認 (unresolved) even when the
# project's floor thermal settings panel had foundation_bottom_insulation
# confirmed (checked) with slab_under_insulation unchecked -- the row
# population code only ever checked slab_under_insulation, exactly the same
# omission PATCH_016 fixed in environment_engine_v9_1.py's calculation, just
# in a different file/function. This guards both occurrences in module2/app.py
# against regressing back to checking slab_under_insulation alone.

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "module2" / "app.py"
_text = _SRC.read_text(encoding="utf-8-sig")

count = _text.count(
    'floor_saved.get("slab_under_insulation") or floor_saved.get("foundation_bottom_insulation")'
)
if count < 2:
    print(
        f"[NG] Expected at least 2 occurrences of the combined "
        f"slab_under_insulation/foundation_bottom_insulation check in module2/app.py, "
        f"found {count}. The floor-row population in the 8760-hour comparison screen "
        f"may have regressed to checking slab_under_insulation alone, which would show "
        f"現状断熱位置 as 未確認 for projects using foundation-bottom insulation instead "
        f"of under-slab insulation, even though that setting is fully confirmed."
    )
    raise SystemExit(1)

print("[OK] comparison_floor_position_self_check passed.")
