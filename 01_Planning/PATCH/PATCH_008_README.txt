PATCH_008 — services/construction_cost_engine_v9_4.py: fix reinforcing-steel row not bridging to its own cost line (duplicate "鉄筋" audit entry)

Background: マルコさん asked why Module 1's summary shows ~22 items while
Module 5 shows ~38, expecting a roughly 1:1 handoff. Audited the full
Module 5 table-building code (module5/app.py's main breakdown tree +
services/construction_cost_engine_v9_4.py's audit builders) to answer this
precisely.

FINDING 1 (architecture, not a bug): Module 5 intentionally shows more
rows than Module 1 by design, in three tiers:
  1. ~8 PRICED cost lines (concrete, roofing, doors, interior finish,
     phenolic foam, XPS, reinforcing steel, formwork) -- each one sums/
     aggregates MANY individual Module 1 quantity rows into one number
     (e.g. "concrete" = sum of foundation + columns + beams + slabs +
     underground foundations + internal RC party-wall concrete).
  2. A "principal cost scope completeness" audit (cost_scope_completeness_audit)
     showing whether required scopes for the detected structural system
     (concrete/reinforcing_steel/formwork/etc.) are priced, unpriced,
     blocked, or have no quantity yet -- shown only when NOT already a
     clean priced line.
  3. A full row-by-row audit (quantity_cost_coverage_audit) of every
     Module 1 quantity_takeoff row that hasn't already been cleanly folded
     into tier 1 -- so nothing (even something excluded/unpriced) silently
     disappears from view.
This 3-tier design is why item counts differ; it is intentional, not a
translation gap.

FINDING 2 (real bug, fixed here): the specific "鉄筋" duplicate the マル
コさん pointed out (row 7 = 16.215 t, 確定・根拠単価, from tier 1; row 12
= 0.864 t, 保留・積算対象外, from tier 3) was NOT just tier-1-vs-tier-3
overlap by design -- it was a genuine bridging bug. Module 1's own
"reinforcement (provisional general specification)" row could never be
recognized by _takeoff_cost_key() as belonging to the "reinforcing_steel"
cost item, because that function's gate required one of
("総重量","合計","total","rollup","roll-up") to appear in the item text,
and "provisional general specification" contains none of them. The
otherwise-identical structural_steel gate two lines above it DID already
accept "provisional" (added in an earlier, unnumbered patch for AZRAS's
"structural steel (provisional total weight)" row) -- this asymmetry
meant reinforcing steel could never reach status="included_in_cost_line"
in the coverage audit and was always re-shown as a separate row, carrying
whatever quantity happened to be stored on it (in this project's case,
the stale 0.864 t value PATCH_007 already found and fixed the *display*
of, but which the coverage audit still read from the underlying stored
row).

Fix: added "provisional" to the reinforcing_steel token set in
_takeoff_cost_key(), mirroring the structural_steel gate immediately
above it.

Verified:
- _takeoff_cost_key({'item':'reinforcement (provisional general
  specification)','unit':'t'}) now returns 'reinforcing_steel' (was None).
- structural_steel's existing "provisional" gate is unaffected.
- A random individual member/detail row still returns None (no new
  double-counting risk introduced).
- Ran _quantity_cost_coverage_audit() end-to-end with a minimal realistic
  input: the reinforcement row now classifies as "included_in_cost_line"
  (was previously falling through to "blocked"), which module5/app.py's
  display loop already skips -- so this row will no longer appear a
  second time in the audit table once Module 5 recalculates the
  construction cost result for a project.
- pyflakes: no new issues. All dev_checks/ scripts still pass.

Note: this fix takes effect the next time Module 5's "建設費・工期を計算"
is re-run for a given project; it does not retroactively rewrite an
already-saved Module 5 result.

Files changed:
- services/construction_cost_engine_v9_4.py (_takeoff_cost_key only)
