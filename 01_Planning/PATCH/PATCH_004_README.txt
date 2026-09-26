PATCH_004 — module5/app.py: add missing Japanese translations for RC-Rahmen AI-takeoff item names

Background: Module 5's construction-cost breakdown table showed several
item names in raw English (e.g. "Isolated footing / grade beam concrete",
"under-slab insulation", "section inter-level height candidate 1/2",
"1F horizontal ceiling-area candidate", "ceiling substrate applicable
area", "floor-finish applicable area 1F/2F", etc.) even with the UI
language set to Japanese.

Root cause: Module 5 maintains its OWN item-name translation dictionary
(_quantity_item_display_name's "pairs" dict) completely separate from
Module 1's own translation table (module1/app.py). A prior patch closed
"46 remaining gaps" in Module 1's table, but that work was never mirrored
into Module 5's separate dictionary. The specific gap hit here is the
canonical English item names used by the AZRAS_AI_TAKEOFF schema for
RC-Rahmen (RC rigid-frame) structural/substrate scope coverage -- Module
5's dictionary was built out mostly around the AZRAS/2x6-timber
vocabulary and never had RC-Rahmen-specific entries added.

Fix: added ~30 missing entries to module5/app.py's _quantity_item_display_name
pairs dict covering every English item name that appeared untranslated on
screen (isolated footing/grade-beam concrete, under-slab insulation, RC
wall concrete, column/beam/slab concrete, the 3 section inter-level-height
candidates, the ceiling/floor-finish applicable-area and provisional-
general-specification candidates, and the 5 AZRAS mandatory-scope-coverage
items: internal RC party wall, internal 2x6 partition framing, ceiling
framing, 1F floor substrate, 2F floor framing, roof framing).

Verified: called _quantity_item_display_name directly (extracted
standalone) against all 15 previously-untranslated strings from the
screenshot; all now return the correct Japanese text.

Note: this is the second known instance of Module 1 and Module 5
maintaining duplicate, independently-incomplete item-name translation
dictionaries (see also PATCH history under "closed 46 remaining gaps" for
Module 1's own table). A future patch should consider consolidating both
into one shared translation table (e.g. under core/) so this class of gap
cannot recur in only one of the two modules.

Files changed:
- module5/app.py (_quantity_item_display_name pairs dict only)
