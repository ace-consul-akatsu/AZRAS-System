PATCH_010 — module1/app.py: reorder 概略数量 table by construction-trade category

Request: order the 概略数量 (approximate quantities) table by construction
trade, per this explicit sequence:
1 地業工事 / 2 躯体工事 / 3 下地工事 / 4 仕上げ工事 / 5 断熱工事 /
6 建具工事 / 7 金属工事(折版屋根・水切り・笠木等) /
8 ユニット工事(キッチン・ユニットバス等) / 9 給水排水衛生工事 /
10 空調換気工事 / 11 電気工事

Replaced the PATCH_165 discipline-grouping sort key
(_primary_display_sort_key, which grouped by
Architecture/Structure/Electrical/HVAC/Plumbing/Fire and always floated
unresolved/conflicting rows to the very top) with a new keyword-based
classifier, _construction_trade_category_rank(), covering the canonical
English item/category/source text for every construction method in this
codebase (RC, 2x6, steel, AZRAS). Anything matching none of the 11 named
trades falls into an unclassified rank 12 (audit/reference rows such as
section-height or floor-area candidates, mandatory AZRAS scope-coverage
checks, etc.) so nothing is silently dropped from the table -- it is
simply shown after the 11 named trades.

Within the same trade, unresolved/conflicting rows still sort first
(keeps the existing review-queue visibility), then by evidence status,
then by the original calculation order -- so the trade grouping the
マルコさん asked for is now the primary sort key, while still surfacing
what needs review within each trade.

The old PATCH_165 sort key was kept, renamed to
_primary_display_sort_key_LEGACY_PATCH_165, for reference; it is no
longer called anywhere.

Verified: a representative item from each of the 11 trades classifies
correctly (Excavation->1, Column concrete->2, ceiling substrate->3,
Interior final finish->4, Phenolic Foam->5, window glazing->6, Roofing/
Waterproofing->7, Kitchen package->8, Plumbing fixture->9, HVAC
equipment->10, LED lighting->11), plus two RC/AZRAS-specific bilingual
item names correctly classify as 躯体工事(2). An audit-only reference row
(section inter-level height candidate) correctly falls into the
unclassified rank 12.

pyflakes: no new issues. All dev_checks/ scripts still pass.

Files changed:
- module1/app.py (_TRADE_CATEGORY_KEYWORDS, _construction_trade_category_rank
  added; _primary_display_sort_key replaced; old implementation kept as
  _primary_display_sort_key_LEGACY_PATCH_165 for reference)
