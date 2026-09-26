PATCH_005 — consolidate module1/module5 item-name translation dicts into a shared lang/ file

Background: following the マルコさん's question "is there an S造 (steel)
dictionary in Module 5? What about other construction methods?", an audit
found:
- module5/app.py's _quantity_item_display_name kept its own local ~95-entry
  English->Japanese dict, containing essentially NO steel/S造 vocabulary
  (0 entries for girt/purlin/base-plate/anchor-bolt/gusset/PHC-pile/etc,
  0 for masonry, only 1 for mass-timber/CLT).
- module1/app.py's _localize_takeoff_text kept a SEPARATE, much larger
  (~270-entry) English->Japanese dict, which DID already have ~9-15
  steel-specific entries (girt, Neko bracket, PHC pile, structural steel,
  etc.) plus many others module5 never had.
- Neither module's dict was a superset of the other; each was missing
  entries the other one had, and every future construction-method
  vocabulary addition would need to be hand-copied into both files or the
  same silent English-fallback bug (PATCH_004) would recur -- for S造,
  masonry, mass-timber now, and for any future language (French/German
  etc.) later, multiplied by however many modules exist.

Fix (architecture, not just a data patch): consolidated the flat exact-
match portions of both dicts into a single shared data file,
lang/item_names_ja.json (302 unique entries: union of both modules' prior
tables; where the same English key existed in both with different Japanese
wording, module1's wording was kept as the more established source --
22 such conflicts existed, e.g. "Exterior window glazing" was
"外壁窓ガラス" in module5 vs "外部窓ガラス" in module1).

Added core/item_translations.py: a small shared loader
(item_translation_table(language) / translate_item_name(...)) that reads
lang/item_names_ja.json (cached), with the language->file mapping isolated
in one place (_PATH_BY_LANGUAGE) so adding e.g. lang/item_names_fr.json
later needs no changes in module1/module5, only a new entry in that one
dict.

- module5/app.py: _quantity_item_display_name's local "pairs" dict literal
  is now `pairs=item_translation_table("ja")`. Full replacement -- module5
  no longer carries any local item-name dict.
- module1/app.py: _localize_takeoff_text's existing ~968-line
  Japanese-source-detection / substring-replacement logic was NOT touched
  (too large and interdependent with _CANONICAL_EN_REPLACEMENTS to safely
  refactor in one pass). Instead, an ADDITIVE fallback was inserted at the
  top of the ja-language branch: check the shared table for an exact match
  first, and return immediately if found. Since the shared file's wording
  for every key module1 already had is IDENTICAL to module1's own existing
  value (module1 was the priority source during the merge), this is a
  no-op for every term module1 already handled correctly, and only adds
  new coverage for terms module1 didn't have (e.g. the 5 AZRAS
  mandatory-scope-coverage items and other module5-only entries).

Added dev_checks/shared_item_translation_self_check.py: verifies the JSON
file exists/is valid/has 200+ entries, verifies module5 no longer has a
large local dict literal and both modules reference
core.item_translations, and cross-checks that a historically module1-only
term is now translatable via module5's function AND a historically
module5-only term is now translatable via module1's function (proving
real sharing, not just coincidental duplicate coverage).

Verified: all 6 dev_checks scripts pass, including the new one. Spot-
checked 8 terms (previously-working module1 terms, previously-working
module5/RC-Rahmen terms, and cross-module terms) via both functions
standalone -- all produce the expected Japanese text, with zero change to
any term either module already translated correctly before this patch.

Note for the future: consider extending this same lang/item_names_<code>.json
+ core/item_translations.py pattern to any other module that needs
item-name display translation, rather than adding a third local dict.

Files changed:
- lang/item_names_ja.json (new, 302 entries)
- core/item_translations.py (new)
- module5/app.py (_quantity_item_display_name: local dict -> shared loader)
- module1/app.py (_localize_takeoff_text: added additive shared-table fallback)
- dev_checks/shared_item_translation_self_check.py (new)
