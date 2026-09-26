AZRAS Planning PATCH 625

Cause found: reported by the developer via screenshot. The "Saved Module 1
Result" window (opened via "保存済みM1結果確認") shows every row's item name
in English even when the UI language selector is set to Japanese, while the
window's own headers/labels ("項目", "値", "単位"...) correctly switch to
Japanese. This became especially visible after importing an AI takeoff JSON
(English-canonical "item" values per the AI contract), which made the whole
table read as English text sitting inside an otherwise-Japanese window.

Cause: this specific display window read only row["item"]/row["canonical_item"]
(the English-canonical value) with no language branch at all, unlike most of
the rest of the UI which explicitly branches on self.i18n.language.

Behavior
- module1/app.py: when self.i18n.language == "ja", the Saved Module 1 Result
  table now prefers row["source_text_original"]["item"] (the original
  source-language wording preserved per the Constitution's English-canonical/
  display-translation rule) when it is present and non-empty, falling back to
  the English-canonical item name otherwise. When the UI language is English,
  behavior is unchanged.

Known remaining limitation (not fixed in this patch)
- A few PRE_TAKEOFF-generated rows (for example local_ids 2 and 3 in the
  current worklist template, "Exterior window glazing" / "Exterior doors")
  have source_text_original.item already written in English rather than the
  original Japanese drawing wording, so those specific rows will still show
  English text even after this fix. That is a PRE_TAKEOFF-generation data
  gap (the request template's own placeholder text), not this display
  window's logic, and is a separate fix in a different part of the code.

Verified
- python -m py_compile passes for module1/app.py.
- Confirmed the fallback correctly returns the English-canonical name when
  source_text_original is absent or empty, so no row ever renders blank.

Not changed in this patch
- No stored data changed. This only affects what text is shown in this one
  results window; the underlying item/canonical_item/source_text_original
  fields in Project JSON are untouched.
