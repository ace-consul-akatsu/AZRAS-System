PATCH_633 — Module 9: harden 地域係数登録状況 (Regional Coefficient Manager) against silent blank-table failures

Background:
User reported the "地域係数の登録状況" (Regional coefficient status) window
opening completely empty (no rows, seemingly no headers rendered) after
selecting 7 cities in Module 9. Standalone testing of the exact refresh()
logic against the real regional_suitability_database_v1.json (15 cities)
produced 15 correctly populated rows with no exception, so no defect was
found in the core logic itself with this data set.

However, RegionalCoefficientManager.refresh() had no error handling at
all: any single bad city entry (missing/duplicate "name", a registry
read failure, etc.) would raise partway through the population loop and
abort silently, since Tkinter's default callback exception handler
swallows the traceback and the packaged EXE has no visible console. The
result is exactly the symptom reported: the window opens (title/note
already drawn before the loop) but the table stays empty with no error
shown to the user.

Fix:
- Each city is now processed in its own try/except inside the loop, so
  one bad entry is skipped (and counted) instead of aborting the whole
  refresh.
- A duplicate or blank "name" used as the Treeview iid no longer raises
  a Tcl "item already exists" error; it is suffixed to stay unique.
- The whole refresh() is wrapped in a try/except that shows a normal
  error dialog (using the existing friendly_exception_text helper) if
  something still fails outright, instead of failing invisibly.

Verified (Xvfb, headless):
- 15/15 rows render with the real database, unchanged from before.
- With 1 malformed entry injected, 15/15 valid rows still render and the
  bad one is skipped (previously this configuration was not tested but
  the un-patched code would raise and abort the loop entirely).

Note: registering actual values in this table is optional — the design
intent (per the on-screen notice) is that missing values are left blank
and are not estimated; leaving all cities at "未登録/D" does not affect
Module 1/2/5 calculations.

Files changed:
- regional_analysis/module9_ui.py (RegionalCoefficientManager.refresh only)
