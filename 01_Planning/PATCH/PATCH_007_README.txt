PATCH_007 — module1/app.py: fix stale reinforcing-steel quantity shown in the "edit provisional value" dialog

Reported: double-clicking the reinforcing steel ("鉄筋") row in Module 1's
概略数量 table opened the "実数量の確認・修正" (confirm/edit) dialog
pre-filled with 0.864 t. This matched Module 5's own row 12 "鉄筋" (marked
保留・積算対象外 -- on hold, excluded from the cost total), but Module 5's
row 7 "鉄筋" (確定・根拠単価, the value actually used in the cost total)
shows 16.215 t. The dialog was showing the wrong, excluded number.

Root cause: this is a "reinforcement (provisional general specification)"
row, whose quantity is meant to be rebar_rate_kg_per_m3 x total RC
concrete volume / 1000. Two separate bugs combined:
1. The row's stored accepted_quantity (0.864 = 7.2 m3 x 120 kg/m3 / 1000)
   was written at an early takeoff stage using only a partial concrete
   figure (isolated-footing concrete alone, 7.2 m3) and was never
   refreshed later as more RC components (columns, beams, slabs,
   underground foundations, internal RC party-wall concrete) were
   resolved, bringing the true total to 135.129 m3.
2. The dialog's own "再計算" (recalculate) button, recalc_from_parameter(),
   only ever searched for a row named exactly "total concrete" (only used
   once RC walls are fully resolved) or, as a fallback, two 2x6/timber-
   specific row names. For an RC-Rahmen project with RC walls still
   unresolved, neither matched, so recalculating never updated the value
   either -- the button looked like it worked but silently left
   concrete_total at 0.

Fix: added _current_rc_concrete_total(), which computes the RC concrete
total by summing the individual, currently-accepted component rows
(foundation/slab, columns, beams, upper slabs, underground foundations,
RC wall concrete, internal RC party-wall concrete) FIRST, falling back to
a named summary row ("total concrete" / "コンクリート小計（RC壁未算入）" /
"AZRAS total RC concrete") only if no individual components are found, and
finally to the 2x6/timber-specific row names as a last resort. Summing
individual components first (rather than trusting a cached summary row)
matters because that summary row can itself go stale for the same reason
the reinforcement row did.

Both call sites now use this helper:
- recalc_from_parameter() (the dialog's own recalculate button) -- now
  actually updates the value for RC/AZRAS projects, which it silently
  failed to do before.
- The dialog's INITIAL qty_var value: for a "reinforcement" provisional
  row, the correct current value (component total x rebar rate) is now
  computed and used to override a materially different stored value
  before the dialog is even shown, rather than trusting whatever was
  written into accepted_quantity earlier in the takeoff.

Verified (standalone extraction, no GUI needed for this part):
- With individual RC component rows present (12.255+11.081+28.839+36.765+
  31.569+14.620 = 135.129) and a deliberately stale
  "コンクリート小計（RC壁未算入）" row also present at 249.919, the helper
  correctly returns 135.129 (components), not 249.919 (stale summary).
- With only the summary row present, the helper falls back to it (249.919)
  as a last resort.
- End-to-end: a row with stale accepted_quantity=0.864 now opens the
  dialog with 16.215 as the initial value, exactly matching Module 5's
  confirmed reinforcing-steel total (which itself derives from 135.129 m3
  x 120 kg/m3 / 1000 = 16.215 t).

pyflakes and all dev_checks/ scripts: no new issues.

Note: Module 1's own "コンクリート小計（RC壁未算入）" row (currently showing
249.919 m3) is itself the row that appears stale/inconsistent with the
135.129 m3 figure Module 5 actually adopts -- this patch works around it
for the reinforcement dialog specifically, but the underlying subtotal row
not being refreshed is a separate, likely broader issue worth a dedicated
look (this row is also flagged directly in Module 5's own "残存項目" list
alongside "独立基礎・地中梁" etc., suggesting it may be a general
"summary rows go stale" pattern rather than something unique to
reinforcement).

Files changed:
- module1/app.py (_edit_takeoff_value: added _current_rc_concrete_total,
  used it in both recalc_from_parameter and the dialog's initial value)
