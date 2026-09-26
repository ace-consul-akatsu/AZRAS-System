from __future__ import annotations
import json
from pathlib import Path
from functools import lru_cache

# PATCH_005: shared English-canonical -> Japanese item-name translation
# table, used by both Module 1 and Module 5 (and any future module that
# needs the same lookup).
#
# Background: this dictionary previously existed as two SEPARATE, hand-
# maintained Python dict literals -- one inside module1/app.py
# (_localize_takeoff_text's ja_exact.update({...}) block, ~270 entries)
# and one inside module5/app.py (_quantity_item_display_name's local
# "pairs" dict, ~95 entries). Each was missing entries the other one had,
# and every new construction method's vocabulary (this file's initial
# contents merge in the RC-Rahmen terms added directly to module5's dict
# before this consolidation) had to be added to BOTH places by hand or it
# would silently display as raw English in whichever module was missed.
#
# This file is the single shared data source going forward. It intentionally
# holds ONLY flat "translate this exact English phrase to this exact
# Japanese phrase" pairs -- it does not attempt to replace either module's
# own Japanese-source-detection or dynamic-row-generation logic, which stay
# local to each module.
#
# To add a language other than Japanese later (e.g. lang/item_names_fr.json),
# add a new JSON file following the same flat key->value shape and extend
# _PATH_BY_LANGUAGE below; no other code changes should be needed in the
# modules that call translate_item_name().

_LANG_DIR = Path(__file__).resolve().parent.parent / "lang"
_PATH_BY_LANGUAGE = {
    "ja": _LANG_DIR / "item_names_ja.json",
}


@lru_cache(maxsize=None)
def _load(language: str) -> dict[str, str]:
    path = _PATH_BY_LANGUAGE.get(language)
    if path is None or not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def item_translation_table(language: str) -> dict[str, str]:
    """Return the shared item-name translation dict for one language.

    Callers that need to merge this with their own local/dynamic entries
    (e.g. module-specific overrides) should treat the returned dict as
    read-only and build their own combined dict rather than mutating this
    one -- it is cached and shared across every caller in the process.
    """
    return _load(language)


def translate_item_name(text: str, language: str, extra: dict[str, str] | None = None) -> str:
    """Translate one item-name string using the shared table.

    Tries an exact match first (against `extra` if given, then the shared
    table), then falls back to a substring-replace pass over the shared
    table (longest keys first, matching the substring-replace behavior
    already used by both module1 and module5's own local dicts) so a
    partially-matching dynamic label still gets whatever portions of it
    are translatable. Returns the original text unchanged if nothing
    matches, exactly like the two dicts this replaces.
    """
    if language not in _PATH_BY_LANGUAGE:
        return text
    table = _load(language)
    if extra:
        if text in extra:
            return extra[text]
    if text in table:
        return table[text]
    out = text
    combined = table if not extra else {**table, **extra}
    for en, ja in sorted(combined.items(), key=lambda kv: len(kv[0]), reverse=True):
        out = out.replace(en, ja)
    return out
