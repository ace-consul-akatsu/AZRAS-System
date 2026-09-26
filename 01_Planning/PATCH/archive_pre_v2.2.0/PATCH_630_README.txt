AZRAS Planning PATCH 630

Requested by the developer: the four item names discussed by name
(timber framing total, and the three non-RC internal partition length
rows) still showed in English in the 概略数量 table even after being
translated in chat; the developer asked for the actual Japanese wording
to be put into the software.

Behavior
1. Added the four specifically-requested translations to the item-name
   display table:
   - "AZRAS timber framing total (method-specific provisional total)"
     -> "AZRAS木造軸組材 合計（工法別・暫定合計）"
   - "AZRAS net non-RC internal partition length 1F"
     -> "AZRAS非RC内部間仕切 正味長さ 1F"
   - "AZRAS net non-RC internal partition length 2F"
     -> "AZRAS非RC内部間仕切 正味長さ 2F"
   - "AZRAS total net non-RC internal partition length"
     -> "AZRAS非RC内部間仕切 正味長さ合計"
2. Given the developer's "まだ英語が残っている" (English still remains),
   performed a full audit: extracted every literal "item": "..." string
   used anywhere in Module 1 and checked each English-looking one against
   the translation table. Found and added Japanese translations for 42
   further gaps -- covering ceiling/floor/partition substrate rows, the
   loft/stair soffit and floor-opening rows, steel/girt/pile/rebar member
   names, roof slope/area rows, and audit-only rows -- so the same class
   of gap does not keep resurfacing item-by-item.

Verified
- python -m py_compile passes for module1/app.py.
- Re-ran the audit after the edit: zero English-only item-name strings
  remain unmapped in the translation table (excluding "Item" and "English
  canonical item name", which are schema/column-header text, not row data).
- Confirmed the addition introduced no new duplicate keys in the
  translation table (3 pre-existing duplicate keys were found during the
  check -- "AZRAS actual sloped roof area", "Exterior window glazing",
  "Exterior doors" -- but all three predate this patch and are out of its
  scope).

Not changed in this patch
- No calculation logic changed; this is purely the Japanese display text
  for item names that already existed in English.
